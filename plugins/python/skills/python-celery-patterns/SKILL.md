---
name: python-celery-patterns
description: "Celery background task patterns for Python. Task design, idempotency, retry strategy, queue routing, error handling, task chains/groups/chords, monitoring with Flower, and deployment with both FastAPI and Django."
user-invocable: false
---

## 1. TASK DESIGN

- Tasks must be idempotent (safe to retry)
- Pass IDs and simple types, NEVER pass ORM objects or complex state
- Keep tasks small and focused — one responsibility
- bind=True for access to self (self.retry, self.request.id)

```python
from app.core.celery import celery_app

@celery_app.task(bind=True, max_retries=3)
def process_order(self, order_id: int) -> None:
    """Process a single order. Idempotent — safe to retry."""
    order = OrderRepository.get_by_id(order_id)  # sync DB call in Celery worker
    if order is None:
        return  # already processed or deleted
    if order.status == "processed":
        return  # idempotent check
    OrderService.process(order)
```

## 2. RETRY STRATEGY

- autoretry_for=(TransientError,) with max_retries=3
- Exponential backoff: retry_backoff=True, retry_backoff_max=600
- retry_jitter=True to prevent thundering herd
- Dead letter queue for permanently failed tasks

```python
@celery_app.task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def send_notification(self, order_id: int) -> None:
    order = get_order(order_id)
    notify_customer(order)
```

```python
# Manual retry with custom logic
@celery_app.task(bind=True, max_retries=5)
def charge_payment(self, order_id: int) -> None:
    try:
        result = payment_gateway.charge(order_id)
    except PaymentGatewayUnavailable as exc:
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
```

## 3. QUEUE ROUTING

- Default queue for standard tasks
- High-priority queue for time-sensitive tasks
- task_routes configuration in celery config
- -Q flag on workers to consume specific queues

```python
# celery config
task_routes = {
    "app.tasks.send_notification": {"queue": "notifications"},
    "app.tasks.process_payment": {"queue": "payments"},
    "app.tasks.generate_report": {"queue": "reports"},
}

# Start workers per queue
# celery -A app worker -Q notifications -c 4
# celery -A app worker -Q payments -c 2
# celery -A app worker -Q reports -c 1
```

## 4. TASK COMPOSITION

- chain() for sequential: chain(fetch.s(url), parse.s(), store.s())
- group() for parallel: group(process.s(item) for item in items)
- chord() for fan-out/fan-in: chord(group, callback)
- Use sparingly — complex chains are hard to debug

```python
from celery import chain, group, chord

# Sequential pipeline
pipeline = chain(
    validate_order.s(order_id),
    charge_payment.s(),
    send_confirmation.s(),
)
pipeline.apply_async()

# Parallel processing
batch = group(process_item.s(item_id) for item_id in item_ids)
batch.apply_async()

# Fan-out then aggregate
workflow = chord(
    group(fetch_price.s(symbol) for symbol in symbols),
    aggregate_prices.s(),
)
workflow.apply_async()
```

## 5. INTEGRATION

- FastAPI: initialize celery app in core/celery.py, import in lifespan
- Django: celery.py in project config, autodiscover_tasks()
- Both: shared config from environment variables
- Beat scheduler for periodic tasks (celery-beat or django-celery-beat)

```python
# FastAPI: app/core/celery.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.autodiscover_tasks(["app.tasks"])
```

```python
# Django: config/celery.py
import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("project")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
```

```python
# Periodic tasks (Beat)
celery_app.conf.beat_schedule = {
    "cleanup-expired-orders": {
        "task": "app.tasks.cleanup_expired_orders",
        "schedule": 3600.0,  # every hour
    },
}
```

## 6. MONITORING

- Flower for web dashboard
- Prometheus exporter for metrics
- Alert on: queue length > threshold, task failure rate, worker count

## 7. ANTI-PATTERNS

- ❌ Passing ORM objects as task arguments (use IDs)
- ❌ Tasks longer than 30 minutes without chunking
- ❌ Ignoring task results when they contain errors
- ❌ No retry strategy (all tasks should handle transient failures)
- ❌ Celery worker running on same process as web server
