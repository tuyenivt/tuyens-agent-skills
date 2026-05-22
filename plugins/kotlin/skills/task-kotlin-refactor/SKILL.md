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

Safe, step-by-step refactoring plan for a specific Kotlin / Spring Boot target. Identifies Kotlin- and Spring-specific smells and proposes independently committable steps with test gates.

The stack-specific delegate of `task-code-refactor`.

## When to Use

- Kotlin / Spring Boot smell identification and resolution
- Technical-debt reduction with a concrete plan
- Safe refactoring of a `@RestController` / `@Service` / `@Repository` / `@Entity` / configuration class
- Java-to-Kotlin idiom modernization

**Not for:** debt prioritization (`task-debt-prioritize`), feature changes (`task-kotlin-implement`), multi-module architecture (`task-design-architecture`), bug fixes (`task-kotlin-debug`).

## Inputs

| Input                | Required    | Description                                                                                       |
| -------------------- | ----------- | ------------------------------------------------------------------------------------------------- |
| Target scope         | Yes         | File, class, or package (e.g., `OrderController.kt`)                                              |
| Goal                 | Yes         | What the refactor should achieve                                                                  |
| Test coverage status | Recommended | Whether JUnit / Kotest / Spring slice / Testcontainers coverage exists                            |
| Shared surface       | Recommended | Whether target crosses module / library / team boundaries                                         |

## Workflow

### Step 1 - Behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-confirmed stack from parent. If not Kotlin / Spring Boot, redirect to `/task-code-refactor`.

### Step 3 - Read the target

Before classifying smells:

1. Read the target class top-to-bottom. Note: method count, longest method, primary-constructor vs `lateinit` injection, `@Transactional` placement, every external collaborator, `suspend` modifiers, scope-function nesting depth, `!!` count
2. Read the matching test file. Count cases by outcome (happy / validation / external failure / security / cancellation)
3. Read the immediate caller if obvious
4. Read `build.gradle.kts` for `kotlin("plugin.spring")` / `kotlin("plugin.jpa")`

If user named only the goal, ask for the target.

### Step 4 - Coverage gate (mandatory)

Refactoring without tests is a rewrite with extra steps. Status:

- **Adequate**: every public method tested; happy path + at least one boundary (401/403/validation/cancellation); coroutine code uses `runTest` / Turbine
- **Thin**: happy path only; missing security / cancellation tests
- **Inadequate**: < 50% line coverage, or no tests

If Inadequate - **stop**. Recommend `task-kotlin-test` first. Do not proceed past Step 5.

**Lint state:** `./gradlew detekt ktlintCheck` for baseline. Surface preparatory cleanup as Step 0 if new violations would land.

### Step 5 - Identify smells

Skip entirely if Step 4 returned Inadequate.

**Controllers**

| Smell                                  | Signal                                                                                | Risk   |
| -------------------------------------- | ------------------------------------------------------------------------------------- | ------ |
| Fat Controller                         | Method > 10 lines of orchestration                                                    | High   |
| Logic in Controller                    | Business rules / validation beyond Bean Validation / calculation / domain decisions   | High   |
| Direct Repository                      | Controllers call `@Repository` methods directly                                       | Medium |
| JPA Entity in API                      | `@RestController` returns or accepts `@Entity` types                                  | High   |
| Manual Validation Duplicating Beans    | Controller body re-checks `@field:NotNull` / `@field:Size`                            | Low    |
| Missing `@field:` Site Target          | Bean Validation on a `data class` parameter without `@field:` - silently ignored      | High   |

**Services**

| Smell                                  | Signal                                                                              | Risk   |
| -------------------------------------- | ----------------------------------------------------------------------------------- | ------ |
| God Service                            | `@Service` > 500 lines mixing concerns                                              | High   |
| Anemic Domain                          | Entities are pure data; rules in services / `OrderHelper.calculate(order)`          | High   |
| Single-Impl Interface                  | `OrderService` interface + single `OrderServiceImpl`                                | Medium |
| `@Transactional` Self-Invocation       | `this.transactionalMethod()` from non-transactional same-bean caller                | High   |
| `REQUIRES_NEW` Without Reason          | Used without comment explaining why                                                 | Medium |
| External I/O Inside `@Transactional`   | HTTP / message publish / file write inside a transactional method                   | High   |
| Service Returning Boolean              | Caller can't distinguish failures - sealed-class result is clearer                  | Medium |
| `@Transactional` + `withContext`       | `suspend @Transactional` switching dispatcher - can detach from TX                  | High   |

**Persistence**

