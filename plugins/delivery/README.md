# Tuyen's Agent Skills - Delivery

Software delivery plugin for Claude Code, for architects and tech leads: design-to-tasks breakdown, task-breakdown review, and release notes.

## Workflow Skills

Workflow skills (`task-*`) for delivery planning and coordination.

| Skill                    | Description                                                                                                                                                                             |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-breakdown-design`  | Break a system design (HLD/LLD, ideally a `task-design-architecture` proposal) into an implementable task graph - phases, dependency order, critical path, sizing, and scope-creep flags. |
| `task-breakdown-review`  | Review a task breakdown authored by another architect or engineer: design coverage, dependency and critical-path soundness, sizing, missing ops-readiness, scope creep. Severity-tagged findings and a verdict. |
| `task-release-notes`     | Generate stakeholder-ready release notes from a commit range or PR list. Categorized changelog plus a folded-in rollback and risk register section for on-call.                         |

`task-breakdown-design` and `task-breakdown-review` are the author/review pair for engineering task plans: the first turns an approved design into a task graph; the second critiques a task graph someone else wrote. Both target the architect or tech lead who owns the build, and pick up where `task-design-architecture` (in the `architecture` plugin) leaves off.

## Atomic Skills

No plugin-local atomics. All atomic skills used by delivery workflows live in the `core` plugin and resolve at runtime when both plugins are installed.

### Core Atomics Used by Delivery Workflows

| Core Atomic                  | Used By                                                             |
| ---------------------------- | ------------------------------------------------------------------- |
| `behavioral-principles`      | all workflow skills                                                 |
| `stack-detect`               | `task-breakdown-design`, `task-breakdown-review`, `task-release-notes` |
| `review-blast-radius`        | `task-breakdown-design`, `task-breakdown-review`, `task-release-notes` |
| `review-change-risk`         | `task-breakdown-design`, `task-release-notes`                       |
| `ops-backward-compatibility` | `task-breakdown-design`, `task-breakdown-review`, `task-release-notes` |
| `ops-release-safety`         | `task-release-notes`                                                |
| `ops-feature-flags`          | `task-breakdown-design`, `task-breakdown-review`, `task-release-notes` |
| `backend-db-migration`       | `task-breakdown-design`, `task-breakdown-review`, `task-release-notes` |
| `dependency-impact-analysis` | `task-breakdown-design`, `task-release-notes`                       |

## Usage Examples

**Break a system design into an engineering task graph:**

```
/task-breakdown-design
[paste a task-design-architecture proposal, HLD, or LLD here]
```

**Review a task breakdown someone else authored:**

```
/task-breakdown-review
[paste the task plan; optionally include the design it implements]
```

**Generate release notes for a deploy:**

```
/task-release-notes
Range: v1.4.0..HEAD
Audience: both
Deploy target: production
```
