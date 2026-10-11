---
name: rails-db-locking-patterns
description: MySQL locking for Rails: GET_LOCK advisory locks for leader election & per-tenant serialization, InnoDB isolation tiers, hold-time discipline.
metadata:
  category: backend
  tags: [ruby, rails, locking, mysql, innodb, concurrency, transactions]
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

- DB advisory lock when guarding a DB write; Redis lock only for non-DB resources (rate limits, cache stampede). Hybrid work (DB write + external call): the DB is the consistency anchor - advisory lock for the DB side, idempotency key for the external call, and an external failure after commit routes to a reconciliation job (`rails-service-objects`); never a Redis lock for the pair.
- Locks prevent overlap, not duplicates - a crash-rerun or manual re-fire re-does the work. Pair every leader lock with row-level idempotency (unique index + create-if-absent / upsert).
- Acquire lock, do DB work, release. Never wrap network calls in an open transaction or row lock. (A long-lived *leader* lock spanning a run that includes IO is legitimate - it serializes runs, holds no row locks - but it costs one connection for the duration; see Connection accounting.)
- Never `find_each` inside `Model.transaction { ... }`.
- Set `innodb_lock_wait_timeout` to 5-10s at the worker session.
- Default stays at the DB's default isolation; escalate per-transaction at the call site (Tier 2); per-connection (Tier 3) only with the audit and `ensure`-reset the tier table demands, never globally.
- Row-lock discipline (PK-only on MySQL RR, short critical section): see `rails-activerecord-patterns`.

## Patterns

### Which coordination primitive

| Coordination need                          | Pick                              |
| ------------------------------------------ | --------------------------------- |
| Lock serializes runs that write the database | DB advisory lock                |
| Lock guards one row's read-modify-write    | Row lock (`with_lock` / `lock`), not advisory - advisory and row locks are independent spaces; one never blocks the other |
| Lock guards a non-DB resource (API, cache) | Redis (Redlock, `redis-mutex`)    |
| Cluster-wide leader election decoupled from app | Kubernetes Lease             |
| Mutual exclusion within one process        | `Mutex` / `Monitor`               |

MySQL advisory locks (`GET_LOCK`) are session-scoped only - there is no transaction-scoped form. They survive both COMMIT and ROLLBACK and must be released explicitly (`RELEASE_LOCK`, or the `with_advisory_lock` block exit); they share the DB's failure domain, which is the reason to prefer them over Redis, but that is not atomicity. Redis without fencing tokens is not safe for "exactly once across N pods".

### `with_advisory_lock` (recommended abstraction)

Wraps MySQL `GET_LOCK` / `RELEASE_LOCK`. The gem holds the connection for the lock duration and releases the lock before checking the connection back in - safe under Sidekiq concurrency.

`GET_LOCK` names share one namespace per MySQL *server*, not per schema, and the gem passes the name through verbatim. Prefix every name with its owner and key: `"reconcile:account:#{id}"`, never `id.to_s` - two unrelated features on a bare id serialize against each other and neither team will know why. When several apps or environments share one server, set `WITH_ADVISORY_LOCK_PREFIX` per app and environment so their names cannot meet - it is an environment variable the gem reads in each process, so it goes in each deploy manifest (`orderdesk-production`, `orderdesk-staging`). Names, prefix included, are capped at 64 characters - a longer one raises instead of locking, so keep interpolated keys short. Re-entering the same name in a nested block is safe - the lock is re-entrant per session - but the inner block does not extend the outer hold.

```ruby
gem "with_advisory_lock"

ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
  # ... work ...
end
# Returns false when not acquired; the block doesn't run.
```

