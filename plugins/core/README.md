# Tuyen's Agent Skills - Core

Stack-agnostic Claude Code core plugin providing ops, governance, and framework-aware workflows for **any** tech stack. Detects the project stack from marker files and your repo context file, then either dispatches to a stack-specific workflow (when the matching language plugin is installed) or runs a universal fallback so unknown stacks still get a usable result.

**Routers and direct workflows.** Most `task-code-*` skills (`debug`, `refactor`, `review`, `review-perf`, `review-security`, `review-observability`, `test`) are thin routers: they detect the stack and delegate to `task-{stack}-*` (e.g., `task-spring-debug`, `task-rails-review-perf`). For best results, install the matching language plugin and call the stack-specific skill directly to avoid the routing layer. `task-code-explain` and `task-onboard` instead **compose** stack-specific atomics into a single workflow output - they remain full direct workflows even when a stack matches.

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

Workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. Invoked as slash commands.

| Skill                            | Description                                                                                                                                                                                                                                                                                                                                                         |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-implement`                 | Universal feature implementation entry point. Detects stack and delegates to the appropriate `task-{stack}-new` workflow.                                                                                                                                                                                                                                           |
| `task-code-debug`                | **Router.** Detects stack and dispatches to `task-{stack}-debug`. For unknown stacks, runs a minimal generic CLASSIFY/LOCATE/ROOT-CAUSE/FIX/PREVENT protocol.                                                                                                                                                                                                       |
| `task-code-explain`              | **Composing workflow.** Explains a specific file, function, or module - composes a stack-specific `*-code-explain` atomic for framework-magic and gotchas (Spring AOP, Rails callbacks, Django signals, etc.). Falls back to universal explanation for unknown stacks.                                                                                                |
| `task-onboard`                   | **Composing workflow.** Codebase onboarding - composes a stack-specific `*-onboard-map` atomic for bootstrap commands, key files, conventions, and risk hotspots (Gradle/composer/cargo, Spring vs Rails layout, etc.). Falls back to universal map for unknown stacks. Supports `Focus: first-pr / architect-survey / full`.                                       |
| `task-pr-create`                 | Generate a production-ready PR description from git diff - title, summary, risk, test plan, linked tickets/ADRs.                                                                                                                                                                                                                                                    |
| `task-code-refactor`             | **Router.** Detects stack and dispatches to `task-{stack}-refactor`. For unknown stacks, runs a minimal generic protocol with smell identification and test-coverage gate.                                                                                                                                                                                          |
| `task-code-review`               | **Router.** Detects stack and dispatches to `task-{stack}-review`, forwarding scope (`+perf`/`+sec`/`+obs`/`full`) and depth flags. For unknown stacks, runs a minimal Phases-A-E generic review.                                                                                                                                                                  |
| `task-code-review-perf`          | **Router.** Detects stack and dispatches to `task-{stack}-review-perf`. For unknown stacks, runs a minimal generic perf review (DB / concurrency / caching / I/O / frontend).                                                                                                                                                                                       |
| `task-code-review-security`      | **Router.** Detects stack and dispatches to `task-{stack}-review-security`. For unknown stacks, runs a minimal OWASP Top 10 review.                                                                                                                                                                                                                                 |
| `task-code-review-observability` | **Router.** Detects stack and dispatches to `task-{stack}-review-observability`. For unknown stacks, runs a minimal generic review (logging / metrics / tracing / SLO).                                                                                                                                                                                             |
| `task-code-test`                 | **Router.** Detects stack and dispatches to `task-{stack}-test`. For unknown stacks, runs a minimal generic test-pyramid + prioritization protocol.                                                                                                                                                                                                                 |

## Atomic Skills

Atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

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

| Skill                        | Description                                                                                                                                                                                                                                           |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend-api-guidelines`     | REST API design - resource naming, HTTP methods, error handling, pagination. Adapts to detected ecosystem.                                                                                                                                            |
| `architecture-guardrail`     | Layer violation and boundary erosion detection. Adapts to detected ecosystem.                                                                                                                                                                         |
| `review-blast-radius`        | Failure propagation and change impact scope assessment                                                                                                                                                                                                |
| `review-change-risk`         | Pre-implementation risk domain classification for proposed changes                                                                                                                                                                                    |
| `review-precondition-check`  | Gate code-review workflows: verify clean tree, non-trunk head, locally-resolvable head ref, confirm head vs current branch when they differ, surface prior-round checkpoint (frontmatter of `review-<branch>.md`) so the workflow can decide incremental re-review. Local git only. |
| `backend-coding-standards`   | Coding conventions adapted to the detected stack - naming, structure, anti-patterns                                                                                                                                                                   |
| `complexity-review`          | Complexity assessment - cyclomatic complexity, cognitive load, abstraction depth                                                                                                                                                                      |
| `ops-engineering-governance` | Engineering process, governance improvement, and guardrail evolution for incident prevention                                                                                                                                                          |
| `review-pr-risk`             | Lightweight heuristic PR risk classification based on change signals                                                                                                                                                                                  |
| `review-prior-findings-reconcile` | Round 2+ of any `task-*-review*` workflow: classify each prior finding as Addressed / Still open / Obsolete / Needs re-check by checking whether the cited smell persists in the new diff. Binary contract; no causation linking. |
| `review-report-writer`       | Writes the completed review with YAML checkpoint frontmatter (head_sha, base_sha, mode, round) so the next round can auto-detect incremental scope. Called as the final step of all `task-*-review*` workflows.                                       |

