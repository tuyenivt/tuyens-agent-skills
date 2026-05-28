---
name: task-rails-debug
description: Diagnose and fix Rails errors from stack traces, logs, Sidekiq failures, and RSpec output.
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing.

## When to Use

- Diagnosing Rails errors from stack traces or logs
- ActiveRecord errors (`RecordNotFound`, `RecordInvalid`, `StatementInvalid`)
- Controller/routing errors (`ParameterMissing`, `RoutingError`, `Pundit::NotAuthorizedError`)
- Sidekiq job failures (`DeserializationError`, argument issues)
- Zeitwerk autoloading (`LoadError`, `NameError`)
- Nil reference tracing

Not for: production incident analysis (`/task-oncall-start`), feature implementation (`task-rails-implement`), perf optimization without an error (`task-rails-review-perf`).

## Rules

- Classify the error before proposing a fix
- State root-cause confidence (HIGH / MEDIUM / LOW)
- Reproduce locally (failing spec or rails console) before proposing the fix
- Fix is minimal and addresses root cause, not symptoms
- Never bypass strong params, Pundit, or Zeitwerk
- Never `rescue` exceptions globally
- Include a prevention step (test, validation, lint)

## Workflow

### Step 1 - Intake

Ask for: full stack trace or error message, source file where it originates, what the user expected. Identify the first application-code frame; read that file.

If user provides a partial error, ask for the full stack trace before proceeding.

**"No error, just wrong behavior":** when a value is silently dropped ("the field I added gets ignored"), reframe as a boundary-loss question - at which layer does the value disappear?

```
params -> params.require.permit (silently drops keys not in the list - most common) ->
  form object / DTO (`attribute :foo` declared?) ->
  service whitelist (`Order.create!(name: dto.name)` vs `dto.attributes`) ->
  AR `alias_attribute` / `attribute :foo, :string` mismatch with migration column name ->
  DB
```

Same shape for ActiveJob/Sidekiq: `dispatch site -> after_commit block (still holds value? record.previous_changes vs attributes) -> GlobalID round-trip (AR records re-fetched on perform; correctness depending on enqueue-time field values is a bug) -> perform body -> side effect`.

**"Action loads associations / fires callbacks / runs queries the code doesn't seem to ask for":** use skill `rails-implicit-config-audit` before tracing the data path. Common invisible sources: `config.load_defaults <= 6.1` (no `has_many_inversing`, no `automatic_scope_inversing`), `belongs_to ... touch: true`, `has_many ... autosave: true`, `accepts_nested_attributes_for`, callbacks that reference `self.<association>`, `default_scope`. Identify the source before reaching for `.includes`.

### Step 2 - Classify

Match the error and load the relevant atomic skill:

**ActiveRecord / Database:**

| Error                                                        | Likely Cause                                              | Skill                              |
| ------------------------------------------------------------ | --------------------------------------------------------- | ---------------------------------- |
| `RecordNotFound`                                             | Missing record, bad params/scopes                         | `rails-activerecord-patterns`      |
| `RecordInvalid`                                              | Validation failure - check `record.errors.full_messages`  | `rails-activerecord-patterns`      |
| No error but `update`/`save` loads associations the action body never references | `touch:` / `autosave:` / `accepts_nested_attributes_for` / callback / missing `inverse_of` | `rails-implicit-config-audit` |
| `StatementInvalid`                                           | Raw SQL error, missing migration, wrong column type       | `rails-migration-safety`           |
| `Mysql2::Error: Lock wait timeout`                           | Long-running transaction or held advisory lock            | `rails-db-locking-patterns`        |
| `Mysql2::Error: Deadlock found`                              | Gap-lock cascade under default RR - non-PK `with_lock`    | `rails-db-locking-patterns`        |
| `Mysql2::Error: Too many connections` / `MySQL gone away`    | Pool / network / `max_connections` / `wait_timeout`       | `rails-connection-pool-sizing`     |
| `Mysql2::Error::TimeoutError`                                | `read_timeout` exceeded                                   | `rails-activerecord-patterns`      |
| MySQL `History list length` / Aurora `undo_log_records` high | Long-running transaction holding undo (Mode A)            | `rails-batch-processing-patterns`  |
| `PG::UniqueViolation`                                        | Duplicate record - needs upsert or idempotency guard      | `rails-activerecord-patterns`      |
| `PG::LockNotAvailable`                                       | Migration lock or long transaction                        | `rails-postgresql-migration-safety` |
| `PG::ConnectionBad: remaining slots reserved`                | DB-side `max_connections` reached                         | `rails-connection-pool-sizing`     |
| PG `idle in transaction` long-runner                         | Worker crashed mid-tx; `idle_in_transaction_session_timeout` unset | `rails-batch-processing-patterns` |

**Controller / Request:**

