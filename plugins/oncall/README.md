# Tuyen's Agent Skills - Oncall

Incident response plugin for Claude Code: root cause analysis and postmortem with systemic learning. Requires the `core` plugin for shared atomic skills (failure-classification, blast-radius-analysis, observability, resiliency, engineering-governance, etc.).

## Workflow Skills

2 workflow skills (`task-*`) for incident response.

| Skill                      | Description                                                                                          |
| -------------------------- | ---------------------------------------------------------------------------------------------------- |
| `task-incident-root-cause` | Staff-level incident root cause analysis with containment and prevention                             |
| `task-incident-postmortem` | Staff-level postmortem for systemic learning. Supports `quick`, `standard`, and `deep` depth levels. |

## Atomic Skills

2 atomic skills provide focused patterns used exclusively by oncall workflows. Hidden from the slash menu (`user-invocable: false`).

| Skill                   | Description                                                                |
| ----------------------- | -------------------------------------------------------------------------- |
| `root-cause-hypothesis` | Generate ranked root cause hypotheses with confidence levels and evidence  |
| `review-gap-analysis`   | Analyze why existing review processes failed to catch a production failure |

## Skill Dependency Index

### Workflow -> Atomics

| Workflow                   | Atomic Skills Used (oncall) | Atomic Skills Used (from core)                                                                                                                                                                                                                                |
| -------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-incident-root-cause` | `root-cause-hypothesis`     | `failure-classification`, `blast-radius-analysis`, `failure-propagation-analysis`, `concurrency-model`, `data-consistency-modeling`, `db-indexing`, `resiliency`, `observability`, `architecture-guardrail`, `engineering-governance`                         |
| `task-incident-postmortem` | `review-gap-analysis`       | `failure-classification`, `concurrency-model`, `data-consistency-modeling`, `resiliency`, `db-indexing`, `blast-radius-analysis`, `architecture-guardrail`, `complexity-review`, `engineering-governance`, `observability`, `idempotency`, `coding-standards` |

## Usage Examples

**Investigate an active incident:**

```
/task-incident-root-cause
[paste stack trace, logs, or error message]
```

**Write a postmortem after resolution:**

```
/task-incident-postmortem
[paste incident timeline or reference root-cause output]
```
