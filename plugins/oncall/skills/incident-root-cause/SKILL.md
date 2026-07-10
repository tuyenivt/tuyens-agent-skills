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

Active production incident, on-call triage, cascading failure diagnosis. Stack context comes from the calling workflow's `stack-detect`; do not re-run it - if absent, proceed stack-agnostic.

## Inputs

Required: error or stack trace, OR a Sentry/Datadog/monitor URL. Optional: log snippets, recent PR diff, metrics summary, config snapshot, deploy metadata, service map.

## Workflow

### Step 1 - Frame the Incident (60 seconds)

Use skill: `ops-observability-fetch` when inputs include a URL or ID, or when any of onset, affected scope, or deploy correlation is missing from the paste. Pull `error_event`, `monitor_state`, `metric_series` (error rate + latency; window: onset minus 60 min to now, or last 60 min when onset is unknown), and `list_deploys` for the last 48h on the affected service and any implicated downstream service. Cache the transport.

Extract: symptom onset (timestamp, or relative like "~40 min ago"), duration, affected services with status (degraded/down/healthy), affected percentage - requests or users, whichever the evidence gives; name which. Assign severity; when criteria from multiple rows match, take the highest row.

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue-impacting (payment, checkout, billing, or auth path), >50% requests affected, or data loss risk |
| High     | User-facing degradation, 10-50% affected, or multiple services impacted |
| Medium   | Partial degradation <10%, single service, no data risk                  |
| Low      | Non-user-facing, minimal impact                                         |

**Thin evidence** (all three missing: metrics, deploy data, scope): assign severity from the worst plausible reading and recommend containment by error class in Step 2. Whenever any of the three is missing - fully thin or not - list the 3-5 evidence items that would raise confidence in the output's `Evidence Needed` section.

### Step 2 - Recommend Containment

Pick from this ladder by speed and safety. Prefer fast reversible actions; avoid patching under pressure.

1. **Resource recovery** - restart affected instances; resize pool/thread limits if runtime-configurable; drain slow consumers
2. **Rollback** - if recent deploy correlates. Use skill: `ops-backward-compatibility` to verify rollback safety (schema/contract changes); attach the verdict to the rollback action line as `rollback safe | unsafe - {reason}`
3. **Feature flag disable** - surgical isolation; preferred when rollback is unsafe
4. **Circuit breaker** - stop cascading; critical when downstream latency exhausts upstream resources
5. **Traffic isolation / rate limit** - shed or route to degraded path
6. **Scale up** - only when resource exhaustion is confirmed and recovery alone is insufficient
7. **Hotfix** - only when rollback and flag-disable are unsafe, root cause is verified, and the diff is minimal with no schema/contract change
8. **Data repair** - if partial writes occurred

Recommend 1-3 actions, each with ETA in minutes. When multiple rungs apply, run rollback (if deploy correlates) and circuit breaker (if downstream latency is the amplifier) concurrently. Lower rungs (scale, hotfix) only after the top three have been tried or ruled out. When the cause is unknown on thin evidence, rung 1 by error class is the default recommendation; add further actions only when independently justified.

Use skill: `ops-resiliency` for circuit breaker / retry patterns.

### Step 3 - Classify and Assess Blast Radius

Use skill: `ops-failure-classification` to name the primary failure class.
Use skill: `review-blast-radius` to score code/data/user dimensions; classify explicitly: Narrow | Moderate | Wide | Critical. Mark code/data dimensions `(unverified)` when the codebase is not accessible.
Use skill: `failure-propagation-analysis` when two or more components are involved - directly (service calling service) or via a shared resource (DB, queue, cache). A single service exhausting its own pool with no external participant does not qualify; that same pool starving because a slow downstream dependency holds connections does.

Also assess: shared resource contention (DB, cache, queue, pools), API contract impact, data corruption risk.

Then load the domain skill matching the root failure type:

