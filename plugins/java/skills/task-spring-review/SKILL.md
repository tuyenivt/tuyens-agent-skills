---
name: task-spring-review
description: "Spring Boot PR review: layering, fat controllers, JPA leaks, @Transactional misuse, VT pinning; parallel perf/security/obs/reliability subagents."
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Code Review

Spring-aware staff-level review umbrella. Stack-specific delegate of `task-code-review`. Runs standalone with full PR/branch resolution. Coordinates Spring perf / security / observability / reliability subagents in parallel.

## When to Use

- Pre-merge Spring Boot PR review, post-AI-generation quality gate, architecture drift detection.
- **Not for:** design (`task-spring-implement`), debugging, new-system architecture (`task-design-architecture`), single-scope reviews (delegate to `task-spring-review-{perf,security,observability,reliability}`).

## Depth and Scope

| Depth      | When                                                              | Runs                                  |
| ---------- | ----------------------------------------------------------------- | ------------------------------------- |
| `standard` | Default                                                           | Phases A-E                            |
| `deep`     | Architectural PRs, post-incident review, Principal sign-off       | A-E + repo-history pass: `git log` the touched files for recurring fix/revert/hotfix churn and check prior review reports for repeat findings |

Depth is resolved in Phase A, not before. Subagents interpret the passed `depth` per their own depth tables (e.g., perf `deep` is profiling-driven; lacking profiling access it delivers estimates and says so) - the umbrella does not redefine their semantics.

| Scope             | Adds                                        |
| ----------------- | ------------------------------------------- |
| Core (default)    | Phases A-E only                             |
| + Perf            | `task-spring-review-perf` subagent          |
| + Sec             | `task-spring-review-security` subagent      |
| + Obs             | `task-spring-review-observability` subagent |
| + Rel             | `task-spring-review-reliability` subagent   |
| Full              | All four in parallel                        |

**Auto-escalation signals** (Step 5 evaluates them; pass `core-only` to suppress):

- **Security:** `MultipartFile`, `SecurityFilterChain`, `@PreAuthorize`/`@PostAuthorize`, `@RequestBody` DTO changes, a response DTO gaining a field sourced from an entity, raw JPQL/native SQL, secrets in any `application*.yml`, listener consuming user input.
- **Perf:** new **or modified** Flyway/Liquibase migration, new `@Query`/`@EntityGraph`, new `Pageable` endpoint, loop hitting DB/HTTP, new `@Cacheable`.
- **Obs:** new `@Service`/external client (`RestClient`/`WebClient`/Feign), new `@Async`/`@Scheduled`, logging or actuator change, new Micrometer `Timer`/`Counter`, new `@TransactionalEventListener`.
- **Reliability:** external client without an explicit timeout or breaker, new `@Retryable`/Resilience4j config, `save` + `kafkaTemplate.send` in one `@Transactional`, new `@KafkaListener`/`@RabbitListener`, new `@Async`/`@Scheduled` with an unbounded executor or queue, new idempotency-key or outbox flow.

Two-plus categories -> Full. User-passed scope wins; firing signals are still recorded so the Summary documents what was deferred.

## Invocation

| Form                            | Meaning                                                           |
| ------------------------------- | ----------------------------------------------------------------- |
| `/task-spring-review`           | Current branch vs base; fails fast on trunk                       |
| `/task-spring-review <branch>`  | `<branch>` vs base (3-dot diff)                                   |
| `/task-spring-review pr-<N>`    | User-fetched local ref `pr-<N>`; see `review-precondition-check`  |

Bare positional flags compose in any order after the target: `+sec` `+perf` `+obs` `+rel` (repeatable), `core-only`, `standard`, `deep`. Example: `/task-spring-review pr-50273 --base release/2026.05 +sec deep`. No checkout required.

`--req <path>` takes exactly one path naming a requirement source (ticket export, PRD, spec) for Phase 0; read the file yourself and pass its contents. If the path does not resolve, do not stop - record `Requirement source <path> not found; Phase 0 ran on commits.` in Summary Notes and continue as if no source was passed. Without `--req`, Phase 0 uses whatever requirement is already in context.

## Workflow

