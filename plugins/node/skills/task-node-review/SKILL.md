---
name: task-node-review
description: Node.js/NestJS/Express code review - event-loop blocking, async pitfalls, ORM leaks, missing guards, validation; spawns perf/security/obs agents.
agent: node-tech-lead
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Node.js Code Review

## Purpose

Node.js-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Node-specific correctness, architecture, AI-quality, and maintainability checks (event-loop blocking, sync-in-async mixing, fat controllers / route handlers, ORM leak in API responses, missing `ValidationPipe` whitelist / `.strict()` Zod schemas, missing guards / auth middleware, anemic services hiding behavior in helpers, NestJS request-scoped provider misuse, prototype-pollution surfaces). Coordinates Node-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Node.js. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a NestJS or Express PR before merge
- Post-AI-generation quality gate on a Node change set
- Architecture drift detection in a Node codebase
- Pre-merge risk assessment on a Node branch

**Not for:**

- Pre-implementation feature design (use `task-node-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-node-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-node-review-perf`, `task-node-review-security`, or `task-node-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Node staff-level review                                    | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                 |
| --------------- | ------------------------------------------------------------------------- |
| Core            | Phases A-E only (Node-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-node-review-perf`                         |
| + Security      | Core + parallel subagent: `task-node-review-security`                     |
| + Observability | Core + parallel subagent: `task-node-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel Node subagents) |

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (Node-tuned):**

- File uploads (`multer`, NestJS `FileInterceptor`, `@UploadedFile()`), auth strategy / guard changes (`AuthGuard('jwt')`, `JwtStrategy`, `requireAuth` middleware), DTO / Zod schema changes, raw SQL via `prisma.$queryRawUnsafe` / `repository.query`, secrets in `.env` / config, BullMQ jobs consuming user-supplied input, `Object.assign(target, req.body)` patterns → auto-add **+Security**
- New Prisma / TypeORM migration, new ORM query (`findMany` / `find()` / `createQueryBuilder`), new `include` / `relations`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `lru-cache` / Redis read paths → auto-add **+Perf**
- New service / module, new external client (`axios.create`, `undici` Pool, `node-fetch` agent), new BullMQ producer / processor, change to logging config (`pino` / `winston` setup, `LOGGING` dict), new `prom-client` registration, new lifecycle hook (`OnModuleInit`, `OnApplicationBootstrap`) → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                   | Meaning                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-node-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-node-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-node-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-node-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-node-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-node-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every subsequent step (think before acting, surgical changes, surface confusion, push back when the user is likely wrong). When invoked as a subagent of `task-code-review`, accept the parent's confirmation that this skill is already loaded; do not re-load.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Node.js / TypeScript. If invoked as a delegate of `task-code-review` (parent already detected Node), accept the pre-detected stack and skip re-detection. If the detected stack is not Node, stop and tell the user to invoke `/task-code-review` instead.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express (`express` in deps without NestJS). Detect ORM: Prisma vs TypeORM. Record `Framework: NestJS | Express | mixed`, `ORM: Prisma | TypeORM`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. Make this explicit because the default of "skip if user did not pass `+security` etc." silently misses the cases where the change itself signals the need.

For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals so the Summary documents why the chosen scope was correct

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`. If the user passed a scope and signals contradicted it, surface a one-line note so reviewers see what was deliberately deferred.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth strategies / guards, middleware, API contracts, shared base classes, `app.module.ts` / `app.ts`, Prisma / TypeORM migrations), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 4.5 - Re-evaluate Depth After Phase A

If `Blast Radius` (from Phase A) is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors (historical pattern matching, cross-PR context, anemic-domain assessment) are in scope for the rest of the review.

### Phase B - Node Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness - through a Node lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding Jest coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication (JWT / Passport / `AuthGuard`), authorization (guards / `requireAuth` middleware), money or billing flows, data-integrity writes (multi-table transactions, state machines), BullMQ jobs that mutate data, migrations that change column semantics. Do not bury this finding in Key Takeaways - a separate, named entry in Findings.

**Node-specific correctness checks (both frameworks):**

