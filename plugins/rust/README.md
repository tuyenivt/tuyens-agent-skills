# Tuyen's Agent Skills - Rust

Claude Code plugin for Rust development.

## Stack

- Rust 1.94+ (edition 2024)
- Tokio
- Axum 0.8
- sqlx 0.9
- sqlx-cli
- PostgreSQL

## Agents

| Agent                         | Description                                                                                                                                             |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rust-engineer`               | Rust 1.94+ engineer for Axum, sqlx - builds features end-to-end: migrations, repositories, services, handlers, middleware, tests. Debugs panics, task leaks, sqlx errors. |
| `rust-tech-lead`              | Rust tech lead for code review, refactoring guidance, doc standards. Reviews for idiomatic Rust, error handling, ownership and async safety.            |
| `rust-security-engineer`      | OWASP Top 10 for Rust, JWT/Axum auth middleware review, input validation, `unsafe` audit, cargo-audit / cargo-deny dependency scanning.                 |
| `rust-performance-engineer`   | Tokio task leak and blocking-on-runtime detection, sqlx query tuning, flamegraph profiling, allocation and cloning analysis, connection pool sizing.    |
| `rust-observability-engineer` | Structured `tracing` logs + spans, OpenTelemetry/OTLP, Prometheus metrics, span propagation across tasks/brokers, tokio-console, graceful shutdown, sentry wiring. |
| `rust-reliability-engineer`   | `tokio::time::timeout` + tower timeout/retry/concurrency-limit layers, retries with backoff, JoinSet/Semaphore bounding, idempotency + transactional outbox, task-leak & channel-backpressure control, graceful shutdown. |
| `rust-test-engineer`          | Test strategies with `#[tokio::test]`, tower oneshot handler tests, testcontainers, mockall, proptest, and cargo nextest discipline for Rust/Axum services. |

## Workflow Skills

| Skill                              | Agent                         | Description                                                                                                                                       |
| ---------------------------------- | ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `task-rust-implement`              | `rust-engineer`               | End-to-end Rust/Axum/sqlx feature implementation. Generates migrations, repositories, services, handlers, DTOs, and tests; idempotency, webhooks. |
| `task-rust-review`                 | `rust-tech-lead`              | Staff-level code review umbrella - Phases A-E with Axum / sqlx / Tokio idioms; spawns perf / security / observability / reliability subagents in parallel for extra scopes. |
| `task-rust-review-perf`            | `rust-performance-engineer`   | Performance review for sqlx N+1, pool sizing, Tokio task leaks, `std::sync::Mutex` across `.await`, blocking on the runtime, allocation hotspots, migration safety. |
| `task-rust-review-security`        | `rust-security-engineer`      | Security review for Axum JWT/auth, validator DTOs, sqlx parameterization, mass assignment, `unsafe`, secrets, CORS, cargo-audit, OWASP Rust lens. |
| `task-rust-review-observability`   | `rust-observability-engineer` | Observability review for `tracing`, tracing-opentelemetry, OTel SDK, metrics-exporter-prometheus, tokio-console, sentry, graceful shutdown.       |
| `task-rust-review-reliability`     | `rust-reliability-engineer`   | Reliability review for tokio/tower timeouts, retries with backoff, JoinSet fan-out, task leaks, bounded channels and backpressure, sqlx pool bounds, idempotency/outbox, graceful shutdown. |
| `task-rust-test`                   | `rust-test-engineer`          | Test strategy and scaffolding using `#[tokio::test]`, tower `oneshot` handler tests, `#[sqlx::test]` / testcontainers PostgreSQL, mockall, proptest, insta, and cargo nextest. |

## Atomic Skills

| Skill                         | Description                                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| `rust-error-handling`         | Rust error patterns: thiserror for libraries, anyhow for applications, `?` and `From` conversions, panic policy, `Option` vs `Result`, boundary mapping to `IntoResponse`. |
| `rust-web-patterns`           | Axum 0.8 patterns: router and `AppState`, extractors, validator DTOs, consistent JSON envelopes, capped pagination, graceful shutdown, health/readiness. |
| `rust-db-access`              | Rust data access with sqlx: compile-time query macros, pool sizing, transactions, N+1 prevention, pagination, streaming, statement timeouts.      |
| `rust-migration-safety`       | Safe sqlx-cli migrations on PostgreSQL: lock risk, backfill safety, rollback coverage, expand-contract, `CONCURRENTLY`, `NOT VALID`.              |
| `rust-testing-patterns`       | Rust testing: `#[tokio::test]`, mockall trait mocks, testcontainers PostgreSQL, tower oneshot handler tests, proptest, fixture isolation.         |
| `rust-async-patterns`         | Tokio async patterns: runtime, JoinSet, `select!` cancel-safety, CancellationToken, spawn_blocking, blocking-in-async, `Send` bounds.             |
| `rust-concurrency`            | Rust shared state: `Arc`, std vs tokio `Mutex`/`RwLock`, mpsc/oneshot/broadcast/watch channels, atomics, ArcSwap, DashMap, rayon, `Send + Sync`, deadlocks. |
| `rust-messaging-patterns`     | Background work on a Postgres job table (`FOR UPDATE SKIP LOCKED`, enqueued inside the business transaction), Kafka via rdkafka, retry classification, DLQ, transactional outbox, in-process Tokio worker pools. |
| `rust-onboard-map`            | Cargo workspace layout, Cargo.toml features, async runtime, framework (Axum/Actix), DB layer (sqlx/sea-orm/diesel), clippy/rustfmt - injected into `task-onboard`. |
| `rust-overengineering-review` | Necessity review: validator-crate rules duplicating sqlx column types / DB / the type system, unreachable `match` arms, `Result` where `E` is never constructed, single-impl trait at the implementation (consumer-side traits are idiomatic), `Box<dyn Trait>` on a hot single call site, `Arc<Mutex<T>>` on never-mutated data, hot-loop `.clone()`, speculative `cfg(feature)`. Composed into `task-rust-review` Phase D. |
| `rust-security-patterns`      | Rust/Axum security pattern bank: default-deny router, JWT (alg / `iss` / `aud` pinning), IDOR scoping, serde mass-assignment prevention, sqlx parameterization, path traversal, command injection, webhook HMAC, argon2, secrets, SSRF, CORS, `unsafe`, cargo-audit / cargo-deny. Composed into `task-rust-implement`, `task-rust-review-security`. |

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
