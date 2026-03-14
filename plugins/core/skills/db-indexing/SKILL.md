---
name: db-indexing
description: Database index strategy and query optimization - when to add indexes, composite index column ordering, covering indexes, partial indexes. Called by workflow skills - not for general SQL help.
metadata:
  category: performance
  tags: [database, indexing, queries, optimization]
user-invocable: false
---

# Database Indexing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Optimizing frequently executed queries
- Improving JOIN performance
- Speeding up search operations

## Rules

- Index foreign keys for JOIN performance
- Index search columns and filter conditions
- Index join condition columns
- Avoid over-indexing (increases write overhead)
- Avoid indexing low-cardinality columns
- Align indexes with actual query patterns
- Monitor slow queries regularly
- Review index usage periodically for maintenance

## Pattern

Bad - Missing indexes:

```sql
-- Slow query without indexes
SELECT u.* FROM users u
WHERE u.status = 'active' AND u.created_at > NOW() - INTERVAL '30 days'
```

Good - Indexed columns:

```sql
CREATE INDEX idx_users_status ON users(status);
CREATE INDEX idx_users_created ON users(created_at);
CREATE INDEX idx_users_status_created ON users(status, created_at);
```

### Common Index Pitfalls

**1. Function on indexed column kills the index**

Applying a function to an indexed column prevents the query planner from using the index:

```sql
-- BAD: function on column, index not used
WHERE created_at::date = '2024-01-01'
WHERE LOWER(email) = 'user@example.com'
WHERE DATE_TRUNC('day', created_at) = '2024-01-01'

-- GOOD: rewrite to avoid function, or use a functional/expression index
WHERE created_at >= '2024-01-01' AND created_at < '2024-01-02'
CREATE INDEX idx_users_email_lower ON users(LOWER(email));  -- expression index
```

**2. Composite index column ordering must match query predicates**

A composite index `(col_a, col_b)` is only used when `col_a` is in the WHERE clause. Querying on `col_b` alone does a full scan:

```sql
-- Index: (user_id, status)
-- Uses index: WHERE user_id = ? AND status = ?
-- Uses index (leading column only): WHERE user_id = ?
-- Does NOT use index (non-leading column): WHERE status = ?  <- full table scan

-- Fix: if queries filter on status alone, add a separate index on (status)
CREATE INDEX idx_orders_status ON orders(status);
```

**3. Equality columns before range columns in composite indexes**

When a query combines equality (`=`) and range (`>`, `<`, `BETWEEN`, `ORDER BY`) predicates, place equality columns first:

```sql
-- Query: WHERE status = 'active' AND created_at > '2024-01-01' ORDER BY created_at
-- GOOD: equality first, then range
CREATE INDEX idx_users_status_created ON users(status, created_at);
-- BAD: range first - cannot skip-scan to equality
CREATE INDEX idx_users_created_status ON users(created_at, status);
```

The index is traversed left-to-right. Equality columns narrow to exact nodes; range columns then scan within that subset.

**4. Covering indexes (INCLUDE clause)**

A covering index includes all columns a query needs, eliminating the table lookup (index-only scan):

```sql
-- Query: SELECT email, name FROM users WHERE status = 'active'
-- Without covering index: index scan on status -> table lookup for email, name
-- With covering index: index-only scan, no table lookup
CREATE INDEX idx_users_status_covering ON users(status) INCLUDE (email, name);
```

Use covering indexes for high-frequency read queries where the table lookup is the bottleneck. INCLUDE columns are stored in the index leaf pages but not used for key ordering, so they do not increase the index tree depth.

**Note:** `INCLUDE` is supported in PostgreSQL 11+, SQL Server 2005+, and MySQL 8.0.13+ (as functional equivalent via index extensions). For older versions, add columns to the index key instead.

**5. Partial indexes (WHERE clause on index)**

A partial index indexes only rows matching a condition, reducing index size and write overhead:

```sql
-- Only 5% of orders are 'pending', but queries filter on them constantly
CREATE INDEX idx_orders_pending ON orders(created_at) WHERE status = 'pending';

-- Only index non-deleted rows (soft-delete pattern)
CREATE INDEX idx_users_active ON users(email) WHERE deleted_at IS NULL;
```

Use partial indexes when queries consistently filter to a small subset of rows. The query's WHERE clause must match or be a subset of the index's WHERE clause for the planner to use it.

**Note:** Partial indexes are supported in PostgreSQL and SQLite. MySQL does not support partial indexes but offers prefix indexes as a partial alternative.

**6. Diagnosing "index exists but query still scans"**

When an existing index is not being used, check for:
- Function applied to indexed column (see above)
- Low cardinality (DB optimizer chooses scan over index for < ~5% selectivity)
- Query planner statistics stale (run ANALYZE)
- Index column order doesn't match WHERE predicates (composite index pitfall)
- Index type mismatch (B-tree index on a JSON/array column requires GIN)
- Partial index WHERE clause does not match query filter

## Output Format

Consuming workflow skills depend on this structure to surface index gaps and lock risks consistently.

```
## Database Indexing Assessment

### Missing Indexes

- [Severity: High | Medium | Low] {table.column(s)} - {description of gap}
  - Query pattern: {the WHERE / JOIN / ORDER BY that needs this index}
  - Recommended index: {CREATE INDEX statement or ORM equivalent}
  - Lock risk: {Low - additive online | Medium - large table, use CONCURRENTLY | High - blocks writes}

### Existing Index Issues

- {table.index_name} - {over-indexed / low-cardinality / unused} - {recommendation}

### No Issues Found

{State explicitly if indexing is adequate - do not omit this section silently}
```

**Severity guidance:**

- **High**: Missing index on a high-traffic query or foreign key on a large table
- **Medium**: Missing composite index causing partial scan on a moderate-traffic path
- **Low**: Low-cardinality index that adds write overhead with minimal read benefit

Always include Lock risk for every recommended index - callers use this for migration planning.

## Avoid

- Indexing every column (each index adds write overhead and storage)
- Indexes on low-cardinality columns (status with 3 values - optimizer prefers full scan)
- Missing indexes on foreign keys used in JOINs
- Duplicate or overlapping indexes (e.g., `(a)` and `(a, b)` - the composite covers single-column lookups on `a`)
- Indexes on frequently updated columns without measuring read vs write trade-off
- Leaving unused indexes in place (they consume write I/O and storage with zero benefit - check `pg_stat_user_indexes` or equivalent)
- Range column before equality column in composite indexes
- Using `SELECT *` and expecting covering indexes to help (they only help when selected columns are in the index)
