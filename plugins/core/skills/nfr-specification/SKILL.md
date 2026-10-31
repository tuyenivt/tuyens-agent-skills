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
- Each SLO states the measurement method, not just the target value; in the bullet sections the method follows the value after a comma (`- MTTR target: 30 min, alert to resolved, measured from the paging tool`). A cadence word ("monthly") fixes the window as the calendar month unless the contract says otherwise
- Surface conflicts between stated NFRs with resolution options, and infeasible targets with the achievable frontier - never silently pick one or write down an impossible target. A conflict may pit a target against a proposed mechanism (a latency target against synchronous dual-write); mechanisms count
- Surface gaps explicitly - unstated NFRs become hidden assumptions
- When business context implies a regulated domain (payments, healthcare, personal data), name every standard or statute the signals implicate (privacy and card data together name GDPR and PCI DSS; bookkeeping retention names the statute, HGB or Code de commerce, with the provision as a Gaps question when unknown), tag each `(assumed: <basis>)`, and add its confirmation question to Gaps
- The predicate runs per field, not per category: a field with topical signal but no stated value ("handle Black Friday", "payments" with no auth mechanism named) gets a defensible default tagged `(assumed: basis)` plus a confirmation question in Gaps; a field with no signal at all reads `not specified` and is listed in Gaps, and a sibling's number licenses nothing (a p99 does not imply a p95). Never present an invented number as confirmed; with no baseline figure anywhere (a figure derived from stated ones counts, tagged `(derived: ...)`), an assumed throughput or volume default is relative (a multiplier of the baseline), never an absolute, while an assumed latency default is an absolute taken from the domain norm its tag names. Reuse one assumption identically wherever it applies on the same basis (a peak multiplier across Performance's Peak throughput and Scalability's Current rate, not across growth projections), and one assumption reused across sections gets one Gaps question
- A conflict may be raised between two assumed defaults; say so in the entry, since answering the Gaps questions may dissolve it
- Team size, incident history, and existing contracts are business context and may ground a default; incident history of a system that shares the new system's database, on-call, or request path counts

## Patterns

### Six NFR Categories

Elicit across all six. For each, extract from context or ask the requester. When no one can answer (non-interactive run), apply the assumed-default rule above.

**Performance**

- Latency: p50 / p95 / p99 per operation class (read / write / batch) - one row per percentile and class the context supports
- Throughput: requests per second sustained (baseline) and at peak, plus burst when a shorter spike is expected - one row each
- Response budget: breakdown across layers if multi-service
- Batch completion: a job that must finish by a clock time (statements by 06:00, reconciliation by 08:00) is a Performance row whose target is the deadline and whose measurement is the job's completion timestamp

**Availability**

- Uptime SLO, and the SLA it sits behind when one exists
- RTO (recovery time objective, from disruption onset) and RPO (recovery point objective)
- Planned maintenance window: allowed or zero-downtime required (recorded in Operability's Deployment field)

**Scalability**

- Today's scale: users, data volume, request rate
- Growth: 12-month and 3-year projections
- Scaling model: horizontal / vertical / mixed, and stateless or stateful

**Security**

- Authentication mechanism (OIDC sign-in with OAuth 2.0 access-token validation at the API, mTLS, API key, session)
- Authorization model (RBAC, ABAC, resource-owner)
- Data sensitivity classification: PII / cardholder data / PHI / none
- Compliance standards by name: GDPR, SOC 2, PCI DSS, HIPAA - or "none identified"

**Operability**

- Deployment model: zero-downtime / canary / blue-green / maintenance window
- Observability: log retention, metrics granularity, tracing coverage
- On-call: MTTR target (alert to resolved), alert acknowledgement target

**Data**

- Consistency model per operation class (strong / eventual / mixed), with how it is verified (a read-your-writes test, a replication-lag metric); for eventual operations the staleness bound (the maximum replication lag a reader may observe); delivery semantics (at-least-once with idempotent-consumer dedup, or exactly-once processing within a named transactional scope such as Kafka transactions) when the system consumes or emits events
- Retention: duration, archival vs deletion; a retention floor longer than a deletion ceiling on the same data is a conflict
- Volume growth rate and storage budget

### Distinguish SLO from SLA

SLOs are internal targets that drive design and alerting. SLAs are contractual obligations to customers with penalties. Record them as separate rows when both exist, labelled `Uptime SLO` and `Uptime SLA (contractual)` so the contractual one is identifiable.

An SLO must be at least as strict as the SLA it sits behind - the gap is the margin that lets you detect and fix a breach before it costs money. An SLO looser than its SLA is a conflict; record it as one. A dependency's contractual availability (a payments partner's 99.9%) is its own row, `Upstream <name> SLA (contractual)`, and an SLO stricter than a hard dependency's SLA is a conflict unless the design names what absorbs the gap; a dependency's rate limit is likewise `Upstream <name> rate limit` under Performance, and a hard dependency's maintenance window is a Notes entry on its `Upstream <name> SLA (contractual)` row when that row has a Target, otherwise a Gaps entry naming the dependency, as is a soft dependency's window. A contractual target on latency or delivery time is a Performance row labelled `<metric> SLA (contractual)`; the Uptime SLA row stays `not specified` unless uptime itself is contracted.

## Output Format

The Consistency line's staleness segment is written only for eventual operations, its delivery segment only when the system consumes or emits events.

