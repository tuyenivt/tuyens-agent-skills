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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. Delegated skills supply analysis method, not structure: this skill's Output Format is the only output contract - absorb their findings into its slots and never emit their own Output blocks. The one exception is the routed deep-pass block, which Step 9 appends verbatim.

# Oncall Triage

An alert, ticket, stack trace, or symptom just landed: classify it, then drive it to a cause.

Two phases. **Phase 1 - First Look** classifies on hydrated evidence alone, inside one fetch pass and its per-monitor `metric_series` follow-ups, and is on screen before anything else - it is what the responder acts on. **Phase 2 - Deep Pass** runs the routed workflow in a subagent and may overturn any Phase 1 field.

## When to Use

- An alert, ticket, stack trace, or user report needs classifying and driving to a cause
- An active production incident, even when the impact is self-evident - Critical/High carries containment in the First Look rather than waiting on the deep pass
- A resolved incident, when the question is why it happened

**Not for:**

- Designing the system so a failure class cannot recur - hand off to `architecture-architect`, which gates redesign on a confirmed root cause; run this workflow first when there is none
- The post-incident write-up - that follows the company's own format; supply the confirmed root cause, blast radius, and timeline as its input
- A forward-looking upgrade assessment or task breakdown - hand off to `architecture-planner`

---

## Phase 1 - First Look

