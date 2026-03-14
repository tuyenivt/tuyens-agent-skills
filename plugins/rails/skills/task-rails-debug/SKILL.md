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

STEP 1 - INTAKE: Rails stack trace, log, Sidekiq error, RSpec failure, browser error

STEP 2 - CLASSIFY:

- DI / Autoloading errors: `LoadError` or `NameError: uninitialized constant Foo` → Zeitwerk autoloading failure; check file path matches constant name (PascalCase class → snake_case file), no typo in require/require_relative. For Rails 6+: run `rails zeitwerk:check`. Prevention: RSpec `describe 'autoloading'` that does `require 'application'` and checks all constants load.
- ActiveRecord::RecordNotFound → missing record, check params/scopes
- ActiveRecord::RecordInvalid → validation failure
- ActionController::ParameterMissing → strong params misconfiguration
- ActiveRecord::StatementInvalid → SQL error, check migration state
- NoMethodError on nil:NilClass → nil reference, trace the nil
- Sidekiq job failure → check args, idempotency, retry state
- PG::UniqueViolation → duplicate, check unique constraints
- PG::LockNotAvailable → migration lock or long transaction
- LoadError/NameError → Zeitwerk autoloading, check file naming

STEP 3 - LOCATE: read stack trace, open source file, trace call chain

STEP 4 - ROOT CAUSE: explain WHY. Confidence: HIGH/MEDIUM/LOW

STEP 5 - FIX: before/after code, minimal change

STEP 6 - PREVENTION: RSpec test, linting rule, validation

OUTPUT: Bug Analysis → Root Cause → Fix → Prevention

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Rails conventions preserved - strong params, service objects, Pundit patterns not bypassed
- [ ] Prevention step included (RSpec test, validation, or linting rule)
- [ ] For `PG::LockNotAvailable`: migration safety pattern referenced; for Sidekiq: idempotency and retry state checked
