---
name: rust-onboard-map
description: "Map Rust onboarding signals: Cargo workspace, features, tokio/async-std, Axum/Actix, sqlx/sea-orm/diesel, clippy/rustfmt."
metadata:
  category: backend
  tags: [onboarding, codebase-map, rust, axum, cargo, tokio]
user-invocable: false
---

# Rust Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is Rust.

## When to Use

Workflow needs Rust-specific orientation: workspace layout, Cargo features, async runtime, framework, DB layer. Project has `Cargo.toml`.

## Rules

- Detect single-crate vs workspace first - `[workspace]` in root `Cargo.toml` indicates members; layout and import semantics differ.
- Detect toolchain: `rust-toolchain.toml` pins exactly; otherwise `Cargo.toml` `rust-version` is a minimum.
- Detect async runtime - tokio dominant, async-std legacy, smol minor. Runtimes do not mix.
- Detect framework: Axum (tower-based), Actix-Web (actor), Rocket, Warp, plain hyper.
- Detect DB layer: sqlx (compile-time SQL + `.sqlx/` cache), sea-orm (active record), diesel (DSL), refinery (migrations only).
- Detect error stack: `anyhow` (apps, erased) vs `thiserror` (libs, typed enums).

## Patterns

### Build Inventory

| File                  | What it tells you                                              |
| --------------------- | -------------------------------------------------------------- |
| `Cargo.toml`          | Crate vs workspace, deps, features, bin/lib type               |
| `Cargo.lock`          | Locked deps (commit for binaries)                              |
| `rust-toolchain.toml` | Pinned toolchain, components (clippy, rustfmt), targets        |
| `.cargo/config.toml`  | Registry, build flags, target-specific options                 |
| `rustfmt.toml` / `clippy.toml` | Format/lint config                                    |
| `.sqlx/`              | sqlx offline query cache (must be in sync with code)           |
| `Dockerfile`          | Often cargo-chef + sccache for layer caching                   |

### Bootstrap

1. Toolchain: `rustup` reads `rust-toolchain.toml` automatically; confirm `rustc --version`.
2. Build: `cargo build` (deps from crates.io); `--release` for prod profile.
3. Local services: `compose.yml` for DB; required env in `.env.example`.
4. Migrations: sqlx `sqlx migrate run` + `cargo sqlx prepare` | sea-orm `sea-orm-cli migrate up` | diesel `diesel migration run` | refinery `refinery migrate -e DATABASE_URL files`.
5. Run: `cargo run` or `cargo run --bin <name>` for multi-binary workspaces.
6. Hot reload: `cargo-watch` (`cargo watch -x run`).
7. Verify: default port from config; `/health` if instrumented.

### Key Files

**Single-crate**

| Location                                | Purpose                                                |
| --------------------------------------- | ------------------------------------------------------ |
| `src/main.rs`                           | Binary entry (or `src/bin/<name>.rs`)                  |
| `src/lib.rs`                            | Library root (enables tests under `tests/`)            |
| `src/routes/` or `src/handlers/`        | HTTP handlers                                          |
| `src/services/`                         | Business logic                                         |
| `src/models/` or `src/domain/`          | Entities, DTOs                                         |
| `src/db/` or `src/repository/`          | DB access                                              |
| `migrations/`                           | SQL migrations (sqlx, refinery)                        |
| `tests/`                                | Integration tests (each file a separate binary)        |

**Workspace**

| Location                            | Purpose                                |
| ----------------------------------- | -------------------------------------- |
| Root `Cargo.toml`                   | `[workspace] members = [...]`          |
| `crates/<name>/Cargo.toml`          | Member crate                           |
| `dep = { path = "..." }`            | Internal cross-crate deps              |

### Module Layout

