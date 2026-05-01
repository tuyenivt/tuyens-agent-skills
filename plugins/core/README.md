# Tuyen's Agent Skills - Core

Stack-agnostic Claude Code core plugin providing ops, governance, and framework-aware workflows for **any** tech stack. Detects the project stack from marker files and your repo context file, then adapts universal engineering principles to the detected ecosystem. Includes universal `task-feature-implement` and `task-code-debug` entry points that delegate to stack-specific workflows.

## Stack Detection

The core detects your project's tech stack automatically, in this priority order:

1. **Marker files (primary)**: Checks well-known files (`build.gradle`, `Gemfile`, `go.mod`, `package.json`, `Cargo.toml`, `pyproject.toml`, `mix.exs`, `*.csproj`, etc.) to determine language and build tool reliably.
2. **Repo context file (supplemental)**: Reads the `## Tech Stack` section of your context file (`CLAUDE.md`, `AGENTS.md`, or `GEMINI.md`) for details that marker files cannot provide - framework, database, ORM, test framework.

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

11 workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. Invoked as slash commands.

| Skill                            | Description                                                                                                                                                                                                                                                           |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-feature-implement`         | Universal feature implementation entry point. Detects stack and delegates to the appropriate `task-{stack}-new` workflow.                                                                                                                                             |
| `task-code-debug`                | Universal debugging entry point. Detects stack and delegates to `task-{stack}-debug`, or runs systematic classify-locate-fix.                                                                                                                                         |
| `task-code-explain`              | Explain a specific file, function, or module - what it does, where it sits in the flow, why it exists, non-obvious gotchas, key invariants, and what to double-check before modifying it.                                                                             |
| `task-db-migration-plan`         | Safe database migration planning - zero-downtime strategy, expand-contract sequencing, rollback plan, backfill estimation, and lock risk assessment.                                                                                                                  |
| `task-onboard-codebase`          | Codebase onboarding for engineers new to a project - detect stack, capture local bootstrap and contribution workflow, map architecture and ecosystem, extract patterns, flag tech debt and first-PR safe zones. Supports `Focus: first-pr / architect-survey / full`. |
| `task-code-refactor`             | Safe refactoring plan with risk assessment. Auto-detects stack and adapts refactoring patterns.                                                                                                                                                                       |
| `task-code-review`               | Staff-level code review for pull requests with risk assessment, architecture boundary protection, AI-generated code quality control, and stack-adapted checks. Supports `quick`, `standard`, and `deep` depth levels.                                                 |
| `task-code-perf-review`          | Performance review for backend and frontend. Auto-detects stack and adapts performance checks. Supports `quick`, `standard`, and `deep` depth levels.                                                                                                                 |
| `task-code-secure-review`        | Security review covering OWASP Top 10, auth, and stack-specific vulnerabilities. Auto-detects stack.                                                                                                                                                                  |
| `task-code-observability-review` | Observability review covering structured logging, RED metrics, distributed tracing, correlation propagation, and SLO/alerting coverage. Auto-detects stack. Supports `quick`, `standard`, and `deep` depth levels.                                                    |
| `task-code-test`                 | Test strategy, scaffolds, and quality review. Auto-detects stack and adapts test patterns.                                                                                                                                                                            |

## Atomic Skills

34 atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

### Core Utility

| Skill                   | Description                                                                                                                                                                                               |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `behavioral-principles` | Cross-cutting behavioral guardrails loaded at the start of every workflow - verify assumptions, surface confusion, present tradeoffs, push back on likely-wrong requests, and match scope to the request. |
| `stack-detect`          | Detect project tech stack from marker files and the repo context file - extracts any declared properties as key-value pairs. Stack-agnostic.                                                              |

### Architecture

| Skill                           | Description                                                                                              |
| ------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `architecture-concurrency`      | Concurrency patterns adapted to the detected stack - threading models, synchronization, safe concurrency |
| `architecture-data-consistency` | Consistency strategy selection across data boundaries                                                    |
| `nfr-specification`             | Elicit and structure NFRs from business context into measurable SLOs and constraints                     |
| `tradeoff-analysis`             | Structured architectural decision and trade-off documentation                                            |

### Performance

| Skill                   | Description                                                                                          |
| ----------------------- | ---------------------------------------------------------------------------------------------------- |
| `backend-caching`       | Caching patterns, response optimization, and serialization efficiency. Adapts to detected ecosystem. |
| `architecture-capacity` | Throughput estimation, scaling analysis, and bottleneck prediction                                   |
| `backend-db-indexing`   | Database index strategy and query optimization                                                       |
| `backend-db-migration`  | Universal zero-downtime database migration patterns - expand-contract, lock risk, backfill safety.   |

### Ops

| Skill                          | Description                                                                                         |
| ------------------------------ | --------------------------------------------------------------------------------------------------- |
| `ops-backward-compatibility`   | API, event, and data contract backward compatibility assessment                                     |
| `dependency-impact-analysis`   | Deployment ordering and dependency change impact assessment                                         |
| `ops-failure-classification`   | Classify production failures by type, mechanism, and system layer                                   |
| `failure-propagation-analysis` | Trace failure propagation paths across service and system boundaries                                |
| `ops-observability`            | Structured logging, metrics, and distributed tracing. Adapts to detected ecosystem.                 |
| `ops-release-safety`           | Rollout, rollback, and deployment risk patterns                                                     |
| `ops-resiliency`               | Resilience patterns - circuit breakers, retries, timeouts, bulkheads. Adapts to detected ecosystem. |
| `ops-feature-flags`            | Feature flag lifecycle - flag design, gradual rollout, rollback, and cleanup discipline.            |

### Integration

| Skill                 | Description                                                             |
| --------------------- | ----------------------------------------------------------------------- |
| `backend-idempotency` | Idempotency key pattern for safe retries. Adapts to detected ecosystem. |

### Governance

| Skill                        | Description                                                                                                |
| ---------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `backend-api-guidelines`     | REST API design - resource naming, HTTP methods, error handling, pagination. Adapts to detected ecosystem. |
| `architecture-guardrail`     | Layer violation and boundary erosion detection. Adapts to detected ecosystem.                              |
| `review-blast-radius`        | Failure propagation and change impact scope assessment                                                     |
| `review-change-risk`         | Pre-implementation risk domain classification for proposed changes                                         |
| `backend-coding-standards`   | Coding conventions adapted to the detected stack - naming, structure, anti-patterns                        |
| `complexity-review`          | Complexity assessment - cyclomatic complexity, cognitive load, abstraction depth                           |
| `ops-engineering-governance` | Engineering process, governance improvement, and guardrail evolution for incident prevention               |
| `review-pr-risk`             | Lightweight heuristic PR risk classification based on change signals                                       |

### Frontend

| Skill                       | Description                                                                                                                                                      |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `frontend-state-management` | State management patterns: local vs global, when to lift state, derived state, state normalization. Adapts to detected stack (Redux, Pinia, NgRx, Zustand, etc.) |
| `frontend-testing-patterns` | Frontend testing: component testing, integration testing, e2e with Playwright/Cypress, mocking APIs (MSW), snapshot discipline. Adapts to detected stack         |
| `frontend-accessibility`    | WCAG 2.1 AA compliance: semantic HTML, ARIA, keyboard navigation, focus management, color contrast, screen reader testing                                        |
| `frontend-api-integration`  | Data fetching patterns: loading/error states, caching, optimistic updates, pagination. Adapts to detected stack (TanStack Query, SWR, Apollo, etc.)              |
| `frontend-performance`      | Core Web Vitals, bundle splitting, lazy loading, image optimization, render performance, memoization discipline                                                  |
| `frontend-form-handling`    | Form patterns: validation, error display, multi-step forms, dirty tracking, submission handling. Adapts to detected stack                                        |

## Skill Dependency Index

Quick reference showing which atomic skills each workflow invokes. Use this to understand scope before customizing or extending a workflow.

### Workflow → Atomics

| Workflow                         | Atomic Skills Used                                                                                                                                                                                                                                            |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-feature-implement`         | `stack-detect` _(then delegates to stack-specific workflow)_                                                                                                                                                                                                  |
| `task-code-debug`                | `stack-detect` _(then delegates to stack-specific workflow)_                                                                                                                                                                                                  |
| `task-onboard-codebase`          | `stack-detect`, `architecture-guardrail`, `complexity-review`, `backend-coding-standards`, `ops-observability`, `dependency-impact-analysis`                                                                                                                  |
| `task-code-refactor`             | `stack-detect`, `backend-coding-standards`, `architecture-concurrency`, `architecture-guardrail`                                                                                                                                                              |
| `task-code-review`               | `stack-detect`, `review-pr-risk`, `review-blast-radius`, `architecture-guardrail`, `complexity-review`, `backend-coding-standards`, `backend-api-guidelines`, `architecture-concurrency`, `ops-observability`, `ops-resiliency`, `ops-backward-compatibility` |
| `task-code-perf-review`          | `stack-detect`, `backend-caching`, `backend-db-indexing`, `ops-observability`, `architecture-concurrency`                                                                                                                                                     |
| `task-code-secure-review`        | `stack-detect`, `ops-observability`, `ops-resiliency`, `backend-idempotency`, `backend-api-guidelines`                                                                                                                                                        |
| `task-code-observability-review` | `stack-detect`, `ops-observability`                                                                                                                                                                                                                           |
| `task-code-test`                 | `stack-detect`, `backend-coding-standards`, `backend-api-guidelines`                                                                                                                                                                                          |
| `task-code-explain`              | `stack-detect`, `architecture-guardrail`, `architecture-concurrency`, `complexity-review`                                                                                                                                                                     |
| `task-db-migration-plan`         | `review-change-risk`, `ops-backward-compatibility`, `backend-db-indexing`, `backend-idempotency`, `ops-release-safety`, `dependency-impact-analysis`, `review-blast-radius`                                                                                   |

