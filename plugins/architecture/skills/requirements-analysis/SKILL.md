---
name: requirements-analysis
description: "Analyze product requirements against each other and the current system: register, ambiguity, conflicts, missing cases, infeasibility."
metadata:
  category: architecture
  tags: [requirements, prd, ambiguity, conflicts, gap-analysis, traceability]
user-invocable: false
---

# Requirements Analysis

## When to Use

- A PRD, epic, ticket, or story set written by a PO, PdM, or PM is about to drive a design, and its functional requirements have not been checked against each other or against the system they land in.
- A revised PRD comes back with the requester's answers to an earlier analysis.

Non-functional targets belong to `nfr-specification`; this skill reads them only to find a functional requirement that contradicts one, or one the current system cannot meet.

## Rules

- **One outcome, one row.** A sentence stating two outcomes is two rows; two sentences stating one outcome are one row quoting the more precise. Every stated row cites its source (section, line, or story ID); an implied requirement takes the next free number, Source `implied by R<n>`, and Status `Implied`.
- **Cite or assume, never recall.** A fact about the current system is evidence only when it cites code (`file:line`, or for an absence the search that found nothing: `no match for <term> under <path>`), a current-system input (its name and line), or a `task-onboard` report row. Anything else is written `(assumed)`, and confirming it becomes part of the finding's question. How such systems usually work is never evidence.
- **Precedent before question.** Before writing an open question, search the current system for the same decision already made for another actor, channel, entity, or state. When one exists, the recommended answer is the option it matches, written `<option> - follows <precedent> (<citation>)`.
- **Which outcome, never which mechanism.** A finding asks who, what value, on which trigger, in which state, or what the user sees on failure. How to build a stated outcome is the design's choice and is never a finding. A mechanism the source prescribes ("add a cron job") is a requester-stated constraint: the outcome it serves becomes the row, the mechanism follows it in the Requirement cell as `stated constraint: <mechanism>`, and it becomes a finding only when a Conflict sources check catches it.
- **Implied is proposed, never added.** An implied requirement with an open Blocking finding stays out of scope until the requester answers; one whose open findings are all `Defaulted` is carried by the caller's handoff as assumed on the recommended answer. The answer brings the row into scope or removes it.
- **Severity is the finding's, keyed to impact class.** One decision per finding, the first that applies: `Minor` when every option yields the same outcome and only the requirement's wording changes; `Blocking` when the options lead to a different data model, API or event contract, consistency model, or authorization model and no precedent settles it, or when no answer can be recommended (`Recommended: none`); `Defaulted` otherwise - the design proceeds on the recommended answer, which the caller's handoff carries as assumed.

## Patterns

### Ambiguity triggers

| Trigger | Example | The question names |
| --- | --- | --- |
| Undefined actor | "the user can cancel" where the system has buyer, seller, and support roles | Which roles, and whether one may act for another |
| Undefined state | "cancelled orders" where the system has `cancelled_by_buyer` and `voided` | Which states, and what happens to records in the others |
| Unbounded trigger | "when the order changes" | Which field or transition fires it, and whether a repeat fires again |
| Vague quantity or time | "recent", "many", "quickly", "end of day" | The value, and whose time zone |
| Cardinality | "the shipment of an order" where orders can split | One or many, and what the user sees with many |
| Modality | "should", "may", "ideally" | Required, optional, or out of scope |
| Unstated failure | "send the invoice" | What the user sees when it fails, and whether it retries |

### Conflict sources

Check each row against another row or the source's stated exclusions; a current-system invariant, validation, or state rule; an existing API, event, export, or report and its consumers; a stated NFR; and a regulatory signal, named only, since `nfr-specification` names the standard. A conflict's options are always changing one side or the other - the requirement, or the row, stated exclusion, system rule, contract, or NFR it collides with - each with its consequence.

### Completeness walk

For every row that creates or changes data or state, ask each line. A line that the source or the current system already answers is not a finding.

| Area | Ask |
| --- | --- |
| Lifecycle | Every state and transition, the terminal states, who may trigger each |
| Failure and duplicates | What the user sees on failure; double submit; retry |
| Concurrency | Two actors on one record at once |
| Existing data | Records created before release: migrate, backfill, or grandfather |
| Permissions and tenancy | Who sees and acts, across which tenant boundary |
| Limits and volume | Maximum per entity; bulk operations; list size |
| Time | Time zone, deadline semantics, scheduling |
| Reversal and retention | Undo, cancel, refund, delete, erasure requests, retention period |
| Downstream readers | Reports, exports, jobs, and integrations reading the changed data |
| Coexistence | Old clients and old behavior during rollout |

