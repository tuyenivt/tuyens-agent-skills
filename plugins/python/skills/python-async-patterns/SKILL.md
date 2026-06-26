---
name: python-async-patterns
description: "Python asyncio patterns: gather, TaskGroup, Semaphore, timeout, run_in_executor, async context managers, event-loop blocking prevention."
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
- Bridging blocking libraries into an async event loop

## Rules

- `async def` for I/O only; CPU-bound work belongs in `run_in_executor` or a process pool
- `await` every coroutine - never leave one unawaited
- No blocking calls inside `async def` (see Patterns: blocking-call catalog)
- One `httpx.AsyncClient` / DB engine per app, not per request
- `asyncio.gather(..., return_exceptions=True)` when partial failure is acceptable; bare `gather` cancels siblings on first raise
- `TaskGroup` (3.11+) for structured concurrency - must handle `ExceptionGroup` via `except*`
- `asyncio.timeout()` (3.11+) for per-operation budgets; wrap each call when one slow API must not block others
- `asyncio.Semaphore` to cap concurrency against rate-limited or connection-limited resources
- Never call `asyncio.run()` inside a running loop; let the framework (uvicorn/FastAPI) own the loop

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
loop = asyncio.get_running_loop()
# I/O-bound (blocking HTTP SDK, blocking file): default thread pool releases the GIL while waiting
result = await loop.run_in_executor(None, partial(legacy_sync_io, data))
# CPU-bound (image resize, hashing): a thread pool stays GIL-serialized - use a ProcessPoolExecutor
result = await loop.run_in_executor(cpu_pool, partial(legacy_cpu_work, data))  # args/return must pickle
```

Executor threads have no request-context thread-locals (Flask/Django, SQLAlchemy scoped session) - pass data as arguments. Create pools once at startup; never per request.

### Concurrent Fetch with gather

```python
async with httpx.AsyncClient() as client:
    order, items = await asyncio.gather(
        client.get(f"/api/orders/{order_id}"),
        client.get(f"/api/orders/{order_id}/items"),
    )
```

When one task raises, bare `gather` cancels the rest. If those tasks hold resources, guard cleanup with `try/finally` inside the coroutine.

### Per-Task Timeout with Partial Results

```python
async def fetch_with_timeout(client, url, timeout=5.0):
    try:
        async with asyncio.timeout(timeout):
            r = await client.get(url)
            r.raise_for_status()
            return r.json()
    except (asyncio.TimeoutError, httpx.HTTPError) as e:
        logger.warning("fetch failed %s: %s", url, e)
        return None

results = await asyncio.gather(*(fetch_with_timeout(client, u) for u in urls))
```

For partial results, put the timeout **inside each task** (above) so every task returns a slot - do **not** wrap `asyncio.timeout` around the outer `gather`: on expiry it cancels the gather and discards already-completed results. When combining `asyncio.timeout` with `httpx.Timeout`, the stricter wins - use httpx for the per-request cap, the per-task `asyncio.timeout` for the call budget.

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

### Concurrency Limit with Semaphore

```python
sem = asyncio.Semaphore(5)

async def fetch(client, url):
    async with sem:
        return (await client.get(url)).json()
```

### Async Context Managers

Always `async with` for sessions, clients, connections. Custom resources implement `__aenter__` / `__aexit__`:

```python
class AsyncDBConn:
    async def __aenter__(self):
        self.conn = await asyncpg.connect(DATABASE_URL)
        return self.conn
    async def __aexit__(self, *_):
        await self.conn.close()
```

### Fire-and-Forget Tasks

`asyncio.create_task(...)` without keeping a reference can be garbage-collected mid-flight, and its exception is swallowed until GC. Hold a strong reference and surface failures:

```python
_background: set[asyncio.Task] = set()

def fire(coro) -> None:
    task = asyncio.create_task(coro)
    _background.add(task)                          # strong ref - GC can kill orphan tasks
    task.add_done_callback(_background.discard)
    task.add_done_callback(lambda t: t.cancelled() or t.exception() and
                           logger.error("background task failed", exc_info=t.exception()))
```

Catch un-awaited coroutines early: run tests with `-W error::RuntimeWarning` (turns "coroutine was never awaited" into a failure) and `asyncio.run(main(), debug=True)`; Ruff `ASYNC`/`RUF006` flags un-stored `create_task`.

### Async Iteration

`async for` over a DB cursor holds the connection for the whole iteration. For large result sets, paginate explicitly instead of using a server-side cursor.

## Output Format

```
## Async Architecture

### Concurrency Primitives
| Pattern | Use Case | Example Site |
|---------|----------|--------------|
| gather(return_exceptions=True) | parallel fetch, partial OK | <file:line> |
| TaskGroup | structured concurrency | <file:line> |
| Semaphore(N) | rate/connection cap | <file:line> |
| timeout() per task | per-call budget | <file:line> |
| run_in_executor | sync bridge | <file:line> |

### Blocking-Call Audit
[file:line -> blocking call -> async replacement]

### Resource Lifecycle
[shared clients/engines and their scope]
```

## Avoid

- Fire-and-forget `create_task` without error handling or tracking
- Mixing sync and async ORM drivers in one codebase
- Relying on thread-local request context inside `run_in_executor`
- `asyncio.run()` inside a running loop; manually managing event loops
