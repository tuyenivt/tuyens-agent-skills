---
name: task-incident-postmortem
description: Post-incident postmortem for systemic prevention after an incident is resolved and root cause is known. Use after resolution - not during an active incident (use task-incident-root-cause for that). Produces enforceable guardrails, not just action items. Requires a completed root cause analysis as input.
metadata:
  category: ops
  tags: [incident, postmortem, retrospective, prevention, governance, reliability]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

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

## Depth Levels

| Depth      | When to Use                                                              | What Runs                                               |
| ---------- | ------------------------------------------------------------------------ | ------------------------------------------------------- |
| `quick`    | SEV3 or low-impact incident needing a brief written record               | Timeline + 3 action items only - no systemic analysis   |
| `standard` | Default - SEV1/SEV2 or any incident requiring team learning              | All 8 sections                                          |
| `deep`     | Major incident, recurring failure class, or cross-team systemic analysis | All 8 sections + pattern analysis across past incidents |

**Quick depth produces:**

- Incident summary (what happened, impact, duration)
- Root cause (one paragraph)
- 3 action items with owners and due dates

**Deep depth adds (on top of standard):**

- Pattern analysis: is this failure class recurring? How many times in the last 6 months?
- Cross-system analysis: which other services have the same structural weakness?
- Long-term systemic recommendation: if this class recurs, what architectural change eliminates it?

Default: `standard`. Use `quick` for minor incidents or when stakeholders need a brief written record. Use `deep` for incidents that represent systemic risk or have recurred.

## Inputs

| Input                   | Required | Description                                                        |
| ----------------------- | -------- | ------------------------------------------------------------------ |
| Incident summary        | Yes      | What happened, severity, duration, user impact                     |
| Root cause analysis     | Yes      | Output from root cause investigation or `task-incident-root-cause` |
| Timeline                | No       | Sequence of events from detection to resolution                    |
| Logs or metrics summary | No       | Key signals observed during the incident                           |
| Recent PR diff          | No       | Changes deployed before the incident                               |
| Deployment context      | No       | Deploy timestamp, version, environment details                     |
| Containment actions     | No       | What was done to stop the bleeding                                 |
| Business impact         | No       | Revenue, SLA, customer trust, regulatory implications              |
| Past incident history   | No       | Required for `deep` depth - prior incidents of the same class      |

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

### Step 0 - Timeline Construction (if no timeline provided)

If no structured timeline is provided as input, construct one from available evidence before proceeding:

- Extract timestamps from any log lines, alert notifications, deploy metadata, or notes provided
- Order events chronologically: triggering change (deploy/config) → first symptom → detection → containment → resolution
- Note gaps where timing is unknown
- Format each event as: `{timestamp} - {event} - {source}`
- **Deploy-to-symptom lag**: if a deployment or config change preceded the incident, calculate the delay between deploy and first symptom. Explain the lag mechanism (gradual resource leak, load-dependent trigger, cache expiry, batch schedule alignment, connection pool drain rate)

This constructed timeline becomes the input for Section 1 and Section 3.

### 1. Incident Overview

**Summarize concisely. No narrative.**

Capture:

- Failure type (from root cause analysis or classify using skill: `ops-failure-classification`)
- Severity: Low | Medium | High | Critical
- User impact scope and nature
- Duration from first symptom to resolution
- **Triggering change**: the deploy, config change, batch job, or traffic pattern that initiated the failure - include timestamp and version/commit if available
- **Detection gap**: time between first symptom and first alert/acknowledgment - flag if > 5 minutes as an observability gap
- **Timeline summary**: key milestones from Step 0 (triggering change → first symptom → detection → containment → resolution) with timestamps
- **Immediate actions taken**: what was done to stop the bleeding (rollback, config revert, feature flag disable, etc.) - document separately before systemic analysis

### 2. Failure Pattern Classification

Use skill: `ops-failure-classification` to categorize by type, mechanism, and system layer.

