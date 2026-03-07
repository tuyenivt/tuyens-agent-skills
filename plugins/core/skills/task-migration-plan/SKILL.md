---
name: task-migration-plan
description: Safe database migration strategy - zero-downtime sequencing, expand-contract, rollback plan, data backfill estimation, and lock risk assessment. Plans the migration strategy only - not for writing migration files (use task-spring-new / task-dotnet-new for scaffolding).
metadata:
  category: data
  tags: [migration, database, schema, zero-downtime, rollback, expand-contract]
  type: workflow
user-invocable: true
---

# Migration Plan

## Purpose

Safe database migration planning for production systems, optimized for zero-downtime delivery:

- **Expand-contract first** -- sequence schema and code changes to eliminate deploy-time lock-in
- **Lock risk assessment** -- identify which operations acquire table locks and for how long
- **Rollback by default** -- every migration phase has an explicit rollback procedure before it runs
- **Backfill planning** -- estimate cost and duration of data backfills to avoid surprise timeouts
- **Multi-service coordination** -- flag when schema changes require deployment ordering across services

This skill produces a migration execution plan. It does not generate ORM model code or migration scripts.

## When to Use

- Adding a column, table, or index to a production database
- Changing a column type, name, or constraint
- Splitting or merging tables
- Migrating data from one shape to another (backfill)
- Removing a column or table that is no longer needed
- Introducing a foreign key or unique constraint on existing data

## Inputs

| Input                   | Required | Description                                                              |
| ----------------------- | -------- | ------------------------------------------------------------------------ |
| Change description      | Yes      | What schema or data change is needed and why                             |
| Current schema          | No       | Relevant table definitions (paste DDL or describe columns)               |
| Estimated row count     | No       | Approximate rows in affected tables (shapes backfill and lock estimates) |
| Database engine         | No       | PostgreSQL, MySQL, SQLite, etc. (shapes lock behavior advice)            |
| Deployment model        | No       | Single service, multi-service, blue-green, rolling, canary               |
| Downtime tolerance      | No       | Is any downtime acceptable, or is zero-downtime required?                |
| Existing migration tool | No       | Flyway, Liquibase, ActiveRecord, Alembic, golang-migrate, etc.           |

Handle partial inputs gracefully. When row counts or schema are missing, state assumptions and flag where estimates are uncertain.

## Rules

- Rollback plan is designed before the migration runs, not after it fails
- Every operation that acquires a table lock must be identified and its duration estimated
- Expand-contract is the default strategy for zero-downtime - skip it only with explicit justification
- Backfill operations on large tables must be batched - never run unbounded UPDATE on a production table
- Additive changes (new nullable column, new table) are safe; destructive changes (drop column, add NOT NULL) need extra phases
- Application code must be backward compatible with both old and new schema during the transition window
- Flag changes that affect multiple services - deployment order matters
- Omit empty sections in output
- When evidence is insufficient, state what is missing rather than guessing

## Migration Planning Model

### Step 1 - Change Classification

Classify the migration before planning any steps.

Use skill: `change-risk-classification` to identify risk domains.
Use skill: `db-migration-safety` for lock risk assessment, expand-contract sequencing, and backfill safety rules.
Use skill: `backward-compatibility-analysis` to assess application-level compatibility during transition.

**Schema change type:**

| Type                    | Risk Level | Zero-Downtime Complexity                     |
| ----------------------- | ---------- | -------------------------------------------- |
| Add nullable column     | Low        | Low - single phase                           |
| Add table               | Low        | Low - single phase                           |
| Add index (concurrent)  | Low-Medium | Medium - locking depends on DB               |
| Add NOT NULL constraint | Medium     | High - requires backfill first               |
| Add unique constraint   | Medium     | High - requires data validation first        |
| Add foreign key         | Medium     | High - requires existing data to be valid    |
| Rename column           | High       | Very high - requires expand-contract         |
| Change column type      | High       | Very high - requires expand-contract         |
| Drop column             | High       | High - requires all readers removed first    |
| Drop table              | High       | High - requires all references removed first |
| Backfill existing rows  | Variable   | Medium-High - batch sizing critical          |
| Split or merge tables   | Very High  | Very high - requires dual-write phase        |

State the type and risk level before continuing.

### Step 2 - Lock Risk Assessment

Identify which operations in this migration acquire locks and estimate duration.

Use skill: `db-indexing` for index creation lock behavior.

**Common lock risks by database:**

**PostgreSQL:**

- `ALTER TABLE ADD COLUMN` (nullable, no default): lock brief, safe
- `ALTER TABLE ADD COLUMN ... DEFAULT ...` (< PG11): full table rewrite, dangerous on large tables
- `ALTER TABLE ADD COLUMN ... DEFAULT ...` (PG11+): metadata only, safe
- `CREATE INDEX`: full table scan, but `CREATE INDEX CONCURRENTLY` avoids lock (cannot run in transaction)
- `ALTER TABLE ADD CONSTRAINT NOT NULL`: full table scan to validate
- `ALTER TABLE ADD CONSTRAINT FOREIGN KEY`: full table scan
- `DROP COLUMN`: brief lock, but `NOT VALID` pattern can defer validation

