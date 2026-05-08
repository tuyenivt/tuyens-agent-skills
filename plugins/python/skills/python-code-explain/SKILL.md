---
name: python-code-explain
description: Python / FastAPI / Django framework signals for code explanation - sync vs async boundaries, GIL implications, decorator stacking, dependency injection, ORM session lifetime, dataclass / pydantic models, and import-time side effects. Used by task-code-explain to explain Python code with stack-aware gotchas.
metadata:
  category: backend
  tags: [explanation, code-understanding, python, fastapi, django, asyncio]
user-invocable: false
---

# Python Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Python (FastAPI primary, Django secondary).

## When to Use

- A workflow needs Python-specific signals: sync vs async boundaries, GIL behavior, decorator order, framework lifecycle (FastAPI dependencies, Django middleware/signals), ORM session/transaction scope.
- The target code uses `async def`, decorators, FastAPI `Depends`, Django models, SQLAlchemy sessions, or Pydantic models.

## Rules

- Identify whether the function is `def` or `async def` first. Mixing them is the most common Python web bug source.
- For FastAPI: trace the dependency graph (`Depends(...)` chain) before describing what the endpoint does. Dependencies execute in graph order and can short-circuit via `HTTPException`.
- For Django: identify the request lifecycle hooks involved (middleware order, signal handlers, model save/pre_save/post_save).
- Surface ORM session lifetime - SQLAlchemy session, Django ORM connection, or async equivalents - because lazy loading and `DetachedInstanceError`-class bugs depend on it.
- Identify import-time side effects: module-level code runs once at import; common bugs are config loaded too early, circular imports, or DB connections opened at import time.

## Patterns

### Sync vs Async

| Construct                              | Behavior                                                                                            | What to flag                                                                                                                                          |
| -------------------------------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `def endpoint(...)` in FastAPI         | Runs in a threadpool (`anyio`); does not block the event loop                                       | Sync DB calls (psycopg2, sync SQLAlchemy) here are fine                                                                                                |
| `async def endpoint(...)` in FastAPI   | Runs on the event loop                                                                              | Sync I/O (requests, sync DB drivers, file reads) blocks the entire event loop and stalls all concurrent requests                                      |
| `await foo()` inside `async def`       | Suspends the coroutine; event loop runs other tasks                                                 | Forgetting `await` silently returns the coroutine object instead of executing it; common with mocks                                                   |
| `asyncio.create_task(coro)`            | Schedules a coroutine without awaiting; returns `Task`                                              | Reference must be retained (otherwise GC may cancel); exceptions in tasks are silent until `await` or task done                                       |
| `asyncio.gather(*coros)`               | Runs concurrently, awaits all                                                                       | Default behavior: first exception cancels remaining and raises immediately. `return_exceptions=True` collects them                                    |
| Django views (default)                 | Sync; runs in WSGI worker                                                                           | Async views (Django 4.1+) require ASGI server; ORM is sync-only - use `sync_to_async` to call from async                                              |
| Celery / RQ tasks                      | Run in worker process, separate from web server                                                     | Web request context (request, user, session) is not available in tasks; pass IDs and re-fetch                                                         |

**GIL note:** Threads in CPython are limited by the GIL for CPU-bound work; use `multiprocessing` or native extensions. I/O-bound parallelism via threads or `asyncio` is fine.

### Decorator Stacking

Decorators apply bottom-up at definition time. The function signature seen by callers is the outermost wrapper's signature.

```python
@router.get("/")           # 3rd: registers route; sees the result of @auth_required
@auth_required             # 2nd: wraps with auth check
@cache(ttl=60)             # 1st: wraps the original function
async def handler():
    ...
```

Common gotchas:

- Decorator order matters: `@auth_required @cache` (auth runs first, cache second) vs `@cache @auth_required` (cache returns before auth runs - cache poisoning risk).
- Decorators that don't `functools.wraps` lose introspection (name, docstring, type hints, signature). FastAPI's dependency resolution depends on accurate signatures - lost signature breaks injection.
- Class-based decorators with `__call__` cannot be applied to bound methods cleanly without `descriptor` protocol.

### FastAPI Dependency Injection

- `Depends(callable)` resolves at request time. The callable can itself have `Depends` parameters - dependency tree.
- Sub-dependencies are cached per request by default (`use_cache=True`). Pass `use_cache=False` to re-evaluate.
- Yield dependencies (`yield`-form generators) provide setup + teardown:
  ```python
  async def get_db():
      async with SessionLocal() as db:
          try:
              yield db
              await db.commit()       # commit on success
          except Exception:
              await db.rollback()     # rollback on any unhandled exception
              raise
  ```
  Code after `yield` runs after response is sent. The teardown order is **reverse** of resolution - last dependency to enter is first to teardown. This matters when one dependency's teardown reads from another (a metrics dependency reading the DB session has to be resolved _after_ the session and torn down _before_ it).
- `BackgroundTasks` runs **after** the response is sent. Errors in background tasks do not affect the response - log them. Important: the DB session yielded by `Depends(get_db)` is **already closed** by the time the BackgroundTask runs (yield-style teardown finished when the response was sent), so a BackgroundTask that touches `db` will fail. Pass IDs and open a new session inside the task instead.

### Django Lifecycle and Signals

- Middleware runs in order for requests, reverse for responses. Order in `MIDDLEWARE` setting matters.
- Signals (`pre_save`, `post_save`, `pre_delete`, `post_delete`, `m2m_changed`, etc.) fire synchronously inside the same transaction. Long-running signal handlers stretch the transaction.
- `bulk_create` / `bulk_update` / `update()` / `delete()` (queryset method) **bypass `save()` and signals**. Use this knowledge when the user expects signals to fire.
- Custom `save()` overrides require explicit `super().save(*args, **kwargs)`; missing this is a silent bug.

