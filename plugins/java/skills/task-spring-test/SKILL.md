---
name: task-spring-test
description: "Spring Boot test plan and scaffolding: JUnit 6, @WebMvcTest, @DataJpaTest, Testcontainers, Mockito, Spring Security Test."
agent: java-test-engineer
metadata:
  category: backend
  tags: [java, spring-boot, junit, testcontainers, mockito, testing, workflow]
  type: workflow
user-invocable: true
---

# Spring Boot Test

Spring-aware test strategy and scaffolding for Java / Spring Boot 4.0+.

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

Use skill: `stack-detect`. Accept pre-confirmed stack. If not Spring Boot, stop: a stop emits `**Stack:**` naming the detected stack and its test workflow; the other sections are omitted, never emitted empty.

Read the Spring Boot version from the build file (Gradle `org.springframework.boot` plugin or version catalog; Maven `spring-boot-starter-parent` or the imported `spring-boot-dependencies` BOM) and the Java version from `java.toolchain` / `<java.version>` / `maven.compiler.release`; `stack-detect` does not report either. Every construct a finding cites as present and every fix recommends must exist and bind on that version - including fixes taken from a composed atomic. Below Boot 4.0, write the row's or the atomic's Boot 3 form; when it has none, say `Boot 3 form not given` rather than emitting the Boot 4 one. Here, every coordinate, annotation and import a scaffold emits counts as a fix. Boot 3.x: `spring-boot-starter-test` declared directly (JUnit 5; Awaitility bundled from 3.2), `spring-security-test`, Testcontainers 1.x, `@MockBean` / `@SpyBean` below 3.4. Boot 3.0: pin Testcontainers 1.x; no `@ServiceConnection`, use `@DynamicPropertySource`.

### Step 3 - Read Code Under Test and Existing Tests

Scaffolds must match project conventions, not generic templates. **The project's working setup outranks every default shape named in this skill** - container wiring, base classes, naming, assertion library, auth helpers. Deviate only to fix a defect, and say why. A setup that cannot work on the declared version (coordinates that do not resolve, a context that cannot start) is a defect, never a convention to copy.

- Target classes top-to-bottom: methods, DTOs, security annotations, transaction boundaries, collaborators
- The requirement the target implements (the ticket or doc the request names, commit messages, `docs/`): tests assert the intended rule - who may act on which resource, what a duplicate does. Code that disagrees is a production defect the test pins; with no requirement found, name the pinned behavior as assumed
- At least one existing `@WebMvcTest`, `@DataJpaTest`, service unit test - learn builders (Instancio / `@RecordBuilder` / static factories), assertion library, auth helpers (`@WithMockUser` vs custom `JwtRequestPostProcessor`)
- `application-test.{properties,yml}` and any `IntegrationTestBase` / `TestContainersConfig` - reuse the container setup; note whether the test schema comes from Flyway/Liquibase or from `ddl-auto` (a `ddl-auto` schema that skips migrations is a finding, not a convention)
- `build.gradle(.kts)` / `pom.xml` test deps - record which are **present, absent, and unresolvable**: the per-technology `spring-boot-starter-<tech>-test` starters (Boot 4; `spring-boot-starter-restclient-test` for `@RestClientTest`), `spring-security-test` (via `spring-boot-starter-security-test` on Boot 4), `spring-boot-testcontainers` (`@ServiceConnection`), Testcontainers plus the per-engine module, `spring-kafka-test`, WireMock, Instancio, Spring Cloud Contract, REST Assured, and on Gradle 9 `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'`. An absent dep is a scaffold dependency to add or a technique to route around (Step 5) - never a silent assumption
- Testcontainers names match the resolved major (build pin, else Boot BOM): 2.x (Boot 4) `org.testcontainers:testcontainers-<module>`, non-generic `org.testcontainers.<module>.*Container`; 1.x (Boot 3.x) `org.testcontainers:<module>`, generic `org.testcontainers.containers.*Container<?>` (deprecated on 2.x). An artifact from the other major does not resolve and fails every container test: record it unresolvable; new code uses the resolved names
- Context start, one result per check: scan roots (compare the `scanBasePackages` / `@EntityScan` / `@EnableJpaRepositories` roots with the package of every injected type from another module); every injected interface has an implementation; entities match the migrated schema when the test profile or a scaffold runs `ddl-auto: validate`; nothing the declared Framework rejects at startup (6.1+: `@Transactional` on a `@TransactionalEventListener` unless `REQUIRES_NEW` / `NOT_SUPPORTED`); inert on the declared version - Framework 7 `@Retryable` / `@ConcurrencyLimit` without `@EnableResilientMethods`, Boot 3 `spring.http.client.*` keys on Boot 4 (binds nothing - `spring.http.clients.*`), a Jackson 2 `ObjectMapper` bean on Boot 4 (Boot uses its own `JsonMapper`), bare `flyway-core` / `liquibase-core` / `spring-kafka` on Boot 4 (no auto-configuration without the starter or module; `validate` then meets an empty schema). Each blocker fails every context-loading test - Step 7 P0; a test never trusts an inert construct

