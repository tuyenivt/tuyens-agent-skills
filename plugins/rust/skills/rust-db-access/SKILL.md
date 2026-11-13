---
name: rust-db-access
description: "Rust sqlx data access: query! offline checks, PgPool sizing, transactions, locking, upserts, keyset paging, streaming, consumer-side traits."
metadata:
  category: backend
  tags: [rust, sqlx, postgresql, database, connection-pool, repository]
user-invocable: false
---

# Rust Data Access (sqlx)

> Load `Use skill: stack-detect` first. This skill reads `Database`; on `unknown` the sqlx feature list in the crate's `Cargo.toml` (`postgres`, `mysql`, `sqlite`) names the engine. The Rust version is `rust-version` in the crate's `Cargo.toml` (else the `rust-toolchain.toml` channel; a `## Tech Stack` `Language:` line may carry a version, and the manifest wins when they differ). In a Cargo workspace the crate under review decides: its own `[dependencies]` (or the `[workspace.dependencies]` entries it inherits) in place of the detected values. A form that needs a newer toolchain or crate than the manifest pins is written in its older equivalent. The SQL here is PostgreSQL (`$1`, `ON CONFLICT`, `RETURNING`, `= ANY($1)`, `UNNEST`, `FOR UPDATE SKIP LOCKED`); on MySQL use `?`, `ON DUPLICATE KEY UPDATE`, `last_insert_id()` in place of `RETURNING`, and an expanded `IN (...)` built with `QueryBuilder::push_bind`; on `unknown` or any other engine, keep the PostgreSQL form. A pattern below with no MySQL form (`RETURNING`, `UNNEST`, partial or `CONCURRENTLY` indexes) is emitted marked `PostgreSQL-only`. Baseline: Rust 1.94+ (edition 2024), sqlx 0.9 (`&mut *tx` as executor; runtime `query*()` take `impl SqlSafeStr` - a `&'static str` or an explicit `AssertSqlSafe(..)`), PgBouncer 1.21+.

## When to Use

- Designing the data access layer for a new Rust service
- Reviewing sqlx usage for injection, N+1, missing transactions, pool misconfiguration
- Choosing between the checked macros, runtime `query_as`, and `QueryBuilder`
- Debugging `PoolTimedOut`, slow queries, or offline query metadata drift

## Rules

- Static SQL uses `query!` / `query_as!` (checked against `DATABASE_URL` at build time, or the committed `.sqlx/` from `cargo sqlx prepare` under `SQLX_OFFLINE=true`); CI runs `cargo sqlx prepare --check` (`--workspace` in a workspace) so the cache cannot drift from the queries
- Bind every value (`$1`, `push_bind`). `format!` into SQL is injection; a column or direction that must be dynamic comes from an allowlist `match`, never the request
- Build `PgPool` once at startup with explicit `max_connections` and `acquire_timeout` (defaults: 10 connections, 30s wait - the wait turns pool exhaustion into latency instead of an error), and share it through `AppState`
- Every query has a server-side bound: `statement_timeout` per role or connection, `SET LOCAL` per transaction
- A multi-statement write is one transaction: `pool.begin()`, `&mut *tx` as the executor, `tx.commit()`. A `Transaction` dropped without `commit` rolls back, so every `?` in between is a rollback. Side effects that leave the database happen after commit, never inside
- Repository functions take `&mut PgConnection`, so one implementation serves the pool (`&mut *pool.acquire().await?`) and an open transaction (`&mut *tx`); a function running several queries reborrows `&mut *conn` per query
- Repository traits live in the consumer (service) module. Driver errors stop at the repository: `RowNotFound`, unique and foreign-key violations map to domain variants there
- `fetch_all` on an unbounded result sizes memory by the table - page, batch or stream it
- Pagination pairs `LIMIT` with a deterministic `ORDER BY` ending on a unique column; prefer keyset over large offsets

## Query Form

