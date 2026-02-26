---
name: db-indexing
description: Database index strategy and query optimization
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

## Avoid

- Indexing all columns
- Indexes on low-cardinality data
- Missing indexes on WHERE clauses
