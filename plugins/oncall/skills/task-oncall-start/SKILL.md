---
name: task-oncall-start
description: Oncall entry point for both shift starts and incoming alerts. Use when starting your oncall rotation (shift-start mode) or when you have a page, alert, or report and are unsure which workflow to invoke (triage mode). Classifies work type and severity, then routes to the correct skill.
metadata:
  category: ops
  tags: [oncall, routing, incident, investigation, handoff, rotation]
  type: workflow
user-invocable: true
---

# Oncall

## Purpose

Entry point for oncall work covering two modes:

1. **Shift-start mode** - You are beginning your oncall rotation and need to assess the current state of your service area before anything fires.
2. **Triage mode** - You received a specific alert, ticket, or report and need to classify it and route to the right workflow.

Most oncall time is lost by treating everything as an incident or jumping to debugging before understanding what type of work this is. Equally, oncall engineers who skip shift-start review get blindsided by context they should have had.

## When to Use

**Shift-start (beginning a rotation or handoff):**

- You are starting your oncall rotation and want to know the current state
- You are taking over from a previous oncall engineer
- You want a checklist of what to review before you start receiving pages

**Triage (incoming alert or request):**

- You received a page, alert, or Slack message and need to decide what to do
- A support ticket or user report landed in the oncall queue
- A teammate forwarded something with "can you look at this?"
- You're not sure whether to use `task-incident-root-cause`, `task-debug`, or something else

For known incidents, go directly to `task-incident-root-cause`. For known non-incident investigations, go directly to `task-oncall-investigate`.

## Inputs

**For shift-start mode:** team or service area name (e.g., "payments team", "order service"). No alert or ticket needed.

**For triage mode:** paste any of the following:

- Alert text or PagerDuty title
- Error message or stack trace
- Support ticket or user report
- Slack message or description of what was observed
- Dashboard screenshot description

## Mode Detection

Determine which mode to use based on the input:

- If the user mentions starting a rotation, shift, handoff, or asks "what should I check?" - use **Shift-Start Mode** (go to Shift-Start Checklist below)
- If the user provides a specific alert, error, ticket, or symptom - use **Triage Mode** (go to Classification Model below)
- If unclear, ask: "Are you starting your oncall shift, or do you have a specific alert or issue to triage?"

---

## Shift-Start Checklist

Run this when beginning an oncall rotation. The goal is to build situational awareness before anything fires.

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Review Handoff Notes

Check for context from the previous oncall engineer:

- Open or recently resolved incidents (last 24-72 hours)
- Known flaky alerts or false positives to expect
- In-progress investigations that may need follow-up
- Temporary workarounds or manual interventions in place
- Escalation contacts for issues the previous oncall was tracking

If no handoff notes exist, note this as a process gap to flag with the team.

### Step 3 - Assess Current System Health

Review these areas for the services you own:

| Area                      | What to Check                                           | Where to Look                                        |
| ------------------------- | ------------------------------------------------------- | ---------------------------------------------------- |
| **Open incidents**        | Any active or recently resolved incidents               | Incident tracker, PagerDuty, Slack incident channels |
| **Error rates**           | Current error rate vs. baseline for owned services      | Dashboards, APM tools (Datadog, New Relic, Grafana)  |
| **Recent deploys**        | What shipped in the last 24-48 hours                    | CI/CD pipeline, deploy log, release channel          |
| **Pending alerts**        | Alerts that fired but were not acknowledged or resolved | PagerDuty, alerting tool                             |
| **Queue health**          | Queue depth, consumer lag, dead-letter queue size       | Message broker dashboard, CloudWatch, queue metrics  |
| **Dependency status**     | Third-party API status pages for critical dependencies  | Status pages (e.g., Stripe, AWS, Twilio)             |
| **Scheduled maintenance** | Planned changes during your rotation window             | Change calendar, team channel                        |

### Step 4 - Identify Known Risks

Based on the review, identify:

- Services with elevated error rates that have not triggered an alert yet
- Recent deploys that have not been validated in production
- Known issues that might escalate during your rotation
- Upcoming scheduled jobs or migrations that could cause alerts

### Step 5 - Confirm Readiness

Before signing off on shift-start:

- [ ] Handoff notes reviewed (or absence noted)
- [ ] Dashboards checked for owned services
- [ ] Recent deploys identified and noted
- [ ] Alerting tool access confirmed and notifications routing to you
- [ ] Escalation path known (who to contact for what)
- [ ] Runbook locations known for owned services

### Shift-Start Output

