# Tuyen's Agent Skills - Delivery

Software delivery plugin for Claude Code: release planning, scope breakdown, tech debt triage, and dependency upgrade assessment.

## Workflow Skills

4 workflow skills (`task-*`) for delivery planning and coordination.

| Skill                  | Description                                                                                                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-release-plan`    | Staff-level production release planning. Supports `quick`, `standard`, and `deep` depth levels with canary metrics and rollback drill plan.                                      |
| `task-scope-breakdown` | Break a feature or epic into implementable tasks with dependency ordering, relative sizing, and scope creep risk flags. Surfaces hidden complexity before implementation starts. |
| `task-debt-prioritize` | Prioritize technical debt by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog.                                                       |
| `task-upgrade-plan`    | Assess a library or platform version upgrade - breaking changes, migration effort, compatibility, and Go/No-Go recommendation.                                                   |

## Atomic Skills

No plugin-local atomics. All atomic skills used by delivery workflows live in the `core` plugin and resolve at runtime when both plugins are installed.

### Core Atomics Used by Delivery Workflows

| Core Atomic                     | Used By                                     |
| ------------------------------- | ------------------------------------------- |
| `stack-detect`                  | `task-release-plan`, `task-scope-breakdown` |
| `review-blast-radius`           | `task-release-plan`, `task-scope-breakdown` |
| `ops-backward-compatibility`    | `task-release-plan`, `task-scope-breakdown` |
| `dependency-impact-analysis`    | `task-release-plan`, `task-scope-breakdown` |
| `review-change-risk`            | `task-scope-breakdown`                      |
| `backend-db-migration`          | `task-release-plan`, `task-scope-breakdown` |
| `ops-feature-flags`             | `task-release-plan`, `task-scope-breakdown` |
| `ops-release-safety`            | `task-release-plan`                         |
| `review-pr-risk`                | `task-release-plan`                         |
| `ops-failure-classification`    | `task-release-plan`                         |
| `architecture-capacity`         | `task-release-plan`                         |
| `ops-engineering-governance`    | `task-release-plan`                         |
| `backend-api-guidelines`        | `task-release-plan`                         |
| `architecture-data-consistency` | `task-release-plan`                         |
| `backend-idempotency`           | `task-release-plan`                         |
| `backend-db-indexing`           | `task-release-plan`                         |
| `ops-resiliency`                | `task-release-plan`                         |
| `ops-observability`             | `task-release-plan`                         |
| `backend-caching`               | `task-release-plan`                         |
| `architecture-concurrency`      | `task-release-plan`                         |

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
/task-debt-prioritize
```

**Assess a dependency upgrade:**

```
/task-upgrade-plan
Upgrade: Spring Boot 3.3 -> 3.5
```
