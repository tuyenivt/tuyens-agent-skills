---
name: rails-db-locking-patterns
description: Database locking for Rails: advisory locks for leader election & per-tenant serialization, MySQL/PG isolation tiers, hold-time discipline.
metadata:
  category: backend
  tags: [ruby, rails, locking, mysql, postgresql, concurrency, transactions]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- De-duping cron rake tasks against double-runs across N pods
- Serializing per-tenant or per-resource work between web and workers
- Choosing between Redis locks, Kubernetes leases, and DB advisory locks
- Preventing deadlock cascades on MySQL `REPEATABLE READ`
- Choosing between RR default, per-transaction RC at the call site, or per-connection RC
- Reviewing lock code for hold-time and connection-accounting risk

## Rules

- DB advisory lock when guarding a DB write; Redis lock only for non-DB resources (rate limits, cache stampede). Hybrid work (DB write + external call): the DB is the consistency anchor - advisory lock for the DB side, idempotency key for the external call; never a Redis lock for the pair.
- Locks prevent overlap, not duplicates - a crash-rerun or manual re-fire re-does the work. Pair every leader lock with row-level idempotency (unique index + create-if-absent / upsert).
- Acquire lock, do DB work, release. Never wrap network calls in an open transaction or row lock. (A long-lived *leader* lock spanning a run that includes IO is legitimate - it serializes runs, holds no row locks - but it costs one connection for the duration; see Connection accounting.)
- Never `find_each` inside `Model.transaction { ... }`.
- Set `innodb_lock_wait_timeout` (MySQL) / `lock_timeout` (PG) to 5-10s at the worker session.
- Default stays at the DB's default isolation; escalate per-transaction at the call site, not per-connection or globally.
- Row-lock discipline (PK-only on MySQL RR, short critical section): see `rails-activerecord-patterns`.

## Patterns

### Which coordination primitive

| Coordination need                          | Pick                              |
| ------------------------------------------ | --------------------------------- |
| Lock guards a database write               | DB advisory lock                  |
| Lock guards a non-DB resource (API, cache) | Redis (Redlock, `redis-mutex`)    |
| Cluster-wide leader election decoupled from app | Kubernetes Lease             |
| Mutual exclusion within one process        | `Mutex` / `Monitor`               |

A *transaction-scoped* advisory lock (`pg_advisory_xact_lock`) releases atomically with the work it guards. Session-scoped locks - `GET_LOCK`, `pg_advisory_lock`, and the `with_advisory_lock` default below - survive both COMMIT and ROLLBACK and must be released explicitly; they share the DB's failure domain, which is the reason to prefer them over Redis, but that is not atomicity. Redis without fencing tokens is not safe for "exactly once across N pods".

### `with_advisory_lock` (recommended abstraction)

Wraps MySQL `GET_LOCK` and PG `pg_advisory_lock` behind one API. The gem holds the connection for the lock duration and releases the lock before checking the connection back in - safe under Sidekiq concurrency.

Lock names share one namespace per database (PG hashes them into a single 64-bit space), so prefix every name with its owner and key: `"reconcile:account:#{id}"`, never `id.to_s`. Two unrelated features on a bare id will serialize against each other and neither team will know why. Re-entering the same name in a nested block is safe on both adapters - the lock is re-entrant per session - but the inner block does not extend the outer hold.

```ruby
gem "with_advisory_lock"

ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
  # ... work ...
end
# Returns false when not acquired; the block doesn't run.
```

MySQL `GET_LOCK` is session-scoped (auto-released on connection drop). PG `pg_advisory_xact_lock(key)` auto-releases at commit - cleaner crash-safety than ensure blocks; acquire it *inside* the transaction it should bind to (`with_advisory_lock(..., transaction: true)`), whereas session locks wrap the transaction from outside.

### Leader election for cron rake tasks

Cron triggers a task while the previous run is still going - two processes mutate the same rows.

```ruby
namespace :reports do
  task rebuild: :environment do
    acquired = ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
      Order.where(needs_rebuild: true).in_batches(of: 1_000) do |batch|
        ApplicationRecord.transaction { batch.each(&:rebuild!) }
      end
      true
    end
    unless acquired
      puts "another reports:rebuild is running - skipping"
      next   # skip-if-held is expected, not a failure. `next` leaves this task only;
             # `exit 0` would end the process and silently skip the rest of a chain
    end
  end
end
```

### Per-tenant serialization across web and worker

