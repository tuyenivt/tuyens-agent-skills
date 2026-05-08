---
name: rust-onboard-map
description: Rust project onboarding signals - Cargo workspace layout, Cargo.toml features, async runtime (tokio), framework (Axum/Actix), sqlx/sea-orm/diesel, and clippy/rustfmt. Used by task-onboard to map a Rust codebase for a new engineer.
metadata:
  category: backend
  tags: [onboarding, codebase-map, rust, axum, cargo, tokio]
user-invocable: false
---

# Rust Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Rust.

## When to Use

- A workflow needs Rust-specific orientation: workspace layout, Cargo features, async runtime, framework, DB layer.
- Project has `Cargo.toml`.

## Rules

- Identify single-crate vs workspace first: `[workspace]` in root `Cargo.toml` indicates multiple member crates.
- Identify Rust toolchain: `rust-toolchain.toml` or `rust-toolchain` file pins; otherwise `Cargo.toml` `rust-version`.
- Identify async runtime: `tokio` is dominant; `async-std` legacy; `smol` minor. Mixing runtimes does not work.
- Identify framework: Axum (modern, tower-based), Actix-Web (older, actor-style), Rocket (annotation-driven), Warp, plain hyper.
- Identify DB layer: sqlx (compile-time SQL), sea-orm (active record), diesel (compile-time DSL), refinery (migrations only).

## Patterns

### Build Inventory

| File                    | What it tells you                                                                       |
| ----------------------- | --------------------------------------------------------------------------------------- |
| `Cargo.toml`            | Single-crate or workspace root; deps; features; binary/library type                     |
| `Cargo.lock`            | Locked deps; commit for binaries, optional for libraries                                |
| `rust-toolchain.toml`   | Pins toolchain version, components (clippy, rustfmt), targets                           |
| `.cargo/config.toml`    | Cargo config: registry, build flags, target-specific options                            |
| `rustfmt.toml`          | Formatter config                                                                         |
| `clippy.toml`           | Linter config                                                                            |
| `Cross.toml`            | Cross-compilation config (when cross is used)                                            |
| `Dockerfile`            | Multi-stage: cargo-chef + sccache patterns common                                       |

### Bootstrap Path

1. Toolchain: `rustup` reads `rust-toolchain.toml` automatically. Confirm with `rustc --version`.
2. Build: `cargo build` (downloads deps from `crates.io`); `cargo build --release` for prod profile.
3. Local services: `compose.yml` for DB; required env in `.env.example`.
4. Migrations:
   - **sqlx:** `sqlx migrate run` (with `DATABASE_URL` set); `cargo sqlx prepare` to update offline cache (`.sqlx/`).
   - **sea-orm:** `sea-orm-cli migrate up`.
   - **diesel:** `diesel migration run`.
   - **refinery:** `refinery migrate -e DATABASE_URL files`.
5. Run: `cargo run` or `cargo run --bin <name>` for workspaces with multiple binaries.
6. Hot reload: `cargo-watch` (`cargo watch -x run`).
7. Verify: default port from config; `/health` if instrumented.

### Key File Inventory

**Single-crate (typical service):**

| Location                | Purpose                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `src/main.rs`           | Binary entry (or `src/bin/<name>.rs` for multi-binary)                   |
| `src/lib.rs`            | Library root if it is a library                                          |
| `src/routes/` or `src/handlers/` | HTTP handlers                                                   |
| `src/services/`         | Business logic                                                            |
| `src/models/` or `src/domain/` | Entities, DTOs                                                    |
| `src/db/` or `src/repository/` | DB access                                                         |
| `migrations/`           | SQL migration files (sqlx, refinery format)                                |
| `tests/`                | Integration tests (separate binary; runs with the public API)            |

**Workspace (multi-crate):**

| Location                       | Purpose                                                          |
| ------------------------------ | ---------------------------------------------------------------- |
| Root `Cargo.toml`              | `[workspace]` with `members = [...]`                            |
| `crates/<name>/Cargo.toml`     | Member crate                                                     |
| Path deps: `dep = { path = "..." }` | Internal cross-crate deps                                  |

