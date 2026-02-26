---
name: python-testing-patterns
description: "pytest patterns for Python. Fixtures, parametrize, async testing (pytest-asyncio), factory_boy, mocking (unittest.mock/pytest-mock), FastAPI TestClient, Django test client, Celery task testing."
user-invocable: false
---

## 1. PYTEST FUNDAMENTALS

- Fixtures over setup/teardown: @pytest.fixture with scope (function, module, session)
- parametrize for table-driven style testing
- conftest.py for shared fixtures (DB session, test client, factories)
- Markers: @pytest.mark.slow, @pytest.mark.integration

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

## 2. FASTAPI TESTING

- TestClient (sync) or AsyncClient (httpx) for endpoint tests
- Override dependencies: app.dependency_overrides[get_db] = mock_db
- pytest-asyncio for async test functions

```python
from httpx import AsyncClient

@pytest.fixture
async def client(app: FastAPI):
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.mark.asyncio
async def test_create_order(client: AsyncClient):
    response = await client.post("/api/v1/orders", json={
        "total": "49.99",
        "items": [{"product": "Widget", "quantity": 1}],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "pending"
```

```python
# Override dependencies in tests
@pytest.fixture
def app_with_mocks(app: FastAPI, mock_db_session):
    app.dependency_overrides[get_db] = lambda: mock_db_session
    yield app
    app.dependency_overrides.clear()
```

## 3. DJANGO TESTING

- APIClient for DRF endpoint tests
- @pytest.mark.django_db for database access
- pytest-django fixtures: client, admin_client, django_user_model
- TransactionTestCase only when testing transaction behavior

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
- Transaction rollback per test (pytest-django default, or manual with Alembic)
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
```

## 5. CELERY TESTING

- @pytest.fixture with celery_app and celery_worker (pytest-celery)
- task.apply() for synchronous execution in tests
- Assert task was called: mock the task.delay() call
- Test task logic separately from Celery machinery

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

- unittest.mock.patch / pytest-mock's mocker fixture
- Mock external APIs: responses library or respx (for httpx)
- Prefer dependency injection over patching where possible

```python
# respx for httpx mocking (FastAPI)
import respx

@respx.mock
@pytest.mark.asyncio
async def test_external_api_call():
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

## 7. ANTI-PATTERNS

- ❌ unittest.TestCase classes (use plain functions with pytest)
- ❌ SQLite for integration tests (use Testcontainers PostgreSQL)
- ❌ Mocking everything (test real DB interactions)
- ❌ No type hints in test functions
- ❌ time.sleep in async tests (use asyncio.wait_for or pytest-timeout)
