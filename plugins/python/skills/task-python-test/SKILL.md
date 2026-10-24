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

# Python Test

Risk-prioritized test strategy and scaffolding for Python; canonical wiring lives in `python-testing-patterns`, which this workflow composes.

## When to Use

- New FastAPI / Django service or module needs a test strategy
- Coverage gaps across unit / integration / endpoint / Celery layers
- Scaffolding tests for under-covered endpoints, repositories, or auth code
- Boundary tests (validation, authorization, edge cases) for existing happy-path tests

**Not for:** test failure debugging, code review (`task-python-review`). A production defect noticed while reading code (an unscoped queryset) is an **Out of scope** entry naming `task-python-review`, never a test-quality item.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python (a block supplied by a spawning workflow is used as is). If not Python, stop and name the detected stack so the user can invoke that stack's test workflow. `Framework` comes from the block, checked against the manifest's dependencies (`fastapi` -> FastAPI, `django` -> Django, both -> `mixed`); the manifest wins when it declares both or the block reads `unknown`. Record `Framework: FastAPI | Django | mixed` - downstream steps branch on it. The Python version is the block's `Language` value, else `requires-python`; the framework version is the pinned dependency; each `unknown` without a source; when manifests disagree (`requires-python` vs CI image), name the conflict in one line.

### Step 3 - Read Code and Existing Tests

For each target, read the module: public surface, request / response types, security dependencies / `permission_classes`, transaction boundaries, external collaborators.

Glob `tests/**/*.py`. Read at least one endpoint test, one service / repository test, one Celery task test (if any), and `conftest.py` files. Note: factory framework (`factory_boy` / `model_bakery` / `polyfactory`), HTTP-stub library (`respx` / `pytest-httpx` / `responses`), auth helpers, DB used by tests. Read `pyproject.toml` `[tool.pytest.ini_options]` / `pytest.ini` `[pytest]` for `asyncio_mode`, `asyncio_default_fixture_loop_scope`, markers, `DJANGO_SETTINGS_MODULE`.
FastAPI: read the test settings profile and any Testcontainers fixture in `tests/conftest.py` / `tests/integration/conftest.py`. Django: read the settings module `DJANGO_SETTINGS_MODULE` names and its `DATABASES`.

No existing tests: say so and propose conventions explicitly in the deliverable. An existing suite that conflicts with `python-testing-patterns` Rules (SQLite conftest, `unittest.TestCase`, `event_loop` override): new scaffolds follow the Rules; scaffolds touching the DB or the app (endpoint, DB-backed Celery task) live under `tests/integration/` with their fixtures in `tests/integration/conftest.py`, fully mocked scaffolds under `tests/unit/` (a same-named fixture overrides the legacy root one, which is never edited; a legacy autouse fixture that still applies is named on the **Suite migration** line with the step for the old suite), and existing files stay untouched unless the user asks.

**Coverage measure.** Run `pytest --cov` when the suite runs in this environment; otherwise count public modules with no test referencing them and report the share as `estimated`. "Low coverage" means under ~50% measured or estimated, or more than 5 gaps listed.

### Step 4 - Python Test Pyramid and Boundaries

| Layer       | Tooling                                                       | Test here                                                                                                                   |
| ----------- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Unit        | pytest + pytest-mock                                          | Service logic, mappers, Pydantic / DRF validators, calculation rules, custom `has_permission` / `has_object_permission`     |
| Endpoint    | httpx `ASGITransport` (FastAPI) or DRF `APIClient` (Django)   | Every endpoint: happy + 401 + 4xx-validation (+ 403 where roles exist); pagination / filtering; custom exception handlers    |
| Integration | pytest + Testcontainers PostgreSQL + real ORM session         | Non-trivial repository queries, ORM constraints (unique / check / FK), migration smoke on a clean DB                         |
| Task        | pytest + Celery `task_always_eager` or `pytest-celery` worker | Celery tasks with retry / idempotency / external side effects; chains / groups; post-commit dispatch                         |
| E2E         | pytest + Testcontainers + real Celery worker / Redis          | Critical journeys only (auth flow, checkout, transactional commit + dispatch)                                                |
| Contract    | `schemathesis` (FastAPI) / DRF OpenAPI consumer-driven        | API contract vs OpenAPI schema                                                                                               |

