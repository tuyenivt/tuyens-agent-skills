---
name: task-python-implement
description: "End-to-end Python feature implementation for FastAPI or Django: migrations, models, services, endpoints, schemas, Celery tasks, pytest tests."
agent: python-engineer
metadata:
  category: backend
  tags: [python, fastapi, django, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

# Implement Python Feature

## When to Use

Migration, model, service, endpoint, schema, tests in one pass for FastAPI or Django.

Not for: single-file edits, bugfixes, frontend.

## Workflow

### STEP 1 - BEHAVIORAL PRINCIPLES

Use skill: `behavioral-principles`.

### STEP 2 - DETECT FRAMEWORK

Use skill: `stack-detect`. `Framework` FastAPI or Django selects the branch; `unknown` or another framework (Flask): name it and ask which branch applies; no answer -> stop (FastAPI and Django only). Record the Python version (`Language`, else `requires-python`) and the pinned framework version, `unknown` when absent. Read what the block lacks: test layout, Celery in the manifest, lint / type tools. Disagreeing manifests: follow the one CI installs; name the conflict.

### STEP 3 - GATHER

Ask only about gaps that change the deliverable - entities, fields, constraints; auth / tenancy model and the tenant-id source; status transitions; outbound integrations, inbound webhooks; background jobs; money or irreversible effects. State other defaults inline ("Assuming X since Y") and proceed.

### STEP 4 - DESIGN (APPROVAL GATE)

FastAPI: Use skill: `python-fastapi-patterns`; Use skill: `python-sqlalchemy-patterns`. Django: Use skill: `python-django-patterns`. Background jobs: Use skill: `python-celery-patterns`. Async-heavy: Use skill: `python-async-patterns`.

Emit each loaded atomic's block (`## FastAPI Architecture`, `## SQLAlchemy Design`, Django `Pattern:` blocks, `## Celery Design`, `## Async Architecture`) and a file tree:

```
app/models/order.py                 # Django: <app>/models.py
app/schemas/order.py                # Django: <app>/serializers.py
app/repositories/order.py           # flush() only; Django: model managers
app/services/order.py               # commits; Django: <app>/services.py
app/api/v1/routes/orders.py         # Django: <app>/views.py + urls.py
app/tasks/order.py                  # Django: <app>/tasks.py
alembic/versions/xxx_add_orders.py  # Django: <app>/migrations/000N_*.py
tests/unit/test_order_service.py
tests/integration/test_orders_api.py
```

Wait for approval; a waiver yields design and code in one turn, recorded under `## Assumptions`.

### STEP 5 - DATABASE

Use skill: `python-migration-safety`; emit its `## Migration Plan`, then the files. Backfills get their own revision.

### STEP 6 - MODELS

SQLAlchemy 2.0 (`Mapped[]`, `mapped_column`) or Django models: typed fields; explicit relationship loading; DB-level constraints; `TextChoices` (Django) or a string enum for status.

### STEP 7 - SERVICES

The service owns the transaction: `get_db` only rolls back, repositories `flush()`, the service commits, then dispatches Celery via `run_in_threadpool`. Django: `transaction.atomic()` + `on_commit`.

```python
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool
from app.models.order import Order
from app.repositories.order import OrderRepository
from app.schemas.order import OrderCreate
from app.tasks.order import process_order


async def create_order(session: AsyncSession, repo: OrderRepository, order_in: OrderCreate, tenant_id: int) -> Order:
    order = Order(tenant_id=tenant_id)  # + `order_in` fields onto columns (nested items -> OrderItem(tenant_id=tenant_id, ...))
    await repo.create(order)  # add + flush
    await session.commit()
    await run_in_threadpool(process_order.delay, order.id)  # after commit, off the loop
    return order
```

```python
from django.db import transaction
from orders.models import Order
from orders.tasks import process_order


def create_order(**data) -> Order:
    with transaction.atomic():
        order = Order.objects.create(**data)
        transaction.on_commit(lambda: process_order.delay(order.id))
    return order
```

Outbound: lifespan-scoped `httpx.AsyncClient` with explicit `httpx.Timeout` on async FastAPI (never `requests`); `requests` / `httpx.Client` with a timeout on sync paths; timeout -> 503, 404 -> not-found, 5xx -> retry. Inbound webhooks: HMAC over the raw body (`hmac.compare_digest`, stale timestamps rejected: `python-security-patterns` Webhook Auth) and the provider event id deduped by a unique constraint (`python-fastapi-patterns` Webhook Receivers; Django alike).

### STEP 8 - ENDPOINTS

FastAPI routes (`async def`, `response_model` on every endpoint) or DRF views (explicit `fields` on every serializer). Domain errors:

| Domain error | FastAPI | DRF |
| --- | --- | --- |
| Validation | 422 (`RequestValidationError`) | 400 (`ValidationError`, `UniqueValidator` included) |
| Not found | 404 | 404 |
| Conflict (state race, duplicate key) | 409 | 409 (`APIException` subclass) |
| Unauthenticated | 401 (`OAuth2PasswordBearer`; every scheme on 0.122+); 403 (`HTTPBearer` / `APIKeyHeader` below 0.122) | 401 (token / JWT); 403 (`SessionAuthentication`) |
| Forbidden | 403 | 403 |
| External timeout | 503 | 503 |

List endpoints paginated and filterable. Any endpoint not fully public: Use skill: `python-security-patterns` for auth / authz wiring (`Depends`, `permission_classes`) and mass-assignment-safe schemas (its blocks cover Step 9).

### STEP 9 - SCHEMAS

Pydantic v2 or DRF serializers: separate Create / Update / Response per resource; `ConfigDict(from_attributes=True)` on response models from ORM rows.

### STEP 10 - TESTS

Use skill: `python-testing-patterns`; emit its `## Test Plan`, then tests under root `tests/unit` and `tests/integration`: endpoints (one case per status above), service logic, Celery tasks when present. A suite conflicting with the atomic's Rules (SQLite conftest, `unittest.TestCase`) stays untouched; new tests follow the Rules and the Test Plan gains `### Suite Migration`.

### STEP 11 - VALIDATE

Run `pytest` and the manifest's lint / type tools; fix failures first. A missing tool or dead runtime reports `not run - <reason>`.

## Output Format

Brace annotations are never emitted.

```markdown
## Python Feature: <name>

- **Stack:** Python <version | unknown>
- **Framework:** FastAPI <version | unknown> | Django <version | unknown>

## Assumptions

- [each Step 3 default; the approval waiver; `None`]

## Design

[approved Step 4 blocks, `## Celery Design` excepted, plus Step 8 security `Pattern:` blocks; `(amended: <why>)` where changed]

## Files Generated

[grouped by layer; edited files marked `(modified)`]

## Endpoints

| Method | Path | Request | Response | Status | Auth |
| ------ | ---- | ------- | -------- | ------ | ---- |

## Celery Design   {when tasks exist}

[the block]

## Migration Plan

[the block: Schema Changes, Indexes, Deploy Sequence, Rollback Plan]

## Test Plan

[the block{ + `### Suite Migration`}]

## Validation

- pytest: <N> passed | not run - <reason>
- ruff / mypy or pyright: pass | not run - <reason>
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `Framework` settled; layout, Celery, tools read
- [ ] Step 3: deliverable-changing gaps asked; defaults under `## Assumptions`
- [ ] Step 4: blocks + tree emitted; approval or waiver recorded
- [ ] Step 5: `## Migration Plan`; backfill separate
- [ ] Step 6: typed fields, explicit loading, constraints, enum status
- [ ] Step 7: service commits; dispatch after commit, off the loop; timeouts; webhooks signed
- [ ] Step 8: `response_model` / explicit `fields`; correct statuses; pagination; security patterns
- [ ] Step 9: Create / Update / Response; `from_attributes`
- [ ] Step 10: `## Test Plan`; root `tests/`; suite migration
- [ ] Step 11: declared tools run; unrun reported `not run - <reason>`

## Avoid

- Code before approval; an unanswered question is not approval
- `.delay()` inline in `async def`, or before the commit
