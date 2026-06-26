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

- Plain pytest functions; no `unittest.TestCase` classes
- Real PostgreSQL via Testcontainers for integration; never SQLite
- Each test independent: rollback per test, clear `dependency_overrides`
- Patch at the import path of the consumer, not the source module
- `pytest-asyncio` `asyncio_mode = "auto"`; no per-test `@pytest.mark.asyncio`
- Test names state behavior: `test_create_order_returns_201_when_valid`
- `scope="session"` only for read-only setup (engine, container); never for mutated DB rows

## Patterns

### Fixtures and Parametrize

```python
@pytest.mark.parametrize("status,expected_count", [
    ("pending", 3), ("completed", 1), ("cancelled", 0),
])
def test_list_orders_by_status(status, expected_count):
    ...
```

Shared fixtures live in `conftest.py` (root and `integration/`). Markers: `slow`, `integration`.

### Test Layout

```
tests/
  conftest.py              # shared: db session, client, factories
  unit/                    # mocked dependencies
  integration/
    conftest.py            # Testcontainers PostgreSQL, real DB
```

### FastAPI Async Testing

`pyproject.toml`:

```ini
[tool.pytest-asyncio]
asyncio_mode = "auto"
```

Mount the app via `httpx.ASGITransport` (httpx 0.27+):

```python
from httpx import ASGITransport, AsyncClient

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

async def test_create_order_returns_201(client: AsyncClient):
    response = await client.post("/api/v1/orders", json={"total": "49.99", "items": [...]})
    assert response.status_code == 201
    assert response.json()["status"] == "pending"
```

### Async SQLAlchemy Session with Rollback

```python
@pytest.fixture(scope="session")
def async_engine(postgres_url):
    return create_async_engine(postgres_url)

@pytest.fixture
async def db_session(async_engine):
    async_session = async_sessionmaker(async_engine, expire_on_commit=False)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as session:
        async with session.begin():
            yield session
            await session.rollback()  # isolation per test

@pytest.fixture
def app_with_db(app: FastAPI, db_session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: db_session
    yield app
    app.dependency_overrides.clear()  # leftover overrides leak between tests
```

### Django Testing

DRF `APIClient` with `force_authenticate`; `@pytest.mark.django_db` for DB access. `TransactionTestCase` only for transaction-behavior tests.

```python
from rest_framework.test import APIClient

@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client

@pytest.mark.django_db
def test_create_order(api_client):
    response = api_client.post("/api/orders/", {"total": "49.99", "items": [...]}, format="json")
    assert response.status_code == 201

# IDOR on owned resources: return 404 (not 403) so existence isn't leaked
@pytest.mark.django_db
def test_other_user_gets_404_for_foreign_order(api_client, other_user):
    order = OrderFactory(owner=other_user)
    response = api_client.get(f"/api/orders/{order.pk}/")  # api_client authed as a different user
    assert response.status_code == 404

# ORM constraint: IntegrityError poisons the transaction - isolate the failing insert
@pytest.mark.django_db
def test_duplicate_reference_rejected(user):
    OrderFactory(owner=user, reference="DUP")
    with pytest.raises(IntegrityError), transaction.atomic():
        OrderFactory(owner=user, reference="DUP")
```

Django factories use `factory.django.DjangoModelFactory` (not `SQLAlchemyModelFactory`); `model_bakery` (`baker.make(Order, ...)`) is the lighter alternative.

### Database Testing

factory_boy with `SQLAlchemyModelFactory`; use `SubFactory` for related models, `LazyAttribute`/`post_generation` to break cycles:

```python
import factory
from factory.alchemy import SQLAlchemyModelFactory

class OrderFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Order
        sqlalchemy_session_persistence = "commit"

    total = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    status = "pending"
```

Testcontainers for real PostgreSQL:

```python
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16") as pg:
        yield pg

@pytest.fixture(scope="session")
def postgres_url(postgres):
    return postgres.get_connection_url().replace("psycopg2", "asyncpg")
```

For shared session-scoped DB, use `SAVEPOINT` rollback per test, not `DROP/CREATE`.

### Celery Testing

Test task logic via `.apply()` (synchronous); mock `.delay()` to verify dispatch:

```python
def test_send_notification_task(db_session, order):
    result = send_notification.apply(args=[order.id])
    assert result.successful()

def test_order_triggers_notification(mocker):
    mock_delay = mocker.patch("app.tasks.send_notification.delay")
    OrderService.complete(order_id=1)
    mock_delay.assert_called_once_with(1)
```

`CELERY_TASK_ALWAYS_EAGER=True` skips serialization; pair with at least one real-broker test (`pytest-celery` `celery_worker` fixture) to catch pickle/JSON bugs, `acks_late` redelivery, and real retry scheduling. Retry sequences need `CELERY_TASK_EAGER_PROPAGATES=False` for `self.retry` to re-run the body under EAGER:

```python
# Post-commit dispatch: assert it fires after commit, not before
def test_dispatch_after_commit(mocker):
    delay = mocker.patch("app.orders.service.process_payment.delay")
    with django_capture_on_commit_callbacks(execute=True):
        order = OrderService.create(...)
        delay.assert_not_called()         # still inside the transaction
    delay.assert_called_once_with(order.id)  # fired by on_commit

# Retry fail-fail-success
def test_retries_then_succeeds(mocker, order):
    mocker.patch("app.tasks.gateway.charge", side_effect=[Timeout(), Timeout(), {"id": "ch_1"}])
    result = process_payment.apply(args=[order.id])  # EAGER_PROPAGATES=False
    assert result.successful()
```

### Mocking

Key the HTTP stub to the **client**, not the framework: `respx` / `pytest-httpx` for `httpx` (whether FastAPI or a Django app calling httpx), `responses` for `requests`. `pytest-mock` `mocker` for general patching. Prefer DI over patching.

```python
import respx

async def test_external_api_call():
    with respx.mock:
        respx.get("https://api.example.com/data").respond(json={"key": "value"})
        result = await fetch_external_data()
        assert result["key"] == "value"
```

### CI and Coverage

```ini
# pyproject.toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80"
markers = [
    "slow: marks tests as slow",
    "integration: requires external services",
]

[tool.coverage.run]
omit = ["tests/*", "migrations/*"]
```

Parallel: `pytest -n auto` (pytest-xdist). Async session-scoped fixtures need `pytest-asyncio` 0.21+ with a session-scoped event loop fixture.

## Output Format

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

- Mocking everything in integration tests (defeats the purpose)
- `time.sleep` in async tests (use `asyncio.wait_for` / `pytest-timeout`)
- `CELERY_TASK_ALWAYS_EAGER` as the only Celery test strategy
- Shared mutable state across tests (module globals, session-scoped mutated fixtures)