Execute in the order printed. A delegated skill's output is either **carried** or **consumed**, and each delegation below says which. Carried: `review-change-intent`'s Change Brief and traceability table, Phase A's Risk and Blast Radius blocks, `review-prior-findings-reconcile`'s table, and a subagent's deep-only section - these land in the report verbatim, in the slot the Output Format names. Consumed: every atomic loaded as a checklist in Phases B-E - their own Output Format blocks are never emitted, and what they surface becomes findings in this workflow's format.

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` (forward `--base`). Surface fail-fast messages verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior review report exists). Decision logic is Step 4; for now, just hold onto it.

Once approved, read once and reuse (skip when a parent passed the handle plus artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git ls-tree -r --name-only <head_ref>` (the head file list - Step 9 needs it to tell a deleted path from an untouched one)
- `git log --oneline <base_ref>..<head_ref>`

Also capture the SHAs for the report's checkpoint frontmatter: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 4 - Decide Round (re-review auto-detect)

**Every round analyzes the full `<base_ref>...<head_ref>` range read in Step 3.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change on every round, so a small follow-up commit cannot under-score a large PR and a defect missed in round 1 stays reachable in round 2. Rounds differ only in that round 2+ reconciles against the prior report.

No `prior_checkpoint` in the handle -> `round = 1`, no fetch, no reconciliation. Continue to Step 5.

`prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `round = 1`. Note: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 5.

Otherwise (valid prior checkpoint present):

**Step 4a - Auto-fetch the head branch.** Refresh the local tracking ref so a script can re-run the same command without manually fetching:

```bash
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "<head_ref>@{u}" 2>/dev/null)
```

If `upstream` resolves to `<remote>/<branch>` form, split and run `git fetch <remote> <branch>`. No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. After a successful fetch, re-resolve `current_head_sha`.

**Step 4b - Compare checkpoints.** Evaluate top to bottom and stop at the first row that matches.

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`, and the invocation adds no scope or depth beyond the prior checkpoint | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation expands scope or depth beyond it | `round = prior.round + 1`. Note: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note: `Base branch advanced since round <prior.round>.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note: `Base ref changed since round <prior.round>.`           |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

### Step 5 - Evaluate Auto-Escalation

Scan files and diff against the signal categories above. Record `signal: <category> -> <path>` per match **in the report's Summary Notes**; a whole-file signal (a new or modified migration) cites the path with no line number. Where a category fires many times on the same file, collapse those to one record for that file rather than dropping paths - the Scope line already carries the category list, so Notes exists to name the files.

Resolve scope (Core / +X / Full) and surface it in Summary:

- Signals fired and no user flag -> `auto-escalated from Core; signals: <list>`
- User flag present and signals agree or none fired -> no annotation
- User flag present and other categories fired -> `Scope user-pinned; <category> signals present: <list>`

**Round 2+:** user flag > firing signals. Signals are scored on the full range every round, so a scope that escalated in round 1 escalates again on its own - nothing is inherited from the prior checkpoint.

### Phase 0 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req` file contents when passed, and `prior_checkpoint.report_path` when round > 1.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its findings join the assembled set verified in Step 8. It emits exactly one of `### Requirement Findings` / `### No Requirement Findings`; record which in Summary Notes as `Phase 0: <marker>` so a later round can confirm the phase ran. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. Runs before Phase A - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk`.
- Use skill: `review-blast-radius`.
- Output Risk and Blast Radius before findings.
- **Resolve depth here.** Start from the invocation (`deep` if flagged, else `standard`); promote to `deep` when Blast Radius is `Wide` or `Critical`, and append `auto-promoted from standard; Blast Radius: <level>` to the Summary's Depth line.
- **Then compare the resolved scope and depth against the prior checkpoint** (round 2+ only; both values exist only now):
  - Scope gained entries -> `Scope expanded round <N>: +<list>.` Newly-added scopes have no prior findings to reconcile.
  - Scope lost entries -> `Scope narrowed round <N>: -<list> - prior findings reconciled; no new <list> pass.` Prior findings from dropped scopes are still reconciled in Step 9; they get no fresh pass.
  - Resolved depth is `standard` where the checkpoint recorded `deep` -> `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

**Low-risk short-circuit:** Risk `Low` + Blast Radius `Narrow` + no architecture-relevant files touched (security config, filters, API contracts, shared base classes, aspects, `application*.yml`, migrations) -> skip Phases C-E, deliver the Phase 0 outputs (Change Brief, traceability, requirement findings) and Phase B findings only. Phase B's conditional migration and API-contract blocks are unreachable under this short-circuit by construction, since both of their trigger surfaces are on the architecture-relevant list.

### Step 6 - Delegate Extra Scopes in Parallel

