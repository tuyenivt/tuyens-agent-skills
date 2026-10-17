---
name: go-data-access
description: "Go data access with GORM and sqlx: models, preloading, transactions, scopes, pool config, upserts, consumer-defined repository interfaces."
metadata:
  category: backend
  tags: [go, gorm, sqlx, database, postgresql, repository]
user-invocable: false
---

# Go Data Access

> Load `Use skill: stack-detect` first. This skill reads `Database`; the Go version is the `go` directive in `go.mod` (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). The SQL and driver-error forms here are PostgreSQL on pgx v5 (`$1`, `ON CONFLICT`, `RETURNING`, `FOR UPDATE SKIP LOCKED`, `*pgconn.PgError`); on MySQL use `?`, `ON DUPLICATE KEY UPDATE`, no `RETURNING`, `*mysql.MySQLError` (`Number` 1062 duplicate key); on `unknown` or any other engine (SQLite), keep the PostgreSQL form. A pattern below with no MySQL form (`RETURNING`, partial or `CONCURRENTLY` indexes, the `SKIP LOCKED` claim subquery, the row-value keyset compare, `reltuples`, `EXPLAIN (ANALYZE, BUFFERS)`) is emitted marked `PostgreSQL-only`. Baseline: Go 1.25+, GORM v1.25+ (a dialector implementing `gorm.ErrorTranslator`), sqlx v1.4+, pgx v5, PgBouncer 1.21+.

## When to Use

- Designing the data access layer for a new Go service
- Reviewing ORM usage for N+1, missing transactions, pool misconfiguration
- Choosing between GORM and sqlx for a specific query
- Debugging slow queries or connection exhaustion

## Rules

- Never `AutoMigrate` in production - use versioned migration files
- Always configure pool limits (`SetMaxOpenConns`, `SetConnMaxLifetime`); defaults are unbounded
- Always pass `ctx`: `db.WithContext(ctx)` for GORM, `*Context` variants for sqlx
- `defer rows.Close()` immediately after a successful query
- Transactions: prefer the closure form (`db.Transaction(func(tx) error { ... })`); side effects that leave the DB happen after commit, never inside
- N+1: `Preload` for associations you'll access; `Joins` to filter by a belongs-to / has-one, `EXISTS` to filter by a has-many
- Repository interfaces live in the consumer (service) package, never in the repo package. Driver and ORM error types stop at the repository; the service imports gorm only to own a transaction boundary - that is the one place a `*gorm.DB` legitimately appears above the repo layer
- Pagination: always pair `Limit`/`Offset` with a deterministic `Order`; prefer keyset over large offsets
- Bind every value as a placeholder (`?`, `$1`, `:name`). Interpolating with `fmt.Sprintf` is SQL injection; a column or direction name that must be dynamic comes from an allowlist, never from the request
- Reading an unbounded result set into a slice (`db.Find(&all)`) sizes memory by the table - batch or stream it
- Raw SQL bypasses GORM's soft-delete filter. That includes `db.Raw` / `db.Exec`, not just sqlx

## GORM vs sqlx

| Scenario                                      | Use    |
| --------------------------------------------- | ------ |
| CRUD with associations                        | GORM   |
| Reporting / complex joins / window functions  | sqlx   |
| Bulk insert                                   | sqlx   |
| Upsert, simple PK lookups                     | Either |

Both share a `*sql.DB` pool via `db.DB()`.

## Patterns

### Consumer-defined Repository Interface

```go
// service/payment.go - interface lives with the caller
type PaymentRepository interface {
    FindByID(ctx context.Context, id string) (*Payment, error)
    CreateIdempotent(ctx context.Context, p *Payment) (*Payment, error)
    List(ctx context.Context, limit, offset int) ([]Payment, int64, error)
}

// repository/payment.go
type paymentRepo struct{ db *gorm.DB }
func NewPaymentRepository(db *gorm.DB) *paymentRepo { return &paymentRepo{db: db} }
```

