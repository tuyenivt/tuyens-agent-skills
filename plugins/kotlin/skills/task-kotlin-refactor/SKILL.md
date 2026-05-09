---
name: task-kotlin-refactor
description: Kotlin / Spring Boot refactor plan: fat controllers, anemic domain, !! abuse, coroutine misuse, @Transactional bugs; phased risk/effort steps.
agent: kotlin-tech-lead
metadata:
  category: backend
  tags: [kotlin, spring-boot, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# Kotlin / Spring Boot Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Kotlin/Spring Boot target (controller, service, repository, JPA entity, configuration class, aspect). Identifies Kotlin- and Spring-specific smells (fat controllers, anemic domain, `!!` abuse, `GlobalScope.launch`, blocking calls in `suspend` functions, `lateinit` overuse, `data class` JPA entities, missing `kotlin-jpa` / `kotlin-spring` plugins, `@Transactional` misuse, single-impl interfaces, `@Autowired` field injection, JPA-listener callback abuse) and proposes independently-committable refactoring steps with JUnit / Kotest / Spring slice test gates.

This workflow is the stack-specific delegate of `task-code-refactor` for Kotlin/Spring Boot.

## When to Use

- Kotlin/Spring Boot code-smell identification and resolution
- Kotlin technical-debt reduction with a concrete plan
- Safe refactoring of a `@RestController` / `@Service` / `@Repository` / `@Entity` / configuration class
- Java-to-Kotlin idiom modernization (`Optional` -> `T?`, `if (x != null)` chains -> safe calls, `CompletableFuture` -> `suspend`)
- Pre-merge "this PR grew the fat-controller / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-kotlin-implement`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-kotlin-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                  |
| --------------------- | ----------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, class, or package to refactor (e.g., `OrderController.kt`, `com.acme.order.service.OrderService`)                      |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `OrderFulfillmentService`, kill `@PostUpdate` chain, split `UserService`) |
| Test coverage status  | Recommended | Whether JUnit / Kotest / Spring slice / Testcontainers coverage exists for the target                                        |
| Shared/public surface | Recommended | Whether the target is used across module / library / team boundaries                                                         |

## Workflow

### Step 1 - Load Behavioral Principles (mandatory, first)

Use skill: `behavioral-principles`. Load these rules first - they govern smell classification, blast-radius assessment, and step proposals.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm Kotlin / Spring Boot. If invoked as a subagent of a Spring-aware parent, accept the pre-confirmed stack. If not Kotlin/Spring Boot, stop and tell the user to invoke `/task-code-refactor` instead.

### Step 3 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells:

1. Read the target class top-to-bottom; note method count, longest method, primary-constructor injection vs `lateinit` field injection, `@Transactional` placement, every external collaborator (`WebClient`, `RestClient`, `KafkaTemplate`), `suspend` modifiers, scope-function nesting depth, `!!` count
2. Read the matching test file (e.g., `OrderServiceTest.kt`, `OrderServiceSpec.kt`, `@WebMvcTest(OrderController::class)`); count cases by outcome (happy path, validation failure, external failure, security denial, coroutine cancellation)
3. If callers are obvious, read the immediate caller too
4. Read `build.gradle.kts` to confirm `kotlin("plugin.spring")` and `kotlin("plugin.jpa")` are present when JPA / Spring annotations exist on the target

If the user named only the goal without a target file, ask for the target before proceeding.

### Step 4 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Before proposing any refactor:

1. Identify the tests covering the target (`<Target>Test.kt`, `<Target>IntegrationTest.kt`, `@WebMvcTest(<Target>::class)`, `@DataJpaTest` for repositories)
2. Run coverage assessment - if coverage is missing or thin, **stop and require coverage first**. Recommend `task-kotlin-test` to fill gaps
3. If coverage exists but is happy-path-only, flag the boundary-test gap as a prerequisite step (refactor must not silently change validation / 401 / 403 / not-found / coroutine-cancellation behavior)

