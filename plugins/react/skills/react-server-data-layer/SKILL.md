---
name: react-server-data-layer
description: "Prisma in Next.js Server Components and Server Actions: client singleton, server-only boundary, service layer, RSC N+1, request vs data cache."
metadata:
  category: backend
  tags: [nextjs, prisma, server-components, server-actions, data-layer, orm]
user-invocable: false
---

# Next.js Server Data Layer

> Load `Use skill: stack-detect` first to determine the project stack. Transaction boundaries are `backend-transaction-patterns`; pool arithmetic is `backend-connection-pooling`; migration sequencing is `backend-db-migration`; authorization depth (ownership checks, IDOR) is `task-react-review-security`. This skill owns only what changes because the caller is a Server Component or Server Action.

## When to Use

- Reading or writing the database from a Server Component, Server Action, or Route Handler
- Reviewing that access, or assessing whether it can be reused by a second client
- Structuring persistence so a future non-web client can reuse it
- Diagnosing repeated identical queries across a rendered page, or a client bundle that pulled in the ORM

Version scope: the examples are Next.js 15 and Prisma 5-6. Prisma 7 constructs the client with a driver adapter (`new PrismaClient({ adapter: new PrismaPg({ connectionString }) })`) imported from the generator's output path, not `@prisma/client`. Next 16 with Cache Components tags an ORM read with `"use cache"` + `cacheTag()` instead of `unstable_cache`, and a Server Action expires its own write with `updateTag(tag)` (`revalidateTag(tag, "max")` elsewhere). The rules hold on both.

## Rules

- The ORM client is a singleton created in one module that imports `server-only`. Never construct it per request, per component, or per action.
- **In development, cache the client on `globalThis`.** Hot module replacement re-evaluates modules on every edit, and a plain module-scope client leaks a new connection pool each time until the database refuses connections. A process-restart watcher (`tsx watch`, nodemon) is exempt: each restart is a fresh process, the guard is inert there, and its absence is not a finding.
- All database access lives under `src/server/<module>/`. Components, actions, and route handlers call those functions; none of them touch the ORM directly.
- Every exported service function is callable without a request context. Read cookies and headers in the caller and pass the resolved identity as an argument, or the same function cannot be reused by a Route Handler later. The identity resolver itself (`requireAdmin`, `getSession`) is the caller-side exception: it exists to read the request. In a client-only app, the module holding the HTTP calls (an api module, a thunk) is the data-access layer.
- Never return an ORM row across the client boundary. Select the fields the client needs, or map to an explicit shape.
- Fetch shared data once per request with request memoization, not once per component that needs it.
- Distinguish the two caches by lifetime: request memoization deduplicates within one render, the data cache persists across requests and needs explicit invalidation.

## Patterns

### Client Singleton That Survives Hot Reload

```ts
// src/server/db.ts
import "server-only";
import { PrismaClient } from "@prisma/client";

const globalForPrisma = globalThis as unknown as { prisma?: PrismaClient };

export const db = globalForPrisma.prisma ?? new PrismaClient(); // Prisma 7: pass { adapter }
if (process.env.NODE_ENV !== "production") globalForPrisma.prisma = db;
```

Without the `globalThis` guard, a few dozen edits during a development session exhaust the connection pool and the failure looks like a database problem rather than a reload problem.

### Service Layer as the Reuse Seam

The service function is written once and exposed two ways. This is the entire mechanism behind shipping web first and adding a non-web client later without rework.

```ts
// src/server/catalog/queries.ts
import "server-only";
import { cache } from "react";
import { db } from "@/server/db";

export const getDeckBySlug = cache(async (slug: string) => {
  return db.deck.findUnique({
    where: { slug, status: "published" },
    select: { id: true, name: true, description: true },   // explicit, never the whole row
  });
});
```

```tsx
// Server Component calls it directly
const deck = await getDeckBySlug(slug);
```

```ts
// Route Handler added later calls the same function
export async function GET(_: Request, { params }: { params: Promise<{ slug: string }> }) {
  const deck = await getDeckBySlug((await params).slug);
  return deck ? Response.json(deck) : new Response(null, { status: 404 });
}
```

