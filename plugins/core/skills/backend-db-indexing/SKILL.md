---
name: backend-db-indexing
description: Design and review database indexes - composite column ordering, covering indexes, partial indexes, expression indexes, query patterns.
metadata:
  category: performance
  tags: [database, indexing, queries, optimization]
user-invocable: false
---

# Database Indexing

> Load `Use skill: stack-detect` first to determine the project stack and database engine.

## When to Use

- Optimizing frequently executed queries
- Improving JOIN and ORDER BY performance
- Diagnosing why an index is not being used

## Rules

- Index JOIN columns and frequent WHERE/ORDER BY predicates. Index foreign-key columns on PostgreSQL, SQLite, and SQL Server; InnoDB creates one automatically only when no existing index leads with the FK columns, so an explicit FK index there is adopted, and a second index leading with the same column is the duplicate. A primary key or unique constraint is an index for every rule here.
- Align indexes with actual query patterns - inspect EXPLAIN, not intuition. Without EXPLAIN, recommend from schema and query shape and suffix each finding `(unverified - confirm with EXPLAIN)`. When traffic or table size is unknown, take severity from the query's role (request path or incident cause vs background path) under the same suffix; read a query's callers, inside the reviewed files or not, to settle its role; a caller that cannot be read adds the suffix `(unverified - callers outside the reviewed files)`.
- Composite column order: always-present equality columns first, then the ORDER BY columns, then range columns - a range column before the sort column breaks the index's ability to return rows pre-sorted. Key direction matters only when the ORDER BY mixes ASC and DESC (a uniform sort is served by a backward scan; MySQL honours `DESC` key parts from 8.0). An optional equality filter (`?status=`) never leads: it trails the sort column as an index filter, or gets a second index when its filtered path is hot.
- Functions on indexed columns disable the index - rewrite the query or add an expression index. Under a case-insensitive collation (MySQL `utf8mb4_0900_ai_ci`, SQL Server defaults) a `LOWER()` wrapper is unnecessary: drop it rather than index it.
- Avoid single-column indexes on evenly distributed low-cardinality columns (a few distinct values - the optimizer prefers a scan). A skewed column whose rare value is the one queried (`status = 'failed'` at 0.1%) is a legitimate target, as is the column as the leading equality column of a composite or as a partial-index predicate.
- Every index taxes writes - on write-heavy tables, recommending no index is a valid outcome (state it with the trade-off). That outcome wins over the FK rule unless a query or a parent-row delete or key update reads by the FK. Several new indexes on one table state their combined write cost once, in the last row's gap description. An index the database has but no migration creates is drift: assess it on its merits and add `absent from migrations` to its recommendation.
- Avoid duplicate or overlapping indexes - a composite `(a, b)` already covers single-column lookups on `a`.
- Always include lock risk when recommending any DDL (callers use it for migration planning). A replacement is two steps - build the new index, then drop the old - never one; a dedup lookup that must reject duplicates is a `UNIQUE` index, not a plain one.
- Engine version unknown: give the advice valid at the lowest version it depends on and name the version gate in the finding.

## Patterns

### Function on indexed column

```sql
-- Bad - function disables the index
WHERE created_at::date = '2024-01-01'
WHERE LOWER(email) = 'user@example.com'

-- Good - rewrite as range, or use an expression index
WHERE created_at >= '2024-01-01' AND created_at < '2024-01-02'
CREATE INDEX idx_users_email_lower ON users (LOWER(email));          -- PostgreSQL, SQLite 3.9+
CREATE INDEX idx_users_email_lower ON users ((LOWER(email)));        -- MySQL 8.0.13+ (double parentheses required)
```

On older MySQL or SQLite the rewrite is the only option, or store the normalized value in its own indexed column. For a timezone-aware column the range bounds are the day's instants in the intended zone, not naive dates.

### Composite column order

A composite index is traversed left-to-right. It is efficient only when the leading columns are constrained.

```sql
-- Index: (user_id, status)
-- Uses index:          WHERE user_id = ? AND status = ?
-- Uses index:          WHERE user_id = ?
-- Full index scan:     WHERE status = ?      <- non-leading column alone (PostgreSQL 17 and earlier walks the whole index, 18 adds skip scan; MySQL 8.0.13+ skip-scans only when the index covers the query)

-- Fix when that query is hot: a partial index on the rare status, or a composite led by status
```

### Equality, sort, then range

