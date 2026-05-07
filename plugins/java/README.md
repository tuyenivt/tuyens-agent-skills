# Tuyen's Agent Skills - Java / Spring Boot

Claude Code plugin for Java 21+ / Spring Boot 3.5+ development.

## Stack

- Java 21+
- Spring Boot 3.5+ (Spring Boot 4 best-effort)
- Gradle

## Key Features

- **Virtual Threads**: All skills enforce Virtual Thread compatibility (no `synchronized`)
- **Java 21+ Patterns**: Records for DTOs, pattern matching, sealed classes
- **Spring Boot 3.5+**: Jakarta EE 10 (EE 11 for Spring Boot 4), optimized connection pools (10-40)
- **JPA/Hibernate**: N+1 prevention, fetch strategies, query optimization
- **Flyway Migrations**: Zero-downtime DDL, expand-then-contract patterns
- **Spring Security 6.x**: SecurityFilterChain, OAuth2/JWT, method security
- **Gradle**: Version catalogs, convention plugins, build cache optimization
- **Testing**: Spring test slices, Testcontainers, JUnit 5, Mockito

## Workflow Skills

Workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. They are invoked as slash commands.

| Skill                              | Agent                       | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| ---------------------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-spring-implement`            | `spring-architect`          | End-to-end Spring Boot feature implementation (entity + migration + API + tests)                                                                                                                                                                                                                                                                                                                                                                                                       |
| `task-spring-debug`                | `java-tech-lead`            | Developer debugging workflow (paste stack trace, get fix)                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `task-spring-review-perf`          | `java-performance-engineer` | Spring-specific performance review: JPA/Hibernate N+1, fetch strategies, `LazyInitializationException`, HikariCP sizing, Virtual Thread compatibility, Spring caching, messaging throughput. Delegate of `task-code-review-perf` when stack is Spring Boot.                                                                                                                                                                                                                            |
| `task-spring-review-security`      | `java-security-engineer`    | Spring-specific security review: `SecurityFilterChain`, OAuth2/JWT, `@PreAuthorize`, Bean Validation, mass-assignment via DTO, Actuator exposure, Spring-aware OWASP Top 10. Delegate of `task-code-review-security` when stack is Spring Boot.                                                                                                                                                                                                                                        |
| `task-spring-test`                 | `java-test-engineer`        | Spring-specific test strategy and scaffolding: JUnit 5, Spring slices (`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`), Testcontainers (PostgreSQL via `@ServiceConnection`), Mockito strict stubbing, Spring Security Test. Delegate of `task-code-test` when stack is Spring Boot.                                                                                                                                                                                                       |
| `task-spring-review`               | `java-tech-lead`            | Spring-specific staff-level code review umbrella: Phases A-E (risk, correctness, architecture, AI quality, maintainability) with Spring idioms (layer boundaries, fat controllers, JPA-in-API, `@Transactional` self-invocation, anemic domain, `@Autowired` field injection, Virtual Thread pinning). Spawns Spring perf/security/observability subagents for extra scopes. Delegate of `task-code-review` when stack is Spring Boot. Runs standalone with full PR/branch resolution. |
| `task-spring-review-observability` | `java-tech-lead`            | Spring-specific observability review: Logback + Logstash JSON, MDC correlation, Spring Boot Actuator exposure, Micrometer metrics with bounded tag cardinality, Micrometer Tracing (Boot 3+) / OTel, Kafka / RabbitMQ listener observation, error-tracker Boot starters. Delegate of `task-code-review-observability` when stack is Spring Boot.                                                                                                                                       |
| `task-spring-refactor`             | `java-tech-lead`            | Spring-specific refactor planning: fat controllers, anemic domain, service god-objects, `@Transactional` self-invocation, single-implementation interface bloat, `@Autowired` field injection, JPA `@PostUpdate` callback abuse. Test-coverage gate + step-by-step independently committable plan. Delegate of `task-code-refactor` when stack is Spring Boot.                                                                                                                         |

## Atomic Skills (Reusable Patterns)

Atomic skills provide focused, reusable Java/Spring Boot patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

| Skill                            | Purpose                                                                 |
| -------------------------------- | ----------------------------------------------------------------------- |
| `spring-jpa-performance`         | JPA optimization and N+1 prevention                                     |
| `spring-transaction`             | Spring `@Transactional` scope and propagation                           |
| `spring-exception-handling`      | Centralized `@RestControllerAdvice` error handling                      |
| `spring-async-processing`        | Spring `@Async` with Virtual Threads                                    |
| `spring-db-migration-safety`     | Flyway/Liquibase zero-downtime DDL patterns                             |
| `spring-test-integration`        | `@DataJpaTest`, `@WebMvcTest`, Testcontainers                           |
| `spring-security-patterns`       | Spring Security 6.x configuration                                       |
| `java-gradle-build-optimization` | Gradle build performance and multi-module setup                         |
| `spring-websocket`               | Spring WebSocket and STOMP messaging                                    |
| `spring-messaging-patterns`      | Spring Kafka, RabbitMQ, transactional outbox, Spring Application Events |

## Agents

| Agent                       | Focus                                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------------- |
| `spring-architect`          | Spring Boot architecture, JPA, APIs, performance                                            |
| `java-tech-lead`            | Java/Spring code review, refactoring guidance, doc standards, JPA patterns, Virtual Threads |
| `java-test-engineer`        | JUnit 5, Testcontainers, Spring test slices                                                 |
| `java-security-engineer`    | Spring Security 6.x, OWASP for Java                                                         |
| `java-performance-engineer` | JVM/Spring/JPA performance, GC tuning                                                       |

## Usage Examples

**Implement full feature (entity + migration + API + tests):**

```
/task-spring-implement
Feature: Order with payment tracking
Package: com.example.order
Operations: CRUD, approve, cancel
Relationships: ManyToOne to Customer
```

**Debug a stack trace:**

```
/task-spring-debug
[paste stack trace or error message]
```

## Core Plugin Skills

The following workflows are provided by `core` (install separately):

- `/task-code-review` - Staff-level code review with risk assessment, framework-aware
- `/task-code-review-security` - Security review
- `/task-code-test` - Test strategy
- `/task-code-refactor` - Refactoring plan
- `/task-code-review-perf` - Performance review
