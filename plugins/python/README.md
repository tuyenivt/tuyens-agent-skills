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

| Skill             | Agent            | Description                                              |
| ----------------- | ---------------- | -------------------------------------------------------- |
| task-python-new   | python-architect | End-to-end feature implementation across all layers      |
| task-python-debug | python-architect | Debug tracebacks, logs, Celery errors, and test failures |

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

## Agents

| Agent                       | Model  | Description                                                                                      |
| --------------------------- | ------ | ------------------------------------------------------------------------------------------------ |
| python-architect            | sonnet | Designs async APIs, repository patterns, SQLAlchemy models, Celery pipelines, project structure  |
| python-tech-lead            | sonnet | Code review for Pythonic patterns, type safety, async correctness, test coverage                 |
| python-reliability-engineer | sonnet | Incident analysis for FastAPI/Django/Celery/PostgreSQL production environments                   |
| python-security-engineer    | sonnet | OWASP Top 10 for Python, JWT/OAuth2 auth review, input validation, dependency vulnerability scan |
| python-performance-engineer | sonnet | Async correctness, SQLAlchemy/Django ORM query tuning, Celery throughput, profiling              |
| python-refactoring-expert   | sonnet | Systematic Python code improvement: async safety, Pydantic v2 migration, layer boundary cleanup  |
| python-technical-writer     | sonnet | Docstrings (Google style), FastAPI OpenAPI annotations, ADRs, and runbooks for Python services   |
| python-test-engineer        | sonnet | pytest strategies, factory_boy fixtures, Testcontainers, async testing, and test pyramid design  |
| python-code-reviewer        | sonnet | Persistent reviewer with session context - tracks recurring async/FastAPI patterns across PRs    |
| python-sprint-planner       | sonnet | Sprint allocation for Python features with Alembic/Celery complexity awareness                   |
| python-incident-commander   | sonnet | Orchestrates incident response, postmortem, and follow-up tracking for FastAPI/Django systems    |

## Framework Detection

FastAPI is the **primary** framework. Django/DRF is supported as secondary.

Skills detect which framework is in use by checking:

1. **Repo context file** - explicit framework declaration takes priority
2. **File detection** (fallback):
   - `main.py` + `fastapi` imports → FastAPI
   - `manage.py` + `settings.py` → Django
