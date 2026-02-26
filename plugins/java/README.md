# Tuyen's Agent Skills - Java / Spring Boot

Claude Code plugin for Java 21+ / Spring Boot 3.5+ development. 8 agents, 11 skills (2 workflow + 9 atomic).

> React support has been removed. This plugin focuses exclusively on Java/Spring Boot. For stack-agnostic code review, architecture, ops, and governance skills, install `core`.

## Installation

```bash
/plugin install core@tuyens-agent-skills
/plugin install java@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/java/skills" "$HOME/.codex/skills/tuyens-agent-skills-java-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-java-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/java/skills"
```

## Requirements

- Claude Code >= 2.0.0
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

| Skill               | Purpose                                                                          |
| ------------------- | -------------------------------------------------------------------------------- |
| `task-spring-new`   | End-to-end Spring Boot feature implementation (entity + migration + API + tests) |
| `task-spring-debug` | Developer debugging workflow (paste stack trace, get fix)                        |

## Atomic Skills (Reusable Patterns)

9 atomic skills provide focused, reusable Java/Spring Boot patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

| Skill                            | Purpose                                            |
| -------------------------------- | -------------------------------------------------- |
| `spring-jpa-performance`         | JPA optimization and N+1 prevention                |
| `spring-transaction`             | Spring `@Transactional` scope and propagation      |
| `spring-exception-handling`      | Centralized `@RestControllerAdvice` error handling |
| `spring-async-processing`        | Spring `@Async` with Virtual Threads               |
| `spring-db-migration-safety`     | Flyway/Liquibase zero-downtime DDL patterns        |
| `spring-test-integration`        | `@DataJpaTest`, `@WebMvcTest`, Testcontainers      |
| `spring-security-patterns`       | Spring Security 6.x configuration                  |
| `java-gradle-build-optimization` | Gradle build performance and multi-module setup    |
| `spring-websocket`               | Spring WebSocket and STOMP messaging               |

## Agents

| Agent                       | Focus                                                  |
| --------------------------- | ------------------------------------------------------ |
| `spring-architect`          | Spring Boot architecture, JPA, APIs, performance       |
| `java-tech-lead`            | Java/Spring code review, JPA patterns, Virtual Threads |
| `java-test-engineer`        | JUnit 5, Testcontainers, Spring test slices            |
| `java-security-engineer`    | Spring Security 6.x, OWASP for Java                    |
| `java-performance-engineer` | JVM/Spring/JPA performance, GC tuning                  |
| `java-reliability-engineer` | JVM ops, Actuator, HikariCP, incident response         |
| `java-refactoring-expert`   | Java modernization, Virtual Thread migration           |
| `java-technical-writer`     | JavaDoc, OpenAPI/Swagger, Spring Boot docs             |

## Usage Examples

**Implement full feature (entity + migration + API + tests):**

```
/task-spring-new
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

- `/task-code-review` — Framework-agnostic code review
- `/task-code-review-advanced` — Staff-level review with risk assessment
- `/task-code-secure` — Security review
- `/task-code-test` — Test strategy
- `/task-code-refactor` — Refactoring plan
- `/task-code-perf-review` — Performance review
- `/task-docs-generate` — Documentation generation
- `/task-incident-root-cause` — Incident root cause analysis
- `/task-incident-postmortem` — Post-incident postmortem
- `/task-release-plan` — Production release planning
- `/task-design-risk-analysis` — Proactive risk assessment
- `/task-design-architecture` — Architecture design proposal