```sql
-- Query: WHERE status = 'active' AND created_at > '2024-01-01' ORDER BY created_at

-- Good - equality narrows, the sort column is also the range column
CREATE INDEX idx_users_status_created ON users (status, created_at);

-- Bad - range first prevents the skip to equality
CREATE INDEX idx_users_created_status ON users (created_at, status);
```

### Covering index (INCLUDE)

Includes non-key columns in the leaf, enabling index-only scans without table lookup.

```sql
-- Query: SELECT email, name FROM users WHERE status = 'active'
CREATE INDEX idx_users_status_covering ON users (status) INCLUDE (email, name);
```

Use for high-frequency read queries where the heap lookup is the bottleneck. `INCLUDE` is supported on PostgreSQL 11+ (B-tree; GiST from 12, SP-GiST from 14; not GIN, hash, or BRIN) and SQL Server 2005+; MySQL and SQLite have no `INCLUDE` - append the columns to the key instead. On PostgreSQL an index-only scan still visits the heap for pages not marked all-visible, so a frequently updated table gains little until `VACUUM` has run.

### Partial index (WHERE on index)

Indexes only rows matching a predicate - smaller index, lower write overhead.

```sql
-- Hot subset
CREATE INDEX idx_orders_pending ON orders (created_at) WHERE status = 'pending';

-- Soft-delete pattern
CREATE INDEX idx_users_active ON users (email) WHERE deleted_at IS NULL;
```

The query's WHERE must match or be a subset of the index's WHERE, and the planner must see the predicate value: a parameterized `status = $1` under a PostgreSQL generic plan or a SQL Server parameter (without `OPTION (RECOMPILE)`) cannot prove it matches the filter and skips the index - the ORM's emitted SQL decides, not the source. Supported on PostgreSQL, SQLite 3.8+, and SQL Server 2008+ (filtered indexes); MySQL has none - use a composite with the predicate column leading instead. When both a composite and a partial index fit, prefer the composite unless the filtered subset is small and the predicate value is stable.

### Write-heavy and append-only tables

