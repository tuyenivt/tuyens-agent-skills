---
name: task-rust-debug
description: Debug Rust errors - panics, borrow checker, async/Send, deadlocks, sqlx (unique/FK/serialization), silent serde drops - from traces or symptoms.
agent: rust-tech-lead
metadata:
  category: backend
  tags: [rust, axum, sqlx, tokio, debug, troubleshooting, backtrace, workflow]
  type: workflow
user-invocable: true
---

# Debug Rust Error

## When to Use

- Panics, `unwrap`/`expect` failures, index-out-of-bounds
- Borrow checker, lifetime, or move errors blocking compilation
- Async: `future is not Send`, nested runtimes, deadlocks across `.await`
- sqlx: PG error codes (`23505`/`23503`/`23514`/`40001`), pool timeout, `no rows`, connection refused
- Silent field loss across serde / sqlx / job-payload boundaries (compiles, runs, drops data)
- Background task failures (`JoinError`, consumer reprocess loops)

Not for: new features (`task-rust-implement`), general review (`task-rust-review`), perf tuning (`task-rust-review-perf`).

## Workflow

**Step 1 - Behavioral principles.** Use skill: `behavioral-principles`.

**Step 2 - Detect stack.** Use skill: `stack-detect`. Confirm Rust + async runtime + data access crate; debug output cites stack-specific fixes (Tokio, sqlx). Halt if non-Rust.

**Step 3 - Intake.** For a backtrace or `cargo` error: collect full text and the source file at the first application frame.

Partial input ("it panics sometimes"): request `RUST_BACKTRACE=1`, command run, expected vs actual, frequency (every call / intermittent / under load only).

**No error, just wrong data** (field deserializes empty, column returns default, job payload arrives stripped): reframe as **which boundary lost the field**, then ask the user to log `?value` with `tracing::debug!` before and after each suspect:

- `Json(req): Json<Dto>` extraction - serde `rename`/`rename_all` mismatch, missing `deny_unknown_fields`, `#[serde(default)]` swallowing a required field
- `From<Dto> for Domain` - `..Default::default()` hiding a forgotten field
- `query_as::<_, T>(...)` runtime macro - column omitted from `SELECT` returns `Default::default()` (compile-time `query_as!` would have caught it)
- `#[sqlx(skip)]` / `#[sqlx(default)]` on a struct field
- Job payload: `serde_json::to_vec` on enqueue vs `from_slice` in worker - field renamed on one side only

**Step 4 - Triage symptoms.** Real bugs surface as several errors at once (a panic + a Send warning + intermittent behavior). Don't classify each independently - identify the root and the downstream symptoms.

Apply this ordering: **concurrency root > data-corruption visible > panic visible**. A `std::sync::MutexGuard` held across `.await` produces all three of: `future is not Send` (compile), deadlock under load (runtime), and downstream `unwrap()` on a timed-out `Option` (visible panic). Fixing the panic site is a band-aid; fixing the guard scope is the root.

Other common multi-symptom roots: unhandled `23505` from a missing `ON CONFLICT` causes both the transaction abort and a cascade of `JoinError` from spawned retry tasks; a misframed Kafka offset commit causes both the reprocess loop and the duplicate-key panic.

**Step 5 - Classify.** Match the root symptom, then load the listed atomic skill.

**Panic / unwrap**
- `unwrap() on None`/`Err` -> trace the source; replace with `?` or pattern match. Use skill: `rust-error-handling`.
- `index out of bounds` -> length check or `.get()`.

**Borrow checker / lifetime**
- `cannot borrow as mutable...also borrowed as immutable` -> drop the immutable borrow first, split the data, or use interior mutability.
- `does not live long enough` -> extend ownership (`Arc`, move) or restructure scope.
- `cannot move...because borrowed` -> clone, or use the value after the borrow.

**Async / Tokio**
- `future is not Send` AND/OR deadlock under load -> non-Send held across `.await` (`Rc`, `std::sync::MutexGuard`, `RefCell`). The Send warning and the deadlock are the same bug. Use skill: `rust-concurrency`.
- `Cannot start a runtime from within a runtime` -> use `tokio::task::spawn_blocking`, not a nested runtime. Use skill: `rust-async-patterns`.

**Type / trait**
- `trait bound X not satisfied` -> derive or implement (`Serialize`, `FromRow`, `Clone`, `Send`/`Sync`).
- `mismatched types` -> usually `Result<T, E>` where `E` doesn't match; align with `From`/`?` or `map_err`.