- [ ] **TypeScript strict + async discipline**: `strict: true` not silently relaxed (`@ts-ignore` / `as any` outside test setup flagged); every `Promise`-returning function `await`-ed; `@typescript-eslint/no-floating-promises` enabled. Depth in `node-typescript-patterns`
- [ ] **No event-loop blocking in request paths**: sync `fs.readFileSync` / `crypto.pbkdf2Sync` / large `JSON.parse` / large regex - flagged. Depth (impact heuristic, worker_threads, AbortSignal) is owned by `task-node-review-perf`; this checklist owns presence/absence
- [ ] **Validation strict-mode wired**: NestJS `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))` in `main.ts`; Express Zod schemas use `.strict()`. Absence is a critical correctness + security gap
- [ ] **Authorization + IDOR**: every endpoint has `@UseGuards(...)` (NestJS) or `requireAuth` middleware (Express); per-owner / per-tenant data scoped via `user.sub` / `tenantId` at the repository - `AuthGuard('jwt')` alone proves authentication, not object access. Depth in `task-node-review-security`
- [ ] **SSRF + edge middleware presence**: user-controlled values in outbound URLs flagged (presence/absence here, depth in `task-node-review-security`); `helmet`, CORS allowlist, body size limits (`express.json({ limit })`) confirmed when app construction changes
- [ ] **No ORM entities returned from endpoints + DTO field hygiene**: controllers return DTOs / response classes (NestJS `@Exclude()` + `ClassSerializerInterceptor`, or explicit Response DTOs); Express maps via typed mappers. Compare the response DTO against the entity's columns and flag `internalNotes`, `auditLog`, `passwordHash`, `mfaSecret`, `isAdmin`, `internalCreatedBy` on the wire - returning a Prisma model directly leaks whatever the schema has
- [ ] **Transactions + post-commit dispatch**: writes that need atomicity wrapped in `prisma.$transaction` / `dataSource.transaction`; `queue.add(...)` / external HTTP / mailers happen **after** the transaction resolves, never inside (worker may pick up before commit). Depth in `node-bullmq-patterns` and the perf workflow
- [ ] **HTTP idempotency on POST/PUT side-effect endpoints**: payment, order-create, refund, external-notify endpoints accept an `Idempotency-Key` header and dedupe via DB unique constraint or Redis `SET NX EX`. **Distinct** from BullMQ `jobId` dedup (worker-side) - the HTTP key protects the client-server boundary
- [ ] **New ORM column with predicate use**: any new Prisma `@db.*` / TypeORM column referenced in `where` / `orderBy` / `groupBy` has an index migration in the same PR, or an explicit "indexed later" note
- [ ] **Error handling + promise rejections**: NestJS `@Catch` filters cover validation / not-found / unauthorized / forbidden / unique-constraint with a consistent shape; Express has a 4-arg global error middleware. No `catch (e) { console.log(e) }` swallowing root causes; Express async handlers wrapped via `asyncHandler` or covered by global error middleware (floating-promise rejection is a silent-death surface)
- [ ] **Migration PRs (any change in `prisma/migrations/` or `src/migrations/`)**: see the Migration PRs subsection below

**Migration PRs (any change under `prisma/migrations/` or `src/migrations/`):**

- [ ] Two-phase deploys for column rename / drop (add new → backfill → cut over → remove old)
- [ ] `NOT NULL` on existing columns added via two-step (add nullable → backfill → set NOT NULL via separate migration)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); Prisma via `--create-only` then manual edit; TypeORM via `queryRunner.query('CREATE INDEX CONCURRENTLY ...')`
- [ ] **`SET lock_timeout`** before DDL on large tables to fail fast
- [ ] Foreign keys added with validation deferred (or as a separate validate step)
- [ ] Data migrations isolated from DDL migrations; long-running data backfills not in the same migration as the schema change; backfills via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] Rollback path documented or verified
- [ ] No `synchronize: true` (TypeORM) or `prisma db push` patterns in non-dev environments
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `node-migration-safety` for canonical safe-migration patterns

**Concurrency safety:**

- [ ] No mutable global state in modules (`let cache: Record<string, T> = {}` mutated by route handlers); if state is required, it is module-level constant, encapsulated in a class with explicit lifecycle, or in a singleton service
- [ ] Race-prone updates (counters, balance changes, state transitions) use database-level locking (`SELECT ... FOR UPDATE`, Prisma `$queryRaw`SELECT ... FOR UPDATE``, TypeORM `setLock('pessimistic_write')`, or optimistic version field)
- [ ] Cache writes thread-safe; cache keys deterministic; no race window between cache miss and cache fill on hot keys (use single-flight via in-flight `Map<string, Promise<T>>` or Redis `SET NX EX`)
- [ ] HTTP clients (`axios.create()`, `undici` Pool) shared at module level - per-request instantiation breaks connection reuse and triggers excess TCP / TLS overhead

Use skill: `node-prisma-patterns` for canonical Prisma correctness patterns (Prisma projects).
Use skill: `node-typeorm-patterns` for canonical TypeORM patterns (TypeORM projects).
Use skill: `node-typescript-patterns` for any new or modified TypeScript code.
Use skill: `node-bullmq-patterns` for any new BullMQ job or dispatch path.

### Phase C - Node Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Node-specific architecture checks:**

