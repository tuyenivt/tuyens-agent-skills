---
name: task-rails-debug
description: Diagnose and fix Rails errors from stack traces, logs, Sidekiq failures, and RSpec output with root-cause confidence.
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

## When to Use

- Rails errors from stack traces, logs, RSpec output, or Sidekiq failures
- ActiveRecord, controller/routing, Pundit, Zeitwerk, or nil-reference errors
- "No error but wrong behavior" - silently dropped values, unexpected queries

Not for: production incident triage (`/task-oncall-start`), feature work (`task-rails-implement`), perf without an error (`task-rails-review-perf`).

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Accept pre-confirmed stack from parent.

### Step 3 - Intake and Locate

Collect: full stack trace or error message, source file, expected behavior. If partial, ask for the full trace before proceeding. Identify the first application-code frame; read that file and the failing method. Trace the data path upstream (controller params -> service -> ORM); for Sidekiq, inspect both `perform` and the enqueue site.

**No error, silent value drop** ("the field I added gets ignored"): trace the boundary chain - walk **every** hop even after finding a drop; multi-hop chains routinely drop the value twice (permit list AND a service whitelist), and fixing only the first leaves the symptom intact. Debug aids: the "Unpermitted parameter" log line; `action_on_unpermitted_parameters = :raise` in test.

```
params -> strong params permit list -> form/DTO attribute -> service whitelist
  -> AR alias_attribute / attribute type vs migration column -> DB
```

For ActiveJob/Sidekiq: dispatch site -> `after_commit` snapshot -> GlobalID round-trip (records re-fetched on perform) -> `perform` body -> side effect.

**Unexpected queries/callbacks/loads** (action loads associations the code never references): use skill `rails-implicit-config-audit` *before* tracing the data path. Common invisible sources: `load_defaults <= 6.1`, `touch:`, `autosave:`, `accepts_nested_attributes_for`, `default_scope`, callbacks referencing `self.<association>`.

### Step 4 - Classify

Match the error and load the relevant atomic skill; follow that skill's cross-references when the fix pattern lives one hop away (deadlock fix shape sits in `rails-activerecord-patterns` via `rails-db-locking-patterns`). No-exception symptoms classify by their Step 3 path (silent value drop / unexpected queries), not these tables. When evidence shows multiple interacting causes (wrong arg shape AND a rollback path), report all of them - the tables name the entry point, not the whole story.

**ActiveRecord / Database:**

| Error                                                | Likely Cause                                              | Skill                              |
| ---------------------------------------------------- | --------------------------------------------------------- | ---------------------------------- |
| `RecordNotFound`                                     | Missing record, bad params/scopes                         | `rails-activerecord-patterns`      |
| `RecordInvalid`                                      | Validation failure - check `record.errors.full_messages`  | `rails-activerecord-patterns`      |
| `StatementInvalid`                                   | Raw SQL error, missing migration, wrong column type       | `rails-migration-safety`           |
| `PG::UniqueViolation`                                | Duplicate - needs upsert or idempotency guard             | `rails-activerecord-patterns`      |
| `PG::LockNotAvailable`                               | Migration lock or long transaction                        | `rails-postgresql-migration-safety` |
| `Mysql2::Error: Lock wait timeout`                   | Long-running transaction or advisory lock                 | `rails-db-locking-patterns`        |
| `Mysql2::Error: Deadlock found` / `Deadlocked`       | Gap-lock cascade under RR; lock order mismatch            | `rails-db-locking-patterns` (+ retry pattern: `rails-transaction-patterns`) |
| `StaleObjectError`                                   | Optimistic-lock conflict on hot rows                      | `rails-db-locking-patterns`        |
| `ConnectionTimeoutError` / `PG::ConnectionBad`       | Pool exhausted; check `connection_pool.stat`              | `rails-connection-pool-sizing`     |
| `Mysql2::Error: Too many connections` / `MySQL gone` | DB-side `max_connections` / `wait_timeout`                | `rails-connection-pool-sizing`     |
| MySQL `history list length` / PG `idle in tx` long   | Long-running tx holding undo; worker crashed mid-tx       | `rails-batch-processing-patterns`  |
| Action loads associations/callbacks the code didn't  | Implicit config: `touch:`, `autosave:`, nested attrs      | `rails-implicit-config-audit`      |

**Controller / Request:**

