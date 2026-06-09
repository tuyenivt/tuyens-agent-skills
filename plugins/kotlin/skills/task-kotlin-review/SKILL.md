---
name: task-kotlin-review
description: Kotlin / Spring Boot code review: null safety, coroutines, !! abuse, @Transactional, JPA; spawns perf/security/observability subagents.
agent: kotlin-tech-lead
metadata:
  category: backend
  tags: [kotlin, spring-boot, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` is passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Step 1 and Step 2. Cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an AC / NFR / task; flag out-of-scope changes as blockers; flag missing coverage of in-scope ACs as gaps. Never edit `spec.md`, `plan.md`, `tasks.md`.

# Kotlin / Spring Boot Code Review

## Purpose

Staff-level review with Kotlin-aware checks: null safety / `!!` discipline, `data class` vs JPA, plugin presence, coroutine structured concurrency, `@Transactional` boundaries, Virtual Thread pinning, `@MockkBean` vs `@MockBean`. Coordinates perf / security / observability subagents in parallel.

The stack-specific delegate of `task-code-review` for Kotlin / Spring Boot. Runs standalone with full PR/branch resolution.

## When to Use

- Reviewing a Kotlin / Spring Boot PR before merge
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-kotlin-implement`), incident triage (`/task-oncall-start`), single-error debug (`task-kotlin-debug`), new-system architecture (`task-design-architecture`), or single-scope reviews (delegate directly to the perf / security / observability workflow).

## Depth Levels

| Depth      | When                                       | What runs                                       |
| ---------- | ------------------------------------------ | ----------------------------------------------- |
| `quick`    | "Is this safe to merge?" - time-pressured  | Risk snapshot + top 3 findings (Phase A + B)    |
| `standard` | Default                                    | Phases A-E                                      |
| `deep`     | Architectural PRs, post-incident, Principal sign-off | Phases A-E + historical patterns + cross-PR |

Default: `standard`.

**Auto-promote to `deep`** if Phase A blast radius is Wide or Critical and user didn't pass `quick`. Surface as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                |
| --------------- | -------------------------------------------------------- |
| Core            | Phases A-E (Kotlin-flavored)                             |
| + Perf          | Core + parallel `task-kotlin-review-perf`                |
| + Sec           | Core + parallel `task-kotlin-review-security`            |
| + Obs           | Core + parallel `task-kotlin-review-observability`       |
| Full            | Core + all three subagents in parallel                   |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Kotlin-tuned):**

- **Security**: file uploads, `SecurityFilterChain` / `@PreAuthorize` changes, `@RequestBody` data class changes, raw JPQL / native SQL, secrets in `application.yml`, `@KafkaListener` consuming user input
- **Perf**: new Flyway / Liquibase migration, new `@Query` / `@EntityGraph`, new `Pageable` endpoints, loops over collections hitting DB or HTTP, new `@Cacheable`, new `Flow<T>` streaming
- **Observability**: new `@Service` / `@Component`, new external client (`WebClient` / `RestClient`), new `@Async` / `@Scheduled` / `CoroutineScope.launch`, logging or actuator config change, new Micrometer registrations, new `@TransactionalEventListener`
- Two or more categories present - promote to **Full**

## Invocation

| Invocation                     | Meaning                                                                     |
| ------------------------------ | --------------------------------------------------------------------------- |
| `/task-kotlin-review`          | Current branch vs its base - fails fast on trunk                            |
| `/task-kotlin-review <branch>` | `<branch>` vs its base (3-dot diff)                                          |
| `/task-kotlin-review pr-<N>`   | PR head in local `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first |

**No checkout required.** Read via ref-qualified diffs. Pass `--base <branch>` when PR opened against a non-trunk base.

Scope and depth flags compose: `/task-kotlin-review pr-50273 --base release/2026.05 +sec deep`.

## Workflow

### Step 1 - Behavioral principles (mandatory, first)

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent dispatcher. If not Kotlin/Spring Boot, redirect to `/task-code-review`.

### Step 3 - Resolve diff

Use skill: `review-precondition-check`. Forward `--base <branch>`. If it stops with a fail-fast message, surface verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Once approved, read once and reuse:

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

Skip this step when invoked as a subagent and the parent passed the precondition handle plus diff + log.

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

### Step 4 - Scope auto-escalation

Scan files + diff for escalation signals. Log each as `signal: <category> -> <file:line>`.

- Zero or `core-only` → Core
- One category → add it
- Two+ → Full
- Explicit user scope → respect (don't downgrade)

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

Surface decision in Summary's `Scope:` field.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk`
- Use skill: `review-blast-radius`