**MySQL / MariaDB:**

- Many `ALTER TABLE` operations cause full table copy (Online DDL varies by version and engine)
- `ADD INDEX`: rebuilds index but can use online DDL in InnoDB
- `ADD COLUMN` not at end: full table copy in older versions

For each migration step, state:

- Lock type acquired (ACCESS SHARE, SHARE, EXCLUSIVE, ACCESS EXCLUSIVE)
- Estimated lock duration relative to table size
- Whether a concurrent/online alternative exists

Flag any step with an exclusive lock on a table larger than estimated threshold (default: 1M rows = high risk).

### Step 3 - Expand-Contract Strategy

For any change that is not purely additive, apply expand-contract to eliminate the coupling between schema change and code deploy.

**The three phases:**

**Expand phase** -- schema becomes compatible with both old and new application code:

- Add the new column / table / index
- Keep the old column / table in place
- Application writes to both old and new (dual-write)
- Application reads from old (new column may have nulls)

**Migrate phase** -- backfill data into new structure while both are live:

- Backfill old data into new column / table in batches
- Validate completeness and correctness before proceeding
- Application begins reading from new once backfill is complete and verified

**Contract phase** -- remove the old structure once all readers and writers use the new:

- Remove dual-write from application code
- Verify no readers or writers reference old column / table (search codebase and logs)
- Drop old column / table in a separate deployment

Apply this pattern to: column renames, type changes, table splits, constraint additions on existing data.

Skip expand-contract only when:

- The change is purely additive (new nullable column, new table with no existing data dependency)
- Downtime is explicitly acceptable and scheduled

Use skill: `release-safety` to plan the deploy ordering across expand, migrate, and contract phases.
Use skill: `dependency-impact-analysis` for multi-service deployment ordering.

### Step 4 - Backfill Planning

If data migration is required (existing rows need updating), plan the backfill operation.

**Never run:**

```sql
UPDATE large_table SET new_col = old_col WHERE new_col IS NULL;
```

**Always batch:**

```sql
-- Pseudocode: run in a loop until 0 rows updated
UPDATE table SET new_col = old_col
WHERE id BETWEEN :start AND :end
  AND new_col IS NULL
LIMIT 1000;
```

Estimate for the backfill plan:

| Estimate            | How to Calculate                                                        |
| ------------------- | ----------------------------------------------------------------------- |
| Total rows          | From input or assume from table name context                            |
| Batch size          | 100-1000 rows is safe for most tables; smaller if row is wide or hot    |
| Rows per second     | Estimate 1000-5000 rows/sec for simple updates; less for joins or calcs |
| Total duration      | rows / rows_per_second (flag if > 1 hour - risk of failure mid-run)     |
| Lock held per batch | Brief row-level locks per batch; no table lock if batched correctly     |
| Retry safety        | Is the backfill idempotent? Can it be re-run safely?                    |

Use skill: `idempotency` to ensure the backfill is safe to re-run.

Recommend a backfill approach:

- **In-migration script** (safe for small tables or fast operations)
- **Separate background job** (preferred for large tables - decoupled from deploy)
- **Application-layer dual-write + lazy migration** (preferred when backfill cannot complete before deploy)

### Step 5 - Rollback Plan

Define rollback procedures for each phase of the migration. Rollback must be designed before the migration runs.

For each phase, answer:

1. **What does rollback require?** (schema revert, data revert, code revert)
2. **Is rollback data-safe?** (have rows been written that cannot be un-written without data loss?)
3. **What is the rollback time estimate?** (seconds / minutes / hours)
4. **What is the rollback trigger?** (error rate threshold, timeout, explicit abort signal)

**Rollback complexity by change type:**

| Change                        | Rollback Safety          | Rollback Mechanism                 |
| ----------------------------- | ------------------------ | ---------------------------------- |
| Add nullable column           | Safe                     | Drop column (if no data written)   |
| Backfill (partial)            | Safe                     | Leave nulls; restart backfill      |
| Backfill (complete)           | Conditional              | Revert if old column still exists  |
| Drop column                   | Dangerous                | Restore from backup only           |
| Type change (expand-contract) | Safe during expand phase | Drop new column; revert dual-write |
| Add NOT NULL constraint       | Safe before contract     | Drop constraint; revert validation |
| Remove NOT NULL (relax)       | Safe                     | Re-add constraint                  |

Flag any phase where rollback requires a database restore - this is a go/no-go decision point.

Use skill: `blast-radius-analysis` to assess the impact if the rollback itself fails.

### Step 6 - Execution Plan

Produce the phased execution plan with ordered steps.

For each step, state:

- **Action**: What to run (migration script, application deploy, backfill job, etc.)
- **Pre-condition**: What must be true before this step runs
- **Lock risk**: Lock acquired, estimated duration
- **Rollback**: How to undo this step specifically
- **Validation**: How to confirm this step succeeded before proceeding

## Output