- [ ] **Layering (NestJS)**: controller → service → repository → entity. No business logic in controllers; no `axios` / `fetch` calls in repositories; no DTO construction in repositories. Repositories return entities or domain types; mapping to response DTOs happens at the service or controller boundary, not in the repository
- [ ] **Layering (Express)**: route → controller (or service) → repository → entity. No business logic in route definitions; service layer for cross-entity orchestration
- [ ] **Service-layer discipline**: any controller / route handler with > 10 lines of orchestration is extracted to a service; services expose intention-revealing names (`fulfillOrder(orderId)` not `processOrderStep2`); cross-entity orchestration lives in a service, not in TypeORM `@AfterInsert` listeners or Prisma middleware
- [ ] **Anemic domain antipattern (deep depth only)**: when reviewing in `deep` mode and historical pattern matching shows business rules accumulating in services while ORM models stay as pure data containers (Prisma generated types, TypeORM `@Entity` with no methods), flag for refactor via `task-node-refactor`. Do **not** raise on a single PR's evidence alone - one PR adding a service method is not "anemic accumulation."
- [ ] **NestJS DI discipline**: constructor injection (`constructor(private readonly orders: OrdersService) {}`) preferred; module imports declare dependencies explicitly; no `Reflect.getMetadata` magic outside platform code; circular dependency between modules flagged - resolve via `forwardRef` only as a last resort, prefer extracting a shared module
- [ ] **NestJS request-scoped providers**: `@Injectable({ scope: Scope.REQUEST })` used only when truly needed (per-request transaction, multi-tenant context); flagged for default-singleton scope - request scope creates a fresh instance per request and bypasses Nest's DI optimizations
- [ ] **Settings discipline**: typed settings via `@nestjs/config` `ConfigService` (NestJS) with a Joi / Zod schema; for Express, `dotenv` + a typed config module (`config/index.ts` returning a frozen typed object); no `process.env.X` sprinkled across files - centralize so missing-at-startup fails fast
- [ ] **Module / package boundaries**: feature-module layout (`src/orders/{controller,service,repository,dto}.ts`) preferred over layer-package layout (`src/controllers/`, `src/services/`); cross-feature imports go through public service interfaces (NestJS module exports), not direct repository imports
- [ ] **Multi-tenant isolation**: tenant scoping enforced at the repository layer (Prisma middleware or extension injecting `tenantId`; TypeORM `@BeforeInsert`/`@BeforeUpdate` listeners or QueryBuilder helpers), not at the controller / route layer alone
- [ ] **Read replica / multi-DB**: when the app uses Prisma with `directUrl` for migrations and a separate read-replica DataSource (TypeORM), queries declare their target explicitly; no surprise cross-database joins
- [ ] **TypeORM listener / Prisma middleware discipline**: listeners (`@AfterInsert`, `@BeforeUpdate`) and Prisma middleware used for genuinely cross-cutting concerns (audit, soft-delete, search index sync) - not as a hidden control-flow mechanism dispatching emails / BullMQ jobs. Move business logic to explicit service calls

**Multi-service PRs (when change spans 2+ services or this Node app + a separate service):**

- API contract compatibility checked (OpenAPI diff, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` for verbosity, over-engineering, and simplification opportunities. Then load **one** framework-specific necessity skill based on Step 2's detection:

- **NestJS:** Use skill: `node-nestjs-overengineering-review` (validator/ORM/DB/TS-strict-null redundancy, defensive DI guards, single-impl interfaces, `Scope.REQUEST` on stateless providers, `Result<T,E>`, broad `catch (e)`).
- **Express:** Use skill: `node-express-overengineering-review` (Zod/TypeORM/DB redundancy, defensive null on typed values, middleware-of-one, Repository wrappers over `Repository<T>`, custom error hierarchies without `instanceof` branching, broad `catch (e)`).

**Additional Node AI smells not covered by the above:**

- [ ] **Redundant mapping layers**: `Entity -> DomainObject -> ServiceDTO -> ResponseDto` when one would suffice
- [ ] **Test verbosity**: `beforeEach` > 30 lines for a single assertion; full deep-equal `expect(response.body).toEqual({...})` when a few field assertions would suffice
- [ ] **Comment cruft**: JSDoc on private helpers that repeats the signature; auto-generated TODOs left in
- [ ] **`as any` / `as unknown as T` proliferation**: in non-test code, `as any` to bypass a real type bug is a finding

### Phase E - Node Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Node-specific maintainability checks:**

- [ ] **Naming conventions**: services describe their operation (`orderFulfillment.service.ts` over `orderHelper.service.ts`); DTOs named after their role (`CreateOrderDto`, `OrderResponseDto`); no `Util` / `Manager` / `Helper` modules accumulating unrelated functions; `_private` prefix or module-private export discipline
- [ ] **Magic numbers / strings**: extracted to module-level constants or config keys; date/time constants use `60_000` or `Duration` helpers, not raw `60000` mid-expression
- [ ] **Hardcoded URLs / credentials**: in env vars / config, not inline in code
- [ ] **Function length**: functions > 30 lines reviewed for extraction; functions > 60 lines flagged unless they are a clearly orchestrating service function calling intention-revealing private helpers
- [ ] **Duplicated query logic**: same `where` / `find` predicate in 3+ places extracted to a repository method or QueryBuilder helper
- [ ] **Logging hygiene**: surface obvious offenders as Core findings at `[Suggestion]` - `console.log(...)` in production code path, log lines without correlation IDs, wrong log levels. The observability subagent owns depth (sampling, structured-field schemas, OTel correlation IDs, log redaction); do not duplicate that audit here. If observability is not in scope this run, still surface the obvious offenders so they are not lost.

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-node-review-observability` subagent owns the depth review).

