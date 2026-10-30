---
name: rails-transaction-patterns
description: "Rails transaction discipline: boundaries, nested + requires_new, savepoints, after_commit, isolation levels, retry under transactions."
metadata:
  category: backend
  tags: [ruby, rails, activerecord, transaction, isolation]
user-invocable: false
---

> Load `Use skill: stack-detect` first to confirm the DB is MySQL (InnoDB) - the isolation and locking rules below are InnoDB's; on `Database: unknown` read `config/database.yml`.

## When to Use

- Designing or reviewing service objects that touch multiple models
- Diagnosing "rollback but write happened" or "job ran before commit" bugs
- Choosing between `after_save` and `after_commit` callbacks
- Deciding whether an inner service needs `requires_new: true`
- Setting an explicit isolation level for a write path
- Reviewing retry logic on uniqueness conflicts or deadlocks

## Rules

- One transaction boundary per business operation; the boundary belongs in the service object, not the model.
- No network calls inside `Model.transaction`. HTTP/S3/Redis/Stripe held under a row lock cascades into fleet-wide lock-wait timeouts on upstream slowdown. An Active Storage `attach` is a local write (its upload runs in `after_commit`) - `rails-active-storage-patterns`.
- No `.perform_async` (or `deliver_later`, a broadcast, or any other post-commit dispatch) inside a transaction. The worker runs on its own connection, so it can never see your uncommitted writes - it sees the state *before* them: `RecordNotFound` for a row not yet committed, stale values for one being updated, and a job for work that never happened if you roll back. Use `ActiveRecord.after_all_transactions_commit` or `after_commit_everywhere` when the dispatch lives inside a caller's transaction. Active Job `perform_later` / `deliver_later` is deferred to commit only when the job class sets `self.enqueue_after_transaction_commit = true` (default `false`; the app-wide config key is ignored on 8.1 and the adapter is never consulted - read the job class); `deliver_later` follows `ActionMailer::MailDeliveryJob`, which inherits `ActiveJob::Base`, not `ApplicationJob`. Sidekiq-native `perform_async` is never deferred unless `Sidekiq.transactional_push!` is on - and even then `perform_bulk` / `push_bulk` and any push inside a `Sidekiq::Batch` go out immediately. The one transactional enqueue is Solid Queue with no `config.solid_queue.connects_to` in `config/environments/production.rb` (queue tables in the primary database; `solid_queue:install` writes `{ database: { writing: :queue } }` there, which makes the enqueue non-transactional): the job row is inserted in the caller's transaction, invisible until commit and gone on rollback.
- Inner services that open `transaction` need `requires_new: true` when the caller rescues inside its own transaction block - a fused inner block has no savepoint, so that rescue commits the inner writes along with the outer transaction. An inner that rescues inside its own block commits its writes with or without `requires_new` (the block exits normally, so the savepoint is released): under `requires_new: true` its rescue ends in `raise ActiveRecord::Rollback`, or the rescue moves outside the block.
- `return`, `break` or `throw` inside a transaction block commits the writes made before it: an exit that means failure raises, or `raise ActiveRecord::Rollback`; `next :code` out of the block is the deliberate commit-and-report exit.
- `after_commit` for side effects (jobs, email, HTTP, broadcasts). `before_save` for a derived column on the record's own row; `after_save` for a derived value on another row of the aggregate that must change in the same transaction.
- Default isolation is InnoDB's `REPEATABLE READ`. Any non-default needs a documented reason: raising it (`:serializable`) costs deadlocks, lowering it (`:read_committed`) costs snapshot consistency.
- Retry on `ActiveRecord::Deadlocked` (MySQL error 1213, which rolls back the whole transaction) - expected under contention. Cap at 3 attempts with backoff. `ActiveRecord::LockWaitTimeout` and `RecordNotUnique` roll back only the failing statement (`innodb_rollback_on_timeout` is off by default): never retry a lock-wait timeout from a rescue inside the transaction block (earlier writes stay applied) - retry around the outermost boundary, or let the job's retry rerun the unit - and handle a uniqueness race with `create_or_find_by` (safe from the snapshot `RecordNotFound` on 7.2+ - its re-read is a locking read: `where(attrs).lock.find_by!` through 8.1.3, whose `FOR UPDATE` can still `Deadlocked` against concurrent losers inside MySQL transactions, covered by the outermost deadlock retry; `FOR SHARE` from 8.1.4 removes that) or a hand-written rescue whose re-read uses `.lock` or sits at the outermost boundary - a plain `find_by!` inside an open REPEATABLE READ transaction reads a snapshot that may predate the winner's commit and raises `RecordNotFound`.
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
# Called outside any transaction: the charge must not run under a caller's locks.
def call
  return Result.failure(["invalid"], code: :invalid) unless valid?

  payment = BillingClient.new.charge(charge_params)  # outside transaction, behind a client

  begin
    with_retry do                              # deadlock retry at the outermost boundary
      ActiveRecord::Base.transaction do
        @order.update!(status: :paid, payment_id: payment.id)
        LedgerEntry.create!(order: @order, amount_cents: @order.total_cents)   # no contended resource here
      end
    end
  rescue ActiveRecord::ActiveRecordError     # the write failed for good after the charge - compensate, never refund inline
    PaymentReconciliationJob.perform_async(payment.id, "order_write_failed")   # no transaction is open here
    raise
  end

  ActiveRecord.after_all_transactions_commit { ShipmentNotificationJob.perform_async(@order.id) }
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
  @user.update!(name: params[:name])
  InnerService.call(@user)  # raises; meant to cancel only the inner writes
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
       @record.update!(status: :active)  # relies on caller's transaction
     end
   end
   ```

2. **Inner uses `requires_new: true`** (savepoint). Only when the inner must roll back independently while the outer continues - which needs the caller to rescue *inside* its block, right around the inner call. A savepoint rolls back only on a raise: an inner that returns `Result.failure` without raising releases it and its writes commit. A caller rescue outside the outer block rolls everything back, and a `Result` is read after the block. Rolling back to the savepoint undoes the inner's writes but keeps its locks on existing rows until the outer transaction ends (InnoDB drops them early only for rows the inner inserted, or when nothing touched InnoDB before the savepoint), so concurrent writers on those rows stay blocked behind the outer.

   ```ruby
   ActiveRecord::Base.transaction(requires_new: true) { @record.update!(status: :active) }
   ```

### `after_save` vs `after_commit`

| Side effect                  | Hook            | Why                                              |
| ---------------------------- | --------------- | ------------------------------------------------ |
| Derived column, same row     | `before_save`   | Written in the same UPDATE                       |
| Derived value, another row   | `after_save`    | Same transaction; must be atomic with the change |
| Sync to external service     | `after_commit`  | Outside transaction; row is durably persisted    |
| Enqueue Sidekiq job          | `after_commit`  | Worker may pick up before commit otherwise       |
| Send email / broadcast       | `after_commit`  | Same; also extends lock-hold time inside the txn |
| Cache invalidation           | `after_commit`  | Invalidated before commit, a concurrent read re-caches the old value |

Moving a guarded callback (`if: :saved_change_to_status?`) from `after_save` to `after_commit` keeps the guard working when the record is saved once per transaction - `saved_change_to_*?` reads the last save, so a second save of it in the same transaction hides the change; capture it in `after_save` then.

A callback inside a locked transaction (`with_lock`, `Model.lock.find`) that makes a network call holds the row lock for the network round-trip - the most common cause of `Lock wait timeout` storms.

Two failure modes the table implies but reviews miss:

- A derived column maintained by `after_commit` updates in a *separate* transaction - it can fail or interleave with concurrent writers and leave the column stale. That asymmetry, not style, is why derived values stay in the transaction - `before_save` on this row, `after_save` on another.
- In bulk loops (`rows.each { create! }` inside one transaction), a per-row callback that recomputes an aggregate runs N times and grows lock-hold time. Recompute once after the loop, or push it into the database: `counter_cache` for association counts, `update_counters` (an atomic `SET col = col + n`) for sum-style columns - `counter_cache` only counts rows, it cannot maintain a sum. A callback that writes a *different* model also adds a cross-model lock-order deadlock surface.

### Post-commit dispatch from inside a caller's transaction

When a service runs inside a caller's transaction, dispatching "after the local block" still fires before the outer commit. Rails 7.2+ ships this natively - `ActiveRecord.after_all_transactions_commit { ... }` (which also runs immediately when no transaction is open) or `Model.current_transaction.after_commit { ... }`. The `after_commit_everywhere` gem is the pre-7.2 equivalent and remains fine where it is already in the Gemfile:

```ruby
class ChargeService
  def call
    ActiveRecord::Base.transaction do
      @order.update!(status: :paid)
      ActiveRecord.after_all_transactions_commit { ShipmentNotificationJob.perform_async(@order.id) }
    end
  end