Output risk level and blast radius before findings.

**Low-risk short-circuit:** Risk Low + Blast Narrow + no architecture-relevant files (security config, filters, API contracts, shared base classes, `application.yml`, Flyway migrations, `build.gradle.kts` plugins) - skip Phases C-D and produce Phase B findings only.

### Phase B - Kotlin correctness and safety

**Test coverage finding** (named, explicit, not buried in takeaways): if PR adds or modifies logic without JUnit / kotest / Spring slice / Testcontainers coverage. Minimum `[Recommend]`; escalate to `[Must]` for auth / Spring Security / `@PreAuthorize` / billing / multi-table writes / state machines / `CoroutineScope.launch` / `@KafkaListener` mutating data / Flyway changing column semantics.

**Kotlin checks:**

- [ ] **Null safety / `!!`**: no `!!` outside truly impossible-null sites; `T?` over `Optional<T>`; platform types treated nullable; `error()` / `requireNotNull` over `!!` for fail-fast
- [ ] **`data class` vs JPA**: every `@Entity` / `@MappedSuperclass` is a regular `class` with ID-based equals/hashCode
- [ ] **Kotlin plugins**: `kotlin("plugin.jpa")` + `kotlin("plugin.spring")` configured; no manual `open` workarounds
- [ ] **`@Transactional`**: writes at service layer (not controller / repository); no external I/O inside (use `@TransactionalEventListener(AFTER_COMMIT)` or outbox)
- [ ] **`@Transactional` self-invocation**: no `this.transactionalMethod()` from a same-bean caller
- [ ] **`@Transactional` on `suspend`**: no `withContext(...)` switches inside (detaches from TX)
- [ ] **Coroutine scope**: no `GlobalScope.launch`; fire-and-forget uses an injected `CoroutineScope` bean; `coroutineScope` for required fan-out; `supervisorScope` only with explicit fallbacks
- [ ] **`runBlocking`**: never in services / controllers; only at non-suspend framework boundaries
- [ ] **Dispatchers vs VTs**: with `spring.threads.virtual.enabled=true`, `Dispatchers.IO` for blocking JDBC is redundant; `Dispatchers.Default` for CPU only
- [ ] **`Flow` exception transparency**: no `throw` inside `collect`; cleanup in `finally` wrapped in `withContext(NonCancellable)` for suspend calls
- [ ] **Bean Validation**: every `@RequestBody` / `@RequestParam` data class has `@Valid` + `@field:`-targeted constraints
- [ ] **Strong typing**: `@RequestBody` uses DTOs, not JPA entities (mass-assignment risk - depth in `task-kotlin-review-security`)
- [ ] **N+1**: walking associations after a query uses `@EntityGraph` / `join fetch`; lazy access outside the TX flagged
- [ ] **`Optional` from repositories**: converted to `T?` at the boundary; no `.get()` without `isPresent()`
- [ ] **JPA entities in API**: controllers return DTOs / projections, never entities
- [ ] **Authorization present**: every controller method has matcher or `@PreAuthorize` (depth in `task-kotlin-review-security`)
- [ ] **Error handling**: `@RestControllerAdvice` + `ProblemDetail`; sealed-class results converted at controller boundary; no blanket `catch (e: Exception)`; no `println(e)` / `e.printStackTrace()`
- [ ] **Bulk operations**: partial-failure defined; idempotency for retryable bulk; JPA batch size sized
- [ ] **Idempotency on writes**: any new POST/PUT/PATCH that mutates state checks `Idempotency-Key` (or equivalent) and short-circuits replays. `[Must]` for money/billing, `[Recommend]` otherwise
- [ ] **Dual-write reliability**: DB write + event/HTTP publish uses outbox or `@TransactionalEventListener(AFTER_COMMIT)`. `BEFORE_COMMIT` for I/O = trap (rollback on listener exception); `AFTER_COMMIT` exceptions silently swallowed by default

**Migration PRs (any change in `db/migration/` or `db/changelog/`):**

- [ ] Two-phase deploys for rename / drop
- [ ] `NOT NULL` on existing columns via two-step
- [ ] `CREATE INDEX CONCURRENTLY` on large tables; concurrent statement outside a transaction
- [ ] FK validation deferred (or as a separate validate step)
- [ ] DDL and DML in separate migrations
- [ ] Rollback path documented
- Use skill: `ops-backward-compatibility` for client / in-flight impact
- Use skill: `kotlin-spring-db-migration-safety` for canonical patterns

**Concurrency:**

