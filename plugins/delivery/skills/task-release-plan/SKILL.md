---
name: task-release-plan
description: Staff-level production release plan before deploying to production - rollout strategy selection, backward compatibility assessment, DB migration ordering, observability readiness check, and rollback plan. Use before deploying a feature, migration, integration, or dependency upgrade to production.
metadata:
  category: ops
  tags: [release, deployment, rollout, rollback, safety, blast-radius]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Release Plan -- Staff Edition

## Purpose

Staff-level release planning that converts change descriptions into safe, production-ready rollout plans:

- **Safety-first rollout** -- every release has a rollback plan before it ships
- **Blast radius control** -- contain failures to the smallest possible scope
- **Backward compatibility** -- validate contract and schema compatibility before deployment
- **Observability readiness** -- confirm monitoring and alerting before traffic arrives
- **AI-era risk awareness** -- high code velocity with lower comprehension increases hidden coupling and drift risk

This skill runs BEFORE deployment. It focuses on risk identification and rollout safety, not code quality or performance.

## When to Use

- Before deploying a feature or change to production
- Before running a database migration in production
- When introducing a new external integration or async flow
- When upgrading dependencies or platform versions
- When deploying changes that affect shared resources or public APIs
- When traffic patterns are expected to change significantly

Not for post-deploy monitoring (handled by SRE/oncall) or pre-implementation risk assessment (use `task-design-risk-analysis`).

## Depth Levels

| Depth      | When to Use                                                             | What Produces                                            |
| ---------- | ----------------------------------------------------------------------- | -------------------------------------------------------- |
| `quick`    | Low-risk release or "is this safe to ship?" fast check                  | Rollout sequence + top 3 risks + rollback trigger        |
| `standard` | Default - most production releases                                      | All 8 phases                                             |
| `deep`     | High-risk release, canary with metrics thresholds, or new critical path | All 8 phases + canary metrics plan + rollback drill plan |

**Quick depth produces:**

- Risk level and blast radius (2-3 sentences)
- Rollout sequence (ordered steps)
- Top 3 risks with mitigation
- Rollback trigger condition

**Deep depth adds (on top of standard):**

- Canary metrics plan: specific metric names, baseline values, and rollback thresholds to monitor during canary
- Rollback drill plan: step-by-step procedure to practice before the release, with time estimates per step
- Post-release monitoring window: what to watch for 24-48 hours after full rollout and who is responsible

Default: `standard`. Use `quick` when the user asks for "release checklist" or "is this safe to ship?" on a low-risk change. Use `deep` for releases that introduce new critical paths, require canary validation, or have complex rollback procedures.

Depth and scope are independent. Example: `quick +review` = risk snapshot + code review findings.

## Scope

Before starting the analysis, ask the user which scope they need:

| Scope    | What runs                                                      |
| -------- | -------------------------------------------------------------- |
| Core     | Phases 1-8 only (risk, compatibility, rollout, rollback, etc.) |
| + Review | Core + delegate to skill: `task-code-review`                   |
| + Perf   | Core + delegate to skill: `task-code-perf-review`              |
| Full     | Core + Review + Performance                                    |

