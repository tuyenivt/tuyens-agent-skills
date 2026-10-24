---
name: python-async-patterns
description: "Python asyncio patterns: gather, TaskGroup, Semaphore, timeout, run_in_executor, lifespan-scoped clients, event-loop blocking prevention."
metadata:
  category: backend
  tags: [python, async, asyncio, concurrency, event-loop]
user-invocable: false
---

# Python Async Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing `async def` code for FastAPI, async SQLAlchemy, httpx, asyncpg
- Coordinating concurrent I/O (parallel fetches, batched API calls)
- Bridging blocking libraries into an async event loop, or entering async from sync code

## Rules

- `async def` for I/O only; pure-Python CPU work runs in `run_in_executor` with a `ProcessPoolExecutor`, GIL-releasing C work (hashlib, Pillow) in the default thread pool
- `await` every coroutine
- No blocking calls inside `async def` (see the blocking-call catalog)
- One `httpx.AsyncClient`, DB engine, `Semaphore`, and executor per process, created inside the running loop at startup (lifespan) - never at module import, never per request
- `asyncio.gather(..., return_exceptions=True)` when every result is needed; bare `gather` re-raises the first exception and leaves the other tasks running un-awaited
- `TaskGroup` (3.11+) when one failure must cancel the siblings; handle `ExceptionGroup` via `except*`
- `asyncio.timeout()` (3.11+) or `wait_for()` is the end-to-end budget; `httpx.Timeout` caps each phase (connect/read/write/pool) and its read timeout resets per chunk
- `asyncio.Semaphore` caps concurrency on rate- or connection-limited resources; the cap is per process, so divide a global limit by the worker count
- `asyncio.run()` is the entry point from sync code (a Celery task, a CLI); never inside a running loop, which uvicorn owns; each call is a new loop, so the client, `Semaphore` and engine (`NullPool`) are created inside it

## Patterns

### Blocking-Call Catalog

| Blocking (wrong)        | Async (correct)            |
| ----------------------- | -------------------------- |
| `time.sleep()`          | `asyncio.sleep()`          |
| `requests.get()`        | `httpx.AsyncClient.get()`  |
| `open()` on large files | `aiofiles.open()`          |
| Sync DB driver          | async SQLAlchemy / asyncpg |

Unavoidable sync code - pick the executor by workload:

```python
from functools import partial
loop = asyncio.get_running_loop()
# I/O-bound (blocking SDK, file): default thread pool releases the GIL while waiting
result = await loop.run_in_executor(None, partial(legacy_sync_io, data))
# pure-Python CPU work (parsing, per-row transforms): threads stay GIL-serialized - use a process pool
result = await loop.run_in_executor(request.app.state.cpu_pool, partial(legacy_cpu_work, data))  # args/return must pickle
```

Executor threads see no request-context thread-locals - pass data as arguments. Pools multiply: `uvicorn --workers 4` x `max_workers=2` = 8 processes.

### Shared Resources in Lifespan

```python
import asyncio, httpx
from concurrent.futures import ProcessPoolExecutor
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(base_url=settings.VENDOR_URL, timeout=httpx.Timeout(5.0))
    app.state.vendor_sem = asyncio.Semaphore(10)              # per process
    app.state.cpu_pool = ProcessPoolExecutor(max_workers=2)
    yield
    if _background: await asyncio.wait(_background, timeout=10)   # drain _background (Fire-and-Forget Tasks); a timeout must not skip the lines below
    await app.state.http.aclose()
    await asyncio.to_thread(app.state.cpu_pool.shutdown, wait=True)
```

Handlers and services reach these through `request.app.state`.

A module-level `Semaphore` binds to the first loop that contends on it; a second loop (per-function pytest-asyncio loops, repeated `asyncio.run`) raises `RuntimeError: ... is bound to a different event loop`.

### Concurrent Fetch with gather

```python
async def order_with_items(client: httpx.AsyncClient, order_id: int):
    order, items = await asyncio.gather(
        client.get(f"/api/orders/{order_id}"),          # relative paths need base_url on the client
        client.get(f"/api/orders/{order_id}/items"),
    )
```

Use `TaskGroup` when a failure must cancel the siblings; `return_exceptions=True` when every slot must come back.

### Per-Task Timeout with Partial Results

```python
async def fetch_with_timeout(client, url, timeout=5.0):
    try:
        async with asyncio.timeout(timeout):
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except (TimeoutError, httpx.HTTPError) as e:        # asyncio.TimeoutError is TimeoutError on 3.11+
        logger.warning("fetch failed %s: %s", url, e)
        return None

results = await asyncio.gather(*(fetch_with_timeout(client, u) for u in urls))
```

For partial results, put the timeout **inside each task** (above) so every task returns a slot - do **not** wrap `asyncio.timeout` around the outer `gather`: on expiry it cancels the gather and discards already-completed results.

### TaskGroup (3.11+)

```python
try:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(operation_a())
        tg.create_task(operation_b())
except* ValueError as eg:
    for exc in eg.exceptions:
        logger.error("ValueError: %s", exc)
except* ConnectionError as eg:
    for exc in eg.exceptions:
        logger.error("connection: %s", exc)
```

Any task failure cancels the group and raises `ExceptionGroup`.

### Fire-and-Forget Tasks

`asyncio.create_task(...)` without a stored reference can be garbage-collected mid-flight and its exception is swallowed until GC:

```python
_background: set[asyncio.Task] = set()

def fire(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)                          # strong ref - GC can kill orphan tasks
    task.add_done_callback(_background.discard)
    task.add_done_callback(lambda t: t.cancelled() or t.exception() and
                           logger.error("background task failed", exc_info=t.exception()))
```

Catch un-awaited coroutines: pytest `-W error::RuntimeWarning -W error::pytest.PytestUnraisableExceptionWarning` (the first flag alone leaves a warning, not a failure); Ruff `RUF006` flags un-stored `create_task`; `ASYNC` rules flag `time.sleep`, `requests` and `open` in `async def`, not DB drivers.

`async for` over a DB cursor holds the connection for the whole iteration - paginate large result sets.

## Output Format

When authoring, emit this block plus the code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it. A primitive the code does not use gets `n/a` in `Example Site`; an audit with no blocking call is the line `No blocking calls found.`

```
## Async Architecture

### Concurrency Primitives
| Pattern | Use Case | Example Site |
|---------|----------|--------------|
| gather(return_exceptions=True) | parallel fetch, every slot needed | {file:line \| n/a} |
| TaskGroup | cancel siblings on first failure | {file:line \| n/a} |
| Semaphore(N) | rate/connection cap, per process | {file:line \| n/a} |
| timeout() per task | per-call budget | {file:line \| n/a} |
| run_in_executor | sync bridge (thread: I/O or GIL-releasing C, process: pure-Python CPU) | {file:line \| n/a} |

### Blocking-Call Audit
[file:line -> blocking call -> async replacement]

### Resource Lifecycle
| Resource | Created at | Scope | Closed at |
|----------|------------|-------|-----------|
```

## Avoid

- Catching `asyncio.CancelledError` without re-raising - breaks structured cancellation
- Mixing sync and async ORM drivers in one codebase