No existing tests (greenfield, or the target has none): every convention above is undetermined. Choose them and state them in the deliverable's `Conventions` slot.

### Step 4 - Map the Pyramid

| Layer        | Annotation / type                                             | Scope                                                                  |
| ------------ | ------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Unit         | JUnit + Mockito, no Spring                                    | Service logic, mappers, validators, calculations, state machines       |
| Slice        | `@WebMvcTest` / `@DataJpaTest` / `@JsonTest` / `@RestClientTest` | Controller routing/binding/validation; repo queries; serialization; HTTP client wiring |
| Full-context | `@SpringBootTest` + Testcontainers                            | End-to-end auth, transactional outbox, listeners, scheduled jobs       |
| Contract     | Spring Cloud Contract / Pact                                  | Consumer/provider API contracts                                        |
| E2E          | `@SpringBootTest(webEnvironment = RANDOM_PORT)` + REST Assured | Critical journeys only (signup, checkout, payment)                     |

**Pyramid fill rule.** Start at 65/25/10 (unit / slice / full-context+E2E; contract tests tracked separately). Move 5-10 points **out of unit**: into slice for a repository/controller-heavy service, into full-context for a messaging/async-heavy one (outbox, listeners, scheduled jobs live there), split evenly across both when both hold. State the result as a target, not a measured value.

### Step 5 - Apply Patterns

Use skill: `spring-test-integration` for the test mechanics (slice wiring, containers, security tests, broker round trips, concurrency, async assertions) - load once, reference rather than restate. In every mode, also load each atomic below whose construct appears in the code under test; it defines the behavior the tests assert:

- Auth rules, JWT claim mapping, method security → `spring-security-patterns`
- `@Async` / `@Scheduled` / event listeners → `spring-async-processing`
- Kafka / Rabbit / outbox / idempotent listeners → `spring-messaging-patterns`
- Fetch plans, N+1 → `spring-jpa-performance`
- `@TransactionalEventListener` phase, `REQUIRES_NEW` → `spring-transaction`
- `@RestControllerAdvice` / ProblemDetail → `spring-exception-handling`
- Migrations (renames, indexes, backfills) → `spring-db-migration-safety`

**Layer-specific essentials:**

