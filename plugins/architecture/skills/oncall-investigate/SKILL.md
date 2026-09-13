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
- Always produce a clear finding (Bug | Working as designed | Config | Data | Permission | False positive / known-condition alert | Insufficient evidence | Escalated - see `incident-root-cause`). Known-condition = the signal is real but the load is expected (scheduled job, known peak); it shares the alert-tuning action path
- When a system a check needs is inaccessible (DB, flags, config, cache contents) and the ticket does not answer it, record the check as `Not run` - never skip it silently

## Workflow

### Step 1 - Detect Stack

Consume the stack the calling workflow supplies; run `Use skill: stack-detect` only when none was handed in. It is consumed in Step 4, where the framework-implicit behaviours to check (transaction boundaries, ORM callbacks, scheduling, retries, caching, serialization defaults) depend on the framework, and it is handed forward on escalation.

### Step 2 - Classify Request

These six values are the `Request Type` enum; use them verbatim here, in Step 5, and in the output.

| Request Type        | Signals                                                          |
| ------------------- | ---------------------------------------------------------------- |
| Data                | Wrong value, missing record, unexpected state                    |
| Access              | User cannot access resource or feature                           |
| Operational         | Batch / cron / queue did not run or completed wrong              |
| Unexpected behavior | Behaves differently than expected, no error thrown               |
| Performance         | Slow response, timeout, high latency (no outage)                 |
| Alert               | Alert fired, unclear if real or spurious                         |

Tiebreakers. **Data** when the symptom is a wrong value persisted or served for a specific entity - in the DB, a cache, or an API/UI response; **Unexpected behavior** when stored and served values are correct but a code path produces an unexpected outcome. **Alert** when a monitor firing is what is in question; **Performance** when the slowness is reported by a person or a client regardless of whether a monitor fired. **Operational** when a scheduled job did not run or produced wrong output; **Performance** when it ran correctly but too slowly.

Request Type describes what was reported; Verdict describes what you found. They share some words and are independent: a Data request routinely ends at a Bug verdict.

### Step 3 - Scope and Blast Radius Check

Narrow first, then verify it is not silently affecting others.

- One entity or many? Reproducible or intermittent? Specific endpoint/feature/data subset? Started at a specific time?
- **Blast radius probe**: query for other entities with the same symptom (e.g., other users with the same status filter); for operational failures, the impact set is other runs of the same job plus downstream consumers of its output; for an alert with no entity, it is whether other hosts or jobs in the same group show the same signal; check error logs/metrics for the same code path - elevated rates suggest wider impact; if traceable to a deploy/config/migration, assume all users on that code path may be affected until proven otherwise. When you cannot run the probe (no DB/log access), mark it `Not run` and name the recommended query as an action item. A probe with more than one part that you could only half-run is `Partially run` - say which half, and carry the unrun half into Remaining Uncertainty.

**Escalate to `incident-root-cause` if any of:** >=3 distinct users (or tenants) affected within an hour - entities alone do not count, and "N others affected" counts distinct users excluding the reporter; error rate on the affected path is more than 2x baseline and more than 10 errors in that hour, so a handful of errors on a quiet path does not qualify; OR a revenue/auth/data-integrity path shows confirmed multi-user impact or active error-rate elevation. "Confirmed" means observed in evidence - a mechanism that could plausibly affect many users is a reason to run the probe, not a reason to escalate. Evaluate the error-rate criterion from evidence in hand; when no error-rate figure is held, fetch `metric_series` for it here (`ops-observability-fetch`) or mark that criterion `Not run`. A single job or queue with no peer group makes the probe `N/A`.

Escalating ends this investigation. Fill Request Type, Affected Scope, Blast Radius Probe, Time Window, Escalation and the Verdict line; write the handoff into Evidence; omit the Expected and Actual lines and the Root Finding section; Recommended Action carries the single hand-off action; put anything still unknown in Remaining Uncertainty. The handoff carries the symptom, the scope found so far, the detected stack, and an error or stack trace or a monitor/issue URL - `incident-root-cause` needs one of those two to start, so where you hold neither, say so in the handoff and name what the receiving engineer must capture first.

### Step 4 - Verify Expected Behavior

