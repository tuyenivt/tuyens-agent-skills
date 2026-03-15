---
name: python-sqlalchemy-patterns
description: "SQLAlchemy 2.0+ patterns: async sessions, mapped_column, select() style queries, relationships, N+1 prevention (selectinload/joinedload), connection pooling, and repository pattern."
user-invocable: false
---

## 1. SQLALCHEMY 2.0 STYLE (NOT legacy 1.x)

DeclarativeBase with mapped_column (NOT Column).
select() statement style (NOT session.query()).
Mapped[] type annotations on all columns.

```python
from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from decimal import Decimal

class Base(DeclarativeBase):
    pass

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    total: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order")

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column()
    order: Mapped["Order"] = relationship(back_populates="items")
```

## 2. ASYNC SESSION

- create_async_engine + async_sessionmaker
- async with session.begin() for transaction scope
- await session.execute(select(Order).where(...))
- await session.scalars(...) for single-column results

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/db",
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
)
async_session = async_sessionmaker(engine, expire_on_commit=False)

async def get_pending_orders(session: AsyncSession) -> list[Order]:
    result = await session.execute(
        select(Order).where(Order.status == "pending")
    )
    return list(result.scalars().all())
```

## 3. N+1 PREVENTION

- `selectinload(Order.items)` - separate SELECT IN query (default choice for collections)
- `joinedload(Order.customer)` - LEFT JOIN (for single-valued FK/OneToOne relationships)
- `subqueryload` - for complex nested relationships
- `lazy="raise"` on relationships to catch N+1 in development
- **`joinedload` on collections causes row duplication** - always chain `.unique()` when using it

```python
from sqlalchemy.orm import selectinload, joinedload

# Default choice: selectinload for collections
stmt = (
    select(Order)
    .options(selectinload(Order.items))
    .where(Order.status == "pending")
)

# joinedload for single-valued (FK) relationships
stmt = (
    select(Order)
    .options(joinedload(Order.customer))
    .where(Order.id == order_id)
)

# joinedload on collections - MUST use .unique() to deduplicate rows
result = await session.execute(
    select(Order).options(joinedload(Order.items))
)
orders = result.unique().scalars().all()  # .unique() is essential here

# Catch N+1 in development with lazy="raise"
class Order(Base):
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", lazy="raise"
    )
```

## 4. FASTAPI SESSION DEPENDENCY

Wire the async session into FastAPI endpoints via `Depends`:

```python
from typing import Annotated, AsyncGenerator

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

DbSession = Annotated[AsyncSession, Depends(get_db)]

@router.get("/orders/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, db: DbSession):
    repo = OrderRepository(db)
    order = await repo.get_by_id(order_id)
    if not order:
        raise HTTPException(404)
    return order
```

## 5. REPOSITORY PATTERN

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from collections.abc import Sequence

class OrderRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, order_id: int) -> Order | None:
        return await self._session.get(Order, order_id)

    async def list_by_status(self, status: str) -> Sequence[Order]:
        result = await self._session.execute(
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.status == status)
        )
        return result.scalars().all()

    async def create(self, order: Order) -> Order:
        self._session.add(order)
        await self._session.flush()
        return order
```

## 6. PAGINATION AND BULK OPERATIONS

### Offset/Limit Pagination

```python
async def list_orders(
    self, status: str, offset: int = 0, limit: int = 20,
) -> tuple[list[Order], int]:
    base_query = select(Order).where(Order.status == status)
    total = await self._session.scalar(
        select(func.count()).select_from(base_query.subquery())
    )
    result = await self._session.execute(
        base_query.options(selectinload(Order.items))
        .offset(offset).limit(limit).order_by(Order.created_at.desc())
    )
    return list(result.scalars().all()), total
```

### Bulk Operations

```python
from sqlalchemy import insert, update

# Bulk insert (bypasses ORM, much faster for large batches)
await session.execute(
    insert(OrderItem),
    [{"order_id": order_id, "product_name": name, "quantity": qty} for name, qty in items],
)

# Bulk update
await session.execute(
    update(Order).where(Order.status == "expired").values(status="cancelled")
)
```

## 7. CONNECTION POOLING

- pool_size: based on workers x tasks per worker
- max_overflow: burst capacity
- pool_pre_ping=True: detect stale connections
- pool_recycle=3600: prevent PostgreSQL idle connection timeout

```python
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,          # base connections
    max_overflow=5,        # burst capacity
    pool_pre_ping=True,    # detect stale connections
    pool_recycle=3600,     # recycle after 1 hour
)
```

## 8. ASYNC SESSION SAFETY AND MISSINGGREENLETERROR

The `MissingGreenlet` error occurs when SQLAlchemy attempts a lazy load (attribute access that triggers a SELECT) in an async context after the session has been closed:

```python
# BAD: accessing relationship after session closes triggers MissingGreenlet
async def get_order_with_items(order_id: int) -> Order:
    async with async_session() as session:
        order = await session.get(Order, order_id)
    # session closed here
    print(order.items)  # MissingGreenlet: greenlet_spawn has not been called
```

Fix: eagerly load all relationships you need inside the session scope:

```python
# GOOD: load relationships before session closes
async def get_order_with_items(order_id: int) -> Order:
    async with async_session() as session:
        result = await session.execute(
            select(Order)
            .options(selectinload(Order.items))  # load eagerly
            .where(Order.id == order_id)
        )
        return result.scalar_one_or_none()
        # items already loaded - safe to access after session closes
```

Set `expire_on_commit=False` on `async_sessionmaker` to prevent attribute expiry after commit (another source of `MissingGreenlet`):

```python
async_session = async_sessionmaker(engine, expire_on_commit=False)
```

## 9. ANTI-PATTERNS

- ❌ `session.query()` (1.x style - use `select()`)
- ❌ `Column()` (use `mapped_column()`)
- ❌ Accessing unloaded relationships after session closes (MissingGreenlet error)
- ❌ `expire_on_commit=True` (default) in async sessions - causes attribute access errors post-commit
- ❌ Long-lived sessions (create per request, close after)
- ❌ Mixing sync and async engines
- ❌ `joinedload` on collections without `.unique()` (duplicate rows in result)
- ❌ Calling `session.commit()` inside repository methods (leaks transaction control - commit at service layer)
- ❌ `session.merge()` as a general-purpose upsert (it's not - use `insert().on_conflict_do_update()`)
