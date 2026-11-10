---
name: task-analyze-requirements
description: "Analyze a PRD against the current system before design: ambiguity, conflicts, missing cases, design impact, questions for the PO."
agent: architecture-architect
metadata:
  category: architecture
  tags: [requirements, prd, analysis, ambiguity, gap-analysis, traceability, product]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Steps 1 and 2 load `behavioral-principles` and `stack-detect`; their rules govern every step that follows. If a delegated skill is unavailable (standalone use), apply the step's inline instructions on judgment and say so. Delegated skills supply analysis method, not structure: this skill's Output Format is the only contract, and the `requirements-analysis` Requirement Register and Findings blocks are emitted inside it exactly as that skill defines them, their headings included.

# Requirements Analysis

Checks a PRD, epic, ticket, or story set against itself and against the system it lands in, before anything is designed, and turns what does not hold into questions the requester can answer. One document serves two readers. The requester answers the Findings. The architect carries the Requirement Register into design, where its `R<n>` IDs trace through design sections, tasks, and the code review.

## When to Use

- A PO, PdM, or PM hands over requirements and the design has not started.
- The requirements were written from an upstream ask by someone who does not know the current system's states, contracts, and rules.
- The requester returned answers or a revised PRD; re-run with the prior analysis.

Not this workflow: designing the solution (`task-design-architecture`, `task-design-brief`) - this one decides whether the ask is ready to design, never how to build it; reviewing a design document (`task-design-architecture` Review Mode). A direction check on a proposed mechanism ("is this approach sensible?") is `task-design-architecture` at `quick`: that judges the mechanism, this judges the ask. A requirements document is always the artifact under analysis here, whoever wrote it; there is no separate review mode.

## Inputs

| Input | Required | Description |
| --- | --- | --- |
| Requirements | Yes | PRD, epic, ticket, or stories - pasted or a path |
| Current system | No | The codebase when the run can read it; a `task-onboard` report, whose Modules and Critical Invariants rows and Primary Flow and Edge Cases That Matter entries are citable; or a description of the services, tables, jobs, and contracts touched, architecture and operations documents included |
| Prior analysis | No | An earlier output of this workflow, with the requester's answers |
| Requester | No | Name and role; the Findings are addressed to them |
| Constraints | No | Deadline, frozen systems, compliance |

A missing current-system input degrades one thing: every system-side fact reads `(assumed)`, no precedent can settle a finding, and the header's Current system line says so. Nothing is invented to fill the gap.

## Workflow

### Step 1 - Behavioral rules

Use skill: `behavioral-principles`.

### Step 2 - Stack

Use skill: `stack-detect`. When the request names a stack and detection returns `unknown`, trust the request and record the assumption.

### Step 3 - Ground the current system

Collect the entities, states, actors and roles, flows, invariants, and contracts that the requirements' nouns and verbs touch, each with its source. This list is a working note and is not emitted. Read in order: the codebase (models and schema, routes and handlers, jobs, published events for each noun), then a `task-onboard` report, then a description. Code outranks a report, and a report outranks a description; a disagreement between them is evidence for the finding it bears on.

### Step 4 - Register and analyze

Use skill: `requirements-analysis` to register every requirement, then run its ambiguity, conflict, completeness, and feasibility patterns against the Step 3 list. When the requirements state or imply a latency, volume, availability, or retention figure, Use skill: `nfr-specification` for the conflicts and infeasible targets among those figures only. Each becomes a Conflict or Infeasible finding citing the row the figure constrains; `nfr-specification`'s output block is not emitted, because design Section 1 owns it.

With a prior analysis, carry its IDs and apply `requirements-analysis`'s re-run rules; name each row the revision drops, and each Implied row the requester declined, on the header's Source line.

### Step 5 - Design consequences

For each row whose System impact is neither `none` nor `UI only`, name what the design must decide or change - never how to build it. Load each atomic with `Use skill: <name>` when its signal fires:

| Signal | Load | Feeds |
| --- | --- | --- |
| A new entity, or data ownership moving between modules | `system-boundary-design` | Which module owns the change |
| One requirement writing to two stores or services | `architecture-data-consistency` | The consistency model the requirement forces |
| A change to an API, event, export, or report already consumed elsewhere | `ops-backward-compatibility` | `compatible: {Yes \| No \| No (unverified)} - <who is affected>` per row of the atomic's Changes Assessed table (one per discrete change, direction, and consumer class), separated by `; `, opening the row's What the design must decide cell |
| At least one impacted row, over the impacted rows taken together | `review-blast-radius` | The header's Blast radius line, read as if the impacted surface were the change |

