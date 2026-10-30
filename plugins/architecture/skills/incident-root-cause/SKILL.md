---
name: incident-root-cause
description: Active incident root cause analysis with containment-first triage, blast radius assessment, and ranked hypotheses for service degradation.
metadata:
  category: ops
  tags: [incident, root-cause, on-call, reliability, containment]
user-invocable: false
---

> Runs under the calling workflow's `behavioral-principles` load (its Step 1); it does not load it again. Stack context likewise comes from the calling workflow's `stack-detect` - if absent, proceed stack-agnostic.

# Incident Root Cause Analysis

## When to Use

Active production incident, on-call triage, cascading failure diagnosis.

Where the evidence already shows a mitigation applied and the symptom subsiding, the incident is contained but not closed: give Duration as the elapsed outage, and let Immediate Containment carry only what is still outstanding - verifying the mitigation holds, reverting a temporary setting, and any data repair - rather than re-recommending what has already been done.

## Inputs

Required: error or stack trace, OR a Sentry/Datadog/monitor URL. Optional: log snippets, recent PR diff, metrics summary, config snapshot, deploy metadata, service map.

## Workflow

### Step 1 - Frame the Incident (60 seconds)

Use skill: `ops-observability-fetch` when inputs include a URL or ID, or when any of onset, affected scope, or deploy correlation is missing from the paste. Always request `metric_series` and `deploy_event`; request `error_event` only when the input carries an issue ID or URL and `monitor_state` only when it carries a monitor ID or URL, since an unanchored block comes back as a question and costs a round trip mid-incident. For `metric_series` name the project's actual metric names for error rate and latency - with no name known, let that block ask rather than inventing one; window is onset minus 60 min to now, or the last 60 min when onset is unknown. For `deploy_event`, ask for the last 48h on the affected service and any implicated downstream service. Whatever comes back unavailable, record on the Evidence Transport line and proceed on the paste alone. A monitor or error block feeds Severity, Onset and Affected Services; no block is pasted into the output.

Extract: symptom onset (timestamp, or relative like "~40 min ago"), duration, affected services with status (degraded/down/healthy), and the affected percentage. Then assign severity.

Percentages are of requests, of users, or of another unit the evidence gives (jobs, SKUs, page views); use one denominator throughout and name it in the output. Critical and High match on any one criterion in their row; Medium and Low require every condition in theirs. Take the highest row that matches. When the affected percentage is unknown, a percentage criterion is unmet for Critical and High and met for Medium; name `percentage unknown` as the denominator.

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Any of: revenue path affected (a request that takes or moves money or grants access: payment, checkout, refund, billing-document creation, auth - viewing a billing document is not one), >50% affected, data loss or corruption risk |
| High     | Any of: 10-50% affected, two or more services impacted                  |
| Medium   | All of: user-facing, under 10% affected, single service, no data loss or corruption risk |
| Low      | All of: not user-facing, no data loss or corruption risk                 |

**Thin evidence** (all three missing: metrics, deploy data, scope): assign severity from the worst reading the error class and affected surface support, and recommend containment by error class in Step 2. Whenever any of the three is missing - fully thin or not - identify the 3-5 evidence items that would raise confidence; the Output splits them between the hypothesis block's Remaining and `Evidence Needed`.

### Step 2 - Recommend Containment

Pick from this ladder by speed and safety. Prefer fast reversible actions; avoid patching under pressure.

1. **Resource recovery** - pause or kill an offending workload (batch job, runaway query, backfill); drain slow consumers; restart affected instances last within this rung, and only after capturing the pool counters, thread and heap state, and in-flight counts that Steps 3 to 5 read, because a restart destroys them and masks exhaustion rather than containing it
2. **Rollback** - if a recent deploy or config change correlates; the safety reading below applies to reverting that change. Rollback safety is the forward-compatibility question - whether the OLD code tolerates the state the new code has already written - the reverse of the backward-compatibility question: a change can be backward compatible and still unsafe to revert once it has dual-written a new column or shipped a field consumers now read. Use skill: `ops-backward-compatibility` on the deployed change when a diff is available: a `db` row it marks `No` or `No (unverified)` whose migration has already run is unsafe to revert; every other row - `in`, `out`, and a `db` row marked `Yes` or whose migration has not run - is judged on whether the deploy has written state or exposed a contract a revert would strand, as is the whole change when no diff is available. Attach the reading as `rollback safe | unsafe - {reason} | unknown - verify {what} first`
3. **Feature flag disable** - surgical isolation; preferred when rollback is unsafe
4. **Circuit breaker** - stop cascading; critical when downstream latency exhausts upstream resources. Use skill: `ops-resiliency` for circuit breaker / retry patterns
5. **Traffic isolation / rate limit** - shed or route to degraded path
6. **Resize or scale** - raise pool, thread or instance limits only when resource exhaustion is confirmed and recovery alone is insufficient. Enlarging a pool against a slow downstream increases concurrent load on the failing dependency, so pair it with rung 4
7. **Hotfix** - only when rollback and flag-disable are unsafe, the leading Step 4 hypothesis is supported by direct evidence at the failure point, and the diff is minimal with no schema/contract change; added after Step 4, never in the first pass
8. **Data repair** - if partial writes occurred

