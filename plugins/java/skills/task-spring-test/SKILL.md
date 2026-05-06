---
name: task-spring-test
description: Spring Boot test strategy and scaffolding using JUnit 5, Spring test slices (@WebMvcTest, @DataJpaTest), Testcontainers, Mockito, and Spring Security Test. Use when designing a Spring test plan, assessing coverage gaps, or scaffolding controller/service/repository/security tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to Java/Spring Boot.
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

Use skill: `stack-detect` to confirm Java / Spring Boot. If the detected stack is not Spring Boot, stop and tell the user to invoke `/task-code-test` instead.

### Step 2 - Spring Test Pyramid

The Spring Boot test pyramid maps to test types and slice annotations:

| Layer               | Spring annotation / type                                                  | What belongs here                                                                           |
| ------------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Unit                | Plain JUnit 5 + Mockito (no Spring context)                               | Service business logic, mappers, validators, pure functions, calculation rules              |
| Slice (integration) | `@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, `@JdbcTest`, `@WebFluxTest`   | Controller routing/binding/validation; repository queries; serialization contracts          |
| Full-context        | `@SpringBootTest` + Testcontainers                                        | End-to-end controller -> service -> repository -> real DB; security filter chain; messaging |
| Contract            | Spring Cloud Contract / Pact (consumer-side)                              | API consumer/provider contracts                                                             |
| E2E                 | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + REST Assured / TestRest | Critical user journeys only - signup, checkout, payment                                     |

**Many** unit tests, **some** slice tests, **few** full-context / E2E tests. `@SpringBootTest` is slow (loads full context) - use sparingly.

### Step 3 - Apply Spring Test Patterns

Use skill: `spring-test-integration` for the canonical patterns referenced below.

**Unit tests (`src/test/java/.../service/`):**

- JUnit 5 (`@Test`, `@Nested`, `@DisplayName`); AssertJ for fluent assertions; Mockito for collaborator stubs (`@Mock`, `@InjectMocks`, `@ExtendWith(MockitoExtension.class)`)
- Test the public method - one test per outcome (success, validation failure, external failure, edge case)
- **No Spring context** - if you find yourself adding `@SpringBootTest` for a unit test, the test is misclassified or the class has too many collaborators
- Stub external HTTP via Mockito on the client interface; do not stub repositories with full SQL behavior - use a slice test or Testcontainers for that
- Verify post-conditions (records persisted, events published) via `verify(...)` on the relevant collaborator mock

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

**Contract tests:**

- Spring Cloud Contract: contracts in `src/test/resources/contracts/`; provider verifies via generated tests; consumer pulls stubs via stub runner
- Pact: pact files committed to a broker; provider verification runs as a separate test class

### Step 4 - Test Boundaries (Spring-Specific)

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

### Step 5 - Test Data and Fixtures

- Prefer constructor-based or builder-based data factories (Instancio, Easy Random, or hand-rolled `OrderTestData.builder()`) over JSON fixtures
- For repository tests with Testcontainers, use `@Sql("/fixtures/orders.sql")` for shared setup; isolate per-test data inside the test
- Records / immutable DTOs: instantiate directly via constructor - no factories needed for trivial cases
- **Avoid `flush + clear` patterns** unless the test is specifically asserting first-level cache behavior
- Test data must be minimal and focused - 100-row `IntStream.range` setups signal the test belongs at integration / load-test layer

### Step 6 - Prioritization (when coverage is low)

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

### Step 7 - Test Infrastructure Hygiene

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

**Scaffold templates** (adapt to project conventions - package names, builder names, constants):

_Service unit test_ (`src/test/java/.../service/ChargeCardServiceTest.java`):

```java
@ExtendWith(MockitoExtension.class)
class ChargeCardServiceTest {

  @Mock GatewayClient gateway;
  @Mock OrderRepository orders;
  @InjectMocks ChargeCardService service;

