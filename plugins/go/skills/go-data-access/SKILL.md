---
name: go-data-access
description: "Go data access with GORM and sqlx. Model definition, associations, preloading, transactions, scopes, connection pooling. When to use GORM vs sqlx. Both can coexist."
user-invocable: false
---

Cover:
GORM: struct tags, associations (BelongsTo, HasMany), Preload for N+1,
Joins for filtering, transactions, scopes, hooks (sparingly), connection pool
(SetMaxOpenConns, SetMaxIdleConns, SetConnMaxLifetime)
SQLX: named queries, scanning into structs, prepared statements, bulk operations
CHOOSING: GORM for CRUD/associations, sqlx for reporting/bulk/complex joins,
both share same \*sql.DB pool
Anti-patterns: ❌ AutoMigrate in prod, ❌ new connections per request,
❌ forgetting rows.Close, ❌ no pool limits
