---
name: task-scope-breakdown
description: Break a feature, epic, or ticket into implementable tasks with dependency ordering, relative sizing (S/M/L/XL), and scope creep risk flags. Surfaces hidden complexity - migrations, backward compatibility, observability, rollback - before a sprint starts. Use during sprint planning, before kicking off a large feature, or when a ticket feels bigger than it looks.
metadata:
  category: planning
  tags: [planning, estimation, task-breakdown, scope, complexity]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Scope Breakdown

## Purpose

Structured task decomposition for features and epics, optimized for tech lead and senior engineer planning:

- **Hidden complexity first** -- surface non-obvious work (migrations, backward compat, observability, rollback) before estimating
- **Dependency ordering** -- sequence tasks so no task blocks another unnecessarily
- **Relative sizing** -- T-shirt estimates grounded in complexity signals, not time pressure
- **Scope creep flags** -- distinguish must-have from nice-to-have before work starts

This skill produces a task breakdown plan. It does not generate implementation code.

## When to Use

- Breaking a feature or epic into implementable tasks before development starts
- Identifying hidden dependencies and risks before implementation starts
- Estimating relative effort for a feature before committing to a timeline
- Reviewing scope to avoid creep during delivery

Not for system design (use `task-design-architecture` for complex new systems) or prioritizing which features to build (use `task-debt-prioritize` for debt triage).

## Inputs

| Input                 | Required | Description                                                      |
| --------------------- | -------- | ---------------------------------------------------------------- |
| Feature description   | Yes      | What needs to be built and why                                   |
| Acceptance criteria   | No       | What "done" looks like from the product or business perspective  |
| Existing system notes | No       | Relevant architecture, data models, or services already in place |
| Constraints           | No       | Timeline, tech debt, compliance, legacy coupling                 |
| Exclusions            | No       | What is explicitly out of scope for this feature                 |

Handle partial inputs gracefully. When input is missing, state assumptions explicitly and flag what clarification would sharpen the breakdown.

## Rules

- Identify hidden complexity before sizing tasks - do not estimate on a feature description alone
- Every task must have a stated dependency (or "none") to enable safe sequencing
- Size estimates are relative (S/M/L/XL) - never calendar time unless explicitly requested
- Scope creep risks are flagged at task level, not just feature level
- Distinguish between implementation tasks, infrastructure tasks, and validation tasks
- Do not generate implementation code - describe what to build, not how to build it
- Omit empty sections in output
- When a task is XL, recommend breaking it down further

## Breakdown Model

### Step 1 - Complexity Signal Scan

Before creating any task, scan for hidden complexity that inflates effort or introduces risk:

Use skill: `stack-detect` to identify stack-specific complexity signals.
Use skill: `review-change-risk` to assess risk domains touched by this feature.
Use skill: `ops-backward-compatibility` to identify contract or schema compatibility work.
Use skill: `backend-db-migration` if database changes are present - to surface lock risk, expand-contract phases, and backfill tasks.
Use skill: `ops-feature-flags` if the feature is high-risk or requires gradual rollout - to surface flag design, rollout stages, and cleanup tasks.

Check for these hidden cost areas:

| Signal                   | Questions to Answer                                                                                                                   |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------- |
| Database changes         | New table, column, index, or migration? Zero-downtime required?                                                                       |
| API contract changes     | New endpoints or changed fields? External consumers affected?                                                                         |
| Auth / permissions       | New roles, scopes, or authorization rules?                                                                                            |
| Async / event flows      | New queues, topics, consumers, or producers? Do webhooks require a separate receive-validate-process pipeline task?                   |
| Third-party integrations | New external APIs, webhooks, or SDKs? Are webhook events idempotent (can be delivered 2+ times)?                                      |
| Idempotency              | Do operations need to be idempotent (e.g., Stripe webhooks, payment retries, queue re-delivery)?                                      |
| State machine            | Does the feature require defined lifecycle states and transition rules? Model this as a dedicated task, not inline in business logic. |
| Domain-specific logic    | Does the feature have complex calculations (e.g., billing proration, tax, shipping rates)? Flag as hidden complexity requiring spike. |
| Data backfill            | Existing data needs migration or transformation?                                                                                      |
| Feature flag needed      | Is the risk high enough to warrant a flag, gradual rollout, or kill switch?                                                           |
| Observability gaps       | New flows need logging, metrics, tracing?                                                                                             |
| Backward compatibility   | Old and new behavior must coexist during rollout?                                                                                     |
| Rollback complexity      | Can this be rolled back safely? What data would be in inconsistent state?                                                             |
| Test surface expansion   | Integration tests, contract tests, load tests needed? For third-party integrations: webhook simulation and test mode coverage needed? |
| Deployment coordination  | Deploy ordering required across services or teams?                                                                                    |

State which signals apply before proceeding to task creation.

### Step 2 - Task Generation

