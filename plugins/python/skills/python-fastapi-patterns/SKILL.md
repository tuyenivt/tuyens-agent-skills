---
name: python-fastapi-patterns
description: "FastAPI patterns: async endpoints, dependency injection, Pydantic v2 models, router organization, error handling, middleware, lifespan events, and OpenAPI customization."
user-invocable: false
---

## 1. DEPENDENCY INJECTION

Depends() for shared logic (get_db_session, get_current_user).
Nested dependencies (auth depends on session depends on pool).
Yield dependencies for resource cleanup (session commit/rollback).

```python
async def get_db(
    session_factory: AsyncSessionFactory = Depends(get_session_factory),
):
    async with session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

## 2. PYDANTIC v2 MODELS

- Request models with Field validators
- Response models with model_config (from_attributes=True for ORM)
- Separate Create/Update/Response schemas per resource
- ConfigDict(strict=True) for strict type checking
- Use Annotated types for reusable validators

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated

PositiveAmount = Annotated[Decimal, Field(gt=0, max_digits=10, decimal_places=2)]

class OrderCreate(BaseModel):
    total: PositiveAmount
    items: list[OrderItemCreate]

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
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrderService(OrderRepository(db))
    return await service.create(order_in, user=current_user)
```

## 4. ERROR HANDLING

- Custom exception classes inheriting from base AppException
- Exception handlers registered via app.add_exception_handler()
- Consistent error response: {"detail": str, "code": str, "errors": [...]}
- HTTPException for known HTTP errors, custom exceptions for business errors

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
```

## 5. ASYNC PATTERNS

- All DB operations must use async SQLAlchemy or asyncpg
- Never call sync I/O in async endpoints (blocks event loop)
- Use run_in_executor() ONLY as escape hatch for unavoidable sync libs
- Background tasks: BackgroundTasks for fire-and-forget, Celery for reliable

```python
@router.post("/orders/{order_id}/notify")
async def notify_order(
    order_id: int,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    order = await OrderRepository(db).get_by_id(order_id)
    if not order:
        raise OrderNotFoundError(order_id)
    background_tasks.add_task(send_notification_email, order.id)
    return {"status": "notification queued"}
```

## 6. MIDDLEWARE

- CORS via CORSMiddleware
- Request ID injection middleware
- Timing middleware (log request duration)
- Auth middleware vs dependency (prefer Depends for per-route auth)

```python
from fastapi.middleware.cors import CORSMiddleware
import time, uuid

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
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

@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start
    response.headers["X-Process-Time"] = f"{duration:.4f}"
    return response
```

## 7. LIFESPAN EVENTS

```python
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import create_async_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    engine = create_async_engine(settings.DATABASE_URL)
    yield {"engine": engine}
    # shutdown
    await engine.dispose()

app = FastAPI(lifespan=lifespan)
```

## 8. ANTI-PATTERNS

- ❌ Sync database calls in async endpoints
- ❌ Global mutable state (use dependency injection)
- ❌ Returning dicts instead of Pydantic models
- ❌ Catching Exception broadly in endpoints
- ❌ Business logic in route functions (use services)
