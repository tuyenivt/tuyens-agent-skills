---
name: task-python-new
description: End-to-end Python feature implementation workflow. Detects FastAPI or Django and generates all layers - migrations, models, services, endpoints, schemas, Celery tasks, and pytest tests. Use for new features requiring multiple coordinated layers. Not for single-file fixes or isolated bug fixes (use task-python-debug for errors).
agent: python-architect
metadata:
  category: backend
  tags: [python, fastapi, django, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for this feature, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. The preamble decides between modes (`no-spec`, `spec-only`, `spec+plan`, `full-spec`); follow its contract - skip GATHER (and DESIGN, when `plan.md` is present) and treat the spec as the source of truth. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface conflicts as proposed amendments.

# Implement Feature

## When to Use

- Implementing a new Python feature end-to-end (migration -> model -> service -> endpoint -> tests)
- Scaffolding a complete CRUD or domain-specific resource with production-ready patterns
- Adding a new domain aggregate requiring REST API, persistence, background tasks, and test coverage
- Any task requiring coordinated generation of multiple FastAPI or Django layers

## Rules

- Detect framework first - FastAPI (primary) or Django (secondary) - before generating any code
- Pydantic v2 schemas (FastAPI) or DRF serializers (Django) for all responses - never return raw ORM objects
- `async def` on all FastAPI endpoints; type hints on all function signatures
- Celery `.delay()` dispatched AFTER DB transaction commits, never inside the transaction
- Transactions: FastAPI = session scoped per request via `Depends(get_db)`; Django = `@transaction.atomic()`
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code

## Implementation

STEP 1 - DETECT FRAMEWORK: Use skill: `stack-detect` to determine FastAPI or Django. Read `pyproject.toml` / `requirements.txt` to confirm.

STEP 2 - GATHER: Ask the user these questions before writing any code:

1. What is the feature? (brief description, primary use case)
2. What are the main entities/models? (fields, relationships, constraints)
3. Are there external integrations? (payment APIs, email, third-party services)
4. Are background jobs needed? (async processing, notifications, scheduled tasks)
5. Does the feature need authentication/authorization?
6. Are there status transitions? (e.g., order: pending -> processing -> completed)

STEP 3 - DESIGN: Propose the implementation layers and present for user approval before generating code.

**If FastAPI**: Use skill: `python-fastapi-patterns` for endpoint/DI design. Use skill: `python-sqlalchemy-patterns` for ORM/session design.
**If Django**: Use skill: `python-django-patterns` for ViewSet/serializer design.
**If background jobs needed**: Use skill: `python-celery-patterns` for task design.
**If async heavy**: Use skill: `python-async-patterns` for concurrency design.

Present a file tree showing what will be generated:

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

STEP 4 - DATABASE: Use skill: `python-migration-safety` to generate the migration safely. Include indexes on foreign keys and frequently-filtered columns. For list endpoints, add indexes that support the default sort order.

STEP 5 - MODELS: Generate SQLAlchemy 2.0 models (Mapped[], mapped_column) or Django models. Include:
- Type annotations on all fields
- Relationships with appropriate loading strategy
- DB-level constraints (unique, check, not-null)
- `TextChoices` (Django) or string enum (FastAPI) for status fields

STEP 6 - SERVICES: Business logic layer.

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

- **External service calls**: Use `httpx.AsyncClient` with timeout. Classify errors: timeout -> 503, 404 -> not-found, 5xx -> retry. Never use `requests` in async context.

STEP 7 - ENDPOINTS: FastAPI routes or Django views. Map domain errors to HTTP status codes:

| Domain Error | HTTP Status |
|---|---|
| Validation failure | 422 |
| Not found | 404 |
| Conflict (duplicate) | 409 |
| External service timeout | 503 |
| Unauthorized | 401 |
| Forbidden | 403 |

List endpoints must be paginated (offset/limit or cursor-based). Include filtering on common fields.

## STEP 8 - SCHEMAS

Pydantic v2 schemas (FastAPI) or DRF serializers (Django). Never return raw ORM objects from endpoints.

- Separate Create/Update/Response schemas per resource
- `ConfigDict(from_attributes=True)` for ORM → Pydantic conversion
- Nested schemas for child resources (e.g., `OrderItemResponse` inside `OrderResponse`)

## STEP 9 - TESTS

Use skill: `python-testing-patterns` for pytest patterns. Generate:
- Endpoint tests (happy path + error cases for each status code)
- Service unit tests (business logic, edge cases)
- Celery task tests (if applicable)
- Factory classes for test data

## STEP 10 - VALIDATE

Run: `pytest`, linter (`ruff check`), type checker (`mypy` or `pyright`). Fix any failures before presenting output.

## Output Template

```
## Files Generated
[grouped file list by layer: models, schemas, services, endpoints, tasks, tests, migrations]

## Endpoints
| Method | Path | Request | Response | Status |
|--------|------|---------|----------|--------|
| POST   | /api/v1/orders | OrderCreate | OrderResponse | 201 |
| GET    | /api/v1/orders | query params | PaginatedResponse[OrderList] | 200 |
| ...    | ... | ... | ... | ... |

## Celery Tasks (if any)
| Task | Queue | Trigger | Retry |
|------|-------|---------|-------|

## Tests
[X] tests passing - [list test files and count per file]

## Migration
[migration file name and what it creates: tables, indexes, constraints]
```

## Avoid

- Dispatching Celery `.delay()` inside a DB transaction (worker races the commit)
- Returning raw ORM objects from endpoints (use Pydantic/DRF serializers)
- Using `requests` library in async FastAPI endpoints (blocks event loop)
- Skipping pagination on list endpoints
- Using bare string fields for status without enum/TextChoices
- Generating code before user approves the design

## Self-Check

- [ ] Framework detected (FastAPI or Django); requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service, endpoint/view, schema, tests
- [ ] Pydantic schemas or DRF serializers used for all responses - no raw ORM objects
- [ ] All async endpoints use `async def`; type hints on all function signatures
- [ ] Celery tasks dispatched after DB commit, not inside transaction
- [ ] pytest, linting, and type checking all pass
- [ ] Migration includes indexes; list endpoints paginated; output template filled
