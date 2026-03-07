---
name: task-rails-debug
description: "Debug Rails errors. Paste a stack trace, Rails log, Sidekiq error, or RSpec failure. Classifies the error, identifies root cause, suggests fix, and recommends prevention."
agent: rails-architect
metadata:
  category: backend
  tags: [ruby, rails, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - INTAKE: Rails stack trace, log, Sidekiq error, RSpec failure, browser error

STEP 2 - CLASSIFY:

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

## Success Criteria

A well-executed debug session passes all of these. Use as a self-check before presenting the fix.

### Completeness

- [ ] Error is classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line from the stack trace
- [ ] A concrete before/after code fix is provided - no vague suggestions
- [ ] A prevention step is included (RSpec test, validation, or linting rule)

### Correctness

- [ ] The fix addresses the root cause, not the symptom
- [ ] Confidence level is stated (HIGH / MEDIUM / LOW) - LOW lists what additional info would help
- [ ] The fix is minimal - no unrelated refactoring
- [ ] Rails conventions preserved - strong params, service objects, Pundit patterns not bypassed

### Staff-Level Signal

- [ ] The "why" is explained - a developer understands how to avoid this class of bug
- [ ] For `PG::LockNotAvailable`, the migration safety pattern is referenced alongside the fix
- [ ] For Sidekiq failures, job idempotency and retry state are checked, not just the error message

## After This Skill

If the output needed significant adjustment - root cause was wrong, Rails conventions were bypassed in the fix, or Sidekiq idempotency was ignored - run `/task-skill-feedback` to log what changed and why.
