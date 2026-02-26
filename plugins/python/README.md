# Tuyen's Agent Skills - Python

Claude Code plugin for Python development.

## Stack

- **Primary:** Python 3.11+, FastAPI + async
- **Secondary:** Django + DRF
- **ORM / Migrations:** SQLAlchemy 2.0+ / Alembic
- **Testing:** pytest
- **Task Queue:** Celery
- **Database:** PostgreSQL

## Installation

Install the core plugin first, then this plugin:

```
/plugin install core@tuyens-agent-skills
/plugin install python@tuyens-agent-skills
```

## Optional: Share Skills Between Claude Code and Codex

Claude Code and Codex use the same `agentskills.io` format. You can create a symbolic link so Codex reuses the skills managed by Claude Code.

```bash
# Unix (Linux/macOS)
ln -s "$HOME/.claude/plugins/marketplaces/tuyens-agent-skills/plugins/python/skills" "$HOME/.codex/skills/tuyens-agent-skills-python-skills"

# Windows
mklink /J "%USERPROFILE%\.codex\skills\tuyens-agent-skills-python-skills" "%USERPROFILE%\.claude\plugins\marketplaces\tuyens-agent-skills/plugins/python/skills"
```

## Workflow Skills

| Skill                         | Agent            | Description                                                                           |
| ----------------------------- | ---------------- | ------------------------------------------------------------------------------------- |
| task-python-new               | python-architect | Create a new API resource (model, repo, service, endpoint, schemas, migration, tests) |
| task-python-implement-feature | python-architect | End-to-end feature implementation across all layers                                   |
| task-python-debug             | python-architect | Debug tracebacks, logs, Celery errors, and test failures                              |

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

| Agent                       | Model  | Description                                                                                     |
| --------------------------- | ------ | ----------------------------------------------------------------------------------------------- |
| python-architect            | sonnet | Designs async APIs, repository patterns, SQLAlchemy models, Celery pipelines, project structure |
| python-tech-lead            | sonnet | Code review for Pythonic patterns, type safety, async correctness, test coverage                |
| python-reliability-engineer | sonnet | Incident analysis for FastAPI/Django/Celery/PostgreSQL production environments                  |

## Framework Detection

FastAPI is the **primary** framework. Django/DRF is supported as secondary.

Skills detect which framework is in use by checking:

1. **CLAUDE.md** — explicit framework declaration takes priority
2. **File detection** (fallback):
   - `main.py` + `fastapi` imports → FastAPI
   - `manage.py` + `settings.py` → Django
