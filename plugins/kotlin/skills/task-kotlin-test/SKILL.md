---
name: task-kotlin-test
description: Kotlin/Spring Boot test strategy and scaffolding using JUnit 5 / kotest, MockK + springmockk (@MockkBean), Spring test slices (@WebMvcTest, @DataJpaTest), Testcontainers, runTest for coroutines, Turbine for Flow, and Spring Security Test. Stack-specific override of task-code-test for Kotlin/Spring Boot.
agent: kotlin-test-engineer
metadata:
  category: backend
  tags: [kotlin, spring-boot, junit, kotest, mockk, testcontainers, coroutines, testing, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after Step 1 (behavioral-principles) and Step 2 (stack-detect). When a spec is loaded, generate one test per acceptance criterion (use `Satisfies: AC<N>` mapping in test names), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Kotlin / Spring Boot Test

## Purpose

Kotlin-aware test strategy and scaffolding using JUnit 5 / kotest, MockK + springmockk (`@MockkBean`), Spring test slices, Testcontainers (PostgreSQL, Kafka, Redis), `runTest` for coroutines, Turbine for `Flow`, and the Spring Boot test pyramid (unit / slice / full-context / E2E). Replaces generic backend test patterns with Kotlin-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for Kotlin / Spring Boot.

## When to Use

- Designing a Kotlin/Spring Boot test strategy for a new service or module
- Assessing test coverage gaps across unit / slice / full-context / contract tests
- Scaffolding tests for under-covered controllers, services, repositories, security configs, or coroutine paths
- Reviewing test pyramid balance for a Kotlin/Spring app
- Adding boundary tests (validation, authorization, edge cases) to existing happy-path tests

**Not for:**

- Test failure debugging (use `task-kotlin-debug`)
- General code review (use `task-code-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Load Behavioral Principles (mandatory, first)

Use skill: `behavioral-principles`. Load these rules first - they govern every step.

### Step 2 - Confirm Stack

Use skill: `stack-detect` to confirm Kotlin / Spring Boot. If invoked as a delegate of `task-code-test` (parent already detected Kotlin/Spring), accept the pre-confirmed stack and skip re-detection. If not, stop and tell the user to invoke `/task-code-test` instead.

### Step 3 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code and a representative sample of existing tests:

- For each target named by the user, read the class top-to-bottom: public methods, request/response types, security annotations, transaction boundaries, external collaborators, `suspend` modifiers
- Glob `src/test/kotlin/**/*Test*.kt` and `**/*Spec*.kt` and read at least: one existing `@WebMvcTest`, one existing `@DataJpaTest`, one existing service unit test - learn the project's package layout, fixture factory names (`createOrder(...)` vs Instancio), assertion library (kotest `shouldBe` vs JUnit `assertEquals` vs AssertJ), authentication helpers (`@WithMockUser` vs custom JWT processor), test framework (JUnit 5 plain vs Kotest FunSpec / BehaviorSpec)
- Read `application-test.properties` / `application-test.yml` and any `TestContainersConfig` / `IntegrationTestBase` / `AbstractIntegrationTest` base class
- Read `build.gradle.kts` test dependencies to confirm `kotlin("plugin.spring")` / `kotlin("plugin.jpa")`, MockK, springmockk, Kotest, Testcontainers, kotlinx-coroutines-test, Turbine

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 4 - Kotlin/Spring Test Pyramid

| Layer               | Spring annotation / type                                                            | What belongs here                                                                           |
| ------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Unit                | Plain JUnit 5 + MockK / Kotest FunSpec + MockK (no Spring context)                  | Service business logic, mappers, validators, pure functions, calculation rules              |
| Slice (integration) | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@JdbcTest`, `@WebFluxTest`             | Controller routing/binding/validation; repository queries; serialization contracts          |
| Full-context        | `@SpringBootTest` + Testcontainers                                                  | End-to-end controller -> service -> repository -> real DB; security filter chain; messaging |
| Contract            | Spring Cloud Contract / Pact (consumer-side)                                        | API consumer/provider contracts                                                             |
| E2E                 | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + WebTestClient / REST Assured      | Critical user journeys only - signup, checkout, payment                                     |

**Many** unit tests, **some** slice tests, **few** full-context / E2E tests.

### Step 5 - Apply Kotlin Test Patterns

Use skill: `kotlin-spring-test-integration` for Spring slice / Testcontainers patterns. Use skill: `kotlin-testing-patterns` for MockK, kotest, runTest, Turbine.

**Unit tests (`src/test/kotlin/.../service/`):**

- JUnit 5 (`@Test`, `@Nested`, `@DisplayName`) **or** Kotest (`FunSpec`, `BehaviorSpec`) - match project convention
- MockK for collaborator stubs (`mockk<T>()`); `clearAllMocks()` in `@AfterEach` or `afterEach`
- kotest matchers (`shouldBe`, `shouldThrow`, `shouldHaveSize`) preferred over JUnit `assertEquals`
- Test the public method - one test per outcome (success, validation failure, external failure, edge case)
- **No Spring context** - if `@SpringBootTest` is needed for a unit test, the test is misclassified or the class has too many collaborators
- For `suspend` functions: wrap test body in `runTest { }`; use `coEvery` / `coVerify` for stubs and verifications
- For `Flow<T>` consumers: use Turbine `flow.test { ... awaitItem() ... awaitComplete() }` to drive the cold flow
- Verify post-conditions via `verify { ... }` / `coVerify { ... }` on the relevant collaborator mock

**Controller slice tests (`@WebMvcTest`):**

- One test per `(method+path, role, outcome)` triple - covers routing, controller, request/response binding, validation, and `SecurityFilterChain` matchers
- Use `MockMvc` Kotlin DSL (`mockMvc.get("/api/orders/1").andExpect { status { isOk() } }`) or `WebTestClient` for reactive
- Authentication via `@WithMockUser`, `@WithUserDetails`, or `with(jwt().authorities(...))`
- Authorization: a separate test for "user without permission gets 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any data class with `@field:NotNull` / `@field:Size` constraints
- Response shape: assert key fields, status, headers, and `Content-Type` - not the full body
- Mock the service layer with `@MockkBean` (springmockk) - **NOT `@MockBean` / `@MockitoBean`** for Kotlin classes

**HTTP stubbing - choose by test type:**

| Test type                                                          | Right tool                                                                                              |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Unit test of a service that uses `WebClient` / `RestClient`        | MockK (`mockk<RestClient>()` and stub the call chain via `every { ... } returns ...`); fast and focused |
| `@WebMvcTest` of a controller whose service depends on an HTTP collaborator | `@MockkBean` the *service*, not the HTTP client; the controller doesn't see the client                  |
| `@SpringBootTest` covering the real `WebClient`/`RestClient` wiring | WireMock (with `@RegisterExtension` JUnit 5) - asserts retry, timeout, header propagation, error mapping behave correctly against a real HTTP transport |

Do not mix MockK on `WebClient` inside a `@SpringBootTest` - the framework will autowire its own bean and ignore the mock unless you replace it via `@MockkBean`. Do not bring in WireMock for unit tests - you lose the speed advantage and add server lifecycle complexity.

**Idempotency tests:**

State-mutating endpoints with `Idempotency-Key` semantics need a test that issues the *same* key twice and asserts (a) the same response body, (b) the operation ran exactly once (verify a single repository write or external-call invocation):

```kotlin
@Test
fun `same idempotency key returns cached result and does not double-execute`() = runTest {
    val key = "order-001"
    val req = createOrderRequest()

    val first = mockMvc.post("/api/orders") {
        header("Idempotency-Key", key); contentType = APPLICATION_JSON; content = json(req)
    }.andReturn().response.contentAsString

    val second = mockMvc.post("/api/orders") {
        header("Idempotency-Key", key); contentType = APPLICATION_JSON; content = json(req)
    }.andReturn().response.contentAsString

    second shouldBe first
    coVerify(exactly = 1) { paymentClient.charge(any()) }
}
```

**`@TransactionalEventListener` phase verification:**

Use `@RecordApplicationEvents` (Boot 3+) plus `ApplicationEvents` to assert the event was published; combine with explicit phase tests. For `AFTER_COMMIT` listeners, the listener must not run when the originating transaction rolls back - test both branches:

```kotlin
@SpringBootTest
@RecordApplicationEvents
class OrderEventTest {
    @Autowired lateinit var events: ApplicationEvents
    @MockkBean lateinit var emailSender: EmailSender

    @Test
    fun `OrderPlaced fires email only after commit`() {
        orderService.place(req)
        events.stream(OrderPlacedEvent::class.java).count() shouldBe 1
        verify(exactly = 1) { emailSender.sendConfirmation(any()) }
    }

    @Test
    fun `rolled-back transaction does not fire email`() {
        shouldThrow<InsufficientStockException> { orderService.place(failingReq) }
        verify(exactly = 0) { emailSender.sendConfirmation(any()) }
    }
}
```

**Async / coroutine + `@Transactional` rollback trap:**

A test that asserts rollback by checking `repository.findById(id)` may pass even when an `applicationScope.launch { ... }` started inside the transaction wrote to a *different* row in its own (separate) transaction. Two safeguards:

- Assert specifically the rows the system-under-test claims to have rolled back; don't infer rollback from absence of any side effect
- For background coroutines that should respect the originating transaction (`@Transactional` propagation requirements), use a synchronous test path or block on completion via `Awaitility` before asserting

**Repository slice tests (`@DataJpaTest`):**

- Use Testcontainers PostgreSQL via `@ServiceConnection` (Boot 3.1+) - `@DataJpaTest` defaults to H2, which diverges from PostgreSQL on JSONB, partial indexes, window functions, and `ON CONFLICT`. Pin to the production engine
- One test per derived query method or `@Query` - assert the result against fixture data inserted via the repository or `TestEntityManager`
- Native queries: must run against Testcontainers (H2 will not parse PostgreSQL syntax)
- N+1 detection: enable `spring.jpa.properties.hibernate.generate_statistics=true` in `application-test.yml`; assert `Statistics.getQueryExecutionCount()` for repository methods that load associations
- Test fixtures via factory functions with named parameters and defaults (Kotlin's natural builder)
- For `CoroutineCrudRepository` with R2DBC: wrap test body in `runTest { }`

**Coroutine tests:**

- `runTest { }` for all `suspend` test bodies - controls virtual time, prevents flakiness; never `runBlocking`
- `coEvery` / `coVerify` for `suspend` function mocks - regular `every` / `verify` silently fail
- `withTimeout(...)` inside `runTest` exercises timeout behavior in virtual time
- Turbine for `Flow` assertions: `flow.test { awaitItem() shouldBe expected; awaitComplete() }`
- For testing structured concurrency (`coroutineScope { ... }`) failures, assert the parent scope rethrows

**Security slice (`@WebMvcTest` + Spring Security Test):**

- One test per `(endpoint, principal-state, outcome)` triple
- Anonymous: assert 401 for protected endpoints
- Authenticated without role: assert 403 for role-gated endpoints
- Authenticated with role: assert 200 plus expected payload
- CSRF: for `@WebMvcTest`, requests need `with(csrf())` for state-changing methods - this is a feature, not a workaround

**Full-context / Testcontainers (`@SpringBootTest`):**

- Reserve for tests that genuinely need the full context: end-to-end auth flows, transactional outbox, message-driven listeners, scheduled jobs
- Use `@Testcontainers` + `companion object { @Container @JvmStatic val pg = PostgreSQLContainer(...) }` with `@DynamicPropertySource` (or `@ServiceConnection`)
- Use `@Sql` for fixture data; reset state between tests via `@Transactional` rollback
- Avoid `@DirtiesContext`

**Contract tests:**

- Spring Cloud Contract: contracts in `src/test/resources/contracts/`; provider verifies via generated tests; consumer pulls stubs via stub runner
- Pact: pact files committed to a broker; provider verification runs as a separate test class

### Step 6 - Test Boundaries (Kotlin-Specific)

**What deserves a unit test:**

- Service logic, mappers / extension functions (`Order.toResponse()`), validators, custom `@ConfigurationProperties` validation
- Domain rules, calculation, state-machine transitions, sealed-class result hierarchies
- Spring-independent helpers / utilities, top-level extension functions

**What deserves a slice test:**

- Every controller endpoint (`@WebMvcTest`): happy path + 401/403 + 4xx validation
- Every custom repository query (`@DataJpaTest` + Testcontainers): query result correctness
- Serialization contracts (`@JsonTest`): `data class` <-> JSON round trip when serialization shape is part of the API
- Security configuration (`@WebMvcTest`): role-based access, CSRF handling, JWT decoding

**What deserves a full-context test:**

- Cross-component flows that traverse controller -> service -> repository -> external (Kafka / S3 / mail)
- Auth flows end-to-end (login -> token issuance -> protected resource access)
- Transactional outbox / message-driven listeners / `CoroutineScope.launch` background work
- Scheduled jobs (`@Scheduled`) verified via Awaitility and a real clock

**What does NOT need a test:**

- Spring-provided behavior: `@Autowired` injection, `@RequestMapping` route resolution, default Jackson serialization
- Generated boilerplate: `data class` `toString` / `equals`, MapStruct identity mappings, kotlin-jpa-generated no-arg constructors
- Trivial delegation: `service.findById(id) -> repository.findById(id)` with no logic

### Step 7 - Test Data and Fixtures

- Prefer factory functions with named parameters and defaults over builders (Kotlin natural):

  ```kotlin
  fun createOrder(
      id: Long = 0L,
      userId: Long = 42L,
      status: OrderStatus = OrderStatus.PENDING,
      total: BigDecimal = BigDecimal("99.99"),
  ) = Order(id = id, userId = userId, status = status, total = total)
  ```

- For repository tests with Testcontainers, use `@Sql("/fixtures/orders.sql")` for shared setup; isolate per-test data inside the test
- `data class` DTOs: instantiate directly via constructor - no factories needed for trivial cases
- **Avoid `flush + clear` patterns** unless specifically asserting first-level cache behavior
- Test data must be minimal and focused

### Step 8 - Prioritization (when coverage is low)

If line coverage is below ~50%, **run this step before scaffolding** (i.e., before producing Step 5 patterns).

When starting from low test coverage, prioritize by Kotlin/Spring-specific risk:

**Priority 1 - Authorization and authentication:**

- `@WebMvcTest` per protected endpoint asserting 401 / 403 with `@WithMockUser` and unauthenticated cases
- OAuth2 / JWT flow tests covering issuer, audience, signature, expiry validation
- Method security: `@PreAuthorize` expressions tested at the service layer
- For `suspend` services using `ReactiveSecurityContextHolder`: explicit principal-propagation tests

**Priority 2 - Data integrity:**

- `@DataJpaTest` for every repository with custom `@Query` or derived methods that touch business-critical tables
- Service tests for write operations (one happy path + one rollback per write)
- Transactional outbox / message dispatch idempotency
- Coroutine cancellation paths (cleanup runs in `finally`, no resource leak)

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (sealed-class result hierarchies)
- Scheduled jobs touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through controllers, simple CRUD - lower risk, can wait

### Step 9 - Test Infrastructure Hygiene

- [ ] Testcontainers reused across tests via `@ServiceConnection` + reusable mode (`testcontainers.reuse.enable=true` in `~/.testcontainers.properties`) for local fast cycles
- [ ] `@SpringBootTest` count kept low; use `@MockkBean` sparingly (each unique mock set forces a new context cache entry)
- [ ] Test profile (`@ActiveProfiles("test")`) overrides only what differs from prod - never silently disables security
- [ ] JUnit 5 parallel execution enabled where safe (`junit.jupiter.execution.parallel.enabled=true`)
- [ ] MockK strict mode (default in newer versions) - flags missing stubs as test smells
- [ ] WireMock or Testcontainers for HTTP stubs; never real network calls
- [ ] `clearAllMocks()` in `@AfterEach` / Kotest `afterEach` to prevent stale stubs causing intermittent failures
- [ ] **`mockito-core` excluded** from `spring-boot-starter-test` when using springmockk - the test runtime should not have both
- [ ] Coverage tool (JaCoCo or Kover) wired to CI with per-module thresholds; coverage reports excluded from production JAR

## Kotlin Test Review Checklist

Quick-reference checklist for reviewing existing Kotlin tests:

- [ ] Test type matches what is being tested (controller -> `@WebMvcTest`, repository -> `@DataJpaTest`, service -> plain JUnit / Kotest + MockK)
- [ ] Every controller endpoint has a slice test with at least happy + 401 + 403 + validation-error
- [ ] Every custom `@Query` and derived repository method has a slice test against Testcontainers (not H2)
- [ ] Every `@PreAuthorize` expression has a passing-and-denied test
- [ ] Test data created via factory functions with named parameters, not JSON fixtures or `new` calls
- [ ] No `verify { repository.save(any()) }` patterns when the test could have asserted DB state via `@DataJpaTest`
- [ ] No `@SpringBootTest` for tests that could run as `@WebMvcTest` or unit
- [ ] No `@DirtiesContext` unless the test specifically mutates singleton state
- [ ] **No `@MockBean` / `@MockitoBean`** for Kotlin classes - use `@MockkBean`
- [ ] **No `every` / `verify`** for `suspend` functions - use `coEvery` / `coVerify`
- [ ] **No `runBlocking`** in test bodies - use `runTest`
- [ ] **No Mockito** for Kotlin class mocks - use MockK (works on final classes by default)

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% -> Strategy Doc (optionally include Coverage Assessment)
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Kotlin / Spring Boot Test Coverage Assessment

**Stack:** Kotlin <version> / Spring Boot <version>
**Test framework:** JUnit 5 / Kotest, MockK + springmockk, kotlinx-coroutines-test, Spring Boot Test, Testcontainers
**Coverage gaps:**

- **Unit tests:** [services / mappers without test coverage]
- **Controller slice tests (@WebMvcTest):** [controllers without tests; controllers missing 401/403 paths]
- **Repository slice tests (@DataJpaTest):** [repositories with @Query / derived methods without tests; repositories tested only against H2]
- **Security tests:** [endpoints without authorization tests; missing JWT/OAuth2 flow tests]
- **Coroutine tests:** [suspend services without `runTest`; `Flow` consumers without Turbine]
- **Full-context tests:** [transactional flows, listeners, scheduled jobs without coverage]
- **Contract tests:** [provider/consumer contracts without verification]

**Recommended pyramid balance:**

- Unit (services, mappers, helpers): [count target]
- Slice (@WebMvcTest, @DataJpaTest, @JsonTest): [count target]
- Full-context (@SpringBootTest + Testcontainers): [count target - keep small]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run Kotlin test files using project conventions. Each scaffold must include:

- The right test type (`@WebMvcTest`, `@DataJpaTest`, `@SpringBootTest`, or plain JUnit / Kotest + MockK)
- Factory functions with named-parameter defaults instead of `Order(...)` / `OrderRequest(...)` calls scattered through tests
- `@MockkBean` (NOT `@MockBean`); `coEvery` / `coVerify` for `suspend`; `runTest { }` for coroutine bodies; Turbine for `Flow`
- For controller tests: happy path + 401 + 403 + validation-error
- For repository tests: Testcontainers via `@ServiceConnection`; assertions against PostgreSQL semantics
- For security tests: `@WithMockUser`, `with(jwt())`, or anonymous; positive and denied cases
- Inline comments explaining non-obvious setup (e.g., why `with(csrf())` is required, why `coEvery` not `every`)

**Strategy Doc** (when designing a test strategy):

```markdown
## Kotlin / Spring Boot Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Slice (@WebMvcTest, @DataJpaTest) {y}% / Full-context {z}%
**Tooling:** JUnit 5 / Kotest, MockK + springmockk (`@MockkBean`), kotlinx-coroutines-test (`runTest`), Turbine (Flow), AssertJ / kotest matchers, Spring Boot Test, Testcontainers (PostgreSQL / Kafka), Spring Security Test
**Database isolation:** Testcontainers PostgreSQL via `@ServiceConnection` + transactional rollback
**Concurrency:** [JUnit parallel execution config]
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness or coroutine cancellation paths]
2. [...]
```

## Self-Check

- [ ] `behavioral-principles` loaded as Step 1 before stack detection or any other delegation
- [ ] Stack confirmed as Kotlin / Spring Boot before any specific guidance applied (Step 2)
- [ ] Code under test and a representative sample of existing tests read directly so scaffolds match project conventions (Step 3)
- [ ] `kotlin-spring-test-integration` and `kotlin-testing-patterns` consulted for canonical patterns
- [ ] Test pyramid mapped to Kotlin/Spring slice annotations (unit -> plain JUnit / Kotest + MockK; slice -> `@WebMvcTest` / `@DataJpaTest` / `@JsonTest`; full-context -> `@SpringBootTest` + Testcontainers)
- [ ] Boundaries clearly defined: each spec layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - authorization, repository correctness, and coroutine cancellation first
- [ ] Test data guidance includes factory functions with named-parameter defaults; immutable `data class` preferred
- [ ] Testcontainers used for repository and full-context tests; H2 flagged as a smell for production-Postgres apps
- [ ] Security testing approach explicit (`@WithMockUser`, `with(jwt())`, anonymous case)
- [ ] Coroutine testing explicit: `runTest`, `coEvery`/`coVerify`, Turbine for `Flow`; `runBlocking` flagged in test bodies
- [ ] MockK + springmockk discipline: `@MockkBean` not `@MockBean`; `mockito-core` excluded from spring-boot-starter-test
- [ ] Test scaffolds (if generated) include happy path + 401 + 403 + validation-error; idempotency for jobs / listeners; per-role tests for method security
- [ ] Spec-aware mode honored when `--spec` was passed
- [ ] Review checklist items addressed when reviewing existing tests

## Avoid

- Scaffolding tests without first reading existing tests in the project
- Chasing a coverage number instead of prioritizing by risk
- `@SpringBootTest` for tests that could run as `@WebMvcTest` or plain unit
- H2 in `@DataJpaTest` for apps that use PostgreSQL features (JSONB, partial indexes, `ON CONFLICT`, window functions)
- Writing controller tests with `@SpringBootTest` instead of `@WebMvcTest`
- Duplicating test data factories per test class - share factory functions in a `TestFixtures.kt` file
- Using `verify { repository.save(any()) }` when a `@DataJpaTest` could assert actual persistence
- Skipping CSRF (`with(csrf())`) by disabling CSRF in tests
- Skipping `@PreAuthorize` tests because the controller has a `@WebMvcTest` - method security is unit-tested separately
- Testing Spring internals (e.g., that `@Autowired` works)
- `@DirtiesContext` as a workaround for shared state - fix the test isolation instead
- Mockito for Kotlin classes - use MockK (works on final classes by default)
- `@MockBean` / `@MockitoBean` for Kotlin classes - use `@MockkBean`
- `every` / `verify` for `suspend` functions - use `coEvery` / `coVerify`
- `runBlocking` in test bodies - use `runTest` for virtual time
- Forgetting `clearAllMocks()` cleanup - causes intermittent failures from stale stubs
