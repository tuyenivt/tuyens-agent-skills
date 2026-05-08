---
name: kotlin-onboard-map
description: Kotlin / Spring Boot project onboarding signals - Gradle Kotlin DSL layout, kotlin-spring/kotlin-allopen plugins, coroutines runtime, application.yml profiles, and persistence/security configuration. Used by task-onboard to map a Kotlin codebase for a new engineer.
metadata:
  category: backend
  tags: [onboarding, codebase-map, kotlin, spring, gradle]
user-invocable: false
---

# Kotlin Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Kotlin / Spring Boot.

## When to Use

- A workflow needs Kotlin-specific orientation: Gradle build, plugin set, coroutine runtime, Spring config layout, Kotlin compiler flags.
- Project has `build.gradle.kts` and a Kotlin Spring Boot main class.

## Rules

- Identify the Gradle build (`build.gradle.kts` is standard for Kotlin) and the Kotlin/Spring versions before describing layout.
- Locate `kotlin-spring` and `kotlin-allopen` plugins in the build file - their absence/presence changes whether Spring AOP works on Kotlin classes.
- Identify the coroutine runtime in use: kotlinx-coroutines version, structured concurrency conventions, integration with Spring (`@Async`, `WebFlux`, `kotlin-coroutines-reactor`).

## Patterns

### Build Inventory

| File / location           | What it tells you                                                                                  |
| ------------------------- | -------------------------------------------------------------------------------------------------- |
| `build.gradle.kts` (root) | Kotlin DSL Gradle build; check `plugins {}` for `kotlin("jvm")`, `kotlin("plugin.spring")`, `org.springframework.boot` |
| `settings.gradle.kts`     | Multi-project build; lists subprojects                                                              |
| `gradle/libs.versions.toml` | Version catalog (recommended for Kotlin projects)                                                 |
| `gradle.properties`       | Gradle daemon config, Kotlin version, JVM target                                                   |
| `gradlew`                 | Gradle wrapper - always use `./gradlew`, not system Gradle                                         |
| `kotlin-spring` plugin    | Auto-opens classes annotated with Spring stereotypes (`@Service`, `@Component`, etc.)              |
| `kotlin-allopen` plugin   | Custom open-rules; check the configuration block                                                   |
| `kotlin-jpa` plugin       | Auto-generates no-arg constructors for `@Entity` classes (JPA requirement)                         |
| `kotlin-noarg`            | Same idea, configurable annotations                                                                 |

### Bootstrap Path

1. JVM toolchain: `kotlinOptions.jvmTarget` and `java.toolchain.languageVersion` in build file. Common: JVM 17 or 21.
2. Local services: `compose.yml` / `docker-compose.yml` or external connection strings in `application-*.yml`.
3. Profiles: `application.yml` `spring.profiles.active`, or `SPRING_PROFILES_ACTIVE` env var.
4. DB migration: Flyway (`src/main/resources/db/migration/`) or Liquibase.
5. Run: `./gradlew bootRun` (Spring Boot Gradle plugin).
6. Verify: actuator endpoints (default `/actuator`); test command `./gradlew test`.

### Key File Inventory

| Location                                        | Purpose                                                                                  |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `src/main/kotlin/.../Application.kt`            | Main class with `@SpringBootApplication`; `fun main(args: Array<String>) { runApplication<App>(*args) }` |
| `src/main/resources/application.yml`            | Config + profile keys                                                                     |
| `src/main/resources/db/migration/`              | Flyway migrations                                                                         |
| `src/main/kotlin/.../config/`                   | `@Configuration` classes; security, JPA, web config                                       |
| `src/main/kotlin/.../controller/`               | `@RestController` endpoints                                                               |
| `src/main/kotlin/.../service/`                  | Business logic, transaction boundaries                                                    |
| `src/main/kotlin/.../repository/`               | Spring Data interfaces or custom repos                                                    |
| `src/main/kotlin/.../domain/`                   | Entities, data classes, value objects                                                     |
| `src/test/kotlin/...`                           | Tests; use kotest or JUnit 5                                                              |

