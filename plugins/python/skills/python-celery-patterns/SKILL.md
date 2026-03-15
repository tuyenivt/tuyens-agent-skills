---
name: python-celery-patterns
description: "Celery background task patterns for Python. Task design, idempotency, retry strategy, queue routing, error handling, task chains/groups/chords, monitoring with Flower, and deployment with both FastAPI and Django."
user-invocable: false
---

## 1. TASK DESIGN

- Tasks must be idempotent (safe to retry)
- Pass IDs and simple types, NEVER pass ORM objects or complex state
- Keep tasks small and focused - one responsibility
- bind=True for access to self (self.retry, self.request.id)

```python
from app.core.celery import celery_app

@celery_app.task(bind=True, max_retries=3)
def process_order(self, order_id: int) -> None:
    """Process a single order. Idempotent - safe to retry."""
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
- Use sparingly - complex chains are hard to debug

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

## 5. TASK TIMEOUTS AND RATE LIMITING

Always set time limits on tasks to prevent hung workers. Use `rate_limit` for external API calls.

```python
@celery_app.task(
    bind=True,
    soft_time_limit=120,    # raises SoftTimeLimitExceeded after 2 min (can catch and clean up)
    time_limit=150,          # hard kill after 2.5 min (last resort)
    rate_limit="10/m",       # max 10 executions per minute per worker (for external APIs)
    max_retries=3,
    retry_backoff=True,
)
def call_payment_gateway(self, order_id: int) -> None:
    try:
        charge_payment(order_id)
    except SoftTimeLimitExceeded:
        logger.error(f"Payment task timed out for order {order_id}")
        mark_payment_as_timed_out(order_id)
```

For fire-and-forget tasks that don't need results stored:

```python
@celery_app.task(ignore_result=True)
def send_notification(order_id: int) -> None:
    ...
```

## 6. CANVAS ERROR HANDLING

Chain and chord errors propagate silently by default. Use `link_error` to catch failures:

```python
from celery import chain

pipeline = chain(
    validate_order.s(order_id),
    charge_payment.s(),
    send_confirmation.s(),
)
pipeline.apply_async(link_error=handle_pipeline_error.s())

@celery_app.task
def handle_pipeline_error(request, exc, traceback):
    logger.error(f"Pipeline failed for task {request.id}: {exc}")
    # Mark order as failed, notify ops, etc.
```

## 7. INTEGRATION

- FastAPI: initialize celery app in core/celery.py, import in lifespan
- Django: celery.py in project config, `autodiscover_tasks()`
- Both: shared config from environment variables
- Beat scheduler for periodic tasks

```python
# FastAPI: app/core/celery.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "app",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
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
# Periodic tasks (Beat) - use crontab or timedelta, not raw floats
from celery.schedules import crontab
from datetime import timedelta

celery_app.conf.beat_schedule = {
    "cleanup-expired-orders": {
        "task": "app.tasks.cleanup_expired_orders",
        "schedule": timedelta(hours=1),
    },
    "daily-report": {
        "task": "app.tasks.generate_daily_report",
        "schedule": crontab(hour=8, minute=0),
    },
}
```

## 8. MONITORING

- Flower: `celery -A app flower --port=5555` for web dashboard
- Prometheus exporter: `celery-exporter` for metrics scraping
- Alert on: queue length > threshold, task failure rate, worker count drop
- Structured logging with task context:

```python
import structlog

@celery_app.task(bind=True)
def process_order(self, order_id: int) -> None:
    log = structlog.get_logger().bind(
        task_id=self.request.id,
        task_name=self.name,
        order_id=order_id,
        retry=self.request.retries,
    )
    log.info("processing_order_started")
    ...
    log.info("processing_order_completed")
```

## 9. ACKS_LATE vs ACKS_EARLY (Delivery Guarantees)

By default, Celery uses `acks_early` (task acknowledged before execution). This risks message loss if the worker crashes mid-task. Use `acks_late=True` for at-least-once delivery:

| Setting                | Acknowledged              | Risk                             | Use When                                    |
| ---------------------- | ------------------------- | -------------------------------- | ------------------------------------------- |
| `acks_early` (default) | Before execution starts   | Message lost on worker crash     | Task is not idempotent, prefer at-most-once |
| `acks_late=True`       | After execution completes | Task re-executed on worker crash | Task is idempotent, prefer at-least-once    |

```python
@celery_app.task(
    bind=True,
    acks_late=True,            # re-queue on worker crash
    reject_on_worker_lost=True, # return to queue if worker dies mid-task
    max_retries=3,
    retry_backoff=True,
)
def process_payment(self, order_id: int) -> None:
    """Idempotent payment processor - safe to retry with acks_late."""
    if payment_already_processed(order_id):
        return  # idempotency guard prevents double charge
    charge_payment(order_id)
```

Always pair `acks_late=True` with an idempotency guard in the task body.

## 10. ANTI-PATTERNS

- ❌ Passing ORM objects as task arguments (use IDs - objects aren't JSON-serializable)
- ❌ Tasks longer than 30 minutes without chunking
- ❌ No `soft_time_limit` / `time_limit` (hung tasks hold workers indefinitely)
- ❌ No retry strategy (all tasks should handle transient failures)
- ❌ Celery worker running on same process as web server
- ❌ `acks_late=True` without idempotency guard (causes double processing on retry)
- ❌ Dispatching `.delay()` inside a DB transaction (worker fires before commit - may read stale data or missing rows)
- ❌ Sharing DB sessions between web process and Celery worker (separate session factories)
- ❌ Using pickle serializer (`task_serializer="pickle"`) - security risk, use JSON
- ❌ Chains/chords without `link_error` (failures propagate silently)
