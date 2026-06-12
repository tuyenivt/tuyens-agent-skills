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

| Depth      | When                                                | Steps run                  | Sections produced                                                        |
| ---------- | --------------------------------------------------- | -------------------------- | ------------------------------------------------------------------------ |
| `quick`    | SEV3 / low-impact - brief written record            | 0, 1 (single duration OK, no MTTR breakdown), 2, 7 | Overview, Classification, Guardrails (3 rows max; omit the MTTR Reduced column) |
| `standard` | Default - SEV1/SEV2 needing team learning           | All                        | All sections except Pattern Analysis                                     |
| `deep`     | Major or recurring failure class, cross-team impact | All                        | All sections + Pattern Analysis (requires prior-incident input)          |

At `quick` depth, detection-gap fixes appear as monitoring guardrail rows (signal + threshold in Exact Patch) since the Observability section is not produced; structural fixes likewise fold into guardrail rows since Systemic Weaknesses is skipped. Both count toward the 3-row cap.

## Inputs

Required: incident summary (what/severity/duration/impact), root cause. Optional: timeline, logs, recent PR diff, deploy metadata, containment actions, business impact. State what is missing if it weakens analysis. The triggering change may be a non-code event (data/traffic growth, onboarding, config drift) - `review-gap-analysis` handles the no-PR path.

## Rules

- Run every `Use skill:` delegation in the steps your depth includes; synthesize sub-skill outputs into the template sections - never paste their raw output blocks
- Each recommendation addresses a failure class and names an enforceable mechanism (lint, CI gate, checklist, monitor)
- Resource-budget primitives (pool sizes, timeouts, retry budgets, circuit breaker thresholds, queue depths, concurrency limits) must include concrete numbers, not directional advice
- Omit empty sections; no blame, no narrative, no raw logs

## Workflow

### Step 0 - Construct Timeline (skip if provided)

Order events: triggering change → first symptom → detection → containment → resolution. Format: `{timestamp} - {event} - {source}`. If a deploy/config/data change preceded the incident, calculate trigger-to-symptom lag and explain the mechanism (gradual leak, load-dependent trigger, cache expiry, batch alignment).

### Step 1 - Incident Overview

Capture failure type, severity, user impact, duration (first symptom → full recovery; for silently-failing jobs this includes the undetected period), triggering change (with timestamp/commit or event), and - at standard/deep - the **MTTR breakdown**: detection gap (first symptom → first alert or human detection), containment lag (first alert → blast stopped), resolution lag (containment → full recovery). Flag detection gap > 5 min as observability gap. List immediate containment actions taken.

### Step 2 - Failure Classification

If `incident-root-cause` output was provided, ingest its Failure Classification and Blast Radius. Otherwise (or if thin/contested) use skill: `ops-failure-classification`, mapping its output: `Failure Type` (root first) → Primary Category; `Scope` + propagation → Chain; `Layer` → System Layer.

Most production incidents are compound: identify the chain (root → amplifier → user impact). Example: "Long-running transaction (root) → connection pool drain (amplifier) → cascading 503 (impact)."

Then load the domain skill matching the root failure type:

| Root failure type                                                          | Domain skill                    |
| -------------------------------------------------------------------------- | ------------------------------- |
| Concurrency issue (genuine race/lock/deadlock)                             | `architecture-concurrency`      |
| Transaction boundary error / partial writes                                | `architecture-data-consistency` |
| DB performance degradation, N+1                                            | `backend-db-indexing`           |
| Resource exhaustion, resource contention, external dependency, cascading   | `ops-resiliency`                |
| Architectural boundary violation                                           | `architecture-guardrail`        |
| Other types (logic bug, misconfiguration, deploy drift)                    | none - proceed                  |

For compound failures, map the root type; load a second domain skill only when the amplifier names a different row. At `quick` depth the domain skill informs guardrail rows only.

### Step 3 - Systemic Weaknesses and Architectural Fix (standard/deep)

For each structural condition, name both the weakness and the architectural change that eliminates it (boundary erosion → boundary enforcement; shared mutable state / resource contention → per-workload isolation, bulkheads; hidden assumptions → explicit timeouts, statement budgets; blast radius amplification → circuit breakers, fail-fast paths).

Use skill: `review-blast-radius` for propagation scope (its scope feeds the Priority column).
Use skill: `architecture-guardrail` for boundary violations.
Use skill: `ops-resiliency` for fault tolerance and resource isolation (skip if already loaded as the Step 2 domain skill).
Use skill: `backend-idempotency` only if duplicate writes or retry-safety was a contributing factor.

### Step 4 - Review and Process Gaps (standard/deep)

Use skill: `review-gap-analysis`. Surface its Highest-Leverage Fix plus top 1-2 P0/P1 rows, including `Non-Reviewable` rows.

### Step 5 - Observability Improvements (standard/deep)

Use skill: `ops-observability`. For each gap: missing signal → diagnostic question it could not answer → concrete addition (with threshold/trigger). If `incident-root-cause` already produced Observability Gaps (its `Diagnosis Impact` column maps to `Detection Impact` here), list only additions; do not restate.

### Step 6 - Governance and Process (standard/deep)

Use skill: `ops-engineering-governance`.

Recommend only the governance changes that close a gap surfaced in Steps 3-5. Candidates: review checklist updates, risk-based reviewer requirements, design-doc triggers, ADR updates, chaos experiments, test strategy, PR-size limits, deployment safeguards (canary, flags, progressive rollout).