### Atomic → Used By (Reuse Count)

Atomics used by the most workflows - highest customization leverage:

| Atomic Skill                 | Used By                                                                                                                           | Count |
| ---------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `stack-detect`               | all except `task-db-migration-plan`                                                                                               | 10    |
| `ops-observability`          | `task-onboard-codebase`, `task-code-review`, `task-code-perf-review`, `task-code-secure-review`, `task-code-observability-review` | 5     |
| `architecture-guardrail`     | `task-onboard-codebase`, `task-code-refactor`, `task-code-review`, `task-code-explain`                                            | 4     |
| `backend-coding-standards`   | `task-onboard-codebase`, `task-code-refactor`, `task-code-review`, `task-code-test`                                               | 4     |
| `ops-resiliency`             | `task-code-review`, `task-code-perf-review`, `task-code-secure-review`                                                            | 3     |
| `architecture-concurrency`   | `task-code-refactor`, `task-code-review`, `task-code-perf-review`, `task-code-explain`                                            | 4     |
| `backend-api-guidelines`     | `task-code-review`, `task-code-secure-review`, `task-code-test`                                                                   | 3     |
| `backend-db-indexing`        | `task-code-perf-review`, `task-db-migration-plan`                                                                                 | 2     |
| `review-blast-radius`        | `task-code-review`, `task-db-migration-plan`                                                                                      | 2     |
| `ops-backward-compatibility` | `task-db-migration-plan`                                                                                                          | 1     |
| `dependency-impact-analysis` | `task-db-migration-plan`, `task-onboard-codebase`                                                                                 | 2     |
| `review-change-risk`         | `task-db-migration-plan`                                                                                                          | 1     |

## Usage Examples

**Staff-level code review (auto-detects framework, includes risk assessment):**

```
/task-code-review
[paste code or file path]
```

Scope options - asks interactively if not specified:

```
/task-code-review +perf            # Core + performance review
/task-code-review +security        # Core + security review
/task-code-review +observability   # Core + observability review
/task-code-review full             # Core + performance + security + observability
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

Reads the repo, detects stack, captures local bootstrap and contribution workflow, maps architecture and ecosystem topology, extracts the team's actual patterns, and surfaces tech debt hotspots, first-PR safe zones, and operational gaps.

```
/task-onboard-codebase
Focus: first-pr
```

Optimizes the report for an engineer who needs to ship their first PR quickly: leads with Local Quickstart, contribution workflow, and recommended safe entry areas.

```
/task-onboard-codebase
Focus: architect-survey
Scope: payments module
Known pain points: checkout flow is slow and poorly tested
```

