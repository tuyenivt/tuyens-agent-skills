---
name: task-pr-conflict-analysis
description: Detect semantic conflicts across concurrent active PRs - logical incompatibilities, shared state mutations, integration ordering risks, and blast radius overlap. Use when multiple branches touch the same codebase areas and you need a safe merge order.
metadata:
  category: review
  tags: [pull-request, conflicts, concurrent, integration, merge-order]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# PR Conflict Analysis

## Purpose

Cross-PR semantic conflict detection for tech leads managing concurrent active branches:

- **Semantic conflicts** -- changes that don't produce a git merge conflict but break each other's assumptions
- **Shared state mutations** -- two PRs modifying the same database schema, config, or shared component
- **Integration ordering risks** -- PRs that must merge in a specific order to avoid a broken intermediate state
- **Blast radius overlap** -- when two PRs touch the same high-risk areas, their combined blast radius is larger than either alone

This skill detects conflicts before merge. It does not review individual PR quality (use `/task-code-review` or `/task-code-review-advanced` for that).

## When to Use

- When multiple branches are active in the same codebase areas and you want to detect conflicts before merge
- Before merging a batch of concurrent PRs
- When two PRs touch the same service, module, schema, or API contract
- When a shared dependency or library is being changed by multiple PRs simultaneously
- On-call or release preparation when understanding what changed is critical

## Inputs

| Input            | Required | Description                                                       |
| ---------------- | -------- | ----------------------------------------------------------------- |
| PR list          | Yes      | List of PRs to analyze - titles, descriptions, or diffs           |
| Merge target     | No       | Target branch (default: main)                                     |
| Priority order   | No       | Any known merge priority or deadline ordering                     |
| Codebase context | No       | Key shared modules, schema areas, or services relevant to the PRs |

Handle partial inputs gracefully. When only PR titles or descriptions are available without diffs, surface likely conflict areas based on stated changes and flag for manual verification.

## Rules

- Detect semantic conflicts, not just git conflicts - two non-conflicting diffs can break each other
- Every conflict must state what breaks if PRs merge in the wrong order or simultaneously
- Ordering recommendations must state the reason - not just a numbered list
- Flag PRs that should be blocked pending resolution of a conflict in another PR
- When analysis is limited by missing diffs, state assumptions and flag for manual check
- Omit empty sections in output

## Analysis Model

### Step 1 - Stack and Shared Resources

Use skill: `stack-detect` to identify the project stack.

Map shared resources across all PRs:

| Resource Type        | Examples                                                           |
| -------------------- | ------------------------------------------------------------------ |
| Database schema      | Table additions, column changes, index additions, migration files  |
| API contracts        | Endpoint additions, request/response shape changes, removed fields |
| Shared configuration | Environment variables, feature flags, app configuration files      |
| Shared modules       | Utility classes, base classes, shared services, common libraries   |
| Event contracts      | Message schemas, event types, queue or topic names                 |
| Auth / permissions   | Role definitions, permission checks, middleware changes            |
| Build artifacts      | Shared test fixtures, factory methods, mock objects                |

### Step 2 - Per-PR Change Summary

For each PR, extract:

- What it adds, modifies, or deletes
- Which shared resources it touches
- What assumptions it makes about the state of the codebase at merge time

**When diffs are unavailable:** If only PR titles or descriptions are provided, infer likely change areas from the description (e.g., "refactors UserService" likely touches user-related models, repositories, and tests). Flag each inference as assumed and recommend manual verification of the specific conflict areas identified in Step 3.

### Step 3 - Conflict Detection

Cross-analyze all PRs for these conflict types:

#### 3a. Schema Conflicts

Two or more PRs modify the same table, migration sequence, or add conflicting constraints:

- Same table migration in multiple PRs (column added independently, naming collision)
- Migration version number conflicts (same timestamp or sequential number used twice)
- One PR adds a NOT NULL column without a default; another PR inserts rows to the same table

#### 3b. API Contract Conflicts

Two or more PRs modify the same endpoint or shared DTO/schema:

- One PR adds a required field; another PR calls the endpoint without that field
- One PR renames a field; another PR depends on the old field name
- One PR deprecates an endpoint; another PR adds a consumer for that endpoint

#### 3c. Shared Code Conflicts

Two or more PRs modify the same shared module, base class, or utility:

- Both modify the same method signature
- One adds behavior to a shared class that another PR's change invalidates
- One PR refactors a class while another adds features to the pre-refactor version

