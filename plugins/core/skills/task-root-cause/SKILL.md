---
name: task-root-cause
description: Staff-level incident root cause analysis with containment and prevention
metadata:
  category: ops
  tags: [incident, root-cause, on-call, reliability, containment]
  type: workflow
---

# Root Cause Analysis -- Staff Edition

## Purpose

Staff-level incident analysis optimized for on-call clarity:

- **Contain first, diagnose second** -- prioritize blast radius reduction over exhaustive analysis
- **System-level thinking** -- trace across service boundaries, shared state, and async flows
- **Structured hypotheses** -- evidence-based, ranked by confidence, with verification steps
- **Prevention over patching** -- every incident is a signal about a class of failure

This skill assumes partial code comprehension. Code volume from AI-generated contributions increases architectural drift risk -- account for this when tracing propagation paths.

## When to Use

- Production incident investigation
- On-call triage and escalation support
- Post-incident root cause analysis
- Cascading failure diagnosis
- Incident postmortem preparation

## Inputs

| Input                | Required | Description                                         |
| -------------------- | -------- | --------------------------------------------------- |
| Error or stack trace | Yes      | The primary failure signal                          |
| Log snippets         | No       | Relevant log entries around the failure window      |
| Recent PR diff       | No       | Changes deployed before the incident                |
| Metrics summary      | No       | Latency, error rate, resource utilization snapshots |
| Config snapshot      | No       | Current configuration or recent config changes      |
| Deployment metadata  | No       | Deploy timestamp, version, environment differences  |
| Service map          | No       | Known dependencies and communication patterns       |

## Rules

- Containment recommendations come before diagnosis
- Every hypothesis must cite observable evidence
- Always assess blast radius explicitly
- Do not produce low-level debugging walkthroughs
- Do not focus on code style
- Omit empty sections in output
- Keep output concise and high-signal -- optimize for on-call clarity
- When evidence is insufficient, state what is missing and what signal would resolve ambiguity

## Analysis Model

### 1. Failure Classification

**Run first. This frames the entire investigation.**

Use skill: `failure-classification` to categorize the failure by type, mechanism, and system layer.

Apply domain-specific skills based on classification:

- Concurrency issue: use skill: `concurrency-model` for thread safety and lock patterns
- Data consistency error: use skill: `data-consistency-modeling` for scope and propagation issues
- DB performance degradation or N+1: use skill: `db-indexing` for query patterns
- External dependency failure: use skill: `resiliency` for timeout, retry, and circuit breaker gaps
- Resource exhaustion: check connection pool sizing, thread pool limits, memory bounds

### 2. Blast Radius Assessment

Use skill: `blast-radius-analysis` to determine scope across code, data, and user dimensions.

Additionally assess:

- **Shared resources** -- database, cache, queue, connection pool contention
- **API contract impact** -- are consumers receiving errors or degraded responses?
- **Data corruption risk** -- partial writes, inconsistent state, lost events
- **Cross-service propagation** -- which downstream services are affected?

Use skill: `failure-propagation-analysis` to trace the cascading failure path.

Output blast radius explicitly: Narrow | Moderate | Wide | Critical.

### 3. Immediate Containment

**Prioritize fast blast radius reduction.**

Evaluate these containment options in order of speed:

1. **Rollback** -- if recent deploy correlates, rollback is the fastest containment
2. **Feature flag disable** -- isolate the failing feature without full rollback
3. **Circuit breaker** -- stop cascading to downstream services
4. **Traffic isolation** -- route affected traffic to degraded-mode path
5. **Rate limiting** -- reduce load to buy recovery time
6. **Scaling mitigation** -- add capacity if resource exhaustion is the bottleneck
7. **Data repair** -- if partial writes occurred, assess correction urgency

Use skill: `resiliency` for circuit breaker and retry patterns.
Use skill: `data-consistency-modeling` for data consistency recovery.

### 4. Root Cause Hypothesis

Use skill: `root-cause-hypothesis` to generate ranked hypotheses.

For each hypothesis, require:

- Primary suspect component and mechanism
- Secondary suspects
- Likely triggering change (recent PR, deploy, config change)
- Failure propagation path (from step 2)
- Confidence level with supporting and contradicting evidence
- One concrete verification step

### 5. Observability Gap Detection

Use skill: `observability` to evaluate signal coverage.

For each gap found, state:

- **What signal was missing** -- specific log, metric, trace span, or alert
- **How it slowed diagnosis** -- what question could not be answered
- **What to add** -- concrete observability improvement

Common gaps to check:

- Correlation IDs across service boundaries
- Connection pool saturation metrics
- Circuit breaker state transitions
- Async event processing lag and failure rates
- Health check coverage for critical dependencies

### 6. Systemic Prevention

Use skill: `engineering-governance` for structured prevention recommendations.
Use skill: `architecture-guardrail` to identify boundary weaknesses exposed by the incident.

For each recommendation:

- Address the failure class, not just this instance
- Assign priority: immediate | next sprint | quarterly
- State the blast radius reduction it provides

Categories to cover:

- Architecture guardrails and boundary enforcement
- Monitoring and alerting additions
- Testing improvements (unit, integration, chaos)
- Review checklist and runbook updates
- Deployment safety (canary, feature flags, rollback automation)

## Output

```markdown
## Incident Summary

Failure Type:
Severity: Low | Medium | High | Critical
Blast Radius: Narrow | Moderate | Wide | Critical

## Immediate Containment

- [ ] Action 1 (priority, expected impact)
- [ ] Action 2

## Root Cause Hypothesis

Primary Suspect:
Mechanism:
Triggering Change:
Failure Propagation Path:
Confidence: X%

Secondary Suspect:
Confidence: X%

Verification Steps:

- Step to confirm or reject primary hypothesis

## Observability Gaps

| Missing Signal          | Diagnosis Impact                    | Recommended Addition |
| ----------------------- | ----------------------------------- | -------------------- |
| Signal that was missing | What question could not be answered | What to add          |

## Systemic Risk Insights

- Boundary weakness:
- Coupling issue:
- Shared state risk:

## Long-Term Preventive Actions

| Action          | Failure Class Prevented      | Priority       | Blast Radius Reduction |
| --------------- | ---------------------------- | -------------- | ---------------------- |
| Specific action | Class of failure it prevents | immediate/next | Impact description     |

## Key Takeaways

- 3-5 concise Staff-level insights about the system, not just the incident.
```

### Output Constraints

- Containment section always comes before diagnosis
- Findings ordered by urgency: containment > hypothesis > gaps > prevention
- Omit empty sections
- No low-level debugging walkthroughs
- No code style commentary
- Optimize for token efficiency and on-call readability

## Avoid

- Treating symptoms as root causes
- Generic debugging advice ("check the logs", "restart the service")
- Analysis without blast radius assessment
- Hypotheses without evidence or verification steps
- Prevention that only fixes this specific instance
- Verbose explanations under incident pressure
- Ignoring AI-generated code as a contributing factor to architectural drift

## Key Skills Reference

### Existing Skills Reused

**Failure Analysis:**

- Use skill: `resiliency` for timeout, retry, and circuit breaker patterns
- Use skill: `data-consistency-modeling` for data consistency issues
- Use skill: `db-indexing` for query performance and N+1 detection
- Use skill: `concurrency-model` for concurrency and thread safety issues
- Use skill: `observability` for logging, metrics, and tracing gaps

**Architecture and Prevention:**

- Use skill: `blast-radius-analysis` for impact scope assessment
- Use skill: `architecture-guardrail` for boundary violation detection

### Sub-Skills Defined for This Workflow

| Skill                          | Purpose                                                 |
| ------------------------------ | ------------------------------------------------------- |
| `failure-classification`       | Classify failures by type, mechanism, and system layer  |
| `failure-propagation-analysis` | Trace cascading failure paths across system boundaries  |
| `root-cause-hypothesis`        | Generate ranked hypotheses with confidence and evidence |
| `engineering-governance`       | Systemic prevention and governance strategies           |
