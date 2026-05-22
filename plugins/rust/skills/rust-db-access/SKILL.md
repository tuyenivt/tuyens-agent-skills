---
name: rust-db-access
description: "Review Rust sqlx data access: compile-time query macros, pool sizing, transactions, N+1, pagination, streaming, statement timeouts."
metadata:
  category: backend
  tags: [rust, sqlx, diesel, postgresql, database, connection-pool]
user-invocable: false
---

# Rust Data Access

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing the data access layer (sqlx primary, diesel where DSL needed)
- Auditing queries for SQL injection, N+1, pool exhaustion, partial-write risk
- Sizing connection pools or diagnosing connection-related latency

## Rules

- Use `sqlx::query!` / `sqlx::query_as!` for static SQL (compile-time checked against schema). Reserve runtime `sqlx::query`/`query_as` for genuinely dynamic SQL.
- Parameterize every value with `$1`, `$2`. Never `format!` into a SQL string.
- Create the `PgPool` once at startup with explicit `PgPoolOptions` (max_connections, acquire_timeout, max_lifetime). Share via `Arc` or app state. Never construct per request.
- Wrap multi-statement mutations in `pool.begin()` + `tx.commit()`. Pass `&mut *tx` as the executor.
- Set a `statement_timeout` (per-pool via `after_connect` or per-tx via `SET LOCAL`) so a runaway query cannot pin a connection.
- For unbounded result sets, stream with `.fetch(executor)` instead of `.fetch_all`. For paginated UI, prefer keyset over offset.
- Commit `.sqlx/` (sqlx 0.7+ offline cache) when `DATABASE_URL` is unavailable at build time. Regenerate via `cargo sqlx prepare` after schema changes.

## When to Use sqlx vs diesel

| Scenario                                                | Use    |
| ------------------------------------------------------- | ------ |
| Static SQL, bulk ops, new project                       | sqlx   |
| Heavily composed query DSL, existing diesel codebase    | diesel |
| Simple PK lookups                                       | either |

## Patterns

### Pool setup (once, at startup)

```rust
let pool = PgPoolOptions::new()
    .max_connections(25)
    .min_connections(5)
    .acquire_timeout(Duration::from_secs(3))
    .max_lifetime(Some(Duration::from_secs(300)))  // survive LB / DB failover
    .after_connect(|conn, _| Box::pin(async move {
        sqlx::query("SET statement_timeout = '5s'").execute(conn).await?;
        Ok(())
    }))
    .connect(&database_url).await?;
```

Sizing: `max_connections` <= DB connection limit / (replicas + admin headroom). Start at 25, tune from observed `acquire_timeout` errors. `min_connections` ~20% of max.

### Compile-time checked query

```rust
// Bad: runtime query, string interpolation -> SQL injection
let q = format!("SELECT * FROM users WHERE name = '{name}'");
sqlx::query_as::<_, User>(&q).fetch_optional(pool).await?;

// Good: macro + parameterized
sqlx::query_as!(User, "SELECT id, name, email FROM users WHERE name = $1", name)
    .fetch_optional(pool).await?;
```

### Transaction for multi-step mutation

```rust
// Bad: two writes, no transaction -> partial state on failure
sqlx::query!("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amt, from)
    .execute(pool).await?;
sqlx::query!("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amt, to)
    .execute(pool).await?;

// Good: atomic with explicit isolation when contention matters
let mut tx = pool.begin().await?;
sqlx::query!("SET LOCAL statement_timeout = '2s'").execute(&mut *tx).await?;
sqlx::query!("UPDATE accounts SET balance = balance - $1 WHERE id = $2", amt, from)
    .execute(&mut *tx).await?;
sqlx::query!("UPDATE accounts SET balance = balance + $1 WHERE id = $2", amt, to)
    .execute(&mut *tx).await?;
tx.commit().await?;
```

Use `RETURNING *` with `fetch_one(&mut *tx)` to capture inserted/updated rows in the same round trip.

### N+1 elimination

```rust
// Bad: query inside loop
for u in &users {
    sqlx::query_as!(Order, "SELECT * FROM orders WHERE user_id = $1", u.id)
        .fetch_all(pool).await?;
}

// Good: single batched query
let ids: Vec<i64> = users.iter().map(|u| u.id).collect();
let orders = sqlx::query_as!(Order,
    "SELECT * FROM orders WHERE user_id = ANY($1)", &ids)
    .fetch_all(pool).await?;
```

### Pagination

```rust
// Offset (small lists only): drifts under concurrent inserts, slow on deep pages
"SELECT ... ORDER BY created_at DESC LIMIT $1 OFFSET $2"

// Keyset (preferred for large/active tables): stable, O(log n)
"SELECT ... WHERE (created_at, id) < ($1, $2) ORDER BY created_at DESC, id DESC LIMIT $3"
```

### Streaming for large result sets

```rust
use futures::TryStreamExt;

// Bad: fetch_all on an unbounded table -> OOM
let all = sqlx::query_as!(User, "SELECT * FROM users").fetch_all(pool).await?;

// Good: stream, process incrementally
let mut stream = sqlx::query_as!(User, "SELECT * FROM users").fetch(pool);
while let Some(user) = stream.try_next().await? {
    export(user).await?;
}
```

## Output Format

Emit one Finding per issue:

```
### Finding: <short title>
Category: {Injection | Pool | Transaction | N+1 | Pagination | Streaming | Timeout | Macro-Usage | Offline-Cache}
Severity: {Critical | High | Medium | Low}
Location: <file>:<line> or <function>
Issue: <one-line problem statement>
Fix: <concrete change, reference Pattern by name>
```

Conclude with:

```
Summary: <N> findings (<C> Critical, <H> High, <M> Medium, <L> Low)
Pool Config: {Configured | Defaults | NotFound}
Compile-Time Coverage: <queries using query!/query_as!> / <total queries>
```

If the project uses diesel, replace macro-coverage with `Schema Sync: {generated | manual | stale}`. If stack is non-Postgres (MySQL/SQLite), note dialect substitutions (`?` placeholders, no `ANY($1)`).

## Avoid

- `format!` / concatenation into SQL strings
- Constructing `PgPool` per request or per handler
- `PgPoolOptions::new().connect(...)` without limits or `max_lifetime`
- Per-row queries in loops - batch with `ANY($1)` or join
- `fetch_all` on tables that can grow without bound - stream instead
- Multi-statement mutations without `tx.begin()` / `tx.commit()`
- Runtime `query_as::<_, T>` for static SQL when the macro form would work
- Holding a transaction open across slow external I/O (HTTP, queue publish)
