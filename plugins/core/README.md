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

26 workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. Invoked as slash commands. (`task-scope-breakdown` also supports `sprint-fit` mode for sprint allocation without being a separate skill.)

| Skill                       | Description                                                                                                                                          |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-feature-implement`    | Universal feature implementation entry point. Detects stack and delegates to the appropriate `task-{stack}-new` workflow.                            |
| `task-debug`                | Universal debugging entry point. Detects stack and delegates to `task-{stack}-debug`, or runs systematic classify-locate-fix.                        |
| `task-scope-breakdown`      | Break an epic or feature into implementable tasks with effort sizing, dependency ordering, hidden complexity signals, and sprint-fit mode.           |
| `task-code-explain`         | Explain a specific file, function, or module - what it does, why it is structured this way, non-obvious gotchas, and key invariants.                 |
| `task-migration-plan`       | Safe database migration planning - zero-downtime strategy, expand-contract sequencing, rollback plan, backfill estimation, and lock risk assessment. |
| `task-onboard-codebase`     | Senior engineer codebase onboarding - detect stack, map architecture, extract patterns, flag tech debt hotspots.                                     |
| `task-pr-create`            | Generate a production-ready PR description from git diff - title, summary, risk, test plan, linked tickets/ADRs.                                     |
| `task-adr-create`           | Write an Architecture Decision Record with context, alternatives, trade-offs, consequences, and review trigger.                                      |
| `task-design-api`           | REST API contract design and review. Auto-detects stack and adapts API patterns.                                                                     |
| `task-design-architecture`  | Staff-level architecture design proposal. Supports `quick`, `standard`, and `deep` depth levels.                                                     |
| `task-design-risk-analysis` | Staff-level proactive engineering risk assessment. Supports `quick`, `standard`, and `deep` depth levels.                                            |
| `task-code-refactor`        | Safe refactoring plan with risk assessment. Auto-detects stack and adapts refactoring patterns.                                                      |
| `task-code-review`          | Code review for pull requests. Auto-detects stack and adapts review criteria.                                                                        |
| `task-code-review-advanced` | Staff-level system-aware code review with risk assessment. Supports `quick`, `standard`, and `deep` depth levels.                                    |
| `task-code-perf-review`     | Performance review for backend and frontend. Auto-detects stack and adapts performance checks.                                                       |
| `task-code-secure`          | Security review covering OWASP Top 10, auth, and stack-specific vulnerabilities. Auto-detects stack.                                                 |
| `task-code-test`            | Test strategy, scaffolds, and quality review. Auto-detects stack and adapts test patterns.                                                           |
| `task-docs-generate`        | Documentation generation (README, API docs, runbooks) for any stack                                                                                  |
| `task-release-plan`         | Staff-level production release planning. Supports `quick`, `standard`, and `deep` depth levels with canary metrics and rollback drill plan.          |
| `task-incident-postmortem`  | Staff-level postmortem for systemic learning. Supports `quick`, `standard`, and `deep` depth levels.                                                 |
| `task-incident-root-cause`  | Staff-level incident root cause analysis with containment and prevention                                                                             |
| `task-debt-triage`          | Prioritize technical debt by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog.                           |
| `task-dependency-upgrade`   | Assess a library or platform version upgrade - breaking changes, migration effort, compatibility, and Go/No-Go recommendation.                       |
| `task-pr-conflict-analysis` | Detect semantic conflicts across concurrent PRs - logical incompatibilities, shared state mutations, and integration ordering risks.                 |
| `task-oncall-handoff`       | Generate a structured on-call handoff - incident summary, open alerts, known flaky areas, and context for the incoming engineer.                     |
| `task-skill-feedback`       | Capture feedback on skill output quality - record what was useful, what was adjusted, and why, to inform future skill iterations.                    |

## Atomic Skills

28 atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

> Note: `task-scope-breakdown` also supports sprint-fit mode (pass team size and sprint length to activate). This is not a separate skill - it is an extended output mode of the existing skill.

### Core Utility

| Skill          | Description                                                                                                                                    |
| -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `stack-detect` | Detect project tech stack by reading CLAUDE.md, AGENTS.md, or GEMINI.md - extracts any declared properties as key-value pairs. Stack-agnostic. |

### Architecture

| Skill                       | Description                                                                                              |
| --------------------------- | -------------------------------------------------------------------------------------------------------- |
| `concurrency-model`         | Concurrency patterns adapted to the detected stack - threading models, synchronization, safe concurrency |
| `data-consistency-modeling` | Consistency strategy selection across data boundaries                                                    |
| `system-boundary-design`    | Formal boundary modeling for module and service decomposition                                            |
| `tradeoff-analysis`         | Structured architectural decision and trade-off documentation                                            |

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
| `root-cause-hypothesis`           | Generate ranked root cause hypotheses with confidence levels and evidence                           |
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
| `review-gap-analysis`        | Analyze why existing review processes failed to catch a production failure                                 |

## Skill Dependency Index

Quick reference showing which atomic skills each workflow invokes. Use this to understand scope before customizing or extending a workflow.

### Workflow → Atomics

| Workflow                    | Atomic Skills Used                                                                                                                                                                                                                                                                                                                                                                                                          |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-feature-implement`    | `stack-detect` _(then delegates to stack-specific workflow)_                                                                                                                                                                                                                                                                                                                                                                |
| `task-debug`                | `stack-detect` _(then delegates to stack-specific workflow)_                                                                                                                                                                                                                                                                                                                                                                |
| `task-onboard-codebase`     | `stack-detect`, `architecture-guardrail`, `complexity-review`, `coding-standards`, `observability`                                                                                                                                                                                                                                                                                                                          |
| `task-pr-create`            | `stack-detect`, `pr-risk-analysis`                                                                                                                                                                                                                                                                                                                                                                                          |
| `task-adr-create`           | `tradeoff-analysis`                                                                                                                                                                                                                                                                                                                                                                                                         |
| `task-design-api`           | `stack-detect`, `api-guidelines`, `backward-compatibility-analysis`                                                                                                                                                                                                                                                                                                                                                         |
| `task-design-architecture`  | `stack-detect`, `architecture-guardrail`, `blast-radius-analysis`, `system-boundary-design`, `data-consistency-modeling`, `idempotency`, `caching`, `resiliency`, `failure-classification`, `failure-propagation-analysis`, `observability`, `payload-optimization`, `db-indexing`, `capacity-modeling`, `release-safety`, `dependency-impact-analysis`, `concurrency-model`, `tradeoff-analysis`, `engineering-governance` |
| `task-design-risk-analysis` | `stack-detect`, `change-risk-classification`, `pr-risk-analysis`, `failure-classification`, `architecture-guardrail`, `complexity-review`, `blast-radius-analysis`, `failure-propagation-analysis`, `data-consistency-modeling`, `idempotency`, `resiliency`, `release-safety`, `backward-compatibility-analysis`, `dependency-impact-analysis`, `observability`, `engineering-governance`                                  |
| `task-code-refactor`        | `stack-detect`, `coding-standards`, `concurrency-model`, `architecture-guardrail`                                                                                                                                                                                                                                                                                                                                           |
| `task-code-review`          | `stack-detect`, `coding-standards`, `api-guidelines`, `architecture-guardrail`, `concurrency-model`, `observability`, `resiliency`                                                                                                                                                                                                                                                                                          |
| `task-code-review-advanced` | `stack-detect`, `pr-risk-analysis`, `blast-radius-analysis`, `architecture-guardrail`, `complexity-review`, `coding-standards`, `observability`, `resiliency`, `api-guidelines`                                                                                                                                                                                                                                             |
| `task-code-perf-review`     | `stack-detect`, `concurrency-model`, `caching`, `db-indexing`, `observability`, `resiliency`, `payload-optimization`                                                                                                                                                                                                                                                                                                        |
| `task-code-secure`          | `stack-detect`, `observability`, `resiliency`, `idempotency`, `api-guidelines`                                                                                                                                                                                                                                                                                                                                              |
| `task-code-test`            | `stack-detect`, `coding-standards`, `api-guidelines`                                                                                                                                                                                                                                                                                                                                                                        |
| `task-docs-generate`        | `stack-detect`, `api-guidelines`, `coding-standards`                                                                                                                                                                                                                                                                                                                                                                        |
| `task-release-plan`         | `stack-detect`, `pr-risk-analysis`, `blast-radius-analysis`, `failure-classification`, `backward-compatibility-analysis`, `api-guidelines`, `data-consistency-modeling`, `idempotency`, `db-indexing`, `release-safety`, `resiliency`, `observability`, `dependency-impact-analysis`, `engineering-governance`, `capacity-modeling`, `caching`, `concurrency-model`                                                         |
| `task-incident-postmortem`  | `failure-classification`, `concurrency-model`, `data-consistency-modeling`, `resiliency`, `db-indexing`, `blast-radius-analysis`, `architecture-guardrail`, `complexity-review`, `review-gap-analysis`, `engineering-governance`, `observability`, `idempotency`, `coding-standards`                                                                                                                                        |
| `task-incident-root-cause`  | `failure-classification`, `blast-radius-analysis`, `failure-propagation-analysis`, `concurrency-model`, `data-consistency-modeling`, `db-indexing`, `resiliency`, `observability`, `root-cause-hypothesis`, `architecture-guardrail`, `engineering-governance`                                                                                                                                                              |
| `task-skill-feedback`       | _(none - self-contained)_                                                                                                                                                                                                                                                                                                                                                                                                   |
| `task-scope-breakdown`      | `stack-detect`, `change-risk-classification`, `backward-compatibility-analysis`, `dependency-impact-analysis`, `blast-radius-analysis`                                                                                                                                                                                                                                                                                      |
| `task-code-explain`         | `stack-detect`, `architecture-guardrail`, `concurrency-model`, `complexity-review`                                                                                                                                                                                                                                                                                                                                          |
| `task-migration-plan`       | `change-risk-classification`, `backward-compatibility-analysis`, `db-indexing`, `idempotency`, `release-safety`, `dependency-impact-analysis`, `blast-radius-analysis`                                                                                                                                                                                                                                                      |