Map driver errors at the repo boundary: `errors.Is(err, gorm.ErrRecordNotFound)` (or `sql.ErrNoRows`) -> return a domain sentinel (`ErrPaymentNotFound`) so services never see gorm or database/sql error types. On a not-found path return `nil, err`, never `&zero, err` - a non-nil pointer to an empty struct misleads every `== nil` check upstream.

### Model

```go
type User struct {
    gorm.Model // ID, CreatedAt, UpdatedAt, DeletedAt (soft delete; queries auto-filter, use Unscoped() for hard delete)
    Name   string  `gorm:"not null"`
    Email  string  `gorm:"uniqueIndex;not null"`
    Orders []Order `gorm:"foreignKey:UserID"`
}
```

### N+1 Prevention

```go
// Bad: 1 + N queries
db.Find(&users)
for i := range users { db.Where("user_id = ?", users[i].ID).Find(&users[i].Orders) }

// Good: Preload (two queries via IN)
db.Preload("Orders").Find(&users)

// Good: filter by a has-many without duplicating parents - EXISTS, not a bare JOIN
db.Where("EXISTS (SELECT 1 FROM orders WHERE orders.user_id = users.id AND orders.total > ?)", 100).
    Preload("Orders").Find(&users)
```

A plain `JOIN` onto a has-many returns one parent row per matching child; use it only with `Distinct()` or for belongs-to / has-one.

### Transactions

Use the closure form - it commits on `return nil`, rolls back on non-nil return or panic, and avoids the connection leak that a `db.Begin()` without a deferred `Rollback` rots into.

```go
return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(order).Error; err != nil {
        return fmt.Errorf("create order: %w", err)
    }
    for i := range items { items[i].OrderID = order.ID }
    if err := tx.Create(&items).Error; err != nil {
        return fmt.Errorf("create items: %w", err)
    }
    return nil // commit
})
```

#### Service-level transactions across repositories

When the unit of work spans repositories, expose `WithTx` so the service owns the transaction and repositories accept the `*gorm.DB` bound to it:

```go
type RefundRepository interface {
    WithTx(tx *gorm.DB) RefundRepository
    Create(ctx context.Context, r *Refund) error
}
type OutboxRepository interface {
    WithTx(tx *gorm.DB) OutboxRepository
    Enqueue(ctx context.Context, m *OutboxMessage) error
}

func (s *RefundService) Create(ctx context.Context, r *Refund) error {
    return s.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
        if err := s.refunds.WithTx(tx).Create(ctx, r); err != nil { return err }
        return s.outbox.WithTx(tx).Enqueue(ctx, outboxFor(r))
    })
}
```

This keeps repositories ignorant of each other while preserving atomicity. Avoid passing `*gorm.DB` as a method parameter on every call.

#### Post-commit dispatch (canonical)

Side effects that leave the database - Asynq enqueue, HTTP call, mailer, cache invalidation - happen **after** `Transaction(...)` returns nil. Enqueueing inside the tx races commit: a worker can read the row before commit completes, or rollback leaves the task referencing a non-existent row.

```go
// Bad - worker may run before commit; rollback orphans the task
return db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&order).Error; err != nil { return err }
    _, err := client.EnqueueContext(ctx, asynq.NewTask("order.notify", payload)) // client: *asynq.Client
    return err
})

// Good - dispatch after commit
var orderID int64
err := db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&order).Error; err != nil { return err }
    orderID = order.ID
    return nil
})
if err != nil { return err }
if _, err := client.EnqueueContext(ctx, asynq.NewTask("order.notify", payload)); err != nil {
    slog.ErrorContext(ctx, "post-commit enqueue failed", "order_id", orderID, "err", err)
}
```

GORM `AfterCreate` / `AfterUpdate` hooks fire **inside** the transaction - same hazard. Move side-effect calls into the calling service.

A process crash between commit and `Enqueue` drops the dispatch. If unacceptable, use the outbox below.

#### Transactional outbox

Insert an `outbox_messages` row inside the tx; a relay claims rows with `FOR UPDATE SKIP LOCKED` and dispatches. Handlers must be idempotent.