| Error                                            | Likely Cause                                | Skill                     |
| ------------------------------------------------ | ------------------------------------------- | ------------------------- |
| `ActionController::ParameterMissing`             | Client body shape mismatches `require/permit` | `rails-security-patterns` |
| `Pundit::NotAuthorizedError`                     | Policy denies action for user's role        | `rails-security-patterns` |
| `InvalidAuthenticityToken`                       | CSRF / `protect_from_forgery` mismatch      | `rails-security-patterns` |
| `RoutingError`                                   | Route not defined - check `rails routes`    | -                         |
| `JSON::ParserError` / `Parameters::ParseError`   | Malformed body - return 400 via `rescue_from` | -                       |
| `Rack::Timeout::RequestTimeoutException`         | Slow query, external API hang, or N+1       | `rails-activerecord-patterns` |

**Sidekiq / Jobs:**

| Error                                                              | Likely Cause                                                                | Skill                              |
| ------------------------------------------------------------------ | --------------------------------------------------------------------------- | ---------------------------------- |
| Sidekiq job failure                                                | Non-serializable args, missing idempotency guard                            | `rails-sidekiq-patterns`           |
| `ActiveJob::DeserializationError`                                  | Record deleted, OR job enqueued inside a transaction not yet committed      | `rails-sidekiq-patterns`           |
| OOM-kill / SIGKILL (no Ruby exception) / `NoMemoryError`           | RSS exceeded container limit; unbounded array in batch loop                 | `rails-batch-processing-patterns`  |

**Autoloading:** `LoadError` / `NameError: uninitialized constant` - Zeitwerk filename/constant mismatch. Run `bin/rails zeitwerk:check`. Prevent with an `Rails.application.eager_load!` test.

**Nil reference:** `NoMethodError: undefined method 'X' for nil` - missing association, failed `find_by`, uninitialized variable.

### Step 5 - Reproduce

Reduce to: a failing RSpec example (preferred - prevention builds on it), a `rails console` snippet, or a `curl` request. Concurrency bugs: a serial spec passing is expected, not exculpatory - say *why* it passes (transactional fixtures can't interleave; one process, no contention) and sketch the two-thread, non-transactional spec that would exercise it. If reproduction is genuinely impossible (prod-only data, third-party outage), state it.

### Step 6 - Root Cause

Explain **why**, not just what, with `file:line`. State confidence:

- **HIGH** - reproduced, or the mechanism is directly evidenced in the code/trace (an unreproduced race can still be HIGH)
- **MEDIUM** - pattern match
- **LOW** - multiple possible causes

After proposing the fix, re-walk the failing path end-to-end with the fix applied - a multi-cause bug "fixed" at one point still fails.

### Step 7 - Fix and Prevention

Before/after diff; minimal; addresses root cause. Never bypass strong params, Pundit, or Zeitwerk. Never `rescue StandardError` globally. Prevention: RSpec example exercising the exact path, model/DB validation, or config change.

## Output Format

```markdown
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH | MEDIUM | LOW)
[Why, referencing file:line]

## Fix
[Before/after diff]

## Prevention
[RSpec test, validation, or config change]

## Remediation                       <!-- only when damage outlives the fix -->
[Dead/poisoned jobs to drain, data to backfill, alerts to clear]

## Also Found                        <!-- only when present -->
[Secondary bugs noticed en route, each with file:line - report, don't silently fix]
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed
- [ ] Step 3: full trace gathered; first app-code frame and data path located; unexpected-query symptoms consulted `rails-implicit-config-audit` before tracing; silent-drop cases walked the full boundary chain
- [ ] Step 4: error classified; matching atomic skill consulted
- [ ] Step 5: reproduction attempted; limitation stated if not feasible
- [ ] Step 6: root cause references file:line; confidence stated
- [ ] Step 7: minimal fix; strong params / Pundit / Zeitwerk preserved; prevention included

## Avoid

- Proposing a fix before classifying and locating the root cause
- Bypassing strong params with `permit!` / `to_unsafe_h` to silence `ParameterMissing`
- `rescue => e; render json: { error: e.message }` instead of handling specific errors
- `config.autoloader = :classic` to fix Zeitwerk autoload errors
- Treating `DeserializationError` as job-side: `discard_on`, nil guards, or `dependent: :destroy` mask an enqueue-site bug - fix the dispatch first, then drain jobs verified dead against the DB
- Blanket `rescue StandardError` in Sidekiq jobs
