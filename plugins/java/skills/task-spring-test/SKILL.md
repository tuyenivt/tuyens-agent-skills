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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `Satisfies: AC<N>` mapping in test names), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Spring Boot Test

## Purpose

Spring-aware test strategy and scaffolding using JUnit 5 idioms, Spring test slices, Testcontainers (PostgreSQL, Kafka, Redis), Mockito, AssertJ, and the Spring Boot test pyramid (unit / slice / full-context / E2E). Replaces the generic backend test patterns with Spring-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for Java / Spring Boot. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a Spring Boot test strategy for a new service or module
- Assessing test coverage gaps across unit / slice / full-context / contract tests
- Scaffolding tests for under-covered controllers, services, repositories, or security configs
- Reviewing test pyramid balance for a Spring Boot app
- Adding boundary tests (validation, authorization, edge cases) to existing happy-path tests

**Not for:**

- Test failure debugging (use `task-spring-debug`)
- General code review (use `task-code-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Java / Spring Boot. If invoked as a delegate of `task-code-test` (parent already detected Spring Boot), accept the pre-confirmed stack and skip re-detection. If the detected stack is not Spring Boot, stop and tell the user to invoke `/task-code-test` instead.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the class top-to-bottom: public methods, request/response types, security annotations, transaction boundaries, external collaborators
- Glob `src/test/java/**/*Test*.java` and read at least: one existing `@WebMvcTest`, one existing `@DataJpaTest`, one existing service unit test - learn the project's package layout, builder/factory names (`OrderTestData.builder()` vs Instancio vs `@RecordBuilder`), assertion library (AssertJ vs Hamcrest), authentication helpers (`@WithMockUser` vs custom `JwtRequestPostProcessor`)
- Read `application-test.properties` / `application-test.yml` and any `TestContainersConfig` / `IntegrationTestBase` / `AbstractIntegrationTest` base class - reuse the project's container setup rather than scaffolding a new one
- Read `build.gradle(.kts)` / `pom.xml` test dependencies to confirm Testcontainers, Instancio, AssertJ, Spring Cloud Contract, REST Assured presence

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 3 - Spring Test Pyramid

The Spring Boot test pyramid maps to test types and slice annotations:

| Layer               | Spring annotation / type                                                  | What belongs here                                                                           |
| ------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Unit                | Plain JUnit 5 + Mockito (no Spring context)                               | Service business logic, mappers, validators, pure functions, calculation rules              |
| Slice (integration) | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@JdbcTest`, `@WebFluxTest`   | Controller routing/binding/validation; repository queries; serialization contracts          |
| Full-context        | `@SpringBootTest` + Testcontainers                                        | End-to-end controller -> service -> repository -> real DB; security filter chain; messaging |
| Contract            | Spring Cloud Contract / Pact (consumer-side)                              | API consumer/provider contracts                                                             |
| E2E                 | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + REST Assured / TestRest | Critical user journeys only - signup, checkout, payment                                     |

**Many** unit tests, **some** slice tests, **few** full-context / E2E tests. `@SpringBootTest` is slow (loads full context) - use sparingly.

### Step 4 - Apply Spring Test Patterns

Use skill: `spring-test-integration` for the canonical patterns referenced below.

**Unit tests (`src/test/java/.../service/`):**

- JUnit 5 (`@Test`, `@Nested`, `@DisplayName`); AssertJ for fluent assertions; Mockito for collaborator stubs (`@Mock`, `@InjectMocks`, `@ExtendWith(MockitoExtension.class)`)
- Test the public method - one test per outcome (success, validation failure, external failure, edge case)
- **No Spring context** - if you find yourself adding `@SpringBootTest` for a unit test, the test is misclassified or the class has too many collaborators
- Stub external HTTP via Mockito on the client interface (`@HttpExchange`-declared interface or a hand-rolled `PaymentGatewayClient` interface); do not stub repositories with full SQL behavior - use a slice test or Testcontainers for that
- Verify post-conditions (records persisted, events published) via `verify(...)` on the relevant collaborator mock. For `ApplicationEventPublisher`, captured arguments via `ArgumentCaptor<DomainEvent>` give finer assertions than `verify(...)` alone

**HTTP stubbing - choose by test type, not by habit:**

| Test type             | Stub HTTP via                                                       |
| --------------------- | ------------------------------------------------------------------- |
| Plain unit test       | Mockito on the client interface - fastest, no network              |
| `@SpringBootTest`     | WireMock (`@WireMockTest` in spring-boot-test 3.2+, or `WireMockExtension`) - exercises real `RestClient` / `WebClient` config including timeouts, retries, deserialization, error handling |
| `@WebMvcTest`         | The downstream client is mocked (`@MockitoBean`) - this slice does not exercise outbound calls |

Mocking `RestClient` itself in an integration test bypasses the very wiring the integration test exists to verify. Use WireMock so the request actually leaves the bean.

**Idempotency tests for replay-safe operations:**

When the code under test accepts an idempotency key (payment charge, webhook delivery, message handler), include a test that invokes the operation twice with the same key and asserts the second call short-circuits without producing a duplicate side effect (no second DB write, no second outbound HTTP call). A unit test with `verify(gateway, times(1))` plus a `@DataJpaTest` or `@SpringBootTest` asserting row count is the typical pair.

**Controller slice tests (`@WebMvcTest`):**

- One test per `(method+path, role, outcome)` triple - covers routing, controller, request/response binding, validation, and `SecurityFilterChain` matchers
- Use `MockMvc` (servlet) or `WebTestClient` (reactive)
- Authentication via `@WithMockUser`, `@WithUserDetails`, or `SecurityMockMvcRequestPostProcessors.user(...)` / `.jwt()`
- Authorization: a separate test for "user without permission gets 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any DTO with `@Valid` constraints
- Response shape: assert key fields, status, headers, and `Content-Type` - not the full body
- Mock the service layer with `@MockitoBean` (Boot 3.4+) or `@MockBean` (deprecated in 3.4 but still works)

**Repository slice tests (`@DataJpaTest`):**

- Use Testcontainers PostgreSQL via `@ServiceConnection` (Boot 3.1+) - `@DataJpaTest` defaults to H2, which diverges from PostgreSQL on JSONB, partial indexes, window functions, and `ON CONFLICT`. Pin to the production engine.
- One test per derived query method or `@Query` - assert the SQL is correct, not just that the method returns something
- Custom `@Query` JPQL: assert the result set against fixture data inserted via the repository or `TestEntityManager`
- Native queries: must run against Testcontainers (H2 will not parse PostgreSQL syntax)
- N+1 detection: enable `spring.jpa.properties.hibernate.generate_statistics=true` in `application-test.properties`; assert `Statistics.getQueryExecutionCount()` for repository methods that load associations

**Security slice (`@WebMvcTest` + Spring Security Test):**

- One test per `(endpoint, principal-state, outcome)` triple
- Anonymous: assert 401 for protected endpoints
- Authenticated without role: assert 403 for role-gated endpoints
- Authenticated with role: assert 200 plus expected payload
- CSRF: for `@WebMvcTest`, requests need `.with(csrf())` for state-changing methods - this is a feature, not a workaround

**Full-context / Testcontainers (`@SpringBootTest`):**

- Reserve for tests that genuinely need the full context: end-to-end auth flows, transactional outbox, message-driven listeners, scheduled jobs
- Use `@Testcontainers` + `@Container static PostgreSQLContainer<?> pg = ...` with `@DynamicPropertySource` to wire datasource properties
- Use `@Sql` for fixture data; reset state between tests via `@Transactional` rollback or explicit cleanup
- Avoid `@DirtiesContext` - it flushes the cached context, multiplying test time
- **`@Transactional` on the test class auto-rolls back, but spawned threads do not see uncommitted test data.** A test that triggers `@Async`, `@Scheduled`, `TaskExecutor.submit`, or any code expecting the row to be visible from another thread will fail inside the async thread (often silently). For tests exercising async paths, drop `@Transactional` from the test and clean up via `@Sql(executionPhase = AFTER_TEST_METHOD)` or explicit teardown.
- **Asserting transactional event listener phases**: use `@RecordApplicationEvents` (Boot 3+) with `ApplicationEvents` injection to assert *what* was published *and when* (correlate with transaction commit). Mocking `ApplicationEventPublisher` in unit tests verifies the event was published but cannot distinguish `BEFORE_COMMIT` from `AFTER_COMMIT` semantics - use a full-context test if the phase matters.

**Contract tests:**

- Spring Cloud Contract: contracts in `src/test/resources/contracts/`; provider verifies via generated tests; consumer pulls stubs via stub runner
- Pact: pact files committed to a broker; provider verification runs as a separate test class

### Step 5 - Test Boundaries (Spring-Specific)

**What deserves a unit test:**

- Service logic, mappers (especially MapStruct), validators, custom `@ConfigurationProperties` validation
- Domain rules, calculation, state-machine transitions
- Spring-independent helpers / utilities

**What deserves a slice test:**

- Every controller endpoint (`@WebMvcTest`): happy path + 401/403 + 4xx validation
- Every custom repository query (`@DataJpaTest` + Testcontainers): query result correctness
- Serialization contracts (`@JsonTest`): DTO <-> JSON round trip when the serialization shape is part of the API
- Security configuration (`@WebMvcTest`): role-based access, CSRF handling, JWT decoding

**What deserves a full-context test:**

- Cross-component flows that traverse controller -> service -> repository -> external (Kafka / S3 / mail)
- Auth flows end-to-end (login -> token issuance -> protected resource access)
- Transactional outbox / message-driven listeners
- Scheduled jobs (`@Scheduled`) verified via `Awaitility` and a real clock

**What does NOT need a test:**

- Spring-provided behavior: `@Autowired` injection, `@RequestMapping` route resolution, default Jackson serialization (test that you wired things correctly via slice tests, not that Spring works)
- Generated boilerplate: Lombok-generated getters/setters, MapStruct identity mappings between identical fields
- Trivial delegation: `service.findById(id) -> repository.findById(id)` with no logic

### Step 6 - Test Data and Fixtures

- Prefer constructor-based or builder-based data factories (Instancio, Easy Random, or hand-rolled `OrderTestData.builder()`) over JSON fixtures
- For repository tests with Testcontainers, use `@Sql("/fixtures/orders.sql")` for shared setup; isolate per-test data inside the test
- Records / immutable DTOs: instantiate directly via constructor - no factories needed for trivial cases
- **Avoid `flush + clear` patterns** unless the test is specifically asserting first-level cache behavior
- Test data must be minimal and focused - 100-row `IntStream.range` setups signal the test belongs at integration / load-test layer

### Step 7 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go untested while plumbing controllers get full coverage.

When starting from low test coverage, prioritize by Spring-specific risk:

**Priority 1 - Authorization and authentication:**

- `@WebMvcTest` per protected endpoint asserting 401 / 403 with `@WithMockUser` and unauthenticated cases
- OAuth2 / JWT flow tests covering issuer, audience, signature, expiry validation
- Method security: `@PreAuthorize` expressions tested at the service layer

**Priority 2 - Data integrity:**

- `@DataJpaTest` for every repository with custom `@Query` or derived methods that touch business-critical tables
- Service tests for write operations (one happy path + one rollback per write)
- Transactional outbox / message dispatch idempotency

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions
- Scheduled jobs touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through controllers, simple CRUD - lower risk, can wait

### Step 8 - Test Infrastructure Hygiene

- [ ] Testcontainers reused across tests via `@ServiceConnection` + reusable mode (`testcontainers.reuse.enable=true` in `~/.testcontainers.properties`) for local fast cycles
- [ ] `@SpringBootTest` count kept low; use `@MockitoBean` / `@MockBean` sparingly (each unique mock set forces a new context cache entry)
- [ ] Test profile (`application-test.properties` / `@ActiveProfiles("test")`) overrides only what differs from prod - never silently disables security
- [ ] JUnit 5 parallel execution enabled where safe (`junit.jupiter.execution.parallel.enabled=true`); per-class isolation for stateful tests
- [ ] Mockito strict stubbing (`MockitoExtension` default in 4+) - flags unused stubs as test smells
- [ ] WireMock or Testcontainers for HTTP stubs; never real network calls
- [ ] `gradle test --info` shows fixture/teardown timing; long-running fixtures flagged for refactoring
- [ ] Coverage tool (JaCoCo) wired to CI with per-module thresholds; coverage reports excluded from the production JAR

## Spring Review Checklist

Quick-reference checklist for reviewing existing Spring tests:

- [ ] Test type matches what is being tested (controller -> `@WebMvcTest`, repository -> `@DataJpaTest`, service -> plain JUnit + Mockito)
- [ ] Every controller endpoint has a slice test with at least happy + 401 + 403 + validation-error
- [ ] Every custom `@Query` and derived repository method has a slice test against Testcontainers (not H2)
- [ ] Every `@PreAuthorize` expression has a passing-and-denied test
- [ ] Test data created via builders/factories, not JSON fixtures
- [ ] No `verify(repository).save(any())` patterns when the test could have asserted DB state via `@DataJpaTest` instead
- [ ] No `@SpringBootTest` for tests that could run as `@WebMvcTest` or unit
- [ ] No `@DirtiesContext` unless the test specifically mutates singleton state

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% -> Strategy Doc (optionally include Coverage Assessment)
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Spring Boot Test Coverage Assessment

**Stack:** Java <version> / Spring Boot <version>
**Test framework:** JUnit 5, Mockito, AssertJ, Spring Boot Test, Testcontainers
**Coverage gaps:**

- **Unit tests:** [services / mappers without test coverage]
- **Controller slice tests (@WebMvcTest):** [controllers without tests; controllers missing 401/403 paths]
- **Repository slice tests (@DataJpaTest):** [repositories with @Query / derived methods without tests; repositories tested only against H2]
- **Security tests:** [endpoints without authorization tests; missing JWT/OAuth2 flow tests]
- **Full-context tests:** [transactional flows, listeners, scheduled jobs without coverage]
- **Contract tests:** [provider/consumer contracts without verification]

**Recommended pyramid balance:**

- Unit (services, mappers, helpers): [count target]
- Slice (@WebMvcTest, @DataJpaTest, @JsonTest): [count target]
- Full-context (@SpringBootTest + Testcontainers): [count target - keep small]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run JUnit 5 test files using project conventions. Each scaffold must include:

- The right test type (`@WebMvcTest`, `@DataJpaTest`, `@SpringBootTest`, or plain JUnit + Mockito)
- Builders / factories for test data instead of `new Order(...)` calls
- For controller tests: happy path + 401 + 403 + validation-error
- For repository tests: Testcontainers via `@ServiceConnection`; assertions against PostgreSQL semantics
- For security tests: `@WithMockUser`, `.with(jwt())`, or anonymous; positive and denied cases
- Inline comments explaining non-obvious setup (e.g., why `.with(csrf())` is required)

**Strategy Doc** (when designing a test strategy):

```markdown
## Spring Boot Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Slice (@WebMvcTest, @DataJpaTest) {y}% / Full-context {z}%
**Tooling:** JUnit 5, Mockito (strict stubbing), AssertJ, Spring Boot Test, Testcontainers (PostgreSQL / Kafka), Spring Security Test
**Database isolation:** Testcontainers PostgreSQL via @ServiceConnection + transactional rollback
**Concurrency:** [JUnit parallel execution config]
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

- [ ] Stack confirmed as Java / Spring Boot before any Spring-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests read directly so scaffolds match project conventions (Step 2)
- [ ] `spring-test-integration` consulted for canonical Spring test patterns
- [ ] Test pyramid mapped to Spring slice annotations (unit -> plain JUnit + Mockito; slice -> `@WebMvcTest` / `@DataJpaTest` / `@JsonTest`; full-context -> `@SpringBootTest` + Testcontainers)
- [ ] Boundaries clearly defined: each spec layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - authorization and repository correctness first, plumbing last
- [ ] Test data guidance includes builders/factories over JSON fixtures; immutable records preferred
- [ ] Testcontainers used for repository and full-context tests; H2 flagged as a smell for production-Postgres apps
- [ ] Security testing approach explicit (`@WithMockUser`, `.with(jwt())`, anonymous case)
- [ ] Test scaffolds (if generated) include happy path + 401 + 403 + validation-error; idempotency for jobs / listeners; per-role tests for method security
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)
- [ ] Review checklist items addressed when reviewing existing tests

## Avoid

- Scaffolding tests without first reading existing tests in the project - the result imports the wrong builder, uses the wrong assertion library, or duplicates the integration-test base class
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no security tests misses the bigger threat
- `@SpringBootTest` for tests that could run as `@WebMvcTest` or plain unit - context-load cost compounds across the suite
- H2 in `@DataJpaTest` for apps that use PostgreSQL features (JSONB, partial indexes, `ON CONFLICT`, window functions) - tests pass, prod fails
- Writing controller tests with `@SpringBootTest` instead of `@WebMvcTest` - heavier and slower for the same coverage
- Duplicating test data factories per test class - share builders / Instancio configs
- Using `verify(repository).save(any())` when a `@DataJpaTest` could assert actual persistence
- Skipping CSRF (`.with(csrf())`) by disabling CSRF in tests - the test is now incorrect for the prod config
- Skipping `@PreAuthorize` tests because the controller has a `@WebMvcTest` - method security is unit-tested separately so it can be reused
- Testing Spring internals (e.g., that `@Autowired` works, that `@RequestMapping` resolves to a method) - test your wiring, not the framework
- `@DirtiesContext` as a workaround for shared state - fix the test isolation instead
