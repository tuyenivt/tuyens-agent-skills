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
- Connection pooling and `MissingGreenlet` debugging

## Rules

- SQLAlchemy 2.0 style: `DeclarativeBase`, `mapped_column`, `Mapped[]`, `select()` - never `Column()` or `session.query()`
- Async sessions: `async_sessionmaker(expire_on_commit=False)` - default `True` causes `MissingGreenlet` after commit
- Load relations eagerly inside session scope; `lazy="raise"` in dev to catch N+1
- `joinedload` on collections requires `.unique()` on the result
- `commit()` at service/request boundary; repositories use `flush()` only
- Never mix sync and async engines

## Patterns

### SQLAlchemy 2.0 Models

```python
from sqlalchemy import String, Numeric, ForeignKey
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase): pass

class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", lazy="raise")

class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    order: Mapped["Order"] = relationship(back_populates="items")
```

### Async Session

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import select

engine = create_async_engine(DATABASE_URL, pool_size=10, max_overflow=5, pool_pre_ping=True, pool_recycle=3600)
async_session = async_sessionmaker(engine, expire_on_commit=False)

# await session.execute(select(...)) for rows; await session.scalars(...) for single column
```

`pool_recycle=3600` prevents PostgreSQL idle timeouts. Pool size = workers x tasks-per-worker.

### N+1 Prevention

- `selectinload(Order.items)` - separate `IN` query, default for collections, safe with `LIMIT`
- `joinedload(Order.customer)` - LEFT JOIN, for single-valued FK/one-to-one
- `lazy="raise"` on relationships catches accidental lazy loads in dev

```python
from sqlalchemy.orm import selectinload, joinedload

# collections -> selectinload
stmt = select(Order).options(selectinload(Order.items)).where(Order.status == "pending")

# single-valued FK -> joinedload
stmt = select(Order).options(joinedload(Order.customer)).where(Order.id == oid)

# joinedload on a collection requires .unique() to dedupe row explosion
result = await session.execute(select(Order).options(joinedload(Order.items)))
orders = result.unique().scalars().all()
```

### FastAPI Session Dependency

```python
async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback(); raise

DbSession = Annotated[AsyncSession, Depends(get_db)]
```

Commit at the dependency boundary - keeps repositories transaction-agnostic.

### Repository Pattern

```python
class OrderRepository:
    def __init__(self, session: AsyncSession): self._session = session

    async def get_by_id(self, oid: int) -> Order | None:
        return await self._session.get(Order, oid)

    async def list_by_status(self, status: str) -> Sequence[Order]:
        result = await self._session.execute(
            select(Order).options(selectinload(Order.items)).where(Order.status == status))
        return result.scalars().all()

    async def create(self, order: Order) -> Order:
        self._session.add(order); await self._session.flush(); return order
```

Composite PK: `session.get(Model, (pk1, pk2))` - passing a single value silently fails.

### Pagination and Bulk Ops

```python
# Offset pagination with total
base = select(Order).where(Order.status == status)
total = await session.scalar(select(func.count()).select_from(base.subquery()))
result = await session.execute(
    base.options(selectinload(Order.items)).offset(off).limit(lim).order_by(Order.created_at.desc()))

# Bulk insert/update bypass ORM listeners
await session.execute(insert(OrderItem), [{"order_id": oid, "quantity": q} for q in qtys])
await session.execute(update(Order).where(Order.status == "expired").values(status="cancelled"))

# Upsert (async-safe): use insert().on_conflict_do_update() + execute() - not session.add()
```

### MissingGreenlet Debugging

Lazy attribute access after session close raises `MissingGreenlet: greenlet_spawn has not been called`.

```python
# BAD: relationship accessed after session closes
async with async_session() as session:
    order = await session.get(Order, oid)
print(order.items)  # MissingGreenlet

# GOOD: eager-load inside session scope
async with async_session() as session:
    result = await session.execute(
        select(Order).options(selectinload(Order.items)).where(Order.id == oid))
    order = result.scalar_one_or_none()
print(order.items)  # safe
```

`expire_on_commit=False` on `async_sessionmaker` prevents post-commit attribute expiry (another `MissingGreenlet` source).

## Output Format

```
## SQLAlchemy Design

### Models
| Model | Key Fields | Relations | Loading Strategy |
|-------|-----------|-----------|------------------|

### Repository Methods
| Method | Query Type | Eager Loads | Returns |
|--------|-----------|-------------|---------|

### Session Strategy
[Engine config, sessionmaker settings, FastAPI dependency shape]

### Pagination
[Offset or keyset with rationale]
```

## Avoid

- `session.merge()` as upsert - use `insert().on_conflict_do_update()`
- Long-lived sessions across requests
- Unbounded `pool_size`; missing `pool_pre_ping` / `pool_recycle`
- `lazy="dynamic"` in async (returns sync `Query`)
