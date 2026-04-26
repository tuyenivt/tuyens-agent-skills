---
name: nfr-specification
description: Elicit and structure Non-Functional Requirements from business context into measurable SLOs and constraints
metadata:
  category: architecture
  tags: [architecture, nfr, slo, requirements, quality-attributes]
user-invocable: false
---

# NFR Specification

> This atomic is composed by workflows - do not invoke directly. Primary consumer: `task-design-architecture` Section 1.

## When to Use

- Before architecture design to convert vague quality expectations into measurable targets
- When business context exists but NFRs are implicit or missing
- When SLO baselines are needed to drive observability and capacity planning sections
- Output feeds directly into `task-design-architecture` (Section 1 and 6) and `tradeoff-analysis` as constraint inputs

## Rules

- Every NFR must produce at least one measurable threshold - no vague statements ("must be fast")
- SLOs must state the measurement method, not just the target value
- Compliance and security NFRs must name the specific standard or regulation, not generic categories
- Conflicting NFRs must be surfaced explicitly - do not silently pick one
- Missing NFRs are as important as stated ones - call out gaps
- When business context implies a regulatory domain (payments, healthcare, personal data), name the likely compliance standard and ask for confirmation rather than omitting it

## Pattern

### NFR Categories

Elicit NFRs across these six categories. For each, extract from business context or ask:

**Performance**

- Latency targets: p50, p95, p99 thresholds per operation type (read vs write vs batch)
- Throughput: requests per second at peak, sustained, and burst
- Response time budget: breakdown across system layers if multi-service

**Availability**

- Uptime target: expressed as SLO percentage and maximum allowed downtime per month
- Recovery objectives: RTO (recovery time objective) and RPO (recovery point objective)
- Planned maintenance window: allowed or zero-downtime required

**Scalability**

- Current scale: users, data volume, request rate today
- Growth projection: expected scale in 12 months and 3 years
- Scaling model: horizontal, vertical, or both; stateless or stateful constraints

**Security**

- Authentication mechanism required (JWT, OAuth2, mTLS, API key)
- Authorization model (RBAC, ABAC, resource-owner checks)
- Data sensitivity: PII, PCI, PHI classification and handling requirements
- Compliance standards: GDPR, SOC 2, PCI-DSS, HIPAA - name specifically

**Operability**

- Deployment model: zero-downtime required, canary/blue-green acceptable, maintenance window allowed
- Observability requirements: logging retention, metrics granularity, tracing coverage
- On-call expectations: MTTR target, alert response SLA

**Data**

- Consistency model required: strong or eventual; which operations need which
- Data retention: how long data must be kept, archival vs deletion policy
- Volume: expected data growth rate, storage budget

### Output Format

Produce an NFR table and a constraints list:

```markdown
## Non-Functional Requirements

### Performance

| Metric            | Target   | Measurement            | Notes                |
| ----------------- | -------- | ---------------------- | -------------------- |
| p99 read latency  | < 200ms  | API gateway percentile | Under peak load      |
| p99 write latency | < 500ms  | API gateway percentile | Includes DB write    |
| Peak throughput   | 1000 RPS | Sustained over 5 min   | Black Friday profile |

### Availability

| Metric     | Target   | Measurement              |
| ---------- | -------- | ------------------------ |
| Uptime SLO | 99.9%    | Rolling 30-day window    |
| RTO        | < 15 min | From alert to restored   |
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
Tracing coverage: {percentage of requests traced or specific services}
Metrics granularity: {per-second / per-minute / per-5-minute}

### Data

Consistency: {strong / eventual / mixed - specify which operations}
Retention: {policy}
Volume growth: {estimate}

## NFR Conflicts

[List any conflicting NFRs - e.g., "strong consistency requirement conflicts with 99.9% availability target under network partition"]

## NFR Gaps

[List NFRs not specified that are important for this system type - e.g., "no RPO stated for a write-heavy system"]
```

## Avoid

- Accepting "as fast as possible" or "always available" - push for numbers
- Treating NFRs as a checklist - each must connect to a design decision
- Omitting the gap section - unstated NFRs become hidden assumptions
- Conflating SLOs (targets) with SLAs (contractual obligations) - keep them separate
- Specifying NFRs more precisely than the business context justifies - state confidence level
