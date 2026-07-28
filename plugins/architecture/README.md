# Tuyen's Agent Skills - Architecture

Stack-agnostic architecture plugin for Claude Code, for architects, tech leads, and on-call responders. Covers the pipeline from design through build planning, plus live incident response: system design (bundling API contract design and C4 diagrams into the same workflow), migration planning (monolith decomposition, microservices consolidation, legacy modernization, zero-downtime schema change), dependency upgrade assessment, design-to-tasks breakdown, and the live incident lifecycle (shift-start, triage, root-cause analysis). Every authoring workflow doubles as a review workflow - pass an existing artifact and you get a severity-tagged review (Blocker / Major / Minor / Nit) with an Approve / Approve-with-changes / Needs-rework verdict.

Post-incident write-ups and release notes are intentionally out of scope: both follow a company-specific format, so the plugin supplies their inputs (confirmed root cause, blast radius, risk classification) rather than a competing template.

## Agents

Stack-agnostic by design - the agents name patterns and boundaries, never a framework. For stack-specific design, use the matching stack plugin's architect. The architect owns the system; the planner owns the plan to build it; the responder owns the live incident lifecycle.

| Agent                  | Description                                                                                                                                                     | Drives                                                                                     |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| architecture-architect | Design authority: system design and migration planning (decomposition, consolidation, modernization, schema change) - authoring and review.                 | `task-design-architecture`, `task-migrate-architecture` |
| architecture-planner   | Delivery planner: design-to-task-graph breakdown and dependency upgrade assessment (effort, Go/No-Go) - authoring and review.                               | `task-breakdown-design`, `task-dependency-upgrade`      |
| oncall-responder       | Incident responder / SRE walking the live incident lifecycle: shift-start health checks, alert triage and routing, containment-first root-cause analysis.   | `task-oncall-start`                                     |

## Workflow Skills

Workflow skills (`task-*`) for architecture design, re-architecture, and delivery planning. Invoked as slash commands.