Identify the primary failure category:

- Concurrency issue
- Transaction boundary failure
- Async/event ordering error
- Data integrity violation
- Resource exhaustion
- External dependency failure
- Configuration drift
- Architecture drift / boundary erosion
- Workload contention (batch vs. online, scheduled job vs. user traffic)
- Guardrail failure (review, test, or monitoring gap)

**Compound failures**: most production incidents involve chained categories where one failure triggers another. Identify the full chain. Example: "Transaction boundary failure (long-running transactions) → Resource exhaustion (connection pool drain) → cascading user-facing outage." Classify both the root category and the amplifying category.

Apply domain-specific skills based on classification:

- Concurrency: use skill: `architecture-concurrency`
- Data consistency: use skill: `architecture-data-consistency`
- External dependency: use skill: `ops-resiliency`
- DB performance: use skill: `backend-db-indexing`
- Resource exhaustion: use skill: `ops-resiliency` for pool sizing, timeouts, and bulkhead patterns

Identify contributing factors that amplified the failure.

### 3. Systemic Weakness Analysis

Go beyond the immediate failure. Identify structural conditions that allowed this category of failure.

Evaluate:

- **Boundary weakness** -- did the failure cross boundaries it should not have?
- **Coupling amplification** -- did tight coupling spread the impact?
- **Shared mutable state risk** -- was shared state a contributing factor?
- **Shared resource contention** -- did multiple workloads (batch, online, scheduled) compete for the same resource pool without isolation? (connection pools, thread pools, memory, I/O bandwidth)
- **Layer violation trend** -- is there a pattern of bypassing abstractions?
- **Incomplete abstraction** -- did a leaky abstraction expose internals?
- **Hidden assumption** -- was there an undocumented assumption that broke? (e.g., "transactions complete in < 1s", "batch jobs run during off-peak hours")
- **Blast radius amplification** -- what structural factors made the impact worse than necessary?
- **AI-generated code cognitive risk** (evaluate only when AI-generated code is in the failure path) -- did code volume or complexity from AI-generated contributions obscure the failure path?

Use skill: `review-blast-radius` to assess propagation scope.
Use skill: `architecture-guardrail` to identify boundary violations exposed by the incident.
Use skill: `complexity-review` to assess whether AI-generated complexity contributed (only when relevant).

### 4. Guardrail and Review Gap Analysis

Determine why existing safeguards did not prevent this incident.

Use skill: `review-gap-analysis` to evaluate:

- Why did code review not catch this?
- Was PR risk scoring insufficient for the change scope?
- Was architecture drift undetected during review?
- Were critical test scenarios missing?
- Was monitoring insufficient to detect early?
- Was cognitive load too high for effective review?
- Did the review assess resource impact? (new batch jobs, background tasks, or scheduled jobs that share connection pools, thread pools, or memory with user-facing workloads)
- Were load/stress tests required before deploying resource-consuming changes?

Use skill: `ops-engineering-governance` to propose specific guardrail improvements.

### 5. Observability and Detection Improvements

Use skill: `ops-observability` to evaluate signal coverage and recommend additions.

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

Use skill: `ops-resiliency` for fault tolerance patterns.
Use skill: `architecture-data-consistency` for data consistency redesign.
Use skill: `architecture-guardrail` for boundary enforcement.
Use skill: `backend-idempotency` for retry safety.

Evaluate:

- Boundary reinforcement (isolate failure domains)
- Decoupling (reduce propagation paths)
- **Resource pool isolation** -- separate connection pools, thread pools, or queues for different workload types (batch vs. OLTP, background vs. user-facing). Prevent one workload from starving another.
- **Transaction timeout enforcement** -- set explicit statement and transaction timeouts to prevent long-running transactions from holding resources. Evaluate both application-level and database-level timeout configuration.
- Idempotency guarantees (make retries safe)
- Retry and timeout policy corrections
- Circuit breaker additions or adjustments
- **Bulkhead pattern** -- isolate critical paths so that failures in non-critical paths (batch processing, reports, analytics) cannot degrade user-facing operations
- Data consistency redesign
- Shared state isolation