### ORM Session and Transaction Scope

**SQLAlchemy:**

- `Session` is a unit-of-work. Objects loaded inside one session become detached after `session.close()`.
- `DetachedInstanceError` when accessing lazy-loaded relationships after session close - usually a sign the session was scoped wrong.
- `Session.commit()` flushes pending changes and ends the transaction. Subsequent access to expired objects re-fetches.
- Async sessions (`AsyncSession`): all DB calls must use `await`; lazy loading is **not supported** on `AsyncSession` - use `selectinload`/`joinedload` eagerly. `async_sessionmaker(expire_on_commit=False)` is the **safe default** - flipping to `True` causes `MissingGreenlet` on attribute access after commit.
- **Celery dispatch inside an open transaction is a bug.** `await session.flush()` does not make the row visible to other connections; `await session.commit()` does. If the code is `await session.flush(); task.delay(order.id); await session.commit()`, the worker can pick the task up before the commit and see `Order.DoesNotExist`. Dispatch _after_ `await session.commit()`, or use a transactional outbox. (Same fix shape as Django `transaction.on_commit(lambda: task.delay(...))`.)

**Django ORM:**

- Querysets are lazy: building a queryset issues no SQL until iteration, slicing, or evaluation (`bool(qs)`, `len(qs)`, `list(qs)`).
- N+1 patterns: looping over a queryset accessing a `ForeignKey` issues one query per row. Use `select_related` (one-to-one, FK) or `prefetch_related` (M2M, reverse FK).
- `transaction.atomic()` blocks: nested with `using='default'` use savepoints; failure rolls back to the savepoint, not the outer transaction.
- `update_fields=['x']` on `save()` writes only listed columns - useful but bypasses fields not listed even when changed in memory.

### Pydantic Models

- Pydantic v1 vs v2 has API differences (`.dict()` -> `.model_dump()`, `Config` class -> `model_config`); confirm version before describing behavior.
- Validators run in declaration order. `@validator` (v1) / `@field_validator` (v2) for single fields; `@root_validator` / `@model_validator` for cross-field.
- `BaseSettings` (Pydantic Settings package in v2) loads from environment variables at instantiation - common bug is mismatched field name vs env var.
- `model_validate` parses a dict; `model_validate_json` parses JSON bytes. Direct constructor `MyModel(**data)` bypasses validation in v1; v2 always validates.

### Import-Time Side Effects

- Module-level code runs at first import. DB connections, config loads, and side-effecting imports (`__init__.py` doing setup) cause hard-to-debug startup ordering bugs.
- Circular imports: `from a import x` at module top-level when `a` imports `b` and `b` imports `a` - `ImportError: cannot import name`. Solutions: import inside functions, restructure, or use `TYPE_CHECKING` guard for typing-only imports.
- `if __name__ == "__main__":` only runs when the module is executed directly. Important context for understanding scripts.

### Threading, Multiprocessing, and Forking

- `multiprocessing` defaults to `fork` on Linux (cheap), `spawn` on macOS/Windows (slow, but safer). Forked workers inherit DB connections - share-after-fork is a corruption source. Most ORMs require `engine.dispose()` after fork.
- `gunicorn --workers N --preload` forks before initialization runs; with `--preload`, init happens once in parent and workers share copy-on-write memory.
- Threads share state; use `threading.Lock` or `queue.Queue` for safe communication.
- `contextvars.ContextVar` is the asyncio equivalent of `threading.local` - propagates across `await` boundaries within the same task.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Sync vs async definition
- For FastAPI: full dependency tree (`Depends` chain), including yield-based teardown
- For Django: middleware path and any signals fired
- For ORM: session lifecycle and transaction boundary
- Background task / queue boundary if applicable

**Into "Non-Obvious Behavior":**

- Sync I/O blocking the event loop in an `async def`
- Decorator ordering effects
- `bulk_create`/`update()` bypassing `save()` and signals
- Async session lazy-load failures
- N+1 queryset access
- Pydantic v1 vs v2 differences if version is unclear
- Background tasks running post-response (errors invisible; DB session already closed by then)
- Celery `task.delay()` dispatched before commit → worker reads stale state / `DoesNotExist`
- Import-time side effects

**Into "Key Invariants":**

- Async functions must be awaited; calling without `await` returns a coroutine object
- Django ORM is sync; calling from async requires `sync_to_async`
- ORM session must be open for lazy attributes
- FastAPI `Depends` returns are cached per request unless `use_cache=False`

**Into "Change Impact Preview":**

- Switching `def` -> `async def` in FastAPI: every sync call inside must become async or be wrapped in `run_in_threadpool`
- Adding a Django signal handler: fires inside the same transaction as the triggering save - watch transaction length
- Changing a Pydantic model field type/validator: input shape contract changes for every API consumer; v1 and v2 surface validation errors differently
- Removing `@functools.wraps` from a decorator: breaks FastAPI dependency resolution because signatures are lost

## Avoid

- Treating `def` and `async def` as equivalent in FastAPI - they have completely different threading models
- Recommending `asyncio.run` inside an already-running event loop - it raises
- Suggesting `Session.merge()` as a fix for `DetachedInstanceError` without explaining session scope
- Describing Pydantic without confirming v1 vs v2 - APIs differ significantly
- Calling Django signals "async" - they are synchronous and inside the transaction
- Glossing over decorator order when behavior depends on it
