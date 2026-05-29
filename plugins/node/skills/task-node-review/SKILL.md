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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles`. Cross-check every changed surface against `spec.md` / `plan.md`: each change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**; missing in-scope coverage is a gap. Never edit spec artifacts.

# Node.js Code Review

Staff-level Node.js / NestJS / Express code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a NestJS or Express PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**
- Pre-implementation design (`task-node-implement`)
- Production incident (`/task-oncall-start`)
- Single-error debug (`task-node-debug`)
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-node-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `quick` | Time-constrained risk snapshot | Risk snapshot + top 3 findings (Phase A + B summary) |
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical pattern matching + cross-PR context |

**Auto-promote to `deep`:** After Phase A, if `Blast Radius` is Wide or Critical and the user did not pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Node-flavored) |
| + Perf | Core + `task-node-review-perf` subagent |
| + Security | Core + `task-node-review-security` subagent |
| + Observability | Core + `task-node-review-observability` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Node-tuned):**

- **+Security:** file uploads (`multer`, `FileInterceptor`, `@UploadedFile()`), auth strategy / guard changes (`AuthGuard('jwt')`, `JwtStrategy`, `requireAuth`), DTO / Zod schema changes, raw SQL via `$queryRawUnsafe` / `repository.query`, secrets in env / config, BullMQ consuming user input, `Object.assign(target, req.body)`
- **+Perf:** new Prisma / TypeORM migration, new ORM query (`findMany` / `find` / `createQueryBuilder`), new `include` / `relations`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `lru-cache` / Redis read paths
- **+Observability:** new service / module, new external client (`axios.create`, `undici` Pool), new BullMQ producer / processor, logging config change (`pino` / `winston`), new `prom-client`, new lifecycle hook (`OnModuleInit`, `OnApplicationBootstrap`)
- **2+ categories → Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-node-review` | Current branch vs base; fails fast on trunk |
| `/task-node-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-node-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-node-review pr-50273 --base release/2026.05 +security deep`.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not Node, stop and recommend `/task-code-review`.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express (`express` without NestJS). Detect ORM: Prisma vs TypeORM. Record `Framework` and `ORM` for branching in later phases.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop.

Once approved, read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

