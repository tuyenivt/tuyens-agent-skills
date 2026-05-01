# Tuyen's Agent Skills - Kotlin

This is a **COMPANION** to the Java plugin (`java@tuyens-agent-skills`), not a replacement.
It adds Kotlin-specific idioms and syntax awareness as a thin layer on top of the shared
Spring Boot ecosystem provided by the Java plugin.

## Stack

- Kotlin 2.0+
- Spring Boot 3.5+
- Kotlin coroutines (alongside Virtual Threads)
- MockK / kotest for testing
- Kotlin DSL for Gradle and Spring Security

## What this plugin adds vs what comes from the Java plugin

| From Java plugin          | From Kotlin plugin                         |
| ------------------------- | ------------------------------------------ |
| JPA/Hibernate patterns    | Kotlin JPA entity idioms (no-arg, allopen) |
| Spring Security 6.x       | Kotlin DSL security config                 |
| Gradle build optimization | Kotlin Gradle DSL specifics                |
| Testcontainers patterns   | MockK + kotest integration                 |
| Virtual Threads           | Coroutines + Virtual Thread interop        |
| Java records for DTOs     | Kotlin data classes for DTOs               |
| Transaction management    | Coroutine-aware @Transactional             |
| Flyway migration safety   | (same - delegates to Java plugin)          |

## Plugin contents

### Agents (7)

| Agent                         | Description                                                                                                                                              |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kotlin-architect`            | Kotlin + Spring Boot architect. Extends the Java `spring-architect` with Kotlin idioms. Delegates core Spring decisions to Java plugin.                  |
| `kotlin-tech-lead`            | Code review, refactoring guidance, and doc standards extending `java-tech-lead` with Kotlin idiom enforcement (null safety, coroutines, data class JPA). |
| `kotlin-test-engineer`        | JUnit 5 + MockK + kotest, Testcontainers, Spring test slices with Kotlin DSL.                                                                            |
| `kotlin-security-engineer`    | Spring Security 6.x with Kotlin DSL, OWASP for Kotlin/JVM.                                                                                               |
| `kotlin-performance-engineer` | JVM/Spring/JPA performance with coroutine-aware profiling, GC tuning.                                                                                    |
| `kotlin-reliability-engineer` | JVM ops, Actuator, HikariCP, incident response, runbook standards with Kotlin-specific failure patterns (!! NPE, coroutine leak, data class JPA).        |
| `kotlin-sprint-planner`       | Sprint allocation extending `java-sprint-planner` with Kotlin-specific complexity (coroutine migration, MockK, Kotlin DSL).                              |

### Atomic skills (3)

| Skill                      | Description                                                                                                                                                               |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kotlin-idioms`            | Data classes, null safety, extension functions, scope functions, sealed classes, inline value classes, JPA plugin config, @ConfigurationProperties, Kotlin-Java interop   |
| `kotlin-coroutines-spring` | Suspend functions in services, Flow streaming, coroutine-aware transactions, Virtual Thread interop, structured concurrency, CoroutineScope beans, retry/timeout patterns |
| `kotlin-testing-patterns`  | MockK mocking (coEvery/coVerify), kotest matchers, @MockkBean, Testcontainers integration, test fixture factories, coroutine testing with runTest/Turbine                 |

### Workflow skills (2)

| Skill               | Description                                                                                                                                              | Delegates to Java plugin                                              |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------- |
| `task-kotlin-new`   | End-to-end Kotlin + Spring Boot feature implementation (stack detect, requirements, design approval, code, migration, tests, validation) with edge cases | `spring-db-migration-safety` for Flyway, test slices from Java plugin |
| `task-kotlin-debug` | Debug Kotlin-specific errors (null safety, coroutines, MockK, JPA plugin, Jackson serialization, Spring startup) with classification tables              | `task-spring-debug` for Java/Spring errors                            |


## Dependency relationship

```
core   (base patterns, git, code quality)
  └── java     (Spring Boot, JPA, Security, Gradle, testing infra)
        └── kotlin  (Kotlin idioms, coroutines, MockK/kotest)
```

The Kotlin plugin **never duplicates** Java plugin content. It references Java plugin skills
by name (e.g., `jpa-performance`, `transaction`, `backend-db-migration`, `task-spring-debug`) and
adds only the Kotlin-specific layer on top.
