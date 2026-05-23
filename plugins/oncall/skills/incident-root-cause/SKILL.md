---
name: incident-root-cause
description: Active incident root cause analysis with containment-first triage, blast radius assessment, and ranked hypotheses for service degradation.
metadata:
  category: ops
  tags: [incident, root-cause, on-call, reliability, containment]
user-invocable: false
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Incident Root Cause Analysis

## When to Use

Active production incident, on-call triage, cascading failure diagnosis. Containment is the priority; analysis exists to enable containment, not gate it.

## Inputs

Required: error or stack trace. Optional: log snippets, recent PR diff, metrics summary, config snapshot, deploy metadata, service map. When evidence is thin, frame from what is available, recommend containment by error class, and list the 3-5 evidence items needed to raise confidence.

## Output Contract

- Containment recommendations come first; every containment action includes ETA in minutes
- Every hypothesis cites observable evidence and includes a verification step
- Blast radius classified explicitly: Narrow | Moderate | Wide | Critical
- Each prevention action has a priority: immediate | next sprint | quarterly
- Findings ordered by urgency: containment > hypothesis > gaps > prevention
- Omit empty sections; no debugging walkthroughs, no code-style commentary

## Workflow

### Step 1 - Frame the Incident (60 seconds)

Extract: symptom onset, duration, affected services with status (degraded/down/healthy), affected percentage. Assign severity:

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue-impacting, >50% requests affected, or data loss risk            |
| High     | User-facing degradation, 10-50% affected, or multiple services impacted |
| Medium   | Partial degradation <10%, single service, no data risk                  |
| Low      | Non-user-facing, minimal impact                                         |

### Step 2 - Recommend Containment

Pick from this ladder by speed and safety. Prefer fast reversible actions; avoid patching under pressure.

1. **Resource recovery** - restart affected instances; resize pool/thread limits if runtime-configurable; drain slow consumers
2. **Rollback** - if recent deploy correlates. Use skill: `ops-backward-compatibility` to verify rollback safety (schema/contract changes)
3. **Feature flag disable** - surgical isolation; preferred when rollback is unsafe
4. **Circuit breaker** - stop cascading; critical when downstream latency exhausts upstream resources
5. **Traffic isolation / rate limit** - shed or route to degraded path
6. **Scale up** - only when resource exhaustion is confirmed and recovery alone is insufficient
7. **Hotfix** - only when rollback and flag-disable are both unsafe, root cause is clear, and the diff is single-line
8. **Data repair** - if partial writes occurred

Use skill: `ops-resiliency` for circuit breaker / retry patterns.

### Step 3 - Classify and Assess Blast Radius

Use skill: `ops-failure-classification` to name the primary failure class.
Use skill: `review-blast-radius` to score code/data/user dimensions.
Use skill: `failure-propagation-analysis` only if cascading is observed across services.

Also assess: shared resource contention (DB, cache, queue, pools), API contract impact, data corruption risk.

Apply domain skills only if the classification matches:

- Concurrency: `architecture-concurrency`
- Data consistency: `architecture-data-consistency`
- Slow query, missing index, N+1: `backend-db-indexing`
- External dependency, connection pool, or other resource exhaustion: `ops-resiliency`

### Step 4 - Generate Hypotheses

Use skill: `root-cause-hypothesis`.

If a recent PR diff is provided, use skill: `review-change-risk` to score the triggering change before forming hypotheses.

Each hypothesis must include: suspect component and mechanism, contributing factors (distinct from root cause), triggering change, propagation path, timeline interpretation if there is a deploy-to-symptom lag, confidence with evidence balance, and one concrete verification step.

### Step 5 - Observability Gaps

Use skill: `ops-observability`. For each gap: missing signal → diagnostic question it could not answer → concrete addition.

### Step 6 - Immediate Prevention Notes

While the incident is active, capture only the 1-3 highest-leverage prevention items that emerged during diagnosis (architecture guardrail, monitoring add, deploy safeguard). Each: addresses the failure class, assigns priority, states blast radius reduction.

Full systemic prevention belongs in `task-postmortem` after resolution. Do not run a deep governance review under incident pressure.

## Output

```markdown
## Incident Summary

Failure Type:
Severity: Low | Medium | High | Critical
Blast Radius: Narrow | Moderate | Wide | Critical
Onset: {timestamp or "unknown"}
Duration:
Affected Services:
- {service}: {degraded/down/healthy}

## Immediate Containment

- [ ] Action 1 ({priority}, ETA {N} min, expected impact)
- [ ] Action 2

## Root Cause Hypothesis

{From root-cause-hypothesis: primary + secondary blocks with mechanism, evidence, contributing factors, triggering change, timeline interpretation, confidence, verification}

## Observability Gaps

| Missing Signal | Diagnosis Impact | Recommended Addition |
| -------------- | ---------------- | -------------------- |

## Immediate Prevention Notes

| Action | Failure Class Prevented | Priority | Blast Radius Reduction |
| ------ | ----------------------- | -------- | ---------------------- |

(1-3 highest-leverage items only; full prevention belongs in postmortem.)

## Key Takeaways

3-5 staff-level insights about the system, not just the incident.
```

## Self-Check

- [ ] Severity assigned with justification; onset and duration stated (or marked unknown)
- [ ] Affected services enumerated with individual status
- [ ] Blast radius classified before any hypothesis
- [ ] At least one containment action with ETA appears before diagnosis
- [ ] Every hypothesis cites evidence and has a verification step
- [ ] Triggering change identified if evidence exists; propagation path traced
- [ ] Prevention notes limited to 1-3 highest-leverage items; deep prevention deferred to postmortem

## Avoid

- Treating symptoms as root causes
- Hypotheses without evidence or verification
- Running a full governance review while the incident is active
- Verbose explanations under incident pressure