**Budget:** one `ops-observability-fetch` pass plus the `metric_series` follow-ups Step 3 names, one per recognized monitor, no source code read, no database query, no reproduction attempt, no waiting on a paste. Evidence the project keeps in the repo as data files - deploy logs, monitor definitions, runbooks, postmortems, tickets, capacity notes, evidence bundles (another incident's bundle included, cited with its date; a diff or PR captured in a bundle is evidence, read for correlation), and the ownership records (`CODEOWNERS`, a service map) the Context Package's Owner slot needs - is evidence, not code: read it inside the fetch pass and cite the path. Where `CLAUDE.md` carries an `## Observability` section, use it to choose between transports, not as the list of what may be read. Anything executable or imported (schedules, settings modules, environment files) is code and waits for the deep pass. A file the session cannot read is an unavailable block after one attempt - no workaround; the deep pass tries once more. Blocks that come back unavailable stay unavailable and are named in the output.

### Step 1 - Behavioral Rules

Use skill: `behavioral-principles`.

### Step 2 - Stack

Use skill: `stack-detect`.

### Step 3 - Hydrate Evidence

Use skill: `ops-observability-fetch`. Request exactly these blocks - the fetch skill emits each one, unavailable when it cannot be fetched:

- `error_event` per recognized issue URL or ID; `monitor_state` per recognized monitor URL or ID; `metric_series` for each recognized monitor's underlying metric, named from the metric in `monitor_state`'s `Threshold:` expression once that block returns - the follow-up fetches the Budget allows, one per monitor; where no name resolves, the block comes back `Needs: metric name` and that is what the Evidence line records. Window: earliest known onset minus 60 min to now, or the last 60 min when onset is unknown - it tells whether the symptom is ongoing
- `deploy_event` via `list_deploys` for every service that ships the affected code path, unless the input already carries a dated change record for that service inside the deploy window: a deploy, release, or config change (a key rotation on the change calendar) with its ship timestamp; pull for every service the input holds no such record for. A release tag or a PR alone names what merged, not when it shipped, and a negative or unverified claim ("nothing deployed as far as I know") is not a record - pull. Window: 48h, or from 24h before the earliest known onset when that is older
- `log_window` and `trace` when the input anchors them (a log-search or trace URL), or when the project keeps them as repo data files the Budget allows reading - an evidence bundle counts, and its files are cited by path

Fetch every recognized URL even when paste content accompanies it - never classify on a URL alone. Pure paste (PagerDuty title, Slack message, stack trace - no URL or ID): request `deploy_event` (unless the paste carries a dated change record inside the deploy window); the fetch skill still emits any block the paste directly anchors (an explicit ID, metric name, or service plus window), and a paste that anchors none goes on the Evidence line under the block type its shape matches (`error_event: <first frame> - user-paste`, `log_window: <N lines, first to last timestamp> - user-paste`), written by this workflow. Paste matching none of the six - a support thread, a chat exchange, a ticket - is not a block: it goes on the Evidence line as `narrative: {source}` with what it establishes, and is never forced into a block type.

The blocks feed Step 4, the Context Package, and the Step 8 subagent prompt, where they are pasted verbatim. Neither the stack-detect output nor the raw blocks are shown to the user - the Evidence line summarizes them, one nested bullet per block in the template's forms: the key-value form for a block fetched, pasted, or read from a repo file, the source named (a dated change record the input carries is a pasted `deploy_event`); `paste pending` when unavailable; `needs` when it returned a `Needs:` line, which asks for a parameter and not a paste; the partly-satisfied form when the paste or repo file gave some fields; `narrative` for input or a repo file matching no block type; `question` for a URL that produced the fetch skill's Question line instead of a block; `note` for a URL that produced its Note line and no block.

### Step 4 - Classify Work Type

Take the first matching row top-down.

| Type                       | Signals                                                                                                        | Deep pass                                       |
| -------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------- |
| **Active incident**        | Multi-user impact (threshold below), ongoing or resolved: error rate spike, service down, SLA breach, data loss across users | `incident-root-cause`                           |
| **Code bug**               | Stack trace, test failure, crash, reproducible error - without multi-user impact, ongoing or resolved          | `oncall-investigate` at Critical/High; none at Medium/Low - terminal at Phase 1 (repro + handoff) |
| **Alert**                  | Alert fired, unclear if real or false positive                                                                 | `oncall-investigate`                            |
| **Performance**            | Slow response, high latency, timeout (no outage)                                                               | `oncall-investigate`                            |
| **User request**           | Single user issue, access problem, data question                                                               | `oncall-investigate`                            |
| **Operational**            | Batch missed, queue backed up, "why did X happen?"                                                             | `oncall-investigate`                            |

"Multi-user impact" is the `oncall-investigate` escalation rule, kept in sync: 3 or more distinct users (or tenants) affected within an hour - "N others affected" counts distinct users excluding the reporter, and affected entities alone do not count; or error rate on the affected path more than 2x baseline **and** more than 10 errors in that hour, so a handful of errors on a quiet path does not qualify; or a revenue/auth/data-integrity path with confirmed multi-user impact or active error-rate elevation. Below it, an error in production is a Code bug or Operational work, not an incident, whatever path it sits on. "Confirmed" means observed in evidence, not a mechanism that could reach many users; when no error-rate figure is held, or the held `metric_series` has no baseline (`Baseline delta: no baseline`, or a user-paste block, which carries no `Baseline delta` line), the error-rate criterion is not run - the deep pass re-runs it when it can obtain a baseline - counts as unmet for classification, and the Basis line says so. Below the threshold, Basis ends with the tripwire that would make this an Active incident.

When the user asks what type this is ("is this an incident?"), classify and answer on the Basis line - do not ask back; "can it wait?" is answered there by Severity: Critical/High cannot, Medium/Low can; "should I roll back?" by Immediate Action at Critical/High, and on the Basis line from Recent change at Medium/Low. A question about the alert's own validity ("is this real?") is not a classification request: it runs the deep pass. When the revenue-path status of the feature is unclear, state the assumption on the Basis line and classify under it.

### Step 5 - Severity

Mirrors `incident-root-cause` Step 1: Critical and High match on any one criterion in their row, Medium and Low on every condition in theirs; an unknown percentage is unmet for Critical and High and met for Medium, with `percentage unknown` named as the denominator:

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue path affected (a request that takes or moves money or grants access: payment, checkout, refund, billing-document creation, auth - viewing a billing document is not one), >50% affected, or data loss or corruption risk |
| High     | 10-50% affected, or two or more services impacted                       |
| Medium   | User-facing but under 10% affected, single service, no data loss or corruption risk |
| Low      | Not user-facing, and no data loss or corruption risk                    |

Percentages are of requests, of users, or of another unit the evidence gives (jobs, SKUs, page views); use one denominator throughout and name it on the Basis line. When criteria from multiple rows match, take the highest row. Below the Step 4 threshold the percentage rows do not apply - a share of a handful of requests is not breadth: a revenue/auth path (as the Critical row defines it) or data loss or corruption risk is Critical whatever the breadth; two or more services impacted is High; otherwise Medium when the affected path is one users interact with directly (request, page, notification), Low when it is not (job, queue, alert-only). For Critical/High: no further work-type refinement - Steps 6-7 still run in one fast pass, and Step 6 feeds the rollback item in Immediate Action. Immediate Action carries 1-3 items - rollback of the Step 6 change when one correlates; when Recent change is Unverified, get the deploy record first and roll back if it correlates; else the fastest reversible containment the evidence supports - plus, outside the cap as `incident-root-cause` keeps them, the state-capture item ahead of any restart or redeploy and the data-integrity check when writes may have partially landed. On terminal case 3 the first item is the evidence capture - an error, stack trace, or error log line, or a Sentry, Datadog, or monitor URL.

### Step 6 - Scope Check

- Repro and Owner (Code bug, any severity) -> the steps that reproduce it with expected vs actual, from the trace or report, and any stuck work to replay once fixed; `CODEOWNERS` or the service map, else the owning service
- Symptom, Time window, Affected scope -> from the blocks: the monitor or issue title and the reporter's sentence; earliest onset to last seen across blocks; the Step 4 count with its denominator
- Ongoing -> `Yes` when the latest window of the fetched metric or error block still shows the symptom, the reporter's timestamped statement says it continues, or the latest timestamped evidence held (a read, a ticket update) still shows it; `No` when the latest window is clean or a timestamped recovery is stated; neither -> `Unknown`. Ongoing impact is already priced into Step 5's rows and raises nothing by itself. Raise one level only where the evidence shows impact still widening - more users or a higher error rate in the latest window than the one before, the two windows being the finest equal split the evidence gives (the fetch window's halves when nothing finer exists) - never above Critical, and never below the Step 4 threshold. Record the raise and its evidence on the Basis line; the deep pass re-derives base severity - `incident-root-cause` from its Step 1 table, `oncall-investigate` from the Step 4-5 tables quoted in its prompt - and Step 9 re-applies the raise when the deep pass's evidence still shows widening
- Recent change -> a `deploy_event` inside the window that touches the affected service or its config; its timestamp is the Recent change value (two dated records that disagree -> `Conflicting`), and rollback is usually the fastest containment (the item itself lands in Immediate Action). A fetched empty list (`Total in window: 0`), or no deploy in the window touching the affected service, reads `None found in {Tool or repo file, Window}`; an unavailable `deploy_event` reads `Unverified - {its Paste prompt or Needs line}`. When Step 3 skipped the pull on an input-carried dated change record, that record and its timestamp are the Recent change value; a record older than the window does not skip the pull, and is named on the Basis line when it touches the affected path. A dated load or traffic change is Basis evidence, not a Recent change
- Prior occurrence -> the hydrated or pasted `error_event`'s `First seen / Last seen` field answers it, whatever the vendor; with no issue block, a runbook, prior postmortem, or ticket the repo keeps (Budget) is cited by path, or "none found"; `unknown` when the issue block came back unavailable and no repo doc exists

### Step 7 - Emit the First Look

Settle Step 8's subagent-availability ladder first, so the Status and Deep Pass lines are final, then emit the First Look block, before anything else is shown and before Phase 2 starts. The Status line marks the whole block: `Provisional` means every classified field is provisional and the Deep Pass section names what could overturn it; `Final` means no deep pass runs, and what is unknown is written as unknown, not provisional.

**Terminal at Phase 1** - only in the three cases listed below; the first two only at Medium/Low. Every other Medium/Low classification still runs its deep pass; at Critical/High the deep pass always runs unless the third case holds. `Status: Final`, the Deep Pass line records `Not run` with the terminal reason, and the workflow ends:

- Code bug - the Context Package's `Repro` and `Owner` slots (Step 6) are the hand-off; the fix belongs to the owning engineer
- The user asked for the classification itself ("is this an incident?") - the Recommended Workflow line names what runs on their go-ahead
- An Active incident whose evidence holds neither an error, stack trace, or error log line nor a Sentry, Datadog, or monitor URL - `incident-root-cause` cannot run without one: Status reads `Final - no evidence anchor, capture first`, the Deep Pass line `Not run - no evidence anchor`, and Immediate Action is emitted at any severity with the capture as its first item

When the first two both apply, it is the Code bug variant; case 3 wins over case 2.

---

## Phase 2 - Deep Pass

### Step 8 - Spawn the Deep Pass

**Routing is execution, not advice.** Spawn one subagent that runs the routed skill on the Context Package, as the **declared subagent** below - do not infer it from the work type. Routing means running it here, not naming it for the responder to run later, whether or not the skill is separately user-invocable.

| Work Type                          | Deep pass skill                                                                                                                         | Subagent (`subagent_type`) |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | -------------------------- |
| Active incident                    | `incident-root-cause`                                                                                                                   | `oncall-responder`         |
| Code bug (Critical/High)           | `oncall-investigate` - exposure and data integrity; the fix stays with the owning engineer                                              | `oncall-responder`         |
| Operational / User request / Alert | `oncall-investigate`                                                                                                                    | `oncall-responder`         |
| Performance                        | `oncall-investigate` - it diagnoses the running system; a suspect change in its Root Finding is followed up by `task-code-review-perf` via Do now | `oncall-responder`         |

**Subagent availability**, keyed to what the Agent tool reports. Declared type registered -> use it. Declared type not registered -> spawn `general-purpose` with the `oncall-responder` agent body (`plugins/architecture/agents/oncall-responder.md`) inlined as its role - its description plus its Role and Response Principles sections only; its Decision Guidance would send the work back here - and record the stand-in on the Deep Pass line. No subagent can be spawned at all -> run the routed skill inline under the same contract and record `inline`; the inline run still produces the `## Changes from First Look` list and the Immediate Action check before Step 9. `Deep Pass: failed` is reserved for a spawn that returned an error or no routed Output block.

**Subagent prompt contract** - each must include:

- The statement that it is running as the deep pass of `task-oncall-triage`. The subagent loads `behavioral-principles` itself as its Step 1 unless the spawning prompt inlines its whole Rules section (Rules 1-7, Proportionality and disposition, Rule interactions), as `behavioral-principles` requires of a spawned subagent (`incident-root-cause` does not load it on its own); it does not re-run `stack-detect`, since the parent's detected stack is supplied below; and it spawns no subagent of its own.
- The original alert, ticket, or paste text verbatim
- Every evidence block Phase 1 fetched, verbatim, as the routed skill's paste input; its own re-fetch rule then decides what it pulls again
- The provisional Work Type, Severity, and Ongoing read, labelled provisional, with this workflow's Step 4 threshold and Step 4-5 tables quoted (the deep pass starts on a fresh context and `oncall-investigate` has no severity model of its own), plus the instruction to re-derive each from evidence and report the delta - a confirmation the deep pass did not earn is worth nothing. On an `oncall-investigate` route, its Request Type maps back onto Work Type: Alert -> Alert, Performance -> Performance, Data or Access -> User request, Operational -> Operational, Unexpected behavior -> Code bug when the First Look held a trace or crash, else Operational, an escalation -> Active incident. On an `incident-root-cause` route, the subagent re-reads the quoted Step 4 threshold against its own evidence and reports the result on the Work Type line: met confirms Active incident; unmet, or a classifier Scope of `Absent`, re-reads from the Step 4 table
- The pre-detected stack, the full Context Package, and the Immediate Action list when the First Look carried one
- Authorization to read the codebase, run read-only queries against the systems it can reach, and fetch the evidence Phase 1 left unavailable
- The return contract: the routed skill's Output block; then `## Changes from First Look` with one line per First Look field (Work Type, Severity, Ongoing, Symptom, Time window, Affected scope, Recent change, Prior occurrence) plus Repro and Owner on a Code bug, in the form `- {Field}: {First Look value} -> {confirmed{ - role revised: <how>} | new value | new value (unverified) | unverified} - {the evidence that settled it, or what would}`, where `new value (unverified)` marks one inferred rather than observed and `role revised` keeps a value whose causal reading changed; a changed Work Type carries the Recommended Workflow it implies as a further line; then, when the First Look carried Immediate Action, `## Immediate Action check` with one line per item: `- {item}: {holds | still holds - narrowed to {what} | no longer needed - {why} | harmful - {why}; do {this} instead}`

While the subagent runs, the main thread stays on the First Look: answer follow-up questions from it, and say which fields are still provisional; with none, wait - no code reading, no re-fetching.

**Failure isolation:** if the spawn returns an error or no routed Output block, the First Look stands - report `Deep Pass: failed - First Look stands`; if the subagent is stopped before it returns (by the user or a tool limit), `timed out - First Look stands`. Either way, replace the Changes table with one line naming what stayed unverified.

### Step 9 - Reconcile and Report

Project the subagent's Changes list into the Updated Assessment, one row per field in that list, and its Immediate Action check into the Acted-On Warning, every item listed. This is reconciliation, not re-investigation: the Basis column carries the deep pass's evidence, and the main thread reads no code. A field the deep pass could not settle is reported as unverified, never as confirmed. A Work Type changed to Active incident by an `oncall-investigate` escalation spawns `incident-root-cause` as a second deep pass under Step 8's contract before reconciling, when its handoff holds an evidence anchor (else the Deep Pass line reads `complete - escalation not run: no evidence anchor` and Do now is the capture) - routing stays execution; the second pass's Changes list supersedes the first's row for row, its block is the one appended, and the escalation stub is folded into Basis. Re-apply the Step 6 raise where the deep pass's evidence still shows widening. Fill `Do now` from the routed block's first action - `incident-root-cause`'s Immediate Containment, the outside-the-cap capture first, or `oncall-investigate`'s first Recommended Action; `task-code-review-perf` on Performance when the Root Finding names a suspect change; `none - First Look actions stand` only on a failed or timed-out deep pass. Then append the routed skill's Output block verbatim; on a failed or timed-out deep pass there is none, and the block is omitted.

---

## Output Format

Two blocks in the same session: the First Look at the end of Step 7, and the Updated Assessment at the end of Step 9 when a deep pass was spawned or run inline, a failed or timed-out one included. On a terminal-at-Phase-1 path the First Look is the whole deliverable. Nothing precedes the First Look.

```markdown
## Oncall First Look

Status: {Provisional - deep pass running | Provisional - deep pass running inline | Final - Code bug, repro handed off | Final - classification-only request | Final - no evidence anchor, capture first}

Work Type: {Active incident | Code bug | Alert | Performance | User request | Operational}

Severity: {Critical | High | Medium | Low}

Ongoing: {Yes | No | Unknown} - {the fetched signal, timestamped statement, or latest timestamped evidence that decides it, or the evidence that would}

Basis: {the Step 4 threshold read - distinct users per hour, error rate vs baseline, path class - the Step 5 row with its denominator (requests, users, or the unit named), any Step 6 raise with its widening evidence; assumptions named}{; answer: <the user's question answered - type, can it wait, roll back from Recent change>}{; older change: <record, date>}{; load change: <what, when>}{; tripwire: <what turns this into an Active incident>}

### Recommended Workflow
Use: {incident-root-cause | oncall-investigate | code-fix handoff (repro + owning engineer)}

### Context Package
- Symptom: {one sentence}
- Time window: {onset and last seen; "unknown" when not in evidence}
- Affected scope: {who/what is impacted}
- Recent change: {deploy/config/flag with timestamp | None found in {Tool or repo file, window} | Unverified - {the deploy_event's Paste prompt or Needs line} | Conflicting - {record A} vs {record B}}
- Prior occurrence: {the error_event's First seen / Last seen{, plus the runbook, postmortem, or ticket path} | the runbook, postmortem, or ticket path | none found | unknown}
- Repro: {steps that reproduce it, expected vs actual, from the evidence}{; stuck work to replay once fixed: <what>} {Code bug only, any severity; at Critical/High the deep pass re-derives it}
- Owner: {team or person from CODEOWNERS or the project's service map | the owning service when no person or team is recorded} {Code bug only, any severity}
- Evidence: {one nested bullet per block}
  - {"{block type}: {key value} - {source: mcp tool, user-paste, or repo path}" | "{block type}: paste pending - {Paste prompt}" | "{block type}: needs {parameter}" | "{block type}: {what the paste or repo file gave} - paste pending for {missing fields}" | "narrative: {source or repo data file} - {what it establishes}" | "{block type}: question - {Question line}" | "note: {url} - {Note line}"}

### Immediate Action {only at Critical/High or on terminal case 3; on a resolved incident - Ongoing No - only the items still outstanding}
- [ ] {action}

### Deep Pass
- {Running {deep pass skill} as `oncall-responder` | Running {deep pass skill} as `general-purpose` standing in for `oncall-responder` | Running {deep pass skill} inline - no subagent available | Not run - {terminal reason}}
- Could overturn: {2-3 specific items - a threshold assumed without a baseline, a block that came back unavailable, a code path not yet read} {omit when the deep pass is not run}
```

```markdown
## Updated Assessment

Deep Pass: {complete | complete - escalation not run: no evidence anchor | failed - First Look stands | timed out - First Look stands}

Do now: {the routed block's first action per Step 9 | {the evidence capture} - escalation not run | `task-code-review-perf` on the suspect change - branch or PR to come from the responder | none - First Look actions stand}

### Changes from First Look
{when Deep Pass is failed or timed out, the table is replaced by one line: `Unverified: {the fields that stayed unverified}`}
| Field | First Look | After deep pass | Basis |
| ----- | ---------- | --------------- | ----- |
| {one row per field in the deep pass's Changes list, in block order, plus a Recommended Workflow row when Work Type changed} | {provisional value} | {confirmed{ - role revised: <how>} \| new value \| new value (unverified) \| unverified} | {the evidence that settled it, or what would} |

### Acted-On Warning {only when the First Look carried Immediate Action and an item reads anything other than `holds` in the deep pass's check, or a Severity or Work Type change invalidates one}
- {First Look action}: {holds | still holds - narrowed to {what} | no longer needed - {why} | harmful - {why}; do {this} instead}

{routed workflow output block, verbatim} {only when Deep Pass is neither failed nor timed out}
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack detected
- [ ] Step 3: every recognized URL fetched; deploys pulled unless a dated change record inside the deploy window was in the input, window covering onset; repo-kept evidence read and cited by path; no paste waited on
- [ ] Step 4: first matching row top-down on hydrated evidence; Basis line carries the threshold read and any assumption
- [ ] Step 5: highest matching row, below-threshold reading applied; Critical/High, and terminal case 3, carry Immediate Action
- [ ] Step 6: Symptom, Time window, Affected scope, `Ongoing`, and on a Code bug Repro and Owner set on the First Look; recent change and prior occurrence recorded in the Context Package; any severity raise justified by widening impact on the Basis line
- [ ] Step 7: First Look on screen before anything else and before Phase 2; Status line states Provisional, or Final with the terminal reason (Medium/Low, or no evidence anchor)
- [ ] Step 8: deep pass spawned as the declared subagent, or the stand-in / inline fallback recorded, carrying the evidence blocks, the provisional read, the re-derive instruction, and the return contract; the subagent loaded behavioral-principles, or the whole Rules section inlined in the spawning prompt (the Step 9 escalation pass likewise) - or the terminal case recorded with its reason
- [ ] Step 9: one row per field in the deep pass's Changes list; Do now filled; where the First Look carried Immediate Action, a changed Severity, Work Type, or item carries an Acted-On Warning projected from the Immediate Action check; the routed block appended verbatim unless the deep pass failed or timed out

## Avoid

- Handing the deep pass the provisional classification as settled fact, or accepting a confirmation it did not re-derive
- Re-classifying when the user has already stated the work type and the evidence meets its row - route directly; below the Step 4 threshold the table wins over the stated type
- Calling production errors "incidents" below the multi-user threshold - route them as bugs or operational work
