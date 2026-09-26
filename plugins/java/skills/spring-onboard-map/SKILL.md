---
name: spring-onboard-map
description: "Spring Boot onboarding signals: build, profiles, ConfigurationProperties, persistence, security chain, scan roots, risks, safe zones."
metadata:
  category: backend
  tags: [onboarding, codebase-map, spring, maven, gradle]
user-invocable: false
---

# Spring Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack; its fields seed **Stack and Tooling** and every field is re-checked against the build files - a disagreement (a `## Tech Stack` saying Java 17 over a toolchain of 21) is written `Conflicting: <doc> vs <build>` and raised as a hotspot. Composed by `task-onboard` when the stack is Java / Spring Boot.

## When to Use

Workflow needs Spring-specific orientation: where code lives, how to run it, what wires the context, where risk concentrates. Triggered when `pom.xml` / `build.gradle(.kts)` + a `@SpringBootApplication` class exist. Also works from a partial file set - every section then says what was not observed.

## Rules

- Identify build system, Boot version, Java toolchain before anything else - structure varies.
- Locate the `@SpringBootApplication` package = component-scan root. Flag any `scanBasePackages`, `@ComponentScan`, `@EntityScan`, `@EnableJpaRepositories` that diverge from it - beans, entities or repositories outside the declared roots are invisible.
- Inventory every `application-<profile>.yml` / `.properties` and state which value wins, highest first: devtools global settings (when devtools is present) > test overrides (`@DynamicPropertySource`, `@TestPropertySource`, `@SpringBootTest(properties)`) > command-line args > `SPRING_APPLICATION_JSON` > Java system properties (`-D`) > OS env vars (relaxed binding: `SERVER_PORT` -> `server.port`) > external `application-<profile>` > external `application` > packaged `application-<profile>` > packaged `application` > `@PropertySource`. Within one location `.properties` beats `.yml`; a `spring.config.import`ed file overrides the file that imports it. Note the `spring.profiles.active` default.
- List `@ConfigurationProperties` classes - typed config beats grepping yml for keys. A class is a live binding only when registered (`@ConfigurationPropertiesScan`, `@EnableConfigurationProperties(X.class)`, or `@Component`); an unregistered one is a hotspot.
- Identify persistence stack(s) - JPA / JDBC / MyBatis / R2DBC / none (several may coexist) - every `DataSource` bean, and the migration tool. Name which one owns the schema. Two schema authorities is a misconfiguration: Flyway + Liquibase both present (both auto-configs run unless one is disabled via `spring.flyway.enabled` / `spring.liquibase.enabled`), or a migration tool plus `spring.jpa.hibernate.ddl-auto: update`, which runs after it and silently mutates the schema the migrations describe. On Boot 4 a migration tool is wired only through its Boot module (`spring-boot-starter-flyway` / `-liquibase`, or `spring-boot-starter-classic`) - a bare `flyway-core` / `liquibase-core` runs nothing at startup, silently (a hotspot). Flyway and Liquibase both need JDBC: on an R2DBC-only app neither runs without `spring.flyway.url` / `spring.liquibase.url` and a JDBC driver - silently, the app still starts.
- Check the enabler for every annotation found: `@Scheduled` needs `@EnableScheduling`, `@Async` needs `@EnableAsync`, `@PreAuthorize`/`@PostAuthorize` need `@EnableMethodSecurity` (`@EnableReactiveMethodSecurity` on WebFlux), `@Secured` needs `securedEnabled = true`, `@RolesAllowed` needs `jsr250Enabled = true`, `@Retryable` needs `@EnableRetry` (Spring Retry's annotation) or `@EnableResilientMethods` (Framework 7's `org.springframework.resilience` one), `@Cacheable` needs `@EnableCaching`. Absent, the annotation is inert but reads as enforced - a hotspot.
- Multi-module: name the module carrying `@SpringBootApplication` and each module's role. A module with none is not independently runnable; its beans load only when the bootable module depends on it **and** its packages fall under a scan root (or are imported: `@Import`, `scanBasePackages`, `META-INF/spring/...AutoConfiguration.imports`).
- Identify the `SecurityFilterChain` beans (WebFlux: `SecurityWebFilterChain` over `ServerHttpSecurity`). A servlet `SecurityFilterChain` built from `HttpSecurity` in a WebFlux-only app fails startup (no `HttpSecurity` bean) - a run-blocking hotspot, not dead config. `WebSecurityConfigurerAdapter` and `antMatchers()` were removed in Spring Security 6, and `and()`, `authorizeRequests()` and `AntPathRequestMatcher` / `MvcRequestMatcher` in Spring Security 7 - each a compile break on Boot 4. Starter present with no chain = Boot's default chain (with actuator present, it permits the health endpoint and authenticates the rest); a generated user exists only when no `UserDetailsService` / `AuthenticationProvider` / `AuthenticationManager` bean exists and no OAuth2 client / resource-server / SAML2 module is on the classpath (unless `spring.security.user.*` is set). Starter absent = no auth. Entry point: `formLogin` as the only entry point answers an unauthenticated API call with a 302 to `/login`; with `httpBasic` also present (Boot's default chain) JSON/XHR callers get 401; no entry point configured -> 403.
- Label each route public / authenticated / role-restricted / **no chain (unsecured)** by cross-referencing the route inventory with each chain's `securityMatcher` and `requestMatchers(...)` (WebFlux: `authorizeExchange` / `pathMatchers(...)`). Routes come from the `@RequestMapping` family or from `RouterFunction` / `coRouter` DSLs; include framework routes with no controller (`/actuator/**`, springdoc) - a `securityMatcher` narrower than the app's URL space leaves them matched by no chain at all, and declaring any chain backs off Boot's default. Check `@PreAuthorize` / `@PostAuthorize` on controllers and services - they can make a route stricter than its matcher. A matcher with no controller is listed as "no controller found - confirm", never dropped. When the only chain is inert or broken, label routes `no effective chain - <reason>`.
- Inventory non-HTTP entry points - `@Scheduled` jobs, `@KafkaListener` / `@RabbitListener`, `@EventListener` / `@TransactionalEventListener`, `ApplicationRunner` / `CommandLineRunner`.
- Report missing expected inputs (no wrapper, no tests, no migrations) as absent plus what that implies - never emit a command that assumes them (`./mvnw` on a wrapper-less repo fails).
- When the project's own docs (`CLAUDE.md`, README, ADRs) contradict the code, report the contradiction as a hotspot; incident notes and runbooks that name code paths are evidence - cite them next to the hotspot they explain.

