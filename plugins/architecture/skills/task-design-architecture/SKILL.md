---
name: task-design-architecture
description: "Staff-level architecture design proposal: boundaries, failure modes, data consistency, trade-offs, deployment, guardrails; also reviews proposals."
metadata:
  category: architecture
  tags: [architecture, design, system-design, trade-offs, risk-analysis]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Architecture Design -- Staff Edition

## Purpose

Staff-level architecture design or review prioritizing boundaries, failure containment, and explicit trade-offs. Produces a structured proposal (or review); no implementation code.

## When to Use

- New feature/system design before implementation
- Pre-implementation design review for Staff/Principal sign-off
- Architecture proposal for cross-team changes
- Reviewing an existing design proposal or comparing competing proposals

## Mode Detection

If the user's input makes mode obvious (e.g., "here's a design doc, review it" or "design a payment service"), proceed. Otherwise ask: **new design** (full proposal) or **review existing** (evaluate proposal). Default: New Design.

### New Design Mode

Run all 10 sections per the Design Model below.

### Review Mode

For 2+ proposals on the same problem: use `architecture-proposal-compare` first, then apply Review Mode to the recommended proposal.

For a single proposal:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Supply this design-specific factor list to the completeness audit:

| Factor                                | What "Present" Looks Like                                          |
| ------------------------------------- | ------------------------------------------------------------------ |
| Problem framing and NFRs              | Business objective, measurable NFRs, explicit constraints          |
| System context and boundaries         | Upstream/downstream, module boundaries, data ownership             |
| Component design                      | Named components, responsibilities, failure modes                  |
| Data and consistency model            | Per-boundary consistency, partial-failure behavior, recovery       |
| Failure mode analysis                 | Per-component failure modes, blast radius, mitigations             |
| Observability plan                    | Metrics, logs, traces, alerts, SLO candidates                      |
| Performance and capacity              | Traffic estimates, bottlenecks, scaling model                      |
| Deployment and rollback               | Rollout approach, migration order, rollback trigger                |
| Trade-off analysis                    | Alternatives considered, why rejected, reversibility               |
| Guardrails                            | Architecture constraints implementation must follow                |

For per-factor depth, compose the same atomic skills as authoring mode (see Design Model sections 2-10) to evaluate quality of what the author wrote. Treat performance, deployment, and trade-offs as first-class review targets, not "flag-only-if-gap."

Output header: `# Architecture Review` and use the output structure defined in `architecture-review-lens`. Skip the New Design output template.

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

| Depth      | When to Use                                                                      | Sections Produced                                      |
| ---------- | -------------------------------------------------------------------------------- | ------------------------------------------------------ |
| `quick`    | Early ideation, async review, or "is this direction sensible?" check             | Problem framing + boundaries + top 1-2 trade-offs only |
| `standard` | Default - pre-implementation design for Staff/Principal sign-off                 | All 10 sections                                        |
| `deep`     | Large cross-team changes, capacity-sensitive systems, or post-incident redesigns | All 10 sections + capacity model + failure simulation  |

**Quick depth produces:**

- Problem framing (functional scope, NFRs, constraints)
- System boundary sketch (modules, data ownership, one sentence per component)
- Top 1-2 trade-offs with reasoning

**Deep depth adds (on top of standard):**

- Capacity model with per-component throughput estimates and saturation point
- Failure simulation: walk through 2-3 cascading failure scenarios end-to-end
- Evolution notes: what changes if traffic doubles or a key dependency is removed

Default: `standard`. If the user asks for a "quick design check" or "rough architecture", use `quick`. If they ask for "full design" or "staff-level review", use `standard` or `deep`.

## Rules

- Boundaries and data ownership first, not classes or endpoints
- Every component states a primary failure mode and isolation guarantee
- Every significant decision states at least one trade-off and one rejected alternative with reason
- No implementation code; describe components, responsibilities, and interactions
- Make conflicting constraints explicit; propose resolution options
- Omit empty sections; output is strategic, concise, high-signal

