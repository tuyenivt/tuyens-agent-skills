---
name: task-node-review
description: Node.js/NestJS/Express code review - event-loop blocking, async pitfalls, ORM leaks, missing guards, validation; spawns perf/security/obs/reliability/api agents.
agent: node-tech-lead
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node.js Code Review

Staff-level Node.js / NestJS / Express code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability / reliability / api subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a NestJS or Express PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**
- Pre-implementation design (`task-node-implement`)
- Production incident (`/task-oncall-start`)
- Single-error debug
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-node-review-perf` / `-security` / `-observability` / `-reliability` / `-api`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical pattern matching + cross-PR context |

**Auto-promote to `deep`:** After Phase A, if `Blast Radius` is Wide or Critical, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Node-flavored) |
| + Perf | Core + `task-node-review-perf` subagent |
| + Sec | Core + `task-node-review-security` subagent |
| + Obs | Core + `task-node-review-observability` subagent |
| + Rel | Core + `task-node-review-reliability` subagent |
| + Api | Core + `task-node-review-api` subagent |
| Full | Core + all five subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Node-tuned):**

- **+Sec:** file uploads (`multer`, `FileInterceptor`, `@UploadedFile()`), auth strategy / guard changes (`AuthGuard('jwt')`, `JwtStrategy`, `requireAuth`), DTO / Zod schema changes, raw SQL via `$queryRawUnsafe` / `repository.query`, secrets in env / config, BullMQ consuming user input, `Object.assign(target, req.body)`
- **+Perf:** new Prisma / TypeORM migration, new ORM query (`findMany` / `find` / `createQueryBuilder`), new `include` / `relations`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `lru-cache` / Redis read paths
- **+Obs:** new service / module, new external client (`axios.create`, `undici` Pool), new BullMQ producer / processor, logging config change (`pino` / `winston`), new `prom-client`, new lifecycle hook (`OnModuleInit`, `OnApplicationBootstrap`)
- **+Rel:** new `axios` / `undici` / `fetch` client without an `AbortSignal.timeout`, new `opossum` / `cockatiel` / `p-retry` config, BullMQ processor without an idempotency check, unbounded `Promise.all` over a collection, missing `SIGTERM` / graceful-shutdown drain, dual write (`queue.add` / `stripe.charge` / `mailer.send` inside `$transaction`)
- **+Api:** a *contract-change* signal (not merely a new internal endpoint) - a removed / renamed / retyped response-DTO field, a changed HTTP status, a new **required** request field or tightened class-validator / zod constraint, a new public route on a `/v1/`-versioned or externally consumed API, a controller returning a raw TypeORM / Prisma entity, or an edit to a `@nestjs/swagger` / swagger-jsdoc / committed OpenAPI spec
- **2+ categories → Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-node-review` | Current branch vs base; fails fast on trunk |
| `/task-node-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-node-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-node-review pr-50273 --base release/2026.05 +sec deep`.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not Node, stop and recommend `/task-code-review`.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express (`express` without NestJS). Detect ORM: Prisma vs TypeORM. Record `Framework` and `ORM` for branching in later phases.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Once approved, read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as a subagent and the parent passed the handle plus pre-read artifacts.

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

### Step 3.5 - Decide Mode (re-review auto-detect)

Skip if the handle has no `prior_checkpoint` -> `mode = full`, `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `mode = full`, `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

Otherwise (valid prior checkpoint present):

**Step 3.5a - Auto-fetch the head branch.** Only when a valid prior checkpoint exists, refresh the local tracking ref so a script can re-run the same command without manually fetching:

```bash
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "<head_ref>@{u}" 2>/dev/null)
```

If `upstream` resolves to `<remote>/<branch>` form, split and run:

```bash
git fetch <remote> <branch>
```

No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. After a successful fetch, re-resolve `current_head_sha = git rev-parse <head_ref>`.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `mode = full`, `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten; full re-review.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round> - full re-review.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round> - full re-review.`           |
| None of the above                                                       | `mode = incremental`, `round = prior.round + 1`, `incremental_range = <prior_head_sha>...<current_head_sha>`.                       |

**Step 3.5c - Incremental: re-read the diff scoped to the new range.**

