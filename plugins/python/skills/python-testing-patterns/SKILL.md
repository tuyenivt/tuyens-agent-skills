---
name: python-testing-patterns
description: "pytest patterns for FastAPI, Django, and Celery applications. Covers fixtures, parametrize, async testing with pytest-asyncio, factory_boy for test data, mocking with respx/pytest-mock, Testcontainers for real PostgreSQL, and CI coverage configuration."
metadata:
  category: backend
  tags: [python, pytest, testing, fixtures, mocking, factory-boy, testcontainers]
user-invocable: false
---

## 1. PYTEST FUNDAMENTALS

- Fixtures over setup/teardown: `@pytest.fixture` with scope (function, module, session)
- `parametrize` for table-driven style testing
- `conftest.py` for shared fixtures (DB session, test client, factories)
- Markers: `@pytest.mark.slow`, `@pytest.mark.integration`

```python
@pytest.fixture
def order_data():
    return {"total": "99.99", "items": [{"product": "Widget", "quantity": 2}]}

@pytest.mark.parametrize("status,expected_count", [
    ("pending", 3),
    ("completed", 1),
    ("cancelled", 0),
])
def test_list_orders_by_status(status, expected_count):
    ...
```

### Test Organization

```
tests/
  conftest.py              # shared fixtures: db session, client, factories
  unit/
    test_order_service.py  # service logic, mocked dependencies
    test_order_schemas.py  # Pydantic validation edge cases
  integration/
    conftest.py            # Testcontainers PostgreSQL, real DB fixtures
    test_orders_api.py     # full endpoint tests with real DB
    test_order_tasks.py    # Celery task tests
```

## 2. FASTAPI ASYNC TESTING

Configure `pytest-asyncio` mode to avoid decorating every test:

```ini
# pyproject.toml
[tool.pytest-asyncio]
asyncio_mode = "auto"
```

Use `httpx.ASGITransport` (httpx 0.27+) to mount the FastAPI app:

```python
from httpx import ASGITransport, AsyncClient

@pytest.fixture
async def client(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

async def test_create_order(client: AsyncClient):
    response = await client.post("/api/v1/orders", json={
        "total": "49.99",
        "items": [{"product": "Widget", "quantity": 1}],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
```

### Async SQLAlchemy Session Fixture

Wire a real async session into FastAPI dependency overrides:

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

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
            await session.rollback()  # rollback per test for isolation

@pytest.fixture
def app_with_db(app: FastAPI, db_session: AsyncSession):
    app.dependency_overrides[get_db] = lambda: db_session
    yield app
    app.dependency_overrides.clear()
```

## 3. DJANGO TESTING

- APIClient for DRF endpoint tests
- `@pytest.mark.django_db` for database access
- pytest-django fixtures: `client`, `admin_client`, `django_user_model`
- `TransactionTestCase` only when testing transaction behavior

```python
from rest_framework.test import APIClient

@pytest.fixture
def api_client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client

@pytest.mark.django_db
def test_create_order(api_client):
    response = api_client.post("/api/orders/", {
        "total": "49.99",
        "items": [{"product": "Widget", "quantity": 1}],
    }, format="json")
    assert response.status_code == 201
```

## 4. DATABASE TESTING

- Testcontainers (testcontainers-python) for real PostgreSQL
- Transaction rollback per test for isolation
- factory_boy for test data (like FactoryBot for Python)

```python
import factory
from factory.alchemy import SQLAlchemyModelFactory

class OrderFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Order
        sqlalchemy_session_persistence = "commit"

    total = factory.Faker("pydecimal", left_digits=4, right_digits=2, positive=True)
    status = "pending"

class OrderItemFactory(SQLAlchemyModelFactory):
    class Meta:
        model = OrderItem
        sqlalchemy_session_persistence = "commit"

    order = factory.SubFactory(OrderFactory)
    product_name = factory.Faker("word")
    quantity = factory.Faker("random_int", min=1, max=10)
```

```python
# Testcontainers for real PostgreSQL
from testcontainers.postgres import PostgresContainer

@pytest.fixture(scope="session")
def postgres():
    with PostgresContainer("postgres:16") as pg:
        yield pg

@pytest.fixture(scope="session")
def postgres_url(postgres):
    return postgres.get_connection_url().replace("psycopg2", "asyncpg")
```

## 5. CELERY TESTING

- `task.apply()` for synchronous execution in tests
- Mock `.delay()` to verify task dispatch without running workers
- Test task logic separately from Celery machinery
- Use `CELERY_TASK_ALWAYS_EAGER=True` for integration tests (but beware: this skips serialization)

```python
def test_send_notification_task(db_session, order):
    # Test task logic directly (synchronous)
    result = send_notification.apply(args=[order.id])
    assert result.successful()

def test_order_triggers_notification(mocker):
    mock_delay = mocker.patch("app.tasks.send_notification.delay")
    OrderService.complete(order_id=1)
    mock_delay.assert_called_once_with(1)
```

## 6. MOCKING

- `unittest.mock.patch` / pytest-mock `mocker` fixture
- Mock external APIs: `respx` for httpx (FastAPI), `responses` for requests (Django)
- Prefer dependency injection over patching where possible
- Patch at the import path, not the source path

```python
# respx for httpx mocking (FastAPI)
import respx

async def test_external_api_call():
    with respx.mock:
        respx.get("https://api.example.com/data").respond(json={"key": "value"})
        result = await fetch_external_data()
        assert result["key"] == "value"

# pytest-mock mocker fixture
def test_service_calls_repo(mocker):
    mock_repo = mocker.AsyncMock(spec=OrderRepository)
    mock_repo.get_by_id.return_value = OrderFactory.build()
    service = OrderService(mock_repo)
    ...
```

## 7. CI AND COVERAGE

```ini
# pyproject.toml
[tool.pytest.ini_options]
addopts = "--cov=app --cov-branch --cov-report=term-missing --cov-fail-under=80"
markers = [
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
    "integration: requires external services",
]

[tool.coverage.run]
omit = ["tests/*", "migrations/*"]
```

For parallel execution: `pytest -n auto` (pytest-xdist).

## 8. EDGE CASES

- **Async fixture scoping**: `scope="session"` async fixtures require `pytest-asyncio` 0.21+ and a session-scoped event loop. If tests hang or fail with event loop errors, check that the event loop fixture scope matches.
- **Dependency override cleanup**: Always call `app.dependency_overrides.clear()` in fixture teardown - leftover overrides leak between tests.
- **Factory circular references**: When two factories reference each other via `SubFactory`, use `LazyAttribute` or `post_generation` to break the cycle.
- **Transaction isolation with Testcontainers**: If tests share a session-scoped database, use `SAVEPOINT` rollback per test (not `DROP/CREATE` tables) for speed.

## 9. ANTI-PATTERNS

- ❌ `unittest.TestCase` classes (use plain functions with pytest)
- ❌ SQLite for integration tests (use Testcontainers PostgreSQL)
- ❌ Mocking everything (test real DB interactions for integration tests)
- ❌ `time.sleep` in async tests (use `asyncio.wait_for` or `pytest-timeout`)
- ❌ Patching at the source module instead of the import path
- ❌ `CELERY_TASK_ALWAYS_EAGER` without also testing with real serialization (masks pickle/JSON bugs)
- ❌ Shared mutable state between tests (global variables, module-scoped fixtures that mutate)
- ❌ `scope="session"` on fixtures that mutate DB state (breaks test isolation)
