---
name: backend-db-indexing
description: Design and review database indexes - composite column ordering, covering indexes, partial indexes, expression indexes, query patterns.
metadata:
  category: performance
  tags: [database, indexing, queries, optimization]
user-invocable: false
---

# Database Indexing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Optimizing frequently executed queries
- Improving JOIN and ORDER BY performance
- Diagnosing why an index is not being used

## Rules

- Index foreign keys, JOIN columns, and frequent WHERE/ORDER BY predicates.
- Align indexes with actual query patterns - inspect EXPLAIN, not intuition. If EXPLAIN is unavailable, recommend from schema and query shape and mark each finding `(unverified - confirm with EXPLAIN)`.
- Composite indexes: equality columns first, range and ORDER BY columns last (matching the sort direction).
- Functions on indexed columns disable the index - rewrite the query or add an expression index.
- Avoid single-column indexes on low-cardinality columns (a few distinct values - optimizer prefers scan). The same column is fine as the leading equality column of a composite or as a partial-index predicate.
- Every index taxes writes - on write-heavy tables, recommending no index is a valid outcome (state it with the trade-off).
- Avoid duplicate or overlapping indexes - a composite `(a, b)` already covers single-column lookups on `a`.
- Always include lock risk when recommending a new index (callers use it for migration planning).

## Patterns

### Function on indexed column

```sql
-- Bad - function disables the index
WHERE created_at::date = '2024-01-01'
WHERE LOWER(email) = 'user@example.com'

-- Good - rewrite as range, or use an expression index
WHERE created_at >= '2024-01-01' AND created_at < '2024-01-02'
CREATE INDEX idx_users_email_lower ON users(LOWER(email));
```

### Composite column order

A composite index is traversed left-to-right. Only the leading column(s) can be used in isolation.

```sql
-- Index: (user_id, status)
-- Uses index:     WHERE user_id = ? AND status = ?
-- Uses index:     WHERE user_id = ?
-- Full scan:      WHERE status = ?      <- non-leading column alone

-- Fix: add a separate index on (status) if that query is hot
```

### Equality before range

```sql
-- Query: WHERE status = 'active' AND created_at > '2024-01-01' ORDER BY created_at

-- Good - equality narrows, range scans within
CREATE INDEX idx_users_status_created ON users(status, created_at);

-- Bad - range first prevents skip to equality
CREATE INDEX idx_users_created_status ON users(created_at, status);
```

### Covering index (INCLUDE)

Includes non-key columns in the leaf, enabling index-only scans without table lookup.

```sql
-- Query: SELECT email, name FROM users WHERE status = 'active'
CREATE INDEX idx_users_status_covering ON users(status) INCLUDE (email, name);
```

Use for high-frequency read queries where the heap lookup is the bottleneck. `INCLUDE` is supported on PostgreSQL 11+ and SQL Server 2005+. MySQL has no `INCLUDE` - append the columns to the key instead (works on any engine).

### Partial index (WHERE on index)

Indexes only rows matching a predicate - smaller index, lower write overhead.

```sql
-- Hot subset
CREATE INDEX idx_orders_pending ON orders(created_at) WHERE status = 'pending';

-- Soft-delete pattern
CREATE INDEX idx_users_active ON users(email) WHERE deleted_at IS NULL;
```

The query's WHERE must match or be a subset of the index's WHERE. Supported on PostgreSQL and SQLite; MySQL has no partial indexes - use a composite with the predicate column leading instead. When both a composite and a partial index fit, prefer the composite unless the filtered subset is small and the predicate value is stable.

### Write-heavy and append-only tables

Each secondary index amplifies every insert (extra page and WAL writes). When ingest rate dominates:

- Prefer a partial index when reads target a hot subset.
- PostgreSQL append-only time ranges: BRIN is orders of magnitude smaller than B-tree.

```sql
CREATE INDEX idx_events_recorded_brin ON events USING BRIN (recorded_at);
```

### Diagnosing "index exists but query scans"

Check, in order:

- Function applied to the indexed column
- Composite column order does not match WHERE predicates
- Low selectivity (planner picks scan under ~5%)
- Stale planner statistics - run `ANALYZE`
- Index type mismatch (B-tree on JSON / array needs GIN)
- Partial index WHERE does not match the query's filter

## Output Format

Consuming workflows parse this structure. When reviewing a diff, report problematic indexes the diff adds under `Existing Index Issues`.

```
## Database Indexing Assessment

### Missing Indexes

- [Severity: High | Medium | Low] {table.column(s)} - {gap description}
  - Query pattern: {WHERE / JOIN / ORDER BY needing the index}
  - Recommended index: {CREATE INDEX statement or ORM equivalent}
  - Lock risk: {Low - additive online | Medium - large table, use CONCURRENTLY | High - blocks writes}

### Existing Index Issues

- {table.index_name} - {over-indexed | low-cardinality | unused | duplicate} - {recommendation}

### No Issues Found

{State explicitly if indexing is adequate - do not omit this section silently}
```

**Severity:**

- **High**: Missing index on a high-traffic query or FK on a large table
- **Medium**: Missing composite causing partial scan on moderate-traffic path
- **Low**: Low-cardinality index with write cost and no read benefit

Lock risk is mandatory on every recommendation.

## Avoid

- Indexing every column - each index adds write and storage cost
- Leaving unused indexes in place (`pg_stat_user_indexes` or equivalent reveals them)
- Indexing frequently updated columns without measuring read vs write trade-off
- Using `SELECT *` and expecting a covering index to help - covering only works for the listed columns