## Skill Dependency Index

Quick reference showing which atomic skills each workflow invokes. Use this to understand scope before customizing or extending a workflow.

### Workflow → Atomics

| Workflow                         | Atomic Skills Used                                                                                                                                                                                                                                                                         |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `task-implement`                 | `stack-detect` _(then delegates to stack-specific workflow)_                                                                                                                                                                                                                               |
| `task-code-debug`                | `stack-detect` _(then dispatches to stack-specific workflow; minimal generic fallback when no match)_                                                                                                                                                                                      |
| `task-onboard`                   | `stack-detect` + `*-onboard-map` (per stack), `architecture-guardrail`, `complexity-review`, `backend-coding-standards`, `ops-observability`, `dependency-impact-analysis`                                                                                                                  |
| `task-pr-create`                 | `stack-detect`, `review-pr-risk`                                                                                                                                                                                                                                                           |
| `task-code-refactor`             | `stack-detect` _(dispatches to stack-specific workflow; generic fallback uses `review-blast-radius`, `ops-backward-compatibility`)_                                                                                                                                                        |
| `task-code-review`               | `stack-detect` _(dispatches; generic fallback uses `review-precondition-check`, `review-pr-risk`, `review-blast-radius`, `architecture-guardrail`, `complexity-review`, `backend-coding-standards`, `backend-api-guidelines`, `architecture-concurrency`, `ops-observability`, `ops-resiliency`, `ops-backward-compatibility`, `review-report-writer`)_ |
| `task-code-review-perf`          | `stack-detect` _(dispatches; generic fallback uses `review-precondition-check`, `backend-db-indexing`, `ops-observability`, `architecture-concurrency`, `review-report-writer`)_                                                                                                                                    |
| `task-code-review-security`      | `stack-detect` _(dispatches; generic fallback uses `review-precondition-check`, `review-report-writer`)_                                                                                                                                                                                    |
| `task-code-review-observability` | `stack-detect` _(dispatches; generic fallback uses `review-precondition-check`, `ops-observability`, `review-report-writer`)_                                                                                                                                                               |
| `task-code-test`                 | `stack-detect` _(dispatches; minimal generic test-pyramid fallback)_                                                                                                                                                                                                                        |
| `task-code-explain`              | `stack-detect` + `*-code-explain` (per stack), `architecture-guardrail`, `architecture-concurrency`, `complexity-review`                                                                                                                                                                    |

