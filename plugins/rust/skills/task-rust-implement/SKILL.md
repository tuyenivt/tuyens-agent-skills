---
name: task-rust-implement
description: Implement multi-layer Rust / Axum / sqlx feature end-to-end - migration, repository, service, handler, DTO, tests, idempotency, webhooks.
agent: rust-architect
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Spec-aware mode.** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Step 2. Follow its contract; skip Step 3 (and Step 4 when `plan.md` is present). Never edit spec artifacts.

## When to Use

Building a new feature in a Rust/Axum/sqlx service that spans migration, repository, service, handler, DTO, and tests.

Not for: single-file edits, bugfixes (`task-rust-debug`), refactors without new behavior (`task-rust-refactor`), non-web crates.

## Workflow

**Step 1 - Behavioral principles.** Use skill: `behavioral-principles`.

**Step 2 - Detect stack.** Use skill: `stack-detect`. Confirm Rust + Axum + sqlx; halt and ask if mismatched.

**Step 3 - Gather.** Ask before writing code; do not guess:

1. Feature scope and primary use case
2. Entities (fields, relations, constraints, status transitions)
3. External integrations (HTTP/Stripe/etc.)
4. Background jobs / async events
5. AuthN / AuthZ requirements
6. Idempotency requirements (retryable POSTs, event consumers)
7. Webhooks (signature scheme, raw body, route placement)
8. Concurrency / ordering needs

**Step 4 - Design (approval gate).** Use skill: `rust-web-patterns` (API surface). Use skill: `rust-db-access` (data layer). Present file tree and decisions; wait for approval:

```
src/{models,repositories,services,handlers,dto}/<entity>.rs
src/{errors,router}.rs
migrations/YYYYMMDDHHMMSS_create_<entity>.{up,down}.sql
tests/integration/<entity>_test.rs
```

Decisions to confirm: endpoints (method/URI/status/DTOs), schema (indexes, FKs, CHECK, idempotency unique), service methods and transaction boundaries, error model, idempotency strategy, webhook design, job dispatch points.

**Step 5 - Migration.** Use skill: `rust-migration-safety`. Use skill: `backend-db-indexing`. up/down SQL; index FKs and filtered columns; `CREATE INDEX CONCURRENTLY` for large tables; CHECK constraints for status; unique index for idempotency keys.

**Step 6 - Data layer.** Use skill: `rust-db-access`. Repository trait in the service module; impl with `sqlx::query_as!` (compile-time checked); pool via `PgPoolOptions`. Use `ON CONFLICT DO NOTHING` / `DO UPDATE` for idempotent upserts.

**Step 7 - Service.** Use skill: `rust-error-handling`. Constructor injection via `Arc<dyn Trait>`; `thiserror` domain types; `?` propagation; `pool.begin()`/`tx.commit()` for multi-step writes. Apply when relevant:

- Idempotency: Use skill: `backend-idempotency`. Atomic check-and-act inside the same transaction.
- Async / cancellation: Use skill: `rust-async-patterns`.
- Shared mutable state: Use skill: `rust-concurrency`.
- Jobs / events: Use skill: `rust-messaging-patterns`. Dispatch AFTER `tx.commit()`, never inside the transaction.
- External APIs: wrap with `tokio::time::timeout`; classify at the gateway; trait for testability.

**Step 8 - HTTP layer.** Use skill: `rust-web-patterns`. Use skill: `rust-security-patterns`. Axum extractors (`Path`, `Query`, `Json`); validator-crate DTOs with `#[serde(deny_unknown_fields)]`; response envelope; pagination on list endpoints. Implement `IntoResponse` for `AppError`:

| Domain Error       | HTTP |
| ------------------ | ---- |
| Validation         | 400  |
| Unauthorized       | 401  |
| Not found          | 404  |
| Conflict           | 409  |
| Invalid transition | 422  |
| External timeout   | 503  |

Webhooks: signature-verifying middleware reads the raw body before any JSON deserialization; route lives outside the JWT auth group.

**Step 9 - Tests.** Use skill: `rust-testing-patterns`. Service unit tests with `mockall` + `#[tokio::test]`; handler tests with `tower::ServiceExt::oneshot`; integration tests with `testcontainers`. Cover happy path, validation, not-found, conflict, timeout. Webhooks: valid / invalid / missing signature. Idempotency: duplicates return the same result. State transitions: every valid + invalid.

**Step 10 - Validate.** Run `cargo build`, `cargo test`, `cargo clippy -- -D warnings`. Fix failures before reporting.

## Output Format

```markdown
## Files Generated

[grouped by layer: migrations, models, repositories, services, handlers, dto, errors, tests]

## Endpoints

| Method | Path | Request | Response | Status |
| ------ | ---- | ------- | -------- | ------ |
| ...    | ...  | ...     | ...      | ...    |

## Tests

- Unit: {count} (service, mockall)
- Handler: {count} (axum oneshot)
- Integration: {count} (testcontainers)

## Migration

[file names; tables, indexes, constraints, idempotency unique]
```

## Self-Check

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Rust/Axum/sqlx
- [ ] Step 3: scope, entities, auth, idempotency, webhooks, jobs gathered
- [ ] Step 4: design and file tree approved before any code
- [ ] Step 5: migration has up/down, FK and filter indexes, CHECKs, idempotency unique
- [ ] Step 6: repository trait in service module; `query_as!` compile-time checked
- [ ] Step 7: `Arc<dyn Trait>` injection; `thiserror` + `?`; jobs/events dispatched after `tx.commit()`; idempotency atomic when applicable
- [ ] Step 8: handlers thin; validator DTOs with `deny_unknown_fields`; `IntoResponse` maps domain errors; list endpoints paginated; webhook outside JWT group with raw-body signature check
- [ ] Step 9: unit + handler + integration cover happy/validation/not-found/conflict/timeout; webhooks and idempotency tested when applicable
- [ ] Step 10: `cargo build`, `cargo test`, `cargo clippy -- -D warnings` pass

## Avoid

- Business logic in handlers - delegate to services
- `.unwrap()`/`.expect()` in production paths - use `?` + `thiserror`
- Dispatching jobs/events inside a DB transaction - worker races commit
- Blocking the Tokio runtime with sync I/O or CPU-bound hashing - use `spawn_blocking`
- Returning raw sqlx models from endpoints - map to response DTOs
- `Json` extractor on webhook routes - signature check needs the raw body
- Mass-assignment DTOs (`serde_json::Value`, `#[serde(flatten)]` on writes)
- Unpaginated list endpoints
- Generating code before design approval