### Step 5 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                      |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-node-review-perf`                                                                             |
| Core + Security      | 1 subagent running `task-node-review-security`                                                                         |
| Core + Observability | 1 subagent running `task-node-review-observability`                                                                    |
| Full                 | 3 subagents running `task-node-review-perf`, `task-node-review-security`, `task-node-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 3 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Node.js / TypeScript) and detected framework (NestJS / Express / mixed) and ORM (Prisma / TypeORM) so the subagent skips its own `stack-detect` and framework branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a synchronous `crypto.pbkdf2Sync` inside an async handler can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Node idiom: blocking `crypto.pbkdf2Sync` in async handler, missing `@UseGuards`, ORM entity returned from controller, BullMQ `queue.add` inside transaction, `ValidationPipe` missing `whitelist: true`, `Object.assign(target, req.body)` prototype-pollution surface, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Node change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

### [Question] file:line

- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on - author intent, business rule, deployment topology, etc.]

_Use [Question] when the change is genuinely ambiguous and the right action depends on author intent. Do NOT use it as a softer Blocker._

## Architecture Notes

_Summary commentary on systemic patterns. **Do not restate individual findings here.** If a pattern is severe enough to be a finding, keep it in Findings and reference it by file:line from these notes. Use this section for cross-cutting observations the per-file findings cannot carry on their own._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes - summary commentary, not duplicated findings._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Replace `crypto.pbkdf2Sync(pwd, salt, ...)` with `await promisify(crypto.pbkdf2)(pwd, salt, ...)` in AuthService.hashPassword"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Node conventions, not generic backend conventions
- Provide actionable feedback with TypeScript code examples
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Node subagent rather than duplicating the check here

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 (or accepted from parent dispatcher)
- [ ] Stack confirmed (Step 2); framework and ORM recorded
- [ ] `review-precondition-check` ran (Step 3); diff and commit log read once and reused by all phases and subagents
- [ ] Scope auto-escalation evaluated (Step 4); promotion or `core-only` suppression recorded in Summary with firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick` (Step 4.5)
- [ ] Risk level and blast radius stated before any line-level findings (Phase A)
- [ ] Phase B Node correctness checklist applied (TS strict + async discipline, ValidationPipe/Zod strict, authn + authz/IDOR, SSRF + edge middleware, ORM leak + DTO field hygiene, transaction + post-commit dispatch, new column predicate index, error handling)
- [ ] Phase B migration safety delegated to `node-migration-safety` when migrations changed
- [ ] Phase C architecture checks applied (layering, anemic domain, settings discipline, listener/middleware discipline, package boundaries, multi-tenant)
- [ ] Phase D applied via `complexity-review` + the framework-matching necessity skill (`node-nestjs-overengineering-review` or `node-express-overengineering-review`); Node AI smells from Phase D (mapping layers, test verbosity, comment cruft, `as any`) addressed
- [ ] Phase E maintainability checks applied (naming, magic numbers, function length, structured logging)
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk; every finding has a label, file:line, and actionable Node fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, subagents ran in parallel and received the pre-resolved diff/log handle plus framework/ORM detection (Step 5)
- [ ] Subagent findings merged with deduplication and highest-severity-wins; raw subagent reports not appended (Step 6)
- [ ] Any failed/missing subagent scope noted as `Scope incomplete: <scope>`
- [ ] Next Steps section produced (tagged `[Implement]` / `[Delegate]`, ordered Blocker > High > Suggestion) unless no actionable findings exist
- [ ] Review report written via `review-report-writer`; confirmation line printed (Step 7)

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Node idiom exists (say "extract to a service module", not "extract to a helper class")
- Providing vague feedback without a concrete Node fix ("this could be better")
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending sync `fs.readFileSync` / `crypto.pbkdf2Sync` in request paths, `eval` / `new Function` on untrusted input, or `Object.assign(target, req.body)` as acceptable patterns
