---
name: python-fastapi-patterns
description: "FastAPI async REST patterns: Depends DI, Pydantic v2 schemas, APIRouter, exception handlers, pagination, CORS, lifespan."
metadata:
  category: backend
  tags: [python, fastapi, pydantic, dependency-injection, async, rest-api]
user-invocable: false
---

# FastAPI Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or extending FastAPI async REST applications
- Wiring DI, Pydantic v2 schemas, routers, exception handlers, pagination, API versions
- Reviewing FastAPI code for structural, async, or CORS issues

## Rules

- All endpoint I/O is async; sync DB/HTTP in `async def` blocks the event loop (Celery `.delay()` included: `run_in_threadpool`)
- `Annotated[T, Depends(...)]` type aliases at module level (`app/dependencies.py`); never repeat `Depends()` per endpoint
- Services commit before returning; `get_db` only rolls back on exception and closes - on FastAPI 0.118+ post-`yield` code runs after the response, so a commit there cannot fail the request
- Separate `Create` / `Update` / `Response` Pydantic models per resource; `ConfigDict(from_attributes=True)` for ORM mapping
- One `APIRouter` per domain with `prefix` + `tags`; declare `response_model` on every endpoint, including uploads and webhooks
- `lifespan` for startup/shutdown; `@app.on_event` is deprecated
- `CORSMiddleware` lists `allow_origins` explicitly when `allow_credentials=True` - `["*"]` silently reflects any `Origin` with credentials

## Patterns

### Dependency Injection

```python
from collections.abc import AsyncGenerator
from typing import Annotated
from fastapi import APIRouter, Depends, FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.state.async_session() as session:          # lifespan state; closes on exit
        try:
            yield session
        except Exception:
            await session.rollback(); raise

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
```

`app.dependency_overrides[get_db]` is keyed on the function object: a second `def get_db` or import path silently misses. `Depends(get_db, scope="function")` (0.121+) runs cleanup before the response when a post-`yield` step must fail the request.

### Pydantic v2 Schemas

```python
from decimal import Decimal
from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field

PositiveAmount = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]

class OrderCreate(BaseModel):
    total: PositiveAmount
    items: list[OrderItemCreate] = Field(min_length=1)

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total: Decimal
    status: str
```

Partial updates: optional fields + `model_dump(exclude_unset=True)`.

### Router Organization and Versions

```python
# api/v1/routes/orders.py
router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(order_in: OrderCreate, db: DbSession, user: CurrentUser):
    return await OrderService(OrderRepository(db)).create(order_in, user=user)

# api/v1/router.py
api_router = APIRouter(prefix="/api/v1"); api_router.include_router(orders.router)

# main.py
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
app.mount("/api/v2", v2_app)          # own error envelope = sub-app with own handlers; request.app is v2_app, so shared resources live in lifespan state
```

### Error Handling

One envelope for domain and validation errors:

```python
from fastapi import Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

class AppException(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 400):
        self.code, self.detail, self.status_code = code, detail, status_code

@app.exception_handler(AppException)
async def app_exception_handler(_req: Request, exc: AppException):
    return JSONResponse(status_code=exc.status_code, content={"code": exc.code, "detail": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"code": "VALIDATION_ERROR", "errors": jsonable_encoder(exc.errors())})  # errors() may hold exception objects in ctx (custom validators)
```

| Domain Error | HTTP | Domain Error | HTTP |
| --- | --- | --- | --- |
| Validation failure, invalid transition | 422 | Not found | 404 |
| Unauthorized | 401 | Conflict | 409 |
| Webhook bad signature | 400 | | |

### Pagination

```python
from typing import Generic, TypeVar
from fastapi import Query
from sqlalchemy import func, select
T = TypeVar("T")

class PaginationParams(BaseModel):
    offset: int = Field(0, ge=0); limit: int = Field(20, ge=1, le=100)

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]; total: int; offset: int; limit: int

@router.get("/", response_model=PaginatedResponse[OrderListResponse])
async def list_orders(db: DbSession, p: Annotated[PaginationParams, Query()]):
    total = await db.scalar(select(func.count()).select_from(Order))
    rows = (await db.execute(select(Order).offset(p.offset).limit(p.limit))).scalars().all()
    return PaginatedResponse(items=rows, total=total, offset=p.offset, limit=p.limit)
```