## Design Model

### 1. Problem Framing

**Run first. This frames the entire design.**

Capture:

- **Business objective** -- what business outcome does this serve
- **Functional scope** -- what must the system do (in / out of scope)
- **Constraints** -- technical debt, legacy systems, team capacity, timeline, budget
- **Assumptions** -- what is assumed true but not yet validated

Use skill: `nfr-specification` to elicit and structure non-functional requirements into measurable SLOs and constraints. The NFR output feeds into Section 6 (Observability) as alert baselines and Section 7 (Performance) as capacity targets.

Use skill: `ops-engineering-governance` to verify alignment with existing engineering standards and design governance triggers.

### 2. System Context and Boundary Definition

Define the system's position in the broader architecture.

Use skill: `architecture-guardrail` to establish boundary rules.
Use skill: `review-blast-radius` to assess failure propagation scope per boundary.
Use skill: `system-boundary-design` for formal boundary modeling.

Define:

- **System context** -- what this system is and what surrounds it
- **Upstream dependencies** -- services, data sources, and event producers this system consumes
- **Downstream consumers** -- services, clients, and event consumers that depend on this system
- **Internal module boundaries** -- logical decomposition within the system
- **Data ownership** -- which module owns which data entities
- **API contracts** -- what this system exposes and guarantees to consumers

For each boundary, state:

- What crosses the boundary (data, commands, events)
- What must NOT cross the boundary (domain internals, implementation details)
- Failure isolation guarantee (does a failure in A propagate to B?)

### 3. Architecture Overview

Provide the high-level component design.

Use skill: `architecture-data-consistency` for consistency boundary design.
Use skill: `backend-idempotency` for retry safety at integration points.
Use skill: `backend-caching` for caching strategy and invalidation.
Use skill: `ops-resiliency` for fault tolerance and REST client integration patterns.

Define:

- **Component breakdown** -- named components with single-sentence responsibilities
- **Communication model** -- sync (REST/gRPC) vs async (events/messages) per interaction
- **Transaction boundaries** -- which operations share a transaction, which use eventual consistency
- **Idempotency requirements** -- which operations must be idempotent and why
- **Caching strategy** -- what is cached, invalidation approach, staleness tolerance
- **Integration patterns** -- how external dependencies are consumed (client, adapter, anti-corruption layer)

For each component, briefly state:

- What it does
- What it owns (data, state)
- What it depends on
- How it fails (primary failure mode)

### 4. Data and Consistency Model

Define data flow and consistency guarantees.

Use skill: `architecture-data-consistency` for consistency strategy selection.
Use skill: `backend-db-indexing` for data access patterns and index strategy.

Define:

- **Data flow** -- how data moves through the system (request path, event path, batch path)
- **Consistency model** -- strong consistency vs eventual consistency per data boundary
- **Distributed consistency strategy** -- outbox pattern, saga, or compensating transactions if applicable
- **Schema evolution strategy** -- how data schemas change without breaking consumers
- **Data access patterns** -- read/write ratio, query patterns, hot paths

For each data boundary:

- State the consistency guarantee
- State what happens during partial failure (data in inconsistent state?)
- State the recovery mechanism

### 5. Failure Mode and Risk Analysis

Analyze how the design fails.

Use skill: `ops-failure-classification` to categorize failure types per component.
Use skill: `failure-propagation-analysis` to trace cascading failure paths.
Use skill: `review-blast-radius` to assess impact scope per failure scenario.
Use skill: `ops-resiliency` for mitigation patterns.
Use skill: `architecture-concurrency` for concurrency risk assessment.

Analyze per component boundary:

- **Failure scenarios** -- what can go wrong (dependency down, data corruption, resource exhaustion)
- **Cascading failure risk** -- can a failure in A take down B?
- **Concurrency risk** -- race conditions, contention, concurrency model compatibility
- **Resource contention** -- connection pools, thread pools, memory, disk
- **Backpressure risk** -- what happens when a consumer is slower than a producer
- **Retry amplification risk** -- can retries compound load during partial failure