Recommend 1-3 containment actions, each with ETA in minutes. A state capture that precedes a restart or a redeploy (a rollback that redeploys or restarts is one) is its own checkbox ahead of it and sits outside the cap, as data repair does. Rungs 1-4 are the fast reversible set: work from the top of it, and run rollback (when a deploy or config change correlates) and circuit breaker (when downstream latency is the amplifier) concurrently. Reach rungs 5-7 only once the fast set is tried or ruled out, and say on the first action's line which rungs were ruled out and why. Rung 8 is not containment and sits outside the cap: list data repair separately whenever partial writes occurred, whatever contained the incident. When the cause is unknown on thin evidence, the default recommendation is the rung-1 action matching the error class - the non-destructive one, not a restart. After Step 3, revise any rung 4 or rung 6 action against its shared-resource list and loop-breaker, and add the loop-breaker as an action when nothing here already breaks the cycle, replacing the lowest-ranked action when three are already listed; a rung-5 loop-breaker carries the ruled-out note. A rung-7 hotfix is added after Step 4 on the same replacement terms.

### Step 3 - Classify and Assess Blast Radius

Use skill: `ops-failure-classification` to name the primary failure class; carry its `Failure Type`, `Layer` and `Scope` into the Summary, keeping any `(candidate)` marker. Its `Layer` is the root type's layer only. When it emits more than one block (concurrent independent failures), write one Failure Type line per block, prefixed with the block's failure identifier, primary incident first. Fold its `Missing Evidence` line into Evidence Needed as one of the 3-5 items, merged with any item naming the same evidence; when evidence was otherwise sufficient, it alone populates that section. Its `Scope` is a share of requests: re-run the severity table against it only when Scope is `Total`, `Partial X%` or `Partial ~X%` and Step 1 used the requests denominator, saying so on the Severity line; with a users denominator or another unit, carry a numeric classifier Scope (`Total` as 100%) on the Severity line without re-running; with `percentage unknown`, re-run against a numeric classifier Scope and name `requests` as the denominator from then on, saying so on the Severity line; for `Absent`, `Partial (unquantified)` or an aggregate, under any denominator, keep the Step 1 severity and carry nothing.

Use skill: `review-blast-radius` to score the dimensions and classify: Narrow | Moderate | Wide | Critical. It is written for prospective change impact, so read its dimensions against realized impact: "what the change would break" becomes "what this incident is breaking". Carry its overall line as written - contract-break parenthetical and two-state form included - appending ` (unverified)` after each level (both levels in the two-state form) when any dimension line it emits carries that marker; carry its Reversibility value as written, two-state form included, with the rationale's `(unverified)` on the value; and its `Mitigation:` line as written, every tagged item with the leading tag first - while that leading tag is `required:`, list the required action as a containment action, replacing the lowest-ranked when three are already listed, and read the level as the unmitigated one. Its per-dimension lines are not reproduced. Blast radius does not revise Severity - the two answer different questions.

Use skill: `failure-propagation-analysis` when two or more components are involved - directly (service calling service) or via a shared resource (DB, queue, cache). A single service exhausting its own pool with no external participant does not qualify; that same pool starving because a slow downstream dependency holds connections does. Carry its path hop by hop, its shared-resource list and its loop-breaker into the Propagation line.

Also assess and record on the Contention and Contract Impact line: shared resource contention (DB, cache, queue, pools), API contract impact, data corruption risk.

