# Tuyen's Agent Skills - Core

Stack-agnostic Claude Code core plugin providing ops, governance, and framework-aware workflows for **any** tech stack. Detects the project stack from your agent instruction file (CLAUDE.md, AGENTS.md, or GEMINI.md) and adapts universal engineering principles to the detected ecosystem. Includes universal `task-feature-implement` and `task-debug` entry points that delegate to stack-specific workflows.

## Installation

```bash
claude plugin install core@tuyens-agent-skills --scope project
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

The core detects your project's tech stack automatically, in this priority order:

1. **CLAUDE.md (primary)**: Checks `./CLAUDE.md` or `.claude/CLAUDE.md`. Reads key-value pairs from any "Tech Stack" or similar section.
2. **AGENTS.md**: Checked if CLAUDE.md has no stack section. OpenAI Codex / multi-agent convention.
3. **GEMINI.md**: Checked if neither CLAUDE.md nor AGENTS.md has a stack section. Google Gemini convention.
4. **File-based fallback**: If no agent instruction file contains a stack section, uses a best-effort heuristic based on marker files (`build.gradle`, `Gemfile`, `go.mod`, `package.json`, `Cargo.toml`, `pyproject.toml`, `mix.exs`, `*.csproj`, etc.).

Whatever you declare in your instruction file, the plugin uses - it does not validate against a fixed list.

### Example entries (any stack works):

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

| Skill                       | Description                                                                                                                                           |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-feature-implement`    | Universal feature implementation entry point. Detects stack and delegates to the appropriate `task-{stack}-new` workflow.                             |
| `task-debug`                | Universal debugging entry point. Detects stack and delegates to `task-{stack}-debug`, or runs systematic classify-locate-fix.                         |
| `task-code-explain`         | Explain a specific file, function, or module - what it does, why it is structured this way, non-obvious gotchas, and key invariants.                  |
| `task-migration-plan`       | Safe database migration planning - zero-downtime strategy, expand-contract sequencing, rollback plan, backfill estimation, and lock risk assessment.  |
| `task-onboard-codebase`     | Senior engineer codebase onboarding - detect stack, map architecture, extract patterns, flag tech debt hotspots.                                      |
| `task-pr-create`            | Generate a production-ready PR description from git diff - title, summary, risk, test plan, linked tickets/ADRs.                                      |
| `task-code-refactor`        | Safe refactoring plan with risk assessment. Auto-detects stack and adapts refactoring patterns.                                                       |
| `task-code-review`          | Code review for pull requests. Auto-detects stack and adapts review criteria. Supports `quick`, `standard`, and `deep` depth levels.                  |
| `task-code-review-advanced` | Staff-level system-aware code review with risk assessment. Supports `quick`, `standard`, and `deep` depth levels.                                     |
| `task-code-perf-review`     | Performance review for backend and frontend. Auto-detects stack and adapts performance checks. Supports `quick`, `standard`, and `deep` depth levels. |
| `task-code-secure`          | Security review covering OWASP Top 10, auth, and stack-specific vulnerabilities. Auto-detects stack.                                                  |
| `task-code-test`            | Test strategy, scaffolds, and quality review. Auto-detects stack and adapts test patterns.                                                            |
| `task-docs-generate`        | Documentation generation (README, API docs, runbooks) for any stack                                                                                   |
| `task-skill-feedback`       | Capture feedback on skill output quality - record what was useful, what was adjusted, and why, to inform future skill iterations.                     |

## Atomic Skills

26 atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

### Core Utility

| Skill          | Description                                                                                                                                    |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `stack-detect` | Detect project tech stack by reading CLAUDE.md, AGENTS.md, or GEMINI.md - extracts any declared properties as key-value pairs. Stack-agnostic. |

### Architecture

| Skill                       | Description                                                                                              |
| --------------------------- | -------------------------------------------------------------------------------------------------------- |
| `concurrency-model`         | Concurrency patterns adapted to the detected stack - threading models, synchronization, safe concurrency |
| `data-consistency-modeling` | Consistency strategy selection across data boundaries                                                    |

### Performance

| Skill                  | Description                                                                             |
| ---------------------- | --------------------------------------------------------------------------------------- |
| `caching`              | Caching patterns - strategy, invalidation, anti-patterns. Adapts to detected ecosystem. |
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
| `resiliency`                      | Resilience patterns - circuit breakers, retries, timeouts, bulkheads. Adapts to detected ecosystem. |
| `safe-file-operations`            | Cross-platform shell operations - always use Unix/bash commands, never Windows commands             |

### Integration

| Skill         | Description                                                             |
| ------------- | ----------------------------------------------------------------------- |
| `idempotency` | Idempotency key pattern for safe retries. Adapts to detected ecosystem. |

### Governance

