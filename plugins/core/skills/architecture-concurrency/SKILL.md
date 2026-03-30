---
name: architecture-concurrency
description: Concurrency patterns adapted to the detected project stack - threading models, synchronization primitives, and safe concurrency practices.
metadata:
  category: architecture
  tags: [concurrency, threading, parallelism, multi-stack]
user-invocable: false
---

# Concurrency Model

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing concurrent or parallel processing in any backend service
- Reviewing code that uses threads, goroutines, coroutines, locks, or background workers
- Migrating from thread-per-request to lightweight concurrency models
- Evaluating shared mutable state and synchronization strategies

## Universal Principles

- Prefer the concurrency primitive native to the detected stack
- Shared mutable state is dangerous in every language - minimize it
- Always define cancellation/timeout boundaries for concurrent work
- Test concurrent code under contention, not just happy path
- Unbounded concurrency is a resource leak - always limit parallelism

---

## Concurrency Model Categories

Every language has a primary concurrency model. After loading stack-detect, identify which model the detected stack uses:

### Thread-Based Concurrency

- OS threads or virtual/lightweight threads managed by the runtime
- Synchronization via locks, mutexes, semaphores
- Key concerns: thread pinning, lock contention, deadlocks, pool sizing
- Examples of ecosystems: Java (Virtual Threads), .NET (async/await with thread pool), Ruby (GVL-constrained threads)

### Coroutine/Lightweight-Task Concurrency

- Runtime-managed lightweight tasks that yield cooperatively
- Synchronization via channels, async/await, structured concurrency
- Key concerns: blocking in async context, cancellation propagation, backpressure
- Examples of ecosystems: Go (goroutines + channels), Kotlin (coroutines), Elixir (processes), Python (asyncio), Rust (async/await with tokio)

### Process-Based Concurrency

- Separate OS processes or isolated runtime actors
- Communication via message passing, shared-nothing architecture
- Key concerns: serialization overhead, message ordering, supervision trees
- Examples of ecosystems: Elixir/Erlang (BEAM processes), Ruby (forked workers)

## Stack-Specific Guidance

After loading stack-detect, apply concurrency patterns using the primitives and constraints of the detected stack:

- **Identify the concurrency primitive**: What is the lightweight unit of concurrent work? (thread, goroutine, coroutine, process, task, fiber)
- **Identify synchronization mechanisms**: What does the ecosystem use for coordination? (mutexes, channels, actors, async/await)
- **Identify known constraints**: Does the runtime have limitations? (e.g., GIL/GVL preventing true thread parallelism, thread pinning with certain lock types, blocking calls in async runtimes)
- **Identify pool sizing guidance**: What are the recommended pool sizes for the detected runtime's concurrency model?

If the detected stack is unfamiliar, apply the universal principles above and recommend the user consult their runtime's concurrency documentation.

---

## Output Format

Consuming workflow skills depend on this structure to surface concurrency issues consistently.

```
## Concurrency Assessment

**Stack:** {detected language / framework}
**Concurrency model:** {Thread-based | Coroutine/Lightweight-task | Process-based}
**Primary primitive:** {thread | goroutine | coroutine | process | task | fiber}

### Issues

- [Severity: High | Medium | Low] {file:line if available} - {description of issue}
  - Anti-pattern: {which anti-pattern from the list applies}
  - Risk: {data race | deadlock | goroutine leak | blocking in async context | etc.}
  - Fix: {concrete correction using the detected stack's idioms}

### No Issues Found

{State explicitly if concurrency usage is safe - do not omit this section silently}
```

**Severity guidance:**

- **High**: Data race, deadlock risk, or unbounded concurrency with resource leak potential
- **Medium**: Blocking call inside cooperative concurrency context, missing cancellation
- **Low**: Style drift from the detected stack's idiomatic concurrency approach

Omit "No Issues Found" if issues were listed.

## Database-Level Concurrency

When concurrent requests modify the same database rows, in-process synchronization (mutexes, channels) is insufficient because the race spans multiple application instances. Use database-level strategies:

| Strategy               | Mechanism                                                        | When to Use                                          |
| ---------------------- | ---------------------------------------------------------------- | ---------------------------------------------------- |
| Pessimistic locking    | `SELECT ... FOR UPDATE` - holds row lock until transaction end   | Short-lived transactions with high contention        |
| Optimistic locking     | Version column checked at UPDATE time; retry on conflict         | Read-heavy workloads, low contention                 |
| Serializable isolation | Database detects and aborts conflicting transactions             | Complex invariants across multiple rows              |
| Advisory locks         | Application-level locks managed by DB (e.g., `pg_advisory_lock`) | Cross-process coordination without row-level locking |

**Bad** - In-process mutex for a database race:

```
// This mutex only protects within a single process instance
mu.Lock()
inventory := db.GetInventory(productID)
if inventory.Qty >= orderQty {
    db.SetInventory(productID, inventory.Qty - orderQty)
}
mu.Unlock()
```

Problem: Two application instances can both read the same inventory and both decrement, overselling the product.

**Good** - Database-level optimistic locking:

```
// Version column prevents lost updates across all instances
result := db.Exec(
    "UPDATE inventory SET qty = qty - ?, version = version + 1 WHERE product_id = ? AND version = ? AND qty >= ?",
    orderQty, productID, currentVersion, orderQty,
)
if result.RowsAffected == 0 {
    // Conflict or insufficient stock - retry or fail
}
```

### Distributed Locking

When mutual exclusion must span multiple application instances (e.g., webhook deduplication, scheduled job coordination):

- Redis `SET NX` with TTL for simple distributed locks
- Idempotency keys for webhook and event deduplication (preferred over distributed locks when possible)
- Distributed locks are inherently fragile - prefer idempotent operations over lock-based coordination when the design allows it
- If using distributed locks, always set a TTL to prevent deadlocks from crashed holders

## Testing Concurrent Code

Concurrency bugs often manifest only under contention. Test strategies that surface them:

- **Stress testing**: Run N concurrent operations against shared state and verify invariants hold (e.g., counter matches expected value, no duplicate inserts)
- **Deterministic scheduling**: Use test harnesses that control goroutine/coroutine/thread scheduling to force specific interleavings (where the ecosystem supports it)
- **Race detection**: Enable the runtime's race detector during tests (e.g., `go test -race`, ThreadSanitizer, `--cfg tokio_unstable` for Tokio)
- **Latch-based tests**: Use countdown latches or barriers to ensure all concurrent actors start simultaneously, maximizing contention window
- **Timeout assertions**: Every concurrent test must have a timeout - a deadlock should fail the test, not hang the CI pipeline

## Anti-Patterns (All Stacks)

- Shared mutable state without explicit synchronization
- Unbounded concurrency (always limit parallelism)
- Fire-and-forget work without error handling or cancellation
- Testing concurrent code only on the happy path
- Mixing concurrency paradigms unnecessarily within a single module
- Using blocking operations inside lightweight/cooperative concurrency contexts
- Ignoring cancellation/timeout propagation across concurrent boundaries
- Using in-process mutexes/locks for database-level race conditions (does not protect across multiple application instances)
- Distributed locks without TTL (deadlock risk if the lock holder crashes)
