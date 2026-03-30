---
name: go-data-access
description: "Go data access with GORM and sqlx. Model definition, associations, preloading, transactions, scopes, connection pooling, upserts, and repository interface patterns. When to use GORM vs sqlx. Both can coexist."
metadata:
  category: backend
  tags: [go, gorm, sqlx, database, postgresql, repository]
user-invocable: false
---

# Go Data Access

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing the data access layer for a new Go service
- Reviewing ORM usage for N+1, missing transactions, or pool misconfiguration
- Choosing between GORM and sqlx for a specific query type
- Implementing idempotent writes with upsert patterns
- Debugging slow queries or connection exhaustion

## Rules

- Never use `AutoMigrate` in production - use versioned migration files instead
- Always configure connection pool limits - zero means unlimited, which will exhaust the database
- Always close `*sql.Rows` - use `defer rows.Close()` immediately after checking the open error
- Always pass `context.Context` to queries - use `db.WithContext(ctx)` for GORM, `db.QueryxContext(ctx, ...)` for sqlx
- Transactions must be explicitly committed or rolled back - always use `defer tx.Rollback()` and only return after `tx.Commit()`
- N+1: use `Preload` for associations you know you'll access; use `Joins` when filtering by association fields
- Define repository interfaces in the consumer (service) package, not in the repository package

## When to Use GORM vs sqlx

| Scenario                                      | Use    |
| --------------------------------------------- | ------ |
| CRUD with associations (users, orders, items) | GORM   |
| Reporting queries with complex joins          | sqlx   |
| Bulk insert or upsert operations              | sqlx   |
| Simple lookups by primary key                 | Either |
| Queries requiring raw SQL for performance     | sqlx   |

Both can share the same `*sql.DB` connection pool via `db.DB()`.

## Patterns

### Repository Interface (defined in consumer package)

The service package defines the interface it needs. The repository package implements it. This keeps the dependency direction clean:

```go
// service/payment.go - consumer defines what it needs
type PaymentRepository interface {
    FindByID(ctx context.Context, id string) (*Payment, error)
    Create(ctx context.Context, payment *Payment) error
    CreateIdempotent(ctx context.Context, payment *Payment) (*Payment, error)
    UpdateStatus(ctx context.Context, id string, status string) error
    List(ctx context.Context, limit, offset int) ([]Payment, int64, error)
}

// repository/payment.go - implementation
type paymentRepo struct {
    db *gorm.DB
}

func NewPaymentRepository(db *gorm.DB) PaymentRepository {
    return &paymentRepo{db: db}
}
```

### Model Definition

```go
type User struct {
    gorm.Model          // embeds ID, CreatedAt, UpdatedAt, DeletedAt
    Name    string      `gorm:"not null"`
    Email   string      `gorm:"uniqueIndex;not null"`
    Orders  []Order     `gorm:"foreignKey:UserID"`
}

type Order struct {
    gorm.Model
    UserID  uint
    User    User
    Total   float64
}
```

### Associations and N+1 Prevention

```go
// Bad: N+1 - one query per user to fetch their orders
var users []User
db.Find(&users)
for _, u := range users {
    db.Find(&u.Orders) // N additional queries
}

// Good: Preload - two queries total (users + all their orders in one IN query)
db.Preload("Orders").Find(&users)

// Good: Joins - single query, use when filtering by association field
db.Joins("JOIN orders ON orders.user_id = users.id").
    Where("orders.total > ?", 100).
    Find(&users)
```

### Transactions

```go
func (r *orderRepo) CreateWithItems(ctx context.Context, order *Order, items []Item) error {
    return r.db.WithContext(ctx).Transaction(func(tx *gorm.DB) error {
        if err := tx.Create(order).Error; err != nil {
            return fmt.Errorf("create order: %w", err)
        }
        for i := range items {
            items[i].OrderID = order.ID
        }
        if err := tx.Create(&items).Error; err != nil {
            return fmt.Errorf("create items: %w", err)
        }
        return nil // commit on nil return
    })
}
```

### Upsert with Idempotency Key

For operations that must be idempotent (payment processing, webhook handling), use GORM's `OnConflict` clause:

```go
func (r *paymentRepo) CreateIdempotent(ctx context.Context, payment *Payment) (*Payment, error) {
    result := r.db.WithContext(ctx).
        Clauses(clause.OnConflict{
            Columns:   []clause.Column{{Name: "idempotency_key"}},
            DoNothing: true,
        }).Create(payment)
    if result.Error != nil {
        return nil, fmt.Errorf("createIdempotent: %w", result.Error)
    }
    if result.RowsAffected == 0 {
        // Already exists - fetch and return the existing record
        var existing Payment
        if err := r.db.WithContext(ctx).Where("idempotency_key = ?", payment.IdempotencyKey).First(&existing).Error; err != nil {
            return nil, fmt.Errorf("fetch existing payment: %w", err)
        }
        return &existing, nil
    }
    return payment, nil
}
```

For sqlx with raw SQL:

```sql
INSERT INTO payments (id, idempotency_key, amount, status)
VALUES (:id, :idempotency_key, :amount, :status)
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING *;
```

### Scopes for Reusable Query Logic

```go
func ActiveUsers(db *gorm.DB) *gorm.DB {
    return db.Where("status = ?", "active")
}

func PaginatedBy(page, pageSize int) func(*gorm.DB) *gorm.DB {
    return func(db *gorm.DB) *gorm.DB {
        return db.Offset((page - 1) * pageSize).Limit(pageSize)
    }
}

// Usage
db.Scopes(ActiveUsers, PaginatedBy(2, 20)).Find(&users)
```