**Output of this step:** explicit coverage status - `Adequate` / `Thin (boundary tests missing)` / `Inadequate (refuse to proceed without coverage)`. Do not proceed past Step 5 if coverage is inadequate.

**Sharp boundaries (Kotlin-specific):**

- **Adequate**: every public method has a test; happy path + at least one boundary case (401/403/validation error/cancellation); coroutine code uses `runTest` and Turbine where appropriate
- **Thin**: happy path only; no security tests; no coroutine cancellation tests when `suspend` is in use
- **Inadequate**: < 50% line coverage on target, or no tests at all

**Lint state check:** run (or have the user run) `./gradlew detekt ktlintCheck` to confirm baseline. If new violations would land in the refactor, surface them as a Step 0 preparatory cleanup item in the output.

### Step 5 - Identify Kotlin/Spring Smells

Inspect the target for these Kotlin- and Spring-specific smells. Use judgment - these are signals, not hard rules. Skip this step entirely if the coverage gate in Step 4 returned `Inadequate`.

**Controller smells:**

| Smell                                         | Signal                                                                                                                | Risk   |
| --------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Controller                                | Controller method > 10 lines of orchestration                                                                         | High   |
| Logic in Controller                           | Business rules, validation beyond Bean Validation, calculation, or domain decisions inside the handler               | High   |
| Direct Repository in Controller               | Controllers call `@Repository` methods directly, bypassing the service layer                                          | Medium |
| JPA Entity in API                             | `@RestController` returns `@Entity` types or accepts entities as `@RequestBody` (mass assignment + lazy load risk)    | High   |
| Manual Validation Duplicating Bean Validation | Controller body re-checks `@field:NotNull` / `@field:Size` constraints already on the data class                      | Low    |
| Missing `@field:` Site Target                 | Bean Validation annotation on a `data class` parameter without `@field:` site target - silently does not apply       | High   |

**Service smells:**