end
```

The block fires after the outermost commit, regardless of nesting depth (the gem form: `include AfterCommitEverywhere`, then `after_commit { ... }` inside the transaction).

### Isolation levels

| Level             | Adapter behavior                          | Use when                                  |
| ----------------- | ----------------------------------------- | ----------------------------------------- |
| `:read_committed` | Opt-in                                    | `SKIP LOCKED` claim (the documented reason: under REPEATABLE READ the claim's next-key locks block concurrent INSERTs - enqueues - into the scanned range; claimers skip each other at either level; the claim query is `rails-db-locking-patterns`'); fresh reads of concurrent counters |
| `:repeatable_read`| InnoDB default                            | Multi-row read consistency in same txn    |
| `:serializable`   | Highest cost. InnoDB promotes plain SELECTs to shared locks, so contention surfaces as lock waits and deadlocks | Invariants over rows you can't enumerate and lock |
| `:read_uncommitted` | Dirty reads                             | Never                                     |

Tie-breaker before bumping: row-locked read-modify-write (`SELECT ... FOR UPDATE`) already prevents lost updates at default isolation - prefer row locks; reserve `:serializable` for invariants spanning rows you can't enumerate and lock. A transfer touches two known rows, so it locks them:

```ruby
ActiveRecord::Base.transaction do
  accounts = Account.where(id: [from_id, to_id]).order(:id).lock.index_by(&:id)   # PK order kills A->B / B->A
  transfer.lock!
  next if transfer.posted?                    # replay guard, read under the lock
  accounts.fetch(from_id).decrement!(:balance_minor, amount)
  accounts.fetch(to_id).increment!(:balance_minor, amount)
  transfer.update!(state: "posted")
