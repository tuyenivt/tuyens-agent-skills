---
name: python-fastapi-patterns
description: "FastAPI patterns for building async REST APIs. Covers Depends-based dependency injection, Pydantic v2 request/response models, router organization, custom exception handlers, pagination, CORS middleware, and lifespan events."
metadata:
  category: backend
  tags: [python, fastapi, pydantic, dependency-injection, async, rest-api]
user-invocable: false
---

## 1. DEPENDENCY INJECTION

Depends() for shared logic (get_db_session, get_current_user).
Nested dependencies (auth depends on session depends on pool).
Yield dependencies for resource cleanup (session commit/rollback).
Use Annotated types to avoid repeating `Depends()` on every endpoint.

```python
from typing import Annotated
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# Reusable annotated dependency - use this type alias in all endpoints
DbSession = Annotated[AsyncSession, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
```

## 2. PYDANTIC v2 MODELS

- Request models with Field validators
- Response models with model_config (from_attributes=True for ORM)
- Separate Create/Update/Response schemas per resource
- Use Annotated types for reusable validators
- `field_validator` and `model_validator` for complex validation

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Annotated

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

class OrderUpdate(BaseModel):
    """Partial update - all fields optional, use exclude_unset=True when applying."""
    total: PositiveAmount | None = None
    status: str | None = None

class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total: Decimal
    status: str
    items: list[OrderItemResponse]
```

## 3. ROUTER ORGANIZATION

- APIRouter per domain in api/v1/routes/
- Tags for OpenAPI grouping
- Prefix chaining: app.include_router(router, prefix="/api/v1")
- Response model declarations on each endpoint

```python
# api/v1/routes/orders.py
router = APIRouter(prefix="/orders", tags=["orders"])

@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(
    order_in: OrderCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    service = OrderService(OrderRepository(db))
    return await service.create(order_in, user=current_user)

# api/v1/router.py - wire all routers
from api.v1.routes import orders, users

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(orders.router)
api_router.include_router(users.router)

# main.py
app = FastAPI(lifespan=lifespan)
app.include_router(api_router)
```

## 4. ERROR HANDLING

Custom exception classes + override Pydantic's default validation error format for consistency.

```python
class AppException(Exception):
    def __init__(self, code: str, detail: str, status_code: int = 400):
        self.code = code
        self.detail = detail
        self.status_code = status_code

class OrderNotFoundError(AppException):
    def __init__(self, order_id: int):
        super().__init__(
            code="ORDER_NOT_FOUND",
            detail=f"Order {order_id} not found",
            status_code=404,
        )

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "code": exc.code},
    )

# Override Pydantic validation error format for consistent API response shape
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "detail": "Validation error",
            "code": "VALIDATION_ERROR",
            "errors": [
                {"field": ".".join(str(loc) for loc in e["loc"]), "message": e["msg"]}
                for e in exc.errors()
            ],
        },
    )
```

## 5. PAGINATION AND FILTERING

All list endpoints must support pagination. Use query parameter dependencies.

```python
from fastapi import Query

class PaginationParams(BaseModel):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=20, ge=1, le=100)

class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int

@router.get("/", response_model=PaginatedResponse[OrderListResponse])
async def list_orders(
    db: DbSession,
    current_user: CurrentUser,
    pagination: Annotated[PaginationParams, Query()],
    status: str | None = None,
):
    query = select(Order).where(Order.user_id == current_user.id)
    if status:
        query = query.where(Order.status == status)

    total = await db.scalar(select(func.count()).select_from(query.subquery()))
    result = await db.execute(
        query.offset(pagination.offset).limit(pagination.limit)
        .options(selectinload(Order.items))
    )
    return PaginatedResponse(
        items=result.scalars().all(),
        total=total,
        offset=pagination.offset,
        limit=pagination.limit,
    )
```

## 6. MIDDLEWARE

- CORS: use explicit origins, not `["*"]` with `allow_credentials=True` (CORS spec violation)
- Request ID injection middleware
- Timing middleware (log request duration)
- Auth middleware vs dependency (prefer Depends for per-route auth)

```python
from fastapi.middleware.cors import CORSMiddleware
import time, uuid

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,  # explicit list, not ["*"] with credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response
```

## 7. LIFESPAN EVENTS

Connect lifespan to DB engine so dependencies can access it via `app.state`.

```python
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    app.state.async_session = async_sessionmaker(engine, expire_on_commit=False)
    yield
    # shutdown
    await engine.dispose()

app = FastAPI(lifespan=lifespan)

# Dependency reads session factory from app state
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## 8. ASYNC PATTERNS

- All DB operations must use async SQLAlchemy or asyncpg
- Never call sync I/O in async endpoints (blocks event loop)
- Use `run_in_executor()` ONLY as escape hatch for unavoidable sync libs
- Background tasks: `BackgroundTasks` for fire-and-forget, Celery for reliable

## 9. EDGE CASES

- **Yield dependency exception handling**: If the code after `yield` in a generator dependency raises, FastAPI catches it but the client still gets the original response. Cleanup logic after `yield` must not raise.
- **Dependency override in tests**: `app.dependency_overrides` requires the exact function object as key - if the dependency is re-imported or aliased, the override silently fails.
- **BackgroundTasks and DB sessions**: Background tasks run after the response is sent and the request-scoped DB session is closed. Pass entity IDs to background tasks, not ORM objects.
- **File upload with Pydantic**: `UploadFile` parameters cannot be part of a Pydantic model body - they must be separate function parameters alongside `File(...)`.

## 10. ANTI-PATTERNS

- ❌ Sync database calls in async endpoints (blocks event loop)
- ❌ `allow_origins=["*"]` with `allow_credentials=True` (CORS spec violation, rejected at runtime)
- ❌ Global mutable state (use dependency injection)
- ❌ Returning dicts instead of Pydantic response models
- ❌ Catching Exception broadly in endpoints
- ❌ Business logic in route functions (extract to services)
- ❌ `@app.on_event("startup")` (deprecated - use lifespan context manager)
- ❌ `model.dict()` (Pydantic v1 - use `model.model_dump()`)
- ❌ List endpoints without pagination
