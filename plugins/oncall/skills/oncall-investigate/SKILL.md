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

Required: report or symptom. Optional: affected entity (user/order/request ID), time window, expected vs actual behavior. Infer scope from the symptom if not provided. Evidence already in the ticket counts - fetch only what is missing.

## Rules

- Classify the request type before gathering evidence - it determines what to look at
- Verify expected behavior before concluding "bug" (in code; for alerts, the monitor's intent)
- Always produce a clear finding (Bug | Working as designed | Config | Data | Permission | False positive / known-condition alert | Insufficient evidence). Known-condition = the signal is real but the load is expected (scheduled job, known peak); it shares the alert-tuning action path
- When a system a check needs is inaccessible (DB, flags, config, cache contents) and the ticket does not answer it, record the check as unchecked or `Not run` - never skip it silently

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

Tiebreaker: **Data** when the symptom is a wrong value persisted or served for a specific entity - in the DB, a cache, or an API/UI response; **Unexpected behavior** when stored and served values are correct but a code path produces an unexpected outcome.

### Step 3 - Scope and Blast Radius Check

Narrow first, then verify it is not silently affecting others.

- One entity or many? Reproducible or intermittent? Specific endpoint/feature/data subset? Started at a specific time?
- **Blast radius probe**: query for other entities with the same symptom (e.g., other users with the same status filter); check error logs/metrics for the same code path - elevated rates suggest wider impact; if traceable to a deploy/config/migration, assume all users on that code path may be affected until proven otherwise. When you cannot run the probe (no DB/log access), mark it `Not run` in the output and name the recommended query as an action item.

**Escalate to `incident-root-cause` if any of:** ≥3 distinct users affected within an hour, error rate on the affected path >2x baseline, OR a revenue/auth/data-integrity path shows confirmed multi-user impact or active error rate elevation.

### Step 4 - Verify Expected Behavior

Before concluding "bug", read the code and confirm what the system is *designed* to do. Use skill: `task-code-explain` if the path is unfamiliar. Check feature flags, config values, A/B assignments, and recent deploys (inaccessible systems: see Rules).

For Alert investigations, "expected behavior" means the monitor's intent: compare threshold, evaluation window, and recovery threshold against the observed metric pattern, and check whether the triggering pattern is scheduled or known load.

### Step 5 - Collect Evidence

Use skill: `ops-observability-fetch` for any row whose evidence lives in an APM/logging/error-tracking tool and is not already in the ticket; if the ticket already contains everything needed, skip the fetch entirely - no unavailable blocks. Match request type to capability: Operational/Alert → `query_metrics` + `fetch_monitor`; Performance/Unexpected → `query_logs` + `fetch_trace`; recurring symptom → `fetch_issue` (first_seen tells you whether it's new or chronic).

| Type                    | Primary evidence                                                                                |
| ----------------------- | ----------------------------------------------------------------------------------------------- |
| **Data issue**          | DB state for the entity; API/UI response vs DB; write-path trace; visibility filters; recent migrations |
| **Access / permission** | Role + permission assignments; feature flag for user/cohort; auth token validity and scope      |
| **Operational**         | Execution logs for job/scheduler/worker; queue depth; consumer health; verify the scheduler ran at all |
| **Unexpected behavior** | Trace via `log-analysis`; identify executed branch; config/flags at the time                    |
| **Performance**         | Slow query logs; external dependency latency; trace via `log-analysis` to tie slowness to data shape or traffic |
| **Alert**               | Metric vs threshold over a multi-day window (recurring patterns need ≥7d); monitor config hygiene - threshold vs observed peaks, recovery threshold present, evaluation window, last edited; trace via `log-analysis` for the triggering window |

**Layer isolation (data issues):** verify what the DB contains, what the API/UI returned, and where they diverge - the bug may be in storage, query, cache, or render. Watch for non-atomic writes across services (e.g., webhook side-effect succeeded but state write failed), timezone mismatches in date filters, soft-delete or pagination scoping silently hiding rows, and the same record served by two read paths (different endpoints, caches, or replicas) returning divergent values. When the diverging layer is a cache, confirm staleness (compare cached value + TTL/written-at against source of truth; when cache contents cannot be inspected, record the inferred staleness under Remaining Uncertainty) and identify the missing invalidation trigger.

### Step 6 - Finding and Action

| Finding                  | Recommended Action                                                  |
| ------------------------ | ------------------------------------------------------------------- |
| Bug                      | Reproduction steps + route to `task-code-debug`                     |
| Working as designed      | Document why it is correct; draft response to requester             |
| Config                   | Identify the change; assess change risk                             |
| Data                     | Identify correction; hotfix vs migration for stored data, invalidation + code fix for stale caches |
| Permission               | Identify role/flag/entitlement to update                            |
| False positive / known-condition alert | Name the tuning: raise threshold above known peak, add recovery threshold, widen evaluation window, or mute window for scheduled load - AND state whether the system should change instead (e.g., stagger the load) when the pattern itself is a risk |
| Insufficient evidence    | State what additional logging or data is needed                     |

## Output

```markdown
## Investigation: {one-line description}

Request Type: {Data | Access | Operational | Unexpected behavior | Performance | Alert}
Affected Scope: {Single entity | Single user | N users | Tenant/cohort | Specific feature | All users | None (alert only)}
Blast Radius Probe: {Confirmed isolated | Potentially affects N others | Not run | N/A - no entity scope} - {query/source used, or recommended}
Time Window: {when}

### Expected vs Actual
- Expected: {what should happen; for alerts, the monitor's intent}
- Actual: {what is happening - may be correct behavior with a miscalibrated monitor}
- Verdict: {Bug | Working as designed | Config | Data | Permission | False positive / known-condition alert | Insufficient evidence}

### Evidence
- {Finding 1 with source - log line, query result, code path, config value}
- {Finding 2}

### Root Finding
{2-4 sentences. Reference specific evidence. Concrete.}

### Recommended Action
- [ ] {Action 1 - who does what; 1-3 actions. Alert verdicts include the tune-vs-fix decision as an action.}

### Remaining Uncertainty
- {Unknown + what would resolve it, or "None - investigation conclusive"}
```

## Self-Check

- [ ] Request type classified before evidence collection
- [ ] Expected behavior verified before concluding (code for bugs; monitor intent for alerts)
- [ ] For data issues: API/UI response compared to DB to isolate the layer
- [ ] Blast radius probed - confirmed isolated, quantified, or marked Not run with the recommended check
- [ ] Escalation criteria checked (≥3 users / >2x error rate / revenue path)
- [ ] Finding is conclusive or names what is needed to conclude
- [ ] Recommended actions (1-3) are concrete and assigned

## Avoid

- Fishing through logs without a hypothesis - state what signal you needed if absent
- Routing to `task-code-debug` without a stack trace or reproduction path
- Skipping layer isolation on data issues - "the value is wrong" without naming which layer is incorrect
- Tuning an alert without asking whether the underlying load pattern should change instead
