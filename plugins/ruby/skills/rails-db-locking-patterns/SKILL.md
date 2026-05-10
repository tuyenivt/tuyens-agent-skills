---
name: rails-db-locking-patterns
description: Database locking for Rails: GET_LOCK / pg_advisory_lock leader election, isolation tiers, lock-hold discipline, deadlock avoidance.
metadata:
  category: backend
  tags: [ruby, rails, locking, mysql, postgresql, concurrency, transactions]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Coordinating cron-style rake tasks across N pods (de-dup against double-runs)
- Serializing per-tenant or per-resource operations spanning multiple statements
- Choosing between Redis locks, Kubernetes leases, and database advisory locks
- Preventing deadlock cascades on MySQL `REPEATABLE READ` workers using row locks
- Deciding whether to keep RR (MySQL default), escalate to per-transaction RC, or set RC at the connection level
- Reviewing existing lock code for hold-time and connection-accounting risk

## Rules

- Use database locks when the lock guards a database write; Redis locks only for non-DB resources (API rate limits, cache stampede)
- Acquire lock, do DB work, release - never wrap a network call inside an open transaction or held advisory lock
- Lock by primary key only on MySQL `REPEATABLE READ` - non-PK locks gap-lock ranges
- Never `find_each` inside `Model.transaction { ... }` - the transaction holds for the whole iteration
- Set `innodb_lock_wait_timeout` (MySQL) or `lock_timeout` (PostgreSQL) to 5-10s at the worker session
- Default isolation stays as the database's default; escalate per-transaction at the call site, not per-connection or globally
- Document the rationale when a Sidekiq middleware sets connection-level isolation

## Patterns

### Why the database, not Redis or Kubernetes leases

| Coordination need                          | Pick                                  |
| ------------------------------------------ | ------------------------------------- |
| Lock guards a database write               | Database advisory lock                |
| Lock guards a non-DB resource (API, cache) | Redis (Redlock, `redis-mutex`)        |
| Cluster-wide leader election decoupled from app | Kubernetes Lease                 |
| Mutual exclusion within one process        | Mutex / `Concurrent::Lock`            |

A DB advisory lock taken in the same DB as the work-table commits and aborts atomically with the work itself. Redis locks (without fencing tokens) are not safe under network partitions for "must run exactly once across N pods".

### MySQL: `GET_LOCK` / `RELEASE_LOCK`

- Named string lock, session-scoped (auto-released on connection drop).
- 8.0+: multiple named locks per connection (5.7: one per).
- `GET_LOCK(name, timeout)` returns 1 (acquired), 0 (timeout), NULL (error).

### PostgreSQL: `pg_advisory_lock` family

- Integer-keyed, session-scoped.
- `pg_try_advisory_lock(key)` non-blocking - the right primitive for cron de-dup.
- `pg_advisory_xact_lock(key)` auto-releases at commit/rollback - bind lock lifetime to the transaction.

### Recommended abstraction: `with_advisory_lock` gem

Wraps both adapters behind one API. Don't branch on adapter at the call site.

```ruby
# Gemfile
gem "with_advisory_lock"

ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
  # ... work ...
end
# Returns false if not acquired; the block doesn't run.
```

### Pattern: leader election for cron rake tasks

Default failure mode: cron triggers a rake task while the previous run hasn't finished, two processes mutate the same rows.

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

### Pattern: transaction-scoped advisory lock (PostgreSQL)

Lock releases exactly when the transaction ends - cleaner than ensure-blocks because crash safety is automatic.

```ruby
ApplicationRecord.transaction do
  ActiveRecord::Base.connection.execute("SELECT pg_advisory_xact_lock(#{tenant_id})")
  # ... work scoped to this tenant ...
end
```

MySQL has no transaction-scoped variant of `GET_LOCK`. Use session-scoped `GET_LOCK` with `ensure { RELEASE_LOCK }`, or use a row-lock on a sentinel row in a `tenant_locks` table.

### Row-level pessimistic locking

