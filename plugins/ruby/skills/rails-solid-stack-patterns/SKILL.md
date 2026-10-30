---
name: rails-solid-stack-patterns
description: Solid Queue/Cache/Cable on MySQL 8.0 - database-backed queue, cache, pub/sub vs Sidekiq/Redis: queue.yml, cache.yml, cable.yml, pools, recovery.
metadata:
  category: backend
  tags: [rails, solid-queue, solid-cache, solid-cable, mysql, active-job, action-cable, caching]
user-invocable: false
---

# Rails Solid Stack Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a job backend, cache store or Action Cable adapter for a deployment with no Redis or memcached, or reviewing one already chosen
- Authoring or reviewing `config/queue.yml`, `config/recurring.yml`, `config/cache.yml`, `config/cable.yml`, or the `queue` / `cache` / `cable` entries of `config/database.yml`
- Sizing Solid Queue workers, bounding Solid Cache and Solid Cable tables, or recovering jobs after a worker crash
- Job class design (idempotency, retries, dispatch, Continuations) stays in `rails-sidekiq-patterns`; Action Cable channel authorization in `rails-actioncable-patterns`; pool arithmetic in `rails-connection-pool-sizing`

## Rules

- Each Solid component gets its own logical database (`queue`, `cache`, `cable` entries in `database.yml`, each with `migrations_paths`) on a server whose `max_connections` budgets them together with the primary; the single-database layout is a documented choice, never an accident of a missing `connects_to`.
- The queue database may run at `READ COMMITTED` on MySQL (`variables: transaction_isolation: READ-COMMITTED` in its `database.yml` entry): under the default `REPEATABLE READ`, InnoDB gap-locks the indexes Solid Queue polls, so this is the mitigation for observed lock waits or deadlocks on the queue tables, not a gem requirement.
- The generator wires Solid Queue and Solid Cache in `production.rb` and Solid Cable in the `production:` entry of `config/cable.yml` only; development stays on `:async` jobs / `:memory_store` / `async` cable and test on `:test` jobs / `:null_store` / `test` cable - an adapter or store line in the environment file (for Cable, the environment's `adapter:` in `cable.yml`) puts an environment on the stack, a `queue.yml` or `cache.yml` entry alone does not; state which environments are on it.
- Every table is bounded: `clear_finished_jobs_after` (queue), `max_age` plus `max_size` or `max_entries` (cache), `message_retention` with `autotrim` (cable). An unbounded Solid table is a disk-full incident on a schedule.
- `enqueue_after_transaction_commit = true` on `ApplicationJob` when the queue database is separate from the primary - the enqueue commits on its own connection, so the job can run before the row it needs exists.
- Solid Queue retries nothing by itself: `retry_on` is the retry channel, `solid_queue_failed_executions` the dead set, and a crash-abandoned job (`ProcessExitError`, `ProcessPrunedError`, `ProcessMissingError`) reaches neither `retry_on` nor `rescue_from` - a `fail_many_claimed.solid_queue` subscriber is the only automatic recovery.
- A worker's queue-database pool is `threads` + 2 (polling and heartbeat); a `fibers:` worker (Solid Queue 1.6+, `config.active_support.isolation_level = :fiber`, the `async` gem) budgets 3-5 per process; a dispatcher budgets 3 (polling, maintenance, heartbeat), the supervisor up to 3 (heartbeat, prune, releasing a crashed fork's jobs) and the scheduler - one per supervisor - 1 heartbeat + 1 per recurring task firing on the same tick (at least 2), + 1 for its reload loop when `dynamic_tasks_enabled`. Its jobs draw `threads` connections from the primary pool as well. Floors: Solid Queue 1.7, Solid Cache 1.0, Solid Cable 4.1.

## Patterns

### Choosing Solid vs Redis-backed

