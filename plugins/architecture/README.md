# Tuyen's Agent Skills - Architecture

Stack-agnostic architecture design plugin for Claude Code. Provides system design, API contract design, pre-implementation risk analysis, Architecture Decision Record (ADR) creation, and re-architecture workflows (monolith decomposition, microservices consolidation, legacy system modernization).

## Workflow Skills

7 workflow skills (`task-*`) for architecture design and re-architecture workflows. Invoked as slash commands.

| Skill                               | Description                                                                                                                                                                |
| ----------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`          | Architecture design or review. Asks whether you're designing new or reviewing existing - adapts output accordingly. Supports `quick`, `standard`, and `deep` depth levels. |
| `task-design-api`                   | REST API contract design and review. Auto-detects stack and adapts API patterns.                                                                                           |
| `task-design-risk-analysis`         | Staff-level proactive engineering risk assessment. Supports `quick`, `standard`, and `deep` depth levels.                                                                  |
| `task-adr-create`                   | Write an Architecture Decision Record with context, alternatives, trade-offs, consequences, and review trigger.                                                            |
| `task-migrate-monolith-to-services` | Monolith to microservices/modular services decomposition migration plan with domain boundaries, extraction order, and data ownership transfer.                             |
| `task-consolidate-services`         | Microservices consolidation - merge over-split services into fewer, well-bounded services with data reunification and consumer migration.                                  |
| `task-modernize-legacy`             | Legacy system modernization - migrate from outdated language/framework to modern stack with behavioral verification and incremental cutover.                               |

## Atomic Skills

3 atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

| Skill                    | Description                                                                                                     |
| ------------------------ | --------------------------------------------------------------------------------------------------------------- |
| `system-boundary-design` | Formal boundary modeling for module and service decomposition                                                   |
| `tradeoff-analysis`      | Structured architectural decision and trade-off documentation                                                   |
| `strangler-fig-pattern`  | Strangler fig migration pattern - incremental traffic routing from legacy to new system with coexistence phases |

## Core Atomics Used

The architecture workflow skills compose with these core atomics via `Use skill:`:

- `architecture-guardrail` - layer violation and boundary erosion detection
- `capacity-modeling` - throughput estimation and scaling analysis
- `data-consistency-modeling` - consistency strategy across data boundaries
- `engineering-governance` - engineering process and guardrail evolution
- `blast-radius-analysis` - failure propagation and change impact scope
- `failure-classification` - classify production failures by type and layer
- `failure-propagation-analysis` - trace failure paths across boundaries
- `observability` - structured logging, metrics, and distributed tracing
- `resiliency` - circuit breakers, retries, timeouts, bulkheads
- `idempotency` - idempotency key pattern for safe retries
- `caching` - caching patterns and invalidation strategies
- `release-safety` - rollout, rollback, and deployment risk patterns
- `backward-compatibility-analysis` - API and data contract compatibility
- `dependency-impact-analysis` - deployment ordering and dependency impact
- `db-indexing` - database index strategy and query optimization
- `concurrency-model` - threading models and synchronization
- `stack-detect` - project tech stack detection
- `api-guidelines` - REST API design conventions
- `change-risk-classification` - pre-implementation risk classification
- `complexity-review` - cyclomatic complexity and cognitive load
- `pr-risk-analysis` - lightweight heuristic PR risk classification
- `feature-flags` - feature flag lifecycle, gradual rollout, and cleanup

All workflow skills depend on core atomics for stack detection, guardrail enforcement, and deeper analysis.

## Skill Dependency Index

### Workflow -> Atomics

| Workflow                            | Atomic Skills Used                                                                                                                                                                                                                                                                                                                                                                                                    |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`          | `stack-detect`_, `architecture-guardrail`_, `blast-radius-analysis`_, `system-boundary-design`, `data-consistency-modeling`_, `idempotency`_, `caching`_, `resiliency`_, `failure-classification`_, `failure-propagation-analysis`_, `observability`_, `db-indexing`_, `capacity-modeling`_, `release-safety`_, `dependency-impact-analysis`_, `concurrency-model`\_, `tradeoff-analysis`, `engineering-governance`\* |
| `task-design-api`                   | `stack-detect`_, `api-guidelines`_, `backward-compatibility-analysis`\*                                                                                                                                                                                                                                                                                                                                               |
| `task-design-risk-analysis`         | `stack-detect`_, `change-risk-classification`_, `pr-risk-analysis`_, `failure-classification`_, `architecture-guardrail`_, `complexity-review`_, `blast-radius-analysis`_, `failure-propagation-analysis`_, `data-consistency-modeling`_, `idempotency`_, `resiliency`_, `release-safety`_, `backward-compatibility-analysis`_, `dependency-impact-analysis`_, `observability`_, `engineering-governance`_            |
| `task-adr-create`                   | `tradeoff-analysis`                                                                                                                                                                                                                                                                                                                                                                                                   |
| `task-migrate-monolith-to-services` | `stack-detect`_, `architecture-guardrail`_, `system-boundary-design`, `strangler-fig-pattern`, `data-consistency-modeling`_, `backward-compatibility-analysis`_, `blast-radius-analysis`_, `dependency-impact-analysis`_, `failure-classification`_, `failure-propagation-analysis`_, `resiliency`_, `observability`_, `engineering-governance`_, `release-safety`_, `feature-flags`\*                                |
| `task-consolidate-services`         | `stack-detect`_, `architecture-guardrail`_, `system-boundary-design`, `strangler-fig-pattern`, `data-consistency-modeling`_, `backward-compatibility-analysis`_, `blast-radius-analysis`_, `dependency-impact-analysis`_, `failure-classification`_, `failure-propagation-analysis`_, `feature-flags`\*                                                                                                               |
| `task-modernize-legacy`             | `stack-detect`_, `architecture-guardrail`_, `strangler-fig-pattern`, `tradeoff-analysis`, `data-consistency-modeling`_, `backward-compatibility-analysis`_, `blast-radius-analysis`_, `dependency-impact-analysis`_, `failure-classification`_, `failure-propagation-analysis`_, `resiliency`_, `feature-flags`_                                                                                                      |

\* _Cross-plugin dependency from `core` - available when `core` is installed alongside `architecture`._

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
