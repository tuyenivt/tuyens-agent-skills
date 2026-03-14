---
name: task-rust-new
description: End-to-end Rust/Axum feature implementation workflow. Generates all layers from migration to HTTP handler with full test coverage. Use for new features requiring multiple coordinated layers. Not for single-file fixes or isolated bug fixes (use task-rust-debug for errors).
agent: rust-architect
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - GATHER: feature, affected modules, external deps, async/concurrency needs

STEP 2 - DESIGN: propose structure, traits, data flow. Load rust-web-patterns, rust-db-access. Present for approval.

STEP 3 - DATABASE: load rust-migration-safety, generate migrations

STEP 4 - DATA LAYER: repository trait + impl (sqlx)

STEP 5 - BUSINESS LOGIC: service with constructor injection, error types (load rust-error-handling). If async concurrency: load rust-async-patterns. If concurrent shared state: load rust-concurrency. If background jobs or async messaging: load rust-messaging-patterns.

STEP 6 - HTTP LAYER: Axum handlers, middleware, routes

STEP 7 - TESTS: load rust-testing-patterns. Unit + integration + tokio::test.

STEP 8 - VALIDATE: cargo build, cargo test, cargo clippy

OUTPUT: file list, endpoint summary, test count

## Self-Check

- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, repository, service, handler, routes, tests
- [ ] Constructor injection via function parameters; errors use thiserror/anyhow
- [ ] No unbounded spawns; repository trait defined in service module
- [ ] `cargo build`, `cargo test`, and `cargo clippy` all pass
- [ ] Migration includes indexes; list endpoints paginated; file list and test count presented
