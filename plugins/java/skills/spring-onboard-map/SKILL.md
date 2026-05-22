---
name: spring-onboard-map
description: "Spring Boot onboarding signals: build system, application.yml profiles, persistence, security, package layout, risk hotspots, first-PR safe zones."
metadata:
  category: backend
  tags: [onboarding, codebase-map, spring, maven, gradle]
user-invocable: false
---

# Spring Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-onboard` when the stack is Java / Spring Boot.

## When to Use

- A workflow needs Spring-specific orientation signals: where things live, how to run locally, what conventions matter, where the risks concentrate
- The project has `pom.xml` or `build.gradle(.kts)` and a Spring Boot main class

## Rules

- Identify build system (Maven vs Gradle) and Spring Boot version first - structure varies
- Locate `@SpringBootApplication` first; its package is the component-scan root
- `application.yml` and its profile variants are the runtime-behavior map - inventory every `application-<profile>.yml`
- Identify the persistence stack (JPA / JDBC / MyBatis / R2DBC / none) before describing data flow
- Identify the security config class. On Boot 3+ this is a `SecurityFilterChain` bean; any `WebSecurityConfigurerAdapter` extension is on an unsupported version (migration is itself an onboarding signal). If no security config exists, state which autoconfigured default applies (`spring-boot-starter-security` present = HTTP basic + generated password; absent = no auth)
- Build a route inventory by grepping `@RequestMapping` / `@GetMapping` etc.; cross-reference each route with `SecurityFilterChain.requestMatchers(...)` so the new engineer knows which routes are public / authenticated / role-restricted

## Patterns

### Build system inventory

| File                                | Signal                                                                                   |
| ----------------------------------- | ---------------------------------------------------------------------------------------- |
| `pom.xml`                           | Maven; check `<parent>` for `spring-boot-starter-parent` and Java version                |
| `build.gradle(.kts)`                | Gradle; check `plugins` for `org.springframework.boot` and `java.toolchain`              |
| `settings.gradle(.kts)` or multi-module `pom.xml` | Multi-module                                                                |
| `gradle/libs.versions.toml`         | Gradle version catalog                                                                   |
| `mvnw` / `gradlew`                  | Use the wrapper, never the system tool                                                   |

### Bootstrap path (clone → running app)

1. Java toolchain: confirm version matches `java -version` (Boot 3.x needs Java 17+; 3.2+ commonly 21)
2. Local services: scan `compose.yml` / `docker-compose.yml` for required dependencies (Postgres, Redis, Kafka)
3. Active profile: `spring.profiles.active` in `application.yml` or `SPRING_PROFILES_ACTIVE` env
4. DB migration tool: Flyway (`src/main/resources/db/migration/`) or Liquibase (`db/changelog/`) - migrations run at startup
5. Run: `./mvnw spring-boot:run` or `./gradlew bootRun`; default port 8080 unless `server.port` overrides
6. Verify: `/actuator/health`; if `springdoc-openapi` present, OpenAPI at `/v3/api-docs`, Swagger UI at `/swagger-ui.html`

### Key file inventory

| Location                                    | Purpose                                                       |
| ------------------------------------------- | ------------------------------------------------------------- |
| `src/main/java/.../<App>Application.java`   | `@SpringBootApplication`; package = component-scan root       |
| `src/main/resources/application.yml`        | Default config + profile keys                                 |
| `src/main/resources/db/migration/`          | Flyway versioned migrations                                   |
| `src/main/resources/db/changelog/`          | Liquibase changesets                                          |
| `.../config/`                               | `@Configuration` - security, JPA, web, async                  |
| `.../controller/` (or `web/`, `api/`)       | `@RestController` / `@Controller`                             |
| `.../service/`                              | `@Service` + transaction boundaries                           |
| `.../repository/` (or `dao/`)               | Persistence                                                   |
| `.../domain/` (or `model/`, `entity/`)      | Entities and value objects                                    |
| `src/test/resources/application-test.yml`   | Test profile (Testcontainers / H2)                            |

### Conventions to extract

