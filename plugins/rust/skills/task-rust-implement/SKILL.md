---
name: task-rust-implement
description: Implement multi-layer Rust / Axum / sqlx feature end-to-end: migrations, models, repositories, services, handlers, DTOs, tests.
agent: rust-architect
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## When to Use

Building a new feature in a Rust/Axum/sqlx service that spans migration, repository, service, handler, DTO, and tests. Not for single-file edits, refactors without new behavior, or non-web crates (CLI, embedded).

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Step 2 and follow its mode contract; skip GATHER (and DESIGN when `plan.md` is present). Never edit spec artifacts from this workflow.

## Workflow

**Step 1 - Behavioral principles.** Use skill: `behavioral-principles`.

**Step 2 - Detect stack.** Use skill: `stack-detect`. Confirm Rust + Axum + sqlx; halt and ask if mismatched.

**Step 3 - Gather.** Ask: feature scope, entities (fields, relations, constraints), external integrations, background jobs/events, auth needs, status transitions, concurrency. Infer reasonable defaults from a brief or ticket and present for confirmation.

**Step 4 - Design.** Use skill: `rust-web-patterns` (API surface). Use skill: `rust-db-access` (data layer). Present a file tree and request approval before any code:

```
src/{models,repositories,services,handlers,dto}/<entity>.rs
src/{errors,router}.rs
migrations/YYYYMMDDHHMMSS_create_<entity>.{up,down}.sql
tests/integration/<entity>_test.rs
```

**Step 5 - Migration.** Use skill: `rust-migration-safety`. Generate up/down SQL with indexes on FKs and filtered columns; `CREATE INDEX CONCURRENTLY` for large tables.

**Step 6 - Data layer.** Use skill: `rust-db-access`. Repository trait in the service module; impl with `sqlx::query_as!` (compile-time checked); pool via `PgPoolOptions`.

**Step 7 - Service.** Use skill: `rust-error-handling`. Constructor injection via `Arc<dyn Trait>`; `thiserror` domain types; `?` propagation; transactions via `pool.begin()`/`tx.commit()` for multi-step mutations. Add when applicable:

- Async concurrency: Use skill: `rust-async-patterns`
- Shared mutable state: Use skill: `rust-concurrency`
- Jobs/events: Use skill: `rust-messaging-patterns`. Dispatch AFTER `tx.commit()`, never inside the transaction.

**Step 8 - HTTP layer.** Use skill: `rust-web-patterns`. Axum extractors (`Path`, `Query`, `Json`); response envelope; pagination on list endpoints. Implement `IntoResponse` for `AppError`:

| Domain Error       | HTTP |
| ------------------ | ---- |
| Validation         | 400  |
| Unauthorized       | 401  |
| Not found          | 404  |
| Conflict           | 409  |
| External timeout   | 503  |

**Step 9 - Tests.** Use skill: `rust-testing-patterns`. Service unit tests with `mockall` + `#[tokio::test]`; handler tests with `tower::ServiceExt::oneshot`; integration tests with `testcontainers`. Cover happy path, validation, not-found, conflict.

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

[file names; tables, indexes, constraints created]
```

## Self-Check

- [ ] Step 1-2: behavioral principles loaded; stack confirmed Rust/Axum/sqlx
- [ ] Step 3-4: requirements gathered; design and file tree approved before code
- [ ] Step 5: migration has up/down and indexes on FKs/filtered columns
- [ ] Step 6: repository trait in service module; `query_as!` compile-time checked
- [ ] Step 7: `Arc<dyn Trait>` injection; `thiserror` + `?`; jobs/events dispatched after `tx.commit()`
- [ ] Step 8: handlers thin; `IntoResponse` maps domain errors to HTTP; list endpoints paginated
- [ ] Step 9: unit + handler + integration tests cover happy/validation/not-found/conflict
- [ ] Step 10: `cargo build`, `cargo test`, `cargo clippy -- -D warnings` pass

## Avoid

- Business logic in handlers - delegate to services
- `.unwrap()`/`.expect()` in production paths - use `?` + `thiserror`
- Dispatching jobs/events inside a DB transaction - worker races commit
- Blocking the Tokio runtime with sync I/O - use `spawn_blocking`
- Returning raw sqlx models from endpoints - map to response DTOs
- Unpaginated list endpoints
- Generating code before design approval