### Middleware

```python
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Correlation id: `@app.middleware("http")` sets `request.state.request_id` and `X-Request-ID`. The last middleware added is outermost; exception handlers run inside the innermost `ExceptionMiddleware`; an `Exception`/500 handler runs in the outermost `ServerErrorMiddleware`, so its response skips user middleware (no CORS headers).

### Lifespan

```python
from contextlib import asynccontextmanager
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(settings.DATABASE_URL, pool_size=settings.DB_POOL_SIZE, max_overflow=settings.DB_MAX_OVERFLOW, pool_pre_ping=True)
    yield {"async_session": async_sessionmaker(engine, expire_on_commit=False)}   # request.state.async_session, in mounted sub-apps too
    await engine.dispose()
```

Lifespan state is the only engine handle; pool sizing per `python-sqlalchemy-patterns`.

### Async and Background Tasks

`BackgroundTasks` runs after the handler returns - after dependency cleanup on 0.115-0.117, before it on 0.118+ - so never hand it the request session or ORM objects: pass entity **IDs** and open a fresh session in the task.

### File Upload with Metadata

A file forces `multipart/form-data`, so metadata goes as form fields too; validate it via a Pydantic model and translate its errors, or the client gets a 500:

```python
from fastapi import File, Form, UploadFile
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

@router.post("/", status_code=202, response_model=JobAccepted)
async def upload(
    file: Annotated[UploadFile, File()],
    project_id: Annotated[int, Form()],          # flat scalars as Form fields
    db: DbSession,                               # no default, so it precedes the defaulted Form field
    tags: Annotated[list[str], Form()] = [],      # repeated form field tags=a&tags=b
):
    try:
        meta = UploadMetadata(project_id=project_id, tags=tags)
    except ValidationError as e:
        raise RequestValidationError(e.errors())  # 422, not 500
    job = await svc.accept(file, meta)            # stream to storage, return a job id
    await run_in_threadpool(process_upload.delay, str(job.id))   # Celery re-reads from storage; UploadFile is closed after the response
    return JobAccepted(job_id=str(job.id), status="accepted")
```

Nested metadata: one `metadata: Annotated[str, Form()]` JSON string, `UploadMetadata.model_validate_json(metadata)` in the same `try`.

### Webhook Receivers

Signature verification needs the **raw bytes** (`await request.body()`), never `request.json()`. Verify in a dependency with `hmac.compare_digest` so the handler only runs on authentic events; failure returns 400 (Stripe and similar providers retry on any non-2xx; 422 is for body validation). Webhooks are at-least-once: persist the provider event id under a unique constraint and short-circuit duplicates inside the same transaction as the handler effect.

## Output Format

When authoring, emit this block plus the code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it. A table the task does not touch reads `n/a`; a middleware or webhook the target state needs is a row even when the code lacks it.

```
## FastAPI Architecture

### Middleware Stack (outermost first; last added = outermost)
| Order | Middleware | Purpose |
|-------|------------|---------|

### Exception Handlers
| Exception | Status | Envelope |
|-----------|--------|----------|

### Router Structure
| Router | Prefix | Tags | Endpoints |
|--------|--------|------|-----------|

### Schemas
| Resource | Create | Update | Response |
|----------|--------|--------|----------|

### Webhooks
| Receiver | Signature dependency | Dedupe key |
|----------|----------------------|------------|

### Dependency Graph
[Annotated DI chain: session -> auth -> service]
```

## Avoid

- Pydantic v1 `.dict()` / `.parse_obj()` calls
- List endpoints without pagination
- Broad `except Exception` in endpoints (defeats the global handler)
