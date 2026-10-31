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
| Coroutine/Lightweight      | coroutine, task (event loop, cooperative scheduler, or multi-threaded executor) | async/await, structured scope, channel | blocking call in async context, lost update across await, lost cancellation, backpressure, data race (multi-threaded executor) |
| Process/Actor              | process, actor               | message passing, mailboxes            | message ordering, serialization cost, supervision gaps          |

A hazard with no Risk value of its own takes the value its consequence matches: pool starvation and backpressure are `unbounded concurrency` (`deadlock` when a task waits on work queued behind it in the same pool), a supervision gap, a claim marked done or an offset committed before the work runs, is `fire-and-forget`, a message-ordering bug is `lost update`; lock contention and serialization cost are performance notes, not Issues. A duplicate from a retry or redelivery is `backend-idempotency`'s finding, a retry policy `ops-resiliency`'s, and I/O held inside an open transaction `backend-transaction-patterns`'; none is an Issue here - the `Routed:` line names them.

Write `coroutine` for code written as async functions (Python asyncio and Node on a single-threaded event loop; Kotlin `suspend` on a dispatcher, which is a thread pool unless it is `Dispatchers.Main` or a single-thread context), `task` for a runtime work item scheduled by a runtime executor (.NET `Task`; a tokio task, on a thread pool under the multi-thread runtime and on one thread under `current_thread`, the `#[tokio::test]` default), `process` for a prefork worker pool (Celery prefork, Gunicorn sync workers) under Process/Actor.

Name well-known runtime constraints, version-gated where a version changes them: a GIL-style global lock (CPython below 3.13, or a 3.13+ build without free-threading; a free-threaded build runs with the GIL off by default but re-enables it when an extension without `Py_mod_gil` support is imported, so the constraint is `absent` only when that is verified - and its absence exposes real data races), the CRuby GVL (every release; Ruby code runs in parallel only across Ractors, Ruby 3.0+ and still experimental, while threads overlap only on blocking I/O or in C extensions that release the GVL), virtual-thread pinning under `synchronized` (JDK 21-23; removed in JDK 24 by JEP 491, native frames still pin), blocking-call restrictions in async runtimes.

A service running several models (threaded API, threaded workers, a singleton scheduler) reports the model and primitive of the code under review, or of the highest-severity Issue's site when the review spans several, and names the others in the `others present` suffix of both lines. The Stack line stays what `stack-detect` returned; a subsystem framework (a task queue, a scheduler) is named in the Concurrency model line, not the Stack line.

### Database-Level Concurrency

In-process locks protect one process. When multiple instances mutate the same row, coordinate in the database:

| Strategy            | Mechanism                                          | Use when                                       |
| ------------------- | -------------------------------------------------- | ---------------------------------------------- |
| Pessimistic         | `SELECT ... FOR UPDATE` row lock until commit      | Short transactions, high contention            |
| Optimistic          | Version column checked at UPDATE; retry on conflict | Read-heavy, low contention                     |
| Serializable        | Conflicting transactions abort with a retryable error: a serialization failure (PostgreSQL SSI) or, after blocking on range locks, a deadlock victim or lock-wait timeout (InnoDB 1213 / 1205, SQL Server 1205 / 1222). Oracle SERIALIZABLE is snapshot isolation: ORA-08177 fires on a write-write conflict only and write skew commits - lock the rows explicitly there | Multi-row invariants; the caller retries |
| Advisory lock       | DB-managed app-level lock, transaction-scoped where the engine offers it (`pg_advisory_xact_lock`; SQL Server `sp_getapplock` with `@LockOwner = 'Transaction'`); session-scoped locks (`pg_advisory_lock`, MySQL `GET_LOCK`) survive commit and leak through a pooled connection unless released in a `finally`, and behind a transaction-mode pooler (PgBouncer `pool_mode = transaction`) they are unsafe at any release point - use the transaction-scoped form there | Cross-process coordination without row locking |
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

Zero rows affected means insufficient stock or no such product - distinguish with a follow-up read before deciding to fail or retry. At READ COMMITTED the row count is the signal on every engine. Above it the engines differ: PostgreSQL REPEATABLE READ or SERIALIZABLE raises a serialization failure (SQLSTATE 40001) on a concurrent update; InnoDB, and SQL Server at its locking levels, block on the row lock, re-evaluate the WHERE clause, and still answer with the row count (failure modes: lock-wait timeout, deadlock); SQL Server SNAPSHOT raises error 3960 and Oracle SERIALIZABLE ORA-08177. The caller rolls the transaction back, then retries every raised error: an InnoDB lock-wait timeout rolls back only the statement (`innodb_rollback_on_timeout` is off by default), and a new `BEGIN` on that connection commits the partial work.

### Distributed Coordination

