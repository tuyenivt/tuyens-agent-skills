---
name: python-onboard-map
description: "Python onboarding signals: dependency manager (poetry/pip/uv/pdm), framework (FastAPI/Django/Flask), venv, settings, ORM, async runtime."
metadata:
  category: backend
  tags: [onboarding, codebase-map, python, fastapi, django]
user-invocable: false
---

# Python Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is Python.

## When to Use

Workflow needs Python-specific orientation: dependency tooling, framework, venv, settings, ORM, async vs sync. Project has `pyproject.toml`, `requirements.txt`, `setup.py`, or `Pipfile`.

## Rules

- Detect dependency manager first - lockfile and command set differ.
- Detect framework: FastAPI, Django, Flask, Starlette, Litestar - layout and entry points differ.
- Detect Python version from `requires-python`, `.python-version`, `.tool-versions`, `runtime.txt`, `setup.cfg` `python_requires`, **and** the `Dockerfile` base image; the CI config's version is the reference (no CI config: `requires-python`; neither: list every source and say there is no reference) - flag every source that diverges from it (e.g., `setup.cfg` 3.9 vs CI 3.12) and any source below the Floors in Conventions.
- Conflicting managers (two or more of `requirements.txt`, a Poetry/uv/PDM `pyproject.toml`, `Pipfile`): name every one; the `pyproject.toml` is the forward state when present, otherwise the one with a committed lockfile, and the rest are legacy. Separately, when no lockfile is committed, flag that no reproducible install exists until one lands.
- Detect async vs sync: `async def` endpoints, asyncio, async DB drivers (asyncpg, psycopg 3 async, aiomysql/asyncmy, aiosqlite, PyMongo `AsyncMongoClient`; `motor` is deprecated) vs sync.

## Patterns

### Dependency Manager

| File                             | Manager    | Lockfile            | Commands                                     |
| -------------------------------- | ---------- | ------------------- | -------------------------------------------- |
| `pyproject.toml` + `poetry.lock` | Poetry     | `poetry.lock`       | `poetry install`, `poetry run`, `poetry add` |
| `pyproject.toml` + `uv.lock`     | uv         | `uv.lock`           | `uv sync`, `uv run`, `uv add`                |
| `pyproject.toml` + `pdm.lock`    | PDM        | `pdm.lock`          | `pdm install`, `pdm run`                     |
| `requirements*.txt`              | pip        | none (or pip-tools) | `pip install -r requirements.txt`            |
| `Pipfile` + `Pipfile.lock`       | Pipenv     | `Pipfile.lock`      | `pipenv install`, `pipenv run`               |
| `setup.py` / `setup.cfg`         | setuptools | none                | `pip install -e .`                           |

### Bootstrap

1. Python version: install the CI/pinned version with `pyenv` (`.python-version`), `asdf` (`.tool-versions`), or `uv` (`.python-version` / `requires-python`).
2. Virtualenv: `python -m venv .venv` (or manager auto-creates).
3. Install via detected manager.
4. Local services: `compose.yml` / `.env.example`.
5. Migrations: Alembic `alembic upgrade head` | Django `python manage.py migrate` | Flask-Migrate `flask db upgrade` (Flask-SQLAlchemy without it: no migrations - flag) | Tortoise `aerich upgrade`.
6. Run: FastAPI `uvicorn app.main:app --reload` (:8000) | Django `python manage.py runserver` (:8000) | Flask `flask run` (:5000) | Starlette `uvicorn <module>:app --reload` (:8000) | Litestar `litestar run --reload` (:8000).
7. Verify: `/docs` (FastAPI), `/schema` (Litestar), `/admin/` (Django), `/health` if implemented.
8. **Celery workers** (if in scope): `celery -A app.tasks worker -l info` (Django: `-A <project>`); beat: same `-A` target with `beat -l info`. Endpoints work while background work silently fails - flag a worker missing from local dev.

### Key Files

**FastAPI**

| Location                     | Purpose                                          |
| ---------------------------- | ------------------------------------------------ |
| `app/main.py`                | `FastAPI()` instance; `app.include_router(...)`  |
| `app/api/` or `app/routers/` | `APIRouter` modules                              |
| `app/models/`                | Pydantic models and SQLAlchemy models            |
| `app/db/`                    | Session factory, base model                      |
| `app/core/config.py`         | `Settings` class (Pydantic Settings)             |
| `app/dependencies.py`        | `Depends`-injectable functions (auth, db)        |
| `app/tasks/`                 | Celery app + tasks                               |
| `alembic/versions/`          | Schema migrations                                |
| `pyproject.toml`             | Deps, ruff/mypy/pytest config                    |

**Django**

