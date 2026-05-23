---
name: task-postmortem
description: Post-incident postmortem producing enforceable guardrails (with persistence targets) plus MTTR-anchored systemic fixes from confirmed root cause.
metadata:
  category: ops
  tags: [incident, postmortem, retrospective, prevention, governance, reliability]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Postmortem

Convert a resolved incident into systemic prevention. Run AFTER root cause is known (typically downstream of `incident-root-cause`); this skill is not for debugging.

## When to Use

- Post-incident retrospective after resolution
- Converting RCA into long-term guardrails
- Identifying recurring failure classes across incidents

## Depth

| Depth      | When                                                | Sections produced                                              |
| ---------- | --------------------------------------------------- | -------------------------------------------------------------- |
| `quick`    | SEV3 / low-impact - brief written record            | Overview, Classification, Guardrails (3 rows max)              |
| `standard` | Default - SEV1/SEV2 needing team learning           | All sections                                                   |
| `deep`     | Major or recurring failure class, cross-team impact | All sections + Pattern Analysis                                |

## Inputs

Required: incident summary (what/severity/duration/impact), root cause analysis. Optional: timeline, logs, recent PR diff, deploy metadata, containment actions, business impact, prior incidents (required for `deep`). State what is missing if it weakens analysis.

## Rules

- Every recommendation addresses a failure class, not just this instance
- Output enforceable guardrails (lint, CI gate, checklist, monitor), not wishes
- Order findings by leverage: guardrails > architecture > governance > observability
- Omit empty sections; no blame, no narrative, no raw logs

## Workflow

### Step 0 - Construct Timeline (if not provided)

Order events: triggering change → first symptom → detection → containment → resolution. Format: `{timestamp} - {event} - {source}`. If a deploy/config change preceded the incident, calculate deploy-to-symptom lag and explain the mechanism (gradual leak, load-dependent trigger, cache expiry, batch alignment).

### Step 1 - Incident Overview

Capture failure type, severity, user impact, duration, triggering change (with timestamp/commit), and **MTTR breakdown**: detection gap (first symptom → first alert), containment lag (first alert → blast stopped), resolution lag (containment → full recovery). Flag detection gap > 5 min as observability gap. List immediate containment actions taken.

### Step 2 - Failure Classification

Use skill: `ops-failure-classification`.

Most production incidents are compound: identify the chain (root → amplifier → user impact). Example: "Long-running transaction (root) → connection pool drain (amplifier) → cascading 503 (impact)."

Apply domain skills based on classification:

- Concurrency: `architecture-concurrency`
- Data consistency: `architecture-data-consistency`
- External dependency, connection pool, or other resource exhaustion: `ops-resiliency`
- Slow query, missing index, N+1: `backend-db-indexing`

### Step 3 - Systemic Weaknesses and Architectural Fix

For each structural condition, name both the weakness and the architectural change that eliminates it:

- Boundary erosion / coupling amplification → boundary enforcement
- Shared mutable state, shared resource contention (pools, threads, memory shared across batch and online workloads) → per-workload isolation, bulkheads
- Hidden assumptions ("transactions complete in <1s", "batch runs off-peak") → explicit timeouts, statement budgets
- Blast radius amplification - what made impact worse than necessary? → circuit breakers, fail-fast paths

Use skill: `review-blast-radius` for propagation scope.
Use skill: `architecture-guardrail` for boundary violations.
Use skill: `ops-resiliency` for fault tolerance and resource isolation.
Use skill: `backend-idempotency` only if duplicate writes or retry-safety was a contributing factor.

Pool/timeout sizing must include concrete numbers (size N, timeout Xs), not directional advice.

### Step 4 - Review and Process Gaps

Use skill: `review-gap-analysis`.

### Step 5 - Observability Improvements

Use skill: `ops-observability`. For each gap: missing signal → diagnostic question it could not answer → concrete addition (with threshold/trigger).

### Step 6 - Governance and Process

Use skill: `ops-engineering-governance`.

