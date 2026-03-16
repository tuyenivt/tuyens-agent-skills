# Tuyen's Agent Skills - Oncall

Incident response and investigation plugin for Claude Code: triage, investigation, root cause analysis, and postmortem. Requires the `core` plugin for shared atomic skills (`ops-failure-classification`, `review-blast-radius`, `ops-observability`, `ops-resiliency`, `ops-engineering-governance`, etc.).

## Workflow Skills

4 workflow skills (`task-*`) for oncall work.

| Skill                      | Description                                                                                                                                                  |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `task-oncall-start`        | Oncall entry point for shift starts (rotation handoff, system health review) and incoming alert triage (classify and route to the right workflow)            |
| `task-oncall-investigate`  | Structured investigation for non-incident oncall work - user requests, support tickets, operational questions, unexpected behavior, and performance concerns |
| `task-incident-root-cause` | Staff-level incident root cause analysis with containment and prevention                                                                                     |
| `task-incident-postmortem` | Staff-level postmortem for systemic learning. Supports `quick`, `standard`, and `deep` depth levels.                                                         |

## Atomic Skills

3 atomic skills provide focused patterns used exclusively by oncall workflows. Hidden from the slash menu (`user-invocable: false`).

| Skill                   | Description                                                                                                                   |
| ----------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `log-analysis`          | Structured log analysis - time-window isolation, correlation ID tracing, frequency analysis, and healthy/unhealthy comparison |
| `root-cause-hypothesis` | Generate ranked root cause hypotheses with confidence levels and evidence                                                     |
| `review-gap-analysis`   | Analyze why existing review processes failed to catch a production failure                                                    |

## Skill Dependency Index

### Workflow -> Atomics

| Workflow                   | Atomic Skills Used (oncall) | Atomic Skills Used (from core)                                                                                                                                                                                                                                                                                             |
| -------------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-oncall-start`        | -                           | `stack-detect`                                                                                                                                                                                                                                                                                                             |
| `task-oncall-investigate`  | `log-analysis`              | `stack-detect`, `task-code-explain`                                                                                                                                                                                                                                                                                        |
| `task-incident-root-cause` | `root-cause-hypothesis`     | `ops-failure-classification`, `review-blast-radius`, `failure-propagation-analysis`, `architecture-concurrency`, `architecture-data-consistency`, `backend-db-indexing`, `ops-resiliency`, `ops-observability`, `architecture-guardrail`, `ops-engineering-governance`, `ops-backward-compatibility`, `review-change-risk` |
| `task-incident-postmortem` | `review-gap-analysis`       | `ops-failure-classification`, `architecture-concurrency`, `architecture-data-consistency`, `ops-resiliency`, `backend-db-indexing`, `review-blast-radius`, `architecture-guardrail`, `complexity-review`, `ops-engineering-governance`, `ops-observability`, `backend-idempotency`, `backend-coding-standards`             |

## Usage Examples

**Starting your oncall rotation:**

```
/task-oncall-start
Starting my oncall rotation for the payments team. What should I check first?
```

**Not sure what type of work this is? Triage here:**

```
/task-oncall-start
[paste the alert, ticket, or Slack message]
```

**Investigate a user report, support ticket, or unexpected behavior:**

```
/task-oncall-investigate
[describe the issue or paste the ticket]
```

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
