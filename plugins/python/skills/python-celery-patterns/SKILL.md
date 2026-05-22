---
name: python-celery-patterns
description: "Celery task patterns: idempotent design, retry/backoff/jitter, acks_late, queue routing, canvas (chain/group/chord), soft_time_limit, JSON serializer."
metadata:
  category: backend
  tags: [python, celery, background-tasks, queue, retry, idempotency]
user-invocable: false
---

# Celery Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Offloading work > 200ms or touching external services (email, webhooks, files)
- Scheduled / periodic jobs (Beat)
- Rate-limited external API integrations
- Fan-out / pipeline workflows via canvas (chain, group, chord)

## Rules

- Tasks are **idempotent**: check state before acting, safe to retry
- Pass IDs and primitives as task args - never ORM objects or sessions
- Dispatch `.delay()` / `.apply_async()` **after** the DB transaction commits, never inside it
- Always set `soft_time_limit` and `time_limit` (hard kill) - no unbounded tasks
- Retries use exponential `retry_backoff` + `retry_jitter`; pair `acks_late=True` with an idempotency guard
- Serializer is JSON (`task_serializer="json"`) - never pickle
- Route by queue; start workers with `-Q` per queue
- Canvas pipelines register `link_error` - failures otherwise propagate silently

## Patterns

### Task Design

```python
@celery_app.task(bind=True, max_retries=3)
def process_order(self, order_id: int) -> None:
    order = OrderRepository.get_by_id(order_id)
    if order is None or order.status == "processed":
        return  # idempotent guard
    OrderService.process(order)
```

### Retry with Backoff

```python
@celery_app.task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    max_retries=3,
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    soft_time_limit=120,
    time_limit=150,
)
def send_notification(self, order_id: int) -> None:
    notify_customer(get_order(order_id))
```

Manual retry when control over `countdown` is needed: `raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))`.

### Acks_late + Idempotency

Default `acks_early` loses messages on worker crash. Use `acks_late` only when the task is idempotent:

| Setting                | Ack Timing      | Guarantee      | Use When               |
| ---------------------- | --------------- | -------------- | ---------------------- |
| `acks_early` (default) | Before execute  | At-most-once   | Non-idempotent         |
| `acks_late=True`       | After execute   | At-least-once  | Idempotent + critical  |

```python
@celery_app.task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=3)
def process_payment(self, order_id: int) -> None:
    if payment_already_processed(order_id):
        return
    charge_payment(order_id)
```

### Queue Routing

```python
task_routes = {
    "app.tasks.send_notification": {"queue": "notifications"},
    "app.tasks.process_payment":   {"queue": "payments"},
}
# celery -A app worker -Q payments -c 2
```

### Canvas (chain / group / chord)

```python
from celery import chain, group, chord

pipeline = chain(validate_order.s(order_id), charge_payment.s(), send_confirmation.s())
pipeline.apply_async(link_error=handle_pipeline_error.s())

batch = group(process_item.s(i) for i in item_ids).apply_async()

workflow = chord(
    group(fetch_price.s(s) for s in symbols),
    aggregate_prices.s(),
).apply_async()
```

`handle_pipeline_error(request, exc, traceback)` logs and marks failure. Guard chord callbacks against empty group headers (callback fires with `[]`).

### Rate Limiting & Fire-and-Forget

`rate_limit="10/m"` for external APIs (per-worker). `ignore_result=True` when no result is consumed - skips backend writes.

### Integration

```python
# FastAPI: app/core/celery.py (Django mirrors: config_from_object + autodiscover_tasks)
celery_app = Celery("app", broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json",
    timezone="UTC", enable_utc=True,
)
celery_app.autodiscover_tasks(["app.tasks"])
```

Beat schedule uses `crontab` or `timedelta` - never raw floats:

```python
celery_app.conf.beat_schedule = {
    "daily-report": {"task": "app.tasks.generate_daily_report", "schedule": crontab(hour=8, minute=0)},
}
```

### Observability

Bind task context to structured logs; expose Flower (`celery -A app flower`) and `celery-exporter` for Prometheus. Alert on queue depth, failure rate, worker count drop.

```python
log = structlog.get_logger().bind(task_id=self.request.id, task_name=self.name, retry=self.request.retries)
```

### Edge Cases

- **Renaming tasks**: keep old import path as alias - `@celery_app.task(name="old.module.task_name")` - or in-flight messages raise `NotRegistered`
- **Redis broker + `acks_late`**: set `visibility_timeout` higher than longest task duration, else mid-flight tasks get re-delivered
- **Prefork pool**: each worker process needs its own DB connections - initialize in `worker_process_init`, never share pools across forks
- **Post-commit dispatch**: in SQLAlchemy use `event.listen(session, "after_commit", ...)`; in Django use `transaction.on_commit(lambda: task.delay(id))`

## Output Format

```
## Celery Design

### Tasks
| Task | Queue | Idempotent | Retries | Backoff | acks_late | Time Limit |
|------|-------|------------|---------|---------|-----------|------------|

### Queues & Workers
| Queue | Worker -Q | Concurrency | Purpose |
|-------|-----------|-------------|---------|

### Canvas Pipelines
| Pipeline | Shape | link_error | Purpose |
|----------|-------|------------|---------|

### Beat Schedule
| Task | Schedule | Purpose |
|------|----------|---------|
```

## Avoid

- ORM objects, sessions, or large payloads as task args - pass IDs only
- `.delay()` inside an open DB transaction - worker fires before commit
- Missing `soft_time_limit` / `time_limit` - hung tasks pin workers
- `acks_late=True` without an idempotency guard - double processing on retry
- `task_serializer="pickle"` - RCE risk
- Canvas without `link_error` - silent failures
- Sharing DB sessions between web process and worker, or across forked workers
- Celery worker co-located with the web server process