- **Layer-module** (small services): `src/{handlers,services,repository,models}/` grouped by stereotype. Easy by stereotype, hard by feature.
- **Feature-module** (medium+): `src/orders/{handler,service,repository,model}.rs` + `mod.rs` with small `pub use` surface. Cross-feature imports go through service interfaces.
- **DDD / hexagonal**: `src/<domain>/{domain,application,adapters}/`. `domain/` is pure Rust - no `axum`/`sqlx` imports.
- **Workspace multi-binary**: `crates/{api,worker,migrate}/` + shared `crates/{core,domain}/`. Each `main.rs` is wire-up only.

`src/main.rs` (or `crates/<bin>/src/main.rs`) is always thin (config, `AppState`, server start). Binary crates are not importable - shared logic belongs in `src/lib.rs` or a library crate.

### Conventions

- **Modules** via `mod` keyword; file tree mirrors module tree. `pub use` re-exports for clean APIs.
- **Errors:** `anyhow::Error` (apps) for erased `?` flow; `thiserror` derive (libs) for typed enums.
- **Logging:** `tracing` (spans, structured) standard for async; `log` legacy.
- **Config:** `config`, `figment`, or `serde` + env; `dotenvy` for `.env` in dev.
- **Tests:** `#[cfg(test)] mod tests` inline + integration in `tests/`; `#[tokio::test]` for async.
- **Lint/format:** `cargo clippy`, `cargo fmt`; both gated in CI typically.
- **Benchmarks:** `criterion` + `cargo bench`.

### Risk Hotspots

- **Async lifetime + cancellation** (sync `MutexGuard` across `.await`, unowned `tokio::spawn`, blocking calls on the runtime, missing `CancellationToken`, mixed runtimes): see `rust-async-patterns`, `rust-concurrency`.
- **Data access** (N+1, missing `LIMIT`, I/O inside transactions, stale `.sqlx/` cache): see `rust-db-access`.
- **Background dispatch inside transaction**, payloads carrying owned domain models: see `rust-messaging-patterns`.
- **Security** (mass assignment, SQL injection, unaudited `unsafe`, JWT misvalidation, `Command::new("sh")`): see `rust-security-patterns`.
- **Migrations** (concurrent index, lock_timeout, expand-then-contract, missing `cargo sqlx prepare`): see `rust-migration-safety`.
- **Rust footguns**: `Box<dyn Error>` at domain boundaries, `.clone()` churn on hot paths, feature mismatches across dependents, `unsafe` without `// SAFETY:` comment.

### First-PR Safe Zones

Safe: new handler in `src/routes/`, new integration test in `tests/`, new error variant in app `Error` enum, new env var with safe default.

Riskier: `main.rs` (boot order), Cargo features (cascade across dep graph), schema migrations (irreversible without reverse), `unsafe` blocks (invariant changes cause UB).

### Ecosystem Currency

- Rust 1.94+ latest stable; `async fn` in traits stable since 1.75.
- Axum 0.7+/0.8; breaking changes between minors common.
- sqlx 0.7+ with `query!`/`query_as!` macros and `.sqlx/` offline cache.
- `anyhow` + `thiserror` canonical error pair.

## Output Format

Inject into `task-onboard` sections:

- **Stack and Tooling**: Rust toolchain version, single-crate vs workspace, async runtime, framework, DB layer, migration tool, error stack, logging.
- **Local Bootstrap**: build command, env file, run command, default port, `cargo sqlx prepare` if sqlx, health-check.
- **Architecture Map**: workspace members (if any), module layout style, routes/services/db split, `lib.rs` presence.
- **Conventions**: error pattern, logging, config approach, test layout, clippy/rustfmt status.
- **Risk Hotspots**: async-mutex-across-await, spawn lifetime, blocking-in-async, `unsafe` usage, sqlx cache freshness, feature fan-out.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Treating async-std and tokio code as interchangeable
- Glossing over Cargo features - they change which code compiles
- Recommending `Box<dyn Error>` over typed errors in libraries
- Skipping `.sqlx/` offline cache freshness for CI
- Confusing single-crate and workspace import semantics
- Recommending Actix-Web patterns on an Axum project
