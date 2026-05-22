---
name: task-spring-test
description: "Spring Boot test plan and scaffolding: JUnit 5, @WebMvcTest, @DataJpaTest, Testcontainers, Mockito, Spring Security Test."
agent: java-test-engineer
metadata:
  category: backend
  tags: [java, spring-boot, junit, testcontainers, mockito, testing, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` after `behavioral-principles`. Generate one test per AC (use `Satisfies: AC<N>` in test names), cover every NFR with a verification step from `plan.md`, refuse tests for behavior the spec marks out-of-scope. Never edit `spec.md` / `plan.md` / `tasks.md`; surface gaps as proposed amendments.

# Spring Boot Test

Spring-aware test strategy and scaffolding using JUnit 5, slices (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`), Testcontainers, Mockito, AssertJ, Spring Security Test, and the Spring test pyramid.

Stack-specific delegate of `task-code-test` for Java / Spring Boot.

## When to Use

- Designing a test strategy for a new service / module
- Assessing coverage gaps across unit / slice / full-context / contract
- Scaffolding tests for under-covered controllers, services, repositories, security configs
- Reviewing test-pyramid balance
- Adding boundary tests to happy-path-only coverage

**Not for:**
- Test failure debugging (`task-spring-debug`)
- General code review (`task-code-review`)
- Incident postmortems (`/task-oncall-postmortem`)

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack from a parent. If not Spring Boot, stop and tell the user to invoke `/task-code-test`.

### Step 3 - Read the Code Under Test and Existing Tests

Output grounded in real conventions, not generic templates.

- Read each target class top-to-bottom: public methods, request/response types, security annotations, transaction boundaries, external collaborators
- Read at least one existing `@WebMvcTest`, one `@DataJpaTest`, one service unit test - learn the project's builders (`OrderTestData.builder()` vs Instancio vs `@RecordBuilder`), assertion library (AssertJ vs Hamcrest), auth helpers (`@WithMockUser` vs custom `JwtRequestPostProcessor`)
- Read `application-test.properties` / `application-test.yml` and any `TestContainersConfig` / `IntegrationTestBase` / `AbstractIntegrationTest` base class - reuse the project's container setup
- Read `build.gradle(.kts)` / `pom.xml` test deps to confirm Testcontainers, Instancio, AssertJ, Spring Cloud Contract, REST Assured presence

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc.

### Step 4 - Spring Test Pyramid