`GET_LOCK` is auto-released when the connection closes, so a crashed process whose socket closed frees it. A *hung* process holds it until killed, and so does a session orphaned by node loss or a partition - the server keeps it until it notices the dead socket or `wait_timeout` expires, and Rails sets that session value very high (`SELECT IS_USED_LOCK('name')` returns the holder's connection id for `KILL`). The lock wraps the transaction from outside. The gem's `transaction: true` and `shared: true` options raise `ArgumentError` on MySQL.

### Leader election for cron rake tasks

Cron triggers a task while the previous run is still going - two processes mutate the same rows. Kubernetes CronJobs default to `concurrencyPolicy: Allow`. A Kubernetes CronJob needs `concurrencyPolicy: Forbid` and `parallelism: 1` - `parallelism: N` starts N pods per run, all racing for the lock; keep the lock anyway, for manual re-fires and restarted pods. Session locks live on the connection that took them - take them on the writer, never through a reader.

```ruby
namespace :reports do
  task rebuild: :environment do
    acquired = ApplicationRecord.with_advisory_lock("reports:rebuild", timeout_seconds: 0) do
      Order.where(needs_rebuild: true).in_batches(of: 1_000) do |batch|
        ApplicationRecord.transaction { batch.each(&:rebuild!) }   # all-or-nothing per batch by design
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

A leader-locked loop over independent items (accounts, tenants) rescues per item, records the failure, continues, and raises a summary after the loop - one bad item must not stop the run, and the final raise keeps the cron exit status honest.

### Per-tenant serialization across web and worker

Reconciler and the web ledger-write endpoint share one lock name namespaced by tenant. They cannot run concurrently on the same tenant but run freely across tenants. Combine with chunked transactions and PK-only row locks inside the lock.

```ruby
class BalanceReconciler
  def self.call(tenant_id)
    # Bang form raises WithAdvisoryLock::FailedToAcquireLock when held - Sidekiq retries; never a silent no-op
    ApplicationRecord.with_advisory_lock!("reconcile:tenant:#{tenant_id}", timeout_seconds: 10) do
      Account.where(tenant_id: tenant_id).in_batches(of: 200) do |batch|
        ApplicationRecord.transaction do
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
      ApplicationRecord.transaction do
        # Parent first, tenant-scoped: inserting the child first would S-lock the parent
        # through the FK check, and the later FOR UPDATE upgrade deadlocks with other writers
        account = current_tenant.accounts.lock.find(ledger_params[:account_id])
        Ledger.create!(ledger_params.merge(account: account))
        account.increment!(:balance, Integer(ledger_params[:amount]))   # integer cents; params are Strings
      end
      true
    end
    acquired ? head(:created) : head(:conflict)   # conflict: the client retries; never swallow the miss
  end
end
```

Neither path escalates isolation: every read that matters is a locking read, and under InnoDB's `REPEATABLE READ` a locking read sees the latest committed row.

### Transaction isolation: three tiers

"RR for web, RC for jobs" silently changes shared-service behavior. Escalate per-transaction at the call site instead.

| Tier | Approach | Use when |
| ---- | -------- | -------- |
| 1 (default) | Keep InnoDB's RR; shorten transactions | Most "stale data"/deadlock complaints - chunked transactions + PK locks resolve at zero cost |
| 2 | Per-transaction `isolation: :read_committed` at the call site | `SKIP LOCKED` claim under contention; fresh reads of concurrent counters; hot-row re-reads. RC needs `binlog_format` ROW or MIXED - RDS MySQL defaults to MIXED and Aurora's default parameter group leaves binary logging off, so both are RC-safe |
| 3 | Per-connection RC via Sidekiq middleware | Only when Tier 2 wrapping gets noisy. Audit shared services; middleware must `ensure` reset or isolation leaks to the next job |

Don't escalate for jobs that scan rows A and B expecting one snapshot - keep RR or fold into one SQL join.

```ruby
ApplicationRecord.transaction(isolation: :read_committed) do
  ids = WorkItem.where(state: "ready").order(:id).limit(BATCH)
                .lock("FOR UPDATE SKIP LOCKED").pluck(:id)
  WorkItem.where(id: ids).update_all(state: "claimed")
end
```

### Nested `isolation:` raises

Passing `isolation:` while any transaction is already open raises `ActiveRecord::TransactionIsolationError`, on every adapter, before Active Record reaches the connection. The message names which case you hit: "cannot set isolation when joining a transaction" for a plain nested call, "cannot set transaction isolation in a nested transaction" on the savepoint path (`requires_new: true`, or a non-joinable outer transaction - which is what transactional fixtures give you). So this error often first appears in specs around code that runs flat in production. Transactional test fixtures wrap each example in a non-joinable transaction, so even a flat `transaction(isolation:)` raises in specs; set `self.use_transactional_tests = false` on that spec - flattening does not help. Flattening fixes the nesting in production code, running each chunk in its own isolated transaction:

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
- A locking read on an unindexed predicate locks every row it scans, not just the matches - index the predicate or lock by PK
- `.lock` outside a transaction locks nothing useful: under autocommit the lock releases when the statement ends

Fail-fast lock-wait timeouts:

```yaml
# config/database.yml - variables: run as SET SESSION on every new connection,
# so no pooled connection misses them; scoped to the worker role by an env var
production:
  primary:
    # adapter, database, host, ... as usual
    <% if ENV["PROCESS_ROLE"] == "worker" %>
    variables:
      innodb_lock_wait_timeout: 5   # row-lock waits
      lock_wait_timeout: 10         # metadata-lock waits (DDL, LOCK TABLES); default is a year
    <% end %>
```

A one-off `SET SESSION innodb_lock_wait_timeout = 5` stays on the pooled connection after the job ends and bounds whatever runs on it next - set it at connect time per role, or reset it in an `ensure`.

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

The gap between iterations is a double-run window - safe only because progress lives in row state and row-level idempotency (Rules) makes re-processing a no-op. See `rails-connection-pool-sizing`.

### Failure modes

| Symptom                                                       | Likely root cause                                                       |
| ------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `Deadlock found when trying to get lock`                      | Non-PK `lock` under RR causing gap-lock cascade (worst on an unindexed predicate); rows locked in different orders by concurrent jobs - sort by PK; or a child INSERT's FK check taking a shared lock on the parent row that a later `FOR UPDATE` upgrades - lock the parent before inserting children |
| `Lock wait timeout exceeded`                                  | Long-running transaction holding row locks; `SHOW ENGINE INNODB STATUS\G` (a contended `GET_LOCK` never raises this - it returns 0 on timeout) |
| Two cron runs of the same task overlapping                    | Missing leader lock around the rake task body                            |
| Every run skips: `GET_LOCK` held for hours                    | Holder hung, or its node lost with the session orphaned - the session is alive; `IS_USED_LOCK` for the connection id, then `KILL` |
| Sidekiq job sees stale data even after `reload`               | Long RR transaction; close+reopen or escalate to per-tx RC               |
| `StaleObjectError` storms on a hot row                        | Optimistic locking on hot rows; use pessimistic by PK                    |

## Output Format

One block per code path under review - three paths contending on one row emit three blocks, each naming its path; a Redis-lock wrapper around a DB path folds into that path's block. In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. In review or diagnosis mode each field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and its numbered finding explains the fix. A build-mode block holds corrected values only, and build mode still numbers findings for the pre-existing violations it touches. A request to design or change code is build mode; one that assesses or diagnoses code as it stands is review or diagnosis mode. A cross-path observation (two writers to one row under different lock names) is a numbered finding. `Lock kinds`, the `Adapter` primitive, `Scope`, `Lock wait timeout`, `Idempotency backing the lock` and `Failure modes considered` list every value that applies, joined with ` + `; a design legitimately combining a leader lock and a per-resource lock says both rather than picking one.

```
Path: {file:method, rake task or job class}

Lock kinds: {advisory leader | advisory per-resource | row pessimistic | optimistic | Redis lock (non-DB resource only) | Kubernetes Lease | in-process Mutex}

Adapter: {MySQL | unknown - read config/database.yml} (primitive: {GET_LOCK | with_advisory_lock gem | SELECT ... FOR UPDATE | SELECT ... FOR UPDATE SKIP LOCKED | lock_version | Redlock / redis-mutex | n/a})

Scope: {session (advisory) | transaction (row locks) | TTL (Redis) | lease duration (Kubernetes) | process (Mutex) | n/a (optimistic)}

Lock wait timeout: {innodb_lock_wait_timeout N s | default - GAP (50s) | advisory timeout_seconds N (advisory-only path) | lock_wait_timeout N s (the path runs DDL or LOCK TABLES) | n/a (SKIP LOCKED never waits; optimistic, Redis, lease, Mutex)}

On non-acquisition: {raise (job retries) | 409 / retry to the client | StaleObjectError -> retry or 409 (optimistic) | skip via next (cron leader) | clean break (release-and-reacquire loop) | skip locked rows (SKIP LOCKED claim) | ignored - GAP (silent no-op)}

Hold time: {expected per lock kind; long leader holds stated in minutes and flagged with connection cost}

Lock target: {PK lookup | ID list - ordered by PK to fix acquisition order | SKIP LOCKED claim on an indexed predicate under RC (legitimate) | non-PK scan under MySQL RR (flagged; in a corrected block, the PK form that replaces it) | n/a (advisory only)}

Isolation tier: {Tier 1 default | Tier 2 per-tx RC escalation at call site | Tier 3 connection-level RC, audited, ensure-reset | Tier 3 without ensure-reset - GAP | serializable - flag it: it is above every tier here and wants a row lock instead}

Deadlock retry: {bounded N with backoff | none needed (single lock, ordered acquisition) | none - GAP (several unordered row locks, or an FK upgrade) | unbounded - GAP}

Idempotency backing the lock: {unique index | upsert | state column | external idempotency key | n/a (not a leader lock) | none (flagged)}

Failure modes considered: {deadlock cascade | double run (crash re-run or manual re-fire) | leader-lock starvation | connection exhaustion | one long transaction over a scan | stale reads inside a long RR transaction | session lock held by a hung or orphaned process | lock-name collision (unprefixed name) | session variable leak on a pooled connection | Tier-3 isolation leak to the next job | StaleObjectError storm | lock held across an external call, backing up writers | lost update on an unlocked read-modify-write - list each one considered, with its verdict}
```

## Avoid

- Network calls inside an open transaction or row lock (a long-lived leader advisory lock spanning IO is the deliberate exception)
- Unbounded `rescue ActiveRecord::Deadlocked; retry` - cap at 3 attempts and back off (as `rails-transaction-patterns` does), or the loser spins against a live winner
- `find_each` inside `Model.transaction { ... }`
- Non-PK row locks on MySQL `REPEATABLE READ`
- Bare or unprefixed lock names on a MySQL server shared by several apps or environments
- Blanket `READ COMMITTED` on the Sidekiq pool without shared-services audit and `ensure`-reset
- "RR for web, RC for jobs" as a one-line recipe - changes shared-service behavior silently
- Long-held `GET_LOCK` without budgeting it - one coordinator connection for hours is fine *if counted*; release-and-reacquire when the pool is tight
- Conflating advisory locks (mutual exclusion) with row locks (data consistency)
- Leaving the defaults: `innodb_lock_wait_timeout` is 50s and `lock_wait_timeout` (metadata locks) is a year
- Optimistic locking on hot rows - use pessimistic by PK
- Nesting `transaction(isolation:)` - raises `TransactionIsolationError` (transactional fixtures included)
