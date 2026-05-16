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

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing. These rules govern every step.

## When to Use

- Diagnosing Rails errors from stack traces or log output
- Debugging ActiveRecord errors (`RecordNotFound`, `RecordInvalid`, `StatementInvalid`)
- Fixing controller/routing errors (`ParameterMissing`, `RoutingError`, `Pundit::NotAuthorizedError`)
- Debugging Sidekiq job failures (`DeserializationError`, argument issues)
- Resolving Zeitwerk autoloading errors (`LoadError`, `NameError`)
- Tracing nil reference errors

Not for:

- Production incident analysis or runbook execution (use `/task-oncall-start`)
- Feature implementation (use `task-rails-implement`)
- Performance optimization without an error (use `task-rails-review-perf`)

## Rules

- Always classify the error before proposing a fix
- Always state root cause confidence (HIGH/MEDIUM/LOW)
- Try to reproduce locally (failing spec or rails console snippet) before proposing the fix
- Fix must be minimal and address root cause, not symptoms
- Never bypass strong params, Pundit policies, or Zeitwerk
- Never rescue exceptions globally
- Always include a prevention step (test, validation, or linting rule)

## Workflow

### STEP 1 - INTAKE

Ask for: full stack trace or error message, source file where it originates, what the user expected. Identify the first application-code frame and read that file.

If the user provides a partial error, ask for the full stack trace or log output before proceeding.

**If "no error, just wrong behavior":** When a value is silently dropped (e.g., "the field I added gets ignored"), reframe as a boundary-loss question: at which layer does the value disappear? Trace the path:

`params -> params.require.permit (silently drops keys not in the list - most common cause) -> form object / DTO (`attribute :foo` declared?) -> service whitelist (`Order.create!(name: dto.name)` vs `dto.attributes`) -> AR `alias_attribute` / `attribute :foo, :string` mismatch with migration column name -> DB`

Same shape for ActiveJob/Sidekiq: `dispatch site -> after_commit block (still holds value? `record.previous_changes` vs `record.attributes`) -> GlobalID round-trip (AR records re-fetched on perform; correctness depending on enqueue-time field values is a bug) -> perform body -> side effect`. The bug is almost always at one of these boundaries.

**If the wrong behaviour is "an action loads associations / fires callbacks / runs queries the code doesn't seem to ask for":** use skill `rails-implicit-config-audit` before tracing the data path. Common invisible sources: `config.load_defaults <= 6.1` (no `has_many_inversing`, no `automatic_scope_inversing`), `belongs_to ... touch: true`, `has_many ... autosave: true`, `accepts_nested_attributes_for`, callbacks that reference `self.<association>`, `default_scope`. Identify the source before reaching for `.includes`.

### STEP 2 - CLASSIFY

Match the error and load the relevant atomic skill:

**ActiveRecord / Database:**

| Error                                                        | Likely Cause                                              | Skill                              |
| ------------------------------------------------------------ | --------------------------------------------------------- | ---------------------------------- |
| `RecordNotFound`                                             | Missing record, bad params/scopes                         | `rails-activerecord-patterns`      |
| `RecordInvalid`                                              | Validation failure - check `record.errors.full_messages`  | `rails-activerecord-patterns`      |
| No error, but `update`/`save` loads associations the action body never references | `touch:` / `autosave:` / `accepts_nested_attributes_for` / callback reads `self.<association>` / missing `inverse_of` under `load_defaults <= 6.1` | `rails-implicit-config-audit` |
| `StatementInvalid`                                           | Raw SQL error, missing migration, wrong column type       | `rails-migration-safety`           |
| `Mysql2::Error: Lock wait timeout exceeded`                  | Long-running transaction or held advisory lock            | `rails-db-locking-patterns`        |
| `Mysql2::Error: Deadlock found`                              | Gap-lock cascade under default RR - non-PK `with_lock`    | `rails-db-locking-patterns`        |
| `Mysql2::Error: Too many connections` / `MySQL gone away`    | Pool / network / `max_connections` / `wait_timeout`       | `rails-connection-pool-sizing`     |
| `Mysql2::Error::TimeoutError`                                | `read_timeout` exceeded                                   | `rails-activerecord-patterns`      |
| MySQL `History list length` / Aurora `undo_log_records` high | Long-running transaction holding undo (Failure mode A)    | `rails-batch-processing-patterns`  |
| `PG::UniqueViolation`                                        | Duplicate record - needs upsert or idempotency guard      | `rails-activerecord-patterns`      |
| `PG::LockNotAvailable`                                       | Migration lock or long transaction                        | `rails-postgresql-migration-safety` |
| `PG::ConnectionBad: remaining slots reserved`                | DB-side `max_connections` reached                         | `rails-connection-pool-sizing`     |
| PG `idle in transaction` long-runner                         | Worker crashed mid-transaction; `idle_in_transaction_session_timeout` not set | `rails-batch-processing-patterns` |

**Controller / Request:**

| Error                                | Likely Cause                                         | Skill                     |
| ------------------------------------ | ---------------------------------------------------- | ------------------------- |
| `ActionController::ParameterMissing` | Strong params expects nested key client doesn't send | `rails-security-patterns` |
| `ActionController::RoutingError`     | Route not defined - run `rails routes`               | -                         |
| `Pundit::NotAuthorizedError`         | Policy denies action for user's role                 | `rails-security-patterns` |
| `ActionController::InvalidAuthenticityToken` | Missing CSRF token / `protect_from_forgery` mismatch | `rails-security-patterns` |
| `JSON::ParserError` / `Parameters::ParseError` | Malformed request body; should return 400 not 500 - add `rescue_from` | - |