Reconciler and the web ledger-write endpoint share one lock name namespaced by tenant. They cannot run concurrently on the same tenant but run freely across tenants. Combine with chunked transactions and PK-only row locks inside the lock.

```ruby
class BalanceReconciler
  def self.call(tenant_id)
    ApplicationRecord.with_advisory_lock("reconcile:tenant:#{tenant_id}", timeout_seconds: 10) do
      Account.where(tenant_id: tenant_id).in_batches(of: 200) do |batch|
        ApplicationRecord.transaction(isolation: :read_committed) do
          Account.where(id: batch.pluck(:id)).order(:id).lock("FOR UPDATE").each(&:recompute_balance!)
        end
      end
    end
  end
end

# Controller takes the same lock around the write - and handles non-acquisition:
# with_advisory_lock returns false without running the block, silently dropping the write otherwise
class LedgerEntriesController < ApplicationController
  def create
    acquired = ApplicationRecord.with_advisory_lock("reconcile:tenant:#{current_tenant.id}", timeout_seconds: 3) do
      ApplicationRecord.transaction(isolation: :read_committed) do
        Ledger.create!(ledger_params)
        Account.where(id: ledger_params[:account_id]).lock("FOR UPDATE").first
               .increment!(:balance, ledger_params[:amount])
      end
      true
    end
    head :conflict unless acquired   # client retries; never swallow the miss
  end
end
```

The explicit `isolation: :read_committed` here is the MySQL Tier-2 escalation - on PostgreSQL omit it, since RC is already the default. The transactional-fixtures constraint is adapter-independent and covered below; it applies to this MySQL form too.

### Transaction isolation: three tiers

"RR for web, RC for jobs" silently changes shared-service behavior. Escalate per-transaction at the call site instead.

| Tier | Approach | Use when |
| ---- | -------- | -------- |
| 1 (default) | Keep RR (MySQL) / RC (PG); shorten transactions | Most "stale data"/deadlock complaints - chunked transactions + PK locks resolve at zero cost |
| 2 | Per-transaction `isolation: :read_committed` at the call site | `SKIP LOCKED` claim under contention; fresh reads of concurrent counters; hot-row re-reads. Aurora/RDS MySQL is RC-safe with `binlog_format=ROW` (default since 5.7.7) |
| 3 | Per-connection RC via Sidekiq middleware | Only when Tier 2 wrapping gets noisy. Audit shared services; middleware must `ensure` reset or isolation leaks to the next job |

Don't escalate for jobs that scan rows A and B expecting one snapshot - keep RR or fold into one SQL join. PostgreSQL: escalate the other direction with `isolation: :repeatable_read` when a stable snapshot is needed.

```ruby
ApplicationRecord.transaction(isolation: :read_committed) do
  ids = WorkItem.where(state: "ready").order(:id).limit(BATCH)
                .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
  WorkItem.where(id: ids).update_all(state: "claimed")
end
```

### Nested `isolation:` raises

Passing `isolation:` while any transaction is already open raises `ActiveRecord::TransactionIsolationError`, on every adapter, before Active Record reaches the connection. The message names which case you hit: "cannot set isolation when joining a transaction" for a plain nested call, "cannot set transaction isolation in a nested transaction" on the savepoint path (`requires_new: true`, or a non-joinable outer transaction - which is what transactional fixtures give you). So this error often first appears in specs around code that runs flat in production. For different isolation per chunk, flatten:

```ruby
slice_ids.each do |slice|
  ApplicationRecord.transaction(isolation: :read_committed) do
    Account.where(id: slice).lock("FOR UPDATE").each(&:recompute_balance!)
  end
end
```

For `requires_new` / savepoint semantics around nested rescues, see `rails-transaction-patterns`.

### Lock-hold discipline

The single biggest failure mode is "held too long":

- A long `GET_LOCK` blocks every other holder - queue stalls, deploy hangs
- A long row lock under RR accumulates gap locks - deadlock cascade
- A long transaction holds *every* row written or scanned within it

Fail-fast lock-wait timeouts:

```ruby
# MySQL
ActiveRecord::Base.connection.execute("SET SESSION innodb_lock_wait_timeout = 5")
# PostgreSQL (per transaction)
ActiveRecord::Base.connection.execute("SET LOCAL lock_timeout = '5s'")
```

Inside `SKIP LOCKED` claim workers, claim small batches (50-500 rows) per transaction.

### Connection accounting