| Scenario | Use |
|----------|-----|
| Fixed SQL, typed result | `query_as!(T, ...)` |
| Fixed SQL, scalar or ad-hoc columns | `query!` / `query_scalar!` |
| SQL assembled at runtime (optional filters, sort allowlist) | `QueryBuilder` + `query_as::<_, T>` with `#[derive(FromRow)]` |
| Bulk insert | `UNNEST` arrays in one `query!` |

The macros infer nullability from the schema: a column of an outer join or an aggregate comes back `Option<T>`. Override in the alias - `count(*) AS "total!"` (non-null), `o.note AS "note?"` (nullable), `status AS "status: OrderStatus"` (a `sqlx::Type` enum).

## Patterns

### Consumer-defined Repository Trait

```rust
// service/payment.rs - the trait lives with its caller
use async_trait::async_trait;
use sqlx::PgConnection;
use crate::domain::{NewPayment, Payment, PaymentId};

#[derive(Debug, thiserror::Error)]
pub enum StoreError {
    #[error("not found")] NotFound,
    #[error("conflict on {0}")] Conflict(String),
    #[error("storage failure")] Storage(#[source] sqlx::Error),
}

#[async_trait] // held as Arc<dyn PaymentStore>: native async fn in a trait is not dyn-compatible
pub trait PaymentStore: Send + Sync {
    async fn find(&self, conn: &mut PgConnection, id: PaymentId) -> Result<Option<Payment>, StoreError>;
    async fn create_idempotent(&self, conn: &mut PgConnection, p: &NewPayment) -> Result<Payment, StoreError>;
}
```

Map at the repository: `fetch_optional` for a lookup whose absence is normal; `sqlx::Error::Database(db) if db.is_unique_violation()` -> `Conflict(db.constraint().unwrap_or_default().into())`; anything else -> `Storage`. A blanket `#[from] sqlx::Error` lets every `?` turn a `RowNotFound` or a 23505 into a 500.

### N+1 Prevention

```rust
// Bad: 1 + N round trips
for u in &users {
    let orders = sqlx::query_as!(Order, "SELECT id, user_id, total FROM orders WHERE user_id = $1", u.id)
        .fetch_all(&pool).await?;
}

// Good: one query, grouped in memory
let ids: Vec<i64> = users.iter().map(|u| u.id).collect();
let orders = sqlx::query_as!(Order, "SELECT id, user_id, total FROM orders WHERE user_id = ANY($1)", &ids[..])
    .fetch_all(&pool).await?;
```

To filter parents by a child, use `WHERE EXISTS (SELECT 1 FROM orders o WHERE o.user_id = u.id AND ...)` - a plain `JOIN` onto a has-many returns one parent row per matching child.

### Transactions

```rust
use sqlx::{PgConnection, PgPool};
use crate::{domain::{NewRefund, RefundId}, outbox, service::payment::StoreError};

pub async fn create_refund(pool: &PgPool, r: &NewRefund) -> Result<RefundId, StoreError> {
    let mut tx = pool.begin().await.map_err(StoreError::Storage)?;
    sqlx::query!("SET LOCAL statement_timeout = '2s'").execute(&mut *tx).await.map_err(StoreError::Storage)?;
    let id = refunds::insert(&mut tx, r).await?;            // &mut Transaction derefs to &mut PgConnection
    outbox::enqueue(&mut tx, "refund.created", id).await?; // same transaction: atomic with the insert
    tx.commit().await.map_err(StoreError::Storage)?;        // an early `?` above dropped tx: rolled back
    Ok(id)
}

mod refunds {
    use super::*;
    pub async fn insert(conn: &mut PgConnection, r: &NewRefund) -> Result<RefundId, StoreError> {
        sqlx::query_scalar!(r#"INSERT INTO refunds (order_id, amount) VALUES ($1, $2) RETURNING id AS "id: RefundId""#,
            r.order_id, r.amount)
            .fetch_one(&mut *conn).await.map_err(StoreError::Storage)
    }
}
```

