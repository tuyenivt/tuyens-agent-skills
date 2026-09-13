---
name: task-design-architecture
description: "Design or review architecture: boundaries, failures, consistency, trade-offs, deployment, guardrails, API contracts (RFC 9457), C4 diagrams."
agent: architecture-architect
metadata:
  category: architecture
  tags: [architecture, design, system-design, trade-offs, risk-analysis]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. Then load `Use skill: stack-detect` - the detected stack shapes Sections 3 through 8 and 11 (caching, resiliency, indexing engine, concurrency runtime, observability, compatibility, capacity, API conventions); when no project context exists, use the stack stated in the request. If a delegated skill is unavailable (standalone use), apply the section's inline instructions on judgment and say so in the output. Delegated skills supply analysis method, not structure: this skill's output contract is the only one - absorb their findings into its sections and never emit their own Output blocks. Review Mode is the one exception: it emits `architecture-review-lens`'s structure, as its section says.

# Architecture Design -- Staff Edition

## Purpose

Staff-level architecture design or review prioritizing boundaries, failure containment, and explicit trade-offs. Produces a structured proposal (or review); no implementation code.

## When to Use

- New feature/system design before implementation
- Pre-implementation design review for Staff/Principal sign-off
- Architecture proposal for cross-team changes
- Reviewing an existing design proposal or comparing competing proposals

Not this workflow when the artifact's only consumer is an approver who will not read a 12-section proposal - `task-design-brief` runs the same analysis and emits a two-page reviewer-facing document instead. Run this one when a named consumer needs the full record: an architecture board, a compliance file, or a cross-team contract outliving the change. Invoked directly with an approver-only consumer, say so and run `task-design-brief` instead. The routing is keyed on depth: a `quick` direction check produces three sections and a summary, not a 12-section proposal, and stays here whoever reads it.

## Mode Detection

If the user's input makes mode obvious (e.g., "here's a design doc, review it" or "design a payment service"), proceed. A pasted authored design artifact (design doc, proposal, design spec) with no authoring request is Review Mode even without a verb; a requirements document, PRD, or the user's own rough sketch inside the request is input to New Design, not an artifact to review. Otherwise ask: **new design** (full proposal) or **review existing** (evaluate proposal). Default: New Design.

### New Design Mode

Run the Design Model sections the chosen depth produces (all 12 at `standard`).

### Review Mode

For 2+ proposals on the same problem, or a single artifact weighing two or more alternatives (the lens routes that case here), compare first, then apply Review Mode to the winner.

**Comparing proposals.** Score every proposal on the six criteria from `architecture-review-lens` Step 6 (Boundary clarity, Failure containment, Consistency model, Operability, Reversibility, Cost and complexity) at **Strong / Adequate / Weak / Not addressed / N/A**, each with a one-clause evidence citation; longer reasoning goes in a per-proposal profile as labelled lines - Strongest, Weakest, Constraint conflicts (assumptions conflicting with the problem's constraints) - each on its own line and blank-line separated, or they render as one paragraph. Apply the same criteria to all - missing information scores Not addressed, and the omission itself is the citation. Score stated mechanisms and their direct implications; a performance promise without a mechanism is an assertion. More than three candidates: pre-screen to exactly three against the binding constraints, recording each elimination in one line. When a binding NFR or constraint (a latency target, a delivery deadline, an invariant that must hold) is captured by none of the six criteria, add one problem-specific criterion row named for it, applied to all proposals. Rejected proposals receive scores and citations only - no severities.

State the shared problem and its binding constraints (NFRs, team capacity, volume, timeline) before the matrix, and flag scope mismatch (proposals solving different problems) separately from coverage gap (a proposal omitting criteria) - on mismatch, compare against the full underlying problem. Complementary proposals each solving a real problem resolve to which to fund first - ordered by the same decisive criteria - and the funded proposal is the named winner; the follow-up is recorded in the recommendation with a trigger condition and horizon.

Close with a named winner - a tie is not a valid output. The recommendation names the decisive criteria (those the stated constraints make non-negotiable), the key trade-off accepted, any gaps the winner must close before adoption, and anything worth carrying over from rejected proposals. When the supplied material contains an explicit recommendation from someone other than a proposal's own author (an ADR author's pick among options, a cover note's preference), explicitly agree with or overturn it with reasoning - a proposal advocating itself is not a recommendation, and with no external recommendation the agree/overturn line is omitted. Do not recommend a hybrid when one proposal is clearly stronger, and do not mistake more detail or better polish for more substance.

The comparison emits as a `## Comparison` section between the lens's Intake and Completeness Audit, in order: problem and binding constraints; eliminations (one line each; omitted when no pre-screen ran); criteria matrix; proposal profiles; recommendation as labelled lines - Winner, Decisive criteria, Trade-off accepted, Gaps to close (F-numbers), Carried over, External recommendation (agree | overturn - reason; omitted when none), Follow-up (complementary proposals only: funding order, trigger, horizon) - each on its own line and blank-line separated, or they render as one paragraph. The lens then runs on the winner only (rejected proposals' scores are final); its criteria-scoring step carries the matrix's scores forward, including any added problem-specific criterion, re-scoring a criterion only where lens findings change it - the step is neither skipped nor re-derived from scratch.