| Skill                               | Description                                                                                                                                                                                                                                                                          |
| ----------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`          | Design or review system architecture in a single workflow: boundaries, failure containment, data consistency, observability, performance, deployment, trade-offs, guardrails, API contracts (REST/RFC 9457), and C4 diagrams (Mermaid). Supports `quick`, `standard`, `deep` depths. |
| `task-migrate-architecture`         | Plan or review a migration between two system states, selected by shape: **Decompose** (monolith to services), **Consolidate** (merge over-split services), **Modernize** (legacy stack migration), **Schema** (zero-downtime schema change - expand-contract, lock risk, backfill). Supports `quick`, `standard`, `deep` depths. |
| `task-dependency-upgrade`                 | Plan or review a library or platform upgrade - changelog analysis, breaking change detection, compatibility conflicts, effort estimate (S/M/L/XL), and Go/No-Go.                                                                                                                    |
| `task-breakdown-design`             | Break a system design (HLD/LLD, ideally a `task-design-architecture` proposal) into an implementable task graph - phases, dependency order, critical path, sizing, scope-creep flags - or review a breakdown someone else authored (severity-tagged findings and a verdict).        |
| `task-oncall-start`                 | Oncall entry point for shift starts (rotation handoff, system health review) and incoming alert triage (classify and route to the right workflow).                                                                                                                                  |

The design pipeline: `task-design-architecture` produces the design and `task-breakdown-design` turns it into a task graph (or, in review mode, critiques a graph someone else wrote). `task-migrate-architecture` covers the other direction - moving an existing system to a new state rather than designing a new one. All target the architect or tech lead who owns the build. `task-oncall-start` covers live incident work - triage, route, and drive to a confirmed root cause.

## Atomic Skills

Atomic skills provide focused, reusable patterns. Hidden from the slash menu (`user-invocable: false`) and referenced only by workflow skills.

| Skill                           | Description                                                                                                                  | Composed By                                                                                  |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `system-boundary-design`        | Formal boundary modeling for module and service decomposition                                                                | `task-design-architecture`, `task-migrate-architecture`                                      |
| `strangler-fig-pattern`         | Strangler fig migration pattern - incremental traffic routing from legacy to new system with coexistence phases              | `task-migrate-architecture`                                                                  |
| `architecture-capacity`         | Throughput estimation, scaling analysis, and bottleneck prediction                                                           | `task-design-architecture`                                                                   |
| `backend-caching`               | Caching patterns, response optimization, and serialization efficiency. Adapts to detected ecosystem.                         | `task-design-architecture`                                                                   |
| `architecture-review-lens`      | Review lens for architecture artifacts - severity taxonomy, completeness audit, consistency check, criteria scoring, verdict | All 4 authoring workflows in their Review Mode                                                |
| `architecture-data-consistency` | Consistency strategy across data boundaries - strong vs eventual, outbox, saga, compensation, schema evolution               | `task-design-architecture`, `task-migrate-architecture`, `incident-root-cause`               |
| `oncall-investigate`            | Structured investigation for non-incident oncall work - support tickets, operational questions, unexpected behavior, performance concerns | `task-oncall-start`                                                              |
| `incident-root-cause`           | Active production incident investigation with blast radius assessment and containment-first analysis                         | `task-oncall-start`                                                                          |
| `log-analysis`                  | Structured log analysis - time-window isolation, correlation ID tracing, frequency analysis, and healthy/unhealthy comparison | `oncall-investigate`                                                                        |
| `root-cause-hypothesis`         | Generate ranked root cause hypotheses with confidence levels and evidence                                                    | `incident-root-cause`                                                                        |
| `ops-observability-fetch`       | Fetch evidence (issues, metrics, logs, traces, deploys, monitors) from Sentry/Datadog/Honeycomb MCP; paste-mode fallback     | `task-oncall-start`, `oncall-investigate`, `incident-root-cause`, `log-analysis`             |

## Core Atomics Used

The architecture workflow skills compose with these core atomics via `Use skill:`:

- `nfr-specification` - elicit and structure NFRs from business context into measurable SLOs and constraints
- `tradeoff-analysis` - structured architectural decision and trade-off documentation
- `architecture-guardrail` - layer violation and boundary erosion detection
- `ops-engineering-governance` - engineering process and guardrail evolution
- `review-blast-radius` - failure propagation and change impact scope
- `ops-failure-classification` - classify production failures by type and layer
- `failure-propagation-analysis` - trace failure paths across boundaries
- `ops-observability` - structured logging, metrics, and distributed tracing
- `ops-resiliency` - circuit breakers, retries, timeouts, bulkheads
- `backend-idempotency` - idempotency key pattern for safe retries
- `ops-release-safety` - rollout, rollback, and deployment risk patterns
- `ops-backward-compatibility` - API and data contract compatibility
- `dependency-impact-analysis` - deployment ordering and dependency impact
- `backend-db-migration` - migration sequencing, reverse-migration availability, and rollback
- `backend-db-indexing` - database index strategy and query optimization
- `architecture-concurrency` - threading models and synchronization
- `stack-detect` - project tech stack detection
- `backend-api-guidelines` - REST API design conventions (HTTP methods, RFC 9457 errors, pagination, idempotency)
- `review-change-risk` - pre-implementation risk classification
- `ops-feature-flags` - feature flag lifecycle, gradual rollout, and cleanup
- `review-pr-risk` - score a triggering PR change during incident root-cause analysis

## Skill Dependency Index

### Workflow -> Atomics

| Workflow                            | Atomic Skills Used                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-design-architecture`          | `nfr-specification`, `architecture-review-lens` (review mode), `system-boundary-design`, `tradeoff-analysis`, `stack-detect`, `architecture-guardrail`, `review-blast-radius`, `architecture-data-consistency`, `backend-idempotency`, `backend-caching`, `ops-resiliency`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-observability`, `backend-db-indexing`, `architecture-capacity`, `ops-release-safety`, `dependency-impact-analysis`, `architecture-concurrency`, `ops-engineering-governance`, `backend-api-guidelines`, `ops-backward-compatibility` |
| `task-migrate-architecture`         | `stack-detect`, `system-boundary-design`, `strangler-fig-pattern`, `architecture-guardrail`, `architecture-data-consistency`, `tradeoff-analysis`, `review-change-risk`, `backend-db-migration`, `backend-db-indexing`, `backend-idempotency`, `ops-backward-compatibility`, `review-blast-radius`, `dependency-impact-analysis`, `ops-failure-classification`, `failure-propagation-analysis`, `ops-resiliency`, `ops-observability`, `ops-engineering-governance`, `ops-release-safety`, `ops-feature-flags`, `architecture-review-lens` (review mode) |
| `task-dependency-upgrade`                 | `stack-detect`, `ops-backward-compatibility`, `review-blast-radius`, `ops-release-safety`, `dependency-impact-analysis`, `architecture-review-lens` (review mode)                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  |
| `task-breakdown-design`             | `stack-detect`, `backend-db-migration`, `ops-backward-compatibility`, `dependency-impact-analysis`, `ops-feature-flags`, `review-blast-radius`, `review-change-risk` (breakdown mode); `stack-detect`, `review-blast-radius` (review mode)                                                                                                                                                                                                                                                                                                                                                                                                          |
| `task-oncall-start`                 | `oncall-investigate`, `incident-root-cause`, `ops-observability-fetch`, `stack-detect`                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           |

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

/task-migrate-architecture
[paste someone's decomposition, consolidation, modernization, or migration plan]

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

**Plan a migration:** one workflow, four shapes. The shape is detected from the request; state it explicitly to override.

```
/task-migrate-architecture
System: E-commerce monolith (Java/Spring Boot), 200k LOC, shared PostgreSQL database
Driver: Teams stepping on each other during deploys, order processing can't scale independently
```

```
/task-migrate-architecture
Services: UserService, ProfileService, PreferenceService, AuthService (4 services, 1 team)
Driver: 15 sync calls per login request, distributed monolith, all share the same DB
```

```
/task-migrate-architecture
System: PHP 5.6 monolith on Apache, custom MVC framework, MySQL with stored procedures
Driver: Can't hire PHP 5.6 developers, no community support, scaling ceiling at 200 RPS
```

```
/task-migrate-architecture
Change: Rename user_id column to account_id across orders table (50M rows, multi-service)
Database: PostgreSQL
Deployment: Rolling, zero-downtime required
```

**Assess a dependency upgrade:**

```
/task-dependency-upgrade
Upgrade: Spring Boot 3.3 -> 3.5
```

**Break a system design into an engineering task graph (or review a breakdown):**

`task-breakdown-design` is dual-mode. Paste a design to get a task graph; paste an authored task plan to get a severity-tagged review of it.

```
/task-breakdown-design
[paste a task-design-architecture proposal, HLD, or LLD here]

/task-breakdown-design
[paste an authored task plan; optionally include the design it implements]
```

**Start an oncall rotation or triage an alert:**

```
/task-oncall-start
Starting my oncall rotation for the payments team. What should I check first?

/task-oncall-start
[paste the alert, ticket, or Slack message to triage]
```