- [ ] Singleton beans hold no mutable state, or use `val` / `ConcurrentHashMap` / `AtomicReference` / lock
- [ ] **No `synchronized` on shared instances on Virtual Thread paths** (Boot 3.2+ with VT) - pins carrier thread. Use `ReentrantLock` or `Mutex`
- [ ] No `companion object` mutable fields (`var`) without explicit thread-safety design
- [ ] Race-prone updates use DB-level locking (`@Lock(LockModeType.PESSIMISTIC_WRITE)`, `@Version`)

Atomic skills consulted in Phase B:

- `kotlin-spring-jpa-performance` for JPA correctness
- `kotlin-spring-transaction` for `@Transactional` semantics
- `kotlin-spring-async-processing` for `@Async` / `CoroutineScope.launch`
- `kotlin-spring-exception-handling` for advice / sealed-result handling
- `kotlin-coroutines-spring` for `suspend` / `Flow`
- `kotlin-idioms` for general idiomatic review

### Phase C - Architecture guardrails

Use skill: `architecture-guardrail`.

- [ ] **Layering**: `@RestController` → `@Service` → `@Repository`. No business logic in controllers; no HTTP clients in repositories; no view rendering in services. Mapping via extension functions
- [ ] **Service-layer discipline**: controller orchestration > 5 lines extracted to `@Service`; intention-revealing service methods; cross-aggregate orchestration in services, not JPA `@PostPersist` / `@PostUpdate`
- [ ] **Anemic domain**: when rules accumulate in services and entities are pure data, flag for refactor (`task-kotlin-refactor`)
- [ ] **DI style**: primary-constructor injection only; no `@Autowired` fields; `lateinit` only for test fields and necessary cases; no `ApplicationContextAware`
- [ ] **Configuration**: typed `@ConfigurationProperties` over scattered `@Value`; profile-separated `application.yml`; no hardcoded config
- [ ] **Package layout**: feature-package preferred; cross-feature imports through public service interfaces
- [ ] **Multi-tenant isolation**: tenant scoping at repository / `@Filter` layer, not controller-only. `findByIdAndTenantId(id, tenantId)` over `findById(id)` + in-controller check (latter is racy)
- [ ] **Aspects**: cross-cutting concerns only - not hidden control flow that swallows exceptions or rewrites returns

Single-implementation `@Service` interface bloat is owned by Phase D (`kotlin-overengineering-review`).

**Multi-service PRs**: API contract compatibility checked (Spring Cloud Contract / Pact); deployment order documented or independent; use `ops-backward-compatibility` for inter-service changes.

### Phase D - AI-generated code quality

Use skill: `complexity-review`.
Use skill: `kotlin-overengineering-review` for the necessity catalog (redundant Bean Validation, defensive guards on guarantees, premature abstraction, scope-function nesting, single-variant sealed classes).

**AI smells not in the necessity catalog:**

- [ ] **Java-in-Kotlin**: `if (x != null)` chains over `?.` / `?:`; `for` loops over `map` / `filter`; companion-object statics where extension functions fit; `CompletableFuture` over `suspend`
- [ ] **Redundant mapping**: `Entity → Domain → ServiceDTO → ResponseDTO` when one extension function suffices
- [ ] **Test verbosity**: `@SpringBootTest` setup > 30 lines for a single assertion; `@MockkBean` chains that should be a slice
- [ ] **Reactive / coroutine misapplication**: `Mono` / `Flux` (or `suspend`) in a non-coroutine servlet stack
- [ ] **Comment cruft**: comments restating method names; KDoc on private helpers; stale TODOs

### Phase E - Maintainability

- [ ] **Naming**: services describe the operation (`OrderFulfillmentService`); data classes name their role; no `Util` / `Manager` / `Helper` accumulators; `internal` over `public` for module-local symbols
- [ ] **Magic numbers / strings**: extracted to `const val` / `@ConfigurationProperties`; `Duration.ofMinutes(...)` over `60_000L`
- [ ] **Hardcoded URLs / credentials**: in `application.yml` / env / Vault
- [ ] **Method length**: > 20 lines reviewed for extraction; > 50 lines flagged unless orchestrating private methods
- [ ] **Duplicated queries**: same JPQL / `Specification` in 3+ places extracted
- [ ] **Logging hygiene**: parameterized SLF4J (`log.info("order={}", id)`) - **never** Kotlin string templates (`log.info("order=$id")`); correct levels; no `println` / `System.out`
- [ ] **KDoc**: on public extension and `suspend` function contracts (cancellation, exception propagation)
- [ ] **`val` over `var`** except framework-required mutable fields

Use skill: `backend-coding-standards` for cross-language naming.
Use skill: `ops-observability` for cross-cutting logging / metrics presence (depth: `task-kotlin-review-observability`).