Boundary with Step 7: any mechanically enforceable item becomes a row in the Step 7 guardrail table only - do not duplicate it here. The Governance Improvements section lists only non-mechanical process changes. Omit categories with no specific change.

### Step 7 - Guardrails and Persistence (highest leverage)

Produce one row per distinct failure-class/enforcement pair surfaced by the steps run; merge overlaps; cap 7 (3 at `quick`). For each guardrail, name a concrete persistence target so the lesson outlives this document:

| Target                                                                 | Use when                                              | Patch shape                                                          |
| ---------------------------------------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------- |
| Stack-specific skill (`<stack>-<concern>`)                             | Rule encodes a framework pattern                      | New bullet under `## Rules` or `## Patterns` with bad/good pair      |
| Stack-agnostic core skill (`ops-resiliency`, `architecture-guardrail`) | Rule applies across stacks                            | New bullet in the relevant core skill                                |
| Project `CLAUDE.md`                                                    | Project-specific policy that does not generalize      | Entry under `## Lessons from Incidents` (create if absent)           |
| Review checklist / CI gate                                             | Mechanically enforceable                              | Concrete file + check name + failure message                         |
| Alerting rule / monitoring-as-code                                     | Mechanically enforceable detection signal             | New alert definition with threshold + window                         |

For each guardrail produce: target file + insertion point + exact text, and the MTTR impact in the format `{detection | containment | resolution} ~-{N min or N%}`, or `prevents entirely` for guardrails that stop the failure from occurring (omit the column at `quick`).

Bad: "Add monitoring for pool exhaustion; improve review process for risky changes."
Good: "Emit `db.pool.acquire.wait` histogram; alert p99 > 200ms for 1 min. Patch: `plugins/core/skills/ops-observability/SKILL.md` Patterns. CODEOWNERS: `**/*retry* @sre`. MTTR: detection ~-10 min."

## Output

Produce only the sections your depth includes (see Depth table); omit the rest entirely.

```markdown
## Incident Overview

Failure Type:
Severity: Low | Medium | High | Critical
User Impact:
Duration:
Triggering Change: {deploy/config/batch/traffic/data event - with timestamp}
Timeline: {triggering → first symptom → detection → containment → resolution}
MTTR (standard/deep): detection gap {X}, containment lag {Y}, resolution lag {Z}
Detection Gap Flag (standard/deep): {yes if > 5 min, else no}
Containment Actions:

## Failure Classification

Primary Category:
Chain (if compound): {root → amplifier → impact}
System Layer:
Contributing Factors:

## Systemic Weaknesses and Architectural Fix (standard/deep)

| Weakness | Structural Change | Failure Class Prevented | Priority |
| -------- | ----------------- | ----------------------- | -------- |

## Review and Process Gaps (standard/deep)

{From review-gap-analysis: Highest-Leverage Fix + top 1-2 P0/P1 rows}

## Observability Improvements (standard/deep)

| Missing Signal | Detection Impact | Recommended Addition |
| -------------- | ---------------- | -------------------- |

## Governance Improvements (standard/deep)

- {non-mechanical process changes closing a gap from Steps 3-5; enforceable items live in Guardrails only}

## Guardrails and Persistence

3-7 rows (max 3 at quick). Every row names a real file or check.

| Rule | Scope | Enforcement | Failure Class | Persistence Target | Exact Patch | MTTR Reduced |
| ---- | ----- | ----------- | ------------- | ------------------ | ----------- | ------------ |
| {specific enforceable rule} | review/CI/arch/monitoring | {how checked} | {class prevented} | {file path} | {bullet/code} | {detection/containment/resolution ~-N min, or "prevents entirely"; omit column at quick} |

## Staff-Level Takeaways (standard/deep)

3-5 lines: "{Failure class}: {structural principle that eliminates it}". Transferable beyond this incident.

## Pattern Analysis (deep only - omit at quick/standard)

- Recurrence: prior incidents of this class (count + dates) | "none on record"
- Cross-system weakness: which other services share this structural weakness
- Long-term elimination: Option A {change, effort, risk} / Option B / Recommended
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Steps and sections match the requested depth; omitted sections are absent, not empty
- [ ] Failure classified by type and layer; compound chain identified if applicable; domain skill from the mapping table applied
- [ ] Triggering change identified with timestamp (code or non-code event); trigger-to-symptom lag explained if relevant
- [ ] Standard/deep: MTTR broken into detection / containment / resolution; detection-gap flag set
- [ ] Standard/deep: each systemic weakness paired with a concrete structural change (resource-budget primitives carry numbers)
- [ ] Standard/deep: top 1-3 review/process gaps named with structural fix; each observability gap names signal → question → threshold
- [ ] Governance items only non-mechanical; enforceable items appear once, in Guardrails
- [ ] At least one enforceable guardrail; every row names persistence target, exact patch, and (standard/deep) which MTTR number it reduces

## Avoid

- Generic advice ("improve monitoring", "add more tests") that does not name a failure class
- Reporting a single "duration" instead of the MTTR split at standard/deep depth
- Ignoring the compound chain: classifying only the immediate failure, not the amplifier
- Blame, narrative, raw log reproduction, or architectural rewrites when targeted fixes suffice
- Duplicating the same guardrail in both Governance and Guardrails sections
