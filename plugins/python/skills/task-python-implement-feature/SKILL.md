---
name: task-python-implement-feature
description: "End-to-end Python feature implementation. Detects FastAPI or Django. Generates all layers: migrations, models, services, endpoints, schemas, Celery tasks, and comprehensive pytest tests."
agent: python-architect
---

STEP 1 — DETECT FRAMEWORK

STEP 2 — GATHER: feature description, affected models, external integrations, async requirements, background jobs

STEP 3 — DESIGN: propose layers, present for approval
  Load: python-sqlalchemy-patterns or python-django-patterns, python-celery-patterns if jobs needed

STEP 4 — DATABASE: load python-migration-safety, generate migration

STEP 5 — MODELS: SQLAlchemy or Django models

STEP 6 — SERVICES: business logic
  If async heavy: load python-async-patterns
  If background jobs: load python-celery-patterns

STEP 7 — ENDPOINTS: FastAPI routes or Django views

STEP 8 — SCHEMAS: Pydantic or DRF serializers

STEP 9 — TESTS: load python-testing-patterns, comprehensive coverage

STEP 10 — VALIDATE: pytest + linting + type checking

OUTPUT: file list, endpoint summary, test count
