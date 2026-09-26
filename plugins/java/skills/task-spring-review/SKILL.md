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
- **Not for:** design (`task-spring-implement`), debugging, new-system architecture, single-scope reviews (delegate to `task-spring-review-{perf,security,observability,reliability}`).

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

Use skill: `stack-detect`. Accept pre-detected stack from a parent. If not Spring Boot, stop and tell the user to invoke `/task-code-review`. Its `Database` value is the engine the Phase B migration rows read.

Once Step 4 has not stopped the run, read the Spring Boot version from the build file at `git show <head_ref>:<path>`, never from the working tree (Gradle `org.springframework.boot` plugin or version catalog; Maven `spring-boot-starter-parent` or the imported `spring-boot-dependencies` BOM) and the Java version from `java.toolchain` / `<java.version>` / `maven.compiler.release`; `stack-detect` does not report either. Every construct a finding cites as present and every fix recommends must exist and bind on that version, composed-atomic fixes included. Below Boot 4.0, write the row's or the atomic's Boot 3 form; when neither has one, say `Boot 3 form not given` rather than emitting the Boot 4 one.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the target argument, any `--base`, and `report_type: review`. Surface fail-fast messages verbatim and stop. From the handle keep `branch` = its `head_short_name` (never `HEAD`, never remote-prefixed), its `report_path` (the checkpoint file Phase 0 and Step 9 read), and any `prior_checkpoint` block or `legacy` scalar for Step 4.