```go
// Inside the writing tx - the insert's error is the whole point; dropping it reopens the dual-write hole
if err := tx.Create(&OutboxMessage{Topic: "order.notify", Payload: payload, Status: "pending"}).Error; err != nil {
    return fmt.Errorf("outbox: %w", err)
}

// Relay (separate goroutine / process). The row lock lasts only for the claiming
// transaction, so claim = mark in one statement and publish from the returned rows.
const claim = `
    UPDATE outbox_messages SET status = 'processing', claimed_at = NOW()
    WHERE id IN (
        SELECT id FROM outbox_messages
        WHERE status = 'pending' OR (status = 'processing' AND claimed_at < NOW() - INTERVAL '5 minutes')
        ORDER BY id LIMIT $1
        FOR UPDATE SKIP LOCKED
    ) RETURNING *`
```

A bare `SELECT ... WHERE status = 'pending'` followed by a separate update double-publishes as soon as the relay runs two replicas. The `claimed_at` clause is the lease: a relay that dies mid-publish returns its rows after the interval.

#### Two commits around an external call

A write that must bracket a provider call (insert `pending` -> call Stripe -> mark `succeeded`) is two short transactions, never one held across the call. A crash between them leaves a `pending` row; a sweep resolves rows older than the call's timeout by looking the operation up at the provider under the idempotency key you sent - never by re-sending blind.

#### Long-running transactions (anti-pattern)

Holding a tx across user input, HTTP calls, or broker dispatch ties up a pool connection and lengthens lock windows. Symptoms: `too many connections`, lock waits, deadlocks. An external client with no timeout makes the hold unbounded.

```go
// Bad - external HTTP inside the tx
db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
    tx.Create(&order)
    resp, _ := http.Get(externalURL) // holds connection + locks for the round trip
    tx.Save(&resp)
    return nil
})

// Good - fetch first, then transact briefly
data, err := fetch(ctx, externalURL) // client has its own timeout
if err != nil { return err }
return db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
    return tx.Create(&Order{Payload: data}).Error
})
```

#### Locking

Pessimistic row lock when concurrent writers contend on the same row (counters, balances, inventory). `FOR UPDATE` holds only for the enclosing transaction - on bare `db` the lock releases after the SELECT and the `Save` runs unprotected:

```go
return db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
    if err := tx.Clauses(clause.Locking{Strength: "UPDATE"}).
        Where("id = ?", id).First(&account).Error; err != nil {
        return err
    }
    account.Balance += amount
    return tx.Save(&account).Error
})
```

When the invariant spans child rows (sum of refunds must not exceed the captured amount), lock the **parent** row `FOR UPDATE`, then compute the sum inside the same tx - the parent lock serializes every writer to that order, and a `CHECK` cannot express a cross-row sum.

Optimistic locking when contention is rare and retry on conflict is acceptable:

```go
type Account struct { ID int64; Balance int64; Version int }

res := db.WithContext(ctx).Model(&account).
    Where("id = ? AND version = ?", account.ID, account.Version).
    Updates(map[string]any{"balance": newBalance, "version": account.Version + 1})
if res.Error != nil { return res.Error }  // a failed UPDATE also reports 0 rows
if res.RowsAffected == 0 {
    return ErrStaleRead // caller re-reads and retries
}
```

`clause.Locking{Strength: "SHARE"}` for `FOR SHARE`. In-process `sync.Mutex` is **not** a substitute - it only serializes within one replica; multi-replica counters/balances require DB-level locking or optimistic versioning.

**Choosing:** pessimistic when the same row is contended by many concurrent writers (a balance, a counter, inventory) - optimistic retry livelocks there. Optimistic when conflicts are rare and a retry is cheap. A `version` column is compatible with both: hold the lock *and* guard the update on the version, so a write that escapes the lock fails loudly instead of silently.

**Lock ordering.** A transaction taking two row locks must take them in a deterministic order - sort by primary key. Two transfers touching accounts A and B in opposite orders deadlock; `Where("id IN ?", sortedIDs).Order("id")` under `FOR UPDATE` makes that impossible.

#### Savepoints (nested transactions)