| Need | Solid | Redis-backed | Decide by |
| ---- | ----- | ------------ | --------- |
| Background jobs | Solid Queue (`FOR UPDATE SKIP LOCKED` claims on MySQL 8) | Sidekiq | Sidekiq already in the Gemfile with Pro / Enterprise features in use (`super_fetch`, rate limiters) keeps Sidekiq; otherwise the queue database removes the Redis dependency and keeps job state queryable |
| Cache | Solid Cache - FIFO, disk-sized, slower per read | `:redis_cache_store` / memcached | A cache whose value comes from size (rendered fragments, API responses for days) is Solid Cache; a sub-millisecond hot-path counter stays in Redis |
| Pub/sub (Action Cable, Turbo Streams) | Solid Cable - polled | `redis` adapter | Delivery latency is `polling_interval` plus one query (0.1 s default) - fine for notifications and stream updates, not for high-frequency fan-out; every cable-serving process polls |

Mixing is normal: Sidekiq for jobs with Solid Cache and Solid Cable for the rest, or Solid Queue with the Redis cable adapter where latency matters. A deployment that keeps Redis for one component gains nothing from moving the others except fewer moving parts.

### Database layout

```yaml
# config/database.yml - production
production:
  primary: &primary_production
    <<: *default
    database: app_production
  queue:
    <<: *primary_production
    database: app_production_queue
    migrations_paths: db/queue_migrate
    variables:
      transaction_isolation: READ-COMMITTED    # optional - fewer gap locks on the polled indexes; add when lock waits on the queue tables show
  cache:
    <<: *primary_production
    database: app_production_cache
    migrations_paths: db/cache_migrate
  cable:
    <<: *primary_production
    database: app_production_cable
    migrations_paths: db/cable_migrate
```

`bin/rails solid_queue:install` / `solid_cache:install` / `solid_cable:install` write `db/queue_schema.rb`, `db/cache_schema.rb`, `db/cable_schema.rb` (the queue and cache installers also write their `production.rb` lines; the cable installer overwrites `config/cable.yml`); `db:prepare` loads each schema into its database. Later gem upgrades ship regular migrations under the `migrations_paths` (`bin/rails solid_queue:update` adds the 1.7 batch tables). `schema_format` is per database (8.1): when the primary entry sets `schema_format: sql`, set `schema_format: ruby` on each Solid entry, since the `<<: *primary_production` merge otherwise inherits it; when `:sql` is app-wide (`config.active_record.schema_format = :sql`), `solid_cache:install` writes `db/cache_structure.sql` and the cache entry stays `:sql`, while the queue and cable installers still write `*_schema.rb`, so those two entries set `schema_format: ruby`.

Single-database layout (one `database.yml` entry, the `*_schema.rb` contents moved into ordinary migrations, no `connects_to`): the queue tables join the primary's `max_connections` budget and its `REPEATABLE READ` default unless the whole app runs `READ COMMITTED`; a job enqueued inside an app transaction commits or rolls back with it (transactional integrity), and a Solid Cache write inside an app transaction is rolled back with it. The separate-database layout is the default for a reason; choose single-database only for a small deployment that wants one backup and one failover.

### Solid Queue - `config/queue.yml`

```yaml
# Bad - one worker on every queue, deploy count unknown; a 10-minute report job starves the mailers
production:
  workers:
    - queues: "*"
      threads: 5

# Good - isolation by queue, pool budget derivable (threads + 2 on the queue database per process)
production:
  dispatchers:
    - polling_interval: 1
      batch_size: 500
      concurrency_maintenance_interval: 300
  workers:
    - queues: [critical, default]       # mail lands on default under 8.1 defaults (deliver_later_queue_name = nil)
      threads: 3
      polling_interval: 0.1
      processes: 2
    - queues: ["reports*"]               # a trailing * matches queues by prefix; a bare * polls every queue
      threads: 2
      polling_interval: 1
      processes: 1
```

