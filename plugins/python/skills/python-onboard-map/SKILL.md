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
- Detect Python version (`requires-python`, `.python-version`, `runtime.txt`); 3.11+ standard.
- Detect async vs sync: `async def` endpoints, asyncio, async DB drivers (asyncpg, aiomysql, motor) vs sync.

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

1. Python version: `.python-version` / `requires-python` / `runtime.txt` via `pyenv` / `asdf` / `uv`.
2. Virtualenv: `python -m venv .venv` (or manager auto-creates).
3. Install via detected manager.
4. Local services: `compose.yml` / `.env.example`.
5. Migrations: Alembic `alembic upgrade head` | Django `python manage.py migrate` | Tortoise `aerich upgrade`.
6. Run: FastAPI `uvicorn app.main:app --reload` | Django `python manage.py runserver` | Flask `flask run`.
7. Verify: `/docs` (FastAPI), `/admin/` (Django), `/health` if implemented.
8. **Celery workers** (if in scope): `celery -A app.tasks worker -l info`; beat `celery -A app.tasks beat -l info`. Endpoints can work while background work silently fails - flag if the worker isn't part of local dev.

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
| `alembic/versions/`          | Schema migrations                                |
| `pyproject.toml`             | Deps, ruff/mypy/pytest config                    |

**Django**

| Location                     | Purpose                                                        |
| ---------------------------- | -------------------------------------------------------------- |
| `manage.py`                  | CLI entry point                                                |
| `<project>/settings/`        | Settings split by env (`base.py`, `local.py`, `production.py`) |
| `<project>/urls.py`          | Root URL config                                                |
| `<app>/models.py`            | Django ORM models                                              |
| `<app>/views.py` or `views/` | Views                                                          |
| `<app>/migrations/`          | Auto-generated migrations                                      |
| `<app>/admin.py`             | Admin registration                                             |
| `requirements/`              | Often split: `base.txt`, `dev.txt`, `prod.txt`                 |

### Package Layout

- **Feature-package** (preferred for FastAPI / new code): `app/orders/{router,service,repository,schema}.py` - cross-feature imports via public service interfaces.
- **Layer-package** (older / tutorial-shaped): `app/routers/`, `app/services/`, `app/repositories/`, `app/models/` grouped by stereotype. Harder to navigate end-to-end flows.
- **Mixed**: feature-package next to legacy layer dirs - project mid-migration. New code goes in feature side; confirm direction before adding files.

### Conventions

- **Type hints** standard in 3.10+ (`int | None`); strict mode via mypy/pyright.
- **Settings:** Pydantic Settings (FastAPI) or split modules (Django); single instance with env binding.
- **Logging:** `logging` stdlib; `structlog` / `loguru` alternatives. JSON for prod.
- **Lint/format:** ruff (replaces flake8/black/isort); mypy or pyright; bandit for security.
- **Testing:** pytest + fixtures; `pytest-asyncio`, `factory_boy`, `httpx` test client.
- **Pre-commit hooks** (`.pre-commit-config.yaml`) common.

### Risk Hotspots

- **Sync I/O / blocking calls inside `async def`** (FastAPI): see `python-async-patterns`.
- **`AsyncSession` lazy-loading + `MissingGreenlet`**: see `python-sqlalchemy-patterns`.
- **Django queryset writes that bypass `save()` / signals** (`bulk_create`, `update()`, raw SQL): see `python-django-patterns`.
- **Celery `.delay()` inside an open transaction**: see `python-celery-patterns`, `task-python-refactor`.
- **Migration safety on large tables** (full-table locks, unbounded backfills): see `python-migration-safety`.
- **Python footguns**: Pydantic v1 vs v2 drift, mutable default args, settings drift, circular imports.

### First-PR Safe Zones

Safe: new FastAPI route in existing router, new Pydantic model, new Django view + URL, new pytest test, new Settings property with safe default.

Riskier: settings/config (cross-env impact), Django migrations (irreversible without reverse), async DB sessions (lazy-loading rules), auth/permissions middleware.

### Ecosystem Currency

- Python 3.11+ standard; 3.13 latest; 3.10 minimum for modern projects.
- FastAPI 0.110+; Pydantic v2 (significant v1 break).
- SQLAlchemy 2.0 unified API (async-first).
- Django 5.x; LTS is 4.2.
- ruff replacing flake8/black/isort.
- uv replacing pip-tools in newer projects.

## Output Format

Inject into `task-onboard` sections:

- **Stack and Tooling**: dependency manager, framework + version, Python version, ORM + migration tool, async vs sync, type-check + lint stack.
- **Local Bootstrap**: install, venv path, run, port, health-check.
- **Architecture Map**: project layout, settings structure, app/router boundaries, DB session factory location.
- **Conventions**: type hints, settings, logging, test framework, lint/format stack.
- **Risk Hotspots**: sync I/O in async, queryset bypass, circular imports, mutable defaults, settings drift.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Listing dependencies without identifying the manager
- Treating Python 3.8 patterns as current
- Recommending `requests` in async paths
- Confusing FastAPI's `Depends` with Django middleware
- Glossing over sync vs async DB session differences
- Ignoring Pydantic v1/v2 API divergence
