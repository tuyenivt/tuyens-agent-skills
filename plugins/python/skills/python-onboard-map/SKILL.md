---
name: python-onboard-map
description: Python project onboarding signals - dependency manager (poetry/pip/uv/pdm), framework (FastAPI/Django/Flask), virtualenv setup, settings/configuration layout, ORM and migration tool, and async runtime. Used by task-onboard to map a Python codebase for a new engineer.
metadata:
  category: backend
  tags: [onboarding, codebase-map, python, fastapi, django]
user-invocable: false
---

# Python Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Python.

## When to Use

- A workflow needs Python-specific orientation: dependency tooling, framework, virtualenv conventions, settings module/file layout, ORM, async vs sync split.
- Project has `pyproject.toml`, `requirements.txt`, `setup.py`, or `Pipfile`.

## Rules

- Identify dependency manager first: Poetry (`pyproject.toml` with `[tool.poetry]`), pip + requirements (`requirements*.txt`), uv (`uv.lock`), PDM, Pipenv. Each has different lockfile and command set.
- Identify framework before describing layout: FastAPI, Django, Flask, Starlette, Litestar - directory conventions and entry points differ.
- Identify Python version (`pyproject.toml` `requires-python`, `.python-version`, `runtime.txt`); 3.11+ is current standard, 3.12 is mainstream.
- Identify async vs sync: `async def` endpoints, `asyncio` usage, async DB drivers (asyncpg, aiomysql, motor) vs sync.

## Patterns

### Dependency Manager Inventory

| File                       | Manager        | Lockfile            | Common commands                                  |
| -------------------------- | -------------- | ------------------- | ------------------------------------------------ |
| `pyproject.toml` + `poetry.lock` | Poetry   | `poetry.lock`       | `poetry install`, `poetry run`, `poetry add`     |
| `pyproject.toml` + `uv.lock`     | uv       | `uv.lock`           | `uv sync`, `uv run`, `uv add`                    |
| `pyproject.toml` + `pdm.lock`    | PDM      | `pdm.lock`          | `pdm install`, `pdm run`                         |
| `requirements*.txt`        | pip            | none (or pip-tools) | `pip install -r requirements.txt`                |
| `Pipfile` + `Pipfile.lock` | Pipenv         | `Pipfile.lock`      | `pipenv install`, `pipenv run`                   |
| `setup.py` / `setup.cfg`   | setuptools     | none                | `pip install -e .`                               |

### Bootstrap Path

1. Python toolchain: confirm version from `.python-version`, `pyproject.toml` `requires-python`, or `runtime.txt`. Use `pyenv`/`asdf`/`uv` for installation.
2. Virtualenv: `python -m venv .venv && source .venv/bin/activate` (or manager auto-creates). Convention varies.
3. Install: per manager command above.
4. Local services: `compose.yml`, `.env.example`, or settings files for required services.
5. Migrations: `alembic upgrade head` (SQLAlchemy + Alembic), `python manage.py migrate` (Django), `aerich upgrade` (Tortoise).
6. Run:
   - **FastAPI:** `uvicorn app.main:app --reload` (often via `make run` or `poetry run`).
   - **Django:** `python manage.py runserver`.
   - **Flask:** `flask run`.
7. Verify: `/docs` (FastAPI), `/admin/` (Django), `/health` for custom health checks.
8. **Async workers** (if Celery is in scope): `celery -A app.tasks worker -l info` (FastAPI) or `celery -A <project> worker -l info` (Django). Beat / scheduled tasks: `celery -A app.tasks beat -l info`. The web server alone is not the whole runtime - new engineers often see endpoints work but background work silently fail because the worker isn't running locally.

### Key File Inventory

**FastAPI:**

| Location                | Purpose                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `app/main.py`           | `FastAPI()` instance; `app.include_router(...)`                         |
| `app/api/` or `app/routers/` | `APIRouter` modules; one per resource                              |
| `app/models/`           | Pydantic models (request/response) and SQLAlchemy models                |
| `app/db/`               | DB session factory, base model                                          |
| `app/core/config.py`    | `Settings` class (Pydantic Settings) reading env                        |
| `app/dependencies.py`   | `Depends`-injectable functions (auth, db session)                       |
| `tests/`                | pytest tests                                                             |
| `alembic/versions/`     | Schema migrations                                                        |
| `pyproject.toml`        | Dependencies, ruff/mypy/pytest config                                   |

**Django:**

