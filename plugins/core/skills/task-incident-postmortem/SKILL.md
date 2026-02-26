---
name: task-incident-postmortem
description: Staff-level postmortem for systemic learning and prevention
metadata:
  category: ops
  tags: [incident, postmortem, retrospective, prevention, governance, reliability]
  type: workflow
---

# Postmortem -- Staff Edition

## Purpose

Staff-level postmortem that converts incident data into systemic improvements:

- **Systemic thinking** -- identify failure classes, not just local bugs
- **Boundary reinforcement** -- detect erosion, coupling amplification, and blast radius growth
- **Guardrail evolution** -- produce enforceable rules, not wishful suggestions
- **Governance improvement** -- strengthen review, testing, and deployment processes
- **Organizational learning** -- every incident teaches something about the system's structural weaknesses

This skill runs AFTER an incident has been resolved and root cause analysis is complete. It focuses on prevention and structural reinforcement, not debugging.

Use skill: `task-incident-root-cause` for active incident investigation and root cause analysis.

## When to Use

- Post-incident postmortem after resolution
- Converting root cause analysis into long-term improvements
- Identifying patterns across multiple related incidents
- Strengthening engineering guardrails after a failure
- Architecture reinforcement planning after a production event

## Inputs

| Input                   | Required | Description                                               |
| ----------------------- | -------- | --------------------------------------------------------- |
| Incident summary        | Yes      | What happened, severity, duration, user impact            |
| Root cause analysis     | Yes      | Output from root cause investigation or `task-incident-root-cause` |
| Timeline                | No       | Sequence of events from detection to resolution           |
| Logs or metrics summary | No       | Key signals observed during the incident                  |
| Recent PR diff          | No       | Changes deployed before the incident                      |
| Deployment context      | No       | Deploy timestamp, version, environment details            |
| Containment actions     | No       | What was done to stop the bleeding                        |
| Business impact         | No       | Revenue, SLA, customer trust, regulatory implications     |

Handle partial inputs gracefully. When input is missing, state what additional data would strengthen the analysis.

## Rules

- Focus on systemic prevention, not blame or storytelling
- Every recommendation must address a failure class, not just this instance
- Prioritize by blast radius reduction potential
- Produce enforceable guardrails, not vague improvement wishes
- Reuse existing skills for domain-specific analysis
- Omit empty sections in output
- Keep output strategic, concise, and high-signal
- When evidence is insufficient, state what is missing
- Always ask: "Why did our system allow this category of failure?"

## Postmortem Model

### 1. Incident Overview

**Summarize concisely. No narrative.**

Capture:

- Failure type (from root cause analysis or classify using skill: `failure-classification`)
- Severity: Low | Medium | High | Critical
- User impact scope and nature
- Duration from detection to resolution
- Containment actions taken

### 2. Failure Pattern Classification

Use skill: `failure-classification` to categorize by type, mechanism, and system layer.

Identify the primary failure category:

- Concurrency issue
- Transaction boundary failure
- Async/event ordering error
- Data integrity violation
- Resource exhaustion
- External dependency failure
- Configuration drift
- Architecture drift / boundary erosion
- Guardrail failure (review, test, or monitoring gap)
- AI-generated code complexity amplification

Apply domain-specific skills based on classification:

- Concurrency: use skill: `concurrency-model`
- Data consistency: use skill: `data-consistency-modeling`
- External dependency: use skill: `resiliency`
- DB performance: use skill: `db-indexing`

Identify contributing factors that amplified the failure.

### 3. Systemic Weakness Analysis

Go beyond the immediate failure. Identify structural conditions that allowed this category of failure.

Evaluate:

- **Boundary weakness** -- did the failure cross boundaries it should not have?
- **Coupling amplification** -- did tight coupling spread the impact?
- **Shared mutable state risk** -- was shared state a contributing factor?
- **Layer violation trend** -- is there a pattern of bypassing abstractions?
- **Incomplete abstraction** -- did a leaky abstraction expose internals?
- **Hidden assumption** -- was there an undocumented assumption that broke?
- **AI-generated code cognitive risk** -- did code volume or complexity from AI-generated contributions obscure the failure path?
- **Blast radius amplification** -- what structural factors made the impact worse than necessary?

Use skill: `blast-radius-analysis` to assess propagation scope.
Use skill: `architecture-guardrail` to identify boundary violations exposed by the incident.
Use skill: `complexity-review` to assess whether AI-generated complexity contributed.

### 4. Guardrail and Review Gap Analysis

Determine why existing safeguards did not prevent this incident.

Use skill: `review-gap-analysis` to evaluate:

- Why did code review not catch this?
- Was PR risk scoring insufficient for the change scope?
- Was architecture drift undetected during review?
- Were critical test scenarios missing?
- Was monitoring insufficient to detect early?
- Was cognitive load too high for effective review?

Use skill: `engineering-governance` to propose specific guardrail improvements.

### 5. Observability and Detection Improvements

Use skill: `observability` to evaluate signal coverage and recommend additions.

For each gap:

- **What signal was missing** -- specific metric, log, trace span, or alert
- **How it slowed detection or diagnosis** -- what question could not be answered
- **What to add** -- concrete improvement with threshold or trigger

Common improvements to evaluate:

- New RED metrics for affected paths
- Alert threshold adjustments
- Trace span coverage for the failure propagation path
- Correlation ID enforcement across service boundaries
- Structured logging additions for the failure category
- SLO definition or revision if missing or violated

### 6. Architecture Reinforcement

