---
name: rust-onboard-map
description: "Rust onboarding signals - Cargo workspace, toolchain/edition, features, Tokio, Axum, sqlx offline cache, clippy/rustfmt/cargo-deny, observability."
metadata:
  category: backend
  tags: [onboarding, codebase-map, rust, axum, cargo, tokio, sqlx]
user-invocable: false
---

# Rust Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when `Language` is Rust **or** stack-detect finds a `Cargo.toml` in a service directory it scans (a fullstack monorepo with a React root puts Rust in `Additional`). When Rust is the primary stack, a `## Tech Stack` declaration wins over tree inference for Framework, Database, ORM and Test framework (stack-detect precedence); when the tree disagrees, report `<declared> (tree shows <inferred>)`. When Rust sits in `Additional`, those scalar fields describe the primary stack and every Rust value comes from the tree. The toolchain is `rust-toolchain.toml` (or a legacy extensionless `rust-toolchain`); a `Language:` line naming another version follows it as `(declared: <value>)`.

## When to Use

- A workflow needs Rust-specific orientation: crate layout, toolchain, framework, features, DB layer, observability
- Project has `Cargo.toml`

## Rules

- Report the toolchain verbatim: `rust-toolchain.toml` `channel` (an exact `1.94.0`, or a floating `stable` / `nightly` - say "floating"), `Cargo.toml` `rust-version` (the MSRV cargo enforces; an older toolchain fails the build), and `edition` (`2024` needs Rust 1.85+). State a support position only if the current stable release is known from the environment; otherwise report the values and skip the judgment rather than inventing a release number
- Identify framework, single-valued: Axum / actix-web / Rocket / warp / bare hyper / none; and the async runtime: Tokio / async-std / smol / none, even when pulled in by the framework. Two runtimes in one binary is a finding, not a list
- Identify the DB layer: sqlx / SeaORM / Diesel (+ `diesel-async`) / tokio-postgres; with sqlx, whether queries are the checked macros (`query!`, `query_as!`) or runtime `query()` - the macros need a live `DATABASE_URL` or the `.sqlx/` offline cache at compile time, and a pre-0.7 `sqlx-data.json` is stale
- Identify the layout convention (drives where new code lands). Report every convention that applies: the module convention, and orthogonally single crate, multi-binary crate (`src/bin/`), or a Cargo workspace. In a workspace, report the root first - `resolver` (a virtual manifest has no edition to infer it from, so an unset one is resolver 1 - cargo warns only when a member is on edition 2021 or later), `[workspace.package]`, `[workspace.dependencies]`, `[workspace.lints]` - then each member's role (bin / lib), framework, DB layer and which sibling crates it depends on; flag members that bypass `workspace = true` for a shared dependency (version skew)
- Features are Rust's build tags: grep `[features]` and `cfg(feature = ...)`. Code behind a non-default feature is excluded from `cargo build` / `cargo test` unless `--features` / `--all-features` names it - report what CI passes; a feature declared that no `cfg` reads is `defined but unused: <feature>`; a `cfg(feature = "x")` with no declared `x` is flagged by the `unexpected_cfgs` lint. Note a member whose `default-features = false` a sibling undoes (features unify across crates built together). Without filesystem access, say the feature surface is unverified
- Deps: a committed `Cargo.lock` lets CI build `--locked`; absent on a binary is a finding. `vendor/` plus a `[source]` replacement in `.cargo/config.toml` builds offline. Name what `build.rs` generates (`prost-build` / `tonic-build` need `protoc`) and each native dependency (`openssl-sys`: OpenSSL headers + `pkg-config` unless rustls features are chosen; `rdkafka`: a C toolchain + `make` for its bundled librdkafka, `cmake` only under the `cmake-build` feature)
- Report the test surface as its own fact: inline `#[cfg(test)]` modules, `tests/` integration files, `#[sqlx::test]`, doctests, feature-gated suites, nextest config (`.config/nextest.toml`), or none at all - per member in a workspace. "This codebase has no tests" is a top-three onboarding fact, not a footnote

## Patterns

### Build Inventory

