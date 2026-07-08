---
name: task-db-migration
description: "Plan or review zero-downtime DB migration: expand-contract phasing, lock risk, backfill, rollback for risky schema changes."
agent: architecture-architect
metadata:
  category: data
  tags: [migration, database, schema, zero-downtime, rollback, expand-contract]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows. If a delegated skill is unavailable (standalone use), apply the step's inline instructions on judgment and say so in the output.

# Migration Plan

## Purpose

Safe zero-downtime DB migration plan: expand-contract phasing, lock risk, batched backfill, rollback per phase, and multi-service coordination. Produces an execution plan; no ORM code or migration scripts.

**Not for**: Simple additive changes (just write the migration), or writing migration files (use stack-specific `task-*-new`).

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

- Rollback designed before the migration runs; flag any phase needing backup restore
- Every lock-acquiring operation states lock type and estimated duration
- Expand-contract is the default for zero-downtime; skip only with explicit downtime authorization
- Backfill is batched and idempotent - never unbounded UPDATE on a production table
- Application code stays backward compatible with old and new schema during transition
- Flag multi-service deployment ordering when schemas are shared

## Migration Planning Model

### Step 1 - Change Classification

Classify the migration before planning any steps.

Use skill: `review-change-risk` to identify risk domains.
Use skill: `backend-db-migration` for lock risk assessment, expand-contract sequencing, and backfill safety rules.
Use skill: `ops-backward-compatibility` to assess application-level compatibility during transition.

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

**Compound migrations:** When a single migration request contains multiple change types, classify each sub-change separately. State the dependency order (which changes must complete before others can begin). The overall risk level is the highest individual risk level among the sub-changes.

State the type and risk level before continuing.

### Step 2 - Lock Risk Assessment

Identify which operations in this migration acquire locks and estimate duration.

Use skill: `backend-db-indexing` for index creation lock behavior.

**Lock risk reference:**

| Operation                         | PostgreSQL                                      | MySQL/MariaDB                     |
| --------------------------------- | ----------------------------------------------- | --------------------------------- |
| ADD COLUMN (nullable, no default) | Brief lock - safe                               | Brief (InnoDB)                    |
| ADD COLUMN with DEFAULT (PG11+)   | Metadata only - safe                            | INSTANT on 8.0.12+ (any position 8.0.29+); table copy older |
| ADD COLUMN with DEFAULT (< PG11)  | Full table rewrite - dangerous                  | -                                 |
| CREATE INDEX                      | Full scan; use CONCURRENTLY (cannot run in txn) | Online DDL in InnoDB              |
| ADD CONSTRAINT NOT NULL / FK      | Full table scan to validate                     | Full table copy                   |
| DROP COLUMN                       | Brief lock; NOT VALID can defer FK validation   | Online DDL                        |

For each migration step, state:

- Lock type acquired, in the engine's vocabulary (PostgreSQL: ACCESS SHARE through ACCESS EXCLUSIVE; MySQL: metadata lock + InnoDB row locks - and note that an MDL request queues behind long-running queries and blocks everything behind it)
- Estimated lock duration relative to table size
- Whether a concurrent/online alternative exists

Flag any step whose exclusive lock duration scales with table size on tables larger than the threshold (default 1M rows = high risk). Brief metadata-only exclusive locks (e.g., ADD COLUMN) pass, but set a `lock_timeout` with retry so they cannot queue behind long transactions. The reference table shows the naive form of each operation; Step 3's sequences avoid the worst cases (e.g., NOT NULL via validated CHECK is metadata-only).

### Step 3 - Expand-Contract Strategy

Apply to any change that is not purely additive (renames, type changes, table splits, constraint additions on existing data).

| Phase | Schema state | App state |
| ----- | ------------ | --------- |
| **Expand** | Add new column/table; keep old | Dual-write old + new; read old |
| **Migrate** | New populated and validated | Read flips to new after verification |
| **Contract** | Drop old in separate deploy | Stop dual-write; verify no readers/writers reference old |

**PostgreSQL: adding NOT NULL on large tables.** Validating with a full scan acquires ACCESS EXCLUSIVE. Use `NOT VALID` + `VALIDATE CONSTRAINT` (ShareUpdateExclusiveLock, non-blocking) whenever validating against >1M rows. Sequence: nullable column -> dual-write -> batched backfill -> `ADD CONSTRAINT ... NOT VALID` -> background `VALIDATE CONSTRAINT` -> `SET NOT NULL` (metadata-only on PG12+ once a validated CHECK exists) -> drop the redundant CHECK. On a rename, relax the old column's NOT NULL before stopping dual-write.

