---
name: task-spring-review
description: "Spring Boot PR review: layering, fat controllers, JPA leaks, @Transactional misuse, VT pinning; parallel perf/security/obs subagents."
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Code Review

Spring-aware staff-level review umbrella. Stack-specific delegate of `task-code-review`. Runs standalone with full PR/branch resolution. Coordinates Spring perf / security / observability subagents in parallel.

## When to Use

- Pre-merge Spring Boot PR review, post-AI-generation quality gate, architecture drift detection.
- **Not for:** design (`task-spring-implement`), incidents (`/task-oncall-start`), debugging (`task-spring-debug`), new-system architecture (`task-design-architecture`), single-scope reviews (delegate to `task-spring-review-{perf,security,observability}`).

## Depth and Scope

| Depth      | When                                                              | Runs                                  |
| ---------- | ----------------------------------------------------------------- | ------------------------------------- |
| `quick`    | Fast "safe to merge?" snapshot                                    | Phase A + B summary, top 3 findings   |
| `standard` | Default                                                           | Phases A-E                            |
| `deep`     | Architectural PRs, post-incident review, Principal sign-off       | A-E + historical pattern matching     |

**Auto-promote to `deep`** when Phase A yields Blast Radius `Wide`/`Critical` and the user did not pass `quick`. Surface as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

| Scope             | Adds                                       |
| ----------------- | ------------------------------------------ |
| Core (default)    | Phases A-E only                            |
| + Perf            | `task-spring-review-perf` subagent         |
| + Security        | `task-spring-review-security` subagent     |
| + Observability   | `task-spring-review-observability` subagent|
| Full              | All three in parallel                      |

**Auto-escalation signals** (Step 4 scans the diff; pass `core-only` to suppress):

- **Security:** `MultipartFile`, `SecurityFilterChain`, `@PreAuthorize`/`@PostAuthorize`, `@RequestBody` DTO changes, raw JPQL/native SQL, secrets in `application.yml`, listener consuming user input.
- **Perf:** new Flyway/Liquibase migration, new `@Query`/`@EntityGraph`, new `Pageable` endpoint, loop hitting DB/HTTP, new `@Cacheable`.
- **Obs:** new `@Service`/external client (`RestClient`/`WebClient`/Feign), new `@Async`/`@Scheduled`, logging or actuator change, new Micrometer `Timer`/`Counter`, new `@TransactionalEventListener`.

Two-plus categories -> Full. User-passed scope wins but signals are still recorded so the Summary documents what was deferred.

## Invocation

| Form                            | Meaning                                                           |
| ------------------------------- | ----------------------------------------------------------------- |
| `/task-spring-review`           | Current branch vs base; fails fast on trunk                       |
| `/task-spring-review <branch>`  | `<branch>` vs base (3-dot diff)                                   |
| `/task-spring-review pr-<N>`    | User-fetched local ref `pr-<N>`; see `review-precondition-check`  |

Flags compose: `/task-spring-review pr-50273 --base release/2026.05 +security deep`. No checkout required.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Spec-Aware Preamble (conditional)

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the diff, use skill: `spec-aware-preamble`. Cross-check the diff against `spec.md` and `plan.md`: every changed surface traces to an AC/NFR/task; out-of-scope -> blocker; missing AC coverage -> gap. Never edit spec artifacts.

### Step 3 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review`.

### Step 4 - Resolve the Diff

Use skill: `review-precondition-check` (forward `--base`). Surface fail-fast messages verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 4.5; for now, just hold onto it.

Once approved, read once and reuse (skip when a parent passed the handle plus artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

### Step 4.5 - Decide Mode (re-review auto-detect)

Skip if the handle has no `prior_checkpoint` -> `mode = full`, `round = 1`, no fetch, no reconciliation. Continue to Step 5.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `mode = full`, `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 5.

Otherwise (valid prior checkpoint present):

**Step 4.5a - Auto-fetch the head branch.** Only when a valid prior checkpoint exists, refresh the local tracking ref so a script can re-run the same command without manually fetching:

```bash
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "<head_ref>@{u}" 2>/dev/null)
```

If `upstream` resolves to `<remote>/<branch>` form, split and run:

```bash
git fetch <remote> <branch>
```

No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. After a successful fetch, re-resolve `current_head_sha = git rev-parse <head_ref>`.

**Step 4.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` and stop. Do not call `review-report-writer`. |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `mode = full`, `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten; full re-review.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round> - full re-review.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round> - full re-review.`           |
| None of the above                                                       | `mode = incremental`, `round = prior.round + 1`, `incremental_range = <prior_head_sha>...<current_head_sha>`.                       |

