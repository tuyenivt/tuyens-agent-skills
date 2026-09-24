---
name: task-node-review
description: Node.js/NestJS/Express PR review - event-loop blocking, async pitfalls, ORM leaks, guards, validation; spawns perf/security/obs/reliability lenses.
agent: node-tech-lead
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Code Review

Staff-level Node.js / NestJS / Express review umbrella: correctness, architecture, AI-generated-code quality, and maintainability, with perf / security / observability / reliability lenses spawned in parallel when scope warrants. Stack-specific delegate of `task-code-review`.

## When to Use

- Pre-merge review of a NestJS or Express PR; post-AI-generation quality gate; architecture-drift detection

**Not for:** pre-implementation design (`task-node-implement`), single-error debugging, new-system architecture, or a single-scope review - invoke `task-node-review-perf` / `-security` / `-observability` / `-reliability` directly.

## Depth and Scope

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Steps 1-10; Step 5 loads the atomics whose area the diff touches |
| `deep` | Architecture PRs, post-incident, Principal sign-off, or auto-promoted | Step 5 consults every listed atomic and reads each touched file in full plus the code the diff calls into; Step 6 adds the anemic-domain check; lenses run at `deep` |

**Auto-promote to `deep`** after Step 4 when Blast Radius is Wide or Critical (Step 4 says which value to read). On round 2+ nothing is inherited; when the resolved depth falls below the checkpoint's, note `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

| Scope | What runs |
|-------|-----------|
| Core | Steps 1-10 |
| +Perf / +Sec / +Obs / +Rel | Core + that lens (Step 9) |
| Full | Core + all four lenses in parallel |

Default: **Core with auto-escalation**; `core-only` suppresses it. Auto-escalation signals:

- **+Sec:** file uploads (`multer`, `FileInterceptor`, `@UploadedFile()`), auth strategy / guard changes (`AuthGuard('jwt')`, `JwtStrategy`, `@Public()`, `requireAuth`), DTO / Zod schema changes, raw SQL (`$queryRawUnsafe`, `repository.query`), secrets in env / config, BullMQ consuming user input, `Object.assign(target, req.body)` or a spread of `req.body` / a DTO into a write
- **+Perf:** new Prisma / TypeORM migration, new ORM query (`findMany` / `find` / `createQueryBuilder`), new `include` / `relations`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `lru-cache` / Redis read paths
- **+Obs:** new service / module, new external client (`axios.create`, `undici` Agent), new BullMQ producer / processor, logging config change (`pino` / `winston`), new `prom-client` metric, new lifecycle hook (`OnModuleInit`, `OnApplicationBootstrap`)
- **+Rel:** new outbound call with no total deadline (`fetch` / `undici.request` / axios without `signal: AbortSignal.timeout(ms)` - axios `timeout` and undici's timers are idle timers), new `opossum` / `cockatiel` / `p-retry` config, BullMQ processor without an idempotency guard, unbounded `Promise.all` over a collection, missing `SIGTERM` drain, `queue.add` / a payment-provider call / `mailer.send` inside `$transaction` / `dataSource.transaction`, a new `@Cron` / `setInterval` job
- Two or more categories in the resolved union (user flags + firing signals) -> **Full**. The Summary `Scope:` line and the Step 10 writer mapping are single-valued, so a two- or three-lens union never renders as a list.

## Invocation

`/task-node-review [<branch>|pr-<N>] [--base <branch>] [--req <path>] [+sec|+perf|+obs|+rel|full|core-only] [standard|deep]`

Defaults to the current branch vs its base; fails fast on trunk. `pr-<N>` is a local branch the user fetched. `--req <path>` names a requirement source (ticket export, PRD, spec) for Step 3.7; without it, `review-change-intent`'s own source ladder decides. The workflow reads through ref-qualified git and never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-detected stack from a parent. Not Node -> stop and recommend `/task-code-review`.

Record from evidence, and pass all of it to every lens:

- `Framework`: NestJS (`nest-cli.json` or `@nestjs/core`), Express (`express` without `@nestjs/core`), or `mixed` (both, as separate apps) - on `mixed`, each step applies the idioms of the app a changed file belongs to.
- `ORM`: Prisma (`@prisma/client` / `prisma/schema.prisma`; its major - Prisma 7 / `@prisma/adapter-*` pools through the adapter), TypeORM (`typeorm`; its driver, `pg` or `mysql2`), both, or `other` (Drizzle, Sequelize, Mongoose, raw `pg`) - an `other` ORM loads no ORM atomic; Step 5 applies the generic transaction and query checks and says so in Notes.
- stack-detect's `Database`, and the module format (ESM `"type": "module"` or CJS).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review`. Surface a fail-fast verbatim and stop. The handle may carry a `prior_checkpoint` block (the file at its `report_path` exists with valid frontmatter) or the scalar `legacy`; Step 3.5 decides what it means.

From the handle, fix `branch` = its `head_short_name` (never `HEAD`, never remote-prefixed). It names the review target in the no-op message, the writer's `branch` field, and the report filename; `head_ref` passes through unchanged to the git commands and to the writer.

Capture the SHAs first - the Step 3.5 gate needs only these:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

Then, once Step 3.5 has not stopped the run, read **once** (skip when a parent passed pre-read artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log <base_ref>..<head_ref>` (full messages - Step 3.7 reads criteria from commit bodies)

Every file read outside the diff uses `git show <head_ref>:<path>`, so a review of a branch you are not standing on reads that branch.

### Step 3.5 - Decide Round

**Every round analyzes the full `<base_ref>...<head_ref>` range.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change every round; rounds differ only in that round 2+ reconciles against the prior report.

No `prior_checkpoint` -> `round = 1`, no fetch, no reconciliation. `prior_checkpoint: legacy` -> `round = 1`; note `Prior report lacks checkpoint metadata - treated as round 1.` (the Step 10 write overwrites the file).

Otherwise:

The review runs on the ref the handle named, never on a fetched one; the workflow runs no state-changing git.

**3.5a - Compare checkpoints.**

| Condition | Decision |
| --------- | -------- |
| `prior_checkpoint.head_sha == current_head_sha`, `prior_checkpoint.base_sha == current_base_sha`, and the checkpoint's `scope` / `depth` cover the invocation's (`full` covers every scope, any scope covers `core-only`, `deep` covers `standard`; map the invocation to the writer enum per Step 10 first; an invocation with no scope flag is never covered by a `core-only` checkpoint) | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` (`<sha_short>` = first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| Same head, but scope or depth not covered | `round = prior.round + 1`. Note `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_checkpoint.head_sha> <current_head_sha>` fails | `round = prior.round + 1`. Note `Prior checkpoint unreachable - history rewritten.` |
| `prior_checkpoint.base_sha != current_base_sha` | `round = prior.round + 1`. Note `Base branch advanced since round <prior.round>.` |
| `prior_checkpoint.base_ref != base_ref` | `round = prior.round + 1`. Note `Base ref changed since round <prior.round>.` |
| None of the above | `round = prior.round + 1`. |

Apply the first matching row's decision and emit every matching row's note - except the no-op row, which prints its line and nothing else.

**3.5b - Scope on round 2+** resolves exactly as on round 1 (Step 4); nothing is inherited. Scopes newly added this round have no prior findings: note `Scope expanded round <N>: +<list>.` When the resolved scope falls below the checkpoint's, note `Scope narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover.`

### Step 3.7 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and the handle's `report_path` (as its `prior_report_path`) when round > 1.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its `### Requirement Findings` items join the Step 9.3 set - that section and the `### No Requirement Findings` marker confirm the step ran and are never rendered. With no requirement source the Brief still renders, and the traceability block and both Summary lines are omitted. Runs before Step 4 - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

### Step 4 - Risk Snapshot and Scope

Use skills: `review-pr-risk`, `review-blast-radius`. State **Risk Level** and **Blast Radius** before any finding, each as the atomic's line value as emitted (a `(contract break: ...)` parenthetical or a two-state `<level> (unmitigated) -> <level> (with ...)` form stays whole). The promote and short-circuit tests read the unmitigated level unless the `Mitigation:` tag is `in-place:`. Only those two lines reach the report; the atomics' `Signals:`, `Action:`, dimension, and `Mitigation:` lines inform the review and are not emitted.

**Resolve scope:** union of user flags and signals firing on the Step 3 diff; `core-only` suppresses signal escalation. Log each fire as `<category> -> <file:line>`. The Summary `Scope:` line carries the resolved value plus one annotation:

| Observed | Annotation |
| -------- | ---------- |
| No user flag, signals fired | `auto-escalated from Core; signals: <list>` |
| User flag, further categories fired | `user-flagged; signals also firing: <list>` |
| `core-only`, signals fired | `core-only; suppressed signals: <list>` |
| Otherwise | none |

Every suppressed signal also emits a `[Delegate]` Next Step tagged `[+<Lens>]` naming the matching `/task-node-review-*` command.

**Low-risk short-circuit:** Risk Level Low, no Blast Radius dimension other than User Scope above Narrow, and no architecture-relevant file touched (auth strategies / guards, middleware, API contracts, shared base classes, `app.module.ts` / `app.ts` / `main.ts`, migrations) -> skip Steps 6-8. Step 5 runs; Step 9 runs the resolved scope as usual, so the checkpoint's `scope` is what actually ran; Steps 9.3-10 run as usual. Note `Low-risk short-circuit: Steps 6-8 skipped`; when Risk Level alone blocked it, note `Short-circuit not taken: Risk Level <level> (<its signals>)`.

### Step 5 - Node Correctness and Safety

Atomics - `Use skill:` each one whose area the diff touches (at `deep`, also each one whose area the code the diff calls into touches):

- `node-typescript-patterns` - strictness not relaxed, `as any` / `as unknown as T` in non-test code
- `node-prisma-patterns` (Prisma) or `node-typeorm-patterns` (TypeORM) - queries, `include` / `relations`, DTO mapping
- `backend-transaction-patterns`, then `node-transaction-patterns` - any diff that opens a transaction, locks a row, or dispatches a side effect around a write
- `node-bullmq-patterns` - producers, processors, queue options
- `ops-resiliency`, then `node-http-client-patterns` - a new or changed outbound client
- `node-exception-handling` - exception filters, error middleware, error classes, `catch` blocks
- `node-nestjs-patterns` (NestJS) or `node-express-patterns` (Express) - modules, providers, guards, middleware order, bootstrap
- `node-migration-safety` plus `ops-backward-compatibility` - any change under `prisma/migrations/` or the TypeORM migrations directory
- `node-testing-patterns` - a diff that adds or changes tests, or leaves critical-path logic untested (what a meaningful assertion is)

**API contract gate** - when the diff carries a contract-change signal (a removed / renamed / retyped response-DTO field, a changed HTTP status, a new **required** request field or tightened class-validator / Zod constraint, a new public route on a `/v1/`-versioned or externally consumed API, a controller returning a raw Prisma model or TypeORM entity, or an edit to a `@nestjs/swagger` / swagger-jsdoc / committed OpenAPI spec), use skills `backend-api-guidelines` and `ops-backward-compatibility`. Judge breakage from the consumer's view ("no external callers" needs a search; when consumption is unknown, a `/v1/`-versioned or spec-published surface is externally consumed); responses go through a DTO; errors follow RFC 9457 (`node-exception-handling`'s `{ error, message }` body is a `[Recommend]` unless the project documents it as its convention); collections paginated; the committed spec matches the code. Each finding names who breaks and how. This gate's table supersedes the atomic's tiers: `[Must]` = unversioned breaking change to an externally consumed contract, or a raw entity on an externally consumed / versioned surface; `[Recommend]` = internal breaking change with no coordinated-deploy note, inconsistent status / error envelope, unpaginated unbounded collection, spec or generated client out of sync; naming drift with no consumer impact is not written. A raw entity on an internal-only surface stays with the DTO-hygiene check below.

**Checks the atomics don't own:**

- **Test coverage (named finding).** Logic added without Jest coverage -> `[Recommend]`; `[Must]` on critical paths: authentication, authorization, money / billing, multi-table writes, state machines, data-mutating BullMQ processors, migrations changing column semantics. Test files are reviewed for coverage correctness only: production logic no test exercises (anchored to the untested production `file:line`), and a test whose assertions cannot fail or no longer match the code. Style, structure, duplication, and speed of test code are not findings.
- **Floating promises.** An unawaited promise in a request or job path (`void doThing()` with no `.catch`, a missing `await` on a write) loses errors and ordering.
- **Event-loop blocking in request and job paths.** `fs.readFileSync`, `crypto.pbkdf2Sync`, large `JSON.parse` / `JSON.stringify`, catastrophic regex - presence here; impact and offloading belong to +Perf.
- **Validation wired.** NestJS: a global `ValidationPipe` (in `main.ts` or as an `APP_PIPE` provider) with `whitelist: true`; Express: every write route parses its body with a schema and passes the parse **result** onward, never `req.body`. A missing global pipe, missing `whitelist`, or `req.body` flowing into a write is `[Must]`; missing `forbidNonWhitelisted` / Zod `.strict()` (which reject rather than strip) is `[Recommend]`.
- **Authorization and IDOR.** A guard or middleware proves identity, not object access. Per-owner / per-tenant endpoints scope at the query: `where: { id, tenantId: user.tenantId }`, not `findUnique({ where: { id } })` plus a later check.
- **Response DTO hygiene.** Compare the DTO against the model: `passwordHash`, `mfaSecret`, `apiKey`, `webhookSecret`, `internalNotes`, `isAdmin` never reach the wire. Returning a Prisma model or TypeORM entity directly is `[Recommend]` regardless of today's fields; this label and the API gate's supersede any atomic's label for entity exposure.
- **Idempotency on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions` accept an `Idempotency-Key` and claim it atomically in the database (unique constraint and a conditional insert, with the stored response for replay), never look-up-then-create. Inbound webhooks dedupe on the provider's event id instead.
- **Multi-replica race safety.** Counters, balances, and state transitions use `SELECT ... FOR UPDATE` inside the transaction (`tx.$queryRaw` in `$transaction(async (tx) => ...)`, TypeORM `setLock('pessimistic_write')`), a guarded conditional update (`WHERE status = <from>`), or a version column - never in-process state.
- **New queried column.** A new Prisma field / TypeORM column used in `where` / `orderBy` / `groupBy` has an index in the same PR, or an explicit "indexed later" note.
- **Error handling.** NestJS exception filters map validation / not-found / unauthorized / forbidden / unique-violation consistently; Express has one terminal 4-arg error middleware registered after the routers. Express 4: every async handler wrapped (an unwrapped rejection never reaches the error middleware); Express 5 forwards rejections natively and a wrapper is redundant. No `catch (e) { console.log(e) }` swallows.
- **SSRF and edge middleware presence.** User-controlled values in outbound URLs; `helmet`, a CORS allowlist, and body limits when app construction changes - body-parser defaults every parser to `100kb`, so the finding is a raised `limit`, not a bare `express.json()`. Depth belongs to +Sec.

### Step 6 - Architecture Guardrails

Use skill: `architecture-guardrail`.

- **Layering (NestJS):** controller -> service -> repository / ORM client. No business logic in controllers; no HTTP clients in repositories; DTO mapping at the service / controller boundary
- **Layering (Express):** router -> handler or service -> repository. No business logic in route definitions
- **Service discipline:** handlers over ~10 lines of orchestration extracted to a service; intention-revealing names; cross-entity orchestration in services, not in TypeORM `@AfterInsert` listeners or Prisma client extensions
- **NestJS DI:** constructor injection; module imports declare dependencies; `forwardRef` only as a last resort
- **Settings discipline:** typed `ConfigService` with a Joi / Zod schema (NestJS) or one validated, frozen config module (Express); no `process.env.X` scattered across files
- **Feature-module layout;** cross-feature imports go through public module exports, not another feature's repository
- **Multi-tenant isolation** at the data layer (a Prisma client extension, a TypeORM scoped repository or query helper - a subscriber stamps `tenantId` on writes only), not controllers alone
- **Listener discipline:** `@AfterInsert` / `@BeforeUpdate` / Prisma extensions reserved for cross-cutting concerns (audit, soft-delete), never hidden control flow that enqueues jobs or sends mail
- **Anemic domain (`deep` only):** business rules accumulating in services while models stay pure data - an Architecture Notes observation, never a finding
- **Multi-service PRs:** contract compatibility (OpenAPI diff, Pact) and deployment order - Use skill: `ops-backward-compatibility`

### Step 7 - AI-Generated Code Quality

- Use skill: `complexity-review`
- Use skill: `node-nestjs-overengineering-review` (NestJS) or `node-express-overengineering-review` (Express); `mixed` runs each on its own app's files, passing that app's framework as `Framework` over the stack-detect value. The necessity skill owns request-scope misuse, single-implementation interfaces, and `Result` wrappers - Step 6 does not re-raise them.
- Redundant mapping layers (`Entity -> DomainObject -> ServiceDTO -> ResponseDto` when one would do)
- Test verbosity (`beforeEach` over ~30 lines for one assertion; a full deep-equal where two field assertions would do) - a Maintainability Notes line, never a finding
- Comment cruft (JSDoc restating a private helper's signature, generated TODOs)

### Step 8 - Maintainability

Use skill: `backend-coding-standards` when the diff introduces naming or structure patterns. Use skill: `ops-observability` for logging / metrics presence (depth belongs to +Obs).

- **Naming:** services name their operation (`order-fulfillment.service.ts`, not `order-helper.service.ts`); DTOs name their role (`CreateOrderDto`, `OrderResponseDto`); no `Util` / `Manager` / `Helper` modules
- **Magic numbers / strings** extracted to constants or config (`60_000` over `60000` mid-expression); URLs and credentials from config, never inline
- **Function length:** over ~30 lines reviewed; over ~60 flagged unless it orchestrates clearly named steps
- **Duplicated query logic:** the same `where` predicate in 3+ places extracted to a repository method or query helper
- **Logging hygiene:** `console.log` in production paths, lines without correlation ids, wrong levels - `[Recommend]`

### Step 9 - Delegate Extra Scopes in Parallel

Skip on Core. For each selected scope, spawn one subagent in parallel with the **declared `subagent_type`** - never infer the agent from the scope name:

| Scope | Skill | Subagent (`subagent_type`) |
|-------|-------|----------------------------|
| +Perf | `task-node-review-perf` | `node-performance-engineer` |
| +Sec | `task-node-review-security` | `node-security-engineer` |
| +Obs | `task-node-review-observability` | `node-observability-engineer` |
| +Rel | `task-node-review-reliability` | `node-reliability-engineer` |

`Full` = four subagents. Each scope's skill is loaded with `Use skill:`; the table names it rather than repeating the directive per row.

**Prompt contract** - each spawn carries: the statement that it runs as a subagent of `task-node-review` (every lens branches on it: no precondition check, no round gate, no verify, no reconcile, no report file); the handle's `base_ref`, `head_ref`, `head_short_name`, `current_base_sha`, `current_head_sha`, and the pre-read diff, `--name-status`, and log; the resolved depth; every Step 2 fact; authorization to read any path at `<head_ref>` via `git show` and to run read-only `git log -p` / `git show <base_ref>:<path>` on changed paths; and the instruction to return exactly what its own subagent clause names - never "its Output Format".

Every lens returns `## Findings` with its tier sections (each finding a numbered block carrying its label, Location, and the lens's fields) plus any `out of lens` lines; reliability ends it with a `Resilience Libraries:` line. Additionally: perf at `deep` returns `## Capacity Guidance` and `## Load Plan`; reliability at `deep` returns `## Failure-Mode and Blast-Radius Map`; security returns `## Not verifiable` when a control could not be read.

**Failure isolation:** a subagent that fails or times out is skipped; note `Scope incomplete: <scope>`, and the checkpoint's `scope` records only the lenses that returned (Step 10).

**No-spawn fallback:** when the environment cannot spawn subagents, run each selected lens inline and in sequence using its own skill, as a subagent run: its Steps 1-3 pre-satisfied, its verify, reconcile, and writer skipped; its checklist and atomic-load gates applied unchanged to the code already read (an atomic its gate selects is opened, not recalled). Each inline lens produces its own `## Findings` first; Step 9.3 then projects and merges them. Note `Scopes run inline`.

### Step 9.3 - Assemble the Finding Set

Runs once Step 9 has returned (on Core, over core findings alone). Verify, reconcile, and the report all read this set:

1. **Project each lens's findings.** Tier by the severity word in the section heading: perf and security `Critical` / `High` / `Medium` / `Low`, observability and reliability `High` / `Medium` / `Low` (`Low Impact / Quick Wins` is Low). The label is the block's `[Must]` / `[Recommend]` token, kept as returned. Re-file each as this report's finding block: heading from the label and the `file:line` prefix of its Location, `Severity:` the tier, `Scope:` the lens, `Issue:` its Issue, `Impact:` its Impact (security: Attack scenario; reliability: Failure Mode, plus `(assumes: <Assumption>)` when it carried one), and `Fix:`. `System Risk:` on a lens `[Must]` states its reach - reliability's Blast Radius when it has one; otherwise written here from what the defect shares (a pool, the event loop, a tenant boundary, the diagnosis of an incident).
2. **Merge.** Core (Steps 5-8), Step 3.7, and lens findings making the same claim about the same defect collapse to one entry: strongest label and highest Severity win, one `file:line`, and `Scope:` lists every source (Step 3.7 counts as Core). Distinct claims at one `file:line` stay separate. The merged entry takes the prose that states the mechanism most specifically; when sources disagree on a fact, Step 9.4's evidence settles it. A requirement finding and a defect finding on the same gap merge, the Issue line naming the criterion.
3. **Non-finding lines.** A lens `out of lens` line is drafted here as a finding (label per Feedback Labels, Fix written here). `## Architecture Notes` carries each `architecture-guardrail` finding's `Drift:` line by `file:line` (or its `No Violations Found` sentence) and the Step 6 anemic-domain observation; `## Maintainability Notes` carries Step 7's unlabelled bullets (mapping layers, test verbosity, comment cruft); the labelled findings those atomics raise join the set in item 2. A lens's non-finding sections (Capacity Guidance, Load Plan, the Failure-Mode map, Not verifiable) render verbatim after Next Steps; reliability's `Resilience Libraries:` line goes into Summary Notes.
4. **Next Steps.** One entry per published finding: `[Implement]` when the fix is local to the PR, `[Delegate]` with a `[scope: <owner>]` token when it leaves the PR; plus one `[Delegate]` `[Recommend]` `[scope: verify]` per security Not verifiable entry.

### Step 9.4 - Verify Findings

Use skill: `review-finding-verify` with the Step 9.3 set, the diff already read, and `base_ref` / `head_ref` - one row per assembled entry, so the tally counts each defect once.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the `Label` and `Annotation` columns. The annotation sits on the finding heading, each its own `_(...)_` group: the combined `_(pre-existing; newly reachable via ...)_` is written `_(pre-existing)_ _(newly reachable via ...)_`, because `review-prior-findings-reconcile` matches `_(pre-existing)_` exactly. Fill Summary's `Findings verified:` in the atomic's Summary form.

### Step 9.5 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the body of the file at the handle's `report_path` (frontmatter excluded), read here
- `diff` and `name_status`: the full-range reads from Step 3
- `head_sha`: `current_head_sha`
- `head_files`: `git ls-tree -r --name-only <current_head_sha>`

Its table, note line, and tally render under `## Prior Round Reconciliation`.

`Still open` and `Needs re-check` rows are unresolved. A row this round re-derived publishes once, in `## High-Impact Findings` at this round's label (a label change noted in the row's Notes). A row is re-derived when this round's set holds a finding on the same construct with the same smell. A row this round did not re-derive republishes its prior block verbatim in `## High-Impact Findings` at its prior label - heading keeping the prior `file:line` and every annotation group, plus `_(carried from round <prior.round>)_` unless a carried group is already there - and skips Step 9.4, outside its tally. Both get a Next Steps entry suffixed `(open since round <N>)`, `<N>` the earliest round the finding appeared, ordered by label with carryovers first among equals. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried. No standalone "Carry-Over" section - reconcile parses only `## High-Impact Findings`, so a row kept out of it is invisible to round 3.

### Step 10 - Write Report

**Assessment** follows the open-label set: `Request Changes` when any `[Must]` is open (this round's findings and carried rows alike); `Discuss` when none is, but a `[Recommend]` rests on an assumption only the author can settle; `Approve` otherwise. Order findings and Next Steps by label, not by scope. Key Takeaways are 2-4 bullets on what the set says about the change as a whole - a pattern, a systemic risk, a structural cause - never a restated finding.

Use skill: `review-report-writer` with `report_type: review` and:

- `report_body` (the assembled report), `branch` (Step 3), `base_ref` and `head_ref` as the handle emitted them, `base_sha = current_base_sha`, `head_sha = current_head_sha`
- `mode: full`, `round` (Step 3.5), `prior_head_sha = prior_checkpoint.head_sha` when round > 1, `pr_url` when the request carried a PR URL, else `prior_checkpoint.pr_url` when present
- `scope` in the writer's enum (`Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, `Full` -> `full`) over the lenses that returned - a `Full` run that lost a lens writes the one to three that ran, space-joined in the order `+perf +sec +obs +rel`, and none -> `core-only`; `depth` as resolved; `stack = node-typescript`

Emit the body, then the writer's confirmation line.

## Feedback Labels

Every finding carries exactly one label: `[Must]` (do not merge until fixed) or `[Recommend]` (fix, or push back with reasoning - never silently acked). A finding this workflow raises takes `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise; its `Severity:` is High for a `[Must]` that corrupts state, moves money wrongly, exposes data across tenants or users, or takes the service down (a write-blocking migration on a large table, a pool breached at deploy) - Critical when unauthenticated, already exploitable, or losing data - Medium for other `[Must]`s and `[Recommend]`s with user-visible effect, Low otherwise. Where `review-finding-verify` publishes a different `Label`, it governs - in Next Steps and Assessment too.

**Envelope precedence.** The atomics loaded in Steps 5-8 emit their own blocks and severity scales. Fold their content into this report's finding blocks; emit none of their envelopes, target-state blocks, `Cleared:` or `Considered, not flagged` lines. Mapping: an atomic's High -> `[Must]`, Medium / Low -> `[Recommend]`, except a maintainability-only High (complexity, structure, naming) and an `ops-observability` presence gap (one that leaks no secret or PII) -> `[Recommend]`; an atomic's own `[Must]` / `[Recommend]` stands, except for entity exposure (Step 5); `ops-backward-compatibility` `Compatible: No` or `No (unverified)` on an externally consumed surface -> `[Must]` (the latter's Issue saying it is unverified); a necessity skill's `Out of scope:` item becomes a finding here when it names a defect.

## Output Format

Emit `report_body` as raw Markdown; the fence below delimits the template for display only. Brace annotations are authoring notes, never emitted. Omit empty sections, except `## High-Impact Findings`, which always renders (`No findings.` when empty) because the next round's reconcile reads it; omit Next Steps when nothing is actionable.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss - <open [Must] count; on Discuss, the assumption to settle>
- **Risk Level:** Low | Medium | High | Critical   {the atomic's line as emitted}
- **Blast Radius:** Narrow | Moderate | Wide | Critical   {the atomic's line as emitted - parenthetical or two-state form included}
- **Stack:** Node.js <version> / TypeScript <version> / <NestJS | Express | mixed> <version> / <Prisma | TypeORM | other> <version>   {versions from package.json; omit one it does not pin}
- **Scope:** Core | +Perf | +Sec | +Obs | +Rel | Full   {plus the Step 4 annotation when one applies}
- **Depth:** standard | deep   {append `auto-promoted from standard; Blast Radius: <level>` when promoted}
- **Round:** <N>   {round 2+ only}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}
- **Requirement Source:** <path or origin> (Specified | Self-attested)   {this line and the next together, or both omitted when Step 3.7 resolved no source}
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable
- **Notes:**   {omit when none}
  - <each note Steps 2-9 produced: round, scope, depth, short-circuit, inline or incomplete scopes, ORM `other`, the handle's own notes>

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability   {omit when Step 3.7 resolved no source}

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, `file:line (pre-existing)`, or `-`> | <file:line or verification note, optionally `(pre-existing)`, or `-`> |

## Prior Round Reconciliation   {round 2+ only}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ... | ... | ... | ... |

<the reconcile skill's note line, when it emitted one>

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line   {+ annotation groups per Steps 9.4 and 9.5}

Severity: Critical | High | Medium | Low

Scope: Core | +Perf | +Sec | +Obs | +Rel   {every source, comma-joined, when merged}

Issue: <the Node idiom: `queue.add` inside `$transaction`, `@Public()` on a tenant-scoped read, raw entity returned from a controller, `ValidationPipe` without `whitelist`, `crypto.pbkdf2Sync` in a handler>

Impact: <user-visible or operational consequence>

System Risk: <why this is system-level, not local>   {`[Must]` defects only; a requirement finding names its criterion instead}

Fix: <concrete Node change with code>

### [Recommend] file:line   {+ annotation groups}

Severity: ...

Scope: ...

Issue: ...

Impact: ...

Fix: ...

## Architecture Notes

- Boundary impact / Coupling change / Drift detected   {reference findings by file:line; never restate them}

## Maintainability Notes

- Over-engineering detected / Simplification opportunities

## Key Takeaways

- <2-4 bullets on systemic impact>

## Next Steps

1. **[Implement]** [Must] file:line - <one-line action>
2. **[Implement]** [Recommend] file:line - <action> (open since round 1)
3. **[Delegate]** [Recommend] [+Sec] - run `/task-node-review-security` (suppressed signal: <signal>)
4. **[Delegate]** [Recommend] [scope: platform] - <action for a fix leaving the PR>

## <Lens section title>   {each non-finding section a lens returned, verbatim - Step 9.3}
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (subagent: loaded, or rules inlined in the spawning prompt)
- [ ] Step 2: stack confirmed; `Framework` and `ORM` resolved, including `mixed` / `other`
- [ ] Step 3: `review-precondition-check` ran with the argument, `--base`, and `report_type: review` (or handle received); `branch` = `head_short_name`; SHAs captured before the diff, name-status, and log were read once
- [ ] Step 3.5: round decided from the handle before any read; no-op exits without writing
- [ ] Step 3.7: `review-change-intent` ran; Change Brief rendered; requirement lines and traceability present together or omitted together; its findings joined the set
- [ ] Step 4: Risk and Blast Radius stated as emitted; depth promoted on the right value; scope resolved with its annotation; a `[Delegate]` per suppressed signal; short-circuit noted when taken
- [ ] Step 5: touched-area atomics loaded (every one at `deep`); API contract gate ran on a contract-change signal; the non-atomic checks applied
- [ ] Steps 6-8: guardrails, AI-quality, and maintainability applied - or skipped by the short-circuit
- [ ] Step 9: lenses spawned in parallel with the prompt contract (or run inline, noted); failed scopes noted
- [ ] Step 9.3: lens findings projected; same-claim entries merged with every source in `Scope:`; `out of lens` lines drafted; non-finding lens sections kept
- [ ] Step 9.4: `review-finding-verify` ran on the assembled set; Dropped excluded; `Label` and split `Annotation` groups applied; four-term tally in Summary
- [ ] Step 9.5: round 2+ reconciled from `report_path` with `head_sha`; unresolved rows carried with `_(carried from round <N>)_` and a Next Step; legacy labels mapped
- [ ] Step 10: Assessment from the open-label set; report written with every writer field; confirmation printed
- [ ] Every `[Must]` states System Risk; every finding has a label, `file:line`, and a Node fix

## Avoid

- State-changing git from this workflow
- Generic backend advice where a Node idiom exists ("move the enqueue after `$transaction` resolves", not "decouple the side effect")
- Blocking on personal preference
- Duplicating a lens's depth in core when that lens runs
