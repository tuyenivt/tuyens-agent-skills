# Tuyen's Agent Skills - Architecture

Stack-agnostic architecture design plugin for Claude Code. Provides system design, API contract design, pre-implementation risk analysis, Architecture Decision Record (ADR) creation, re-architecture workflows (monolith decomposition, microservices consolidation, legacy system modernization), diagram generation, and docs repo auditing.

## Workflow Skills

Workflow skills (`task-*`) for architecture design, re-architecture, and docs-repo workflows. Invoked as slash commands.

| Skill                               | Description                                                                                                                                                                                                           |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`          | Architecture design or review. Asks whether you're designing new or reviewing existing - adapts output accordingly. Compares multiple proposals when provided. Supports `quick`, `standard`, and `deep` depth levels. |
| `task-design-api`                   | REST API contract design and review. Auto-detects stack and adapts API patterns.                                                                                                                                      |
| `task-design-risk-analysis`         | Staff-level proactive engineering risk assessment. Supports `quick`, `standard`, and `deep` depth levels.                                                                                                             |
| `task-design-diagram`               | Generate architecture diagrams (C4 context/container/component, sequence, data flow, deployment) as Mermaid or PlantUML from a design doc or description.                                                             |
| `task-adr-create`                   | Write an Architecture Decision Record with context, alternatives, trade-offs, consequences, and review trigger.                                                                                                       |
| `task-architecture-docs-audit`      | Audit an architecture docs repo - inventory artifacts, detect stale or conflicting documents, and produce a prioritized remediation plan.                                                                             |
| `task-migrate-monolith-to-services` | Monolith to microservices/modular services decomposition migration plan with domain boundaries, extraction order, and data ownership transfer.                                                                        |
| `task-consolidate-services`         | Microservices consolidation - merge over-split services into fewer, well-bounded services with data reunification and consumer migration.                                                                             |
| `task-modernize-legacy`             | Legacy system modernization - migrate from outdated language/framework to modern stack with behavioral verification and incremental cutover.                                                                          |

## Atomic Skills

Atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

| Skill                           | Description                                                                                                     | Composed By                                                                                                              |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `system-boundary-design`        | Formal boundary modeling for module and service decomposition                                                   | `task-design-architecture`, `task-migrate-monolith-to-services`, `task-consolidate-services`                             |
| `strangler-fig-pattern`         | Strangler fig migration pattern - incremental traffic routing from legacy to new system with coexistence phases | `task-migrate-monolith-to-services`, `task-consolidate-services`, `task-modernize-legacy`                                |
| `architecture-landscape`        | Build a landscape view of multiple systems - owners, stacks, integration points, and cross-system risks         | `task-consolidate-services` (Section 1), `task-migrate-monolith-to-services` (Section 3), `task-architecture-docs-audit` |
| `architecture-proposal-compare` | Compare 2-3 architecture proposals against a fixed criteria set and produce a ranked recommendation             | `task-design-architecture` (review mode, multiple proposals), `task-architecture-docs-audit`                             |

## Core Atomics Used

The architecture workflow skills compose with these core atomics via `Use skill:`:

- `nfr-specification` - elicit and structure NFRs from business context into measurable SLOs and constraints
- `tradeoff-analysis` - structured architectural decision and trade-off documentation
- `architecture-guardrail` - layer violation and boundary erosion detection
- `architecture-capacity` - throughput estimation and scaling analysis
- `architecture-data-consistency` - consistency strategy across data boundaries
- `ops-engineering-governance` - engineering process and guardrail evolution
- `review-blast-radius` - failure propagation and change impact scope
- `ops-failure-classification` - classify production failures by type and layer
- `failure-propagation-analysis` - trace failure paths across boundaries
- `ops-observability` - structured logging, metrics, and distributed tracing
- `ops-resiliency` - circuit breakers, retries, timeouts, bulkheads
- `backend-idempotency` - idempotency key pattern for safe retries
- `backend-caching` - caching patterns and invalidation strategies
- `ops-release-safety` - rollout, rollback, and deployment risk patterns
- `ops-backward-compatibility` - API and data contract compatibility
- `dependency-impact-analysis` - deployment ordering and dependency impact
- `backend-db-indexing` - database index strategy and query optimization
- `architecture-concurrency` - threading models and synchronization
- `stack-detect` - project tech stack detection
- `backend-api-guidelines` - REST API design conventions
- `review-change-risk` - pre-implementation risk classification
- `complexity-review` - cyclomatic complexity and cognitive load
- `review-pr-risk` - lightweight heuristic PR risk classification
- `ops-feature-flags` - feature flag lifecycle, gradual rollout, and cleanup

All workflow skills depend on core atomics for stack detection, guardrail enforcement, and deeper analysis.

## Skill Dependency Index

### Workflow -> Atomics

| Workflow                            | Atomic Skills Used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `task-design-architecture`          | `nfr-specification`, `architecture-proposal-compare` (review mode, multi-proposal), `system-boundary-design`, `tradeoff-analysis`, `stack-detect`, `architecture-guardrail`, `review-blast-radius`, `architecture-data-consistency`, `backend-idempotency`, `backend-caching`, `ops-resiliency`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-observability`, `backend-db-indexing`, `architecture-capacity`, `ops-release-safety`, `dependency-impact-analysis`, `architecture-concurrency`, `ops-engineering-governance` |
| `task-design-api`                   | `stack-detect`, `backend-api-guidelines`, `ops-backward-compatibility`                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `task-design-risk-analysis`         | `stack-detect`, `review-change-risk`, `review-pr-risk`, `ops-failure-classification`, `architecture-guardrail`, `complexity-review`, `review-blast-radius`, `failure-propagation-analysis`, `architecture-data-consistency`, `backend-idempotency`, `ops-resiliency`, `ops-release-safety`, `ops-backward-compatibility`, `dependency-impact-analysis`, `ops-observability`, `ops-engineering-governance`                                                                                                                                        |
| `task-design-diagram`               | _(no atomic dependencies - reads source docs directly)_                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| `task-adr-create`                   | `tradeoff-analysis`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `task-architecture-docs-audit`      | `architecture-landscape`, `architecture-proposal-compare`, `nfr-specification`                                                                                                                                                                                                                                                                                                                                                                                                                                                                   |
| `task-migrate-monolith-to-services` | `architecture-landscape` (optional, Section 3), `system-boundary-design`, `strangler-fig-pattern`, `stack-detect`, `architecture-guardrail`, `architecture-data-consistency`, `ops-backward-compatibility`, `review-blast-radius`, `dependency-impact-analysis`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-resiliency`, `ops-observability`, `ops-engineering-governance`, `ops-release-safety`, `ops-feature-flags`                                                                                                    |
| `task-consolidate-services`         | `architecture-landscape`, `system-boundary-design`, `strangler-fig-pattern`, `stack-detect`, `architecture-guardrail`, `architecture-data-consistency`, `ops-backward-compatibility`, `review-blast-radius`, `dependency-impact-analysis`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-feature-flags`                                                                                                                                                                                                                     |
| `task-modernize-legacy`             | `strangler-fig-pattern`, `tradeoff-analysis`, `stack-detect`, `architecture-guardrail`, `architecture-data-consistency`, `ops-backward-compatibility`, `review-blast-radius`, `dependency-impact-analysis`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-resiliency`, `ops-feature-flags`                                                                                                                                                                                                                                  |

## Usage Examples

**Design a new system architecture:**

```
/task-design-architecture
Feature: Order payment flow with Stripe integration
Requirements: Handle 500 RPS, zero-downtime deploys, PCI compliance
```

**Review an existing design proposal:**

```
/task-design-architecture
[paste design doc or ADR here]
```

**Compare two competing architecture proposals:**

```
/task-design-architecture
[paste Proposal A]
---
[paste Proposal B]
```

**Generate a C4 container diagram:**

```
/task-design-diagram
[paste task-design-architecture output or design doc]
Diagram type: C4 container
```

**Generate a sequence diagram for a specific flow:**

```
/task-design-diagram
Source: docs/design/order-processing.md
Flow: Order creation through to fulfillment event
```

**Audit the architecture docs repo:**

```
/task-architecture-docs-audit
Path: docs/
```

**Design an API contract:**

```
/task-design-api
Resource: Payment intents
Operations: create, confirm, cancel, list
```

**Pre-implementation risk analysis:**

```
/task-design-risk-analysis
Change: Migrate from monolith to event-driven order processing
```

**Write an Architecture Decision Record:**

```
/task-adr-create
Decision: Use the transactional outbox pattern for event publishing
Context: We're losing events when the app crashes after DB write but before publishing to Kafka
Alternatives: Two-phase commit, direct publish inside transaction, CDC with Debezium
```

**Plan a monolith to services migration:**

```
/task-migrate-monolith-to-services
System: E-commerce monolith (Java/Spring Boot), 200k LOC, shared PostgreSQL database
Driver: Teams stepping on each other during deploys, order processing can't scale independently
```

**Consolidate over-split microservices:**

```
/task-consolidate-services
Services: UserService, ProfileService, PreferenceService, AuthService (4 services, 1 team)
Driver: 15 sync calls per login request, distributed monolith, all share the same DB
```

**Modernize a legacy system:**

```
/task-modernize-legacy
System: PHP 5.6 monolith on Apache, custom MVC framework, MySQL with stored procedures
Driver: Can't hire PHP 5.6 developers, framework has no community support, scaling ceiling at 200 RPS
```