| Smell                                         | Signal                                                                                                              | Risk   |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------ |
| God Service                                   | `@Service` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                     | High   |
| Anemic Domain                                 | Entities are pure data containers; business rules live in services with names like `OrderHelper.calculate(order)`   | High   |
| Single-Impl Interface                         | `OrderService` interface + single `OrderServiceImpl` (Kotlin's MockK works on final classes - interface unnecessary) | Medium |
| `@Transactional` Self-Invocation              | `this.transactionalMethod()` from a non-transactional method in the same bean - proxy bypassed                       | High   |
| `@Transactional(REQUIRES_NEW)` Without Reason | `REQUIRES_NEW` used without comment explaining why outer rollback should not propagate                              | Medium |
| External I/O Inside `@Transactional`          | HTTP call, message publish, file write inside a transactional method                                                 | High   |
| Service Returning Boolean                     | Service returns `Boolean`; caller cannot distinguish failure cases - prefer sealed-class result                      | Medium |
| `@Transactional` + `withContext` Switch       | `suspend @Transactional` body switches dispatcher mid-method - can detach from the transaction binding              | High   |

**Persistence / JPA smells:**

| Smell                                            | Signal                                                                                                                     | Risk   |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- | ------ |
| `data class` for JPA Entity                      | `@Entity data class Order(...)` - `equals` / `hashCode` / `copy` corrupt Hibernate proxies                                  | High   |
| Missing `kotlin-jpa` / `kotlin-spring` Plugin    | `build.gradle.kts` lacks `kotlin("plugin.jpa")` or `kotlin("plugin.spring")` - manual `open` modifiers as workaround       | High   |
| Fat Entity                                       | `@Entity` > 300 lines; mixes mapping, computed properties, business operations, mapping helpers                            | High   |
| `@PostUpdate` / `@PostPersist` Abuse             | JPA lifecycle callback dispatching emails, publishing events, calling external services - races commit and silently breaks | High   |
| `FetchType.EAGER` on Collections                 | Eager fetch on `@OneToMany` / `@ManyToMany` - cartesian explosion + locks lazy semantics elsewhere                         | High   |
| Repository Returning `List` for Unbounded Reads  | `findAll()`, `findByX(...)` without `Pageable` parameter                                                                   | Medium |
| `@Query` String-Template Concatenation           | `@Query("... where x = $userInput")` - SQL injection (Kotlin string templates evaluate at compile time - same as Java concat) | High |

**Configuration / DI smells:**

| Smell                                  | Signal                                                                                              | Risk   |
| -------------------------------------- | --------------------------------------------------------------------------------------------------- | ------ |
| `@Autowired` Field Injection           | `@Autowired private lateinit var bean: SomeBean` - prefer primary-constructor injection             | High   |
| `@Autowired` Setter Injection          | Same problems plus mutable bean state                                                               | Medium |
| `@Value("\${...}")` Field Injection    | Single config values scattered across classes; should be `@ConfigurationProperties` data class     | Medium |
| `lateinit var` Overuse                 | `lateinit var` used outside of Spring-injected non-constructor cases or test setup                 | Medium |
| `ApplicationContextAware` Lookup       | Service uses `ApplicationContext.getBean(...)` - service locator antipattern                         | High   |
| Hidden `@ConditionalOnProperty`        | Bean conditional on a property with no off path                                                     | Low    |

**Coroutine / async smells:**

| Smell                                       | Signal                                                                                                | Risk   |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------ |
| `GlobalScope.launch`                        | Fire-and-forget on `GlobalScope` - leaks on shutdown, no error handler                                | High   |
| `runBlocking` in Service / Controller       | `runBlocking { ... }` inside service methods - blocks the dispatcher                                  | High   |
| Blocking JDBC inside `suspend` without VTs  | `suspend` method calls blocking JPA / JDBC without `withContext(Dispatchers.IO)` and VTs not enabled  | High   |
| Redundant `Dispatchers.IO` under VTs        | `withContext(Dispatchers.IO)` on JDBC when `spring.threads.virtual.enabled=true`                      | Medium |
| Missing `MDCContext` on Coroutine Launch    | `applicationScope.launch { ... }` without `MDCContext` - trace correlation lost                       | Medium |
| `synchronized` on Virtual Thread Path       | `synchronized` block in a `@Service` running under Boot 3.2+ Virtual Threads - pins carrier thread    | High   |
| `@KafkaListener` Without Idempotency        | Listener that re-runs side effects when the same message is delivered twice                          | High   |
| `@Async` Without `TaskDecorator`            | Trace context, MDC, and `SecurityContext` lost across the async boundary                              | Medium |
| Throwing Inside `Flow.collect`              | Violates Flow exception transparency - use `catch` operator before `collect`                          | High   |

**Kotlin idiom smells (Java-in-Kotlin):**

| Smell                                  | Signal                                                                                       | Risk   |
| -------------------------------------- | -------------------------------------------------------------------------------------------- | ------ |
| `!!` Abuse                             | `!!` used where `?:`, safe call, or `requireNotNull(...)` would express intent              | Medium |
| `Optional<T>` in Kotlin Code           | Repository returns wrapped in `Optional<T>` instead of `T?`                                  | Medium |
| Java Streams Where Kotlin Stdlib Fits  | `.stream().map(...).collect(...)` instead of `.map { ... }`                                   | Low    |
| `CompletableFuture` Where `suspend` Fits | New async code returning `CompletableFuture<T>` in a coroutine-aware codebase               | Medium |
| Utility Class with Static Methods      | `object OrderUtils { @JvmStatic fun ... }` where extension functions would be cleaner       | Low    |
| Scope-Function Over-Nesting            | More than 2 levels of `let`/`apply`/`run` nested - extract to a named function              | Low    |

**Aspect / interceptor smells:**

| Smell                         | Signal                                                                                                | Risk   |
| ----------------------------- | ----------------------------------------------------------------------------------------------------- | ------ |
| Aspect as Hidden Control Flow | `@Around` aspect that swallows exceptions, rewrites return values, or short-circuits invisibly       | High   |
| Aspect Across Many Pointcuts  | One `@Aspect` class with > 3 unrelated `@Around` advices - split per-concern                         | Medium |

**Test smells:**

| Smell                                         | Signal                                                                                  | Risk   |
| --------------------------------------------- | --------------------------------------------------------------------------------------- | ------ |
| `@SpringBootTest` for Unit Logic              | Full context loaded for what could be a plain JUnit / Kotest + MockK test               | Medium |
| H2 in `@DataJpaTest` for Postgres-feature App | Tests pass on H2 but fail in prod on JSONB / partial index / `ON CONFLICT` semantics   | High   |
| `@MockBean` for Kotlin Class                  | `@MockBean` used instead of `@MockkBean` - Mockito + final Kotlin class fails silently | Medium |
| `every` for `suspend` Function                | `every { repo.findById(1L) } returns x` instead of `coEvery { ... }` - silently fails  | High   |
| `runBlocking` in Test Body                    | Test body wrapped in `runBlocking` instead of `runTest` - real-time waits, flaky        | Medium |
| `@DirtiesContext`                             | Used to work around shared state instead of fixing isolation                            | Medium |

Use skill: `backend-coding-standards` for cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl interfaces, premature `Strategy`/`Factory`, redundant mapping layers).
Use skill: `kotlin-idioms` for Java-in-Kotlin pattern detection.
Use skill: `kotlin-coroutines-spring` for coroutine pattern review.

