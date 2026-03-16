---
name: task-release-validate
description: Post-deploy go-live monitoring runbook. Converts a release plan into a time-boxed checkpoint sequence - what signals to watch, when to advance canary or roll back, and who makes the call. Use immediately after a production deployment while the team is watching.
metadata:
  category: ops
  tags: [release, monitoring, canary, go-live, rollback, observability]
  type: workflow
user-invocable: true
---

# Release Validate -- Go-Live Monitoring

## Purpose

Turn a deployed release into a structured monitoring sequence that the on-call engineer can follow without interpretation:

- **Time-boxed checkpoints** -- explicit "at T+N minutes, check these signals" progression
- **Go / No-Go criteria** -- binary decisions at each checkpoint, not open-ended observation
- **Rollback trigger** -- a specific condition that initiates rollback, not a vague threshold
- **Canary advancement** -- when and how to widen traffic percentage
- **Handoff** -- when the active monitoring window closes and what normal operation looks like

This skill is for the window _after_ deployment. For pre-deploy planning, use `/task-release-plan`.

## When to Use

- Immediately after a production deployment while the team is watching
- After enabling a feature flag for a gradual rollout
- After advancing a canary to the next traffic percentage
- When a release plan (from `/task-release-plan`) was produced and you need the live monitoring version of it

Not for pre-deploy planning (use `task-release-plan`) or writing postmortems (use `task-incident-postmortem`).

## Inputs

| Input                | Required | Description                                                                  |
| -------------------- | -------- | ---------------------------------------------------------------------------- |
| Release summary      | Yes      | What was deployed - feature description or release plan summary              |
| Rollout strategy     | Yes      | Rolling / canary / feature flag / blue-green and current traffic % if canary |
| Deploy time          | Yes      | When the deploy completed (e.g. "deployed at 14:32 UTC")                     |
| Risk level           | No       | Low / Medium / High / Critical (from release plan, or re-classify here)      |
| Canary metrics plan  | No       | Specific metrics and thresholds from a prior `/task-release-plan --deep`     |
| Rollback plan        | No       | Rollback procedure from the release plan                                     |
| Monitoring dashboard | No       | URL or name of the team dashboard for this service                           |

Handle partial inputs gracefully. When a prior release plan is not provided, derive risk level and key signals from the release summary.

## Rules

- Every checkpoint must have a binary Go / No-Go decision - not "continue observing"
- Rollback trigger must be a specific observable condition, not "if things look bad"
- Time-box every phase - open-ended monitoring is not a runbook
- Canary advancement must state traffic percentage and soak time before each advance
- When risk is High or Critical, require explicit human sign-off before advancing canary
- Omit phases that don't apply (e.g., no canary section for a rolling update)
- Output must be followable by an on-call engineer with no prior context on the release

## Monitoring Model

### Step 1 - Classify and Calibrate

Use skill: `ops-observability` to identify the key signals for this release.
Use skill: `ops-failure-classification` to determine which failure modes are most likely in the first minutes post-deploy.

Determine the monitoring window length based on risk:

| Risk Level | Active Monitoring Window | Canary Soak (if applicable) |
| ---------- | ------------------------ | --------------------------- |
| Low        | 30 minutes               | N/A                         |
| Medium     | 1 hour                   | 30 min per stage            |
| High       | 2-4 hours                | 1-2 hours per stage         |
| Critical   | 24 hours with handoffs   | 2-4 hours per stage         |

### Step 2 - Define Checkpoints

Create a time-boxed checkpoint sequence from T+0 (deploy complete) through end of monitoring window.

For each checkpoint:

- **Time**: T+N minutes from deploy complete
- **Signals to check**: Specific metric names, log patterns, or health endpoint responses
- **Healthy state**: What "green" looks like for each signal
- **Unhealthy state**: What triggers a No-Go decision
- **Decision**: Go (advance to next checkpoint or widen canary) / No-Go (rollback)

Use skill: `review-blast-radius` to prioritize which signals matter most for the specific change.

### Step 3 - Canary Advancement Plan

**Skip if rollout is not canary-based.**

Define explicit stages with traffic percentages and advancement criteria:

| Stage | Traffic % | Soak Time    | Advance Criteria                     | Rollback Trigger                    |
| ----- | --------- | ------------ | ------------------------------------ | ----------------------------------- |
| 1     | 5-10%     | 30 min       | Error rate and latency within bounds | Error rate > threshold or p99 spike |
| 2     | 25%       | 30-60 min    | Same signals, larger sample          | Same                                |
| 3     | 50%       | 30-60 min    | Same signals                         | Same                                |
| 4     | 100%      | Full rollout | -                                    | -                                   |

Adjust stages based on risk level. High / Critical risk: require explicit approval before each advance.