### Atomic → Used By

Atomics used by the most workflows - highest customization leverage:

| Atomic Skill                 | Used By                                                                                                                    |
| ---------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `stack-detect`               | all workflows                                                                                                              |
| `ops-observability`          | `task-onboard`, `task-code-review`, `task-code-review-perf`, `task-code-review-observability`                              |
| `architecture-guardrail`     | `task-onboard`, `task-code-review`, `task-code-explain`                                                                    |
| `backend-coding-standards`   | `task-onboard`, `task-code-review`                                                                                         |
| `architecture-concurrency`   | `task-code-review`, `task-code-review-perf`, `task-code-explain`                                                           |
| `ops-resiliency`             | `task-code-review`                                                                                                         |
| `backend-api-guidelines`     | `task-code-review`                                                                                                         |
| `backend-db-indexing`        | `task-code-review-perf`                                                                                                    |
| `review-blast-radius`        | `task-code-review`, `task-code-refactor`                                                                                   |
| `review-precondition-check`  | `task-code-review`, `task-code-review-perf`, `task-code-review-security`, `task-code-review-observability`                 |
| `dependency-impact-analysis` | `task-onboard`                                                                                                             |
| `review-prior-findings-reconcile` | all `task-*-review` stack workflows (round 2+ only)                                                                  |
| `review-report-writer`       | all `task-*-review*` workflows (core + all stack plugins)                                                                  |

## Usage Examples

**Staff-level code review (auto-detects framework, includes risk assessment):**

```
/task-code-review                        # current feature branch vs base (fails fast on trunk)
/task-code-review pr-50273               # PR fetched locally: git fetch origin pull/50273/head:pr-50273
/task-code-review feature/my-branch      # named branch vs base (cross-review or named self-review)
```

Scope options - asks interactively if not specified:

```
/task-code-review +perf                        # Core + performance review
/task-code-review +sec                         # Core + security review
/task-code-review +obs                         # Core + observability review
/task-code-review full                         # Core + performance + security + observability
/task-code-review pr-50273 +sec deep           # compose: PR + security + deep depth
```

**Re-review (round 2+)** is auto-detected. Rerunning the same command after the commenter pushes fixes will:

1. Look for `review-<branch>.md` from the prior round, parse its YAML checkpoint frontmatter (head_sha, base_sha, mode, round).
2. Fetch the head branch via its upstream tracking ref (no checkout). Skip silently if no upstream.
3. If the new head equals the prior head, exit with `No new commits...` - the report file is left byte-identical.
4. Otherwise scope analysis to `<prior_head_sha>...<current_head_sha>` and reconcile prior High-Impact Findings as Addressed / Still open / Obsolete / Needs re-check. Open items fold into Next Steps with `(open since round <N>)`.
5. Force fall back to full mode automatically when the prior SHA is unreachable (force-push) or the base branch advanced.

No flags needed - same invocation works for every round. Reports without frontmatter (predating this behavior) are treated as round-1.

**Test strategy:**

```
/task-code-test
[paste code or file path]
```

**Performance review:**

```
/task-code-review-perf
[paste code or file path]
```

**Onboard to a new codebase:**

```
/task-onboard
```

Reads the repo, detects stack, captures local bootstrap and contribution workflow, maps architecture and ecosystem topology, extracts the team's actual patterns, and surfaces tech debt hotspots, first-PR safe zones, and operational gaps.

```
/task-onboard
Focus: first-pr
```

Optimizes the report for an engineer who needs to ship their first PR quickly: leads with Local Quickstart, contribution workflow, and recommended safe entry areas.

```
/task-onboard
Focus: architect-survey
Scope: payments module
Known pain points: checkout flow is slow and poorly tested
```

```
/task-pr-create
```

Auto-reads `git diff main...HEAD` and commit messages. Produces title, summary, risk level, test plan, and linked tickets/ADRs.

```
/task-pr-create
Branch: feature/PROJ-123-add-payment-flow
```
