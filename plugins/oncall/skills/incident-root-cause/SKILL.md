---
name: incident-root-cause
description: Active production incident investigation with blast radius assessment and containment-first analysis. Use when a service is degraded or down and multiple users are affected. Not for developer debugging of a specific error (use task-code-debug), not for non-incident oncall investigation (use oncall-investigate), not for post-incident writeup (use task-postmortem).
metadata:
  category: ops
  tags: [incident, root-cause, on-call, reliability, containment]
user-invocable: false
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Root Cause Analysis -- Staff Edition

## Purpose

Staff-level incident analysis optimized for on-call clarity:

- **Contain first, diagnose second** -- prioritize blast radius reduction over exhaustive analysis
- **System-level thinking** -- trace across service boundaries, shared state, and async flows
- **Structured hypotheses** -- evidence-based, ranked by confidence, with verification steps
- **Prevention over patching** -- every incident is a signal about a class of failure

This skill assumes partial code comprehension. Code volume from AI-generated contributions increases architectural drift risk -- account for this when tracing propagation paths.

## When to Use

- Active production incident investigation
- On-call triage and escalation support
- Cascading failure diagnosis
- Containment-first analysis during an ongoing outage

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
- When input provides only an error message without logs, metrics, or deploy context: frame incident from what is available, provide containment based on the error class, form hypotheses at lower confidence, and explicitly list the 3-5 evidence items needed to raise confidence

## Analysis Model

### 1. Incident Framing

**Establish timeline and severity before analysis begins.**

From the input, extract:

- **Symptom onset** -- when the issue started (or was first detected)
- **Duration** -- how long the incident has been active
- **Affected percentage** -- what fraction of requests, users, or services are impacted
- **Affected services** -- enumerate each service and its current status (degraded, down, healthy)

Assign severity using these criteria:

| Severity | Criteria                                                                |
| -------- | ----------------------------------------------------------------------- |
| Critical | Revenue-impacting, >50% of requests affected, or data loss risk         |
| High     | User-facing degradation, 10-50% affected, or multiple services impacted |
| Medium   | Partial degradation <10%, single service, no data risk                  |
| Low      | Non-user-facing, minimal impact, single component                       |

### 2. Failure Classification

**Run immediately after framing. This drives the entire investigation.**

Use skill: `ops-failure-classification` to categorize the failure by type, mechanism, and system layer.

Apply domain-specific skills based on classification:

- Concurrency issue: use skill: `architecture-concurrency` for thread safety and lock patterns
- Data consistency error: use skill: `architecture-data-consistency` for scope and propagation issues
- DB performance degradation or N+1: use skill: `backend-db-indexing` for query patterns
- External dependency failure: use skill: `ops-resiliency` for timeout, retry, and circuit breaker gaps
- Resource exhaustion: assess connection pool sizing, thread pool limits, memory bounds, file descriptors; check current utilization vs. configured maximums and identify what is consuming the resource

### 3. Blast Radius Assessment

Use skill: `review-blast-radius` to determine scope across code, data, and user dimensions.

Additionally assess:

- **Shared resources** -- database, cache, queue, connection pool contention
- **API contract impact** -- are consumers receiving errors or degraded responses?
- **Data corruption risk** -- partial writes, inconsistent state, lost events
- **Cross-service propagation** -- which downstream services are affected?

Use skill: `failure-propagation-analysis` to trace the cascading failure path.

Output blast radius explicitly: Narrow | Moderate | Wide | Critical.

### 4. Immediate Containment

**Prioritize fast blast radius reduction.**

Evaluate these containment options in order of speed and safety:

1. **Immediate resource recovery** -- for resource exhaustion (connection pool, thread pool, memory): restart affected instances to reclaim resources, resize pool limits if configurable at runtime, or drain slow consumers holding resources
2. **Rollback** -- if recent deploy correlates, rollback is the fastest containment. Before recommending rollback, use skill: `ops-backward-compatibility` to check for schema or contract breakage that would make rollback unsafe.
3. **Feature flag disable** -- surgical isolation of the failing feature without full rollback; prefer when rollback has compatibility concerns
4. **Circuit breaker** -- stop cascading to downstream services; especially critical when downstream latency is exhausting upstream resources
5. **Traffic isolation** -- route affected traffic to degraded-mode path
6. **Rate limiting** -- reduce load to buy recovery time
7. **Scaling mitigation** -- add capacity if resource exhaustion is the bottleneck and recovery alone is insufficient
8. **Patch and redeploy** -- only if root cause is clearly understood and the fix is small (avoid under pressure)
9. **Data repair** -- if partial writes occurred, assess correction urgency

Use skill: `ops-resiliency` for circuit breaker and retry patterns.
Use skill: `architecture-data-consistency` for data consistency recovery.

### 5. Root Cause Hypothesis

Use skill: `root-cause-hypothesis` to generate ranked hypotheses.

If a recent PR diff is provided as input, use skill: `review-change-risk` to assess the risk level of the triggering change before forming hypotheses.

For each hypothesis, require:

- Primary suspect component and mechanism
- Secondary suspects
- Likely triggering change (recent PR, deploy, config change)
- **Contributing factors** (distinct from root cause): conditions that made the system vulnerable - e.g., no memory limit set, no load test for large payloads, missing circuit breaker
- Failure propagation path (from step 3)
- **Timeline interpretation**: if there is a lag between triggering change and symptom onset (e.g., deploy at T+0, alerts at T+15min), explain why - load-dependent trigger, cache warming, gradual leak vs. startup error
- Confidence level with supporting and contradicting evidence
- One concrete verification step

### 6. Observability Gap Detection

Use skill: `ops-observability` to evaluate signal coverage.

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

### 7. Systemic Prevention

Use skill: `ops-engineering-governance` for structured prevention recommendations.
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
Onset: {timestamp or "unknown"}
Duration: {how long the incident has been active}
Affected Services:

- {service-1}: {status -- degraded/down/healthy}
- {service-2}: {status}

## Immediate Containment

- [ ] Action 1 (priority, expected impact, estimated time)
- [ ] Action 2

## Root Cause Hypothesis

Primary Suspect:
Mechanism:
Triggering Change:
Contributing Factors:
Failure Propagation Path:
Timeline Interpretation: {why symptom onset lagged triggering change, if applicable}
Confidence: X%

Secondary Suspect:
Mechanism:
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
- Each containment action includes estimated time to execute (minutes, not hours)
- Findings ordered by urgency: containment > hypothesis > gaps > prevention
- Omit empty sections
- No low-level debugging walkthroughs
- No code style commentary
- Optimize for token efficiency and on-call readability

## Self-Check

- [ ] Severity assigned with justification based on criteria table
- [ ] Incident onset time and duration stated (or explicitly marked unknown)
- [ ] All affected services enumerated with individual status
- [ ] Blast radius classified (Narrow / Moderate / Wide / Critical) before any hypothesis
- [ ] At least one immediate containment action recommended before diagnosis begins
- [ ] Every hypothesis cites observable evidence; concrete verification step exists per hypothesis
- [ ] Primary hypothesis addresses a failure class, not just the symptom
- [ ] Triggering change identified if evidence exists; propagation path traced from origin to impact
- [ ] Each prevention action has an assigned priority (immediate / next sprint / quarterly)
- [ ] Output can be handed to an on-call engineer and acted on without clarification

## Avoid

- Treating symptoms as root causes
- Generic debugging advice ("check the logs", "restart the service")
- Analysis without blast radius assessment
- Hypotheses without evidence or verification steps
- Prevention that only fixes this specific instance
- Verbose explanations under incident pressure
- Ignoring AI-generated code as a contributing factor to architectural drift