Constraints and facts stated in the request are citable evidence (cite: request); a conflict between the winner and the request is a Per-Factor finding citing the request, not an Internal Consistency finding. When no quantitative target exists for a decisive criterion, derive a working target from the stated symptoms, mark it assumed, and carry it into the winner's gaps-to-close. Because a comparison gates selection rather than deployment, a required factor absent - Missing, not Under-specified - because the winning proposal is pre-design (a direction argued before a full design, so sections it never set out to cover are absent) is Major, not Blocker - selection, not deployment, is the decision being made - and is recorded once, as the F-number on its Completeness Audit row, which gaps-to-close and the verdict's required-changes list reference; the expected verdict for a pre-design winner is Approve with changes, and Needs rework is reserved for defects in what the proposal states or absences that would change the selection. Comparison content is not F-numbered - a defect that matters for the winner's review is numbered once, in the owning lens step, and the Comparison references it (forward references to lens steps that follow are expected).

For a single proposal:

Use skill: `architecture-review-lens` for severity taxonomy, intake, completeness audit, internal-consistency check, assumptions audit, per-factor findings, criteria scoring, questions for the author, and verdict.

Supply this design-specific factor list to the completeness audit. The `Required` column names the factors the verdict turns on; a factor the artifact's scope does not reach reads `N/A` with its reason, Required or not, and is not a gap. Every other factor is Present, Under-specified (partial coverage), or Missing, and the lens's own floors set severity - Under-specified Minor at least, Missing Major at least, Blocker when the decision cannot be made without it.

| Factor                        | Required | What "Present" Looks Like                                                                  |
| ----------------------------- | -------- | ------------------------------------------------------------------------------------------ |
| Problem framing and NFRs      | Yes      | Business objective, measurable NFRs, explicit constraints                                  |
| System context and boundaries | Yes      | Upstream/downstream, module boundaries, data ownership                                     |
| Component design              | No       | Named components, responsibilities, failure modes                                          |
| Data and consistency model    | Yes      | Per-boundary consistency, partial-failure behavior, recovery                               |
| Failure mode analysis         | Yes      | Per-component failure modes, blast radius, mitigations                                     |
| Security and auth             | Yes      | Authn/authz model, secret/key rotation, rate limiting and abuse controls                   |
| Observability plan            | No       | Metrics, logs, traces, alerts, SLO candidates                                              |
| Performance and capacity      | No       | Traffic estimates, bottlenecks, scaling model                                              |
| Deployment and rollback       | Yes      | Rollout approach, migration order, rollback trigger                                        |
| Trade-off analysis            | No       | Alternatives considered, why rejected, reversibility                                       |
| Guardrails                    | No       | Architecture constraints implementation must follow                                       |
| API contracts                 | Yes*     | Endpoints, auth per endpoint, idempotency, multi-tenancy, RFC 9457 errors, backward compat, outbound event contracts |
| Diagrams                      | No       | At minimum a C4 Container; sequence/data-flow/deployment when relevant                     |

*Required only when the design exposes an API surface or delivers events/webhooks to consumers outside the design's boundary - another team's service counts as outside.

The factor list mirrors Design Model Sections 1-12 (Security and auth spans Sections 3 and 11): for per-factor depth, compose that section's atomic skills to evaluate the quality of what the author wrote; a factor with no dedicated atomic (Security and auth, Diagrams, multi-tenancy within API contracts) is evaluated directly against its "What Present Looks Like" column. Treat performance, deployment, trade-offs, API contracts, and diagrams as first-class review targets - when Present or Under-specified, evaluate their substance; when Missing, the completeness finding carries them. Depth levels apply to New Design only; reviews always run the full lens, using the lens's own skip rule for steps that do not fit. Compose a section's atomic only where the factor is Present and its quality is what the finding turns on - a Missing factor is settled in the Completeness Audit and needs no atomic. Diagrams are N/A under Section 12's skip conditions and API contracts when the asterisk condition fails; every factor follows the Required rule above.

Output header: `# Architecture Review` and use the output structure defined in `architecture-review-lens` (tables for audits, lists for findings; report depth as "full") - the Completeness Audit table carries Factor, Required, Status (Present / Under-specified / Missing / N/A), a Finding cell (the F-number the row raises or forward-references, the N/A reason, or `-`), and for a raised finding its Severity and Recommendation, as the lens requires wherever a finding is raised. Skip the New Design output template. In this mode the Review Self-Check below replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

- [ ] behavioral-principles loaded first, stack-detect second
- [ ] Comparison, when two or more proposals were supplied: pre-screened to three when more than three came in, each elimination recorded, all scored on the same criteria, a named winner with its decisive criteria, and the external recommendation agreed or overturned when one was supplied
- [ ] All factors audited with Required marking applied; verdict driven by highest severity
- [ ] Specific quality findings recorded once in the correct lens step and numbered
- [ ] Every finding cites a doc section; non-Approve verdict lists required changes

## Inputs