| Location                     | Purpose                                                        |
| ---------------------------- | -------------------------------------------------------------- |
| `manage.py`                  | CLI entry point                                                |
| `<project>/settings/`        | Settings split by env (`base.py`, `local.py`, `production.py`) |
| `<project>/urls.py`          | Root URL config                                                |
| `<project>/celery.py`        | Celery app (`config_from_object`, `autodiscover_tasks`)        |
| `<app>/models.py`            | Django ORM models                                              |
| `<app>/views.py`, `serializers.py` | Views / DRF ViewSets, serializers                        |
| `<app>/migrations/`          | Auto-generated migrations                                      |
| `<app>/admin.py`             | Admin registration                                             |
| `requirements/`              | Often split: `base.txt`, `dev.txt`, `prod.txt`                 |

**Flask**: `app.py` / `wsgi.py` (app factory + `create_app`), `blueprints/` or per-feature `views.py`, sync `SessionLocal` or Flask-SQLAlchemy `db.session`, config via `app.config` / env. `async def` views run with `flask[async]` (one worker per request, no concurrency gain, also behind an ASGI adapter); real async needs an async-first framework (Quart).

If a `Makefile` is present, treat it as the authoritative command source - `make <target>` wraps install / migrate / run / test with env and `DJANGO_SETTINGS_MODULE` set; read it before suggesting raw commands. Point new engineers at `.env.example` for required env/secrets; when it or the `Makefile` is missing, say so and derive the commands from the manager table. Flag a mismatch between `Makefile`, CI and manifest (a tool CI runs that no manifest declares; tests on SQLite against a PostgreSQL production database).

### Package Layout

- **Feature-package** (preferred for FastAPI / new code): `app/orders/{router,service,repository,schema}.py` - cross-feature imports via public service interfaces.
- **Layer-package** (older / tutorial-shaped): `app/routers/`, `app/services/`, `app/repositories/`, `app/models/` grouped by stereotype. Harder to navigate end-to-end flows.
- **Mixed**: a feature package next to legacy layer dirs - project mid-migration. New code goes in feature side; confirm direction before adding files.

### Conventions

- **Type hints** standard in 3.10+ (`int | None`); strict mode via mypy/pyright. **Settings:** Pydantic Settings (FastAPI) or split modules (Django). **Logging:** `logging` stdlib; `structlog` / `loguru`; JSON for prod. **Lint/format:** ruff (replaces flake8/black/isort); bandit for security. **Testing:** pytest + fixtures; `pytest-asyncio`, `factory_boy`, `httpx` test client; `unittest.TestCase` suites are legacy. **Pre-commit hooks** (`.pre-commit-config.yaml`) common.
- **Floors (2026):** Python 3.11+ (3.10 EOL October 2026; 3.15 latest); FastAPI 0.115+ with Pydantic v2 (v1 `.dict()` / `orm_mode` is drift); SQLAlchemy 2.0+ 2.0-style API, asyncio via `sqlalchemy.ext.asyncio` (2.1 current); Django 5.2 LTS (4.2 LTS ended April 2026; 6.x needs Python 3.12+); uv replacing pip-tools.

### Risk Hotspots

- **Sync I/O / blocking calls inside `async def`** (FastAPI): see `python-async-patterns`.
- **`AsyncSession` lazy-loading + `MissingGreenlet`**: see `python-sqlalchemy-patterns`.
- **Connection budget**: per-process pool x uvicorn workers x replicas + Celery processes vs `max_connections`: see `python-sqlalchemy-patterns`.
- **Django queryset writes that bypass `save()` / signals** (`bulk_create`, `update()`, raw SQL): see `python-django-patterns`.
- **Celery `.delay()` inside an open transaction; `pickle` serializer**: see `python-celery-patterns`.
- **Migration safety on large tables** (full-table locks, unbounded backfills): see `python-migration-safety`.
- **Python footguns**: Pydantic v1 vs v2 drift, mutable default args, settings drift, circular imports, CORS `["*"]` with credentials.

### First-PR Safe Zones

Safe: new FastAPI route in existing router, new Pydantic model, new Django view + URL, new pytest test, new Settings property with safe default.

Riskier: settings/config (cross-env impact), Django migrations (irreversible without reverse), async DB sessions (lazy-loading rules), auth/permissions middleware.

## Output Format

Inject into `task-onboard` sections; invoked standalone, emit the same six headings as `##` sections in this order.

- **Stack and Tooling**: dependency manager + lockfile status (conflicting managers / missing lockfile flagged per Rules), framework + version (manifest pin; `CLAUDE.md` claim noted when it differs), Python version + its reference (CI, else `requires-python`, named) + every source diverging from it or below the Floors, ORM + migration tool, async vs sync, type-check + lint stack.
- **Local Bootstrap**: install, venv path, run, port, health-check, Celery worker/beat when `celery` is a dependency (present in local dev or flagged absent).
- **Architecture Map**: project layout (named per Package Layout), settings structure, app/router boundaries, DB session factory location.
- **Conventions**: type hints, settings, logging, test framework, lint/format stack.
- **Risk Hotspots**: one line per hotspot from Patterns that the repo exhibits: the evidence plus its `see` pointer when it has one.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Treating a `CLAUDE.md` stack claim as the installed version when the manifest pin differs