end
```

On MySQL `REPEATABLE READ`, locking reads see the latest committed row (current read), not the transaction snapshot - that fact, not the isolation name, is what a compliance rationale should state.

Higher isolation -> more `Deadlocked` - the caller must retry. For lock-acquisition ordering (sort IDs to kill A->B/B->A deadlocks), nested isolation behavior, and the three-tier isolation escalation (default / per-transaction / per-connection), see `rails-db-locking-patterns`.

### Retry on deadlock

```ruby
def with_retry(max: 3)
  # transactional fixtures are non-joinable, so current_transaction is NULL_TRANSACTION here and specs pass this guard
  raise ArgumentError, "retry only at the outermost transaction" if ActiveRecord::Base.current_transaction.open?
  attempts = 0
  begin
    yield
  rescue ActiveRecord::Deadlocked
    attempts += 1
    raise if attempts >= max
    sleep(0.05 * 2**attempts)
    retry
  end
end
```

Wrap the outermost transaction only - side effects (charge, email) stay outside the retried block, per the idempotency rule.

### Long-running transactions

Anything >100 ms in a write transaction holds row locks, burns a pool connection and compounds replica lag (a long read-only transaction holds no row locks but still pins undo purge and a connection): open late, close early, with external calls and computation outside (`rails-batch-processing-patterns` for chunk-per-transaction work).

## Output Format

One block per transaction boundary. A flow that opens two (claim, then finalize) emits two, named in order (in review, the existing block keeps its name and takes the first boundary's corrected values, and a `(proposed)` block takes the one the fix adds); a review spanning a service, a model method and a callback emits one per boundary, and observations that name no boundary - a lock order, a callback on another model, a dispatch reached transitively through a composed service - are numbered findings with no block. A unit that writes with no explicit transaction (a single `update!` in a job `perform`) gets a block only when the fix adds one, `(proposed)`; its observations are otherwise numbered findings. In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no client class, no transaction, no channel class) gets a block for the unit the fix introduces, its name suffixed `(proposed)`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to add code, or to change code the request does not ask you to judge, is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding. A request that names existing code to assess, even when it also asks for the fix, is review mode. `Nested transactions:` states this block's own relationship to its caller; a service reached from two call sites emits one block per call site when the relationship differs. A callback on the boundary's own model folds into that block; in build mode the numbered findings carry pre-existing violations the design replaces. A block's name is the first part of its `Boundary:` line.

The job backend comes from the Gemfile (`sidekiq` or `solid_queue`), not from stack-detect. An Active Job class (`ApplicationJob`, any backend) retries through `retry_on` / `discard_on` and enqueues with `perform_later`; a `Sidekiq::Job` retries through `sidekiq_options retry:` + `sidekiq_retry_in` and enqueues with `perform_async`. In `Retry strategy` and `Post-commit dispatch inside`, read the backend's own channel: `retry_on` / `perform_later` for an Active Job class, `sidekiq_options retry:` / `perform_async` for a `Sidekiq::Job`. A `rescue` inside `perform` for a class the retry channel owns wins and silently disables that retry - one channel per class.

```
Boundary: <Class#method or job class>{ (proposed)} - <service.call | model callback - GAP (move to a service) | model method - GAP (move to a service) | controller action - GAP (move to a service) | rake task | job perform | out of the read set - name the file>

