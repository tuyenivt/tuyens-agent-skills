---
name: go-data-access
description: "Go data access with GORM and sqlx: models, preloading, transactions, scopes, pool config, upserts, consumer-defined repository interfaces."
metadata:
  category: backend
  tags: [go, gorm, sqlx, database, postgresql, repository]
user-invocable: false
---

# Go Data Access

> Load `Use skill: stack-detect` first to determine the project stack.

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
- Transactions: prefer the closure form (`db.Transaction(func(tx) error { ... })`); side effects that leave the DB happen after commit, never inside the closure
- N+1: `Preload` for associations you'll access; `Joins` when filtering by them
- Repository interfaces live in the consumer (service) package, never in the repo package
- Pagination: always pair `Limit`/`Offset` with a deterministic `Order`; prefer keyset (`WHERE id < ? ORDER BY id DESC`) over large offsets

## GORM vs sqlx

| Scenario                                      | Use    |
| --------------------------------------------- | ------ |
| CRUD with associations                        | GORM   |
| Reporting / complex joins / window functions  | sqlx   |
| Bulk insert / upsert                          | sqlx   |
| Simple PK lookups                             | Either |

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
func NewPaymentRepository(db *gorm.DB) PaymentRepository { return &paymentRepo{db: db} }
```

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
// Bad: N queries
db.Find(&users)
for _, u := range users { db.Find(&u.Orders) }

// Good: Preload (two queries via IN)
db.Preload("Orders").Find(&users)

// Good: Joins (single query; use when filtering by association)
db.Joins("JOIN orders ON orders.user_id = users.id").
    Where("orders.total > ?", 100).Find(&users)
```

### Transactions

Use the closure form - it commits on `return nil`, rolls back on non-nil return or panic, and avoids the connection-leak class that `db.Begin()` + `defer tx.Rollback()` rots into.

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

When the unit of work spans repositories, expose `WithTx` constructors so the service owns the transaction and repositories accept the `*gorm.DB` bound to it:

```go
type RefundRepository interface{ Create(ctx context.Context, r *Refund) error }
type OutboxRepository interface{ Enqueue(ctx context.Context, m *OutboxMessage) error }

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
return db.Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&order).Error; err != nil { return err }
    _, err := asynq.Enqueue(asynq.NewTask("order.notify", payload))
    return err
})

// Good - dispatch after commit
var orderID int64
err := db.Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&order).Error; err != nil { return err }
    orderID = order.ID
    return nil
})
if err != nil { return err }
if _, err := asynq.Enqueue(asynq.NewTask("order.notify", payload)); err != nil {
    slog.ErrorContext(ctx, "post-commit enqueue failed", "order_id", orderID, "err", err)
}
```

GORM `AfterCreate` / `AfterUpdate` hooks fire **inside** the transaction - same hazard. Move side-effect calls into the calling service.

A process crash between commit and `Enqueue` drops the dispatch. If unacceptable, use the outbox below.

#### Transactional outbox

Insert an `outbox_messages` row inside the tx; a relay claims rows with `FOR UPDATE SKIP LOCKED` and dispatches. Handlers must be idempotent.

```go
// Inside the writing tx:
tx.Create(&OutboxMessage{Topic: "order.notify", Payload: payload, Status: "pending"})

// Relay (separate goroutine / process):
const claim = `
    UPDATE outbox_messages SET status = 'processing', claimed_at = NOW()
    WHERE id IN (
        SELECT id FROM outbox_messages
        WHERE status = 'pending' ORDER BY id LIMIT $1
        FOR UPDATE SKIP LOCKED
    ) RETURNING *`
```

#### Long-running transactions (anti-pattern)

Holding a tx across user input, HTTP calls, or broker dispatch ties up a pool connection and lengthens lock windows. Symptoms: `too many connections`, lock waits, deadlocks.

```go
// Bad - external HTTP inside the tx
db.Transaction(func(tx *gorm.DB) error {
    tx.Create(&order)
    resp, _ := http.Get(externalURL) // holds connection + locks for the round trip
    tx.Save(&resp)
    return nil
})

// Good - fetch first, then transact briefly
data, err := fetch(ctx, externalURL)
if err != nil { return err }
return db.Transaction(func(tx *gorm.DB) error {
    return tx.Create(&Order{Payload: data}).Error
})
```

#### Locking

Pessimistic row lock when concurrent writers contend on the same row (counters, balances, inventory):

```go
db.Clauses(clause.Locking{Strength: "UPDATE"}).
    Where("id = ?", id).First(&account)
account.Balance += amount
db.Save(&account)
```

Optimistic locking when contention is rare and retry on conflict is acceptable:

```go
type Account struct { ID int64; Balance int64; Version int }

res := db.Model(&account).
    Where("id = ? AND version = ?", account.ID, account.Version).
    Updates(map[string]any{"balance": newBalance, "version": account.Version + 1})
if res.RowsAffected == 0 {
    return ErrStaleRead // caller re-reads and retries
}
```

`clause.Locking{Strength: "SHARE"}` for `FOR SHARE`. In-process `sync.Mutex` is **not** a substitute - it only serializes within one replica; multi-replica counters/balances require DB-level locking or optimistic versioning.

#### Savepoints (nested transactions)

GORM nested `Transaction(...)` calls become savepoints, letting an inner step fail without aborting the outer tx. Use sparingly - most "keep going on partial failure" cases are better as two top-level transactions plus retry.

```go
db.Transaction(func(tx *gorm.DB) error {
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
            Columns:   []clause.Column{{Name: "idempotency_key"}},
            DoNothing: true,
        }).Create(p)
    if res.Error != nil {
        return nil, fmt.Errorf("createIdempotent: %w", res.Error)
    }
    if res.RowsAffected == 0 {
        var existing Payment
        if err := r.db.WithContext(ctx).
            Where("idempotency_key = ?", p.IdempotencyKey).First(&existing).Error; err != nil {
            return nil, fmt.Errorf("fetch existing: %w", err)
        }
        return &existing, nil
    }
    return p, nil
}
```

sqlx equivalent:

```sql
INSERT INTO payments (id, idempotency_key, amount, status)
VALUES (:id, :idempotency_key, :amount, :status)
ON CONFLICT (idempotency_key) DO NOTHING RETURNING *;
```

Retryable endpoints (`POST /payments`) need a client-supplied idempotency key in the request, not a server-generated one.

### Scopes

```go
func ActiveUsers(db *gorm.DB) *gorm.DB { return db.Where("status = ?", "active") }
func PaginatedBy(page, size int) func(*gorm.DB) *gorm.DB {
    return func(db *gorm.DB) *gorm.DB {
        return db.Offset((page - 1) * size).Limit(size)
    }
}

db.Scopes(ActiveUsers, PaginatedBy(2, 20)).Find(&users)
```

### List with Count

```go
func (r *paymentRepo) List(ctx context.Context, limit, offset int) ([]Payment, int64, error) {
    var (payments []Payment; total int64)
    db := r.db.WithContext(ctx).Model(&Payment{})
    if err := db.Count(&total).Error; err != nil {
        return nil, 0, fmt.Errorf("count: %w", err)
    }
    if err := db.Order("created_at DESC, id DESC").Limit(limit).Offset(offset).Find(&payments).Error; err != nil {
        return nil, 0, fmt.Errorf("list: %w", err)
    }
    return payments, total, nil
}
```

`Limit`/`Offset` without `Order` returns rows in undefined order - page 2 may overlap page 1. Tiebreak on a unique column (`id`) when the primary sort can repeat. For tables that grow without bound, prefer keyset pagination.

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
    items)
```

### Dropping from GORM to sqlx

sqlx queries bypass GORM's `deleted_at IS NULL` filter. When the table uses `gorm.Model`, add `WHERE deleted_at IS NULL` to raw SQL explicitly, or you will return soft-deleted rows.

## Connection Pool

Configure immediately after open:

```go
sqlDB, _ := db.DB()
sqlDB.SetMaxOpenConns(25)
sqlDB.SetMaxIdleConns(10)                  // ~40% of max open
sqlDB.SetConnMaxLifetime(5 * time.Minute)  // recycle for LB failover
sqlDB.SetConnMaxIdleTime(1 * time.Minute)
```

**Replica fan-in math.** `replicas * SetMaxOpenConns < DB max_connections - reserved`. Example: Postgres `max_connections=100`, reserve 10 for admin/migrations, 8 service replicas → `SetMaxOpenConns((100-10)/8) ≈ 11`. Front the DB with PgBouncer (transaction pooling) when the worker count makes per-replica limits too tight.

## Edge Cases

- `db.Save(&user)` updates zero values too; use `db.Model(&u).Updates(map[string]any{...})` for partial updates
- Partial updates with a struct skip zero-valued fields silently; use `map[string]any{}` or `Select(...)` to set zeros explicitly

## Output Format

```
## Data Access Design

### Models
| Model | Table | Associations | Soft Delete? |

### Repository Interface
| Method | GORM/sqlx | Query Type |

### Pool
| Setting | Value | Rationale |
```

## Avoid

- `AutoMigrate` in production
- Pool defaults (unbounded)
- Hooks for non-trivial business logic or outbound dispatch
- GORM for complex reporting or window functions (use sqlx)
- Missing `WithContext` / `*Context`
- Repository interface in the repository package
- `Limit`/`Offset` without `Order`
- sqlx raw SQL on `gorm.Model` tables without an explicit `deleted_at IS NULL` filter
