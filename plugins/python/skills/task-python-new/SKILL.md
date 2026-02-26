---
name: task-python-new
description: "Create a new Python API resource. Detects FastAPI or Django from project context. Generates model, repository/manager, service, endpoint, Pydantic/serializer schemas, migration, and pytest tests."
agent: python-architect
---

STEP 1 — DETECT FRAMEWORK: check CLAUDE.md or project files (main.py→FastAPI, manage.py→Django)

STEP 2 — GATHER: resource name, fields with types, associations, operations, background jobs needed?

STEP 3 — MIGRATION:
  Load skill: python-migration-safety
  FastAPI: alembic revision --autogenerate
  Django: makemigrations

STEP 4 — MODEL:
  FastAPI: SQLAlchemy 2.0 model (load python-sqlalchemy-patterns)
  Django: Django model with constraints

STEP 5 — DATA ACCESS:
  FastAPI: repository class with async session
  Django: custom Manager / QuerySet methods

STEP 6 — SERVICE: business logic, dependency injection (FastAPI) or explicit calls (Django)

STEP 7 — ENDPOINT:
  FastAPI: APIRouter with Pydantic models (load python-fastapi-patterns)
  Django: ViewSet with serializers (load python-django-patterns)

STEP 8 — SCHEMAS:
  FastAPI: Pydantic Create/Update/Response models
  Django: DRF Create/Update/List/Detail serializers

STEP 9 — TESTS:
  Load skill: python-testing-patterns
  FastAPI: AsyncClient tests + factory_boy
  Django: APIClient tests + factory_boy

STEP 10 — VALIDATE: pytest + ruff/flake8 + mypy

OUTPUT: file checklist
