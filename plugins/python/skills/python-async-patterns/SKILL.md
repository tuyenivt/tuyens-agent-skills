---
name: python-async-patterns
description: "Python async/await patterns: event loop management, async context managers, asyncio.gather, avoiding event loop blocking, sync-to-async bridges, and common async pitfalls."
user-invocable: false
---

## 1. ASYNC FUNDAMENTALS

- async def for I/O-bound operations (DB, HTTP, file)
- await for every async call — never forget
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
- asyncio.gather(return_exceptions=True) to collect all errors
- Timeout: async with asyncio.timeout(5.0): await operation()
- TaskGroup (Python 3.11+) for structured concurrency

```python
# Collect results and errors together
results = await asyncio.gather(
    fetch_order(1),
    fetch_order(2),
    fetch_order(3),
    return_exceptions=True,
)
for result in results:
    if isinstance(result, Exception):
        logger.error(f"Failed: {result}")
```

```python
# Timeout (Python 3.11+)
async with asyncio.timeout(5.0):
    data = await fetch_external_api()
```

```python
# TaskGroup (Python 3.11+) — structured concurrency
async with asyncio.TaskGroup() as tg:
    task_a = tg.create_task(operation_a())
    task_b = tg.create_task(operation_b())
# Both tasks guaranteed complete here; any exception cancels all
```

## 5. ANTI-PATTERNS

- ❌ Blocking calls in async functions (kills throughput)
- ❌ Creating event loops manually (FastAPI/uvicorn manages this)
- ❌ asyncio.run() inside an already-running loop
- ❌ Fire-and-forget tasks without error handling
- ❌ Mixing sync and async ORMs in the same codebase