| Smell                                  | Signal                                                                                 | Risk   |
| -------------------------------------- | -------------------------------------------------------------------------------------- | ------ |
| `data class` JPA Entity                | `@Entity data class` corrupts Hibernate proxies                                        | High   |
| Missing Kotlin Plugins                 | Manual `open` workarounds instead of `kotlin-jpa` / `kotlin-spring`                    | High   |
| Fat Entity                             | `@Entity` > 300 lines mixing mapping / computed properties / business ops              | High   |
| `@PostUpdate` / `@PostPersist` Abuse   | JPA lifecycle callback dispatching events / HTTP - races commit                        | High   |
| `FetchType.EAGER` on Collections       | Cartesian explosion + locks lazy semantics                                             | High   |
| Unbounded `findAll`                    | No `Pageable` on growing tables                                                        | Medium |
| `@Query` String Interpolation          | `"... where x = $userInput"` - SQL injection (Kotlin templates same as Java concat)    | High   |

**DI / config**

| Smell                                  | Signal                                                                              | Risk   |
| -------------------------------------- | ----------------------------------------------------------------------------------- | ------ |
| `@Autowired` Field Injection           | `@Autowired private lateinit var x: X`                                              | High   |
| `@Value` Field Injection               | Scattered config values; should be `@ConfigurationProperties`                       | Medium |
| `lateinit var` Overuse                 | Outside Spring-injected non-constructor cases or test setup                         | Medium |
| `ApplicationContextAware` Lookup       | Service-locator antipattern                                                         | High   |

**Coroutines / async**

| Smell                                  | Signal                                                                              | Risk   |
| -------------------------------------- | ----------------------------------------------------------------------------------- | ------ |
| `GlobalScope.launch`                   | Fire-and-forget leaks on shutdown                                                   | High   |
| `runBlocking` in Service / Controller  | Blocks the dispatcher                                                               | High   |
| Blocking JDBC in `suspend` w/o VTs     | No `withContext(Dispatchers.IO)`, VTs not enabled                                   | High   |
| Redundant `Dispatchers.IO` under VTs   | With VTs enabled, the wrap is dead noise                                            | Medium |
| Missing `MDCContext` on launch         | Trace correlation lost across dispatcher switches                                   | Medium |
| `synchronized` on VT path              | Pins carrier thread                                                                 | High   |
| `@KafkaListener` Without Idempotency   | Side effects re-run on redelivery                                                   | High   |
| `@Async` Without `TaskDecorator`       | MDC / trace / security context lost                                                 | Medium |
| Throw Inside `Flow.collect`            | Violates exception transparency                                                     | High   |

**Java-in-Kotlin idioms**

| Smell                              | Signal                                                              | Risk   |
| ---------------------------------- | ------------------------------------------------------------------- | ------ |
| `!!` Abuse                         | Where `?:`, safe call, or `requireNotNull` would express intent     | Medium |
| `Optional<T>` in Kotlin            | Repository wrappers instead of `T?`                                 | Medium |
| Java Streams Where Stdlib Fits     | `.stream().map().collect()` over `.map { }`                         | Low    |
| `CompletableFuture` for `suspend`  | New async code returning `CompletableFuture` in a suspend codebase  | Medium |
| Utility Class with Static Methods  | `object OrderUtils { @JvmStatic ... }` - prefer extension functions | Low    |
| Scope-Function Over-Nesting        | More than 2 levels                                                  | Low    |

**Aspects / tests** (same as Java equivalents): aspect as hidden control flow, aspect across many pointcuts; `@SpringBootTest` for unit logic, H2 for Postgres-feature app, `@MockBean` for Kotlin class, `every` for `suspend`, `runBlocking` in test bodies, `@DirtiesContext`.

Atomic skills consulted:

- `backend-coding-standards` cross-language catalog
- `complexity-review` for over-engineering signals
- `kotlin-idioms` Java-in-Kotlin detection
- `kotlin-coroutines-spring` coroutine pattern review

### Step 6 - Blast radius

Use skill: `review-blast-radius`. Kotlin/Spring-specific signals:

- [ ] Public API surface used by external clients
- [ ] `@AutoConfiguration` class or published artifact
- [ ] Aspect with broad pointcut
- [ ] Bean injected into 10+ callers
- [ ] JPA entity used in many queries
- [ ] `@Transactional` method called from outside
- [ ] `suspend` function with many callers

State: **Narrow** / **Moderate** / **Wide** / **Critical** before steps.

### Step 7 - Step sequence

Each step must be:

1. **Independently committable** - compiles + tests pass after each
2. **Behaviorally invariant** - no behavior change unless explicitly noted
3. **Reversible** - one revert away
4. **Tested** - existing suite continues to pass