Queue order in `queues:` is priority order for that worker. `bin/jobs` validates the file at boot. The Puma plugin (`plugin :solid_queue` in `puma.rb`, gated by `SOLID_QUEUE_IN_PUMA`) forks the supervisor on the web pod - the workers are separate processes with their own pools; `solid_queue_mode :async` (1.3+) runs them as threads in the Puma master and ignores `processes` - the README's own advice is `fork` unless there is a strong reason. Other settings live in `config/environments/*.rb` under `config.solid_queue.*`: `shutdown_timeout` (5 s - keep the orchestrator's grace period above it; on `QUIT` in-flight jobs return to their queues), `process_alive_threshold` (5 min before a silent process is pruned), `preserve_finished_jobs` with `clear_finished_jobs_after` (1 day; the installer adds the hourly recurring clear task), `on_thread_error`, `silence_polling`.

Enqueue errors raise `SolidQueue::Job::EnqueueError` rather than the Active Job error, so `perform_later` never returns `false` silently. Incremental adoption: `self.queue_adapter = :solid_queue` on the job classes being moved while `config.active_job.queue_adapter` stays on the old backend.

### Concurrency controls, recurring tasks, batches

```ruby
class SyncAccountJob < ApplicationJob
  limits_concurrency to: 1, key: ->(account) { account }, duration: 15.minutes, on_conflict: :discard   # on_conflict: 1.2+
end
```

`limits_concurrency` takes a semaphore per `key` at enqueue: a conflicting job waits in `solid_queue_blocked_executions` (`:block`, the default - a backlog, not a drop) or is dropped (`:discard`); `duration` (default `default_concurrency_control_period`, 3 min) is the failsafe after which a semaphore a dead worker never released expires, so set it above the job's worst-case runtime, and know that under `:discard` every conflicting enqueue inside that window is lost. `group:` shares one limit across classes. A scheduled job's limit is enforced when it becomes due, not at enqueue.

Recurring tasks are `config/recurring.yml` (`class` or `command`, `schedule` in cron or `every 15 minutes` form, `args`, `queue`, `priority`), run by the scheduler process; several schedulers on one schedule dedupe through the unique index on `solid_queue_recurring_executions` (only while `preserve_finished_jobs` is true and the finished jobs are still kept), so a recurring task needs no leader lock - overlap of a slow run with its next tick is `limits_concurrency`'s job. `SOLID_QUEUE_SKIP_RECURRING=true` disables them for a one-off process; `dynamic_tasks_enabled: true` (1.4+) lets the app schedule and unschedule tasks at runtime.

Batches: `SolidQueue::Batch.enqueue(on_finish: ReportDoneJob, on_success: ReportOkJob, on_failure: ReportFailedJob) { items.each { |i| ProcessItemJob.perform_later(i) } }` - `on_finish` fires after every job's retries end, failures included; `on_success` only when none failed (a `discard_on` discard counts as success); `on_failure` when at least one failed. The dispatcher's `batch_maintenance` sweeps stalled batches. Finished batches are cleared only by `SolidQueue::Batch.clear_finished_in_batches` - add it to `recurring.yml` beside the jobs clear task; failed batches stay until handled.

### Failure, crash recovery, visibility

A job that raises past `retry_on` lands in `solid_queue_failed_executions` and stays until retried or discarded - `mission_control-jobs` (mount the engine auth-gated, as `Sidekiq::Web` is) or `SolidQueue::FailedExecution#retry` / `#discard`. A worker fork killed by SIGKILL or OOM is reaped by its supervisor and its jobs fail at once with `SolidQueue::Processes::ProcessExitError`; when the supervisor or pod dies too, the jobs stay claimed until another process prunes the registration after `process_alive_threshold` and fails them with `ProcessPrunedError`; an execution orphaned by a vanished process registration fails with `ProcessMissingError` when the next supervisor boots. Either way a different process fails them, so no `retry_on` or `rescue_from` ever sees them. A deploy's `SIGTERM` gives running jobs `shutdown_timeout` (5 s default); the supervisor then sends `QUIT`, the workers exit at once and their in-flight jobs return to the queue and rerun - a job longer than that checkpoints (`rails-sidekiq-patterns`, Graceful Shutdown). Recovery for idempotent jobs is a subscriber in an initializer, where every Solid Queue process loads it - capped, since the job itself may be what kills the worker:

```ruby
# config/initializers/solid_queue.rb
CRASH_ERRORS = [SolidQueue::Processes::ProcessExitError, SolidQueue::Processes::ProcessPrunedError, SolidQueue::Processes::ProcessMissingError].freeze
ActiveSupport::Notifications.subscribe("fail_many_claimed.solid_queue") do |event|
  next unless CRASH_ERRORS.any? { |klass| event.payload[:error].is_a?(klass) }
  SolidQueue::FailedExecution.where(job_id: event.payload[:job_ids]).find_each do |failed|
    failed.retry if Rails.cache.increment("crash-retry:#{failed.job.active_job_id}", 1, expires_in: 1.day).to_i <= 2
  end
end
```

Without it, a crashed pod silently parks every in-flight job as failed: alert on `SolidQueue::FailedExecution.count`, or on the `mission_control-jobs` failed view, the way the Sidekiq dead set is watched.

### Solid Cache - `config/cache.yml`

```yaml
default: &default
  database: cache                     # the database.yml entry; omitting it puts the cache on ActiveRecord::Base's pool
  store_options:
    max_age: <%= 60.days.to_i %>
    max_size: <%= 256.gigabytes %>    # and/or max_entries, plus max_age
    namespace: <%= Rails.env %>
    expiry_method: :job               # :thread (default) expires inline on a background thread of the writing process
    expiry_queue: default             # a queue the app's Active Job backend (Solid Queue or Sidekiq) serves, or expiry never runs

production:
  <<: *default
  size_estimate_samples: 1000
  encrypt: true                       # environment level, not store_options; Active Record Encryption must be configured
```

`config.cache_store = :solid_cache_store` (the installer writes it in `production.rb`). Expiry is write-driven: every write increments a counter and at half of `expiry_batch_size` (100) a task deletes one batch - over `max_entries` / `max_size` the oldest entries, otherwise entries older than `max_age` (2 weeks by default; `nil` only with `max_entries`). A cache that is read far more than written expires slowly; `max_age` unset means the 2-week default, and only an explicit `max_age: nil` (with `max_entries`) keeps entries until size pressure evicts them. Size `max_size` to the disk and buffer pool given to the cache database (a cache larger than the buffer pool reads from disk) and `max_age` to how long an entry stays correct. `max_key_bytesize` (1024) truncates longer keys with a digest, so a key carrying a serialized record is not a correctness bug but a readability one. `clear_with: :truncate` (`:delete` in test) is what `Rails.cache.clear` runs. A `fetch` inside a hot action writes a DB row per miss and `race_condition_ttl` still applies; a per-request `increment` (a `rate_limit` counter on a public endpoint) is a row update per request - acceptable at hundreds per second, Redis beyond that.

### Solid Cable - `config/cable.yml`

```yaml
production:
  adapter: solid_cable
  connects_to:
    database:
      writing: cable
  polling_interval: 0.1.seconds       # delivery latency floor; every cable-serving process polls at this rate
  message_retention: 1.day            # trim cut-off; must outlive the slowest subscriber's poll plus a margin
  autotrim: true                      # SolidCable::TrimJob otherwise, on a recurring schedule
  trim_batch_size: 100
  use_skip_locked: true               # MySQL 8.0+ - leave on
  encrypt: true                       # Solid Cable 4.1+; when broadcasts carry user data - Active Record Encryption configured and the msgpack gem in the Gemfile
```

