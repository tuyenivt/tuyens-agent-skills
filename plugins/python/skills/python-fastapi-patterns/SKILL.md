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
- Wiring DI, Pydantic v2 schemas, routers, exception handlers, pagination
- Reviewing FastAPI code for structural, async, or CORS issues

## Rules

- All endpoint I/O is async; sync DB/HTTP in `async def` blocks the event loop
- `Annotated[T, Depends(...)]` type aliases at module level; never repeat `Depends()` per endpoint
- Yield-dependencies handle commit/rollback; cleanup after `yield` must not raise
- Separate `Create` / `Update` / `Response` Pydantic models per resource; `ConfigDict(from_attributes=True)` for ORM mapping
- One `APIRouter` per domain with `prefix` + `tags`; declare `response_model` on every endpoint
- `lifespan` for startup/shutdown; `@app.on_event` is deprecated
- `CORSMiddleware` with explicit `allow_origins` when `allow_credentials=True` (`["*"]` is rejected at runtime)
- Route functions delegate to services; no business logic in handlers

## Patterns

### Dependency Injection

```python
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
```

Nested deps compose (auth -> session -> pool). In tests, `app.dependency_overrides[get_db]` requires the exact function object - aliased imports silently fail.

### Pydantic v2 Schemas

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator

PositiveAmount = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]

class OrderCreate(BaseModel):
    total: PositiveAmount
    items: list[OrderItemCreate]

    @field_validator("items")
    @classmethod
    def at_least_one_item(cls, v: list) -> list:
        if not v:
            raise ValueError("Order must have at least one item")
        return v

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total: Decimal
    status: str
```

Partial updates: optional fields + `model_dump(exclude_unset=True)` when applying. Use `model_dump()`, never v1 `.dict()`.

### Router Organization

```python
# api/v1/routes/orders.py
router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(order_in: OrderCreate, db: DbSession, user: CurrentUser):
    return await OrderService(OrderRepository(db)).create(order_in, user=user)

# api/v1/router.py
api_router = APIRouter(prefix="/api/v1")
api_router.include_router(orders.router)

# main.py
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
```

### Error Handling

Domain exception + override Pydantic's validation envelope for consistent shape:

```python
class AppException(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 400):
        self.code, self.detail, self.status_code = code, detail, status_code

@app.exception_handler(AppException)
async def app_exception_handler(_req: Request, exc: AppException):
    return JSONResponse(exc.status_code, {"code": exc.code, "detail": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_handler(_req: Request, exc: RequestValidationError):
    return JSONResponse(422, {"code": "VALIDATION_ERROR", "errors": exc.errors()})
```

| Domain Error       | HTTP |
| ------------------ | ---- |
| Validation failure | 422  |
| Unauthorized       | 401  |
| Not found          | 404  |
| Conflict           | 409  |
| Invalid transition | 422  |

### Pagination

```python
class PaginationParams(BaseModel):
    offset: int = Field(0, ge=0)
    limit: int = Field(20, ge=1, le=100)

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int

@router.get("/", response_model=PaginatedResponse[OrderListResponse])
async def list_orders(db: DbSession, p: Annotated[PaginationParams, Query()]):
    total = await db.scalar(select(func.count()).select_from(Order))
    rows = (await db.execute(select(Order).offset(p.offset).limit(p.limit))).scalars().all()
    return PaginatedResponse(items=rows, total=total, offset=p.offset, limit=p.limit)
```

All list endpoints must paginate.

### Middleware

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # explicit list when allow_credentials=True
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def request_id(request: Request, call_next):
    request.state.request_id = str(uuid.uuid4())
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response
```

Prefer `Depends` over middleware for per-route auth.

### Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    app.state.async_session = async_sessionmaker(engine, expire_on_commit=False)
    yield
    await engine.dispose()

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.async_session() as session:
        yield session
```

### Async and Background Tasks

`BackgroundTasks` runs after the response - the request-scoped session is already closed. Pass entity **IDs**, not ORM objects, and open a fresh session inside the task. Use Celery/queue for reliable delivery. `UploadFile` parameters cannot be inside a Pydantic body - pass them as separate `File(...)` args.

## Output Format

```
## FastAPI Architecture

### Middleware Stack
| Order | Middleware         | Purpose                          |
|-------|--------------------|----------------------------------|
| 1     | CORSMiddleware     | CORS (explicit origins)          |
| 2     | request_id         | correlation ID injection         |
| 3     | exception_handlers | centralized error envelope       |

### Router Structure
| Router | Prefix | Tags | Endpoints |
|--------|--------|------|-----------|

### Schemas
| Resource | Create | Update | Response |
|----------|--------|--------|----------|

### Dependency Graph
[Annotated DI chain: session -> auth -> service]
```

## Avoid

- Returning dicts or raw ORM objects instead of Pydantic response models
- Pydantic v1 `.dict()` / `.parse_obj()` calls
- List endpoints without pagination
- Passing ORM objects to `BackgroundTasks` (session already closed)
- Broad `except Exception` in endpoints (defeats the global handler)
