---
name: python-testing-patterns
description: "pytest patterns for FastAPI, Django, Celery: fixtures, parametrize, pytest-asyncio, factory_boy, respx, Testcontainers PostgreSQL, coverage."
metadata:
  category: backend
  tags: [python, pytest, testing, fixtures, mocking, factory-boy, testcontainers]
user-invocable: false
---

# Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing unit tests for services, repositories, utilities
- Writing integration/e2e tests for FastAPI or Django endpoints
- Setting up test infrastructure (DB, async fixtures, factories, mocks)
- Reviewing test code for coverage gaps or anti-patterns

## Rules

- Plain pytest functions; no `unittest.TestCase` / `TransactionTestCase` classes (`@pytest.mark.django_db(transaction=True)` for transaction-behaviour tests)
- Real PostgreSQL via Testcontainers for integration, never SQLite; SQLite test settings get a migration step in the plan
- Each test independent: SAVEPOINT rollback per test (a service `commit()` leaks no rows), clear `dependency_overrides`
- Patch at the import path of the consumer, not the source module
- `scope="session"` only for read-only setup (engine, container), never for mutated rows or created users
- `asyncio_mode = "auto"`; async fixtures run on the session loop (`asyncio_default_fixture_loop_scope`), async test modules opt in via module `pytestmark`, never per-test marks; `event_loop` overrides are deprecated

## Patterns

### Fixtures and Layout

Layout: `tests/conftest.py`, `tests/unit/` (mocked dependencies), `tests/integration/conftest.py` (Testcontainers PostgreSQL).

### FastAPI Async Testing

`pyproject.toml` (the same keys work in `pytest.ini` `[pytest]`; a function-loop fixture under a session-loop test raises `MultipleEventLoopsRequestedError`):

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
asyncio_default_fixture_loop_scope = "session"
```

Mount via `httpx.ASGITransport`; `client` depends on the fixture installing the DB override:

```python
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

pytestmark = pytest.mark.asyncio(loop_scope="session")

@pytest.fixture
async def client(app_with_db: FastAPI):
    async with AsyncClient(transport=ASGITransport(app=app_with_db), base_url="http://test") as ac:
        yield ac

async def test_create_order_returns_201(client: AsyncClient):
    response = await client.post("/api/v1/orders", json={"total": "49.99", "items": [...]})
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
```

Sync `TestClient` serves async endpoints on a portal thread but shares no async fixtures: sync tests only.

### Async SQLAlchemy Session with SAVEPOINT Rollback

```python
import pytest, pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

pytestmark = pytest.mark.asyncio(loop_scope="session")       # every async test module; not on sync modules