### Atomic → Used By (Reuse Count)

Atomics used by the most workflows - highest customization leverage:

| Atomic Skill                      | Used By                                                                                                                                                                                                                                                     | Count |
| --------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `stack-detect`                    | all except `task-incident-postmortem`, `task-incident-root-cause`, `task-adr-create`, `task-migration-plan`                                                                                                                                                 | 17    |
| `observability`                   | `task-onboard-codebase`, `task-design-architecture`, `task-design-risk-analysis`, `task-code-review`, `task-code-review-advanced`, `task-code-perf-review`, `task-code-secure`, `task-release-plan`, `task-incident-postmortem`, `task-incident-root-cause` | 10    |
| `resiliency`                      | `task-design-architecture`, `task-design-risk-analysis`, `task-code-review`, `task-code-review-advanced`, `task-code-perf-review`, `task-code-secure`, `task-release-plan`, `task-incident-postmortem`, `task-incident-root-cause`                          | 9     |
| `architecture-guardrail`          | `task-onboard-codebase`, `task-design-architecture`, `task-design-risk-analysis`, `task-code-refactor`, `task-code-review`, `task-code-review-advanced`, `task-incident-postmortem`, `task-incident-root-cause`, `task-code-explain`                        | 9     |
| `blast-radius-analysis`           | `task-design-architecture`, `task-design-risk-analysis`, `task-code-review-advanced`, `task-release-plan`, `task-incident-postmortem`, `task-incident-root-cause`, `task-scope-breakdown`, `task-migration-plan`                                            | 8     |
| `concurrency-model`               | `task-design-architecture`, `task-code-refactor`, `task-code-review`, `task-code-perf-review`, `task-release-plan`, `task-incident-postmortem`, `task-incident-root-cause`, `task-code-explain`                                                             | 8     |
| `coding-standards`                | `task-onboard-codebase`, `task-code-refactor`, `task-code-review`, `task-code-review-advanced`, `task-code-test`, `task-docs-generate`, `task-incident-postmortem`                                                                                          | 7     |
| `api-guidelines`                  | `task-design-api`, `task-code-review`, `task-code-review-advanced`, `task-code-secure`, `task-code-test`, `task-docs-generate`, `task-release-plan`                                                                                                         | 7     |
| `backward-compatibility-analysis` | `task-design-api`, `task-design-risk-analysis`, `task-release-plan`, `task-scope-breakdown`, `task-migration-plan`                                                                                                                                          | 5     |
| `dependency-impact-analysis`      | `task-design-architecture`, `task-release-plan`, `task-scope-breakdown`, `task-migration-plan`                                                                                                                                                              | 4     |
| `change-risk-classification`      | `task-design-risk-analysis`, `task-scope-breakdown`, `task-migration-plan`                                                                                                                                                                                  | 3     |
| `engineering-governance`          | `task-design-architecture`, `task-design-risk-analysis`, `task-release-plan`, `task-incident-postmortem`, `task-incident-root-cause`                                                                                                                        | 5     |
| `failure-classification`          | `task-design-architecture`, `task-design-risk-analysis`, `task-release-plan`, `task-incident-postmortem`, `task-incident-root-cause`                                                                                                                        | 5     |

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

**Write an Architecture Decision Record:**

```
/task-adr-create
Decision: Use the transactional outbox pattern for event publishing
Context: We're losing events when the app crashes after DB write but before publishing to Kafka
Alternatives: Two-phase commit, direct publish inside transaction, CDC with Debezium
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

**Production release planning:**

```
/task-release-plan
Feature: New order payment flow with Stripe integration
DB migration: adds payment_intent_id column to orders table
Traffic expectation: 500 RPS steady state
```

**Incident root cause analysis:**

```
/task-incident-root-cause
[paste stack trace, logs, or error message]
```
