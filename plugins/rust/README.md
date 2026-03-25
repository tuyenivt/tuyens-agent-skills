# Tuyen's Agent Skills - Rust

Claude Code plugin for Rust development.

## Stack

- Rust 1.94+
- Tokio (async runtime)
- Axum (primary) / Actix-web (secondary)
- sqlx (compile-time checked SQL)
- sqlx-cli (migrations)
- PostgreSQL

## Agents

| Agent                       | Description                                                                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rust-architect`            | Rust architect for Axum, sqlx, clean architecture, and production Rust patterns. Designs features, structures projects, makes architecture decisions.  |
| `rust-tech-lead`            | Rust tech lead for code review, refactoring guidance, doc standards. Reviews for idiomatic Rust, error handling, ownership safety, and async patterns. |
| `rust-reliability-engineer` | Rust reliability engineer for incident analysis, runbook standards in Rust/Axum/PostgreSQL environments. Tokio runtime profiling, task leak detection. |
| `rust-security-engineer`    | OWASP Top 10 for Rust, JWT/Axum auth middleware review, input validation, cargo audit dependency scanning.                                             |
| `rust-performance-engineer` | Tokio task leak detection, sqlx query tuning, memory allocation analysis, profiling, connection pool sizing.                                           |
| `rust-test-engineer`        | Unit test strategies, tokio::test, testcontainers, mockall, and cargo clippy discipline for Rust/Axum services.                                        |
| `rust-sprint-planner`       | Sprint allocation for Rust features with sqlx/Kafka/async complexity awareness and dependency sequencing.                                              |

## Workflow Skills

| Skill             | Description                                                                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-rust-new`   | End-to-end Rust/Axum feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests. |
| `task-rust-debug` | Debug Rust errors. Paste a panic backtrace, error log, or describe unexpected behavior. Classifies error, identifies root cause, suggests fix.    |

## Atomic Skills

| Skill                     | Description                                                                                                                                       |
| ------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rust-error-handling`     | Rust error patterns: `Result<T, E>`, thiserror for libraries, anyhow for applications, custom error types, error propagation with `?`.            |
| `rust-web-patterns`       | Axum web framework patterns: routing, tower middleware, extractors, request validation, consistent JSON responses, pagination, graceful shutdown. |
| `rust-db-access`          | Rust data access with sqlx. Compile-time checked queries, connection pooling, transactions, N+1 prevention.                                       |
| `rust-migration-safety`   | Safe migration patterns with sqlx-cli and PostgreSQL. File naming, reversible migrations, zero-downtime DDL, embedded migrations.                 |
| `rust-testing-patterns`   | Rust testing: unit tests, tokio::test for async, testcontainers for PostgreSQL, mockall for trait mocking, proptest, criterion.                   |
| `rust-async-patterns`     | Rust async patterns: Tokio runtime, async/await, JoinSet, CancellationToken, select!, spawn_blocking, cancellation safety.                        |
| `rust-concurrency`        | Rust concurrency patterns: Arc/Mutex, RwLock, channels, Send+Sync traits, rayon for data parallelism, atomics.                                    |
| `rust-messaging-patterns` | Background jobs with Tokio task queues, Kafka consumers with rdkafka, AMQP with lapin, and worker pools.                                          |
| `rust-security-patterns`  | JWT authentication, input validation, SQL injection prevention, secrets management, CORS, cargo-audit.                                            |

## Usage Examples

### Implement a feature end-to-end

```
> task-rust-new

Feature: Add payment processing with webhook endpoint
- Creates migration for payments table
- Repository with sqlx for CRUD
- Service with Stripe integration and error wrapping
- Axum handlers with webhook signature validation
- Unit tests with mockall + integration tests with testcontainers

-> Validates with cargo build, cargo test, cargo clippy
```

### Debug a Rust error

```
> task-rust-debug

thread 'tokio-runtime-worker' panicked at 'called `Result::unwrap()` on an `Err` value: ...
   at src/service/order.rs:45:10

-> Classifies, locates root cause, provides before/after fix, prevention strategy
```