**MySQL/InnoDB:** prefer `ALGORITHM=INPLACE` or `INSTANT` and verify support per operation and server version; use pt-osc/gh-ost for operations that force a table rebuild. Multi-table `RENAME TABLE` is atomic - use it for cutovers. Unique-index builds fail on duplicate data - dedupe first (Step 4). For table splits, bake new constraints into the new table's DDL (no online constraint add needed) and keep the old table write-complete until cutover so a reverse RENAME is lossless.

Name the dual-write mechanism and its failure modes in the Expand phase's "Application changes required" field: trigger-based survives mixed app versions during rolling deploys; application-level is simpler to remove. Renames and table swaps carry dependent objects - inventory indexes, FKs, views, triggers, RLS policies, grants, and replication publications in the pre-conditions. Build secondary indexes after bulk backfill (denser, faster) unless reads need them during dual-write. Skip expand-contract only when: the change is purely additive, or downtime is explicitly acceptable and scheduled.

Use skill: `ops-release-safety` for deploy ordering across phases.
Use skill: `dependency-impact-analysis` for multi-service ordering.

### Step 4 - Backfill Planning

If data migration is required (existing rows need updating), plan the backfill operation.

**Never run unbounded UPDATE on a production table.** Always batch by ID range or cursor, 100-1000 rows per batch, in a loop until 0 rows updated. (The batch and rate numbers below are for in-place UPDATEs; bulk copies via batched INSERT...SELECT size by measured rows/sec on a staging slice, and any job over ~1 hour needs checkpointed resume.)

Backfills that prepare a constraint include data repair: define the survivor policy for duplicates (keep newest, merge, quarantine) and run dedupe as a batched, idempotent job before adding a unique constraint. Throttle backfills on replica lag (default: pause above 10s, resume below 5s); the same throttle protects logical-replication/CDC consumers - backfill WAL floods their slots, so watch slot lag, WAL retention (`max_slot_wal_keep_size` or equivalent), and how schema changes appear in decoded events. Ongoing jobs a migration creates (e.g., a permanent archiver for a hot/cold split) are in scope as a final-phase deliverable.

Estimate for the backfill plan:

| Estimate            | How to Calculate                                                        |
| ------------------- | ----------------------------------------------------------------------- |
| Total rows          | From input or assume from table name context                            |
| Batch size          | 100-1000 rows is safe for most tables; smaller if row is wide or hot    |
| Rows per second     | Estimate 1000-5000 rows/sec for simple updates; less for joins or calcs |
| Total duration      | rows / rows_per_second (flag if > 1 hour - risk of failure mid-run)     |
| Lock held per batch | Brief row-level locks per batch; no table lock if batched correctly     |
| Retry safety        | Is the backfill idempotent? Can it be re-run safely?                    |

Use skill: `backend-idempotency` to ensure the backfill is safe to re-run (idempotent by design - re-running produces the same result).

Recommend a backfill approach:

- **In-migration script** (safe for small tables or fast operations)
- **Separate background job** (preferred for large tables - decoupled from deploy)
- **Application-layer dual-write + lazy migration** (preferred when backfill cannot complete before deploy)

### Step 5 - Rollback Plan

Per phase: what rollback requires (schema/data/code), data safety (any rows that cannot be un-written without loss), time estimate, trigger condition. Designed before the migration runs.

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

Use skill: `review-blast-radius` to assess the impact if the rollback itself fails.

### Step 6 - Execution Plan

For each step: action, pre-condition, lock acquired with duration, step-level rollback, concrete validation that confirms success before the next step - every phase's step table carries all five columns. Vague validation ("verify the migration ran") is not acceptable on Blocker-risk steps. This step renders as the per-phase step tables in the Output; the three template phases are canonical, not exhaustive - insert additional deploy phases (e.g., a per-service read/write flip between Migrate and Contract) and renumber. State which steps run as migration-tool versions vs runbook/background jobs, and flag tool constraints (e.g., `CREATE INDEX CONCURRENTLY` cannot run in a transaction - mark the migration non-transactional in Flyway/Alembic; MySQL DDL is non-transactional regardless - one statement per golang-migrate version, plan dirty-state recovery).

## Review Mode

