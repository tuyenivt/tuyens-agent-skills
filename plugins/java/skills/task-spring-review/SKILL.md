---
name: task-spring-review
description: Spring Boot staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with Spring idioms (layer boundaries, fat controllers, JPA leak in API, `@Transactional` misuse, anemic domain, dependency-injection abuse, Virtual Thread pinning). Spawns Spring-specific perf/security/observability subagents for extra scopes. Stack-specific override of task-code-review for Java/Spring Boot. Runs standalone with full PR/branch resolution.
agent: java-tech-lead
metadata:
  category: backend
  tags: [java, spring-boot, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Spring Boot Code Review

## Purpose

Spring-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Spring-specific correctness, architecture, AI-quality, and maintainability checks (layer boundaries, fat `@RestController`, JPA entity leakage in API responses, `@Transactional` propagation misuse, anemic-domain pattern, `@Autowired` field injection, Virtual Thread pinning via `synchronized`). Coordinates Spring-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Java / Spring Boot. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a Spring Boot PR before merge
- Post-AI-generation quality gate on a Spring Boot change set
- Architecture drift detection in a Spring Boot codebase
- Pre-merge risk assessment on a Spring Boot branch

**Not for:**

- Pre-implementation feature design (use `task-spring-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-spring-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-spring-review-perf`, `task-spring-review-security`, or `task-spring-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Spring staff-level review                                  | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                   |
| --------------- | --------------------------------------------------------------------------- |
| Core            | Phases A-E only (Spring-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-spring-review-perf`                         |
| + Security      | Core + parallel subagent: `task-spring-review-security`                     |
| + Observability | Core + parallel subagent: `task-spring-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel Spring subagents) |

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (Spring-tuned):**

- File uploads (`MultipartFile`), Spring Security config (`SecurityFilterChain`, `@EnableMethodSecurity`), `@PreAuthorize` / `@PostAuthorize` changes, `@RequestBody` DTO changes, raw JPQL/native SQL, secrets/credentials in `application.yml`, `KafkaListener` / `RabbitListener` consuming user input → auto-add **+Security**
- New Flyway/Liquibase migration, new JPA `@Query`, new `@EntityGraph`, new `Pageable` endpoints, new endpoints with payloads, loops over collections that hit DB or HTTP, new `@Cacheable` annotations → auto-add **+Perf**
- New `@Service` / `@Component`, new external client (`RestClient`/`WebClient`/Feign), new `@Async` / `@Scheduled` method, change to logback-spring.xml / `application.yml` logging or actuator config, new Micrometer `Timer`/`Counter` registrations, new `@TransactionalEventListener` → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                     | Meaning                                                                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-spring-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-spring-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-spring-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-spring-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-spring-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-spring-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Java / Spring Boot. If invoked as a delegate of `task-code-review` (parent already detected Spring Boot), accept the pre-detected stack and skip re-detection. If the detected stack is not Spring Boot, stop and tell the user to invoke `/task-code-review` instead.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 3 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. Make this explicit because the default of "skip if user did not pass `+security` etc." silently misses the cases where the change itself signals the need.

For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals so the Summary documents why the chosen scope was correct

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`. If the user passed a scope and signals contradicted it, surface a one-line note (`Scope user-pinned to Core; +Security signals present: <list>`) so reviewers see what was deliberately deferred.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (security config, filters/interceptors, API contracts, shared base classes / aspects, `application.yml`, Flyway migrations), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Phase B - Spring Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness - through a Spring lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding JUnit / Spring slice / Testcontainers coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication (Spring Security / OAuth2 / JWT), authorization (`@PreAuthorize` / `SecurityFilterChain` matchers), money or billing flows, data-integrity writes (multi-table transactions, state machines), `@Async` / `@KafkaListener` jobs that mutate data, Flyway migrations that change column semantics. Do not bury this finding in Key Takeaways - a separate, named entry in Findings.

**Spring-specific correctness checks:**

- [ ] **`@Transactional` boundaries**: writes happen inside `@Transactional` at the service layer (not the controller, not the repository); no HTTP calls / Kafka publishes / external I/O _inside_ the transaction (use `TransactionalEventListener(phase = AFTER_COMMIT)` or transactional outbox)
- [ ] **`@Transactional` propagation**: explicit `propagation` only when needed; `REQUIRES_NEW` documented (defeats outer rollback); `readOnly = true` on read paths so Hibernate skips dirty checking
- [ ] **`@Transactional` self-invocation**: no `this.transactionalMethod()` calls within the same bean - the Spring proxy is bypassed and the transaction silently does not start. Refactor to a separate bean or use `TransactionTemplate` / `AopContext.currentProxy()`
- [ ] **Checked exceptions and rollback**: `@Transactional` rolls back on `RuntimeException` and `Error` by default; for checked exceptions, `rollbackFor` must be declared explicitly
- [ ] **Bean Validation on input**: every `@RequestBody` and `@RequestParam` DTO has `@Valid` and the DTO carries `@NotNull` / `@Size` / `@Pattern`; no manual validation duplicating constraint annotations
- [ ] **Strong typing for input**: `@RequestBody` uses DTOs / records, never JPA entities directly (mass assignment risk - see `task-spring-review-security` for depth)
- [ ] **N+1 query patterns**: any code that walks a `@OneToMany` / `@ManyToOne` after a query uses `@EntityGraph` or `join fetch`; lazy associations not touched outside the transaction (delegate to `task-spring-review-perf` for depth)
- [ ] **`Optional` use**: `Optional` returned from repository methods handled (`.orElseThrow`, `.map`); never `.get()` without a prior `isPresent()`; `Optional` not used as a method parameter
- [ ] **JPA entities exposed in API**: controllers do not return `@Entity` types directly; responses go through DTO / record / projection - entities do not leak `created_at` audit fields, password hashes, or lazy collections that trigger `LazyInitializationException` mid-serialization
- [ ] **Authorization on every endpoint**: every controller method has explicit `SecurityFilterChain` matcher coverage OR `@PreAuthorize` (defense in depth at service layer); `permitAll` documented (delegate to `task-spring-review-security` for depth)
- [ ] **Error handling**: `@RestControllerAdvice` / `@ControllerAdvice` handles common exceptions (`MethodArgumentNotValidException`, `EntityNotFoundException`, `AccessDeniedException`) with consistent error response shape; no blanket `catch (Exception e)` swallowing root causes; no `printStackTrace()` / `e.printStackTrace()` in production code paths
- [ ] **Migration PRs (any change in `db/migration/` or `db/changelog/`)**: see the Migration PRs subsection below
- [ ] **Bulk operations**: partial-failure handling defined; idempotency for retryable bulk; `JdbcTemplate.batchUpdate` or JPA batch (`spring.jpa.properties.hibernate.jdbc.batch_size`) sized appropriately

**Migration PRs (any change in `src/main/resources/db/migration/` or `db/changelog/`):**

- [ ] Two-phase deploys for column rename / drop (add new → backfill → cut over → remove old)
- [ ] `NOT NULL` on existing columns added via two-step (add nullable → backfill → set NOT NULL)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); migration split so the concurrent statement runs outside a transaction
- [ ] Foreign keys added with validation deferred (or as a separate validate step)
- [ ] Data migrations isolated from DDL migrations; long-running data backfills not in Flyway/Liquibase scripts
- [ ] Rollback path documented or verified
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `spring-db-migration-safety` for canonical safe-migration patterns

**Concurrency safety:**

- [ ] Singleton beans hold no mutable state; if state is required, it is `final` immutable, `ConcurrentHashMap`, `AtomicReference`, or guarded by a lock
- [ ] **No `synchronized` on shared instances in Virtual Thread paths** (Spring Boot 3.2+ with `spring.threads.virtual.enabled=true`) - pinning the carrier thread defeats the model. Use `ReentrantLock` or `StampedLock` instead
- [ ] No `static` mutable fields ("global state via class loader")
- [ ] Race-prone updates (counters, balance changes, state transitions) use database-level locking (`@Lock(LockModeType.PESSIMISTIC_WRITE)`, optimistic `@Version`, or `SELECT ... FOR UPDATE`)
- [ ] Cache writes thread-safe; `@Cacheable` keys deterministic; no race window between cache miss and cache fill on hot keys (use Caffeine `LoadingCache` or explicit lock-on-fill)

Use skill: `spring-jpa-performance` for canonical JPA correctness patterns.
Use skill: `spring-transaction` for `@Transactional` propagation and scope when this PR introduces or extends transactional methods.
Use skill: `spring-async-processing` for any new or modified `@Async` / Virtual Thread code.
Use skill: `spring-exception-handling` for any new `@RestControllerAdvice` / exception mapping.

### Phase C - Spring Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Spring-specific architecture checks:**

- [ ] **Layering**: `@RestController` / `@Controller` → `@Service` → `@Repository`. No business logic in controllers; no `RestClient` / `WebClient` calls in repositories or entities; no view rendering inside services. Repositories return entities or projections; mapping to DTOs happens at the service or controller boundary, not in the repository
- [ ] **Service-layer discipline**: any controller method with > 5 lines of orchestration is extracted to a `@Service`; services expose intention-revealing methods (`fulfillOrder(orderId)`) not CRUD pass-throughs (`callRepoSaveAndPublishEvent`); cross-aggregate orchestration lives in a service, not in `@PostPersist` / `@PostUpdate` JPA callbacks
- [ ] **Anemic domain antipattern**: when business rules accumulate in services and entities are pure data containers, flag for refactor (see `task-spring-refactor`); push behavior into entities or value objects where it belongs to the aggregate's invariants
- [ ] **Dependency injection style**: constructor injection only - no `@Autowired` field injection (breaks immutability and testability); `final` fields with a `@RequiredArgsConstructor` or hand-rolled constructor; no `@Autowired` setter injection; no `ApplicationContextAware` for cross-bean lookup
- [ ] **Configuration discipline**: typed `@ConfigurationProperties` records over `@Value("${...}")` field injection; `application.yml` profiles separated (`application-prod.yml`, `application-dev.yml`); no hardcoded values that should be config
- [ ] **Module / package boundaries**: feature-package layout (`com.acme.order.*` contains controller/service/repo for orders) preferred over layer-package layout (`com.acme.controller`, `com.acme.service`, `com.acme.repository`); cross-feature imports go through public service interfaces, not direct `OtherFeatureRepository` calls
- [ ] **Multi-tenant isolation**: tenant scoping enforced at the repository / `@Filter` layer (Hibernate `@TenantId` in 6.x or `@Filter`), not at the controller layer alone
- [ ] **Multi-database / read replica**: when the app uses `AbstractRoutingDataSource` or read replicas, queries declare their target via `@Transactional(readOnly = true)` or explicit annotation; no surprise cross-database joins
- [ ] **Aspect / interceptor discipline**: AOP aspects (`@Aspect`) used for genuinely cross-cutting concerns (audit, retries, metrics) - not as a hidden control-flow mechanism that swallows exceptions or rewrites return values

**Multi-service PRs (when change spans 2+ services or this Spring app + a separate service):**

- API contract compatibility checked (Spring Cloud Contract or Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**Spring-specific AI smells:**

- [ ] **Pattern inflation**: a `@Service` interface + single `@Service` implementation pair where the interface adds no value (no second implementation, no test double); a custom `Result<T>` wrapper where `Optional` or a checked domain exception would suffice; a class created where a `static` method would do
- [ ] **Over-abstraction**: `BaseService<T>` / `BaseController<T>` parent classes for two services; premature `Strategy` pattern with one strategy; `Factory` classes for objects that have one constructor path
- [ ] **Speculative configurability**: `@ConfigurationProperties` with documented but unused keys; profile-conditional beans for environments that do not exist; `@ConditionalOnProperty` flags with no off path
- [ ] **Redundant mapping layers**: `Entity → DomainObject → ServiceDTO → ResponseDTO` when one mapping would suffice; MapStruct mappers chained 3+ deep
- [ ] **Test verbosity**: `@SpringBootTest` setup blocks > 30 lines for a single assertion; `@MockBean` chains that could be a slice test; AssertJ assertion builders reimplemented when standard matchers exist
- [ ] **Reactive misapplication**: `Mono` / `Flux` used in a non-reactive servlet stack ("just in case we go reactive") - the runtime cost without the runtime benefit
- [ ] **Comment cruft**: comments restating method names; `// end of method foo` markers; Javadoc on private helpers that just repeats the method signature; auto-generated TODOs left in

### Phase E - Spring Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Spring-specific maintainability checks:**

- [ ] **Naming conventions**: services describe their operation (`OrderFulfillmentService` over `OrderHelper`); records named after their role (`OrderUpdateRequest`, `OrderResponse`); no `Util` / `Manager` / `Helper` classes accumulating unrelated methods; package-private over `public` when the symbol does not cross the feature boundary
- [ ] **Magic numbers / strings**: extracted to `static final` constants or `@ConfigurationProperties`; date/time constants use `Duration.ofMinutes(...)` not `60_000L`
- [ ] **Hardcoded URLs / credentials**: in `application.yml` profiles, env vars, or Vault - never inline in code
- [ ] **Method length**: methods > 20 lines reviewed for extraction; methods > 50 lines flagged unless they are a clearly orchestrating service method calling intention-revealing private methods
- [ ] **Duplicated query logic**: same JPQL or `Specification` predicate in 3+ places extracted to a `Specification` factory or repository method
- [ ] **Logging hygiene**: SLF4J parameterized logging (`log.info("processing order={}", orderId)`) not string concatenation; log levels used correctly (`error` for actionable failures, `warn` for recoverable anomalies, `info` for state transitions, `debug` for verbose); structured fields via Logback MDC when configured (delegate to `task-spring-review-observability` for depth)

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-spring-review-observability` subagent owns the depth review).

### Step 4 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-spring-review-perf`                                                                                 |
| Core + Security      | 1 subagent running `task-spring-review-security`                                                                             |
| Core + Observability | 1 subagent running `task-spring-review-observability`                                                                        |
| Full                 | 3 subagents running `task-spring-review-perf`, `task-spring-review-security`, `task-spring-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Java / Spring Boot) so the subagent skips its own `stack-detect`
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 5 - Synthesize (only if Step 4 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a synchronous external call inside `@Transactional` can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

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
**Stack Detected:** Java <version> / Spring Boot <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Spring idiom: `@Transactional` self-invocation, fat controller, JPA entity in API, `@Autowired` field injection, missing `@PreAuthorize`, `synchronized` on Virtual Thread, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Spring change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

## Architecture Notes

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Move `kafkaTemplate.send(...)` to a `@TransactionalEventListener(phase = AFTER_COMMIT)` outside the transaction in OrderService#place"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Spring conventions, not generic backend conventions
- Provide actionable feedback with Spring code examples
- Never comment on trivial formatting or style where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Spring subagent rather than duplicating the check here


### Step 6 - Write Report

Use skill: `review-report-writer` with `report_type: review`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Java / Spring Boot (or accepted from parent dispatcher)
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If user passed `--base`, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated in Step 3; promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; promotion recorded in Summary
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B Spring correctness checks applied: `@Transactional` boundaries, propagation, self-invocation, Bean Validation, JPA-in-API, `@PreAuthorize` coverage, exception advice, Virtual Thread pinning
- [ ] Phase C Spring architecture checks applied: layering, anemic domain, constructor injection only, configuration discipline, package boundaries, multi-tenant
- [ ] Phase D AI-quality checks applied: pattern inflation, single-impl interfaces, over-abstraction, speculative configurability, reactive misapplication
- [ ] Phase E Spring maintainability checks applied: naming, magic numbers, method length, parameterized SLF4J logging
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Spring fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Spring-specific subagents (`task-spring-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Spring idiom exists (say "extract to a `@Service`", not "extract to a helper class")
- Nitpicking style where no project standard exists; no `[Nitpick]` or `[Praise]` labels
- Providing vague feedback without a concrete Spring fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Spring subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `WebSecurityConfigurerAdapter`, `@Autowired` field injection, or `@Transactional` self-invocation as acceptable patterns - all three are anti-patterns in modern Spring Boot