Every advisory lock = one DB connection held for the lock duration. A 6-hour backfill lock holds a connection for 6 hours - usually acceptable for one coordinator, and it holds no *row* locks - but every other contender for that lock name waits behind it, and the connection must be budgeted. When that's too costly, release-and-reacquire between work batches:

```ruby
loop do
  done = ApplicationRecord.with_advisory_lock("billing:run", timeout_seconds: 0) do
    batch = next_unprocessed_batch or break :finished   # re-derive progress from row state
    process(batch)
    :more
  end
  break if done == :finished || done == false           # false = another holder; exit cleanly
end
```

The gap between iterations is a double-run window - safe only because progress lives in row state and row-level idempotency (Rules) makes re-processing a no-op. PG alternative: `pg_advisory_xact_lock` inside short per-batch transactions. See `rails-connection-pool-sizing`.

### Failure modes

| Symptom                                                       | Likely root cause                                                       |
| ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `Deadlock found when trying to get lock`                      | Non-PK `lock` under RR causing gap-lock cascade                          |
| `Lock wait timeout exceeded`                                  | Long-running transaction or held advisory lock; `SHOW ENGINE INNODB STATUS\G` |
| Two cron runs of the same task overlapping                    | Missing leader lock around the rake task body                            |
| `pg_advisory_lock` still held after process crash             | Session-scoped; releases on TCP close. Use `pg_advisory_xact_lock`       |
| Sidekiq job sees stale data even after `reload`               | Long RR transaction; close+reopen or escalate to per-tx RC               |
| `StaleObjectError` storms on a hot row                        | Optimistic locking on hot rows; use pessimistic by PK                    |

## Output Format

One block per code path under review - three paths contending on one row emit three blocks, each naming its path. In review mode, precede the blocks with numbered findings citing the violated rule; the blocks describe the corrected design, so target state lives there. `Lock kinds`, `Scope` and `Failure modes considered` list every value that applies, joined with ` + `; a design legitimately combining a leader lock and a per-resource lock says both rather than picking one.

```
Lock kinds: {advisory leader | advisory per-resource | row pessimistic | optimistic | transaction-scoped advisory}

Adapter: {MySQL | PostgreSQL} (primitive: {GET_LOCK | pg_advisory_lock | pg_advisory_xact_lock | with_advisory_lock gem})

Scope: {session | transaction}

Hold time: {expected per lock kind; long leader holds stated in minutes and flagged with connection cost}

Lock target: {PK lookup | ID list - ordered by PK to fix acquisition order | non-PK scan (flagged) | n/a (advisory only)}

Isolation tier: {Tier 1 default | Tier 2 per-tx escalation at call site (RC, or RR on PG for snapshot reads) | Tier 3 connection-level RC with documented rationale | serializable - flag it: it is above every tier here and wants a row lock instead}

Deadlock retry: {bounded N with backoff | none needed (single lock, ordered acquisition) | unbounded - GAP}

Idempotency backing the lock: {unique index | upsert | state column | external idempotency key - list all that apply | none (flagged)}

Failure modes considered: {deadlock cascade | leader-lock starvation | connection exhaustion | StaleObjectError storm | lock held across an external call, backing up writers | lost update on an unlocked read-modify-write - list each one considered, with its verdict}
```

## Avoid

- Network calls inside an open transaction or row lock (a long-lived leader advisory lock spanning IO is the deliberate exception)
- Unbounded `rescue ActiveRecord::Deadlocked; retry` - cap the attempts (3-5) and back off, or the loser spins against a live winner
- `find_each` inside `Model.transaction { ... }`
- Non-PK row locks on MySQL `REPEATABLE READ`
- Session-scoped advisory locks for transactions that should use `pg_advisory_xact_lock`
- Blanket `READ COMMITTED` on the Sidekiq pool without shared-services audit and `ensure`-reset
- "RR for web, RC for jobs" as a one-line recipe - changes shared-service behavior silently
- Long-held `GET_LOCK` without budgeting it - one coordinator connection for hours is fine *if counted*; release-and-reacquire when the pool is tight
- Conflating advisory locks (mutual exclusion) with row locks (data consistency)
- Leaving the defaults: MySQL `innodb_lock_wait_timeout` is 50s, and PostgreSQL `lock_timeout` is `0` - disabled, so a blocked statement waits forever
- Optimistic locking on hot rows - use pessimistic by PK
- Nesting `transaction(isolation:)` - raises `TransactionIsolationError` (transactional fixtures included)
