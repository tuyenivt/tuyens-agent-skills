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

# Spring Boot Test

Spring-aware test strategy and scaffolding. Stack-specific delegate of `task-code-test` for Java / Spring Boot 3.5+.

## When to Use

- New service / module test strategy
- Coverage-gap assessment
- Scaffolding controller / repository / service / security tests
- Reviewing pyramid balance or adding boundary tests to happy-path-only suites

**Not for:** test failure debugging, code review (`task-code-review`).

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack. If not Spring Boot, stop and direct the user to `/task-code-test`.

### Step 3 - Read Code Under Test and Existing Tests

Scaffolds must match project conventions, not generic templates. **The project's working setup outranks every default shape named in this skill** - container wiring, base classes, naming, assertion library, auth helpers. Deviate only to fix a defect, and say why.

- Target classes top-to-bottom: methods, DTOs, security annotations, transaction boundaries, collaborators
- At least one existing `@WebMvcTest`, `@DataJpaTest`, service unit test - learn builders (Instancio / `@RecordBuilder` / static factories), assertion library, auth helpers (`@WithMockUser` vs custom `JwtRequestPostProcessor`)
- `application-test.{properties,yml}` and any `IntegrationTestBase` / `TestContainersConfig` - reuse the container setup; note whether the test schema comes from Flyway/Liquibase or from `ddl-auto` (a `ddl-auto` schema that skips migrations is a finding, not a convention)
- `build.gradle(.kts)` / `pom.xml` test deps - record which are **present and which are absent**: `spring-security-test`, Testcontainers plus the per-broker module, `spring-kafka-test`, WireMock, Awaitility, Instancio, AssertJ, Spring Cloud Contract, REST Assured. An absent dep is a scaffold dependency to add or a technique to route around (Step 5) - never a silent assumption

No existing tests (greenfield, or the target has none): every convention above is undetermined. Choose them and state them in the deliverable's `Conventions` slot.

### Step 4 - Map the Pyramid

| Layer        | Annotation / type                                             | Scope                                                                  |
| ------------ | ------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Unit         | JUnit 5 + Mockito, no Spring                                  | Service logic, mappers, validators, calculations, state machines       |
| Slice        | `@WebMvcTest` / `@DataJpaTest` / `@JsonTest` / `@RestClientTest` | Controller routing/binding/validation; repo queries; serialization; HTTP client wiring |
| Full-context | `@SpringBootTest` + Testcontainers                            | End-to-end auth, transactional outbox, listeners, scheduled jobs       |
| Contract     | Spring Cloud Contract / Pact                                  | Consumer/provider API contracts                                        |
| E2E          | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + REST Assured | Critical journeys only (signup, checkout, payment)                     |

Many unit, some slice, few full-context / E2E. `@SpringBootTest` is slow - reserve it.

**Pyramid fill rule.** Start at 65/25/10 (unit / slice / full-context+E2E; contract tests tracked separately). Move 5-10 points **out of unit**: into slice for a repository/controller-heavy service, into full-context for a messaging/async-heavy one (outbox, listeners, scheduled jobs live there), split evenly across both when both hold. State the result as a target, not a measured value.

### Step 5 - Apply Patterns

Use skill: `spring-test-integration` for canonical patterns (slice wiring, container setup, security helpers, async assertions) - load once, reference rather than restate. Compose as scope demands:

- Auth (`@WithMockUser`, `jwt()`, method security) → `spring-security-patterns`
- `@Async` / `@Scheduled` / event listeners → `spring-async-processing`
- Kafka / Rabbit / outbox / idempotent listeners → `spring-messaging-patterns`
- `@DataJpaTest` N+1 (`Statistics.getQueryExecutionCount()`), fetch graphs → `spring-jpa-performance`
- `@TransactionalEventListener` phase, `REQUIRES_NEW` → `spring-transaction`
- `@RestControllerAdvice` / ProblemDetail → `spring-exception-handling`

**Layer-specific essentials:**

