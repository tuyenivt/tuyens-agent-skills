# Tuyen's Agent Skills - Core

Stack-agnostic Claude Code core plugin providing ops, governance, and framework-aware workflows for **any** tech stack. Detects the project stack from CLAUDE.md (falls back to file-based detection) and adapts universal engineering principles to the detected ecosystem.

## Installation

```bash
# Install
/plugin install core@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/core/skills" "$HOME/.codex/skills/tuyens-agent-skills-core-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-core-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/core/skills"
```

## Requirements

- Claude Code >= 2.0.0

## Stack Detection

The core detects your project's tech stack automatically:

1. **CLAUDE.md (primary)**: Reads key-value pairs from any "Tech Stack" or similar section. Whatever you declare, the plugin uses — it does not validate against a fixed list.
2. **File-based fallback**: If CLAUDE.md has no stack section, the plugin uses a best-effort heuristic based on marker files (`build.gradle`, `Gemfile`, `go.mod`, `package.json`, `Cargo.toml`, `pyproject.toml`, `mix.exs`, `*.csproj`, etc.).

### Example CLAUDE.md entries (any stack works):

```markdown
## Tech Stack

- Language: Rust
- Framework: Actix-web
- Build: Cargo
- Database: PostgreSQL
- Test: cargo test + rstest
```

```markdown
## Tech Stack

- Language: Elixir
- Framework: Phoenix
- Build: Mix
- Database: PostgreSQL
- Test: ExUnit
```

```markdown
## Tech Stack

- Language: Python
- Framework: FastAPI
- Build: Poetry
- Database: PostgreSQL
- Test: pytest
```

```markdown
## Tech Stack

- Language: Java
- Framework: Spring Boot
- Build: Gradle
- Database: PostgreSQL
- Test: JUnit 5
```

## Workflow Skills

14 workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. Invoked as slash commands.

| Skill                       | Description                                                                                          |
| --------------------------- | ---------------------------------------------------------------------------------------------------- |
| `task-api-design`           | REST API contract design and review. Auto-detects stack and adapts API patterns.                     |
| `task-architecture-design`  | Staff-level architecture design proposal for new features and systems                                |
| `task-code-refactor`        | Safe refactoring plan with risk assessment. Auto-detects stack and adapts refactoring patterns.      |
| `task-code-review`          | Code review for pull requests. Auto-detects stack and adapts review criteria.                        |
| `task-code-review-advanced` | Staff-level system-aware code review with risk assessment. Auto-detects stack.                       |
| `task-code-secure`          | Security review covering OWASP Top 10, auth, and stack-specific vulnerabilities. Auto-detects stack. |
| `task-code-test`            | Test strategy, scaffolds, and quality review. Auto-detects stack and adapts test patterns.           |
| `task-docs-generate`        | Documentation generation (README, API docs, ADRs) for any stack                                      |
| `task-perf-review`          | Performance review for backend and frontend. Auto-detects stack and adapts performance checks.       |
| `task-postmortem`           | Staff-level postmortem for systemic learning and prevention                                          |
| `task-pr-prepare`           | PR preparation with commit messages, description, and pre-submit validation. Auto-detects stack.     |
| `task-release-plan`         | Staff-level production release planning with rollout safety and blast radius control                 |
| `task-risk-analysis`        | Staff-level proactive engineering risk assessment for proposed changes                               |
| `task-root-cause`           | Staff-level incident root cause analysis with containment and prevention                             |

## Atomic Skills

28 atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

### Core Utility

| Skill          | Description                                                                                                           |
| -------------- | --------------------------------------------------------------------------------------------------------------------- |
| `stack-detect` | Detect project tech stack by reading CLAUDE.md — extracts any declared properties as key-value pairs. Stack-agnostic. |

### Architecture

