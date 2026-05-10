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

Decompose a feature or epic into implementable tasks with dependencies, sizes, and scope flags. Audience: tech leads and senior engineers planning the work. Surface hidden complexity (migrations, backward compat, rollback, observability) before estimating - this is the value of the workflow.

Produces a task plan, not implementation code. For story-level slicing aimed at PM/QA, use `task-breakdown-epic`.

## When to Use

- Breaking a feature or epic into tasks before development
- Estimating relative effort and surfacing risks before committing a timeline
- Reviewing scope to catch creep during delivery

## Inputs

Required: feature description.
Optional: acceptance criteria, existing-system notes, constraints, exclusions.
Handle thin input by stating assumptions and naming what would sharpen the plan.

## Workflow

### STEP 1 - Setup

Use skill: `behavioral-principles`.
Use skill: `stack-detect`.

### STEP 2 - Hidden Complexity Scan

Walk this checklist and state which signals apply. Estimating without this scan is the most common failure of the workflow.

| Signal | Look for |
| --- | --- |
| Database changes | New table/column/index; zero-downtime required; backfill |
| API contract changes | New endpoints or field changes; external consumers affected |
| Auth / permissions | New roles, scopes, or rules |
| Async / events | New queues, topics, or consumers |
| Third-party integrations | External APIs, webhooks, SDKs |
| Idempotency | Operations must tolerate retries (webhooks, payments, queues) |
| State machine | Lifecycle states + transition rules |
| Domain calculations | Billing proration, tax, shipping - likely needs a spike |
| Backward compatibility | Old and new behavior coexist during rollout |
| Rollback | Can it be reverted? What data would be inconsistent? |
| Feature flag | Risk warrants gradual rollout or kill switch |
| Observability | New flows need logs, metrics, traces |
| Test surface | Integration, contract, load, webhook simulation |
| Deploy coordination | Cross-service or cross-team ordering |

For signals that apply, load the relevant deep-dive only when material:
- DB changes → `Use skill: backend-db-migration`
- Schema or API contract changes → `Use skill: ops-backward-compatibility`
- Cross-service contracts → `Use skill: dependency-impact-analysis`
- Flag-gated rollout → `Use skill: ops-feature-flags`
- Use `Use skill: review-change-risk` and `review-blast-radius` to size the riskiest tasks

### STEP 3 - Generate Tasks

Group by phase; include only the phases that apply:

- **Foundation** - data model, contracts, infra that other work depends on
- **Build** - primary feature logic; usually parallelizable once Foundation lands
- **Integration** - connecting to consumers, events, external services
- **Validation** - tests, contract checks, load tests, QA
- **Ops Readiness** - observability, runbooks, flag config, rollback verification

Each task:

- **Name** - action-oriented ("Implement X", "Add Y", "Migrate Z"); never "Backend work" or "Testing"
- **Type** - implementation | infrastructure | data | validation | ops
- **Description** - one or two sentences; what to build, not how
- **Depends on** - task name(s) or none
- **Size** - S (½d) / M (1-2d) / L (3-5d) / XL (>5d, recommend breaking down)
- **Complexity signals** - only when size is non-obvious or L/XL (justify the size)
- **Scope** - only flag `nice-to-have` or `risk-reduction`; default is must-have, no need to repeat

### STEP 4 - Dependency Order and Critical Path

Numbered sequence with blocking relationships:

```
1. Task A (no deps)
2. Task B (no deps, parallel with A)
3. Task C (requires: A)
4. Task D (requires: A, B)
```

Critical path = longest chain of dependent tasks. Name the chain; do not sum T-shirt sizes (that's meaningless math).

### STEP 5 - Scope and Risk Flags

Surface flags at feature level, with one of: **proceed** / **de-scope** / **add spike** / **split epic**.

- **Scope creep:** nice-to-have items stakeholders may assume are must-have; work discovered during the scan that wasn't in the original ask; XL tasks that should be a separate epic
- **Hidden risks:** L/XL tasks on the critical path; data tasks with rollback complexity; integration blocked on external teams; tasks with unclear complexity (needs a spike)

When recommending a spike, define it with three things so it is actionable:
- **Question:** the specific unknown ("Can we query X without a full table scan at 10M rows?")
- **Done condition:** what the spike must produce ("Working POC with measured latency, or documented reason it cannot work")
- **Time-box:** maximum time before it concludes with a finding ("½ day; if not resolved, escalate and de-scope")

## Output Format

```markdown
# Scope Breakdown: <Feature>

## Complexity Signals

- **<signal>:** <one-sentence impact>
- [only signals that apply]

## Tasks

### Foundation

#### <Task>
- **Type:** infrastructure / data / implementation / validation / ops
- **Description:** what to build
- **Depends on:** task(s) or none
- **Size:** S / M / L / XL
- **Complexity signals:** only when size is L/XL or non-obvious
- **Scope:** only when nice-to-have or risk-reduction (omit for must-have)

[repeat per task; omit phases with no tasks]

## Dependency Order

[numbered list with blocking relationships]

**Critical path:** Task A → Task C → Task E - <one line on why this chain pins delivery time>

## Scope and Risk Flags

- **<flag>:** <recommendation>

## Spikes

- **Question:** <unknown>
  **Done:** <output>
  **Time-box:** <duration>

## Assumptions and Open Questions

- {Assumption made due to missing input}
- {Question that, if answered, would change the breakdown}
```

## Self-Check

- [ ] Complexity scan completed before any task was sized
- [ ] Every task has type, size, dependency
- [ ] XL tasks recommended for breakdown; sizes ≥L cite complexity signals
- [ ] Nice-to-have / risk-reduction flagged; everything else implicit must-have
- [ ] Critical path named; hidden ops/observability/rollback tasks present
- [ ] Spikes defined with Question + Done + Time-box (or none)

## Avoid

- Generating implementation code or technical design
- Calendar estimates unless asked
- Estimating without the complexity scan
- Generic task names ("Backend", "Testing")
- Treating all tasks as must-have when scope hasn't been agreed
- Tasks without dependency statements - sequence matters
- Summing T-shirt sizes