| Layer                 | Non-negotiables                                                                                                                                                                                |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit                  | One test per outcome. Stub HTTP via Mockito on the client interface. `ArgumentCaptor<DomainEvent>` on `ApplicationEventPublisher` for richer assertions than `verify(...)`.                     |
| `@WebMvcTest`         | One test per `(method+path, role, outcome)`. Mock service via `@MockitoBean`. State-changing methods need `.with(csrf())` when the prod chain has CSRF enabled (session-based apps); stateless JWT chains with CSRF disabled omit it - tests mirror prod. Per protected endpoint: unauthenticated (assert what the prod entry point actually returns - 401 on a stateless chain, 302 to the login page on form login - and send `.with(csrf())` on that case too where CSRF is on, or `CsrfFilter` rejects first and the test asserts CSRF instead of authentication), wrong-role 403, and validation. |
| `@DataJpaTest`        | Testcontainers matching production - H2 diverges on JSONB, partial indexes, window functions, `ON CONFLICT`. **The slice replaces the DataSource with an embedded one unless you stop it**: `@ServiceConnection` on the container does that implicitly, `@DynamicPropertySource` does not - that shape needs `@AutoConfigureTestDatabase(replace = NONE)` or the container starts and the test runs on H2 anyway. The schema comes from the migrations, not `ddl-auto`. Reuse the project's existing container rather than starting a second one; when the container lives inside a `@SpringBootTest` base a slice cannot extend, hoist it into a shared holder. One test per `@Query` / derived method asserting SQL behavior, not nullability. |
| `@SpringBootTest`     | Reserve for full context (auth flow, outbox, listeners, scheduled jobs). Avoid `@DirtiesContext`.                                                                                               |
| Commit-phase / async  | Test-managed `@Transactional` rolls back, so `AFTER_COMMIT` listeners and every commit-gated effect never run and the test passes asserting nothing. Drop test-managed rollback, let the call commit, clean via `@Sql(..., executionPhase = AFTER_TEST_METHOD)` or `@AfterEach`, and assert the listener's **effect** - not that the event was published. Wait with Awaitility or `verify(mock, timeout(2000))`, never `Thread.sleep`. A live `@Scheduled` bean polls throughout the shared context and races the test's own invocation - keep it out by making the bean conditional on a property the test profile disables, or by mocking it; a literal `fixedDelay` cannot be turned off from configuration. |
| HTTP stubs            | `@RestClientTest` + `MockRestServiceServer` for one client bean in isolation; WireMock in `@SpringBootTest` when the real client config is the subject; `@MockitoBean` in `@WebMvcTest`; Mockito on the interface in plain unit. Mocking the client whose wiring is under test bypasses the test. |
| Method security       | `@WebMvcTest` excludes plain `@Configuration` classes, so the app's `SecurityFilterChain` **and** its `@EnableMethodSecurity` are both absent: the slice runs Boot's default chain and every `@PreAuthorize` silently no-ops. `@Import` the security config to get both, which makes a **controller-level** `@PreAuthorize` testable. A **service-level** one stays untestable there for a second reason - the service is a `@MockitoBean` with no real rules to enforce - so assert those in a `@SpringBootTest` / `@ContextConfiguration` with the real bean and `@EnableMethodSecurity` in scope, using `@WithMockUser` callers, positive and denied. |
| Idempotency           | Code accepting an idempotency key: invoke twice, assert single DB row + `verify(gateway, times(1))`.                                                                                            |
| Absent test dep       | Any dependency Step 3 recorded absent that this scaffold needs: either add it, or name the fallback used (`spring-kafka-test` / `@EmbeddedKafka` for a missing broker module, `MockRestServiceServer` for missing WireMock, `verify(mock, timeout(...))` for missing Awaitility, direct handler invocation with a mocked template). Either way it goes in `Scaffold notes`. |
| External auth on a client | A client using OAuth2 client credentials fetches its token from a second endpoint the tests must also stub, and overriding only the API base URL leaves the token exchange reaching the real network. Stub the token endpoint and point `spring.security.oauth2.client.provider.<id>.token-uri` at the stub, or mock the authorized-client manager in a slice. |

**No test needed:** Spring-provided behavior (`@Autowired`, route resolution), generated boilerplate (Lombok / MapStruct), trivial pass-through delegation. A generated mapper carrying a hand-written expression, `default` method, or conditional mapping is logic and belongs in the Unit row.

### Step 6 - Test Data

- Builders / factories (Instancio, `OrderTestData.builder()`) over JSON fixtures; records go through their canonical constructor, wrapped in a factory once the argument list is long
- `@Sql("/fixtures/*.sql")` for shared repo setup; per-test data inline
- Avoid `flush + clear` unless asserting first-level-cache behavior
- `IntStream.range(0, 100)` setups belong in load tests, not the unit suite

### Step 7 - Prioritize When Coverage Is Low

