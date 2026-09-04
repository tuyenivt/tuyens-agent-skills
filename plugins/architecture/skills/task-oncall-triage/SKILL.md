---
name: task-oncall-triage
description: Triage an oncall alert, ticket, or symptom: fast provisional first look on work type and severity, then a subagent deep pass drives the root cause.
agent: oncall-responder
metadata:
  category: ops
  tags: [oncall, triage, incident, investigation, alert, routing]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Oncall Triage

An alert, ticket, stack trace, or symptom just landed: classify it, then drive it to a cause.

Two phases. **Phase 1 - First Look** classifies on hydrated evidence alone, inside one fetch pass, and is on screen before anything else - it is what the responder acts on. **Phase 2 - Deep Pass** runs the routed workflow in a subagent and may overturn any Phase 1 field.

## When to Use

- An alert, ticket, stack trace, or user report needs classifying and driving to a cause
- An active production incident, even when the impact is self-evident - Critical/High carries containment in the First Look rather than waiting on the deep pass
- A resolved incident, when the question is why it happened

**Not for:**

- Designing the system so a failure class cannot recur - hand off to `architecture-architect`, which gates redesign on a confirmed root cause; run this workflow first when there is none
- The post-incident write-up - that follows the company own format; supply the confirmed root cause, blast radius, and timeline as its input
- A forward-looking upgrade assessment or task breakdown - hand off to `architecture-planner`

---

## Phase 1 - First Look

**Budget:** one `ops-observability-fetch` invocation, no source code read, no database query, no reproduction attempt, no waiting on a paste. Evidence the project keeps in the repo as data files - the deploy log, monitor definitions, runbooks, and postmortems that `CLAUDE.md` `## Observability` names - is evidence, not code: read it inside the fetch pass and cite the path. Anything executable or imported (schedules, settings modules, environment files) is code and waits for the deep pass. A file the session cannot read is an unavailable block after one attempt - no workaround; the deep pass tries once more. Blocks that come back unavailable stay unavailable and are named in the output.

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Hydrate Evidence

Use skill: `ops-observability-fetch`. Request exactly these blocks - the fetch skill emits each one, unavailable when it cannot be fetched:

- `error_event` per recognized issue URL or ID; `monitor_state` per recognized monitor URL or ID; `metric_series` for each recognized monitor's underlying metric (window: earliest known onset minus 60 min to now) - it tells whether the symptom is ongoing
- `deploy_event` via `list_deploys` for every service that ships the affected code path, unless the input already carries a dated change record: a deploy, PR, or release with its timestamp. A release tag alone names what is running, not when it shipped, and a negative or unverified claim ("nothing deployed as far as I know") is not a record - pull. Window: 48h, or from 24h before the earliest known onset when that is older
- `log_window` and `trace` only when the input anchors them (a log-search or trace URL)

Fetch every recognized URL even when paste content accompanies it - never classify on a URL alone. Pure paste (PagerDuty title, Slack message, stack trace - no URL or ID): the paste is normalized as its block type (`Source: user-paste`), `deploy_event` is still pulled, and no other block is requested.

The blocks feed Step 3, the Context Package, and the Step 7 subagent prompt, where they are pasted verbatim. Neither the stack-detect output nor the raw blocks are shown to the user - the Evidence line summarizes them.

### Step 3 - Classify Work Type

Take the first matching row top-down.

| Type                       | Signals                                                                                                        | Deep pass                                       |
| -------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **Active incident**        | Ongoing multi-user impact (threshold below): error rate spike, service down, SLA breach, data loss across users | `incident-root-cause`                           |
| **Code bug**               | Stack trace, test failure, crash, reproducible error - without ongoing multi-user impact                       | `oncall-investigate` at Critical/High; none at Medium/Low - terminal at Phase 1 (repro + handoff) |
| **Alert investigation**    | Alert fired, unclear if real or false positive                                                                 | `oncall-investigate`                            |
| **Performance**            | Slow response, high latency, timeout (no outage)                                                               | `oncall-investigate` or `task-code-review-perf` |
| **User / support request** | Single user issue, access problem, data question                                                               | `oncall-investigate`                            |
| **Operational issue**      | Batch missed, queue backed up, "why did X happen?"                                                             | `oncall-investigate`                            |

"Ongoing multi-user impact" is the `oncall-investigate` escalation rule, kept in sync: 3 or more distinct users within an hour, or error rate on the affected path >2x baseline, or a revenue/auth/data-integrity path with confirmed multi-user impact or active error-rate elevation. Below it, an error in production is a Code bug or Operational issue, not an incident, whatever path it sits on.

When the user asks what type this is ("is this an incident?"), classify and answer on the Basis line - do not ask back; "can it wait?" is answered there by Severity: Critical/High cannot, Medium/Low can. When a threshold input is unknowable from the evidence (baseline unknown, revenue-path status of the feature unclear), state the assumption on the Basis line and classify under it.

### Step 4 - Severity

