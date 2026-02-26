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

- selectinload(Order.items) — separate SELECT IN query (default choice)
- joinedload(Order.customer) — LEFT JOIN (for single-valued relationships)
- subqueryload — for complex nested relationships
- lazy="raise" on relationships to catch N+1 in development

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

# Catch N+1 in development with lazy="raise"
class Order(Base):
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", lazy="raise"
    )
```

## 4. REPOSITORY PATTERN

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

## 5. CONNECTION POOLING

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

## 6. ANTI-PATTERNS

- ❌ session.query() (1.x style — use select())
- ❌ Column() (use mapped_column())
- ❌ Forgetting to load relationships (causes N+1 or lazy load errors in async)
- ❌ Long-lived sessions (create per request, close after)
- ❌ Mixing sync and async engines
