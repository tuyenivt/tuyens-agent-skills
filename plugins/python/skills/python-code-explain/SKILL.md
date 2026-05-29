---
name: python-code-explain
description: "Python / FastAPI / Django explain signals: sync vs async, GIL, decorators, DI, ORM session lifetime, Pydantic, import-time side effects."
metadata:
  category: backend
  tags: [explanation, code-understanding, python, fastapi, django, asyncio]
user-invocable: false
---

# Python Code Explain (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-code-explain` for Python (FastAPI primary, Django secondary).

## When to Use

Workflow needs Python-specific signals: sync vs async boundaries, GIL, decorator order, FastAPI `Depends`, Django lifecycle/signals, ORM session and transaction scope, Pydantic, import-time side effects.

## Rules

- Identify `def` vs `async def` first - mixing is the top FastAPI bug source.
- FastAPI: trace the `Depends(...)` graph before describing the endpoint.
- Django: name the request lifecycle hooks (middleware order, signals, `save()` overrides).
- Surface ORM session lifetime - lazy loads and `DetachedInstanceError` depend on it.
- Flag import-time side effects: module-level code runs once at import.

## Patterns

### Sync vs Async

| Construct                            | Behavior                                         | Flag                                                                          |
| ------------------------------------ | ------------------------------------------------ | ----------------------------------------------------------------------------- |
| `def` endpoint in FastAPI            | Runs in threadpool (`anyio`)                     | Sync DB drivers OK here                                                       |
| `async def` endpoint in FastAPI      | Runs on event loop                               | Sync I/O blocks every concurrent request                                      |
| `await foo()`                        | Suspends coroutine                               | Missing `await` returns coroutine object (common with mocks)                  |
| `asyncio.gather(*coros)`             | Concurrent, awaits all                           | First exception cancels rest; `return_exceptions=True` collects               |
| Django views                         | Sync by default                                  | Async views need ASGI; ORM is sync - use `sync_to_async`                      |

**GIL:** Threads serialize CPU-bound work; use `multiprocessing` or native ext. I/O via threads or asyncio is fine.

### Decorator Stacking

Bottom-up at definition; caller sees outermost signature.

```python
@router.get("/")     # 3rd: registers route
@auth_required       # 2nd: wraps with auth
@cache(ttl=60)       # 1st: wraps original
async def handler(): ...
```

- Order matters: `@cache @auth_required` caches *before* auth runs - cache poisoning.
- Missing `functools.wraps` strips the signature; FastAPI's `Depends` resolution breaks.

### FastAPI Dependency Injection

- `Depends(callable)` resolves at request time; sub-deps cached per request (`use_cache=False` to opt out).
- Yield deps run teardown in **reverse** of resolution order.
- `BackgroundTasks` run **after** response; the `Depends(get_db)` session is **already closed** - pass IDs, open a new session.

```python
async def get_db():
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            raise
```

### Django Lifecycle and Signals

- Middleware: forward order on request, reverse on response.
- Signals (`pre_save`/`post_save`/...) fire **synchronously inside the same transaction**.
- `bulk_create` / `bulk_update` / queryset `update()` / `delete()` **bypass `save()` and signals**.
- Custom `save()` needs explicit `super().save(*args, **kwargs)`.

### ORM Session and Transaction Scope

**SQLAlchemy:**

- `Session` is a unit-of-work; objects detach after `close()` -> `DetachedInstanceError` on lazy attrs.
- `AsyncSession`: no lazy loading - use `selectinload`/`joinedload`. `async_sessionmaker(expire_on_commit=False)` is the safe default.
- Celery dispatch before commit is a bug: `flush()` does not publish; worker sees `DoesNotExist`. Dispatch after `commit()` or use outbox.

```python
# BAD: worker may run before commit
await session.flush(); task.delay(order.id); await session.commit()
```

**Django ORM:**

- Querysets are lazy; SQL fires on iteration/slice/`bool`/`len`/`list`.
- N+1: loop + FK access. Use `select_related` (FK/O2O) or `prefetch_related` (M2M/reverse FK).
- Nested `transaction.atomic()` uses savepoints; inner failure rolls back only the savepoint.
- `transaction.on_commit(lambda: task.delay(...))` is the Celery-after-commit pattern.

### Pydantic

- Confirm v1 vs v2 before describing API (`.dict()` -> `.model_dump()`, `Config` -> `model_config`, `@validator` -> `@field_validator`).
- v1 constructor bypasses validation; v2 always validates.
- `BaseSettings` reads env at instantiation - mismatched field name vs env var is the common bug.

### Import-Time Side Effects

- Module-level code (DB connections, config loads, side-effecting `__init__.py`) runs once at first import.
- Circular import: `from a import x` when `a` and `b` import each other. Fix: function-local import, restructure, or `TYPE_CHECKING` guard.

### Threading / Multiprocessing

- `multiprocessing`: `fork` on Linux, `spawn` on macOS/Windows. Forked workers inherit DB connections - call `engine.dispose()` after fork.
- `gunicorn --preload` initializes in parent; workers share copy-on-write memory.
- `contextvars.ContextVar` propagates across `await` within a task - asyncio's `threading.local`.

## Output Format

Inject into `task-code-explain`:

- **Flow Context**: sync vs async; FastAPI `Depends` tree (with yield teardown); Django middleware + signals; ORM session lifecycle and transaction boundary; background task / queue boundary.
- **Non-Obvious Behavior**: sync I/O on event loop; decorator order; `bulk_create`/`update()` bypass signals; async session lazy-load failure; queryset N+1; Pydantic v1 vs v2; `BackgroundTasks` post-response with closed session; Celery dispatch before commit; import-time side effects.
- **Key Invariants**: coroutines must be awaited; Django ORM is sync; ORM session must be open for lazy attrs; `Depends` cached per request unless `use_cache=False`.
- **Change Impact**: `def` -> `async def` ripples through every sync call; new Django signal stretches the triggering transaction; Pydantic field/validator changes the API contract; removing `functools.wraps` breaks FastAPI DI.

## Avoid

- Recommending `asyncio.run` inside a running loop.
- Suggesting `Session.merge()` for `DetachedInstanceError` without addressing session scope.
- Calling Django signals async - they are sync and in-transaction.
