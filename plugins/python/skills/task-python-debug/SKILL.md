---
name: task-python-debug
description: "Debug Python errors: classify tracebacks, find root cause, generate before/after fixes for FastAPI, Django, SQLAlchemy, Celery, async."
agent: python-architect
metadata:
  category: backend
  tags: [python, fastapi, django, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

## STEP 1 - INTAKE

Ask for: full traceback, source file at the first application frame (skip library frames), framework (FastAPI / Django), expected behavior. If a traceback is given, open the first app frame.

**Partial input:** description without traceback - search codebase for the named symbol, ask clarifying questions. Error message only - check logs and try classification table below before asking more.

**"No error, just wrong behavior"** (Celery double-execution, scheduled job not firing, 200 response with missing DB row or wrong body shape): no traceback to classify. Reframe as _which boundary lost the contract_ - dispatcher -> broker -> worker (Celery), commit -> post-commit hook (transaction-scoped side effects), client -> server (request schema), serializer -> client (response schema). Ask for one diagnostic (broker `LRANGE` / RabbitMQ UI, DB row state, log around event timestamp) before guessing.

## STEP 2 - CLASSIFY

Match the error, then load the listed atomic skill.

### Async / Event Loop

- `MissingGreenlet: greenlet_spawn has not been called` - lazy load on a relationship after async session closed. Use skill: `python-sqlalchemy-patterns` (async session safety).
- `RuntimeError: no running event loop` - async called from sync context. Use skill: `python-async-patterns`.
- `TypeError: object X can't be used in 'await' expression` - missing `async def`, or awaiting a non-coroutine.
- `DetachedInstanceError` - expired attribute access after session close (sync equivalent of MissingGreenlet).

### SQLAlchemy / Database

- `IntegrityError` - constraint violation; constraint name identifies column/table.
- `OperationalError` - DB connection / pool exhausted. Check `pool_size`, `max_overflow`, DSN. Use skill: `python-sqlalchemy-patterns` (connection pooling).
- `StaleDataError` - concurrent update conflict; check optimistic locking.

### FastAPI / Pydantic

- `pydantic.ValidationError` - request schema mismatch; read `.errors()` for failing field.
- `Depends()` chain `ImportError` / `AttributeError` - circular import, missing package, or dependency returns `None`. Prevention: pytest fixture that instantiates all service modules.
- `AttributeError: 'NoneType'` on injected dep - `Depends()` function returned `None`.

### Django

- `AppRegistryNotReady` - models accessed before `django.setup()`; check `INSTALLED_APPS` order and `AppConfig.ready()`.
- `django.core.exceptions.ValidationError` - model-level validation failure.
- `django.db.utils.IntegrityError` - same shape as SQLAlchemy constraint errors.

### Celery

- `Retry` - retrying; check retry config and the original exception. Use skill: `python-celery-patterns` (retry strategy).
- `MaxRetriesExceededError` - retries exhausted; check idempotency and DLQ.
- `kombu.exceptions.OperationalError` - broker down (Redis / RabbitMQ).
- Task hangs silently - `soft_time_limit` / `time_limit` not set.
- **Task executed twice, same args, no error, side effect duplicated** (charged twice, email sent twice) - **expected under `acks_late=True`**, not an error. Causes: (a) worker crashed before ack, (b) `visibility_timeout` elapsed (Redis default 1h) and broker re-delivered, (c) dispatcher retried `task.delay(...)` on transient error. **Fix is idempotency, not "stop re-delivery"** - at-least-once is the contract. Use skill: `python-celery-patterns` (idempotency).
- **Task dispatched but never executes** - dispatched inside an uncommitted DB transaction; worker picked the row before it was visible, failed with `DoesNotExist`, logged at `INFO`. Wrap with `transaction.on_commit(lambda: task.delay(...))` (Django) or dispatch after `await session.commit()` (async SQLAlchemy).

### Import / Environment

- `ImportError` / `ModuleNotFoundError` - missing dependency, wrong venv, or circular import. Check `pip list | grep <pkg>` and venv activation.

## STEP 3 - LOCATE

1. Read traceback top-to-bottom; find first application frame (skip library code).
2. Open that file; read the failing function.
3. Trace the data path: where does the problematic value originate? Follow upstream through calls, DI, ORM queries.
4. Async errors: confirm `async def` and `await` at every boundary.

## STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced or obvious), **MEDIUM** (pattern match), **LOW** (multiple candidates).

```
ROOT CAUSE: [HIGH] MissingGreenlet at services/order.py:42 - `order.items`
lazy-loads after the async session closed; relationship was not eagerly
loaded in the query at line 38.
```

## STEP 5 - FIX

Before/after code. Minimal, addresses root cause not symptom.

```python
# BEFORE (MissingGreenlet - lazy load after session closes)
async def get_order(session: AsyncSession, order_id: int) -> Order:
    return await session.get(Order, order_id)
    # order.items accessed later -> lazy load -> MissingGreenlet

# AFTER (eager load inside session scope)
async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    return result.scalar_one_or_none()
```

## STEP 6 - PREVENTION

Add one guard so this class cannot recur:

- pytest test exercising the exact path
- `lazy="raise"` on relationships to surface lazy loads in dev
- Lint rule (ruff / flake8) if applicable

## Output Format

```
## Error Classification
[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)
[Why the error occurs, referencing specific file:line]

## Fix
[Before/after code blocks]

## Prevention
[Test, type hint, or config change to prevent recurrence]
```

## Self-Check

- [ ] STEP 2: error classified before reading code or proposing a fix
- [ ] STEP 4: root cause references file:line; confidence stated
- [ ] STEP 5: minimal before/after fix; addresses root cause
- [ ] STEP 6: prevention guard added (test, type hint, lint, or idempotency)
- [ ] Async/sync mixing addressed architecturally - not patched with `asyncio.run()`
- [ ] Celery: retry + idempotency addressed; SQLAlchemy: pool config checked

## Avoid

- Proposing a fix before classifying
- `asyncio.run()` inside an already-running loop
- `expire_on_commit=False` without understanding attribute expiry
- Switching async -> sync SQLAlchemy as a "quick fix" for MissingGreenlet
- `lazy="dynamic"` in async SQLAlchemy (returns sync Query objects)
- Blanket `try/except Exception: pass` to suppress errors