| Layer               | Spring annotation / type                                                  | What belongs                                                                                |
| ------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Unit                | Plain JUnit 5 + Mockito (no Spring context)                               | Service logic, mappers, validators, pure functions, calculation rules                       |
| Slice (integration) | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@JdbcTest`, `@WebFluxTest`   | Controller routing/binding/validation; repository queries; serialization contracts          |
| Full-context        | `@SpringBootTest` + Testcontainers                                        | End-to-end controller → service → repository → real DB; security chain; messaging           |
| Contract            | Spring Cloud Contract / Pact                                              | API consumer/provider contracts                                                             |
| E2E                 | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + REST Assured            | Critical user journeys only - signup, checkout, payment                                     |

Many unit tests, some slices, few full-context / E2E. `@SpringBootTest` is slow - use sparingly.

### Step 5 - Apply Spring Test Patterns

Use skill: `spring-test-integration` for the canonical patterns. Compose as scope demands - load the patterns once and reference rather than restate:

- Auth tests (`@WithMockUser`, `jwt()` post-processor, method security) → `spring-security-patterns`
- `@Async` / `@Scheduled` / event listener tests → `spring-async-processing`
- Kafka / Rabbit / outbox / listener idempotency → `spring-messaging-patterns`
- N+1 detection in `@DataJpaTest` (`Statistics.getQueryExecutionCount()`), fetch-graph correctness → `spring-jpa-performance`
- `@TransactionalEventListener` phase assertions, `REQUIRES_NEW`, `@RecordApplicationEvents` → `spring-transaction`
- `@RestControllerAdvice` / ProblemDetail assertions → `spring-exception-handling`

**Unit tests:** JUnit 5 + Mockito + AssertJ, no Spring context. One test per outcome. Stub HTTP via Mockito on the client interface. Use `ArgumentCaptor<DomainEvent>` on `ApplicationEventPublisher` for richer assertions than `verify(...)`.

**HTTP stubbing by test type:**

| Test type             | Stub HTTP via                                                                                          |
| --------------------- | ------------------------------------------------------------------------------------------------------ |
| Plain unit            | Mockito on the client interface                                                                        |
| `@SpringBootTest`     | WireMock (`@WireMockTest` in spring-boot-test 3.2+, or `WireMockExtension`) - exercises real `RestClient` / `WebClient` config (timeouts, retries, deserialization) |
| `@WebMvcTest`         | Downstream client mocked via `@MockitoBean` - this slice does not exercise outbound calls              |

Mocking `RestClient` itself in an integration test bypasses the wiring the test exists to verify.

**Idempotency tests:** when the code accepts an idempotency key (payment, webhook, message handler), test that invoking twice with the same key short-circuits the second call - no second DB write, no second outbound HTTP. Pair `verify(gateway, times(1))` with a row-count assertion.

**Controller slices (`@WebMvcTest`):**

- One test per `(method+path, role, outcome)` triple
- Auth via `@WithMockUser` / `@WithUserDetails` / `SecurityMockMvcRequestPostProcessors`
- Authorization: separate test for "user without permission gets 403" per protected endpoint
- Validation: "rejects invalid payload" test for any `@Valid` DTO
- Response shape: assert key fields, status, headers, content-type - not the full body
- Mock the service layer with `@MockitoBean`

**Repository slices (`@DataJpaTest`):**

- Testcontainers Postgres via `@ServiceConnection` - `@DataJpaTest` defaults to H2 which diverges from Postgres on JSONB, partial indexes, window functions, `ON CONFLICT`
- One test per derived query / `@Query` - assert SQL behavior, not just that the method returns something
- Native queries must run against Testcontainers (H2 won't parse Postgres syntax)
- N+1 detection: `spring.jpa.properties.hibernate.generate_statistics=true` in `application-test.properties`; assert `Statistics.getQueryExecutionCount()`

**Security slices:**

- One test per `(endpoint, principal-state, outcome)` triple
- Anonymous: assert 401 on protected
- Authenticated without role: assert 403 on role-gated
- Authenticated with role: assert 200 plus expected payload
- CSRF: `@WebMvcTest` state-changing methods need `.with(csrf())`

**Full-context (`@SpringBootTest`):**

- Reserve for tests that need the full context: end-to-end auth, transactional outbox, message-driven listeners, scheduled jobs
- `@Container static PostgreSQLContainer<?> pg = ...` with `@DynamicPropertySource` or `@ServiceConnection`
- `@Sql` for fixtures; clean between tests via `@Transactional` rollback or explicit cleanup
- Avoid `@DirtiesContext` - it flushes the cached context
- **`@Transactional` on the test class auto-rolls back, but spawned threads do not see uncommitted data.** Tests triggering `@Async`, `@Scheduled`, or `TaskExecutor.submit` fail inside the async thread (often silently). For async paths, drop `@Transactional` and clean up via `@Sql(executionPhase = AFTER_TEST_METHOD)` or explicit teardown
- **`@TransactionalEventListener` phase**: use `@RecordApplicationEvents` (Boot 3+) with `ApplicationEvents` to assert *what* was published *and when*. Mocking `ApplicationEventPublisher` cannot distinguish `BEFORE_COMMIT` from `AFTER_COMMIT`

**Contract tests:**

- Spring Cloud Contract: contracts in `src/test/resources/contracts/`; provider verifies via generated tests; consumer pulls stubs
- Pact: pact files in a broker; provider verification as a separate test class

### Step 6 - Test Boundaries

**Unit test:** service logic, mappers (especially MapStruct), validators, `@ConfigurationProperties` validation, domain rules, calculations, state-machine transitions, Spring-independent helpers.

**Slice test:** every controller endpoint (happy + 401/403 + 4xx); every custom repository query; serialization contracts (`@JsonTest`) when the shape is part of the API; security configuration.

**Full-context:** cross-component flows (controller → service → repo → external); auth flows end-to-end; transactional outbox / message-driven listeners; scheduled jobs via Awaitility and a real clock.

**No test needed:**

- Spring-provided behavior (`@Autowired`, route resolution, default Jackson) - test your wiring via slices, not the framework
- Generated boilerplate (Lombok getters/setters, MapStruct identity mappings)
- Trivial delegation (`service.findById(id) -> repository.findById(id)` with no logic)

### Step 7 - Test Data and Fixtures

- Constructor / builder factories (Instancio, Easy Random, `OrderTestData.builder()`) over JSON fixtures
- Repository tests: `@Sql("/fixtures/orders.sql")` for shared setup; per-test data isolated in the test
- Records / immutable DTOs: instantiate directly via constructor for trivial cases
- Avoid `flush + clear` unless the test asserts first-level-cache behavior
- Minimal, focused data - `IntStream.range(0, 100)` setups belong in integration / load-test layer

### Step 8 - Prioritization (when coverage is low)

If line coverage (or equivalent signal) is below ~50%, run this step before scaffolding - it determines _which_ tests first. Alphabetical / by-file scaffolding misses authorization holes while plumbing gets full coverage.

**P1 - Auth:** `@WebMvcTest` per protected endpoint asserting 401 / 403 with `@WithMockUser` + unauthenticated; OAuth2 / JWT issuer/audience/signature/expiry; method security `@PreAuthorize` at the service layer.

**P2 - Data integrity:** `@DataJpaTest` for every repository with `@Query` / derived methods on business-critical tables; service tests for write operations (one happy path + one rollback); transactional outbox / message dispatch idempotency.

**P3 - Business-critical flows:** revenue paths (checkout, billing, subscription transitions), state-machine transitions, scheduled jobs touching billing / notifications.

**P4 - High-churn code:** files with frequent recent commits (`git log --since="3 months ago"`); files with bug-fix history (`git log --grep="fix"`).

**P5 - Plumbing:** pass-through controllers, simple CRUD.

### Step 9 - Test Infrastructure Hygiene

- [ ] Testcontainers reused via `@ServiceConnection` + reusable mode (`testcontainers.reuse.enable=true` in `~/.testcontainers.properties`) for local cycles
- [ ] `@SpringBootTest` count low; `@MockitoBean` / `@MockBean` sparingly (each unique mock set forces a new context cache entry)
- [ ] Test profile overrides only what differs from prod - never silently disables security
- [ ] JUnit 5 parallel execution where safe; per-class isolation for stateful tests
- [ ] Mockito strict stubbing (default in 4+) - flags unused stubs
- [ ] WireMock or Testcontainers for HTTP stubs; never real network calls
- [ ] JaCoCo wired to CI with per-module thresholds; reports excluded from production JAR

## Spring Review Checklist

Quick-reference for reviewing existing Spring tests:

- [ ] Test type matches what is being tested
- [ ] Every controller endpoint has a slice test with happy + 401 + 403 + validation-error
- [ ] Every custom `@Query` and derived method has a slice test against Testcontainers
- [ ] Every `@PreAuthorize` expression has a passing-and-denied test
- [ ] Test data via builders / factories, not JSON fixtures
- [ ] No `verify(repository).save(any())` patterns when `@DataJpaTest` could assert DB state
- [ ] No `@SpringBootTest` for tests that could run as `@WebMvcTest` or unit
- [ ] No `@DirtiesContext` unless mutating singleton state

## Output Format

**Which output to produce:**

- "What tests are missing?" / "review our coverage" → Coverage Assessment
- "Write tests for X" / "scaffold tests" → Test Scaffolds
- "Test strategy" / "test plan" / coverage < 50% → Strategy Doc (optionally with Coverage Assessment)
- Unclear → Strategy Doc

**Coverage Assessment:**

```markdown
## Spring Boot Test Coverage Assessment

