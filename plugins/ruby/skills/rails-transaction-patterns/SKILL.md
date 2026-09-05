---
name: rails-transaction-patterns
description: "Rails transaction discipline: boundaries, nested + requires_new, savepoints, after_commit, isolation levels, retry under transactions."
metadata:
  category: backend
  tags: [ruby, rails, activerecord, transaction, isolation]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine DB adapter (MySQL/PostgreSQL) - isolation defaults and savepoint behavior differ.

## When to Use

- Designing or reviewing service objects that touch multiple models
- Diagnosing "rollback but write happened" or "job ran before commit" bugs
- Choosing between `after_save` and `after_commit` callbacks
- Deciding whether an inner service needs `requires_new: true`
- Setting an explicit isolation level for a write path
- Reviewing retry logic on uniqueness conflicts or deadlocks

## Rules

- One transaction boundary per business operation; the boundary belongs in the service object, not the model.
- No network calls inside `Model.transaction`. HTTP/S3/Redis/Stripe held under a row lock cascades into fleet-wide lock-wait timeouts on upstream slowdown.
- No `.perform_async` (or `deliver_later`, or any other post-commit dispatch) inside a transaction. The worker runs on its own connection, so it can never see your uncommitted writes - it sees the state *before* them: `RecordNotFound` for a row not yet committed, stale values for one being updated, and nothing at all if you roll back. Use `after_commit_everywhere` when the dispatch lives inside a caller's transaction.
- Inner services that open `transaction` need `requires_new: true` if rescued by the caller - a fused inner block has no savepoint, so the caller's rescue commits the inner writes along with the outer transaction.
- `after_commit` for side effects (jobs, email, HTTP). `after_save` only for in-aggregate derived columns that must be visible inside the same transaction.
- Default isolation is adapter-default (MySQL `REPEATABLE READ`, PG `READ COMMITTED`). Bump only with a documented reason (multi-row invariants, financial ledgers); cost is higher deadlock rate.
- Retry on `ActiveRecord::Deadlocked` and `ActiveRecord::SerializationFailure` (PG) - both expected under contention. Cap at 3 attempts with backoff.
- Idempotency keys live one layer above the transaction - retrying a transaction is safe; retrying a charge is not.

## Patterns

### Transaction boundary - the five-step ordering

A multi-model service with an external call follows one ordering:

```
1. Validate inputs and preconditions          (no transaction)
2. External call (charge, signed URL, etc.)   (no transaction, with idempotency key)
3. Open transaction
4. Persist all DB mutations referencing the external result
5. Commit -> after_commit hooks fire jobs, emails, broadcasts
```

```ruby
def call
  return Result.failure(["invalid"], code: :invalid) unless valid?

  payment = BillingClient.new.charge(charge_params)  # outside transaction, behind a client

  ActiveRecord::Base.transaction do
    @order.update!(status: :paid, stripe_charge_id: payment.id)
    @inventory.decrement!(:available, @order.quantity)
  end

  ShipmentNotificationJob.perform_async(@order.id)  # post-commit
  Result.success(@order.reload)
rescue BillingError::Declined => e     # domain error - services never name a vendor class
  Result.failure([e.message], code: :payment_declined)
end
```

If the DB write fails after the charge, enqueue a reconciliation job (compensating action) - inline refund compounds failure.

When the mutation claims a contended resource (seat, slot, finite stock), charge-first inverts: use the two-transaction variant in `rails-service-objects` - txn 1 claims pending under row lock -> charge -> txn 2 finalizes, with pending-claim expiry.

### Nested transactions and `requires_new`

Rails fuses a re-entered `Model.transaction` block into the outer transaction unless `requires_new: true` is passed (`with_lock` also opens/joins a transaction). Two footguns follow:

```ruby
# Bad - rescue INSIDE the transaction block commits everything
ActiveRecord::Base.transaction do
  @user.update!(...)
  InnerService.call(...)  # raises; meant to cancel only the inner writes
rescue => e
  Rails.logger.warn(e)    # txn never sees the raise -> ALL writes commit, inner included
end
```

- `ActiveRecord::Rollback` raised inside a fused inner block is swallowed by the inner `transaction` call and rolls back **nothing**.
- Rescue placement decides the outcome: rescue outside the transaction block rolls everything back; rescue inside commits everything done so far. When a reported symptom (partial state persisted) contradicts the rescue placement you see, look for a rescue hidden inside the inner service.

Two fixes:

1. **Outer owns the transaction; inner opens none.** Default.

   ```ruby
   class InnerService
     def call
       @record.update!(...)  # relies on caller's transaction
     end
   end
   ```

2. **Inner uses `requires_new: true`** (savepoint; supported on MySQL and PG). Only when the inner must roll back independently while the outer continues.

   ```ruby
   ActiveRecord::Base.transaction(requires_new: true) { @record.update!(...) }
   ```

### `after_save` vs `after_commit`

| Side effect                  | Hook            | Why                                              |
| ---------------------------- | --------------- | ------------------------------------------------ |
| Update derived column        | `after_save`    | Same transaction; must be atomic with the change |
| Sync to external service     | `after_commit`  | Outside transaction; row is durably persisted    |
| Enqueue Sidekiq job          | `after_commit`  | Worker may pick up before commit otherwise       |
| Send email                   | `after_commit`  | Same; also extends lock-hold time inside the txn |
| Cache invalidation           | `after_commit`  | Avoid serving stale data after rollback          |

A callback inside a locked transaction (`with_lock`, `Model.lock.find`) that makes a network call holds the row lock for the network round-trip - the most common cause of `Lock wait timeout` storms.

Two failure modes the table implies but reviews miss:

- A derived column maintained by `after_commit` updates in a *separate* transaction - it can fail or interleave with concurrent writers and leave the column stale. That asymmetry, not style, is why derived columns use `after_save`.
- In bulk loops (`rows.each { create! }` inside one transaction), a per-row callback that recomputes an aggregate runs N times and grows lock-hold time. Recompute once after the loop, or push it into the database: `counter_cache` for association counts, `update_counters` (an atomic `SET col = col + n`) for sum-style columns - `counter_cache` only counts rows, it cannot maintain a sum. A callback that writes a *different* model also adds a cross-model lock-order deadlock surface.

### Post-commit dispatch from inside a caller's transaction

When a service runs inside a caller's transaction, dispatching "after the local block" still fires before the outer commit. Rails 7.2+ ships this natively - `ActiveRecord.after_all_transactions_commit { ... }` (which also runs immediately when no transaction is open) or `Model.current_transaction.after_commit { ... }`. The `after_commit_everywhere` gem is the pre-7.2 equivalent and remains fine where it is already in the Gemfile:

```ruby
class ChargeService
  include AfterCommitEverywhere

  def call
    ActiveRecord::Base.transaction do
      @order.update!(status: :paid)
      after_commit { ShipmentNotificationJob.perform_async(@order.id) }
    end
  end
end
```

The block fires after the outermost commit, regardless of nesting depth.

### Isolation levels

| Level             | Adapter behavior                          | Use when                                  |
| ----------------- | ----------------------------------------- | ----------------------------------------- |
| `:read_committed` | PG default; opt-in on MySQL               | `SKIP LOCKED` claim; fresh reads of concurrent counters |
| `:repeatable_read`| MySQL default; PG opt-in                  | Multi-row read consistency in same txn    |
| `:serializable`   | Highest cost. PG raises `SerializationFailure` (SSI, SQLSTATE 40001); MySQL promotes plain SELECTs to shared locks and deadlocks | Financial ledgers, accounting invariants  |

```ruby
ActiveRecord::Base.transaction(isolation: :serializable) do
  Ledger.transfer(from: a, to: b, amount: cents)
end
```

