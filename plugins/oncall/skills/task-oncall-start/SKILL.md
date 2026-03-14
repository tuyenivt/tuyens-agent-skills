---
name: task-oncall-start
description: Oncall triage entry point. Use when you have a page, alert, or report and are unsure which workflow to invoke. Classifies work type (incident vs investigation vs bug) and severity, then routes to the correct skill. Not needed when you already know it is an active incident (use task-incident-root-cause directly) or a non-incident investigation (use task-oncall-investigate directly).
metadata:
  category: ops
  tags: [oncall, routing, incident, investigation]
  type: workflow
user-invocable: true
---

# Oncall

## Purpose

Entry point for oncall work when you're not sure what you're dealing with. Classify the work type and route to the right workflow before investing investigation effort.

Most oncall time is lost by treating everything as an incident or jumping to debugging before understanding what type of work this is.

## When to Use

- You received a page, alert, or Slack message and need to decide what to do
- A support ticket or user report landed in the oncall queue
- A teammate forwarded something with "can you look at this?"
- You're not sure whether to use `task-incident-root-cause`, `task-debug`, or something else

For known incidents, go directly to `task-incident-root-cause`. For known non-incident investigations, go directly to `task-oncall-investigate`.

## Inputs

Paste any of the following:

- Alert text or PagerDuty title
- Error message or stack trace
- Support ticket or user report
- Slack message or description of what was observed
- Dashboard screenshot description

## Classification Model

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

## Output

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