```markdown
# Migration Plan: [Change Description]

## Change Classification

- **Type**: [schema change type]
- **Risk level**: Low / Medium / High / Very High
- **Zero-downtime strategy**: Expand-contract / Single-phase additive / Scheduled downtime
- **Backfill required**: Yes / No
- **Multi-service coordination required**: Yes / No

## Lock Risk Assessment

| Step | Operation | Lock Type | Estimated Duration | Alternative               |
| ---- | --------- | --------- | ------------------ | ------------------------- |
| 1    | Operation | Exclusive | Estimate           | Concurrent index creation |

**High-risk steps**: [List steps with exclusive locks on large tables]

## Migration Phases

### Phase 1: Expand -- [date or deploy N]

**Goal**: Schema becomes compatible with both old and new application code.

| Step | Action | Pre-condition     | Lock Risk       | Rollback    | Validation     |
| ---- | ------ | ----------------- | --------------- | ----------- | -------------- |
| 1    | What   | What must be true | Type / duration | How to undo | How to confirm |

**Application changes required**: [what code changes ship with this deploy]
**Backward compatible with old schema**: Yes / No

### Phase 2: Migrate -- [background job or deploy N+1]

**Goal**: Backfill data into new structure.

**Backfill estimate**:

- Rows to process: [estimate]
- Batch size: [recommended]
- Estimated duration: [estimate]
- Idempotent: Yes / No

| Step | Action | Pre-condition | Rollback | Validation |
| ---- | ------ | ------------- | -------- | ---------- |

### Phase 3: Contract -- [deploy N+2 or later]

**Goal**: Remove old structure. Run only after all readers and writers use new structure.

**Pre-condition checklist**:

- [ ] No application code reads or writes old column/table
- [ ] Logs confirm zero reads/writes to old column/table for [N days]
- [ ] Backfill complete and validated

| Step | Action | Lock Risk | Rollback | Validation |
| ---- | ------ | --------- | -------- | ---------- |

## Rollback Procedures

| Phase | Rollback Action | Data Safety | Time Estimate | Trigger              |
| ----- | --------------- | ----------- | ------------- | -------------------- |
| 1     | What to do      | Safe/Risky  | Duration      | When to pull trigger |

**Phases requiring backup restore to roll back**: [list, or "none"]

## Backfill Plan

- **Approach**: In-migration script / Background job / Lazy migration
- **Batch size**: [recommended]
- **Idempotent**: Yes / No (reason)
- **Re-run safe**: Yes / No
- **Monitoring**: How to track backfill progress

## Multi-Service Coordination

[Only if applicable]

| Service | Deploy Order | Schema Compatibility Requirement |
| ------- | ------------ | -------------------------------- |
| Name    | Before/After | What it requires                 |

## Assumptions

- [Assumption made due to missing input]

## Open Questions

- [Question that would change the plan if answered]
```

### Output Constraints

- No ORM model code or migration script code
- Every phase must have a rollback procedure
- Every lock-acquiring step must state lock type and estimated duration
- Backfill operations must always be batched - never unbounded
- Omit phases that do not apply to this migration
- Flag any phase where rollback requires a restore - make this explicit, not a footnote

## Success Criteria

A well-executed migration plan passes all of these.

### Safety

- [ ] Lock risk assessed for every schema operation
- [ ] No unbounded UPDATE or DELETE on a large table - backfill is batched
- [ ] Rollback procedure defined before any step runs
- [ ] Phases requiring backup restore to roll back are explicitly flagged
- [ ] Expand-contract applied to all non-additive changes unless downtime is explicitly accepted

### Completeness

- [ ] All phases are sequenced with pre-conditions
- [ ] Backfill duration estimated where data migration is needed
- [ ] Multi-service deployment ordering flagged where applicable
- [ ] Application code changes are aligned with each schema phase

### Staff-Level Signal

- [ ] The plan answers "what happens if this fails at phase N?" for every phase
- [ ] Backfill is idempotent - it can be re-run safely after a failure
- [ ] The plan can be handed to a junior engineer to execute with confidence
- [ ] The validation step for each phase is concrete, not "check that it worked"

## Avoid

- Generating ORM model code or migration script code
- Running migrations without a defined rollback plan
- Recommending unbounded UPDATE/DELETE on production tables
- Skipping expand-contract for non-additive changes without explicit justification
- Treating "add a column" as always trivially safe (NOT NULL, DEFAULT, and constraint additions are not)
- Ignoring multi-service deployment ordering when shared databases are involved
- Vague validation steps ("verify the migration ran") - validations must be concrete and checkable

## Key Skills Reference

- Use skill: `change-risk-classification` for migration risk domain assessment
- Use skill: `backward-compatibility-analysis` for application-level compatibility during transition
- Use skill: `db-indexing` for index creation lock behavior and query access patterns
- Use skill: `idempotency` for backfill operation safety
- Use skill: `release-safety` for deploy ordering across migration phases
- Use skill: `dependency-impact-analysis` for multi-service deployment coordination
- Use skill: `blast-radius-analysis` for rollback failure impact assessment

## After This Skill

If the output needed significant adjustment - lock risk was underestimated, expand-contract phasing was wrong, or rollback procedures were missing - run `/task-skill-feedback` to log what changed and why.