| Skill                        | Description                                                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `api-guidelines`             | REST API design - resource naming, HTTP methods, error handling, pagination. Adapts to detected ecosystem. |
| `architecture-guardrail`     | Layer violation and boundary erosion detection. Adapts to detected ecosystem.                              |
| `blast-radius-analysis`      | Failure propagation and change impact scope assessment                                                     |
| `change-risk-classification` | Pre-implementation risk domain classification for proposed changes                                         |
| `coding-standards`           | Coding conventions adapted to the detected stack - naming, structure, anti-patterns                        |
| `complexity-review`          | Complexity assessment - cyclomatic complexity, cognitive load, abstraction depth                           |
| `engineering-governance`     | Engineering process, governance improvement, and guardrail evolution for incident prevention               |
| `pr-risk-analysis`           | Lightweight heuristic PR risk classification based on change signals                                       |

## Skill Dependency Index

Quick reference showing which atomic skills each workflow invokes. Use this to understand scope before customizing or extending a workflow.

### Workflow → Atomics

| Workflow                    | Atomic Skills Used                                                                                                                                                              |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-feature-implement`    | `stack-detect` _(then delegates to stack-specific workflow)_                                                                                                                    |
| `task-debug`                | `stack-detect` _(then delegates to stack-specific workflow)_                                                                                                                    |
| `task-onboard-codebase`     | `stack-detect`, `architecture-guardrail`, `complexity-review`, `coding-standards`, `observability`                                                                              |
| `task-pr-create`            | `stack-detect`, `pr-risk-analysis`                                                                                                                                              |
| `task-code-refactor`        | `stack-detect`, `coding-standards`, `concurrency-model`, `architecture-guardrail`                                                                                               |
| `task-code-review`          | `stack-detect`, `coding-standards`, `api-guidelines`, `architecture-guardrail`, `concurrency-model`, `observability`, `resiliency`                                              |
| `task-code-review-advanced` | `stack-detect`, `pr-risk-analysis`, `blast-radius-analysis`, `architecture-guardrail`, `complexity-review`, `coding-standards`, `observability`, `resiliency`, `api-guidelines` |
| `task-code-perf-review`     | `stack-detect`, `concurrency-model`, `caching`, `db-indexing`, `observability`, `resiliency`, `payload-optimization`                                                            |
| `task-code-secure`          | `stack-detect`, `observability`, `resiliency`, `idempotency`, `api-guidelines`                                                                                                  |
| `task-code-test`            | `stack-detect`, `coding-standards`, `api-guidelines`                                                                                                                            |
| `task-docs-generate`        | `stack-detect`, `api-guidelines`, `coding-standards`                                                                                                                            |
| `task-skill-feedback`       | _(none - self-contained)_                                                                                                                                                       |
| `task-code-explain`         | `stack-detect`, `architecture-guardrail`, `concurrency-model`, `complexity-review`                                                                                              |
| `task-migration-plan`       | `change-risk-classification`, `backward-compatibility-analysis`, `db-indexing`, `idempotency`, `release-safety`, `dependency-impact-analysis`, `blast-radius-analysis`          |

### Atomic → Used By (Reuse Count)

Atomics used by the most workflows - highest customization leverage:

| Atomic Skill                      | Used By                                                                                                                                | Count |
| --------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `stack-detect`                    | all except `task-migration-plan`                                                                                                       | 10    |
| `observability`                   | `task-onboard-codebase`, `task-code-review`, `task-code-review-advanced`, `task-code-perf-review`, `task-code-secure`                  | 5     |
| `architecture-guardrail`          | `task-onboard-codebase`, `task-code-refactor`, `task-code-review`, `task-code-review-advanced`, `task-code-explain`                    | 5     |
| `coding-standards`                | `task-onboard-codebase`, `task-code-refactor`, `task-code-review`, `task-code-review-advanced`, `task-code-test`, `task-docs-generate` | 6     |
| `resiliency`                      | `task-code-review`, `task-code-review-advanced`, `task-code-perf-review`, `task-code-secure`                                           | 4     |
| `concurrency-model`               | `task-code-refactor`, `task-code-review`, `task-code-perf-review`, `task-code-explain`                                                 | 4     |
| `api-guidelines`                  | `task-code-review`, `task-code-review-advanced`, `task-code-secure`, `task-code-test`, `task-docs-generate`                            | 5     |
| `blast-radius-analysis`           | `task-code-review-advanced`, `task-migration-plan`                                                                                     | 2     |
| `backward-compatibility-analysis` | `task-migration-plan`                                                                                                                  | 1     |
| `dependency-impact-analysis`      | `task-migration-plan`                                                                                                                  | 1     |
| `change-risk-classification`      | `task-migration-plan`                                                                                                                  | 1     |

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

Scope options - asks interactively if not specified:

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
/task-code-perf-review
[paste code or file path]
```

**Onboard to a new codebase:**

```
/task-onboard-codebase
```

Reads the repo, detects stack, maps architecture and modules, extracts the team's actual patterns, and surfaces tech debt hotspots and operational gaps.

```
/task-onboard-codebase
Focus: payments module
Known pain points: checkout flow is slow and poorly tested
```

**Generate PR description from diff:**

```
/task-pr-create
```

Auto-reads `git diff main...HEAD` and commit messages. Produces title, summary, risk level, test plan, and linked tickets/ADRs.

```
/task-pr-create
Branch: feature/PROJ-123-add-payment-flow
```
