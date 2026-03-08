# Tuyen's Agent Skills - Architecture

Stack-agnostic architecture design plugin for Claude Code. Provides system design, API contract design, pre-implementation risk analysis, and Architecture Decision Record (ADR) creation workflows.

## Workflow Skills

4 workflow skills (`task-*`) for architecture design workflows. Invoked as slash commands.

| Skill                       | Description                                                                                                                                                                |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`  | Architecture design or review. Asks whether you're designing new or reviewing existing - adapts output accordingly. Supports `quick`, `standard`, and `deep` depth levels. |
| `task-design-api`           | REST API contract design and review. Auto-detects stack and adapts API patterns.                                                                                           |
| `task-design-risk-analysis` | Staff-level proactive engineering risk assessment. Supports `quick`, `standard`, and `deep` depth levels.                                                                  |
| `task-adr-create`           | Write an Architecture Decision Record with context, alternatives, trade-offs, consequences, and review trigger.                                                            |

## Atomic Skills

2 atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

| Skill                    | Description                                                   |
| ------------------------ | ------------------------------------------------------------- |
| `system-boundary-design` | Formal boundary modeling for module and service decomposition |
| `tradeoff-analysis`      | Structured architectural decision and trade-off documentation |

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

All workflow skills depend on core atomics for stack detection, guardrail enforcement, and deeper analysis.

## Skill Dependency Index

### Workflow -> Atomics

| Workflow                    | Atomic Skills Used                                                                                                                                                                                                                                                                                                                                                                                                    |
| --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`  | `stack-detect`_, `architecture-guardrail`_, `blast-radius-analysis`_, `system-boundary-design`, `data-consistency-modeling`_, `idempotency`_, `caching`_, `resiliency`_, `failure-classification`_, `failure-propagation-analysis`_, `observability`_, `db-indexing`_, `capacity-modeling`_, `release-safety`_, `dependency-impact-analysis`_, `concurrency-model`\_, `tradeoff-analysis`, `engineering-governance`\* |
| `task-design-api`           | `stack-detect`_, `api-guidelines`_, `backward-compatibility-analysis`\*                                                                                                                                                                                                                                                                                                                                               |
| `task-design-risk-analysis` | `stack-detect`_, `change-risk-classification`_, `pr-risk-analysis`_, `failure-classification`_, `architecture-guardrail`_, `complexity-review`_, `blast-radius-analysis`_, `failure-propagation-analysis`_, `data-consistency-modeling`_, `idempotency`_, `resiliency`_, `release-safety`_, `backward-compatibility-analysis`_, `dependency-impact-analysis`_, `observability`_, `engineering-governance`_            |
| `task-adr-create`           | `tradeoff-analysis`                                                                                                                                                                                                                                                                                                                                                                                                   |

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