Many unit, some endpoint / integration, few E2E. **Skip:** framework internals (route resolution, Pydantic / DRF engines), dataclasses with no logic, trivial delegation (`service.get -> repo.get`).

### Step 5 - Apply Python Test Patterns

Use skill: `python-testing-patterns` for wiring and code shapes. Per-type strategy rules:

- **Unit**: one test per outcome (success / validation / external fail / edge). No app context or DB; needing them means misclassified. HTTP stub keyed to the client (`respx` / `pytest-httpx` for httpx, `responses` for requests); `mocker.patch.object(Target, "attr", autospec=True)` to catch typo'd names and wrong signatures.
- **Endpoint**: one test per `(method, path, principal-state, outcome)` - happy + 401 + 4xx-validation, plus 403 when the app has a role model (no roles -> the 403 case is N/A, written as such). FastAPI: `httpx.ASGITransport` with `app.dependency_overrides` for `get_db` / `get_current_user`. Django: `APIClient` with `force_authenticate` or `client.login`. Per-owner / per-tenant resources get an IDOR case (404 for another user's resource). An endpoint the code leaves unprotected, or any production defect a scaffold would otherwise assert as correct, gets the expected-behaviour test marked `pytest.mark.xfail(strict=True)` plus an **Out of scope** line.
- **Repository / ORM integration**: Testcontainers PostgreSQL only - never SQLite (JSONB, arrays, `FOR UPDATE SKIP LOCKED`, timezone handling and type enforcement diverge). Per-test transactional rollback (SAVEPOINT). Assert PostgreSQL semantics and constraint errors.
- **Pydantic / DRF schemas**: instantiate directly (`Schema(**data)` / `Serializer(data=...)`); cover unknown-key rejection (`model_config = ConfigDict(extra="forbid")`; DRF ignores unknown keys by default, so test the `validate()` that raises on `set(self.initial_data) - set(self.fields)`), missing required, type mismatch.
- **Celery**: `task_always_eager=True` for fast tests; `pytest-celery` real broker when behavior depends on `acks_late=True` / `max_retries` / visibility timeout. Always cover: idempotency (invoke twice, side effect once), retry (fail-fail-success), terminal failure after `max_retries` (final exception; dead-letter routing only when the queue declares `x-dead-letter-exchange`). Post-commit dispatched tasks: assert they fire after the parent commit.
- **E2E**: full-stack flows only (auth, commit + Celery dispatch); never what endpoint tests cover.

### Step 6 - Test Data and Fixtures

Factories over `dict(...)` literals (`factory_boy`, `model_bakery`, `polyfactory`), shared via `tests/factories.py`. SQLAlchemy: `SQLAlchemyModelFactory` bound to the per-test `db_session` by an autouse fixture; Django: `DjangoModelFactory` / model_bakery. Pydantic v2: keyword args; factories only for nested / repeated cases. The test session's `expire_on_commit` equals the production sessionmaker's (the canonical async `db_session` uses `False`) - never flipped to mask an isolation bug. 100-row setups belong at the integration / load-test layer. Only scaffolds that touch the DB carry the Testcontainers fixture.

### Step 7 - Prioritization (low coverage)

Run before scaffolding when coverage is low (Step 3 measure).

1. **P1 - AuthN/Z**: 401 anonymous per protected endpoint, 403 wrong-role where roles exist; JWT / OAuth2 issuer / audience / signature / expiry (FastAPI); DRF `permission_classes` at endpoint + unit for custom classes.
2. **P2 - Data integrity**: integration tests for non-trivial queries; write paths with rollback; Celery idempotency for side-effect tasks.
3. **P3 - Business-critical**: revenue paths, state-machine transitions (Pydantic / `TextChoices`), scheduled billing / notification jobs.
4. **P4 - High-churn**: files with frequent recent commits (`git log --since="3 months ago"`) or bug-fix history; a history with no standout file (one squashed commit, uniform counts) skips this band.
5. **P5 - Plumbing**: pass-through endpoints, simple CRUD.

### Step 8 - Test Infrastructure Hygiene (Scaffolds and Strategy Doc)

- [ ] Testcontainers started once per pytest session (one per xdist worker) via a session fixture
- [ ] `pytest-asyncio` `asyncio_mode = "auto"` - no per-test `@pytest.mark.asyncio`
- [ ] Test profile only overrides what differs from prod - never disables auth / CSRF / request validation / throttling
- [ ] `pytest-xdist` enabled where safe (`-n auto`); stateful tests serialized
- [ ] HTTP stubs keyed to the client (Step 5) - no real network
- [ ] `pytest --durations=10` reviewed; long fixtures flagged
- [ ] `pytest-cov` wired to CI with `--cov-fail-under` (one total); per-package floors as separate `coverage report --include='app/<pkg>/*' --fail-under=N` steps; exclusions documented

## Review Checklist (existing tests)

An item with no matching surface (CSRF on a JWT-only API) is N/A, not an issue; a defect outside the list that breaks a `python-testing-patterns` Rule (a session-scoped mutated fixture, a `TestCase` class) is an issue.

- [ ] Test type matches subject (endpoint -> ASGI / APIClient, repository -> Testcontainers, service -> unit)
- [ ] Every endpoint: happy + 401 + validation, plus 403 where roles exist
- [ ] Non-trivial repository queries integration-tested against Testcontainers, not SQLite
- [ ] Every `permission_classes` / security dependency has passing-and-denied tests
- [ ] Test data via factories, not raw dict literals
- [ ] No internal `mocker.patch(...session.commit)` mocks where Testcontainers could assert real DB state
- [ ] Assertions check the body and persisted state, not the status code alone
- [ ] No E2E covering what an endpoint test could
- [ ] No `CELERY_TASK_ALWAYS_EAGER` masking a missing real-broker test for `acks_late=True` tasks
- [ ] CSRF-protected Django form views have one `Client(enforce_csrf_checks=True)` test - the default test `Client` skips CSRF

## Output Format

**Which deliverable:**

- "review existing tests" / "test quality" -> Coverage Assessment with **Test-quality issues** (run the Review Checklist; each failing item or broken Rule is one issue; Steps 4-8 reference only)
- "what tests are missing?" / "review coverage" -> Coverage Assessment
- "write tests for X" / "scaffold tests" -> Test Scaffolds
- "test strategy" / "test plan" / low coverage with no scaffolds requested -> Strategy Doc
- Multiple deliverables in one invocation -> produce all, separated by `---`, in order: Coverage Assessment, Strategy Doc, Test Scaffolds
- Unclear -> Strategy Doc as default

Brace annotations are authoring notes, never emitted; a line whose condition fails is omitted. Every deliverable opens, under its own `##` heading, with the same four-bullet header block shown in the Coverage Assessment.

**Coverage Assessment:**

```markdown
## Python Test Coverage Assessment

- **Stack:** Python <version>
- **Framework:** FastAPI <version> | Django <version> | mixed (FastAPI <version> + Django <version>)
- **Test framework:** pytest <plugins detected>; factories: factory_boy | model_bakery | polyfactory | none; HTTP stubs: respx | pytest-httpx | responses | none; DB: Testcontainers PostgreSQL | SQLite | other
- **Coverage:** <N>% measured | ~<N>% covered, estimated (<untested> of <modules> modules untested)

**Coverage gaps:**

- **Unit:** [services / validators / mappers without coverage]
- **Endpoint:** [endpoints missing 401 / 403 / validation paths]
- **Integration:** [non-trivial queries without tests; SQLite for a Postgres app]
- **Auth:** [endpoints without authorization tests; missing JWT / OAuth2 flow tests]
- **Celery:** [tasks without tests; tasks without idempotency / retry / terminal-failure cases]
- **Contract:** [OpenAPI / Pact contracts without verification]

**Test-quality issues**   {review mode only}

- [one line per failing Review Checklist item or broken `python-testing-patterns` Rule, with `file:line`]

**Recommended pyramid balance:**

- Unit: [count target]
- Endpoint + integration: [count target]
- E2E: [count target - keep small]

**Prioritization**   {low coverage only}

1. P1 AuthN/Z: [gaps]
2. P2 Data integrity: [gaps]
3. P3 Business-critical: [gaps]
4. P4 High-churn: [gaps, or `skipped - flat history`]
5. P5 Plumbing: [gaps]

**Notes**   {when either bullet exists}

- **Suite migration:** [existing-suite conflict and the step]   {when the existing suite conflicts with the Rules}
- **Out of scope:** [per defect: file:line - defect - `task-python-review`]   {when a production defect was noticed}
```

**Test Scaffolds:**

```markdown
## Python Test Scaffolds

[the header block]

[the `## Test Plan` block from `python-testing-patterns`]

[ready-to-run pytest files using project conventions, one fenced file each with its path]

- **Conventions followed:** [factory / stub / auth helper reused from the existing suite]
- **Dev dependencies to add:** [package list for `pyproject.toml` / `requirements-dev.txt`, or `none`]
- **Hygiene gaps:** [Step 8 items failing, or `none`]
- **Suite migration:** [existing-suite conflict and the step]   {when the existing suite conflicts with the Rules}
- **Out of scope:** [per defect: file:line - defect - `task-python-review`]   {when a production defect was noticed}
```

Each scaffold uses the right test type, factories, endpoint coverage = happy + 401 + validation (+ 403 where roles exist; IDOR for per-owner resources), repository tests on Testcontainers PostgreSQL, Celery tests with idempotency + retry + terminal failure (real broker for `acks_late=True`), `app.dependency_overrides` in `conftest.py` not invented per test; under low coverage, files ordered by Step 7 band.

**Strategy Doc:**

```markdown
## Python Test Strategy

[the header block]

- **Objective:** [what this achieves]
- **Pyramid balance:** Unit <x>% / Endpoint + Integration <y>% / E2E <z>%
- **Tooling:** pytest, pytest-asyncio (FastAPI) | pytest-django (Django) | both (mixed), factory_boy | model_bakery, Testcontainers PostgreSQL, respx | pytest-httpx | responses
- **Celery tooling:** pytest-celery   {when Celery is present}
- **Database isolation:** Testcontainers PostgreSQL + per-test SAVEPOINT rollback
- **Concurrency:** [pytest-xdist config]
- **Suite migration:** [steps to move an existing SQLite / unittest suite]   {when the existing suite conflicts with the Rules}
- **Out of scope:** [per defect: file:line - defect - `task-python-review`]   {when a production defect was noticed}

**Gaps to close (prioritized):**

1. [Highest risk - usually authorization or repository correctness]
2. [...]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed Python; `Framework` (FastAPI / Django / mixed) and version recorded from stack-detect or the manifest
- [ ] Step 3: code under test, sample existing tests, `conftest.py`, pytest config read; test framework, factories, stubs, DB noted for the header block; coverage measured or estimated; suite conflicts recorded as a migration step
- [ ] Step 4: pyramid mapped to Python idioms; framework internals and trivial delegation skipped; no duplicated assertions across layers
- [ ] Step 5: `python-testing-patterns` consulted; auth approach explicit (FastAPI: dependency override or token fixture; Django: `force_authenticate` / `client.login`); 403 required only where roles exist
- [ ] Step 6: factories over dict literals, bound to the per-test session; `expire_on_commit` matches prod
- [ ] Step 7: risk bands applied when coverage is low
- [ ] Step 8: hygiene items checked when producing Scaffolds or a Strategy Doc; failures on the Scaffolds' Hygiene gaps line or under the Strategy Doc's Gaps to close
- [ ] Scaffolds: `## Test Plan` precedes the files; the scaffold contract met; dev dependencies listed
- [ ] Review mode: Review Checklist applied to every test file in scope; production defects routed to **Out of scope**

## Avoid

- `requests.get(...)` against a real running server when `ASGITransport` / `APIClient` is faster and deterministic