Use skill: `ops-feature-flags` if the canary is controlled by a feature flag - define the flag state at each stage.

### Step 4 - Rollback Trigger and Procedure

**Every runbook must have a single, unambiguous rollback trigger condition.**

Define:

- **Rollback trigger**: The specific condition that initiates rollback (e.g. "error rate > 1% for 5 consecutive minutes on /api/v1/orders")
- **Who calls it**: On-call engineer / tech lead / automated alert
- **Rollback steps**: Ordered steps from the release plan (or derived here if not provided)
- **Rollback time estimate**: How long until the system is back to pre-deploy state
- **Post-rollback validation**: How to confirm the rollback succeeded

Use skill: `ops-resiliency` to check if circuit breakers or fallbacks are providing any automatic protection during the monitoring window.

### Step 5 - Monitoring Window Close

Define what "done" looks like - the condition under which active monitoring ends and the release is considered stable:

- All checkpoints passed without a No-Go condition
- Error rate and latency have been within bounds for the full monitoring window
- No anomalies in downstream consumers or dependent services
- Feature flag is in its final state (if applicable)

After the window closes:

- Remove the release from active monitoring
- Hand off any follow-up work (cleanup of dual-write, feature flag removal, backfill completion check) as normal tickets

## Output

```markdown
# Go-Live Monitoring Runbook: [Release Name]

**Deployed:** [time]
**Rollout strategy:** [rolling / canary at X% / feature flag / blue-green]
**Risk level:** [Low | Medium | High | Critical]
**Monitoring window:** [duration - e.g. "2 hours, closes at 16:32 UTC"]
**On-call:** [name or rotation - fill in]

---

## Rollback Trigger

> **Roll back immediately if:** [specific observable condition - e.g. "error rate on POST /api/v1/payments exceeds 1% for 5 consecutive minutes"]

**Rollback steps:**

1. [Step 1]
2. [Step 2]
3. [Step N]

**Estimated rollback time:** [duration]

---

## Checkpoint Sequence

### T+0 - Deploy Complete

- [ ] Health check: [endpoint or command] returns [expected response]
- [ ] No spike in error rate on [affected endpoints]
- [ ] Deploy confirmed in [monitoring tool / dashboard]

**Go**: Proceed to T+15 checkpoint.
**No-Go**: Rollback - trigger condition above is met.

---

### T+[N] min - [Checkpoint Name]

**Check:**

- [ ] [Signal 1]: [metric name] is [expected range]
- [ ] [Signal 2]: [metric name] is [expected range]
- [ ] [Signal 3 - downstream]: [metric name] is [expected range]

**Healthy state**: All signals within bounds.
**Unhealthy state**: [specific condition that triggers No-Go]

**Decision:**

- Go: [what Go means - e.g., "advance canary to 25% traffic"]
- No-Go: Rollback - [reason]

---

[repeat checkpoint blocks through end of monitoring window]

---

## Canary Advancement (if applicable)

| Stage | Traffic % | Advance At | Advance Criteria | Approval Required |
| ----- | --------- | ---------- | ---------------- | ----------------- |
| 1     | [%]       | T+[N] min  | [criteria]       | [Yes/No]          |
| 2     | [%]       | T+[N] min  | [criteria]       | [Yes/No]          |
| Full  | 100%      | T+[N] min  | [criteria]       | [Yes/No]          |

---

## Monitoring Window Close

**Active monitoring ends at:** [time]

Conditions to close:

- [ ] All checkpoints passed
- [ ] Error rate and p99 latency within baseline for full window
- [ ] No anomalies in downstream services
- [ ] Feature flag in final state (if applicable)

**After close:** [any follow-up tickets or cleanup - e.g., "schedule feature flag cleanup", "verify backfill complete"]
```

### Output Constraints

- Rollback trigger must be the first thing in the output after the header - it is the most important part
- Every checkpoint must have a binary Go / No-Go decision
- Times must be concrete (T+N minutes or wall-clock time) - never "after a while"
- Canary stage advancement criteria must reference specific metrics, not general health
- Output must be self-contained - followable without reading the release plan

## Self-Check

- [ ] Rollback trigger is specific and observable - not "if things look bad"
- [ ] Every checkpoint has a Go / No-Go decision with a concrete condition
- [ ] Monitoring window has an explicit end time or duration
- [ ] Canary stages (if applicable) have traffic percentages and soak times
- [ ] Post-rollback validation step defined
- [ ] Output is followable at 2am by someone who did not write the release plan

## Avoid

- Open-ended monitoring ("keep watching for a few hours")
- Vague rollback triggers ("if error rate increases")
- Checkpoints without a No-Go path
- Reproducing the full release plan - reference it, don't repeat it
- Advancing canary based on time alone - advancement requires signal validation
- Omitting downstream service signals for releases that affect consumers