| Location                | Purpose                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `manage.py`             | CLI entry point                                                          |
| `<project>/settings/`   | Settings split by environment (`base.py`, `local.py`, `production.py`)   |
| `<project>/urls.py`     | Root URL config                                                          |
| `<app>/models.py`       | Django ORM models                                                        |
| `<app>/views.py` or `views/` | View functions/classes                                              |
| `<app>/migrations/`     | Auto-generated migrations                                                |
| `<app>/admin.py`        | Django admin registration                                                |
| `requirements/`         | Often split: `base.txt`, `dev.txt`, `prod.txt`                          |

**Package layout convention** - check which the project uses before describing the architecture:

- **Feature-package** (preferred for FastAPI / new code): `app/orders/{router,service,repository,schema}.py` keeps an entire feature in one directory; cross-feature imports go through public service interfaces. Easier to extract a feature later
- **Layer-package** (older convention, common in tutorial-shaped projects): `app/routers/`, `app/services/`, `app/repositories/`, `app/models/` group by stereotype. Harder to navigate end-to-end flows but matches what newcomers expect from older FastAPI tutorials
- **Mixed** (frequent in growing codebases): `app/orders/` (feature-package) sits next to a legacy `app/services/order_service.py` (layer-package). When you find both, the project is mid-migration - new code goes in the feature-package side, edits to legacy code stay in place until a planned refactor. Confirm direction with the team before adding files

### Conventions

- **Type hints** are standard in modern Python (3.10+ uses native `int | None`); strict modes via mypy/pyright.
- **Settings via Pydantic Settings (FastAPI) or split modules (Django).** Single `Settings` instance with env var binding.
- **Logging via `logging` module**; `structlog` and `loguru` are common alternatives. JSON logging for prod.
- **Linters/formatters:** ruff (linter + formatter, replacing flake8/black/isort), mypy or pyright (types), bandit (security).
- **Testing:** pytest with fixtures; `pytest-asyncio` for async tests; `factory_boy` for test data; `httpx` for FastAPI test client.
- **Pre-commit hooks** (`.pre-commit-config.yaml`) commonly used.

### Risk Hotspots Specific to Python

- **Sync I/O in `async def` endpoints (FastAPI):** blocks the event loop, stalls all concurrent requests.
- **`requests` (sync) in async code:** use `httpx.AsyncClient` instead.
- **Sync SQLAlchemy with `AsyncSession`:** lazy loading not supported on async sessions; need `selectinload`/`joinedload`.
- **`bulk_create`/`update()` (Django queryset)** bypassing model `save()` and signals.
- **Circular imports**: especially when models import each other.
- **Missing `__init__.py`** with implicit namespace packages: imports may behave unexpectedly across Python versions.
- **Settings via `env()` calls outside the Settings class**: drift between docs and runtime.
- **Pinned vs unpinned dependencies**: lockfile vs `requirements.in` distinction.
- **`from x import *`** in module init: hides what is exported.
- **Mutable default arguments** (`def f(x=[])`): shared across calls - classic Python footgun.

### First-PR Safe Zones

- New FastAPI route in an existing router with existing patterns.
- New Pydantic model with validation.
- New Django view + template + URL pattern.
- New pytest test for an existing function.
- New property in Settings with a safe default.

Riskier:

- Settings/config: changes affect every environment.
- Django migrations: irreversible without explicit reverse migrations.
- Async DB sessions: lazy loading rules differ from sync.
- Auth/permissions middleware.

### Ecosystem Currency

- Python 3.11+ standard; 3.13 latest, 3.10 minimum for modern projects.
- FastAPI 0.110+; Pydantic v2 (significant API change from v1).
- SQLAlchemy 2.0 unified API (async-first).
- Django 5.x; LTS is 4.2.
- ruff replacing flake8/black/isort in most projects.
- uv replacing pip-tools in newer projects (faster).

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** dependency manager, framework + version, Python version, ORM + migration tool, async vs sync runtime, type-check + lint stack.

**Local Bootstrap:** install command, virtualenv path, run command, default port, health check path.

**Architecture Map:** project layout, settings module structure, app/router boundaries, DB session factory location.

**Conventions:** type hints, settings approach, logging stack, test framework, linter/formatter stack.

**Risk Hotspots:** sync I/O in async, queryset method bypass, circular imports, mutable defaults, settings drift.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Listing dependencies without identifying the manager - commands differ
- Treating Python 3.8 patterns as current
- Recommending `requests` in async code paths
- Confusing FastAPI's `Depends` with Django's middleware
- Glossing over sync vs async DB session differences
- Ignoring Pydantic v1/v2 API divergence
