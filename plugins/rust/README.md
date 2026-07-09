# Tuyen's Agent Skills - Rust

Claude Code plugin for Rust development.

## Stack

- Rust 1.94+
- Tokio (async runtime)
- Axum 0.8 (primary) / Actix-web (secondary)
- sqlx (compile-time checked SQL)
- sqlx-cli (migrations)
- PostgreSQL

## Agents

| Agent                       | Description                                                                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `rust-architect`            | Rust architect for Axum, sqlx, clean architecture, and production Rust patterns. Designs features, structures projects, makes architecture decisions.  |
| `rust-tech-lead`            | Rust tech lead for code review, refactoring guidance, doc standards. Reviews for idiomatic Rust, error handling, ownership safety, and async patterns. |
| `rust-security-engineer`    | OWASP Top 10 for Rust, JWT/Axum auth middleware review, input validation, cargo audit dependency scanning.                                             |
| `rust-performance-engineer` | Tokio task leak detection, sqlx query tuning, memory allocation analysis, profiling, connection pool sizing.                                           |
| `rust-test-engineer`        | Unit test strategies, tokio::test, testcontainers, mockall, and cargo clippy discipline for Rust/Axum services.                                        |

## Workflow Skills

| Skill                              | Agent                       | Description                                                                                                                                       |
| ---------------------------------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-rust-implement`              | `rust-architect`            | End-to-end Rust/Axum feature implementation. Generates migrations, models, repositories, services, handlers, middleware, and comprehensive tests. |
| `task-rust-debug`                  | `rust-tech-lead`            | Debug Rust errors. Paste a panic backtrace, error log, or describe unexpected behavior. Classifies error, identifies root cause, suggests fix.    |
| `task-rust-review`                 | `rust-tech-lead`            | Rust staff-level code review umbrella - Phases A-E with Axum/sqlx/Tokio idioms. Spawns parallel perf/security/observability subagents.            |
| `task-rust-review-perf`            | `rust-performance-engineer` | sqlx N+1, Tokio task leaks, std::sync::Mutex across .await, blocking I/O on the runtime, allocation hotspots, pool sizing.                        |
| `task-rust-review-security`        | `rust-security-engineer`    | Axum auth, jsonwebtoken, validator-crate input, sqlx parameterization, mass assignment via serde_json::from_value, unsafe audit, cargo-audit.     |
| `task-rust-review-observability`   | `rust-tech-lead`            | tracing crate + tracing-opentelemetry, OTel SDK, metrics-exporter-prometheus, tokio-console, graceful shutdown, sentry-rust.                      |
| `task-rust-test`                   | `rust-test-engineer`        | Test strategy: #[tokio::test], axum-test / tower::oneshot, testcontainers PostgreSQL, mockall, proptest, cargo nextest discipline.                |
| `task-rust-refactor`               | `rust-tech-lead`            | Rust refactor planning: fat handlers, leaked Tokio tasks, std Mutex across await, single-impl traits, Box<dyn> defaults, mass assignment.         |

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
| `rust-code-explain`       | Ownership and borrowing, lifetimes, async runtimes (tokio), trait objects vs generics, error types with `?`, sqlx compile-time queries - injected into `task-code-explain`. |
| `rust-onboard-map`        | Cargo workspace layout, Cargo.toml features, async runtime, framework (Axum/Actix), DB layer (sqlx/sea-orm/diesel), clippy/rustfmt - injected into `task-onboard`. |
| `rust-overengineering-review` | Necessity review: validator-crate rules duplicating sqlx column types / DB / the Rust type system, unreachable `match` arms / `Result` where `E` is never constructed / dead `.unwrap_or_default()` on non-Option values, single-impl trait at the implementation (consumer-side traits are idiomatic) / `Box<dyn Trait>` on hot single-callsite / `Arc<Mutex<T>>` on never-mutated data / hot-loop `.clone()` / speculative `cfg(feature)`. Intentionally narrow - the type system eliminates most categories. Composed into `task-rust-review` Phase D. |

## Usage Examples

### Implement a feature end-to-end

```
> task-rust-implement

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
