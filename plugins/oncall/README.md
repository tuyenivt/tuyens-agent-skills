# Tuyen's Agent Skills - Oncall

Incident response and investigation plugin for Claude Code: triage, investigation, root cause analysis, and postmortem. Requires the `core` plugin for shared atomic skills (`ops-failure-classification`, `review-blast-radius`, `ops-observability`, `ops-resiliency`, `ops-engineering-governance`, etc.).

## Agents

Stack-agnostic - the agent classifies failures and enforces guardrails without assuming a framework, and routes stack-specific debugging to the matching stack plugin.

| Agent            | Description                                                                                                                                    | Drives                                     |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| oncall-responder | Incident responder / SRE walking the incident lifecycle: shift-start health checks, alert triage and routing, and prevention-focused postmortems. | `task-oncall-start`, `task-postmortem`     |

## Workflow Skills

Workflow skills (`task-*`) for oncall work.

| Skill               | Description                                                                                                                                       |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-oncall-start` | Oncall entry point for shift starts (rotation handoff, system health review) and incoming alert triage (classify and route to the right workflow) |
| `task-postmortem`   | Staff-level postmortem for systemic learning. Supports `quick`, `standard`, and `deep` depth levels.                                              |

## Atomic Skills

Atomic skills provide focused patterns used exclusively by oncall workflows. Hidden from the slash menu (`user-invocable: false`).

| Skill                     | Description                                                                                                                                                  |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `oncall-investigate`      | Structured investigation for non-incident oncall work - user requests, support tickets, operational questions, unexpected behavior, and performance concerns |
| `incident-root-cause`     | Active production incident investigation with blast radius assessment and containment-first analysis                                                         |
| `log-analysis`            | Structured log analysis - time-window isolation, correlation ID tracing, frequency analysis, and healthy/unhealthy comparison                                |
| `root-cause-hypothesis`   | Generate ranked root cause hypotheses with confidence levels and evidence                                                                                    |
| `review-gap-analysis`     | Analyze why existing review processes failed to catch a production failure                                                                                   |
| `ops-observability-fetch` | Fetch evidence (issues, metrics, logs, traces, deploys, monitors) from Sentry/Datadog/Honeycomb MCP; falls back to paste-mode when no transport is available |

## Skill Dependency Index

### Workflow -> Atomics

| Workflow              | Atomic Skills Used (oncall)                                            | Atomic Skills Used (from core)                                                                                                                                                                                                                                                                                             |
| --------------------- | ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-oncall-start`   | `oncall-investigate`, `incident-root-cause`, `ops-observability-fetch` | `stack-detect`                                                                                                                                                                                                                                                                                                             |
| `oncall-investigate`  | `log-analysis`, `ops-observability-fetch`                              | `stack-detect`, `task-code-explain`                                                                                                                                                                                                                                                                                        |
| `incident-root-cause` | `root-cause-hypothesis`, `ops-observability-fetch`                     | `ops-failure-classification`, `review-blast-radius`, `failure-propagation-analysis`, `architecture-concurrency`, `architecture-data-consistency`, `backend-db-indexing`, `ops-resiliency`, `ops-observability`, `ops-backward-compatibility`, `review-pr-risk`                                                             |
| `log-analysis`        | `ops-observability-fetch`                                              | -                                                                                                                                                                                                                                                                                                                          |
| `task-postmortem`     | `review-gap-analysis`                                                  | `ops-failure-classification`, `architecture-concurrency`, `architecture-data-consistency`, `ops-resiliency`, `backend-db-indexing`, `review-blast-radius`, `architecture-guardrail`, `ops-engineering-governance`, `ops-observability`, `backend-idempotency`                                                              |

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

**Write a postmortem after resolution:**

```
/task-postmortem
[paste incident timeline or reference incident-root-cause output]
```