### Step 6 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected.

Kotlin/Spring-specific blast-radius signals:

- [ ] **Public API surface**: target is a controller used by external clients
- [ ] **Library / module boundary**: target is in an `@AutoConfiguration` class or a published artifact
- [ ] **Aspect with broad pointcut**: refactoring an aspect with `execution(* com.acme..*.*(..))` affects every matching method
- [ ] **Bean injected widely**: target is a `@Bean` injected into > 10 callers
- [ ] **JPA entity used in many queries**: refactoring an entity affects every `@Query` / `Specification`
- [ ] **`@Transactional` method called from outside**: removing `@Transactional` may silently break callers
- [ ] **`suspend` function called from many places**: changing the suspend signature ripples through the call chain

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single module, multiple callers) / **Wide** (cross-module, public API, broad aspect) / **Critical** (`@AutoConfiguration` published, entity used by 5+ services).

### Step 7 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing JUnit / Kotest / slice / Testcontainers suite continues to pass

**Per-step stance contracts:**

- **Transaction stance**: when extracting orchestration that runs inside a `@Transactional` method, state whether the extracted unit inherits the transaction context. If the extracted code makes HTTP calls / publishes Kafka / writes files, they now happen mid-transaction (regression). Either keep them outside or move them to `@TransactionalEventListener(phase = AFTER_COMMIT)` / outbox
- **Coroutine stance**: when extracting from a `suspend` method, state whether the extracted unit is also `suspend` and whether dispatcher is preserved
- **Container stance**: when extracting beans, confirm `kotlin("plugin.spring")` is configured so the new class can be proxied
- **Rollback**: how to revert in one git revert

**Common Kotlin/Spring refactor recipes:**

**Recipe: Extract service from fat controller**

1. Add `<Verb><Noun>Service` (e.g., `PlaceOrderService`) with a single intention-revealing method returning a domain result type (sealed class or `data class`); copy logic from controller; controller still does the original work
2. Add `<Verb><Noun>ServiceTest` with one test per outcome
3. Update controller to call the service; preserve response shape; ensure `@WebMvcTest` slice test passes unchanged
4. Remove the original logic from the controller; verify `@WebMvcTest` passes
5. Add a `@WebMvcTest` example asserting service failure surfaces as the expected error response (likely via `@RestControllerAdvice` + sealed-class-to-exception conversion)

**Recipe: Convert `data class` JPA entity to regular class**

1. Add a `@DataJpaTest` (or focused service test) reproducing equality / collection behavior currently relied upon
2. Replace `data class Order(...)` with `class Order(...)` and add explicit ID-based `equals` / `hashCode`:
   ```kotlin
   override fun equals(other: Any?) = other is Order && id != 0L && id == other.id
   override fun hashCode() = id.hashCode()
   ```
