---
name: task-kotlin-test
description: Kotlin / Spring Boot test scaffolding: JUnit 5, Kotest, MockK + @MockkBean, test slices, Testcontainers, runTest, Turbine for Flow.
agent: kotlin-test-engineer
metadata:
  category: backend
  tags: [kotlin, spring-boot, junit, kotest, mockk, testcontainers, coroutines, testing, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` is passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Step 1 and Step 2. Generate one test per AC (`Satisfies: AC<N>` in test names), cover every NFR via a `plan.md` verification step, refuse to test out-of-scope behavior. Never edit `spec.md`, `plan.md`, `tasks.md`; surface coverage gaps as proposed amendments.

# Kotlin / Spring Boot Test

## Purpose

Test strategy and scaffolding using JUnit 5 / Kotest, MockK + springmockk (`@MockkBean`), Spring test slices, Testcontainers, `runTest` for coroutines, Turbine for `Flow`. The stack-specific delegate of `task-code-test`.

## When to Use

- Designing a test strategy for a new Kotlin / Spring service or module
- Assessing test coverage gaps (unit / slice / full-context / contract)
- Scaffolding tests for under-covered controllers / services / repositories / security / coroutine paths
- Reviewing test pyramid balance
- Adding boundary tests to happy-path-only coverage

**Not for:** test failure debugging (`task-kotlin-debug`), general review (`task-code-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Behavioral principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm stack

Use skill: `stack-detect`. Accept pre-confirmed from parent.

### Step 3 - Read code + existing tests

Before strategy or scaffolds:

- Read target classes top-to-bottom: public methods, request/response types, security annotations, transaction boundaries, external collaborators, `suspend` modifiers
- Glob `src/test/kotlin/**/*Test*.kt` and `**/*Spec*.kt`. Read at least one existing `@WebMvcTest`, `@DataJpaTest`, and service unit test - learn package layout, fixture-factory names (`createOrder(...)` vs Instancio), assertion library (kotest `shouldBe` vs JUnit `assertEquals`), auth helpers (`@WithMockUser` vs custom JWT), test framework (JUnit 5 plain vs Kotest FunSpec / BehaviorSpec)
- Read `application-test.yml` and any `TestContainersConfig` / `AbstractIntegrationTest` base
- Read `build.gradle.kts` test deps: `kotlin-spring` / `kotlin-jpa`, MockK, springmockk, Kotest, Testcontainers, `kotlinx-coroutines-test`, Turbine

If no existing tests, propose conventions explicitly rather than inventing silently.

### Step 4 - Test pyramid

| Layer               | Slice                                                                            | What belongs                                                                  |
| ------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------- |
| Unit                | Plain JUnit 5 / Kotest + MockK                                                   | Service logic, mappers, validators, pure functions                            |
| Slice               | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@JdbcTest`                          | Controller routing/binding/validation; repository queries; serialization      |
| Full-context        | `@SpringBootTest` + Testcontainers                                               | E2E controller → service → repository → DB; security chain; messaging         |
| Contract            | Spring Cloud Contract / Pact                                                     | API consumer/provider contracts                                               |
| E2E                 | `@SpringBootTest(RANDOM_PORT)` + WebTestClient / REST Assured                    | Critical user journeys only                                                    |

Many unit, some slice, few full-context / E2E.

### Step 5 - Apply patterns

Use skill: `kotlin-testing-patterns` for MockK / `coEvery` / `coVerify` / Kotest / `runTest` / Turbine / fixture factories / mocking extension functions.
Use skill: `kotlin-spring-test-integration` for slice annotations / `@MockkBean` / Testcontainers / `@ServiceConnection` / WireMock / Awaitility / slice rollback differences.

**Strategy-side rules** the workflow enforces (the *what*; *how* lives in the atomic skills):

- Unit tests have no Spring context. If `@SpringBootTest` seems necessary, the class has too many collaborators or the test is misclassified.
- Controller slice tests cover `(method+path, role, outcome)` per test; mock services with `@MockkBean`.
- Authorization has its own denied-case test per protected endpoint.
- Validation has a rejects-invalid-payload test for every `@field:`-annotated DTO.
- Response shape: key fields + status + Content-Type, not the full body.

**HTTP stubbing:**

| Test type                                        | Tool                                                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------------- |
| Service unit test with `WebClient` / `RestClient` | `mockk<RestClient>()` - fast and focused                                              |
| `@WebMvcTest` with HTTP-collaborator service     | `@MockkBean` the **service**; controller never sees the client                        |
| `@SpringBootTest` with real `WebClient` wiring   | WireMock (`@RegisterExtension`) - asserts retry, timeout, header propagation          |

Don't mix MockK on `WebClient` inside `@SpringBootTest`; don't pull in WireMock for unit tests.

**Idempotency:**

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

**`@TransactionalEventListener` phases:**

`@RecordApplicationEvents` + `ApplicationEvents`. For `AFTER_COMMIT`, test both branches - listener does not run on rollback:

```kotlin
@SpringBootTest @RecordApplicationEvents
class OrderEventTest {
    @Autowired lateinit var events: ApplicationEvents
    @MockkBean lateinit var emailSender: EmailSender

    @Test fun `OrderPlaced fires only after commit`() {
        orderService.place(req)
        events.stream(OrderPlacedEvent::class.java).count() shouldBe 1
        verify(exactly = 1) { emailSender.sendConfirmation(any()) }
    }

    @Test fun `rolled-back tx does not fire`() {
        shouldThrow<InsufficientStockException> { orderService.place(failingReq) }
        verify(exactly = 0) { emailSender.sendConfirmation(any()) }
    }
}
```

**Coroutine + `@Transactional` rollback trap:** asserting rollback via `repository.findById(id)` can pass even when an `applicationScope.launch { ... }` started inside the TX wrote to a different row in its own (separate) transaction. Safeguards: assert specifically the rows the SUT claims to have rolled back; for background coroutines that must respect the originating TX, use a synchronous test path or block on completion via Awaitility before asserting.

**Repository slices (`@DataJpaTest`):**

- Testcontainers PostgreSQL via `@ServiceConnection` (`@DataJpaTest` defaults to H2 which diverges on JSONB, partial indexes, window functions, `ON CONFLICT`)
- One test per derived method or `@Query`
- Native queries must run against Testcontainers
- N+1 detection via `spring.jpa.properties.hibernate.generate_statistics=true`; assert `Statistics.getQueryExecutionCount()`
- Factory functions with named parameters
- `CoroutineCrudRepository` + R2DBC: wrap test body in `runTest { }`

**Coroutine tests:**

- `runTest { }` for `suspend` test bodies - virtual time, no flakes
- `coEvery` / `coVerify` for suspend mocks
- `withTimeout(...)` inside `runTest` exercises timeout in virtual time
- Turbine: `flow.test { awaitItem() shouldBe expected; awaitComplete() }`
- For structured-concurrency failure testing, assert the parent scope rethrows

**Security slice (`@WebMvcTest` + Spring Security Test):**

- One test per `(endpoint, principal-state, outcome)` triple
- Anonymous → 401; authenticated without role → 403; with role → 200
- CSRF: `with(csrf())` for state-changing methods - feature, not workaround

**Full-context (`@SpringBootTest`):** reserve for genuinely needs-full-context tests - E2E auth flows, transactional outbox, listeners, scheduled jobs.

### Step 6 - Test boundaries

**Unit:** service logic, mappers / extension functions, validators, custom `@ConfigurationProperties` validation, domain rules, state-machine transitions.

**Slice:** every controller endpoint (`@WebMvcTest`: happy + 401/403 + 4xx); every custom repository query (`@DataJpaTest` + Testcontainers); serialization contracts (`@JsonTest`); security config role-based access.

**Full-context:** cross-component flows through controller → service → repository → external; auth flows end-to-end; transactional outbox / message listeners / scheduled jobs.

**Does NOT need a test:** Spring-provided behavior (`@Autowired`, route resolution, default Jackson); generated boilerplate (`data class` `toString` / `equals`, kotlin-jpa no-arg); trivial delegation.

### Step 7 - Test data

`kotlin-testing-patterns` § Factory factories has the canonical pattern. Rules:

- Share factories across slice + full-context tests
- `@Sql("/fixtures/orders.sql")` for shared seed data; per-test data inline
- Trivial DTOs: constructor calls directly
- Avoid `flush + clear` unless asserting first-level cache behavior

### Step 8 - Prioritize (when coverage < 50%)

Run before scaffolding.

1. **Authorization / auth**: `@WebMvcTest` per protected endpoint asserting 401 / 403; OAuth2 / JWT validation; method-security `@PreAuthorize`; principal propagation in `suspend`
2. **Data integrity**: `@DataJpaTest` for every repository with custom `@Query`; write-operation tests (happy + rollback); outbox idempotency; coroutine cancellation cleanup
3. **Business-critical**: revenue paths; state transitions; scheduled jobs
4. **High-churn**: files with frequent commits or bug-fix history
5. **Plumbing**: pass-through controllers, simple CRUD

### Step 9 - Infrastructure hygiene

- [ ] Testcontainers reused via `@ServiceConnection` + reusable mode (`testcontainers.reuse.enable=true` in `~/.testcontainers.properties`) locally
- [ ] `@SpringBootTest` count low; `@MockkBean` sparingly (each unique set forces a new context cache entry)
- [ ] `@ActiveProfiles("test")` explicit; profile doesn't silently disable security
- [ ] JUnit 5 parallel execution where safe
- [ ] MockK strict mode
- [ ] No real network calls - WireMock or Testcontainers
- [ ] `clearAllMocks()` in `@AfterEach` / Kotest `afterEach`
- [ ] **`mockito-core` excluded** from `spring-boot-starter-test` when using springmockk
- [ ] JaCoCo / Kover wired to CI with per-module thresholds; coverage reports excluded from production JAR

## Test Review Checklist

- [ ] Test type matches what's tested (controller → `@WebMvcTest`, repository → `@DataJpaTest`, service → JUnit / Kotest + MockK)
- [ ] Every controller endpoint has happy + 401 + 403 + validation-error
- [ ] Every custom `@Query` + derived method against Testcontainers (not H2)
- [ ] Every `@PreAuthorize` has passing + denied test
- [ ] Test data via factory functions, not JSON fixtures or `new`
- [ ] No `verify { repository.save(any()) }` when `@DataJpaTest` could assert DB state
- [ ] No `@SpringBootTest` for tests that could run as `@WebMvcTest` or unit
- [ ] No `@DirtiesContext` unless mutating singleton state
- [ ] No `@MockBean` / `@MockitoBean` for Kotlin classes
- [ ] No `every` / `verify` for `suspend`
- [ ] No `runBlocking` in test bodies
- [ ] No Mockito for Kotlin class mocks

## Output Format

- User asks "what tests are missing?" → **Coverage Assessment**
- "Write tests for X" / "scaffold tests" → **Test Scaffolds**
- "Test strategy" / "test plan" / coverage < 50% → **Strategy Doc** (optionally include Coverage Assessment)
- Unclear → Strategy Doc

**Coverage Assessment:**

```markdown
## Kotlin / Spring Boot Test Coverage Assessment

**Stack:** Kotlin <version> / Spring Boot <version>
**Test framework:** JUnit 5 / Kotest, MockK + springmockk, kotlinx-coroutines-test, Spring Boot Test, Testcontainers
**Gaps:**
- **Unit:** [services / mappers without tests]
- **Controller slice (@WebMvcTest):** [missing controllers / 401/403 paths]
- **Repository slice (@DataJpaTest):** [missing @Query / derived methods; H2-only tests]
- **Security:** [endpoints without authz tests; missing JWT/OAuth2 flow tests]
- **Coroutine:** [suspend services without runTest; Flow consumers without Turbine]
- **Full-context:** [transactional flows / listeners / scheduled jobs without coverage]
- **Contract:** [provider/consumer contracts without verification]

**Recommended pyramid balance:**
- Unit: [count target]
- Slice: [count target]
- Full-context: [count target - keep small]
```

**Test Scaffolds** (when generating boilerplate):

- Right test type (slice or unit)
- Factory functions with named-parameter defaults
- `@MockkBean`, `coEvery`/`coVerify`, `runTest { }`, Turbine for Flow
- Controller: happy + 401 + 403 + validation-error
- Repository: Testcontainers via `@ServiceConnection`
- Security: `@WithMockUser` / `with(jwt())` / anonymous; positive + denied
- Inline comments only for non-obvious setup (e.g., why `with(csrf())` is required)

**Strategy Doc:**

```markdown
## Kotlin / Spring Boot Test Strategy

**Objective:** [what]
**Pyramid balance:** Unit {x}% / Slice {y}% / Full-context {z}%
**Tooling:** JUnit 5 / Kotest, MockK + springmockk, kotlinx-coroutines-test, Turbine, kotest matchers / AssertJ, Spring Boot Test, Testcontainers (Postgres / Kafka), Spring Security Test
**Database isolation:** Testcontainers PostgreSQL via `@ServiceConnection` + transactional rollback
**Concurrency:** [JUnit parallel config]
**Gaps to close (prioritized):**
1. [Highest-risk gap]
2. ...
```

## Self-Check

- [ ] `behavioral-principles` loaded
- [ ] Stack confirmed
- [ ] Code + existing tests read so scaffolds match project conventions
- [ ] `kotlin-spring-test-integration` + `kotlin-testing-patterns` consulted
- [ ] Pyramid mapped to slice annotations
- [ ] No duplicated assertions across layers
- [ ] Prioritization by risk when coverage low
- [ ] Factory functions used; no per-test-class duplication
- [ ] Testcontainers for repository / full-context; H2 flagged
- [ ] Security testing explicit
- [ ] Coroutine testing explicit: `runTest`, `coEvery`/`coVerify`, Turbine; `runBlocking` flagged
- [ ] MockK + springmockk discipline; `mockito-core` excluded
- [ ] Scaffolds include happy + 401 + 403 + validation-error
- [ ] Spec-aware mode honored when applicable
- [ ] Review checklist items addressed when reviewing existing tests

## Avoid

- Scaffolding tests without reading existing tests
- Chasing a coverage number instead of risk
- `@SpringBootTest` when a slice works
- H2 for Postgres-feature apps
- Controller tests with `@SpringBootTest`
- Duplicating test data factories per test class
- `verify { repository.save(any()) }` when `@DataJpaTest` could assert persistence
- Skipping `with(csrf())` by disabling CSRF
- Skipping `@PreAuthorize` tests
- Testing Spring internals
- `@DirtiesContext` as a workaround for shared state
- Mockito / `@MockBean` for Kotlin classes
- `every` / `verify` for `suspend`
- `runBlocking` in test bodies
- Forgetting `clearAllMocks()`
