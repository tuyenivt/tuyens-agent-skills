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

Where the evidence already shows a mitigation applied and the symptom subsiding, the incident is contained but not closed: give Duration as the elapsed outage, and let Immediate Containment carry only what is still outstanding - verifying the mitigation holds, reverting a temporary setting, and any data repair - rather than re-recommending what has already been done.

## Inputs

Required: error or stack trace, OR a Sentry/Datadog/monitor URL. Optional: log snippets, recent PR diff, metrics summary, config snapshot, deploy metadata, service map.

## Workflow

### Step 1 - Frame the Incident (60 seconds)

Use skill: `ops-observability-fetch` when inputs include a URL or ID, or when any of onset, affected scope, or deploy correlation is missing from the paste. Request the `error_event`, `monitor_state`, `metric_series` and `deploy_event` blocks. For `metric_series` name the project's actual metric names for error rate and latency - the capability requires a named metric and will otherwise return an unavailable block and ask for one, which costs a round trip mid-incident; with no name known, let that block ask rather than inventing one; window is onset minus 60 min to now, or the last 60 min when onset is unknown. For `deploy_event`, ask for the last 48h on the affected service and any implicated downstream service. Whatever comes back unavailable, record on the Evidence Transport line and proceed on the paste alone.

Extract: symptom onset (timestamp, or relative like "~40 min ago"), duration, affected services with status (degraded/down/healthy), and the affected percentage. Then assign severity.

Percentages are of requests or of users, whichever the evidence gives; use one denominator throughout and name it in the output. Take the highest row any member of which matches.

| Severity | Any one of                                                              |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue path affected (a request that takes or moves money or grants access: payment, checkout, refund, billing-document creation, auth - viewing a billing document is not one), >50% affected, or data loss risk |
| High     | 10-50% affected, or two or more services impacted                       |
| Medium   | User-facing but under 10% affected, single service, no data risk         |
| Low      | Not user-facing, and no data risk                                        |

**Thin evidence** (all three missing: metrics, deploy data, scope): assign severity from the worst reading the error class and affected surface support, and recommend containment by error class in Step 2. Whenever any of the three is missing - fully thin or not - identify the 3-5 evidence items that would raise confidence; the Output splits them between the hypothesis block's Remaining and `Evidence Needed`.

### Step 2 - Recommend Containment

Pick from this ladder by speed and safety. Prefer fast reversible actions; avoid patching under pressure.

1. **Resource recovery** - pause or kill an offending workload (batch job, runaway query, backfill); drain slow consumers; restart affected instances last within this rung, and only after capturing the pool counters, thread and heap state, and in-flight counts that Steps 3 to 5 read, because a restart destroys them and masks exhaustion rather than containing it
2. **Rollback** - if a recent deploy correlates. Rollback safety asks whether the OLD code tolerates the state the new code has already written, which is the reverse of the forward-compatibility question: a change can be backward compatible and still unsafe to revert once it has dual-written a new column or shipped a field consumers now read. Use skill: `ops-backward-compatibility` on the deployed change when a diff is available - a change it marks incompatible is unsafe to revert - and otherwise judge on whether the deploy has written state or exposed a contract that a revert would strand. Attach the reading as `rollback safe | unsafe - {reason} | unknown - verify {what} first`
3. **Feature flag disable** - surgical isolation; preferred when rollback is unsafe
4. **Circuit breaker** - stop cascading; critical when downstream latency exhausts upstream resources
5. **Traffic isolation / rate limit** - shed or route to degraded path
6. **Resize or scale** - raise pool, thread or instance limits only when resource exhaustion is confirmed and recovery alone is insufficient. Enlarging a pool against a slow downstream increases concurrent load on the failing dependency, so pair it with rung 4
7. **Hotfix** - only when rollback and flag-disable are unsafe, the leading hypothesis is supported by direct evidence at the failure point, and the diff is minimal with no schema/contract change
8. **Data repair** - if partial writes occurred

Recommend 1-3 containment actions, each with ETA in minutes. A state capture that precedes a restart or a redeploy is its own checkbox ahead of it and sits outside the cap, as data repair does. Rungs 1-4 are the fast reversible set: work from the top of it, and run rollback (when a deploy correlates) and circuit breaker (when downstream latency is the amplifier) concurrently. Reach rungs 5-7 only once the fast set is tried or ruled out, and say on the first action's line which rungs were ruled out and why. Rung 8 is not containment and sits outside the cap: list data repair separately whenever partial writes occurred, whatever contained the incident. When the cause is unknown on thin evidence, the default recommendation is the rung-1 action matching the error class - the non-destructive one, not a restart.

