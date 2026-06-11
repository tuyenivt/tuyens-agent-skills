---
name: task-design-architecture
description: "Design or review architecture: boundaries, failures, consistency, trade-offs, deployment, guardrails, API contracts (RFC 9457), C4 diagrams."
metadata:
  category: architecture
  tags: [architecture, design, system-design, trade-offs, risk-analysis]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. Then load `Use skill: stack-detect` - the detected stack shapes Section 3 (caching, resiliency), Section 7 (capacity), and Section 11 (API conventions); when no project context exists, use the stack stated in the request. If a delegated skill is unavailable (standalone use), apply the section's inline instructions on judgment and say so in the output.

# Architecture Design -- Staff Edition

## Purpose

Staff-level architecture design or review prioritizing boundaries, failure containment, and explicit trade-offs. Produces a structured proposal (or review); no implementation code.

## When to Use

- New feature/system design before implementation
- Pre-implementation design review for Staff/Principal sign-off
- Architecture proposal for cross-team changes
- Reviewing an existing design proposal or comparing competing proposals

## Mode Detection

If the user's input makes mode obvious (e.g., "here's a design doc, review it" or "design a payment service"), proceed. A pasted authored artifact (design doc, proposal, spec) with no authoring request is Review Mode even without a verb; the user's own rough sketch or idea inside the request is input to New Design, not an artifact to review. Otherwise ask: **new design** (full proposal) or **review existing** (evaluate proposal). Default: New Design.

### New Design Mode

Run the Design Model sections the chosen depth produces (all 12 at `standard`).

### Review Mode

For 2+ proposals on the same problem: use `architecture-proposal-compare` first, then apply Review Mode to the recommended proposal.

For a single proposal:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Supply this design-specific factor list to the completeness audit. Required factors carry no severity cap (Missing - or critically under-specified - required factors may be Blockers); advisory (No) factors cap at Major:

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
| API contracts                 | Yes*     | Endpoints, auth per endpoint, idempotency, multi-tenancy, RFC 9457 errors, backward compat |
| Diagrams                      | No       | At minimum a C4 Container; sequence/data-flow/deployment when relevant                     |

*Required only when the design exposes an API surface.

The factor list mirrors Design Model Sections 1-12 (Security and auth spans Sections 2, 3, and 11): for per-factor depth, compose that section's atomic skills to evaluate the quality of what the author wrote. Treat performance, deployment, trade-offs, API contracts, and diagrams as first-class review targets - when Present or Under-specified, evaluate their substance; when Missing, the completeness finding carries them. Depth levels apply to New Design only; reviews always run the full lens, using the lens's own skip rule for steps that do not fit.

Output header: `# Architecture Review` and use the output structure defined in `architecture-review-lens` (tables for audits, lists for findings; report depth as "full"). Skip the New Design output template. In this mode the Review Self-Check below replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

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
| Depth                  | No       | `quick`, `standard` (default), or `deep` - see Depth Levels below |

Handle partial inputs gracefully. When input is missing, state assumptions explicitly and flag what additional context would strengthen the design.

## Depth Levels

| Depth      | When to Use                                                                      | Sections Produced                                                      |
| ---------- | -------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| `quick`    | Early ideation, async review, or "is this direction sensible?" check             | Problem framing + boundaries + top 1-2 trade-offs only                 |
| `standard` | Default - pre-implementation design for Staff/Principal sign-off                 | All 12 sections (API contracts, C4 Container diagram included)         |
| `deep`     | Large cross-team changes, capacity-sensitive systems, or post-incident redesigns | All 12 sections + capacity model + failure simulation + extra diagrams |

Default: `standard`. Use `quick` for "rough architecture" or "is this direction sensible"; use `deep` for cross-team changes, capacity-sensitive systems, or post-incident redesigns. Deep adds the Capacity Model, Failure Simulation, and Evolution Notes sections in the Output template plus extra diagrams beyond C4 Container.

The Staff-Level Summary ships at every depth. At `quick`, produce template Sections 1, 2, and 9 (top 1-2 decisions only) plus the Staff-Level Summary, keeping template numbering; omit the rest silently and waive their Self-Check items. For "is this direction sensible?" inputs, place a one-line verdict immediately below the H1: **Direction: {Sensible | Sensible with changes | Reconsider}** - {reason}. The Self-Check is applied internally, never emitted in the deliverable.

## Rules

- Boundaries and data ownership first, not classes or endpoints
- Every component states a primary failure mode and isolation guarantee
- Every significant decision states at least one trade-off and one rejected alternative with reason
- No implementation code; describe components, responsibilities, and interactions
- Make conflicting constraints explicit; propose resolution options
- Omit empty sections silently - except Sections 11 and 12, which require an explicit skip one-liner at the depths where they run; output is strategic, concise, high-signal

## Design Model

### 1. Problem Framing