Skip if Core only. Spawn now, before Phase B, so the subagents run in parallel with Phases B-E. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `java-tech-lead` spawn:

| Scope | Skill                              | Subagent (`subagent_type`)    |
| ----- | ---------------------------------- | ----------------------------- |
| +Perf | `task-spring-review-perf`          | `java-performance-engineer`   |
| +Sec  | `task-spring-review-security`      | `java-security-engineer`      |
| +Obs  | `task-spring-review-observability` | `java-observability-engineer` |
| +Rel  | `task-spring-review-reliability`   | `java-reliability-engineer`   |

`Full` = 4 subagents.

**Subagent prompt contract:** pass the resolved `base_ref`/`head_ref`, the already-read diff and commit log, depth level, pre-confirmed stack, the `round`, and - on round 2+ - the prior report's findings for that scope, so the subagent does not re-raise a finding this round will reconcile. Subagent skips `review-precondition-check`, re-reading the diff, and its own verify pass. It returns its `## Findings` (each carrying a label, a citation, and - on a `[Must]` - the `Impact` and `System Risk` lines this report format needs), its `## Next Steps`, one trailing coverage / not-applicable line, and at `deep` its named deep-only section. It returns no Summary block, no lens-specific section such as an OWASP sweep, and no `Recommendations`.

**Failure isolation:** if a subagent fails or times out, continue. Record `Scope incomplete: <scope> review did not complete` under Summary Notes.

### Phase B - Spring Correctness and Safety

Logical correctness, error handling, backward compatibility, transaction boundary correctness. Use atomic skills `spring-transaction`, `spring-jpa-performance`, `spring-async-processing`, `spring-exception-handling`, `spring-messaging-patterns` as relevant, as diagnostic checklists.

**Spring idioms (cite the named smell in findings):**

- [ ] **Transactions** - writes at service layer; no HTTP/broker/IO inside `@Transactional`; `readOnly = true` on reads; `rollbackFor` for checked exceptions; no `this.txMethod()` self-invocation.
- [ ] **JPA in API** - controllers never expose `@Entity` types; DTO/record/projection only.
- [ ] **N+1** - `@EntityGraph`/`join fetch` wherever lazy associations are walked post-query (depth -> `task-spring-review-perf`).
- [ ] **Bean Validation** - `@Valid` on every `@RequestBody`/`@RequestParam` DTO; no manual checks duplicating annotations.
- [ ] **Authorization coverage** - every controller method covered by `SecurityFilterChain` matcher or `@PreAuthorize`; `permitAll` documented; `@PreAuthorize` present but `@EnableMethodSecurity` absent means the annotation never fires (depth -> `task-spring-review-security`).
- [ ] **Error handling** - `@RestControllerAdvice` maps validation/not-found/access-denied; no blanket `catch (Exception)`; no `printStackTrace()`.
- [ ] **Optional discipline** - `.orElseThrow`/`.map`; never `.get()` unguarded; never as a parameter.
- [ ] **Idempotency** - monetary/notification side effects accept an idempotency key, and dedup is atomic rather than check-then-insert.
- [ ] **Dual-write** - `save` + `kafkaTemplate.send` + `save` in `@Transactional` is a smell; use outbox or `AFTER_COMMIT`.
- [ ] **VT pinning** - when `spring.threads.virtual.enabled=true` **and the project targets a JDK below 24**, `synchronized` on a shared instance pins the carrier; use `ReentrantLock`/`StampedLock`. JEP 491 removed that pinning in JDK 24 - on 24+ raise it only where the monitor is contended enough to block carriers.
- [ ] **Race-prone updates** - counters/balances/state transitions use `@Lock(PESSIMISTIC_WRITE)`/`@Version`/`SELECT FOR UPDATE`.
- [ ] **Singleton state** - no mutable fields; if required, `final` immutable, `ConcurrentHashMap`, `AtomicReference`, or lock-guarded.
- [ ] **Bulk operations** - partial-failure path; `hibernate.jdbc.batch_size` set; retries idempotent.

**Test coverage as a named finding** (not buried in Takeaways): logic changes without JUnit / slice / Testcontainers -> `[Recommend]`; escalate to `[Must]` for security, money, multi-table state machines, `@Async`/`@KafkaListener` mutations, or migrations changing column semantics. Anchor the finding to the untested production `file:line` and state the case to cover.

