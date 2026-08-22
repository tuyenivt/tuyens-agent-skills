---
name: spring-onboard-map
description: "Spring Boot onboarding signals: build, profiles, ConfigurationProperties, persistence, security chain, scan roots, risks, safe zones."
metadata:
  category: backend
  tags: [onboarding, codebase-map, spring, maven, gradle]
user-invocable: false
---

# Spring Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-onboard` when the stack is Java / Spring Boot.

## When to Use

Workflow needs Spring-specific orientation: where code lives, how to run, what wires the context, where risk concentrates. Triggered when `pom.xml` / `build.gradle(.kts)` + a `@SpringBootApplication` class exist.

## Rules

- Identify build system, Boot version, Java toolchain before anything else - structure varies.
- Locate `@SpringBootApplication` package = component-scan root. Flag any `scanBasePackages`, `@EntityScan`, `@EnableJpaRepositories` that diverge from it - beans outside become invisible.
- Inventory every `application-<profile>.yml` / `.properties` and state precedence: CLI args > env (`SPRING_APPLICATION_JSON`, `SPRING_*`) > `application-<profile>` > `application.yml`. Note `spring.profiles.active` default and `spring.config.import`.
- List `@ConfigurationProperties` classes (and any `@EnableConfigurationProperties`) - typed config beats grepping yml for keys.
- Identify persistence stack(s) - JPA / JDBC / MyBatis / R2DBC / none, and more than one may coexist - plus the migration tool and every `DataSource` bean. Two schema authorities is a misconfiguration in any combination: Flyway + Liquibase both present (both auto-configs fire unless one is disabled via `spring.flyway.enabled` / `spring.liquibase.enabled`), or a migration tool plus `spring.jpa.hibernate.ddl-auto: update`, which runs after it and silently mutates the schema the changelog claims to describe. Name which one actually owns the schema. Flyway needs a JDBC URL, so on an R2DBC app it does not run without one.
- Check the enabler for every annotation found: `@Scheduled` needs `@EnableScheduling`, `@PreAuthorize` needs `@EnableMethodSecurity` (`@EnableReactiveMethodSecurity` on WebFlux), `@Retryable` needs `@EnableRetry`. Absent, the annotation is inert and reads as enforced - report it as a hotspot, not as working behaviour.
- Multi-module: name which module carries `@SpringBootApplication`. A module with none is not independently runnable, and whether its beans load at all depends on the bootable module declaring a dependency on it.
- Identify the `SecurityFilterChain` bean (WebFlux: `SecurityWebFilterChain` over `ServerHttpSecurity`; servlet types in a WebFlux app are dead config). `WebSecurityConfigurerAdapter` and `antMatchers()` were removed in Spring Security 6, so on a Boot 3 build they are a compile break, not a style note. No security config + `spring-boot-starter-security` on classpath = a generated user whose credential is used by whichever entry point is configured; starter absent = no auth. Note the entry point too: `formLogin` answers an unauthenticated API call with a 302 to `/login`, not a 401.
- Cross-reference route inventory with `securityMatcher`/`requestMatchers(...)` so each route is labeled public / authenticated / role-restricted. Routes come from the `@RequestMapping` / `@GetMapping` family, or from `RouterFunction` / `coRouter` DSLs in a functional-routing app. Include framework-provided routes with no controller (`/actuator/**`, springdoc) - a `securityMatcher` narrower than the app's URL space leaves them matched by no chain at all, and an explicit chain bean backs Boot's default off. Also check `@PreAuthorize` / `@PostAuthorize` on controllers and services - these enforce auth outside the chain, so a route that looks "authenticated" from matchers alone may carry a stricter role rule. A matcher with no matching controller is listed as "no controller found - confirm", never dropped (a permitAll orphan is security-relevant).
- Inventory non-HTTP entry points - `@Scheduled` jobs, message listeners (`@KafkaListener` / `@RabbitListener`), `@EventListener` / `@TransactionalEventListener` - a service's runtime behavior is often dominated by them.
- Report missing expected inputs (no wrapper, no tests, no migrations) as absent plus what that implies - never emit a command that assumes them (`./mvnw` on a wrapper-less repo fails).

## Patterns

### Build inventory

| File | Signal |
| --- | --- |
| `pom.xml` | Maven; `<parent>` -> `spring-boot-starter-parent`; `<java.version>` |
| `build.gradle(.kts)` | Gradle; `plugins { id 'org.springframework.boot' }`; `java { toolchain { languageVersion = ... } }` |
| `settings.gradle(.kts)` `include(...)` / multi-module `<modules>` | Multi-module fan-out - map each module's role |
| `gradle/libs.versions.toml` | Version catalog - version source of truth |
| `mvnw` / `gradlew` | Use wrapper, not system tool; if absent, flag it and give the system-tool command |

### Bootstrap (clone -> running)

1. Java version matches toolchain (`java -version`).
2. Local deps from `compose.yml` (Postgres, Redis, Kafka) or external URLs in profile yml.
3. Active profile from `spring.profiles.active` or `SPRING_PROFILES_ACTIVE`.
4. Migrations: Flyway (`src/main/resources/db/migration/`) or Liquibase (`db/changelog/`) - run at startup.
5. Run: `./mvnw spring-boot:run` or `./gradlew bootRun` (multi-module: qualify the runnable module, `./gradlew :app:bootRun`). Port `server.port` (default 8080).
6. Verify `/actuator/health` when the actuator starter is present (else hit a known route); springdoc -> `/v3/api-docs`, `/swagger-ui.html`.

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
- **Layering**: controller -> service -> repository. Business logic in controllers or repo access from controllers = smell.
- **API boundary**: records/DTOs vs entities returned from `@RestController`. Direct entity exposure leaks lazy state.
- **Error handling**: `@RestControllerAdvice` present, else Spring defaults leak.
- **Validation**: `@Valid` on controller args + JSR-380 on DTOs.
- **Tx placement**: `@Transactional` at service. On controller/repo = smell.
- **Logging**: SLF4J or `@Slf4j`; per-package levels in `logging.level`.
- **Injection**: constructor (`@RequiredArgsConstructor`) modern; field `@Autowired` legacy.