| File | What it tells you |
| ---- | ----------------- |
| `Cargo.toml` | `edition`, `rust-version`, dependencies, `[features]`, `[[bin]]`, `[lints]`; at a workspace root, members and shared tables |
| `Cargo.lock` | Exact resolved versions; whether `--locked` builds are possible |
| `rust-toolchain.toml` | Toolchain channel, `components` (clippy, rustfmt), `targets` |
| `Cargo.toml` + `src/main.rs` (or `src/bin/*.rs`) | Logging / Observability: `tracing` + `tracing-subscriber`, OpenTelemetry crates, `metrics` / `prometheus`, and where the subscriber is installed |
| `Cargo.toml` + the compose file | Queue / Broker: the client crate (`rdkafka`, `lapin`, `apalis`, a `jobs` table) and the service it connects to |
| `.cargo/config.toml` | Aliases, `[env]`, `rustflags`, linker, source replacement |
| `build.rs` | Build-time codegen and native dependencies |
| `.sqlx/` | sqlx offline query cache; stale against the queries means `SQLX_OFFLINE=true` builds fail |
| `migrations/` | sqlx-cli (`<timestamp>_name.sql`, or `.up.sql` / `.down.sql` pairs from `-r`), Diesel (`<dir>/up.sql` + `down.sql`), or SeaORM (a `migration` crate) |
| `clippy.toml`, `rustfmt.toml` / `.rustfmt.toml`, `deny.toml`, `.cargo/audit.toml` | Lint and supply-chain bar: clippy levels may also sit in `[lints.clippy]`; what is enforced is what CI runs (`-D warnings`) |
| `Makefile` / `justfile` / `cargo xtask` | Project commands |
| `Dockerfile` | Multi-stage build (often `cargo-chef` for layer caching; musl or distroless runtime) |
| `.github/workflows/*.yml`, `.gitlab-ci.yml` | CI: test runner (`cargo test` / nextest), features, `--locked`, clippy, fmt, audit - the `CI / Deploy` source |
| `k8s/`, `deploy/`, `Dockerfile` | Deploy target; a mismatch between them (binary name, port, probe path, features built) is reported under `CI / Deploy` |

### Bootstrap Path

1. Toolchain: rustup reads `rust-toolchain.toml` in the directory; with none, the MSRV in `rust-version` is the floor
2. System deps: native libraries `build.rs` or `-sys` crates need (OpenSSL + `pkg-config`, `cmake`, `protoc`)
3. Local services: `compose.{yaml,yml}` / `docker-compose.{yaml,yml}`; env vars in `.env.example`, and how they load (`dotenvy`, `direnv`, exported by hand)
4. Database: `sqlx database create` then `sqlx migrate run` (sqlx-cli, both reading `DATABASE_URL`), `diesel migration run`, the SeaORM migration crate's `cargo run -p migration -- up`, or `sqlx::migrate!()` run on boot - say which
5. Build: `cargo build --locked`; with sqlx macros and no reachable database, `SQLX_OFFLINE=true` against a committed `.sqlx/`, and `cargo sqlx prepare` (add `--workspace` in a workspace) after query changes
6. Run: one line per binary - `cargo run --bin <name>` / `cargo run -p <crate>` with its port; `cargo watch -x run` or `bacon` for reload when the repo uses them
7. Verify: `/health` or `/healthz`; if neither exists, the first routed endpoint

### Crate Layout

`src/main.rs` (or `src/bin/<name>.rs`) should be thin - config, tracing setup, `AppState`, router, serve. Business logic or a route table in `main.rs` is a smell to report, not a convention to assume; a binary crate is not importable, so testable code lives in `src/lib.rs` or a library crate.

| Convention | Shape | When |
| ---------- | ----- | ---- |
| **Layer-module** | `src/{handlers,services,repository,models}/` | Default for < ~5 domains; tutorials. A mixed tree reports the dominant convention first (`layer-module, one feature module: billing/`) |
| **Feature-module** | `src/orders/{handler,service,repo,model}.rs` | Recommended for medium+ services |
| **Flat** | `src/main.rs` plus a few sibling modules (`db.rs`, `routes.rs`) | A service too small to show either convention - report `flat` |
| **Hexagonal** | a `domain` crate (or module) with no `axum` / `sqlx` / `reqwest` in its dependencies; adapters in `infra/` or `api/` | Teams enforcing ports and adapters - confirm from the crate's `Cargo.toml`, not the directory name |
| **Multi-binary** | `src/bin/{api,worker}.rs` or `crates/{api,worker,migrate}/` + shared library crates | One repo serves API + workers |
| **Cargo workspace** | root `[workspace]` + `crates/*/Cargo.toml`, each member with its own layout | Independently built crates in one repo |

The last two rows are orthogonal to the module convention; report every row that applies. `pub(crate)` enforces a boundary inside a crate; only a crate split makes it a dependency-graph rule - name which one the repo relies on.

### Risk Hotspots (delegate depth to dedicated skills)

- `std::sync::Mutex` guard held across `.await`, blocking calls (`std::fs`, `reqwest::blocking`, CPU-heavy hashing) on the runtime, detached `tokio::spawn`, shutdown without drain -> `rust-async-patterns`
- Shared state, lock ordering, `Arc<Mutex<_>>` contention, unbounded channels -> `rust-concurrency`
- N+1 per-row queries, pool config, transactions held across HTTP calls, `.sqlx/` drift -> `rust-db-access`
- Broker calls inside transactions, models in payloads, auto-commit consumers -> `rust-messaging-patterns`
- Mass assignment, `format!` into SQL, JWT without `aud` / `exp`, `unsafe` without `// SAFETY:`, `Command::new("sh")`, no `cargo audit` gate -> `rust-security-patterns`
- Non-concurrent index builds on hot tables, no `lock_timeout`, migrations run on every replica's boot -> `rust-migration-safety`
- `unwrap()` / `expect()` on request paths, errors that leak internals in responses -> `rust-error-handling`
- Route added after its auth layer, missing body limit, middleware order -> `rust-web-patterns`
- Tests sharing a `static` pool, SQLite standing in for Postgres, integration suites CI never runs -> `rust-testing-patterns`

