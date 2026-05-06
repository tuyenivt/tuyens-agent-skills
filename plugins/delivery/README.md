# Tuyen's Agent Skills - Delivery

Software delivery plugin for Claude Code: sprint planning, scope breakdown, tech debt triage, and release notes.

## Workflow Skills

Workflow skills (`task-*`) for delivery planning and coordination.

| Skill                  | Description                                                                                                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-story-slice`     | Break a feature or epic into vertically-sliced user stories with explicit Given/When/Then acceptance criteria, demoable value, and INVEST validation. For sprint planning.       |
| `task-scope-breakdown` | Break a feature or epic into implementable tasks with dependency ordering, relative sizing, and scope creep risk flags. Surfaces hidden complexity before implementation starts. |
| `task-debt-prioritize` | Prioritize technical debt by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog.                                                       |
| `task-release-notes`   | Generate stakeholder-ready release notes from a commit range or PR list. Categorized changelog plus a folded-in rollback and risk register section for on-call.                  |

`task-story-slice` and `task-scope-breakdown` are complementary, not substitutes: stories are the sprint-board artifact (PM/QA/dev audience); scope breakdown is the engineering planning artifact (phased task graph with hidden-complexity surfacing).

## Atomic Skills

No plugin-local atomics. All atomic skills used by delivery workflows live in the `core` plugin and resolve at runtime when both plugins are installed.

### Core Atomics Used by Delivery Workflows

| Core Atomic                  | Used By                                                          |
| ---------------------------- | ---------------------------------------------------------------- |
| `behavioral-principles`      | all workflow skills                                              |
| `stack-detect`               | `task-story-slice`, `task-scope-breakdown`, `task-release-notes` |
| `review-blast-radius`        | `task-story-slice`, `task-scope-breakdown`, `task-release-notes` |
| `review-change-risk`         | `task-scope-breakdown`, `task-release-notes`                     |
| `ops-backward-compatibility` | `task-scope-breakdown`, `task-release-notes`                     |
| `ops-release-safety`         | `task-release-notes`                                             |
| `ops-feature-flags`          | `task-story-slice`, `task-scope-breakdown`, `task-release-notes` |
| `backend-db-migration`       | `task-scope-breakdown`, `task-release-notes`                     |
| `dependency-impact-analysis` | `task-scope-breakdown`, `task-release-notes`                     |

## Usage Examples

**Slice an epic into sprint-ready user stories:**

```
/task-story-slice
Feature: Members can save and resume draft orders. Primary user: signed-in member.
```

**Break down a feature into engineering tasks:**

```
/task-scope-breakdown
Feature: User authentication overhaul - migrate from session-based to JWT
```

**Triage tech debt:**

```
/task-debt-prioritize
```

**Generate release notes for a deploy:**

```
/task-release-notes
Range: v1.4.0..HEAD
Audience: both
Deploy target: production
```
