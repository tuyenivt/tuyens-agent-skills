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

**Not for:** test failure debugging (`task-spring-debug`), code review (`task-code-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-confirmed stack. If not Spring Boot, stop and direct the user to `/task-code-test`.

### Step 3 - Read Code Under Test and Existing Tests

Scaffolds must match project conventions, not generic templates.

- Target classes top-to-bottom: methods, DTOs, security annotations, transaction boundaries, collaborators
- At least one existing `@WebMvcTest`, `@DataJpaTest`, service unit test - learn builders (Instancio / `@RecordBuilder` / static factories), assertion library, auth helpers (`@WithMockUser` vs custom `JwtRequestPostProcessor`)
- `application-test.{properties,yml}` and any `IntegrationTestBase` / `TestContainersConfig` - reuse container setup
- `build.gradle(.kts)` / `pom.xml` test deps - confirm Testcontainers, Instancio, AssertJ, Spring Cloud Contract, REST Assured presence

If no existing tests, state conventions explicitly in the strategy.

### Step 4 - Map the Pyramid

| Layer        | Annotation / type                                  | Scope                                                                  |
| ------------ | -------------------------------------------------- | ---------------------------------------------------------------------- |
| Unit         | JUnit 5 + Mockito, no Spring                       | Service logic, mappers, validators, calculations, state machines       |
| Slice        | `@WebMvcTest` / `@DataJpaTest` / `@JsonTest`       | Controller routing/binding/validation; repo queries; serialization     |
| Full-context | `@SpringBootTest` + Testcontainers                 | End-to-end auth, transactional outbox, listeners, scheduled jobs       |
| Contract     | Spring Cloud Contract / Pact                       | Consumer/provider API contracts                                        |
| E2E          | `@SpringBootTest(RANDOM_PORT)` + REST Assured      | Critical journeys only (signup, checkout, payment)                     |

Many unit, some slice, few full-context / E2E. `@SpringBootTest` is slow - reserve it. For the percentage fields below, default to 65/25/10 (unit/slice/full-context+E2E; contract tests tracked separately), shifting 5-10 points toward slice for repository/controller-heavy services. State it as a target, not a measured value.

### Step 5 - Apply Patterns

Use skill: `spring-test-integration` for canonical patterns - load once, reference rather than restate. Compose as scope demands:

- Auth (`@WithMockUser`, `jwt()`, method security) → `spring-security-patterns`
- `@Async` / `@Scheduled` / event listeners → `spring-async-processing`
- Kafka / Rabbit / outbox / idempotent listeners → `spring-messaging-patterns`
- `@DataJpaTest` N+1 (`Statistics.getQueryExecutionCount()`), fetch graphs → `spring-jpa-performance`
- `@TransactionalEventListener` phase, `REQUIRES_NEW` → `spring-transaction` (`@RecordApplicationEvents` usage: `@SpringBootTest` row below)
- `@RestControllerAdvice` / ProblemDetail → `spring-exception-handling`

**Layer-specific essentials:**

| Layer            | Non-negotiables                                                                                                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Unit             | One test per outcome. Stub HTTP via Mockito on client interface. `ArgumentCaptor<DomainEvent>` on `ApplicationEventPublisher` for richer assertions than `verify(...)`.                        |
| `@WebMvcTest`    | One test per `(method+path, role, outcome)`. Mock service via `@MockitoBean`. State-changing methods need `.with(csrf())` when the prod chain has CSRF enabled (session-based apps); stateless JWT chains with CSRF disabled omit it - tests mirror prod. 401 (anonymous) + 403 (wrong role) + validation per protected endpoint. |
| `@DataJpaTest`   | Testcontainers Postgres via `@ServiceConnection` - H2 diverges on JSONB, partial indexes, window functions, `ON CONFLICT`. One test per `@Query` / derived method asserting SQL behavior, not nullability. |
| `@SpringBootTest`| Reserve for full context (auth flow, outbox, listeners, scheduled jobs). `@Transactional` rollback fails for `@Async` threads - drop it and clean via `@Sql(AFTER_TEST_METHOD)`. Use `@RecordApplicationEvents` for `BEFORE_COMMIT` vs `AFTER_COMMIT`. Avoid `@DirtiesContext`. |
| HTTP stubs       | WireMock in `@SpringBootTest` (exercises real `RestClient` config); `@MockitoBean` in `@WebMvcTest`; Mockito on interface in plain unit. Mocking `RestClient` in integration bypasses the wiring under test. |
| Idempotency      | Code accepting an idempotency key: invoke twice, assert single DB row + `verify(gateway, times(1))`.                                                                                            |

**No test needed:** Spring-provided behavior (`@Autowired`, route resolution), Lombok / MapStruct boilerplate, trivial pass-through delegation.

### Step 6 - Test Data

- Builders / factories (Instancio, `OrderTestData.builder()`) over JSON fixtures
- `@Sql("/fixtures/*.sql")` for shared repo setup; per-test data inline
- Records: instantiate via constructor
- Avoid `flush + clear` unless asserting first-level-cache behavior
- `IntStream.range(0, 100)` setups belong in load tests, not unit suite

### Step 7 - Prioritize When Coverage Is Low

When line coverage < ~50% (no coverage tooling: estimate from the test-class-to-class ratio and state the estimate), scaffold in this order - alphabetical scaffolding misses authz holes while plumbing gets covered.

| Priority | Target                                                                                  |
| -------- | --------------------------------------------------------------------------------------- |
| P1 Auth  | `@WebMvcTest` 401/403 per protected endpoint; JWT issuer/audience/signature/expiry (as a `JwtDecoder`-bean unit test or full-context with a local issuer - the `@WebMvcTest` slice stubs the decoder, so they cannot fire there); service-layer `@PreAuthorize` |
| P2 Data  | `@DataJpaTest` per repo with `@Query`/derived; write-path happy + rollback; outbox idempotency                    |
| P3 Revenue | Checkout, billing, subscription transitions; scheduled jobs touching money / notifications                       |
| P4 Churn | High-commit-frequency files (`git log --since="3 months ago"`); bug-fix-heavy files                              |
| P5 Plumbing | Pass-through controllers, simple CRUD                                                                          |

### Step 8 - Infrastructure Hygiene

- [ ] Testcontainers reusable mode (`testcontainers.reuse.enable=true`) for local cycles
- [ ] `@SpringBootTest` and `@MockitoBean` sparingly - each unique mock set forks the context cache
- [ ] Test profile overrides only what differs from prod; never silently disables security
- [ ] JUnit 5 parallel execution where safe
- [ ] Mockito strict stubbing (default under the JUnit 5 `MockitoExtension`)
- [ ] WireMock / Testcontainers for HTTP; no real network
- [ ] JaCoCo in CI with per-module thresholds; generated / boilerplate classes excluded from thresholds

## Output Format

Pick by request shape:

| Request                                       | Produce                                       |
| --------------------------------------------- | --------------------------------------------- |
| "What's missing?" / "review coverage"         | Coverage Assessment                           |
| "Write tests for X" / "scaffold tests"        | Test Scaffolds                                |
| "Test strategy" / "test plan" / coverage <50% | Strategy Doc (+ optional Coverage Assessment) |
| Unclear                                       | Strategy Doc                                  |

Compound requests produce each matched deliverable (e.g. "test plan and scaffolding" -> Strategy Doc + Test Scaffolds).

**Coverage Assessment:**

```markdown
## Spring Boot Test Coverage Assessment

**Stack:** Java <version> / Spring Boot <version>
**Tooling:** JUnit 5, Mockito, AssertJ, Spring Boot Test, Testcontainers

**Gaps:**
- **Unit:** [services / mappers]
- **@WebMvcTest:** [controllers; missing 401/403]
- **@DataJpaTest:** [repos with @Query / derived; H2-only flagged]
- **Security:** [endpoints without authz; missing JWT flow]
- **Full-context:** [transactional flows, listeners, jobs]
- **Contract:** [provider/consumer]

**Recommended balance:** Unit {x}% / Slice {y}% / Full-context+E2E {z}% (Step 4 fill rule)
```

**Test Scaffolds** - ready-to-run JUnit 5 files in project conventions:

- Right test type per target
- Layout mirrors the prod package under `src/test/java`; naming `<Class>Test` (unit / slice), `<Flow>IT` (full-context) - unless existing tests establish another convention (Step 3 wins)
- Full-context tests share a singleton-container base class (per `spring-test-integration`); create it when absent
- Security cases (401/403/role) live in the same controller slice class as the functional tests unless the existing suite separates `*SecurityTest` classes
- Builders / factories (not `new Order(...)`)
- Controllers: happy + 401 + 403 + validation-error
- Repos: Testcontainers via `@ServiceConnection`; Postgres semantics
- Security: `@WithMockUser` / `.with(jwt())` / anonymous; positive and denied
- Inline comments only where non-obvious (e.g., why `.with(csrf())`)
- `spring-test-integration`'s per-class output blocks go in the Strategy Doc (when produced), never inside scaffold files

**Strategy Doc:**

```markdown
## Spring Boot Test Strategy

**Objective:** [what this achieves]
**Pyramid balance:** Unit {x}% / Slice {y}% / Full-context+E2E {z}% (Step 4 fill rule)
**Tooling:** JUnit 5, Mockito (strict), AssertJ, Spring Boot Test, Testcontainers (Postgres / Kafka), Spring Security Test
**DB isolation:** [singleton Testcontainers Postgres base + @ServiceConnection; transactional rollback, or @Sql cleanup for @Async / @Scheduled flows]
**Concurrency:** [JUnit parallel config]

**Prioritized gaps:**
1. [Highest-risk - typically authz or repository correctness]
2. [...]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed as Spring Boot
- [ ] Step 3: code under test and representative existing tests read
- [ ] Step 4: pyramid mapped to Spring slice annotations
- [ ] Step 5: `spring-test-integration` consulted; layer non-negotiables applied (Testcontainers over H2; CSRF; auth coverage; `@RecordApplicationEvents` for phases)
- [ ] Step 6: builders / factories over JSON fixtures
- [ ] Step 7: when coverage low, P1 auth and P2 data scaffolded before plumbing
- [ ] Step 8: infrastructure hygiene applied (context cache, strict stubbing, no real network)

## Avoid

- Scaffolding before reading existing tests - wrong builder, wrong assertions, duplicated base class
- Chasing coverage % instead of prioritizing by risk
- `@SpringBootTest` where `@WebMvcTest` or unit suffices
- H2 in `@DataJpaTest` for Postgres-feature apps
- `verify(repository).save(any())` when `@DataJpaTest` could assert persistence
- Disabling CSRF in tests to avoid `.with(csrf())` when prod has it enabled - the test no longer mirrors prod
- Skipping `@PreAuthorize` tests because the controller has `@WebMvcTest` - method security tests separately
- Testing Spring internals (`@Autowired`, `@RequestMapping` resolution)
- `@DirtiesContext` as a shared-state workaround - fix isolation instead
