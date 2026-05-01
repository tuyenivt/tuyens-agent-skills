# Tuyen's Agent Skills - Delivery

Software delivery plugin for Claude Code: scope breakdown and tech debt triage.

## Workflow Skills

Workflow skills (`task-*`) for delivery planning and coordination.

| Skill                  | Description                                                                                                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-scope-breakdown` | Break a feature or epic into implementable tasks with dependency ordering, relative sizing, and scope creep risk flags. Surfaces hidden complexity before implementation starts. |
| `task-debt-prioritize` | Prioritize technical debt by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog.                                                       |

## Atomic Skills

No plugin-local atomics. All atomic skills used by delivery workflows live in the `core` plugin and resolve at runtime when both plugins are installed.

### Core Atomics Used by Delivery Workflows

| Core Atomic                  | Used By                |
| ---------------------------- | ---------------------- |
| `stack-detect`               | `task-scope-breakdown` |
| `review-blast-radius`        | `task-scope-breakdown` |
| `ops-backward-compatibility` | `task-scope-breakdown` |
| `dependency-impact-analysis` | `task-scope-breakdown` |
| `review-change-risk`         | `task-scope-breakdown` |
| `backend-db-migration`       | `task-scope-breakdown` |
| `ops-feature-flags`          | `task-scope-breakdown` |

## Usage Examples

**Break down a feature into tasks:**

```
/task-scope-breakdown
Feature: User authentication overhaul - migrate from session-based to JWT
```

**Triage tech debt:**

```
/task-debt-prioritize
```

