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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. Delegated skills supply analysis method, not structure: this skill's Output Format is the only output contract - absorb their findings into its slots and never emit their own Output blocks. The one exception is the routed deep-pass block, which Step 8 appends verbatim.

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

**Budget:** one `ops-observability-fetch` invocation, no source code read, no database query, no reproduction attempt, no waiting on a paste. Evidence the project keeps in the repo as data files - deploy logs, monitor definitions, runbooks, postmortems, evidence bundles, and the ownership records (`CODEOWNERS`, a service map) the Context Package's Owner slot needs - is evidence, not code: read it inside the fetch pass and cite the path. Where `CLAUDE.md` carries an `## Observability` section, use it to choose between transports, not as the list of what may be read. Anything executable or imported (schedules, settings modules, environment files) is code and waits for the deep pass. A file the session cannot read is an unavailable block after one attempt - no workaround; the deep pass tries once more. Blocks that come back unavailable stay unavailable and are named in the output.

### Step 1 - Detect Stack

Use skill: `stack-detect`

### Step 2 - Hydrate Evidence

Use skill: `ops-observability-fetch`. Request exactly these blocks - the fetch skill emits each one, unavailable when it cannot be fetched:

- `error_event` per recognized issue URL or ID; `monitor_state` per recognized monitor URL or ID; `metric_series` for each recognized monitor's underlying metric, named from that monitor's threshold expression once `monitor_state` returns; where no name resolves, the block comes back `Needs: metric name` and that is what the Evidence line records. Window: earliest known onset minus 60 min to now, or the last 60 min when onset is unknown - it tells whether the symptom is ongoing
- `deploy_event` via `list_deploys` for every service that ships the affected code path, unless the input already carries a dated change record: a deploy, PR, or release with its timestamp. A release tag alone names what is running, not when it shipped, and a negative or unverified claim ("nothing deployed as far as I know") is not a record - pull. Window: 48h, or from 24h before the earliest known onset when that is older
- `log_window` and `trace` when the input anchors them (a log-search or trace URL), or when the project keeps them as repo data files the Budget allows reading - an evidence bundle counts, and its files are cited by path

Fetch every recognized URL even when paste content accompanies it - never classify on a URL alone. Pure paste (PagerDuty title, Slack message, stack trace - no URL or ID): request `deploy_event` and nothing else. Paste whose content matches a block's shape is normalized into that block with `Source: user-paste`. Paste matching none of the six - a support thread, a chat exchange, a ticket - is not a block: it goes on the Evidence line as `narrative: {source}` with what it establishes, and is never forced into a block type.

The blocks feed Step 3, the Context Package, and the Step 7 subagent prompt, where they are pasted verbatim. Neither the stack-detect output nor the raw blocks are shown to the user - the Evidence line summarizes them.

### Step 3 - Classify Work Type

Take the first matching row top-down.

| Type                       | Signals                                                                                                        | Deep pass                                       |
| -------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **Active incident**        | Ongoing multi-user impact (threshold below): error rate spike, service down, SLA breach, data loss across users | `incident-root-cause`                           |
| **Code bug**               | Stack trace, test failure, crash, reproducible error - without ongoing multi-user impact                       | `oncall-investigate` at Critical/High; none at Medium/Low - terminal at Phase 1 (repro + handoff) |
| **Alert**                  | Alert fired, unclear if real or false positive                                                                 | `oncall-investigate`                            |
| **Performance**            | Slow response, high latency, timeout (no outage)                                                               | `oncall-investigate` or `task-code-review-perf` |
| **User request**           | Single user issue, access problem, data question                                                               | `oncall-investigate`                            |
| **Operational**            | Batch missed, queue backed up, "why did X happen?"                                                             | `oncall-investigate`                            |

"Ongoing multi-user impact" is the `oncall-investigate` escalation rule, kept in sync: 3 or more distinct users within an hour; or error rate on the affected path more than 2x baseline **and** more than 10 errors in that hour, so a handful of errors on a quiet path does not qualify; or a revenue/auth/data-integrity path with confirmed multi-user impact or active error-rate elevation. Below it, an error in production is a Code bug or Operational work, not an incident, whatever path it sits on.