**Run first. This frames the entire design.**

Capture:

- **Business objective** -- what business outcome does this serve
- **Functional scope** -- what must the system do (in / out of scope)
- **Constraints** -- technical debt, legacy systems, team capacity, timeline, budget
- **Assumptions** -- what is assumed true but not yet validated

Use skill: `nfr-specification` to elicit and structure non-functional requirements into measurable SLOs and constraints. The NFR output feeds into Section 6 (Observability) as alert baselines and Section 7 (Performance) as capacity targets.

### 2. System Context and Boundary Definition

Use skill: `system-boundary-design` for formal boundary modeling.
Use skill: `architecture-guardrail` for boundary rules.
Use skill: `review-blast-radius` for failure propagation scope.

For each boundary state: what crosses (data, commands, events), what must NOT cross (domain internals), failure isolation guarantee.

### 3. Architecture Overview

Use skill: `architecture-data-consistency` for consistency boundary design.
Use skill: `backend-idempotency` for retry safety at integration points.
Use skill: `backend-caching` for caching strategy and invalidation.
Use skill: `ops-resiliency` for fault tolerance and REST client integration patterns.

For each component, state: what it owns (data, state), what it depends on, primary failure mode. The component, communication, and caching tables in the Output template are the contract.

### 4. Data and Consistency Model

Use skill: `architecture-data-consistency` for consistency strategy selection.
Use skill: `backend-db-indexing` for data access patterns and index strategy.

For each data boundary: consistency guarantee, partial-failure behavior, recovery mechanism. Name the distributed consistency strategy when applicable (outbox, saga, compensating transactions). The consistency-boundaries table in the Output template is the contract.

### 5. Failure Mode and Risk Analysis

Use skill: `ops-failure-classification` for failure type categorization.
Use skill: `failure-propagation-analysis` for cascading paths.
Use skill: `review-blast-radius` for impact scope per scenario.
Use skill: `ops-resiliency` for mitigation patterns.
Use skill: `architecture-concurrency` for concurrency risk.

For each high-risk scenario: failure mode, blast radius (Narrow / Moderate / Wide), mitigation. Cover backpressure and retry amplification explicitly - hand-waved retry storms are a common cause of cascading failure.

### 6. Observability Plan

Use skill: `ops-observability` for logging, metrics, and tracing patterns.

Produce: RED metrics per component boundary, trace span coverage across service boundaries, liveness/readiness checks, alert conditions with severity, and at least one SLO candidate tied to user-facing quality. SLO baselines come from Section 1 NFRs.

### 7. Performance and Capacity Considerations

Use skill: `architecture-capacity` for throughput estimation and bottleneck identification.
Use skill: `backend-caching` for cache-based load reduction.
Use skill: `backend-db-indexing` for query performance.

The bottleneck (component saturating first) and the scaling model are non-optional. At `standard`, coarse numbers suffice: stated or derived RPS (steady and peak) and the binding bottleneck with its approximate saturation point; the per-component capacity model is deep-only. Name cost drivers when scaling has material cost implications.

### 8. Deployment and Release Strategy

Use skill: `ops-release-safety` for rollout and rollback patterns.
Use skill: `dependency-impact-analysis` for deployment ordering.

The rollback trigger (specific condition, not "if something goes wrong") and the migration order vs. code deploy are the load-bearing decisions. Name the rollout mechanism (canary, blue-green, feature flag) and feature flags by purpose.

### 9. Trade-Off Analysis

Use skill: `tradeoff-analysis` for structured decision documentation.

For each significant decision: chosen option, alternatives, reasons, what is sacrificed, reversibility, risk-of-being-wrong. Flag High-reversibility-cost decisions (messaging broker, consistency model, primary storage, async vs sync) under a **Significant Decisions** subsection - a bullet list referencing the decision tables, not duplicates of them - and require an ADR before implementation.

### 10. Guardrails and Review Guidance

Use skill: `architecture-guardrail` for boundary enforcement rules.
Use skill: `ops-engineering-governance` for evolving existing guardrails.

Each constraint must be concrete and detectable: rule, what violation looks like, consequence - at least one guardrail per module (per Module Boundaries row). "Follow clean architecture" is not a guardrail; "no module under `domain/` may import from `infrastructure/`" is. Include AI-codegen constraints when patterns must be enforced on generated code.

### 11. API Contracts

Run at `standard` and `deep` for any design exposing APIs to external clients, services, or browsers. Skip with a one-liner only if there is no HTTP surface (e.g., "Internal event-driven worker").

Use skill: `backend-api-guidelines` for HTTP semantics, naming, pagination, RFC 9457 errors, idempotency, multi-tenancy patterns.
Use skill: `ops-backward-compatibility` for versioning and breaking-change classification.

