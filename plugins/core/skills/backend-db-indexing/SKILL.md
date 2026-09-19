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
- Align indexes with actual query patterns - inspect EXPLAIN, not intuition. Without EXPLAIN, recommend from schema and query shape and suffix each finding `(unverified - confirm with EXPLAIN)`. When traffic or table size is unknown, take severity from the query's role (request path or incident cause vs background path) under the same suffix; read a query's callers, inside the reviewed files or not, to settle its role.
- Composite column order: always-present equality columns first, then the ORDER BY columns, then range columns - a range column before the sort column breaks the index's ability to return rows pre-sorted. Key direction matters only when the ORDER BY mixes ASC and DESC (a uniform sort is served by a backward scan; MySQL honours `DESC` key parts from 8.0). An optional equality filter (`?status=`) never leads: it trails the sort column as an index filter, or gets a second index when its filtered path is hot.
- Functions on indexed columns disable the index - rewrite the query or add an expression index. Under a case-insensitive collation (MySQL `utf8mb4_0900_ai_ci`, SQL Server defaults) a `LOWER()` wrapper is unnecessary: drop it rather than index it.
- Avoid single-column indexes on evenly distributed low-cardinality columns (a few distinct values - the optimizer prefers a scan). A skewed column whose rare value is the one queried (`status = 'failed'` at 0.1%) is a legitimate target, as is the column as the leading equality column of a composite or as a partial-index predicate.
- Every index taxes writes - on write-heavy tables, recommending no index is a valid outcome (state it with the trade-off).
- Avoid duplicate or overlapping indexes - a composite `(a, b)` already covers single-column lookups on `a`.
- Always include lock risk when recommending any DDL (callers use it for migration planning).

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

Use for high-frequency read queries where the heap lookup is the bottleneck. `INCLUDE` is supported on PostgreSQL 11+ (B-tree; GiST from 12) and SQL Server 2005+; MySQL and SQLite have no `INCLUDE` - append the columns to the key instead. On PostgreSQL an index-only scan still visits the heap for pages not marked all-visible, so a frequently updated table gains little until `VACUUM` has run.

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

Each secondary index amplifies every insert (extra page writes and log records; InnoDB's change buffer softens this for non-unique secondaries). When ingest rate dominates:

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
- Index type mismatch - containment or key-existence queries on JSON/array columns need PostgreSQL GIN; MySQL uses multi-valued indexes (8.0.17+) or indexed generated columns, SQL Server a persisted computed column (native JSON indexes from SQL Server 2025)
- Partial index WHERE does not match the query's filter

## Output Format

Consuming workflows parse this structure. Modes:

- Reviewing a diff: problematic indexes the diff adds go under `Existing Index Issues`, gaps the diff leaves under `Missing Indexes`; `Indexes Not Recommended` appears only when an index that was proposed or considered is declined.
- Audit mode (an existing schema, no diff): every index on the tables in scope is an `Existing Index Issues` candidate (`over-indexed`, `unused`, `duplicate`), every unserved query a `Missing Indexes` row.
- Design mode (new queries or tables to serve): `Missing Indexes` holds the proposed indexes, `Indexes Not Recommended` the declined ones, `Existing Index Issues` any existing index on a table the design touches that a proposal makes redundant or that the reading found ineffective.
- Diagnosis mode (an index exists but the query scans): the defective index is an `Existing Index Issues` row with reason `ineffective`, the corrective index or rewrite is a `Missing Indexes` row (its `Recommended index` slot holds the rewrite when no index can fix it), and a non-index remedy is an `Existing Index Issues` row anchored on the table with reason `stale statistics` or `planner settings`.

```
## Database Indexing Assessment

**Engine:** {database / version | unknown}

### Missing Indexes                              {when at least one entry}

- [Severity: High | Medium | Low] {table.column(s)} - {gap description}{ (unverified - <confirm with EXPLAIN | callers outside the reviewed files | both>)}
  - Query pattern: {WHERE / JOIN / ORDER BY needing the index}
  - Recommended index: {CREATE INDEX statement, ORM equivalent, or the query rewrite when no index can fix it}
  - Lock risk: {None - no DDL (a rewrite, a statistics refresh) | Low - online build (PostgreSQL CONCURRENTLY; InnoDB, the default ALGORITHM=INPLACE, LOCK=NONE; SQL Server ONLINE=ON, Enterprise edition) | High - blocking build (plain CREATE INDEX on PostgreSQL, SQL Server, or SQLite; SQL Server online build unavailable on the edition)}

### Existing Index Issues                        {when at least one entry}

- [Severity: High | Medium | Low] {table.index_name, or table (statistics) or table (planner)} - {over-indexed | low-cardinality | unused within the reviewed scope | duplicate | ineffective (wrong column order, type mismatch, unmatchable predicate) | stale statistics | planner settings} - {recommendation}{ (unverified - <confirm with EXPLAIN | callers outside the reviewed files | both>)}
  - Lock risk: {as above; a DROP INDEX is Low, a rewrite-only fix or a statistics refresh is None}

### Indexes Not Recommended                      {when an index proposed or considered is declined}

- {table.column(s)} - {why the index costs more than it returns, and what to do instead}{ (unverified - confirm with EXPLAIN)}

### No Issues Found                              {instead of all sections above, when none has an entry: one sentence stating indexing is adequate}
```

**Severity:**

- **High**: missing index on a request-path query, an incident-causing query, or a JOIN/FK column on a table above ~1M rows; a blocking `CREATE INDEX` shipped against a large live table
- **Medium**: missing composite causing a partial scan on a background or reporting path; a duplicate index the diff adds
- **Low**: a pre-existing low-cardinality, duplicate, over-indexed, or unused index with write cost and no read benefit

When table size is unknown, the query's role decides between High and Medium - role wins over size. An `ineffective`, `stale statistics`, or `planner settings` row takes the severity of the query it degrades: High on a request path or as an incident cause, Medium on a background path.

Lock risk is mandatory on every DDL recommendation. A plain `CREATE INDEX` blocks writes for the whole build on PostgreSQL, SQL Server, and SQLite at any table size; InnoDB takes the online path by default. `unused` is a claim about the reviewed scope only - carry the `callers outside the reviewed files` suffix when the review did not cover every caller.

## Avoid

- Indexing every column - each index adds write and storage cost
- Leaving unused indexes in place (`pg_stat_user_indexes` or equivalent reveals them)
- Indexing frequently updated columns without measuring read vs write trade-off
- Using `SELECT *` and expecting a covering index to help - covering only works for the listed columns
