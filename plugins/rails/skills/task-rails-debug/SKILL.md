---
name: task-rails-debug
description: Debug Rails application errors - stack traces, Rails logs, Sidekiq errors, and RSpec failures. Paste an error or describe the unexpected behavior. Not for production incident analysis with blast radius assessment (use task-incident-root-cause for that).
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

## STEP 1 - INTAKE

Ask for: full stack trace or error message, the source file where the error originates, and what the user expected to happen. If a stack trace is provided, identify the first application-code frame (skip gem/library frames) and read that file.

## STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

### ActiveRecord / Database Errors

- `ActiveRecord::RecordNotFound` -> missing record. Check params, scopes, and whether the record exists. Common when IDs come from user input without validation.
- `ActiveRecord::RecordInvalid` -> validation failure. Read the model's validations and check which one(s) failed via `record.errors.full_messages`. Use skill: `rails-activerecord-patterns`.
- `ActiveRecord::StatementInvalid` -> raw SQL error. Check migration state (`rails db:migrate:status`), column types, and whether a migration was missed.
- `PG::UniqueViolation` -> duplicate record. Check unique constraints and indexes. May need upsert (`find_or_create_by`) or an idempotency guard.
- `PG::LockNotAvailable` -> migration lock or long transaction. Use skill: `rails-migration-safety` (concurrent index, lock timeout). Check for long-running queries: `SELECT * FROM pg_stat_activity WHERE wait_event_type = 'Lock'`.

### Controller / Request Errors

- `ActionController::ParameterMissing` -> strong params misconfiguration. The client sends `{ field: value }` but the controller expects `{ model_name: { field: value } }`. Check `params.require(:model_name).permit(...)` against the actual request body.
- `ActionController::RoutingError` -> route not defined. Run `rails routes | grep <path>` to verify.
- `Pundit::NotAuthorizedError` -> authorization failure. Check the policy file and the user's role/permissions.

### Autoloading / Require Errors

- `LoadError` or `NameError: uninitialized constant Foo` -> Zeitwerk autoloading failure. File path must match constant name (PascalCase class -> snake_case file in the correct directory). For Rails 6+: run `bin/rails zeitwerk:check`. Prevention: RSpec test that does `Rails.application.eager_load!` and verifies all constants load.

### Sidekiq Errors

- Sidekiq job failure -> check args (must be JSON-serializable primitives, not AR objects), idempotency guard, retry state. Use skill: `rails-sidekiq-patterns`.
- `ActiveJob::DeserializationError` -> the record was deleted between enqueue and execution. Add `return unless record` guard.

### Nil Reference Errors

- `NoMethodError: undefined method 'X' for nil:NilClass` -> trace where the nil originates. Common causes: missing association (`belongs_to` without record), failed `find_by` returning nil, uninitialized variable.

## STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (not gem code)
2. Open that source file and read the failing method
3. Trace the data path: where does the problematic value originate? Follow it upstream through controller params, service calls, or ORM queries
4. For Sidekiq errors: check both the job's `perform` method and the code that enqueues it

## STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The ParameterMissing error occurs because the controller expects params nested
under :order (params.require(:order)) but the client sends a flat JSON body
{ total: 99.99 } without the :order wrapper key.
```

## STEP 5 - FIX

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

## STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **RSpec request spec** that exercises the exact code path with the expected params shape
- **Validation** at the model level to catch bad data early
- **Linting rule** (rubocop) if applicable

## Avoid

- Do not bypass strong params with `params.permit!` or `to_unsafe_h` to "fix" ParameterMissing
- Do not rescue exceptions globally with `rescue => e; render json: { error: e.message }` - handle specific errors
- Do not disable Zeitwerk with `config.autoloader = :classic` to fix autoloading errors
- Do not add `dependent: :destroy` as a fix for DeserializationError (that destroys data; add a nil guard instead)
- Do not add blanket `rescue StandardError` to suppress errors in Sidekiq jobs

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

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Rails conventions preserved - strong params, service objects, Pundit patterns not bypassed
- [ ] Prevention step included (RSpec test, validation, or linting rule)
- [ ] For `PG::LockNotAvailable`: Use skill: `rails-migration-safety` referenced; for Sidekiq: idempotency and retry state checked