For row-locking discipline (lock by PK, short critical section, MySQL gap-lock cascade explanation), see `rails-activerecord-patterns` "Pessimistic Locking" section. Two rules summarized:

1. Lock by primary key only on MySQL RR.
2. Keep critical section short. No external calls, no `find_each`.

### Optimistic locking with `lock_version`

For low-contention concurrent updates (rare conflicts, cheap retry), see `rails-activerecord-patterns` "Optimistic Locking". For hot rows with frequent contention, optimistic produces `StaleObjectError` storms - use pessimistic by PK instead.

### Lock-hold-time discipline

The single biggest production failure mode for DB locks is "held too long":

- A long-held `GET_LOCK` blocks every other holder behind it - queue stalls, deploy hangs.
- A long-held row lock under MySQL RR accumulates gap locks - deadlock cascades.
- A long-held transaction holds *every* row written or scanned within it - one bad query in a loop locks the whole batch.

Rules:

- Never wrap a network call (HTTP, Redis, S3) inside an open transaction or advisory lock.
- Use chunked transactions instead of `find_each` inside a transaction (cross-reference `rails-batch-processing-patterns`).
- Set lock-wait timeouts at session level so a stuck holder fails fast:

```ruby
# MySQL
ActiveRecord::Base.connection.execute("SET SESSION innodb_lock_wait_timeout = 5")

# PostgreSQL (per-transaction)
ActiveRecord::Base.connection.execute("SET LOCAL lock_timeout = '5s'")
```

- Inside `SKIP LOCKED` workers, claim small batches (50-500 rows) per transaction.

### Connection accounting for lock holders

Every advisory lock held = one DB connection held for the lock duration. A rake task holding a 6-hour lock holds a connection for 6 hours - counted against `max_connections`.

For long coordinators: prefer `pg_advisory_xact_lock` inside short transactions, or release-and-reacquire with a heartbeat between work batches. Cross-reference `rails-connection-pool-sizing`.

### Transaction isolation: the three-tier framework

The intuitive proposal "use RR for web, RC for jobs" is half right and half a footgun. Workers genuinely hit RR's stale-snapshot and gap-lock pathologies more than web requests; but blanket-setting RC on Sidekiq connections changes the semantics of every transaction sharing the pool - including code paths shared with web. A service object called from both contexts now behaves differently per caller, producing a bug class where the same code passes tests on the web side (RR snapshot masks a missing reload) and fails on the worker side, or vice versa.

The recommendation: **per-transaction RC at the call site** - visible to reviewers, easy to grep, easy to undo.

#### Tier 1 - Default: keep RR, fix the transaction shape

Most "stale data" and deadlock complaints under RR are symptoms of long transactions, not the isolation level. A transaction that holds 30s sees a 30s-old snapshot and accumulates 30s of gap locks; one that holds 200ms does not. Apply chunked transactions and lock-by-PK discipline first - resolves ~80% of cases at zero cost.

#### Tier 2 - Per-transaction RC at the call site

For specific paths where Tier 1 isn't sufficient, escalate the *individual transaction*.

`SKIP LOCKED` queue claim under contention - RC reduces gap-lock cascades:

```ruby
ApplicationRecord.transaction(isolation: :read_committed) do
  ids = WorkItem.where(state: "ready").order(:id).limit(BATCH)
                .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
  WorkItem.where(id: ids).update_all(state: "claimed")
  ids
end
```

Reconciliation that wants fresh reads of concurrently-updated counters:

```ruby
ApplicationRecord.transaction(isolation: :read_committed) do
  current = Account.find(account_id).balance
  Ledger.create!(account_id: account_id, before: current, ...)
end
```

When to reach for Tier 2:
- `SKIP LOCKED` queue claim under contention
- Long-ish scans where snapshot drift is acceptable and freshness matters
- Reconciliation jobs that want "see committed writes from concurrent jobs"
- Hot row updates re-read after each commit