**Per-step contracts:**

- **Transaction stance**: when extracting from a `@Transactional` caller, state whether the callee inherits the TX. If the extracted code makes external calls / publishes events / writes files, either keep them outside or move to `@TransactionalEventListener(AFTER_COMMIT)` / outbox.
- **Coroutine stance**: when extracting from `suspend`, state whether the callee is also `suspend` and whether the dispatcher is preserved.
- **Container stance**: when extracting beans, confirm `kotlin("plugin.spring")` is present.
- **Rollback**: how to revert in one `git revert`.

**Recipes:**

**Extract service from fat controller**

1. Add `<Verb><Noun>Service` with a single intention-revealing method returning a domain result; copy logic from controller; controller still does the work
2. Add `<Verb><Noun>ServiceTest` with one test per outcome
3. Update controller to call the service; preserve response shape; `@WebMvcTest` slice passes unchanged
4. Remove the original logic from the controller; verify slice test
5. Add slice test asserting failure surfaces as expected error response

**Convert `data class` JPA entity to regular class**

1. Add focused test reproducing equality / collection behavior currently relied on
2. Replace `data class Order(...)` with `class Order(...)` + explicit ID-based equality:
   ```kotlin
   override fun equals(other: Any?) = other is Order && id != 0L && id == other.id
   override fun hashCode() = id.hashCode()
   ```
3. Replace `.copy(...)` calls with explicit constructor calls
4. Run tests
5. If `kotlin-jpa` / `kotlin-spring` plugins are missing, add them in the same step

**Eliminate `!!`**

1. For each `!!`, decide intent: truly impossible → `requireNotNull(value) { "..." }`; default available → `?: default`; fail-fast → `error("...")`; optional → `?.let { } ?: alternative`
2. Compile and run tests after each batch
3. Track count: `git grep -c "!!"` before/after; aim for zero in production code

**Convert `@PostUpdate` to `@TransactionalEventListener(AFTER_COMMIT)`**

1. Add test reproducing current observable behavior
2. Replace JPA callback with a domain event published from the service; add `@TransactionalEventListener(phase = AFTER_COMMIT)` for the side effect
3. Side effects now fire post-commit; verify
4. Cross-aggregate work → extract to its own `@Service`

**Eliminate single-impl interface**

1. Confirm no test doubles, no second impl, no AOP target requirement (rare for Kotlin with MockK)
2. Rename `OrderServiceImpl` → `OrderService`, delete interface, update callers
3. Run tests
4. **Skip** if part of a published library API or has a real second implementation

**Field injection → primary constructor**

1. Add primary constructor parameters as `val`; remove `@Autowired` annotations; remove `lateinit var` when no longer needed
2. Run tests; MockK works on final classes
3. One class per commit if the suite is slow

**Replace `GlobalScope.launch` with managed scope bean**

1. Add `CoroutineConfig` with `applicationScope` bean (SupervisorJob + Dispatchers.Default + CoroutineExceptionHandler) + DisposableBean for shutdown
2. Inject the scope; replace `GlobalScope.launch` calls
3. Test the scope cancels at shutdown

**Make `@KafkaListener` idempotent**

1. Test that exact-once side effect occurs when the same message arrives twice
2. Add idempotency: dedup table on message UUID, business-key upsert, or version check
3. Verify transient retries still complete the work
4. Configure DLT + retry policy

**Replace `synchronized` on VT paths**

1. Confirm VT enabled (Boot 3.2+ + `spring.threads.virtual.enabled=true`)
2. Replace with `ReentrantLock` (or `Mutex` from `kotlinx.coroutines.sync` for coroutine paths)
3. Concurrency test (multiple VTs racing the critical section)
4. Audit other `synchronized` in the same module

**Move external I/O out of `@Transactional`**

Pick based on whether the original relied on rollback for the external action.

Option A - No rollback semantics needed:
1. Extract into `@TransactionalEventListener(AFTER_COMMIT)` handler; publish a domain event from the service
2. Move suspend HTTP / blocking I/O out of the `@Transactional` body into the listener
3. State the failure-mode warning: listener exceptions after commit are swallowed/logged by default
4. Use `@RecordApplicationEvents` to assert the event was published

Option B - Rollback semantics required:
1. Replace in-transaction call with a transactional outbox row: persist `OutboxEntry(intent, payload)` in the same transaction
2. Separate poller drains pending entries with at-least-once + idempotency key
3. Test the outbox is written even if the external call would fail
4. **Don't** simply move to `BEFORE_COMMIT` - same I/O hold + listener exception still rolls back, rarely the intent

Apply only one option per step.

