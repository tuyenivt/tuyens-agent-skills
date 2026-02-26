---
name: task-python-debug
description: "Debug Python application errors. Paste a traceback, log, Celery error, or test failure. Classifies the error, identifies root cause, suggests fix. Works with FastAPI and Django."
agent: python-architect
---

STEP 1 — INTAKE: Python traceback, application log, Celery task error, pytest failure

STEP 2 — CLASSIFY:

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

STEP 3 — LOCATE: read traceback, open source file, trace call chain

STEP 4 — ROOT CAUSE: explain WHY. Confidence: HIGH/MEDIUM/LOW

STEP 5 — FIX: before/after code, minimal change

STEP 6 — PREVENTION: pytest test, type hint, linting rule