When NOT to reach for Tier 2:
- Jobs that scan rows A and B and join them in app code expecting a consistent snapshot - keep RR (or restructure to a single SQL join)
- Anywhere the gain is "feels safer" without a measured contention or staleness problem

#### Tier 3 - Per-connection RC (Sidekiq middleware)

Only when *most* transactions on the worker process want RC and per-transaction wrapping gets noisy.

```ruby
Sidekiq.configure_server do |config|
  config.server_middleware do |chain|
    chain.add(Class.new do
      # Documented rationale: this worker's queues are dominated by SKIP LOCKED claim
      # cycles and short reconciliation transactions. Service objects shared with web
      # (FulfillOrder, ChargeCustomer) audited to confirm no RR snapshot dependency.
      def call(_w, _j, _q)
        ActiveRecord::Base.connection.execute(
          "SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED"
        )
        yield
      end
    end)
  end
end
```

Pitfalls:
- Connection-pool reuse - a connection set to RC may later be used by a non-Sidekiq path on the same pool (rake task, console).
- Isolation applies to *the next* transaction on that connection - timing matters.
- Service objects shared between web and worker have different semantics per context.

#### Aurora MySQL / RDS MySQL

RC is replication-safe under `binlog_format=ROW` (default since 5.7.7). The "RR is the MySQL default because statement-based replication needed it" reason is obsolete on modern RDS/Aurora. This unblocks Tier 2/3 without replication risk.

#### PostgreSQL

Default is already RC. The escalation goes the other direction: for code that *needs* a stable snapshot, use `transaction(isolation: :repeatable_read)` per-transaction.

### Common failure modes

| Symptom                                                                | Likely root cause                                                       |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `Deadlock found when trying to get lock`                               | Non-PK `with_lock` under RR causing gap-lock cascade                    |
| `Lock wait timeout exceeded`                                           | Long-running transaction or held advisory lock; check `SHOW ENGINE INNODB STATUS\G` |
| Two cron runs of the same task overlapping                             | Missing leader lock around the rake task body                           |
| `pg_advisory_lock` connection still held after process crash           | Session-scoped; releases on TCP close. Use `pg_advisory_xact_lock` for crash-safety |
| Sidekiq job sees stale data even after `reload`                        | Long RR transaction; close and re-open or escalate to per-tx RC         |
| `StaleObjectError` storms in a hot table                               | Optimistic locking is wrong for hot rows; use pessimistic by PK         |

## Output Format

```
Lock kind: {advisory leader | row pessimistic | row optimistic | transaction-scoped advisory}
Adapter: {MySQL | PostgreSQL} (primitive: {GET_LOCK | pg_advisory_lock | with_advisory_lock gem})
Scope: {session | transaction}
Hold time: {expected ms; reviewed for network calls / find_each / external IO}
Lock target: {PK lookup | ID list | non-PK scan (flagged for review)}
Isolation tier: {Tier 1 default | Tier 2 per-tx RC at call site | Tier 3 connection-level RC with documented rationale}
Failure mode considered: {deadlock cascade | leader-lock starvation | connection exhaustion | StaleObjectError storm}
```

## Avoid

- Wrapping HTTP / Redis / S3 calls inside an open transaction or advisory lock
- `find_each` inside `Model.transaction { ... }`
- Non-PK `with_lock` on MySQL `REPEATABLE READ` - gap-lock deadlock cascade
- Long-held session-scoped advisory locks for transactions that should use `pg_advisory_xact_lock`
- Setting `READ COMMITTED` on the entire Sidekiq pool without documented rationale and shared-services audit
- Treating "RR for web, RC for jobs" as a one-line recipe - it changes shared-service behavior silently
- Holding `GET_LOCK` across a long backfill - one connection consumed for hours, blocks rolling deploys
- Conflating advisory locks (mutual exclusion) with row locks (data consistency) - they solve different problems
- Skipping `innodb_lock_wait_timeout` / `lock_timeout` tuning - default 50s makes stuck holders look like a hang
- Optimistic locking for hot rows - use pessimistic by PK