`RefundId` is a `#[sqlx(transparent)]` newtype. When the service must own a boundary spanning repositories it does not know about, it passes `&mut tx` to each - repositories stay ignorant of each other while the write stays atomic.

#### Post-commit dispatch

Side effects that leave the database - a queue publish, an HTTP call, a mailer, a cache invalidation - run after `commit()` returns `Ok`. Inside the transaction a consumer can read before commit, and a rollback leaves the message pointing at a row that never existed. A crash between commit and publish drops the dispatch; if that is unacceptable, use the outbox.

#### Transactional outbox

Insert an `outbox_messages` row inside the writing transaction; a relay claims rows and publishes (publishing and idempotent consumers: `rust-messaging-patterns`):

```sql
-- claim = mark in one statement; the row lock lasts only for the claiming transaction
UPDATE outbox_messages SET status = 'processing', claimed_at = NOW()
WHERE id IN (
    SELECT id FROM outbox_messages
    WHERE status = 'pending' OR (status = 'processing' AND claimed_at < NOW() - INTERVAL '5 minutes')
    ORDER BY id LIMIT $1
    FOR UPDATE SKIP LOCKED
) RETURNING id, topic, payload
```

A bare `SELECT ... WHERE status = 'pending'` followed by a separate update double-publishes once the relay runs two replicas. The `claimed_at` clause is the lease: a relay that dies mid-publish returns its rows after the interval. MySQL has no `RETURNING` and rejects `LIMIT` inside an `IN` subquery: claim in one short transaction (`SELECT id ... ORDER BY id LIMIT ? FOR UPDATE SKIP LOCKED`, 8.0+, then `UPDATE ... WHERE id IN (...)`, commit) and publish from the selected rows.

#### Two commits around an external call

A write that must bracket a provider call (insert `pending` -> call the provider -> mark `succeeded`) is two short transactions, never one held across the call. A crash between them leaves a `pending` row; a sweep resolves rows older than the call's timeout by looking the operation up at the provider under the idempotency key you sent - never by re-sending blind.

#### Long-running transactions

A transaction held across an HTTP call, a publish or a slow `.await` pins a pool connection and holds its locks for the round trip; with no client timeout the hold is unbounded. Symptoms: `PoolTimedOut`, lock waits, deadlocks. Fetch first, then open a short transaction. An `.await` on a non-database future between `begin` and `commit` is the thing to look for.

#### Locking

```rust
let mut tx = pool.begin().await?;
let acct = sqlx::query_as!(Account, "SELECT id, balance, version FROM accounts WHERE id = $1 FOR UPDATE", id)
    .fetch_one(&mut *tx).await?;
sqlx::query!("UPDATE accounts SET balance = $1 WHERE id = $2", acct.balance + amount, id)
    .execute(&mut *tx).await?;
tx.commit().await?;
```

`FOR UPDATE` holds only for the enclosing transaction - against `&pool` the lock releases with the `SELECT` and the update runs unprotected. When the invariant spans child rows (refunds must not exceed the captured amount), lock the **parent** row and compute the sum in the same transaction; a `CHECK` cannot express a cross-row sum.

Optimistic, when conflicts are rare and a retry is cheap: `UPDATE ... SET balance = $1, version = version + 1 WHERE id = $2 AND version = $3`, and `rows_affected() == 0` is a stale read the caller re-reads and retries. Pessimistic when many writers contend on one row - optimistic retry livelocks there. A `tokio::sync::Mutex` is not a substitute: it serializes one replica only.

**Lock ordering.** A transaction taking two row locks takes them in primary-key order (`WHERE id = ANY($1) ORDER BY id FOR UPDATE`); two transfers locking A and B in opposite orders deadlock.

**Savepoints.** `use sqlx::Acquire;` then `let mut sp = tx.begin().await?;` opens a `SAVEPOINT`; dropping `sp` uncommitted rolls back to it and the outer transaction survives. Most "keep going on partial failure" cases are better as two top-level transactions.

### Idempotent Upsert