Default: **Core** (if the user doesn't specify, run Core only).

If the user invokes with an explicit scope argument (e.g., `/task-release-plan +review`), skip the question and use that scope directly.

## Inputs

| Input                       | Required | Description                                                         |
| --------------------------- | -------- | ------------------------------------------------------------------- |
| Feature description         | Yes      | What the change does and why                                        |
| PR diff or change summary   | No       | Code changes included in the release                                |
| Architecture change summary | No       | Structural changes (new services, boundary shifts, new async flows) |
| DB migration scripts        | No       | Schema changes to be applied                                        |
| Config changes              | No       | Feature flags, environment variables, infrastructure config         |
| New external integration    | No       | Third-party APIs, services, or data sources added                   |
| Traffic expectation         | No       | Expected load change or traffic pattern shift                       |
| Dependency upgrades         | No       | Library, framework, or platform version changes                     |

Handle partial inputs gracefully. When input is missing, state what additional data would strengthen the analysis.

## Rules

- Every release must have an explicit rollback plan
- Risk assessment comes before rollout strategy recommendation
- Backward compatibility must be validated for any contract or schema change
- Database migrations must be zero-downtime safe
- Observability readiness is a deployment prerequisite, not a follow-up
- Reuse existing skills for domain-specific analysis
- Omit empty sections in output
- Keep output concise, actionable, and prioritized by risk
- When evidence is insufficient, state what is missing
- Always ask: "What happens if we need to roll this back in 10 minutes?"

## Release Planning Model

### 1. Release Risk Classification

**Run first. This frames the entire rollout plan.**

Use skill: `review-pr-risk` for change signal assessment.
Use skill: `review-blast-radius` to determine scope across code, data, and user dimensions.

Evaluate risk signals:

- Cross-module or cross-service impact
- Shared resource modification (DB, cache, queue, config)
- Database schema change
- Public API or event schema change
- New async flow or event introduction
- New external integration or dependency
- Dependency or platform upgrade
- Traffic pattern change

Use skill: `ops-failure-classification` to identify which failure types the change is most susceptible to.

Classify:

- **Release Risk**: Low | Medium | High | Critical
- **Blast Radius**: Narrow | Moderate | Wide | Critical

Risk classification drives rollout strategy -- higher risk demands more conservative rollout.

### 2. Backward Compatibility Assessment

Use skill: `ops-backward-compatibility` to evaluate contract and schema compatibility.

Validate:

- **API compatibility** -- are REST endpoints, request/response contracts, and status codes backward compatible?
- **Event schema compatibility** -- do event changes maintain backward compatibility for existing consumers?
- **Database compatibility** -- does the schema work with both current and previous code versions during rolling deployment?
- **Consumer impact** -- which downstream services or clients are affected?
- **Dual-write requirement** -- is a transition period needed where both old and new formats coexist?

Use skill: `backend-api-guidelines` for API contract standards.
Use skill: `architecture-data-consistency` for consistency strategy across data boundaries.
Use skill: `backend-idempotency` for retry safety during transition periods.

If breaking changes exist, require an expand-contract migration plan before deployment.

### 3. Database Migration Safety

**Skip if no schema changes.**

For complex schema changes (column type changes, table splits, large backfills, multi-service coordination), run `/task-db-migration-plan` first to produce a detailed migration execution plan. This skill consumes that plan's output - do not duplicate the migration planning work here.

Use skill: `backend-db-migration` for expand-contract strategy, lock risk, and backfill safety.
Use skill: `backend-db-indexing` for index impact assessment.

Evaluate:

- **Zero-downtime feasibility** -- can the migration run while the application serves traffic?
- **Expand-and-contract strategy** -- is the migration split into additive and destructive phases?
- **Lock risk** -- does the migration acquire table-level locks on large tables?
- **Index impact** -- do new indexes require long-running builds? Use `CONCURRENTLY` where supported.
- **Data backfill strategy** -- is backfill needed? Estimated duration? Batched or bulk?
- **Rollback plan** -- can the migration be reversed without data loss?

Deploy order for additive changes: code first (handle both schemas) -> migrate -> code that uses new schema.
Deploy order for destructive changes: code stops using old schema -> verify -> migrate to drop.

**New async integrations and microservices:**

When the release introduces a new queue, worker service, or webhook endpoint:
- Deploy infrastructure (queue, topics) before any code that depends on it
- Deploy the consumer (worker, webhook handler) before the producer starts emitting
- For webhook endpoints: the endpoint must be registered with the third party AFTER it is deployed and healthy - not before
- Specify deployment ordering explicitly when multiple new services are involved

### 4. Rollout Strategy Recommendation

Use skill: `ops-release-safety` for rollout, rollback, and deployment risk patterns.
Use skill: `ops-feature-flags` for flag design, gradual rollout sequencing, rollback triggers, and cleanup discipline.

Select strategy based on risk classification:

| Risk Level | Recommended Strategy                                 |
| ---------- | ---------------------------------------------------- |
| Low        | Rolling update, standard deployment                  |
| Medium     | Feature flag or canary (5-10% traffic, 30 min soak)  |
| High       | Feature flag + canary with extended soak (1-4 hours) |
| Critical   | Feature flag + canary + phased rollout over days     |

For each strategy, define:

- **Rollout stages** -- percentage and duration per stage
- **Promotion criteria** -- what signals must be green to advance
- **Rollback trigger** -- what signals trigger automatic or manual rollback
- **Soak time** -- minimum observation period before next stage

Use skill: `ops-resiliency` for circuit breaker and timeout patterns during rollout.

### 5. Observability and Alerting Readiness

**Observability is a deployment prerequisite.**

Use skill: `ops-observability` to evaluate signal coverage.

Verify before deployment:

- **Metrics** -- are RED metrics (Rate, Error, Duration) instrumented for affected paths?
- **Alerts** -- are alert thresholds defined for error rate and latency regressions?
- **Correlation IDs** -- are requests traceable across service boundaries?
- **Tracing** -- are trace spans covering the new or modified code paths?
- **Dashboard** -- does the team dashboard reflect the new feature or change?
- **Rollback triggers** -- are automated rollback criteria tied to observable signals?

For each gap:

- **What is missing** -- specific metric, alert, trace span, or dashboard panel
- **Why it matters for this release** -- what failure mode it would detect
- **What to add before deployment** -- concrete addition with threshold

### 6. Rollback Strategy

**Every release must answer: "How do we undo this in 10 minutes?"**

Use skill: `ops-release-safety` for rollback patterns.
Use skill: `ops-engineering-governance` for prevention strategies.
Use skill: `failure-propagation-analysis` to understand rollback propagation impact.

Define:

- **Code rollback** -- can the previous version be redeployed? Any state incompatibility?
- **Database rollback** -- is the migration reversible? Does rollback require compensating migration?
- **Feature flag fallback** -- can the feature be disabled without redeployment?
- **Data corruption mitigation** -- if partial writes occurred, how to detect and correct?
- **Compensating actions** -- manual or automated steps to restore consistency after rollback
- **Consumer notification** -- do downstream consumers need to be notified of rollback?

Classify rollback complexity:

| Rollback Type    | Speed   | Risk                                 |
| ---------------- | ------- | ------------------------------------ |
| Feature flag     | Instant | Low                                  |
| Code revert      | Minutes | Low                                  |
| Code + DB revert | Hours   | High                                 |
| No rollback      | N/A     | Critical -- requires mitigation plan |

If rollback is not feasible, define a forward-fix strategy with explicit timeline.

### 7. Dependency and Platform Risk

**Skip if no dependency or platform changes.**

Use skill: `dependency-impact-analysis` for deployment ordering and impact assessment.

Evaluate:

- **Breaking change risk** -- does the upgrade introduce breaking API or behavior changes?
- **Transitive dependency impact** -- do transitive dependencies conflict or change behavior?
- **Runtime compatibility** -- is the upgrade compatible with the current runtime?
- **Runtime config impact** -- do default configurations change (thread pools, timeouts, serialization)?
- **Deployment ordering** -- must the dependency be deployed before or after dependent services?

For framework or platform upgrades:

- Review migration guide for breaking changes
- Verify concurrency model compatibility
- Test with production-like configuration, not just defaults
- Plan for rollback if runtime behavior regresses

### 8. Capacity and Load Consideration

**Skip if no traffic impact expected.**

Use skill: `architecture-capacity` for throughput estimation and bottleneck prediction.
Use skill: `backend-caching` for cache pressure and invalidation impact.
Use skill: `architecture-concurrency` for concurrency risk assessment.

Evaluate:

- **Thread/worker pool sizing** -- are thread pools or worker processes sized for the new load?
- **Connection pool sizing** -- do database and HTTP connection pools accommodate the change?
- **Cache pressure** -- does the change invalidate existing caches or increase cache miss rate?
- **Database load** -- does the change introduce new query patterns or increase write volume?
- **Burst handling** -- can the system absorb peak traffic after rollout?

If the change introduces a new hot path or significantly changes traffic distribution, require a load test before production deployment.

## Output

```markdown
## Release Summary

Feature:
Risk Level: Low | Medium | High | Critical
Blast Radius: Narrow | Moderate | Wide | Critical

## Compatibility Assessment

- API: compatible | breaking (migration plan required)
- Event schema: compatible | breaking (migration plan required)
- Database: compatible | breaking (expand-contract required)
- Consumer impact: none | list affected consumers

## Recommended Rollout Strategy

Strategy:
Stages:
Promotion criteria:
Rollback trigger:
Soak time:

## Database Migration Plan

- Migration pattern: additive | expand-contract | destructive
- Lock risk: none | low | high (mitigation required)
- Backfill needed: yes (estimated duration) | no
- Rollback plan:

## Observability Checklist

- [ ] Metrics: RED metrics for affected paths
- [ ] Alerts: error rate and latency thresholds defined
- [ ] Tracing: spans covering new/modified paths
- [ ] Dashboard: updated to reflect the change

## Rollback Plan

- Code rollback: feasible | not feasible (reason)
- DB rollback: reversible | irreversible (forward-fix plan)
- Feature flag fallback: available | not available
- Data recovery plan: not needed | specific recovery steps
- Estimated rollback time:

## Dependency and Platform Risk

- Upgrade impact: none | compatible | breaking (migration required)
- Runtime risk: none | config change | behavioral change
- Deployment ordering:

## Capacity Considerations

- Traffic impact: none | moderate increase | significant change
- Resource risk: none | connection pool | cache pressure | DB load
- Load test required: yes | no

## Staff-Level Risk Notes

- 3-5 systemic risk insights about this release.

## Canary Metrics Plan (deep only)

Define specific metrics to monitor during canary deployment:

| Metric        | Baseline              | Warning Threshold    | Rollback Threshold     | Owner  |
| ------------- | --------------------- | -------------------- | ---------------------- | ------ |
| {metric name} | {current p99 or rate} | {10% above baseline} | {rollback if exceeded} | {team} |

Minimum metrics to define:

- Error rate for affected endpoints
- p99 latency for affected endpoints
- Downstream error rate (if dependency calls are involved)
- Business metric (if applicable - order completion rate, payment success rate)

**Canary soak window**: {minimum time before advancing - e.g., 30 minutes for low-risk, 2 hours for high-risk}

## Rollback Drill Plan (deep only)

Step-by-step procedure to practice before the release goes live:

| Step | Action                                                             | Who     | Time Estimate |
| ---- | ------------------------------------------------------------------ | ------- | ------------- |
| 1    | Detect rollback trigger (alert fires or metric threshold exceeded) | On-call | < 2 min       |
| 2    | {First rollback action - e.g., disable feature flag}               | {Role}  | {Time}        |
| 3    | {Second rollback action - e.g., revert code deploy}                | {Role}  | {Time}        |
| 4    | {Database rollback if needed}                                      | {Role}  | {Time}        |
| 5    | Verify system stable (error rate returns to baseline)              | On-call | {Time}        |

**Total estimated rollback time**: {sum of steps}
**Practice recommended**: Run through this procedure in staging before production release
```

### Output Constraints

- Risk classification always comes before rollout recommendation
- Findings ordered by deployment impact: compatibility > migration > rollout > observability > rollback
- Omit empty sections
- Every recommendation must be actionable and deployment-specific
- No generic deployment advice ("test thoroughly", "monitor closely")
- Prioritize by blast radius containment potential
- Optimize for token efficiency and deployment readiness

## Self-Check

- [ ] Risk level and blast radius explicitly classified; rollout strategy matches risk level
- [ ] Rollback plan covers code, DB, and feature flag dimensions; trigger is a specific observable condition
- [ ] DB migration order follows expand-contract; backward compatibility validated for the rolling window
- [ ] Every breaking change (API, event, schema) has a migration plan - not just a flag
- [ ] Promotion criteria are measurable signals, not time-based
- [ ] "No rollback feasible" scenario acknowledged if it exists; observability gaps have concrete remediations
- [ ] Plan can be handed to an on-call engineer at 2am and followed without clarification

## Avoid

- Generic deployment checklists without risk-specific analysis
- Restating the full PR diff or feature description
- Code review or performance commentary (use dedicated skills)
- Recommendations without blast radius context
- Rollout plans without rollback strategy
- Database migrations without zero-downtime assessment
- Ignoring AI-generated code velocity as a contributor to hidden coupling
- Treating all releases as equal risk regardless of change scope
- Proposing overly conservative rollout for genuinely low-risk changes