Tie-breaker before bumping: row-locked read-modify-write (`SELECT ... FOR UPDATE`) already prevents lost updates at default isolation - prefer row locks; reserve `:serializable` for invariants spanning rows you can't enumerate and lock. On MySQL `REPEATABLE READ`, locking reads see the latest committed row (current read), not the transaction snapshot - that fact, not the isolation name, is what a compliance rationale should state.

Bump isolation only with a documented reason. Higher isolation -> more `SerializationFailure` (PG) / `Deadlock` (MySQL) - the caller must retry. For lock-acquisition ordering (sort IDs to kill A->B/B->A deadlocks), nested isolation behavior, and the three-tier per-call-site escalation pattern, see `rails-db-locking-patterns`.

### Retry on deadlock / serialization failure

```ruby
def with_retry(max: 3)
  attempts = 0
  begin
    yield
  rescue ActiveRecord::Deadlocked, ActiveRecord::SerializationFailure  # SerializationFailure: PG-only; harmless to list on MySQL
    attempts += 1
    raise if attempts >= max
    sleep(0.05 * 2**attempts)
    retry
  end
end
```

Wrap the transaction only - side effects (charge, email) stay outside the retried block, per the idempotency rule.

### Long-running transactions

Anything >100ms in a write transaction is a smell on production traffic:

- Holds row locks; other writers queue
- Burns a connection from the pool
- Replication lag compounds on hot tables

Split: open transaction late, close it early. External calls and computation happen outside. See `rails-batch-processing-patterns` for chunk-per-transaction work.

## Output Format

One block per transaction boundary. A flow that opens two (claim, then finalize) emits two, named in order; a review spanning a service, a model method and a callback emits one per boundary and carries the rest as numbered findings.

```
Boundary: <service.call | model callback | controller action | rake task | job perform>

Network calls inside: <Yes (BLOCKER) | No>

Post-commit dispatch inside: <Yes - name it: perform_async / deliver_later / cache write (BLOCKER) | No - uses after_commit | No>

Nested transactions: <None | Inner uses requires_new | Inner relies on outer (caller-aware) | Inner fused + caller rescues (BLOCKER)>

Side-effect hook: <after_commit (correct for side effects) | after_save - derived column (correct) | after_save - side effect (BLOCKER) | after_commit - derived column (GAP) | N/A - no callbacks>

Isolation: <adapter default | :read_committed | :repeatable_read | :serializable - reason: <text>>

Concurrent writers on the same column: <none | row lock / atomic UPDATE | unguarded read-modify-write (BLOCKER) - name the other writer>

Retry strategy: <None | None - GAP (isolation bumped, retry required) | Deadlock retry x N | in-process retry AND job-level retry - GAP, pick one>

Compensating action on partial failure: <Yes - <job> | No - acceptable | No - GAP>
```

`isolation:` is only legal on the outermost transaction: nested, Active Record raises `TransactionIsolationError` before reaching the adapter, on every database. Transactional test fixtures open that outer transaction with `joinable: false`, which makes even a *flat* `transaction(isolation:)` take the savepoint path and raise - so flattening the call does not help and dropping the parameter deletes the behaviour under test. Set `self.use_transactional_tests = false` on that spec instead. Never set isolation on the pool. Lost-update mechanics and lock choice: use skill: `rails-db-locking-patterns`.

## Avoid

- Network/HTTP/S3 calls inside `Model.transaction` - holds locks across round-trip
- `.perform_async` inside `Model.transaction` without `after_commit_everywhere`
- Rescuing inside nested `transaction` blocks without `requires_new` - leaves inner writes committed
- `after_save` for side effects that require the row to exist (jobs read a not-yet-persisted record)
- Bumping isolation level "for safety" without a documented invariant - pays deadlock cost for no gain
- Wrapping retries around side effects (charges, emails) instead of the transaction only