```rust
let inserted = sqlx::query_as!(Payment,
    r#"INSERT INTO payments (merchant_id, idempotency_key, body_hash, amount)
       VALUES ($1, $2, $3, $4)
       ON CONFLICT (merchant_id, idempotency_key) DO NOTHING
       RETURNING id, merchant_id, idempotency_key, body_hash, amount"#,
    p.merchant_id, p.idempotency_key, p.body_hash, p.amount)
    .fetch_optional(&mut *conn).await.map_err(StoreError::Storage)?;
let payment = match inserted {
    Some(row) => row,
    None => { // conflict: RETURNING yields no row
        let existing = sqlx::query_as!(Payment,
            "SELECT id, merchant_id, idempotency_key, body_hash, amount FROM payments
             WHERE merchant_id = $1 AND idempotency_key = $2", p.merchant_id, p.idempotency_key)
            .fetch_one(&mut *conn).await.map_err(StoreError::Storage)?;
        if existing.body_hash != p.body_hash { return Err(StoreError::Conflict("idempotency_key".into())); } // 409
        existing
    }
};
```

The `ON CONFLICT` target names the unique index's columns exactly, or PostgreSQL rejects the statement. The key is client-supplied and scoped to the principal (unique index on `(merchant_id, idempotency_key)`), stored with a hash of the request body.

### Dynamic SQL

```rust
use sqlx::{Postgres, QueryBuilder};

let order_col = match q.sort.as_deref() { // allowlist - the request never reaches the SQL text
    Some("amount") => "amount",
    _ => "created_at",
};
let mut qb = QueryBuilder::<Postgres>::new("SELECT id, amount, created_at FROM payments WHERE merchant_id = ");
qb.push_bind(merchant_id);
if let Some(s) = &q.status { qb.push(" AND status = ").push_bind(s); }
qb.push(format_args!(" ORDER BY {order_col} DESC, id DESC LIMIT ")).push_bind(limit);
let rows: Vec<PaymentRow> = qb.build_query_as().fetch_all(&pool).await?;
```

`push` writes SQL text and `push_bind` a placeholder: a request value passed to `push` is injection. `LIKE` binds the pattern as a value (`push_bind(format!("%{}%", escaped))`) after escaping `%` and `_`.

### List with Count

Offset paging costs two scans that both grow with the table: `OFFSET n` produces and discards n rows, and `count(*)` aggregates the whole filtered set on every page. Fine on a bounded table; on a growing one, use keyset.

### Keyset Pagination

```rust
// next page; the first page is the same query without the row-value predicate
let rows = sqlx::query_as!(Order,
    "SELECT id, created_at, total FROM orders
     WHERE merchant_id = $1 AND (created_at, id) < ($2, $3)
     ORDER BY created_at DESC, id DESC LIMIT $4",
    merchant_id, cur.created_at, cur.id, limit + 1)
    .fetch_all(&pool).await?;
```

One query with `$2 IS NULL OR (created_at, id) < ...` also works, but can lose the index once PostgreSQL switches sqlx's prepared statement to a generic plan. Backed by an index on `(merchant_id, created_at, id)` - equality columns first. Fetch `limit + 1` to derive `has_more`. Keyset has no page numbers and no total; if a count is needed, serve an estimate (`reltuples`) or a cached rollup. Sign or opaquely encode the cursor and re-apply the principal scope - its contents land in a `WHERE` clause. MySQL's optimizer wants the expanded `created_at < ? OR (created_at = ? AND id < ?)`.

### Streaming Large Reads

```rust
use futures::TryStreamExt;

let mut rows = sqlx::query_as!(User, "SELECT id, email FROM users WHERE status = 'pending'").fetch(&pool);
while let Some(user) = rows.try_next().await? {
    export(&user).await?;
}
```

A stream pins its connection until exhausted or dropped - a slow `export` per row holds it for the whole run. Run long exports on a dedicated pool, or page by primary key in batches.

### Bulk Insert