Generate the full task list, grouped by phase. For each task:

- **Task name**: Short, action-oriented (Implement X, Add Y, Migrate Z)
- **Type**: `implementation` | `infrastructure` | `data` | `validation` | `ops`
- **Description**: One to two sentences - what to build, not how
- **Complexity signals**: Why this task is the size it is
- **Depends on**: Task names that must complete before this can start (or "none")
- **Size**: S (half day), M (1-2 days), L (3-5 days), XL (>5 days - flag for breakdown)
- **Scope flag**: `must-have` | `nice-to-have` | `risk-reduction`

Common phases (include only what applies):

**Phase 1: Foundation**
Infrastructure, data model changes, and API contracts that other work depends on.

**Phase 2: Core Implementation**
The primary feature logic. This phase can often be parallelized once Phase 1 is done.

**Phase 3: Integration**
Connecting the new implementation to consumers, event flows, and external services.

**Phase 4: Validation**
Tests, load testing, contract validation, and QA.

**Phase 5: Ops Readiness**
Observability, runbooks, feature flags, rollback verification.

Use skill: `dependency-impact-analysis` to validate deployment ordering for infrastructure and data tasks.
Use skill: `review-blast-radius` to assess which tasks carry the highest rollback risk.

### Step 3 - Dependency Order

Sequence tasks into a logical order showing which tasks block others.

Format as a simple numbered list with blocking relationships:

```
1. Task A (no deps)
2. Task B (no deps, parallel with A)
3. Task C (requires: A)
4. Task D (requires: A, B)
5. Task E (requires: C, D)
```

Identify the critical path - the longest chain of dependent tasks that determines minimum delivery time.

### Step 4 - Scope and Risk Flags

Flag scope and risk issues at feature level:

**Scope creep risks:**

- Tasks that are nice-to-have but may be assumed as must-have by stakeholders
- Work discovered during complexity scan that wasn't in the original requirements
- Tasks with XL size that should be a separate epic

**Hidden risks:**

- Any task on the critical path that is L or XL
- Data tasks with rollback complexity (data written cannot be easily undone)
- Integration tasks blocked on external teams or third-party APIs
- Tasks where the complexity signals are unclear (needs spike / discovery task)

For each flag, recommend: proceed as-is / de-scope / add spike / split epic.

When recommending a spike, define it with three things so it is actionable rather than open-ended:

- **Question**: The specific unknown the spike must answer (e.g. "Can we query X without a full table scan at 10M rows?")
- **Done condition**: What the spike must produce (e.g. "A proof-of-concept query with measured latency, or a documented reason it cannot work")
- **Time-box**: Maximum time before the spike must conclude with a finding (e.g. "Half a day - if not resolved, escalate and descope")

## Output

```markdown
# Scope Breakdown: [Feature Name]

## Complexity Signals Detected

[Signals from Step 1 that apply, with brief note on impact]

## Task List

### Phase 1: Foundation

#### [Task Name]

- **Type**: infrastructure/data/implementation/validation/ops
- **Description**: What to build
- **Complexity signals**: Why it is this size
- **Depends on**: task(s) or none
- **Size**: S/M/L/XL
- **Scope**: must-have/nice-to-have/risk-reduction

[repeat per task]

### Phase 2: Core Implementation

[tasks]

### Phase 3: Integration

[tasks]

### Phase 4: Validation

[tasks]

### Phase 5: Ops Readiness

[tasks]

## Dependency Order

[Numbered list with blocking relationships]

**Critical path**: Task A -> Task C -> Task E (estimated: M + L + M)

## Scope and Risk Flags

### Scope Creep Risks

- [Flag]: [Recommendation]

### Hidden Risks

- [Flag]: [Recommendation]

## Assumptions and Open Questions

- [Assumption made due to missing input]
- [Question that, if answered, would change the breakdown]
```

### Output Constraints

- No implementation code
- Every task must have a size, type, and dependency statement
- XL tasks must be flagged with a recommendation to break down further
- Assumptions made due to missing input must be listed
- Omit phases with no tasks

## Self-Check

- [ ] Complexity signal scan completed before any task was created
- [ ] Every hidden cost area (migrations, observability, rollback, compat) checked
- [ ] Every task has a type, size, dependency statement, and scope flag
- [ ] XL tasks flagged for breakdown; size rationale references complexity signals
- [ ] Nice-to-have tasks explicitly separated from must-have; open questions listed
- [ ] Critical path identified; hidden tasks (observability, rollback, data migration) surfaced

## Avoid

- Generating implementation code or detailed technical design
- Estimating in calendar days or hours without being asked
- Accepting a feature description at face value without scanning for hidden complexity
- Treating all tasks as must-have when scope has not been agreed
- Ignoring rollback complexity on data and infrastructure tasks
- Creating tasks without dependency relationships - sequence matters
- Generic task names ("Backend work", "Testing") - every task must be actionable