**Autoloading:**

| Error                                     | Cause                                                    |
| ----------------------------------------- | -------------------------------------------------------- |
| `LoadError` / `NameError: uninitialized constant` | Zeitwerk filename/constant mismatch              |

Run `bin/rails zeitwerk:check` to verify. Prevention: `Rails.application.eager_load!` test.

**Sidekiq:**

| Error                                                              | Likely Cause                                                                | Skill                              |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------- | ---------------------------------- |
| Sidekiq job failure                                                | Non-serializable args, missing idempotency guard                            | `rails-sidekiq-patterns`           |
| `ActiveJob::DeserializationError`                                  | Record deleted, OR job enqueued inside a transaction that hasn't committed  | `rails-sidekiq-patterns`           |
| OOM-kill / SIGKILL on Sidekiq (no Ruby exception, process gone)    | RSS exceeded container memory limit; missing `WorkerKiller`                 | `rails-batch-processing-patterns`  |
| `NoMemoryError` / `Errno::ENOMEM`                                  | In-process or kernel-side memory exhaustion - unbounded array in batch loop | `rails-batch-processing-patterns`  |

**Concurrency / Resource:**

| Error                                       | Likely Cause                                                                          | Skill                              |
| ------------------------------------------- | ------------------------------------------------------------------------------------- | ---------------------------------- |
| `Rack::Timeout::RequestTimeoutException`    | Slow query, external API hang, or N+1                                                 | `rails-activerecord-patterns`      |
| `ActiveRecord::Deadlocked`                  | Two transactions taking row locks in opposite order; on MySQL RR more often gap-lock cascade | `rails-db-locking-patterns`  |
| `ActiveRecord::ConnectionTimeoutError`      | Pool exhausted; check `connection_pool.stat` for `waiting > 0`                        | `rails-connection-pool-sizing`     |
| `ActiveRecord::StaleObjectError`            | Optimistic lock conflict - retry with fresh state. Storms on hot rows = wrong choice  | `rails-db-locking-patterns`        |
| `PG::ConnectionBad` / `PG::UnableToSend`    | DB restart, network blip, or pool corruption after fork                               | `rails-connection-pool-sizing`     |

**Nil Reference:**

| Error                                         | Cause                                                         |
| --------------------------------------------- | ------------------------------------------------------------- |
| `NoMethodError: undefined method 'X' for nil` | Missing association, failed `find_by`, uninitialized variable |

### STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame
2. Open that file and read the failing method
3. Trace the data path upstream (controller params, service calls, ORM queries)
4. For Sidekiq errors: check both the `perform` method and the enqueue site

### STEP 3.5 - REPRODUCE (when feasible)

A fix you can't reproduce is a guess. Reduce the failure to:

- A failing RSpec example (preferred - prevention step builds on it)
- A `rails console` snippet that triggers the error
- A `curl`/`httpie` request in dev

If reproduction is impossible (race condition, prod-only data, third-party outage), state that explicitly and lower confidence accordingly.

### STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The ParameterMissing error occurs because the controller expects params nested
under :order but the client sends a flat JSON body without the wrapper key.
```

### STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause.

```ruby
# BEFORE (expects { order: { total: 99.99 } })
def order_params
  params.require(:order).permit(:total, :status, :customer_id)
end

# AFTER - Option A: fix the client to wrap params
# AFTER - Option B (if API convention is flat):
def order_params
  params.permit(:total, :status, :customer_id)
end
```

### STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **RSpec request spec** that exercises the exact code path with the expected params shape
- **Validation** at the model level
- **Linting rule** (rubocop) if applicable

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why the error occurs, referencing specific file:line]

## Fix
[Before/after code blocks]

## Prevention
[RSpec test, validation, or config change]
```

## Self-Check

- [ ] Error classified into a specific category before any fix proposed
- [ ] Reproduction attempted; if not feasible, that limitation is stated and confidence lowered
- [ ] Root cause references the specific file:line; confidence stated
- [ ] Concrete before/after fix; minimal, addresses root cause not symptom
- [ ] Rails conventions preserved - strong params, service objects, Pundit not bypassed
- [ ] Prevention step included
- [ ] Migration-lock errors: `rails-postgresql-migration-safety` (PG) or `rails-migration-safety` (MySQL) referenced
- [ ] Sidekiq errors: idempotency and retry state checked
- [ ] `Rack::Timeout` / `ConnectionTimeoutError`: `rails-connection-pool-sizing` referenced
- [ ] OOM-kill / `NoMemoryError` / `History list length`: `rails-batch-processing-patterns` referenced
- [ ] `Lock wait timeout` / `Deadlock`: `rails-db-locking-patterns` referenced; lock-by-PK and isolation-tier escalation considered
- [ ] "Wrong behaviour, no error" cases: `rails-implicit-config-audit` consulted when the symptom looks like invisible loads, unexpected callback order, or silent persistence drops

## Avoid

- Bypassing strong params with `params.permit!` or `to_unsafe_h` to "fix" `ParameterMissing`
- `rescue => e; render json: { error: e.message }` - handle specific errors
- `config.autoloader = :classic` to fix autoloading errors - fix the filename/constant mismatch
- Adding `dependent: :destroy` as a fix for `DeserializationError` - add a nil guard instead
- Blanket `rescue StandardError` to suppress errors in Sidekiq jobs
- Proposing a fix before classifying and locating the root cause
