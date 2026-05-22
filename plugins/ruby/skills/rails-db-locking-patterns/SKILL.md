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
- Deciding between RR default, per-transaction RC at the call site, or per-connection RC
- Reviewing lock code for hold-time and connection-accounting risk

## Rules

- DB advisory lock when guarding a DB write; Redis lock only for non-DB resources (API rate limits, cache stampede)
- Acquire lock, do DB work, release - never wrap network calls in an open transaction or held lock
- Lock by PK only on MySQL `REPEATABLE READ` - non-PK scans gap-lock ranges (see `rails-activerecord-patterns`)
- Never `find_each` inside `Model.transaction { ... }`
- Set `innodb_lock_wait_timeout` (MySQL) / `lock_timeout` (PG) to 5-10s at the worker session
- Default stays at the DB's default isolation; escalate per-transaction at the call site, not per-connection or globally

## Patterns

### Which coordination primitive

| Coordination need                          | Pick                              |
| ------------------------------------------ | --------------------------------- |
| Lock guards a database write               | DB advisory lock                  |
| Lock guards a non-DB resource (API, cache) | Redis (Redlock, `redis-mutex`)    |
| Cluster-wide leader election decoupled from app | Kubernetes Lease             |
| Mutual exclusion within one process        | Mutex / `Concurrent::Lock`        |

A DB advisory lock taken in the same DB as the work commits/aborts atomically with the work. Redis without fencing tokens is not safe for "exactly once across N pods".

### `with_advisory_lock` (recommended abstraction)

Wraps MySQL `GET_LOCK` and PG `pg_advisory_lock` behind one API. The gem holds the connection for the duration of the block and releases the lock before checking the connection back in - safe under Sidekiq concurrency.

```ruby
gem "with_advisory_lock"

ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
  # ... work ...
end
# Returns false when not acquired; the block doesn't run.
```

MySQL `GET_LOCK` is session-scoped (auto-released on connection drop). PG offers `pg_advisory_xact_lock(key)` that auto-releases at commit - cleaner crash-safety than ensure blocks.

### Pattern: leader election for cron rake tasks

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
    abort "another reports:rebuild is running; exiting cleanly" unless acquired
  end
end
```

### Pattern: per-tenant serialization across web and worker

The reconciler and the web ledger-write endpoint share one lock name namespaced by tenant. They cannot run concurrently on the same tenant but run freely across tenants. Combine with chunked transactions and PK-only row locks inside the lock.

```ruby
class BalanceReconciler
  def self.call(tenant_id)
    ApplicationRecord.with_advisory_lock("reconcile:tenant:#{tenant_id}", timeout_seconds: 10) do
      Account.where(tenant_id: tenant_id).in_batches(of: 200) do |slice_ids|
        ApplicationRecord.transaction(isolation: :read_committed) do
          Account.where(id: slice_ids.pluck(:id)).order(:id).lock("FOR UPDATE").each(&:recompute_balance!)
        end
      end
    end
  end
end

# Controller takes the same lock around the write
class LedgerEntriesController < ApplicationController
  def create
    ApplicationRecord.with_advisory_lock("reconcile:tenant:#{current_tenant.id}", timeout_seconds: 3) do
      ApplicationRecord.transaction(isolation: :read_committed) do
        Ledger.create!(ledger_params)
        Account.where(id: ledger_params[:account_id]).lock("FOR UPDATE").first.increment!(:balance, ledger_params[:amount])
      end
    end
  end