Use skill: `ops-resiliency` for circuit breaker / retry patterns.

### Step 3 - Classify and Assess Blast Radius

Use skill: `ops-failure-classification` to name the primary failure class; carry its `Failure Type`, `Layer` and `Scope` into the Summary, keeping any `(candidate)` marker, and fold its `Missing Evidence` line into Evidence Needed. Its `Scope` estimate is the affected percentage of requests - when Step 1 used the requests denominator and the figures disagree, re-run the severity table against it and say so on the Severity line; with a users denominator, carry both figures and re-run on neither. Use skill: `review-blast-radius` to score the dimensions and classify: Narrow | Moderate | Wide | Critical. It is written for prospective change impact, so read its dimensions against realized impact: "what the change would break" becomes "what this incident is breaking". Carry its two-state form, its `Mitigation:` line (which it emits only when a mitigation changes the level, tagged `in-place:` or `required:`) and its `Recoverable | Conditional | Irreversible` reversibility value into the Summary intact. Where it marks a dimension `(unverified)` - an unenumerable consumer set, or code it cannot see - append that marker to the level. Blast radius does not revise Severity - the two answer different questions. Use skill: `failure-propagation-analysis` when two or more components are involved - directly (service calling service) or via a shared resource (DB, queue, cache). A single service exhausting its own pool with no external participant does not qualify; that same pool starving because a slow downstream dependency holds connections does. Carry its shared-resource list into the Propagation line, and its loop-breaker too when it found a cycle, because Step 2's rungs 4 and 6 depend on both.

Also assess and record on the Contention and Contract Impact line: shared resource contention (DB, cache, queue, pools), API contract impact, data corruption risk.

Then load the domain skill matching the root failure type. It informs the mechanism in Step 4's hypotheses; it produces no section of its own:

| Root failure type                                                          | Domain skill                                       |
| -------------------------------------------------------------------------- | -------------------------------------------------- |
| Concurrency issue (genuine race/lock/deadlock)                             | `architecture-concurrency`                         |
| Transaction boundary error / partial writes                                | `architecture-data-consistency`                    |
| DB performance degradation, N+1                                            | `backend-db-indexing`                              |
| Resource exhaustion, resource contention, external dependency failure      | `ops-resiliency`                                   |
| Silent contract loss                                                       | `ops-backward-compatibility`                       |
| Other types (logic bug, misconfiguration, deploy drift, boundary violation) | none - proceed                                     |

Route on the MECHANISM, even when the classifier names the origin as the root type. A misconfiguration or deploy that caused resource exhaustion still routes to `ops-resiliency`, because that is where the containment patterns live; the classifier's root type stays on the Failure Type line. Pool exhaustion likewise routes by what starved the pool: a slow downstream holding connections is `ops-resiliency`; a lock-ordering deadlock, nested acquisition, or leak under a race is `architecture-concurrency`; a query slow enough to hold connections is `backend-db-indexing`. When several apply, take the one that explains the earliest signal.

### Step 4 - Generate Hypotheses

Use skill: `root-cause-hypothesis`. If a recent PR diff is provided, use skill: `review-pr-risk` first on the triggering change, and carry its `Risk Level` into the hypothesis's `Triggering change` line alongside the change itself. If propagation across services was observed in Step 3, the hypothesis must include the propagation path.

When signals conflict (deploy timestamp vs. degradation onset, region split vs. global change), or two causal directions fit the same evidence (the deploy overloaded the dependency vs. the dependency degraded independently), score both directions rather than settling on one, and make each `Verification` the single action that would separate them rather than one that merely supports its own hypothesis. Whether both reach the output is the sub-skill's normalization call: a rival that falls below its reporting floor is named in Remaining, which is the answer, not a gap.

### Step 5 - Observability Gaps

Use skill: `ops-observability`. For each gap: missing signal -> diagnostic question it could not answer -> concrete addition.

### Step 6 - Immediate Prevention Notes

Capture 1-3 items the on-call team can start within the next hour that prevent recurrence in the current incident window (e.g., shipping the per-attempt timeout, enabling the breaker flag). Each: addresses the failure class, has an ETA, states blast radius reduction. Longer-horizon prevention belongs in the team's own post-incident write-up - do not produce a guardrail/persistence table here.

## Output

