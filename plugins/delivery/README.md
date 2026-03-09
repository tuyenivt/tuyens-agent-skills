# Tuyen's Agent Skills - Delivery

Software delivery plugin for Claude Code: release planning, scope breakdown, tech debt triage, dependency upgrade assessment, and cross-PR conflict detection.

## Workflow Skills

5 workflow skills (`task-*`) for delivery planning and coordination.

| Skill                       | Description                                                                                                                                                                      |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-release-plan`         | Staff-level production release planning. Supports `quick`, `standard`, and `deep` depth levels with canary metrics and rollback drill plan.                                      |
| `task-scope-breakdown`      | Break a feature or epic into implementable tasks with dependency ordering, relative sizing, and scope creep risk flags. Surfaces hidden complexity before implementation starts. |
| `task-debt-triage`          | Prioritize technical debt by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog.                                                       |
| `task-dependency-upgrade`   | Assess a library or platform version upgrade - breaking changes, migration effort, compatibility, and Go/No-Go recommendation.                                                   |
| `task-pr-conflict-analysis` | Detect semantic conflicts across concurrent PRs - logical incompatibilities, shared state mutations, and integration ordering risks.                                             |

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
| `db-migration-safety`             | `task-release-plan`, `task-scope-breakdown`                              |
| `feature-flags`                   | `task-release-plan`, `task-scope-breakdown`                              |
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

**Break down a feature into tasks:**

```
/task-scope-breakdown
Feature: User authentication overhaul - migrate from session-based to JWT
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
