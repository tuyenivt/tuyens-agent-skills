# Tuyen's Agent Skills - Python

Claude Code plugin for Python development.

## Stack

- **Primary:** Python 3.11+, FastAPI + async
- **Secondary:** Django + DRF
- **ORM / Migrations:** SQLAlchemy 2.0+ / Alembic
- **Testing:** pytest
- **Task Queue:** Celery
- **Database:** PostgreSQL

## Workflow Skills

| Skill                             | Agent                       | Description                                                                                                          |
| --------------------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| task-python-implement             | python-architect            | End-to-end feature implementation across all layers                                                                  |
| task-python-debug                 | python-architect            | Debug tracebacks, logs, Celery errors, and test failures                                                             |
| task-python-review                | python-tech-lead            | Python staff-level code review umbrella - Phases A-E with FastAPI/Django idioms; spawns parallel scope subagents     |
| task-python-review-perf           | python-performance-engineer | SQLAlchemy / Django ORM N+1, async event-loop blocking, Celery throughput, migration safety                          |
| task-python-review-security       | python-security-engineer    | FastAPI OAuth2 / JWT, Django auth / DRF permissions, Pydantic v2 mass assignment, ORM injection, OWASP Top 10        |
| task-python-review-observability  | python-tech-lead            | structlog, OpenTelemetry SDK + auto-instrumentation, Prometheus client, error-tracker SDKs (library-level focus)     |
| task-python-test                  | python-test-engineer        | pytest strategy / scaffolding (httpx ASGITransport, DRF APIClient, Testcontainers, factory_boy, Celery testing)      |
| task-python-refactor              | python-tech-lead            | Refactor plan: fat routers/views, anemic services, sync-in-async, Django signal abuse, Celery idempotency, with gates|

## Atomic Skills (internal, not user-invocable)

| Skill                      | Description                                                                                 |
| -------------------------- | ------------------------------------------------------------------------------------------- |
| python-fastapi-patterns    | Async endpoints, dependency injection, Pydantic v2, routers, middleware, lifespan           |
| python-django-patterns     | ViewSets, serializers, QuerySet optimization, DRF permissions                               |
| python-sqlalchemy-patterns | SQLAlchemy 2.0+ async sessions, mapped_column, select(), N+1 prevention, repository pattern |
| python-migration-safety    | Alembic + Django migrations, zero-downtime DDL, data migration separation                   |
| python-testing-patterns    | pytest fixtures, parametrize, async testing, factory_boy, TestClient, Celery testing        |
| python-celery-patterns     | Task design, idempotency, retry strategy, queue routing, chains/groups/chords               |
| python-async-patterns      | async/await, asyncio.gather, event loop blocking prevention, TaskGroup                      |
| python-code-explain        | Sync vs async boundaries, GIL, decorator stacking, FastAPI Depends, Django lifecycle, ORM session - injected into `task-code-explain` |
| python-onboard-map         | Dependency manager (poetry/pip/uv/pdm), framework, virtualenv, settings, ORM + migrations, async runtime - injected into `task-onboard` |
| python-fastapi-overengineering-review | Necessity review for FastAPI: Pydantic validators duplicating SQLAlchemy `Mapped[T]` / DB constraints, defensive `None` checks after `scalar_one()` / on typed values, single-impl `Protocol` / `BaseService` / speculative `BaseSettings` / `Result[T]` wrappers, bare `except` defeating the global exception handler. Composed into `task-python-review` Phase D when FastAPI is detected. |
| python-django-overengineering-review | Necessity review for Django: DRF serializer validators duplicating Django ORM `null=False` / model validators / unique constraints, defensive `None` after `.objects.get()`, single-impl `ABC` / `BaseService` / `Result[T]` / multiple serializers, `post_save` signals hiding business logic. Composed into `task-python-review` Phase D when Django is detected. |

## Agents

| Agent                       | Description                                                                                            |
| --------------------------- | ------------------------------------------------------------------------------------------------------ |
| python-architect            | Designs async APIs, repository patterns, SQLAlchemy models, Celery pipelines, project structure        |
| python-tech-lead            | Code review, refactoring guidance, doc standards for Pythonic patterns, type safety, async correctness |
| python-security-engineer    | OWASP Top 10 for Python, JWT/OAuth2 auth review, input validation, dependency vulnerability scan       |
| python-performance-engineer | Async correctness, SQLAlchemy/Django ORM query tuning, Celery throughput, profiling                    |
| python-test-engineer        | pytest strategies, factory_boy fixtures, Testcontainers, async testing, and test pyramid design        |

## Framework Detection

FastAPI is the **primary** framework. Django/DRF is supported as secondary.

Skills detect which framework is in use by checking:

1. **Repo context file** - explicit framework declaration takes priority
2. **File detection** (fallback):
   - `main.py` + `fastapi` imports → FastAPI
   - `manage.py` + `settings.py` → Django