GORM nested `Transaction(...)` calls become savepoints, letting an inner step fail without aborting the outer tx. Use sparingly - most "keep going on partial failure" cases are better as two top-level transactions plus retry.

```go
db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&order).Error; err != nil { return err }
    _ = tx.Transaction(func(tx *gorm.DB) error { // SAVEPOINT
        return tx.Create(&optionalAuditEntry).Error
    }) // outer survives inner failure
    return nil
})
```

#### `db.Begin()` fallback

If you must use `db.Begin()` (e.g., crossing a function boundary), `defer tx.Rollback()` immediately - `Rollback` after `Commit` is a no-op, but a missed path leaks the connection.

```go
tx := db.WithContext(ctx).Begin()
if tx.Error != nil { return tx.Error }
defer tx.Rollback() // safe to call after Commit

if err := tx.Create(&order).Error; err != nil { return err }
return tx.Commit().Error
```

### Idempotent Upsert

```go
func (r *paymentRepo) CreateIdempotent(ctx context.Context, p *Payment) (*Payment, error) {
    res := r.db.WithContext(ctx).
        Clauses(clause.OnConflict{
            Columns:   []clause.Column{{Name: "merchant_id"}, {Name: "idempotency_key"}}, // the unique index, exactly
            DoNothing: true,
        }).Create(p)
    if res.Error != nil {
        return nil, fmt.Errorf("createIdempotent: %w", res.Error)
    }
    if res.RowsAffected == 0 {
        var existing Payment
        if err := r.db.WithContext(ctx).
            Where("merchant_id = ? AND idempotency_key = ?", p.MerchantID, p.IdempotencyKey).First(&existing).Error; err != nil {
            return nil, fmt.Errorf("fetch existing: %w", err)
        }
        if existing.BodyHash != p.BodyHash { return nil, ErrIdempotencyConflict } // same key, different body: 409
        return &existing, nil
    }
    return p, nil
}
```

sqlx equivalent:

```sql
INSERT INTO payments (id, merchant_id, idempotency_key, body_hash, amount, status)
VALUES (:id, :merchant_id, :idempotency_key, :body_hash, :amount, :status)
ON CONFLICT (merchant_id, idempotency_key) DO NOTHING;
```

`DO NOTHING RETURNING *` returns **no row** on conflict - to mirror the GORM fetch-existing path, re-select by `(merchant_id, idempotency_key)` when zero rows return (or use a no-op `DO UPDATE SET idempotency_key = EXCLUDED.idempotency_key ... RETURNING *`, which locks the row). The `ON CONFLICT` target must name the unique index's columns exactly, or PostgreSQL rejects the statement.

Retryable endpoints (`POST /payments`) need a client-supplied idempotency key in the request, not a server-generated one. The key is scoped to the principal (unique index on `(merchant_id, idempotency_key)`) and stored with a hash of the request body: same key + same body returns the first result, same key + different body is a conflict error, never a second write.

### Scopes

```go
func ActiveUsers(db *gorm.DB) *gorm.DB { return db.Where("status = ?", "active") }
func PaginatedBy(page, size int, order string) func(*gorm.DB) *gorm.DB { // order from an allowlist, never the request
    return func(db *gorm.DB) *gorm.DB {
        return db.Order(order).Offset((page - 1) * size).Limit(size)
    }
}

db.WithContext(ctx).Scopes(ActiveUsers, PaginatedBy(2, 20, "created_at DESC, id DESC")).Find(&users)
```

### List with Count

```go
func (r *paymentRepo) List(ctx context.Context, limit, offset int) ([]Payment, int64, error) {
    var (payments []Payment; total int64)
    db := r.db.WithContext(ctx).Model(&Payment{}).Session(&gorm.Session{}) // Session: safe reuse after Count (a finisher)
    if err := db.Count(&total).Error; err != nil {
        return nil, 0, fmt.Errorf("count: %w", err)
    }
    if err := db.Order("created_at DESC, id DESC").Limit(limit).Offset(offset).Find(&payments).Error; err != nil {
        return nil, 0, fmt.Errorf("list: %w", err)
    }
    return payments, total, nil
}
```

