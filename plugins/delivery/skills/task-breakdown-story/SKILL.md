---
name: task-breakdown-story
description: Break feature or ticket into implementable tasks with dependency order, S/M/L/XL sizing, scope creep flags; surfaces migration/rollback complexity.
metadata:
  category: planning
  tags: [planning, estimation, task-breakdown, scope, complexity]
  type: workflow
user-invocable: true
---

# Scope Breakdown

Decompose a feature or epic into implementable tasks with dependencies, sizes, and scope flags. Audience: tech leads and senior engineers planning the work. Surfaces hidden complexity (migrations, backward compat, rollback, observability) before estimating.

Produces a task plan, not implementation code or design docs. For story-level slicing aimed at PM/QA, use `task-breakdown-epic`.

## When to Use

- Breaking a feature into tasks before development
- Estimating relative effort and surfacing risks before committing a timeline
- Catching scope creep during delivery

## Inputs

Required: feature description.
Optional: acceptance criteria, existing-system notes, constraints, exclusions, owning teams.

When the prompt names a stack ("Node.js/Express", "Rails") and `stack-detect` returns `unknown`, trust the prompt and record the assumption. State assumptions and name what would sharpen the plan when input is thin.

## Workflow

### STEP 1 - Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect`. Stack output is used to pick which deep-dive atomics fire and to name stack-specific tooling in tasks (test frameworks, migration tools). If unknown, proceed stack-agnostic.

### STEP 2 - Hidden Complexity Scan

Walk this checklist and state which signals apply with one-line evidence. Skipping the scan is the most common failure of this workflow.

| Signal | Look for |
| --- | --- |
| Database changes | New table/column/index; zero-downtime required; backfill |
| Data store migration | Moving data between stores (Redis→Postgres, session→token, etc.) |
| API or protocol contract change | New endpoints, field changes, auth-token format, webhook signatures |
| Auth / permissions | New roles, scopes, token formats, key rotation |
| Async / events | New queues, topics, consumers; idempotency requirements |
| State machine | Lifecycle states + transition rules |
| Domain calculations | Billing, tax, shipping, refunds, prorations |
| Backward compatibility | Old and new behavior coexist during rollout |
| Rollback | Can it be reverted? What data would be inconsistent? |
| Feature flag | Risk warrants gradual rollout or kill switch |
| Observability | New flows need logs, metrics, traces |
| Test surface | Contract, integration, load, webhook replay |
| Deploy coordination | Cross-service or cross-team ordering; consumer SDK distribution |
| Third-party integration | External APIs, webhooks, SDKs |

A signal is **material** (load the deep-dive) when it will produce at least one L+ task or a Scope and Risk Flags entry downstream. Otherwise note the signal and move on. Summarize non-applicable signals in one line ("Checked, not applicable: ...").

Deep-dive mapping (load only when material):

- DB schema or data changes (tables, indexes, backfills) → `Use skill: backend-db-migration` (data-store moves without relational schema work do not route here)
- Schema, API, or protocol contract change → `Use skill: ops-backward-compatibility`
- Cross-service / cross-team dependencies → `Use skill: dependency-impact-analysis`
- Flag-gated rollout → `Use skill: ops-feature-flags`
- Any L/XL task touching shared state, auth, money, or cross-service contracts → run `Use skill: review-blast-radius` and `Use skill: review-change-risk` on the single riskiest such task

Deep-dives inform task descriptions, sizes, and flag rationales - cite verdicts inline in the relevant flag (e.g. "blast radius Critical, Wide with flag"); do not paste their output blocks into the artifact.

### STEP 3 - Generate Tasks

Group by phase; include only phases that apply:

- **Foundation** - data model, contracts, infra that other work depends on
- **Build** - primary feature logic
- **Integration** - connecting to consumers, events, external services
- **Validation** - tests, contract checks, load tests, QA
- **Ops Readiness** - observability, runbooks, flag config, rollback drill

Each task:

- **Name** - action-oriented ("Implement dual-mode /auth/validate"). Never "Backend work" or "Testing".
- **Type** - one of: `implementation`, `infrastructure`, `data`, `validation`, `ops`, `analysis` (specs, contracts, audits, decision records)
- **Description** - one or two sentences; what to build, not how
- **Depends on** - task name(s), external (<team/system>), or none
- **Size** - S (<1d) / M (1-2d) / L (3-5d focused engineering days) / XL (>5d - keep in the backlog but add a `split` note naming the cohorts/waves it should break into). Size measures engineering effort; fixed elapsed time (soak windows, parallel runs) goes in the description, not the size.
- **Complexity signals** - required for L or XL; cite which Step 2 signals justify the size
- **Tag** - optional, only `nice-to-have` or `risk-reduction`

