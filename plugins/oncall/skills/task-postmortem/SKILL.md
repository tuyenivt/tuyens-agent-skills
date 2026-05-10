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

| Depth      | When                                                | Sections produced                            |
| ---------- | --------------------------------------------------- | -------------------------------------------- |
| `quick`    | SEV3 / low-impact - brief written record            | Overview + 3 action items                    |
| `standard` | Default - SEV1/SEV2 needing team learning           | All 8 sections                               |
| `deep`     | Major or recurring failure class, cross-team impact | All 8 sections + Pattern Analysis            |

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
- External dependency / resource exhaustion: `ops-resiliency`
- DB performance: `backend-db-indexing`

### Step 3 - Systemic Weaknesses

Identify structural conditions that allowed this failure class. Evaluate:

- Boundary erosion / coupling amplification
- Shared mutable state, shared resource contention (pools, threads, memory shared across batch and online workloads)
- Hidden assumptions (e.g., "transactions complete in <1s", "batch runs off-peak")
- Blast radius amplification - what made impact worse than necessary?

Use skill: `review-blast-radius` for propagation scope.
Use skill: `architecture-guardrail` for boundary violations.

### Step 4 - Review and Process Gaps

Use skill: `review-gap-analysis`.

### Step 5 - Observability Improvements

Use skill: `ops-observability`. For each gap: missing signal → diagnostic question it could not answer → concrete addition (with threshold/trigger).

### Step 6 - Architecture Reinforcement

Use skill: `ops-resiliency` for fault tolerance, `architecture-guardrail` for boundaries, `backend-idempotency` for retry safety.

Evaluate: pool/queue isolation (per workload), explicit statement and transaction timeouts, bulkheads, circuit breakers, idempotent retries, decoupling, shared-state isolation.

### Step 7 - Governance and Process

Use skill: `ops-engineering-governance`.

Cover: review checklist updates, risk-based reviewer requirements, design-doc triggers, ADR updates, chaos experiments, test strategy, PR-size limits, deployment safeguards (canary, flags, progressive rollout).

### Step 8 - Guardrails and Persistence (highest leverage)

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

## Systemic Weaknesses

- {Boundary/coupling/shared-resource/hidden-assumption finding} (one bullet each that applies; omit those that do not)

## Review and Process Gaps

{From review-gap-analysis: top 1-3 gaps with priority and structural fix}

## Observability Improvements

| Missing Signal | Detection Impact | Recommended Addition |
| -------------- | ---------------- | -------------------- |

## Architecture Reinforcement

| Structural Change | Failure Class Prevented | Priority |
| ----------------- | ----------------------- | -------- |

## Governance Improvements

- Review process change:
- Design-doc trigger:
- ADR update:
- Chaos scenario:
- Deployment safeguard:

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
- [ ] At least one enforceable guardrail produced (lint, checklist, CI gate, monitor)
- [ ] Every guardrail row names a concrete persistence target and an exact patch
- [ ] Each guardrail names which MTTR number it reduces and roughly by how much
- [ ] Architecture reinforcement includes resource isolation when shared resources were involved
- [ ] No blame, no narrative, no raw log reproduction

## Avoid

- Generic advice ("improve monitoring", "add more tests") - every recommendation must address a failure class
- Guardrails that live only inside this document - if no skill, `CLAUDE.md`, or CI gate is patched, the lesson dies
- Reporting a single "duration" instead of detection/containment/resolution split
- Recommending pool/timeout changes without concrete sizing values
- Ignoring the compound chain: classifying only the immediate failure, not the amplifier
- Architectural rewrites when targeted fixes suffice
