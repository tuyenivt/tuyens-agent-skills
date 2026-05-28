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
- Surface conflicting NFRs explicitly - do not silently pick one
- Surface gaps explicitly - unstated NFRs become hidden assumptions
- When business context implies a regulated domain (payments, healthcare, personal data), name the likely standard and ask for confirmation rather than omit it
- State confidence when the business context underdetermines a target - do not invent precision

## Patterns

### Six NFR Categories

Elicit across all six. For each, extract from context or ask.

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

| Metric            | Target   | Measurement            | Notes                |
| ----------------- | -------- | ---------------------- | -------------------- |
| p99 read latency  | < 200ms  | API gateway percentile | Under peak load      |
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

[List conflicts - e.g. "strong consistency target conflicts with 99.9% availability under network partition"]

## NFR Gaps

[List NFRs not specified that matter for this system type - e.g. "no RPO stated for a write-heavy system"]
```

Always produce all six sections plus Conflicts and Gaps. If a category has no business signal, state "not specified" and list it in Gaps.

## Avoid

- Accepting "as fast as possible" or "always available" - push for numbers
- Treating NFRs as a checklist - each must connect to a design decision
- Omitting the Gaps section - unstated NFRs become hidden assumptions
- Conflating SLOs with SLAs
- Inventing precision the business context does not support