Network calls inside: <Yes (BLOCKER) | No>

Post-commit dispatch inside (list every dispatch): <Yes - name it: perform_async / deliver_later / broadcast / cache write (BLOCKER) | No - deferred via after_all_transactions_commit / current_transaction.after_commit / after_commit_everywhere | No - Active Job deferred by enqueue_after_transaction_commit (name the Rails version and the setting or job class that proves it) | No - Sidekiq transactional_push! enabled (a `perform_bulk` / `push_bulk` or in-batch push is still `Yes`) | No - Solid Queue on the primary database (no connects_to; the job row is in the caller's transaction) | unknown - Solid Queue, the production config.solid_queue.connects_to not in evidence | unknown - Active Job, deferral setting or Rails version not in evidence | unknown - Sidekiq, the transactional_push! initializer not in evidence | No - uses after_commit | No>

Hold time: <under 100 ms | long - GAP (name the work inside that could move out; an unbounded loop in evidence is long even untimed) | long, read-only - GAP (no row locks, but it pins the read view against undo purge and holds a connection - name the reads to move) | unknown - the work inside is not in evidence>

Nested transactions (list every value that applies, ` + `-joined): <None | Inner uses requires_new | Inner relies on outer (caller-aware) | Inner fused + caller rescues (BLOCKER) | ActiveRecord::Rollback inside a fused block (BLOCKER - swallowed) | rescue inside the transaction block (BLOCKER - commits partial state) | return / break / throw meant as an abort (BLOCKER - it commits) | isolation: on a nested call (BLOCKER - raises; 8.1+ passes only a joining call at the outer transaction's own level) | unknown - caller out of the read set>

Side-effect hook (list every hook): <after_commit (correct for side effects) | before_save - derived column on this row (correct) | after_save - derived value on another row (correct) | after_save - update_counters, or a counter_cache association (correct) | after_save - outbox row (correct; it must commit with the record) | after_save - side effect (BLOCKER) | after_commit - derived column (GAP) | unknown - the models are out of the read set | N/A - no callbacks>

Isolation: <adapter default | :repeatable_read | :read_committed - <reason> | :serializable - <reason> | :read_uncommitted - GAP>

Concurrent writers on the same column: <none | row lock (ids ordered) / atomic UPDATE | unguarded read-modify-write (BLOCKER) - name the other writer, or this same path running concurrently | unknown - a writer is implied but its source is out of scope>

Retry strategy: <None | None - GAP (contended write path, or isolation bumped) | Deadlock or LockWaitTimeout retry x N at the outermost boundary (a retrying job around it is correct) | RecordNotUnique handled - create_or_find_by, or a rescue around a requires_new block whose re-read uses `.lock` or runs with no transaction open | RecordNotUnique swallowed, no re-read - GAP (the caller proceeds without the row) | retry around a nested or fused block (BLOCKER - retried writes autocommit) | unbounded, or wrapping side effects - GAP | retry of LockWaitTimeout from a rescue inside the block (BLOCKER - only the statement rolled back, earlier writes stay; a retry around the outermost boundary reruns from a full rollback) | retry of RecordNotUnique at any boundary (BLOCKER - the winner's row is committed, so the rerun hits the same key; handle it with create_or_find_by or a locked re-read) | job retry_on plus an inner rescue of the same class - GAP (the rescue wins, nothing retries) | rescue-and-return false - GAP (nothing retries, the caller reads success-shaped false) | provider redelivery (a webhook handler answering non-2xx on failure) | webhook handler answers 200 on failure - GAP (the provider never redelivers)>

Compensating action on partial failure: <Yes - <job> | Yes - existing <job> already covers it | No - acceptable | No - GAP>
```

`isolation:` is only legal on the outermost transaction: nested, Active Record raises `TransactionIsolationError` (8.1+ lets a joining nested call through when its `isolation:` equals the outer transaction's explicit level; a `requires_new:` call still raises). Transactional test fixtures open that outer transaction with `joinable: false`, so on 8.1+ a flat `transaction(isolation:)` inside a spec is validated then silently ignored - the spec passes without ever running at that isolation. Drop an isolation with no documented reason (Rules); when the reason stands, set `self.use_transactional_tests = false` on that spec. Never set isolation pool-wide (`database.yml` `variables:`); per-connection escalation, lost-update mechanics and lock choice are `rails-db-locking-patterns`'.

## Avoid

- Rescuing inside the outer transaction block around an inner call that has no `requires_new` - leaves inner writes committed
- Bumping isolation level "for safety" without a documented invariant - pays deadlock cost for no gain
- Wrapping retries around side effects (charges, emails) instead of the transaction only
