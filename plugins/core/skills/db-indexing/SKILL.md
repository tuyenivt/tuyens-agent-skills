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