Every process that broadcasts (web or job worker) holds cable-database connections for the `solid_cable_writer` thread and the autotrim thread, and a cable-serving process one more for its listener's polling - count them in the cable pool budget (`rails-connection-pool-sizing`'s Cable extra). Broadcasts queue in-process and are written in batches of up to `writer_batch_size` (4) per insert; subscriber cost is one poll per `polling_interval` per process, so lowering the interval multiplies queries by the process count, not the subscriber count. `message_retention` is why the table stays small.

## Output Format

When authoring, emit this block plus the config it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it. One block per Solid component in evidence (`Gemfile` has the gem, or an adapter / store / `connects_to` names it). Every field holds the corrected value, except a field the reviewed config violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when nothing is set). A component the request names but the code lacks gets a block for the config the fix introduces, its `Component` suffixed `(proposed)`; a component the request keeps on Redis gets one line, no block. A field whose evidence is outside the read set is `not in evidence` plus the file to read.

```
Component: {Solid Queue | Solid Cache | Solid Cable}

Environments: {production only (generator default) | production + staging | every environment including test | <list> - the environment files say which}

Database: {own logical database `<name>` on the primary's server | own server | shares the primary (single-database layout - documented: <reason>) | shares the primary - GAP (no connects_to, undocumented) | not in evidence}

Isolation: {READ COMMITTED via database.yml variables | REPEATABLE READ (default; GAP when lock waits or deadlocks on the queue tables are observed) | n/a (Cache, Cable, or a non-MySQL Database per stack-detect)}

Pool budget: {per host: <processes> x (<threads> + 2) per worker entry (3-5 per fibers process) + 3 per dispatcher + 3 supervisor + 2 or more per scheduler (+ 1 with dynamic_tasks_enabled) on the queue database, + <threads> per worker process on the primary; hosts not in evidence - say so | 2 per broadcasting process (writer + autotrim) + 1 per cable-serving process | ActiveRecord::Base pool - the cache shares the primary's connections | own pool on the cache database, sized like the primary's (every thread may read) + 1 for the expiry thread | not computed - GAP}

Bounds: {clear_finished_jobs_after <N> (the recurring clear task present; absent - GAP) | preserve_finished_jobs false (deleted on completion; recurring dedupe lost) | max_age <N> + max_size <N> and/or max_entries <N> | message_retention <N>, autotrim on | unbounded - GAP (<what grows>)}

Dispatch: {enqueue_after_transaction_commit = true on ApplicationJob | transactional integrity (single database, documented) | not set - GAP (separate queue database, enqueue inside transactions) | n/a (Cache, Cable)}

Concurrency controls: {<JobClass>: key <expr>, to <N>, duration <N>, on_conflict <:block | :discard> | none needed - no overlapping or rate-bound job in scope | unknown - job runtime not in evidence | none - GAP (<job> overlaps its next run) | n/a (Cache, Cable)}

Recovery: {fail_many_claimed subscriber retries idempotent jobs + failed-count alert | mission_control-jobs mounted (auth-gated) + failed-count alert | failed executions unwatched - GAP | n/a (Cache, Cable)}

Encryption: {encrypt: true (Active Record Encryption configured) | off - payloads hold no personal or secret data | off - GAP (<what is stored>) | n/a (Queue - arguments are IDs)}
```

## Avoid

- Leaving the queue database on `REPEATABLE READ` once lock waits on its tables show - `transaction_isolation: READ-COMMITTED` is the fix
- `queues: "*"` on the only worker when one queue holds minute-long jobs - isolate by queue and `processes`
- Solid Cache with an explicit `max_age: nil`, or no `database:` on a deployment whose primary pool is already sized to Puma threads
- `on_conflict: :discard` on a job whose runs must all happen - a stuck semaphore discards every conflicting enqueue for `duration`
- Expecting `retry_on` to see `ProcessPrunedError` - subscribe to `fail_many_claimed.solid_queue` instead
- `polling_interval` below 0.1 s on Solid Cable to chase Redis latency - the query rate scales with the process count