When a size hinges on an unmade design choice (e.g., sync vs async), state the assumption in the task description and the alternative under Open Questions, or raise a spike.

### STEP 4 - Dependency Order and Critical Path

Number tasks with blocking relationships:

```
1. Define JWT spec (no deps)
2. JWKS endpoint infra (requires: 1)
3. Dual-mode /auth/validate (requires: 1)
4. Consumer SDK rollout - 30 services (requires: 2, 3)
```

**Critical path** = longest chain by hop count of dependent tasks (do not sum sizes; external dependencies are not hops). If chains tie on hops, pick the one carrying more external coordination or larger sizes. Name the chain in arrow form and add one sentence on *why* it pins delivery (size, externality, cross-team sequencing).

When tasks depend on other teams or external systems, name the owning team in `Depends on` so the critical path surfaces team-coordination risk. Another team's deliverable is an `external (<team>)` dependency, not a task - create tasks only for work your team executes. Spikes are numbered in the Dependency Order when other tasks depend on their outcome, but stay in the Spikes section and do not count toward the task count.

### STEP 5 - Scope and Risk Flags

Surface feature-level flags, each with a verdict: `proceed`, `de-scope`, `add spike`, `split epic`.

- **Scope creep:** items stakeholders may assume are must-have; work discovered during the scan that wasn't in the original ask
- **Hidden risks:** L/XL tasks on the critical path; data tasks with rollback complexity; integration blocked on external teams; tasks with unclear complexity (needs a spike); domain-calculation tasks (billing, tax, shipping)
- **XL tasks** stay in the backlog with `split` notes; promote to `split epic` only when the XL spans cohorts/waves that warrant their own planning

When the verdict is `add spike`, define:
- **Question:** specific unknown
- **Done condition:** what the spike must produce
- **Time-box:** maximum duration before it concludes with a finding

## Output Format

```markdown
# Scope Breakdown: <Feature>

**Stack:** <detected | prompt-stated: <stack> | unknown> | **Tasks:** <count>

## Complexity Signals

- **<signal>:** <one-line evidence>

## Tasks

### Foundation

#### <Task name>
- **Type:** implementation | infrastructure | data | validation | ops | analysis
- **Description:** what to build
- **Depends on:** task(s), external (<team/system>), or none
- **Size:** S / M / L / XL
- **Complexity signals:** <Step-2 signals; required for L/XL>
- **Tag:** nice-to-have | risk-reduction (omit otherwise)

[repeat per task; omit phases with no tasks]

## Dependency Order

[numbered list with `requires:` clauses]

**Critical path:** Task A → Task C → Task E - <why this chain pins delivery>

## Scope and Risk Flags

- **<flag>:** <proceed | de-scope | add spike | split epic> - <one-line rationale>

## Spikes

- **Question:** <unknown>
  **Done:** <output>
  **Time-box:** <duration>

## Assumptions and Open Questions

- <assumption made due to missing input>
- <question that, if answered, would change the breakdown>
```

Omit empty sections (Spikes, Scope and Risk Flags, Assumptions).

## Self-Check

- [ ] **Setup:** behavioral-principles + stack-detect loaded; prompt-stated stack honored when detect is unknown
- [ ] **Scan:** every applicable signal listed with evidence; material deep-dive atomics loaded
- [ ] **Tasks:** each task has Name, Type (from enum), Description, Depends-on, Size; L/XL cite complexity signals; XL has a `split` note; team/system named when external
- [ ] **Dependencies:** critical path named by hop count with a "why" sentence; Ops Readiness includes observability/rollback when relevant
- [ ] **Flags:** each flag carries a verdict; spikes have Question + Done + Time-box
- [ ] **Assumptions and Open Questions** populated when input was thin

## Avoid

- Implementation code or technical design (use a design doc skill)
- Calendar estimates unless asked
- Estimating without the complexity scan
- Generic task names ("Backend", "Testing")
- Treating all tasks as must-have when scope hasn't been agreed
- Tasks without dependency statements
- Summing T-shirt sizes
- Silently dropping XL tasks from the backlog
