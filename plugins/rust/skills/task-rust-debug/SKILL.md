---
name: task-rust-debug
description: Debug Rust errors: panic backtraces, borrow checker, async/Send, deadlocks, sqlx failures, silent serde field drops from traces or symptoms.
agent: rust-architect
metadata:
  category: backend
  tags: [rust, axum, debug, troubleshooting, backtrace, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Debug Rust Error

## When to Use

- Panics, `unwrap`/`expect` failures, index-out-of-bounds
- Borrow checker, lifetime, or move errors blocking compilation
- Async issues: `future is not Send`, nested runtimes, deadlocks across `.await`
- sqlx failures: pool timeout, `no rows`, connection refused
- Silent field loss across serde / sqlx / job-payload boundaries (compiles, runs, drops data)
- Background task failures (`JoinError`, consumer reprocess loops)

Not for: new features (`task-rust-implement`), general review (`task-rust-review`), perf tuning (`task-rust-review-perf`).

## Workflow

### STEP 1 - INTAKE

Ask for the full backtrace (or `cargo` error output) and the source file at the first application frame. For partial input ("it panics sometimes"): request `RUST_BACKTRACE=1`, command run, expected vs actual, frequency (every call / intermittent / under load only).

**For "no error, just wrong data"** (a field deserializes empty, a row's column comes back default, a background-job payload arrives stripped): no backtrace to classify. Reframe as **which boundary lost the field**, then ask the user to log `?value` with `tracing::debug!` immediately before and after each boundary. Suspect boundaries:

- `Json(req): Json<Dto>` extraction - serde `rename`/`rename_all` mismatch, missing `deny_unknown_fields`, `#[serde(default)]` swallowing a required field
- `From<Dto> for Domain` mapping - `..Default::default()` hiding a forgotten field
- `query_as::<_, T>(...)` runtime macro - column omitted from `SELECT` returns `Default::default()` (compile-time `query_as!` would have caught it)
- `#[sqlx(skip)]` / `#[sqlx(default)]` on a struct field
- Job payload round-trip: `serde_json::to_vec` on enqueue, `from_slice` in worker - renamed field on one side only

### STEP 2 - CLASSIFY

Match one category, then load the listed atomic skill.

**Panic / unwrap**
- `unwrap() on a None`/`Err` -> trace the source value; replace with `?` or pattern match. Use skill: `rust-error-handling`.
- `index out of bounds` -> length check or `.get()`.

**Borrow checker / lifetime**
- `cannot borrow as mutable...also borrowed as immutable` -> drop the immutable borrow first, split the data, or use interior mutability.
- `does not live long enough` -> extend ownership (`Arc`, move) or restructure scope.
- `cannot move...because borrowed` -> clone, or use the value after the borrow.

**Async / Tokio**
- `future is not Send` -> a non-Send type (`Rc`, `std::sync::MutexGuard`, `RefCell`) held across `.await`. Drop the guard before await, or switch to `Arc` / `tokio::sync::Mutex`. Use skill: `rust-concurrency`.
- Deadlock / task never completes -> `std::sync::MutexGuard` held across `.await`. **The Send warning and the deadlock are the same bug** - both surface here. Use skill: `rust-concurrency`.
- `Cannot start a runtime from within a runtime` -> use `tokio::task::spawn_blocking`, not a nested runtime. Use skill: `rust-async-patterns`.

```rust
// Bad: std Mutex held across .await -> not Send + deadlocks under load
let cfg = std_mutex.lock().unwrap();
fetch(&cfg).await?;

// Good: clone out, drop guard before await
let cfg = { std_mutex.lock().unwrap().clone() };
fetch(&cfg).await?;
```

**Type / trait**
- `trait bound X not satisfied` -> derive or implement (`Serialize`, `FromRow`, `Clone`, `Send`/`Sync`).
- `mismatched types` -> usually `Result<T, E>` where `E` doesn't match; align with `From`/`?` or `map_err`.

**sqlx / database**
- `connection refused` -> DB down or wrong DSN. Use skill: `rust-db-access`.
- `pool timed out` -> raise `max_connections` only after ruling out connection leaks (unawaited transactions, missing drops).
- `no rows returned by a query that expected to return at least one row` -> use `fetch_optional`, handle `None`.

**Build / compile**
- `unresolved import` -> wrong path, missing `pub`, or missing dep in `Cargo.toml`.

**Background jobs**
- `JoinError` -> spawned task panicked; root cause is inside the task, not at the join site. Use skill: `rust-async-patterns`.
- Kafka/AMQP consumer reprocess loop -> handler returns error on poison message. Use skill: `rust-messaging-patterns`.

### STEP 3 - LOCATE

1. Read backtrace top-to-bottom; first application frame (skip std/crate frames).
2. Open that file; read the failing function.
3. Trace the problematic value upstream through parameters, trait impls, spawn sites.
4. Borrow errors: identify the two conflicting uses.
5. Async errors: scan every `.await` in the function for guards or non-Send types in scope.

### STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced or obvious), **MEDIUM** (pattern match), **LOW** (multiple candidates).

```
ROOT CAUSE: [HIGH] src/handlers/billing.rs:147 holds `std::sync::MutexGuard`
from line 144 across `sqlx::query(...).fetch_one(&pool).await`. The future
is not Send under tokio's multi-thread runtime, and under load contending
tasks block waiting for the guard - the visible symptom is the unwrap()
panic on a downstream `Option` that times out.
```

### STEP 5 - FIX

Before/after code. Minimal, root-cause-targeted. Preserve error-handling conventions per `rust-error-handling`.

### STEP 6 - PREVENTION

Add one guard so this class cannot recur:

- Test exercising the exact path (load test for concurrency bugs)
- `cargo clippy -- -W clippy::await_holding_lock` in CI for std-Mutex-across-await
- `#[must_use]` on Result-returning APIs; newtype wrappers for invariants
- Repository integration test (e.g. `sqlx::test`) for runtime `query_as` field drops

## Edge Cases

- **No backtrace**: request `RUST_BACKTRACE=full cargo run`; for prod, check tracing/sentry breadcrumbs.
- **Intermittent / under-load only**: suspect Send/lock contention, pool exhaustion, or a race on an `Arc<Mutex>`.
- **Compiles in dev, fails in release**: `unsafe` UB exposed by optimizer, or a `debug_assert!` masking the issue.
- **Cascading panics**: focus on the **first** frame; later panics are often `JoinError` wrappers.

## Output Format

```
## Error Classification
[Category]: [specific type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why, citing file:line]

## Fix
[Before/after code]

## Prevention
[Test, clippy lint, type-system guard]
```

## Self-Check

- [ ] STEP 1: full backtrace requested; silent-data-loss path checked if no error
- [ ] STEP 2: classified before reading code or proposing fix
- [ ] STEP 3: first application frame identified; data path traced upstream
- [ ] STEP 4: root cause cites file:line; confidence stated
- [ ] STEP 5: before/after fix is minimal and root-cause-targeted
- [ ] STEP 6: prevention guard added (test, clippy, type system)

## Avoid

- `.unwrap()` added to silence a type or `Option` error; propagate with `?`
- `unsafe` to bypass the borrow checker; restructure ownership instead
- Nesting Tokio runtimes; use `spawn_blocking` for sync work
- `Rc`/`RefCell` in async code; use `Arc`/`tokio::sync::Mutex`
- `clone()` scattered to silence borrow errors without naming the cost
- `#[allow(unused)]` to bury warnings whose cause is unknown