The output template (Section 11 in Output) lists the per-endpoint fields the design must produce: endpoint table (method, path, auth, request, response, status), idempotency table for state-sensitive endpoints, multi-tenancy pattern, RFC 9457 error examples, and a backward-compatibility table when modifying existing APIs. Treat these as first-class - reviewers must be able to evaluate auth, idempotency, multi-tenancy, and pagination from the proposal alone. Section 11's idempotency table is authoritative for HTTP endpoints - Communication Model rows for HTTP interactions write "see Section 11" in the Idempotent cell; the column itself covers non-HTTP interactions (events, queues). Inbound third-party webhooks fit the endpoint table with auth = signature verification (e.g., Stripe-Signature). Section 8's Backward Compatibility field summarizes deploy-level compatibility; API-change detail lives in Section 11's table.

### 12. Diagrams

Run at `standard` and `deep`. Skip with a one-liner only if a current accurate diagram exists or the design is too narrow to diagram meaningfully.

Default format: **Mermaid**. Use **PlantUML** only when explicitly requested.

Always: **C4 Container** (major deployable units + tech).
When applicable: **C4 Context** (3+ external interactors), **Sequence** (non-obvious ordering or async/sync semantics), **Data flow** (multiple paths through the system), **Deployment** (multi-region, VPC, networking).

**Rules:**

- Every element traces to a component or boundary from Sections 2-3; never invent elements to "complete" the diagram
- One abstraction level per diagram (no Context/Container mixing)
- Diagram Notes (Scope / Assumptions / Next level) accompany each diagram; assumptions go in Notes, not silently inside the diagram

Use Mermaid's standard syntax: `C4Container` for C4, `sequenceDiagram` with `autonumber` for sequence, `flowchart LR/TD` for data flow, nested `subgraph` blocks for deployment topology.

## Output

