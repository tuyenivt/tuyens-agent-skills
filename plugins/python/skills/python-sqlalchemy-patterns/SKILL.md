---
name: python-sqlalchemy-patterns
description: "SQLAlchemy 2.0 async patterns: DeclarativeBase, mapped_column, select(), N+1 prevention (selectinload/joinedload), pooling, repository."
metadata:
  category: backend
  tags: [python, sqlalchemy, async, orm, n-plus-one, repository]
user-invocable: false
---

# SQLAlchemy Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing SQLAlchemy 2.0 models, relations, async sessions
- Queries needing N+1 prevention, pagination, or bulk ops
- FastAPI session dependency and repository pattern wiring
- Connection pooling and `MissingGreenlet` / `DetachedInstanceError` debugging

## Rules

- SQLAlchemy 2.0 style: `DeclarativeBase`, `mapped_column`, `Mapped[]`, `select()` - never `Column()` or `session.query()`
- Async sessions: `async_sessionmaker(expire_on_commit=False)` - the default expires attributes on commit and the next access raises `MissingGreenlet`
- Load relations eagerly inside session scope; `lazy="raise"` on every relationship so each load is explicit (`raiseload("*")` does the same for one statement)
- `joinedload` on collections requires `.unique()`
- Services commit before returning; `get_db` only rolls back on exception and closes; repositories `flush()` only
- One `AsyncSession` is **not** concurrency-safe - never `asyncio.gather` queries on one session, never share one across requests or processes (web -> Celery worker)
- Never mix sync and async engines

## Patterns

### SQLAlchemy 2.0 Models

```python
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass

class TenantScoped:                                                 # every tenant-owned table, children included
    tenant_id: Mapped[int] = mapped_column(index=True)

class Order(TenantScoped, Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    customer: Mapped["Customer"] = relationship(lazy="raise")      # Customer / Product: ordinary models, omitted
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", lazy="raise")

class OrderItem(TenantScoped, Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int]
    order: Mapped["Order"] = relationship(back_populates="items", lazy="raise")
    product: Mapped["Product"] = relationship(lazy="raise")

class StockItem(Base):
    __tablename__ = "stock_items"
    __table_args__ = (UniqueConstraint("warehouse_id", "sku", name="uq_stock_warehouse_sku"),)  # upsert target
    id: Mapped[int] = mapped_column(primary_key=True)
    warehouse_id: Mapped[int]; sku: Mapped[str] = mapped_column(String(64)); quantity: Mapped[int] = mapped_column(default=0)
```

### Async Session

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=5, pool_pre_ping=True, pool_recycle=3600)
async_session = async_sessionmaker(engine, expire_on_commit=False)
# session.scalars(select(Order)) yields the first column of each row
```

`pool_recycle` retires connections before a proxy, NAT, or a configured `idle_session_timeout` drops them (PostgreSQL never times out idle sessions by default). `pool_size` + `max_overflow` is **per process**; peak = `N_processes x (pool_size + max_overflow)`, kept under `max_connections` minus a reserve for migrations and one surge replica (4 uvicorn workers x (10+5) = 60 against 100). Celery prefork: `NullPool` per worker process, budgeted separately.

### N+1 Prevention

```python
from sqlalchemy.orm import joinedload, selectinload

stmt = select(Order).options(selectinload(Order.items))            # collections: separate IN query, safe with LIMIT
stmt = select(Order).options(joinedload(Order.customer))           # single-valued FK / one-to-one: LEFT JOIN
orders = (await session.execute(select(Order).options(joinedload(Order.items)))).unique().scalars().all()
stmt = select(Order).options(selectinload(Order.items).selectinload(OrderItem.product))  # nested: one IN per level per 500 parents
```

### FastAPI Session Dependency

```python
from collections.abc import AsyncGenerator
from typing import Annotated
from fastapi import Depends, Request

async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.state.async_session() as session:       # lifespan state; closes on exit
        session.info["tenant_id"] = request.state.tenant_id       # from auth middleware
        try:
            yield session
        except Exception:
            await session.rollback(); raise

DbSession = Annotated[AsyncSession, Depends(get_db)]
```

The service commits before returning; never commit after `yield`: on FastAPI 0.118+ post-`yield` code runs after the response, so a failed commit cannot change the 2xx already sent (`Depends(get_db, scope="function")`, 0.121+, restores the old order).

### Repository Pattern

```python
class OrderRepository:
    def __init__(self, session: AsyncSession): self._session = session

    async def get_by_id(self, oid: int) -> Order | None:
        return await self._session.get(Order, oid)   # identity map; select() for filters or eager loads

    async def create(self, order: Order) -> Order:
        self._session.add(order); await self._session.flush(); return order
