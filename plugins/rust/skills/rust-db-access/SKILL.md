---
name: rust-db-access
description: "Rust data access with sqlx. Compile-time checked queries, connection pooling, transactions, query building, N+1 prevention. sqlx (primary) vs diesel (secondary)."
user-invocable: false
---

# Rust Data Access

## When to Use

- Designing the data access layer for a new Rust service
- Reviewing database queries for safety, N+1, or pool misconfiguration
- Choosing between sqlx and diesel for a specific use case
- Debugging slow queries or connection exhaustion

## Rules

- Always use compile-time checked queries (`sqlx::query!` / `sqlx::query_as!`) when possible
- Always configure connection pool limits - defaults may exhaust the database
- Always use transactions for multi-step mutations - never partial writes
- Use parameterized queries - never string interpolation in SQL
- Close/return connections promptly - don't hold pool connections across long operations

## When to Use sqlx vs diesel

| Scenario                                       | Use    |
| ---------------------------------------------- | ------ |
| Most queries (compile-time checked, zero-cost) | sqlx   |
| Complex query builder with type-safe DSL       | diesel |
| Bulk insert or upsert operations               | sqlx   |
| Simple lookups by primary key                  | Either |
| Existing project with diesel setup             | diesel |

sqlx is the primary recommendation for new projects - compile-time query checking catches SQL errors at build time.

## sqlx Patterns

### Model Definition

```rust
use sqlx::FromRow;
use chrono::{DateTime, Utc};

#[derive(Debug, FromRow)]
pub struct User {
    pub id: i64,
    pub name: String,
    pub email: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}
```

### Compile-Time Checked Queries

```rust
// query_as! checks SQL against your actual database schema at compile time
async fn find_by_id(pool: &PgPool, id: i64) -> Result<User, AppError> {
    sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id)
        .fetch_optional(pool)
        .await
        .map_err(AppError::Database)?
        .ok_or_else(|| AppError::NotFound(format!("user {id}")))
}

// query! for operations that don't return a struct
async fn update_email(pool: &PgPool, id: i64, email: &str) -> Result<(), AppError> {
    sqlx::query!("UPDATE users SET email = $1, updated_at = NOW() WHERE id = $2", email, id)
        .execute(pool)
        .await
        .map_err(AppError::Database)?;
    Ok(())
}
```

### Transactions

```rust
async fn create_order_with_items(
    pool: &PgPool,
    order: &NewOrder,
    items: &[NewOrderItem],
) -> Result<Order, AppError> {
    let mut tx = pool.begin().await.map_err(AppError::Database)?;

    let order = sqlx::query_as!(
        Order,
        "INSERT INTO orders (user_id, total) VALUES ($1, $2) RETURNING *",
        order.user_id,
        order.total,
    )
    .fetch_one(&mut *tx)
    .await
    .map_err(AppError::Database)?;

    for item in items {
        sqlx::query!(
            "INSERT INTO order_items (order_id, sku, quantity) VALUES ($1, $2, $3)",
            order.id,
            item.sku,
            item.quantity,
        )
        .execute(&mut *tx)
        .await
        .map_err(AppError::Database)?;
    }

    tx.commit().await.map_err(AppError::Database)?;
    Ok(order)
}
```

### Pagination

```rust
async fn list_users(
    pool: &PgPool,
    page: i64,
    page_size: i64,
) -> Result<(Vec<User>, i64), AppError> {
    let offset = (page - 1) * page_size;

    let users = sqlx::query_as!(
        User,
        "SELECT * FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2",
        page_size,
        offset,
    )
    .fetch_all(pool)
    .await
    .map_err(AppError::Database)?;

    let total = sqlx::query_scalar!("SELECT COUNT(*) FROM users")
        .fetch_one(pool)
        .await
        .map_err(AppError::Database)?
        .unwrap_or(0);

    Ok((users, total))
}
```

## Connection Pool Configuration

Configure immediately after creating the pool - never leave at defaults:

```rust
use sqlx::postgres::PgPoolOptions;

let pool = PgPoolOptions::new()
    .max_connections(25)            // max simultaneous connections to DB
    .min_connections(5)             // connections kept open when idle
    .acquire_timeout(Duration::from_secs(3))  // fail fast if pool exhausted
    .idle_timeout(Duration::from_secs(60))    // close connections idle longer than this
    .max_lifetime(Duration::from_secs(300))   // recycle connections (important for load balancers)
    .connect(&database_url)
    .await?;
```

**Sizing guidance:**

- `max_connections`: start at 25; tune based on DB thread limit and observed wait times
- `min_connections`: set to ~20% of max_connections to avoid connection churn
- `max_lifetime`: always set - prevents stale connections after DB restarts or load balancer failovers

## Anti-Patterns

```rust
// Bad: string interpolation in SQL (SQL injection)
let query = format!("SELECT * FROM users WHERE name = '{name}'");
sqlx::query(&query).fetch_all(pool).await?;

// Bad: new connection per request (exhausts DB connections)
async fn handler() {
    let pool = PgPool::connect(&url).await.unwrap(); // wasteful
}

// Bad: no pool limits (unlimited connections will crash the DB under load)
PgPoolOptions::new().connect(&url).await?; // missing max_connections

// Bad: N+1 queries in a loop
for user in &users {
    let orders = sqlx::query_as!(Order, "SELECT * FROM orders WHERE user_id = $1", user.id)
        .fetch_all(pool).await?; // N additional queries
}

// Good: batch fetch with IN clause
let orders = sqlx::query_as!(Order,
    "SELECT * FROM orders WHERE user_id = ANY($1)",
    &user_ids[..]
).fetch_all(pool).await?;
```

## Avoid

- String interpolation in SQL - always use parameterized queries (`$1`, `$2`)
- Creating new pools per request
- Pools without connection limits
- N+1 queries in loops - batch with `ANY($1)` or joins
- Transactions without error handling (partial commits)
- Holding pool connections across long-running async operations