Populate Summary fields as steps complete (blast radius arrives in Step 3); section order is presentation order, not execution order. Reproduce the `root-cause-hypothesis` output block verbatim; synthesize all other sub-skill outputs into the sections below rather than pasting their raw blocks. Omit empty sections, including `Evidence Needed` when evidence was sufficient.

```markdown
## Incident Summary

Failure Type: {the classifier's Failure Type list as emitted, root first} at {layer}{, or one "<class> at <layer> (candidate)" per candidate the classifier could not discriminate}{; mechanism: <class>, when Step 3 routed on a mechanism other than the root}, Scope: {Total | Partial N%} + {Isolated | Cascading}

Severity: {Low | Medium | High | Critical} - {the criterion that decided it, and the denominator used}{; re-run against classifier scope N%: <old> -> <new>}

Blast Radius: {Narrow | Moderate | Wide | Critical}{ (unverified)}{ (unmitigated) -> <level>, Mitigation: {in-place | required}: <the mitigation, as the sub-skill wrote it>}; reversibility {Recoverable | Conditional | Irreversible}

Onset: {timestamp | "~N min ago" | "unknown"} - {first hard error | first precursor anomaly, named}

Duration: {elapsed so far, or start to recovery | "unknown"}

Affected Services:

- {service}{ (external)}: {degraded (N%) | down | healthy}

Propagation: {origin -> affected, via <channel from the propagation analysis>; the shared resources on the path; the loop-breaker when a cycle was found; omit when single-service}

Contention and Contract Impact: {shared resources under contention, API contract impact, data corruption risk; "none identified" when clear}

Evidence Transport: {mcp | user-paste | unavailable | mixed} - {which capabilities came from where, and why any is unavailable; `mixed` is this skill's roll-up across blocks, not a block value}

## Immediate Containment

- [ ] {state capture before any restart or redeploy - pool counters, thread and heap state, in-flight counts; outside the cap; omit when nothing restarts}
- [ ] {action} (ETA {N} min, {expected impact}){; rollback safe | ; rollback unsafe - <reason> | ; rollback unknown - verify <what> first}{; rungs <n>-<n> ruled out - <reason>, on the first action when a rung 5-7 action is recommended}
- [ ] {action} (1-3 containment actions total)
- [ ] {data repair, listed whenever partial writes occurred, outside the containment cap}

## Root Cause Hypothesis

{root-cause-hypothesis output block, verbatim}

## Evidence Needed

- {missing evidence item + where to get it}

## Observability Gaps

| Missing Signal | Diagnosis Impact | Recommended Addition |
| -------------- | ---------------- | -------------------- |

## Immediate Prevention Notes

| Action | Failure Class Prevented | ETA | Blast Radius Reduction |
| ------ | ----------------------- | --- | ---------------------- |
```

Evidence Needed and the hypothesis block's Remaining together name 3-5 items whenever metrics, deploy data or scope was missing. The hypothesis block is reproduced verbatim, so add here only the items its Remaining does not name. Prevention Notes holds 1-3 startable-now items; full prevention belongs in the postmortem.

## Self-Check

- [ ] behavioral-principles loaded before Step 1
- [ ] Step 1: severity assigned with the deciding criterion named, highest matching row on ties, denominator stated; onset and duration given or marked unknown; affected services enumerated with individual status
- [ ] Step 1: evidence fetched where the trigger applied, and the Evidence Transport line states what was pasted, fetched, or unavailable
- [ ] Step 2: 1-3 containment actions with ETA appear before diagnosis; rollback carries its safety reading; any restart is preceded in the list by the capture action, which sits outside the cap
- [ ] Step 3: failure class, layer and scope named, with scope reconciled against the severity call; blast radius classified before any hypothesis, carrying its reversibility value and its mitigation line when one was emitted
- [ ] Step 3: the domain skill for the root failure type was loaded, or the row says none applies
- [ ] Step 3: propagation traced when two or more components are involved, carrying shared resources and the loop-breaker; contention and contract impact recorded
- [ ] Step 4: every hypothesis cites evidence and has a verification step; where two directions fit, each verification discriminates between them; triggering change identified if evidence exists
- [ ] Step 5: observability gaps each name the diagnostic question the missing signal could not answer
- [ ] Step 6: prevention notes limited to 1-3 startable-now items; guardrail/persistence deferred to postmortem
- [ ] Missing signals (metrics/deploys/scope): Evidence Needed plus Remaining name 3-5 items, none duplicated
- [ ] Empty sections omitted

## Avoid

- Treating symptoms as root causes
- Hypotheses without evidence or verification
- Running a full governance review while the incident is active
- Verbose explanations under incident pressure