| Skill                       | Description                                                                                              |
| --------------------------- | -------------------------------------------------------------------------------------------------------- |
| `concurrency-model`         | Concurrency patterns adapted to the detected stack — threading models, synchronization, safe concurrency |
| `data-consistency-modeling` | Consistency strategy selection across data boundaries                                                    |
| `system-boundary-design`    | Formal boundary modeling for module and service decomposition                                            |
| `tradeoff-analysis`         | Structured architectural decision and trade-off documentation                                            |

### Performance

| Skill                  | Description                                                                             |
| ---------------------- | --------------------------------------------------------------------------------------- |
| `caching`              | Caching patterns — strategy, invalidation, anti-patterns. Adapts to detected ecosystem. |
| `capacity-modeling`    | Throughput estimation, scaling analysis, and bottleneck prediction                      |
| `db-indexing`          | Database index strategy and query optimization                                          |
| `payload-optimization` | API response size and serialization efficiency. Adapts to detected ecosystem.           |

### Ops

| Skill                             | Description                                                                                         |
| --------------------------------- | --------------------------------------------------------------------------------------------------- |
| `backward-compatibility-analysis` | API, event, and data contract backward compatibility assessment                                     |
| `dependency-impact-analysis`      | Deployment ordering and dependency change impact assessment                                         |
| `failure-classification`          | Classify production failures by type, mechanism, and system layer                                   |
| `failure-propagation-analysis`    | Trace failure propagation paths across service and system boundaries                                |
| `observability`                   | Structured logging, metrics, and distributed tracing. Adapts to detected ecosystem.                 |
| `release-safety`                  | Rollout, rollback, and deployment risk patterns                                                     |
| `resiliency`                      | Resilience patterns — circuit breakers, retries, timeouts, bulkheads. Adapts to detected ecosystem. |
| `root-cause-hypothesis`           | Generate ranked root cause hypotheses with confidence levels and evidence                           |
| `safe-file-operations`            | Cross-platform shell operations — always use Unix/bash commands, never Windows commands             |

### Integration

| Skill         | Description                                                             |
| ------------- | ----------------------------------------------------------------------- |
| `idempotency` | Idempotency key pattern for safe retries. Adapts to detected ecosystem. |

### Governance

| Skill                        | Description                                                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `api-guidelines`             | REST API design — resource naming, HTTP methods, error handling, pagination. Adapts to detected ecosystem. |
| `architecture-guardrail`     | Layer violation and boundary erosion detection. Adapts to detected ecosystem.                              |
| `blast-radius-analysis`      | Failure propagation and change impact scope assessment                                                     |
| `change-risk-classification` | Pre-implementation risk domain classification for proposed changes                                         |
| `coding-standards`           | Coding conventions adapted to the detected stack — naming, structure, anti-patterns                        |
| `complexity-review`          | Complexity assessment — cyclomatic complexity, cognitive load, abstraction depth                           |
| `engineering-governance`     | Engineering process, governance improvement, and guardrail evolution for incident prevention               |
| `pr-risk-analysis`           | Lightweight heuristic PR risk classification based on change signals                                       |
| `review-gap-analysis`        | Analyze why existing review processes failed to catch a production failure                                 |

## Usage Examples

**Code review (auto-detects framework):**

```
/task-code-review
[paste code or file path]
```

**Staff-level review with risk assessment:**

```
/task-code-review-advanced
[paste code or file path]
```

Scope options — asks interactively if not specified:

```
/task-code-review-advanced +perf      # Core + performance review
/task-code-review-advanced +security  # Core + security review
/task-code-review-advanced full       # Core + performance + security
```

**Test strategy:**

```
/task-code-test
[paste code or file path]
```

**Performance review:**

```
/task-perf-review
[paste code or file path]
```

**Production release planning:**

```
/task-release-plan
Feature: New order payment flow with Stripe integration
DB migration: adds payment_intent_id column to orders table
Traffic expectation: 500 RPS steady state
```

**Incident root cause analysis:**

```
/task-root-cause
[paste stack trace, logs, or error message]
```
