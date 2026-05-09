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

Ask for: full traceback, the source file where the error originates, framework (FastAPI or Django), and what the user expected to happen. If a traceback is provided, identify the first application-code frame (skip library frames) and read that file.

**If partial input**: If the user provides only a description without a traceback, search the codebase for the relevant file/function and ask clarifying questions. If only an error message is given (no traceback), check logs and match against the classification table below before asking for more context.

**If "no error, just wrong behavior"** (Celery double-execution, scheduled job not firing, request returns success but DB row missing, request returns 200 but body is wrong shape): there is no traceback to classify. Reframe the question as _which boundary lost the contract_ - dispatcher → broker → worker (Celery), commit → post-commit hook (transaction-scoped side effects), client → server (request schema), serializer → client (response schema). Ask for one diagnostic the user can pull (broker `LRANGE` / RabbitMQ management UI, DB row state, application log around the event timestamp) before guessing.

## STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

### Async / Event Loop Errors

- `MissingGreenlet: greenlet_spawn has not been called` → lazy-loading a relationship after async session closes. Use skill: `python-sqlalchemy-patterns` (section 6 - async session safety).
- `RuntimeError: no running event loop` → calling async code from sync context. Use skill: `python-async-patterns`.
- `TypeError: object X can't be used in 'await' expression` → forgot `async def` or awaiting a non-coroutine.
- `DetachedInstanceError` → accessing expired attributes after session close (sync equivalent of MissingGreenlet).

### SQLAlchemy / Database Errors

- `sqlalchemy.exc.IntegrityError` → constraint violation (unique, FK, NOT NULL). Check the constraint name in the error message to identify which column/table.
- `sqlalchemy.exc.OperationalError` → DB connection issue, pool exhausted. Check `pool_size`, `max_overflow`, connection string. Use skill: `python-sqlalchemy-patterns` (section 5 - connection pooling).
- `sqlalchemy.exc.StaleDataError` → concurrent update conflict, check optimistic locking.

### FastAPI / Pydantic Errors

- `pydantic.ValidationError` → request body/query params don't match schema. Read the error's `.errors()` list - it shows exactly which field failed and why.
- DI errors: `ImportError` or `AttributeError` in a `Depends()` chain → circular import, missing package, or dependency returns None. Prevention: pytest fixture that imports and instantiates all service modules.
- `AttributeError: 'NoneType'` on injected dep → `Depends()` function returns None instead of a value.

### Django Errors

- `AppRegistryNotReady` → accessing models before `django.setup()`; check `INSTALLED_APPS` order and `AppConfig.ready()`.
- `django.core.exceptions.ValidationError` → model-level validation failure.
- `django.db.utils.IntegrityError` → same as SQLAlchemy constraint issues.

### Celery Errors

- `celery.exceptions.Retry` → task retrying, check retry config and the original exception. Use skill: `python-celery-patterns` (section 2 - retry strategy).
- `celery.exceptions.MaxRetriesExceededError` → all retries exhausted, check idempotency and dead letter queue.
- `kombu.exceptions.OperationalError` → broker connection lost (Redis/RabbitMQ down).
- Task hangs silently → check `soft_time_limit` / `time_limit` are set.
- **Task executed twice with the same args, no error, side effect duplicated** (e.g., customer charged twice, email sent twice) → this is **expected delivery behavior** under `acks_late=True`, not an error. Causes: (a) worker crashed / OOM-killed before sending the ack, (b) `visibility_timeout` (Redis broker default 1 hour) elapsed before the task finished and the broker re-delivered, (c) the dispatcher retried `task.delay(...)` because of a transient broker error and produced two messages. **Root fix is idempotency, not "stop the second delivery"** - at-least-once is the contract. Use skill: `python-celery-patterns` (idempotency patterns).
- **Task dispatched but never executes** → likely dispatched inside a DB transaction that hasn't committed, and the worker picked up the row before it was visible (then the task failed with `DoesNotExist` / not-found and the lookup was logged at `INFO`, not surfaced). Wrap with `transaction.on_commit(lambda: task.delay(...))` (Django) or dispatch after `await session.commit()` (FastAPI / async SQLAlchemy).

### Import / Environment Errors

- `ImportError` / `ModuleNotFoundError` → missing dependency, wrong virtualenv, circular import. Check: `pip list | grep <package>`, verify virtualenv is activated.

## STEP 3 - LOCATE

1. Read the traceback top-to-bottom; find the first application-code frame (not library code)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it upstream through function calls, dependency injection, or ORM queries
4. For async errors: check whether the function is `async def` and whether the caller uses `await`

## STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The MissingGreenlet error occurs because `order.items` triggers a lazy load
after the async session has already closed at line 42 of services/order.py.
The relationship was not eagerly loaded in the query at line 38.
```

## STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms.

```python
# BEFORE (triggers MissingGreenlet - lazy load after session closes)
async def get_order(session: AsyncSession, order_id: int) -> Order:
    return await session.get(Order, order_id)
    # accessing order.items later triggers lazy load = MissingGreenlet

# AFTER (eagerly load relationship inside session scope)
async def get_order(session: AsyncSession, order_id: int) -> Order | None:
    result = await session.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    return result.scalar_one_or_none()
```

## STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **pytest test** that exercises the exact code path
- **Type hint** or `lazy="raise"` on relationships to catch N+1/lazy loads in development
- **Linting rule** (ruff/flake8) if applicable

## Avoid

- Do not patch async errors with `asyncio.run()` inside an already-running loop
- Do not add `expire_on_commit=False` without understanding why attributes expire
- Do not switch from async to sync SQLAlchemy as a "quick fix" for MissingGreenlet
- Do not use `lazy="dynamic"` in async SQLAlchemy code (it returns sync Query objects)
- Do not add blanket `try/except Exception: pass` to suppress errors

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

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Async/sync mixing addressed at architectural level - not just patched with `asyncio.run()`
- [ ] Prevention step included (pytest test, type hint, or linting rule)
- [ ] For Celery: retry config and idempotency addressed; for SQLAlchemy: pool config checked