| Layer                 | Non-negotiables                                                                                                                                                                                |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit                  | One test per outcome. Stub HTTP via Mockito on the client interface. `ArgumentCaptor<DomainEvent>` on `ApplicationEventPublisher` for richer assertions than `verify(...)`.                     |
| `@WebMvcTest`         | One test per `(method+path, role, outcome)`. Mock service via `@MockitoBean`. State-changing requests carry `.with(csrf())` exactly when the prod chain enables CSRF (session apps; stateless JWT chains usually disable it) - tests mirror prod. Per protected endpoint: unauthenticated (assert what the prod entry point returns - 401 stateless, 302 to login on form login; with CSRF on, send `.with(csrf())` here too or `CsrfFilter` answers first), wrong-role 403, validation, and non-owner (right role, another user's resource: 403 or 404 per the requirement) where the owner check lives: a controller-level `@PreAuthorize` in the slice with the config imported; service-level or query-scoped (`findByIdAndOwnerId`) checks in `@SpringBootTest` / `@DataJpaTest`. |
| `@DataJpaTest`        | Testcontainers matching production - H2 diverges on JSONB, partial indexes, window functions, `ON CONFLICT`. **The slice replaces any DataSource that is not a test database with an embedded one**: a container wired through `@ServiceConnection` or `@DynamicPropertySource` counts as one (Boot 3.0-3.3: both need `@AutoConfigureTestDatabase(replace = NONE)`); a container that starts but is never wired leaves the test on an embedded database, or fails to start when none is on the classpath. The schema comes from the migrations, not `ddl-auto`. Reuse the project's existing container rather than starting a second one; when the container lives inside a `@SpringBootTest` base a slice cannot extend, hoist it into a shared holder. One test per `@Query` / derived method asserting SQL behavior, not nullability. N+1: with `hibernate.generate_statistics=true`, persist, `flush()` + `clear()`, clear the `Statistics`, run the call plus the caller's mapping, touching every association it reads, assert `getPrepareStatementCount()` - `getQueryExecutionCount()` misses the lazy loads that are the N+1. |
| `@SpringBootTest`     | Reserve for full context (auth flow, outbox, listeners, scheduled jobs). Avoid `@DirtiesContext`.                                                                                               |
| Commit-phase / async  | Test-managed `@Transactional` rolls back, so `AFTER_COMMIT` listeners and every commit-gated effect never run and the test passes asserting nothing. No `@Transactional` on the test (`@DataJpaTest`: `propagation = NOT_SUPPORTED`), clean via `@Sql(..., executionPhase = AFTER_TEST_METHOD)` or `@AfterEach`, assert the listener's **effect**, and wait with Awaitility or `verify(mock, timeout(2000))`. A live `@Scheduled` bean races the test's own invocation - make it conditional on a property the test profile disables, or mock it; a literal `fixedDelay` cannot be turned off from configuration. |
| HTTP stubs            | `@RestClientTest` + `MockRestServiceServer` for one client bean in isolation; WireMock in `@SpringBootTest` when the real client config is the subject; `@MockitoBean` in `@WebMvcTest`; Mockito on the interface in plain unit. Mocking the client whose wiring is under test bypasses the test. |
| Method security       | `@WebMvcTest` skips a separate security config, so `@PreAuthorize` silently no-ops (`spring-test-integration` Security tests): `@Import` it for a **controller-level** one; a **service-level** one needs the real bean (a `@MockitoBean` enforces nothing) in a `@SpringBootTest` with `@EnableMethodSecurity` in scope, positive and denied. |
| JWT authorities       | On a JWT resource server, every hasRole / hasAuthority check is only as real as the JWT converter feeding it: a top-level claim needs authorities-claim-name plus authority-prefix ROLE_; a nested claim (Keycloak realm_access.roles) yields no authorities through setAuthoritiesClaimName - Boot 4.1 authorities-claim-expressions plus authority-prefix ROLE_ (its default prefix is SCOPE_), else a custom converter; the prefix is empty instead when the claim values already carry ROLE_. When the mapping yields nothing, every role gate denies everyone: say so, and never propose a role-based bypass. `jwt()` / `@WithMockUser` inject authorities directly and skip the mapping: each role rule gets one test with the IdP's real claim shape run through the production converter (`spring-test-integration` Security tests). A session chain has no converter: `@WithMockUser(roles = ...)`. |
| Idempotency           | Idempotency key or message dedup: invoke twice sequentially **and** twice concurrently (`CountDownLatch`, real transactions, a gateway stub that counts down a second latch and awaits it with a timeout, so both callers pass the check before either proceeds - `spring-test-integration` Concurrency); each asserts one row + `verify(gateway, times(1))` - a check-then-act dedup passes only the first. A catch-all consumer gets a case asserting retry or dead-letter, not acknowledgement. |
| Publish path          | A mocked `KafkaTemplate` / `RabbitTemplate` skips the converter and serializer, so a publish that throws in production passes. Each publish path gets one real round trip - broker container or `@EmbeddedKafka`, production converter, payload read back and asserted (`spring-test-integration` Broker round trips); no broker: a unit test round-trips the payload through the production converter. |
| Absent test dep       | Any dependency Step 3 recorded absent or unresolvable that this scaffold needs: add or correct it, or name the fallback used (`@EmbeddedKafka` for a missing Kafka container module, the Publish-path converter test for a missing broker, `MockRestServiceServer` for missing WireMock). Either way it goes in `Scaffold notes`. |
| External auth on a client | A client using OAuth2 client credentials fetches its token from a second endpoint the tests must also stub, and overriding only the API base URL leaves the token exchange reaching the real network. Stub the token endpoint and point `spring.security.oauth2.client.provider.<id>.token-uri` at the stub, or mock the authorized-client manager in a slice. |

**No test needed:** Spring-provided behavior (`@Autowired`, route resolution), generated boilerplate (Lombok / MapStruct), trivial pass-through delegation. A generated mapper carrying a hand-written expression, `default` method, or conditional mapping is logic and belongs in the Unit row.

### Step 6 - Test Data

- Builders / factories (Instancio, `OrderTestData.builder()`) over JSON fixtures; records go through their canonical constructor, wrapped in a factory once the argument list is long
- `@Sql("/fixtures/*.sql")` for shared repo setup; per-test data inline
- `flush + clear` only for first-level-cache or query-count assertions (Step 5 `@DataJpaTest`)
- `IntStream.range(0, 100)` setups belong in load tests, not the unit suite

### Step 7 - Prioritize When Coverage Is Low

P0 applies at any coverage; under ~50% line coverage, scaffold in this order - alphabetical scaffolding misses authz holes while plumbing gets covered. With no coverage tooling, use the tested-class ratio (production classes with any test / total production classes) as a rough proxy; report it as an estimate and say it is a class ratio, not line coverage. A class counts as tested only when a test asserts its behavior; a context load, a bean-exists smoke test or an assertion-free test (these go under `Misuse`), or a test a P0 blocker keeps from starting, does not. P1 applies only when an authenticated surface exists; internal consumer/batch services start at P2 (state the skip).

| Priority | Target                                                                                  |
| -------- | --------------------------------------------------------------------------------------- |
| P0 Boots | Step 3 context-start blockers and unresolvable test deps - every context-loading test is red until they are fixed |
| P1 Auth  | `@WebMvcTest` unauthenticated + wrong-role per protected endpoint; non-owner where the owner check lives (Step 5); JWT authority mapping through the production converter (Step 5); JWT issuer/audience/signature/expiry as a `JwtDecoder`-bean unit test or full-context with a local issuer (`jwt()` never calls a decoder, and a slice test stubs `JwtDecoder`); method security per Step 5 |
| P2 Data  | `@DataJpaTest` per repo with `@Query`/derived; write-path happy + rollback; outbox claim and replay              |
| P3 Revenue | Money and notification paths: checkout, billing, subscription transitions, scheduled jobs that charge or notify |
| P4 Churn | High-commit-frequency files (`git log --since="3 months ago"`); bug-fix-heavy files. No history yet -> skip and say so |
| P5 Plumbing | Pass-through controllers, simple CRUD                                                                          |

### Step 8 - Infrastructure Hygiene

Every row goes into the deliverable's `Suite hygiene` slot with its state: `failing` where the practice exists and is wrong, `to establish` where the tooling is not there yet, `ok` omitted. Checked here, reported there.

- [ ] Testcontainers reuse for local cycles: `.withReuse(true)` on a manually started singleton (the JUnit extension stops a `@Container` field) **and** `testcontainers.reuse.enable=true` in `~/.testcontainers.properties` or `TESTCONTAINERS_REUSE_ENABLE=true` - any piece alone is a no-op; CI runs clean
- [ ] `@SpringBootTest` and `@MockitoBean` sparingly - each unique mock set forks the context cache
- [ ] Test profile overrides only what differs from prod; never silently disables security or swaps the migrated schema for `ddl-auto`
- [ ] JUnit parallel execution where safe
- [ ] Mockito strict stubbing (default under `MockitoExtension`)
- [ ] WireMock / Testcontainers for HTTP; no real network
- [ ] JaCoCo in CI with per-module thresholds, generated / boilerplate classes excluded; integration tests in a separate task merge their execution data into the report, or the gate scores the code the ITs cover at zero

## Output Format

Route on the request's verb, not on project state:

| Request                                               | Produce             |
| ----------------------------------------------------- | ------------------- |
| "What's missing?" / "review coverage" / "audit tests" | Coverage Assessment |
| "Write tests for X" / "scaffold tests"                | Test Scaffolds      |
| "Test strategy" / "test plan" / new service           | Strategy Doc        |
| Unclear                                               | Strategy Doc        |

A compound request produces each matched deliverable ("test plan and scaffolding" -> Strategy Doc + Test Scaffolds). When the request targets a whole module or service and the Step 7 estimate lands under ~50%, the Coverage Assessment's `Gaps` content joins the **first** deliverable produced - Test Scaffolds' `Gaps` slot, a Strategy Doc's `Prioritized gaps`, already present in a Coverage Assessment. A request naming flows or classes, one or several, gets no Gaps content.

Composed atomics' Output Formats are never emitted: `spring-test-integration`'s Engine goes to `Stack`, its production changes and suite artifacts to `Scaffold notes` (Coverage Assessment: `Fix in this order`; Strategy Doc: production changes to `Prioritized gaps`, suite artifacts to `Tooling`), its `Contexts` line to `Suite hygiene`, its per-class blocks nowhere; other atomics' Stack lines and finding envelopes fold into this deliverable's slots.

**Coverage Assessment** - the `Blockers`, `Production defects`, `Contract` and `Misuse` lines are omitted when empty:

```markdown
## Spring Boot Test Coverage Assessment

**Stack:** Java <version> / Spring Boot <version> / <database engine> <major>{ - below the floor (<Boot 3.x | Java < 21 | Boot 3.x and Java < 21>)}

**Conventions:** <builder / assertions / auth helper / naming / container base>, each marked (observed) or (chosen - nothing to learn from)

**Tooling present:** <opt-in test dependencies observed; `spring-boot-starter-test` bundles JUnit, Mockito, AssertJ, Awaitility, JSONassert and JsonPath, so those are never "absent" - Boot 4: JUnit 6, brought in by every `-test` starter; Boot 3.x: per Step 2>

**Tooling absent:** <opt-in dependencies a scaffold would need, plus declared ones marked (unresolvable); `None`>

**Coverage:** {<n>% line coverage (JaCoCo) | ~<n>% estimated from tested-class ratio <t>/<c>, a class ratio rather than line coverage | n/a - no production code yet}

**Context start:** <one result per Step 3 check - scan roots, implementations, schema, Framework rejects, inert constructs: `ok` or what fails>

**Gaps:**

- **Blockers:** [context-start blockers and unresolvable test deps]
- **Production defects:** [code-vs-requirement gaps and inert annotations, each with the test that pins the requirement]
- **Unit:** [services / mappers]
- **@WebMvcTest:** [controllers; missing unauthenticated / wrong-role cases]
- **@DataJpaTest:** [repos with @Query / derived; H2 or `ddl-auto` schema flagged]
- **Security:** [endpoints without authz; missing non-owner cases; inert `@PreAuthorize`; JWT authorities unmapped or untested through the converter; missing JWT flow]
- **Full-context:** [transactional flows, listeners, jobs]
- **External boundaries:** [client beans, mail senders, and any other real-network side effect with no stubbed test]
- **Contract:** [provider/consumer, or event schemas downstream consumers depend on]
- **Misuse:** [wrong slice, H2 in `@DataJpaTest`, `@DirtiesContext`, context-cache forking, security disabled in the test profile, publish paths covered only by mocked templates, tests asserting nothing]

**Suite hygiene:** [Step 8 rows with their state; `None`]

**Recommended balance:** Unit {x}% / Slice {y}% / Full-context+E2E {z}% of test methods

**Fix in this order:**

1. [by the Step 7 priority ladder, P0 first, rather than by the layer order above]
2. [...]
```

**Test Scaffolds** - ready-to-run JUnit files, preceded by this header:

```markdown
## Spring Boot Test Scaffolds

**Stack:** <as above>

**Conventions:** <as above>

**Coverage:** <as above>

**Context start:** <as above>

**Files:**

- `<path>` - <what it covers; mark an edit to an existing file as (edit)>

**Production defects:** <P0 blockers, code-vs-requirement gaps and inert annotations found while reading, each with the test that pins the requirement (for a retry: no retry of a non-idempotent money call without an idempotency key), never an inert annotation's intent, or `no test pins it`; `None`>

**Publish paths:** <each send site -> its round-trip or converter test; `None`>

**Scaffold notes:** <what the scaffold forced: dependencies to add or correct, the fallback used for an absent dep, wiring the project's container setup required, scheduler or async races handled, production changes the tests depend on; `None`>

**Suite hygiene:** <Step 8 rows with their state; `None`>

**Deferred:** <targets left for a next round, each with its reason; `None`>

**Gaps:** <the Coverage Assessment's Gaps list>
```

Then the files themselves:

- Right test type per target; layout mirrors the prod package under `src/test/java`
- Naming `<Class>Test` (unit / slice), `<Flow>IT` (full-context) - on Maven `*IT` runs under Failsafe, so the build must bind it
- Security cases live in the same controller slice class as the functional tests unless the existing suite separates `*SecurityTest` classes
- Builders / factories over ad-hoc construction, records through their canonical constructor (Step 6)
- Cases per the Step 5 rows; names per the resolved major
- Inline comments only where non-obvious (e.g., why `.with(csrf())`)

**Strategy Doc:**

```markdown
## Spring Boot Test Strategy

**Objective:** [what this achieves]

**Stack:** <as above>

**Conventions:** <as above>

**Coverage:** <as above>

**Context start:** <as above>

**Publish paths:** <as above>

**Pyramid balance:** Unit {x}% / Slice {y}% / Full-context+E2E {z}% of test methods

**Tooling:** <what the suite will use, marking which are not yet on the classpath>

**DB isolation:** [singleton Testcontainers base; schema from migrations; transactional rollback, or committed + `@Sql` / `@AfterEach` cleanup for commit-gated and `@Async` flows]

**Concurrency:** [JUnit parallel config]

**Suite hygiene:** [Step 8 rows with their state, including the CI coverage gate when one is required]

**Prioritized gaps:**

1. [By the Step 7 priority ladder, production defects included - P0 blockers, then authz or repository correctness]
2. [...]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed as Spring Boot; Boot and Java versions read from the build; every emitted construct binds on them
- [ ] Step 3: code, requirement, tests and test deps read; every context-start check reported
- [ ] Step 4: percentages derived by the fill rule
- [ ] Step 5: `spring-test-integration` and each present construct's atomic loaded; every layer row applied
- [ ] Step 6: builders / factories over JSON fixtures; flush + clear only for cache or query-count assertions
- [ ] Step 7: the priority ladder ordered the work, P0 first
- [ ] Step 8: every row's state in `Suite hygiene`
- [ ] Deliverable routed on the request verb; every slot filled per its condition; composed atomics' outputs mapped, never emitted

## Avoid

- Scaffolding before reading existing tests - wrong builder, wrong assertions, duplicated base class
- Chasing coverage % instead of prioritizing by risk
- `@SpringBootTest` where `@WebMvcTest`, `@RestClientTest`, or a plain unit test suffices
- `verify(repository).save(any())` when `@DataJpaTest` could assert persistence
- Asserting that an event was published instead of asserting what its listener did
- `Thread.sleep` to wait for async work
- Testing Spring internals (`@Autowired`, `@RequestMapping` resolution)