Propose structural changes that prevent the failure class.

Use skill: `resiliency` for fault tolerance patterns.
Use skill: `data-consistency-modeling` for data consistency redesign.
Use skill: `architecture-guardrail` for boundary enforcement.
Use skill: `idempotency` for retry safety.

Evaluate:

- Boundary reinforcement (isolate failure domains)
- Decoupling (reduce propagation paths)
- Idempotency guarantees (make retries safe)
- Retry and timeout policy corrections
- Circuit breaker additions or adjustments
- Data consistency redesign
- Shared state isolation

### 7. Governance and Process Improvements

Use skill: `engineering-governance` to recommend process-level changes.
Use skill: `engineering-governance` for prevention strategies tied to failure classes.

Evaluate:

- Review checklist updates (new items based on this failure class)
- Risk-based review enforcement (mandatory second reviewer for high-risk changes)
- Mandatory design doc triggers (what change scope should require a design doc)
- ADR updates (record the architectural decision or constraint learned)
- Chaos experiment design (fault injection to simulate this failure class)
- Test strategy improvements (integration, contract, or chaos tests to add)
- PR size limit enforcement (if change scope contributed to review miss)
- Deployment safeguards (canary, feature flag, progressive rollout)

### 8. Convert Lessons into Reusable Guardrails

This is the highest-leverage section. Produce concrete, enforceable outputs.

For each guardrail:

- **Rule** -- specific, enforceable constraint
- **Scope** -- where it applies (review, CI, deployment, architecture)
- **Enforcement** -- how it is checked (automated lint, review checklist, CI gate, monitoring alert)
- **Failure class prevented** -- which category of failure this guards against

Categories:

- New code review rules
- Architecture constraints (boundary enforcement, dependency rules)
- Monitoring baseline requirements (mandatory metrics or alerts)
- Deployment safeguards (mandatory canary, rollback criteria)
- Coding standards updates (patterns to require or prohibit)
- AI-generated code constraints (complexity limits, mandatory simplification review)

## Output

```markdown
## Incident Overview

Failure Type:
Severity: Low | Medium | High | Critical
User Impact:
Duration:
Containment Actions:

## Failure Pattern Classification

Primary Category:
System Layer:
Contributing Factors:

## Systemic Weaknesses

- Boundary weakness:
- Coupling risk:
- Shared state risk:
- Observability blind spot:
- AI-related cognitive risk:

## Guardrail and Review Gaps

- Missed during review because:
- Missing checklist item:
- Missing test scenario:
- Missing monitoring:

## Observability Improvements

| Missing Signal | Detection Impact | Recommended Addition |
| -------------- | ---------------- | -------------------- |
| Signal         | Impact           | Addition             |

## Architecture Reinforcement

| Structural Change | Failure Class Prevented | Priority       |
| ----------------- | ----------------------- | -------------- |
| Specific change   | Class it prevents       | immediate/next |

## Governance Improvements

- Review process change:
- Design requirement trigger:
- ADR update:
- Chaos scenario to simulate:
- Deployment safeguard:

## New Guardrails to Adopt

| Rule          | Scope | Enforcement | Failure Class Prevented |
| ------------- | ----- | ----------- | ----------------------- |
| Specific rule | Where | How checked | What it prevents        |

## Staff-Level Takeaways

- 3-5 systemic insights focused on prevention, not this specific incident.
```

### Output Constraints

- No blame or individual attribution
- No narrative storytelling or raw log reproduction
- Findings ordered by leverage: guardrails > architecture > governance > observability
- Omit empty sections
- Every recommendation must be actionable and scoped
- Prioritize high-leverage structural changes over trivial suggestions
- Optimize for token efficiency and long-term organizational value

## Avoid

- Blaming individuals or teams
- Narrative storytelling about the incident timeline
- Repeating raw logs or stack traces
- Generic advice ("improve monitoring", "add more tests")
- Recommendations that only fix this specific instance
- Unbounded improvement wishlists without prioritization
- Proposing architectural rewrites when targeted fixes suffice
- Ignoring AI-generated code as a contributing factor to complexity drift
- Treating the postmortem as a debugging session

## Key Skills Reference

### Existing Skills Reused

**Failure Analysis:**

- Use skill: `failure-classification` for failure type, mechanism, and layer classification
- Use skill: `blast-radius-analysis` for impact scope assessment
- Use skill: `resiliency` for timeout, retry, and circuit breaker patterns
- Use skill: `data-consistency-modeling` for data consistency issues
- Use skill: `db-indexing` for query performance and N+1 detection
- Use skill: `concurrency-model` for concurrency and thread safety issues

**Observability and Architecture:**

- Use skill: `observability` for logging, metrics, and tracing improvements
- Use skill: `architecture-guardrail` for boundary violation and drift detection
- Use skill: `idempotency` for retry safety patterns

**Quality and Governance:**

- Use skill: `complexity-review` for AI-generated complexity assessment
- Use skill: `engineering-governance` for prevention strategies tied to failure classes
- Use skill: `coding-standards` for coding standards updates

**Related Workflow:**

- Use skill: `task-incident-root-cause` for active incident investigation (run before this skill)

### Sub-Skills Defined for This Workflow

| Skill                    | Purpose                                                                          |
| ------------------------ | -------------------------------------------------------------------------------- |
| `review-gap-analysis`    | Analyze why existing review processes did not catch the failure                  |
| `engineering-governance` | Engineering process, governance, guardrail improvements, and incident prevention |