**Stack:** Java <version> / Spring Boot <version>
**Test framework:** JUnit 5, Mockito, AssertJ, Spring Boot Test, Testcontainers
**Coverage gaps:**

- **Unit:** [services / mappers without coverage]
- **Controller slice (@WebMvcTest):** [controllers without tests; controllers missing 401/403]
- **Repository slice (@DataJpaTest):** [repositories with @Query / derived methods without tests; H2-only]
- **Security:** [endpoints without authz tests; missing JWT/OAuth2 flow tests]
- **Full-context:** [transactional flows, listeners, scheduled jobs without coverage]
- **Contract:** [provider/consumer contracts without verification]

**Recommended pyramid balance:**

- Unit: [target]
- Slice: [target]
- Full-context: [target - keep small]
```

**Test Scaffolds** (when generating):

Ready-to-run JUnit 5 files using project conventions. Each scaffold includes:

- Right test type (`@WebMvcTest` / `@DataJpaTest` / `@SpringBootTest` / plain JUnit + Mockito)
- Builders / factories for data (not `new Order(...)`)
- Controller tests: happy + 401 + 403 + validation-error
- Repository tests: Testcontainers via `@ServiceConnection`; assertions against Postgres semantics
- Security tests: `@WithMockUser` / `.with(jwt())` / anonymous; positive and denied
- Inline comments explaining non-obvious setup (why `.with(csrf())` is required)

**Strategy Doc:**

```markdown
## Spring Boot Test Strategy