| Error                                            | Likely Cause                                | Skill                     |
| ------------------------------------------------ | ------------------------------------------- | ------------------------- |
| `ActionController::ParameterMissing`             | Strong params expects nested key client doesn't send | `rails-security-patterns` |
| `ActionController::RoutingError`                 | Route not defined - `rails routes`          | -                         |
| `Pundit::NotAuthorizedError`                     | Policy denies action for user's role        | `rails-security-patterns` |
| `ActionController::InvalidAuthenticityToken`     | Missing CSRF / `protect_from_forgery` mismatch | `rails-security-patterns` |
| `JSON::ParserError` / `Parameters::ParseError`   | Malformed body; return 400 not 500 - add `rescue_from` | - |

**Autoloading:**

`LoadError` / `NameError: uninitialized constant` - Zeitwerk filename/constant mismatch. Run `bin/rails zeitwerk:check`. Prevention: `Rails.application.eager_load!` test.

**Sidekiq:**

| Error                                                              | Likely Cause                                                                | Skill                              |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------- | ---------------------------------- |
| Sidekiq job failure                                                | Non-serializable args, missing idempotency guard                            | `rails-sidekiq-patterns`           |
| `ActiveJob::DeserializationError`                                  | Record deleted, OR job enqueued inside a transaction that hasn't committed  | `rails-sidekiq-patterns`           |
| OOM-kill / SIGKILL on Sidekiq (no Ruby exception)                  | RSS exceeded container limit; missing `WorkerKiller`                        | `rails-batch-processing-patterns`  |
| `NoMemoryError` / `Errno::ENOMEM`                                  | Memory exhaustion - unbounded array in batch loop                           | `rails-batch-processing-patterns`  |

**Concurrency / Resource:**

| Error                                       | Likely Cause                                                                          | Skill                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------- |
| `Rack::Timeout::RequestTimeoutException`    | Slow query, external API hang, or N+1                                                 | `rails-activerecord-patterns`      |
| `ActiveRecord::Deadlocked`                  | Two transactions taking locks in opposite order; on MySQL RR usually gap-lock cascade | `rails-db-locking-patterns`        |
| `ActiveRecord::ConnectionTimeoutError`      | Pool exhausted; check `connection_pool.stat` for `waiting > 0`                        | `rails-connection-pool-sizing`     |
| `ActiveRecord::StaleObjectError`            | Optimistic lock conflict; storms on hot rows = wrong choice                           | `rails-db-locking-patterns`        |
| `PG::ConnectionBad` / `PG::UnableToSend`    | DB restart, network blip, or pool corruption after fork                               | `rails-connection-pool-sizing`     |

**Nil reference:** `NoMethodError: undefined method 'X' for nil` - missing association, failed `find_by`, uninitialized variable.

### Step 3 - Locate

1. Read stack trace top to bottom; find first application-code frame
2. Open that file, read the failing method
3. Trace data path upstream (controller params, service calls, ORM queries)
4. Sidekiq errors: check both `perform` and the enqueue site

### Step 3.5 - Reproduce (when feasible)

A fix you can't reproduce is a guess. Reduce to:
- A failing RSpec example (preferred - prevention builds on it)
- A `rails console` snippet
- A `curl`/`httpie` request in dev

If reproduction is impossible (race condition, prod-only data, third-party outage), state that and lower confidence accordingly.

### Step 4 - Root Cause

Explain **why**, not just what. State confidence: **HIGH** (reproduced or obvious), **MEDIUM** (pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The ParameterMissing error occurs because the controller expects params nested
under :order but the client sends a flat JSON body without the wrapper key.
```

### Step 5 - Fix

Provide before/after. Minimal; addresses root cause:

```ruby
# BEFORE (expects { order: { total: 99.99 } })
def order_params
  params.require(:order).permit(:total, :status, :customer_id)
end

# AFTER A: fix client to wrap params
# AFTER B (if API convention is flat):
def order_params
  params.permit(:total, :status, :customer_id)
end
```

### Step 6 - Prevention

- **RSpec request spec** exercising the exact path with expected params shape
- **Validation** at the model level
- **Linting rule** if applicable

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why, referencing file:line]

## Fix
[Before/after code]

## Prevention
[RSpec test, validation, or config change]
```

## Self-Check

- [ ] Error classified via Step 2 table; matching atomic skill consulted
- [ ] Reproduction attempted; if not feasible, that limitation is stated and confidence lowered
- [ ] Root cause references file:line; confidence stated
- [ ] Before/after fix is minimal and addresses root cause
- [ ] Rails conventions preserved - strong params, services, Pundit not bypassed
- [ ] Prevention step included (RSpec, validation, lint, or config)
- [ ] "Wrong behaviour, no error" cases consulted `rails-implicit-config-audit` before tracing data path

## Avoid

- Bypassing strong params with `permit!` / `to_unsafe_h` to "fix" `ParameterMissing`
- `rescue => e; render json: { error: e.message }` - handle specific errors
- `config.autoloader = :classic` to fix autoloading - fix the filename/constant mismatch
- Adding `dependent: :destroy` as a fix for `DeserializationError` - add a nil guard instead
- Blanket `rescue StandardError` to suppress errors in Sidekiq jobs
- Proposing a fix before classifying and locating the root cause