- **Package layout**: feature-package (`com.acme.order.{controller,service,repository}`) - modern preference, cross-feature imports become visible. Or layer-package (`com.acme.controller.*`, `com.acme.service.*`).
- **Layering**: controller → service → repository. Flag deviations (business logic in controllers, repository access from controllers).
- **DTO vs entity at API boundary**: do `@RestController` methods return entities or records/DTOs? Direct entity exposure is a red flag.
- **Exception handling**: `@RestControllerAdvice` / `@ControllerAdvice` - if absent, errors leak Spring defaults.
- **Validation**: `@Valid` on controller args + JSR-380 on DTOs.
- **Transaction placement**: `@Transactional` at service layer is correct; on controllers/repositories is a smell.
- **Bean naming**: explicit `@Component("name")` is rare; default is class name camelCased.
- **Logging**: SLF4J via `LoggerFactory` or Lombok `@Slf4j`; per-package levels in `logging.level`.

### Risk hotspots

Surface as orientation signals; defer depth to the atomic that owns each topic:

- **Proxy self-invocation** on `@Transactional` / `@Async` / `@Cacheable` / `@PreAuthorize` (see `spring-transaction`)
- **OSIV state**: `spring.jpa.open-in-view` true or default - masks N+1 / LIE (see `spring-jpa-performance`)
- **`@PostConstruct` heavy work** - delays startup, runs before health checks
- **Custom `scanBasePackages`** - classes outside listed packages are invisible
- **Multiple `DataSource` / `PlatformTransactionManager` without `@Primary`** - ambiguous wiring
- **Custom `Filter` / `OncePerRequestFilter` without explicit order** - undefined position vs Spring Security
- **`@EnableAsync` without a `TaskExecutor` bean** - unbounded `SimpleAsyncTaskExecutor` (see `spring-async-processing`)
- **JPA entities with Lombok `@Data`** - generated `equals`/`hashCode`/`toString` traverse lazy associations
- **Flyway `out of order` enabled** - dev/CI/prod schema drift is invisible

### First-PR safe zones

- New endpoint on an existing controller using established patterns
- New DTO field (with validation) without schema change
- New test in `src/test/java/...` exercising an existing service method
- INFO-level log statement following the existing logger pattern
- New `application.yml` property with `@ConfigurationProperties` and a default that preserves current behavior

Riskier:
- Anything in `config/` (one bean change rewires the context)
- JPA entity changes (cascade across migrations, queries, serialization)
- Spring Security config (silent failures)
- Schema migrations (irreversible in prod without backout)

### Currency signals

- Boot 3.x = Jakarta EE namespace; pre-3.x = `javax.*`. Mixing is a runtime error.
- Java 21 + `spring.threads.virtual.enabled=true` puts controllers on Virtual Threads.
- Constructor injection (`@RequiredArgsConstructor`) is modern; `@Autowired` field injection is legacy.
- Slice tests (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`) over full-context `@SpringBootTest`.

## Output Format

Inject into the parent workflow's output sections:

**Stack and Tooling:**
- Build system, Spring Boot version, Java version, key starter dependencies
- Persistence layer + migration tool
- Web (Spring MVC / WebFlux), security (present / absent / autoconfigured)

**Local Bootstrap:**
- Exact run command (`./mvnw spring-boot:run` or `./gradlew bootRun`)
- Required local services (from `compose.yml` or external URLs in `application-*.yml`)
- Profile inventory: every `application-<profile>.yml` discovered, the default profile, override mechanism
- Default port and actuator base path

**Architecture Map:**
- Component-scan root package
- Layer directories with file counts
- `@Configuration` classes and what each wires
- Cross-cutting: `@RestControllerAdvice`, custom filters, AOP aspects
- Route table: HTTP method + path → controller method, with auth requirement from `SecurityFilterChain`

**Conventions:**
- DTO vs entity at API boundary
- Transaction placement
- Validation strategy
- Logging idiom

**Risk Hotspots:**
- Self-invocation in annotated services
- OSIV state
- Custom security filter ordering
- `@PostConstruct` heavy work
- Async without configured `TaskExecutor`

**First-PR Safe Zones:**
- The list above, scoped to the observed structure

## Avoid

- Describing layout from generic Spring docs without reading the actual file tree
- Listing every `@Configuration` class - focus on those wiring cross-cutting concerns
- Treating Spring autoconfiguration as invisible - name which starters pull in what
- Recommending Java 8 / Boot 2.x patterns on a Boot 3.x project
- Skipping `application.yml` profile inventory - that's where runtime behavior lives
- Listing every dependency - focus on starters, persistence, security, observability
