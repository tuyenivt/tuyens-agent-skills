---
name: python-fastapi-overengineering-review
description: FastAPI necessity review - Pydantic validators duplicating SQLAlchemy/DB, defensive None on typed values, single-impl Protocols, BaseService bloat.
metadata:
  category: backend
  tags: [python, fastapi, pydantic, sqlalchemy, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Use only when the detected `Framework:` is FastAPI; otherwise the deliverable is the single line Output Format gives for the detected framework.

## When to Use

- Reviewing a FastAPI diff that adds Pydantic validators, defensive `None` guards, service classes, `Protocol`s, or new abstractions
- Phase D of `task-python-review` when FastAPI is detected: catching code that is correct, performant, and safe - but does not need to exist. Defects seen on the way (Pydantic v1 leftovers, blocking calls in `async def`, missing pagination) belong to the sibling lenses, never to a necessity finding.

## Rules

- Every finding cites the constraint that makes the code redundant - one `Redundant because:` value from Output Format, named concretely (the FK, the unique index, the `Mapped[T]` type, the single implementer). No citation, no finding.
- Label ladder, applied in order:
  1. The constraint is not visible in the diff or the repo (unique index absent from the models and migrations shown) -> `[Recommend]`, asking the author to confirm it.
  2. The constraint is visible and a measurable cost is present -> `[Must]`, with `Cost:` filled: an extra SELECT per write on a hot path (`extra SELECT per write`); a bare `except` / `except Exception` that defeats the global exception handler or swallows a typed error (`masked exception`); a handler that catches `asyncio.CancelledError` and does not re-raise (`swallowed cancellation`); a `Protocol` / `ABC` / `BaseRepository[T]` / `BaseService[T]` with a single implementer and no test fake or planned second implementer (`two-file refactor`).
  3. Otherwise -> `[Recommend]`.
- "Single implementer" and "no test fake" are confirmed by search (`tests/`, `conftest.py`, `fakes.py`, structural subtypes), never assumed; a fake that exists but no test imports counts as absent and is named in the finding.
- A redundancy with visible justification emits no block: a comment naming the second implementer, a second write path that bypasses the DTO (Celery task, CLI, script), a validator that adds a rule or user-facing message the mirrored constraint lacks.
- `file:line` comes from the diff; for a PR described in prose with no diff on disk, write `file:n/a` and quote the line in `Code:`.

## Patterns

### Category 1: Redundant validation vs SQLAlchemy / DB constraints

Stack: type annotation -> Pydantic `Field` -> SQLAlchemy `Mapped[T]` (non-`| None` => NOT NULL) -> DB. FastAPI returns 422 when Pydantic rejects a null or missing required field at the request boundary; the DB is authoritative.

#### `model_validator` re-checking a `Field(...)` constraint

```python
# Bad - Field(min_length=1) already enforces this
class CreateOrderRequest(BaseModel):
    customer_id: int = Field(gt=0)
    items: list[OrderItem] = Field(min_length=1)

    @model_validator(mode="after")
    def items_present(self):
        if not self.items: raise ValueError("items required")
        return self

# Good - keep the Field constraint; drop the validator
class CreateOrderRequest(BaseModel):
    customer_id: int = Field(gt=0)
    items: list[OrderItem] = Field(min_length=1)
```

`x: T | None` with no default is **required** in Pydantic v2 (null allowed, key mandatory); `Field(default=None)` equals `= None` and is not a redundancy. A validator is a finding only when it re-checks a rule the `Field` or the DB already carries; so is a presence check after binding:

```python
# Bad - FastAPI returned 422 if customer_id was missing; Field(gt=0) rejected 0/negative
async def create(req: CreateOrderRequest):
    if not req.customer_id: raise HTTPException(422, "customer_id required")
```

#### Manual unique-check before `INSERT`

Races and adds a SELECT per write; the unique index decides.

```python
class DuplicateEmailError(Exception): ...  # app-defined
# Bad
if await db.scalar(select(User).where(User.email == req.email)):
    raise HTTPException(409, "email taken")
db.add(User(email=req.email)); await db.commit()

# Good - let the unique index decide; translate only the matching constraint at the catch site
db.add(User(email=req.email))
try: await db.commit()
except IntegrityError as e:
    if "uq_users_email" not in str(e.orig): raise  # asyncpg names the constraint; SQLite does not
    raise DuplicateEmailError() from e
```

### Category 2: Defensive code for impossible states

Python type annotations, Pydantic binding, and SQLAlchemy's `scalar_one()` signal absence by raising or by typed result. Broad `except` hides regressions; bare `except` and `except BaseException` also break async cancellation.

#### `if x is None` after `scalar_one()`

`scalar_one()` raises `NoResultFound`; the `None` branch is unreachable. When a global `NoResultFound` handler already maps to 404, the edit is deleting the check, not switching to `scalar_one_or_none()`.

```python
# Bad
order = (await db.execute(select(Order).where(Order.id == id))).scalar_one()
if order is None: raise HTTPException(404)        # never fires

# Good - scalar_one_or_none when None is a legitimate result and no global handler exists
order = (await db.execute(select(Order).where(Order.id == id))).scalar_one_or_none()
if order is None: raise HTTPException(404)
```

#### Defensive checks on typed values

```python
# Bad - status is str non-Optional; truthiness also drops "" silently
if order.status: process(order.status)
# Bad - getattr with default hides typos on a typed attribute
customer_id = getattr(order, "customer_id", None)

# Good
process(order.status)
customer_id = order.customer_id
```

`getattr(..., default)` is legitimate at duck-typed boundaries (HTTP responses, untyped dicts); flag only on typed dataclass / Pydantic / ORM attributes.

#### `bare except` / `except Exception` swallowing real bugs

Category 2, `Redundant because: exception propagation`, `Cost: masked exception`, labelled per the ladder. Bare `except` catches `KeyboardInterrupt`, `SystemExit` and `asyncio.CancelledError` (all `BaseException`); `except Exception` does not catch `CancelledError` but masks `TypeError`, `AttributeError` and every domain error, and defeats the global exception handler in routers.

```python
# Bad
try: return await service.fulfill(order_id)
except Exception as e:
    logger.error("fulfillment failed", exc_info=e)
    return {"error": "something went wrong"}

# Good - name the failures; let the rest reach the global handler
try: return await service.fulfill(order_id)
except InsufficientStockError as e: raise HTTPException(409, str(e))
except PaymentDeclinedError as e: raise HTTPException(402, str(e))
```

A handler that catches `asyncio.CancelledError` (directly, bare, or via `BaseException`) and returns instead of re-raising is ladder step 2: `[Must]`, `Redundant because: exception propagation`, `Cost: swallowed cancellation`.

### Category 3: Premature abstraction

#### Single-impl `Protocol` / `ABC` / wrapper classes

```python
# Bad - one Protocol, one implementer, no fake
class OrderRepository(Protocol):
    async def find(self, id: int) -> Order | None: ...
class SqlAlchemyOrderRepository:
    def __init__(self, db: AsyncSession): self.db = db
    async def find(self, id: int) -> Order | None:
        return await self.db.scalar(select(Order).where(Order.id == id))

# Good - module-level function until a second impl or test fake is needed
async def get_order(db: AsyncSession, id: int) -> Order | None:
    return await db.scalar(select(Order).where(Order.id == id))
```

Use a class when state spans methods, polymorphism is needed, or a `pytest` substitution requires a structural type. `BaseRepository[T]` / `BaseService[T]` with one child is the same finding - inline until 3+ consumers share real cross-cutting behaviour. `Redundant because: single implementer`; once the search in Rules confirms no test fake or planned second implementer, ladder step 2 gives `[Must]` with `Cost: two-file refactor`.

#### Custom `Result[T]` where exceptions or `T | None` suffice

```python
# Bad - hand-rolled Result wraps a one-line read
T = TypeVar("T")
@dataclass
class Result(Generic[T]):
    value: T | None; error: str | None
async def find_order(db, id) -> Result[Order]:
    o = await db.scalar(select(Order).where(Order.id == id))
    return Result(value=o, error=None if o else "not found")

# Good - absence is already in the type system
async def find_order(db, id) -> Order | None:
    return await db.scalar(select(Order).where(Order.id == id))
```

Keep `Result[T]` only when callers branch on multiple distinct failure modes carrying data beyond a string; otherwise cite `Redundant because: exception propagation` - raised exceptions and `T | None` already carry the failure.

#### Speculative `BaseSettings` keys / redundant schema chains

```python
# Bad - audit is declared and validated, never read
class Settings(BaseSettings):
    gateway_url: str
    audit: bool = False

# Bad - Entity -> ServiceDTO -> ResponseSchema, three classes with the same fields
class OrderEntityDTO(BaseModel): ...
class OrderServiceDTO(BaseModel): ...
class OrderResponseSchema(BaseModel): ...

# Good - one response schema; map ORM rows via from_attributes
class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    total: Decimal
```

Flag speculative settings only after a repo-wide search confirms zero read sites (`Redundant because: zero read sites`); same-field class chains are `Redundant because: duplicate schema`.

## Output Format

Blocks join the consuming workflow's unified output ordered `[Must]` first; invoked standalone, the same ordered blocks are the whole deliverable. A redundancy with visible justification emits no block. When the detected framework is Django or DRF, the whole deliverable is one line, `Handed off to python-django-overengineering-review`; for any other non-FastAPI framework it is `Not applicable - not a FastAPI project`. No blocks and no `No <category> findings.` lines follow either.

```
### [Must | Recommend] {file:line | file:n/a}

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `model_validator` re-checking `Field(min_length=1)`}
- Redundant because: {FK name | `nullable=False` column | unique index | non-Optional type | Pydantic rule | framework guarantee | single implementer | zero read sites | duplicate schema | exception propagation}
- Cost: {extra SELECT per write | masked exception | swallowed cancellation | two-file refactor} {only for [Must]}
- Recommendation: {concrete edit}
- Justified when: {the legitimate reason that would keep it} {omit the line when none applies}
```

After the blocks, one line per category with no findings: `No <category> findings.` - so the consuming workflow knows the check ran.

## Avoid

- Flagging `Field(..., gt=0)` / `min_length` / regex - those go beyond the type
