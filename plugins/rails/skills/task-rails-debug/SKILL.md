---
name: task-rails-debug
description: "Debug Rails errors. Paste a stack trace, Rails log, Sidekiq error, or RSpec failure. Classifies the error, identifies root cause, suggests fix, and recommends prevention."
agent: rails-architect
---

STEP 1 — INTAKE: Rails stack trace, log, Sidekiq error, RSpec failure, browser error

STEP 2 — CLASSIFY:

- ActiveRecord::RecordNotFound → missing record, check params/scopes
- ActiveRecord::RecordInvalid → validation failure
- ActionController::ParameterMissing → strong params misconfiguration
- ActiveRecord::StatementInvalid → SQL error, check migration state
- NoMethodError on nil:NilClass → nil reference, trace the nil
- Sidekiq job failure → check args, idempotency, retry state
- PG::UniqueViolation → duplicate, check unique constraints
- PG::LockNotAvailable → migration lock or long transaction
- LoadError/NameError → Zeitwerk autoloading, check file naming

STEP 3 — LOCATE: read stack trace, open source file, trace call chain

STEP 4 — ROOT CAUSE: explain WHY. Confidence: HIGH/MEDIUM/LOW

STEP 5 — FIX: before/after code, minimal change

STEP 6 — PREVENTION: RSpec test, linting rule, validation

OUTPUT: Bug Analysis → Root Cause → Fix → Prevention