Capture `current_head_sha = git rev-parse <head_ref>` and `current_base_sha = git rev-parse <base_ref>` first - the Step 4 no-op gate needs only these. Once Step 4 has not stopped the run, read once and reuse (skip when a parent passed the handle plus artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

### Step 4 - Decide Round (re-review auto-detect)

**Every round analyzes the full `<base_ref>...<head_ref>` range read in Step 3.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change on every round, so a small follow-up commit cannot under-score a large PR and a defect missed in round 1 stays reachable in round 2. Rounds differ only in that round 2+ reconciles against the prior report.

No `prior_checkpoint` -> `round = 1`. `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `round = 1`, noted `Prior report lacks checkpoint metadata - treated as round 1.` Otherwise evaluate top to bottom and stop at the first matching row. The SHAs come from local refs as they stand; nothing is fetched.

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `current_head_sha` equals the valid prior checkpoint's `head_sha` (head only; matches the lenses), and the invocation adds no scope or depth beyond the checkpoint | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` (`<sha_short>` = the first 7 chars of `current_head_sha`) and stop before reading any surface. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation expands scope or depth beyond it | `round = prior.round + 1`. Note: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_checkpoint.head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note: `Base branch advanced since round <prior.round>.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note: `Base ref changed since round <prior.round>.`           |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

### Step 5 - Evaluate Auto-Escalation

Scan files and diff against the signal categories above. Record `signal: <category> -> <path>` per match **in the report's Summary Notes**; a whole-file signal (a new or modified migration) cites the path with no line number. Many matches on one file collapse to one record for that file.

Resolve scope (Core / +X / Full) and surface it in Summary:

- Signals fired and no user flag -> `auto-escalated from Core; signals: <list>`
- User flag present and signals agree or none fired -> no annotation
- User flag present and other categories fired -> `Scope user-pinned; <category> signals present: <list>`

**Round 2+:** user flag > firing signals. Signals are scored on the full range every round, so a scope that escalated in round 1 escalates again on its own - nothing is inherited from the prior checkpoint.

### Phase 0 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req` file contents when passed, and the handle's `report_path` (as `prior_report_path`) when round > 1.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its findings join the assembled set verified in Step 8. It emits exactly one of `### Requirement Findings` / `### No Requirement Findings`; record which in Summary Notes as `Phase 0: <marker>` so a later round can confirm the phase ran. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. Runs before Phase A - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk`.
- Use skill: `review-blast-radius`.
- Output Risk and Blast Radius before findings.
- **Resolve depth here.** Start from the invocation (`deep` if flagged, else `standard`); promote to `deep` when Blast Radius is `Wide` or `Critical`, and append `auto-promoted from standard; Blast Radius: <level>` to the Summary's Depth line. A two-state Blast Radius gates this and the short-circuit on its mitigated value only when the leading `Mitigation:` tag is `in-place:`, else on the unmitigated one.
- **Then compare the resolved scope and depth against the prior checkpoint** (round 2+ only; both values exist only now):
  - Scope gained entries -> `Scope expanded round <N>: +<list>.` Newly-added scopes have no prior findings to reconcile.
  - Scope lost entries -> `Scope narrowed round <N>: -<list> - prior findings reconciled; no new <list> pass.` Prior findings from dropped scopes are still reconciled in Step 9; they get no fresh pass.
  - Resolved depth is `standard` where the checkpoint recorded `deep` -> `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

**Low-risk short-circuit:** Risk `Low` + Blast Radius `Narrow` + no architecture-relevant files touched (security config, filters, API contracts, shared base classes, aspects, `application*.yml`, migrations) -> skip Phases C-E, deliver the Phase 0 outputs (Change Brief, traceability, requirement findings) and Phase B findings only. Phase B's conditional migration and API-contract blocks are unreachable under this short-circuit by construction, since both of their trigger surfaces are on the architecture-relevant list. Record `Low-risk short-circuit: Phases C-E skipped` in Summary Notes.

### Step 6 - Delegate Extra Scopes in Parallel

Skip if Core only. Spawn now, before Phase B, so the subagents run in parallel with Phases B-E. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `java-tech-lead` spawn:

| Scope | Skill                              | Subagent (`subagent_type`)    |
| ----- | ---------------------------------- | ----------------------------- |
| +Perf | `task-spring-review-perf`          | `java-performance-engineer`   |
| +Sec  | `task-spring-review-security`      | `java-security-engineer`      |
| +Obs  | `task-spring-review-observability` | `java-observability-engineer` |
| +Rel  | `task-spring-review-reliability`   | `java-reliability-engineer`   |

`Full` = 4 subagents.

**Subagent inputs** stand in for the precondition handle, so the lens runs no precondition check, round gate, diff read, verify, reconcile, or report write: `base_ref`, `head_ref`, `base_sha`, `head_sha`, the diff, the commit log, `depth`, the stack (Boot and Java versions, database engine), `round`, and on round 2+ `prior_head_sha` plus the prior findings for that scope - prior `## High-Impact Findings` entries whose `raised by` names it (an entry with no `raised by` goes to every lens). The lens applies `never re-raise a prior finding the parent passed unless its cited site changed since prior_head_sha`.

**Subagent returns** its `## Findings` (severity-tier sections of numbered finding blocks), its `## Next Steps`, its one trailing `Coverage:` or `Not applicable:` line, and at `deep` its named deep-only section - no Summary, sweep section, or `Recommendations`. Step 7 projects the return.

**No-spawn fallback:** When subagents cannot be spawned, run each resolved scope inline: read that lens's SKILL.md and run it in subagent mode (its trigger: spawned by `task-spring-review`, or run inline by it when it cannot spawn) against the artifacts already read, then merge its return as if spawned; record Scopes run inline: <list> in Notes. A scope is Scope incomplete only when it failed.

**Failure isolation:** if a subagent fails or times out, continue. Record `Scope incomplete: <scope> review did not complete` under Summary Notes.

### Phase B - Spring Correctness and Safety

Logical correctness, error handling, backward compatibility, transaction boundary correctness. Load each atomic as a diagnostic checklist when the diff touches its surface: Use skill: `spring-transaction` (transactions, repositories), Use skill: `spring-jpa-performance` (entities, queries), Use skill: `spring-async-processing` (`@Async`, `@Scheduled`, executors, events), Use skill: `spring-exception-handling` (advice, error responses), Use skill: `spring-messaging-patterns` (Kafka, Rabbit), Use skill: `spring-security-patterns` (filter chain, method security, JWT).

**Spring idioms (cite the named smell in findings):**

- [ ] **Transactions** - writes at service layer; no HTTP/broker/IO inside `@Transactional`; `readOnly = true` on reads; `rollbackFor` for checked exceptions unless `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)` (Framework 6.2 / Boot 3.4+) is set; no `this.txMethod()` self-invocation.
- [ ] **JPA in API** - controllers never expose `@Entity` types; DTO/record/projection only.
- [ ] **N+1** - `@EntityGraph`/`join fetch` wherever lazy associations are walked post-query (depth -> `task-spring-review-perf`).
- [ ] **Bean Validation** - `@Valid` on every `@RequestBody`/`@RequestParam` DTO; no manual checks duplicating annotations.
- [ ] **Authorization coverage** - every controller method covered by `SecurityFilterChain` matcher or `@PreAuthorize`; `permitAll` documented; `@PreAuthorize` present but `@EnableMethodSecurity` absent means the annotation never fires (depth -> `task-spring-review-security`).
- [ ] **Authority mapping** - Every hasRole / hasAuthority check is only as real as the JWT converter feeding it: a top-level claim needs authorities-claim-name; a nested claim (Keycloak realm_access.roles) yields no authorities through setAuthoritiesClaimName - Boot 4.1 `authorities-claim-expressions`, else a custom converter; either property needs `authority-prefix: ROLE_` when the claim values are bare role names, or an empty prefix when they already carry `ROLE_` (the default prefix is `SCOPE_`). When the mapping yields nothing, every role gate denies everyone: say so, and never propose a role-based bypass.
- [ ] **Error handling** - `@RestControllerAdvice` maps validation/not-found/access-denied; no blanket `catch (Exception)`; no `printStackTrace()`.
- [ ] **Optional discipline** - `.orElseThrow`/`.map`; never `.get()` unguarded; never as a parameter.
- [ ] **Idempotency** - monetary/notification side effects accept an idempotency key, and dedup is atomic rather than check-then-insert.
- [ ] **Race-prone updates** - a check-then-act on a status, counter, or balance needs `@Version`, `@Lock(PESSIMISTIC_WRITE)`, or a conditional `UPDATE ... WHERE status = ?`. A key does not serialize two concurrent requests, so the race is its own finding, never folded into Idempotency.
- [ ] **Dual-write** - A publish or remote call that must happen when the row commits needs the transactional outbox. AFTER_COMMIT fits only best-effort side effects (a publish an acceptance criterion requires is not): it loses the send on a crash or a listener exception (swallowed in afterCompletion). A money call whose result must be saved is neither: PENDING row, the call outside any transaction, a completion transaction, and a reconciler.
- [ ] **Executors** - Any user Executor bean - a ThreadPoolTaskScheduler included - backs off Boot's applicationTaskExecutor unless it is `@Bean(defaultCandidate = false)` (needs Boot 3.4+) or spring.task.execution.mode=force (needs Boot 3.5+). Once it is backed off, with two or more TaskExecutor beans (Boot's @EnableScheduling taskScheduler counts, so one user executor already makes two - check the base before attributing) and none named taskExecutor, unnamed @Async runs on a new SimpleAsyncTaskExecutor - unbounded, one thread per task. spring.task.execution.propagate-context (Boot 4.1) and TaskDecorator beans reach only Boot-built executors.
- [ ] **VT pinning** - only when `spring.threads.virtual.enabled=true` and the JDK is 21-23 (an unknown JDK counts as below 24): `synchronized` held across blocking IO pins the carrier; use `ReentrantLock`/`StampedLock`. JEP 491 removed the pinning in JDK 24 - on 24+ never raise it.
- [ ] **Inert on the declared version** - a `@Retryable` / `@ConcurrencyLimit` / Resilience4j annotation with none of its enablers; Boot 3 `spring.http.client.*` keys on Boot 4 (binds nothing - `spring.http.clients.*`); a Jackson 2 `ObjectMapper` on Boot 4 (Boot auto-configures the `tools.jackson` `JsonMapper`: a defined one configures nothing, and an injected `com.fasterxml.jackson.databind.ObjectMapper` has no bean without the deprecated `spring-boot-jackson2` module, so the context fails to start - `[Must]`); bare `flyway-core` / `liquibase-core` / `spring-kafka` on Boot 4 (no auto-configuration without the starter or module). The inert check searches for every enabler, not only the annotation: Framework 7 `@Retryable` / `@ConcurrencyLimit` are live with `@EnableResilientMethods` or a declared `RetryAnnotationBeanPostProcessor` / `ConcurrencyLimitBeanPostProcessor` bean; Spring Retry's `@Retryable` needs `@EnableRetry` plus the AOP starter (`spring-boot-starter-aop` on Boot 3, `spring-boot-starter-aspectj` on Boot 4); Resilience4j annotations need that same starter. A search that finds none of a construct's enablers settles it as inert. A finding whose impact or fix assumes the inert construct works is wrong. A fix that enables `@EnableResilientMethods` (or `@EnableRetry`) names every `@Retryable` it activates and is recommended only when each retried call is idempotent, excludes 4xx, and runs outside a transaction; otherwise the fix is to remove the annotation or make the call idempotent first.
- [ ] **Singleton state** - no mutable fields; if required, `final` immutable, `ConcurrentHashMap`, `AtomicReference`, or lock-guarded.
- [ ] **Bulk operations** - partial-failure path; `hibernate.jdbc.batch_size` set; retries idempotent.