When the user asks what type this is ("is this an incident?"), classify and answer on the Basis line - do not ask back; "can it wait?" is answered there by Severity: Critical/High cannot, Medium/Low can. When a threshold input is unknowable from the evidence (baseline unknown, revenue-path status of the feature unclear), state the assumption on the Basis line and classify under it.

### Step 4 - Severity

Mirrors `incident-root-cause` Step 1 - keep in sync:

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue path affected (payment, checkout, billing, auth), >50% affected, or data loss risk |
| High     | 10-50% affected, or two or more services impacted                       |
| Medium   | User-facing but under 10% affected, single service, no data risk        |
| Low      | Not user-facing, and no data risk                                       |

Percentages are of requests or of users, whichever the evidence gives; use one denominator throughout and name it on the Basis line. When criteria from multiple rows match, take the highest row. Below the Step 3 threshold the percentage, degradation, and multi-service criteria cannot match: a revenue/auth path or data-loss risk is Critical whatever the breadth; otherwise Medium when the affected path is one users interact with directly (request, page, notification), Low when it is not (job, queue, alert-only). For Critical/High: no further work-type refinement - Steps 5-6 still run in one fast pass, and Step 5 feeds the rollback item in Immediate Action.

### Step 5 - Scope Check

- Ongoing impact is already priced into Step 4's rows and raises nothing by itself. Raise one level only where the evidence shows impact still widening - more users or a higher error rate in the latest window than the one before - never above Critical, and never below the Step 3 threshold. Record the raise and its evidence on the Basis line, so the deep pass re-deriving severity from the same rows can see it
- Recent change -> a `deploy_event` inside the window that touches the affected service or its config; its timestamp is the Recent change value, and rollback is usually the fastest containment (the item itself lands in Immediate Action)
- Happened before -> the hydrated `error_event`'s `First seen` field answers it, whatever the vendor; with no issue block, a runbook or prior postmortem the repo keeps (Budget) is cited by path, or "none found"

### Step 6 - Emit the First Look

Emit the First Look block now, before anything else is shown and before Phase 2 starts. The Status line marks the whole block: `Provisional` means every classified field is provisional and the Deep Pass section names what could overturn it; `Final` means no deep pass runs, and what is unknown is written as unknown, not provisional.

**Terminal at Phase 1** - only in the two cases listed below, and only at Medium/Low. Every other Medium/Low classification still runs its deep pass; at Critical/High the deep pass always runs (a Code bug there runs `oncall-investigate` to settle exposure and data integrity, the fix still belonging to the owning engineer). `Status: Final`, the Deep Pass line records `Not run` with the terminal reason, and the workflow ends:

- Code bug - derive the repro condition from the evidence into the Context Package `Repro` and `Owner` slots and hand off; the fix belongs to the owning engineer
- The user asked for the classification itself ("is this an incident?") - the Recommended Workflow line names what runs on their go-ahead

When both apply, it is the Code bug variant.

---

## Phase 2 - Deep Pass

### Step 7 - Spawn the Deep Pass

**Routing is execution, not advice.** Spawn one subagent that runs the routed skill on the Context Package, as the **declared subagent** below - do not infer it from the work type. Routing means running it here, not naming it for the responder to run later, whether or not the skill is separately user-invocable.

| Work Type                          | Deep pass skill                                                                                                                         | Subagent (`subagent_type`) |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| Active incident                    | `incident-root-cause`                                                                                                                   | `oncall-responder`         |
| Code bug (Critical/High)           | `oncall-investigate` - exposure and data integrity; the fix stays with the owning engineer                                              | `oncall-responder`         |
| Operational / User request / Alert | `oncall-investigate`                                                                                                                    | `oncall-responder`         |
| Performance                        | `oncall-investigate` - it diagnoses the running system from evidence. Where a change is the suspect, its handoff names `task-code-review-perf` as the follow-up, which needs a branch or PR the Context Package does not carry | `oncall-responder`         |

**Subagent availability**, keyed to what the Agent tool reports. Declared type registered -> use it. Declared type not registered -> spawn `general-purpose` with the `oncall-responder` agent body (`plugins/architecture/agents/oncall-responder.md`) inlined as its role - its description and routing rules, not the whole file - and record the stand-in on the Deep Pass line. No subagent can be spawned at all -> run the routed skill inline under the same contract and record `inline`. `Deep Pass: failed` is reserved for a spawn that ran and did not return.

**Subagent prompt contract** - each must include:

- The statement that it is running as the deep pass of `task-oncall-triage`. The subagent loads `behavioral-principles` itself, as every routed skill requires; it does not re-run `stack-detect`, since the parent's detected stack is supplied below; and it spawns no subagent of its own.
- The original alert, ticket, or paste text verbatim
- Every evidence block Phase 1 fetched, verbatim, so the deep pass re-fetches only what came back unavailable
- The provisional Work Type, Severity, and Ongoing read, labelled provisional, plus the instruction to re-derive each from evidence and report the delta - a confirmation the deep pass did not earn is worth nothing
- The pre-detected stack and the full Context Package
- Authorization to read the codebase, run read-only queries against the systems it can reach, and fetch the evidence Phase 1 left unavailable
- The return contract: the routed skill's Output block; then `## Changes from First Look` with one line per First Look field (Work Type, Severity, Ongoing, Symptom, Time window, Affected scope, Recent change, Prior occurrence) in the form `- {Field}: {First Look value} -> {confirmed | new value | new value (unverified) | unverified} - {the evidence that settled it, or what would}`, where `new value (unverified)` marks one inferred rather than observed; a changed Work Type carries the Recommended Workflow it implies as a further line; then, when the First Look carried Immediate Action, `## Immediate Action check` with one line per item: `- {item}: {holds | still holds - narrowed to {what} | no longer needed - {why} | harmful - {why}; do {this} instead}`

While the subagent runs, the main thread stays on the First Look: answer follow-up questions from it, and say which fields are still provisional; with none, wait - no code reading, no re-fetching.

**Failure isolation:** if the subagent fails, the First Look stands - report `Deep Pass: failed`; if it exceeds its window, report `timed out`. Either way, replace the Changes table with one line naming what stayed unverified.

### Step 8 - Reconcile and Report

Project the subagent's Changes list into the Updated Assessment, one row per First Look field, and its Immediate Action check into the Acted-On Warning. This is reconciliation, not re-investigation: the Basis column carries the deep pass's evidence, and the main thread reads no code. A field the deep pass could not settle is reported as unverified, never as confirmed.

---

## Output Format

Two blocks in the same session: the First Look at the end of Step 6, and the Updated Assessment at the end of Step 8 when a deep pass ran. On a terminal-at-Phase-1 path the First Look is the whole deliverable. Nothing precedes the First Look.

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
  - {"{block type}: {key value}" when fetched, pasted, or read from a repo file (name the source); "{block type}: paste pending - {the block's Paste prompt}" when unavailable; "{block type}: needs {parameter}" when the block returned a `Needs:` line, which asks for a parameter and not a paste; "{block type}: {what the paste or repo file gave} - paste pending for {missing fields}" when partly satisfied; "narrative: {source} - {what it establishes}" for input matching no block type}

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

Do now: {the first action from the routed block's containment or recommended actions; on an `oncall-investigate` escalation, the first item of the handoff it wrote into Evidence | none - First Look actions stand}

### Changes from First Look
| Field | First Look | After deep pass | Basis |
| ----- | ---------- | --------------- | ----- |
| {one row per field in the deep pass's Changes list, in block order} | {provisional value} | {confirmed \| new value \| new value (unverified) \| unverified} | {the evidence that settled it, or what would} |

### Acted-On Warning
(omit this entire section, heading included, unless the First Look carried Immediate Action and one of its items changed status, or a Severity or Work Type change invalidates one. With no Immediate Action list there is nothing to warn about)
- {First Look action}: {now supported by {evidence} | still holds - narrowed to {what} | no longer needed - {why} | harmful - {why}; do {this} instead}

{routed workflow output block, verbatim}
```

## Self-Check

- [ ] behavioral-principles loaded before any step
- [ ] Step 1: stack detected
- [ ] Step 2: every recognized URL fetched; deploys pulled unless a dated change record was in the input, window covering onset; repo-kept evidence read and cited by path; no paste waited on
- [ ] Step 3: first matching row top-down on hydrated evidence; Basis line carries the threshold read and any assumption
- [ ] Step 4: highest matching row, below-threshold reading applied; Critical/High carries Immediate Action
- [ ] Step 5: `Ongoing` set on the First Look; recent change and prior occurrence recorded in the Context Package; any severity raise justified by widening impact on the Basis line
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
