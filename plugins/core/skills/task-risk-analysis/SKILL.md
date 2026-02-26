---
name: task-risk-analysis
description: Staff-level proactive engineering risk assessment for proposed changes
metadata:
  category: ops
  tags: [risk-analysis, blast-radius, safety, architecture, deployment, prevention]
  type: workflow
---

# Risk Analysis -- Staff Edition

## Purpose

Staff-level proactive risk assessment that identifies systemic risk before implementation or merge:

- **Risk-first thinking** -- classify risk domains and blast radius before code is written
- **Boundary awareness** -- every change alters boundaries; detect drift and coupling amplification
- **Consistency protection** -- evaluate transaction, idempotency, and async failure modes early
- **Deployment safety** -- assess rollback feasibility and backward compatibility before commit
- **Observability readiness** -- verify detection capability matches the risk profile
- **AI-era risk awareness** -- high code velocity with lower comprehension increases hidden complexity and boundary erosion

This skill runs BEFORE implementation or merge. It focuses on systemic and operational risk, not code quality or performance.

## When to Use

- Before implementing a new feature or large change
- Before merging a significant PR with cross-module impact
- Before executing a database migration plan
- Before introducing async flows, events, or new integrations
- Before a dependency or platform upgrade
- Before a major refactor that shifts boundaries or ownership
- When evaluating an architecture proposal for hidden risk
- When a deployment plan needs risk sign-off

## Inputs

| Input                     | Required | Description                                                         |
| ------------------------- | -------- | ------------------------------------------------------------------- |
| Change description        | Yes      | What is changing and why                                            |
| PR diff or change summary | No       | Code changes included in the proposal                               |
| Architecture proposal     | No       | Structural changes (new services, boundary shifts, new async flows) |
| DB migration plan         | No       | Schema changes to be applied                                        |
| Dependency upgrades       | No       | Library, framework, or platform version changes                     |
| Integration changes       | No       | External APIs, services, or data sources added or modified          |
| Deployment plan           | No       | Rollout strategy, feature flags, migration ordering                 |
| Existing incident history | No       | Past incidents related to the affected area                         |

Handle partial inputs gracefully. When input is missing, state what additional data would strengthen the analysis.

## Rules

- Risk classification comes before mitigation recommendations
- Blast radius assessment is mandatory for every analysis
- Reuse existing skills for domain-specific analysis
- Omit empty sections in output
- Keep output concise, actionable, and prioritized by systemic impact
- When evidence is insufficient, state what is missing
- Focus on systemic and operational risk, not style or code quality
- Do not blame individuals
- Do not overlap with deep performance review or code review
- Avoid trivial observations -- every finding must be actionable
- Always ask: "What fails silently if this goes wrong?"

## Risk Analysis Model

### 1. Change Summary

**Run first. This frames the entire risk assessment.**

Capture:

- **What is changing** -- components, modules, boundaries, data, integrations affected
- **Why** -- business or technical objective driving the change
- **Scope** -- narrow (single module) to wide (cross-service, cross-team)

### 2. Risk Classification

**Classify the change by risk domains.**

Use skill: `change-risk-classification` for pre-implementation risk domain classification.
Use skill: `pr-risk-analysis` for code signal-based risk assessment (when PR diff is available).
Use skill: `failure-classification` to identify which failure types the change is most susceptible to.
Use skill: `architecture-guardrail` to detect boundary erosion risk.
Use skill: `complexity-review` to detect AI-generated complexity amplification.

Evaluate risk domains:

- **Data risk** -- schema migration, data integrity, consistency model change
- **Concurrency risk** -- shared mutable state, race conditions, concurrency model compatibility
- **Transaction boundary change** -- scope expansion, distributed transaction introduction
- **Async/event introduction** -- new event flows, ordering concerns, consumer coupling
- **External integration change** -- new or modified third-party dependency
- **Dependency upgrade** -- framework, library, or platform version change
- **Performance risk** -- new hot paths, query pattern changes, resource contention
- **Security risk** -- authentication, authorization, data exposure changes
- **Architecture drift risk** -- boundary erosion, layer violation, coupling amplification
- **Deployment risk** -- rollback complexity, migration ordering, backward compatibility