**Step 4.5c - Incremental: re-read the diff scoped to the new range.**

If `mode = incremental`, replace the diff read from Step 4 with:

- `git diff <prior_head_sha>...<current_head_sha>`
- `git diff --name-status <prior_head_sha>...<current_head_sha>`
- `git log --oneline <prior_head_sha>..<current_head_sha>`

The full-range diff from Step 4 is discarded; all Phase A-E analysis operates on the incremental range only.

**Step 4.5d - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.` The reconciliation table only covers findings whose scope was active in the prior round.

### Step 5 - Evaluate Auto-Escalation

Scan files and diff against signal categories (above). Log `signal: <category> -> <file:line>` for each match. Resolve scope (Core / +X / Full) and surface in Summary: `auto-escalated from Core; signals: <list>` or, when user-pinned with conflicting signals, `Scope user-pinned; <category> signals present: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk`.
- Use skill: `review-blast-radius`.
- Output Risk and Blast Radius before findings.

**Low-risk short-circuit:** Risk `Low` + Blast Radius `Narrow` + no architecture-relevant files touched (security config, filters, API contracts, shared base classes, aspects, `application.yml`, migrations) -> skip Phases C-D, deliver Phase B findings only.

### Phase B - Spring Correctness and Safety

Logical correctness, error handling, backward compatibility, transaction boundary correctness. Use atomic skills `spring-transaction`, `spring-jpa-performance`, `spring-async-processing`, `spring-exception-handling`, `spring-messaging-patterns` as relevant.

**Spring idioms (cite the named smell in findings):**

- [ ] **Transactions** - writes at service layer; no HTTP/broker/IO inside `@Transactional`; `readOnly = true` on reads; `rollbackFor` for checked exceptions; no `this.txMethod()` self-invocation.
- [ ] **JPA in API** - controllers never expose `@Entity` types; DTO/record/projection only.
- [ ] **N+1** - `@EntityGraph`/`join fetch` wherever lazy associations are walked post-query (depth -> `task-spring-review-perf`).
- [ ] **Bean Validation** - `@Valid` on every `@RequestBody`/`@RequestParam` DTO; no manual checks duplicating annotations.
- [ ] **Authorization coverage** - every controller method covered by `SecurityFilterChain` matcher or `@PreAuthorize`; `permitAll` documented (depth -> `task-spring-review-security`).
- [ ] **Error handling** - `@RestControllerAdvice` maps validation/not-found/access-denied; no blanket `catch (Exception)`; no `printStackTrace()`.
- [ ] **Optional discipline** - `.orElseThrow`/`.map`; never `.get()` unguarded; never as a parameter.
- [ ] **Idempotency** - monetary/notification side effects accept an idempotency key.
- [ ] **Dual-write** - `save` + `kafkaTemplate.send` + `save` in `@Transactional` is a smell; use outbox or `AFTER_COMMIT`.
- [ ] **VT pinning** - on `spring.threads.virtual.enabled=true`, no `synchronized` on shared instances; use `ReentrantLock`/`StampedLock`.
- [ ] **Race-prone updates** - counters/balances/state transitions use `@Lock(PESSIMISTIC_WRITE)`/`@Version`/`SELECT FOR UPDATE`.
- [ ] **Singleton state** - no mutable fields; if required, `final` immutable, `ConcurrentHashMap`, `AtomicReference`, or lock-guarded.
- [ ] **Bulk operations** - partial-failure path; `hibernate.jdbc.batch_size` set; retries idempotent.

**Test coverage as a named finding** (not buried in Takeaways): logic changes without JUnit / slice / Testcontainers -> `[Recommend]`; escalate to `[Must]` for security, money, multi-table state machines, `@Async`/`@KafkaListener` mutations, or migrations changing column semantics.

**Migration PRs** (`db/migration/`, `db/changelog/`) - use skills `spring-db-migration-safety`, `ops-backward-compatibility`:

- [ ] Column rename/drop via two-phase deploy (add -> backfill -> cut over -> remove).
- [ ] New `NOT NULL` on existing columns via two-step (add nullable -> backfill -> set NOT NULL).
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY`, split outside a transaction.
- [ ] FKs validated separately (`NOT VALID` then `VALIDATE`).
- [ ] Long backfills isolated from DDL, not inline in Flyway/Liquibase.
- [ ] Rollback path documented.

