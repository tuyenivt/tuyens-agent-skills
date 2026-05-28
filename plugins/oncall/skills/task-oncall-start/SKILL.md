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

Check: open incidents AND incidents resolved in last 72h, known flaky alerts, in-progress investigations, active workarounds, escalation contacts. If no handoff notes exist, flag as a process gap.

### Step 2 - Assess Health and Risks

| Area               | What to check                                              | Source                                            |
| ------------------ | ---------------------------------------------------------- | ------------------------------------------------- |
| Open incidents     | Active or unacknowledged pages                             | Incident tracker, PagerDuty, Slack                |
| Error rates        | Current vs. baseline for owned services                    | APM                                               |
| Recent deploys     | Shipped in last 24-48h, including unvalidated production traffic | CI/CD log, release channel                  |
| Queue health       | Depth, consumer lag, DLQ size                              | Broker dashboard, queue metrics                   |
| Dependencies       | Status pages for critical third parties                    | Payment, cloud, comms, identity providers         |
| Scheduled changes  | Maintenance, migrations, cron during your window           | Change calendar                                   |

Identify risks not yet alerting: elevated error rates, unvalidated deploys, upcoming jobs that may trigger pages.

### Output

```
## Oncall Shift-Start Summary

Team/Service: {name}
Rotation Start: {date/time}
Previous Oncall: {name or "Unknown"}

### Handoff Review
- Open incidents: {list or "None"}
- Recently resolved (72h): {list with severity + time + status, or "None"}
- Known flaky alerts: {list or "None"}
- In-progress investigations: {list or "None"}
- Active workarounds: {list or "None"}
- Escalation contacts: {list, or "Not documented - flag as gap"}

### Current Health
- Error rates: {normal / elevated for {service} / unknown}
- Recent deploys (48h): {list with timestamps, or "None"}
- Queue health: {normal / {queue} lagging / unknown}
- Dependencies: {all green / {dep} degraded}

### Known Risks
- {Risk 1 - e.g., "v2.4.1 deployed 6h ago, not yet validated under peak"}
- {Risk 2}
```

---

## Triage Mode

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Classify Work Type

| Type                       | Signals                                                                                | Route to                                        |
| -------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **Active incident**        | Service down, error rate spike, multiple users affected, SLA breach, data loss risk    | `incident-root-cause`                           |
| **Code bug**               | Stack trace, test failure, crash, reproducible error                                   | `task-code-debug`                               |
| **Operational issue**      | Batch missed, queue backed up, "why did X happen?"                                     | `oncall-investigate`                            |
| **User / support request** | Single user issue, access problem, data question                                       | `oncall-investigate`                            |
| **Performance**            | Slow response, high latency, timeout (no outage)                                       | `oncall-investigate` or `task-code-review-perf` |
| **Alert investigation**    | Alert fired, unclear if real or false positive                                         | `oncall-investigate`                            |

### Step 3 - Severity

Use the severity table in `incident-root-cause` Step 1. For triage routing, only the Critical/High distinction matters - route immediately, skip further classification.

### Step 4 - Scope Check

- Data at risk or ongoing impact → raise severity
- Recent deploy or config change → rollback is often the fastest resolution
- Happened before → check runbooks and prior postmortems

### Step 5 - Route and Package Context

State the classification, severity, recommended workflow, and the context the next workflow needs.

### Output

```
## Oncall Classification

Work Type: {Active incident | Code bug | Operational | User request | Performance | Alert}
Severity: {Critical | High | Medium | Low}
Ongoing: {Yes | No | Unknown}

### Recommended Workflow
Use: {incident-root-cause | task-code-debug | oncall-investigate | task-code-review-perf}

### Context Package
- Symptom: {one sentence}
- Time window: {when did it start?}
- Affected scope: {who/what is impacted}
- Recent change: {deploy/config/flag, or "None identified"}

### Immediate Action (Critical/High only)
- [ ] {first thing to do now}
```

## Self-Check

- [ ] Mode detected (Shift-Start vs Triage)
- [ ] Triage: stack detected; work type classified
- [ ] Triage: severity assigned; Critical/High routed without further classification time
- [ ] Triage: scope check completed (data risk, recent change, prior occurrence)
- [ ] Triage: context package names symptom, time window, affected scope, recent change
- [ ] Shift-Start: handoff reviewed (or absence flagged as gap)
- [ ] Shift-Start: health table walked; known risks identified

## Avoid

- Re-classifying when the user has already stated the work type - route directly
- Spending classification time on Critical/High before containment routing
- Producing a Shift-Start summary with empty sections rather than naming the missing input as a gap
- Inventing stack details in Shift-Start - the workflow is stack-agnostic
