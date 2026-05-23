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
- User already knows it is an active incident → route directly to `incident-root-cause`
- User already knows it is non-incident investigation → route directly to `oncall-investigate`
- Ambiguous → ask: "Are you starting your shift, or do you have a specific alert to triage?"

---

## Shift-Start Mode

Goal: build situational awareness before anything fires.

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Review Handoff

Check: open or recently resolved incidents (24-72h), known flaky alerts, in-progress investigations, active workarounds, escalation contacts. If no handoff notes exist, flag it as a process gap.

### Step 3 - Assess Health and Risks

| Area               | What to check                                              | Source                                            |
| ------------------ | ---------------------------------------------------------- | ------------------------------------------------- |
| Open incidents     | Any active or recently resolved                            | Incident tracker, PagerDuty, Slack                |
| Error rates        | Current vs. baseline for owned services                    | APM (Datadog, New Relic, Grafana)                 |
| Recent deploys     | Shipped in last 24-48h, including unvalidated production traffic | CI/CD log, release channel                  |
| Pending alerts     | Unacknowledged or unresolved                               | PagerDuty                                         |
| Queue health       | Depth, consumer lag, DLQ size                              | Broker dashboard, queue metrics                   |
| Dependencies       | Status pages for critical third parties                    | Stripe, AWS, Twilio, etc.                         |
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
- Known flaky alerts: {list or "None"}
- In-progress investigations: {list or "None"}
- Active workarounds: {list or "None"}

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

Tiebreaker: if a symptom matches both **Performance** and **Active incident**, choose Active incident when user-visible impact is ongoing OR multiple users are affected; otherwise Performance.

### Step 3 - Severity

| Severity     | Criteria                                                                                                          |
| ------------ | ----------------------------------------------------------------------------------------------------------------- |
| **Critical** | Service fully down, data loss in progress, SLA already breached, or payment/auth fully broken                     |
| **High**     | Partial outage on a critical path (payments, auth, checkout), >10% affected, or critical-path latency >2x baseline |
| **Medium**   | Feature broken for a subset, workaround exists, no data loss                                                      |
| **Low**      | Single user, cosmetic, non-critical feature                                                                       |

For Critical / High: route immediately. Skip further classification.

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

- [ ] Mode detected (shift-start vs triage); stack detection invoked
- [ ] Triage: work type and severity assigned; scope check completed; context package names symptom, time window, recent change
- [ ] Shift-start: handoff reviewed (or absence flagged); health and risks identified
- [ ] Critical/High routed immediately, no further classification time spent

## Avoid

- Routing to `task-code-debug` without a stack trace or reproducible error
- Skipping the recent-change check - it is the fastest path to resolution for many alerts