- Idempotency keys for webhook and event deduplication - preferred over locks
- A per-key cap across instances (N jobs per tenant) is a counting semaphore in the shared store with TTL'd holder tokens, never an in-process semaphore
- `SET key token NX PX <ms>` for simple distributed locks when idempotency is not possible, paired with a fencing token the protected resource checks (a monotonic value issued with the lock - `INCR` on a counter key, or a database sequence); release with a compare-and-delete on the token (a Lua script), never a bare `DEL`, or an expired holder deletes the next holder's lock

## Output Format

One Issue entry per defect, not per symptom: when several rules fail on the same construct - or on one construct spread over two files, such as a check in a handler and the insert it guards in a service - and one restructure resolves them all, that is one Issue at the highest severity listing every Risk, anchored at the file:line where the Fix lands (the service insert when the fix is there, even though the handler check triggered the rule) and naming the other site in the description. Order Issues by severity, High first. Every Risk value has a severity tier below, and every tier entry has a Risk value; an Issue's severity is the highest tier among its Risks.

```
## Concurrency Assessment

**Stack:** {language / framework | <language> (no framework detected) | unknown}{ - <qualifier: unfamiliar stack, verify against runtime docs>}

**Concurrency model:** {Thread-based | Coroutine/Lightweight | Process/Actor | not yet chosen}{; others present: ...}

**Primary primitive:** {OS thread | virtual thread | goroutine | coroutine | task | process | actor | not yet chosen}{; others present: ...}

**Runtime constraints:** {constraints that apply, version-gated where a version changes them | none known | verify: <what to check>}

### Issues                                    {when at least one issue}

- [Severity: High | Medium | Low] {file:line if available} - {description}
  - Risk: {one or more, comma-separated: data race, lost update, deadlock, cross-instance race, unbounded concurrency, overlapping runs, lock without TTL, blocking in async context, missing timeout or cancellation boundary, lost cancellation, fire-and-forget, unsafe lock release, untested contention, spurious conflict error, idiomatic drift}
  - Fix: {concrete correction using the detected stack's idioms}{; the proposed fix closes it | ; the proposed fix does not close it: <why>}       {suffix only when the request proposes a fix, or a design choice addressing this risk}

### No Issues Found                           {instead, when none: one sentence stating no concurrency Issue was found; routed hazards appear only on the Routed line}

Routed: {hazard at file:line -> skill, ...}       {only when a hazard was routed to a sibling skill}
```

Severity:

- **High**: `data race`, `lost update` (a read-modify-write interleaved across a suspension point, between concurrent transactions, or between instances, or by a distributed-lock holder paused past its TTL while the protected operation is not idempotent and the resource checks no fencing token), `deadlock`, `cross-instance race` (an in-process lock guarding it), `unbounded concurrency` (unbounded fan-out is a resource leak), `overlapping runs` (a periodic job that can fire again before the previous run finishes), `lock without TTL`
- **Medium**: `blocking in async context`, `missing timeout or cancellation boundary` (no boundary at all), `lost cancellation` (a cancel signal raised but not propagated or honoured), `fire-and-forget` (no error path, or a claim or offset committed before the work runs), `unsafe lock release` (a distributed lock released without a token check, or left held after a partial acquisition fails), `untested contention` (no contention test - N parallel actors released on a latch, asserting invariants - or race-detector coverage on code holding shared mutable state; raised only when its test files were read or none exist), `spurious conflict error` (a race the database constraint blocks but that still surfaces as an error to the caller)
- **Low**: `idiomatic drift` from the detected stack's conventions

For design tasks (no implementation yet), use the same format: list risks of the proposed design as Issues, anchor each at the proposal document and item (`docs/proposals/x.md item 4`) instead of {file:line}, and when the proposal's intent is ambiguous, state the reading taken in the description rather than raising the ambiguity as an Issue. The two header lines are set independently: Concurrency model is `not yet chosen` when the proposal names no runtime (a proposal naming only a language keeps the model of the code it extends, `not yet chosen` when it extends none), Primary primitive is `not yet chosen` when it names no primitive, and Runtime constraints reads `verify: <what to check once chosen>` when either is. `untested contention` is never raised for a design task. When `Language` is `unknown`, apply the model table and database strategies generically - they are runtime-agnostic. Write `<language> (no framework detected)` when stack-detect reports a known `Language` and `Framework: unknown`. When the language is detected but its runtime is outside the model table's vocabulary (the review cannot name its scheduler, memory model, or global-lock behaviour with confidence), add the Stack qualifier and write the Runtime constraints line as `verify: <what to check>`. Deployment lifecycle interactions (a deploy interrupting a long job, cutover flag skew) belong to `ops-release-safety` and go on the `Routed:` line; a singleton scheduler duplicated for the length of a rollout is `overlapping runs` here.

## Avoid

- Guarding a cross-instance race with an in-process lock