**Test files are reviewed for coverage and honesty only.** For files that are themselves tests, the only findings to raise are a coverage gap - anchored to the untested production code, never to the test file - and a test weakened to pass (security disabled, an assertion or `@PreAuthorize` removed), which is anchored to the test. Do not review test code for style, structure, duplication, naming, or performance: a passing test with awkward setup or a duplicated stub is not a finding, and Phase D's verbosity checks do not apply to it.

**Migration PRs** (`db/migration/`, `db/changelog/`) - use skills `spring-db-migration-safety`, `ops-backward-compatibility`:

- [ ] **An already-applied migration file was edited in place** - Flyway `validate-on-migrate` fails the deploy on the checksum mismatch, and where validation is off, deployed and freshly-built schemas silently diverge. Always `[Must]`; the fix is a new forward migration.
- [ ] Column rename/drop via two-phase deploy (add -> backfill -> cut over -> remove).
- [ ] New `NOT NULL` on existing columns via two-step (add nullable -> backfill -> set NOT NULL).
- [ ] Large-table indexes use `CREATE INDEX CONCURRENTLY`, split outside a transaction.
- [ ] FKs validated separately (`NOT VALID` then `VALIDATE`).
- [ ] Long backfills isolated from DDL, not inline in Flyway/Liquibase.
- [ ] Rollback path documented.

**API contract PRs** - run when the diff carries a contract-change signal: a removed / renamed / retyped response-DTO field, a changed status code, a new **required** request field or tightened `@Valid` constraint (`@NotNull`, `@Size`), a new public route on a `/v1/`-versioned or externally consumed API, a `@RestController` returning a JPA `@Entity` directly, or an edit to a springdoc/OpenAPI spec. A Phase B check - `core-only` suppresses subagent scopes, not this block. Use skills `backend-api-guidelines`, `ops-backward-compatibility`:

- [ ] Breaking change (removed/renamed/retyped field, tightened constraint, new required request field, changed status or error shape) carries a version bump or expand-contract plan; "no external callers" backed by a search, not an assumption; when consumption is unknown, treat a `/v1/`-versioned or spec-published surface as externally consumed.
- [ ] Responses returned through DTOs/records/projections, never a raw `@Entity`; errors follow RFC 9457 via `@RestControllerAdvice`; collections paginated.
- [ ] When the project commits an OpenAPI artifact or generated client, it matches the code - changed endpoints, schemas, status codes, and error shapes present and accurate. Annotation-only springdoc with no committed artifact has nothing to drift - skip this row.
- [ ] Each finding names who breaks and how (for a leaked `@Entity`: what it exposes and who couples to it). Severity maps to labels: High -> `[Must]` = unversioned breaking change to an externally consumed contract, or an `@Entity` leaked on an externally consumed / versioned surface; Medium -> `[Recommend]` = internal breaking change with no coordinated-deploy note, inconsistent status/error envelope, unpaginated unbounded collection; Low = naming drift with no consumer impact - below the reporting bar, write nothing. An `@Entity` on an internal-only surface stays with the **JPA in API** idiom row at `[Recommend]`; one finding per `file:line` either way.

### Phase C - Spring Architecture Guardrails

Use skill: `architecture-guardrail`.

- [ ] **Layering** - `@RestController` -> `@Service` -> `@Repository`. No business logic in controllers; no HTTP clients in repos/entities; no view rendering in services. DTO mapping at service/controller boundary.
- [ ] **Service-layer discipline** - controller orchestration > 5 lines -> extract `@Service`; methods reveal intent (`fulfillOrder(orderId)`) over CRUD pass-through; cross-aggregate work lives in a service, not `@PostPersist`/`@PostUpdate`.
- [ ] **Anemic domain** - rules accumulating in services with entities as pure data -> flag for refactor/extraction.
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
- [ ] `@SpringBootTest` > 30 lines for a single assertion; mock chains better served by a slice test.
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

### Step 7 - Assemble Findings

Runs on every review, Core included.