| Input                  | Required | Description                                                       |
| ---------------------- | -------- | ----------------------------------------------------------------- |
| Feature requirements   | Yes      | What the system must do                                           |
| Business context       | No       | Business objective, success criteria, priority                    |
| Existing system sketch | No       | Current architecture, services, and data stores                   |
| Constraints            | No       | Performance, compliance, timeline, legacy, team capacity          |
| Traffic assumptions    | No       | Expected request volume, growth projections, burst profile        |
| Integration needs      | No       | External APIs, third-party services, event sources                |
| Reviewer profile       | No       | Architecture and domain fluency, `High` or `Low` each             |
| Reference doc          | No       | Company template or approved prior design; path or pasted content |
| Depth                  | No       | `quick`, `standard` (default), or `deep` - see Depth Levels below |

Handle partial inputs gracefully. When input is missing, state assumptions under Section 1 Assumptions and list what additional context would strengthen the design under Section 1 Open Questions, together with the confirmation questions `nfr-specification` raises for assumed targets.

**Audience and house format (New Design Mode only).** When a reviewer profile is supplied, or a house pattern is loaded, load `Use skill: design-audience-calibration` (with no profile it calibrates on its recorded default); when a reference doc is supplied or the project's instruction file carries a `## Design Docs` section, load `Use skill: design-reference-pattern`; when it reports `Source: built-in` (a section naming only `Approver:` or `Tool:`), its skeleton is this workflow's own template and only its Approver and Tool values are taken. In Review Mode load neither - the review's reader is the artifact's author, and approver-fit review belongs to `task-design-brief`. `stack-detect` does still run in Review Mode: it grounds the stack-specific guidance a complete design should carry, and lands in the lens's Review Context as a `Stack:` line this workflow adds, never as its own block. Neither changes this workflow's analysis or its 12-section content contract: calibration governs prose, glossing, and what moves to an appendix (its diagrams-before-prose rule yields to this template's Section 12), and the house pattern governs headings (the H1 becomes the house title slot), order, and metadata slots, with every section mapped to a house heading or appended under its own name, unnumbered and placed after the house Appendix in this template's order, and the pattern's Reviewer value in the house reviewers slot or as a metadata line below `Written for` - the one sanctioned exception to the behavioral directive's structure rule. Each numbered heading appears exactly once and in order; a house pattern replaces the numbering wholesale rather than interleaving with it. Required content is never dropped to fit a template: when the calibration budget conflicts with the 12-section contract, the contract wins - load-bearing tables and decisions stay in the body, elaboration moves to the appendix, and the C4 Container outranks the diagram budget, with further diagrams relocating to the appendix rather than dropping. When either is loaded the deliverable carries an appendix - the house Appendix section when one exists, else `## Appendix` as the final section - and the `Written for` / `Format` line in the Output template; unknown metadata slot values read `TBD`. A house pattern carried as front matter stays first, the H1 and the lines below it following. The required-content list is handed over stating that the deliverable carries no appendix for the required content - its appendix holds depth only - so a required item the skeleton cannot house resolves as `appended as <name>`. Where neither a project nor the request names a stack, the header's `Stack:` line reads `unknown` and recommendations stay stack-agnostic rather than assuming one. Depth selects sections; calibration and the house pattern never add one back - a `quick` output carries no diagram, whatever the diagram budget or a house section's diagram-first convention. The required-content list handed to the house pattern is one item per template section (the Staff-Level Summary included), subsection, or field block the depth produces; calibration decides body versus appendix first, then the house pattern places the body content. Settle every item's destination before drafting a heading, and write the resulting heading list out in order first: several template sections may fold into one house heading, and the failure this prevents is inventing a numbered heading the house skeleton does not have. Numbering comes from the house skeleton alone - never extend it.

## Depth Levels

| Depth      | When to Use                                                                      | Sections Produced                                                      |
| ---------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `quick`    | Early ideation, async review, or "is this direction sensible?" check             | Problem framing + boundaries + top 1-2 trade-offs + Staff-Level Summary |
| `standard` | Default - pre-implementation design for Staff/Principal sign-off                 | All 12 sections + Staff-Level Summary (API contracts, C4 Container included) |
| `deep`     | Large cross-team changes, capacity-sensitive systems, or post-incident redesigns | Everything at `standard` + capacity model + failure simulation + evolution notes + extra diagrams |

Default: `standard`. Use `quick` for "rough architecture" or "is this direction sensible"; use `deep` for cross-team changes, capacity-sensitive systems, or post-incident redesigns. Deep adds the Capacity Model, Failure Simulation, and Evolution Notes sections in the Output template plus extra diagrams beyond C4 Container.

The Staff-Level Summary ships at every depth. At `quick`, produce template Sections 1, 2, and 9 (top 1-2 decisions only) plus the Staff-Level Summary, keeping template numbering (house headings replace it when a house pattern is loaded); Section 1 elicits only the NFRs those decisions depend on and lists the rest under Open Questions (overriding `nfr-specification`'s every-field rule at this depth); Section 2 covers the boundaries the decision touches plus any caller whose facts change it; omit the other sections silently and waive their Self-Check items. For "is this direction sensible?" inputs, place a one-line verdict immediately below the H1, above any house metadata table: **Direction: {Sensible | Sensible with changes | Reconsider}** - {reason}: Sensible with changes when the proposed mechanism holds with named changes, Reconsider when the mechanism is rejected even though the goal stands. The Self-Check is applied internally, never emitted in the deliverable.

## Rules

- Boundaries and data ownership first, not classes or endpoints
- Every component states a primary failure mode and isolation guarantee
- Every significant decision states at least one trade-off and one rejected alternative with reason
- No implementation code; describe components, responsibilities, and interactions
- Make conflicting constraints explicit; propose resolution options
- Omit empty sections and subsection tables silently; a house heading with no mapped content is kept and carries one line saying why it is empty, since the house skeleton is reproduced in full - except Sections 11 and 12, which require an explicit skip one-liner at the depths where they run - their conditional subsections are omitted silently like any other; output is strategic, concise, high-signal

## Design Model

### 1. Problem Framing

**Run first. This frames the entire design.**

Capture:

- **Business objective** -- what business outcome does this serve
- **Functional scope** -- what must the system do (in / out of scope)
- **Constraints** -- technical debt, legacy systems, team capacity, timeline, budget
- **Assumptions** -- what is assumed true but not yet validated

Use skill: `nfr-specification` to elicit and structure non-functional requirements into measurable SLOs and constraints - its Performance and Availability tables fill the Non-Functional Requirements table one row per metric, and its Scalability, Security, Operability and Data field blocks contribute their stated values as rows in the same table - a field with no stated or derivable target gets its row reading `not specified`, the atomic's own value, never an invented figure. Its Conflicts (with resolution options) go under Constraints, its Gaps under Open Questions. The NFR output feeds into Section 6 (Observability) as alert baselines and Section 7 (Performance) as capacity targets.

### 2. System Context and Boundaries

Use skill: `system-boundary-design` for formal boundary modeling. Use skill: `architecture-guardrail` for the boundary violations it detects in the current codebase; restate each as a forward constraint in Section 10's Architecture Constraints, or at `quick` in the Must Not Cross cell. It emits review findings, not authored rules - on a greenfield design with no code to inspect, derive the constraints from Section 2's boundaries instead and say so. Use skill: `review-blast-radius` to size a Shared cell in Boundary Contracts - run as if the boundary's own change were the diff; its overall `Blast Radius:` value only.

For each boundary state: what crosses (data, commands, events), what must NOT cross (domain internals), failure isolation guarantee.

### 3. Architecture Overview

Use skill: `architecture-data-consistency` for consistency boundary design. Use skill: `backend-idempotency` for retry safety at integration points. Use skill: `backend-caching` for caching strategy and invalidation. Use skill: `ops-resiliency` for fault tolerance and REST client integration patterns.

For each component, state: what it owns (data, state), what it depends on, primary failure mode. State the security model once here - authn mechanism, authz enforcement point, secret/key rotation, rate limiting and abuse controls; per-endpoint auth stays in Section 11. The component, communication, and caching tables plus the Security Model block in the Output template are the contract; the Communication Model's Pattern and Notes cells copy `system-boundary-design`'s Pattern and Trade-off strings verbatim, transport named alongside.

### 4. Data and Consistency Model

Use skill: `architecture-data-consistency` for consistency strategy selection. Use skill: `backend-db-indexing` for data access patterns and index strategy - recorded in Data Flow as the lookups each path relies on, each carrying the atomic's recommended index and lock-risk line as a sub-bullet.

For each data boundary: consistency guarantee, partial-failure behavior, recovery mechanism. Name the distributed consistency strategy when applicable (outbox, saga, compensating transactions). The Data Flow, Consistency Boundaries, Saga Steps, and Schema Evolution blocks in the Output template are the contract; `architecture-data-consistency`'s Schema Evolution Plan fills the last.

### 5. Failure and Risk Analysis

Use skill: `ops-failure-classification` for its Failure Type vocabulary only, in the Scenario column - its block, Evidence line included, is not emitted here. Use skill: `failure-propagation-analysis` for cascading paths. Use skill: `review-blast-radius` for impact scope per scenario. Use skill: `ops-resiliency` for mitigation patterns. Use skill: `architecture-concurrency` for concurrency risk.

For each high-risk scenario: failure mode, blast radius (Narrow / Moderate / Wide / Critical), mitigation. Cover backpressure and retry amplification explicitly - hand-waved retry storms are a common cause of cascading failure.

### 6. Observability Plan

Use skill: `ops-observability` for logging, metrics, and tracing patterns.

Produce: RED metrics per component boundary, trace span coverage across service boundaries, liveness/readiness checks, alert conditions with severity, and at least one SLO candidate tied to user-facing quality in the SLO Candidate block. SLO baselines come from Section 1 NFRs.

### 7. Performance and Capacity

Use skill: `architecture-capacity` for throughput estimation and bottleneck identification. Use skill: `backend-caching` for cache-based load reduction. Use skill: `backend-db-indexing` for query performance - feeds Bottleneck Prediction.

The bottleneck (component saturating first) and the scaling model are non-optional; every queue- or batch-fed component gets a Queue Depth line. At `standard`, coarse numbers suffice: stated or derived RPS (steady and peak) and the binding bottleneck with its approximate saturation point; the per-component capacity model is deep-only. Name cost drivers when scaling has material cost implications.

### 8. Deployment Strategy

Use skill: `ops-release-safety` for rollout and rollback patterns. Use skill: `dependency-impact-analysis` for deployment ordering.

The rollback trigger (specific condition, not "if something goes wrong") and the migration order vs. code deploy are the load-bearing decisions. Name the rollout mechanism (`ops-release-safety`'s enum: feature flag, canary, blue-green, rolling update, one-shot script, big bang as proposed) and feature flags by purpose.

### 9. Trade-Off Analysis

Use skill: `tradeoff-analysis` for structured decision documentation.

For each significant decision: chosen option, alternatives, reasons, what is sacrificed, reversibility, risk-of-being-wrong, and an observable review trigger. Flag Hard-reversibility decisions (messaging broker, consistency model, primary storage, async vs sync) under a **Significant Decisions** subsection - a bullet list referencing the decision tables, not duplicates of them - and require an ADR before implementation.

### 10. Guardrails and Review Guidance

Use skill: `architecture-guardrail` for the violations it detects; each becomes a forward constraint here. Use skill: `ops-engineering-governance` for evolving existing guardrails - enforcement tiers, and its category prefix (`[new]`, `[strengthen]`, `[automate]`, `[broaden]`, `[retire]`) on the Constraint cell and its Enforcement value (`checklist (automate: <mechanism>)` when manual) in the Enforcement column; its incident-evidence bound and its Guardrails That Held section do not apply to a design, whose constraints trace to Section 2's boundaries instead. Also produce the Review Checklist Additions (one item per constraint a reviewer cannot detect mechanically) and the Drift Detection Points (the signal that says a constraint is eroding).

Each constraint must be concrete and detectable: rule, what violation looks like, consequence - at least one guardrail per module (per Module Boundaries row). "Follow clean architecture" is not a guardrail; "no module under `domain/` may import from `infrastructure/`" is. Include AI-codegen constraints when patterns must be enforced on generated code.

### 11. API Contracts

Run at `standard` and `deep` for any design exposing APIs to external clients, services, or browsers, or delivering events/webhooks to consumers outside the design's boundary. Skip with a one-liner only if neither surface exists (e.g., "Internal worker; no external consumers").

Use skill: `backend-api-guidelines` for HTTP semantics, naming, pagination, RFC 9457 errors, idempotency; the multi-tenancy pattern comes from Section 3's Security Model. Use skill: `ops-backward-compatibility` for versioning and breaking-change classification.

The output template (Section 11 in Output) lists the per-endpoint fields the design must produce: endpoint table (method, path, auth, request - including the pagination parameters on every collection endpoint - response, status), idempotency table for state-sensitive endpoints, multi-tenancy pattern, RFC 9457 error examples, and a backward-compatibility table when modifying existing APIs. Treat these as first-class - reviewers must be able to evaluate auth, idempotency, multi-tenancy, and pagination from the proposal alone. Section 11's idempotency table is authoritative for the HTTP endpoints this design exposes - the Communication Model row for their caller (one row per caller-callee pair, not per endpoint) writes "see Section 11" in the Idempotent cell; every other row (events, queues, outbound HTTP calls to external systems) states Yes/No with its mechanism in Notes. Inbound third-party webhooks fit the endpoint table with auth = signature verification (e.g., Stripe-Signature). Outbound events and webhooks delivered to external consumers are contracts too: the Outbound Events / Webhooks table documents payload schema version, receiver-side auth (e.g., HMAC signature header), ordering, and retry/redelivery semantics. Section 8's Backward Compatibility field summarizes deploy-level compatibility; API-change detail lives in Section 11's table.

### 12. Diagrams

Run at `standard` and `deep`. Skip with a one-liner only if a current accurate diagram exists or the design is too narrow to diagram meaningfully.

Default format: **Mermaid**. Use **PlantUML** only when explicitly requested.

Always: **C4 Container** (major deployable units + tech). When applicable: **C4 Context** (3+ external interactors), **Sequence** (non-obvious ordering or async/sync semantics), **Data flow** (multiple paths through the system), **Deployment** (multi-region, VPC, networking).

**Rules:**

- Every element traces to a component or boundary from Sections 2-3; never invent elements to "complete" the diagram
- One abstraction level per diagram: a Container diagram shows containers, not the internals of one. The actors and external systems at the system boundary belong on it and are not a level mix
- One `Diagram Notes` block after the last diagram (a house pattern may separate them), one sub-list per diagram carrying Scope / Assumptions / Next level and, for the container diagram, the form used; assumptions go in Notes, not silently inside the diagram

Use Mermaid: `C4Container` for C4, `sequenceDiagram` with `autonumber` for sequence, `flowchart LR/TD` for data flow, nested `subgraph` blocks for deployment topology. Mermaid's C4 support is still experimental; where the renderer does not carry it, a `flowchart` showing the same containers, actors and external systems satisfies the requirement - say which form was used in Diagram Notes.

## Output

````markdown
# Architecture Design Proposal

**Direction: {Sensible | Sensible with changes | Reconsider}** - {reason} _(only for `quick` "is this direction sensible?" inputs)_

Stack: {<language / framework> (detected) | <stack> (prompt-stated) | unknown - recommendations stay stack-agnostic}

Written for: {reader} (Architecture {High | Low}, {source}; Domain {High | Low}, {source}). Format: {house reference | built-in} _(only when calibration or the house pattern was loaded; below the Direction line, above any house metadata table; below house front matter. With a house pattern but no reviewer profile, the axes take `design-audience-calibration`'s default - Architecture Low, Domain High - with the source recorded as `assumed default`)_

## 1. Problem Framing

Business Objective:

Functional Scope:

Non-Functional Requirements:

| Category | Metric | Target | Measurement | Notes |
| -------- | ------ | ------ | ----------- | ----- |
| Performance / Availability / Scalability / Security / Operability / Data | p99 latency, RPO, uptime SLO, ... | Measurable threshold | How it is measured | (assumed: basis) when defaulted |

Constraints:

- Conflict: {tension} - options: {a} / {b}
- Infeasible: {target} - achievable frontier: {value}

Assumptions:

Open Questions:

## 2. System Context and Boundaries

System Context:

Upstream Dependencies:

Downstream Consumers:

### Module Boundaries

| Module | Owner | Responsibility | Data Owned | Failure Isolation |
| ------ | ----- | -------------- | ---------- | ----------------- |
| Name   | Team, or TBD | What it does | Entities | Guarantee |

**Ownership Rationale:** {each contested entity, the boundary it went to, and the write that decided it; "none - every placement follows from data ownership" when clear}

### Boundary Contracts

| Boundary | Crosses     | Must Not Cross          | Failure Propagation |
| -------- | ----------- | ----------------------- | ------------------- |
| A -> B   | Data/events | Internal implementation | Isolated / Shared: Narrow/Moderate/Wide/Critical |

## 3. Architecture Overview

### Components

| Component          | Responsibility                                   | Owns                             | Depends On                      | Primary Failure Mode                   |
| ------------------ | ------------------------------------------------ | -------------------------------- | ------------------------------- | -------------------------------------- |
| Name               | One sentence                                     | Data/state                       | Components                      | How it fails                           |
| NotificationRouter | Routes notifications to channel-specific senders | routing rules, template registry | ChannelSenders, TemplateService | Channel sender timeout; queues back up |

### Communication Model

| Interaction | Type       | Pattern          | Idempotent | Notes             |
| ----------- | ---------- | ---------------- | ---------- | ----------------- |
| A -> B      | Sync/Async | {Sync API \| Async event \| Shared cache \| Data replication \| Direct DB read (violation)} | {Yes \| No \| see Section 11} | Trade-off string; transport (REST, gRPC, Kafka); timeout, fallback |

### Caching Strategy

| Cache Target | Level | TTL      | Invalidation  | Staleness Tolerance | Memory Bound | Stampede Risk                |
| ------------ | ----- | -------- | ------------- | ------------------- | ------------ | ---------------------------- |
| What         | In-process / Distributed / CDN | How long | How refreshed | Acceptable lag | Key count or bytes, eviction policy | Low/Medium/High - mitigation |

### Security Model

Authentication:

Authorization enforcement point:

Secret and key rotation:

Rate limiting and abuse controls:

## 4. Data and Consistency Model

### Data Flow

[Describe request path, event path, batch path; per lookup a sub-bullet `Recommended index: <index> - Lock risk: <line>` from backend-db-indexing]

### Consistency Boundaries

| Boundary | Pattern | Consistency Model | Staleness Tolerance | Partial Failure Behavior | Recovery Mechanism |
| -------- | ------- | ----------------- | ------------------- | ------------------------ | ------------------ |
| A -> B   | database transaction / shared transaction / outbox + events / saga (orchestrated or choreographed) / CQRS + async sync / region-local strong + async replication / dual-field contract versioning | {Strong \| Eventual \| Version-skew} | Acceptable lag | What happens, the tolerated anomaly, and how concurrent writers resolve | How to recover |

### Saga Steps _(when a saga is named)_

| Step | Forward Action | Compensation | Idempotency Key |
| ---- | -------------- | ------------ | --------------- |
| Name | What it does | How it unwinds \| `pivot - go/no-go, no compensation defined` \| `none - retry until success` (post-pivot) | Key and scope |

### Schema Evolution

[Strategy for backward-compatible schema changes; an expand-contract sequence as a Phase / Change / Verify-before-next table]

## 5. Failure and Risk Analysis

### Failure Scenarios

| Scenario            | Component | Blast Radius         | Mitigation                |
| ------------------- | --------- | -------------------- | ------------------------- |
| External dependency failure | Name | Narrow/Moderate/Wide/Critical | Circuit breaker, fallback |
| Transaction boundary error  | Name | Scope | Mechanism |
| Resource exhaustion         | Name | Scope | Mechanism |

### Concurrency Risks

| Risk          | Component | Severity              | Mitigation          |
| ------------- | --------- | --------------------- | ------------------- |
| Specific risk | Name      | {High \| Medium \| Low} | Specific mitigation |

### Retry Amplification

[Assessment of retry storms and backpressure risks]

## 6. Observability Plan

### Metrics

| Metric       | Component | Type                                  | Alert Threshold | Alert Severity |
| ------------ | --------- | ------------------------------------- | --------------- | -------------- |
| request_rate | Name      | RED / Business / Saturation / Absence | Condition       | Page / Ticket / Info |

### Tracing

[Trace span coverage and correlation strategy]

### Health Checks

| Check | Type     | Dependency | Failure Action |
| ----- | -------- | ---------- | -------------- |
| Name  | Liveness | What       | What happens   |

### SLO Candidate

SLI:

SLO:

Error budget:

Burn-rate alert:

Latency, saturation, and absence alerts: {one line each, or `none - <why>`}

## 7. Performance and Capacity

Capacity Verdict: {Within capacity and headroom met | Within capacity, headroom short | Over capacity at current steady load | Over capacity at current peak | Over capacity at projected steady load | Over capacity at projected peak} - lead with this when the bottleneck is already saturated

Traffic Estimate: {stated or derived; say which}

Scaling Model:

Bottleneck Prediction:

Headroom Target: {multiplier over peak, or over long-run average demand for queue-absorbed work, and the usable-capacity derate applied}

Queue Depth: {per queue- or batch-fed component: producer rate, effective consumer rate, peak backlog, recovery time, max depth before back-pressure | none - no queue-fed component}

Next Bottleneck Once Mitigated:

Cost Drivers:

## 8. Deployment Strategy

Rollout Approach: {Feature flag | Canary | Blue-green | Rolling update | One-shot script | Big bang (as proposed)}

Backward Compatibility: {Yes | No | N/A - no schema change} - {summary}

DB Migration Order:

Rollback Plan:

Rollback Trigger:

Rollback Speed: {Instant | Fast (minutes) | Moderate | Slow | None past the point of no return}

Point of No Return: {the step after which rollback becomes roll-forward, or none}

Affected Services:

Deployment Order: {from dependency-impact-analysis | Single deploy; ordering is not the risk - <the verification that is>}

Feature Flags:

## 9. Trade-Off Analysis

### Decision: [Decision Name]

| Aspect        | Detail                     |
| ------------- | -------------------------- |
| Chosen        | What was selected          |
| Alternatives  | What was considered        |
| Reason        | Why this option            |
| Rejected      | Why not alternatives       |
| Trade-off     | What is sacrificed         |
| Reversibility | Easy / Moderate / Hard - work to reverse |
| Risk          | What could make this wrong |
| Unknowns      | Facts the decision needs and does not have, or none |
| Review Trigger | Observable condition that says revisit |

### Significant Decisions

- {Decision name} - Hard reversibility; ADR required before implementation

## 10. Guardrails and Review Guidance

### Architecture Constraints

| Constraint    | Violation Looks Like    | Consequence | Enforcement |
| ------------- | ----------------------- | ----------- | ----------- |
| Specific rule | How to detect violation | What breaks | CI gate / lint rule / policy-as-code / architecture test / framework constraint / alert / dashboard / SLO / checklist / review policy / contract term |

### Review Checklist Additions

- [ ] Item specific to this design
- [ ] Item specific to this design

### Drift Detection Points

- Signal to watch for erosion

## 11. API Contracts

_Skip with a one-liner if the design exposes neither HTTP endpoints nor externally consumed events._

### Endpoints

| Method | Path           | Description  | Auth | Request         | Response            | Status |
| ------ | -------------- | ------------ | ---- | --------------- | ------------------- | ------ |
| GET    | /api/v1/orders | List orders  | USER | `cursor`, `limit` | `{ items[], next_cursor }` | 200    |
| POST   | /api/v1/orders | Create order | USER | order payload, `Idempotency-Key` | created order | 201, 400 missing key, 409 in flight, 422 body mismatch |

### Idempotency

| Endpoint              | Idempotency | Mechanism                           |
| --------------------- | ----------- | ----------------------------------- |
| POST /api/v1/orders   | Required    | Idempotency-Key header, 24h window  |

### Multi-Tenancy

Pattern: [Path segment | JWT claim | Header X-Tenant-ID | Single-tenant - N/A]

Isolation enforced at: [middleware / repository / both]

Rate limits: per-tenant or global

### Error Format

RFC 9457 problem details; example bodies for the error statuses the API actually returns (typically 400, 404, 409, 422).

### Outbound Events / Webhooks _(when the design delivers events or webhooks to external consumers)_

| Contract        | Schema / Version                  | Receiver Auth         | Ordering          | Retry / Redelivery               |
| --------------- | --------------------------------- | --------------------- | ----------------- | -------------------------------- |
| invoice.paid v1 | Versioned envelope, additive-only | HMAC signature header | Per-endpoint FIFO | Backoff schedule, dead-letter    |

### Backward Compatibility (if modifying existing API)

| Change | Contract Type | Direction | Consumers (evidence) | Compatible | Impact | Migration Path |
| ------ | ------------- | --------- | -------------------- | ---------- | ------ | -------------- |
| ...    | REST API / Event schema / DB schema / Shared library / other | out / in / db | ... | Yes / No / No (unverified) | ... | ... |

## 12. Diagrams

_Skip with a one-liner if a current diagram already exists or the design is too narrow to diagram meaningfully._

### Container Diagram (C4)

```mermaid
{Mermaid C4Container code showing major deployable units, data stores, queues, and external systems}
```

### Sequence Diagram - {Flow name} _(when ordering or async/sync semantics are non-obvious)_

```mermaid
{Mermaid sequenceDiagram code for the flow}
```

### Data Flow / Deployment _(include when applicable)_

```mermaid
{Mermaid flowchart or deployment subgraph code}
```

### Diagram Notes

- **{Diagram name}** ({C4Container | flowchart fallback}, container diagram only)
  - **Scope:**
  - **Assumptions:**
  - **Next level:**

## Staff-Level Summary

Each bullet should be specific to this design, not generic advice. Example: 'Key systemic risks: Retry amplification from SMS provider timeouts can overload the outbox worker under burst load.'

- Key systemic risks:
- Long-term evolution notes:
- Areas requiring strict review:

## Capacity Model

_Deep only._

| Component | Limit (native unit) | Per-Request Cost (native unit) | Expected RPS | Peak RPS | Saturation Point | Bottleneck? | Scaling Action |
| --------- | ------------------- | ------------------------------ | ------------ | -------- | ---------------- | ----------- | -------------- |
| Name      | N                   | N                              | N            | N        | N RPS / 0 above current load / N/A (not limiting) | Yes / No / Also below demand | Scale out / up |

## Failure Simulation

_Deep only._

### Scenario 1: {Most likely high-impact failure}

Walk through the failure end-to-end:

1. {Component} fails due to {cause}
2. {Propagation path} - {affected component}
3. {User-visible impact}
4. {Mitigation that activates}
5. {Recovery path}

**Blast radius:** {Narrow | Moderate | Wide | Critical}

**MTTR estimate:** {minutes / hours}

**Gap identified:** {What the design is missing to contain this faster}

[Repeat for 1-2 additional scenarios in deep mode]

## Evolution Notes

_Deep only._

- **If traffic doubles**: {What saturates first, what to scale, what must be redesigned}
- **If {key dependency} is removed**: {What breaks, what the fallback is}
- **If team size changes significantly**: {What becomes hard to maintain, what should be simplified}

## Appendix

_Present whenever calibration or a house pattern was loaded; the house Appendix heading when one exists. Holds elaboration relocated from the body, each topic with one line saying why it sits here. Appended sections follow it, unnumbered, each with its one-line reason._
````

## Self-Check

- [ ] behavioral-principles loaded first, stack-detect second
- [ ] Every module boundary states responsibility, data ownership, and isolation guarantee
- [ ] Every component lists primary failure mode
- [ ] Every significant decision has a rejected alternative with reason; trade-offs include negatives; each carries a review trigger
- [ ] Consistency model stated per data boundary, with partial-failure behavior
- [ ] Highest-blast-radius scenario has a mitigation; retry amplification and backpressure assessed
- [ ] Rollback strategy and rollback trigger present; observability plan names an SLO candidate
- [ ] Guardrails are concrete, detectable rules (one per module boundary minimum)
- [ ] Security Model block states authn, authz enforcement point, secret rotation, and abuse controls
- [ ] Section 11 produced if any API surface exists: auth per endpoint, RFC 9457 errors, idempotency on state-mutating endpoints, pagination on collections, multi-tenancy if applicable; outbound event/webhook contracts documented when the design delivers them
- [ ] Section 12 produced at standard/deep, or its skip one-liner: at minimum a C4 Container diagram; every diagram element traces to a component/boundary defined in Sections 2-3; Diagram Notes state scope, assumptions, and next level per diagram
- [ ] Section 1 states the problem, the NFRs the design is accountable to, and the constraints; unmet NFRs listed under Open Questions rather than assumed
- [ ] Section 7 names the binding bottleneck and the scaling model at every depth where it runs, not only at deep
- [ ] Heading list settled before drafting; every numbered heading appears exactly once, comes from the house skeleton or the template rather than being invented, and runs in order; appended sections sit after the appendix, unnumbered, each with its one-line reason
- [ ] Staff-Level Summary present at every depth, each bullet specific to this design; the Direction line present on a quick direction check
- [ ] Design grounded in stated requirements - no hypothetical future scope
- [ ] If depth = deep: capacity model per component, 2+ failure scenarios simulated, evolution notes cover traffic doubling, sequence/data-flow/deployment diagrams added where applicable

## Avoid

- Class-level design or over-specifying internal component structure
- Architecture astronautics; designing for unstated future requirements
- Generic advice ("use microservices", "add caching") without context-specific reasoning
- Verbose prose where a table communicates more clearly