**Test coverage as a named finding** (not buried in Takeaways): logic changes without JUnit / slice / Testcontainers -> `[Recommend]`; escalate to `[Must]` for security, money, multi-table state machines, `@Async`/`@KafkaListener` mutations, or migrations changing column semantics. Anchor the finding to the untested production `file:line` and state the case to cover. Use skill: `spring-test-integration` for the test a finding asks for and for test-dependency edits in the diff (Boot 4 manages Testcontainers 2: `org.testcontainers:testcontainers-postgresql` and `testcontainers-junit-jupiter`, class `org.testcontainers.postgresql.PostgreSQLContainer`; the 1.x `postgresql` / `junit-jupiter` artifacts are not published at 2.x, so a test dependency that cannot resolve is `[Must]`).

**Test files are reviewed for coverage and honesty only.** For files that are themselves tests, the only findings to raise are a coverage gap - anchored to the untested production code, never to the test file - and a test weakened to pass (security disabled, an assertion or `@PreAuthorize` removed), which is anchored to the test. Do not review test code for style, structure, duplication, naming, or performance: a passing test with awkward setup or a duplicated stub is not a finding, and Phase D's verbosity checks do not apply to it.

**Migration PRs** (`db/migration/`, `db/changelog/`) - use skills `spring-db-migration-safety`, `ops-backward-compatibility`:

- [ ] **An already-applied migration file was edited in place** - Flyway `validate-on-migrate` fails the deploy on the checksum mismatch, and where validation is off, deployed and freshly-built schemas silently diverge. Always `[Must]`; the fix is a new forward migration.
- [ ] Column rename/drop via two-phase deploy (add -> backfill -> cut over -> remove).
- [ ] New `NOT NULL` on existing columns via two-step (add nullable -> backfill -> set NOT NULL).
- [ ] Large-table DDL in the engine's online form (Step 2's `Database`): PostgreSQL `CREATE INDEX CONCURRENTLY` outside a transaction and FKs `NOT VALID` then `VALIDATE`; MySQL `ALGORITHM=INSTANT` or `INPLACE, LOCK=NONE` per `spring-db-migration-safety`.
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
- [ ] **Read replica / routing** - `AbstractRoutingDataSource` reads declare target via `@Transactional(readOnly = true)` or explicit annotation, and `readOnly` reaches the router only behind a `LazyConnectionDataSourceProxy`; no surprise cross-DB joins.
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

Runs on every review, Core included. Verify, reconcile, and the report all read this set.

- **Project each lens return.** Each numbered block becomes `### [Label] <file:line>`: the label from the block's own label line (`**[Must]**` in perf and obs, `**Label:** [Must]` in security and reliability) and the `file:line` prefix of its Location line; in subagent mode a lens returns no Location annotation of its own, so verify's Annotation is the only provenance. `Issue`, `Impact`, `System Risk`, and `Fix` carry over; security's `Attack scenario` and reliability's Location suffix `verify: <assumption>` fold into `Issue`, perf's `_(quick win)_` / `_(structural)_` tag into `Fix`; reliability's `Failure Mode` -> `Impact` and `Blast Radius` -> `System Risk`. The lens's trailing `Coverage:` / `Not applicable:` line becomes a Notes bullet; its Next Steps, `[Delegate]` items included, join the merge below.
- **Tag the source.** Every finding's Issue line ends `raised by: <sources>` with tokens `core`, `+perf`, `+sec`, `+obs`, `+rel` (Phase 0 counts as `core`) - Step 6 routes round 2's prior findings by it.
- **Order by severity, never by scope or phase.** `[Must]` before `[Recommend]`; within a label, by blast radius.
- **Deduplicate across every source** - Phase 0 requirement findings, the Phase A-E phases, and subagent returns. Merge on the *claim*, not the citation: an unmet acceptance criterion that is also a Phase B defect is one entry, and a defect two scopes both flagged is one entry citing both. Two findings sharing a `file:line` but making different claims stay separate; requirement findings on different criteria stay separate unless one defect causes them all, then one entry whose Issue names each criterion. **Strongest intent wins** when labels differ: `Must` > `Recommend`.
- **Preserve citations.** The heading is exactly `### [Label] <path>:<line>` followed only by `_(...)_` groups: one repo-relative `file:line` where the diff carries hunk headers; `file#member` where it does not, or the file path alone for a migration or config file - say once in Summary Notes when the precision degraded. A merged or multi-site claim cites its primary site and names the others in its Issue. A coarser citation never merges findings: several defects in one method stay several findings, because the key is the claim.
- **Merge Next Steps**: combine, preserve `[Implement]`/`[Delegate]`, dedupe, re-sort.
- **Hold deep-only subagent sections** (e.g. perf's `Capacity and Load-Test Plan`) verbatim for the report's Depth Appendix - they are not findings and must not be dropped or merged.
- Never append a raw subagent report.

### Step 8 - Verify Findings

Use skill: `review-finding-verify` with the assembled findings, the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` and `Annotation` columns. Each annotation is its own `_(...)_` group after the heading's `file:line`: the combined `_(pre-existing; newly reachable via ...)_` is written `_(pre-existing)_ _(newly reachable via ...)_`, because `review-prior-findings-reconcile` matches `_(pre-existing)_` exactly and a merged group marks an untouched prior finding `Addressed`. The obs carve-out keys on verify's `Pre-existing` verdict plus `raised by: +obs` (missing-wire kinds only: an absent observation flag, probe property, or health indicator); such a finding keeps its drafted label. The tally fills the Summary's `Findings verified:` slot.

### Step 9 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the body of the file at the handle's `report_path` (frontmatter excluded), any combined `_(pre-existing; newly reachable via ...)_` group split into `_(pre-existing)_ _(newly reachable via ...)_`; a prior finding whose path is absent from the name-status is projected with `_(pre-existing)_`, so an `Unverified` or one-hop finding in an untouched file is never closed as `Addressed` without being read
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff --name-status` from Step 3
- `head_sha`: `current_head_sha`
- `head_files`: `git ls-tree -r --name-only <current_head_sha>`, when `name_status` has a `D` entry; otherwise omit

Insert the returned table, note line, and tally under `## Prior Round Reconciliation`. **A `Still open` or `Needs re-check` row stays a live finding.** When this round re-derived the same defect it is one entry, at this round's label and current `file:line`, with no carried group. Otherwise a carried finding republishes its prior block with the prior Location annotation kept (it skips verify, so the annotation is not re-derived), `raised by` included, at its prior label and `file:line` in `## High-Impact Findings`, plus `_(carried from round <N>)_` as its own group; `<N>` is the round the finding was first raised, and a finding that already carries `_(carried from round <N>)_` keeps it (never a second group). A legacy prior label maps `[Blocker]` / `[High]` -> `[Must]`, anything else -> `[Recommend]`, and `[Praise]` is never carried. Either way it goes into `## Next Steps` with an `(open since round <N>)` suffix. Do not emit a standalone "Carry-Over Open Items" section.

Reconciliation is location-scoped: it answers whether the cited smell is still at the cited line. When a defect moved rather than vanished (a secret relocated to another file, a method deleted and its logic re-homed), the prior row resolves on its own terms and the new location is a fresh finding this round - state the relocation in the row's Notes without asserting cause.

### Step 10 - Write Report

Use skill: `review-report-writer` with `report_type: review` and every field the writer requires:

- `report_body`, `branch` (Step 3's `head_short_name`), `base_ref`, `head_ref`, `base_sha = current_base_sha`, `head_sha = current_head_sha`
- `mode: full`, `round` (Step 4), `prior_head_sha = prior_checkpoint.head_sha` (omit on round 1), `pr_url` when the request or the checkpoint carries one
- `scope` mapped to the writer's enum: `Core` -> `core-only`, all four -> `full`, otherwise the resolved scopes space-joined in the order `+perf +sec +obs +rel` - the Summary's display form (`+Sec +Perf`) is not the enum form
- `depth` (resolved in Phase A), `stack = java-spring-boot`

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence. `{...}` annotations are authoring notes: act on them, never emit them.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss   {any `[Must]` -> Request Changes; no `[Must]` but an unresolved assumption stated in a `[Recommend]` could block merge -> Discuss; otherwise Approve}
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical   {the atomic's overall line as emitted, two-state form included}
- **Stack Detected:** Java <version> / Spring Boot <version>   {append `- below the floor (<Boot 3.x | Java < 21>)` when either is, and `- past OSS end` when the spring.io support table says so}
- **Scope:** Core | one or more of +Sec +Perf +Obs +Rel | Full   {append the Step 5 annotation when one applies}
- **Depth:** standard | deep   {append `auto-promoted from standard; Blast Radius: <level>` when Phase A promoted it}
- **Round:** <N>   {round 2+ only}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}
- **Requirement Source:** <path or origin> (Specified | Self-attested)   {this line and the next together, or both omitted when Phase 0 resolved no source}
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable
- **Notes:**   {omit when every entry below is empty; one bullet each}
  - `signal: <category> -> <path>`, one bullet per Step 5 record
  - `Phase 0: <marker>`
  - round, scope, and depth notes from Step 4 and Phase A, and the handle's `notes`
  - `Low-risk short-circuit: Phases C-E skipped`
  - `Scopes run inline: <list>`
  - `Scope incomplete: <scope> review did not complete`
  - `<scope>: <the lens's trailing Coverage: or Not applicable: line>`
  - deep-pass limitations, citation-precision caveats, and anything else the run could not establish

[full Risk and Blast Radius blocks from Phase A's atomics]

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability   {omit when Phase 0 resolved no source; rows come from `review-change-intent` unchanged}

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, or `-`> | <file:line, or `-`> |

## Prior Round Reconciliation   {round 2+ only}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

<reconcile's note line>   {only when it emitted one}

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line   {exactly one label, `[Must]` or `[Recommend]`; one citation per Step 7; then each Step 8 / Step 9 annotation as its own `_(...)_` group}
- Issue: [named Spring idiom: `@Transactional` self-invocation, fat controller, JPA entity in API, field `@Autowired`, missing `@PreAuthorize`, edited-in-place migration, dual-write, etc.] raised by: <sources>
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Spring change with code]

### [Recommend] file:line _(pre-existing)_ _(carried from round 1)_
- Issue: [...] raised by: <sources>
- Impact:
- Fix:

No findings survived verification.   {instead of the finding blocks, only when none is published}

## Architecture Notes   {`None` in an empty slot; omit this section, and likewise Maintainability Notes, when every slot is `None`}
- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes
- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways   {omit when there are no findings}
- 2-4 bullets summarizing systemic impact and what to address before merge.

## Next Steps   {omit when no actionable findings; each tagged `[Implement]` or `[Delegate]`; Must before Recommend}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] OldFile.java:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]

## Depth Appendix   {deep only}

### <deep-only section title>   {each section a subagent returned, body unchanged: `Capacity and Load-Test Plan`, `Failure-Mode and Blast-Radius Map`; security and observability return none}

### Repo History   {a churn match that explains a finding also goes into that finding's System Risk}

<recurring fix/revert/hotfix churn on the touched files, or `Read; nothing recurring`, or `History too shallow to signal`>
```

## Self-Check

- [ ] Step 1 - behavioral principles loaded
- [ ] Step 2 - stack confirmed (or accepted from parent); Boot and Java versions read at `git show <head_ref>:<path>` after Step 4; every cited construct and fix binds on them
- [ ] Step 3 - `review-precondition-check` ran with `report_type: review` (or handle received); `branch`, `report_path`, and both SHAs taken before any read; diff, name-status, and commit log read once after Step 4
- [ ] Step 4 - round decided (1 / prior + 1 / no-op) with no fetch; no-op exits before any surface read and without writing the report; the full `<base_ref>...<head_ref>` range analyzed regardless of round
- [ ] Step 5 - scope decision recorded with firing signals; user-pinned conflicts surfaced
- [ ] Phase 0 - `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; requirement lines in Summary, or all three requirement outputs omitted when no source resolved; its marker recorded; its findings assembled with the rest
- [ ] Phase A - Risk and Blast Radius stated before findings; depth resolved and promoted on Wide/Critical (two-state read per its Mitigation tag); scope and depth compared against the prior checkpoint on round 2+
- [ ] Step 6 - subagents spawned before Phase B, in parallel, with the listed inputs (when scope > Core); inline runs noted as `Scopes run inline`; failed scopes noted
- [ ] Phase B - Spring idioms applied (transactions, JPA-in-API, authz coverage and authority mapping, race as its own finding, dual-write to the outbox, executors, VT pinning on JDK 21-23 only, inert-on-version constructs); migration safety in the engine's form, including edited-in-place files; API contract checks ran when a route, controller, DTO, or springdoc spec changed; missing tests raised as a named finding anchored to production code
- [ ] Phase C - layering, anemic domain, constructor injection, configuration, boundaries, multi-tenant (skipped under the Phase A low-risk short-circuit)
- [ ] Phase D - `complexity-review` + `spring-overengineering-review` invoked; remaining AI smells covered (skipped under the short-circuit)
- [ ] Phase E - maintainability applied (skipped under the short-circuit)
- [ ] Step 7 - lens returns projected (Attack scenario, Failure Mode, Blast Radius mapped; trailing lines to Notes); every finding tagged `raised by`; deduped across Phase 0, phases, and subagents; strongest label wins; severity-ordered; deep-only sections held for the appendix; no raw subagent report appended
- [ ] Step 8 - `review-finding-verify` ran on all assembled findings; Dropped rows excluded; labels applied and annotations split into separate groups; obs missing-wire labels kept; four-count tally in Summary
- [ ] Step 9 - on round 2+, `review-prior-findings-reconcile` ran with `prior_report`, `diff`, `name_status`, `head_sha` (and `head_files` on a `D`); table inserted; unresolved rows live in High-Impact Findings (carried with `_(carried from round <N>)_` unless re-derived) and in Next Steps
- [ ] Step 10 - report written via `review-report-writer` with every required field; `branch` is `head_short_name`; scope mapped to the writer's enum in writer order; confirmation printed
- [ ] Every Must cites system risk; every finding has one label, one citation, a `raised by` tag, and an actionable Spring fix

## Avoid

- State-changing git (`fetch`/`checkout`/`merge`/`pull`/`rebase`) from this workflow - every round is read-only.
- Scoping round 2+ analysis to `<prior_head_sha>...<head_sha>` - risk, scope, depth, and requirement fit score the full `<base_ref>...<head_ref>` range on every round.
- Writing the report on no-op exit - the file must stay byte-identical.
- Generic backend phrasing when a Spring idiom exists ("extract to a `@Service`", not "helper class").
- Vague feedback without a concrete Spring fix; blocking on personal preference; nitpicking absent project standard.
- Running perf/security/observability/reliability when the user passed `core-only`; sequential subagent runs when they could be parallel.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Asserting that a round-2 defect was caused by a round-1 fix - state both facts, let the reader connect them.
- Approving field `@Autowired`, `@Transactional` self-invocation, or on Boot 4 the DSL Security 7 removed (`and()`, `authorizeRequests`, `AntPathRequestMatcher`).
