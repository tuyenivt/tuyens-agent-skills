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
- Bound every concurrent workload - pool size, semaphore, or queue. Unbounded fan-out is a resource leak
- Every concurrent unit must have a cancellation or timeout boundary
- Minimize shared mutable state; when unavoidable, protect it with the ecosystem's idiomatic mechanism
- In-process locks do not coordinate across instances - use database or distributed locks for cross-process races
- Distributed locks always carry a TTL; prefer idempotent operations over locks when feasible

## Patterns

### Identify the Model

After `stack-detect`, classify the runtime's primary model and reason about issues using its vocabulary:

| Model                      | Primitive                    | Sync mechanisms                       | Common hazards                                                  |
| -------------------------- | ---------------------------- | ------------------------------------- | --------------------------------------------------------------- |
| Thread-based               | OS / virtual thread          | mutex, semaphore, monitor             | deadlock, lock contention, pool starvation, thread pinning      |
| Coroutine / lightweight    | coroutine, task, goroutine   | channel, async/await, structured scope | blocking call in async context, lost cancellation, backpressure |
| Process / actor            | process, actor               | message passing, mailboxes            | message ordering, serialization cost, supervision gaps          |

If the runtime has well-known constraints (GIL-style global locks, thread pinning under certain locks, blocking-call restrictions in async runtimes), name them in the assessment.

### Database-Level Concurrency

In-process locks protect one process. When multiple instances mutate the same row, coordinate in the database:

| Strategy            | Mechanism                                          | Use when                                       |
| ------------------- | -------------------------------------------------- | ---------------------------------------------- |
| Pessimistic         | `SELECT ... FOR UPDATE` row lock until commit      | Short transactions, high contention            |
| Optimistic          | Version column checked at UPDATE; retry on conflict | Read-heavy, low contention                     |
| Serializable        | DB aborts conflicting transactions                  | Multi-row invariants                           |
| Advisory lock       | DB-managed app-level lock (e.g. `pg_advisory_lock`)| Cross-process coordination without row locking |

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
   SET qty = qty - :n, version = version + 1
 WHERE product_id = :id AND version = :v AND qty >= :n
```

Zero rows affected means conflict or insufficient stock - retry or fail.

### Distributed Coordination

- Idempotency keys for webhook and event deduplication - preferred over locks
- `SET NX` with TTL for simple distributed locks when idempotency is not possible
- A crashed holder must not stall the system - TTL is mandatory

### Testing for Contention

Concurrency bugs surface only under contention:

- Stress test: N parallel actors hitting shared state; assert invariants
- Latch/barrier: start all actors simultaneously to maximize the contention window
- Enable the runtime's race detector during tests where one exists
- Every concurrent test has a timeout - a deadlock must fail the test, not hang CI

## Output Format

```
## Concurrency Assessment

**Stack:** {detected language / framework}
**Concurrency model:** {Thread-based | Coroutine/Lightweight | Process/Actor}
**Primary primitive:** {thread | goroutine | coroutine | process | task | fiber}

### Issues

- [Severity: High | Medium | Low] {file:line if available} - {description}
  - Risk: {data race | deadlock | resource leak | blocking in async context | cross-instance race | etc.}
  - Fix: {concrete correction using the detected stack's idioms}

### No Issues Found

{State explicitly if concurrency usage is safe - do not omit this section silently}
```

Severity:

- **High**: data race, deadlock risk, unbounded concurrency, in-process lock used for a cross-instance race
- **Medium**: blocking call in cooperative context, missing cancellation or timeout, distributed lock without TTL
- **Low**: idiomatic drift from the detected stack's conventions

Omit "No Issues Found" only when issues were listed.

## Avoid

- Mixing concurrency paradigms inside one module without justification
- Fire-and-forget work with no error path or cancellation
- Treating in-process mutexes as protection against cross-instance races
- Distributed locks where idempotency would suffice
- Validating concurrent code only on the happy path
