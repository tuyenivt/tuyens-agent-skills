---
name: oncall-investigate
description: Structured non-incident oncall investigation: support tickets, operational questions, unexpected behavior, performance concerns, alert tuning.
metadata:
  category: ops
  tags: [oncall, investigation, user-request, operational, performance, support]
user-invocable: false
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Oncall Investigation

Investigation for oncall work that is **not** an active incident: support tickets, operational questions, unexpected behavior, performance concerns, alert tuning. For active incidents (blast radius, containment urgency), use `incident-root-cause`.

## When to Use

- System is not down; the case is specific or recurring, not a broad outage
- User or support team reported something unexpected
- Need to determine if behavior is a bug, expected, or a config issue
- Alert fired - real, spurious, or known condition?

## Inputs

Required: report or symptom. Optional: affected entity (user/order/request ID), time window, expected vs actual behavior. Infer scope from the symptom if not provided.

## Rules

- Classify the request type before gathering evidence - it determines what to look at
- Verify expected behavior in code before concluding "bug"
- Scale investigation depth to blast radius (Step 3), not to ticket volume
- Always produce a clear finding (Bug | Working as designed | Config | Data | Permission | Insufficient evidence)

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Classify Request

| Request Type        | Signals                                                          |
| ------------------- | ---------------------------------------------------------------- |
| Data issue          | Wrong value, missing record, unexpected state                    |
| Access / permission | User cannot access resource or feature                           |
| Operational failure | Batch / cron / queue did not run or completed wrong              |
| Unexpected behavior | Behaves differently than expected, no error thrown               |
| Performance         | Slow response, timeout, high latency (no outage)                 |
| Alert investigation | Alert fired, unclear if real or spurious                         |

### Step 3 - Scope and Blast Radius Check

Narrow first, then verify it is not silently affecting others.

- One entity or many? Reproducible or intermittent? Specific endpoint/feature/data subset? Started at a specific time?
- **Blast radius probe**: query for other entities with the same symptom (e.g., other users with the same status filter); check error logs/metrics for the same code path - elevated rates suggest wider impact; if traceable to a deploy/config/migration, assume all users on that code path may be affected until proven otherwise.

**Escalate to `incident-root-cause` if any of:** ≥3 distinct users affected within an hour, error rate on the affected path >2x baseline, OR a revenue/auth/data-integrity path is impacted.

### Step 4 - Verify Expected Behavior

Before concluding "bug", read the code and confirm what the system is *designed* to do. Use skill: `task-code-explain` if the path is unfamiliar. Check feature flags, config values, A/B assignments, and recent deploys. This step frequently reveals the reported behavior is correct (misunderstanding) or a known limitation.

### Step 5 - Collect Evidence

| Type                    | Primary evidence                                                                                                          |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| **Data issue**          | DB state for the entity; API/UI response vs DB; write-path trace; visibility filters; recent migrations                  |
| **Access / permission** | Role + permission assignments; feature flag for user/cohort; auth token validity and scope                               |
| **Operational**         | Execution logs for job/scheduler/worker; queue depth; consumer health; verify the scheduler ran at all                   |
| **Unexpected behavior** | Trace specific request via `log-analysis`; identify executed branch; config/flags at the time                            |
| **Performance**         | Slow query logs; external dependency latency; tie slowness to data shape or traffic pattern via `log-analysis`           |
| **Alert**               | Metric vs threshold over 24h; corroborate with `log-analysis`; check for historical pattern (scheduled load, known flap) |

**Layer isolation (data issues):** verify what the DB contains, what the API/UI returned, and where they diverge - the bug may be in storage, query, cache, or render. Watch for non-atomic writes across services (e.g., webhook side-effect succeeded but state write failed), timezone mismatches in date filters, and soft-delete or pagination scoping silently hiding rows.

### Step 6 - Finding and Action

| Finding                                 | Recommended Action                                                                    |
| --------------------------------------- | ------------------------------------------------------------------------------------- |
| Bug confirmed                           | Reproduction steps + route to `task-code-debug`                                       |
| Expected behavior                       | Document why it is correct; draft response to requester                               |
| Config or flag issue                    | Identify the change; assess change risk                                               |
| Data issue                              | Identify correction; decide hotfix vs migration                                       |
| Permission / access                     | Identify role/flag/entitlement to update                                              |
| Intermittent, insufficient evidence     | State what additional logging or data is needed                                       |
| False positive alert                    | Document expected pattern; recommend alert tuning                                     |

## Output

```markdown
## Investigation: {one-line description}

Request Type: {Data | Access | Operational | Unexpected behavior | Performance | Alert}
Affected Scope: {Single user | N users | Tenant/cohort | Specific feature | All users}
Blast Radius Probe: {Confirmed isolated | Potentially affects N others - method used}
Time Window: {when}

### Expected vs Actual
- Expected: {what should happen}
- Actual: {what is happening}
- Verdict: {Bug | Working as designed | Config | Data | Permission | Insufficient evidence}

### Evidence
- {Finding 1 with source - log line, query result, code path, config value}
- {Finding 2}

### Root Finding
{2-4 sentences. Reference specific evidence. Concrete.}

### Recommended Action
- [ ] {Action 1 - who does what}
- [ ] {Action 2}

### Remaining Uncertainty
- {Unknown + what would resolve it, or "None - investigation conclusive"}
```

## Self-Check

- [ ] Request type classified before evidence collection
- [ ] Expected behavior verified in code before concluding "bug"
- [ ] For data issues: API/UI response compared to DB to isolate the layer
- [ ] Blast radius probed - confirmed isolated or quantified silent impact
- [ ] Escalation criteria checked (≥3 users / >2x error rate / revenue path)
- [ ] Finding is conclusive or names what is needed to conclude
- [ ] Recommended action is concrete and assigned

## Avoid

- Fishing through logs without a hypothesis - state what signal you needed if absent
- Routing to `task-code-debug` without a stack trace or reproduction path
- Skipping layer isolation on data issues - "the value is wrong" without naming which layer is incorrect