If `mode = incremental`, replace the diff read from Step 3 with:

- `git diff <prior_head_sha>...<current_head_sha>`
- `git diff --name-status <prior_head_sha>...<current_head_sha>`
- `git log --oneline <prior_head_sha>..<current_head_sha>`

The full-range diff from Step 3 is discarded; all Phase A-E analysis operates on the incremental range only.

**Step 3.5d - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary based on mode:

- `mode = incremental`: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.`
- `mode = full`: `Scope expanded round <N>: +<list>.` (the incremental clause does not apply)

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` → stay Core
- One signal category → add matching extra scope
- 2+ categories → promote to Full
- User passed an explicit scope → respect it; still log signals so the Summary documents why

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth strategies / guards, middleware, API contracts, shared base classes, `app.module.ts` / `app.ts`, migrations), skip Phases C-E and produce a streamlined report (Phase A snapshot + Phase B findings). Note the short-circuit in Summary.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

### Phase B - Node Correctness and Safety

Apply atomic skills. Each owns the canonical patterns; this phase flags deviations and surfaces what they did not see:

- Use skill: `node-typescript-patterns` - `strict: true` not relaxed, no floating promises, no `as any` in non-test code
- Use skill: `node-prisma-patterns` (Prisma) or `node-typeorm-patterns` (TypeORM) - transactions, `include`/`relations`, post-commit dispatch
- Use skill: `node-bullmq-patterns` if diff touches BullMQ jobs
- Use skill: `node-migration-safety` if diff touches `prisma/migrations/` or `src/migrations/`. Also use skill: `ops-backward-compatibility` for client/in-flight impact

**Additional Node-specific checks the atomics don't own:**

- **Test coverage finding (named, not buried).** PR adds logic without Jest coverage -> `[Recommend]`; escalate to `[Must]` when the change is critical path: auth (JWT / Passport / `AuthGuard`), authorization (guards / `requireAuth`), money / billing, multi-table writes, state machines, BullMQ mutators, migrations changing column semantics. Surface as a dedicated finding.

**Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.
- **Event-loop blocking in request paths.** `fs.readFileSync` / `crypto.pbkdf2Sync` / large `JSON.parse` / catastrophic regex flagged (presence/absence here; depth - impact heuristic, `worker_threads`, `AbortSignal` - belongs to perf subagent).
- **Validation strict-mode wired.** NestJS `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))` in `main.ts`; Express Zod schemas use `.strict()`. Absence is a critical correctness + security gap.
- **Authorization + IDOR.** Authn (guard / middleware) proves identity, not object access. Per-owner / per-tenant endpoints must scope at the repository: `where: { id, userId: user.sub }`, `tenantId` injected by middleware/extension.
- **Response DTO field hygiene.** Compare the DTO against entity columns. Flag `passwordHash` / `mfaSecret` / `recoveryCodes` / `apiKey` / `webhookSecret` / `internalNotes` / `auditLog` / `isAdmin` / `internalCreatedBy` on the wire. Returning a Prisma model or TypeORM entity directly is `[Recommend]` regardless of current fields - a new sensitive column silently leaks later.
- **HTTP `Idempotency-Key` on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` accept an `Idempotency-Key` header and dedupe via DB unique constraint or Redis `SET NX EX`. Distinct from BullMQ `jobId` - the HTTP key protects the client→server boundary.
- **Multi-replica race safety.** Counters / balances / state transitions use DB locking (`SELECT ... FOR UPDATE`, Prisma `$queryRaw`, TypeORM `setLock('pessimistic_write')`) or optimistic version field, not in-process state.
- **HTTP client sharing.** `axios.create()` / `undici` Pool shared at module level. Per-request instantiation breaks connection reuse.
- **SSRF + edge middleware presence.** User-controlled values in outbound URLs flagged here; `helmet`, CORS allowlist, body size limits (`express.json({ limit })`) confirmed when app construction changes. Depth in security subagent.
- **New ORM column with predicate use.** Any new Prisma `@db.*` / TypeORM column referenced in `where` / `orderBy` / `groupBy` has an index migration in the same PR, or an explicit "indexed later" note.
- **Error handling.** NestJS `@Catch` filters cover validation / not-found / unauthorized / forbidden / unique-constraint consistently; Express has a 4-arg global error middleware. No `catch (e) { console.log(e) }` swallows; Express async handlers wrapped via `asyncHandler` or covered by global error middleware.

### Phase C - Node Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Node-specific:**

- **Layering (NestJS):** controller → service → repository → entity. No business logic in controllers; no `axios` / `fetch` in repositories; DTO mapping at the service / controller boundary
- **Layering (Express):** route → controller (or service) → repository → entity. No business logic in route definitions
- **Service-layer discipline:** route handlers > 10 lines of orchestration extracted to a service; intention-revealing names (`fulfillOrder` not `processOrderStep2`); cross-entity orchestration in services, not in TypeORM `@AfterInsert` listeners or Prisma middleware
- **NestJS DI:** constructor injection; module imports declare dependencies explicitly; no `Reflect.getMetadata` outside platform code; `forwardRef` only as last resort - prefer extracting a shared module
- **NestJS request-scoped providers:** `Scope.REQUEST` only when truly needed (per-request transaction, multi-tenant context); flagged on otherwise-stateless providers
- **Settings discipline:** typed `ConfigService` with Joi / Zod schema (NestJS) or `dotenv` + a typed frozen config (Express); no `process.env.X` scattered across files
- **Feature-module layout** (`src/orders/{controller,service,repository,dto}.ts`) preferred over layer-package; cross-feature imports go through public module exports, not direct repository imports
- **Multi-tenant isolation** enforced at the repository layer (Prisma extension / TypeORM listener / QueryBuilder helper), not at controllers alone
- **Listener / middleware discipline:** `@AfterInsert`, `@BeforeUpdate`, Prisma middleware reserved for genuinely cross-cutting concerns (audit, soft-delete, search-index) - not as hidden control flow dispatching emails / BullMQ jobs
- **Anemic domain (deep depth only):** business rules accumulating in services while ORM models stay pure data - flag for refactor/extraction. Do not raise on a single PR's evidence alone

**Multi-service PRs:**

- API contract compatibility (OpenAPI diff, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility`

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering, simplification
- Load **one** framework-specific necessity skill from Step 2's detection:
  - **NestJS:** Use skill: `node-nestjs-overengineering-review`
  - **Express:** Use skill: `node-express-overengineering-review`

**Additional Node AI smells the atomics don't own:**

- Redundant mapping layers (`Entity → DomainObject → ServiceDTO → ResponseDto` when one would do)
- Test verbosity (`beforeEach` > 30 lines for one assertion; full deep-equal when a few field assertions would do)
- Comment cruft (JSDoc on private helpers repeating the signature; auto-generated TODOs left in)
- `as any` / `as unknown as T` proliferation in non-test code to silence a real type bug

### Phase E - Maintainability and Clarity

Use skill: `backend-coding-standards` for cross-language naming. Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth belongs to `task-node-review-observability`).

**Node-specific:**

- **Naming:** services describe their operation (`orderFulfillment.service.ts` over `orderHelper.service.ts`); DTOs named after role (`CreateOrderDto`, `OrderResponseDto`); no `Util` / `Manager` / `Helper` modules
- **Magic numbers / strings:** extracted to module-level constants or config; `60_000` over raw `60000` mid-expression
- **Hardcoded URLs / credentials:** env / config, not inline
- **Function length:** > 30 lines extracted; > 60 lines unless clearly orchestrating
- **Duplicated query logic:** same `where` / `find` predicate in 3+ places extracted to a repository method or QueryBuilder helper
- **Logging hygiene:** surface `console.log` in prod paths, lines without correlation IDs, wrong levels as `[Recommend]` (depth in observability subagent)

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip. For each extra scope, spawn one independent subagent **in parallel** with the main thread. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `node-tech-lead` spawn:

| Scope | Skill | Subagent (`subagent_type`) |
|-------|-------|----------------------------|
| + Perf | `task-node-review-perf` | `node-performance-engineer` |
| + Sec | `task-node-review-security` | `node-security-engineer` |
| + Obs | `task-node-review-observability` | `node-observability-engineer` |
| + Rel | `task-node-review-reliability` | `node-reliability-engineer` |
| +Api | `task-node-review-api` | `node-api-engineer` |