When reviewing a migration plan authored by someone else:

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Reviews run the full lens (standalone formatting defaults; the lens's skip rule covers steps that do not fit). This skill's planning content (classification, lock reference, backfill discipline) is valid review evidence - cite it as the bar the plan must meet. Mark structurally inapplicable factors N/A with one line (e.g., no phase could ever need backup restore) - N/A is not Missing.

Supply this migration-plan-specific factor list to the completeness audit. Required = Blocker-eligible when Missing; advisory (No) factors cap at Major:

| Factor                          | Required | What "Present" Looks Like                                                       |
| ------------------------------- | -------- | ------------------------------------------------------------------------------- |
| Change classification           | Yes      | Schema change type and risk level per sub-change; compound migrations sequenced |
| Lock risk per operation         | Yes      | Lock type, estimated duration, concurrent/online alternative when applicable    |
| Expand-contract strategy        | Yes      | Three phases for non-additive changes, or explicit justification for skipping   |
| Application backward compat     | Yes      | Code stays compatible with old AND new schema during transition                 |
| Backfill plan                   | Yes*     | Batched (100-1000 rows), idempotent, re-run safe, monitored                     |
| Rollback per phase              | Yes      | What rolls back, time estimate, data safety, trigger condition                  |
| Backup-restore dependency       | No       | Phases requiring backup restore explicitly flagged as go/no-go                  |
| Multi-service coordination      | No       | Deploy order across services and non-app consumers with compat requirements     |
| Per-step pre-conditions         | No       | What must be true before each step runs                                         |
| Per-step validation             | No       | Concrete, checkable confirmation that the step succeeded                        |

*Required only when existing rows need updating.

Specific quality checks beyond the standard lens:

- **Unbounded UPDATE/DELETE on production**: Blocker; never acceptable
- **NOT NULL, FK, or unique constraint added without backfill or validation**: Blocker
- **Rollback requires backup restore but not flagged as go/no-go**: Major minimum, often Blocker
- **Expand-contract skipped on a non-additive change with no downtime authorization**: Blocker
- **Vague validation ("verify migration ran")**: Minor; promote to Major when on a Blocker-risk step
- **Lock duration estimated relative to table size for high-risk operations**: required - absence is Major

A check fires when a compound change is non-additive in aggregate even if each sub-change looks additive alone (column add + backfill + same-deploy read flip is not "single phase additive"), and when content is concretely stated but wrong - wrongness promotes, vagueness does not excuse. Record each quality-check hit once, in the lens step that owns it (Missing factor -> Completeness; internal contradiction -> Internal Consistency; Present-but-wrong or Under-specified content -> Per-Factor Findings), numbered with the lens's F-numbers. A check's preset severity overrides the advisory cap - the cap binds only completeness-status findings.

Output header: `# Migration Plan Review` and use the output structure defined in `architecture-review-lens`. Skip the plan Output template below. In this mode the Review Self-Check replaces the authoring Self-Check (self-checks are applied internally, never emitted in the deliverable):

- [ ] All factors audited with Required marking applied; verdict driven by highest severity
- [ ] Quality-check hits recorded once in the correct lens step and numbered
- [ ] Every finding cites a plan step; non-Approve verdict lists required changes

## Output

```markdown
# Migration Plan: [Change Description]

## Change Classification

- **Type**: [schema change type; for compound migrations list sub-changes: {sub-change | type | risk | depends on}]
- **Risk level**: Low / Medium / High / Very High (highest sub-change)
- **Zero-downtime strategy**: Expand-contract / Single-phase additive / Scheduled downtime
- **Backfill required**: Yes / No
- **Multi-service coordination required**: Yes / No

Phases may split per service or sub-change (Phase 2a, 2b) when independent deploys or separate gates are needed.

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

| Step | Action | Pre-condition | Lock Risk | Rollback | Validation |
| ---- | ------ | ------------- | --------- | -------- | ---------- |

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

[Only if applicable. Non-app consumers (ETL jobs, BI dashboards, replication slots) get rows too - their "deploy" is a query/config update.]

| Service / Consumer | Deploy Order | Schema Compatibility Requirement |
| ------------------ | ------------ | -------------------------------- |
| Name               | Before/After | What it requires                 |

## Assumptions

- [Assumption made due to missing input]

## Open Questions

- [Question that would change the plan if answered]
```

## Self-Check

- [ ] Lock risk assessed for every schema operation; phases needing backup restore are flagged explicitly
- [ ] No unbounded UPDATE/DELETE; backfill is batched and idempotent
- [ ] Expand-contract applied to all non-additive changes unless downtime is explicitly accepted
- [ ] All phases sequenced with pre-conditions and concrete, checkable validations
- [ ] Application code changes aligned per phase

## Avoid

- Treating "add a column" as trivially safe (NOT NULL, DEFAULT, constraint adds are not)
- Vague validation steps ("verify the migration ran") - must be concrete and checkable