### Step 5 - Delegate extra scopes (if scope includes)

Spawn subagents in parallel:

| Scope                | Subagents                                                                                          |
| -------------------- | -------------------------------------------------------------------------------------------------- |
| Core + Perf          | `task-kotlin-review-perf`                                                                          |
| Core + Sec           | `task-kotlin-review-security`                                                                      |
| Core + Obs           | `task-kotlin-review-observability`                                                                 |
| Full                 | All three in parallel                                                                              |

Each subagent prompt includes: resolved review target (`base_ref`, `head_ref`) + pre-read diff + log, depth, pre-confirmed stack, instruction to use its own Output Format.

If a subagent fails: continue with remaining results. Note `Scope incomplete: <scope>` in Summary.

### Step 6 - Synthesize (if Step 5 ran)

- Deduplicate cross-cutting findings (same issue across scopes → one entry citing all)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`
- Preserve `file:line`
- Order by intent, not scope
- Merge Next Steps into one prioritized list

### Step 6.5 - Reconcile Prior Findings (incremental mode only)

Skip if `mode = full`. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `incremental_diff`: from Step 3.5c
- `name_status`: from Step 3.5c

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |
| [Question]   | Author must answer; reviewer decides if a fix follows.                   |

No `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Scope:** Core | +Sec | +Perf | +Obs | Full _(if auto-escalated, append `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append `auto-promoted from standard; Blast Radius: <level>`)_
**Round:** <N>                                _(include from round 2 onward)_
**Mode:** incremental (since <prior_head_sha_short>) | full _(include from round 2 onward)_
**Diff Range:** <range_short> (<N> commits, <M> files) _(incremental rounds only)_

## Prior Round Reconciliation _(incremental rounds only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line
- Issue: [Kotlin/Spring idiom: `!!` abuse, `data class` JPA, missing `kotlin-jpa` plugin, `GlobalScope.launch`, `synchronized` on VT, `@Transactional` self-invocation, `every` on suspend, etc.]
- Impact: [user-visible / operational]
- System Risk: [why systemic]
- Fix: [concrete Kotlin change with code]

### [Recommend] file:line
- Issue:
- Impact:
- Fix:

### [Question] file:line
- Question:
- Why it matters:

## Architecture Notes
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes
- Over-engineering:
- Simplification opportunities:

## Key Takeaways
- 2-4 bullets, systemic impact, what to address before merge

## Next Steps
Prioritized, each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question. On incremental rounds, prior-round `Still open` items are folded in with `(open since round <N>)` suffix and ordered by intent alongside new findings.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] OldFile.kt:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope] - [one-line action]

_Omit empty sections._
```

### Step 7 - Write report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode` (from Step 3.5), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted in Phase A), `stack = kotlin-spring-boot`

Print the confirmation line.

## Self-Check

- [ ] `behavioral-principles` loaded; stack confirmed
- [ ] `review-precondition-check` ran (or parent handle reused); diff + log read once; `current_head_sha` and `current_base_sha` captured
- [ ] For `pr-ref`, fetch surfaced and local ref existed; `head_matches_current` resolved
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Scope auto-escalation evaluated; depth auto-promoted on Wide/Critical; scope expansion vs. prior round noted when applicable
- [ ] Risk + blast radius stated before findings
- [ ] Phases B-E applied via the named atomic skills; missing tests raised as explicit finding
- [ ] Every Must cites system risk; every finding has label + file:line + Kotlin fix
- [ ] If `--spec`, every finding traces to AC / NFR / task or flagged out-of-scope blocker
- [ ] Extra scopes ran in parallel; findings deduped, strongest intent wins; failed scopes noted
- [ ] Step 6.5 - on incremental rounds, `review-prior-findings-reconcile` ran; reconciliation table inserted; `Still open` rows folded into Next Steps with `(open since round <N>)` suffix
- [ ] Next Steps tagged `[Implement]` / `[Delegate]`, ordered by intent; carry-overs from prior round inline-suffixed, not in a separate section
- [ ] Report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed

## Avoid

- State-changing git from this workflow. The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Reviewing without reading full diff + log
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Generic backend advice when a Kotlin idiom applies
- Nitpicking style without a project standard
- Vague feedback without concrete Kotlin fix
- Blocking on preference vs correctness / risk / maintainability
- Running extra scopes when `core-only` was passed
- Sequential extra scopes that could run in parallel
- Appending raw subagent reports section-by-section
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Recommending `WebSecurityConfigurerAdapter`, `@Autowired` fields, `data class` JPA, `GlobalScope.launch`, `every` for suspend, `@MockBean` for Kotlin