### Conventions

- **Constructor injection** is idiomatic; field injection rare. `class FooService(private val bar: BarService)`.
- **Data classes for DTOs**; entities usually regular classes (need `open` for JPA proxies, or use `kotlin-jpa` plugin).
- **Coroutines for async**: prefer `suspend fun` and `Flow<T>` over `CompletableFuture` in modern code.
- **Sealed classes/interfaces** for closed type hierarchies (success/failure, state machines).
- **MockK** over Mockito for tests; `runTest` for coroutine tests.
- **Detekt** and **ktlint** for static analysis; configured in build file.

### Risk Hotspots Specific to Kotlin + Spring

- **Missing `kotlin-spring` plugin**: Spring annotations (`@Transactional`, `@Async`, `@Cacheable`) silently no-op on `final`-by-default Kotlin classes.
- **Missing `kotlin-jpa` plugin** with JPA entities: `org.hibernate.InstantiationException` on entity load (no no-arg constructor).
- **`data class` as JPA `@Entity`**: cannot open; equals/hashCode tied to constructor properties only - frequently the wrong identity model.
- **Self-invocation**: same gotcha as Java/Spring; calling `this.method()` bypasses the proxy.
- **Coroutine launch without scope**: `GlobalScope.launch` leaks; use injected `CoroutineScope` or structured `coroutineScope { }`.
- **Mixing blocking and suspend**: blocking I/O in suspend function freezes the dispatcher. `withContext(Dispatchers.IO)` for unavoidable blocking.
- **`runBlocking` in production code** (not tests/main): blocks a thread, defeats coroutine benefits.
- **Platform types from Java interop**: `Type!` bypasses null checking - frequent NPE source.

### First-PR Safe Zones

- New endpoint on existing `@RestController` following the established pattern.
- New `data class` DTO with validation annotations, no entity changes.
- New test using kotest/JUnit + MockK.
- New property in `application.yml` with safe default.

Risky areas:

- `config/` - one bean change rewires the context.
- JPA entity changes - cascade across migrations and queries.
- Coroutine scope management - leak risk.
- Spring Security configuration.

### Ecosystem Currency

- Kotlin 2.0+ (K2 compiler) is standard for new projects.
- Spring Boot 3.x: Jakarta namespace.
- `kotlinx-coroutines` 1.8+; `kotlinx-serialization` for JSON (alternative to Jackson).
- Project Reactor + coroutines: `kotlinx-coroutines-reactor` for `mono { ... }` and `flow { ... }` interop.
- Java 21: virtual threads available; coroutines complement (not replace) them.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Gradle Kotlin DSL, Spring Boot version, Kotlin version, JVM target, key plugins (`kotlin-spring`, `kotlin-jpa`, `kotlin-allopen`), persistence + migration tool, coroutines runtime.

**Local Bootstrap:** `./gradlew bootRun`, required local services, default profile, port, actuator path.

**Architecture Map:** Component-scan root, layer directories with file counts, `@Configuration` classes, cross-cutting concerns.

**Conventions:** constructor injection, data class DTOs, coroutine usage, sealed type usage, test stack (kotest/JUnit + MockK).

**Risk Hotspots:** plugin presence (kotlin-spring, kotlin-jpa), self-invocation, coroutine scope leaks, platform-type NPEs, blocking in suspend.

**First-PR Safe Zones:** scoped to actual structure observed.

## Avoid

- Describing the project as "just Java with Kotlin" - the open-by-default and coroutine differences are foundational
- Listing dependencies without checking the plugin set
- Recommending Java 8 / Spring Boot 2.x patterns on a Boot 3.x Kotlin project
- Skipping the `kotlin-spring` plugin check - its absence is a silent footgun
- Treating `runBlocking` and `runTest` as interchangeable - one blocks, one uses virtual time