Mirrors `incident-root-cause` Step 1 - keep in sync:

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue-impacting (payment, checkout, billing, or auth path), >50% requests affected, or data loss risk |
| High     | User-facing degradation, 10-50% affected, or multiple services impacted |
| Medium   | Partial degradation <10%, single service, no data risk                  |
| Low      | Non-user-facing, minimal impact                                         |

When criteria from multiple rows match, take the highest row. Below the Step 3 threshold the percentage, degradation, and multi-service criteria cannot match: a revenue/auth path or data-loss risk is Critical whatever the breadth; otherwise Medium when the affected path is one users interact with directly (request, page, notification), Low when it is not (job, queue, alert-only). For Critical/High: no further work-type refinement - Steps 5-6 still run in one fast pass, and Step 5 feeds the rollback item in Immediate Action.

### Step 5 - Scope Check

- Ongoing impact -> raise severity one level (data-loss risk is already Critical in Step 4)
- Recent change -> a `deploy_event` inside the window that touches the affected service or its config; its timestamp is the Recent change value, and rollback is usually the fastest containment (the item itself lands in Immediate Action)
- Happened before -> Sentry `first_seen` on the hydrated issue answers it; a runbook or prior postmortem the repo keeps (Budget) is cited by path, or "none found"

### Step 6 - Emit the First Look

Emit the First Look block now, before anything else is shown and before Phase 2 starts. The Status line marks the whole block: `Provisional` means every classified field is provisional and the Deep Pass section names what could overturn it; `Final` means no deep pass runs, and what is unknown is written as unknown, not provisional.

**Terminal at Phase 1** - only at Medium/Low; at Critical/High the deep pass always runs (a Code bug there runs `oncall-investigate` to settle exposure and data integrity, the fix still belonging to the owning engineer). `Status: Final`, the Deep Pass line records `Not run` with the terminal reason, and the workflow ends:

- Code bug - derive the repro condition from the evidence into the Context Package `Repro` and `Owner` slots and hand off; the fix belongs to the owning engineer
- The user asked for the classification itself ("is this an incident?") - the Recommended Workflow line names what runs on their go-ahead

When both apply, it is the Code bug variant.

---

## Phase 2 - Deep Pass

### Step 7 - Spawn the Deep Pass

**Routing is execution, not advice.** The routed skills are not user-invocable: spawn one subagent that runs the routed skill on the Context Package, as the **declared subagent** below - do not infer it from the work type.

| Work Type                          | Deep pass skill                                                                                                                         | Subagent (`subagent_type`) |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| Active incident                    | `incident-root-cause`                                                                                                                   | `oncall-responder`         |
| Code bug (Critical/High)           | `oncall-investigate` - exposure and data integrity; the fix stays with the owning engineer                                              | `oncall-responder`         |
| Operational / User request / Alert | `oncall-investigate`                                                                                                                    | `oncall-responder`         |
| Performance                        | `task-code-review-perf` when code or a recent change is the suspect; `oncall-investigate` when the ask is to diagnose the running system | `oncall-responder`         |

**Subagent availability**, keyed to what the Agent tool reports. Declared type registered -> use it. Declared type not registered -> spawn `general-purpose` with the `oncall-responder` agent body inlined as its role, and record the stand-in on the Deep Pass line. No subagent can be spawned at all -> run the routed skill inline under the same contract and record `inline`. `Deep Pass: failed` is reserved for a spawn that ran and did not return.

**Subagent prompt contract** - each must include:

- The statement that it is running as the deep pass of `task-oncall-triage`. Behavioral principles and `stack-detect` are already confirmed by the parent: the subagent re-runs neither and spawns no subagent of its own.
- The original alert, ticket, or paste text verbatim
- Every evidence block Phase 1 fetched, verbatim, so the deep pass re-fetches only what came back unavailable
- The provisional Work Type, Severity, and Ongoing read, labelled provisional, plus the instruction to re-derive each from evidence and report the delta - a confirmation the deep pass did not earn is worth nothing
- The pre-detected stack and the full Context Package
- Authorization to read the codebase, run read-only queries against the systems it can reach, and fetch the evidence Phase 1 left unavailable
- The return contract: the routed skill's Output block; then `## Changes from First Look` with one line per First Look field (Work Type, Severity, Ongoing, Symptom, Time window, Affected scope, Recent change, Prior occurrence) in the form `- {Field}: {First Look value} -> {confirmed | new value | unverified} - {the evidence that settled it, or what would}`, a new value inferred rather than observed marked `(unverified)`; then, when the First Look carried Immediate Action, `## Immediate Action check` with one line per item: `- {item}: {holds | still holds - narrowed to {what} | no longer needed - {why} | harmful - {why}; do {this} instead}`

While the subagent runs, the main thread stays on the First Look: answer follow-up questions from it, and say which fields are still provisional; with none, wait - no code reading, no re-fetching.

**Failure isolation:** if the subagent fails or times out, the First Look stands - report `Deep Pass: failed` and name what stayed unverified.

### Step 8 - Reconcile and Report

Project the subagent's Changes list into the Updated Assessment, one row per First Look field, and its Immediate Action check into the Acted-On Warning. This is reconciliation, not re-investigation: the Basis column carries the deep pass's evidence, and the main thread reads no code. A field the deep pass could not settle is reported as unverified, never as confirmed.