### List with Count (Pagination)

```go
func (r *paymentRepo) List(ctx context.Context, limit, offset int) ([]Payment, int64, error) {
    var payments []Payment
    var total int64

    db := r.db.WithContext(ctx).Model(&Payment{})
    if err := db.Count(&total).Error; err != nil {
        return nil, 0, fmt.Errorf("count payments: %w", err)
    }
    if err := db.Limit(limit).Offset(offset).Order("created_at DESC").Find(&payments).Error; err != nil {
        return nil, 0, fmt.Errorf("list payments: %w", err)
    }
    return payments, total, nil
}
```

### Hooks (Use Sparingly)

```go
// Use for cross-cutting concerns like hashing passwords or setting audit fields
func (u *User) BeforeCreate(tx *gorm.DB) error {
    hash, err := bcrypt.GenerateFromPassword([]byte(u.Password), bcrypt.DefaultCost)
    if err != nil {
        return err
    }
    u.Password = string(hash)
    return nil
}
```

Hooks are invisible to callers and can cause surprising behavior. Prefer explicit service-layer logic for non-trivial operations.

## sqlx Patterns

### Named Queries and Struct Scanning

```go
type OrderSummary struct {
    UserID     int     `db:"user_id"`
    UserName   string  `db:"user_name"`
    OrderCount int     `db:"order_count"`
    TotalSpend float64 `db:"total_spend"`
}

const summaryQuery = `
    SELECT u.id AS user_id, u.name AS user_name,
           COUNT(o.id) AS order_count, SUM(o.total) AS total_spend
    FROM users u
    LEFT JOIN orders o ON o.user_id = u.id
    WHERE u.status = :status
    GROUP BY u.id, u.name
    HAVING SUM(o.total) > :min_spend
`

func (r *reportRepo) GetTopSpenders(ctx context.Context, minSpend float64) ([]OrderSummary, error) {
    var results []OrderSummary
    rows, err := r.db.NamedQueryContext(ctx, summaryQuery, map[string]any{
        "status":    "active",
        "min_spend": minSpend,
    })
    if err != nil {
        return nil, fmt.Errorf("GetTopSpenders: %w", err)
    }
    defer rows.Close()

    if err := sqlx.StructScan(rows, &results); err != nil {
        return nil, fmt.Errorf("GetTopSpenders scan: %w", err)
    }
    return results, nil
}
```

### Bulk Insert

```go
func (r *itemRepo) BulkInsert(ctx context.Context, items []Item) error {
    _, err := r.db.NamedExecContext(ctx,
        `INSERT INTO items (order_id, sku, quantity) VALUES (:order_id, :sku, :quantity)`,
        items,
    )
    if err != nil {
        return fmt.Errorf("BulkInsert items: %w", err)
    }
    return nil
}
```

## Connection Pool Configuration

Configure immediately after opening the connection - never leave at defaults:

```go
sqlDB, err := db.DB() // get underlying *sql.DB from GORM
if err != nil {
    return err
}

sqlDB.SetMaxOpenConns(25)                // max simultaneous connections to DB
sqlDB.SetMaxIdleConns(10)               // connections kept open when idle
sqlDB.SetConnMaxLifetime(5 * time.Minute) // recycle connections (important for load balancers)
sqlDB.SetConnMaxIdleTime(1 * time.Minute) // close connections idle longer than this
```

**Sizing guidance:**

- `MaxOpenConns`: start at 25; tune based on DB thread limit and observed wait times
- `MaxIdleConns`: set to ~40% of MaxOpenConns to avoid connection churn
- `ConnMaxLifetime`: always set - prevents stale connections after DB restarts or load balancer failovers

## Edge Cases

- **GORM soft delete**: `gorm.Model` embeds `DeletedAt` which enables soft delete automatically. `db.Delete(&user)` sets `deleted_at` rather than removing the row. Use `db.Unscoped().Delete(&user)` for hard delete. Queries automatically filter out soft-deleted rows
- **GORM zero-value updates**: `db.Save(&user)` updates all fields including zero values. Use `db.Model(&user).Updates(map[string]any{...})` to update only specific fields
- **sqlx StructScan with NULL**: nullable columns must use pointer types or `sql.NullString`/`sql.NullInt64` in the scan target, or the scan will fail

## Output Format

```
## Data Access Design

### Models
| Model | Table | Associations | Soft Delete? |
|-------|-------|-------------|-------------|
| {Name} | {table_name} | {has-many/belongs-to} | {yes/no} |

### Repository Interface
| Method | GORM/sqlx | Query Type |
|--------|-----------|------------|
| FindByID | GORM | single record lookup |
| List | GORM | paginated list with count |
| CreateIdempotent | GORM | upsert with ON CONFLICT |
| GetReport | sqlx | aggregate reporting query |

### Connection Pool
| Setting | Value | Rationale |
|---------|-------|-----------|
| MaxOpenConns | {n} | {why} |
| MaxIdleConns | {n} | {why} |
| ConnMaxLifetime | {duration} | {why} |
```

## Avoid

- `AutoMigrate` outside of local development
- Connections without pool limits
- Unclosed `*sql.Rows`
- Hooks for non-trivial business logic
- GORM for complex reporting queries - use sqlx
- Transactions without deferred rollback
- Missing `WithContext(ctx)` on GORM queries
- Defining repository interfaces in the repository package instead of the consumer (service) package
