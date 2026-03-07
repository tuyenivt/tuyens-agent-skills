---
name: task-python-debug
description: "Debug Python application errors. Paste a traceback, log, Celery error, or test failure. Classifies the error, identifies root cause, suggests fix. Works with FastAPI and Django."
agent: python-architect
metadata:
  category: backend
  tags: [python, fastapi, django, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - INTAKE: Python traceback, application log, Celery task error, pytest failure

STEP 2 - CLASSIFY:

- ImportError / ModuleNotFoundError → missing dependency, wrong virtualenv, circular import
- AttributeError: 'NoneType' → None reference, trace the None
- pydantic.ValidationError → request validation failed, check schema
- sqlalchemy.exc.IntegrityError → constraint violation (unique, FK, NOT NULL)
- sqlalchemy.exc.OperationalError → DB connection issue, pool exhausted
- asyncio.TimeoutError → async operation timed out
- celery.exceptions.Retry → task retry, check retry config and root cause
- django.core.exceptions.ValidationError → model validation
- django.db.utils.IntegrityError → same as SQLAlchemy constraint issues
- RuntimeError: no running event loop → sync/async mixing
- TypeError: object X can't be used in 'await' expression → forgot to make function async

STEP 3 - LOCATE: read traceback, open source file, trace call chain

STEP 4 - ROOT CAUSE: explain WHY. Confidence: HIGH/MEDIUM/LOW

STEP 5 - FIX: before/after code, minimal change

STEP 6 - PREVENTION: pytest test, type hint, linting rule

## Success Criteria

A well-executed debug session passes all of these. Use as a self-check before presenting the fix.

### Completeness

- [ ] Error is classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line from the traceback
- [ ] A concrete before/after code fix is provided - no vague suggestions
- [ ] A prevention step is included (pytest test, type hint, or linting rule)

### Correctness

- [ ] The fix addresses the root cause, not the symptom
- [ ] Confidence level is stated (HIGH / MEDIUM / LOW) - LOW lists what additional info would help
- [ ] The fix is minimal - no unrelated refactoring
- [ ] Async/sync mixing is addressed at the architectural level - not just patched with `asyncio.run()`

### Staff-Level Signal

- [ ] The "why" is explained - a developer understands how to avoid this class of bug
- [ ] For Celery issues, retry config and idempotency are addressed alongside the immediate fix
- [ ] For SQLAlchemy connection issues, pool configuration is checked, not just the query

## After This Skill

If the output needed significant adjustment - root cause was wrong, async/sync mixing was patched instead of fixed, or the wrong framework's patterns were applied - run `/task-skill-feedback` to log what changed and why.