## Patterns

### Build inventory

| File | Signal |
| --- | --- |
| `pom.xml` | Maven; Boot version from `<parent>spring-boot-starter-parent` or a `spring-boot-dependencies` BOM import in `<dependencyManagement>`; `<java.version>` / `maven.compiler.release` |
| `build.gradle(.kts)` | Gradle; `id 'org.springframework.boot'` (Groovy) / `id("org.springframework.boot")` or `alias(libs.plugins...)` (Kotlin DSL); `java { toolchain { languageVersion = ... } }` |
| `settings.gradle(.kts)` `include(...)` / `<modules>` | Multi-module - map each module's role |
| `gradle/libs.versions.toml` | Version catalog - version source of truth |
| `mvnw` / `gradlew` | Use the wrapper; absent -> flag it and give the system-tool command |

### Bootstrap (clone -> running)

1. JDK: Maven needs a running JDK >= `<java.version>`. Gradle's own JVM must be 17+ (the Boot 4 Gradle plugin requires it) and supported by the wrapper (Boot 4: Gradle 8.14+ or 9.x; a Java 25 toolchain needs 9.1+); the toolchain JDK must be installed or auto-provisionable (foojay resolver in `settings.gradle`).
2. Local services: `spring-boot-docker-compose` on the classpath starts `compose.yaml` / `docker-compose.yml` from the app's working directory with the app (no manual `docker compose up`; multi-module: a root-level file needs `spring.docker.compose.file`; skipped in tests by default); otherwise run compose by hand or point at the URLs in the profile yml. A `Test<App>Application` using `SpringApplication.from(...)` means the dev run is `./gradlew bootTestRun` / `./mvnw spring-boot:test-run` with Testcontainers.
3. Active profile: `spring.profiles.active` or `SPRING_PROFILES_ACTIVE`.
4. Migrations run at startup (Flyway `db/migration/`, Liquibase `db/changelog/`) when their auto-config applies (see Rules).
5. Run: `./gradlew bootRun` (multi-module: `./gradlew :app:bootRun`) or `./mvnw spring-boot:run` (multi-module: `./mvnw -pl app -am install -DskipTests`, then `./mvnw -pl app spring-boot:run`). Tests: `./gradlew test` / `./mvnw verify` (integration tests: the task or profile CI invokes).
6. Verify health. Same port: `<server.port><server.servlet.context-path | spring.webflux.base-path><management.endpoints.web.base-path, default /actuator>/health`. Separate `management.server.port`: `<management.server.port><management.server.base-path><base-path>/health` (the app context path does not apply). springdoc -> `/v3/api-docs`, `/swagger-ui.html`.

