---
name: task-python-new
description: "End-to-end Python feature implementation. Detects FastAPI or Django. Generates all layers: migrations, models, services, endpoints, schemas, Celery tasks, and comprehensive pytest tests."
agent: python-architect
metadata:
  category: backend
  tags: [python, fastapi, django, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - DETECT FRAMEWORK

STEP 2 - GATHER: feature description, affected models, external integrations, async requirements, background jobs

STEP 3 - DESIGN: propose layers, present for approval
Load: python-sqlalchemy-patterns or python-django-patterns, python-celery-patterns if jobs needed

STEP 4 - DATABASE: load python-migration-safety, generate migration

STEP 5 - MODELS: SQLAlchemy or Django models

STEP 6 - SERVICES: business logic
If async heavy: load python-async-patterns
If background jobs: load python-celery-patterns

STEP 7 - ENDPOINTS: FastAPI routes or Django views

STEP 8 - SCHEMAS: Pydantic or DRF serializers

STEP 9 - TESTS: load python-testing-patterns, comprehensive coverage

STEP 10 - VALIDATE: pytest + linting + type checking

OUTPUT: file list, endpoint summary, test count

## Self-Check

- [ ] Framework detected (FastAPI or Django); requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service, endpoint/view, schema, tests
- [ ] Pydantic schemas or DRF serializers used for all responses - no raw ORM objects
- [ ] All async endpoints use `async def`; type hints on all function signatures
- [ ] pytest, linting, and type checking all pass
- [ ] Migration includes indexes; list endpoints paginated; file list and test count presented

> Run `/task-skill-feedback` if output needed significant correction.