---

## Output Format

Two blocks in the same session: the First Look at the end of Step 6, the Updated Assessment at the end of Step 8. Nothing precedes the First Look.

```markdown
## Oncall First Look

Status: {Provisional - deep pass running | Final - Code bug, repro handed off | Final - classification-only request}

Work Type: {Active incident | Code bug | Alert | Performance | User request | Operational}

Severity: {Critical | High | Medium | Low}

Ongoing: {Yes | No | Unknown} - {the fetched signal or the user's timestamped statement that decides it; neither -> Unknown}

Basis: {the Step 3 threshold read - distinct users per hour, error rate vs baseline, path class - and the Step 4 row; assumptions named}

### Recommended Workflow
Use: {incident-root-cause | oncall-investigate | task-code-review-perf | code-fix handoff (repro + owning engineer)}

### Context Package
- Symptom: {one sentence}
- Time window: {onset and last seen; "unknown" when not in evidence}
- Affected scope: {who/what is impacted}
- Recent change: {deploy/config/flag with timestamp | None found in {source, window} | Unverified - {why the deploy history was unreachable}}
- Prior occurrence: {first_seen or earlier firings, and the runbook or postmortem path | none found | unknown}
- Repro: {the condition that reproduces it, from the evidence} (Code bug only)
- Owner: {team or person from CODEOWNERS or the project's service map | the owning service when no person or team is recorded} (Code bug only)
- Evidence: (one nested bullet per block)
  - {"{block type}: {key value}" when fetched, pasted, or read from a repo file (name the source); "{block type}: paste pending - {the block's Paste prompt}" when unavailable; "{block type}: {what the paste or repo file gave} - paste pending for {missing fields}" when partly satisfied}

### Immediate Action
(omit this entire section, heading included, unless Critical/High)
- [ ] {1-3 items: rollback of the Step 5 change when one correlates; when Recent change is Unverified, get the deploy record first and roll back if it correlates; else the fastest reversible containment the evidence supports; the data-integrity check when writes may have partially landed; below the Step 3 threshold, the tripwire that turns this into an Active incident}

### Deep Pass
- {Running {deep pass skill} as `oncall-responder` | Running {deep pass skill} as `general-purpose` standing in for `oncall-responder` | Running {deep pass skill} inline - no subagent available | Not run - {terminal reason}}
- Could overturn: {2-3 specific items - a threshold assumed without a baseline, a block that came back unavailable, a code path not yet read} (omit this line when the deep pass is not run)
```

```markdown
## Updated Assessment

Deep Pass: {complete | failed - First Look stands | timed out - First Look stands}

Do now: {the first action from the routed block's containment or recommended actions | none - First Look actions stand}

### Changes from First Look
| Field | First Look | After deep pass | Basis |
| ----- | ---------- | --------------- | ----- |
| {one row per First Look field, in block order} | {provisional value} | {confirmed | new value | new value (unverified) | unverified} | {the evidence that settled it, or what would} |

### Acted-On Warning
(omit this entire section, heading included, unless Severity, Work Type, or an Immediate Action item changed)
- {First Look action}: {now supported by {evidence} | still holds - narrowed to {what} | no longer needed - {why} | harmful - {why}; do {this} instead}

{routed workflow output block, verbatim}
```

## Self-Check

- [ ] behavioral-principles loaded before any step
- [ ] Step 1: stack detected
- [ ] Step 2: every recognized URL fetched; deploys pulled unless a dated change record was in the input, window covering onset; repo-kept evidence read and cited by path; no paste waited on
- [ ] Step 3: first matching row top-down on hydrated evidence; Basis line carries the threshold read and any assumption
- [ ] Step 4: highest matching row, below-threshold reading applied; Critical/High carries Immediate Action
- [ ] Step 5: ongoing impact, recent change, and prior occurrence recorded in the Context Package
- [ ] Step 6: First Look on screen before anything else and before Phase 2; Status line states Provisional, or Final with the terminal reason (Medium/Low only)
- [ ] Step 7: deep pass spawned as the declared subagent, or the stand-in / inline fallback recorded, carrying the evidence blocks, the provisional read, the re-derive instruction, and the return contract - or the terminal case recorded with its reason
- [ ] Step 8: one row per First Look field projected from the deep pass's Changes list; Do now filled; a changed Severity, Work Type, or Immediate Action item carries an Acted-On Warning projected from the Immediate Action check

## Avoid

- Starting the deep pass, or showing stack-detect output or raw evidence blocks, before the First Look block is on screen - the fast answer is the point of the split
- Running the deep pass inline when a subagent can be spawned - the main thread has to stay free for follow-up questions
- Handing the deep pass the provisional classification as settled fact, or accepting a confirmation it did not re-derive
- Spending First Look time refining a Critical/High work type before containment lands in Immediate Action
- Re-classifying when the user has already stated the work type - route directly
- Calling production errors "incidents" below the multi-user threshold - route them as bugs or operational work