### Key locations

| Location | Purpose |
| --- | --- |
| `.../<App>Application.java` | `@SpringBootApplication` - scan root |
| `src/main/resources/application*.yml` | Config + profile keys |
| `src/main/resources/db/{migration,changelog}/` | Flyway / Liquibase |
| `.../config/` | `@Configuration` - security, JPA, web, async |
| `.../*Properties.java` | `@ConfigurationProperties` - typed config bindings |
| `.../{controller,web,api}/` | `@RestController` / `@Controller` |
| `.../service/` | `@Service` + tx boundaries |
| `.../{repository,dao}/` | Persistence |
| `.../{domain,model,entity}/` | Entities / value objects |
| `src/test/resources/application-test.yml` | Test profile (Testcontainers / H2) |

### Conventions to extract

State the observed choice per axis; flag deviations rather than describe both options:

- **Package layout**: feature-package (`com.acme.order.{controller,service,repository}`) vs layer-package. Feature is modern.
- **Layering**: controller -> service -> repository. Business logic or repo access in controllers = smell.
- **API boundary**: records/DTOs vs entities returned from `@RestController`. Direct entity exposure leaks lazy state.
- **Error handling**: `@RestControllerAdvice` present, else Spring defaults leak.
- **Validation**: `@Valid` on controller args + JSR-380 on DTOs.
- **Tx placement**: `@Transactional` at service. On controller/repo = smell.
- **Logging**: SLF4J or `@Slf4j`; per-package levels in `logging.level`.
- **Injection**: constructor (`@RequiredArgsConstructor`) modern; field `@Autowired` legacy.

### Risk hotspots

Name and locate; defer depth to the owning atomic:

- **Findings from the Rules above**: missing enablers, dual schema authority, scan divergence, APIs removed in Security 6 / 7, servlet security types in a WebFlux app, routes with no chain, docs contradicting code.
- **Proxy self-invocation** on `@Transactional` / `@Async` / `@Cacheable` / `@PreAuthorize` (-> `spring-transaction`); `readOnly` transactions around writes; remote calls (HTTP, broker publish) inside a transaction.
- **Missing beans**: a constructor-injected type with no producing `@Bean` / `@Component` in the scanned packages - startup failure, or a bean from a dependency to confirm.
- **OSIV state**: `spring.jpa.open-in-view` unset = on - masks N+1 / LIE and holds a connection per request (-> `spring-jpa-performance`).
- **`@PostConstruct` heavy work** delays startup and precedes health checks (servlet and WebFlux alike).
- **Ambiguous wiring**: multiple `DataSource` / `PlatformTransactionManager` without `@Primary`.
- **Filter ordering / double registration**: custom `OncePerRequestFilter` without explicit order; a filter that is both a `@Component` and `addFilterBefore(...)`'d registers twice unless suppressed via `FilterRegistrationBean`.
- **Unnamed `@Async` executor**: with no `Executor` bean it lands on Boot's `applicationTaskExecutor` (virtual threads when enabled, else 8 threads with an unbounded queue); any `Executor` bean backs that off unless it is declared `@Bean(defaultCandidate = false)` or `spring.task.execution.mode=force` is set (Boot 3.x: re-declaring `applicationTaskExecutor` / `taskExecutor`, or `mode=force` from 3.5). A single `TaskExecutor` then receives every unnamed `@Async` - but a Boot-created `taskScheduler` (from `@EnableScheduling`) counts, and with several and none named `taskExecutor` they fall to a thread-per-task executor (-> `spring-async-processing`).
- **State-changing GET routes** - crawler- and prefetch-triggerable, and exempt from CSRF protection.
- **Lombok `@Data` on JPA entities** - generated `equals`/`hashCode`/`toString` traverse lazy associations.
- **Flyway `out-of-order` enabled** masks dev/CI/prod schema drift.
- **Jakarta vs javax**: Boot 3+ = `jakarta.*`; `javax.persistence` does not resolve, and a compat jar's entities are ignored by Hibernate 6+.
- **Boot 4 module split**: a library with neither its Boot starter / `spring-boot-<tech>` module nor `spring-boot-starter-classic` gets no auto-configuration - bare `flyway-core` / `liquibase-core` (migrations never run), bare `spring-kafka` (injecting `KafkaTemplate` fails startup; `@KafkaListener` methods are silently never registered unless the app declares `@EnableKafka` and a container factory). `spring-boot-starter-aop` no longer exists (build break; the replacement is `spring-boot-starter-aspectj`).
- **Dependency risk visible in the build**: versions pinned below the Boot BOM, scanner-flagged versions noted in docs.
- **Seen in passing**: string-built SQL, unreferenced components (mappers or services nothing injects) - one line each, routed to the owning review.
- **Stack variants.** WebFlux: no OSIV, no servlet filter double-registration; blocking calls (JDBC, `block()`, blocking HTTP clients) on the event loop are a runtime hotspot. Kotlin: without `kotlin("plugin.spring")` classes are final - a final `@Configuration` / `@Transactional` class fails startup, and final methods on an opened class are silently not proxied; JPA entities also need `kotlin("plugin.jpa")` plus `allOpen` entries for `jakarta.persistence.Entity`, `MappedSuperclass` and `Embeddable`; `spring-boot-configuration-processor` needs `kapt`. Report rows that do not apply as not applicable rather than dropping them.

