---
name: task-architecture-design
description: Staff-level architecture design proposal for new features and systems
metadata:
  category: architecture
  tags: [architecture, design, system-design, trade-offs, risk-analysis]
  type: workflow
---

# Architecture Design -- Staff Edition

## Purpose

Staff-level architecture design that prioritizes boundaries, failure containment, and trade-off clarity:

- **Boundary-first thinking** -- design module boundaries and data ownership before classes
- **Failure-aware design** -- every component has a failure mode; design for containment, not just the happy path
- **Explicit trade-offs** -- document what was chosen, what was rejected, and why
- **Evolution-friendly** -- optimize for change velocity and rollback safety, not just day-one delivery
- **Implementation-ready** -- produce enough structure for AI-generated code to follow guardrails

This skill produces a structured design proposal. It does not generate implementation code.

## When to Use

- Designing a new feature or system before implementation
- Evaluating architecture alternatives for a complex requirement
- Pre-implementation design review for Staff/Principal sign-off
- Establishing module boundaries and data ownership for a new domain
- Architecture proposal for cross-team or cross-service changes

## Inputs

| Input                  | Required | Description                                                |
| ---------------------- | -------- | ---------------------------------------------------------- |
| Feature requirements   | Yes      | What the system must do                                    |
| Business context       | No       | Business objective, success criteria, priority             |
| Existing system sketch | No       | Current architecture, services, and data stores            |
| Constraints            | No       | Performance, compliance, timeline, legacy, team capacity   |
| Traffic assumptions    | No       | Expected request volume, growth projections, burst profile |
| Integration needs      | No       | External APIs, third-party services, event sources         |

Handle partial inputs gracefully. When input is missing, state assumptions explicitly and flag what additional context would strengthen the design.

## Rules

- Design boundaries and data ownership first, not classes or endpoints
- Every architectural decision must state at least one trade-off
- Failure modes and blast radius must be assessed for every component boundary
- Do not generate implementation code -- describe components, responsibilities, and interactions
- Do not over-specify internal implementation details that belong to coding time
- Reuse existing skills for domain-specific patterns
- Omit empty sections in output
- Keep output strategic, concise, and high-signal
- When constraints conflict, make the conflict explicit and propose resolution options

## Design Model

### 1. Problem Framing

**Run first. This frames the entire design.**

Capture:

- **Business objective** -- what business outcome does this serve
- **Functional scope** -- what must the system do (in / out of scope)
- **Non-functional requirements** -- latency, throughput, availability, consistency, compliance
- **Constraints** -- technical debt, legacy systems, team capacity, timeline, budget
- **Assumptions** -- what is assumed true but not yet validated

Use skill: `engineering-governance` to verify alignment with existing engineering standards and design governance triggers.

If this design is triggered by an incident or failure pattern, reference outputs from skill: `task-root-cause` or skill: `task-postmortem` to incorporate lessons learned.

### 2. System Context and Boundary Definition

Define the system's position in the broader architecture.

Use skill: `architecture-guardrail` to establish boundary rules.
Use skill: `blast-radius-analysis` to assess failure propagation scope per boundary.
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

Use skill: `data-consistency-modeling` for consistency boundary design.
Use skill: `idempotency` for retry safety at integration points.
Use skill: `caching` for caching strategy and invalidation.
Use skill: `resiliency` for fault tolerance and REST client integration patterns.

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

Use skill: `data-consistency-modeling` for consistency strategy selection.
Use skill: `db-indexing` for data access patterns and index strategy.

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

Use skill: `failure-classification` to categorize failure types per component.
Use skill: `failure-propagation-analysis` to trace cascading failure paths.
Use skill: `blast-radius-analysis` to assess impact scope per failure scenario.
Use skill: `resiliency` for mitigation patterns.
Use skill: `concurrency-model` for concurrency risk assessment.

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

Use skill: `observability` for logging, metrics, and tracing patterns.

Define:

- **Structured logging** -- what events are logged, correlation ID strategy
- **Metrics** -- RED metrics (Rate, Errors, Duration) per component boundary
- **Distributed tracing** -- trace span coverage across service boundaries
- **Health checks** -- liveness and readiness probes, dependency health
- **Alerting signals** -- what conditions trigger alerts, severity classification
- **SLO candidates** -- which metrics represent user-facing quality