Bad - the same logic inlined in the page, so the later handler has to reimplement it and the two drift:

```tsx
export default async function Page({ params }) {
  const deck = await db.deck.findUnique({ where: { slug: (await params).slug } });
}
```

### N+1 in a Component Tree

RSC makes N+1 easy to write and hard to see, because each query lives in a different file and nothing looks like a loop.

```tsx
// Bad - one query per row, issued from the child component
{questions.map((q) => <QuestionRow key={q.id} id={q.id} />)}
async function QuestionRow({ id }) {
  const choices = await db.choice.findMany({ where: { questionId: id } });
}
```

```tsx
// Good - one query in the service, called once by the parent, passed down as props
// src/server/catalog/queries.ts
export const getDeckQuestions = (deckId: string) => db.question.findMany({
  where: { deckId },
  select: { id: true, stem: true, choices: { select: { id: true, body: true } } },
});
// parent component
const questions = await getDeckQuestions(deckId);
{questions.map((q) => <QuestionRow key={q.id} question={q} />)}
```

Request memoization does not save you here: the arguments differ per row, so each call is a distinct cache entry and a distinct query.

### Which Cache

| Mechanism             | Lifetime         | Use for                                                | Invalidation             |
| --------------------- | ------------------ | -------------------------------------------------------- | -------------------------- |
| `cache()` from React  | One render pass  | Any lookup repeated within a render, per-user reads included | Automatic                |
| Data cache with a tag | Across requests  | Content that changes on publish, not per request        | `revalidateTag` on write |
| Neither               | None             | A read that runs once per request anyway                | n/a                      |

On 15, `fetch` is the only call the framework can tag for you, and only when you ask - `next: { tags: [...] }`, plus an opt-in to caching at all, since Next 15 leaves `fetch` uncached by default. An ORM query enters the tagged data cache through `unstable_cache`:

```ts
import { unstable_cache } from "next/cache";

export const getPublishedDecks = unstable_cache(
  () => db.deck.findMany({ where: { status: "published" }, select: { id: true, name: true } }),
  ["published-decks"],
  { tags: ["decks"] },
);
```

Wrapping a per-user query in the cross-request data cache can serve one user's data to another. The arguments you pass are part of the key, so a function taking `userId` caches per user correctly; the leak comes from identity the key never sees - a value read from module scope or closed over rather than passed in. `cookies()`/`headers()` inside a cached function throw at request time, which turns that mistake into an error rather than a leak - an auth helper that reads the cookie (Auth.js `auth()`) throws the same way. Report either outcome as `PerUserDataCached` at Blocker; the fix is identical. Wrapping a published-content query in request memoization only leaves every uncached request hitting the database. Both mistakes look like caching.

### Writes From Server Actions

```ts
"use server";
import { revalidateTag } from "next/cache";
import { publishBatch } from "@/server/authoring/mutations";
import { requireAdmin } from "@/server/identity/session";

export async function publish(batchId: string) {
  const admin = await requireAdmin();                 // authorize before anything
  const { deckIds } = await publishBatch(batchId, admin.id);
  revalidateTag("decks");                             // the list cached above
  for (const id of deckIds) revalidateTag(`deck:${id}`);
  return { ok: true };
}
```

The action authorizes, delegates to a service function, then invalidates. It contains no ORM call of its own. Revalidation happens after the write returns, never inside the transaction that performed it.

## Output Format

Emit one block per finding, ordered by severity. A finding is one defect with its own fix; when several Issue values describe the same root cause, emit one block carrying the most specific value at the highest applicable severity (the singleton-module trio `ClientNotSingleton`/`MissingHotReloadGuard`/`MissingServerOnly` is one root cause). Repeated call sites of one Issue with one fix pattern merge into one block listing each Location, even when each site is edited separately. Otherwise two defects are separable - and stay separate blocks, different Issue values on one line included - when fixing one leaves the other in place; the singleton trio merges because one fix (a single guarded `server-only` client module that every caller imports) clears all three. Open with `Scope: <files reviewed>` whenever this skill produces its own output - on the stack-neutral branch, `Scope: stack-neutral review (not App Router - Next-specific rules skipped) - <files reviewed>`; a consuming workflow that supplies its own scope line takes precedence, and synthesizes its own summary, so do not duplicate one for it. After the last finding come, in this order: any `Not assessed:` line (required-but-unseen infrastructure, not a guessed finding), any `Notes:` line (off-enum observations, e.g. an authorization gap -> `task-react-review-security`), for a reuse consult only, `Reuse readiness: {ready | not ready - <blocker>}` grounded in the service-layer and no-request-context rules (a sound service with no HTTP entry point yet is `ready`, the missing endpoint named in the justifying sentence), one verdict per surface when the consult names several (`order history: ready; cancel order: not ready - <blocker>`), one or two justifying sentences may follow, then `Tally: <N> findings (<B> Blocker, <H> High, <M> Medium, <L> Low)` last.

