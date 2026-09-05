---
name: react-server-testing
description: "Test Next.js server code: real-database integration tests, per-test isolation, Server Action and Route Handler tests, RSC testing strategy."
metadata:
  category: testing
  tags: [nextjs, testing, integration, testcontainers, server-actions, vitest]
user-invocable: false
---

# Next.js Server Testing

> Load `Use skill: stack-detect` first to determine the project stack. Component, hook, and browser testing are owned by `react-testing-patterns`. This skill owns tests that exercise server code or touch a database.

## When to Use

- Testing a Server Action, Route Handler, or anything under `src/server/`
- Standing up database-backed tests
- Deciding what to test directly versus through the browser

## Rules

- Test service functions directly. They are plain async functions with no request context, which is what makes them the cheapest thing in the codebase to test.
- **Use a real database, never a mocked ORM.** A mocked client asserts that you called it the way you expected, which is the one thing that was never in doubt. Constraints, cascades, transactions, and `null` handling are what break.
- Every test starts from a known state and leaves none behind. Choose one isolation mechanism and apply it everywhere.
- Mock at the network edge only: external HTTP, payment providers, mail - plus two sanctioned stubs: the session boundary (`requireUser`/`requireAdmin`) and Next framework modules with request-scoped side effects (`next/cache` revalidation, which throws outside a request). Never mock other own modules to make a test pass.
- **Async Server Components are not unit-testable** with a component renderer. Test the data function underneath, and cover the rendered page with a browser test.
- Route Handlers are tested by constructing a `Request` and calling the exported method. No HTTP server is needed. A handler that reads `cookies()` or `headers()` from `next/headers` needs the same session-boundary stub as a Server Action. Webhook handlers run real signature verification against a test-signed payload (e.g. Stripe's test header helper), never a mocked verifier, and get a replay test: the same event delivered twice, the second a no-op - which forces event-id dedupe in the handler.
- A Server Action's authorization path is a required test case, not an optional one. Assert that an unauthorized caller is rejected before asserting that an authorized one succeeds.

## Patterns

### Isolation: Pick One

| Mechanism             | Speed  | Catches                             | Cost                                                    |
| --------------------- | ------ | ------------------------------------- | --------------------------------------------------------- |
| Transaction rollback  | Fast   | Most logic bugs                     | Cannot test code that commits its own transaction       |
| Truncate between tests | Medium | Everything, including commits       | One `TRUNCATE ... CASCADE` covers FK order; names need quoting |
| Fresh container per file | Slow | Everything, including migrations    | Only worth it for the migration suite                   |

Default to truncation. Transaction rollback is faster but silently cannot test the transaction boundary itself, which is exactly where the expensive bugs live.

### Database Setup

```ts
// vitest.server.config.ts - own node-env project beside the jsdom component config
// globalSetup: ["test/global-setup.ts"], setupFiles: ["test/setup.ts"]

// test/global-setup.ts - main process, before workers fork
import { PostgreSqlContainer } from "@testcontainers/postgresql";

export default async function () {
  const container = await new PostgreSqlContainer("postgres:16-alpine").start();
  process.env.DATABASE_URL = container.getConnectionUri();
  await runMigrations();                      // e.g. execSync("npx prisma migrate deploy") - the real migrations, not db push
  return async () => { await container.stop(); };
}
```

```ts
// test/setup.ts - per test file
beforeEach(async () => {
  // Introspect information_schema for BASE TABLEs only (views cannot be truncated),
  // excluding _prisma_migrations; a hand-maintained list rots silently.
  const tables = await publicTableNames();
  const quoted = tables.map((t) => `"${t}"`).join(", ");   // Prisma's PascalCase names need quoting; `user` is reserved
  await db.$executeRawUnsafe(`TRUNCATE ${quoted} RESTART IDENTITY CASCADE`);
});
```

The container starts in `globalSetup` because that runs in the main process before workers fork: workers inherit `DATABASE_URL`, so the module-scope client singleton captures the container URI. Starting it in a per-file `beforeAll` both spins one container per file (the slow row of the isolation table) and loses the race with the singleton, which reads the env at import time.

Running the real migrations rather than a schema sync means the test suite also verifies that the migrations produce the schema the code expects, which is otherwise only discovered in production.

One shared database plus parallel workers race on truncation: set `fileParallelism: false`. Per-worker schemas are the faster alternative but need more than a name: `globalSetup` migrates the default schema only, so each worker must create its own schema and run the migrations against it, then rewrite `DATABASE_URL` before the client module is imported.

### Testing a Service Function

```ts
it("publishes only reviewed questions", async () => {
  const deck = await seedDeck();
  await seedQuestion({ deckId: deck.id, status: "draft", reviewedAt: null });
  const reviewed = await seedQuestion({ deckId: deck.id, status: "draft", reviewedAt: new Date() });

  const { publishedCount } = await publishBatch(deck.batchId, adminId);

  expect(publishedCount).toBe(1);
  expect(await getPublishedIds(deck.id)).toEqual([reviewed.id]);
});
```

### Testing a Server Action

A Server Action is an async function, so it is called directly. What it needs is a request context, which is supplied by stubbing the session boundary rather than the database.

```ts
import { requireAdmin } from "@/server/identity/session";
import { publish } from "@/app/actions/publish";
import { ForbiddenError } from "@/server/identity/errors";
import { countPublished } from "test/helpers";

vi.mock("@/server/identity/session", () => ({
  requireAdmin: vi.fn(),
  requireUser: vi.fn(),
}));

it("rejects a non-admin caller", async () => {
  vi.mocked(requireAdmin).mockRejectedValue(new ForbiddenError());
  await expect(publish("batch-1")).rejects.toThrow(ForbiddenError);
  expect(await countPublished()).toBe(0);        // assert no write happened
});
```

The second assertion matters. A test that only checks the thrown error passes even if the action deleted everything before throwing.

### Testing a Route Handler

```ts
import { POST } from "@/app/api/report/route";

it("rejects an unsigned payload", async () => {
  const res = await POST(new Request("http://test/api/report", {
    method: "POST",
    body: JSON.stringify({ questionId: "q1", reason: "typo" }),
  }));
  expect(res.status).toBe(400);
});
```

### The Server Component Boundary

```
Bad   render(<DeckPage params={...} />)      -- async component, renderer cannot await it
Good  test getDeckBySlug() directly, then cover the page with one browser test
```

Splitting the page's data function out of the component, as `react-server-data-layer` requires, is what makes this workable. A page whose query is inlined has no unit-testable surface at all.

## Output Format

When standing up testing (authoring), emit in this order: the chosen isolation mechanism with the one-line reason the Isolation table gives for it; each setup file in full under a `### <file path>` heading; a `### Tests to Write` list naming, for every surface in scope, the test and the assertion that matters (the authorization case first wherever one applies); then this assessment block covering what the authored setup does not yet cover, its headers describing that setup. Where a required case cannot pass against the code as written - an authorization test on a function with no authorization - list the test in `Tests to Write` marked `(fails until <the change it forces>)` and raise the underlying defect as a Gap. When assessing, headers describe the layer as found: a split suite lists each observed value (`mocked (unit) / real (containerized, integration)`); with no server tests, Isolation is `none` and Database is `none - no server tests exist`. Open the block with `Scope: <files assessed>` directly under the heading and, when the caller asked a direct question (a yes/no or either/or ask), one `Verdict:` line answering it. Order gaps by severity, blast radius breaking ties (payment and webhook surfaces first), one gap per exported function or route - two functions in one file are two gaps, and merge only when a single test would close both. Absent or defective infrastructure is one gap of its own listing each defect; per-surface gaps assume it lands.

```
## Server Test Assessment

**Isolation:** {transaction rollback | truncate | fresh container | none}

**Database:** {real (containerized) | real (shared test DB) | mocked | none - no server tests exist; name each when the suite is split, e.g. `mocked (unit) / real (containerized, integration)`}

**Client-side coverage:** {present (not assessed - client testing is a separate concern) | none present | n/a (authoring server tests)}

### Gaps

- [Severity: High | Medium | Low] {function or route} - {gap description}
  - Missing: {one or more of: authorization case | database-backed test | isolation | migration coverage | error path | ownership/IDOR case | sanctioned-mock breach (a verifier, ORM, or own module mocked where the real thing must run) | harness (container lifecycle, env race, stale table list)}
  - Risk: {what ships broken}
  - Recommendation: {concrete test to add}

### No Gaps Found

{State explicitly when server coverage is adequate - do not omit silently.}
```

Severity:

- **High**: a mutating Server Action or Route Handler with no authorization test; a mocked ORM standing in for database behavior; no isolation between tests; a setup race that can point destructive cleanup (TRUNCATE) at a non-test database.
- **Medium**: happy path only; migrations not exercised; ownership and IDOR paths untested.
- **Low**: missing edge cases on an otherwise covered function.

Omit "No Gaps Found" when gaps were listed. A clean run still emits `Scope:`, the `Verdict:` line when one was asked for, all three header fields, and `No Gaps Found`; only the gap entries are omitted. If the project has no server surface, emit `Scope:`, the `Verdict:` line when one was asked for, and `No server test findings (no server surface).` - the three header fields and the gap list are omitted; a `Verdict:` answers the server-test question only, naming any part of the caller's ask that falls outside this skill.

## Avoid

- Asserting that the ORM was called with particular arguments; assert the resulting state instead
- Sharing one database state across an ordered test file, which makes a single failure cascade
- Testing Server Actions through the browser only; the authorization cases are hard to reach and slow to run there
- Seeding through raw inserts that bypass the constraints the production write path must satisfy
