---
name: python-async-patterns
description: "Python async/await patterns: event loop management, async context managers, asyncio.gather, avoiding event loop blocking, sync-to-async bridges, and common async pitfalls."
user-invocable: false
---

## 1. ASYNC FUNDAMENTALS

- async def for I/O-bound operations (DB, HTTP, file)
- await for every async call - never forget
- asyncio.gather() for concurrent I/O: await asyncio.gather(fetch_a(), fetch_b())
- asyncio.create_task() for fire-and-forget within request scope (with care)

```python
import asyncio
import httpx

async def fetch_order_with_details(order_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        order, items = await asyncio.gather(
            client.get(f"/api/orders/{order_id}"),
            client.get(f"/api/orders/{order_id}/items"),
        )
    return {"order": order.json(), "items": items.json()}
```

## 2. NEVER BLOCK THE EVENT LOOP

| Blocking (wrong)         | Async (correct)            |
| ------------------------ | -------------------------- |
| `time.sleep()`           | `asyncio.sleep()`          |
| `requests.get()`         | `httpx.AsyncClient.get()`  |
| `open()` for large files | `aiofiles.open()`          |
| Sync DB calls            | async SQLAlchemy / asyncpg |

If unavoidable sync code: `loop.run_in_executor(None, sync_func)`

```python
import asyncio
from functools import partial

async def call_legacy_sync_lib(data: dict) -> str:
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        None, partial(legacy_sync_function, data)
    )
    return result
```

## 3. ASYNC CONTEXT MANAGERS

Always use `async with` for resources (sessions, connections, clients).
Implement `__aenter__` / `__aexit__` for custom async resources.

```python
async with httpx.AsyncClient() as client:
    response = await client.get(url)

async with async_session() as session:
    result = await session.execute(select(Order))
```

```python
class AsyncDatabaseConnection:
    async def __aenter__(self):
        self.conn = await asyncpg.connect(DATABASE_URL)
        return self.conn

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.conn.close()
```

## 4. ERROR HANDLING IN ASYNC

- try/except works normally in async functions
- `asyncio.gather(return_exceptions=True)` to collect all errors without cancelling siblings
- `asyncio.timeout()` (Python 3.11+) for per-operation timeouts
- `TaskGroup` (Python 3.11+) for structured concurrency with `except*` for error handling

### Per-Task Timeout with Partial Results

When calling multiple external APIs, wrap each call individually so one slow API doesn't block the others:

```python
async def fetch_with_timeout(client: httpx.AsyncClient, url: str, timeout: float = 5.0) -> dict | None:
    try:
        async with asyncio.timeout(timeout):
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except (asyncio.TimeoutError, httpx.HTTPError) as e:
        logger.warning(f"Failed to fetch {url}: {e}")
        return None  # partial failure - return None instead of crashing

async def fetch_all_apis(order_id: int) -> dict:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            fetch_with_timeout(client, f"https://api-a.com/orders/{order_id}"),
            fetch_with_timeout(client, f"https://api-b.com/orders/{order_id}"),
            fetch_with_timeout(client, f"https://api-c.com/orders/{order_id}"),
        )
    return {
        "api_a": results[0],  # None if failed
        "api_b": results[1],
        "api_c": results[2],
    }
```

### TaskGroup with ExceptionGroup Handling (Python 3.11+)

```python
async with asyncio.TaskGroup() as tg:
    task_a = tg.create_task(operation_a())
    task_b = tg.create_task(operation_b())
# Both tasks guaranteed complete here; any exception cancels all and raises ExceptionGroup

# Handle ExceptionGroup from TaskGroup failures
try:
    async with asyncio.TaskGroup() as tg:
        tg.create_task(risky_operation_a())
        tg.create_task(risky_operation_b())
except* ValueError as eg:
    for exc in eg.exceptions:
        logger.error(f"ValueError: {exc}")
except* ConnectionError as eg:
    for exc in eg.exceptions:
        logger.error(f"Connection failed: {exc}")
```

## 5. CONCURRENCY CONTROL

Use `asyncio.Semaphore` to limit concurrent operations (rate limiting, connection limits):

```python
# Limit to 5 concurrent API calls (respects external rate limits)
sem = asyncio.Semaphore(5)

async def rate_limited_fetch(client: httpx.AsyncClient, url: str) -> dict:
    async with sem:
        response = await client.get(url)
        return response.json()

async def fetch_all(urls: list[str]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        return await asyncio.gather(
            *(rate_limited_fetch(client, url) for url in urls)
        )
```

## 6. ANTI-PATTERNS

- ❌ Blocking calls in async functions (kills throughput)
- ❌ Creating event loops manually (FastAPI/uvicorn manages this)
- ❌ `asyncio.run()` inside an already-running loop
- ❌ Fire-and-forget tasks without error handling
- ❌ Mixing sync and async ORMs in the same codebase
- ❌ `asyncio.gather()` without `return_exceptions=True` when partial failure tolerance is needed
- ❌ Using `TaskGroup` without handling `ExceptionGroup` / `except*`
- ❌ Creating a new `httpx.AsyncClient` per request instead of reusing one (connection pool waste)