### Risk hotspots

Name and locate; defer depth to the owning atomic:

- **Proxy self-invocation** on `@Transactional` / `@Async` / `@Cacheable` / `@PreAuthorize` (-> `spring-transaction`).
- **OSIV state**: `spring.jpa.open-in-view` masks N+1 / LIE (-> `spring-jpa-performance`).
- **`@PostConstruct` heavy work** delays startup, precedes health checks.
- **Scan divergence**: custom `scanBasePackages` / `@EntityScan` / `@EnableJpaRepositories` outside the app package.
- **Ambiguous wiring**: multiple `DataSource` / `PlatformTransactionManager` without `@Primary`.
- **Filter ordering / double registration**: custom `OncePerRequestFilter` without explicit order vs Spring Security chain; a filter that is both a `@Component` and `addFilterBefore(...)`'d registers twice (servlet container + chain) unless suppressed via `FilterRegistrationBean`.
- **`@EnableAsync` without an executor bean** -> unnamed `@Async` lands on Boot's `applicationTaskExecutor`: 8 threads with an *unbounded queue*, so no back-pressure (-> `spring-async-processing`).
- **Lombok `@Data` on JPA entities** - generated `equals`/`hashCode`/`toString` traverse lazy associations.
- **Flyway `out-of-order` enabled** masks dev/CI/prod schema drift.
- **Jakarta vs javax**: Boot 3 = `jakarta.*`; `javax.persistence` on a Boot 3 classpath does not resolve, and if a compat jar supplies it Hibernate 6 ignores the class as an entity.
- **Non-servlet / non-Java stacks** shift where the same signals live and retire several rows above. On WebFlux: no OSIV, no servlet filter double-registration, blocking work on an event loop replaces `@PostConstruct` as the startup-stall risk. On Kotlin: `kotlin("plugin.spring")` (all-open) is required or `@Configuration`/`@Transactional` proxies silently do not apply, and annotation processors need `kapt`. Report the inapplicable rows as not applicable rather than silently dropping them.

### First-PR safe zones (vs riskier)

| Safe | Riskier |
| --- | --- |
| New endpoint on existing controller, established patterns | Anything in `config/` - one bean rewires the context |
| New DTO field with validation, no schema change | JPA entity changes - cascade migrations / queries / serialization |
| New test exercising existing service | Spring Security config - silent failures |
| INFO log following existing pattern | Schema migrations - irreversible in prod |
| New `@ConfigurationProperties` field with default preserving current behavior | New profile - changes runtime wiring |

### Currency signals

- Boot < 3 (`javax.*` baseline) is out of OSS support - surface as a migration signal regardless of which pre-3 patterns appear.
- Java 21 + `spring.threads.virtual.enabled=true` -> Virtual Threads on controllers.
- Slice tests (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`) over full-context `@SpringBootTest`.

## Output Format

Inject into the parent workflow's onboarding output; standalone (no parent workflow), emit the six sections below directly:

**Stack and Tooling:** build system, Boot version, source language, Java toolchain, key starters, persistence + migration tool, web stack (MVC / WebFlux, annotated or functional routing), security state (configured / autoconfigured / absent - annotate hybrids, e.g. a configured chain with no `UserDetailsService`, so the configured entry point authenticates against the generated user), plus the currency signals that apply: Boot < 3 is out of OSS support; on a servlet stack, Java 21 + `spring.threads.virtual.enabled=true` puts request handling on virtual threads (not applicable on WebFlux, where requests run on the event loop); slice tests over full-context `@SpringBootTest`.

**Local Bootstrap:** exact run command, required local services, profile inventory (every `application-<profile>.yml`, default active, override mechanism, precedence chain), default port, actuator base path.

**Architecture Map:** component-scan root, any divergent `@EntityScan` / `@EnableJpaRepositories`, layer directories with source-file counts (`.java` / `.kt`; write "not observed" rather than guessing when the listing is partial), `@Configuration` classes (what each wires), `@ConfigurationProperties` classes (key prefix), cross-cutting (`@RestControllerAdvice`, custom filters, AOP), route table (method + path -> controller method -> auth label from chain; above ~30 routes group by path prefix and expand only security-interesting rows), non-HTTP entry points (`@Scheduled` / message listeners / event listeners -> trigger + handler).

**Conventions:** chosen value per axis from the list above.

**Risk Hotspots:** observed instances from the list above, with file paths, ordered by whether they block the build or the app from running, then by blast radius. Retire the inapplicable rows explicitly rather than dropping them.

**First-PR Safe Zones:** scoped to the observed structure.

## Avoid

- Describing layout from generic Spring docs without reading the file tree.
- Listing every `@Configuration` class - focus on those wiring cross-cutting concerns.
- Listing every dependency - focus on starters, persistence, security, observability.
- Treating autoconfiguration as invisible - name which starters pull in what.
- Recommending Boot 2.x / `javax.*` patterns on a Boot 3 project.
- Skipping profile precedence - "which value wins" is the question new engineers actually ask.
