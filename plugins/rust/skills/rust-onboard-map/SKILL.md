---
name: rust-onboard-map
description: "Map Rust onboarding signals: Cargo workspace, features, tokio, Axum/Actix, sqlx/sea-orm/diesel, clippy/rustfmt - injected into task-onboard."
metadata:
  category: backend
  tags: [onboarding, codebase-map, rust, axum, cargo, tokio]
user-invocable: false
---

# Rust Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is Rust. Emits Rust-specific signals into host workflow sections; does not re-establish bootstrap, safe-zone, or operational concepts the host already owns.

## When to Use

`task-onboard` detected Rust (`Cargo.toml` present). Output feeds Stack, Local Quickstart, Architecture, Patterns, Tech Debt, and First-PR sections of the host report.

## Rules

- Classify layout from root `Cargo.toml`: `[workspace]` present -> workspace (enumerate members and their `[[bin]]`/`[lib]`); else single-crate.
- Toolchain source: `rust-toolchain.toml` `channel` (exact pin like `1.84.0`, or a floating channel like `stable`/`nightly`) vs `Cargo.toml` `rust-version` (minimum). Report which; for a floating channel say `pinned-channel via rust-toolchain.toml` not an exact version.
- Runtime is the effective async runtime, single-valued: tokio | async-std | smol | none. Report the runtime even when pulled transitively by the framework (e.g. actix-web -> tokio). Do not list multiple - mixing distinct runtimes is a bug, flag if seen.
- Framework, DB layer, error stack are each single-valued from `Cargo.toml` deps - pick the dominant one, name overrides explicitly.
- Per-crate features: list non-default features actually enabled by binary crates or `default-features = false` overrides. Features change which code compiles - silently listing "has features" is useless.
- `.sqlx/` cache must exist if `sqlx::query!`/`query_as!` macros are used and CI runs offline. Flag mismatch as Tech Debt.
- Hexagonal/DDD detection: a `domain/` or `core/` crate (or module) with zero `axum`/`sqlx`/`reqwest` imports. Cite by checking its `Cargo.toml` deps, not just the directory name. A project can be both a workspace and hexagonal - report `hexagonal` for Pattern when a pure domain crate is confirmed (it is the stronger architectural signal); the workspace shape still shows in Layout and member roles.

## Patterns

### Detection Signals

| Signal                     | Source                                                       | Maps to                            |
| -------------------------- | ------------------------------------------------------------ | ---------------------------------- |
| Workspace                  | `[workspace] members = [...]` in root `Cargo.toml`           | Stack: layout                      |
| Toolchain pin              | `rust-toolchain.toml` `channel`                              | Stack: language version            |
| Runtime                    | `tokio` / `async-std` / `smol` in `[dependencies]`           | Stack: async                       |
| Framework                  | `axum` / `actix-web` / `rocket` / `warp` / `hyper` direct    | Stack: framework                   |
| DB layer                   | `sqlx` / `sea-orm` / `diesel` direct dep                     | Stack: database                    |
| Migrations                 | `migrations/` + (`sqlx-cli` / `sea-orm-cli` / `diesel_cli`)  | Operational: migrations            |
| Error stack                | `thiserror` (libs) + `anyhow` (apps) in deps                 | Patterns: errors                   |
| Logging                    | `tracing` (+ `tracing-subscriber`) vs `log` + `env_logger`   | Patterns: logging                  |
| Config                     | `config` / `figment` / `serde` + env + `dotenvy`             | Patterns: config                   |
| Per-crate bin/lib          | `[[bin]]`, `[lib]`, or `src/main.rs` / `src/lib.rs`          | Architecture: crate roles          |
| Hexagonal split            | `domain` crate has no web/db deps in its `Cargo.toml`        | Architecture: pattern              |
| sqlx offline cache         | `.sqlx/*.json` files present                                 | Tech Debt: cache freshness         |
| Lint/format gates          | `clippy.toml` / `rustfmt.toml` + CI invoking them            | Conventions                        |

### Layout Variants

| Variant                | Indicators                                                          |
| ---------------------- | ------------------------------------------------------------------- |
| Single-crate, layered  | `src/{handlers,services,repository,models}/`                        |
| Single-crate, feature  | `src/<feature>/{handler,service,repo,model}.rs` + `mod.rs`          |
| Workspace multi-binary | `crates/{api,worker,migrate}/` bins + `crates/{core,domain}/` libs  |
| Hexagonal              | `domain/` pure crate/module; adapters live in `infra/` or `api/`    |

