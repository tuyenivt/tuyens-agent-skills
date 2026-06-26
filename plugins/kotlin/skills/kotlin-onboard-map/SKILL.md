---
name: kotlin-onboard-map
description: Kotlin / Spring Boot onboarding map: Gradle Kotlin DSL, kotlin-spring/allopen plugins, coroutines, application.yml profiles, persistence/security.
metadata:
  category: backend
  tags: [onboarding, codebase-map, kotlin, spring, gradle]
user-invocable: false
---

# Kotlin Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Kotlin / Spring Boot.

## When to Use

- A workflow needs Kotlin-specific orientation: Gradle build, plugin set, coroutine runtime, Spring config layout.
- Project has `build.gradle.kts` and a Kotlin Spring Boot main class.

## Rules

- Identify the Kotlin / Spring versions and plugin set before describing layout.
- Locate `kotlin-spring` and `kotlin-jpa` plugins - their absence changes whether Spring AOP and JPA work on Kotlin classes.
- Identify the coroutine runtime (kotlinx-coroutines version, `kotlin-coroutines-reactor` for Spring interop).
- Inventory every `application-<profile>.yml` / `.properties` and state precedence: CLI args > env (`SPRING_APPLICATION_JSON`, `SPRING_*`) > `application-<profile>` > `application.yml`. Note `spring.profiles.active` default and any `spring.config.import`.
- List `@ConfigurationProperties` data classes (and any `@EnableConfigurationProperties`) - typed config beats grepping yml for keys. Flag missing `kotlin-spring` plugin when these are used without `open` (constructor-binding is fine; method-binding needs proxying).
- Locate `@SpringBootApplication` package = component-scan root. Flag any `scanBasePackages`, `@EntityScan`, `@EnableJpaRepositories` that diverge from it - beans outside become invisible.
- Identify the `SecurityFilterChain` bean. Flag `WebSecurityConfigurerAdapter` as legacy (Boot 2.x). No security config + `spring-boot-starter-security` on classpath = HTTP Basic with generated password.

## Patterns

### Build inventory

| File / location              | What it tells you                                                                |
| ---------------------------- | -------------------------------------------------------------------------------- |
| `build.gradle.kts` (root)    | Kotlin DSL Gradle; check `plugins {}` block                                      |
| `settings.gradle.kts`        | Multi-project structure                                                          |
| `gradle/libs.versions.toml`  | Version catalog                                                                  |
| `gradle.properties`          | Daemon, Kotlin, JVM target                                                       |
| `gradlew`                    | Wrapper - always use `./gradlew`, never system Gradle                            |
| `kotlin-spring` plugin       | Auto-opens classes with Spring stereotypes (`@Service`, `@Component`, etc.)      |
| `kotlin-jpa` plugin          | No-arg constructors for `@Entity` / `@Embeddable` / `@MappedSuperclass`          |
| `kotlin-allopen` plugin      | Custom open rules; check configuration block                                     |

### Bootstrap path

1. JVM toolchain: `kotlinOptions.jvmTarget` / `kotlin { jvmToolchain(...) }` / `java.toolchain.languageVersion`. Common: 17 or 21. With `jvmToolchain(...)` confirm `foojay-resolver-convention` is applied in `settings.gradle.kts` (otherwise CI fails on first run).
2. Multi-module (`settings.gradle.kts` has `include(...)`): state which module is the boot app (`./gradlew :app:bootRun`, qualified) and where entities / repositories / migrations live. A domain/library module holding `@Entity` needs `kotlin-jpa` applied there; `@EntityScan` / `@EnableJpaRepositories` on the app must point at the domain package or those beans go missing. Migration resources (`db/migration/`) only run if they're on the boot module's runtime classpath - find which module packages them (often the app, sometimes alongside the entities).
3. Local services: `compose.yml` / `docker-compose.yml` or external connections in `application-*.yml`.
4. Migrations: `src/main/resources/db/migration/` (Flyway) or `db/changelog/` (Liquibase). Both present = misconfiguration.
5. Run: `./gradlew bootRun` (qualify with the module for multi-module). Port `server.port` (default 8080).
6. Verify: actuator at `/actuator/health`; `./gradlew test`. With springdoc on classpath, `/swagger-ui.html` is the fastest API survey.

### Configuration axes

State the observed value for each axis. New engineers ask "which value wins" - the precedence chain answers it.

