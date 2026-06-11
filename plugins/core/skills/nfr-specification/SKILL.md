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

- Every NFR produces at least one measurable threshold - never "must be fast"
- Each SLO states the measurement method, not just the target value
- Compliance and security NFRs name the specific standard, not a generic category
- Surface conflicting or infeasible NFRs explicitly with resolution options - never silently pick one or write down an impossible target
- Surface gaps explicitly - unstated NFRs become hidden assumptions
- When business context implies a regulated domain (payments, healthcare, personal data), name the likely standard and ask for confirmation rather than omit it
- When context underdetermines a target, propose a defensible default tagged `(assumed: basis)` and add a confirmation question to Gaps - never present an invented number as confirmed

## Patterns

### Six NFR Categories

Elicit across all six. For each, extract from context or ask the requester. When no one can answer (non-interactive run), record the question in Gaps and proceed with an `(assumed)` default.

**Performance**

- Latency: p50 / p95 / p99 per operation class (read / write / batch)
- Throughput: requests per second at peak, sustained, and burst
- Response budget: breakdown across layers if multi-service

**Availability**

- Uptime SLO and maximum allowed downtime per month
- RTO (recovery time objective) and RPO (recovery point objective)
- Planned maintenance window: allowed or zero-downtime required

**Scalability**

- Today's scale: users, data volume, request rate
- Growth: 12-month and 3-year projections
- Scaling model: horizontal / vertical / mixed; stateless or stateful constraints

**Security**

- Authentication mechanism (JWT, OAuth2, mTLS, API key)
- Authorization model (RBAC, ABAC, resource-owner)
- Data sensitivity classification: PII / PCI / PHI / none
- Compliance standards by name: GDPR, SOC 2, PCI-DSS, HIPAA - or "none identified"

**Operability**

- Deployment model: zero-downtime / canary / blue-green / maintenance window
- Observability: log retention, metrics granularity, tracing coverage
- On-call: MTTR target, alert response SLA

**Data**

- Consistency model per operation class (strong / eventual / mixed)
- Retention: duration, archival vs deletion
- Volume growth rate and storage budget

### Distinguish SLO from SLA

SLOs are internal targets that drive design and alerting. SLAs are contractual obligations to customers with penalties. Record them as separate rows when both exist.

## Output Format

```markdown
## Non-Functional Requirements

### Performance

| Metric            | Target   | Measurement            | Notes                          |
| ----------------- | -------- | ---------------------- | ------------------------------ |
| p99 read latency  | < 200ms  | API gateway percentile | (assumed: B2B API norm) - confirm |
| p99 write latency | < 500ms  | API gateway percentile | Includes DB write    |
| Peak throughput   | 1000 RPS | Sustained over 5 min   | Black Friday profile |

### Availability

| Metric     | Target   | Measurement              |
| ---------- | -------- | ------------------------ |
| Uptime SLO | 99.9%    | Rolling 30-day window    |
| RTO        | < 15 min | Alert to restored        |
| RPO        | < 5 min  | Max data loss on failure |

### Scalability

Current: {users / RPS / data volume}
12-month target: {projected growth}
Scaling model: {horizontal stateless / vertical / mixed}

### Security

Authentication: {mechanism}
Authorization: {model}
Data classification: {PII / PCI / PHI / none}
Compliance: {standards or "none identified"}

### Operability

Deployment: {zero-downtime / maintenance window allowed}
MTTR target: {minutes}
Log retention: {days}
Tracing coverage: {percentage of requests or specific services}
Metrics granularity: {per-second / per-minute / per-5-minute}

### Data

Consistency: {strong / eventual / mixed - specify which operations}
Retention: {policy}
Volume growth: {estimate}

## NFR Conflicts

[One entry per conflicting or infeasible target: name the tension, then 1-2 resolution options with tradeoffs, decision left to the owner - e.g. "99.999% uptime conflicts with single-region constraint: (a) relax to 99.9%, (b) add a second region at roughly 2x infra cost"]

## NFR Gaps

[NFRs not specified that matter for this system type, plus a confirmation question for each `(assumed)` target - e.g. "no RPO stated for a write-heavy system"]
```

Always produce all six sections plus Conflicts and Gaps. If a category has no business signal, state "not specified" and list it in Gaps.

## Avoid

- Accepting "as fast as possible" or "always available" - push for numbers
- Treating NFRs as a checklist - each must connect to a design decision
- Omitting the Gaps section - unstated NFRs become hidden assumptions
- Conflating SLOs with SLAs
- Inventing precision the business context does not support - propose defaults only with the `(assumed)` tag