- **Order by severity, never by scope or phase.** `[Must]` before `[Recommend]`; within a label, by blast radius.
- **Deduplicate across every source** - Phase 0 requirement findings, the Phase A-E phases, and subagent returns. Merge on the *claim*, not the citation: an unmet acceptance criterion that is also a Phase B defect is one entry, and a defect two scopes both flagged is one entry citing both. Two findings sharing a `file:line` but making different claims stay separate. **Strongest intent wins** when labels differ: `Must` > `Recommend`.
- **Preserve citations.** `file:line` where the diff carries hunk headers; `file#member` where it does not, or the file path alone for a migration or config file - say once in Summary Notes when the precision degraded. A coarser citation never merges findings: several defects in one method stay several findings, because the key is the claim.
- **Merge Next Steps**: combine, preserve `[Implement]`/`[Delegate]`, dedupe, re-sort.
- **Hold deep-only subagent sections** (e.g. perf's `Capacity and Load-Test Plan`) verbatim for the report's Depth Appendix - they are not findings and must not be dropped or merged.
- Never append a raw subagent report.

### Step 8 - Verify Findings

Use skill: `review-finding-verify` with the assembled findings, the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column and its inline provenance annotation on the finding heading. Carry its tally into Summary in its full form, including the dropped-reason split when any row was dropped.

### Step 9 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the body at `prior_checkpoint.report_path` (frontmatter excluded)
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff --name-status` from Step 3
- `head_files`: the head file list from Step 3 - without it the skill cannot distinguish a deleted path from an untouched one

Pass only the prior findings whose scope ran in the prior round; a scope this round dropped is still reconciled, one this round added has nothing to reconcile.

Insert the returned table under `## Prior Round Reconciliation`. **A `Still open` or `Needs re-check` row stays a live finding:** carry it into `## High-Impact Findings` with its original label so the next round can reconcile it again, and into `## Next Steps` with an `(open since round <N>)` suffix. If Step 7 already assembled the same `file:line` from this round's own pass, that is one entry, not two - the reconciliation table row and the finding describe the same defect. Do not emit a standalone "Carry-Over Open Items" section.

Reconciliation is location-scoped: it answers whether the cited smell is still at the cited line. When a defect moved rather than vanished (a secret relocated to another file, a method deleted and its logic re-homed), the prior row resolves on its own terms and the new location is a fresh finding this round - state the relocation in the row's Notes without asserting cause.

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review` and every field the writer requires:

- `report_body`, `branch`, `base_ref`, `head_ref`, `base_sha = current_base_sha`, `head_sha = current_head_sha`
- `mode: full`, `round` (Step 4), `prior_head_sha` (omit on round 1)
- `scope` mapped to the writer's enum: `Core` -> `core-only`, otherwise the space-joined set of `+perf` `+sec` `+obs` `+rel` that resolved, or `full` when all four - the writer rejects unmapped values, and the Summary's display form (`+Sec +Perf`) is not the enum form
- `depth` (resolved in Phase A), `stack = java-spring-boot`

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence. Omit sections marked omittable when they have no content.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss _(any `[Must]` -> Request Changes; no `[Must]` but an unresolved assumption stated in a `[Recommend]` could block merge -> Discuss; otherwise Approve)_
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical
- **Stack Detected:** Java <version> / Spring Boot <version>
- **Scope:** Core | one or more of +Sec +Perf +Obs +Rel | Full _(append the Step 5 annotation when one applies)_
- **Depth:** standard | deep _(append `auto-promoted from standard; Blast Radius: <level>` when Phase A promoted it)_
- **Round:** <N>                                _(from round 2 onward)_
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(drop the parenthetical when K is 0)_
- **Requirement Source:** <path or origin> (Specified | Self-attested) _(this line and the next are emitted together, or both omitted when Phase 0 resolved no source)_
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable
- **Notes:** _(omit when every entry below is empty; one bullet each)_
  - `signals: <list>` from Step 5
  - `Phase 0: <marker>`
  - round decision, scope, and depth notes from Step 4 and Phase A
  - `Scope incomplete: <scope> review did not complete`
  - deep-pass limitations, citation-precision caveats, and anything else the run could not establish

[full Risk and Blast Radius blocks from Phase A's atomics]

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability _(omit when Phase 0 resolved no source)_

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, or `-`> | <file:line, or `-`> |

Rows come from `review-change-intent` unchanged - it owns the Status semantics and the anchor rules. Do not re-derive them here.

## Prior Round Reconciliation _(round 2+ only)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

Every finding carries exactly one label, `[Must]` or `[Recommend]`, on its heading. No other label is written. The heading also carries the scopes that raised it when more than one did, any provenance annotation from Step 8, and the carry-over suffix on a reconciled open item.

### [Must] file:line _(scopes: Core, Perf)_
- Issue: [named Spring idiom: `@Transactional` self-invocation, fat controller, JPA entity in API, field `@Autowired`, missing `@PreAuthorize`, edited-in-place migration, dual-write, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Spring change with code]

### [Recommend] file:line _(pre-existing; newly reachable via ...)_ (open since round 1)
- Issue:
- Impact:
- Fix:

## Architecture Notes
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes
- Over-engineering detected:
- Simplification opportunities:

Write `None` in any slot with nothing to report; omit either section entirely only when every slot is `None`.

## Key Takeaways _(omit when there are no findings)_
- 2-4 bullets summarizing systemic impact and what to address before merge.

## Next Steps
Prioritized, each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] OldFile.java:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._

## Depth Appendix _(deep only; omit otherwise)_

Each deep-only section a subagent returned, its body unchanged, re-titled as an `###` heading (`### Capacity and Load-Test Plan`, `### Failure-Mode and Blast-Radius Map`). Not every lens has one - security and observability return none, and that is not a gap.

Then `### Repo History`: the recurring fix/revert/hotfix churn the deep pass found on the touched files, or `Read; nothing recurring`, or `History too shallow to signal`. A churn match that explains a finding also goes into that finding's System Risk - the appendix records the pass, it does not replace the evidence.
```

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed (or accepted from parent)
- [ ] Step 3 - `review-precondition-check` ran (or handle received); diff, name-status, head file list, and commit log read once; both SHAs captured
- [ ] Step 4 - round decided (1 / prior + 1 / no-op); auto-fetch attempted only when a prior checkpoint exists; the full `<base_ref>...<head_ref>` range analyzed regardless of round; no-op path exits without writing the report
- [ ] Step 5 - scope decision recorded with firing signals; user-pinned conflicts surfaced
- [ ] Phase 0 - `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; requirement lines in Summary, or all three requirement outputs omitted when no source resolved; its marker recorded; its findings assembled with the rest
- [ ] Phase A - Risk and Blast Radius stated before findings; depth resolved and promoted on Wide/Critical; scope and depth compared against the prior checkpoint on round 2+
- [ ] Step 6 - subagents spawned before Phase B and run in parallel, with round and prior-scope findings passed (when scope > Core); missing scopes noted
- [ ] Phase B - Spring idioms applied (transactions, JPA-in-API, authz coverage, exception advice, VT pinning under its JDK predicate, dual-write); migration safety where applicable, including edited-in-place files; API contract checks ran when a route, controller, DTO, or springdoc spec changed; missing tests raised as a named finding anchored to production code
- [ ] Phase C - layering, anemic domain, constructor injection, configuration, boundaries, multi-tenant (skipped under the Phase A low-risk short-circuit)
- [ ] Phase D - `complexity-review` + `spring-overengineering-review` invoked; remaining AI smells covered (skipped under the short-circuit)
- [ ] Phase E - maintainability applied (skipped under the short-circuit)
- [ ] Step 7 - findings deduped across Phase 0, phases, and subagents; strongest label wins; severity-ordered; deep-only sections held for the appendix; no raw subagent report appended
- [ ] Step 8 - `review-finding-verify` ran on all assembled findings; Dropped rows excluded; labels and provenance annotations applied; full tally in Summary
- [ ] Step 9 - on round 2+, `review-prior-findings-reconcile` ran with all four inputs; table inserted; `Still open` rows live in both High-Impact Findings and Next Steps, deduped against this round's own findings
- [ ] Step 10 - report written via `review-report-writer` with every required field; scope mapped to the writer's enum; confirmation printed
- [ ] Every Must cites system risk; every finding has one label, a citation, and an actionable Spring fix

## Avoid

- State-changing git (`checkout`/`merge`/`pull`/`rebase`) from this workflow. The one allowed exception is `git fetch <remote> <branch>` in Step 4a, and only when a valid prior checkpoint exists - round 1 stays strictly read-only.
- Scoping round 2+ analysis to `<prior_head_sha>...<head_sha>` - risk, scope, depth, and requirement fit score the full `<base_ref>...<head_ref>` range on every round.
- Writing the report on no-op exit - the file must stay byte-identical.
- Generic backend phrasing when a Spring idiom exists ("extract to a `@Service`", not "helper class").
- Vague feedback without a concrete Spring fix; blocking on personal preference; nitpicking absent project standard.
- Running perf/security/observability/reliability when the user passed `core-only`; sequential subagent runs when they could be parallel.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Asserting that a round-2 defect was caused by a round-1 fix - state both facts, let the reader connect them.
- Approving `WebSecurityConfigurerAdapter`, field `@Autowired`, or `@Transactional` self-invocation.
