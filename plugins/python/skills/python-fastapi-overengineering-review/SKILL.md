---
name: python-fastapi-overengineering-review
description: FastAPI necessity review - Pydantic validators duplicating SQLAlchemy/DB, defensive None on typed values, single-impl Protocols, BaseService bloat.
metadata:
  category: backend
  tags: [python, fastapi, pydantic, sqlalchemy, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Use only when the detected framework is FastAPI. For Django/DRF, use `python-django-overengineering-review`.

## When to Use

- Reviewing a FastAPI diff that adds Pydantic validators, defensive `None` guards, service classes, `Protocol`s, or new abstractions
- Phase D of `task-python-review` when FastAPI is detected: catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint that makes the code redundant: FK name, `nullable=False` column, unique index, SQLAlchemy `Mapped[T]` non-Optional type, Pydantic field constraint, Python type annotation, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present: extra SELECT in a hot path, bare `except` / `except Exception` defeating the global exception handler, sync I/O hidden in `async def` via broad except, or `Protocol` / `ABC` + single concrete subclass forcing two-file refactors. Cite the cost in the `Cost:` field.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. Skip it. Classic cases: Pydantic validation on a router DTO (FastAPI returns 422 with field errors); defense in depth across multiple write paths (HTTP + Celery + management command); `Protocol` with a planned second implementer or a `pytest` substitution requirement.

## Patterns

### Category 1: Redundant validation vs SQLAlchemy / DB constraints

The FastAPI validation stack: **type annotation → Pydantic `Field` constraint → SQLAlchemy `Mapped[T]` (non-`| None` ⇒ NOT NULL) → DB schema**. Pydantic v2 enforces type-based nullability at the request boundary (returns 422 on null/missing required). Net-new validators are redundant when the type and the DB already enforce the same rule.

#### `model_validator` re-checking a `Field(...)` constraint

```python
# Bad - Field(min_length=1) already enforces this; the validator runs the same check
class CreateOrderRequest(BaseModel):
    items: list[OrderItem] = Field(..., min_length=1)

    @model_validator(mode="after")
    def items_present(self):
        if not self.items:
            raise ValueError("items required")
        return self

# Good - keep the type-going-beyond constraints (gt=0, min_length=1); drop the validator
class CreateOrderRequest(BaseModel):
    items: list[OrderItem] = Field(..., min_length=1)
```

`Field(default=None)` on a `T | None` field is also redundant - `| None` already permits None and Pydantic defaults it.

#### Manual presence check after a validated request

```python
# Bad - FastAPI returned 422 if customer_id was missing; Field(gt=0) rejected 0/negative
@router.post("/orders")
async def create(req: CreateOrderRequest, db: AsyncSession = Depends(get_db)):
    if not req.customer_id:
        raise HTTPException(422, "customer_id required")
    ...
```

#### Manual unique-check before `INSERT`

`[High]` - races (two concurrent requests both pass the SELECT) and adds a query per write; the unique index decides anyway.

```python
# Bad
existing = await db.scalar(select(User).where(User.email == req.email))
if existing:
    raise HTTPException(409, "email taken")
db.add(User(email=req.email))
await db.commit()

# Good - the unique index `ix_users_email` is authoritative; translate at the catch site
db.add(User(email=req.email))
try:
    await db.commit()
except IntegrityError as e:
    raise DuplicateEmailError() from e
```

### Category 2: Defensive code for impossible states

Python type annotations, Pydantic binding, and SQLAlchemy's `scalar_one()` signal absence by raising or by returning a typed result. Re-checking what one already proved is dead code; broad `except` can hide regressions and break async cancellation.

#### `if x is None` after `scalar_one()`

`scalar_one()` raises `NoResultFound`; the `None` branch is unreachable.

```python
# Bad
order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one()
if order is None:                        # scalar_one() raises; this never fires
    raise HTTPException(404, "order not found")

# Good - use scalar_one_or_none when None is a legitimate result
order = (await db.execute(select(Order).where(Order.id == order_id))).scalar_one_or_none()
if order is None:
    raise HTTPException(404, "order not found")
```

#### Defensive checks on typed values

```python
# Bad - status is str non-Optional; the type proves it's present
if order.status:
    process(order.status)

# Bad - getattr with a default hides typos on a typed attribute
customer_id = getattr(order, "customer_id", None)

# Good
process(order.status)
customer_id = order.customer_id
```

Truthiness checks paper over the absence question and silently treat falsy-but-valid values (`0`, `""`, `[]`) as absent. `getattr(..., default)` is legitimate at duck-typed boundaries (HTTP responses, untyped dicts) - flag only on typed dataclass / Pydantic / ORM attributes.

#### `bare except` / `except Exception` swallowing real bugs

`[High]`. Bare `except` catches `KeyboardInterrupt` and `SystemExit`. `except Exception` masks `TypeError`, `AttributeError`, `asyncio.CancelledError`. In a router, it additionally defeats the global exception handler, turning typed errors into opaque 500s.

```python
# Bad
try:
    return await service.fulfill(order_id)
except Exception as e:
    logger.error("fulfillment failed", exc_info=e)
    return {"error": "something went wrong"}

# Good - name the failures the call can raise; let the rest reach the global handler
try:
    return await service.fulfill(order_id)
except InsufficientStockError as e:
    raise HTTPException(409, str(e))
except PaymentDeclinedError as e:
    raise HTTPException(402, str(e))
```

**Never** catch `asyncio.CancelledError` without re-raising - it breaks structured cancellation.

### Category 3: Premature abstraction

#### Single-impl `Protocol` / `ABC` / wrapper classes

`[High]` when the abstraction forces refactors to touch two files for no behavioral reason.

```python
# Bad - one Protocol, one implementer; or a class wrapping a single function
class OrderRepository(Protocol):
    async def find(self, order_id: int) -> Order | None: ...

class SqlAlchemyOrderRepository:
    def __init__(self, db: AsyncSession): self.db = db
    async def find(self, order_id: int) -> Order | None:
        return await self.db.scalar(select(Order).where(Order.id == order_id))

# Good - a module-level function until a second implementer or test fake is needed
async def get_order(db: AsyncSession, order_id: int) -> Order | None:
    return await db.scalar(select(Order).where(Order.id == order_id))
```

Python's function-first culture favors modules over classes. Use a class when state spans methods, when polymorphism is needed, or when a `pytest` substitution requires a structural type. `BaseRepository[T]` / `BaseService[T]` for two children fall into the same anti-pattern - inline until 3+ consumers share genuine cross-cutting behavior.

#### Custom `Result[T]` where exceptions or `T | None` suffice

```python
# Bad - hand-rolled Result wraps a one-line read
@dataclass
class Result(Generic[T]):
    value: T | None
    error: str | None

async def find_order(db: AsyncSession, order_id: int) -> Result[Order]:
    order = await db.scalar(select(Order).where(Order.id == order_id))
    return Result(value=order, error=None if order else "not found")

# Good - the absence is already in the type system
async def find_order(db: AsyncSession, order_id: int) -> Order | None:
    return await db.scalar(select(Order).where(Order.id == order_id))
```

Keep `Result[T]` only when callers branch on multiple distinct failure modes carrying data beyond a string.

#### Speculative `BaseSettings` keys / redundant schema chains

```python
# Bad - audit and tracing_tag are declared and validated, never read
class Settings(BaseSettings):
    gateway_url: str
    audit: bool = False             # never read in the codebase
    tracing_tag: str | None = None  # never read in the codebase

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

Flag speculative settings only after a repo-wide search confirms zero read sites.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `model_validator` re-checking `Field(min_length=1)`}
- Redundant because: {FK name | `nullable=False` column | unique index | non-Optional type | Pydantic rule | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | bare except hiding async cancellation} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging Pydantic validators on router DTOs - that layer owns user-facing error messages
- Flagging `Field(..., gt=0)` / `min_length` / regex constraints - those go beyond the type and are legitimate
- Recommending removal of a unique-check without confirming a unique index exists
- Flagging `Protocol` / `ABC` before checking for a test fake or a planned second implementer
- Flagging `getattr(obj, "x", None)` on values from external sources - the dynamic-typing escape hatch is legitimate at boundaries
- Confusing "duplicated" with "defense in depth" when multiple write paths bypass the DTO (HTTP + Celery + management command)
- Recommending removal of any `try/except` that catches `asyncio.CancelledError` and re-raises - that pattern is correct