**Skip entirely** when invoked as a subagent and the parent passed the handle plus pre-read artifacts.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` → stay Core
- One signal category → add matching extra scope
- 2+ categories → promote to Full
- User passed an explicit scope → respect it; still log signals so the Summary documents why

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth strategies / guards, middleware, API contracts, shared base classes, `app.module.ts` / `app.ts`, migrations), skip Phases C-D and produce a streamlined output with Phase B only.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical and user did not pass `quick`, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

### Phase B - Node Correctness and Safety

Apply atomic skills. Each owns the canonical patterns; this phase flags deviations and surfaces what they did not see:

- Use skill: `node-typescript-patterns` - `strict: true` not relaxed, no floating promises, no `as any` in non-test code
- Use skill: `node-prisma-patterns` (Prisma) or `node-typeorm-patterns` (TypeORM) - transactions, `include`/`relations`, post-commit dispatch
- Use skill: `node-bullmq-patterns` if diff touches BullMQ jobs
- Use skill: `node-migration-safety` if diff touches `prisma/migrations/` or `src/migrations/`. Also use skill: `ops-backward-compatibility` for client/in-flight impact

**Additional Node-specific checks the atomics don't own:**

- **Test coverage finding (named, not buried).** PR adds logic without Jest coverage? At minimum `[Suggestion]`; escalate to `[High]` when the change is critical path: auth (JWT / Passport / `AuthGuard`), authorization (guards / `requireAuth`), money / billing, multi-table writes, state machines, BullMQ mutators, migrations changing column semantics. Surface as a dedicated finding.
- **Event-loop blocking in request paths.** `fs.readFileSync` / `crypto.pbkdf2Sync` / large `JSON.parse` / catastrophic regex flagged (presence/absence here; depth - impact heuristic, `worker_threads`, `AbortSignal` - belongs to perf subagent).
- **Validation strict-mode wired.** NestJS `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))` in `main.ts`; Express Zod schemas use `.strict()`. Absence is a critical correctness + security gap.
- **Authorization + IDOR.** Authn (guard / middleware) proves identity, not object access. Per-owner / per-tenant endpoints must scope at the repository: `where: { id, userId: user.sub }`, `tenantId` injected by middleware/extension.
- **Response DTO field hygiene.** Compare the DTO against entity columns. Flag `passwordHash` / `mfaSecret` / `recoveryCodes` / `apiKey` / `webhookSecret` / `internalNotes` / `auditLog` / `isAdmin` / `internalCreatedBy` on the wire. Returning a Prisma model or TypeORM entity directly is `[High]` regardless of current fields - a new sensitive column silently leaks later.
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
- **Anemic domain (deep depth only):** business rules accumulating in services while ORM models stay pure data - flag for `task-node-refactor`. Do not raise on a single PR's evidence alone

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
- **Logging hygiene:** surface `console.log` in prod paths, lines without correlation IDs, wrong levels as `[Suggestion]` (depth in observability subagent)

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread:

| Scope | Subagents |
|-------|-----------|
| + Perf | `task-node-review-perf` |
| + Security | `task-node-review-security` |
| + Observability | `task-node-review-observability` |
| Full | All three in parallel |

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (Node / TypeScript) + framework (NestJS / Express / mixed) + ORM (Prisma / TypeORM)
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Highest severity wins** (`Blocker` > `High` > `Suggestion` > `Question`)
- **Preserve `file:line` citations**
- **Order by severity**, not by scope
- **Note missing scopes** in Summary as `Scope incomplete: <scope>`
- **Merge Next Steps** with `[Implement]` / `[Delegate]` tags preserved; re-sort by severity

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Write before ending; print the confirmation line.

## Feedback Labels

| Label | Meaning | Required |
|-------|---------|----------|
| [Blocker] | Must fix before merge - correctness / risk | Yes |
| [High] | Should fix - significant impact | Strong |
| [Suggestion] | Would improve - non-blocking | No |
| [Question] | Need clarity from author | Clarify |

No `[Nitpick]` or `[Praise]`.

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

- Issue: [name the Node idiom: blocking `crypto.pbkdf2Sync` in async handler, missing `@UseGuards`, ORM entity returned from controller, BullMQ `queue.add` inside transaction, `ValidationPipe` missing `whitelist: true`, `Object.assign(target, req.body)` prototype-pollution surface, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Node change with code]

### [High] file:line
- Issue: ...
- Impact: ...
- Fix: ...

### [Suggestion] file:line
- Improvement: ...

### [Question] file:line
- Question: [what is ambiguous]
- Why it matters: [what the right next step depends on]

_Use [Question] for genuine ambiguity, not as a softer Blocker._

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

Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Blocker heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Node conventions, not generic backend conventions
- Provide actionable feedback with TypeScript code examples
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] `behavioral-principles` loaded; stack, framework, ORM recorded (Steps 1-2)
- [ ] `review-precondition-check` ran (or handle received); diff/log read once (Step 3)
- [ ] Scope auto-escalation evaluated and recorded; depth auto-promoted on Wide/Critical blast radius (Step 4, 4.5)
- [ ] Risk + blast radius stated before any finding (Phase A)
- [ ] Phase B: atomic skills applied; test-coverage gap raised as named finding; event-loop, validation strict, authz / IDOR, response-DTO hygiene, Idempotency-Key, race safety, migration safety all checked
- [ ] Phase C: layering, DI, settings, listener / middleware, multi-tenant
- [ ] Phase D: `complexity-review` + framework-matching necessity skill applied
- [ ] Phase E: naming, magic numbers, function length, logging hygiene
- [ ] Every Blocker states a system risk; every finding has label + `file:line` + actionable Node fix
- [ ] Spec mode: every finding traces to AC/NFR/task or is flagged out-of-scope
- [ ] Extra scopes ran in parallel; subagent findings merged severity-ordered (no raw reports); missing scope noted as `Scope incomplete: <scope>`
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered by severity
- [ ] Report written via `review-report-writer`; confirmation printed

## Avoid

- `git fetch` / `git checkout` from this workflow - user runs these
- Reviewing without reading the full diff and commit log first
- Generic backend conventions when a Node idiom exists ("extract to a service module", not "extract to a helper class")
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security / observability depth here when the dedicated subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Recommending sync `fs.readFileSync` / `crypto.pbkdf2Sync` in request paths, `eval` / `new Function` on untrusted input, or `Object.assign(target, req.body)` as acceptable patterns