### First-PR Safe Zones

Scope to the observed layout, not the generic defaults. For a feature-module crate, that means a new file in `src/<feature>/`; for hexagonal, a new use case in the domain crate or a new adapter.

Generic safe zones (replace with concrete equivalents from the tree):
- New handler following the existing extractor and error pattern
- New service method on an existing type
- New test in the module's `#[cfg(test)]` block or a new `tests/` file
- New migration in the repo's existing naming (`sqlx migrate add <name>`, `-r` when the repo keeps down files; see rust-migration-safety), followed by `cargo sqlx prepare` when the macros are used

Riskier: `main.rs` wire-up, `[features]` and `[workspace.dependencies]` (they cascade across members), `build.rs`, `unsafe` blocks, public trait signatures of a library crate other members implement.

## Output Format

Inject into `task-onboard` as Markdown sections in this order. Every value is read from the tree (or the instruction file, per the precedence above); mark a derived value `(inferred)` - a run command assembled from the tree alone, a hotspot named from a path with no code read - and an unavailable one `(unknown)` with the reason (`file unreadable`, `no filesystem access`). A directory listing that shows no lint config supports `none`; an unreadable tree is `(unknown)`. `docs/` is part of the tree: an incident or design doc that names a hotspot is read for Risk Hotspots. Never carry a value over from the shape below - it shows the section skeleton, not defaults. In a workspace, `Rust`, `Framework`, `DB`, `Migrations`, `Features` and `Tests` carry one sub-bullet per member where members differ.

```markdown
### Stack and Tooling
- **Rust:** <toolchain channel, or "no toolchain file">{ (declared: <value>)} (rust-version <MSRV or "unset">; edition <edition>; <support position, only when the current release is known>) - workspace: root `resolver` first, then per member
- **Runtime:** <Tokio / async-std / smol / none>
- **Framework:** <framework + version, or (unknown)>
- **DB:** <crate + features + engine; sqlx: macros or runtime queries, `.sqlx/` present or not>
- **Migrations:** <tool + command>
- **Queue / Broker:** <crate + broker (rdkafka + Kafka, job table on PostgreSQL), or "none found">
- **Logging / Observability:** <crates and where the subscriber is installed>
- **Lint:** <clippy levels and where set, rustfmt config, cargo-deny / cargo-audit, and what CI enforces, or "none - no lint config">
- **Features:** <non-default features each binary enables, "none beyond defaults", "defined but unused: <feature>", or "unverified - no filesystem access">
- **Tests:** <inline / tests/ / #[sqlx::test] / feature-gated / doctests / none found> + the command that runs them
- **CI / Deploy:** <workflow file + what it runs; k8s or compose manifests; or (unknown)>

### Local Bootstrap
Ordered commands, each one runnable, in Bootstrap Path order. Omit steps the tree does not
support rather than inventing them. A port counts as set when code, config, or a manifest
sets it - say which; never state one the tree does not set.

### Architecture Map
- Entry: <src/main.rs, src/bin/*, or member crates>, and whether wire-up is thin
- App code: <src/ or crates/>
- Layout: **<convention>**, plus single crate / multi-binary / Cargo workspace
- <one line per structural module or crate>
- Workspace only: member dependency edges (a declared dependency nothing uses is a deviation), members bypassing `[workspace.dependencies]`, and feature unification effects - framework, DB layer and toolchain already sit per member under Stack and Tooling

### Conventions
Only what the tree shows - sample the entry, one handler, one repository, one test. A convention
with no evidence is `(unknown)` with the file to read for it - not restated as an idiom the repo
may not follow. Call out deviations from the idiomatic baseline explicitly (`anyhow` in a library
crate's public API, `log` instead of `tracing`, a trait declared beside its only implementation,
`unwrap()` on request paths, a dependency nothing uses), since they change where new code goes.

### Risk Hotspots
Ordered most-exploitable first (reachable without auth, then authenticated, then internal), then by blast radius. One bullet each:
`- <hotspot> (<path or file:line>) -> <delegate skill>`. Delegates: `rust-security-patterns` (auth layering, secrets, `unsafe`, advisories), `rust-async-patterns`, `rust-concurrency`, `rust-db-access` (pool, transactions, offline cache), `rust-messaging-patterns`, `rust-migration-safety`, `rust-error-handling`, `rust-web-patterns` (router, middleware, shutdown), `rust-testing-patterns`; a hotspot no skill owns (member version skew, a Dockerfile/k8s mismatch, feature unification) reads `-> none (ops)`.

### First-PR Safe Zones
Concrete paths from the observed layout. When a generic safe zone does not exist here
(no `migrations/` directory, route table inside `main.rs`), say so and say why instead of
offering the generic form. Close with what to avoid and the reason.

### Unknowns - Ask the Team
Every `(unknown)` above, consolidated. On a repo with no compose file, no `.env.example`,
no CI, and no lint config, this is the highest-value section for a new joiner.
```

## Avoid

- Recommending `log` + `env_logger` for a new async service (use `tracing`)
