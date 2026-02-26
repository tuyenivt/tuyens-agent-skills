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

## Installation

All three plugins are required, installed in order:

```
/plugin install core@tuyens-agent-skills
/plugin install java@tuyens-agent-skills
/plugin install kotlin@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/kotlin/skills" "$HOME/.codex/skills/tuyens-agent-skills-kotlin-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-kotlin-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/kotlin/skills"
```

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
| Flyway migration safety   | (same — delegates to Java plugin)          |

## Plugin contents

### Agent (1)

| Agent              | Description                                                                                                                             |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| `kotlin-architect` | Kotlin + Spring Boot architect. Extends the Java `spring-architect` with Kotlin idioms. Delegates core Spring decisions to Java plugin. |

### Atomic skills (3)

| Skill                      | Description                                                                                                                 |
| -------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `kotlin-idioms`            | Data classes, null safety, extension functions, scope functions, sealed classes, inline value classes, Kotlin-Java interop  |
| `kotlin-coroutines-spring` | Suspend functions in services, Flow streaming, coroutine-aware transactions, Virtual Thread interop, structured concurrency |
| `kotlin-testing-patterns`  | MockK mocking, kotest matchers, @MockkBean, coroutine testing with runTest/turbine                                          |

### Workflow skills (2)

| Skill               | Description                                                                           | Delegates to Java plugin                                       |
| ------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `task-kotlin-new`   | Create a new Kotlin + Spring Boot resource (entity, DTOs, service, controller, tests) | `db-migration-safety` for Flyway, test slices from Java plugin |
| `task-kotlin-debug` | Debug Kotlin-specific errors (null safety, coroutines, MockK, JPA plugin config)      | `task-spring-debug` for Java/Spring errors                     |

### Total: 1 agent + 5 skills (intentionally small — this is a companion plugin)

## Dependency relationship

```
core   (base patterns, git, code quality)
  └── java     (Spring Boot, JPA, Security, Gradle, testing infra)
        └── kotlin  (Kotlin idioms, coroutines, MockK/kotest)
```

The Kotlin plugin **never duplicates** Java plugin content. It references Java plugin skills
by name (e.g., `jpa-performance`, `transaction`, `db-migration-safety`, `task-spring-debug`) and
adds only the Kotlin-specific layer on top.
