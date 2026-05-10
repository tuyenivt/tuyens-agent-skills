---
name: spring-onboard-map
description: "Spring Boot / Java onboarding signals: Maven/Gradle layout, application.yml profiles, config classes, persistence, security, starters."
metadata:
  category: backend
  tags: [onboarding, codebase-map, spring, maven, gradle]
user-invocable: false
---

# Spring Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Java / Spring Boot.

## When to Use

- A workflow needs Spring-specific orientation signals: where things live, how to bootstrap locally, what conventions matter, where the risk concentrations are.
- The project has `pom.xml` or `build.gradle(.kts)` and a Spring Boot main class.

## Rules

- Always identify the build system (Maven vs Gradle) and the Spring Boot version before describing layout - module structure differs between Maven multi-module and Gradle composite/multi-project builds.
- Locate the `@SpringBootApplication` main class first; the package containing it is the component scan root and defines what gets auto-wired.
- Treat `application.yml` (and its profile variants) as the single source of truth for runtime configuration - never describe behavior without mapping which property drives it.
- Identify the persistence stack (JPA/Hibernate, JDBC, MyBatis, R2DBC, none) before discussing data flow - it changes everything downstream.
- Identify the security configuration class - on Spring Boot 3+ this is a `@Configuration` declaring one or more `SecurityFilterChain` beans (the legacy `WebSecurityConfigurerAdapter` was removed in Spring Security 6 / Spring Boot 3, so any code still extending it is on an unsupported version and the migration is itself an onboarding signal). If no security configuration class exists, the project is on the autoconfigured default - state which one (`spring-boot-starter-security` present means HTTP basic + a generated password printed to logs; absent means no auth at all).
- Enumerate every `application-<profile>.yml` discovered. For each, list which keys override the base `application.yml` - this is the dev/staging/prod map a new engineer needs to read before changing config.
- Build a route inventory by grepping `@RequestMapping` / `@GetMapping` / `@PostMapping` / `@PutMapping` / `@DeleteMapping` / `@PatchMapping` at class and method level. Cross-reference each route with `SecurityFilterChain.requestMatchers(...)` so the new engineer knows which routes are public, authenticated, or role-restricted.

## Patterns

### Build System Inventory

| File / location           | What it tells you                                                                        |
| ------------------------- | ---------------------------------------------------------------------------------------- |
| `pom.xml` (root)          | Maven; check `<parent>` for `spring-boot-starter-parent` and Java version in `<properties>`           |
| `build.gradle(.kts)`      | Gradle; check `plugins` for `org.springframework.boot` and `java.toolchain.languageVersion` |
| `settings.gradle(.kts)` / multi-module `pom.xml` | Multi-module project; each module has its own dependency set                       |
| `gradle/libs.versions.toml` | Gradle version catalog; central dependency-version source                              |
| `mvnw` / `gradlew`        | Wrapped build; use `./mvnw` or `./gradlew` for local commands - never the system Maven  |

### Bootstrap Path (clone -> running app)

Standard sequence to surface to the new engineer:

1. Java toolchain: confirm version from `pom.xml`/`build.gradle` matches local `java -version` (Spring Boot 3.x requires Java 17+; Boot 3.2+ commonly Java 21).
2. Local services: scan `compose.yml` / `docker-compose.yml` for required dependencies (Postgres, Redis, Kafka, etc.). If absent, check `application-*.yml` for connection URLs to identify external dependencies.
3. Config: identify which profile is the default (`spring.profiles.active` in `application.yml`, or `SPRING_PROFILES_ACTIVE` env). Local dev typically uses `local` or `dev`.
4. DB migration: detect Flyway (`src/main/resources/db/migration/`) or Liquibase (`src/main/resources/db/changelog/`). Run via `./mvnw spring-boot:run` or `./gradlew bootRun` - migrations execute at startup.
5. Run: `./mvnw spring-boot:run` (Maven) or `./gradlew bootRun` (Gradle). Surface the default port (8080 unless `server.port` overrides).
6. Verify: identify the actuator base path (default `/actuator`) and at minimum check `/actuator/health`. If `springdoc-openapi` is on the classpath, the OpenAPI document is at `/v3/api-docs` and Swagger UI at `/swagger-ui.html` - surface these as the API exploration entry point.