`Limit`/`Offset` without `Order` returns rows in undefined order - page 2 may overlap page 1. Tiebreak on a unique column (`id`) when the primary sort can repeat.

Offset paging costs two scans that both grow with the table: `OFFSET n` produces and discards n rows, and `Count` aggregates the whole filtered set on every page. Both are fine on a bounded table and neither is on a growing one.

### Keyset Pagination

The cursor is every column in the `ORDER BY`, compared as a row value so one index descent serves page 5,000 as cheaply as page 1:

```go
q := db.WithContext(ctx).Model(&Order{}).Order("created_at DESC, id DESC").Limit(limit + 1)
if cur != nil { // row-value compare (PostgreSQL); MySQL's optimizer wants the expanded created_at < ? OR (created_at = ? AND id < ?)
    q = q.Where("(created_at, id) < (?, ?)", cur.CreatedAt, cur.ID)
}
```

Backed by an index on `(created_at, id)` with any equality filter (`merchant_id`) as the leading column; a btree is scanned backward for a `DESC` sort, so direction only matters when the sort mixes directions. Fetch `limit + 1` to derive `has_more` without a second query.

Keyset has no page numbers and no total - that is the trade, not an omission. Return `next_cursor` + `has_more`; if a count is genuinely needed, serve an estimate (`reltuples`; MySQL `information_schema.TABLES.TABLE_ROWS`) or a cached rollup rather than `COUNT(*)` per request. Sign or opaquely encode the cursor: its contents land in a `WHERE` clause.

### Streaming Large Reads

`Find(&all)` materializes every row before returning, so peak memory is the result set. Batch instead:

```go
err := db.WithContext(ctx).Where("status = ?", "pending").
    FindInBatches(&batch, 1000, func(tx *gorm.DB, _ int) error {
        return process(ctx, batch) // batch is reused between calls - do not retain it
    }).Error
```

`FindInBatches` advances by primary key, so it does not degrade the way an offset loop does. sqlx's `SelectContext` materializes too - stream with `QueryxContext` + `rows.StructScan` and `defer rows.Close()`.

### Indexing the Access Path

An index serves a query only when its column order matches: equality columns first, then the range or sort columns. A partial index (`WHERE deleted_at IS NULL`) matches the predicate GORM auto-appends for `gorm.Model` tables and keeps the index off dead rows. Build with `CREATE INDEX CONCURRENTLY` (see `go-migration-safety`), and confirm with `EXPLAIN (ANALYZE, BUFFERS)` (MySQL 8.0.18+: `EXPLAIN ANALYZE`) that the plan is an index scan rather than a seq scan plus sort. A missing index is cited at the query that needs it, not at the model.

### Hooks (Sparingly)

Hooks are invisible to callers. Use only for genuine cross-cutting concerns (audit fields, password hashing); prefer explicit service-layer logic for non-trivial operations. Never put outbound dispatch in a hook.

## sqlx Patterns

### Named Query + Struct Scan

```go
type OrderSummary struct {
    UserID     int     `db:"user_id"`
    OrderCount int     `db:"order_count"`
    TotalSpend float64 `db:"total_spend"`
}

const q = `SELECT u.id AS user_id, COUNT(o.id) AS order_count, SUM(o.total) AS total_spend
           FROM users u LEFT JOIN orders o ON o.user_id = u.id
           WHERE u.status = :status GROUP BY u.id HAVING SUM(o.total) > :min_spend`

rows, err := r.db.NamedQueryContext(ctx, q, map[string]any{"status": "active", "min_spend": minSpend})
if err != nil { return nil, fmt.Errorf("query: %w", err) }
defer rows.Close()

var results []OrderSummary
if err := sqlx.StructScan(rows, &results); err != nil {
    return nil, fmt.Errorf("scan: %w", err)
}
```

Nullable columns require pointer types or `sql.NullX` for scan.

### Top-N-per-group (window function)

GORM has no idiomatic shape for this; drop to sqlx:

```sql
SELECT * FROM (
  SELECT id, user_id, total,
         ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY total DESC) AS rn
  FROM orders
) t WHERE rn <= 3
```

### Bulk Insert

```go
_, err := r.db.NamedExecContext(ctx,
    `INSERT INTO items (order_id, sku, quantity) VALUES (:order_id, :sku, :quantity)`,
    items) // slice expansion; an empty slice errors
```

PostgreSQL caps a statement at 65535 bind parameters, so chunk at `65535 / columns` rows (about 21k for three columns).

### IN-Clause with Slices

Placeholders don't expand slices. Use `sqlx.In` + `Rebind`:

```go
q, args, err := sqlx.In(`SELECT * FROM orders WHERE id IN (?)`, ids)
if err != nil { return nil, fmt.Errorf("build query: %w", err) }
err = r.db.SelectContext(ctx, &orders, r.db.Rebind(q), args...)
```

### Dropping from GORM to sqlx

sqlx queries bypass GORM's `deleted_at IS NULL` filter. When the table uses `gorm.Model`, add `WHERE deleted_at IS NULL` to raw SQL explicitly, or you will return soft-deleted rows.

## Connection Pool

Configure immediately after open:

```go
sqlDB, err := db.DB()
if err != nil { return err }
sqlDB.SetMaxOpenConns(25)
sqlDB.SetMaxIdleConns(10)                  // starting point: ~40% of max open; tune by conn-churn vs memory
sqlDB.SetConnMaxLifetime(5 * time.Minute)  // recycle for LB failover
sqlDB.SetConnMaxIdleTime(1 * time.Minute)
```

**Replica fan-in math.** `sum over binaries of ((replicas + maxSurge) * SetMaxOpenConns) < DB max_connections - reserved`. Example: Postgres `max_connections=100`, reserve 10 for admin/migrations, 8 api replicas with `maxSurge: 2` and 4 workers -> the 90 slots split by need, say `api: (8 + 2) * 6 = 60`, `worker: (4 + 1) * 5 = 25` (worker surge assumed), 85 of 90. Count api and worker binaries separately - a worker's pool should track its concurrency, not the pod count - and size against the replica count during a rolling deploy (`replicas + maxSurge`), when old and new pods hold pools at once; when the manifest is not supplied, assume `maxSurge` = 25% of replicas rounded up and mark the figure `(assumed)`. When the budget holds the surge only at a per-replica limit too small for peak, the answer is PgBouncer or fewer replicas, never a pool sized over the budget.