### 7. Governance and Process Improvements

Use skill: `ops-engineering-governance` to recommend process-level changes.
Use skill: `ops-engineering-governance` for prevention strategies tied to failure classes.

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
Triggering Change: {deploy, config change, batch job, traffic pattern - with timestamp}
Timeline: {triggering change → first symptom → detection → containment → resolution, with timestamps}
Detection Gap: {time between first symptom and first alert}
Containment Actions:

## Failure Pattern Classification

Primary Category:
Chained Categories: {if compound failure, list the chain: root category → amplifying category → user impact}
System Layer:
Contributing Factors:

## Systemic Weaknesses

- Boundary weakness:
- Coupling risk:
- Shared resource contention: {did multiple workloads compete for the same pool?}
- Hidden assumption: {what undocumented assumption broke?}
- Blast radius amplification: {what structural factor made impact worse than necessary?}
- Observability blind spot:

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

- 3-5 systemic insights. Each must name a failure class and state the structural principle that prevents it.
- Format: "{Failure class}: {structural principle or policy change that eliminates the class}"
- Focus on transferable lessons: resource isolation policies, workload governance, deployment safety invariants, or boundary enforcement rules that apply beyond this incident.

## Pattern Analysis (deep only)

### Recurrence Check

- Has this failure class occurred before? {Yes - N times in last 6 months | No | Unknown}
- Previous incidents: {list with dates and severity, or "none on record"}
- Pattern: {Is this random, triggered by deploys, triggered by traffic spikes, or cyclical?}

### Cross-System Weakness

- Which other services or components have the same structural weakness as identified in Section 3?
- Recommended proactive assessment: {where to look for the same failure class before it triggers}

### Long-Term Elimination

If this failure class recurs, what architectural change eliminates it permanently?

- Option A: {architectural change} - Effort: {S/M/L/XL} - Risk: {Low/Medium/High}
- Option B: {alternative} - Effort: - Risk:
- Recommended: {which option and why}
```

### Output Constraints

- No blame or individual attribution
- No narrative storytelling or raw log reproduction
- Findings ordered by leverage: guardrails > architecture > governance > observability
- Omit empty sections
- Every recommendation must be actionable and scoped
- Prioritize high-leverage structural changes over trivial suggestions
- Optimize for token efficiency and long-term organizational value

## Self-Check

- [ ] Failure pattern classified by type and system layer - not just described narratively
- [ ] Compound failure chain identified if multiple categories are involved (root → amplifier → impact)
- [ ] Triggering change identified with timestamp; deploy-to-symptom lag explained if applicable
- [ ] Systemic weaknesses identified beyond the immediate failure (boundary, coupling, shared resources, hidden assumptions)
- [ ] Every observability gap has a concrete recommended addition with threshold or trigger
- [ ] At least one new enforceable guardrail produced (lint rule, checklist item, CI gate) - not a process wish
- [ ] Every recommendation addresses a failure class, not just this specific incident
- [ ] Architecture reinforcement includes resource isolation if shared resources were involved
- [ ] New guardrails table has at least one item implementable in the next sprint
- [ ] No blame or individual attribution in any section

## Avoid

- Blaming individuals or teams
- Narrative storytelling about the incident timeline
- Repeating raw logs or stack traces
- Generic advice ("improve monitoring", "add more tests")
- Recommendations that only fix this specific instance
- Unbounded improvement wishlists without prioritization
- Proposing architectural rewrites when targeted fixes suffice
- Treating the postmortem as a debugging session
- Classifying only the immediate failure without tracing the compound chain
- Omitting the triggering change when deployment or config change evidence exists
- Recommending resource pool changes without specifying concrete sizing or timeout values
