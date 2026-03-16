---
name: go-data-access
description: "Go data access with GORM and sqlx. Model definition, associations, preloading, transactions, scopes, connection pooling. When to use GORM vs sqlx. Both can coexist."
metadata:
  category: backend
  tags: [go, gorm, sqlx, database, postgresql, repository]
user-invocable: false
---

# Go Data Access

## When to Use

- Designing the data access layer for a new Go service
- Reviewing ORM usage for N+1, missing transactions, or pool misconfiguration
- Choosing between GORM and sqlx for a specific query type
- Debugging slow queries or connection exhaustion

## Rules

- Never use `AutoMigrate` in production - use versioned migration files instead
- Always configure connection pool limits - zero means unlimited, which will exhaust the database
- Always close `*sql.Rows` - use `defer rows.Close()` immediately after checking the open error
- Transactions must be explicitly committed or rolled back - always use `defer tx.Rollback()` and only return after `tx.Commit()`
- N+1: use `Preload` for associations you know you'll access; use `Joins` when filtering by association fields

## When to Use GORM vs sqlx

| Scenario                                      | Use    |
| --------------------------------------------- | ------ |
| CRUD with associations (users, orders, items) | GORM   |
| Reporting queries with complex joins          | sqlx   |
| Bulk insert or upsert operations              | sqlx   |
| Simple lookups by primary key                 | Either |
| Queries requiring raw SQL for performance     | sqlx   |

Both can share the same `*sql.DB` connection pool via `db.DB()`.

## GORM Patterns

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

## Anti-Patterns

```go
// Bad: AutoMigrate in production (drops columns, causes locks)
db.AutoMigrate(&User{})

// Bad: new connection per request (exhausts DB connections)
func handler(w http.ResponseWriter, r *http.Request) {
    db, _ := gorm.Open(...)
    defer db.Close() // this is wasteful and slow
}

// Bad: forgetting to close rows (connection leak)
rows, _ := db.Raw("SELECT ...").Rows()
// no defer rows.Close()

// Bad: no pool limits (unlimited connections will crash the DB under load)
db, _ := gorm.Open(...)
// missing SetMaxOpenConns

// Bad: mixing AutoMigrate and manual migrations (schema drift)
```

## Avoid

- `AutoMigrate` outside of local development
- Connections without pool limits
- Unclosed `*sql.Rows`
- Hooks for non-trivial business logic
- GORM for complex reporting queries - use sqlx
- Transactions without deferred rollback

## Self-Check

- [ ] GORM used for CRUD with associations; sqlx used for complex reporting queries
- [ ] Connection pool configured immediately after opening (`SetMaxOpenConns`, `SetMaxIdleConns`, `SetConnMaxLifetime`)
- [ ] All `*sql.Rows` closed with `defer rows.Close()` after checking the open error
- [ ] Transactions use `defer tx.Rollback()` with explicit `tx.Commit()` on success
- [ ] N+1 prevented with `Preload` for known associations or `Joins` for filtered queries
- [ ] Repository interface defined in the consumer (service) package
- [ ] No `AutoMigrate` in production code
