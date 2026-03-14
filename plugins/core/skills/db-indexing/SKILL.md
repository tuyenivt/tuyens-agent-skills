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

**3. Diagnosing "index exists but query still scans"**

When an existing index is not being used, check for:
- Function applied to indexed column (see above)
- Low cardinality (DB optimizer chooses scan over index for < ~5% selectivity)
- Query planner statistics stale (run ANALYZE)
- Index column order doesn't match WHERE predicates (composite index pitfall)
- Index type mismatch (B-tree index on a JSON/array column requires GIN)

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

- Indexing all columns
- Indexes on low-cardinality data
- Missing indexes on WHERE clauses