```rust
sqlx::query!(
    "INSERT INTO items (order_id, sku, quantity) SELECT * FROM UNNEST($1::bigint[], $2::text[], $3::int[])",
    &order_ids[..], &skus[..], &quantities[..])
    .execute(&mut *tx).await?;
```

Three binds regardless of row count. `QueryBuilder::push_values` binds once per value and hits PostgreSQL's 65535-parameter cap at `65535 / columns` rows - chunk it.

### Indexing the Access Path

An index serves a query only when its column order matches: equality columns first, then the range or sort columns. A partial index (`WHERE deleted_at IS NULL`) matches a soft-delete filter every query carries. Build with `CREATE INDEX CONCURRENTLY` (see `rust-migration-safety`) and confirm with `EXPLAIN (ANALYZE, BUFFERS)` that the plan is an index scan. A missing index is cited at the query that needs it.

## Connection Pool

```rust
use std::time::Duration;
use sqlx::postgres::{PgConnectOptions, PgPoolOptions};

let opts: PgConnectOptions = cfg.database_url.parse()?;
let pool = PgPoolOptions::new()
    .max_connections(20)
    .acquire_timeout(Duration::from_secs(3))    // fail fast; a 30s default looks like an outage
    .max_lifetime(Duration::from_secs(30 * 60)) // recycle for failover
    .idle_timeout(Duration::from_secs(10 * 60))
    .connect_with(opts.options([("statement_timeout", "5s")])) // startup parameter
    .await?;
```

**Replica fan-in math.** `sum over binaries of ((replicas + maxSurge) * max_connections) < max_connections(server) - reserved`. Count api and worker binaries separately - a worker's pool tracks its concurrency, not the pod count - and size against `replicas + maxSurge`, when old and new pods hold pools at once; when the manifest is not supplied, assume `maxSurge` = 25% of replicas rounded up and mark the figure `(assumed)`. `min_connections` holds connections open on every replica even when idle and counts against the same budget.

When the arithmetic yields a per-replica limit too small for peak, the answer is fewer replicas or PgBouncer in **transaction** mode - never a pool sized over the budget. With PgBouncer the app pools size against `max_client_conn`, and the server side counts `default_pool_size + reserve_pool_size` per (database, user) pair against `max_connections`. Transaction mode breaks session state: a `SET` (use `SET LOCAL`), session advisory locks, `LISTEN`, and the `options` startup parameter (PgBouncer rejects it, or silently drops it when listed in `ignore_startup_parameters`) - move `statement_timeout` to `ALTER ROLE ... SET`. sqlx caches named prepared statements per connection: they need PgBouncer 1.21+ with `max_prepared_statements` > 0, else `statement_cache_capacity(0)` on `PgConnectOptions`. `FOR UPDATE SKIP LOCKED` is transaction-scoped and safe.

Set `idle_in_transaction_session_timeout` server-side as containment for any transaction left holding a connection across external I/O.

## Edge Cases

- `fetch_one` returns `Err(RowNotFound)` on zero rows - use `fetch_optional` when absence is a value
- `.sqlx/` is keyed by query text: any SQL edit needs `cargo sqlx prepare`, or the offline build fails with no cached data for that query
- `query!` against a view or a function result marks every column nullable - override with `"col!"`
- `DELETE` / `UPDATE` return success on zero rows; check `rows_affected()` when the row must exist

## Output Format

Open the deliverable with one line above everything else, `**Engine:** {database | unknown}` - stack-detect's `Database` value as written, or the engine named by the reviewed crate's sqlx feature.

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design | `## Data Access Design` with `### Models`, `### Repository Interface`, `### Pool`; code for each decision follows the tables under `### <Decision>` headings, in the order the decision sentences list them. A design handed existing code that violates a Rule emits `## Findings` first. DDL belongs to `rust-migration-safety`; the dispatch mechanism's queue or topic to `rust-messaging-patterns` - name each in one sentence |
| Review | `## Findings`, then `## Data Access Design` describing the layer as it exists today |
| Debug | two opening lines `**Failing:**` and `**First fix:**`, then `## Findings`, then `## Data Access Design` as it exists today; a sizing question adds `### Sizing` under it: a table of the proposed budget with the columns Binary, Replicas (+surge), MaxConnections and Total, closed by a `PgBouncer: yes` or `PgBouncer: no` line with the reason |