```markdown
# Architecture Design Proposal

## 1. Problem Framing

Business Objective:
Functional Scope:
Non-Functional Requirements:
Constraints:
Assumptions:

## 2. System Context and Boundaries

System Context:
Upstream Dependencies:
Downstream Consumers:

### Module Boundaries

| Module | Responsibility | Data Owned | Failure Isolation |
| ------ | -------------- | ---------- | ----------------- |
| Name   | What it does   | Entities   | Guarantee         |

### Boundary Contracts

| Boundary | Crosses     | Must Not Cross          | Failure Propagation |
| -------- | ----------- | ----------------------- | ------------------- |
| A -> B   | Data/events | Internal implementation | Isolated / Shared   |

## 3. Architecture Overview

### Components

| Component          | Responsibility                                   | Owns                             | Depends On                      | Primary Failure Mode                   |
| ------------------ | ------------------------------------------------ | -------------------------------- | ------------------------------- | -------------------------------------- |
| Name               | One sentence                                     | Data/state                       | Components                      | How it fails                           |
| NotificationRouter | Routes notifications to channel-specific senders | routing rules, template registry | ChannelSenders, TemplateService | Channel sender timeout; queues back up |

### Communication Model

| Interaction | Type       | Pattern          | Idempotent | Notes             |
| ----------- | ---------- | ---------------- | ---------- | ----------------- |
| A -> B      | Sync/Async | REST/Event/Queue | Yes/No     | Timeout, fallback |

### Caching Strategy

| Cache Target | TTL      | Invalidation  | Staleness Tolerance |
| ------------ | -------- | ------------- | ------------------- |
| What         | How long | How refreshed | Acceptable lag      |

## 4. Data and Consistency Model

### Data Flow

[Describe request path, event path, batch path]

### Consistency Boundaries

| Boundary | Consistency Model | Partial Failure Behavior | Recovery Mechanism |
| -------- | ----------------- | ------------------------ | ------------------ |
| A -> B   | Strong/Eventual   | What happens             | How to recover     |

### Schema Evolution

[Strategy for backward-compatible schema changes]

## 5. Failure and Risk Analysis

### Failure Scenarios

| Scenario            | Component | Blast Radius         | Mitigation                |
| ------------------- | --------- | -------------------- | ------------------------- |
| Dependency down     | Name      | Narrow/Moderate/Wide | Circuit breaker, fallback |
| Data corruption     | Name      | Scope                | Mechanism                 |
| Resource exhaustion | Name      | Scope                | Mechanism                 |

### Concurrency Risks

| Risk          | Component | Likelihood   | Mitigation          |
| ------------- | --------- | ------------ | ------------------- |
| Specific risk | Name      | Low/Med/High | Specific mitigation |

### Retry Amplification

[Assessment of retry storms and backpressure risks]

## 6. Observability Plan

### Metrics

| Metric       | Component | Type | Alert Threshold |
| ------------ | --------- | ---- | --------------- |
| request_rate | Name      | RED  | Condition       |

### Tracing

[Trace span coverage and correlation strategy]

### Health Checks

| Check | Type     | Dependency | Failure Action |
| ----- | -------- | ---------- | -------------- |
| Name  | Liveness | What       | What happens   |

## 7. Performance and Capacity

Traffic Estimate:
Scaling Model:
Bottleneck Prediction:
Cost Drivers:

## 8. Deployment Strategy

Rollout Approach:
Backward Compatibility:
DB Migration Order:
Rollback Plan:
Rollback Trigger:
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
| Reversibility | Easy / Moderate / Hard     |
| Risk          | What could make this wrong |

## 10. Guardrails and Review Guidance

### Architecture Constraints

| Constraint    | Violation Looks Like    | Consequence |
| ------------- | ----------------------- | ----------- |
| Specific rule | How to detect violation | What breaks |

### Review Checklist Additions

- [ ] Item specific to this design
- [ ] Item specific to this design

### Drift Detection Points

- Signal to watch for erosion

## 11. API Contracts

_Skip with a one-liner if no public API surface._

### Endpoints

| Method | Path           | Description  | Auth | Request         | Response            | Status |
| ------ | -------------- | ------------ | ---- | --------------- | ------------------- | ------ |
| GET    | /api/v1/orders | List orders  | USER | Pageable params | Page<OrderResponse> | 200    |
| POST   | /api/v1/orders | Create order | USER | OrderRequest    | OrderResponse       | 201    |

### Idempotency

| Endpoint              | Idempotent | Mechanism                            |
| --------------------- | ---------- | ------------------------------------ |
| POST /api/v1/payments | Required   | Idempotency-Key header, 24h window   |

### Multi-Tenancy

Pattern: [Path segment | JWT claim | Header X-Tenant-ID | Single-tenant - N/A]
Isolation enforced at: [middleware / repository / both]
Rate limits: per-tenant or global

### Error Format

RFC 9457 problem details; example bodies for the error statuses the API actually returns (typically 400, 404, 409, 422).

### Backward Compatibility (if modifying existing API)

| Change | Impact | Migration Path |
| ------ | ------ | -------------- |
| ...    | ...    | ...            |

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

- **Scope:**
- **Assumptions:**
- **Next level:**

## Staff-Level Summary

Each bullet should be specific to this design, not generic advice. Example: 'Key systemic risks: Retry amplification from SMS provider timeouts can overload the outbox worker under burst load.'

- Key systemic risks:
- Long-term evolution notes:
- Areas requiring strict review:

## Capacity Model (deep only)

| Component | Expected RPS | Peak RPS | Saturation Point | Scaling Action |
| --------- | ------------ | -------- | ---------------- | -------------- |
| Name      | N            | N        | N (bottleneck)   | Scale out / up |

## Failure Simulation (deep only)

### Scenario 1: {Most likely high-impact failure}

Walk through the failure end-to-end:

1. {Component} fails due to {cause}
2. {Propagation path} - {affected component}
3. {User-visible impact}
4. {Mitigation that activates}
5. {Recovery path}

**Blast radius:** {Narrow | Moderate | Wide}
**MTTR estimate:** {minutes / hours}
**Gap identified:** {What the design is missing to contain this faster}

[Repeat for 1-2 additional scenarios in deep mode]

## Evolution Notes (deep only)

- **If traffic doubles**: {What saturates first, what to scale, what must be redesigned}
- **If {key dependency} is removed**: {What breaks, what the fallback is}
- **If team size changes significantly**: {What becomes hard to maintain, what should be simplified}
```

## Self-Check

- [ ] Every module boundary states responsibility, data ownership, and isolation guarantee
- [ ] Every component lists primary failure mode
- [ ] Every significant decision has a rejected alternative with reason; trade-offs include negatives
- [ ] Consistency model stated per data boundary, with partial-failure behavior
- [ ] Highest-blast-radius scenario has a mitigation; retry amplification and backpressure assessed
- [ ] Rollback strategy and rollback trigger present; observability plan names an SLO candidate
- [ ] Guardrails are concrete, detectable rules (one per module boundary minimum)
- [ ] Section 11 produced if any API surface exists: auth per endpoint, RFC 9457 errors, idempotency on state-mutating endpoints, pagination on collections, multi-tenancy if applicable
- [ ] Section 12 produced at standard/deep: at minimum a C4 Container diagram; every diagram element traces to a component/boundary defined in Sections 2-3; Diagram Notes state scope and assumptions
- [ ] Design grounded in stated requirements - no hypothetical future scope
- [ ] If depth = deep: capacity model per component, 2+ failure scenarios simulated, evolution notes cover traffic doubling, sequence/data-flow/deployment diagrams added where applicable

## Avoid

- Class-level design or over-specifying internal component structure
- Architecture astronautics; designing for unstated future requirements
- Generic advice ("use microservices", "add caching") without context-specific reasoning
- Verbose prose where a table communicates more clearly