```
## Oncall Shift-Start Summary

Team/Service Area: {team or service name}
Rotation Start: {date/time}
Previous Oncall: {name if known, or "Unknown"}

### Handoff Review

- Open incidents: {list or "None"}
- Known flaky alerts: {list or "None identified"}
- In-progress investigations: {list or "None"}
- Active workarounds: {list or "None"}

### Current System Health

- Error rates: {normal / elevated for {service} / unknown}
- Recent deploys (last 48h): {list with timestamps, or "None"}
- Queue health: {normal / {queue} showing lag / unknown}
- Dependency status: {all green / {dependency} degraded}

### Known Risks for This Rotation

- {Risk 1 - e.g., "v2.4.1 deployed 6h ago, not yet validated under peak traffic"}
- {Risk 2}
- {or "No elevated risks identified"}

### Readiness

- [ ] Notifications routing correctly
- [ ] Escalation contacts confirmed
- [ ] Runbook locations known
```

---

## Classification Model (Triage Mode)

Use this when you have a specific alert, ticket, or report to classify.

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Classify Work Type

| Type                               | Signals                                                                                       | Route to                                             |
| ---------------------------------- | --------------------------------------------------------------------------------------------- | ---------------------------------------------------- |
| **Active incident**                | Service down, error rate spike, multiple users affected, SLA breach, data loss risk           | `task-incident-root-cause`                           |
| **Code bug**                       | Stack trace, test failure, crash, specific reproducible error in code                         | `task-debug`                                         |
| **Operational investigation**      | "Why did X happen?", batch job missed, queue backed up, unexpected behavior for specific case | `task-oncall-investigate`                            |
| **User / support request**         | Single user issue, access problem, data question, "why can't I see X?"                        | `task-oncall-investigate`                            |
| **Performance concern**            | Slow response, high latency, timeout (no outage)                                              | `task-oncall-investigate` or `task-code-perf-review` |
| **Monitoring / alerting question** | Alert fired but unclear why, alert seems false positive, dashboard anomaly                    | `task-oncall-investigate`                            |

Apply the highest matching type. If signals are mixed, classify as **Active incident** to err on the side of urgency.

### Step 3 - Severity Assessment

| Severity     | Criteria                                                                     |
| ------------ | ---------------------------------------------------------------------------- |
| **Critical** | Service fully down, data loss occurring, SLA breached, payment/auth broken   |
| **High**     | Partial outage, significant user population affected, degraded critical path |
| **Medium**   | Feature broken for subset of users, workaround exists, no data loss          |
| **Low**      | Single user affected, cosmetic issue, non-critical feature, no user impact   |

For Critical and High: route immediately - do not spend time on further classification.

For Medium and Low: complete classification fully before investigating.

### Step 4 - Scope Check (30 seconds)

- **Is this ongoing?** (Yes = urgency up; No = investigation can be measured)
- **Is data at risk?** (Yes = Critical regardless of other signals)
- **Has this happened before?** (Yes = check runbooks or prior postmortems first)
- **Did an external dependency degrade?** (Yes = check third-party API status pages, latency dashboards before assuming internal cause)
- **Was there a recent deploy or config change?** (Yes = rollback may be fastest resolution)

### Step 5 - Route and Package Context

State the classification, severity, and recommended next step. Package the key context the next workflow needs:

- Relevant error message, log snippet, or symptom description
- Time window (when did it start?)
- Affected scope (who/what is impacted?)
- Recent changes (deploy, config, feature flag, traffic change)

## Triage Output

```
## Oncall Classification

Work Type: {Active incident | Code bug | Operational investigation | User request | Performance | Monitoring}
Severity: {Critical | High | Medium | Low}
Ongoing: {Yes | No | Unknown}

### Recommended Workflow

Use: {task-incident-root-cause | task-debug | task-oncall-investigate | task-code-perf-review}

### Context Package

- Symptom: {one-sentence description}
- Time window: {when did it start or occur?}
- Affected scope: {who or what is impacted}
- Recent change: {deploy, config, or flag change if known, or "None identified"}
- Runbook exists: {Yes - link | No | Unknown}

### Immediate Action (Critical/High only)

- [ ] {First thing to do right now}
```

## Self-Check

**Shift-start mode:**

- [ ] Handoff notes reviewed or absence flagged
- [ ] Dashboard and error rates checked for owned services
- [ ] Recent deploys identified
- [ ] Alerting access confirmed and routing to you
- [ ] Escalation path documented

**Triage mode:**

- [ ] Work type classified before any investigation starts
- [ ] Severity assessed - Critical/High routes immediately
- [ ] Scope check completed (ongoing? data at risk? recent change?)
- [ ] Context package ready for the target workflow
- [ ] Output can be read in under 30 seconds

## Avoid

- Spending more than 2 minutes on classification for Critical/High severity - route immediately
- Treating every alert as an incident - most oncall work is investigation, not incident response
- Starting debugging before classifying - classification shapes what to look for
- Routing to `task-debug` when there is no stack trace or reproducible error
- Skipping the "recent change?" check - this is the fastest path to resolution for many issues
- Starting an oncall rotation without reviewing handoff notes and current system health
- Assuming "no alerts = all healthy" at shift start - check dashboards to confirm