Classify:

- **Primary Risk Domains** -- domains with direct, high-confidence risk signals
- **Secondary Risk Domains** -- domains with indirect or lower-confidence risk signals
- **Overall Risk Level**: Low | Medium | High | Critical

### 3. Blast Radius Analysis

**Evaluate the scope and propagation of potential failure.**

Use skill: `blast-radius-analysis` to assess impact across code, data, and user dimensions.
Use skill: `failure-propagation-analysis` to trace cascading failure paths.

Evaluate:

- **Modules affected** -- which internal modules are directly or transitively impacted
- **Shared state touched** -- databases, caches, queues, config stores
- **DB tables impacted** -- schema changes, new query patterns, write amplification
- **Public API contracts modified** -- request/response changes, new endpoints, deprecations
- **Event consumers impacted** -- downstream consumers affected by schema or flow changes
- **Cross-service coupling change** -- new synchronous or asynchronous dependencies
- **Cross-team impact** -- changes that require coordination with other teams

Classify:

- **Blast Radius**: Narrow | Moderate | Wide | Critical

### 4. Consistency and Transaction Risk

**Evaluate data consistency and transaction safety implications.**

Use skill: `data-consistency-modeling` for consistency strategy evaluation.
Use skill: `idempotency` for retry safety assessment.
Use skill: `resiliency` for failure handling pattern assessment.

Evaluate:

- **Transaction boundary changes** -- scope expansion, new distributed boundaries, isolation level changes
- **Idempotency guarantees** -- are new write paths idempotent? What happens on retry?
- **Retry amplification risk** -- can retries compound load during partial failure?
- **Partial failure handling** -- what state is left if the operation fails midway?
- **Distributed consistency impact** -- does the change introduce or modify cross-service consistency requirements?
- **Event ordering concerns** -- does the change assume ordering that is not guaranteed?

### 5. Deployment and Rollback Risk

**Evaluate deployment safety and rollback feasibility.**

Use skill: `release-safety` for rollout and rollback patterns.
Use skill: `backward-compatibility-analysis` for contract compatibility assessment.
Use skill: `dependency-impact-analysis` for deployment ordering and dependency impact.

Evaluate:

- **Backward compatibility** -- are API, event, and data contracts backward compatible?
- **Rolling deployment safety** -- does the change work when old and new versions coexist?
- **DB migration ordering** -- is the migration safe to run before, during, or after code deployment?
- **Feature flag necessity** -- does the risk level warrant a feature flag or kill switch?
- **Rollback feasibility** -- can the change be reverted quickly? What state is left after rollback?
- **Data corruption risk** -- can partial deployment leave data in an inconsistent state?

Classify rollback complexity:

| Rollback Type    | Speed   | Risk                                 |
| ---------------- | ------- | ------------------------------------ |
| Feature flag     | Instant | Low                                  |
| Code revert      | Minutes | Low                                  |
| Code + DB revert | Hours   | High                                 |
| No rollback      | N/A     | Critical -- requires mitigation plan |

### 6. Observability and Detection Readiness

**Evaluate whether existing observability can detect the failure modes identified above.**

Use skill: `observability` to evaluate signal coverage.

Verify:

- **Metrics** -- are RED metrics instrumented for affected paths?
- **Alerts** -- are alert thresholds defined for the failure modes this change introduces?
- **Correlation IDs** -- are requests traceable across affected boundaries?
- **Logging** -- are structured logs covering the new or modified code paths?
- **Health checks** -- are liveness and readiness probes updated for new dependencies?

For each gap:

- What is missing
- Which failure mode it would detect
- What to add before merge or deployment

### 7. Mitigation Strategy

**Recommend specific mitigations proportional to the identified risks.**

Use skill: `engineering-governance` for process, governance, and guardrail recommendations.
Use skill: `engineering-governance` for systemic prevention strategies.
Use skill: `architecture-guardrail` for boundary enforcement recommendations.

Recommend across five categories:

- **Architectural** -- boundary reinforcement, coupling reduction, failure isolation improvements
- **Deployment** -- feature flags, canary strategy, staged rollout, rollback plan
- **Testing** -- contract tests, integration tests, chaos experiments, load tests
- **Monitoring** -- new metrics, alert thresholds, dashboard updates, baseline establishment
- **Governance** -- design doc requirement, ADR requirement, review checklist additions, guardrail updates

Every recommendation must reference the specific risk it mitigates.

## Output

```markdown
## Change Overview

Scope:
Intent:

## Risk Classification

Primary Risk Domains:
Secondary Risk Domains:

Overall Risk Level: Low | Medium | High | Critical

## Blast Radius

Affected Boundaries:
Shared Resources:
External Contracts:
Blast Radius: Narrow | Moderate | Wide | Critical

## Consistency and Transaction Risk

- Transaction impact:
- Idempotency risk:
- Async/event risk:
- Partial failure handling:

## Deployment and Rollback Risk

- Backward compatibility:
- Migration risk:
- Rollback complexity:
- Feature flag recommended: Yes | No

## Observability Readiness

- Metrics: covered | gaps (list)
- Alerts: covered | gaps (list)
- Logging: covered | gaps (list)
- Tracing: covered | gaps (list)

## Mitigation Recommendations

- Architectural:
- Deployment:
- Testing:
- Monitoring:
- Governance:

## Staff-Level Assessment

- Key systemic risks: 3-5 systemic risk insights about this change
- Confidence level: High | Medium | Low (state what data would increase confidence)
- Should require design doc? Yes | No
- Should require ADR? Yes | No
- Should require staged rollout? Yes | No
```

### Output Constraints

- Risk classification always comes before mitigation recommendations
- Findings ordered by systemic impact: risk classification > blast radius > consistency > deployment > observability > mitigation
- Omit empty sections
- Every recommendation must reference the specific risk it mitigates
- No generic safety advice ("test thoroughly", "monitor closely")
- Prioritize by blast radius containment potential
- Optimize for token efficiency and decision readiness

## Avoid

- Code review or performance commentary (use dedicated skills)
- Restating the full PR diff or input description
- Trivial style or formatting observations
- Generic risk warnings without specific context
- Recommendations without blast radius context
- Blaming individuals or teams
- Overlapping with deep performance review or code review scope
- Treating all changes as equal risk regardless of scope
- Proposing overly conservative mitigation for genuinely low-risk changes
- Ignoring AI-generated code velocity as a contributor to hidden coupling

## Key Skills Reference

### Existing Skills Reused

**Risk and Impact Assessment:**

- Use skill: `pr-risk-analysis` for code signal-based risk classification (when PR diff available)
- Use skill: `blast-radius-analysis` for failure propagation and impact scope
- Use skill: `failure-classification` for susceptible failure type identification
- Use skill: `failure-propagation-analysis` for cascading failure path analysis

**Consistency and Transactions:**

- Use skill: `data-consistency-modeling` for consistency strategy evaluation
- Use skill: `idempotency` for retry safety assessment
- Use skill: `resiliency` for failure handling pattern assessment

**Deployment and Compatibility:**

- Use skill: `release-safety` for rollout and rollback patterns
- Use skill: `backward-compatibility-analysis` for contract compatibility assessment
- Use skill: `dependency-impact-analysis` for deployment ordering and dependency impact
- Use skill: `observability` for logging, metrics, and tracing readiness

**Governance and Prevention:**

- Use skill: `architecture-guardrail` for boundary erosion detection and enforcement
- Use skill: `complexity-review` for AI-generated complexity detection
- Use skill: `engineering-governance` for process, governance, and guardrail recommendations
- Use skill: `engineering-governance` for systemic prevention strategies

**Related Workflows:**

- Use skill: `task-code-review-advanced` for code quality assessment (separate concern)
- Use skill: `task-root-cause` for incorporating incident lessons into risk analysis
- Use skill: `task-postmortem` for incorporating postmortem findings into risk analysis
- Use skill: `task-release-plan` for detailed release planning after risk assessment

### Sub-Skills Defined for This Workflow

| Skill                        | Purpose                                                            |
| ---------------------------- | ------------------------------------------------------------------ |
| `change-risk-classification` | Pre-implementation risk domain classification for proposed changes |