`src/main.rs` (or `crates/<bin>/src/main.rs`) is wire-up only - config load, `AppState`, server start. Binary crates are not importable; shared code belongs in a library crate or `src/lib.rs`.

### Rust-Typical Risk Hotspots

Cross-reference and cite path evidence:

- `std::sync::Mutex`/`MutexGuard` held across `.await`, blocking calls (`std::fs`, `reqwest::blocking`) on the runtime, detached `tokio::spawn` without `JoinHandle` tracking, mixed runtimes -> `rust-async-patterns`, `rust-concurrency`.
- `sqlx::query!` strings drifted from `.sqlx/` cache, N+1 from per-row queries in a loop, transactions wrapping HTTP/IO calls -> `rust-db-access`.
- Side-effect dispatch (Kafka/HTTP) inside an open transaction -> `rust-messaging-patterns`.
- Mass assignment via `serde_json::from_value` into entity, `unsafe` block without `// SAFETY:` comment, JWT verified without `aud`/`exp`, `Command::new("sh")` -> `rust-security-patterns`.
- Migration uses `CREATE INDEX` (non-concurrent) on large table, no `lock_timeout`, no expand/contract, missing `cargo sqlx prepare` in CI -> `rust-migration-safety`.
- Cargo features: `default-features = false` in one consumer but transitively re-enabled by another; feature unification across workspace can quietly pull in heavy deps.

### Rust-Typical First-PR Areas

Safe: new handler in `src/routes/` or new method on an existing service, new integration test in `tests/`, new variant on an app `Error` enum (anyhow apps are even more forgiving), new env var with a default.

Riskier: `main.rs` / wire-up (boot ordering), Cargo features (cascade across the workspace dep graph), schema migrations (irreversible without an explicit down), `unsafe` blocks (UB on invariant change), trait signature changes in a published library crate (semver break).

## Output Format

Emit the following keyed signals for `task-onboard` to merge into its report sections. Use the exact enums shown; mark `unknown` rather than guessing.

```
### Stack and Tooling
- Layout: {single-crate | workspace(<N> members)}
- Toolchain: <version-or-channel> ({pinned via rust-toolchain.toml | pinned-channel via rust-toolchain.toml | min via Cargo.toml rust-version})
- Runtime: {tokio | async-std | smol | none}
- Framework: {axum | actix-web | rocket | warp | hyper | none}
- DB layer: {sqlx | sea-orm | diesel | refinery | none}
- Migrations: {sqlx-cli | sea-orm-cli | diesel_cli | refinery | none}
- Error stack: {anyhow | thiserror | anyhow+thiserror | std::error::Error | custom}
- Logging: {tracing | log | none}
- Config: {config | figment | serde+env | none}
- Lint/format gates in CI: {clippy:yes/no, rustfmt:yes/no}

### Local Bootstrap (commands only; host owns narrative)
- build: `cargo build`
- run: `cargo run` | `cargo run --bin <name>`
- migrate: <one of: `sqlx migrate run` | `sea-orm-cli migrate up` | `diesel migration run` | `refinery migrate -e DATABASE_URL files`>
- sqlx offline prep (if sqlx): `cargo sqlx prepare` (append `--workspace` only for a Cargo workspace)
- watch: `cargo watch -x run` if `cargo-watch` in dev-deps, else omit this line
- default port: <from config or `unknown`>; health: <`/health` if instrumented or `unknown`>

### Architecture
- Pattern: {layered | feature-module | hexagonal | workspace-multi-binary}
- Workspace members (if any): <crate -> role (bin|lib) -> purpose one-liner>
- lib.rs present: {yes | no}; binary entry: <path>

### Conventions
- Errors: <observed pattern + path>
- Logging: <library + path>
- Config: <library + path>
- Tests: <unit inline / integration in `tests/` / `#[tokio::test]` usage>

### Risk Hotspots (only those observed; cite paths)
- <hotspot>: <path> -> see `<atomic skill>`

### First-PR Safe Zones (Rust-typical, intersect with observed structure)
- <area>: <path>
```

## Avoid

- Listing multiple async runtimes as if interchangeable (mixing is a bug).
- Reporting "features: present" without naming the enabled features per binary crate.
- Reproducing host-workflow narrative (bootstrap prose, generic safe-zone definitions, operational sections).
- Recommending Actix-Web patterns on an Axum project (or vice versa).
- Treating directory names alone as evidence of hexagonal split - check the crate's `Cargo.toml` deps.
- Skipping `.sqlx/` freshness check when `sqlx::query!` macros are used.
