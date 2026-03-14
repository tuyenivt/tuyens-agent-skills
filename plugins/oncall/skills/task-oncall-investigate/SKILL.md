---
name: task-oncall-investigate
description: Structured investigation for non-incident oncall work - user requests, support tickets, operational questions, unexpected behavior, and performance concerns. Not for active incidents with service degradation or user impact (use task-incident-root-cause for that).
metadata:
  category: ops
  tags: [oncall, investigation, user-request, operational, performance, support]
  type: workflow
user-invocable: true
---

# Oncall Investigation

## Purpose

Structured investigation for oncall work that is not an active incident:

- **User and support requests** -- "why can't customer X access feature Y?"
- **Operational questions** -- "why did the batch job skip last night's run?"
- **Unexpected behavior** -- "this returns Y but we expected X - is this a bug?"
- **Performance concerns** -- slow response or high latency without outage
- **Monitoring questions** -- alert fired, not clear if it's real or a false positive

This skill is for understanding why something happened, not for containing an active production failure. Use `task-incident-root-cause` for active incidents with blast radius and containment urgency.

## When to Use

- The system is not down - this is a specific case or recurring pattern, not a broad outage
- A user or support team reported something unexpected
- You need to determine if observed behavior is a bug, expected behavior, or a configuration issue
- An alert fired and you need to investigate if it's real, spurious, or a known condition

## Inputs

| Input             | Required | Description                                                                 |
| ----------------- | -------- | --------------------------------------------------------------------------- |
| Report or symptom | Yes      | User report, support ticket, alert, or description of unexpected behavior   |
| Affected entity   | No       | Specific user ID, request ID, order ID, or resource that exhibits the issue |
| Time window       | No       | When the issue occurred or was first observed                               |
| Expected behavior | No       | What the reporter expected to happen                                        |
| Actual behavior   | No       | What actually happened                                                      |

Handle partial inputs. Infer time window and scope from the symptom if not provided.

## Rules

- Classify the request type before investigating - this determines what evidence to look for
- Check expected behavior first: is this a bug or working as designed?
- Use log and data evidence to confirm or rule out hypotheses - do not speculate
- Keep investigation proportional to impact - a single-user issue does not need system-wide analysis
- Always produce a clear finding that answers the original question
- State what evidence was checked, what it showed, and what remains uncertain

## Investigation Model

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Classify the Request

| Request Type        | Signals                                                         | Investigation Focus                                                |
| ------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------ |
| Data issue          | Wrong value returned, missing record, unexpected state          | Check DB state, data pipeline, write path                          |
| Access / permission | User can't access resource or feature                           | Check auth config, role assignment, feature flag                   |
| Operational failure | Batch job, cron, queue processing didn't run or completed wrong | Check execution logs, scheduler state, queue depth                 |
| Unexpected behavior | System behaves differently than expected but no error thrown    | Check code path, feature flags, config, edge cases                 |
| Performance concern | Slow response, timeout, high latency (no outage)                | Check slow query logs, external dependency latency, resource usage |
| Alert investigation | Alert fired, unclear if real or spurious                        | Check metrics against alert threshold, compare to baseline         |

### Step 3 - Scope the Affected Case

Narrow investigation to the specific case before broadening:

- Is this affecting one user/entity or many?
- Is it reproducible or intermittent?
- Is it scoped to a specific endpoint, feature, or data subset?
- Did it start at a specific time or has it always been this way?

If more than one user is affected and the issue is ongoing, reassess whether this should be escalated to `task-incident-root-cause`.

### Step 4 - Check Expected Behavior

Before investigating a bug, confirm what the expected behavior actually is:

- Read the relevant code path to understand what the system is designed to do
- Use skill: `task-code-explain` if the code path is unfamiliar
- Check if any feature flags, config values, or A/B test assignments affect this case
- Check if this behavior was recently changed by a deploy or config update

This step frequently reveals that the reported behavior is actually correct (misunderstanding) or a known limitation (not a bug).