**sqlx / database**
- `Database(PgDatabaseError { code: "23505", ... })` unique violation -> missing `ON CONFLICT DO NOTHING/UPDATE` or pre-check race. Use skill: `rust-db-access`.
- `code: "23503"` FK violation -> parent missing or wrong write order; check transaction sequence.
- `code: "23514"` check constraint -> domain invariant violated; validate before insert.
- `code: "40001"` serialization failure -> retry with backoff at the transaction boundary (read-modify-write under `Repeatable Read`/`Serializable`).
- `pool timed out` -> rule out connection leaks (unawaited transactions, missing `drop(tx)`) before raising `max_connections`.
- `connection refused` -> DB down or wrong DSN.
- `no rows returned by a query that expected to return at least one row` -> use `fetch_optional`, handle `None`.

**Build / compile**
- `unresolved import` -> wrong path, missing `pub`, or missing dep in `Cargo.toml`.

**Silent data loss** (no error; a field arrives empty/default)
- Throws nothing, so it routes to no atomic skill - run the Step 3 boundary analysis to find which boundary drops the field. The root is usually a `..Default::default()` in a `From<Dto>` conversion or a serde `rename`/`default` mismatch; fix it at that boundary.

**Background jobs**
- `JoinError` -> spawned task panicked; root cause is inside the task, not the join site. Use skill: `rust-async-patterns`.
- Kafka/AMQP consumer reprocess loop -> handler returns error on poison message; needs DLQ. Use skill: `rust-messaging-patterns`.

**Step 6 - Locate.**

1. Read backtrace top-down; first application frame (skip std/crate frames).
2. Open that file; read the failing function.
3. Trace the problematic value upstream through parameters, trait impls, spawn sites.
4. Borrow errors: identify the two conflicting uses.
5. Async errors: scan every `.await` in the function for guards or non-Send types in scope.
6. Cascading panics: focus on the **first** frame; later panics are often `JoinError` wrappers of the same root.

**Step 7 - Root cause.** Explain **why**, not just what. State confidence: **HIGH** (reproduced or obvious), **MEDIUM** (pattern match), **LOW** (multiple candidates). Cite `file:line`. If multi-symptom, name root and downstream symptoms.

**Step 8 - Fix.** Before/after, minimal, root-cause-targeted. Preserve error-handling conventions per `rust-error-handling`.

```rust
// Bad: std Mutex held across .await -> not Send + deadlocks under load
let cfg = std_mutex.lock().unwrap();
fetch(&cfg).await?;

// Good: clone out, drop guard before await
let cfg = { std_mutex.lock().unwrap().clone() };
fetch(&cfg).await?;
```

If the lock genuinely must be held across the `.await` (shared state mutated mid-await), switch the field to `tokio::sync::Mutex`, whose guard is `Send`, instead of cloning out.

**Step 9 - Prevention.** Add one guard so this class cannot recur:

| Class                          | Guard                                                              |
| ------------------------------ | ------------------------------------------------------------------ |
| std-Mutex across `.await`      | `cargo clippy -- -W clippy::await_holding_lock` in CI              |
| Concurrency bug (load-only)    | Load test or `#[tokio::test(flavor = "multi_thread")]` reproducer  |
| Runtime `query_as` field drop  | `sqlx::test` integration test; prefer compile-time `query_as!`     |
| `From<Dto>` conversion drop     | Drop `..Default::default()` so an unmapped field fails to compile; round-trip test |
| Unique-violation race          | DB unique index + `ON CONFLICT`; idempotency-key test              |
| `unwrap()` on fallible API     | `#[must_use]`, newtype invariants, or `?` propagation              |

## Edge Cases

- **No backtrace:** request `RUST_BACKTRACE=full cargo run`; in prod, check tracing/sentry breadcrumbs.
- **Compiles in dev, fails in release:** `unsafe` UB exposed by the optimizer, or a `debug_assert!` masking the issue.

## Output Format

```
## Error Classification
[Category]: [specific type]   (multi-symptom: root -> downstream)

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why, citing file:line]

## Fix
[Before/after code]

## Prevention
[Test, clippy lint, type-system guard, or DB constraint]
```

## Self-Check

- [ ] Step 1 - `behavioral-principles` loaded
- [ ] Step 2 - stack confirmed Rust; runtime + data-access crate recorded
- [ ] Step 3 - full backtrace requested; silent-data-loss boundaries checked if no error
- [ ] Step 4 - multi-symptom input triaged; root vs downstream named
- [ ] Step 5 - classified before reading code or proposing fix
- [ ] Step 6 - first application frame identified; data path traced upstream
- [ ] Step 7 - root cause cites file:line; confidence stated
- [ ] Step 8 - before/after fix is minimal and root-cause-targeted
- [ ] Step 9 - prevention guard added (test, clippy, type system, or DB constraint)

## Avoid

- `.unwrap()` added to silence a type or `Option` error; propagate with `?`
- `unsafe` to bypass the borrow checker; restructure ownership instead
- Nesting Tokio runtimes; use `spawn_blocking` for sync work
- `Rc`/`RefCell` in async code; use `Arc`/`tokio::sync::Mutex`
- Fixing a downstream panic without checking whether a concurrency root produced it
- Raising `max_connections` before ruling out connection leaks