`Full` = 5 subagents.

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (Node / TypeScript) + framework (NestJS / Express / mixed) + ORM (Prisma / TypeORM)
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend`
- **Preserve `file:line` citations**
- **Order by intent**, not by scope
- **Note missing scopes** in Summary as `Scope incomplete: <scope>`
- **Merge Next Steps** with `[Implement]` / `[Delegate]` tags preserved; re-sort by intent
- **Preserve deep-only sections** returned by subagents (e.g., reliability's `Failure-Mode and Blast-Radius Map`) as their own section after Next Steps - they are not findings; the merge must not drop them

### Step 6.6 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the assembled findings (including any merged back from subagents), the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column. Carry its tally into Summary as `Findings verified: <N> confirmed, <M> reattributed, <K> dropped`.

### Step 6.5 - Reconcile Prior Findings (incremental mode only)

Skip if `mode = full`. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `incremental_diff`: from Step 3.5c
- `name_status`: from Step 3.5c

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode` (from Step 3.5), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4, mapped to the writer's enum: `Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, `+Api` -> `+api`, `Full` -> `full` - the writer rejects unmapped display values), `depth` (resolved/auto-promoted), `stack = node-typescript`

Write before ending; print the confirmation line.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide | Critical
**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version> | mixed
**ORM:** Prisma <version> | TypeORM <version>
**Scope:** Core | +Sec | +Perf | +Obs | +Rel | +Api | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_
**Round:** <N>                                _(include from round 2 onward)_
**Mode:** incremental (since <prior_head_sha_short>) | full _(include from round 2 onward)_
**Findings verified:** <N> confirmed, <M> reattributed, <K> dropped
**Diff Range:** <range_short> (<N> commits, <M> files) _(incremental rounds only)_

## Prior Round Reconciliation _(incremental rounds only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line

- Issue: [name the Node idiom: blocking `crypto.pbkdf2Sync` in async handler, missing `@UseGuards`, ORM entity returned from controller, BullMQ `queue.add` inside transaction, `ValidationPipe` missing `whitelist: true`, `Object.assign(target, req.body)` prototype-pollution surface, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Node change with code]

### [Recommend] file:line
- Issue: ...
- Impact: ...
- Fix: ...

## Architecture Notes

_Cross-cutting commentary. Do not restate individual findings; reference them by file:line._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] OldFile.ts:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Must heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Node conventions, not generic backend conventions
- Provide actionable feedback with TypeScript code examples
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability / reliability / api depth to subagents

## Self-Check

- [ ] `behavioral-principles` loaded; stack, framework, ORM recorded (Steps 1-2)
- [ ] `review-precondition-check` ran (or handle received); diff/log read once (Step 3); current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Scope auto-escalation evaluated and recorded; depth auto-promoted on Wide/Critical blast radius (Step 4, 4.5)
- [ ] Risk + blast radius stated before any finding (Phase A)
- [ ] Phase B: atomic skills applied; test-coverage gap raised as named finding; event-loop, validation strict, authz / IDOR, response-DTO hygiene, Idempotency-Key, race safety, migration safety all checked
- [ ] Phases C-E ran (C: layering, DI, settings, listener / middleware, multi-tenant; D: `complexity-review` + framework-matching necessity skill; E: naming, magic numbers, function length, logging hygiene) - or low-risk short-circuit invoked and noted in Summary
- [ ] Every Must cites system risk; every finding has label + `file:line` + actionable Node fix
- [ ] Extra scopes ran in parallel; subagent findings merged intent-ordered (no raw reports); missing scope noted as `Scope incomplete: <scope>`
- [ ] Step 6.6 - review-finding-verify ran on all assembled findings; Dropped rows excluded; verdict labels applied; tally in Summary
- [ ] Step 6.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered by intent
- [ ] Report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Reviewing without reading the full diff and commit log first
- Generic backend conventions when a Node idiom exists ("extract to a service module", not "extract to a helper class")
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability / reliability / api depth here when the dedicated subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Recommending sync `fs.readFileSync` / `crypto.pbkdf2Sync` in request paths, `eval` / `new Function` on untrusted input, or `Object.assign(target, req.body)` as acceptable patterns
