# Tuyen's Agent Skills - Architecture

Stack-agnostic architecture design plugin for Claude Code. Provides system design (now bundling API contract design and C4 diagrams into the same workflow), re-architecture (monolith decomposition, microservices consolidation, legacy system modernization), database migration planning, and dependency upgrade assessment. Every authoring workflow doubles as a review workflow - pass an existing artifact and you get a severity-tagged review (Blocker / Major / Minor / Nit) with an Approve / Approve-with-changes / Needs-rework verdict.

## Workflow Skills

Workflow skills (`task-*`) for architecture design and re-architecture. Invoked as slash commands.

| Skill                               | Description                                                                                                                                                                                                                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`          | Design or review system architecture in a single workflow: boundaries, failure containment, data consistency, observability, performance, deployment, trade-offs, guardrails, API contracts (REST/RFC 9457), and C4 diagrams (Mermaid). Supports `quick`, `standard`, `deep` depths. |
| `task-decompose-monolith` | Plan or review a monolith-to-microservices decomposition with domain boundaries, extraction order, and data ownership transfer.                                                                                                                                                     |
| `task-consolidate-services`         | Plan or review a microservices consolidation - merge over-split services into fewer, well-bounded services with data reunification and consumer migration.                                                                                                                          |
| `task-modernize-legacy`             | Plan or review a legacy system modernization - migrate from outdated language/framework to modern stack with behavioral verification and incremental cutover.                                                                                                                       |
| `task-db-migration`            | Plan or review a database migration for complex schema changes - zero-downtime sequencing, expand-contract phasing, lock risk, backfill, and rollback.                                                                                                                              |
| `task-dependency-upgrade`                 | Plan or review a library or platform upgrade - changelog analysis, breaking change detection, compatibility conflicts, effort estimate (S/M/L/XL), and Go/No-Go.                                                                                                                    |

## Atomic Skills

Atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

| Skill                           | Description                                                                                                                  | Composed By                                                                                  |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `system-boundary-design`        | Formal boundary modeling for module and service decomposition                                                                | `task-design-architecture`, `task-decompose-monolith`, `task-consolidate-services` |
| `strangler-fig-pattern`         | Strangler fig migration pattern - incremental traffic routing from legacy to new system with coexistence phases              | `task-decompose-monolith`, `task-consolidate-services`, `task-modernize-legacy`    |
| `architecture-landscape`        | Build a landscape view of multiple systems - owners, stacks, integration points, and cross-system risks                      | `task-consolidate-services` (Section 1), `task-decompose-monolith` (Section 3)     |
| `architecture-proposal-compare` | Compare 2-3 architecture proposals against a fixed criteria set and produce a ranked recommendation                          | `task-design-architecture` (review mode, multiple proposals)                                 |
| `architecture-capacity`         | Throughput estimation, scaling analysis, and bottleneck prediction                                                           | `task-design-architecture`                                                                   |
| `architecture-review-lens`      | Review lens for architecture artifacts - severity taxonomy, completeness audit, consistency check, criteria scoring, verdict | All 6 authoring workflows in their Review Mode                                               |

## Core Atomics Used

The architecture workflow skills compose with these core atomics via `Use skill:`:

- `nfr-specification` - elicit and structure NFRs from business context into measurable SLOs and constraints
- `tradeoff-analysis` - structured architectural decision and trade-off documentation
- `architecture-guardrail` - layer violation and boundary erosion detection
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
- `backend-api-guidelines` - REST API design conventions (HTTP methods, RFC 9457 errors, pagination, idempotency)
- `review-change-risk` - pre-implementation risk classification
- `ops-feature-flags` - feature flag lifecycle, gradual rollout, and cleanup

## Skill Dependency Index

### Workflow -> Atomics

| Workflow                            | Atomic Skills Used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`          | `nfr-specification`, `architecture-proposal-compare` (review mode, multi-proposal), `architecture-review-lens` (review mode), `system-boundary-design`, `tradeoff-analysis`, `stack-detect`, `architecture-guardrail`, `review-blast-radius`, `architecture-data-consistency`, `backend-idempotency`, `backend-caching`, `ops-resiliency`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-observability`, `backend-db-indexing`, `architecture-capacity`, `ops-release-safety`, `dependency-impact-analysis`, `architecture-concurrency`, `ops-engineering-governance`, `backend-api-guidelines`, `ops-backward-compatibility` |
| `task-decompose-monolith` | `architecture-landscape` (optional, Section 3), `system-boundary-design`, `strangler-fig-pattern`, `stack-detect`, `architecture-guardrail`, `architecture-data-consistency`, `ops-backward-compatibility`, `review-blast-radius`, `dependency-impact-analysis`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-resiliency`, `ops-observability`, `ops-engineering-governance`, `ops-release-safety`, `ops-feature-flags`, `architecture-review-lens` (review mode)                                                                                                                                                              |
| `task-consolidate-services`         | `architecture-landscape`, `system-boundary-design`, `strangler-fig-pattern`, `stack-detect`, `architecture-guardrail`, `architecture-data-consistency`, `ops-backward-compatibility`, `review-blast-radius`, `dependency-impact-analysis`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-feature-flags`, `architecture-review-lens` (review mode)                                                                                                                                                                                                                                                                              |
| `task-modernize-legacy`             | `strangler-fig-pattern`, `tradeoff-analysis`, `stack-detect`, `architecture-guardrail`, `architecture-data-consistency`, `ops-backward-compatibility`, `review-blast-radius`, `dependency-impact-analysis`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-resiliency`, `ops-feature-flags`, `architecture-review-lens` (review mode)                                                                                                                                                                                                                                                                                           |
| `task-db-migration`            | `review-change-risk`, `ops-backward-compatibility`, `backend-db-indexing`, `backend-idempotency`, `ops-release-safety`, `dependency-impact-analysis`, `review-blast-radius`, `architecture-review-lens` (review mode)                                                                                                                                                                                                                                                                                                                                                                                                                              |
| `task-dependency-upgrade`                 | `stack-detect`, `ops-backward-compatibility`, `review-blast-radius`, `ops-release-safety`, `dependency-impact-analysis`, `architecture-review-lens` (review mode)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |

## Usage Examples

**Design a new system architecture (system design + API contracts + diagrams in one output):**

```
/task-design-architecture
Feature: Order payment flow with Stripe integration
Requirements: Handle 500 RPS, zero-downtime deploys, PCI compliance
```

`task-design-architecture` produces all 12 sections at `standard` depth: problem framing, boundaries, components, data/consistency, failure modes, observability, capacity, deployment, trade-offs, guardrails, **API contracts** (endpoint table, RFC 9457 errors, idempotency, multi-tenancy, backward compatibility), and **diagrams** (C4 Container always; sequence/data-flow/deployment when applicable).

**Review someone else's artifact (works on every workflow):**

Pass an existing artifact and the workflow switches to Review Mode automatically. Output: severity-tagged findings (Blocker / Major / Minor / Nit), completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and a verdict.

```
/task-design-architecture
[paste a design doc, OpenAPI spec, or proposal here]

/task-db-migration
[paste someone's migration plan]

/task-dependency-upgrade
[paste someone's upgrade assessment]
```

**Compare two competing architecture proposals:**

```
/task-design-architecture
[paste Proposal A]
---
[paste Proposal B]
```

**Plan a monolith to services migration:**

```
/task-decompose-monolith
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

**Plan a complex database schema migration:**

```
/task-db-migration
Change: Rename user_id column to account_id across orders table (50M rows, multi-service)
Database: PostgreSQL
Deployment: Rolling, zero-downtime required
```

**Assess a dependency upgrade:**

```
/task-dependency-upgrade
Upgrade: Spring Boot 3.3 -> 3.5
```