### Key File Inventory

| Location                                         | Purpose                                                                                          |
| ------------------------------------------------ | ------------------------------------------------------------------------------------------------ |
| `src/main/java/.../<App>Application.java`        | Main class; `@SpringBootApplication` package = component-scan root                               |
| `src/main/resources/application.yml`             | Default config + the profile keys; profile-specific variants in `application-<profile>.yml`      |
| `src/main/resources/db/migration/`               | Flyway migrations (versioned: `V1__init.sql`, `V2__add_index.sql`)                               |
| `src/main/resources/db/changelog/`               | Liquibase changesets                                                                             |
| `src/main/resources/static/` / `templates/`      | Static assets / Thymeleaf templates (only present for non-API apps)                              |
| `src/main/java/.../config/`                      | `@Configuration` classes - `WebSecurityConfig`, `JpaConfig`, `WebMvcConfig`, etc.                |
| `src/main/java/.../controller/` (or `web/`, `api/`) | HTTP entry points (`@RestController`, `@Controller`)                                          |
| `src/main/java/.../service/`                     | Business logic, transaction boundaries (`@Service` + `@Transactional`)                           |
| `src/main/java/.../repository/` (or `dao/`)      | Persistence; Spring Data JPA interfaces or custom repositories                                   |
| `src/main/java/.../domain/` (or `model/`, `entity/`) | JPA entities and value objects                                                              |
| `src/test/java/...`                              | Tests; mirror main package structure                                                             |
| `src/test/resources/application-test.yml`        | Test-only profile (often points to Testcontainers or H2)                                         |

### Conventions to Extract by Reading the Code

- **Package layout:** two common shapes - **feature-package** (`com.acme.order.{controller,service,repository}`, `com.acme.payment.{controller,service,repository}`) or **layer-package** (`com.acme.controller.*`, `com.acme.service.*`, `com.acme.repository.*`). Modern Boot 3+ projects increasingly favor feature-package because cross-feature imports become visible (a `payment` package importing from `order` signals coupling). Identify which shape applies before describing where files live.
- **Layering:** controller -> service -> repository is the default. Detect deviations: business logic in controllers, repository access from controllers, services calling other controllers.
- **DTO vs entity at API boundary:** check whether `@RestController` returns JPA entities directly or maps to records/DTOs. Direct entity exposure is a red flag.
- **Exception handling:** look for `@RestControllerAdvice` / `@ControllerAdvice` - this defines the team's error contract. If absent, errors leak Spring defaults.
- **Validation:** `@Valid` on controller arguments + JSR-380 annotations on DTOs is the standard. `@Validated` at class level enables method-parameter validation.
- **Transaction placement:** `@Transactional` at the service layer is correct. On controllers or repositories is a smell.
- **Bean naming:** explicit `@Component("name")` is rare; default is class name camelCased. Multiple beans of the same type need `@Qualifier`.
- **Logging:** SLF4J via `LoggerFactory.getLogger(...)` or Lombok's `@Slf4j`. Log levels configured per package in `application.yml` under `logging.level`.

### Risk Hotspots Specific to Spring

Surface these as orientation signals; defer depth to the atomic skill that owns each topic:

- **Proxy self-invocation** on `@Transactional` / `@Async` / `@Cacheable` / `@PreAuthorize` (see `spring-transaction`)
- **OSIV state**: `spring.jpa.open-in-view` set to `true` or omitted (default applies) - silently masks N+1 and `LazyInitializationException` (see `spring-jpa-performance`)
- **`@PostConstruct` heavy work**: delays startup; runs before health checks
- **`@SpringBootApplication` with non-default `scanBasePackages`**: classes outside listed packages are invisible
- **Multiple `DataSource` / `PlatformTransactionManager` beans without `@Primary`**: ambiguous wiring, startup failure
- **Custom `Filter` / `OncePerRequestFilter` without explicit order**: undefined position relative to Spring Security
- **`@EnableAsync` without a `TaskExecutor` bean**: falls back to `SimpleAsyncTaskExecutor`, unbounded thread per call (see `spring-async-processing`)
- **JPA entities annotated with Lombok `@Data`**: generated `equals`/`hashCode`/`toString` traverse lazy associations
- **Flyway `out of order` enabled**: dev/CI/prod schema drift is invisible

