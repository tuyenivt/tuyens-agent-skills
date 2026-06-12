---
name: task-oncall-start
description: Oncall entry point routing shift-starts and alerts: classifies work type and severity, dispatches to incident-root-cause or oncall-investigate.
metadata:
  category: ops
  tags: [oncall, routing, incident, investigation, handoff, rotation]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Oncall

Two modes:

1. **Shift-start** - beginning a rotation; assess current state before pages fire
2. **Triage** - alert/ticket/report just landed; classify and route

## Mode Detection

- "starting my shift", "taking over", "what should I check?" → **Shift-Start**
- A specific alert, error, ticket, or symptom is provided → **Triage**
- Ambiguous → ask: "Are you starting your shift, or do you have a specific alert to triage?"

---

## Shift-Start Mode

Goal: build situational awareness before anything fires. Stack-agnostic - skip `stack-detect`.

### Step 1 - Review Handoff

Check: open incidents AND incidents resolved in last 72h, known flaky alerts, in-progress investigations, active workarounds, pending follow-up actions, escalation contacts. If no handoff notes exist, flag as a process gap. Facts taken from handoff text without live verification are reported as "(per handoff)".

### Step 2 - Assess Health and Risks

Use skill: `ops-observability-fetch` for any of the rows below when an MCP transport is available; cache transport detection for the rest of the workflow. Digest fetched blocks into the summary lines - do not paste raw blocks. Produce the full summary in one pass, marking unfetchable rows `unknown - paste from {source}` rather than waiting for pastes.

| Area               | What to check                                              | Capability / Source                                          |
| ------------------ | ---------------------------------------------------------- | ------------------------------------------------------------ |
| Open incidents     | Active or unacknowledged pages                             | `fetch_monitor` (Datadog) / Incident tracker, PagerDuty, Slack |
| Error rates        | Current vs. baseline for owned services                    | `query_metrics` (24h window vs. prior 7d) / APM              |
| Recent deploys     | Shipped in last 24-48h, including unvalidated production traffic | `list_deploys` / CI/CD log, release channel             |
| Queue health       | Depth, consumer lag, DLQ size                              | `query_metrics` / Broker dashboard                           |
| Dependencies       | Status pages for critical third parties                    | Payment, cloud, comms, identity providers (manual)           |
| Scheduled changes  | Maintenance, migrations, cron during your window           | Change calendar (manual)                                     |

Identify risks not yet alerting: elevated error rates, unvalidated deploys, upcoming jobs or known-flaky alerts that may page during this shift.

### Output

```
## Oncall Shift-Start Summary

Team/Service: {name}
Rotation Start: {date/time}
Previous Oncall: {name | "unnamed handoff" | "no handoff"}

### Handoff Review
- Open incidents: {list or "None"}
- Recently resolved (72h): {list: severity, time, current state + pending follow-up if any, or "None"}
- Known flaky alerts: {list or "None"}
- In-progress investigations: {list or "None"}
- Active workarounds: {list or "None"}
- Pending follow-ups: {list or "None"}
- Escalation contacts: {list, or "Not documented - flag as gap"}

### Current Health
- Error rates: {normal / elevated for {service} / unknown - paste from {source}}
- Recent deploys (48h): {list with timestamps, or "None" / unknown}
- Queue health: {normal / {queue} lagging / unknown}
- Dependencies: {all green / {dep} degraded / unknown - not checked}
- Scheduled changes (this window): {list, or "None known" / unknown}

### Known Risks
Ordered by likelihood of paging during this shift; 3-5 items.
1. {Risk - e.g., "v2.4.1 deployed 6h ago, not yet validated under peak (per handoff)"}
2. {Risk - include known-flaky alerts expected to fire, with the expected window}
```

---

## Triage Mode

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Hydrate Evidence

Use skill: `ops-observability-fetch`.

- If the input contains any recognized URL (Sentry issue, Datadog monitor, log search, trace), fetch it now - even when paste content accompanies it. Do not classify on URL alone. When a monitor was fetched, also pull `query_metrics` for its underlying metric to confirm whether the symptom is ongoing.
- Also pull `list_deploys` (48h, affected service) whenever the user's input does not mention a recent deploy or config change.
- Pure paste (PagerDuty title, Slack message, stack trace - no URLs): proceed to classify on the paste.

