---
name: nfr-specification
description: Elicit Non-Functional Requirements from business context into measurable SLOs, constraints, conflicts, and gaps across six quality categories.
metadata:
  category: architecture
  tags: [architecture, nfr, slo, requirements, quality-attributes]
user-invocable: false
---

# NFR Specification

## When to Use

- Converting vague quality expectations ("fast", "reliable") into measurable targets before architecture design
- Producing SLO baselines that observability and capacity planning will reference
- Surfacing conflicting or missing quality requirements early

## Rules

- Every quantitative NFR produces at least one measurable threshold - never "must be fast". Security, scaling model, and consistency are categorical choices; each still names the specific mechanism or standard, never a generic category.
- Each SLO states the measurement method, not just the target value; in the bullet sections the method follows the value after a comma (`- MTTR target: 30 min, alert to resolved, from the paging tool`). A cadence word ("monthly") fixes the window as the calendar month unless the contract says otherwise
- Surface conflicts between stated NFRs with resolution options, and infeasible targets with the achievable frontier - never silently pick one or write down an impossible target. A conflict may pit a target against a proposed mechanism (a latency target against synchronous dual-write); mechanisms count
- Surface gaps explicitly - unstated NFRs become hidden assumptions
- When business context implies a regulated domain (payments, healthcare, personal data), name every standard the signals implicate (privacy and card data together name GDPR and PCI DSS), tag each `(assumed: <basis>)`, and add its confirmation question to Gaps
- The predicate runs per field, not per category: a field with topical signal but no stated value ("handle Black Friday", "payments" with no auth mechanism named) gets a defensible default tagged `(assumed: basis)` plus a confirmation question in Gaps; a field with no signal at all reads `not specified` and is listed in Gaps, and a sibling's number licenses nothing (a p99 does not imply a p95). Never present an invented number as confirmed; with no baseline figure anywhere, an assumed default is relative (a multiplier of the baseline), never an absolute. Reuse one assumption identically wherever it applies on the same basis (a peak multiplier across Performance and Scalability's peak, not across growth projections), and one assumption reused across sections gets one Gaps question
- A conflict may be raised between two assumed defaults; say so in the entry, since answering the Gaps questions may dissolve it
- Team size, incident history, and existing contracts are business context and may ground a default; incident history of a system that shares the new system's database, on-call, or request path counts

## Patterns

### Six NFR Categories

Elicit across all six. For each, extract from context or ask the requester. When no one can answer (non-interactive run), apply the assumed-default rule above.

**Performance**

- Latency: p50 / p95 / p99 per operation class (read / write / batch) - one row per percentile and class the context supports
- Throughput: requests per second sustained (baseline) and at peak, plus burst when a shorter spike is expected - one row each
- Response budget: breakdown across layers if multi-service

**Availability**