For each high-risk scenario:

- State the failure mode
- State the blast radius (Narrow / Moderate / Wide)
- State the mitigation (circuit breaker, fallback, bulkhead, timeout)

### 6. Observability Plan

Define what signals the system must produce from day one.

Use skill: `ops-observability` for logging, metrics, and tracing patterns.

Define:

- **Structured logging** -- what events are logged, correlation ID strategy
- **Metrics** -- RED metrics (Rate, Errors, Duration) per component boundary
- **Distributed tracing** -- trace span coverage across service boundaries
- **Health checks** -- liveness and readiness probes, dependency health
- **Alerting signals** -- what conditions trigger alerts, severity classification
- **SLO candidates** -- which metrics represent user-facing quality

### 7. Performance and Capacity Considerations

Estimate capacity requirements and identify bottlenecks.

Use skill: `architecture-capacity` for throughput estimation and scaling analysis.
Use skill: `backend-caching` for cache-based load reduction and API response optimization.
Use skill: `backend-db-indexing` for query performance.

Estimate:

- **Expected traffic** -- requests per second, concurrent users, burst profile
- **Throughput assumptions** -- per-component throughput targets
- **Scaling model** -- horizontal vs vertical, stateless vs stateful constraints
- **Bottleneck prediction** -- which component saturates first under load
- **Cost awareness** -- resource cost drivers, cost per request estimate if applicable

### 8. Deployment and Release Strategy

Define how the system goes to production safely.

Use skill: `ops-release-safety` for rollout and rollback patterns.
Use skill: `dependency-impact-analysis` for deployment ordering.

Define:

- **Rollout approach** -- canary, blue-green, feature flag, progressive rollout
- **Backward compatibility** -- API versioning, data format compatibility during transition
- **Database migration order** -- schema changes before or after code deploy, zero-downtime strategy
- **Rollback plan** -- what to roll back, in what order, what data is affected
- **Monitoring during rollout** -- what signals to watch, rollback trigger criteria
- **Feature flag strategy** -- which capabilities are gated, kill switch design

### 9. Trade-Off Analysis

Explicitly document architectural decisions and alternatives.

Use skill: `tradeoff-analysis` for structured decision documentation.

For each significant decision:

- **Decision** -- what was chosen
- **Alternatives considered** -- what was evaluated
- **Why this option** -- primary reasons for selection
- **Why not alternatives** -- specific reasons each was rejected
- **Trade-off** -- what is sacrificed (complexity, flexibility, performance, cost)
- **Reversibility** -- how hard is it to change this decision later
- **Risk** -- what could make this decision wrong

**ADR candidates:** For any decision with High reversibility cost or significant trade-offs (messaging broker, consistency model, primary storage engine, async vs sync communication), recommend creating an ADR using `/task-adr-create`. State which decisions warrant an ADR so the team can commit the rationale before implementation begins.

### 10. Guardrails and Review Guidance

Define constraints to enforce during implementation.

Use skill: `architecture-guardrail` for boundary enforcement rules.
Use skill: `ops-engineering-governance` for evolving existing guardrails.

Define:

- **Architecture constraints** -- rules that implementation must follow (layer boundaries, dependency direction, data ownership)
- **Review checklist additions** -- specific items reviewers must check for this feature
- **Drift detection points** -- where to watch for gradual erosion of the design
- **AI code generation constraints** -- boundaries and patterns that AI-generated code must respect

For each constraint:

- State the rule
- State what violation looks like
- State the consequence of violation

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
- [ ] Design grounded in stated requirements - no hypothetical future scope
- [ ] If depth = deep: capacity model per component, 2+ failure scenarios simulated, evolution notes cover traffic doubling

## Avoid

- Class-level design or over-specifying internal component structure
- Architecture astronautics; designing for unstated future requirements
- Generic advice ("use microservices", "add caching") without context-specific reasoning
- Verbose prose where a table communicates more clearly