```
Scope: <files reviewed>

- Location: <file>:<line or symbol>
  Issue: {OrmInComponent | ClientNotSingleton | MissingHotReloadGuard | MissingServerOnly | RawRowToClient | OverbroadSelect | RscNPlusOne | WrongCacheScope | PerUserDataCached | ActionBypassesService | RequestContextInService | MissingRevalidation}
  Severity: {Blocker | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name>

Not assessed: <required-but-unseen infrastructure, or a referenced module whose behaviour decides a severity; omit when none>

Notes: <off-enum observations naming the owning concern; omit when none>

Reuse readiness: {ready | not ready - <blocker>}

Tally: <N> findings (<B> Blocker, <H> High, <M> Medium, <L> Low)
```

Severity:

- **Blocker**: per-user data written to the cross-request data cache (`PerUserDataCached`); an ORM row containing secret fields returned across the client boundary (`RawRowToClient`); ORM client imported into a Client Component (`MissingServerOnly` with the client import observed).
- **High**: ORM client constructed per file or without the hot-reload guard (`ClientNotSingleton` / `MissingHotReloadGuard`); database access outside `src/server/` (`OrmInComponent` in view code, `ActionBypassesService` in any HTTP-facing entry - action, route handler, controller; `OrmInComponent` also covers a shared non-entry module, such as a cache wrapper or helper, that queries the ORM outside `src/server/`); a Server Action mutating tag-cached content without a following revalidation (a write that touches no cached surface has nothing to revalidate); a whole row with no secret fields crossing the client boundary (`RawRowToClient` - with the model's fields unknown, name the Blocker escalation in the block).
- **Medium**: RSC N+1; a service function reading cookies or headers directly; wrong or absent cache scope with no leak (`WrongCacheScope` covers a per-render lookup duplicated for want of `cache()`); a server module missing `import "server-only"` with no observed client import.
- **Low**: an over-broad select whose rows never cross the client boundary (`OverbroadSelect`; a crossing makes it `RawRowToClient`).

App Router = an `app/` or `src/app/` directory with a root layout (`layout.{tsx,jsx,js}` at its top, or atop each route group) - beside `pages/` the tree is hybrid and the App Router rules apply to `app/`; Pages Router = `pages/` or `src/pages/` alone. `stack-detect` reports `React (Next.js)` for both. If the project is not Next.js App Router, apply only the stack-neutral rules - singleton client (the hot-reload guard only under HMR dev), explicit field selection, no persistence logic in view code (HTTP handlers and controllers count as view code) - opening with the stack-neutral `Scope:` line above. The block shape, merge rules, closing lines, and Issue enum apply unchanged - `ActionBypassesService` names any HTTP-facing entry. Emit `No server data layer findings (not App Router).` only when those rules are clean; the `Scope:` opening and the `Not assessed:` / `Notes:` / `Reuse readiness:` / `Tally:` closing lines still apply to a clean run - only the finding blocks are omitted. Read the retained rules by their behaviour, not their ORM wording: with no database in the project, "no persistence logic in view code" covers any data-access call (HTTP client included) made directly from a component.

## Avoid

- Passing an ORM client or a transaction handle as a prop
- `select: undefined` on a model holding credentials, tokens, or internal flags
- Reaching for the data cache to fix an N+1; the fix is one query, not a cached bad query
- Service functions that call `cookies()` or `headers()`, which makes them unusable from any other caller