  @Nested
  @DisplayName("when the gateway succeeds")
  class GatewaySucceeds {
    @Test
    void returnsSuccessAndRecordsCharge() {
      var order = OrderTestData.builder().totalCents(5_000).build();
      given(gateway.charge(any())).willReturn(GatewayResponse.ok("ch_1"));
      given(orders.save(any())).willAnswer(inv -> inv.getArgument(0));

      var result = service.charge(order, "tok_visa");

      assertThat(result.isSuccess()).isTrue();
      assertThat(result.chargeId()).isEqualTo("ch_1");
      verify(orders).save(argThat(o -> o.getStatus() == OrderStatus.CHARGED));
    }
  }

  @Nested
  @DisplayName("when the gateway returns a card error")
  class CardDeclined {
    @Test
    void returnsFailureAndDoesNotCharge() {
      var order = OrderTestData.builder().totalCents(5_000).build();
      given(gateway.charge(any())).willReturn(GatewayResponse.error("card_declined"));

      var result = service.charge(order, "tok_visa");

      assertThat(result.isFailure()).isTrue();
      assertThat(result.error()).isEqualTo("card_declined");
      verify(orders, never()).save(any());
    }
  }
}
```

_Controller slice test_ (`src/test/java/.../web/OrderControllerTest.java`):

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {

  @Autowired MockMvc mvc;
  @MockitoBean OrderService service;

  @Test
  @WithMockUser(username = "alice", roles = "USER")
  void getOrderReturns200ForOwner() throws Exception {
    given(service.findForUser(42L, "alice")).willReturn(Optional.of(OrderTestData.builder().id(42L).build()));

    mvc.perform(get("/orders/42"))
       .andExpect(status().isOk())
       .andExpect(jsonPath("$.id").value(42));
  }

  @Test
  @WithMockUser(username = "mallory", roles = "USER")
  void getOrderReturns404ForNonOwner() throws Exception {
    given(service.findForUser(42L, "mallory")).willReturn(Optional.empty());

    mvc.perform(get("/orders/42"))
       .andExpect(status().isNotFound());
  }

  @Test
  void getOrderReturns401WhenAnonymous() throws Exception {
    mvc.perform(get("/orders/42"))
       .andExpect(status().isUnauthorized());
  }

  @Test
  @WithMockUser(roles = "USER")
  void postOrderReturns400WhenPayloadInvalid() throws Exception {
    mvc.perform(post("/orders").with(csrf())
         .contentType(MediaType.APPLICATION_JSON)
         .content("{\"totalCents\": -1}"))
       .andExpect(status().isBadRequest());
  }
}
```

_Repository slice test_ (`src/test/java/.../repo/OrderRepositoryTest.java`):

```java
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
class OrderRepositoryTest {

  @Container @ServiceConnection
  static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

  @Autowired OrderRepository orders;
  @Autowired TestEntityManager em;

  @Test
  void findOpenOrdersByCustomerReturnsOnlyOpenStatuses() {
    var customer = em.persistAndFlush(CustomerTestData.builder().build());
    em.persistAndFlush(OrderTestData.builder().customer(customer).status(OrderStatus.OPEN).build());
    em.persistAndFlush(OrderTestData.builder().customer(customer).status(OrderStatus.CLOSED).build());

    var result = orders.findOpenOrders(customer.getId());

    assertThat(result).hasSize(1).extracting(Order::getStatus).containsOnly(OrderStatus.OPEN);
  }
}
```

_Security slice test_ (excerpt):

```java
@Test
@WithMockUser(roles = "USER")
void adminEndpointReturns403ForNonAdmin() throws Exception {
  mvc.perform(get("/admin/orders"))
     .andExpect(status().isForbidden());
}

@Test
@WithMockUser(roles = "ADMIN")
void adminEndpointReturns200ForAdmin() throws Exception {
  mvc.perform(get("/admin/orders"))
     .andExpect(status().isOk());
}
```

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

- [ ] Stack confirmed as Java / Spring Boot before any Spring-specific guidance applied
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
