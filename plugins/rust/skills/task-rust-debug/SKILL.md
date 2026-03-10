---
name: task-rust-debug
description: "Debug Rust errors. Paste a panic backtrace, error log, or describe unexpected behavior. Classifies error, identifies root cause, suggests fix."
agent: rust-architect
metadata:
  category: backend
  tags: [rust, axum, debug, troubleshooting, backtrace, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - INTAKE: panic backtrace, error log, test failure, compiler error

STEP 2 - CLASSIFY:

- panic: unwrap on None/Err - trace the source value
- borrow checker error - lifetime or ownership issue
- type mismatch / trait bound not satisfied - generic constraint issue
- tokio runtime: "Cannot start a runtime from within a runtime" - nested runtime
- sqlx: connection refused - DB connectivity, pool config
- sqlx: pool timed out - MaxConnections too low or connection leak
- deadlock (task never completes) - await holding lock across .await point
- stack overflow - unbounded recursion or deeply nested futures
- Build error - dependency/import/type issue
- Tokio task panic (JoinError) - load rust-async-patterns, check spawn boundaries
- Kafka/AMQP consumer lag - consumer group offset issue, handler error causing reprocess loop

STEP 3 - LOCATE: read backtrace, open source at panic/error origin point

STEP 4 - ROOT CAUSE: WHY, confidence level

STEP 5 - FIX: minimal before/after

STEP 6 - PREVENTION: test, clippy lint, MIRI check

- Prefer `?` operator over `.unwrap()` in fallible paths
- Run `cargo clippy` for common pitfalls
- For async bugs, check for holding MutexGuard across `.await`
- For lifetime issues, consider owned types or `Arc` for shared ownership

OUTPUT: bug -> location -> fix -> prevention

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal and addresses root cause, not symptom
- [ ] Rust idioms preserved - errors use `?` and thiserror/anyhow, no unnecessary `.unwrap()`
- [ ] Prevention step included (test, `cargo clippy`, or MIRI guidance)
- [ ] For async bugs, cancellation safety and `.await` holding addressed
- [ ] For borrow checker issues, ownership model explained clearly

> Run `/task-skill-feedback` if output needed significant correction.
