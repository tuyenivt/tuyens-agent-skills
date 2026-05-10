---
name: task-design-risk-analysis
description: "Pre-implementation risk analysis: blast radius, consistency hazards, deployment safety, observability readiness; adaptive depth."
metadata:
  category: ops
  tags: [risk-analysis, blast-radius, safety, architecture, deployment, prevention]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Risk Analysis -- Staff Edition

## Purpose

Staff-level pre-implementation risk assessment: classify risk domains, blast radius, consistency hazards, deployment safety, and observability readiness. Runs before implementation or merge; focuses on systemic and operational risk, not code quality.

## When to Use

- Before implementing a feature, merging a cross-module PR, or running a DB migration
- Before introducing async flows, events, integrations, or dependency upgrades
- Before a refactor shifting boundaries or ownership
- When a deployment plan or architecture proposal needs risk sign-off

## Depth Levels

| Depth      | When to Use                                                         | What Produces                                               |
| ---------- | ------------------------------------------------------------------- | ----------------------------------------------------------- |
| `quick`    | Pre-PR sanity check or "is this risky?" fast assessment             | Risk matrix only - domains, blast radius, top 3 mitigations |
| `standard` | Default - full pre-implementation risk assessment                   | All 7 sections                                              |
| `deep`     | High-risk change, cross-service redesign, or post-incident redesign | All 7 sections + cascading failure simulation               |

**Quick depth produces:**

- Risk classification (primary domains + overall level)
- Blast radius (Narrow / Moderate / Wide / Critical)
- Top 3 mitigations with specific references to risk domains

**Deep depth adds (on top of standard):**

- Cascading failure simulation: walk through the worst-case failure scenario end-to-end, step by step, to identify gaps in containment and detection

Default: `standard`. Use `quick` when the user asks for "risk check" or "is this safe?" before writing code. Use `deep` for cross-service changes, post-incident redesigns, or changes to auth/payment/data core paths.

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

- Risk classification before mitigation; blast radius is mandatory
- Every recommendation references the specific risk it mitigates
- Focus on systemic and operational risk - not code style, performance review, or individual blame
- State what's missing when evidence is insufficient
- Every finding is actionable - ask "what fails silently if this goes wrong?"
- Omit empty sections; output is concise and prioritized by systemic impact

## Risk Analysis Model

### 0. Determine Analysis Depth

If the user specified `quick` or `deep`, use that. Otherwise default to `standard`, but auto-escalate to `deep` if the change touches auth, payment, PII data core paths, or cross-service ownership boundaries. State the selected depth and rationale before proceeding.

### 1. Change Summary

**Run first. This frames the entire risk assessment.**

Capture:

- **What is changing** -- components, modules, boundaries, data, integrations affected
- **Why** -- business or technical objective driving the change
- **Scope** -- narrow (single module) to wide (cross-service, cross-team)

### 2. Risk Classification

**Classify the change by risk domains.**

Use skill: `review-change-risk` for pre-implementation risk domain classification.
Use skill: `review-pr-risk` for code signal-based risk assessment (when PR diff is available).
Use skill: `ops-failure-classification` to identify which failure types the change is most susceptible to.
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

Use skill: `review-blast-radius` to assess impact across code, data, and user dimensions.
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

Use skill: `architecture-data-consistency` for consistency strategy evaluation.
Use skill: `backend-idempotency` for retry safety assessment.
Use skill: `ops-resiliency` for failure handling pattern assessment.

Evaluate:

- **Transaction boundary changes** -- scope expansion, new distributed boundaries, isolation level changes
- **Idempotency guarantees** -- are new write paths idempotent? What happens on retry?
- **Retry amplification risk** -- can retries compound load during partial failure?
- **Partial failure handling** -- what state is left if the operation fails midway?
- **Distributed consistency impact** -- does the change introduce or modify cross-service consistency requirements?
- **Event ordering concerns** -- does the change assume ordering that is not guaranteed?

### 5. Deployment and Rollback Risk

**Evaluate deployment safety and rollback feasibility.**

Use skill: `ops-release-safety` for rollout and rollback patterns.
Use skill: `ops-backward-compatibility` for contract compatibility assessment.
Use skill: `dependency-impact-analysis` for deployment ordering and dependency impact.
Use skill: `backend-db-migration` when the change involves schema decomposition or migration.
Use skill: `ops-feature-flags` when evaluating feature flag necessity.

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

Use skill: `ops-observability` to evaluate signal coverage.

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

Use skill: `ops-engineering-governance` for process, governance, guardrail, and systemic prevention recommendations.
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

Primary Risk Domains: [list from taxonomy, ordered by confidence, one evidence note per domain]
Secondary Risk Domains:

Overall Risk Level: Low | Medium | High | Critical

## Blast Radius

Affected Boundaries: [bullet list: module/service name -- direct or transitive impact]
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

## Cascading Failure Simulation (deep only)

Walk through the worst-case failure scenario for this change end-to-end:

**Scenario**: {The most likely or highest-impact failure this change introduces}

1. {Trigger}: {What starts the failure - e.g., "payment-gateway timeout"}
2. {Propagation}: {What is affected next and how}
3. {Amplification}: {What shared resource or coupling makes it worse}
4. {User impact}: {What users experience}
5. {Detection}: {How long before the team knows - and what signal fires}
6. {Containment}: {What stops further spread - or why nothing does}
7. {Recovery}: {How the system returns to normal}

**Gap identified**: {What this simulation revealed about missing containment, detection, or recovery}
**Recommendation**: {Specific change to add before this code ships to address the gap}
```

## Self-Check

- [ ] Change summary captures scope, intent, affected components (Section 1)
- [ ] Risk domains (primary and secondary) classified with evidence (Section 2)
- [ ] Blast radius explicitly Narrow / Moderate / Wide / Critical with named boundaries (Section 3)
- [ ] Consistency, idempotency, partial-failure risk assessed (Section 4)
- [ ] Deployment, rollback, backward compatibility assessed; "no rollback feasible" called out if present (Section 5)
- [ ] Observability gaps listed with concrete additions per failure mode (Section 6)
- [ ] Mitigations reference specific risks; proportional to blast radius (Section 7)
- [ ] Staff Assessment states design-doc / ADR / staged-rollout requirements with confidence
- [ ] If depth = deep: cascading failure simulation identifies one containment or detection gap

## Avoid

- Restating the full PR diff or input description
- Generic safety advice ("test thoroughly", "monitor closely") without specific context
- Treating all changes as equal risk; over-mitigating low-risk changes