Each secondary index amplifies every insert (extra page writes and log records; on MySQL 8.0 InnoDB's change buffer softens this for non-unique secondaries - 8.4 defaults `innodb_change_buffering` to `none`). When ingest rate dominates:

- Prefer a partial index when reads target a hot subset.
- PostgreSQL append-only time ranges: BRIN is orders of magnitude smaller than B-tree.

```sql
CREATE INDEX idx_events_recorded_brin ON events USING BRIN (recorded_at);
```

### Diagnosing "index exists but query scans"

Check, in order:

- Function applied to the indexed column
- Composite column order does not match WHERE predicates
- Low selectivity - the predicate returns a large fraction of the table (PostgreSQL typically switches to a sequential scan above roughly 5-10% of rows; the crossover is a cost estimate, not a fixed number)
- Stale planner statistics - PostgreSQL/SQLite `ANALYZE <table>`, MySQL `ANALYZE TABLE <table>`, SQL Server `UPDATE STATISTICS <table>`
- Index type mismatch - containment or key-existence queries on `jsonb` or array columns need PostgreSQL GIN (a `json` column has no GIN operator class: convert it or index an expression); MySQL uses multi-valued indexes (8.0.17+) or indexed generated columns, SQL Server an indexed computed column over `JSON_VALUE` (`PERSISTED` only when the expression is imprecise)
- Partial index WHERE does not match the query's filter
- Planner settings - a session or server cost setting steers away from the index (PostgreSQL `random_page_cost` tuned for spinning disks, `enable_indexscan` / `enable_bitmapscan` set `off`; MySQL `optimizer_switch`)

## Output Format

Consuming workflows parse this structure. Modes set the row shapes, and one assessment uses every shape its inputs call for (an audit that finds an index existing but unused by its query writes that row in the diagnosis shape):

- Reviewing a diff: problematic indexes the diff adds go under `Existing Index Issues` (a diff-added index whose own build is High has reason `blocking build`, and its Lock risk slot states the corrected statement's risk; an index that also carries any other reason takes that reason and names the blocking build in its recommendation), gaps the diff leaves under `Missing Indexes`; `Indexes Not Recommended` appears only when an index that was proposed or considered is declined.
- Audit mode (an existing schema, no diff): every index on the tables in scope is an `Existing Index Issues` candidate (`over-indexed`, `low-cardinality`, `unused within the reviewed scope`, `duplicate`), every unserved query a `Missing Indexes` row.
- Design mode (new queries or tables to serve): `Missing Indexes` holds the proposed indexes, `Indexes Not Recommended` the declined ones, `Existing Index Issues` any existing index on a table the design touches that a proposal makes redundant or that the reading found ineffective.
- Diagnosis mode (an index exists but the query scans): the defective index is an `Existing Index Issues` row with reason `ineffective`, the corrective index or rewrite is a `Missing Indexes` row (its `Recommended index` slot holds the rewrite when no index can fix it), and a non-index remedy is an `Existing Index Issues` row anchored on the table with reason `stale statistics` or `planner settings`.

```
## Database Indexing Assessment

**Engine:** {database / version | database (version unknown) | unknown}

### Missing Indexes                              {when at least one entry}

- [Severity: High | Medium | Low] {table.column(s)} - {gap description}{ (unverified - <confirm with EXPLAIN | callers outside the reviewed files | both>)}
  - Query pattern: {WHERE / JOIN / ORDER BY needing the index}
  - Recommended index: {CREATE INDEX statement, ORM equivalent, or the query rewrite when no index can fix it}
  - Lock risk: {None - no DDL (a rewrite, a statistics refresh), or an index on a table the same diff creates | Low - online build (PostgreSQL CONCURRENTLY, outside any transaction block - `backend-db-migration` names each migration tool's opt-out; InnoDB plain secondary index, the default ALGORITHM=INPLACE, LOCK=NONE; SQL Server ONLINE=ON, Enterprise edition) | High - blocking DDL (plain CREATE INDEX on PostgreSQL, SQL Server, or SQLite; plain DROP INDEX on a busy PostgreSQL table; MySQL functional (including multi-valued), FULLTEXT, or SPATIAL index; SQL Server online build unavailable on the edition)}

### Existing Index Issues                        {when at least one entry}

- [Severity: High | Medium | Low] {table.index_name, or table (statistics) or table (planner)} - {over-indexed | low-cardinality | unused within the reviewed scope | duplicate | ineffective (wrong column order, type mismatch, unmatchable predicate) | stale statistics | planner settings | blocking build} - {recommendation}{ (unverified - <confirm with EXPLAIN | callers outside the reviewed files | both>)}
  - Lock risk: {as above; a DROP INDEX is Low (PostgreSQL: `DROP INDEX CONCURRENTLY`); dropping a constraint-backed index is `ALTER TABLE ... DROP CONSTRAINT`, High on a busy PostgreSQL table; a rewrite-only fix, a statistics refresh, or keeping the index unchanged is None}

### Indexes Not Recommended                      {when an index proposed or considered is declined}

- {table.column(s)} - {why the index costs more than it returns, and what to do instead}{ (unverified - confirm with EXPLAIN)}

### No Issues Found                              {instead of all sections above, when none has an entry: one sentence stating indexing is adequate}
```

**Severity:**

- **High**: missing index on a request-path query, an incident-causing query, or a JOIN/FK column on a table above ~1M rows; a blocking `CREATE INDEX` shipped against a large live table
- **Medium**: missing composite causing a partial scan on a background or reporting path; a duplicate index the diff adds
- **Low**: a pre-existing low-cardinality, duplicate, over-indexed, or unused index with write cost and no read benefit

When table size is unknown, the query's role decides between High and Medium - role wins over size. An `ineffective`, `stale statistics`, or `planner settings` row takes the severity of the query it degrades: High on a request path or as an incident cause, Medium on a background path. A `blocking build` row is High when the table is live and large or of unknown size, Medium when it is known small; every other diff-added `Existing Index Issues` row is Medium, raised to High when its own build is blocking against a live table that is large or of unknown size.

Lock risk is mandatory on every DDL recommendation. A plain `CREATE INDEX` blocks writes for the whole build on PostgreSQL, SQL Server, and SQLite at any table size; InnoDB builds a plain secondary index online by default, while a functional (including multi-valued), FULLTEXT, or SPATIAL index blocks writes. An index on a table the same diff creates is Lock risk None and keeps the plain `CREATE INDEX`. `unused within the reviewed scope` is a claim about the reviewed scope only - carry the `callers outside the reviewed files` suffix when the review did not cover every caller.

## Avoid

- Using `SELECT *` and expecting a covering index to help - covering only works for the listed columns