### Conventions

- **Modules** declared via `mod` keyword; file system mirrors module tree.
- **`pub use` re-exports** for clean public APIs.
- **Result-and-error patterns:**
  - `anyhow::Error` (apps): erased, easy `?`.
  - `thiserror::Error` derive (libs): typed enums.
- **Logging:** `tracing` ecosystem (spans, structured fields) standard for async; `log` legacy.
- **Configuration:** `config` crate, `figment`, or hand-rolled `serde` + env. `dotenvy` for `.env` loading in dev.
- **Tests:** `#[cfg(test)] mod tests { ... }` inline; integration tests in `tests/`. `tokio::test` for async tests.
- **Linter/formatter:** `cargo clippy` (linter), `cargo fmt` (formatter); both run in CI typically.
- **Benchmarks:** `criterion` crate; `cargo bench`.

### Risk Hotspots Specific to Rust

- **Holding sync `MutexGuard` across `.await`:** deadlock risk; use `tokio::sync::Mutex` for async.
- **Spawning unowned futures:** `tokio::spawn(async {...})` without retaining the JoinHandle leaks if no shutdown coordination.
- **Mixing async runtimes:** Tokio future called inside async-std runtime panics.
- **Blocking calls in async context:** stalls the runtime worker; use `tokio::task::spawn_blocking`.
- **`unsafe` blocks:** must justify the invariant; rare in app code, more common in performance-sensitive libs.
- **Cargo features turning on/off behavior:** features like `feature = "tls"` change available types; mismatch between dependents causes subtle compile errors or runtime behavior shifts.
- **`sqlx` offline cache (`.sqlx/`)**: must commit and regenerate via `cargo sqlx prepare`; CI failures result from stale cache.
- **Blanket `Box<dyn Error>`** error types in app: lose type info at boundaries; `thiserror` enums are richer.
- **`String` cloning everywhere:** profile-time perf cost; consider `Arc<str>` or `Cow<'a, str>` for shared/borrowed.

### First-PR Safe Zones

- New route handler in existing `src/routes/`.
- New endpoint test in `tests/`.
- New error variant in app `Error` enum.
- New env var with safe default in config struct.

Riskier:

- `main.rs` - boot order matters.
- Cargo features - cascade across the dep graph.
- DB schema migrations - irreversible without explicit reverse.
- `unsafe` blocks - invariant changes can cause undefined behavior.

### Ecosystem Currency

- Rust 1.75+ for `async fn` in traits stabilized; 1.94+ latest stable.
- Tokio 1.x with stable API; major reorgs unlikely.
- Axum 0.7+ (axum 0.8 for newer); breaking changes between minors common.
- sqlx 0.7+ with `query!`/`query_as!` macros and `.sqlx/` offline cache.
- `tracing` standard; `log` only in older or no-std code.
- `anyhow` + `thiserror` is the canonical error pair.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** Rust toolchain version, async runtime (tokio), framework, DB layer, error stack (`anyhow`/`thiserror`), tracing/log, single-crate vs workspace.

**Local Bootstrap:** `cargo build`, env file, run command, default port, `cargo sqlx prepare` for sqlx projects.

**Architecture Map:** workspace member crates, module tree (`src/`), routes/handlers/services/db split.

**Conventions:** error type pattern, logging stack, config approach, test framework, clippy/rustfmt presence.

**Risk Hotspots:** sync-mutex-across-await, spawn lifetime, blocking in async, unsafe usage, sqlx cache freshness, feature flag fan-out.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating async-std and tokio code as interchangeable
- Glossing over `Cargo.toml` features - they fundamentally change the build
- Recommending `Box<dyn Error>` over typed errors in libraries
- Skipping the `.sqlx/` offline cache requirement for CI
- Confusing single-crate and workspace layouts when describing imports
- Recommending Actix-Web patterns on an Axum project