```
## Data Access Design

### Models
| Struct | Table | Mapping | Soft Delete? |
|--------|-------|---------|--------------|

### Repository Interface
| Method | Query Form | Query Type |
|--------|------------|------------|

### Pool
| Binary | Setting | Value | Rationale |
|--------|---------|-------|-----------|
```

Cell values: on a review or debug every cell describes the code as written and the intended value goes in the finding's `Fix` (`### Sizing` alone holds the proposed budget); on a design the cells are the design. `Mapping` is `query_as! | FromRow | sqlx::Type | none`. `Soft Delete?` is `Yes | No | unknown` - `Yes` when the table carries a `deleted_at` that queries filter on, `unknown` when the schema was not supplied, never inferred from the table name; a struct the design does not own gets one row marked `(existing)`. `Query Form` is `query! | query_as! | query_scalar! | runtime query | QueryBuilder | format!`; `format!` is a string-built query and always carries a finding. `Query Type` is `PK lookup | Locking read | List | Keyset page | Aggregate | Stream | Write | Transactional write | Upsert | Claim | Tx boundary | n/a` - `PK lookup` covers any unique-key lookup, `Tx boundary` a method that opens a transaction for other repositories, `n/a` a non-query accessor; an unbounded read is `List` plus a `[Must]` finding. `Pool` holds one row per setting per binary - `Binary` is the process (`api`, `worker`), `server`, or `pgbouncer`; a setting that is never called is `not configured (default: <the sqlx default>)`, since the default is the value in force - `max_connections` 10, `min_connections` 0, `acquire_timeout` 30s, `idle_timeout` 10min, `max_lifetime` 30min. A server or proxy setting cites its source in `Rationale` as `<doc>:<setting>`. `Pool` includes the proxy and server settings the fan-in math depends on (`pool_mode`, `max_client_conn`, `default_pool_size`, `max_connections`) when one is in front of the database. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. When the design turns on a transaction boundary, a lock strategy, an index, or an event-dispatch mechanism, state each in a sentence under the tables - those decisions have no column and must not be dropped. `**Failing:**` names the symptom; `**First fix:**` names the one change that must land before the others work (re-sizing a pool is inert while transactions still hold connections across external I/O) - the rest follow in `## Findings` order.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what happens at runtime - wrong rows, pinned connection, unbounded memory, injectable query}
- Rule: {the data-access rule violated}
- Fix: {concrete edit}
```

Owned findings: `[Must]` for injectable SQL, a long-held connection or transaction, unconfigured or oversubscribed pool limits, a dual write across the transaction boundary, a driver error mapped to the wrong outcome (`RowNotFound` or 23505 as a 500), data loss or corruption, unbounded memory, or a query that returns the wrong rows (missing tenant scope, missing soft-delete filter, page overlap); `[Recommend]` for a violated `Rules` line whose consequence here is structural (a runtime query where the macro compiles, a trait in the repository module). Judge by consequence, not by matching the list. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not (code the input names but does not supply, or telemetry); a range is `file:start-end`. Order owned findings `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (task lifecycle, authorization, error-to-response mapping) is still reported, never dropped: one block per such defect after every owned finding, in that same order among themselves, labelled `[Must]` when it risks incorrect behaviour, data loss or a security hole and `[Recommend]` otherwise, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- `PgPoolOptions::new().connect(...)` with no limits or timeouts
- `format!` or `push` of a request value into SQL text
- Per-row queries in a loop
- A transaction held across HTTP calls, publishes, or other slow `.await`s
- `fetch_all` on an unbounded table
- `LIMIT` / `OFFSET` without a unique tiebreak in `ORDER BY`
- A blanket `#[from] sqlx::Error` with no prior mapping of `RowNotFound` and constraint violations