| Root failure type                                                          | Domain skill                                       |
| -------------------------------------------------------------------------- | -------------------------------------------------- |
| Concurrency issue (genuine race/lock/deadlock)                             | `architecture-concurrency`                         |
| Transaction boundary error / partial writes                                | `architecture-data-consistency`                    |
| DB performance degradation, N+1                                            | `backend-db-indexing`                              |
| Resource exhaustion, resource contention, external dependency failure      | `ops-resiliency`                                   |
| Other types (logic bug, misconfiguration, deploy drift, boundary violation) | none - proceed                                     |

Pool exhaustion is `ops-resiliency`, not `architecture-concurrency`.

### Step 4 - Generate Hypotheses

Use skill: `root-cause-hypothesis`. If a recent PR diff is provided, use skill: `review-pr-risk` first to score the triggering change. If propagation across services was observed in Step 3, the hypothesis must include the propagation path.

When signals conflict (deploy timestamp vs. degradation onset, region split vs. global change), or two causal directions fit the same evidence (the deploy overloaded the dependency vs. the dependency degraded independently), produce two hypotheses with explicit confidence and a verification step that discriminates them.

### Step 5 - Observability Gaps

Use skill: `ops-observability`. For each gap: missing signal → diagnostic question it could not answer → concrete addition.

### Step 6 - Immediate Prevention Notes

Capture 1-3 items the on-call team can start within the next hour that prevent recurrence in the current incident window (e.g., shipping the per-attempt timeout, enabling the breaker flag). Each: addresses the failure class, has an ETA, states blast radius reduction. Longer-horizon prevention belongs in `task-postmortem` Step 7 - do not produce a guardrail/persistence table here.

## Output

Populate Summary fields as steps complete (blast radius arrives in Step 3); section order is presentation order, not execution order. Reproduce the `root-cause-hypothesis` output block verbatim; synthesize all other sub-skill outputs into the sections below rather than pasting their raw blocks - the blast radius classification and propagation path land in the Incident Summary (Blast Radius line + Affected Services), and the propagation path also feeds Step 4. Omit empty sections, including `Evidence Needed` when evidence was sufficient.

```markdown
## Incident Summary

Failure Type:
Severity: Low | Medium | High | Critical
Blast Radius: Narrow | Moderate | Wide | Critical
Onset: {timestamp | "~N min ago" | "unknown"}
Duration:
Affected Services:
- {service}: {degraded (N% when known) | down | healthy}

## Immediate Containment

- [ ] Action 1 (ETA {N} min, expected impact; rollback actions carry the rollback-safety verdict)
- [ ] Action 2 (1-3 actions total)

## Root Cause Hypothesis

{root-cause-hypothesis output block, verbatim}

## Evidence Needed

- {missing evidence item + where to get it} (whenever metrics, deploy data, or scope was missing; 3-5 items)

## Observability Gaps

| Missing Signal | Diagnosis Impact | Recommended Addition |
| -------------- | ---------------- | -------------------- |

## Immediate Prevention Notes

| Action | Failure Class Prevented | ETA | Blast Radius Reduction |
| ------ | ----------------------- | --- | ---------------------- |

(1-3 startable-now items only; full prevention belongs in postmortem.)
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Onset, affected scope, and recent deploys fetched via `ops-observability-fetch` (or output states why unavailable)
- [ ] Severity assigned with justification, highest matching row on ties; onset and duration stated (or marked unknown)
- [ ] Affected services enumerated with individual status
- [ ] Blast radius classified (Narrow/Moderate/Wide/Critical) before any hypothesis; unverifiable dimensions marked
- [ ] 1-3 containment actions with ETA appear before diagnosis; rollback carries safety verdict
- [ ] Every hypothesis cites evidence and has a verification step
- [ ] Triggering change identified if evidence exists; propagation path traced when cascading
- [ ] Missing signals (metrics/deploys/scope): Evidence Needed section lists 3-5 items
- [ ] Prevention notes limited to 1-3 startable-now items; guardrail/persistence deferred to postmortem
- [ ] Empty sections omitted

## Avoid

- Treating symptoms as root causes
- Hypotheses without evidence or verification
- Running a full governance review while the incident is active
- Verbose explanations under incident pressure
