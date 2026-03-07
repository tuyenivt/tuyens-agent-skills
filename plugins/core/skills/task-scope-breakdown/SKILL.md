---
name: task-scope-breakdown
description: Task planning and effort sizing for an epic or feature - implementable tasks, dependency ordering, T-shirt sizing, and scope creep risk flags. Supports sprint-fitting mode to allocate tasks to sprints with team capacity constraints. Not a substitute for system design (use task-design-architecture for that).
metadata:
  category: planning
  tags: [planning, estimation, task-breakdown, scope, complexity, sprint-planning]
  type: workflow
user-invocable: true
---

# Scope Breakdown

## Purpose

Structured task decomposition for epics and features, optimized for tech lead and senior engineer planning:

- **Hidden complexity first** -- surface non-obvious work (migrations, backward compat, observability, rollback) before estimating
- **Dependency ordering** -- sequence tasks so no task blocks another unnecessarily
- **Relative sizing** -- T-shirt or story point estimates grounded in complexity signals, not time pressure
- **Scope creep flags** -- distinguish must-have from nice-to-have before work starts
- **Ticket-ready output** -- produce a breakdown that can be copied directly into a tracker

This skill produces a task breakdown plan. It does not generate implementation code.

## When to Use

- Breaking an epic or feature into sprint-ready tasks before a planning session
- Estimating relative effort for a feature before committing to a timeline
- Identifying hidden dependencies and risks before implementation starts
- Reviewing scope before writing tickets to avoid creep during delivery
- Onboarding a new team member to the expected shape of upcoming work

## Inputs

| Input                 | Required | Description                                                            |
| --------------------- | -------- | ---------------------------------------------------------------------- |
| Feature description   | Yes      | What needs to be built and why                                         |
| Acceptance criteria   | No       | What "done" looks like from the product or business perspective        |
| Existing system notes | No       | Relevant architecture, data models, or services already in place       |
| Constraints           | No       | Timeline, team size, tech debt, compliance, legacy coupling            |
| Exclusions            | No       | What is explicitly out of scope for this feature                       |
| Mode                  | No       | `breakdown` (default) or `sprint-fit` - see Sprint-Fit Mode below      |
| Sprint capacity       | No       | Required for `sprint-fit` mode - number of engineers and sprint length |

Handle partial inputs gracefully. When input is missing, state assumptions explicitly and flag what clarification would sharpen the breakdown.

## Sprint-Fit Mode

When the user provides a team size and sprint length (or asks to "fit into sprints"), run the full breakdown first, then execute Step 6 below to allocate tasks to sprints.

**Activation**: Provide `sprint-fit` mode explicitly, or include capacity context such as "team of 3 engineers, 2-week sprints" in the request.

**Output**: Produces the full breakdown from Steps 1-5 plus a sprint allocation plan from Step 6.

## Rules

- Identify hidden complexity before sizing tasks - do not estimate on a feature description alone
- Every task must have a stated dependency (or "none") to enable safe sequencing
- Size estimates are relative (S/M/L/XL) - never calendar time unless explicitly requested
- Scope creep risks are flagged at task level, not just feature level
- Distinguish between implementation tasks, infrastructure tasks, and validation tasks
- Do not generate implementation code - describe what to build, not how to build it
- Omit empty sections in output
- When a task is XL, recommend breaking it down further before it enters a sprint

## Breakdown Model

### Step 1 - Complexity Signal Scan

Before creating any task, scan for hidden complexity that inflates effort or introduces risk:

Use skill: `stack-detect` to identify stack-specific complexity signals.
Use skill: `change-risk-classification` to assess risk domains touched by this feature.
Use skill: `backward-compatibility-analysis` to identify contract or schema compatibility work.

Check for these hidden cost areas:

| Signal                   | Questions to Answer                                                       |
| ------------------------ | ------------------------------------------------------------------------- |
| Database changes         | New table, column, index, or migration? Zero-downtime required?           |
| API contract changes     | New endpoints or changed fields? External consumers affected?             |
| Auth / permissions       | New roles, scopes, or authorization rules?                                |
| Async / event flows      | New queues, topics, consumers, or producers?                              |
| Third-party integrations | New external APIs, webhooks, or SDKs?                                     |
| Data backfill            | Existing data needs migration or transformation?                          |
| Observability gaps       | New flows need logging, metrics, tracing?                                 |
| Backward compatibility   | Old and new behavior must coexist during rollout?                         |
| Rollback complexity      | Can this be rolled back safely? What data would be in inconsistent state? |
| Test surface expansion   | Integration tests, contract tests, load tests needed beyond unit tests?   |
| Deployment coordination  | Deploy ordering required across services or teams?                        |

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
Use skill: `blast-radius-analysis` to assess which tasks carry the highest rollback risk.

### Step 3 - Dependency Graph

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

### Step 4 - Effort Summary

Produce a summary table:

| Task | Type | Size     | Scope Flag                            | Depends On      |
| ---- | ---- | -------- | ------------------------------------- | --------------- |
| Name | type | S/M/L/XL | must-have/nice-to-have/risk-reduction | task(s) or none |

Totals:

- Must-have tasks: count, aggregate size
- Nice-to-have tasks: count, aggregate size
- Risk-reduction tasks: count, aggregate size

### Step 6 - Sprint Fit (sprint-fit mode only)

**Skip this step if sprint-fit mode was not activated.**

Allocate tasks to sprints based on:

- **Team capacity**: Convert T-shirt sizes to relative points using the capacity provided
  - S = 1 point, M = 2 points, L = 4 points, XL = 8 points (adjust if team has different conventions)
  - Default capacity: 1 engineer = 2 points per week (or as stated in inputs)
- **Dependency ordering**: Tasks that depend on earlier tasks cannot be moved to an earlier sprint
- **Risk distribution**: Avoid concentrating all high-risk tasks in one sprint
- **Scope flags**: Nice-to-have and risk-reduction tasks are last-in, first-out if capacity is tight

For each sprint:

- List tasks assigned with their size
- Show capacity used vs available
- Flag if the sprint is over-capacity (must de-scope or split)
- Flag any must-have tasks that do not fit within the total sprint budget (requires scope or timeline negotiation)

**Capacity sizing formula:**

```
Sprint capacity (points) = team size (engineers) x sprint weeks x 2 points/engineer/week x 0.7 (overhead buffer)
```

The 0.7 buffer accounts for meetings, reviews, incidents, and context switching. Adjust if team has empirical velocity data.

**Example** (3 engineers, 2-week sprints):

- Raw capacity: 3 x 2 x 2 = 12 points
- With buffer: 12 x 0.7 = 8 points per sprint

Output a sprint allocation table:

```
Sprint 1 (capacity: N points)
  Task A [M] - 2 pts - deps: none
  Task B [S] - 1 pt  - deps: none
  Used: 3/8 pts

Sprint 2 (capacity: N points)
  Task C [L] - 4 pts - deps: Task A
  Task D [M] - 2 pts - deps: Task A
  Used: 6/8 pts

Sprint 3 ...
```

Flag:

- Over-capacity sprints (must de-scope or extend timeline)
- Must-have tasks that exceed total sprint budget (epic must be split or timeline extended)
- Nice-to-have tasks deferred if capacity is tight

### Step 5 - Scope Creep and Risk Flags

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

## Output

```markdown
# Scope Breakdown: [Feature Name]

## Complexity Signals Detected

[List of signals from Step 1 that apply, with brief note on impact]

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

## Effort Summary

| Task | Type | Size | Scope | Depends On |
| ---- | ---- | ---- | ----- | ---------- |

**Must-have total**: N tasks (aggregate: S+M+L...)
**Nice-to-have total**: N tasks
**Risk-reduction total**: N tasks

## Scope and Risk Flags

### Scope Creep Risks

- [Flag]: [Recommendation]

### Hidden Risks

- [Flag]: [Recommendation]

## Sprint Allocation (sprint-fit mode only)

**Team:** {N engineers}, **Sprint:** {N weeks}, **Capacity:** {N points/sprint}

### Sprint 1

| Task | Size     | Points | Deps |
| ---- | -------- | ------ | ---- |
| Name | S/M/L/XL | N      | none |

**Used:** N / N points

### Sprint 2

[repeat]

### Sprint Summary

| Sprint | Tasks | Points Used | Points Available | Status                   |
| ------ | ----- | ----------- | ---------------- | ------------------------ |
| 1      | N     | N           | N                | On track / Over capacity |

**Must-have delivery:** Sprint N
**Nice-to-have completion:** Sprint N or deferred

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
- Optimize for copy-paste into a ticket tracker
- In sprint-fit mode, include the Sprint Allocation section after the Effort Summary

## Success Criteria

A well-executed scope breakdown passes all of these.

### Completeness

- [ ] Complexity signal scan completed before any task was created
- [ ] Every hidden cost area (migrations, observability, rollback, compat) has been checked
- [ ] Every task has a type, size, dependency statement, and scope flag
- [ ] A dependency order and critical path are identified
- [ ] Scope creep risks are flagged - not assumed away

### Sizing Quality

- [ ] XL tasks are flagged for breakdown - none silently accepted
- [ ] Size rationale references complexity signals, not calendar time
- [ ] The aggregate must-have effort is a realistic delivery signal for the tech lead

### Staff-Level Signal

- [ ] Hidden tasks (observability, rollback verification, data migration) are surfaced - not left to be discovered mid-sprint
- [ ] Nice-to-have tasks are explicitly separated from must-have - no scope ambiguity
- [ ] Open questions that would change the breakdown are listed, not silently assumed away
- [ ] The critical path is identified so the team knows where to reduce risk first

## Avoid

- Generating implementation code or detailed technical design
- Estimating in calendar days or hours without being asked
- Accepting a feature description at face value without scanning for hidden complexity
- Treating all tasks as must-have when scope has not been agreed
- Ignoring rollback complexity on data and infrastructure tasks
- Creating tasks without dependency relationships - sequence matters
- Generic task names ("Backend work", "Testing") - every task must be actionable

## Key Skills Reference

- Use skill: `stack-detect` for stack-specific hidden complexity signals
- Use skill: `change-risk-classification` for risk domain identification
- Use skill: `backward-compatibility-analysis` for contract and schema compatibility work
- Use skill: `dependency-impact-analysis` for deployment ordering of infrastructure tasks
- Use skill: `blast-radius-analysis` for rollback risk assessment per task

**Sprint-fit mode only:**

- Apply capacity formula: `team size x sprint weeks x 2 x 0.7` for default velocity
- Use dependency order from Step 3 to constrain sprint allocation
- Flag over-capacity sprints rather than silently overfilling them

## After This Skill

If the output needed significant adjustment - tasks were wrong-sized, hidden complexity was missed, or the dependency order was off - run `/task-skill-feedback` to log what changed and why.
