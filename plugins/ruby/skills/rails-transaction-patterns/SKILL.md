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

- One transaction boundary per business operation; that boundary belongs in the service object, not the model.
- No network calls inside `Model.transaction` - HTTP/S3/Redis/Stripe held under a row lock cascades into fleet-wide lock-wait timeouts on upstream slowdown.
- No `.perform_async` inside a transaction - the worker can pick the job up before the commit and see uncommitted state. Use `after_commit_everywhere` when the dispatch lives inside a caller's transaction.
- Inner services that open `transaction` need `requires_new: true` if rescued by the caller - otherwise rescued exceptions leave the inner savepoint committed.
- `after_commit` for side effects (jobs, email, HTTP). `after_save` only for in-aggregate derived columns that must be visible inside the same transaction.
- Default isolation (`READ COMMITTED` on MySQL/PG) is correct for most writes. Bump to `:repeatable_read` or `:serializable` only with a documented reason (multi-row invariants, financial ledgers); cost is higher deadlock rate.
- Retry on `ActiveRecord::Deadlocked` and `ActiveRecord::SerializationFailure` (PG) - both are expected under contention. Cap at 3 retries with backoff.
- Idempotency keys live one layer above the transaction - retrying a transaction is safe; retrying a charge is not.

## Patterns

### Transaction Boundary - The Five-Step Ordering

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
  return Result.failure(:invalid) unless valid?

  payment = Stripe::Charge.create(charge_params)  # outside transaction

  ActiveRecord::Base.transaction do
    @order.update!(status: :paid, stripe_charge_id: payment.id)
    @inventory.decrement!(@order.items)
  end

  ShipmentNotificationJob.perform_async(@order.id)  # post-commit
  Result.success(@order.reload)
rescue Stripe::CardError => e
  Result.failure(:payment_declined, e.message)
end
```

If the DB write fails after the charge, enqueue a reconciliation job (compensating action) - inline refund compounds failure.

### Nested Transactions and `requires_new`

When A calls B and both open `transaction`, the inner is a **savepoint** by default, **but** Rails treats a re-entered `Model.transaction` block as part of the outer transaction unless `requires_new: true` is passed. A `raise` inside B caught in A leaves B's writes committed.

Bad - silent partial-commit:

```ruby
def outer_service.call
  ActiveRecord::Base.transaction do
    @user.update!(...)
    InnerService.call(...)  # raises inside its own transaction; outer rescues
  rescue => e
    Rails.logger.warn(e)    # @user update is rolled back; inner writes already committed
  end
end
```

Good - two choices:

1. **Outer owns the transaction; inner does not open one.** Preferred when B is only called from A.

   ```ruby
   class InnerService
     def call
       # no transaction here; rely on caller's
       @record.update!(...)
     end
   end
   ```

2. **Inner uses `requires_new: true`.** Use when B is called from multiple places.

   ```ruby
   ActiveRecord::Base.transaction(requires_new: true) do
     @record.update!(...)
   end
   ```

### `after_save` vs `after_commit`

| Side effect                  | Hook            | Why                                                  |
| ---------------------------- | --------------- | ---------------------------------------------------- |
| Update derived column        | `after_save`    | Same transaction; must be atomic with the change     |
| Sync to external service     | `after_commit`  | Outside transaction; row is durably persisted        |
| Enqueue Sidekiq job          | `after_commit`  | Worker may pick up before commit otherwise           |
| Send email                   | `after_commit`  | Same; also extends lock-hold time inside the txn     |
| Cache invalidation           | `after_commit`  | Avoid serving stale data after rollback              |

A callback inside a locked transaction (`with_lock`, `Model.lock.find`) that makes a network call holds the row lock for the network round-trip - the most common cause of `Lock wait timeout` storms.

### `after_commit_everywhere` for Nested Dispatch

When a service runs inside a caller's transaction, dispatching "after the local block" still fires before the outer commit. Use `after_commit_everywhere`:

```ruby
class ChargeService
  def call
    ActiveRecord::Base.transaction do
      @order.update!(status: :paid)
      after_commit { ShipmentNotificationJob.perform_async(@order.id) }
    end
  end
end
```

The block fires after the outermost commit, regardless of nesting depth.

### Isolation Levels

| Level             | Adapter behavior                        | Use when                                  |
| ----------------- | --------------------------------------- | ----------------------------------------- |
| `:read_committed` | MySQL/PG default                        | Most CRUD; row locks suffice              |
| `:repeatable_read`| MySQL default; PG opt-in                | Multi-row read consistency in same txn    |
| `:serializable`   | Highest cost; deadlocks under contention| Financial ledgers, accounting invariants  |

```ruby
ActiveRecord::Base.transaction(isolation: :serializable) do
  Ledger.transfer(from: a, to: b, amount: cents)
end
```

Bump isolation only with a documented reason. Higher isolation -> more `SerializationFailure` (PG) / `Deadlock` (MySQL) - the caller must retry.

### Retry on Deadlock / Serialization Failure

```ruby
def with_retry(max: 3)
  attempts = 0
  begin
    yield
  rescue ActiveRecord::Deadlocked, ActiveRecord::SerializationFailure
    attempts += 1
    raise if attempts >= max
    sleep(0.05 * 2**attempts)
    retry
  end
end
```

Idempotency keys belong outside this retry boundary - retrying the transaction is safe; retrying a side effect (charge, email) is not.

### Long-Running Transactions

Anything >100ms in a write transaction is a smell on production traffic:

- Holds row locks; other writers queue
- Burns a connection from the pool
- Replication lag compounds on hot tables

Split: open transaction late, close it early. External calls and computation happen outside. See `rails-batch-processing-patterns` for chunk-per-transaction work.

## Output Format

When reviewing a transaction boundary:

```
Boundary: <service.call | model callback | controller action>
Network calls inside: <Yes (BLOCKER) | No>
.perform_async inside: <Yes (BLOCKER) | No - uses after_commit | No>
Nested transactions: <None | Inner uses requires_new | Inner relies on outer (caller-aware)>
Isolation: <:read_committed (default) | :repeatable_read | :serializable - reason: <text>>
Retry strategy: <None | Deadlock retry x N>
Compensating action on partial failure: <Yes - <job> | No - acceptable | No - GAP>
```

## Avoid

- Network/HTTP/S3 calls inside `Model.transaction` - holds locks across round-trip
- `.perform_async` inside `Model.transaction` without `after_commit_everywhere`
- Rescuing inside nested `transaction` blocks without `requires_new` - leaves inner writes committed
- `after_save` for side effects that require the row to exist (jobs read a not-yet-persisted record)
- Bumping isolation level "for safety" without a documented invariant - pays deadlock cost for no gain
- Wrapping retries around side effects (charges, emails) instead of the transaction only
