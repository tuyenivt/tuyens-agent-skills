# Tuyen's Agent Skills - Delivery

Software delivery plugin for Claude Code: sprint planning, scope breakdown, tech debt triage, and release notes.

## Workflow Skills

Workflow skills (`task-*`) for delivery planning and coordination.

| Skill                  | Description                                                                                                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-breakdown-epic`  | Break an epic into vertically-sliced user stories with explicit Given/When/Then acceptance criteria, demoable value, and INVEST validation. For sprint planning.                 |
| `task-breakdown-story` | Break a story (or epic) into implementable tasks with dependency ordering, relative sizing, and scope creep risk flags. Surfaces hidden complexity before implementation starts. |
| `task-debt-prioritize` | Prioritize technical debt by risk-adjusted ROI - blast radius, change frequency, and team pain. Produces a ranked backlog.                                                       |
| `task-release-notes`   | Generate stakeholder-ready release notes from a commit range or PR list. Categorized changelog plus a folded-in rollback and risk register section for on-call.                  |

`task-breakdown-epic` and `task-breakdown-story` are complementary, not substitutes: epic-level breakdown produces the sprint-board artifact - user stories (PM/QA/dev audience); story-level breakdown produces the engineering planning artifact (phased task graph with hidden-complexity surfacing).

## Atomic Skills

No plugin-local atomics. All atomic skills used by delivery workflows live in the `core` plugin and resolve at runtime when both plugins are installed.

### Core Atomics Used by Delivery Workflows

| Core Atomic                  | Used By                                                             |
| ---------------------------- | ------------------------------------------------------------------- |
| `behavioral-principles`      | all workflow skills                                                 |
| `stack-detect`               | `task-breakdown-epic`, `task-breakdown-story`, `task-release-notes` |
| `review-blast-radius`        | `task-breakdown-epic`, `task-breakdown-story`, `task-release-notes` |
| `review-change-risk`         | `task-breakdown-story`, `task-release-notes`                        |
| `ops-backward-compatibility` | `task-breakdown-story`, `task-release-notes`                        |
| `ops-release-safety`         | `task-release-notes`                                                |
| `ops-feature-flags`          | `task-breakdown-epic`, `task-breakdown-story`, `task-release-notes` |
| `backend-db-migration`       | `task-breakdown-story`, `task-release-notes`                        |
| `dependency-impact-analysis` | `task-breakdown-story`, `task-release-notes`                        |

## Usage Examples

**Slice an epic into sprint-ready user stories:**

```
/task-breakdown-epic
Feature: Members can save and resume draft orders. Primary user: signed-in member.
```

**Break down a feature into engineering tasks:**

```
/task-breakdown-story
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