When that arithmetic yields a per-replica limit too small to serve peak traffic, the answer is PgBouncer in **transaction** pooling mode, and the formula changes: the app pools now size against PgBouncer's `max_client_conn`, and the server side counts `default_pool_size + reserve_pool_size` per (database, user) pair, capped by `max_db_connections`, against `max_connections`. Session mode does not multiplex - it holds one server connection per client connection for that connection's whole life, so it is a pass-through and the fan-in math still binds. Transaction mode has prerequisites: session state stops working - audit for `SET` (use `SET LOCAL`), session advisory locks, and `LISTEN` (`NOTIFY` is delivered at commit and works). Protocol-level prepared statements need PgBouncer 1.21+ with `max_prepared_statements` > 0 (default 200 since 1.24); below that use the simple protocol (`PreferSimpleProtocol` on GORM's Postgres driver, pgx `default_query_exec_mode=simple_protocol`) or pgx `exec` mode. `FOR UPDATE SKIP LOCKED` is transaction-scoped and safe.

Set `idle_in_transaction_session_timeout` server-side as containment: it caps the damage from any transaction that starts holding a connection across external I/O.

## Edge Cases

- `db.Save(&user)` updates zero values too; use `db.Model(&u).Updates(map[string]any{...})` for partial updates
- Partial updates with a struct skip zero-valued fields silently; use `map[string]any{}` or `Select(...)` to set zeros explicitly

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design | `## Data Access Design` with `### Models`, `### Repository Interface`, `### Pool`; code for each decision follows the tables under `### <Decision>` headings, in the order the decision sentences list them. A design handed existing code that violates a Rule emits `## Findings` first. DDL belongs to `go-migration-safety`; the dispatch mechanism's queue or topic to `go-messaging-patterns` - name each in one sentence |
| Review | `## Findings`, then `## Data Access Design` describing the layer as it exists today |
| Debug | two opening lines `**Failing:**` and `**First fix:**`, then `## Findings`, then `## Data Access Design` as it exists today; a sizing question adds `### Sizing` under it: a table with the columns Binary, Replicas (+surge), MaxOpen and Total, closed by a `PgBouncer: yes` or `PgBouncer: no` line with the reason |

```
## Data Access Design

### Models
| Model | Table | Associations | Soft Delete? |
|-------|-------|--------------|--------------|

### Repository Interface
| Method | GORM/sqlx | Query Type |
|--------|-----------|------------|

### Pool
| Binary | Setting | Value | Rationale |
|--------|---------|-------|-----------|
```

Cell values: every cell describes the code as written; the intended value goes in the finding's `Fix`. `Associations` lists GORM associations by name, or `none (FK column only)` when a foreign key exists without an association. `Soft Delete?` is `Yes | No | unknown` - `No` when the struct has no `DeletedAt`, `unknown` when the struct was not supplied, never inferred from the table name; a model the design does not own gets one row marked `(existing)`. `GORM/sqlx` is `GORM | sqlx | raw SQL`; `db.Raw` and `db.Exec` are `raw SQL`. `Query Type` is `PK lookup | Locking read | List | Keyset page | Aggregate | Stream | Write | Transactional write | Upsert | Claim | Tx boundary | n/a` - `PK lookup` covers any unique-key lookup, `Tx boundary` a method that opens a transaction for other repositories, `n/a` a non-query accessor (`DB()`, `WithTx`); an unbounded read is `List` plus a `[Must]` finding. `Pool` holds one row per setting per binary - `Binary` is the process (`api`, `worker`), `server`, or `pgbouncer`; a setting that is never called is `not configured (default: <the database/sql default>)`, since the default is the value in force - `MaxOpenConns` 0 (unlimited), `MaxIdleConns` 2, `ConnMaxLifetime` and `ConnMaxIdleTime` 0 (never). A server or proxy setting cites its source in `Rationale` as `<doc>:<setting>`. On a review or debug the `Value` is the in-force value and the proposed value belongs in the finding's `Fix`. `Pool` includes the proxy and server settings the fan-in math depends on (`pool_mode`, `max_client_conn`, `default_pool_size`, `max_connections`) when one is in front of the database. A cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries. When the design turns on a transaction boundary, a lock strategy, an index, or an event-dispatch mechanism, state each in a sentence under the tables - those decisions have no column and must not be dropped. `**Failing:**` names the symptom; `**First fix:**` names the one change that must land before the others work (re-sizing a pool is inert while transactions still hold connections across external I/O) - the rest follow in `## Findings` order.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {what happens at runtime - wrong rows, leaked connection, unbounded memory, injectable query}
- Rule: {the data-access rule violated}
- Fix: {concrete edit}
```

`[Must]` for injectable SQL, a leaked or long-held connection or transaction, unconfigured or oversubscribed pool limits, `AutoMigrate` on a production path, a dual write across the transaction boundary, data loss or corruption, unbounded memory, or a query that returns the wrong rows (missing tenant scope, missing soft-delete filter, page overlap); `[Recommend]` for a violated `Rules` line whose consequence here is structural (an interface in the repository package, a scope without `WithContext` on a path that has no deadline). Judge by consequence, not by matching the list. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not (code the input names but does not supply, or telemetry); a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (goroutine lifecycle, authorization, error wrapping) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Rule:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- `AutoMigrate` in production
- Pool defaults (unbounded)
- Hooks for non-trivial business logic or outbound dispatch
- GORM for complex reporting or window functions (use sqlx)
- Missing `WithContext` / `*Context`
- Repository interface in the repository package
- `Limit`/`Offset` without `Order`
- sqlx raw SQL on `gorm.Model` tables without an explicit `deleted_at IS NULL` filter