Before concluding "bug", read the code and confirm what the system is *designed* to do. With no repository access at all, the intended behaviour comes from whatever states it - the ticket, a runbook, a design doc - and the verdict says which source stood in for the code, since a Bug verdict resting on a description rather than a code path is weaker than one resting on the path itself. When the path is unfamiliar, trace it end to end - entry point -> handler -> service -> persistence - and note any framework-implicit behavior that could explain the symptom on its own (transactions and their boundaries, ORM callbacks/signals, async or scheduled execution, retries, caching, default serialization). Check feature flags, config values, A/B assignments, and recent deploys (inaccessible systems: see Rules).

For Alert requests, "expected behavior" means the monitor's intent: compare threshold, evaluation window, and recovery threshold against the observed metric pattern, and check whether the triggering pattern is scheduled or known load.

### Step 5 - Collect Evidence

Use skill: `ops-observability-fetch` for any row whose evidence lives in an APM/logging/error-tracking tool and is not already in the ticket; if the ticket already contains everything needed, skip the fetch entirely - no unavailable blocks. Every `query_logs`, `query_metrics` and `list_deploys` fetch carries a window - the reported occurrence plus enough history to tell new from chronic, and at least 7 days for a recurring pattern - and the affected service. Name the project's actual metric for any `query_metrics` call - that capability has no URL trigger and will otherwise come back asking for one.

Synthesize what comes back into the `Evidence` bullets with its source named; do not paste raw blocks. A block that comes back needing a parameter is answerable - supply it and refetch; a block with no transport, or whose call errored, makes its check `Not run`; an empty result from a working transport is evidence of absence, not `Not run`.

Where a row names `log-analysis`, hand it the affected service and the failure window, or the request ID with the window it occurred in, which its required inputs need, and fold what it returns into this report: its Key Evidence into `Evidence`, its trigger and causal chain into `Root Finding`, its Log Gaps into `Remaining Uncertainty`.

Some evidence these rows call for lives outside all six capabilities - DB state, role and entitlement records, flag assignments, migration history. Read those from the systems that hold them, or mark the check `Not run` per the Rules.