end
```

### Transaction isolation: three-tier framework

The intuitive "RR for web, RC for jobs" is half right, half footgun. Worker code hits RR's stale-snapshot and gap-lock pathologies more than web, but blanket-setting RC on the Sidekiq pool changes shared-service semantics silently.

**Recommendation: per-transaction RC at the call site** - visible to reviewers, easy to grep, easy to undo.

**Tier 1 - Default: keep RR, fix the transaction shape.** Most "stale data" / deadlock complaints under RR are symptoms of long transactions. A 30s transaction sees a 30s-old snapshot and holds 30s of gap locks; a 200ms one doesn't. Apply chunked transactions + lock-by-PK first - resolves ~80% of cases at zero cost.

**Tier 2 - Per-transaction RC at the call site.** Aurora/RDS MySQL with `binlog_format=ROW` (default since 5.7.7) makes RC replication-safe - the "RR is the MySQL default because SBR needed it" reason is obsolete on modern RDS/Aurora.

Use Tier 2 for:
- `SKIP LOCKED` queue claim under contention - RC reduces gap-lock cascades
- Reconciliation that wants fresh reads of concurrently-updated counters
- Hot-row updates re-read after each commit

Don't use Tier 2 for:
- Jobs that scan rows A and B and join them in app code expecting a consistent snapshot - keep RR or restructure into one SQL join
- "Feels safer" without a measured contention or staleness problem

```ruby
ApplicationRecord.transaction(isolation: :read_committed) do
  ids = WorkItem.where(state: "ready").order(:id).limit(BATCH)
                .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
  WorkItem.where(id: ids).update_all(state: "claimed")
end
```

**Tier 3 - Per-connection RC (Sidekiq middleware).** Only when most transactions on the worker process want RC and per-transaction wrapping gets noisy. Audit shared services first. The middleware must `ensure` reset to default - otherwise isolation leaks to the next job on the same connection.

PostgreSQL: default is already RC; for code that needs a stable snapshot, use `transaction(isolation: :repeatable_read)`.

### Nested transactions and isolation

`transaction(isolation: :read_committed) do ... transaction(isolation: ...) end` - the inner `isolation:` is silently ignored. The inner block becomes a savepoint (`requires_new: true`) or a no-op under MySQL/PG. If you need different isolation per chunk, don't nest - flatten:

```ruby
slice_ids.each do |slice|
  ApplicationRecord.transaction(isolation: :read_committed) do
    Account.where(id: slice).lock("FOR UPDATE").each(&:recompute_balance!)
  end
end
```

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

Every advisory lock = one DB connection held for the lock duration. A 6-hour backfill lock holds a connection for 6 hours. For long coordinators, prefer `pg_advisory_xact_lock` inside short transactions, or release-and-reacquire with a heartbeat between work batches. Cross-reference `rails-connection-pool-sizing`.

### Row locking and optimistic locking

For row-locking discipline (PK-only, short critical section, MySQL gap-lock cascade) and optimistic `lock_version`, see `rails-activerecord-patterns`.

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

```
Lock kinds: {comma-separated: advisory leader | advisory per-resource | row pessimistic | optimistic | transaction-scoped advisory}
Adapter: {MySQL | PostgreSQL} (primitive: {GET_LOCK | pg_advisory_lock | pg_advisory_xact_lock | with_advisory_lock gem})
Scope: {session | transaction}
Hold time: {expected ms / s; reviewed for network calls / find_each / external IO}
Lock target: {PK lookup | ID list | non-PK scan (flagged)}
Isolation tier: {Tier 1 default | Tier 2 per-tx RC at call site | Tier 3 connection-level RC with documented rationale}
Failure modes considered: {deadlock cascade | leader-lock starvation | connection exhaustion | StaleObjectError storm}
```

## Avoid

- Network calls inside an open transaction or advisory lock
- `find_each` inside `Model.transaction { ... }`
- Non-PK row locks on MySQL `REPEATABLE READ`
- Session-scoped advisory locks for transactions that should use `pg_advisory_xact_lock`
- Blanket `READ COMMITTED` on the Sidekiq pool without shared-services audit and `ensure`-reset
- "RR for web, RC for jobs" as a one-line recipe - changes shared-service behavior silently
- Long-held `GET_LOCK` across a backfill - one connection consumed for hours, blocks rolling deploys
- Conflating advisory locks (mutual exclusion) with row locks (data consistency)
- Default `innodb_lock_wait_timeout` / `lock_timeout` (50s) - makes stuck holders look like a hang
- Optimistic locking on hot rows - use pessimistic by PK
- Nesting `transaction(isolation:)` - the inner isolation is silently ignored
