---
name: task-rust-new
description: Scaffold a multi-layer Rust/Axum feature end-to-end - migrations, models, repositories, services, handlers, DTOs, and tests. Use for new features requiring coordinated layers; not for single-file fixes (use task-rust-debug).
agent: rust-architect
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## Rules

- No business logic in handlers - handlers extract params, call services, map responses
- Constructor injection via function parameters - services take `Arc<dyn Trait>` dependencies
- Errors use `thiserror` for domain types, `?` operator for propagation - no `.unwrap()` in production paths
- Repository trait defined in the service module (consumer defines its dependency)
- Transactions for multi-step mutations - `pool.begin()` / `tx.commit()`
- Event/job dispatch timing: emit domain events or enqueue background jobs AFTER the transaction commits, never inside it
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Implementation

STEP 1 - GATHER: Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main entities? (fields, relationships, constraints)
3. Are there external integrations? (third-party APIs, message brokers)
4. Are background jobs or async events needed? (notifications, syncing)
5. Does the feature need authentication/authorization?
6. Are there status transitions? (e.g., order: pending -> confirmed -> shipped)
7. Concurrency needs? (shared state, parallel processing, rate limiting)

If the user provides only a brief description without answering all questions, infer reasonable defaults and present them for confirmation. If the user provides a ticket or spec, extract the answers from it.

STEP 2 - DESIGN: Use skill: `rust-web-patterns` for API/handler design. Use skill: `rust-db-access` for data layer design. Propose the implementation layers and present for user approval before generating code.

Present a file tree showing what will be generated:

```
src/
  models/order.rs               # sqlx FromRow struct
  repositories/order.rs         # Repository trait + impl
  services/order.rs             # Business logic
  handlers/order.rs             # Axum handlers
  dto/order.rs                  # Request/response types (serde)
  errors.rs                     # AppError with thiserror
  router.rs                     # Route registration
migrations/
  YYYYMMDDHHMMSS_create_orders.up.sql
  YYYYMMDDHHMMSS_create_orders.down.sql
tests/
  integration/order_test.rs     # Integration tests (testcontainers)
```

STEP 3 - DATABASE: Use skill: `rust-migration-safety`. Generate up/down SQL migration files. Include indexes on foreign keys and frequently-filtered columns. Use `CREATE INDEX CONCURRENTLY` for large tables.

STEP 4 - DATA LAYER: Use skill: `rust-db-access`. Generate repository trait (in service module) and implementation with `sqlx::query_as!` for compile-time checked queries. Configure connection pool with `PgPoolOptions`.

STEP 5 - SERVICE: Use skill: `rust-error-handling`. Generate service with constructor injection via `Arc<dyn Trait>`. Map errors at layer boundaries with `thiserror`.

- If async concurrency needed: Use skill: `rust-async-patterns`
- If shared mutable state needed: Use skill: `rust-concurrency`
- If background jobs or events needed: Use skill: `rust-messaging-patterns`. Dispatch after transaction commit, not inside it.

STEP 6 - HTTP LAYER: Use skill: `rust-web-patterns`. Axum handlers with extractors (`Path`, `Query`, `Json`), consistent response envelope, pagination on list endpoints. Implement `IntoResponse` for `AppError` to map domain errors to HTTP status codes:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 400         |
| Not found            | 404         |
| Conflict (duplicate) | 409         |
| Unauthorized         | 401         |
| External timeout     | 503         |

STEP 7 - TESTS: Use skill: `rust-testing-patterns`. Unit tests with `mockall` + `#[tokio::test]`. Integration tests with `testcontainers`. Handler tests with `tower::ServiceExt::oneshot`. Cover: happy path, validation errors, not-found, conflict.

STEP 8 - VALIDATE: Run `cargo build`, `cargo test`, `cargo clippy -- -D warnings`. Fix any failures before presenting output.

## Output

```markdown
## Files Generated

[grouped file list by layer: models, repositories, services, handlers, dto, errors, tests, migrations]

## Endpoints

| Method | Path               | Request                   | Response                               | Status |
| ------ | ------------------ | ------------------------- | -------------------------------------- | ------ |
| POST   | /api/v1/orders     | CreateOrderRequest (Json) | Json<OrderResponse>                    | 201    |
| GET    | /api/v1/orders     | PaginationQuery (Query)   | Json<PaginatedResponse<OrderResponse>> | 200    |
| GET    | /api/v1/orders/:id | Path<i64>                 | Json<OrderResponse>                    | 200    |
| PATCH  | /api/v1/orders/:id | UpdateOrderRequest (Json) | Json<OrderResponse>                    | 200    |
| DELETE | /api/v1/orders/:id | Path<i64>                 | StatusCode::NO_CONTENT                 | 204    |

## Tests

- Unit tests: {count} (service layer, mockall)
- Handler tests: {count} (axum oneshot)
- Integration tests: {count} (testcontainers)

## Migration

[migration file names and what they create: tables, indexes, constraints]
```

## Avoid

- Business logic in Axum handlers (delegate to service layer)
- `.unwrap()` or `.expect()` in production code paths (use `?` and `thiserror`)
- Dispatching background jobs inside a DB transaction (worker races the commit)
- Blocking the Tokio runtime with sync I/O (use `spawn_blocking`)
- Returning raw sqlx models from endpoints (use response DTOs with serde)
- Skipping pagination on list endpoints
- Generating code before user approves the design

## Self-Check

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, repository, service, handler, routes, tests
- [ ] Constructor injection via `Arc<dyn Trait>`; errors use `thiserror` and `?` operator
- [ ] No unbounded spawns; repository trait defined in service module
- [ ] Background jobs dispatched after transaction commit, not inside it
- [ ] `cargo build`, `cargo test`, and `cargo clippy` all pass
- [ ] Migration includes indexes; list endpoints paginated; output template filled