| Type                    | Capabilities                              | Primary evidence                                                                                |
| ----------------------- | ----------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Data**                | `query_logs`, `list_deploys`, `fetch_trace` | DB state for the entity; API/UI response vs DB; the write path (Step 4's code path, or `fetch_trace` when a trace ID is held); visibility filters; recent migrations and deploys |
| **Access**              | `query_logs`                              | Role + permission assignments; feature flag for user/cohort; auth token validity and scope      |
| **Operational**         | `query_logs`, `query_metrics`, `list_deploys` | Execution logs for job/scheduler/worker; queue depth; consumer health; verify the scheduler ran at all |
| **Unexpected behavior** | `query_logs`, `fetch_trace`               | Use skill: `log-analysis` on the failing request; identify executed branch; config/flags at the time |
| **Performance**         | `query_logs`, `fetch_trace`               | Slow query logs; external dependency latency; use skill: `log-analysis` on the slow window to place the slowness in a causal chain |
| **Alert**               | `query_metrics`, `fetch_monitor`, `fetch_issue` | Metric vs threshold over a multi-day window; monitor config hygiene - `fetch_monitor` returns name, status, threshold, current value and last-triggered, so read evaluation window, recovery threshold and last-edited from the monitor definition itself and mark them `Not run` when you cannot open it |

`fetch_issue` returns first-seen and last-seen, which tell you whether a recurring symptom is new or chronic. Step 4's deploy check uses `list_deploys` on any row when a deploy is a candidate. Where a row names `log-analysis`, invoke it instead of fetching those blocks yourself - it performs its own fetch.

**Layer isolation (data issues):** verify what the DB contains, what the API/UI returned, and where they diverge - the bug may be in storage, query, cache, or render. Watch for non-atomic writes across services (e.g., webhook side-effect succeeded but state write failed), timezone mismatches in date filters, soft-delete or pagination scoping silently hiding rows, and the same record served by two read paths (different endpoints, caches, or replicas) returning divergent values. When the diverging layer is a cache, confirm staleness (compare cached value + TTL/written-at against source of truth; when cache contents cannot be inspected, record the inferred staleness under Remaining Uncertainty) and identify the missing invalidation trigger.

### Step 6 - Finding and Action

| Finding                  | Recommended Action                                                  |
| ------------------------ | ------------------------------------------------------------------- |
| Bug                      | Reproduction steps + hand off to the owning engineer; where wrong data is already persisted or cached, the correction is an action too |
| Working as designed      | Document why it is correct; draft response to requester             |
| Config                   | Identify the change; assess change risk                             |
| Data                     | Correct the wrong value: hotfix vs migration for stored data, re-import or re-sync for a bad feed |
| Permission               | Identify role/flag/entitlement to update                            |
| Escalated                | Hand off per Step 3; this skill produces no further finding         |
| False positive / known-condition alert | Name the tuning: raise threshold above known peak, add recovery threshold, widen evaluation window, or mute window for scheduled load - AND state whether the system should change instead (e.g., stagger the load) when the pattern itself is a risk |
| Insufficient evidence    | State what additional logging or data is needed                     |

Where wrong data and a code defect coexist - a stale cache caused by a missing invalidation - the verdict is `Bug` and the data correction is one of its actions. `Data` is for a wrong value with no code defect behind it: a bad import, a manual edit, an upstream feed.

## Output

`Affected Scope` states what you know after the probe and stays consistent with the probe line: an unrun probe cannot yield a confirmed scope, and `None (alert only)` rests on the ticket or monitor stating there is no user-facing impact, not on the probe.

```markdown
## Investigation: {one-line description}

Request Type: {Data | Access | Operational | Unexpected behavior | Performance | Alert}

Affected Scope: {Single entity | N entities | Single user | N users | Tenant/cohort | Specific feature | All users | None (alert only) | Unknown - probe not run}

Blast Radius Probe: {Confirmed isolated | Confirmed N others affected | Potentially affects N others | Partially run - <which half> | Not run | N/A - no entity or group scope} - {query/source used, or the one recommended}

Escalation: {Not met | Not met - <criterion> not run | Escalated - <criterion met>; handoff: stack <stack>, <error or stack trace, or monitor/issue URL held | none held - capture <what> first>}

Time Window: {first occurrence | range from first to latest occurrence}{, recurring <cadence>}{, unknown - <what would establish it>}

### Expected vs Actual
- Expected: {what should happen; for alerts, the monitor's intent}
- Actual: {what is happening - may be correct behavior with a miscalibrated monitor}
- Verdict: {Bug | Working as designed | Config | Data | Permission | False positive / known-condition alert | Insufficient evidence | Escalated - see incident-root-cause}

### Evidence
- {Finding 1 with source - log line, query result, code path, config value}
- {Finding 2}
- {each check that could not be run: "Not run - <what was inaccessible>"}

### Root Finding
{2-4 sentences. Reference specific evidence. Concrete.}

### Recommended Action
- [ ] {Action 1 - who does what; 1-3 actions. Alert verdicts include the tune-vs-fix decision as an action. A probe that could not be run contributes its recommended query here - under Escalated, appended to the hand-off action.}

### Remaining Uncertainty
- {Every check marked Not run, plus any inference the evidence could not settle, each with what would resolve it; or "None - investigation conclusive"}
```

## Self-Check

- [ ] behavioral-principles loaded before Step 1; Step 1: stack taken from the caller or detected
- [ ] Step 2: request type classified, using the enum verbatim, before evidence collection
- [ ] Step 3: blast radius probed - confirmed isolated, quantified, partially run, N/A, or marked Not run with the recommended check
- [ ] Step 3: escalation criteria checked (>=3 distinct users within an hour / error rate over 2x baseline and over 10 errors in that hour / revenue, auth or data-integrity path with confirmed multi-user impact or active error-rate elevation); Escalation line states the outcome, naming any criterion not run
- [ ] Step 4: expected behavior verified before concluding (code for bugs, or the source that stood in for it; monitor intent for alerts), or n/a - Escalated at Step 3
- [ ] Step 5: fetch performed or deliberately skipped because the ticket already held the evidence; for Data requests, API/UI response compared to DB to isolate the layer; unrunnable checks marked Not run; or n/a - Escalated at Step 3
- [ ] Step 6: verdict named from the enum; alert verdicts carry the tune-vs-fix decision as an action
- [ ] Finding is conclusive, names what is needed to conclude, or is Escalated; every Not run check reaches Remaining Uncertainty
- [ ] Recommended actions (1-3; the single hand-off when Escalated) are concrete and assigned

## Avoid

- Fishing through logs without a hypothesis - state what signal you needed if absent
- Handing off a "Bug" verdict without a stack trace or reproduction path
- Skipping layer isolation on data issues - "the value is wrong" without naming which layer is incorrect
- Tuning an alert without asking whether the underlying load pattern should change instead