### 7. Performance and Capacity Considerations

Estimate capacity requirements and identify bottlenecks.

Use skill: `capacity-modeling` for throughput estimation and scaling analysis.
Use skill: `payload-optimization` for API response efficiency.
Use skill: `caching` for cache-based load reduction.
Use skill: `db-indexing` for query performance.

Estimate:

- **Expected traffic** -- requests per second, concurrent users, burst profile
- **Throughput assumptions** -- per-component throughput targets
- **Scaling model** -- horizontal vs vertical, stateless vs stateful constraints
- **Bottleneck prediction** -- which component saturates first under load
- **Cost awareness** -- resource cost drivers, cost per request estimate if applicable

### 8. Deployment and Release Strategy

Define how the system goes to production safely.

Use skill: `release-safety` for rollout and rollback patterns.
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

### 10. Guardrails and Review Guidance

Define constraints to enforce during implementation.

Use skill: `architecture-guardrail` for boundary enforcement rules.
Use skill: `engineering-governance` for evolving existing guardrails.

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

| Component | Responsibility | Owns       | Depends On | Primary Failure Mode |
| --------- | -------------- | ---------- | ---------- | -------------------- |
| Name      | One sentence   | Data/state | Components | How it fails         |

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

- Key systemic risks:
- Long-term evolution notes:
- Areas requiring strict review:
```

### Output Constraints

- No implementation code
- Every component must state its failure mode
- Every boundary must state its isolation guarantee
- Every significant decision must state a trade-off
- Findings ordered by structural impact
- Omit empty sections
- No trivial detail inflation
- Optimize for implementation team clarity and AI code generation guidance

## Avoid

- Generating implementation code or class-level design
- Over-specifying internal component structure
- Ignoring failure modes and blast radius
- Implicit trade-offs -- if it is a decision, make it explicit
- Architecture astronautics -- designs must be grounded in stated requirements and constraints
- Designing for hypothetical future requirements not stated in inputs
- Verbose explanations where a table communicates more clearly
- Generic advice ("use microservices", "add caching") without context-specific reasoning
- Treating this as a code review or implementation plan

## Key Skills Reference

### Existing Skills Reused

**Boundary and Structure:**

- Use skill: `architecture-guardrail` for boundary enforcement and drift detection
- Use skill: `blast-radius-analysis` for failure propagation scope per boundary
- Use skill: `engineering-governance` for alignment with engineering standards

**Component Design:**

- Use skill: `data-consistency-modeling` for consistency boundary design
- Use skill: `idempotency` for retry safety at integration points
- Use skill: `caching` for caching strategy and invalidation
- Use skill: `resiliency` for fault tolerance and REST client integration patterns

**Failure Analysis:**

- Use skill: `failure-classification` for failure type categorization
- Use skill: `failure-propagation-analysis` for cascading failure path tracing
- Use skill: `observability` for logging, metrics, and tracing patterns

**Performance:**

- Use skill: `payload-optimization` for API response efficiency
- Use skill: `db-indexing` for data access patterns and index strategy

**Governance:**

- Use skill: `engineering-governance` for evolving existing guardrails

**Related Workflows:**

- Use skill: `task-root-cause` for incorporating incident lessons into design
- Use skill: `task-postmortem` for incorporating postmortem findings into design
- Use skill: `task-code-review-advanced` for reviewing implementation against this design
- Use skill: `task-perf-review` for deep performance review of implementation

### Sub-Skills Defined for This Workflow

| Skill                        | Purpose                                                            |
| ---------------------------- | ------------------------------------------------------------------ |
| `system-boundary-design`     | Formal boundary modeling for module and service decomposition      |
| `data-consistency-modeling`  | Consistency strategy selection across data boundaries              |
| `tradeoff-analysis`          | Structured architectural decision and trade-off documentation      |
| `capacity-modeling`          | Throughput estimation, scaling analysis, and bottleneck prediction |
| `release-safety`             | Rollout, rollback, and deployment risk patterns                    |
| `dependency-impact-analysis` | Deployment ordering and dependency change impact assessment        |
| `concurrency-model`          | Concurrency risk assessment and thread safety patterns             |