### Phase C - Spring Architecture Guardrails

Use skill: `architecture-guardrail`.

- [ ] **Layering** - `@RestController` -> `@Service` -> `@Repository`. No business logic in controllers; no HTTP clients in repos/entities; no view rendering in services. DTO mapping at service/controller boundary.
- [ ] **Service-layer discipline** - controller orchestration > 5 lines -> extract `@Service`; methods reveal intent (`fulfillOrder(orderId)`) over CRUD pass-through; cross-aggregate work lives in a service, not `@PostPersist`/`@PostUpdate`.
- [ ] **Anemic domain** - rules accumulating in services with entities as pure data -> flag for refactor (see `task-spring-refactor`).
- [ ] **DI style** - constructor only; `final` fields with `@RequiredArgsConstructor`; no setter injection, no field `@Autowired`, no `ApplicationContextAware`.
- [ ] **Configuration** - typed `@ConfigurationProperties` records over `@Value`; profiles separated; no hardcoded values.
- [ ] **Module boundaries** - feature-package layout; cross-feature access via public service interfaces, not direct `OtherFeatureRepository` calls.
- [ ] **Multi-tenant isolation** - tenant scoping at repository/`@Filter`/`@TenantId` layer. Derived queries like `findByIdAndUserId` are acceptable only when every read on that aggregate uses one - a single missing variant exposes other tenants' data.
- [ ] **Read replica / routing** - `AbstractRoutingDataSource` reads declare target via `@Transactional(readOnly = true)` or explicit annotation; no surprise cross-DB joins.
- [ ] **Aspect discipline** - `@Aspect` for genuinely cross-cutting concerns, not hidden control flow.

**Multi-service PRs:** API contract compatibility verified (Spring Cloud Contract/Pact); deployment order documented or independent; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` for verbosity. Use skill: `spring-overengineering-review` for necessity findings (redundant Bean Validation, defensive guards, premature abstraction) - the atomic owns the catalog.

**Additional Spring AI smells:**

- [ ] Redundant mapping chains (`Entity -> Domain -> ServiceDTO -> ResponseDTO` when one would do).
- [ ] `@SpringBootTest` > 30 lines for a single assertion; `@MockBean` chains better served by a slice test.
- [ ] `Mono`/`Flux` in a servlet stack.
- [ ] Comments restating method names; Javadoc on private helpers; stale TODOs.

### Phase E - Spring Maintainability

Use skill: `backend-coding-standards`. Use skill: `ops-observability` for cross-cutting logging/metrics presence.

- [ ] **Naming** - operations described (`OrderFulfillmentService` over `OrderHelper`); records named by role (`OrderUpdateRequest`); no `Util`/`Manager`/`Helper` grab bags; package-private over `public` when not crossing the feature boundary.
- [ ] **Magic numbers/strings** - `static final` or `@ConfigurationProperties`; durations use `Duration.ofMinutes(...)`.
- [ ] **Hardcoded URLs/credentials** - in `application.yml`/env/Vault.
- [ ] **Method length** - > 20 lines reviewed for extraction; > 50 flagged unless clearly orchestrating named helpers.
- [ ] **Duplicated queries** - same JPQL/`Specification` predicate in 3+ places -> `Specification` factory or repo method.
- [ ] **Logging hygiene** - SLF4J parameterized, not concatenation; correct levels; MDC for structured fields (depth -> `task-spring-review-observability`).

### Step 6 - Delegate Extra Scopes in Parallel

Skip if Core only. Spawn each extra subagent in parallel with the main thread.

| Scope                | Subagents                                                          |
| -------------------- | ------------------------------------------------------------------ |
| Core + Perf          | `task-spring-review-perf`                                          |
| Core + Security      | `task-spring-review-security`                                      |
| Core + Observability | `task-spring-review-observability`                                 |
| Full                 | All three in parallel                                              |

**Subagent prompt contract:** pass the resolved `base_ref`/`head_ref`, the already-read diff and commit log, depth level, and pre-confirmed stack. Subagent skips `review-precondition-check` and re-reading the diff. Return findings using its own Output Format.

**Failure isolation:** if a subagent fails or times out, continue. Record `Scope incomplete: <scope> review did not complete` under Summary.

### Step 7 - Synthesize

Skip if Step 6 didn't run. Merge subagent findings into the single Output Format - never append raw reports.

- **Deduplicate** cross-cutting findings (e.g., external call in `@Transactional` flagged by Phase B and Perf) into one entry citing all scopes.
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`.
- **Preserve `file:line` citations**; order by severity, not by scope.
- **Merge Next Steps**: combine, preserve `[Implement]`/`[Delegate]`, dedupe, re-sort.