Recommend only the governance changes that close a gap surfaced in Steps 3-5. Candidates: review checklist updates, risk-based reviewer requirements, design-doc triggers, ADR updates, chaos experiments, test strategy, PR-size limits, deployment safeguards (canary, flags, progressive rollout). Omit categories with no specific change.

### Step 7 - Guardrails and Persistence (highest leverage)

For each new guardrail, name a concrete persistence target so the lesson outlives this document:

| Target                                                       | Use when                                              | Patch shape                                                          |
| ------------------------------------------------------------ | ----------------------------------------------------- | -------------------------------------------------------------------- |
| Stack-specific skill (`rails-*`, `node-*`, ...)              | Rule encodes a framework pattern                      | New bullet under `## Rules` or `## Patterns` with bad/good pair      |
| Stack-agnostic core skill (`ops-resiliency`, `architecture-guardrail`) | Rule applies across stacks                  | New bullet in the relevant core skill                                |
| Project `CLAUDE.md`                                          | Project-specific policy that does not generalize      | Entry under `## Lessons from Incidents` (create if absent)           |
| Review checklist / CI gate                                   | Mechanically enforceable                              | Concrete file + check name + failure message                         |
| Runbook                                                      | Recovery procedure, not prevention                    | New runbook entry                                                    |

For each guardrail produce: target file + insertion point + exact text. State which MTTR number it would have reduced and roughly by how much. If a guardrail does not fit any target, the rule is too vague - tighten or drop.

## Output

```markdown
## Incident Overview

Failure Type:
Severity: Low | Medium | High | Critical
User Impact:
Duration:
Triggering Change: {deploy/config/batch/traffic - with timestamp}
Timeline: {triggering → first symptom → detection → containment → resolution}
MTTR: detection gap {X}, containment lag {Y}, resolution lag {Z}
Containment Actions:

## Failure Classification

Primary Category:
Chain (if compound): {root → amplifier → impact}
System Layer:
Contributing Factors:

## Systemic Weaknesses and Architectural Fix

| Weakness | Structural Change | Failure Class Prevented | Priority |
| -------- | ----------------- | ----------------------- | -------- |

## Review and Process Gaps

{From review-gap-analysis: top 1-3 gaps with priority and structural fix}

## Observability Improvements

| Missing Signal | Detection Impact | Recommended Addition |
| -------------- | ---------------- | -------------------- |

## Governance Improvements

- {only the governance changes that close a gap from Steps 3-5; omit empty categories}

## Guardrails and Persistence

3-7 rows for `standard` depth. Every row names a real file or check.

| Rule | Scope | Enforcement | Failure Class | Persistence Target | Exact Patch | MTTR Reduced |
| ---- | ----- | ----------- | ------------- | ------------------ | ----------- | ------------ |
| {specific enforceable rule} | review/CI/arch/monitoring | {how checked} | {class prevented} | {file path} | {bullet/code} | {detection / containment / resolution, ~delta} |

## Staff-Level Takeaways

3-5 lines: "{Failure class}: {structural principle that eliminates it}". Transferable beyond this incident.

## Pattern Analysis (deep only)

- Recurrence: prior incidents of this class (count + dates) | "none on record"
- Cross-system weakness: which other services share this structural weakness
- Long-term elimination: Option A {change, effort, risk} / Option B / Recommended
```

## Self-Check

- [ ] Failure classified by type and layer; compound chain identified if applicable
- [ ] Triggering change identified with timestamp; deploy-to-symptom lag explained if relevant
- [ ] MTTR broken into detection / containment / resolution
- [ ] Each systemic weakness paired with a concrete structural change (with sizing values when pools/timeouts apply)
- [ ] At least one enforceable guardrail produced; every guardrail names a persistence target, exact patch, and which MTTR number it reduces

## Avoid

- Generic advice ("improve monitoring", "add more tests") that does not name a failure class
- Guardrails confined to this document - if no skill, `CLAUDE.md`, or CI gate is patched, the lesson dies
- Reporting a single "duration" instead of detection/containment/resolution split
- Ignoring the compound chain: classifying only the immediate failure, not the amplifier
- Blame, narrative, raw log reproduction, or architectural rewrites when targeted fixes suffice