### Infeasible as stated

A requirement the current system or a stated NFR rules out names the constraint with its citation and the achievable frontier: what can be delivered, and which requirement or system rule relaxing would lift the limit. "Real-time stock on the storefront" over a nightly inventory import is infeasible as stated; the frontier is "stock as of the last import, labelled with its time - or an hourly import, which needs a new supplier agreement".

### Bad and good finding

Bad - a mechanism dressed as a question, with no evidence and no recommendation:

```
Q2: Should shipment notifications use a queue or be sent synchronously?
```

Good - the outcome question, the precedent, and the consequence:

```
#### Q2 - Who is told when an order ships

- **Class:** Ambiguity
- **Requirements:** R4
- **Question:** "Notify the user when the order ships" - the buyer only, or the buyer and the staff member who packed it?
- **Options:** (a) buyer only - staff keep using the back office; (b) both - staff get one email per shipped order
- **Recommended:** (a) - follows refund notifications, which go to the buyer only (`app/notifiers/refund_notifier.rb:18`)
- **Evidence:** two order-facing roles, `Buyer` and `StaffMember` (`app/models/order.rb:12-14`)
- **Design consequence:** recipient list only; no entity, contract, or authorization change
```

## Output Format

The register and the findings are the contract consuming workflows parse. IDs are stable: on the first run, stated rows are numbered in source order, implied rows after them, and findings, Minor ones included, in the order of the first row each cites, so each finding section lists its own in ascending `Q<n>`, gaps and all; a re-run on a revised source keeps every row's `R<n>` and every finding's `Q<n>`, answered or reworded ones included, gives new rows and findings the next free number, removes a row the revision drops with its findings, and never reuses a removed or answered number.

Every Blocking or Defaulted finding carries a recommended answer - a precedent is not required for one - or `none - <why>`, always Blocking, when no precedent exists and both options are defensible; a Minor finding's Proposed text is its recommendation. A stated row that never had a Blocking or Defaulted finding is `Clear`; otherwise its open Blocking and Defaulted findings set it: Status is the first that applies in the order Implied, Infeasible as stated, Conflicting, Ambiguous (an Ambiguity or Missing finding), and the Finding cell lists each of them, open or answered; Acceptance check reads `pending Q<n>{, Q<n>}`, naming each open Blocking finding that leaves the row's outcome undecided; a row resting only on Defaulted findings states the check for the recommended answer. When the requester answers one, it leaves its finding section, the Finding cell marks it `Q<n> (answered)`, and the Requirement cell is rewritten to the outcome the answer settles; a row with none left open becomes `Answered`, an answer that states a new outcome adds a row, one that opens a new question adds a `Q<n>`, and an implied row the answer declines is removed. A `Minor` finding is a Wording row only: it enters neither finding section (Needed Before Design Starts, Proceeding on These Unless You Object), the Finding cell, nor Status.

```markdown
## Requirement Register

| ID | Requirement | Source | Status | System impact | Acceptance check | Finding |
| --- | --- | --- | --- | --- | --- | --- |
| R1 | <one outcome>{ - stated constraint: <mechanism>} | {<section, line, or story ID> \| implied by R<n>} | {Clear \| Ambiguous \| Conflicting \| Infeasible as stated \| Implied \| Answered} | {none \| data model \| API contract \| event contract \| consistency \| authz \| job or batch \| external integration \| UI only} | {<observable outcome that proves the row> \| pending Q<n>{, Q<n>}} | {Q<n>{ (answered)}, ... \| -} |

## Findings

### Needed Before Design Starts

#### Q<n> - <short title>

- **Class:** {Ambiguity | Conflict | Missing | Infeasible}
- **Requirements:** R<n>{, R<n>}
- **Question:** <source quote - the question in the requester's terms>
- **Options:** (a) <outcome> - <what it means for the requester>; (b) <outcome> - <what it means>
- **Recommended:** {<option>{ - follows <precedent> (`<citation>`)} | none - <why>}
- **Evidence:** <system citation, or the fact marked (assumed)>
- **Design consequence:** <what each option changes: entity, contract, consistency, or authorization>

{instead, when no Blocking finding is open: one line saying none}

### Proceeding on These Unless You Object

{one block per open Defaulted finding, same fields}

{instead, when no Defaulted finding is open: one line saying none}

### Wording {only when a Minor finding exists}

| Q | Requirement | Current text | Proposed text |
| --- | --- | --- | --- |
| Q<n> | R<n> | <quote> | <rewrite> |
```

## Avoid

- Rephrasing a requirement into one the current system already satisfies