The fetched evidence (error_event, monitor_state, log_window, trace, deploy_event) feeds Step 3 classification and the Context Package in the output.

### Step 3 - Classify Work Type

| Type                       | Signals                                                                                | Route to                                        |
| -------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **Active incident**        | Ongoing user-facing impact: error rate spike, service down, SLA breach, data loss risk | `incident-root-cause`                           |
| **Code bug**               | Stack trace, test failure, crash, reproducible error - without ongoing multi-user impact | `task-code-debug`                               |
| **Operational issue**      | Batch missed, queue backed up, "why did X happen?"                                     | `oncall-investigate`                            |
| **User / support request** | Single user issue, access problem, data question                                       | `oncall-investigate`                            |
| **Performance**            | Slow response, high latency, timeout (no outage)                                       | `oncall-investigate` or `task-code-review-perf` |
| **Alert investigation**    | Alert fired, unclear if real or false positive                                         | `oncall-investigate`                            |

When multiple rows match, precedence: Active incident > Code bug > the rest. "Ongoing multi-user impact" uses the same thresholds as `oncall-investigate` escalation: ≥3 distinct users within an hour, or error rate >2x baseline, or a revenue/auth/data-integrity path affected. Below those thresholds, an error in production is a Code bug or Operational issue, not an incident.

When the user asks what type this is ("is this an incident?"), classify and state the answer with the threshold evidence - do not ask back. When a threshold input is unknowable from the evidence (baseline unknown, revenue-path status of the feature unclear), state the assumption used and classify under it.

### Step 4 - Severity

Mirrors `incident-root-cause` Step 1 - keep in sync:

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue-impacting (payment, checkout, billing, or auth path), >50% requests affected, or data loss risk |
| High     | User-facing degradation, 10-50% affected, or multiple services impacted |
| Medium   | Partial degradation <10%, single service, no data risk                  |
| Low      | Non-user-facing, minimal impact                                         |

When criteria from multiple rows match, take the highest row. For Critical/High: route immediately, skip further classification.

### Step 5 - Scope Check

- Data at risk or ongoing impact → raise severity one level
- Recent deploy or config change → rollback is often the fastest resolution; confirm the deploy window from the Step 2 `deploy_event` blocks (the rollback recommendation itself lands in Immediate Action)
- Happened before → check runbooks and prior postmortems. Sentry `first_seen` on the hydrated issue answers this directly.

### Step 6 - Route and Package Context

State the classification, severity, recommended workflow, and the context the next workflow needs.

### Output

```
## Oncall Classification

Work Type: {Active incident | Code bug | Operational | User request | Performance | Alert}
Severity: {Critical | High | Medium | Low}
Ongoing: {Yes (symptom still occurring) | No | Unknown}

### Recommended Workflow
Use: {incident-root-cause | task-code-debug | oncall-investigate | task-code-review-perf}

### Context Package
- Symptom: {one sentence}
- Time window: {when did it start?}
- Affected scope: {who/what is impacted}
- Recent change: {deploy/config/flag with timestamp, or "None identified"}
- Evidence: {one line per fetched block: "{block type}: {key value}"; unavailable blocks as "{block type}: paste pending"; or "paste only"}

### Immediate Action
(omit this entire section, heading included, unless Critical/High)
- [ ] {1-3 things to do now}
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded

Shift-Start:
- [ ] Handoff reviewed including pending follow-ups (or absence flagged as gap)
- [ ] Health table walked via `ops-observability-fetch` where available; unfetchable rows marked unknown, not invented
- [ ] Known risks ordered by paging likelihood

Triage:
- [ ] Stack detected; URLs hydrated via `ops-observability-fetch` when present; deploys pulled when recent-change info was missing
- [ ] Work type classified using hydrated evidence and the precedence rule (not URL alone)
- [ ] Severity assigned (highest matching row); Critical/High routed without further classification time
- [ ] Scope check completed (data risk, recent change, prior occurrence)
- [ ] Context package names symptom, time window, affected scope, recent change, and fetched evidence

## Avoid

- Re-classifying when the user has already stated the work type - route directly
- Spending classification time on Critical/High before containment routing
- Producing a Shift-Start summary with empty sections rather than naming the missing input as a gap
- Inventing stack details in Shift-Start - the workflow is stack-agnostic
- Calling production errors "incidents" below the multi-user thresholds - route them as bugs/operational work