@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def async_engine(postgres_url):
    engine = create_async_engine(postgres_url)                 # asyncpg connections are bound to this loop
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest_asyncio.fixture(loop_scope="session")
async def db_session(async_engine):
    async with async_engine.connect() as conn:
        trans = await conn.begin()                             # outer transaction, never committed
        session = AsyncSession(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
        yield session                                          # service commit() releases a SAVEPOINT only
        await session.close()
        await trans.rollback()                                 # isolation per test

@pytest.fixture
def app_with_db(app: FastAPI, db_session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: db_session
    yield app
    app.dependency_overrides.clear()                           # leftovers leak between tests
```

### Django Testing

DRF `APIClient` with `force_authenticate`; `@pytest.mark.django_db` for DB. `django_capture_on_commit_callbacks` is a pytest-django 4.4+ fixture.

```python
from django.db import IntegrityError, transaction
from rest_framework.test import APIClient

@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client

@pytest.mark.django_db
def test_create_order(api_client):
    assert api_client.post("/api/orders/", {"total": "49.99", "items": [...]}, format="json").status_code == 201

# IDOR: foreign order returns 404 (not 403), existence not leaked
@pytest.mark.django_db
def test_other_user_gets_404_for_foreign_order(api_client, other_user):
    order = OrderFactory(owner=other_user)
    assert api_client.get(f"/api/orders/{order.pk}/").status_code == 404

# ORM constraint: IntegrityError poisons the transaction - isolate the failing insert
@pytest.mark.django_db
def test_duplicate_reference_rejected(user):
    OrderFactory(owner=user, reference="DUP")
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderFactory(owner=user, reference="DUP")

# Post-commit dispatch: assert it fires after commit, not before
@pytest.mark.django_db
def test_dispatch_after_commit(mocker, django_capture_on_commit_callbacks):
    delay = mocker.patch("app.orders.service.process_payment.delay")
    with django_capture_on_commit_callbacks(execute=True):
        order = OrderService.create(...)
        delay.assert_not_called()         # still inside the transaction
    delay.assert_called_once_with(order.id)  # on_commit fired
```

Django factories: `DjangoModelFactory` or `model_bakery`. The `user` fixture is function-scoped (`django_db` rolls it back); a session-scoped user via `django_db_blocker` outlives every test transaction and leaks.

### Database Testing

factory_boy is sync: bind the `AsyncSession` per test and `flush` yourself - `sqlalchemy_session_persistence="commit"` would leave the coroutine `commit()` un-awaited. `SubFactory` for related models:

```python
import factory
from factory.alchemy import SQLAlchemyModelFactory

pytestmark = pytest.mark.asyncio(loop_scope="session")

class OrderFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Order
        sqlalchemy_session_persistence = None

    total = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    status = "pending"

@pytest.fixture(autouse=True)
def _bind_factories(db_session):
    OrderFactory._meta.sqlalchemy_session = db_session

async def test_lists_pending(db_session):
    OrderFactory.create_batch(3); await db_session.flush()
```

Testcontainers for real PostgreSQL:

```python
from testcontainers.postgres import PostgresContainer     # testcontainers 4.15+: testcontainers.community.postgres

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16", driver="asyncpg") as pg:
        yield pg

@pytest.fixture(scope="session")
def postgres_url(postgres):
    return postgres.get_connection_url()
```

### Celery Testing

Test task logic via `.apply()` (synchronous); mock `.delay()` to verify dispatch:

```python
from requests.exceptions import Timeout

def test_send_notification_task(order):  # SQLAlchemy: stub the repository the task reads (SAVEPOINT rows are invisible to it); Django: @pytest.mark.django_db on both DB tests
    result = send_notification.apply(args=[order.id])
    assert result.successful()

def test_order_triggers_notification(mocker, order):  # Django: django_db + django_capture_on_commit_callbacks(execute=True) around the call
    mock_delay = mocker.patch("app.tasks.send_notification.delay")
    OrderService.complete(order_id=order.id)
    mock_delay.assert_called_once_with(order.id)

# Retry fail-fail-success
def test_retries_then_succeeds(mocker, order):
    mocker.patch("app.tasks.gateway.charge", side_effect=[Timeout(), Timeout(), {"id": "ch_1"}])
    result = process_payment.apply(args=[order.id])  # EAGER_PROPAGATES=False
    assert result.successful()
```

`CELERY_TASK_ALWAYS_EAGER=True` skips serialization; one real-broker test (`pytest-celery` `celery_worker`) covers pickle/JSON bugs, `acks_late` redelivery and real retry scheduling. Retry sequences need `CELERY_TASK_EAGER_PROPAGATES=False` so `self.retry` re-runs the body. Non-Django post-commit dispatch: patch `.delay`, run the service, assert `.delay` is uncalled before `await db_session.commit()` and called once it returns (a SQLAlchemy `after_commit` listener fires inside it).

### Mocking

Key the HTTP stub to the **client**, not the framework: `respx` / `pytest-httpx` for `httpx` (FastAPI or a Django app calling httpx), `responses` for `requests` - including `requests` calls from inside `async def`. `pytest-mock` `mocker` for general patching; prefer DI.

```python
import respx

async def test_external_api_call():
    with respx.mock:
        respx.get("https://api.example.com/data").respond(json={"key": "value"})
        assert (await fetch_external_data())["key"] == "value"
```

### CI and Coverage

```toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80"
markers = [
    "slow",
    "integration: needs external services",
]

[tool.coverage.run]
omit = ["*/tests/*", "*/migrations/*"]
```

Parallel: `pytest -n auto`. Dev deps: `pytest`, `pytest-asyncio`, `pytest-cov`, `pytest-mock`, `pytest-xdist`, `pytest-timeout`, `factory_boy`, `respx`, `testcontainers[postgres]`; Django adds `pytest-django`; Celery adds `pytest-celery`.

## Output Format

When authoring, emit this block plus the test code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it. Coverage Targets count the planned tests in both modes.

```
## Test Plan

### Unit Tests
| Test | Module | Mocks | Assertions |
|------|--------|-------|------------|

### Integration Tests
| Test | Endpoint/Task | DB/Broker | Assertions |
|------|---------------|-----------|------------|

### Coverage Targets
- Service layer: {count} unit tests
- API layer: {count} integration tests
- Task layer: {count} Celery tests
```

## Avoid

- `time.sleep` in tests - poll with a deadline (`asyncio.wait_for` async, bounded loop sync); `pytest-timeout` only caps hangs
