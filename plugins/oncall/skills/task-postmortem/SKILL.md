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

| Depth      | When                                                | Sections produced                                                        |
| ---------- | --------------------------------------------------- | ------------------------------------------------------------------------ |
| `quick`    | SEV3 / low-impact - brief written record            | Overview (no MTTR breakdown required), Classification, Guardrails (3 rows max) |
| `standard` | Default - SEV1/SEV2 needing team learning           | All sections                                                             |
| `deep`     | Major or recurring failure class, cross-team impact | All sections + Pattern Analysis (requires prior-incident input)          |

## Inputs

Required: incident summary (what/severity/duration/impact), root cause. Optional: timeline, logs, recent PR diff, deploy metadata, containment actions, business impact. State what is missing if it weakens analysis.

## Rules

- Each recommendation addresses a failure class and names an enforceable mechanism (lint, CI gate, checklist, monitor)
- Resource-budget primitives (pool sizes, timeouts, retry budgets, circuit breaker thresholds, queue depths, concurrency limits) must include concrete numbers, not directional advice
- Omit empty sections; no blame, no narrative, no raw logs

## Workflow

### Step 0 - Construct Timeline (if not provided)

Order events: triggering change → first symptom → detection → containment → resolution. Format: `{timestamp} - {event} - {source}`. If a deploy/config change preceded the incident, calculate deploy-to-symptom lag and explain the mechanism (gradual leak, load-dependent trigger, cache expiry, batch alignment).

### Step 1 - Incident Overview

Capture failure type, severity, user impact, duration, triggering change (with timestamp/commit), and **MTTR breakdown**: detection gap (first symptom → first alert), containment lag (first alert → blast stopped), resolution lag (containment → full recovery). Flag detection gap > 5 min as observability gap. List immediate containment actions taken.

### Step 2 - Failure Classification

If `incident-root-cause` output was provided, ingest its Failure Classification and Blast Radius. Re-run `ops-failure-classification` only if classification was thin or contested.

Most production incidents are compound: identify the chain (root → amplifier → user impact). Example: "Long-running transaction (root) → connection pool drain (amplifier) → cascading 503 (impact)."

Apply the domain skill named by the classification.

### Step 3 - Systemic Weaknesses and Architectural Fix

For each structural condition, name both the weakness and the architectural change that eliminates it (boundary erosion → boundary enforcement; shared mutable state / resource contention → per-workload isolation, bulkheads; hidden assumptions → explicit timeouts, statement budgets; blast radius amplification → circuit breakers, fail-fast paths).

Use skill: `review-blast-radius` for propagation scope.
Use skill: `architecture-guardrail` for boundary violations.
Use skill: `ops-resiliency` for fault tolerance and resource isolation.
Use skill: `backend-idempotency` only if duplicate writes or retry-safety was a contributing factor.

### Step 4 - Review and Process Gaps

Use skill: `review-gap-analysis`.

### Step 5 - Observability Improvements

Use skill: `ops-observability`. For each gap: missing signal → diagnostic question it could not answer → concrete addition (with threshold/trigger). If `incident-root-cause` already produced Observability Gaps, list only additions; do not restate.

### Step 6 - Governance and Process

Use skill: `ops-engineering-governance`.

Recommend only the governance changes that close a gap surfaced in Steps 3-5. Candidates: review checklist updates, risk-based reviewer requirements, design-doc triggers, ADR updates, chaos experiments, test strategy, PR-size limits, deployment safeguards (canary, flags, progressive rollout). Omit categories with no specific change.

### Step 7 - Guardrails and Persistence (highest leverage)

For each new guardrail, name a concrete persistence target so the lesson outlives this document:

| Target                                                                 | Use when                                              | Patch shape                                                          |
| ---------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------- |
| Stack-specific skill (`<stack>-<concern>`)                             | Rule encodes a framework pattern                      | New bullet under `## Rules` or `## Patterns` with bad/good pair      |
| Stack-agnostic core skill (`ops-resiliency`, `architecture-guardrail`) | Rule applies across stacks                            | New bullet in the relevant core skill                                |
| Project `CLAUDE.md`                                                    | Project-specific policy that does not generalize      | Entry under `## Lessons from Incidents` (create if absent)           |
| Review checklist / CI gate                                             | Mechanically enforceable                              | Concrete file + check name + failure message                         |
| Alerting rule / monitoring-as-code                                     | Mechanically enforceable detection signal             | New alert definition with threshold + window                         |

For each guardrail produce: target file + insertion point + exact text. State which MTTR number it would have reduced and roughly by how much.

Bad: "Add monitoring for pool exhaustion; improve review process for risky changes."
Good: "Emit `db.pool.acquire.wait` histogram; alert p99 > 200ms for 1 min. Patch: `plugins/core/skills/ops-observability/SKILL.md` Patterns. CODEOWNERS: `**/*retry* @sre`."

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
Detection Gap Flag: {yes if > 5 min, else no}
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
- [ ] MTTR broken into detection / containment / resolution; detection-gap flag set
- [ ] Each systemic weakness paired with a concrete structural change (resource-budget primitives carry numbers)
- [ ] Top 1-3 review/process gaps named with structural fix
- [ ] Each observability gap names missing signal → diagnostic question → concrete threshold/trigger
- [ ] Governance items only included when closing a gap from Steps 3-5; empty categories omitted
- [ ] At least one enforceable guardrail produced; every guardrail names a persistence target, exact patch, and which MTTR number it reduces

## Avoid

- Generic advice ("improve monitoring", "add more tests") that does not name a failure class
- Reporting a single "duration" instead of detection/containment/resolution split
- Ignoring the compound chain: classifying only the immediate failure, not the amplifier
- Blame, narrative, raw log reproduction, or architectural rewrites when targeted fixes suffice