Then load the domain skill matching the failure mechanism - the root failure type unless the routing rule below names another. It informs the mechanism in Step 4's hypotheses; it produces no section of its own:

| Failure mechanism (root type unless routed otherwise)                      | Domain skill                                       |
| -------------------------------------------------------------------------- | -------------------------------------------------- |
| Concurrency issue (genuine race/lock/deadlock)                             | `architecture-concurrency`                         |
| Transaction boundary error / partial writes                                | `architecture-data-consistency`                    |
| DB performance degradation, N+1 / query overload                           | `backend-db-indexing`                              |
| Resource exhaustion, Resource contention / noisy neighbor, External dependency failure | `ops-resiliency`                       |
| Silent contract loss                                                       | `ops-backward-compatibility`                       |
| Other types (logic bug, misconfiguration, deploy drift, boundary violation, Infrastructure failure) | none - proceed            |

Route on the MECHANISM, even when the classifier names the origin as the root type. A misconfiguration or deploy that caused resource exhaustion still routes to `ops-resiliency`, because that is where the containment patterns live; the classifier's root type stays on the Failure Type line. Pool exhaustion likewise routes by what starved the pool: a slow downstream holding connections is `ops-resiliency`; a lock-ordering deadlock, nested acquisition, or leak under a race is `architecture-concurrency`; a query slow enough to hold connections is `backend-db-indexing`. When several apply, take the one that explains the earliest signal.

### Step 4 - Generate Hypotheses

Use skill: `root-cause-hypothesis`. If a recent PR diff is provided, use skill: `review-pr-risk` first on the triggering change, and carry its `Risk Level` into the hypothesis's `Triggering change` line alongside the change itself. If propagation across services was observed in Step 3, the primary hypothesis's `Mechanism` field traces the propagation path; with no scored candidate, Remaining's first clause names it.

When signals conflict (deploy timestamp vs. degradation onset, region split vs. global change), or two causal directions fit the same evidence (the deploy overloaded the dependency vs. the dependency degraded independently), consider both directions, scoring each that has a signal on its own distinguishing claim, and make each `Verification` the single action that would separate them rather than one that merely supports its own hypothesis. A direction with no such signal is named unscored in Remaining; one below the reporting floor is named there with its raw score - either is the answer, not a gap.

### Step 5 - Observability Gaps

Use skill: `ops-observability`. For each gap: missing signal -> diagnostic question it could not answer -> concrete addition.

### Step 6 - Immediate Prevention Notes

Capture 1-3 items the on-call team can start within the next hour that prevent recurrence in the current incident window (e.g., shipping the per-attempt timeout, enabling the breaker flag). Each: addresses the failure class, has an ETA, states blast radius reduction. Longer-horizon prevention belongs in the team's own post-incident write-up - do not produce a guardrail/persistence table here.

## Output

Populate Summary fields as steps complete (blast radius arrives in Step 3); section order is presentation order, not execution order. Reproduce the `root-cause-hypothesis` output block verbatim; synthesize all other sub-skill outputs into the sections below rather than pasting their raw blocks. Omit empty sections, including `Evidence Needed` when evidence was sufficient. Conditional parts: the failure-identifier prefix only when the classifier emitted more than one block; `; mechanism:` only when Step 3 routed on a mechanism other than the root; Propagation only when two or more components are involved; the state-capture checkbox only when an action restarts or redeploys; the ruled-out note on the first containment action (the capture is not one) only when a rung 5-7 action is recommended; the data-repair checkbox only when partial writes occurred - capture and data repair sit outside the 1-3 cap, and a verification or retry of an action listed here is written on that action's line, never as its own checkbox; verifying a mitigation applied before this report is its own action. Affected Services carries status at the time of writing, with the in-window state in parentheses when they differ.