- **Profile precedence**: CLI args > env (`SPRING_APPLICATION_JSON`, `SPRING_PROFILES_ACTIVE`, `SPRING_*`) > `application-<profile>.yml` > `application.yml` > `application.properties` (if both `.yml` and `.properties` exist, `.properties` wins for the same key in the same source).
- **Active profile**: `spring.profiles.active` in `application.yml`, or `SPRING_PROFILES_ACTIVE` env.
- **Profile inventory**: every `application-<profile>.yml` (dev / staging / prod / test / local) with one-line purpose.
- **`spring.config.import`**: external config sources (`configtree:`, `optional:`, `vault:`); call out what's loaded.
- **`@ConfigurationProperties` classes**: prefix + bound type. Constructor-bound `data class` is idiomatic in Kotlin; method-bound `class` needs the `kotlin-spring` plugin to be proxied.
- **Plugin presence**: `kotlin-spring` (opens stereotype-annotated classes), `kotlin-jpa` (no-arg ctors), `kotlin-allopen` (custom open rules). Missing plugin + the feature it opens = silent failure at runtime.
- **Scan divergence**: any `@ComponentScan(basePackages = ...)`, `@EntityScan`, `@EnableJpaRepositories` whose root differs from `@SpringBootApplication` - beans outside it become invisible.

### Key file inventory

| Location                                    | Purpose                                                                |
| ------------------------------------------- | ---------------------------------------------------------------------- |
| `src/main/kotlin/.../Application.kt`        | `@SpringBootApplication` + `fun main(...) { runApplication<App>(*args) }` |
| `src/main/resources/application.yml`        | Config + profiles                                                       |
| `src/main/resources/db/migration/`          | Flyway migrations                                                       |
| `src/main/kotlin/.../config/`               | `@Configuration` classes; security, JPA, web                            |
| `src/main/kotlin/.../controller/`           | `@RestController` endpoints                                             |
| `src/main/kotlin/.../service/`              | Business logic, transaction boundaries                                  |
| `src/main/kotlin/.../repository/`           | Spring Data interfaces                                                  |
| `src/main/kotlin/.../domain/`               | Entities, data classes, value objects                                   |
| `src/test/kotlin/...`                       | Tests - kotest / JUnit 5 + MockK                                        |

**Package layout** - check before describing:

- **Feature-package** (preferred for Boot 3+): `com.acme.order` contains `OrderController` / `OrderService` / `OrderRepository` / `Order`. Cross-feature imports via public service interfaces.
- **Layer-package** (older): `com.acme.controller`, `com.acme.service`, etc. Harder to follow end-to-end flows.

### Conventions

- Constructor injection idiomatic: `class FooService(private val bar: BarService)`.
- Data classes for DTOs; entities are regular classes (need `kotlin-jpa` plugin).
- Coroutines for async: `suspend fun` and `Flow<T>` over `CompletableFuture` in modern code.
- Sealed classes / interfaces for closed hierarchies.
- MockK over Mockito; `runTest` for coroutines.
- Detekt + ktlint for static analysis.

### Kotlin + Spring risk hotspots

- **Missing `kotlin-spring` / `kotlin-jpa` plugins**: silent no-op on `@Transactional`; `No default constructor` on entities. See `kotlin-gradle-build-optimization`.
- **`data class` as `@Entity`**: corrupts Hibernate proxy identity. See `kotlin-spring-jpa-performance`.
- **`@Transactional` self-invocation / external I/O / `suspend` without reactor bridge**: see `kotlin-spring-transaction`.
- **`GlobalScope.launch`, `runBlocking` in production**: see `kotlin-coroutines-spring`.
- **Platform types (`T!`) from Java interop**: bypass null checks, frequent NPE source. See `kotlin-idioms`.
- **OSIV (`spring.jpa.open-in-view=true`)** default-on: lazy-loads after service return, holds connections. See `kotlin-spring-jpa-performance`.

### First-PR safe zones

- New endpoint on existing `@RestController` following the pattern
- New `data class` DTO with validation
- New test using kotest / JUnit + MockK
- New `application.yml` property with safe default

Risky areas: `config/`, JPA entity changes, coroutine scope management, security configuration.

### Ecosystem currency

- Kotlin 2.0+ (K2 compiler) standard
- Spring Boot 3.x: Jakarta namespace
- `kotlinx-coroutines` 1.8+; `kotlin-coroutines-reactor` for Spring interop
- Java 21: virtual threads available; coroutines complement (not replace) them

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Gradle Kotlin DSL, Spring Boot version, Kotlin version, JVM target, key plugins (`kotlin-spring`, `kotlin-jpa`, `kotlin-allopen`), persistence + migration tool, coroutines runtime.

**Local Bootstrap:** `./gradlew bootRun`, required local services, default profile, port, actuator path.

**Architecture Map:** Component-scan root, layer directories with file counts, `@Configuration` classes, cross-cutting concerns.

**Conventions:** constructor injection, data class DTOs, coroutine usage, sealed type usage, test stack.

**Risk Hotspots:** plugin presence, self-invocation, coroutine scope leaks, platform-type NPEs, blocking-in-suspend.

**First-PR Safe Zones:** scoped to actual structure observed.

## Avoid

- Describing the project as "Java with Kotlin syntax" - open-by-default and coroutines are foundational differences
- Listing dependencies without checking the plugin set
- Recommending Java 8 / Spring Boot 2.x patterns on a Boot 3.x Kotlin project
- Skipping the `kotlin-spring` plugin check
- Treating `runBlocking` and `runTest` as interchangeable