When line coverage is under ~50%, scaffold in this order - alphabetical scaffolding misses authz holes while plumbing gets covered. With no coverage tooling, use the tested-class ratio (production classes with any test / total production classes) as a rough proxy; report it as an estimate and say it is a class ratio, not line coverage. P1 applies only when an authenticated surface exists; internal consumer/batch services start at P2 (state the skip).

| Priority | Target                                                                                  |
| -------- | --------------------------------------------------------------------------------------- |
| P1 Auth  | `@WebMvcTest` unauthenticated + wrong-role per protected endpoint; JWT issuer/audience/signature/expiry (as a `JwtDecoder`-bean unit test or full-context with a local issuer - the `@WebMvcTest` slice stubs the decoder, so they cannot fire there); method security per Step 5 |
| P2 Data  | `@DataJpaTest` per repo with `@Query`/derived; write-path happy + rollback; outbox claim and replay              |
| P3 Revenue | Money and notification paths: checkout, billing, subscription transitions, scheduled jobs that charge or notify |
| P4 Churn | High-commit-frequency files (`git log --since="3 months ago"`); bug-fix-heavy files. No history yet -> skip and say so |
| P5 Plumbing | Pass-through controllers, simple CRUD                                                                          |

### Step 8 - Infrastructure Hygiene

Every row goes into the deliverable's `Suite hygiene` slot with its state: `failing` where the practice exists and is wrong, `to establish` where the tooling is not there yet, `ok` omitted. Checked here, reported there.

- [ ] Testcontainers reuse for local cycles: `.withReuse(true)` on the container **and** `testcontainers.reuse.enable=true` in `~/.testcontainers.properties` - either alone is a no-op; CI runs clean
- [ ] `@SpringBootTest` and `@MockitoBean` sparingly - each unique mock set forks the context cache
- [ ] Test profile overrides only what differs from prod; never silently disables security or swaps the migrated schema for `ddl-auto`
- [ ] JUnit 5 parallel execution where safe
- [ ] Mockito strict stubbing (default under the JUnit 5 `MockitoExtension`)
- [ ] WireMock / Testcontainers for HTTP; no real network
- [ ] JaCoCo in CI with per-module thresholds; generated / boilerplate classes excluded. Decide whether integration tests run in the default `test` task or a separate one - if separate, its execution data must be merged into the report, or the gate scores the very code the ITs cover at zero

## Output Format

Route on the request's verb, not on project state:

| Request                                               | Produce             |
| ----------------------------------------------------- | ------------------- |
| "What's missing?" / "review coverage" / "audit tests" | Coverage Assessment |
| "Write tests for X" / "scaffold tests"                | Test Scaffolds      |
| "Test strategy" / "test plan" / new service           | Strategy Doc        |
| Unclear                                               | Strategy Doc        |

A compound request produces each matched deliverable ("test plan and scaffolding" -> Strategy Doc + Test Scaffolds). When the request targets a whole module or service and the Step 7 estimate lands under ~50%, append the Coverage Assessment's `Gaps` block to the **first** deliverable produced - low coverage adds a section, never a second document. Skip the append when the request targets one named flow (the estimate is about the project, not the flow) or when the deliverable already is a Coverage Assessment.

Every deliverable carries the Step 7 estimate in its `Coverage` line and the Step 8 states in its `Suite hygiene` slot.

**Coverage Assessment:**

```markdown
## Spring Boot Test Coverage Assessment

**Stack:** Java <version> / Spring Boot <version>

**Conventions:** <builder / assertions / auth helper / naming / container base>, each marked (observed) or (chosen - nothing to learn from)

**Tooling present:** <opt-in test dependencies observed; `spring-boot-starter-test` bundles JUnit 5, Mockito, AssertJ, JSONassert and JsonPath, so those are never "absent">

**Tooling absent:** <opt-in dependencies a scaffold would need; `None`>

**Coverage:** <n>% (JaCoCo) | ~<n>% estimated from tested-class ratio <t>/<c>, a class ratio rather than line coverage

**Gaps:**

- **Unit:** [services / mappers]
- **@WebMvcTest:** [controllers; missing unauthenticated / wrong-role cases]
- **@DataJpaTest:** [repos with @Query / derived; H2 or `ddl-auto` schema flagged]
- **Security:** [endpoints without authz; inert `@PreAuthorize`; missing JWT flow]
- **Full-context:** [transactional flows, listeners, jobs]
- **External boundaries:** [client beans, mail senders, and any other real-network side effect with no stubbed test]
- **Contract:** [provider/consumer, or event schemas downstream consumers depend on; omit when none]
- **Misuse:** [wrong slice, H2 in `@DataJpaTest`, `@DirtiesContext`, context-cache forking, security disabled in the test profile; omit when none]

**Suite hygiene:** [Step 8 rows with their state; `None`]

**Recommended balance:** Unit {x}% / Slice {y}% / Full-context+E2E {z}%

**Fix in this order:**

1. [highest-risk first, by the Step 7 priority ladder rather than by the layer order above]
2. [...]
```

