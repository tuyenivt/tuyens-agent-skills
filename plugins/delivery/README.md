# Tuyen's Agent Skills - Delivery

Software delivery plugin for Claude Code: release planning, scope breakdown, sprint-fit sizing, tech debt triage, dependency upgrade assessment, and cross-PR conflict detection.

## Installation

```bash
claude plugin install core@tuyens-agent-skills --scope project
claude plugin install delivery@tuyens-agent-skills --scope project
```

## Optional: Share Skills Between Claude Code and Codex

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/delivery/skills" "$HOME/.codex/skills/tuyens-agent-skills-delivery-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-delivery-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/delivery/skills"
```

## Requirements

- Claude Code >= 2.0.0

## Workflow Skills

5 workflow skills (`task-*`) for delivery planning and coordination.

| Skill                       | Description                                                                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-release-plan`         | Staff-level production release planning. Supports `quick`, `standard`, and `deep` depth levels with canary metrics and rollback drill plan. |
| `task-scope-breakdown`      | Break an epic or feature into implementable tasks with effort sizing, dependency ordering, hidden complexity signals, and sprint-fit mode.  |
| `task-debt-triage`          | Prioritize technical debt by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog.                  |
| `task-dependency-upgrade`   | Assess a library or platform version upgrade - breaking changes, migration effort, compatibility, and Go/No-Go recommendation.              |
| `task-pr-conflict-analysis` | Detect semantic conflicts across concurrent PRs - logical incompatibilities, shared state mutations, and integration ordering risks.        |

## Atomic Skills

No plugin-local atomics. All atomic skills used by delivery workflows live in the `core` plugin and resolve at runtime when both plugins are installed.

### Core Atomics Used by Delivery Workflows

| Core Atomic                       | Used By                                                                  |
| --------------------------------- | ------------------------------------------------------------------------ |
| `stack-detect`                    | `task-release-plan`, `task-scope-breakdown`                              |
| `blast-radius-analysis`           | `task-release-plan`, `task-scope-breakdown`                              |
| `backward-compatibility-analysis` | `task-release-plan`, `task-scope-breakdown`                              |
| `dependency-impact-analysis`      | `task-release-plan`, `task-scope-breakdown`, `task-pr-conflict-analysis` |
| `change-risk-classification`      | `task-scope-breakdown`                                                   |
| `release-safety`                  | `task-release-plan`                                                      |
| `pr-risk-analysis`                | `task-release-plan`                                                      |
| `failure-classification`          | `task-release-plan`                                                      |
| `capacity-modeling`               | `task-release-plan`                                                      |
| `engineering-governance`          | `task-release-plan`                                                      |
| `api-guidelines`                  | `task-release-plan`                                                      |
| `data-consistency-modeling`       | `task-release-plan`                                                      |
| `idempotency`                     | `task-release-plan`                                                      |
| `db-indexing`                     | `task-release-plan`                                                      |
| `resiliency`                      | `task-release-plan`                                                      |
| `observability`                   | `task-release-plan`                                                      |
| `caching`                         | `task-release-plan`                                                      |
| `concurrency-model`               | `task-release-plan`                                                      |

## Usage Examples

**Production release planning:**

```
/task-release-plan
Feature: New order payment flow with Stripe integration
DB migration: adds payment_intent_id column to orders table
Traffic expectation: 500 RPS steady state
```

**Break down an epic into tasks:**

```
/task-scope-breakdown
Epic: User authentication overhaul - migrate from session-based to JWT
```

**Sprint-fit mode (pass team size and sprint length):**

```
/task-scope-breakdown
Epic: Payment processing V2
Team: 4 engineers
Sprint: 2 weeks
```

**Triage tech debt:**

```
/task-debt-triage
```

**Assess a dependency upgrade:**

```
/task-dependency-upgrade
Upgrade: Spring Boot 3.3 -> 3.5
```

**Check concurrent PR conflicts before batch-merging:**

```
/task-pr-conflict-analysis
```
