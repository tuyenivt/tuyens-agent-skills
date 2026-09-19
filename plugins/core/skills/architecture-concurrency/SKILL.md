---
name: architecture-concurrency
description: Review concurrency design across stacks - threading models, synchronization primitives, database locking, async pitfalls, and safe parallelism.
metadata:
  category: architecture
  tags: [concurrency, threading, parallelism, multi-stack]
user-invocable: false
---

# Concurrency Model

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing concurrent or parallel processing in a backend service
- Reviewing code using threads, goroutines, coroutines, locks, or background workers
- Evaluating shared mutable state, contention, or cancellation behavior
- Deciding between in-process, database-level, or distributed coordination

## Rules

- Use the concurrency primitive native to the detected stack; do not mix paradigms inside a module without cause
- Bound every concurrent workload - pool size, semaphore, or queue. Unbounded fan-out is a resource leak. The bound must sit at the point of *creation*: a semaphore that throttles the work while every unit is still allocated up front bounds throughput, not memory, and an attacker-sized input still exhausts the process. A periodic job is a workload too: a schedule that can fire again before the previous run finishes is unbounded unless the run is skipped or serialized.
- Every concurrent unit must have a cancellation or timeout boundary
- Minimize shared mutable state; when unavoidable, protect it with the ecosystem's idiomatic mechanism
- In-process locks do not coordinate across instances - use database or distributed locks for cross-process races
- Distributed locks always carry a TTL, and a TTL buys liveness, not safety: a holder paused past its TTL still runs while the next holder acquires, so the protected operation must be idempotent or the resource must check a fencing token. Prefer idempotent operations over locks when feasible

## Patterns

### Identify the Model

After `stack-detect`, classify the runtime's primary model and reason about issues using its vocabulary:

| Model                      | Primitive                    | Sync mechanisms                       | Common hazards                                                  |
| -------------------------- | ---------------------------- | ------------------------------------- | --------------------------------------------------------------- |
| Thread-based               | OS thread, virtual thread, goroutine | mutex, semaphore, monitor, channel | data race, deadlock, lock contention, pool starvation           |
| Coroutine/Lightweight      | coroutine, task (single-threaded event loop or cooperative scheduler) | async/await, structured scope, channel | blocking call in async context, lost update across await, lost cancellation, backpressure |
| Process/Actor              | process, actor               | message passing, mailboxes            | message ordering, serialization cost, supervision gaps          |

Name well-known runtime constraints in the assessment, version-gated where a version changes them: a GIL-style global lock (CPython below 3.13, or a 3.13+ build without free-threading; a free-threaded build runs with the GIL off by default but re-enables it when an extension without `Py_mod_gil` support is imported, so the constraint is `absent` only when that is verified - and its absence exposes real data races), the CRuby GVL (every release, no version gate; parallelism only across Ractors), virtual-thread pinning under `synchronized` (JDK 21-23; removed in JDK 24 by JEP 491, native frames still pin), blocking-call restrictions in async runtimes.

A single-threaded event loop is not race-free: any read-modify-write that spans an await or suspension point can interleave with another task - a lost update, even with one instance.

A service running several models (threaded API, threaded workers, a singleton scheduler) reports the model and primitive of the code under review, or of the highest-severity Issue's site when the review spans several, and names the others in the same lines. The Stack line stays what `stack-detect` returned; a subsystem framework (a task queue, a scheduler) is named in the Concurrency model line, not the Stack line.

### Database-Level Concurrency

In-process locks protect one process. When multiple instances mutate the same row, coordinate in the database:

| Strategy            | Mechanism                                          | Use when                                       |
| ------------------- | -------------------------------------------------- | ---------------------------------------------- |
| Pessimistic         | `SELECT ... FOR UPDATE` row lock until commit      | Short transactions, high contention            |
| Optimistic          | Version column checked at UPDATE; retry on conflict | Read-heavy, low contention                     |
| Serializable        | Conflicting transactions abort (PostgreSQL SSI, Oracle) or block on range locks (InnoDB, SQL Server) | Multi-row invariants |
| Advisory lock       | DB-managed app-level lock, transaction-scoped (`pg_advisory_xact_lock`; the session-scoped `pg_advisory_lock` survives commit and leaks through a pooled connection) | Cross-process coordination without row locking |
| Skip-locked claim   | `SELECT ... FOR UPDATE SKIP LOCKED` (PostgreSQL 9.5+, MySQL 8.0+, Oracle; SQL Server uses `READPAST`; SQLite has no row locks) | Workers claiming queue/job rows without blocking peers |

Bad - in-process mutex for a cross-instance race:

```
mu.Lock()
inv := db.Get(productID)
if inv.Qty >= n { db.Set(productID, inv.Qty - n) }
mu.Unlock()
```

