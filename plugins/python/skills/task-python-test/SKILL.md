---
name: task-python-test
description: "Python test plan and scaffolding with pytest, pytest-asyncio, factory_boy, httpx ASGITransport, DRF APIClient, Testcontainers, Celery."
agent: python-test-engineer
metadata:
  category: backend
  tags: [python, pytest, fastapi, django, testcontainers, factory-boy, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble`. Generate one test per acceptance criterion (tag `# Satisfies: AC<N>`), cover every NFR per `plan.md`, refuse out-of-scope tests. Never edit spec artifacts; surface gaps as proposed amendments.

# Python Test

Stack-specific delegate of `task-code-test` for Python. Preserves the parent contract (output shape, prioritization). Canonical wiring (pytest fixtures, `httpx.ASGITransport`, DRF `APIClient`, factory_boy, Testcontainers, `respx`, Celery test modes) lives in `python-testing-patterns` - this workflow composes, does not restate.

## When to Use

- New FastAPI / Django service or module needs a test strategy
- Coverage gaps across unit / integration / endpoint / Celery layers
- Scaffolding tests for under-covered endpoints, repositories, or auth code
- Boundary tests (validation, authorization, edge cases) for existing happy-path tests

**Not for:** test failure debugging (`task-python-debug`), code review (`task-python-review`), postmortems (`/task-oncall-postmortem`).

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If invoked from `task-code-test`, accept the parent's stack. If not Python, stop and direct to `/task-code-test`.

Detect: FastAPI (`fastapi` import + `main.py`) vs Django (`manage.py` + `settings.py`). Record `Framework: FastAPI | Django | mixed` for output - downstream steps branch on this.

### Step 2 - Read Code and Existing Tests

Ground output in real conventions. For each target, read the module top-to-bottom: public surface, request / response types, security dependencies / `permission_classes`, transaction boundaries, external collaborators.

Glob `tests/**/*.py`. Read at least one endpoint test, one service / repository test, one Celery task test (if applicable), and `conftest.py` files. Note: factory framework (`factory_boy` / `model_bakery` / `polyfactory`), HTTP-stub library (`respx` / `httpx_mock` / `responses`), auth helpers. Read `pyproject.toml` / `pytest.ini` for `[tool.pytest]` config, `asyncio_mode`, markers.

For FastAPI: read `app/core/config.py` test profile and any Testcontainers / `IntegrationTestBase` helper. For Django: read `settings.py` `TEST_RUNNER`, test settings module, `DATABASES`.

If no existing tests, say so and propose conventions explicitly in the strategy doc.

### Step 3 - Python Test Pyramid

| Layer       | Tooling                                                          | Belongs here                                                                              |
| ----------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Unit        | pytest + Mock / pytest-mock                                      | Service logic, Pydantic validators, mappers, pure functions, calculation rules            |
| Integration | pytest + Testcontainers PostgreSQL + real ORM session            | Repository queries, ORM constraints, DB invariants                                        |
| Endpoint    | httpx `ASGITransport` (FastAPI) or DRF `APIClient` (Django)      | Routing, request / response binding, validation, auth dependencies / `permission_classes` |
| Task        | pytest + Celery `task_always_eager` or `pytest-celery` worker    | Celery task happy path, retry, idempotency                                                |
| E2E         | pytest + Testcontainers + real Celery worker / Redis             | Critical journeys only (auth flow, checkout, transactional commit + dispatch)             |
| Contract    | `schemathesis` (FastAPI) / DRF OpenAPI consumer-driven           | API contract vs OpenAPI schema                                                            |

Many unit, some endpoint / integration, few E2E.

### Step 4 - Apply Python Test Patterns

Use skill: `python-testing-patterns` for wiring and code shapes. Per-type strategy rules:

- **Unit**: one test per outcome (success / validation / external fail / edge). No app context or DB - if it needs the app + DB, it is misclassified. `respx` / `httpx_mock` for HTTP; `mocker.patch.object(spec=True)` to catch typo'd method names.
- **Endpoint**: one test per `(method, path, principal-state, outcome)` - happy + 401 + 403 + 4xx-validation. FastAPI: `httpx.ASGITransport` with `app.dependency_overrides` for `get_db` / `get_current_user`. Django: `APIClient` with `force_authenticate` or `client.login`. Per-owner / per-tenant resources get an IDOR (404 for other-user's resource) case.
- **Repository / ORM integration**: Testcontainers PostgreSQL only - never SQLite (JSONB, partial indexes, `ON CONFLICT`, array types diverge). Per-test transactional rollback (SAVEPOINT). Assert PostgreSQL semantics and constraint errors.
- **Pydantic / DRF schemas**: instantiate via constructor or `Schema(**data)` for direct validation; cover unknown-key rejection (`model_config = ConfigDict(extra="forbid")` / DRF serializer `extra_kwargs`), missing required, type mismatch. Faster than full endpoint test.
- **Celery**: `task_always_eager=True` for fast tests; `pytest-celery` real broker when behavior depends on `acks_late=True` / `max_retries` / visibility timeout. Always cover: idempotency (invoke twice, side effect once), retry (fail-fail-success), DLQ. Post-commit dispatched tasks (`transaction.on_commit`): assert they fire after parent commit, not before.
- **E2E**: full-stack flows only (auth, commit + Celery dispatch, scheduled billing). Avoid for what endpoint tests cover.

### Step 5 - Test Boundaries

| Layer       | Test it                                                                                              |
| ----------- | ---------------------------------------------------------------------------------------------------- |
| Unit        | Service logic, mappers, Pydantic / DRF validators, custom `has_permission` / `has_object_permission` |
| Endpoint    | Every endpoint: happy + 401 + 403 + 4xx; pagination / filtering; custom exception handlers           |
| Integration | Non-trivial repository queries, ORM constraints (unique / check / FK), migration smoke on clean DB   |
| Task        | Celery tasks with retry / idempotency / external side effects; chains / groups; post-commit dispatch |

**Skip:** framework internals (FastAPI route resolution, Django URL routing, Pydantic / DRF engines), dataclasses with no logic, trivial delegation (`service.get -> repo.get`).

### Step 6 - Test Data and Fixtures

Factories over `dict(...)` literals (`factory_boy`, `model_bakery`, `polyfactory`). Configure per project: factory_boy session-scoped factory, model_bakery for Django. Pydantic v2: construct directly via keyword args; factories only for nested / repeated cases. Avoid `expire_on_commit` flips in tests - fix fixture isolation instead. 100-row setups signal the test belongs at integration / load-test layer.

### Step 7 - Prioritization (when coverage is low)

Run before scaffolding when coverage is below ~50%. Alphabetic or by-file order leaves auth holes while plumbing gets full coverage.

1. **P1 - AuthN/Z**: 401 anonymous + 403 wrong-role per protected endpoint; JWT / OAuth2 issuer / audience / signature / expiry (FastAPI); DRF `permission_classes` at endpoint + unit for custom classes.
2. **P2 - Data integrity**: integration tests for non-trivial queries; write paths with rollback; Celery idempotency for side-effect tasks.
3. **P3 - Business-critical**: revenue paths, state-machine transitions (Pydantic / `TextChoices`), scheduled billing / notification jobs.
4. **P4 - High-churn**: files with frequent recent commits (`git log --since="3 months ago"`) or bug-fix history.
5. **P5 - Plumbing**: pass-through endpoints, simple CRUD.

### Step 8 - Test Infrastructure Hygiene

- [ ] Testcontainers reused via session-scoped fixture + `testcontainers.reuse=True` in `~/.testcontainers.properties`
- [ ] `pytest-asyncio` `asyncio_mode = "auto"` - no per-test `@pytest.mark.asyncio`
- [ ] Test profile only overrides what differs from prod - never silently disables auth / CSRF / `ValidationPipe`
- [ ] `pytest-xdist` enabled where safe (`-n auto`); stateful tests serialized
- [ ] HTTP stubs via `respx` / `pytest-httpx` / `responses` - one library per project, no real network
- [ ] `pytest --durations=10` reviewed; long fixtures flagged
- [ ] `pytest-cov` wired to CI with per-package thresholds; exclusions documented

## Review Checklist (existing tests)

- [ ] Test type matches subject (endpoint -> ASGI / APIClient, repository -> Testcontainers, service -> unit)
- [ ] Every endpoint: happy + 401 + 403 + validation
- [ ] Non-trivial repository queries integration-tested against Testcontainers, not SQLite
- [ ] Every `permission_classes` / security dependency has passing-and-denied tests
- [ ] Test data via factories, not raw dict literals
- [ ] No internal `mocker.patch(...session.commit)` mocks where Testcontainers could assert real DB state
- [ ] No E2E covering what an endpoint test could
- [ ] No `CELERY_TASK_ALWAYS_EAGER` masking a missing real-broker test for `acks_late=True` tasks

## Output Format

**Which deliverable:**

- "what tests are missing?" / "review coverage" -> Coverage Assessment
- "write tests for X" / "scaffold tests" -> Test Scaffolds
- "test strategy" / "test plan" / coverage < 50% with no scaffolds requested -> Strategy Doc
- Multiple deliverables in one invocation -> produce all, separated by `---`, in order: Coverage Assessment, Strategy Doc, Test Scaffolds
- Unclear -> Strategy Doc as default

**Coverage Assessment:**

```markdown
## Python Test Coverage Assessment

**Stack:** Python <version>
**Framework:** FastAPI <version> | Django <version>
**Test framework:** pytest, pytest-asyncio, factory_boy / model_bakery, Testcontainers
**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Endpoint:** [endpoints missing 401/403/validation paths]
- **Integration:** [non-trivial queries without tests; SQLite for a Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT / OAuth2 flow tests]
- **Celery:** [tasks without tests; tasks without idempotency / retry]
- **Contract:** [OpenAPI / Pact contracts without verification]

**Recommended pyramid balance:**

- Unit: [count target]
- Endpoint + integration: [count target]
- E2E: [count target - keep small]

**Prioritization** _(when coverage < ~50% or > 5 gaps)_

Apply Step 7 risk bands: P1 AuthN/Z, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing.
```

**Test Scaffolds:** ready-to-run pytest files using project conventions. Each scaffold must include the right test type, factories (not dict literals), endpoint coverage = happy + 401 + 403 + validation, repository tests on Testcontainers PostgreSQL, Celery tests with idempotency + retry (real-broker variant for `acks_late=True`), `app.dependency_overrides` in `conftest.py` not invented per-test.

**Strategy Doc:**

```markdown
## Python Test Strategy

**Objective:** [what this achieves]
**Pyramid balance:** Unit {x}% / Endpoint + Integration {y}% / E2E {z}%
**Tooling:** pytest, pytest-asyncio (FastAPI) / pytest-django (Django), factory_boy / model_bakery, Testcontainers PostgreSQL, respx / responses, pytest-celery
**Database isolation:** Testcontainers PostgreSQL + per-test SAVEPOINT rollback
**Concurrency:** [pytest-xdist config]
**Gaps to close (prioritized):**

1. [Highest risk - usually authorization or repository correctness]
2. [...]
```

## Self-Check

**Always:**

- [ ] Stack confirmed Python; Framework (FastAPI / Django / mixed) recorded (Step 1)
- [ ] Code under test + sample existing tests + `conftest.py` read directly (Step 2)
- [ ] `python-testing-patterns` consulted for canonical wiring (Step 4)
- [ ] Auth approach explicit (FastAPI: dependency override or token fixture; Django: `force_authenticate` / `client.login`)
- [ ] Spec-aware mode honored when `--spec` passed (one test per AC, NFR coverage, no out-of-scope)

**Strategy Doc / Coverage Assessment:**

- [ ] Pyramid mapped to Python idioms (Step 3) - no duplicated assertions across layers
- [ ] Risk prioritization applied when coverage is low (Step 7)
- [ ] Testcontainers required for repository tests; SQLite flagged on Postgres apps

**Test Scaffolds:**

- [ ] Factories over dict literals; factory_boy session binding shown when applicable (Step 6)
- [ ] Endpoint scaffolds: happy + 401 + 403 + validation; IDOR for per-owner / per-tenant resources
- [ ] Repository scaffolds on Testcontainers PostgreSQL with per-test SAVEPOINT rollback - never SQLite
- [ ] Celery scaffolds include idempotency + retry; real-broker (`pytest-celery`) variant for `acks_late=True`
- [ ] `app.dependency_overrides` for `get_db` / `get_current_user` shown in `conftest.py`, not invented per-test
- [ ] Pydantic schema unit tests for non-trivial validators or `model_config = ConfigDict(extra="forbid")` contracts

**Review-existing-tests mode:**

- [ ] Review Checklist items addressed for every test file in scope

## Avoid

- Scaffolding without first reading existing tests + `conftest.py` - imports the wrong factory, duplicates the integration base fixture
- Chasing a coverage number instead of prioritizing by risk - 100% lines with no auth tests misses the bigger threat
- E2E for what an endpoint test could cover - context cost compounds
- `requests.get(...)` against a real running server when `ASGITransport` / `APIClient` is faster and deterministic
- Per-test-class factory duplication - share via `tests/factories.py` / `conftest.py`
- `mocker.patch("...session.commit")` internal mocks where Testcontainers could assert real DB state
- Disabling `CsrfViewMiddleware` in Django form tests - test no longer reflects prod config
- Skipping Pydantic validator unit tests because the endpoint has integration - validators are unit-tested for reuse
- Testing framework internals (that `Depends` resolves, that DRF routers route)
