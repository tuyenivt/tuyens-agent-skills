# Tuyen's Agent Skills - Kotlin

A Claude Code plugin for Kotlin + Spring Boot.

## Stack

- Kotlin 2.0+
- Spring Boot 3.5+
- Kotlin coroutines (alongside Virtual Threads)
- MockK / springmockk / Kotest / Turbine for testing
- Kotlin DSL for Gradle, Spring Security, and Spring Bean / Router configuration
- `kotlin("plugin.jpa")` + `kotlin("plugin.spring")` Gradle plugins

## Plugin contents

### Agents (5)

| Agent                         | Description                                                                                                                                                                          |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `kotlin-architect`            | Kotlin + Spring Boot architect. Designs services with data classes, coroutines, null safety, sealed-class result hierarchies, Kotlin DSL configuration, and Kotlin JPA conventions. |
| `kotlin-tech-lead`            | Code review, refactoring guidance, observability review, and doc standards with Kotlin idiom enforcement (null safety, coroutines, data class JPA, parameterized SLF4J).            |
| `kotlin-test-engineer`        | JUnit 5 / Kotest + MockK + springmockk + Testcontainers + runTest + Turbine, Spring test slices with Kotlin DSL.                                                                     |
| `kotlin-security-engineer`    | Spring Security 6.x with Kotlin DSL, OWASP for Kotlin/JVM, coroutine SecurityContext propagation.                                                                                    |
| `kotlin-performance-engineer` | JVM/Spring/JPA performance with coroutine-aware profiling, dispatcher selection vs Virtual Threads, GC tuning.                                                                       |

### Atomic skills (11)

| Skill                              | Description                                                                                                                                                                            |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kotlin-idioms`                    | Data classes, null safety, extension functions, scope functions, sealed classes, inline value classes, JPA plugin config, `@ConfigurationProperties`, Kotlin-Java interop              |
| `kotlin-coroutines-spring`         | Suspend functions in services, Flow streaming, coroutine-aware transactions, Virtual Thread interop, structured concurrency, CoroutineScope beans, retry/timeout                       |
| `kotlin-testing-patterns`          | MockK mocking (coEvery/coVerify), Kotest matchers, `@MockkBean`, Testcontainers, factory-function fixtures, coroutine testing with runTest/Turbine                                     |
| `kotlin-spring-jpa-performance`    | JPA/Hibernate N+1 prevention with fetch joins / `@EntityGraph`, batch fetching, projection queries, second-level cache, Kotlin entity caveat (regular class over data class)           |
| `kotlin-spring-transaction`        | `@Transactional` scope, propagation, self-invocation proxy bypass, checked-exception rollback, timeout, `@Transactional` on `suspend` functions and the `withContext` caveat            |
| `kotlin-spring-exception-handling` | `@RestControllerAdvice` + `ProblemDetail` (RFC 9457), sealed-class domain error hierarchies, `DataIntegrityViolationException` handling, external API error wrapping                  |
| `kotlin-spring-security-patterns`  | Spring Security 6.x Kotlin DSL `SecurityFilterChain`, OAuth2/JWT resource server, method security, CORS / CSRF, security headers, coroutine SecurityContext propagation                |
| `kotlin-spring-db-migration-safety` | Flyway / Liquibase zero-downtime migration patterns, expand-then-contract, non-blocking index creation, Testcontainers migration validation in Kotlin                                 |
| `kotlin-spring-test-integration`   | Spring test slice strategy (`@DataJpaTest`, `@WebMvcTest`, `@SpringBootTest`), Testcontainers via `@ServiceConnection`, `@MockkBean`, Awaitility, runTest patterns                     |
| `kotlin-spring-async-processing`   | `@Async`, `ApplicationEvent`, `@TransactionalEventListener`, `@Scheduled` patterns with Virtual Thread / coroutine interop, executor configuration, `@Async` vs coroutines decision    |
| `kotlin-gradle-build-optimization` | Gradle Kotlin DSL, version catalog, build cache, configuration cache, parallel execution, kotlin-jpa / kotlin-spring / kotlin-allopen plugins, springmockk + mockito-core exclusion    |

### Workflow skills (8)

| Skill                              | Agent                          | Description                                                                                                                                                                                |
| ---------------------------------- | ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `task-kotlin-implement`            | `kotlin-architect`             | End-to-end Kotlin + Spring Boot feature implementation (stack detect, requirements, design approval, code, migration, tests, validation) with Kotlin idioms throughout                    |
| `task-kotlin-debug`                | `kotlin-architect`             | Debug Kotlin-specific errors (null safety, coroutines, MockK, JPA plugin, Jackson serialization, Spring startup) with classification tables                                                |
| `task-kotlin-review`               | `kotlin-tech-lead`             | Kotlin/Spring Boot staff-level code review umbrella (Phases A-E + scope auto-escalation). Spawns Kotlin perf / security / observability subagents in parallel                              |
| `task-kotlin-review-perf`          | `kotlin-performance-engineer`  | Kotlin/Spring Boot perf review for JPA N+1, fetch strategies, coroutine dispatcher / Virtual Thread interop, HikariCP sizing, Flow backpressure, caching                                   |
| `task-kotlin-review-security`      | `kotlin-security-engineer`     | Kotlin/Spring Boot security review for Spring Security 6.x Kotlin DSL, OAuth2/JWT, method security, mass assignment via data class DTOs, coroutine SecurityContext propagation, OWASP    |
| `task-kotlin-review-observability` | `kotlin-tech-lead`             | Kotlin/Spring Boot observability review for Micrometer, Actuator, structured logging, MDC + coroutine context correlation, OTel tracing, async/messaging instrumentation, error tracker   |
| `task-kotlin-test`                 | `kotlin-test-engineer`         | Kotlin/Spring Boot test strategy and scaffolding using JUnit 5 / Kotest, MockK + springmockk, Spring test slices, Testcontainers, runTest, Turbine, Spring Security Test                  |
| `task-kotlin-refactor`             | `kotlin-tech-lead`             | Kotlin/Spring Boot refactor planning for fat controllers, anemic domain, `!!` abuse, GlobalScope leakage, blocking-in-suspend, lateinit overuse, data class JPA, missing kotlin plugins   |