**Fix `@Transactional` self-invocation**

Three options - pick on cohesion.

Option A - Extract to a separate bean (preferred for distinct responsibilities)
Option B - Self-injection (`@Lazy private val self: ThisService` - acceptable when extraction is artificial, document why)
Option C - `TransactionTemplate` (short inner method, single use site)

**Replace `runBlocking` in services with `suspend` propagation**

1. Identify the chain: which non-suspend caller forces `runBlocking`?
2. Add `suspend` to the original method
3. Walk up the chain; stop at the controller (Spring 6 supports `suspend` controllers)
4. If a caller can't be `suspend` (`@Scheduled`, JPA listener), keep `runBlocking` only at that boundary with a TODO comment naming the blocker
5. Replace test-side `runBlocking` with `runTest`

**`@MockBean` → `@MockkBean`**

1. Add `com.ninja-squad:springmockk` test dependency
2. Replace `@MockBean` with `@MockkBean`; `Mockito.given(...).willReturn(...)` → `every { ... } returns ...` (`coEvery` for suspend)
3. `verify(bean).method(...)` → `verify { bean.method(...) }` / `coVerify { ... }`
4. One test class per commit if the suite is slow

**`Optional<T>` → `T?`**

1. Extension `fun <T> Optional<T>.toNullable(): T? = orElse(null)` at the boundary, OR change Spring Data return types to `T?` directly
2. Update callers to use `?:` / `?.let` / `orElseThrow { ... }`
3. Repeat per repository method

### Step 8 - Validate plan

- [ ] Goal achieved at the end of the sequence
- [ ] Each step reviewable in < 30 minutes
- [ ] Tests run between steps
- [ ] Low-risk first (extracts, additions) before high-risk (deletions, signature changes, aspect rewrites)
- [ ] One revert per step
- [ ] No "while we're here" cleanup
- [ ] detekt + ktlint green between steps

## Output Format

```markdown
## Kotlin / Spring Boot Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Stack:** Kotlin <version> / Spring Boot <version>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate (cannot proceed)

[If Inadequate: state what coverage must exist first.]

## Lint Baseline

**detekt + ktlint:** Clean | Has violations - [count]

## Smells Identified

| Smell        | Location  | Risk | Notes                  |
| ------------ | --------- | ---- | ---------------------- |
| [Smell name] | file:line | High | [one-sentence why]     |

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one paragraph]

## Step Sequence

### Step 1 - [Verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Test gate:** [which tests must pass]
- **Transaction stance:** [inherits | post-commit listener | not transactional]
- **Coroutine stance:** [suspend | blocking | n/a]
- **Container stance:** [kotlin-spring confirmed | n/a]
- **Rollback:** [one revert command]

### Step 2 - [Verb + noun]
[Same structure]

## Verification

- [ ] Goal achieved
- [ ] Each step independently committable
- [ ] Test suite passes between steps
- [ ] No bundled cleanup
- [ ] Rollback = one revert per step
- [ ] No I/O silently moved across `@Transactional` boundaries
- [ ] No coroutine dispatcher silently changed mid-`suspend @Transactional`
- [ ] detekt + ktlint clean between steps

## Out of Scope

[Adjacent improvements not in this plan]
```

## Self-Check

- [ ] `behavioral-principles` loaded
- [ ] Stack confirmed
- [ ] Target + tests read directly before smell classification
- [ ] Coverage gate evaluated; refused if Inadequate
- [ ] Lint state checked
- [ ] Smells identified using Step 5 catalog
- [ ] Blast radius stated before steps
- [ ] Each step independently committable; test gate per step
- [ ] Transaction + coroutine + container stance per step
- [ ] Steps ordered low-risk first
- [ ] No bundled cleanup
- [ ] Goal mapped to end state
- [ ] Rollback per step

## Avoid

- Proposing without a test-coverage gate
- Bundling behavior changes with refactor steps
- "While we're here" cleanups
- Renaming during a refactor
- Removing `@PostUpdate` / `@PostPersist` without a test asserting current behavior
- Extracting an interface with one implementation
- "Fixing" `@Transactional` self-invocation by annotating the inner method without restructuring
- Moving HTTP / message publishes across `@Transactional` boundaries without stating the stance
- `withContext(...)` switches inside a `suspend @Transactional` method
- Refactoring an `@AutoConfiguration` class without a backward-compatibility plan
- Replacing `synchronized` with `ReentrantLock` on a non-VT path with no concurrency benefit
- Replacing `data class` JPA entity without verifying `kotlin-jpa` / `kotlin-spring` plugins
- Removing `!!` by adding blanket try/catch