Two instances both read, both decrement, oversell.

Good - conditional update is the lock:

```
UPDATE inventory
   SET qty = qty - :n
 WHERE product_id = :id AND qty >= :n
```

Zero rows affected means insufficient stock or no such product - distinguish with a follow-up read before deciding to fail or retry. At READ COMMITTED the row count is the signal on every engine. Above it the engines differ: PostgreSQL at REPEATABLE READ or SERIALIZABLE raises a serialization failure (SQLSTATE 40001) on a concurrent update, which the caller retries; InnoDB and SQL Server block on the row lock, re-evaluate the WHERE clause, and still answer with the row count (their failure modes are lock-wait timeout and deadlock); Oracle SERIALIZABLE raises ORA-08177.

### Distributed Coordination

- Idempotency keys for webhook and event deduplication - preferred over locks
- `SET key token NX PX <ms>` for simple distributed locks when idempotency is not possible; release with a compare-and-delete on the token (a Lua script), never a bare `DEL`, or an expired holder deletes the next holder's lock
- A crashed holder must not stall the system - TTL is mandatory

### Testing for Contention

Concurrency bugs surface only under contention:

- Stress test: N parallel actors hitting shared state; assert invariants
- Latch/barrier: start all actors simultaneously to maximize the contention window
- Enable the runtime's race detector during tests where one exists
- Every concurrent test has a timeout - a deadlock must fail the test, not hang CI

## Output Format

One Issue entry per defect, not per symptom: when several rules fail on the same construct - or on one construct spread over two files, such as a check in a handler and the insert it guards in a service - and one restructure resolves them all, that is one Issue at the highest severity listing every Risk, anchored at the file:line where the Fix lands (the service insert when the fix is there, even though the handler check triggered the rule) and naming the other site in the description. Order Issues by severity, High first. Every Risk value has a severity tier below, and every tier entry has a Risk value; an Issue's severity is the highest tier among its Risks.

```
## Concurrency Assessment

**Stack:** {language / framework | unknown}{ - <qualifier: unfamiliar stack, verify against runtime docs>}

**Concurrency model:** {Thread-based | Coroutine/Lightweight | Process/Actor | not yet chosen}{; others present: ...}

**Primary primitive:** {OS thread | virtual thread | goroutine | coroutine | task | process | actor | not yet chosen}

**Runtime constraints:** {version-gated constraints that apply, or "none known"}

### Issues                                    {when at least one issue}

- [Severity: High | Medium | Low] {file:line if available} - {description}
  - Risk: {one or more, comma-separated: data race, lost update, deadlock, cross-instance race, unbounded concurrency, overlapping runs, lock without TTL, blocking in async context, missing timeout or cancellation boundary, lost cancellation, fire-and-forget, unsafe lock release, untested contention, spurious conflict error, idiomatic drift}
  - Fix: {concrete correction using the detected stack's idioms}

### No Issues Found                           {instead, when none: one sentence stating concurrency usage is safe}
```

Severity:

- **High**: `data race`, `lost update` (across a suspension point or between instances), `deadlock`, `cross-instance race` (an in-process lock guarding it), `unbounded concurrency` (unbounded fan-out is a resource leak), `overlapping runs` (a periodic job that can fire again before the previous run finishes), `lock without TTL`
- **Medium**: `blocking in async context`, `missing timeout or cancellation boundary` (no boundary at all), `lost cancellation` (a cancel signal raised but not propagated or honoured), `fire-and-forget` (no error path), `unsafe lock release` (a distributed lock released without a token check), `untested contention` (no contention test or race-detector coverage on code holding shared mutable state), `spurious conflict error` (a race the database constraint blocks but that still surfaces as an error to the caller)
- **Low**: `idiomatic drift` from the detected stack's conventions

For design tasks (no implementation yet), use the same format: list risks of the proposed design as Issues, anchor each at the proposal document and item (`docs/proposals/x.md item 4`) instead of {file:line}, and when the proposal's intent is ambiguous, state the reading taken in the description rather than raising the ambiguity as an Issue. When `Language` is `unknown`, apply the model table and database strategies generically - they are runtime-agnostic. When the language is detected but its runtime is outside the model table's vocabulary (the review cannot name its scheduler, memory model, or global-lock behaviour with confidence), add the Stack qualifier and write the Runtime constraints line as `verify: <what to check>`. Deployment lifecycle interactions (a deploy interrupting a long job) belong to `ops-release-safety`, not here.

## Avoid

- Mixing concurrency paradigms inside one module without justification
- Fire-and-forget work with no error path or cancellation
- Treating in-process mutexes as protection against cross-instance races
- Distributed locks where idempotency would suffice
- Validating concurrent code only on the happy path