### First-PR Safe Zones

Good first changes that minimize blast radius for a new engineer:

- Adding a new endpoint to an existing `@RestController` (controller -> service -> existing repository) using established patterns.
- Adding a field to a DTO (and its validation) without changing the underlying entity schema.
- Adding a new test in `src/test/java/...` that exercises an existing service method.
- Adding a log statement at INFO level following the existing logger pattern.
- Adding a property to `application.yml` and a `@ConfigurationProperties` field, with a default that preserves current behavior.

Riskier areas to flag:

- Anything in `config/` - one bean change can rewire the whole context.
- JPA entity changes - cascade across migrations, queries, and serialization.
- Spring Security configuration - silent failures (filters in wrong order, missing CSRF, etc.).
- Schema migrations - irreversible in production without a backout migration.

### Ecosystem Currency Signals

- Spring Boot 3.x: Jakarta EE namespace (`jakarta.persistence`, `jakarta.servlet`); pre-3.x uses `javax.*`. Mixing is a runtime error.
- Java 21: virtual threads available via `spring.threads.virtual.enabled=true`. If absent, controllers run on platform threads from the Tomcat pool.
- Constructor injection (often via Lombok `@RequiredArgsConstructor`) is the modern default; `@Autowired` field injection is legacy.
- `@SpringBootTest` slices (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`) over full-context tests for speed.

## Output Format

This atomic produces signals consumed by `task-onboard`. Inject the following into the parent workflow's output sections:

**Into "Stack and Tooling":**

- Build system (Maven / Gradle), Spring Boot version, Java version, key starter dependencies
- Persistence layer (JPA / JDBC / MyBatis / none) and migration tool (Flyway / Liquibase / none)
- Web layer (Spring MVC / WebFlux), security (Spring Security present / absent / autoconfigured default)

**Into "Local Bootstrap":**

- Exact command to run the app (`./mvnw spring-boot:run` or `./gradlew bootRun`)
- Required local services (from `compose.yml` or external connection strings in `application-*.yml`)
- Profile inventory: every `application-<profile>.yml` discovered, the default profile, and the override mechanism (`spring.profiles.active` / `SPRING_PROFILES_ACTIVE`)
- Default port and actuator base path

**Into "Architecture Map":**

- Component-scan root package
- Layer directories (controller / service / repository / domain) with file counts
- `@Configuration` classes and what each configures
- Cross-cutting concerns: `@RestControllerAdvice`, custom filters, AOP aspects
- Route table: HTTP method + path -> controller method, with auth requirement read from `SecurityFilterChain` matchers (public / authenticated / role-restricted)

**Into "Conventions":**

- DTO vs entity at API boundary
- Transaction placement (service layer vs other)
- Validation strategy (`@Valid` + JSR-380)
- Logging idiom (SLF4J / Lombok `@Slf4j`)

**Into "Risk Hotspots":**

- Self-invocation patterns in annotated services
- OSIV state (`spring.jpa.open-in-view`)
- Custom security filter ordering
- `@PostConstruct` heavy work
- Async without configured `TaskExecutor`

**Into "First-PR Safe Zones":**

- The list above, scoped to the actual project structure observed

## Avoid

- Describing project layout from generic Spring docs without reading the actual file tree - module boundaries vary
- Listing every `@Configuration` class - focus on the ones that wire cross-cutting concerns
- Treating Spring autoconfiguration as invisible - call out which starters are pulling in what
- Recommending Java 8 / Spring Boot 2.x patterns when the project is on 3.x (Jakarta namespace, virtual threads, records)
- Skipping `application.yml` profile inventory - that is where the runtime behavior actually lives
- Listing every dependency - focus on starters, persistence, security, observability stack
