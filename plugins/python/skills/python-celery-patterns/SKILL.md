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

- Tasks are **idempotent**: check durable state before acting (a `processed` row under a unique constraint or a Redis key with TTL, never memory) and pass external providers an idempotency key so a retry cannot charge twice
- Pass IDs and primitives as task args - never ORM objects or sessions
- Dispatch `.delay()` / `.apply_async()` **after** the DB transaction commits, never inside it
- Always set `soft_time_limit` and `time_limit` (hard kill)
- Retries use exponential `retry_backoff` + `retry_jitter`; `acks_late=True` only with an idempotency guard
- Serializer is JSON (`task_serializer="json"`, `accept_content=["json"]`) - never pickle
- Route by queue; start workers with `-Q` per queue
- Canvas pipelines register `link_error` - otherwise a failed link halts the pipeline silently

## Patterns

### Task Design and Retry

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
def process_order(self, order_id: int) -> None:
    order = OrderRepository.get_by_id(order_id)
    if order is None or order.status == "processed":
        return  # idempotent guard
    OrderService.process(order, idempotency_key=f"order-{order_id}")   # provider dedupes on the key
```

Manual retry: `raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))`.

### acks_late + Idempotency

`acks_late=False` (default) acks before execution, so a worker crash loses the message; `acks_late=True` acks after execution and re-delivers on a lost broker connection (a killed child re-delivers only with `reject_on_worker_lost=True`, which loops a task that always kills its child - pair with a hard `time_limit`), so the task may run twice:

| Setting                   | Ack Timing     | Guarantee     | Use When              |
| ------------------------- | -------------- | ------------- | --------------------- |
| `acks_late=False` (default) | Before execute | At-most-once  | Non-idempotent        |
| `acks_late=True`          | After execute  | At-least-once | Idempotent + critical |

```python
@celery_app.task(bind=True, acks_late=True, reject_on_worker_lost=True, max_retries=3, soft_time_limit=60, time_limit=90)
def process_payment(self, order_id: int) -> None:
    if payment_already_processed(order_id):
        return
    charge_payment(order_id, idempotency_key=f"payment-{order_id}")
```

### Queue Routing

```python
task_routes = {
    "app.tasks.process_order":     {"queue": "orders"},
    "app.tasks.process_payment":   {"queue": "payments"},
}
# celery -A app worker -Q payments -c 2
```

### Canvas (chain / group / chord)

```python
from celery import chain, chord, group

pipeline = chain(validate_order.s(order_id), charge_payment.s(), send_confirmation.s())
pipeline.apply_async(link_error=handle_pipeline_error.s())

batch = group(process_item.s(i) for i in item_ids).apply_async()

workflow = chord(
    group(fetch_price.s(s) for s in symbols),
    aggregate_prices.s(),
).apply_async()
```

`handle_pipeline_error(request, exc, traceback, order_id=None)` records the failure (row or alert); Celery passes `(request, exc, traceback)` plus kwargs pinned via `.s(order_id=...)`. `link_error` on a chain attaches to every link; on a nested chord it attaches to the body only (default `task_allow_error_cb_on_chord_header=False`), so a header failure arrives once as `ChordError`. Chord callbacks fire with `[]` on an empty header - guard them.

Charge -> parallel fulfillment -> confirm is a chord inside a chain; each upstream return value becomes the next task's first positional arg:

```python
pipeline = chain(
    charge_payment.s(order_id),                              # returns order_id
    chord(group(generate_invoice.s(), reserve_inventory.s()),  # both receive order_id
          send_confirmation.s(order_id=order_id)),           # receives [results], order_id pinned
)
pipeline.apply_async(link_error=handle_pipeline_error.s(order_id=order_id))
```

Large fan-out: `task.chunks(iterable_of_arg_tuples, n)` bounds the task count and chord result-backend pressure (every header result buffers until the callback fires); `group(...).skew(start=0, step=1)` only staggers countdowns.

### Rate Limiting and Fire-and-Forget

`rate_limit="10/m"` is **per worker instance** - a fleet-wide cap means one worker for that queue, the limit divided by worker count, or a Redis token bucket. `ignore_result=True` when nothing reads the result.

### Integration

```python
# FastAPI app/core/celery.py; Django: config_from_object + autodiscover_tasks
from celery import Celery
from celery.schedules import crontab

celery_app = Celery("app", broker=settings.CELERY_BROKER_URL, backend=settings.CELERY_RESULT_BACKEND)
celery_app.conf.update(
    task_serializer="json", accept_content=["json"], result_serializer="json",
    timezone="UTC", enable_utc=True,
    broker_transport_options={"visibility_timeout": 7200},   # Redis: see Edge Cases
)
celery_app.autodiscover_tasks(["app.tasks"])

celery_app.conf.beat_schedule = {
    "daily-report": {"task": "app.tasks.generate_daily_report", "schedule": crontab(hour=8, minute=0)},
}
```

Beat uses `crontab` or `timedelta`, never raw floats, in exactly one beat process; a task that must not double-run on restart also takes a Redis lock keyed by schedule slot (`SET report:2026-10-23 1 NX EX 3600`). Observability: `task_id`/`task_name`/`retries` in logs; alert on queue depth and failure rate.

### Edge Cases

- **Renaming tasks**: register the function under both names (`@celery_app.task(name="app.tasks.new")` plus `celery_app.task(name="old.module.task_name")(fn)`) and drop the old only when no deploy enqueues it, or in-flight messages raise `NotRegistered`
- **Redis broker + `acks_late`**: `visibility_timeout` must exceed the longest `time_limit` and ETA/countdown (retry backoff included), else in-flight or scheduled tasks re-deliver and run twice
- **Prefork pool**: DB connections are per worker process - initialize in `worker_process_init`, never share pools across forks; async SQLAlchemy wraps the task body in `asyncio.run(...)` - a new loop each call, so the engine uses `NullPool` or is disposed before returning
- **Post-commit dispatch**: Django `transaction.on_commit(lambda: task.delay(id))` (Celery 5.4: `task.delay_on_commit(id)`); async SQLAlchemy: after `await session.commit()` or an `after_commit` listener

## Output Format

When authoring, emit this block plus the code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state (proposed tasks included) and one finding per deviation from it. A table the task does not touch reads `n/a`. Queues & Workers has one row per worker deployment (several queues comma-separated).

```
## Celery Design

### Tasks
| Task | Queue | Idempotent | Retries | Backoff | acks_late | Time Limit |
|------|-------|------------|---------|---------|-----------|------------|
| {task} | {queue} | {<durable key> + provider key \| <durable key> \| no} | {n} | {exp \| none} | {True \| False} | {soft/hard s} |

### Queues & Workers
| Queue | Worker -Q | Concurrency | Purpose |
|-------|-----------|-------------|---------|

### Canvas Pipelines
| Pipeline | Shape | link_error | Purpose |
|----------|-------|------------|---------|

### Beat Schedule
| Task | Schedule | Single-run guard | Purpose |
|------|----------|------------------|---------|
```

## Avoid

- Large payloads (HTML, images) as task args - pass references
- Worker co-located with the web server process
- `pickle` anywhere in `accept_content` - RCE on any broker write
