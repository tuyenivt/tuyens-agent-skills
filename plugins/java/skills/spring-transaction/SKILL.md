---
name: spring-transaction
description: "Design Spring @Transactional boundaries: propagation, self-invocation, rollback, read-only, pool exhaustion, AFTER_COMMIT side effects."
metadata:
  category: backend
  tags: [transactions, database, spring, consistency]
user-invocable: false
---

# Transaction Management

> Load `Use skill: stack-detect` first to determine the project stack. Its `Database` picks the diagnosis queries and the insert-or-ignore syntax: PostgreSQL-family values -> PostgreSQL; MySQL and MariaDB -> MySQL syntax (MariaDB lock waits: `information_schema.innodb_lock_waits`); anything else or `unknown` -> give both variants.

## When to Use

- Defining DB consistency boundaries on the service layer
- Diagnosing connection-pool exhaustion or "transaction not rolling back" bugs
- Coordinating multi-step writes plus side effects (broker, HTTP, email, payment)
- Reviewing transaction boundaries

## Rules

- `@Transactional` on the service layer only - not controller, not repository
- Default propagation `REQUIRED`; deviate only with a written reason
- `readOnly = true` on query-only methods
- Checked exceptions need `rollbackFor` - Spring rolls back only on unchecked by default (unless the app sets `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)` - check before adding `rollbackFor`)
- No remote IO (HTTP, broker, email, S3, payment) inside a transaction - it pins the DB connection and the row locks the transaction already holds
- `spring.jpa.open-in-view=false`. With Boot's default (`true`) the request's EntityManager keeps the connection from the first query until the response is written, so narrowing transactions releases nothing
- Side effects that must not run on rollback fire after commit; side effects that must survive a crash go through a transactional outbox (`spring-messaging-patterns`)
- Pass IDs across thread boundaries (`@Async`, virtual threads, executors), never managed entities
- `timeout` bounds the database statements inside the transaction: each statement gets the remaining time as its JDBC query timeout, so one in flight at the deadline is cancelled (`QueryTimeoutException`; an untranslated `PersistenceException` from a direct `EntityManager` query) and one started after it fails - `TransactionTimedOutException` from `JdbcTemplate` or a direct `EntityManager` query (from a derived repository query, wrapped in Spring Data's `BadJpqlGrammarException`), Hibernate's `TransactionException` ("Transaction timeout expired") for statements Hibernate issues - wrapped in `JpaSystemException` from a repository call (`findById`) and at the commit-time flush, which then rolls back; bare from a lazy load or a direct `EntityManager.find`. It does not interrupt Java code or remote calls. Set it on batch and multi-query transactions from the p99 of the queries inside (typically 2-5s); without latency data, estimate from the query shape and say so

## Patterns

### Self-invocation bypass

`@Transactional` rides Spring's AOP proxy. `this.method()` calls bypass the proxy - no transaction starts.

```java
// Bad - createWithAudit's @Transactional is ignored
class OrderService {
    Order create(OrderRequest req) { return createWithAudit(req); }
    @Transactional Order createWithAudit(OrderRequest req) { ... }
}

// Good - inject self so the proxy intercepts (or extract to a separate bean)
class OrderService {
    private final OrderService self;
    OrderService(@Lazy OrderService self) { this.self = self; }  // @Lazy on the ctor param; on a final field it is ignored
    Order create(OrderRequest req) { return self.createWithAudit(req); }
    @Transactional Order createWithAudit(OrderRequest req) { ... }
}
```

Prefer a collaborator bean when the inner method has a distinct responsibility; self-injection is fine for thin wrappers.

### Remote IO pins the connection pool

A 2-second HTTP call inside `@Transactional` holds a HikariCP connection for 2 seconds. Size from `connections = arrival rate x hold time`: 120 rps x 30ms of DB work needs ~4 connections; the same 120 rps with a 1.5s call inside the transaction needs ~184, and a pool of 20 supports 13 rps. Two amplifiers:

- Every row the transaction has already written to the database stays locked until its commit - `JdbcTemplate` and `@Modifying` statements, `IDENTITY` inserts, anything flushed before the call (Hibernate defers dirty-checked updates to the commit flush, so those lock only after the call returns) - so other requests block on those rows *while holding their own connections* - endpoints that never make the remote call time out too. Their wait is hold time as well, so measured exhaustion exceeds `rate x remote latency`; name the difference as lock amplification, `(inferred)` unless lock waits were sampled during the incident.
- With `spring.threads.virtual.enabled=true` the 200-thread Tomcat cap is gone (admission is bounded only by `server.tomcat.max-connections`, default 8192), so overload queues at Hikari's 30s `connectionTimeout`. Set `connection-timeout` to fail fast, and bound the remote call itself (read timeout + a concurrency limit) - it is now the only bounded resource. A parked HTTP call on a virtual thread still holds the connection bound to that thread.

Confirm before rewriting. PostgreSQL: `pg_stat_activity` shows backends `idle in transaction` with an old `xact_start`, plus backends with `wait_event_type = 'Lock'`; a transaction that has sent no SQL yet (Hibernate defers inserts and dirty updates to the flush) holds its pool connection while its backend shows plain `idle`, so Hikari's active and pending counts are the hold-time evidence. MySQL: `information_schema.innodb_trx` (old `trx_started`) plus `performance_schema.data_lock_waits` (8.0+).

```java
// Bad
@Transactional
void placeOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    inventoryClient.reserve(order.getId());  // 1-3s HTTP, holds the DB connection
    kafkaTemplate.send("orders", order);
}

// Good - narrow tx around DB work; the side effect runs after commit
void placeOrder(OrderRequest req) {
    inventoryClient.reserve(req.itemId(), req.qty());  // pre-tx, no connection held (with OSIV off)
    self.saveOrder(req);
}

@Transactional
void saveOrder(OrderRequest req) {
    Order order = orderRepository.save(new Order(req));
    events.publishEvent(new OrderPlacedEvent(order.getId()));
}

@TransactionalEventListener(phase = AFTER_COMMIT)
@Async
void onPlaced(OrderPlacedEvent e) { kafkaTemplate.send("orders", e.orderId()); }
```

Pre-tx calls add a compensation duty: if `saveOrder` fails, the reservation leaks - release it in a catch block and, where the remote system offers one, reserve with a TTL as the backstop for a crash before the catch runs (a system you do not own gets whichever of the two it supports). The duty belongs to the method that makes the remote call (the orchestrator); its transactional callees carry none.

### AFTER_COMMIT listeners

AFTER_COMMIT listeners run in the transaction's `afterCompletion` callback, before the connection is released. So:

- A synchronous listener still holds the connection - slow work belongs on `@Async`.
- An exception thrown by a synchronous listener is caught and logged by Spring and never reaches the caller: the request returns success and the side effect is silently lost. Required effects go through the outbox.
- A listener that writes needs `@Transactional(propagation = REQUIRES_NEW)`. Spring 6.1+ fails startup when a `@TransactionalEventListener` carries `@Transactional` (on the method; 6.2+ also its class) with any propagation other than `REQUIRES_NEW` / `NOT_SUPPORTED` (6.1.3+; 6.2.10+ exempts `BEFORE_COMMIT`); and a `REQUIRED` write in a callee joins the completed transaction and never commits.
- An `@Async` handler that loads by ID is safe only because it runs after commit - dispatching `@Async` work directly from inside the transaction races the commit and can read nothing. The same holds for virtual-thread executors and `CompletableFuture` chains: the async method takes the ID, opens its own transaction and re-reads committed state.

### Remote call whose result must be persisted (payment)

Neither pre-tx nor AFTER_COMMIT fits. State machine - short tx before, no tx around the call, short tx after:

```java
public Order placeOrder(OrderRequest req) {
    Order order = self.createPending(req);                    // tx 1: PENDING row, idempotency key
    ChargeResult r;
    try {
        r = paymentGateway.charge(order.idempotencyKey(), order.total());   // no connection held
    } catch (PaymentDeclinedException e) {
        self.markDeclined(order.getId(), e.reason());          // definite outcome
        throw e;
    }
    // A timeout or a failure below leaves the row PENDING - the outcome is unknown, not failed
    return self.completeCharge(order.getId(), r);             // tx 2: PAID
}
```

- Only a definite decline marks the row failed. An ambiguous gateway error (timeout, 5xx) or a failure in tx 2 leaves it PENDING, and a scheduled reconciliation job resolves PENDING rows against the gateway by idempotency key - so a charged order is never recorded as failed. Any intermediate claim state of another flow (`SETTLING`, `REFUNDING`) is PENDING under another name and gets the same reconciliation.
- The idempotency key is generated once per PENDING row in tx 1 and stored on it before the call, so every retry of the call reuses it; a key generated per attempt, or taken from an optional client header (`null` - a unique constraint accepts any number of NULLs), makes every retry a new charge. A client that wraps every failure in one exception type is split first, by the gateway's response code, into declined and ambiguous - until then every failure is ambiguous and stays PENDING.
- The same shape holds for any tap/terminal flow: `AWAITING_PAYMENT` before the call, a terminal state after, `UNKNOWN` for ambiguous outcomes.

### "Not rolling back" - five causes

Rule these out in order before assuming a Spring bug:

1. **Checked exception** - rollback is unchecked-only by default. Add `rollbackFor`.
2. **Exception caught inside the method** - nothing propagates. Rethrow or `setRollbackOnly()`.
3. **Self-invocation** - `this.txMethod()` never enters the proxy.
4. **Private, `final` or `static` method** - silently not advised (Boot's class-based proxies do advise protected/package-private methods).
5. **Write outside the managed connection** - `dataSource.getConnection()` returns a separate connection even on the Spring-managed pool; go through `JdbcTemplate`, `DataSourceUtils.getConnection(dataSource)`, or a `TransactionAwareDataSourceProxy`. With several `DataSource`s, a write through one whose transaction manager is not the one `@Transactional` resolved is also outside it - name it with `@Transactional(transactionManager = ...)`.

```java
// Bad - PaymentException is checked: the transaction COMMITS despite the failure
@Transactional
void processPayment(Order order) throws PaymentException { ... }

// Good
@Transactional(rollbackFor = Exception.class)
void processPayment(Order order) throws PaymentException { ... }
```

### Read-only services

`readOnly = true` sets Hibernate's flush mode to MANUAL and marks the JDBC connection read-only. An UPDATE in a `readOnly` method still commits when the method joins a caller's read-write transaction - the flag applies only where the transaction starts. In a transaction that does start read-only, changes to existing entities are dropped silently - whether dirty-checked or passed to `save` / `saveAndFlush`, which merges them into a read-only instance - and so is a new entity passed to `save` whose ID needs no database call (`UUID`, a cached `SEQUENCE` block); only a statement that reaches the database fails with a read-only-transaction error (`@Modifying` queries, `saveAndFlush` of a new entity, an `IDENTITY` insert, PostgreSQL's `nextval()` refilling the sequence block). Removing a stray controller-level `@Transactional` flips which method starts the transaction - fix the write method's annotation in the same change.

```java
@Service @Transactional(readOnly = true) @RequiredArgsConstructor
class OrderQueryService {
    private final OrderRepository orderRepo;   // extends JpaRepository<Order, Long>, JpaSpecificationExecutor<Order>

    public Page<OrderDto> search(Specification<Order> spec, Pageable p) {
        return orderRepo.findAll(spec, p).map(OrderDto::from);
    }

    @Transactional  // override for writes
    public OrderDto updateStatus(Long id, OrderStatus s) { ... }
}
```

Replica routing: `readOnly` reaches a read replica only behind a `LazyConnectionDataSourceProxy` (otherwise the connection is taken before the flag is set) - `new LazyConnectionDataSourceProxy(primary)` + `setReadOnlyDataSource(replica)` (Spring 6.1.2+), or the proxy around an `AbstractRoutingDataSource` keyed on `TransactionSynchronizationManager.isCurrentTransactionReadOnly()` - Boot 4.1's `spring.datasource.connection-fetch=lazy` adds the proxy with no replica, so it defers acquisition and routes nothing.

### `REQUIRES_NEW` for records that must survive rollback

```java
@Component
class AuditLog {
    @Transactional(propagation = REQUIRES_NEW)
    public void write(String action, String ref, String outcome) { ... }   // commits even if the caller rolls back
}
```

It suspends the outer transaction and takes a second connection. Two failure modes: if the inner transaction touches a row the suspended outer one has locked, it waits on itself - no deadlock is detected, it hangs until `lock_timeout` (PostgreSQL, default none) / `innodb_lock_wait_timeout` (MySQL, 50s); and once concurrent callers reach the pool size, each holds one connection waiting for a second - pool deadlock until `connectionTimeout`. Keep it out of loops. Decide per record which semantics it needs: an audit of the *attempt* (a declined payment, a rejected request) must survive the rollback - `REQUIRES_NEW`; an audit of the *outcome* belongs to the business transaction - `REQUIRED`, gone with it on rollback.

### Batch jobs: short transaction per item

A scheduled or batch orchestrator has no transaction of its own (`none - orchestrator, tx lives in callees`) and calls a `@Transactional` per-item (or per-chunk) method, so one bad item neither rolls back nor blocks the rest and no transaction spans the whole run. Overlap between runs is the scheduler's concern (`spring-async-processing`).

### Concurrent-write anomalies

Lost updates (two tills selling the last unit) are a locking concern, not a propagation one: an atomic conditional `UPDATE ... WHERE on_hand >= :qty`, optimistic `@Version` + retry, or a pessimistic lock - see `spring-jpa-performance`. A transaction that updates several rows (every line's stock) locks them in a fixed order (sorted by ID), or two orders sharing items deadlock. `isolation = SERIALIZABLE` is the last resort.

### Idempotent writes

The unique constraint on the idempotency key is the barrier; the claim is its own short transaction and the remote work follows it (state machine above). The insert must not fail inside the business transaction: through a repository or JPA, a caught `DataIntegrityViolationException` still marks it rollback-only (`UnexpectedRollbackException` at commit) and the Hibernate session is unusable after the failed flush; on PostgreSQL any failed statement also aborts the transaction. Insert-or-ignore, then read:

```java
@Transactional
PaymentResponse processPayment(PaymentRequest req) {
    int inserted = jdbc.update("""
        INSERT INTO payments (idempotency_key, amount, status) VALUES (?, ?, 'PENDING')
        ON CONFLICT (idempotency_key) DO NOTHING""",            // MySQL: INSERT IGNORE INTO ... - it also silences
                                                        // NOT NULL/FK/truncation errors, so validate the row first;
                                                        // ON DUPLICATE KEY UPDATE returns 1 on replay by default
        req.idempotencyKey(), req.amount());
    Payment p = paymentRepository.findByIdempotencyKey(req.idempotencyKey()).orElseThrow();
    return inserted == 1 ? PaymentResponse.accepted(p) : PaymentResponse.from(p);   // 0 = replay: stored result
}
```

Alternative: the insert in a `@Transactional` method on another bean, called from a non-transactional method that catches the violation and re-reads in a fresh transaction (`REQUIRES_NEW` only when some callers are already transactional).

## Output Format

In every mode, emit the `**Engine:**` line once, then one block per method whose transactional configuration or call path the design sets or changes - including methods the fix extracts into new beans and the orchestrator that calls them; a callee that joins its caller's transaction unchanged, every repository method, and methods the design leaves exactly as they are get none; a callee the design changes whose source was not provided gets its block with `unknown - <class> not reviewed` in the slots its source would fill. Diagnosis answers (an incident's questions, with numbers) go in prose before the findings; a cause established by inference rather than evidence carries `(inferred)`. Carry a current broken value in `Reason` as `was: ...`; a setting considered and rejected (`isolation = SERIALIZABLE`, `REQUIRES_NEW`, outbox) goes in `Reason` as `rejected: <setting> - <why>`. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, list findings first - `### [Must|Recommend] file:line` (pasted input: `Class.method`), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when it can exhaust the pool, commit a failure, lose a required side effect, or lose an update, `[Recommend]` otherwise - then the blocks for the target design. A design request against existing code reviews that code first: findings, then the blocks as the target state; a greenfield request has no findings. Close with the `Pool:` line whenever pool sizing or connection hold time is part of the analysis.

```
**Engine:** {PostgreSQL | MySQL | MariaDB - MySQL syntax | <detected engine> - both variants given | unknown - both variants given}
```

```
Method: {class.method}

Propagation: {REQUIRED | REQUIRES_NEW | MANDATORY | SUPPORTS | NOT_SUPPORTED | NEVER | NESTED | none - orchestrator, tx lives in callees | none - no transaction}

Read-Only: {Yes | No | n/a}

Rollback: {default | rollbackFor=Exception.class | custom | n/a}

Timeout: {seconds - <derived from query p99 | estimated from query shape> | none - no bound set | n/a - joins the caller's transaction | n/a - no transaction}

External-IO-In-Tx: {Yes | No}

Concurrency: {none needed | atomic conditional UPDATE | @Version + retry | PESSIMISTIC_WRITE | unique constraint | isolation = SERIALIZABLE + retry on serialization failure}

Compensation: {catch-and-release | TTL reservation | catch-and-release + TTL | reconciliation job | none needed - <the call is a read or idempotent> | n/a - this method makes no remote call}

Post-Commit Hooks: {AFTER_COMMIT events | outbox | none}

Reason: {why this configuration; "was: <current setting>" and "rejected: <setting> - <why>" where they apply}
```

Closing line, once per deliverable - `required` is the cluster-wide figure computed with the designed hold time (the incident's hold time and its product belong in the diagnosis prose), compared with the product:

```
Pool: {maximum-pool-size} x {instances}, connection-timeout {s}, db max_connections {n | unknown}; required ~ {rate} x {hold time} = {n | unknown - no rate data}
```

## Avoid

- `REQUIRES_NEW` in loops, or without a written reason
- Catching `DataIntegrityViolationException` and continuing in the same transaction
