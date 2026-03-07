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

## Success Criteria

A well-executed feature implementation passes all of these. Use as a self-check before presenting to the user.

### Completeness

- [ ] Framework detected (FastAPI or Django) before any code generated
- [ ] Requirements gathered and design approved before code generation
- [ ] All layers generated: migration, model, service, endpoint/view, schema, tests
- [ ] Validated with pytest, linting, and type checking

### Python Correctness

- [ ] Pydantic schemas (FastAPI) or DRF serializers (Django) used for all request/response shaping - no raw ORM objects in responses
- [ ] All async endpoints consistently use `async def` where async IO is involved
- [ ] Type hints present on all function signatures
- [ ] Celery tasks are idempotent if background jobs are included
- [ ] pytest tests cover happy path, validation errors, and not-found scenarios

### Staff-Level Signal

- [ ] Migration includes indexes for foreign keys and filter columns
- [ ] List endpoints include pagination
- [ ] If Celery used, retry config and error classification are included
- [ ] File list, endpoint summary, and test count presented to user

## After This Skill

If the output needed significant adjustment - wrong framework detected, raw ORM objects returned in responses, or async/sync mixing introduced - run `/task-skill-feedback` to log what changed and why.
