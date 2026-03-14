---
name: task-python-debug
description: Debug Python application errors - tracebacks, Celery errors, pytest failures, and unexpected behavior in FastAPI and Django apps. Paste a traceback or describe the unexpected behavior. Not for production incident analysis with blast radius assessment (use task-incident-root-cause for that).
agent: python-architect
metadata:
  category: backend
  tags: [python, fastapi, django, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - INTAKE: Python traceback, application log, Celery task error, pytest failure

STEP 2 - CLASSIFY:

- DI / Dependency errors (FastAPI): `ImportError` or `AttributeError` in a `Depends()` chain → check if service class is imported correctly, no circular imports, virtualenv has the package. For `AttributeError: 'NoneType'` on an injected dep: check `Depends()` returns a value (not None). Prevention: pytest fixture that imports all service modules and instantiates them.
- DI / Dependency errors (Django): `AppRegistryNotReady` or `django.core.exceptions.AppRegistryNotReady` → accessing models before `django.setup()`; check `INSTALLED_APPS`, `AppConfig.ready()` order.
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

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Async/sync mixing addressed at architectural level - not just patched with `asyncio.run()`
- [ ] Prevention step included (pytest test, type hint, or linting rule)
- [ ] For Celery: retry config and idempotency addressed; for SQLAlchemy: pool config checked

> Run `/task-skill-feedback` if output needed significant correction.