```markdown
## Incident Summary

Failure Type: {<failure identifier>: }{root type} at {layer}{, then trigger and symptom types as the classifier listed them}{, or one "<class> at <layer> (candidate)" per root-position candidate}{; mechanism: <class>}, Scope: {Total | Partial X% | Partial ~X% | Partial (unquantified) | Partial X% aggregate, not split | Absent} + {Isolated | Cascading (<propagation path>)}

Severity: {Low | Medium | High | Critical} - {the criterion that decided it, and the denominator used}{; re-run against classifier scope N%: <old> -> <new> | ; re-run against classifier scope N%, denominator now requests: <old> -> <new> | ; classifier scope N% of requests, not re-run (<denominator> denominator)}

Blast Radius: {the sub-skill's Blast Radius value after its label, contract-break parenthetical and two-state form included, " (unverified)" after each flagged level}{; Mitigation: <the sub-skill's Mitigation line as written, every tagged item, leading tag first>}; reversibility {the sub-skill's Reversibility value as written, two-state form included}{ (unverified)}

Onset: {timestamp | "~N min ago" | "unknown"} - {first hard error | first precursor anomaly, named}

Duration: {elapsed so far, or start to recovery | "unknown"}

Affected Services:

- {service}{ (external)}: {degraded (N%) | down | healthy}{ (in window: <state>)}

Propagation: {origin -> <channel>: <component> -> <channel>: <component> ..., one channel per hop with its (unverified) or (response action) marker; fan-out and configuration-decided branches as "; branch <Na>: ..." segments keeping "(branch Nb only)"; a cycle as "-> loops to <component>"; the shared resources on the path with their size and markers; the loop-breaker when a cycle was found}

Contention and Contract Impact: {shared resources under contention, API contract impact, data corruption risk; "none identified" when clear}

Evidence Transport: {mcp | user-paste | unavailable | mixed} - {which capabilities came from where, and why any is unavailable; `mixed` is this skill's roll-up across blocks, not a block value}

## Immediate Containment

- [ ] {state capture before any restart or redeploy - pool counters, thread and heap state, in-flight counts}
- [ ] {action} (ETA {N} min, {expected impact}){; then <verification or retry>}{; rollback safe | ; rollback unsafe - <reason> | ; rollback unknown - verify <what> first}{; rungs <list> ruled out - <reason>}
- [ ] {action} (ETA {N} min, {expected impact}){; then <verification or retry>}
- [ ] {data repair}

## Root Cause Hypothesis

{root-cause-hypothesis output block, verbatim}

## Evidence Needed

- {missing evidence item + where to get it}

## Observability Gaps

| Missing Signal | Diagnostic Question Unanswered | Recommended Addition |
| -------------- | ------------------------------ | -------------------- |

## Immediate Prevention Notes

| Action | Failure Class Prevented | ETA | Blast Radius Reduction |
| ------ | ----------------------- | --- | ---------------------- |
```

Evidence Needed and the hypothesis block's Remaining together name 3-5 items whenever metrics, deploy data or scope was missing. The hypothesis block is reproduced verbatim, so add here only the items its Remaining does not name. Prevention Notes holds 1-3 startable-now items; full prevention belongs in the postmortem.

## Self-Check

- [ ] Step 1: severity assigned with the deciding criterion named, highest matching row, denominator stated; onset and duration given or marked unknown; affected services enumerated with individual status
- [ ] Step 1: evidence fetched where the trigger applied, and the Evidence Transport line states what was pasted, fetched, or unavailable
- [ ] Step 2: 1-3 containment actions with ETA appear before diagnosis; rollback carries its safety reading; any restart or redeploy, a redeploying rollback included, is preceded in the list by the capture action, which sits outside the cap
- [ ] Step 3: failure class, layer and scope named, with scope reconciled against the severity call; blast radius classified before any hypothesis, carrying its reversibility value and its mitigation line when one was emitted
- [ ] Step 3: the domain skill for the routed mechanism (the root failure type unless Step 3 routed on another) was loaded, or the row says none applies
- [ ] Step 3: propagation traced when two or more components are involved, carrying shared resources and the loop-breaker, and rung 4/6 actions revised against them; contention and contract impact recorded
- [ ] Step 4: every hypothesis cites evidence and has a verification step; where two directions fit, each verification discriminates between them; triggering change identified if evidence exists; the primary Mechanism, or Remaining's first clause with no scored candidate, traces the propagation path when one was found
- [ ] Step 5: observability gaps each name the diagnostic question the missing signal could not answer
- [ ] Step 6: prevention notes limited to 1-3 startable-now items; guardrail/persistence deferred to postmortem
- [ ] Missing signals (metrics/deploys/scope): Evidence Needed plus Remaining name 3-5 items, none duplicated
- [ ] Empty sections omitted

## Avoid

- Running a full governance review while the incident is active
- Verbose explanations under incident pressure