### First-PR safe zones (vs riskier)

| Safe | Riskier |
| --- | --- |
| New endpoint on existing controller, established patterns | Anything in `config/` - one bean rewires the context |
| New DTO field with validation, no schema change | JPA entity changes - cascade migrations / queries / serialization |
| New test exercising existing service | Spring Security config - silent failures |
| INFO log following existing pattern | Schema migrations - irreversible in prod |
| New `@ConfigurationProperties` field with default preserving current behavior | New profile - changes runtime wiring |

### Currency signals

- A Boot line past its OSS end date (spring.io support table) is a migration signal; Boot < 3 additionally means the `javax.*` -> `jakarta.*` migration, and Boot 3 -> 4 means Jackson 3 (`tools.jackson.*`), the modular starters, and Spring Security 7.
- Servlet stack + Java 21 + `spring.threads.virtual.enabled=true` -> request handling on virtual threads, and `@Scheduled` moves to the virtual-thread scheduler (fixedRate/cron runs can overlap) - not applicable on WebFlux.
- Slice tests (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`) over full-context `@SpringBootTest`.

## Output Format

Inject into the parent workflow's onboarding output; standalone (no parent workflow), emit the six sections below directly. Counts and inventories come from files actually read; anything the input did not include is written "not observed" rather than guessed. A finding inferred by cross-referencing (migrations vs entities, incident notes vs code) carries `(inferred)`. Unmerged material (diffs, branches) is out of the map.

**Stack and Tooling:** build system, Boot version, source language, Java toolchain, key starters (an embedded frontend build included), persistence stack(s) + every `DataSource` bean + migration tool + schema owner, web stack (MVC / WebFlux, annotated or functional routing), security state (configured / autoconfigured / absent - annotate hybrids, e.g. a configured chain with no `UserDetailsService` authenticates against the generated user), dependency risks visible in the build, and the currency signals that apply.

**Local Bootstrap:** exact run command, test command, required local services and how they start, profile inventory (every `application-<profile>.yml`, default active, override mechanism, which value wins), port, health URL.

**Architecture Map:** module map (multi-module: module -> role, which carries `@SpringBootApplication`, what the bootable module depends on), component-scan root and any divergent `scanBasePackages` / `@ComponentScan` / `@EntityScan` / `@EnableJpaRepositories`, layer directories with source-file counts (`.java` / `.kt`), `@Configuration` classes (what each wires), `@ConfigurationProperties` classes (key prefix), cross-cutting (`@RestControllerAdvice`, custom filters, AOP), route table (method + path -> handler `{Class#method | no controller found - confirm | security filter}` -> auth label `{public | authenticated | role-restricted | no chain (unsecured) | no effective chain - <reason>}`, plus `+ inert @PreAuthorize` when method security is not enabled; above ~30 routes group by path prefix and expand only security-interesting rows), non-HTTP entry points (trigger + handler).

**Conventions:** chosen value per axis from the list above.

**Risk Hotspots:** observed instances from the Risk hotspots list (Rules-derived findings included), each with file paths and the evidence (code, config, or doc) that shows it. Order: first what stops the build or the app from starting, then what exposes data or routes without auth, then what loses or corrupts data, then the rest. Rows that do not apply are listed as not applicable.

**First-PR Safe Zones:** scoped to the observed structure.

## Avoid

- Describing layout from generic Spring docs without reading the file tree
- Listing every `@Configuration` class - focus on those wiring cross-cutting concerns
- Listing every dependency - focus on starters, persistence, security, observability
- Treating autoconfiguration as invisible - name which starters pull in what
- Recommending patterns from an older Boot line than the project runs (`javax.*` on Boot 3+; Jackson 2 `com.fasterxml.jackson.databind` or `spring-boot-starter-web` on Boot 4)
- Skipping profile precedence - "which value wins" is the question new engineers actually ask
