---
name: task-rust-debug
description: Debug Rust application errors - panic backtraces, borrow checker violations, async/await issues, and sqlx errors. Paste a backtrace or describe the unexpected behavior. Not for production incident analysis with blast radius assessment (use task-incident-root-cause for that).
agent: rust-architect
metadata:
  category: backend
  tags: [rust, axum, debug, troubleshooting, backtrace, workflow]
  type: workflow
user-invocable: true
---

## STEP 1 - INTAKE

Ask for: full backtrace or compiler error, the source file where the error originates, and what the user expected to happen. If a backtrace is provided, identify the first application-code frame (skip standard library and crate frames) and read that file. For compiler errors, read the file and line referenced in the error.

## STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

### Panic / Unwrap Errors

- `called Option::unwrap() on a None value` or `called Result::unwrap() on an Err value` -> trace the source value. The backtrace shows where `.unwrap()` was called; the fix is to use `?` or pattern matching instead. Use skill: `rust-error-handling`.
- `index out of bounds` -> check collection length before indexing, use `.get()` for safe access.

### Borrow Checker / Lifetime Errors

- `cannot borrow X as mutable because it is also borrowed as immutable` -> restructure to avoid overlapping borrows. Common fix: clone the value, use `RefCell`/`Mutex`, or restructure the code to drop the immutable borrow first.
- `X does not live long enough` -> the value is dropped before the reference. Fix: extend the lifetime by moving ownership, using `Arc`, or restructuring the scope.
- `cannot move out of X because it is borrowed` -> the value is borrowed and you're trying to move it. Fix: clone, or restructure to use the value after the borrow ends.

### Async / Tokio Errors

- `Cannot start a runtime from within a runtime` -> nested Tokio runtime. Never create a second runtime; use `tokio::task::spawn_blocking` for sync code. Use skill: `rust-async-patterns`.
- `future is not Send` -> the future holds a non-Send type (e.g., `Rc`, `MutexGuard` across `.await`). Fix: drop the guard before `.await`, or use `Arc` instead of `Rc`.
- Deadlock / task never completes -> holding `std::sync::MutexGuard` across `.await`. Use `tokio::sync::Mutex` if the lock must span awaits. Use skill: `rust-concurrency`.

```rust
// BEFORE (deadlock - std Mutex held across .await)
let guard = std_mutex.lock().unwrap();
some_async_op().await; // other tasks blocked from acquiring the lock

// AFTER (tokio Mutex - safe across .await)
let guard = tokio_mutex.lock().await;
some_async_op().await;
```

### Type / Trait Errors

- `the trait bound X is not satisfied` -> check which trait is needed and implement or derive it. Common: `Serialize`, `Deserialize`, `FromRow`, `Clone`, `Send`, `Sync`.
- `mismatched types` -> check function signatures and return types. Common with `Result<T, E>` where `E` doesn't match.
- `the trait X is not implemented for Y` -> use `#[derive(...)]` or implement the trait manually.

### sqlx / Database Errors

- `error returned from database: connection refused` -> DB not running or wrong connection string. Use skill: `rust-db-access`.
- `pool timed out while waiting for an open connection` -> `max_connections` too low or connection leak. Check pool config and ensure connections are returned promptly.
- `no rows returned by a query that expected to return at least one row` -> `fetch_one` on empty result. Use `fetch_optional` and handle `None`.

### Build / Compilation Errors

- `unresolved import` -> wrong module path, missing `pub`, or missing dependency in `Cargo.toml`.
- `unused variable` / `unused import` -> clean up or prefix with `_`.

### Background Job Errors

- Tokio task panic (`JoinError`) -> the spawned task panicked. Check the task's code for `.unwrap()` or index out of bounds. Use skill: `rust-async-patterns` (task spawning section).
- Kafka/AMQP consumer lag -> consumer group offset issue, handler error causing reprocess loop. Use skill: `rust-messaging-patterns`.

## STEP 3 - LOCATE

1. Read the backtrace top-to-bottom; find the first application-code frame (not crate or std library)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it upstream through function parameters, trait implementations, or async task spawns
4. For borrow checker errors: identify the two conflicting uses of the value and which one should be restructured
5. For async errors: check whether any lock guards or non-Send types are held across `.await` points

## STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The future is not Send because a std::sync::MutexGuard is held across the
.await at src/services/cache.rs:34. The guard is acquired at line 32 and
not dropped until after the async database call completes at line 36.
```

## STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms. Use skill: `rust-error-handling` to ensure error patterns are preserved.

## STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **Test** that exercises the exact code path
- **`cargo clippy`** for common lint issues
- **Type system** (e.g., newtype wrappers, `#[must_use]` on Result-returning functions)
- For async bugs: check for `MutexGuard` held across `.await` (clippy `await_holding_lock`)
- For borrow checker issues: explain the ownership model to help the user avoid similar patterns

## Avoid

- Do not add `.unwrap()` to "fix" a type mismatch - propagate the error with `?`
- Do not use `unsafe` to bypass borrow checker errors - restructure the code
- Do not nest Tokio runtimes to fix "cannot start a runtime" - use `spawn_blocking`
- Do not use `Rc`/`RefCell` in async code to fix Send errors - use `Arc`/`Mutex`
- Do not add `#[allow(unused)]` to suppress warnings without understanding why
- Do not add `clone()` everywhere to fix borrow errors without understanding the performance implications

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why the error occurs, referencing specific file:line]

## Fix
[Before/after code blocks]

## Prevention
[Test, clippy lint, or type system change to prevent recurrence]
```

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal and addresses root cause, not symptom
- [ ] Rust idioms preserved - errors use `?` and thiserror/anyhow, no unnecessary `.unwrap()`
- [ ] Prevention step included (test, `cargo clippy`, or MIRI guidance)
- [ ] For async bugs, cancellation safety and `.await` holding addressed
- [ ] For borrow checker issues, ownership model explained clearly