### Step 7.5 - Reconcile Prior Findings (incremental mode only)

Skip if `mode = full`. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `incremental_diff`: from Step 4.5c
- `name_status`: from Step 4.5c

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

### Step 8 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode` (from Step 4.5), `round` (from Step 4.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 5), `depth` (resolved/auto-promoted in Phase A), `stack = java-spring-boot`

The report writer owns label semantics (`[Must]` / `[Recommend]` / `[Question]` - no severity-mixed `[Blocker]`/`[High]`/`[Suggestion]`, no `[Nit]`/`[Consider]`/`[Praise]`).

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Java <version> / Spring Boot <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(append `auto-escalated from Core; signals: <list>` if applicable)_
**Depth:** quick | standard | deep _(append `auto-promoted from standard; Blast Radius: <level>` if applicable)_
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
- Issue: [named Spring idiom: `@Transactional` self-invocation, fat controller, JPA entity in API, field `@Autowired`, missing `@PreAuthorize`, `synchronized` on VT, dual-write, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Spring change with code]

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
- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways
- 2-4 bullets summarizing systemic impact and what to address before merge.

## Next Steps
Prioritized, each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question. On incremental rounds, prior-round `Still open` items are folded in with `(open since round <N>)` suffix and ordered by intent alongside new findings.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] OldFile.java:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

Omit empty sections.

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - spec preamble loaded when `--spec` / `.specs/<slug>/spec.md` present; findings traced to AC/NFR/task or flagged out-of-scope
- [ ] Step 3 - stack confirmed (or accepted from parent)
- [ ] Step 4 - `review-precondition-check` ran (or handle received); diff/commit log read once; `current_head_sha` and `current_base_sha` captured
- [ ] Step 4.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Step 5 - scope decision recorded with firing signals; user-pinned conflicts surfaced; scope expansion vs. prior round noted when applicable
- [ ] Phase A - Risk and Blast Radius stated before findings; depth auto-promoted on Wide/Critical unless `quick`
- [ ] Phase B - Spring idioms applied (transactions, JPA-in-API, authz coverage, exception advice, VT pinning, dual-write); migration safety where applicable; missing tests raised as named finding
- [ ] Phase C - layering, anemic domain, constructor injection, configuration, boundaries, multi-tenant
- [ ] Phase D - `complexity-review` + `spring-overengineering-review` invoked; remaining AI smells covered
- [ ] Phase E - maintainability applied
- [ ] Step 6 - subagents ran in parallel with pre-resolved handle (when scope > Core)
- [ ] Step 7 - findings deduped, highest-severity wins, severity-ordered, raw subagent reports not appended; missing scopes noted
- [ ] Step 7.5 - on incremental rounds, `review-prior-findings-reconcile` ran; reconciliation table inserted; `Still open` rows folded into Next Steps with `(open since round <N>)` suffix
- [ ] Step 8 - report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation printed
- [ ] Every Must cites system risk; every finding has label, `file:line`, actionable Spring fix
- [ ] Next Steps tagged `[Implement]`/`[Delegate]`, ordered Must > Recommend > Question (omit if none); carry-overs from prior round inline-suffixed, not in a separate section

## Avoid

- State-changing git (`checkout`/`merge`/`pull`/`rebase`) from this workflow. The one allowed exception is `git fetch <remote> <branch>` in Step 4.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Reviewing without reading full diff + commit log first.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Generic backend phrasing when a Spring idiom exists ("extract to a `@Service`", not "helper class").
- Vague feedback without a concrete Spring fix; blocking on personal preference; nitpicking absent project standard.
- Running perf/security/observability when user passed `core-only`; sequential subagent runs when they could be parallel.
- Appending raw subagent reports instead of one severity-ordered list.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Approving `WebSecurityConfigurerAdapter`, field `@Autowired`, or `@Transactional` self-invocation.