**Objective:** [what this achieves]
**Pyramid balance:** Unit {x}% / Slice {y}% / Full-context {z}%
**Tooling:** JUnit 5, Mockito (strict), AssertJ, Spring Boot Test, Testcontainers (Postgres / Kafka), Spring Security Test
**Database isolation:** Testcontainers Postgres via @ServiceConnection + transactional rollback
**Concurrency:** [JUnit parallel config]
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

- [ ] Behavioral principles loaded as Step 1
- [ ] Stack confirmed before Spring-specific guidance
- [ ] Code under test and a representative sample of existing tests read so scaffolds match conventions
- [ ] `spring-test-integration` consulted for canonical patterns
- [ ] Pyramid mapped to Spring slice annotations
- [ ] Boundaries defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization applied when coverage is low - auth and repository correctness first, plumbing last
- [ ] Test data via builders / factories; immutable records preferred
- [ ] Testcontainers used; H2 flagged for production-Postgres apps
- [ ] Security testing explicit (`@WithMockUser`, `.with(jwt())`, anonymous)
- [ ] Scaffolds include happy + 401 + 403 + validation-error; idempotency for jobs/listeners; per-role tests for method security
- [ ] Spec-aware mode honored when `--spec` was passed
- [ ] Review checklist applied when reviewing existing tests

## Avoid

- Scaffolding without first reading existing tests - results in wrong builder, wrong assertion library, duplicated base class
- Chasing coverage numbers instead of prioritizing by risk
- `@SpringBootTest` for tests that could be slice or unit
- H2 in `@DataJpaTest` for Postgres-feature apps
- Controller tests with `@SpringBootTest` instead of `@WebMvcTest`
- Duplicating data factories per test class
- `verify(repository).save(any())` when `@DataJpaTest` could assert actual persistence
- Skipping CSRF (`.with(csrf())`) by disabling CSRF in tests - test is now incorrect for prod
- Skipping `@PreAuthorize` tests because the controller has a `@WebMvcTest` - method security tested separately
- Testing Spring internals (that `@Autowired` works, that `@RequestMapping` resolves)
- `@DirtiesContext` as a workaround for shared state - fix the isolation