- Uptime SLO, and the SLA it sits behind when one exists
- RTO (recovery time objective, from disruption onset) and RPO (recovery point objective)
- Planned maintenance window: allowed or zero-downtime required (recorded in Operability's Deployment field)

**Scalability**

- Today's scale: users, data volume, request rate
- Growth: 12-month and 3-year projections
- Scaling model: horizontal / vertical / mixed, and stateless or stateful

**Security**

- Authentication mechanism (OIDC ID token or OAuth 2.0 bearer-token validation, mTLS, API key, session)
- Authorization model (RBAC, ABAC, resource-owner)
- Data sensitivity classification: PII / cardholder data / PHI / none
- Compliance standards by name: GDPR, SOC 2, PCI DSS, HIPAA - or "none identified"

**Operability**

- Deployment model: zero-downtime / canary / blue-green / maintenance window
- Observability: log retention, metrics granularity, tracing coverage
- On-call: MTTR target (alert to resolved), alert response SLA

**Data**

- Consistency model per operation class (strong / eventual / mixed)
- Retention: duration, archival vs deletion; a retention floor and a deletion ceiling on the same data are a conflict
- Volume growth rate and storage budget

### Distinguish SLO from SLA

SLOs are internal targets that drive design and alerting. SLAs are contractual obligations to customers with penalties. Record them as separate rows when both exist, labelled `Uptime SLO` and `Uptime SLA (contractual)` so the contractual one is identifiable.

An SLO must be at least as strict as the SLA it sits behind - the gap is the margin that lets you detect and fix a breach before it costs money. An SLO looser than its SLA is a conflict; record it as one.

## Output Format

```markdown
## Non-Functional Requirements

### Performance

| Metric              | Target   | Measurement            | Notes                          |
| ------------------- | -------- | ---------------------- | ------------------------------ |
| p99 read latency    | < 200ms  | API gateway percentile | (assumed: B2B API norm)        |
| p95 read latency    | < 80ms   | API gateway percentile | (assumed: B2B API norm)        |
| p99 write latency   | < 500ms  | API gateway percentile | Includes DB write              |
| Sustained throughput| 400 RPS  | p95 of 1-minute averages, non-peak days | Stated baseline         |
| Peak throughput     | 1000 RPS | 1-minute average held over 5 min | (assumed: Black Friday 2.5x multiplier) |
| Response budget     | 200ms = gateway 10 + service 40 + DB 150 | Per-layer traces | n/a - single service when there is one layer |

### Availability

| Metric                    | Target   | Measurement                       | Notes |
| ------------------------- | -------- | --------------------------------- | ----- |
| Uptime SLO                | 99.95%   | Rolling 30-day window             |       |
| Uptime SLA (contractual)  | 99.9%    | Calendar month, per contract      |       |
| Max downtime per 30 days  | 21.6 min | Derived from the SLO window       |       |
| RTO                       | < 15 min | Disruption onset to restored      |       |
| RPO                       | < 5 min  | Max data loss on failure          |       |

### Scalability

- Current: {users / RPS / data volume}
- 12-month target: {projected growth}
- 3-year target: {projected growth, or "not specified"}
- Scaling model: {horizontal / vertical / mixed}, {stateless / stateful: <what holds state>}

### Security

- Authentication: {mechanism | not specified}
- Authorization: {model | not specified}
- Data classification: {PII / cardholder data / PHI / none | not specified}
- Compliance: {standards | none identified - <why nothing applies> | not specified}

### Operability

- Deployment: {zero-downtime / maintenance window allowed}
- MTTR target: {minutes, alert to resolved, measured from <source>}
- Alert response SLA: {minutes to acknowledge, measured from <source>}
- Log retention: {days}
- Tracing coverage: {percentage of requests or specific services}
- Metrics granularity: {per-second / per-minute / per-5-minute}

### Data

- Consistency: {strong / eventual / mixed - specify which operations, verified by <how>}
- Retention: {policy}
- Volume growth: {estimate}
- Storage budget: {amount or "not specified"}

## NFR Conflicts

- {tension between two stated (or assumed - say which) targets}: (a) {resolution option with tradeoff}; (b) {resolution option with tradeoff} - decision left to the owner
- {infeasible target}: floor is {the achievable frontier and what approaching it costs}

## NFR Gaps

- {NFR not specified that matters for this system type}
- {confirmation question for each `(assumed)` target}
```

Always produce all six sections plus Conflicts and Gaps. A field with no business signal reads `not specified` and is listed in Gaps. An empty Conflicts or Gaps section is the single bullet `- none identified`. The table rows above are the illustrative shape; emit the rows the context supports, and omit the SLA row when no SLA exists.

`(assumed: basis)` goes in the Notes column where a table has one, and directly after the value everywhere else (`- MTTR target: 30 min, alert to resolved (assumed: no on-call target stated)`). Every tag anywhere gets its confirmation question in Gaps.

An infeasible target is not a conflict between two stated NFRs - no choice between them makes it attainable. Record it in Conflicts with the achievable frontier: "p99 50ms with strong consistency across US-East and EU is below the cross-continent round trip (~70-90ms): the floor is one round trip plus commit, ~90-100ms, for a US-East/EU quorum committed from the leader's region, about double for a client in the far region, higher only when a third region is farther than the existing peer, or 50ms per-region with eventual cross-region convergence."

## Avoid

- Accepting "as fast as possible" or "always available" - push for numbers
- Treating NFRs as a checklist - each must connect to a design decision
- Omitting the Gaps section - unstated NFRs become hidden assumptions
- Conflating SLOs with SLAs
- Inventing precision the business context does not support - propose defaults only with the `(assumed)` tag