```markdown
## Non-Functional Requirements

### Performance

| Metric              | Target   | Measurement            | Notes                          |
| ------------------- | -------- | ---------------------- | ------------------------------ |
| p99 read latency    | < 200ms  | API gateway percentile | (assumed: B2B API norm)        |
| p95 read latency    | < 80ms   | API gateway percentile | (assumed: B2B API norm)        |
| p99 write latency   | < 500ms  | API gateway percentile | Includes DB write              |
| Sustained throughput| 400 RPS  | p95 of 1-minute averages, non-peak days | Stated baseline         |
| Peak throughput     | 1000 RPS | 1-minute average, window not specified | (assumed: Black Friday 2.5x multiplier) |
| Response budget     | 200ms = gateway 10 + service 40 + DB 150 | Per-layer traces | Sums to the p99 read target (assumed: DB-dominant split of the assumed p99) |

### Availability

| Metric                    | Target   | Measurement                       | Notes |
| ------------------------- | -------- | --------------------------------- | ----- |
| Uptime SLO                | 99.95%   | Rolling 30-day window             |       |
| Uptime SLA (contractual)  | 99.9%    | Calendar month, per contract      |       |
| Max downtime per 30 days  | 21.6 min | Derived from the SLO window       | (derived: 0.05% x 43,200 min) |
| RTO                       | < 15 min | Disruption onset to restored, measured from the incident timeline |       |
| RPO                       | < 5 min  | Replication lag at failover (last committed write vs restored state) |       |

### Scalability

- Current: {users / RPS / data volume}
- 12-month target: {projected growth}
- 3-year target: {projected growth}
- Scaling model: {horizontal / vertical / mixed}, {stateless / stateful: <what holds state>}

### Security

- Authentication: {mechanism}
- Authorization: {model}
- Data classification: {PII / cardholder data / PHI / none}
- Compliance: {standards | none identified - <why nothing applies>}{; not implicated: <nearby standard the system touches> - <why>}

### Operability

- Deployment: {zero-downtime / canary / blue-green / maintenance window allowed}
- MTTR target: {minutes, alert to resolved, measured from <source>}
- Alert acknowledgement target: {minutes, alert to acknowledged, measured from <source>}
- Log retention: {days}
- Tracing coverage: {percentage of requests or specific services}
- Metrics granularity: {per-second / per-minute / per-5-minute}

### Data

- Consistency: {strong / eventual / mixed - specify which operations, verified by <how>}{; staleness bound <N s>}{; delivery: at-least-once with dedup / exactly-once processing within <scope>}
- Retention: {policy}
- Volume growth: {estimate}
- Storage budget: {amount}

## NFR Conflicts

- {tension between two stated (or assumed - say which) targets, or a target and the proposed mechanism}: (a) {resolution option with tradeoff}; (b) {resolution option with tradeoff} - decision left to the owner
- {infeasible target}: floor is {the achievable frontier and what approaching it costs}

## NFR Gaps

- {NFR not specified that matters for this system type}
- {confirmation question for each `(assumed)` target}
```

Always produce all six sections plus Conflicts and Gaps. Every field accepts `not specified`: a field with no business signal reads it and is listed in Gaps, and its Notes cell holds only an `observed: <value>` when a measurement exists, otherwise stays empty. When there is one layer, the Response budget row's Target reads `n/a - single service` and its Measurement and Notes are empty. A stated rate or availability figure keeps its stated window in Measurement (`held for 3 min`); with no window stated, Measurement reads `<method>, window not specified` and Gaps asks for it. An empty Conflicts or Gaps section is the single bullet `- none identified`. The table rows above are the illustrative shape; emit the rows the context supports. Omit the `Uptime SLA (contractual)` row when the context states there is no customer SLA; when it is silent, the row reads `not specified` and Gaps asks whether one exists. An `Upstream <name> SLA (contractual)` row exists only for a named hard dependency.

`(assumed: basis)` goes in the Notes column where a table has one, and directly after the value everywhere else (`- MTTR target: 30 min, alert to resolved, measured from the paging tool (assumed: 24/7 on-call stated, no MTTR given)`). Every `(assumed)` tag anywhere gets its confirmation question in Gaps. A value the context states carries no tag; a number computed from stated figures is tagged `(derived: <arithmetic>)` and needs no Gaps question, and one computed from an assumed value keeps that value's `(assumed)` tag; an observed figure that is not the target goes in Notes as `observed: <value>`. `(derived: <arithmetic>)` and `observed: <value>` take the same placement as `(assumed: basis)`: the Notes column where a table has one, directly after the value everywhere else.

An infeasible target is not a conflict between two stated NFRs - no choice between them makes it attainable. A target arithmetic or physics forbids under the other stated requirements (p99 50ms for a strongly consistent cross-continent write) is infeasible, and its frontier names the floor and which requirement relaxing would lift it; a target the proposed mechanism cannot meet but another could (`never stale` over a read path the design makes eventually consistent) is a conflict against that mechanism; a conflict needs two figures (stated or assumed - say which), or a figure against a proposed mechanism. A case is recorded once, as whichever applies. Record it in Conflicts with the achievable frontier: "p99 50ms with strong consistency across US-East and EU is below the cross-continent round trip (~70-90ms): the floor is one round trip plus commit, ~75-100ms - or 50ms per-region with eventual cross-region convergence."

## Avoid

- Treating NFRs as a checklist - each must connect to a design decision
