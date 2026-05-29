---
name: task-python-implement
description: "End-to-end Python feature implementation for FastAPI or Django: migrations, models, services, endpoints, schemas, Celery tasks, pytest tests."
agent: python-architect
metadata:
  category: backend
  tags: [python, fastapi, django, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. Follow its contract; skip GATHER (and DESIGN when `plan.md` is present). Never edit spec artifacts; surface conflicts as proposed amendments.

# Implement Python Feature

## When to Use

End-to-end Python feature work: migration + model + service + endpoint + schema + tests in one pass for FastAPI or Django.

Not for: single-file edits (edit directly), bugfixes (`task-python-debug`), frontend.

## Rules

- Detect FastAPI vs Django before generating code
- Pydantic v2 schemas (FastAPI) or DRF serializers (Django) for all responses; never return raw ORM objects
- `async def` on FastAPI endpoints; type hints on every signature
- Celery `.delay()` dispatched **after** transaction commit, never inside it
- Transactions: FastAPI = `Depends(get_db)` per request; Django = `@transaction.atomic()`
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - DETECT FRAMEWORK

Use skill: `stack-detect`. Confirm FastAPI vs Django from `pyproject.toml` / `requirements.txt`; identify ORM, test layout, Celery presence.

### STEP 2 - GATHER

Ask before writing code:

1. Feature description and primary use case
2. Entities, fields, relationships, constraints
3. External integrations (payment APIs, email, third-party services)
4. Background jobs (async processing, notifications, scheduled tasks)
5. Authentication / authorization
6. Status transitions (e.g., `pending -> processing -> completed`)

Ask targeted clarifying questions for any gap. Do not guess.

### STEP 3 - DESIGN (APPROVAL GATE)

FastAPI: Use skill: `python-fastapi-patterns` for endpoints/DI; `python-sqlalchemy-patterns` for ORM/session.
Django: Use skill: `python-django-patterns` for ViewSet/serializer design.
Background jobs: Use skill: `python-celery-patterns`.
Async-heavy: Use skill: `python-async-patterns`.

Present a file tree:

```
# FastAPI example
app/
  models/order.py          # SQLAlchemy model
  schemas/order.py         # Pydantic request/response schemas
  repositories/order.py    # Repository pattern
  services/order.py        # Business logic
  api/v1/routes/orders.py  # Endpoints
  tasks/order.py           # Celery tasks (if needed)
  tests/
    test_orders_api.py     # Endpoint tests
    test_order_service.py  # Service unit tests
    test_order_tasks.py    # Celery task tests (if needed)
migrations/versions/xxx_add_orders.py
```

Wait for approval before generating code.

### STEP 4 - DATABASE

Use skill: `python-migration-safety`. Index foreign keys and frequently-filtered columns; for list endpoints, index columns supporting the default sort order.

### STEP 5 - MODELS

SQLAlchemy 2.0 (`Mapped[]`, `mapped_column`) or Django models. Include:

- Type annotations on all fields
- Relationships with explicit loading strategy
- DB-level constraints (unique, check, not-null)
- `TextChoices` (Django) or string enum (FastAPI) for status fields

### STEP 6 - SERVICES

Business logic layer.

```python
# CORRECT: dispatch after commit
async def create_order(self, order_in: OrderCreate) -> Order:
    order = Order(**order_in.model_dump())
    self._session.add(order)
    await self._session.flush()  # get order.id
    await self._session.commit()
    process_order.delay(order.id)  # after commit - worker will find the row
    return order
```

External service calls: `httpx.AsyncClient` with timeout; classify errors (timeout -> 503, 404 -> not-found, 5xx -> retry). Never use `requests` in async context.

### STEP 7 - ENDPOINTS

FastAPI routes or Django views. Map domain errors:

| Domain Error | HTTP |
|---|---|
| Validation | 422 |
| Not found | 404 |
| Conflict (duplicate) | 409 |
| Unauthorized | 401 |
| Forbidden | 403 |
| External timeout | 503 |

List endpoints paginated (offset/limit or cursor); include filtering on common fields.

### STEP 8 - SCHEMAS

Pydantic v2 (FastAPI) or DRF serializers (Django).

- Separate Create/Update/Response schemas per resource
- `ConfigDict(from_attributes=True)` for ORM -> Pydantic conversion
- Nested schemas for child resources

### STEP 9 - TESTS

Use skill: `python-testing-patterns`. Generate:

- Endpoint tests (happy path + error case per status code)
- Service unit tests (business logic, edge cases)
- Celery task tests (if applicable)
- Factory classes for test data

### STEP 10 - VALIDATE

Run `pytest`, `ruff check`, `mypy` (or `pyright`). Fix failures before reporting done.

## Output Format

```markdown
## Files Generated
[grouped by layer: models, schemas, services, endpoints, tasks, tests, migrations]

## Endpoints
| Method | Path | Request | Response | Status |
| ... |

## Celery Tasks (if any)
| Task | Queue | Trigger | Retry |
| ... |

## Tests
[X] tests passing - [list test files and count per file]

## Migration
[file names + what they create: tables, indexes, constraints]
```

## Self-Check

- [ ] Framework detected; requirements gathered; design approved before code
- [ ] All layers generated: migration, model, service, endpoint/view, schema, tests
- [ ] Pydantic / DRF schemas everywhere; no raw ORM objects in responses
- [ ] `async def` on FastAPI endpoints; type hints on every signature
- [ ] Celery tasks dispatched after commit; transactions scoped correctly
- [ ] External calls timeout-wrapped; `httpx.AsyncClient` in async context
- [ ] pytest, ruff, mypy/pyright all pass; list endpoints paginated; output template filled

## Avoid

- Generating code before design approval
- Bare string fields for status without enum / `TextChoices`
- Mixing data migration into the schema migration revision