```

Composite PK: `session.get(Model, (pk1, pk2))` - a single value raises `InvalidRequestError`. `scalar_one()` raises `NoResultFound` on no row; `scalar_one_or_none()` returns `None`.

### Pagination and Bulk Ops

```python
from sqlalchemy import and_, func, insert, or_, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

# Offset pagination skips/duplicates under concurrent inserts
total = await session.scalar(select(func.count()).select_from(Order))
rows = (await session.execute(select(Order).order_by(Order.created_at.desc()).offset(off).limit(lim))).scalars().all()

# Keyset pagination - stable under concurrent writes; cursor (created_at, id) is a total order
stmt = select(Order).order_by(Order.created_at.desc(), Order.id.desc()).limit(lim)
if cursor:                                       # cursor = (last_created_at, last_id)
    c_ts, c_id = cursor
    stmt = stmt.where(or_(Order.created_at < c_ts, and_(Order.created_at == c_ts, Order.id < c_id)))
rows = (await session.execute(stmt)).scalars().all()
next_cursor = (rows[-1].created_at, rows[-1].id) if len(rows) == lim else None
# needs Index("ix_orders_created_id", Order.created_at.desc(), Order.id.desc()); send next_cursor as base64(f"{created_at.isoformat()}|{id}")

# Bulk insert/update bypass ORM listeners; batch large updates by re-selecting a bounded id set until none match
await session.execute(insert(OrderItem), [{"tenant_id": session.info["tenant_id"], "order_id": oid, "product_id": pid, "quantity": q} for pid, q in lines])
while ids := (await session.scalars(select(Order.id).where(Order.status == "expired").limit(5000))).all():
    await session.execute(update(Order).where(Order.id.in_(ids)).values(status="cancelled")
                          .execution_options(synchronize_session=False))
    await session.commit()                       # maintenance job (script or service method) commits per batch; request code leaves commit to the service

# Upsert: on_conflict_do_update(), never session.merge(); index_elements must match a unique constraint (uq_stock_warehouse_sku) or PostgreSQL rejects it
stmt = pg_insert(StockItem).values(warehouse_id=wid, sku=sku, quantity=qty)
await session.execute(stmt.on_conflict_do_update(
    index_elements=["warehouse_id", "sku"], set_={"quantity": stmt.excluded.quantity}))
```

Tenant scoping: every tenant-owned table inherits `TenantScoped` (above). Enforce it once per session, not per query: a `do_orm_execute` listener on `AsyncSession.sync_session_class` adds `with_loader_criteria(TenantScoped, lambda cls: cls.tenant_id == tid, include_aliases=True)` to every select when `tid = session.info.get("tenant_id")` is set (`get_db` sets it; admin jobs leave it unset) - this also covers eager-loaded relations.

### MissingGreenlet and DetachedInstanceError

Lazy access **inside** an open async session raises `MissingGreenlet: greenlet_spawn has not been called` (the sync lazy-loader cannot await); **after** the session closes it raises `DetachedInstanceError`; with `lazy="raise"` either case raises `InvalidRequestError: ... not available due to lazy='raise'`.

```python
# BAD: nothing eager-loaded the relation
async with async_session() as session:
    order = await session.get(Order, oid)
    print(order.items)      # MissingGreenlet (InvalidRequestError with lazy="raise")

# GOOD: eager-load inside session scope; attributes stay readable after close (expire_on_commit=False keeps them past a commit)
async with async_session() as session:
    order = (await session.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == oid))).scalar_one_or_none()
print(order.items)
```

## Output Format

When authoring, emit this block plus the code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it. A section the task does not touch reads `n/a` in place of its table or text.

```
## SQLAlchemy Design

### Models
| Model | Key Fields | Relations | Loading Strategy |
|-------|-----------|-----------|------------------|

### Repository Methods
| Method | Query Type | Eager Loads | Returns |
|--------|-----------|-------------|---------|

### Session Strategy
[Engine config per process type (API, Celery), sessionmaker settings, dependency shape, commit site | n/a]

### Pagination
[Offset or keyset with rationale | n/a]
```

## Avoid

- `session.merge()` as upsert - use `pg_insert(...).on_conflict_do_update()`
- Long-lived sessions across requests
- Unbounded `pool_size`; missing `pool_pre_ping` / `pool_recycle`
- `lazy="dynamic"` in async (returns sync `Query`)