3. Replace any `.copy(...)` calls in production code with explicit constructor or builder calls
4. Run tests; confirm pass. Hibernate proxy semantics are now correct
5. If the project lacks `kotlin("plugin.jpa")` / `kotlin("plugin.spring")`, add them in the same step (otherwise the no-arg constructor and proxy subclassing will fail)

**Recipe: Eliminate `!!` abuse**

1. For each `!!` site, decide intent:
   - Truly impossible null (e.g., post-validation): replace with `requireNotNull(value) { "expected non-null because ..." }`
   - Default available: replace with `?: defaultValue`
   - Fail-fast crash: replace with `error("never null because ...")`
   - Optional handling: replace with `?.let { ... } ?: alternative`
2. Compile and run tests after each batch; the suite catches changes in failure semantics
3. Track the count: `git grep -c "!!"` before and after - aim for zero in production code (test code may legitimately use `!!` for known-non-null values)

**Recipe: Convert `@PostUpdate` / JPA lifecycle callback to `@TransactionalEventListener(AFTER_COMMIT)`**

1. Add a `@SpringBootTest` (or focused `@DataJpaTest` + service test) reproducing the current observable behavior
2. Replace the JPA `@PostUpdate` with a domain event published from the service: `applicationEventPublisher.publishEvent(OrderUpdated(orderId))`. Add a `@TransactionalEventListener(phase = AFTER_COMMIT)` for the side effect
3. Run tests; confirm pass. Side effects now fire post-commit
4. If callback was doing cross-aggregate work, extract the side-effect handler into its own `@Service`
5. Run the full suite

**Recipe: Eliminate single-implementation interface**

1. Confirm the interface has no test doubles, no second implementation, no AOP target requirement (rare for Kotlin since MockK works on final classes)
2. Inline the interface: rename `OrderServiceImpl` -> `OrderService`, delete the interface, update callers
3. Run tests; confirm pass
4. **Skip if** the interface is part of a published library API or has a real second implementation

**Recipe: Migrate `@Autowired` field injection to primary-constructor injection**

1. Add a primary constructor accepting the injected dependencies as parameters (`val` properties)
2. Remove `@Autowired` annotations on fields; remove `lateinit var` if no longer needed
3. Run tests; confirm pass. MockK continues to work
4. Repeat per class; one class per commit if the suite is slow

**Recipe: Replace `GlobalScope.launch` with managed `CoroutineScope` bean**

1. Add a `CoroutineConfig` `@Configuration` class with an `applicationScope` bean (`SupervisorJob() + Dispatchers.Default + CoroutineExceptionHandler { ... }`) plus a `DisposableBean` to cancel on shutdown
2. Inject the `CoroutineScope` bean into the service
3. Replace `GlobalScope.launch { ... }` calls with `applicationScope.launch { ... }`
4. Add a test asserting the scope cancels on application shutdown (no zombie work)

**Recipe: Make `@KafkaListener` idempotent**

1. Add a listener test asserting the side effect happens exactly once when the same message is delivered twice (different offsets, same business key)
2. Add an idempotency guard: dedup table keyed by message UUID, business-key upsert (`ON CONFLICT DO NOTHING`), or version check
3. Verify retries on transient failures still complete the work
4. Configure DLT (`spring.kafka.listener.ack-mode: manual_immediate` + retry / DLT topic)

**Recipe: Replace `synchronized` on Virtual Thread paths**

1. Confirm the path runs under Virtual Threads (Boot 3.2+ with `spring.threads.virtual.enabled=true`)
2. Replace `synchronized(this)` / `synchronized(lock)` with `ReentrantLock` (or `Mutex` from `kotlinx.coroutines.sync` for coroutine paths)
3. Verify with a concurrency test (multiple Virtual Threads racing the critical section)
4. Audit other `synchronized` blocks in the same module

**Recipe: Move external I/O out of `@Transactional`**

External calls (HTTP, Kafka publish, email, file write) inside an `@Transactional` block hold the DB connection for the round-trip and can leave the system in an inconsistent state if the post-IO commit fails. Two safe options - pick based on whether the original code relied on rollback for the external action.

