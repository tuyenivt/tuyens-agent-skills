---
name: task-rails-debug
description: Diagnose and fix Rails application errors from stack traces, logs, Sidekiq failures, and RSpec output. Paste an error or describe unexpected behavior. Not for production incident analysis (use /task-oncall-start).
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

## When to Use

- Diagnosing Rails application errors from stack traces or log output
- Debugging ActiveRecord errors (RecordNotFound, RecordInvalid, StatementInvalid)
- Fixing controller/routing errors (ParameterMissing, RoutingError, Pundit::NotAuthorizedError)
- Debugging Sidekiq job failures (DeserializationError, argument issues)
- Resolving Zeitwerk autoloading errors (LoadError, NameError)
- Tracing nil reference errors (NoMethodError on nil)

Not for:

- Production incident analysis or runbook execution (use `/task-oncall-start`)
- Feature implementation (use `task-rails-new`)
- Performance optimization without an error

## Rules

- Always classify the error before proposing a fix - understand the category first
- Always state root cause confidence level (HIGH/MEDIUM/LOW)
- Fix must be minimal and address root cause, not symptoms
- Never bypass strong params, Pundit policies, or Zeitwerk to "fix" an error
- Never rescue exceptions globally - handle specific error types
- Always include a prevention step (test, validation, or linting rule)

## Workflow

### STEP 1 - INTAKE

Ask for: full stack trace or error message, the source file where the error originates, and what the user expected to happen. If a stack trace is provided, identify the first application-code frame (skip gem/library frames) and read that file.

If the user provides only a partial error (e.g., just an error class name or a single line), ask for the full stack trace or the relevant log output before proceeding. If the user describes unexpected behavior without an error, ask them to reproduce it and capture the Rails log output (`tail -f log/development.log`).

### STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

**ActiveRecord / Database Errors:**

| Error                            | Likely Cause                                             | Skill                         |
| -------------------------------- | -------------------------------------------------------- | ----------------------------- |
| `ActiveRecord::RecordNotFound`   | Missing record, bad params/scopes                        | `rails-activerecord-patterns` |
| `ActiveRecord::RecordInvalid`    | Validation failure - check `record.errors.full_messages` | `rails-activerecord-patterns` |
| `ActiveRecord::StatementInvalid` | Raw SQL error, missing migration, wrong column type      | `rails-migration-safety`      |
| `PG::UniqueViolation`            | Duplicate record - needs upsert or idempotency guard     | `rails-activerecord-patterns` |
| `PG::LockNotAvailable`           | Migration lock or long transaction                       | `rails-migration-safety`      |

**Controller / Request Errors:**

| Error                                | Likely Cause                                         | Skill                     |
| ------------------------------------ | ---------------------------------------------------- | ------------------------- |
| `ActionController::ParameterMissing` | Strong params expects nested key client doesn't send | `rails-security-patterns` |
| `ActionController::RoutingError`     | Route not defined - run `rails routes`               | -                         |
| `Pundit::NotAuthorizedError`         | Policy denies action for user's role                 | `rails-security-patterns` |

**Autoloading / Require Errors:**

| Error                                             | Likely Cause                                             | Skill |
| ------------------------------------------------- | -------------------------------------------------------- | ----- |
| `LoadError` / `NameError: uninitialized constant` | Zeitwerk naming mismatch (file path must match constant) | -     |

Run `bin/rails zeitwerk:check` to verify. Prevention: add `Rails.application.eager_load!` test.

**Sidekiq Errors:**

| Error                             | Likely Cause                                     | Skill                    |
| --------------------------------- | ------------------------------------------------ | ------------------------ |
| Sidekiq job failure               | Non-serializable args, missing idempotency guard | `rails-sidekiq-patterns` |
| `ActiveJob::DeserializationError` | Record deleted between enqueue and execution     | `rails-sidekiq-patterns` |

**Nil Reference Errors:**

| Error                                         | Likely Cause                                                  |
| --------------------------------------------- | ------------------------------------------------------------- |
| `NoMethodError: undefined method 'X' for nil` | Missing association, failed `find_by`, uninitialized variable |

### STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (not gem code)
2. Open that source file and read the failing method
3. Trace the data path: where does the problematic value originate? Follow it upstream through controller params, service calls, or ORM queries
4. For Sidekiq errors: check both the job's `perform` method and the code that enqueues it

### STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The ParameterMissing error occurs because the controller expects params nested
under :order (params.require(:order)) but the client sends a flat JSON body
{ total: 99.99 } without the :order wrapper key.
```

### STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms.

```ruby
# BEFORE (expects { order: { total: 99.99 } })
def order_params
  params.require(:order).permit(:total, :status, :customer_id)
end

# AFTER - Option A: fix the client to wrap params
# POST body: { "order": { "total": 99.99, "customer_id": 1, "status": "pending" } }

# AFTER - Option B: if API convention is flat params
def order_params
  params.permit(:total, :status, :customer_id)
end
```

### STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **RSpec request spec** that exercises the exact code path with the expected params shape
- **Validation** at the model level to catch bad data early
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
[RSpec test, validation, or config change to prevent recurrence]
```

## Self-Check

- [ ] Error classified into a specific category before any fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Rails conventions preserved - strong params, service objects, Pundit patterns not bypassed
- [ ] Prevention step included (RSpec test, validation, or linting rule)
- [ ] For `PG::LockNotAvailable`: `rails-migration-safety` skill referenced; for Sidekiq: idempotency and retry state checked

## Avoid

- Bypassing strong params with `params.permit!` or `to_unsafe_h` to "fix" ParameterMissing
- Rescuing exceptions globally with `rescue => e; render json: { error: e.message }` - handle specific errors
- Disabling Zeitwerk with `config.autoloader = :classic` to fix autoloading errors
- Adding `dependent: :destroy` as a fix for DeserializationError (destroys data; add a nil guard instead)
- Adding blanket `rescue StandardError` to suppress errors in Sidekiq jobs
- Proposing a fix before classifying and locating the root cause