**Test Scaffolds** - ready-to-run JUnit 5 files, preceded by this header:

```markdown
## Spring Boot Test Scaffolds

**Conventions:** <as above>

**Coverage:** <as above>

**Files:**

- `<path>` - <what it covers; mark an edit to an existing file as (edit)>

**Scaffold notes:** <what the scaffold forced: dependencies to add, the fallback used for an absent dep, wiring the project's container setup required, scheduler or async races handled, production changes the tests depend on; `None`>

**Suite hygiene:** <Step 8 rows with their state; `None`>

**Deferred:** <targets left for a next round, each with its reason; `None`>
```

Then the files themselves:

- Right test type per target; layout mirrors the prod package under `src/test/java`
- Naming `<Class>Test` (unit / slice), `<Flow>IT` (full-context) - on Maven `*IT` runs under Failsafe, so the build must bind it
- Full-context tests share the project's singleton-container base class; a slice reuses that same container instead of starting a second one; create the base when absent
- Security cases live in the same controller slice class as the functional tests unless the existing suite separates `*SecurityTest` classes
- Builders / factories over ad-hoc construction, records through their canonical constructor (Step 6)
- Controllers: happy + unauthenticated + wrong-role + validation-error
- Repos: Testcontainers matching production, schema from the migrations
- Security: `@WithMockUser` / `.with(jwt())` / anonymous; positive and denied
- Inline comments only where non-obvious (e.g., why `.with(csrf())`)
- `spring-test-integration`'s per-class output blocks are never emitted as files; anything they would have said belongs in `Scaffold notes`

**Strategy Doc:**

```markdown
## Spring Boot Test Strategy

**Objective:** [what this achieves]

**Conventions:** <as above>

**Coverage:** <as above>

**Pyramid balance:** Unit {x}% / Slice {y}% / Full-context+E2E {z}% of test methods

**Tooling:** <what the suite will use, marking which are not yet on the classpath>

**DB isolation:** [singleton Testcontainers base; schema from migrations; transactional rollback, or committed + `@Sql` / `@AfterEach` cleanup for commit-gated and `@Async` flows]

**Concurrency:** [JUnit parallel config]

**Suite hygiene:** [Step 8 rows with their state, including the CI coverage gate when one is required]

**Prioritized gaps:**

1. [Highest-risk - typically authz or repository correctness]
2. [...]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed as Spring Boot
- [ ] Step 3: code under test and existing tests read; present and absent test deps recorded; conventions taken from the project or chosen and stated
- [ ] Step 4: pyramid mapped; percentages derived by the fill rule (points moved out of unit; split when both triggers hold)
- [ ] Step 5: `spring-test-integration` consulted; layer non-negotiables applied (production-matching containers, CSRF, unauthenticated / wrong-role coverage, method security imported or asserted in full context, commit-gated work committed and awaited)
- [ ] Step 6: builders / factories over JSON fixtures
- [ ] Step 7: the priority ladder ordered the work - P1 auth and P2 data before plumbing, whether scaffolded or listed; estimate reported as a class ratio
- [ ] Step 8: hygiene applied; every row written into the `Suite hygiene` slot with its state
- [ ] Deliverable routed on the request verb; `Conventions` and `Coverage` filled; `Gaps` block appended only when the request targets a module or service under ~50%

## Avoid

- Scaffolding before reading existing tests - wrong builder, wrong assertions, duplicated base class
- Overriding a project's working container or auth setup with this skill's default shape
- Chasing coverage % instead of prioritizing by risk
- `@SpringBootTest` where `@WebMvcTest`, `@RestClientTest`, or a plain unit test suffices
- H2 in `@DataJpaTest` for a Postgres-feature app; `ddl-auto` where migrations define the schema
- `verify(repository).save(any())` when `@DataJpaTest` could assert persistence
- Disabling CSRF or security in tests to make them pass - the test no longer mirrors prod
- Asserting that an event was published instead of asserting what its listener did
- `Thread.sleep` to wait for async work
- Testing Spring internals (`@Autowired`, `@RequestMapping` resolution)
- `@DirtiesContext` as a shared-state workaround - fix isolation instead
