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
- Transactions: defer rollback; only return after commit
- N+1: `Preload` for associations you'll access; `Joins` when filtering by them
- Repository interfaces live in the consumer (service) package, never in the repo package

## GORM vs sqlx

| Scenario                                      | Use    |
| --------------------------------------------- | ------ |
| CRUD with associations                        | GORM   |
| Reporting / complex joins                     | sqlx   |
| Bulk insert / upsert                          | sqlx   |
| Simple PK lookups                             | Either |

Both share a `*sql.DB` pool via `db.DB()`.

## Patterns

### Consumer-defined Repository Interface

```go
// service/payment.go
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
    gorm.Model // ID, CreatedAt, UpdatedAt, DeletedAt
    Name   string  `gorm:"not null"`
    Email  string  `gorm:"uniqueIndex;not null"`
    Orders []Order `gorm:"foreignKey:UserID"`
}
```

### N+1 Prevention

```go
// Bad: N queries to load Orders
db.Find(&users)
for _, u := range users { db.Find(&u.Orders) }

// Good: Preload (two queries via IN)
db.Preload("Orders").Find(&users)

// Good: Joins (single query; use when filtering by association)
db.Joins("JOIN orders ON orders.user_id = users.id").
    Where("orders.total > ?", 100).Find(&users)
```

### Transactions

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
    if err := db.Limit(limit).Offset(offset).Order("created_at DESC").Find(&payments).Error; err != nil {
        return nil, 0, fmt.Errorf("list: %w", err)
    }
    return payments, total, nil
}
```

### Hooks (Sparingly)

Hooks are invisible to callers. Use only for genuine cross-cutting concerns (audit fields, password hashing); prefer explicit service-layer logic for non-trivial operations.

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

### Bulk Insert

```go
_, err := r.db.NamedExecContext(ctx,
    `INSERT INTO items (order_id, sku, quantity) VALUES (:order_id, :sku, :quantity)`,
    items)
```

## Connection Pool

Configure immediately after open:

```go
sqlDB, _ := db.DB()
sqlDB.SetMaxOpenConns(25)                  // tune to DB thread limit
sqlDB.SetMaxIdleConns(10)                  // ~40% of max open
sqlDB.SetConnMaxLifetime(5 * time.Minute)  // recycle for LB failover
sqlDB.SetConnMaxIdleTime(1 * time.Minute)
```

## Edge Cases

- `gorm.Model` enables soft delete: `db.Delete()` sets `deleted_at`; queries auto-filter. Use `Unscoped()` for hard delete
- `db.Save(&user)` updates zero values too; use `db.Model(&u).Updates(map[string]any{...})` for partial updates
- sqlx StructScan on nullable columns requires pointer types or `sql.NullX`

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
- Hooks for non-trivial business logic
- GORM for complex reporting (use sqlx)
- Missing `WithContext` / `*Context`
- Repository interface in the repository package