### Step 5 - Evidence Collection

Gather evidence specific to the request type:

**For data issues:**

- Query the relevant DB state for the affected entity
- Trace the write path: was the data ever written? Was it overwritten? Was it corrupted?
- Check for recent migrations or data pipeline failures; specifically check if a soft-delete pattern was introduced (new `deleted_at` column) that invalidates existing queries missing `deleted_at IS NULL` filters

**For access/permission issues:**

- Check the user's role and permission assignments
- Check feature flag state for this user or their cohort
- Check auth token validity and scope

**For operational failures:**

- Check execution logs for the scheduled job or queue processor
- Check if the scheduler or worker process was running
- Check for errors in the job execution log
- Check queue depth and consumer health

**For unexpected behavior:**

- Use skill: `log-analysis` to trace the specific request through logs
- Identify the exact code branch that executed for this case
- Check config values and feature flags active at the time

**For performance concerns:**

- Use skill: `log-analysis` to find duration fields in the relevant time window
- Check slow query logs or external dependency latency
- Identify if the slowness is constant or tied to specific data shape or traffic pattern

**For alert investigation:**

- Compare the metric against its alert threshold over the last 24 hours
- Use skill: `log-analysis` to check if log evidence corroborates the metric signal
- Check if similar patterns exist at the same time historically (scheduled load, known flap)

### Step 6 - Finding and Recommended Action

Classify the finding and recommend a clear next action:

| Finding                                 | Recommended Action                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------- |
| **Bug confirmed**                       | Provide reproduction steps and link to `task-debug` for fix                           |
| **Expected behavior**                   | Document why the behavior is correct; draft response to requester                     |
| **Config or flag issue**                | Identify the specific config change needed; assess change risk                        |
| **Data issue**                          | Identify the data correction needed; assess whether a hotfix or migration is required |
| **Permission/access issue**             | Identify what needs to change (role, flag, entitlement)                               |
| **Intermittent, insufficient evidence** | State what additional logging or data is needed to resolve                            |
| **False positive alert**                | Document the expected pattern; recommend alert tuning                                 |

## Output

```markdown
## Investigation: {one-line description of what was investigated}

Request Type: {Data issue | Access | Operational failure | Unexpected behavior | Performance | Alert}
Affected Scope: {Single user | N users | Specific feature | All users}
Time Window: {when the issue occurred or was observed}

### Expected vs. Actual Behavior

- Expected: {what should happen}
- Actual: {what is happening}
- Verdict: {Bug | Working as designed | Config issue | Data issue | Insufficient evidence}

### Evidence

- {Finding 1 with source - log line, query result, code path, config value}
- {Finding 2}
- {Finding 3}

### Root Finding

{2-4 sentences explaining why this is happening. Reference specific evidence. Be concrete.}

### Recommended Action

- [ ] {Action 1 - who does what}
- [ ] {Action 2}

### Remaining Uncertainty

- {What is still unknown and what would resolve it, or "None - investigation is conclusive"}
```

## Self-Check

- [ ] Request type classified before investigation starts
- [ ] Expected behavior checked before concluding it is a bug
- [ ] Evidence collected specific to the request type - no generic log fishing
- [ ] Finding is conclusive (Bug | Working as designed | Config | Data) or states what is needed to reach a conclusion
- [ ] Recommended action is concrete and actionable
- [ ] Scope reassessed - if more than one user is affected and ongoing, `task-incident-root-cause` may be more appropriate

## Avoid

- Treating this as an incident (no blast radius or containment needed for non-incident work)
- Concluding "it's a bug" before reading the relevant code to confirm expected behavior
- Fishing through logs without a specific hypothesis
- Reporting "I checked the logs and didn't find anything" without stating what signal was missing
- Scope creep - investigate the specific case first, then broaden only if evidence points to a systemic issue
- Using `task-debug` unless the investigation confirms a code bug with a clear stack trace or reproduction path