Findings from these atomics land in a finding's Design consequence line or in the Design Consequences table; no atomic output block is emitted.

### Step 6 - Word for the requester

Use skill: `design-audience-calibration` with the requester as the reader; with nothing stated and no signal to infer from, its default profile applies. Its Vocabulary governs the Question, Options, and Recommended lines, and its Attribution line becomes the header's `Written for` bullet. Its diagram and page budgets, `Appendix carries` and `Domain context` do not apply. Evidence and Design consequence lines stay in engineering terms, because the architect reads them.

### Step 7 - Readiness and handoff

The verdict is **Not ready** when any Blocking finding is open, **Ready with defaults** when none is and a Defaulted finding is open, and **Ready** when no Blocking or Defaulted finding is open. Write the Handoff to Design from the register.

## Output Format

````markdown
# Requirements Analysis: <feature>

- **Readiness:** {Ready | Ready with defaults | Not ready} - {the open Blocking Q-IDs | the count of open Defaulted findings | no Blocking or Defaulted finding is open}
- **Source:** <path | pasted>{ - revision of <prior analysis path | pasted prior analysis>}{; dropped: R<n>, ...}{; declined: R<n>, ...}
- **Current system:** {codebase read | task-onboard report | description | none - every system fact assumed}
- **Constraints:** {<as supplied>{ - bears on Q<n>, ...} | none stated}
- **Stack:** {<language> / <framework> | <language> (no framework detected) | <stack> (prompt-stated) | unknown}
- **Blast radius:** {<review-blast-radius's Blast Radius value as printed, any parenthetical included, label dropped> - <the impacted surface in one clause> | n/a - no row has system impact beyond none or UI only}
- **Written for:** <design-audience-calibration's Attribution line>

<requirements-analysis Requirement Register and Findings blocks, their headings included>

## Design Consequences

| Requirements | Impact | What the design must decide | Evidence |
| --- | --- | --- | --- |
| R2, R5 | data model | Order-to-shipment cardinality becomes one-to-many; the design decides where shipment state lives, and orders placed before release follow the answer to Q<n> | `db/schema.rb:88` |

{instead, when no row has system impact beyond `none` or `UI only`: one line saying so}

## Handoff to Design

- **Proceed on:** {<every R-ID neither Gated nor Out of scope; one resting on a Defaulted finding, an Implied row whose open findings are all Defaulted included, carries its Q-ID, taken as assumed> | none}
- **Gated:** {<R-IDs whose Status is not Implied, waiting on Blocking Q-IDs, each with the design area it gates and any Defaulted Q-ID it also rests on> | none}
- **Out of scope until answered:** {<R-IDs whose Status is Implied and that wait on a Blocking finding, each with its Q-IDs> | none}
- **Next:** `/task-design-architecture` or `/task-design-brief` with this analysis as the Requirements analysis input; after the build, pass this file to the code review as `--req`
````

## Self-Check

Applied internally, never emitted in the deliverable.

- [ ] Step 1: behavioral-principles loaded
- [ ] **Step 2:** stack-detect loaded; a request-stated stack honored when detection is `unknown`
- [ ] **Step 3:** current-system facts gathered from the strongest source available, each with its source
- [ ] **Step 4:** one outcome per row, each cited; every system fact cited or marked `(assumed)`; precedent searched before each open question; no finding asks for a mechanism; implied rows proposed, not added; severities keyed to impact class; prior IDs carried on a re-run
- [ ] **Step 5:** every impacted row names what the design must decide; signal atomics loaded; no atomic output block emitted
- [ ] **Step 6:** questions and options in the requester's vocabulary; Written for line present
- [ ] **Step 7:** verdict follows the open Blocking and Defaulted findings; every R-ID lands in exactly one Handoff line

## Avoid

- Designing the solution: choosing mechanisms, drawing components, or naming tables to add
- Defaulting a Blocking finding to keep the design moving
- Treating the PRD as correct because its author is senior, or wrong because its author is not technical