Option A - No rollback semantics needed (most common; "send email after order is saved"):

1. Extract the external call into a `@TransactionalEventListener(phase = AFTER_COMMIT)` handler, publishing a domain event from the service: `applicationEventPublisher.publishEvent(OrderPlaced(orderId))`
2. Move the suspend HTTP / blocking I/O out of the `@Transactional` body into the new listener
3. **Failure mode warning:** if the listener throws, the transaction is already committed - the exception is swallowed/logged by default. State this in the plan and decide whether you need durability (queue, outbox, retry pattern)
4. Run tests (use `@RecordApplicationEvents` to assert the event was published)

Option B - Rollback semantics required (e.g., "if Stripe charge succeeds but DB save fails, refund"):

1. Replace the in-transaction call with a transactional outbox row: persist an `OutboxEntry(intent, payload)` inside the same transaction
2. A separate poller / scheduled job reads pending outbox entries and performs the external call with at-least-once semantics + idempotency key
3. Add a test asserting the outbox is written even if the external call would fail
4. **Do not** simply move the call to `BEFORE_COMMIT` - it still holds the connection and a listener exception still rolls back the TX, which is rarely the intent

Apply only one option per step; do not mix.

**Recipe: Fix `@Transactional` self-invocation**

`this.transactionalMethod()` from a non-transactional method in the same bean bypasses the Spring proxy. Three options - pick based on cohesion:

Option A - Extract to a separate bean (preferred when the methods belong to different responsibilities):

1. Create a new `@Service` containing the inner transactional method; inject the new service into the original
2. Replace `this.transactionalMethod()` with `newService.transactionalMethod()`
3. Run tests; the proxy now applies

Option B - Self-injection (when methods belong to the same responsibility and extraction would be artificial):

1. Add `@Lazy private val self: ThisService` to the constructor (or use `@Resource` field in a `lateinit var`)
2. Call `self.transactionalMethod()` instead of `this.transactionalMethod()`
3. **Caveat**: self-injection is a known smell in many style guides; document why it was chosen over extraction

Option C - `TransactionTemplate` (when the inner method is short and used in one place):

1. Inject `TransactionTemplate`; replace `this.transactionalMethod()` with `transactionTemplate.execute { /* body */ }`
2. Remove `@Transactional` from the inner method (now redundant)
3. Run tests

**Recipe: Replace `runBlocking` in service code with `suspend` propagation**

`runBlocking` inside `@Service` / `@RestController` methods blocks the dispatcher thread, defeating coroutines and risking deadlock under load.

1. Identify the call chain: which non-suspend caller forces `runBlocking`?
2. Add `suspend` to the original service method
3. Walk up the call chain, adding `suspend` to each caller; stop at the controller (Spring 6 supports `suspend` controller methods natively)
4. If a caller is genuinely blocking (e.g., `@Scheduled`, JPA listener) and cannot be made `suspend`, keep `runBlocking` only at that boundary and add a TODO comment naming the blocker (e.g., `// TODO: @Scheduled does not support suspend; safe here because scheduler thread pool is dedicated`)
5. Run tests using `runTest` (replace any test-side `runBlocking` with `runTest` to enable virtual time)

**Recipe: Migrate `@MockBean` to `@MockkBean` (Kotlin)**

`@MockBean` uses Mockito; Mockito does not mock final Kotlin classes by default and silently produces non-mock instances when `kotlin-spring` plugin doesn't open the bean. `@MockkBean` (from `com.ninja-squad:springmockk`) handles final classes natively.

1. Add `com.ninja-squad:springmockk:<version>` test dependency in `build.gradle.kts` if not present
2. For each test class with `@MockBean`, replace with `@MockkBean`; replace `Mockito.given(...).willReturn(...)` / `when_(...).thenReturn(...)` with MockK `every { ... } returns ...` (and `coEvery` for suspend)
3. Replace `verify(bean).method(...)` with `verify { bean.method(...) }` / `coVerify { bean.suspendMethod(...) }`
4. Run tests; assertion semantics are equivalent but argument matchers differ (`any()` -> `any()`, `eq(x)` -> `eq(x)`, `argThat { ... }` -> `match { ... }`)
5. One test class per commit if the suite is slow