#### 3d. Logic and State Conflicts

Two PRs make assumptions about shared state that are mutually exclusive:

- One PR assumes feature flag X is off; another PR assumes it is on
- One PR caches data with a given key format; another changes the key format
- One PR changes how auth tokens are validated; another adds code using the old validation path

#### 3e. Integration Ordering Conflicts

PRs that are individually correct but must merge in a specific order:

- Schema must be deployed before the code that uses the new column
- New shared utility must merge before consumers of that utility
- API producer change must merge before API consumer change

Use skill: `dependency-impact-analysis` for deployment ordering assessment.

### Step 4 - Blast Radius Overlap

When two or more PRs touch the same high-risk area, their combined blast radius is higher than either alone:

Use skill: `review-change-risk` to classify the risk domains each PR touches.
Use skill: `review-blast-radius` to assess each PR's individual blast radius.

Flag PRs where blast radius overlap creates elevated combined risk:

- Both touch auth, payments, or core data access
- Both modify high-traffic endpoints
- Both change shared caching behavior

### Step 5 - Merge Order Recommendation

Based on conflict and dependency analysis, recommend a safe merge order:

For each ordering constraint:

- State which PR must merge first
- State why (schema dependency, API producer/consumer ordering, shared code conflict)
- State what breaks if the order is violated

Flag any PRs that should be held pending resolution of a conflict in another PR.

## Output

```markdown
# PR Conflict Analysis

## Summary

**PRs Analyzed:** {count}
**Conflicts Found:** {count}
**Integration Risks:** {count}
**Stack:** {detected language / framework}

## Conflict Map

| PR   | Conflicts With | Conflict Type | Severity |
| ---- | -------------- | ------------- | -------- |
| PR-A | PR-B           | Schema        | High     |
| PR-C | PR-D           | API Contract  | Medium   |

## Conflict Details

### [High] PR-A conflicts with PR-B - Schema Conflict

- **What conflicts**: {e.g., "Both add a migration modifying the `orders` table - PR-A adds column `status`, PR-B adds column `status` with a different type"}
- **What breaks**: {what fails if both merge without coordination}
- **Resolution**: {how to resolve - e.g., "Combine into one migration, or sequence PR-A first and rebase PR-B"}

### [Medium] PR-C conflicts with PR-D - API Contract Conflict

- **What conflicts**: {description}
- **What breaks**: {description}
- **Resolution**: {description}

## Integration Ordering

Recommended merge order to avoid broken intermediate states:

1. {PR name or ID} - {reason: e.g., "Adds shared utility consumed by PR-2 and PR-3"}
2. {PR name or ID} - {reason}
3. {PR name or ID and PR name} - {can merge in parallel once 1 and 2 are merged}

**PRs to hold**: {Any PRs that should not merge until another conflict is resolved}

## Blast Radius Overlap

| PRs         | Shared Risk Area | Combined Blast Radius | Note                                                            |
| ----------- | ---------------- | --------------------- | --------------------------------------------------------------- |
| PR-A + PR-B | Auth middleware  | Wide                  | Both touch auth path - merge separately with validation between |

## No-Conflict PRs

{PRs with no detected conflicts - safe to merge in any order}

## Assumptions and Manual Checks

- {Assumption made due to missing diff - flag for manual verification}
- {Area where analysis was limited by available information}
```

### Output Constraints

- Conflict map must be shown before detail sections
- Every conflict must state what breaks and how to resolve
- Merge order must state the reason for each ordering constraint
- PRs with no conflicts must be explicitly listed - do not silently omit them
- Assumptions from limited input must be listed

## Self-Check

- [ ] All PRs analyzed; schema, API, shared code, logic, and ordering conflicts all checked
- [ ] Semantic conflicts detected, not just git merge conflicts
- [ ] Every conflict has a stated resolution path; PRs with no conflicts explicitly listed
- [ ] Severity levels reflect actual merge risk; hold recommendations state which PR is blocked by which conflict
- [ ] Output gives a clear merge plan; conflicts resolvable before merge review starts

## Avoid

- Reporting only git conflicts (semantic conflicts are the harder problem)
- Ordering recommendations without reasons
- Treating every overlap as a conflict (read access to the same class is not a conflict)
- Silently omitting PRs with no conflicts
- Reviewing individual PR quality (use `task-code-review` for that)
