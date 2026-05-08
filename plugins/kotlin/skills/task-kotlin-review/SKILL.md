---
name: task-kotlin-review
description: Kotlin/Spring Boot staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with Kotlin idioms (null safety, coroutines, data class JPA, !! abuse, GlobalScope, @Transactional self-invocation, Virtual Thread pinning via synchronized) and Spring idioms. Spawns Kotlin-specific perf/security/observability subagents for extra scopes. Stack-specific override of task-code-review for Kotlin/Spring Boot. Runs standalone with full PR/branch resolution.
agent: kotlin-tech-lead
metadata:
  category: backend
  tags: [kotlin, spring-boot, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after Step 1 (behavioral-principles) and Step 2 (stack-detect). When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Kotlin / Spring Boot Code Review

## Purpose

Kotlin-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Kotlin- and Spring-specific correctness, architecture, AI-quality, and maintainability checks (null safety / `!!` discipline, `data class` for JPA entities, `kotlin-jpa` / `kotlin-spring` plugin presence, coroutine structured concurrency, `GlobalScope` leakage, `@Transactional` propagation misuse, Virtual Thread pinning via `synchronized`, `@MockBean` vs `@MockkBean`, `every` vs `coEvery` for `suspend`). Coordinates Kotlin-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Kotlin / Spring Boot. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved. **Runs standalone** with full PR/branch resolution.

## When to Use

- Reviewing a Kotlin + Spring Boot PR before merge
- Post-AI-generation quality gate on a Kotlin change set
- Architecture drift detection in a Kotlin codebase
- Pre-merge risk assessment on a Kotlin branch

**Not for:**

- Pre-implementation feature design (use `task-kotlin-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-kotlin-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-kotlin-review-perf`, `task-kotlin-review-security`, or `task-kotlin-review-observability`

## Depth Levels

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Kotlin staff-level review                                  | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                   |
| --------------- | --------------------------------------------------------------------------- |
| Core            | Phases A-E only (Kotlin-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-kotlin-review-perf`                         |
| + Security      | Core + parallel subagent: `task-kotlin-review-security`                     |
| + Observability | Core + parallel subagent: `task-kotlin-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel Kotlin subagents) |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Scope auto-escalation signals (Kotlin-tuned):**

- File uploads (`MultipartFile`), Spring Security config (`SecurityFilterChain` Kotlin DSL, `@EnableMethodSecurity`), `@PreAuthorize` / `@PostAuthorize` changes, `@RequestBody` data class changes, raw JPQL/native SQL, secrets in `application.yml`, `KafkaListener` consuming user input -> auto-add **+Security**
- New Flyway/Liquibase migration, new JPA `@Query`, new `@EntityGraph`, new `Pageable` endpoints, new endpoints with payloads, loops over collections that hit DB or HTTP, new `@Cacheable` annotations, new `Flow<T>` streaming endpoints -> auto-add **+Perf**
- New `@Service` / `@Component`, new external client (`WebClient`/`RestClient`), new `@Async` / `@Scheduled` / `CoroutineScope.launch`, change to `logback-spring.xml` / `application.yml` logging or actuator config, new Micrometer registrations, new `@TransactionalEventListener` -> auto-add **+Observability**
- Two or more signal categories present -> promote to **Full**

## Invocation

| Invocation                     | Meaning                                                                                                                                |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-kotlin-review`          | Review current branch vs its base - fails fast if on a trunk branch; commit or switch to a feature branch first                        |
| `/task-kotlin-review <branch>` | Review `<branch>` vs its base (3-dot diff)                                                                                              |
| `/task-kotlin-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first                                |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>`.

Examples:

- `/task-kotlin-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-kotlin-review feature/x --base develop` - branch off `develop`

Scope and depth flags compose: `/task-kotlin-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Load Behavioral Principles (mandatory, first)

Use skill: `behavioral-principles`. These rules govern every step that follows - load them first so they apply to stack detection, diff resolution, scope decisions, and finding generation.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm Kotlin / Spring Boot. If invoked as a delegate of `task-code-review` (parent already detected Kotlin/Spring), accept the pre-detected stack. If the detected stack is not Kotlin/Spring Boot, stop and tell the user to invoke `/task-code-review` instead.

### Step 3 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument. Forward `--base <branch>` if passed.

If the precondition check stops with a fail-fast message, surface verbatim and stop. Do not run any state-changing git command.

Once approved, read the diff and commit log:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope**. For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals

Surface the decision in the Summary's `Scope:` field.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (security config, filters/interceptors, API contracts, shared base classes, `application.yml`, Flyway migrations, `build.gradle.kts` plugin block), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Phase B - Kotlin Correctness and Safety

Logical correctness, null-safety, coroutine safety, error handling completeness, edge cases, transaction boundary correctness - through a Kotlin/Spring lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding JUnit / kotest / Spring slice / Testcontainers coverage, raise this as an explicit named finding. Minimum [Suggestion]; escalate to [High] when the change touches a critical path - authentication (Spring Security / OAuth2 / JWT), authorization (`@PreAuthorize` / `SecurityFilterChain` matchers), money or billing flows, data-integrity writes (multi-table transactions, state machines), `CoroutineScope.launch` / `@KafkaListener` jobs that mutate data, Flyway migrations that change column semantics.

**Kotlin-specific correctness checks:**

- [ ] **Null safety / `!!` discipline**: no `!!` outside truly impossible-null sites; nullable types `T?` used over `Optional<T>`; platform types from Java collaborators treated as nullable at call sites; `error("...")` / `requireNotNull(...)` over `!!` for fail-fast intent
- [ ] **`data class` vs `class` for JPA**: every `@Entity` / `@MappedSuperclass` is a regular `class` with ID-based `equals`/`hashCode`, NEVER a `data class` (auto-generated `equals`/`hashCode`/`copy` break Hibernate proxies)
- [ ] **Kotlin compiler plugins**: `kotlin("plugin.jpa")` and `kotlin("plugin.spring")` configured in `build.gradle.kts`; no manual `open` modifier workarounds on entities or services
- [ ] **`@Transactional` boundaries**: writes inside `@Transactional` at the service layer (not controller, not repository); no HTTP calls / Kafka publishes / external I/O _inside_ the transaction (use `@TransactionalEventListener(phase = AFTER_COMMIT)` or transactional outbox)
- [ ] **`@Transactional` self-invocation**: no `this.transactionalMethod()` calls within the same bean - the Spring proxy is bypassed and the transaction silently does not start
- [ ] **`@Transactional` on `suspend`**: when a `suspend @Transactional` method exists, no `withContext(...)` switches inside it (can detach from the transaction binding)
- [ ] **Coroutine structured concurrency**: no `GlobalScope.launch { ... }` (leaks on shutdown); fire-and-forget uses an injected `CoroutineScope` bean; `coroutineScope { }` for parallel fan-out within a request; `supervisorScope { }` only when each child has an explicit fallback
- [ ] **`runBlocking` placement**: never inside service / controller methods; only at top-level entry points (`main`, scheduled-job adapters, Spring `@Bean` factory methods bridging to Java code)
- [ ] **Dispatchers vs Virtual Threads**: with `spring.threads.virtual.enabled=true`, `Dispatchers.IO` for blocking JDBC is redundant noise; `Dispatchers.Default` for CPU-bound work only
- [ ] **`Flow` exception transparency**: no `throw` inside `flow.collect { ... }`; use `catch` operator before `collect`; cleanup in `finally` wrapped in `withContext(NonCancellable)` if it must call `suspend` functions
- [ ] **Bean Validation on input**: every `@RequestBody` and `@RequestParam` data class has `@Valid` and the data class carries `@field:NotNull` / `@field:Size` / `@field:Pattern` (Kotlin annotation site target for Bean Validation)
- [ ] **Strong typing for input**: `@RequestBody` uses `data class` DTOs / records, never JPA entities directly (mass assignment risk - delegate to `task-kotlin-review-security` for depth)
- [ ] **N+1 query patterns**: any code that walks a `@OneToMany` / `@ManyToOne` after a query uses `@EntityGraph` or `join fetch`; lazy associations not touched outside the transaction (delegate to `task-kotlin-review-perf` for depth)
- [ ] **`Optional` returned from repository methods**: Kotlin code should convert to `T?` at the boundary (`.orElse(null)`) or use `.orElseThrow { ... }`; never `.get()` without prior `isPresent()`
- [ ] **JPA entities exposed in API**: controllers do not return `@Entity` types directly; responses go through `data class` DTO / projection - entities do not leak audit fields, password hashes, or lazy collections triggering `LazyInitializationException` mid-Jackson
- [ ] **Authorization on every endpoint**: every controller method has explicit `SecurityFilterChain` matcher coverage OR `@PreAuthorize`; `permitAll` documented (delegate to `task-kotlin-review-security`)
- [ ] **Error handling**: `@RestControllerAdvice` handles common exceptions (`MethodArgumentNotValidException`, `EntityNotFoundException`, `AccessDeniedException`) with consistent `ProblemDetail`; sealed-class result hierarchies converted to exceptions at the controller boundary; no blanket `catch (e: Exception)` swallowing root causes; no `e.printStackTrace()` / `println(e)` in production
- [ ] **Migration PRs (any change in `db/migration/` or `db/changelog/`)**: see the Migration PRs subsection below
- [ ] **Bulk operations**: partial-failure handling defined; idempotency for retryable bulk; JPA batch (`spring.jpa.properties.hibernate.jdbc.batch_size`) sized appropriately

**Migration PRs (any change in `src/main/resources/db/migration/` or `db/changelog/`):**

- [ ] Two-phase deploys for column rename / drop (add new -> backfill -> cut over -> remove old)
- [ ] `NOT NULL` on existing columns added via two-step
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); migration split so the concurrent statement runs outside a transaction
- [ ] Foreign keys added with validation deferred (or as a separate validate step)
- [ ] Data migrations isolated from DDL migrations
- [ ] Rollback path documented or verified
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `kotlin-spring-db-migration-safety` for canonical safe-migration patterns

**Concurrency safety:**

- [ ] Singleton beans hold no mutable state; if state is required, it is `val` immutable, `ConcurrentHashMap`, `AtomicReference`, or guarded by a lock
- [ ] **No `synchronized` on shared instances in Virtual Thread paths** (Spring Boot 3.2+ with `spring.threads.virtual.enabled=true`) - pinning the carrier thread defeats the model. Use `ReentrantLock` or `Mutex` (kotlinx.coroutines) instead
- [ ] No `companion object`-level mutable fields (`var`) without explicit thread-safety design
- [ ] Race-prone updates use database-level locking (`@Lock(LockModeType.PESSIMISTIC_WRITE)`, optimistic `@Version`)
- [ ] Cache writes thread-safe; `@Cacheable` keys deterministic; no race window between cache miss and cache fill on hot keys

Use skill: `kotlin-spring-jpa-performance` for canonical JPA correctness patterns.
Use skill: `kotlin-spring-transaction` for `@Transactional` propagation and coroutine-aware transactions.
Use skill: `kotlin-spring-async-processing` for any new or modified `@Async` / `CoroutineScope.launch` / Virtual Thread code.
Use skill: `kotlin-spring-exception-handling` for any new `@RestControllerAdvice` / sealed-class result handling.
Use skill: `kotlin-coroutines-spring` for any new `suspend` / `Flow` / structured concurrency code.
Use skill: `kotlin-idioms` for general Kotlin idiomatic review (data class, scope functions, sealed classes, value classes, interop).

### Phase C - Kotlin/Spring Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions.

**Kotlin-specific architecture checks:**

- [ ] **Layering**: `@RestController` -> `@Service` -> `@Repository`. No business logic in controllers; no `WebClient` / `RestClient` calls in repositories or entities; no view rendering inside services. Repositories return entities or projections; mapping to DTOs via extension functions (`Order.toResponse()`) at the service or controller boundary
- [ ] **Service-layer discipline**: any controller method with > 5 lines of orchestration extracted to a `@Service`; services expose intention-revealing methods (`fulfillOrder(orderId)`) not CRUD pass-throughs; cross-aggregate orchestration in a service, not in `@PostPersist` / `@PostUpdate` JPA callbacks
- [ ] **Anemic domain antipattern**: when business rules accumulate in services and entities are pure data containers, flag for refactor (see `task-kotlin-refactor`); push behavior into entities or value objects
- [ ] **Dependency injection style**: constructor injection via primary constructor only - no `@Autowired` field injection; `lateinit` only for test fields and Spring-injected non-constructor cases; no `ApplicationContextAware` for cross-bean lookup
- [ ] **Configuration discipline**: typed `@ConfigurationProperties` data classes over `@Value("\${...}")` field injection; `application.yml` profiles separated; no hardcoded values that should be config
- [ ] **Module / package boundaries**: feature-package layout (`com.acme.order.*` contains controller/service/repo for orders) preferred over layer-package layout; cross-feature imports go through public service interfaces
- [ ] **Multi-tenant isolation**: tenant scoping at the repository / `@Filter` layer, not at the controller layer alone
- [ ] **Aspect / interceptor discipline**: AOP aspects used for genuinely cross-cutting concerns - not as a hidden control-flow mechanism that swallows exceptions or rewrites return values
- [ ] **Single-impl interfaces**: no `OrderService` interface + single `OrderServiceImpl` pair without a test double or AOP requirement (Kotlin doesn't need interface for testability - MockK works on final classes)

**Multi-service PRs:**

- API contract compatibility checked (Spring Cloud Contract or Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**Kotlin-specific AI smells:**

- [ ] **Java-in-Kotlin patterns**: `Optional<T>` usage in pure-Kotlin code; `if (x != null)` chains instead of `?.`/`?:`/`let`; `for` loops where `map`/`filter`/`forEach` is idiomatic; utility classes with companion-object static methods where extension functions would be cleaner; `CompletableFuture` instead of `suspend` / coroutines
- [ ] **`!!` abuse**: non-null assertions used when a `?:` default, safe call, or `requireNotNull(...)` would express intent more clearly
- [ ] **Pattern inflation**: a `@Service` interface + single `@Service` implementation pair where the interface adds nothing; custom `Result<T>` wrapper where a sealed class or domain exception suffices; `BaseService<T>` parent classes for two services
- [ ] **Speculative configurability**: `@ConfigurationProperties` data classes with documented but unused keys; profile-conditional beans for environments that do not exist
- [ ] **Redundant mapping layers**: `Entity -> DomainObject -> ServiceDTO -> ResponseDTO` when one mapping (an extension function) would suffice
- [ ] **Test verbosity**: `@SpringBootTest` setup blocks > 30 lines for a single assertion; `@MockkBean` chains that could be a slice test; AssertJ assertion builders reimplemented when kotest matchers exist
- [ ] **Reactive / coroutine misapplication**: `Mono` / `Flux` (or `suspend`) in a non-coroutine servlet stack ("just in case we go reactive") - the runtime cost without the runtime benefit
- [ ] **Comment cruft**: comments restating method names; KDoc on private helpers that just repeats the signature; auto-generated TODOs left in
- [ ] **Scope function over-nesting**: more than 2 levels of `let`/`apply`/`run` nested - refactor to a named function

### Phase E - Kotlin Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Kotlin-specific maintainability checks:**

- [ ] **Naming conventions**: services describe their operation (`OrderFulfillmentService`); data classes named after their role (`OrderUpdateRequest`, `OrderResponse`); no `Util` / `Manager` / `Helper` classes accumulating unrelated methods; `internal` over `public` when the symbol does not cross the module boundary
- [ ] **Magic numbers / strings**: extracted to `const val` constants or `@ConfigurationProperties`; date/time constants use `Duration.ofMinutes(...)` not `60_000L`
- [ ] **Hardcoded URLs / credentials**: in `application.yml` profiles, env vars, or Vault - never inline
- [ ] **Method length**: methods > 20 lines reviewed for extraction; methods > 50 lines flagged unless orchestrating service methods calling intention-revealing private methods
- [ ] **Duplicated query logic**: same JPQL or `Specification` predicate in 3+ places extracted to a `Specification` factory or repository method
- [ ] **Logging hygiene**: SLF4J parameterized logging (`log.info("processing order={}", orderId)`) not string concatenation or string templates (`log.info("processing order=$orderId")` defeats parameterized logging benefits); log levels used correctly; no `println` / `System.out` / `dump()` in production
- [ ] **KDoc on public APIs**: public extension functions and `suspend` function contracts (cancellation behavior, exception propagation) documented; `@param`, `@return`, `@throws` on non-trivial public methods
- [ ] **`val` over `var`**: prefer `val` everywhere except framework-required mutable fields (entity status fields)

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-kotlin-review-observability` subagent owns the depth review).

### Step 5 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread.

| Scope                | Subagents spawned                                                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-kotlin-review-perf`                                                                                 |
| Core + Security      | 1 subagent running `task-kotlin-review-security`                                                                             |
| Core + Observability | 1 subagent running `task-kotlin-review-observability`                                                                        |
| Full                 | 3 subagents running `task-kotlin-review-perf`, `task-kotlin-review-security`, `task-kotlin-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Kotlin / Spring Boot)
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails, continue with remaining results. Note the missing scope.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below.

- **Deduplicate cross-cutting findings.** Same issue may surface in multiple scopes; keep one entry citing all scopes.
- **Severity wins.** Highest severity wins (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations.**
- **Order findings by severity, not by scope.**
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope>` under Summary.
- **Merge Next Steps.** Combine into one prioritized list.

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
**Stack Detected:** Kotlin <version> / Spring Boot <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Kotlin/Spring idiom: `!!` abuse, `data class` JPA entity, missing `kotlin-jpa` plugin, `GlobalScope.launch`, `synchronized` on Virtual Thread, `@Transactional` self-invocation, `every` on suspend function, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern]
- Fix: [concrete Kotlin change with code example]

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

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Replace `data class Order` with `class Order` + ID-based equals/hashCode in OrderEntity.kt"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.**

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Kotlin idioms (not just Spring conventions) - `!!`, `Optional`, `CompletableFuture` in Kotlin code are always flagged
- Provide actionable feedback with Kotlin code examples
- Never comment on trivial formatting where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Kotlin subagent


### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before stack detection or any other delegation
- [ ] Stack confirmed as Kotlin / Spring Boot (or accepted from parent dispatcher)
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher)
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained
- [ ] Scope auto-escalation evaluated in Step 4; promotion (or `core-only` suppression) recorded in Summary
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B Kotlin correctness checks applied: null-safety, `!!` discipline, `data class` JPA, kotlin-jpa/spring plugins, `@Transactional` boundaries / self-invocation / suspend, `GlobalScope`, `runBlocking`, Dispatchers vs VTs, `Flow` exception transparency, Bean Validation, JPA-in-API, `@PreAuthorize` coverage, exception advice, Virtual Thread pinning
- [ ] Phase C architecture checks applied: layering, anemic domain, primary-constructor injection, configuration discipline, package boundaries, multi-tenant
- [ ] Phase D AI-quality checks applied: Java-in-Kotlin, `!!` abuse, pattern inflation, speculative configurability, reactive/coroutine misapplication, scope-function over-nesting
- [ ] Phase E maintainability checks applied: naming, magic numbers, method length, parameterized SLF4J logging, KDoc, `val` over `var`
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk
- [ ] Every finding has a label, location (file:line), and actionable Kotlin fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Kotlin-specific subagents ran in parallel and received the pre-resolved diff/log handle
- [ ] Subagent findings merged with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Kotlin idiom exists (say "use `?:` instead of `if (x != null) ... else ...`")
- Nitpicking style where no project standard exists
- Providing vague feedback without a concrete Kotlin fix
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; default is to promote
- Duplicating perf / security / observability depth checks here when the dedicated Kotlin subagent owns them
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging
- Recommending `WebSecurityConfigurerAdapter`, `@Autowired` field injection, `data class` for JPA entities, `GlobalScope.launch`, `every` for `suspend`, or `@MockBean` for Kotlin classes - all anti-patterns