**Recipe: Convert `Optional<T>` repository returns to `T?`**

1. Add a thin extension function (`fun <T> Optional<T>.toNullable(): T? = orElse(null)`) at the boundary, OR change Spring Data repository return types to `T?` directly (Spring Data Kotlin extension supports both)
2. Update callers to use Kotlin null handling (`?:`, `?.let`, `orElseThrow { ... }`)
3. Run tests
4. Repeat per repository method

### Step 8 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, aspect rewrites)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup
- [ ] Linter (detekt + ktlint) green between every step

## Output Format

```markdown
## Kotlin / Spring Boot Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Stack:** Kotlin <version> / Spring Boot <version>

## Coverage Gate

**Status:** Adequate | Thin (boundary tests missing) | Inadequate (cannot proceed)

[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-kotlin-test` first.]

## Lint Baseline

**detekt + ktlint:** Clean | Has violations - [count, summary]

[If violations would land in the refactor, surface them as Step 0a preparatory cleanup.]

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale]

## Step Sequence

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Test gate:** [which tests must pass after this step - JUnit / Kotest / `@WebMvcTest` / `@DataJpaTest` / `@SpringBootTest`]
- **Transaction stance:** [callee runs inside caller's `@Transactional` | callee uses `@TransactionalEventListener(AFTER_COMMIT)` | not transactional]
- **Coroutine stance:** [callee is `suspend` | callee is blocking | n/a]
- **Container stance:** [`kotlin("plugin.spring")` confirmed | n/a]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] Test suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across `@Transactional` boundaries
- [ ] No coroutine dispatcher silently changed mid-`suspend @Transactional`
- [ ] detekt + ktlint clean between every step

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before stack detection or any other delegation
- [ ] Stack confirmed as Kotlin / Spring Boot (or accepted from parent dispatcher)
- [ ] Target file(s) and matching tests read directly before smell classification
- [ ] Coverage gate evaluated; refused to propose plan if coverage was inadequate
- [ ] Lint state checked; preparatory cleanup added when violations would land in the refactor
- [ ] Kotlin/Spring-specific smells identified using Step 4 catalog (controller, service, persistence, configuration/DI, coroutine/async, Java-in-Kotlin, aspect, test)
- [ ] Cross-module risk (blast radius) stated before proposing steps
- [ ] Each step independently committable; test gate stated per step
- [ ] Transaction stance + coroutine stance + container stance stated per step
- [ ] Steps ordered low-risk first
- [ ] No step bundles unrelated cleanup
- [ ] Goal explicitly mapped to the end state
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate
- Bundling behavior changes with refactoring steps
- Making "while we're here" unrelated cleanups
- Renaming during a refactor
- Removing JPA `@PostUpdate` / `@PostPersist` callbacks without a test asserting the original behavior is preserved
- Extracting an interface with one implementation - Kotlin's MockK works on final classes
- Replacing `@Transactional` self-invocation by adding `@Transactional` to the inner method without restructuring the call - the proxy is still bypassed
- Moving HTTP calls or message publishes from a non-transactional context to inside a transactional one (or vice versa) without explicitly stating the transaction stance
- Switching dispatcher (`withContext(...)`) inside a `suspend @Transactional` method - can detach from the transaction binding
- Refactoring an `@AutoConfiguration` class without a backward-compatibility plan
- Replacing `synchronized` with `ReentrantLock` on a non-Virtual-Thread path with no concurrency benefit (premature change)
- Replacing `data class` JPA entity with regular class without simultaneously verifying `kotlin("plugin.jpa")` / `kotlin("plugin.spring")` are configured - the no-arg constructor and proxy subclassing will fail at runtime
- Removing `!!` by adding blanket `try/catch` blocks - keep the fail-fast intent via `requireNotNull` or `error()`
