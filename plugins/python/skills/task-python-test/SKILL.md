---
name: task-python-test
description: Python test strategy and scaffolding using pytest, pytest-asyncio, factory_boy / model_bakery, httpx ASGITransport (FastAPI) or DRF APIClient (Django), Testcontainers PostgreSQL, and Celery testing. Detects FastAPI vs Django and applies the right idioms. Use when designing a test plan, assessing coverage gaps, or scaffolding endpoint/service/task/security tests. Stack-specific override of task-code-test, invoked when stack-detect resolves to Python.
agent: python-test-engineer
metadata:
  category: backend
  tags: [python, pytest, fastapi, django, testcontainers, factory-boy, testing, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the code under test, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, generate one test per acceptance criterion (use `# Satisfies: AC<N>` mapping or test-name suffix), cover every NFR with a verification step from `plan.md`, and refuse to generate tests for behavior the spec marks out-of-scope. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface coverage gaps as proposed amendments.

# Python Test

## Purpose

Python-aware test strategy and scaffolding using pytest idioms, `pytest-asyncio` (FastAPI), DRF `APIClient` (Django), Testcontainers PostgreSQL, factory_boy / model_bakery / Polyfactory for test data, `respx` / `httpx_mock` for HTTP stubs, and Celery `task_always_eager` / pytest fixtures for task tests. Replaces the generic backend test patterns with Python-specific guidance.

This workflow is the stack-specific delegate of `task-code-test` for Python. The core workflow's contract (output shape, prioritization rules) is preserved so callers see a stable shape.

## When to Use

- Designing a test strategy for a new FastAPI or Django service / module
- Assessing test coverage gaps across unit / integration / endpoint / Celery layers
- Scaffolding tests for under-covered endpoints, services, repositories, or auth code
- Reviewing test pyramid balance for a Python app
- Adding boundary tests (validation, authorization, edge cases) to existing happy-path tests

**Not for:**

- Test failure debugging (use `task-python-debug`)
- General code review (use `task-code-review` / `task-python-review`)
- Production incident postmortems (use `/task-oncall-postmortem`)

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If the detected stack is not Python, stop and tell the user to invoke `/task-code-test` instead.

Detect framework: FastAPI (`fastapi` import + `main.py`) vs Django (`manage.py` + `settings.py`). Record `Framework: FastAPI | Django | mixed` for the output. Each section that follows branches on this signal where the test idiom differs.

### Step 2 - Read the Code Under Test and Existing Tests

Before producing assessment, scaffolds, or strategy, open both the production code in scope and a representative sample of existing tests. This grounds the output in real conventions instead of generic templates.

- For each target named by the user, read the module top-to-bottom: public functions / classes, request / response types, security dependencies / `permission_classes`, transaction boundaries, external collaborators
- Glob `tests/**/*.py` and read at least: one existing endpoint test, one existing service / repository test, one existing Celery task test (if applicable), `conftest.py` files - learn the project's package layout, factory framework (`factory_boy` vs `model_bakery` vs `polyfactory`), HTTP-stub library (`respx` vs `httpx_mock` vs `pytest-httpx`), authentication helpers
- Read `pyproject.toml` / `pytest.ini` / `setup.cfg` for `[tool.pytest]` config, `asyncio_mode`, markers, coverage config
- Read `conftest.py` at repo root and per-package level for shared fixtures (`db_session`, `client`, `current_user`, factory autouse)
- For Django: read `settings.py` `TEST_RUNNER`, `DATABASES`, test settings module; for FastAPI: read `app/core/config.py` test profile and any `TestContainersConfig` / `IntegrationTestBase` helper

If the project has no existing tests, say so and propose conventions explicitly in the strategy doc rather than inventing them silently.

### Step 3 - Python Test Pyramid

The Python test pyramid maps to test types:

| Layer       | Tooling                                                          | What belongs here                                                                         |
| ----------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Unit        | Plain pytest + Mock / pytest-mock                                | Service business logic, Pydantic validators, mappers, pure functions, calculation rules   |
| Integration | pytest + Testcontainers PostgreSQL + real ORM session            | Repository queries, ORM constraints, DB-level invariants                                  |
| Endpoint    | httpx `ASGITransport` (FastAPI) or DRF `APIClient` (Django)      | Routing, request / response binding, validation, auth dependencies / `permission_classes` |
| Task        | pytest + Celery `task_always_eager` or fixture-based worker      | Celery task happy path, retry logic, idempotency                                          |
| E2E         | pytest + Testcontainers + real Celery worker / Redis             | Critical user journeys only - signup, checkout, payment                                   |
| Contract    | `schemathesis` (FastAPI) / DRF `OpenAPIRenderer` consumer-driven | API contract validation against OpenAPI schema                                            |

**Many** unit tests, **some** endpoint / integration tests, **few** full E2E tests.

### Step 4 - Apply Python Test Patterns

Use skill: `python-testing-patterns` for the canonical patterns referenced below.

**Unit tests (`tests/unit/`):**

- pytest (`@pytest.mark.parametrize`, fixtures); `pytest-mock` `mocker` over manual `unittest.mock.patch`
- Test the public function / method - one test per outcome (success, validation failure, external failure, edge case)
- **No app context / DB** - if a unit test needs the FastAPI app or Django settings, it is misclassified
- Stub external HTTP via `respx` (httpx) or `responses` (requests); do not stub repositories with full SQL behavior - use Testcontainers for that

**FastAPI endpoint tests:**

- `httpx.AsyncClient` with `ASGITransport(app=app)` (httpx 0.27+); `pytest-asyncio` `asyncio_mode = "auto"` to avoid decorating every test
- One test per `(method, path, principal-state, outcome)` triple
- Authentication via fixture that sets the `Authorization` header or overrides `Depends(get_current_user)` via `app.dependency_overrides`
- Authorization: a separate test for "anonymous → 401" and "wrong role → 403" per protected endpoint
- Validation: a "rejects invalid payload" test for any endpoint with a Pydantic body schema
- Response shape: assert key fields, status, headers, and `Content-Type`
- DB session: override `Depends(get_db)` to point at the Testcontainers session fixture; transactional rollback per test

**Django endpoint tests (DRF):**

- `rest_framework.test.APIClient` with `client.force_authenticate(user=...)` or `client.login(...)`
- One test per `(method, url, principal, outcome)` triple
- `pytest-django` `db` / `transactional_db` fixture for database access; `django_db` marker for fast rollback
- Authentication: `@pytest.fixture` returning an authenticated client; per-permission cases (admin, regular user, anonymous)
- Validation: assert `response.status_code == 400` and key error fields
- Permissions: assert 401 unauth, 403 wrong-role, 404 IDOR-attempt (object-level perm denies before exposing existence)

**Repository / ORM integration tests:**

- Testcontainers PostgreSQL (`testcontainers[postgresql]`) - **not SQLite, not in-memory** - SQLite diverges from PostgreSQL on JSON / JSONB, partial indexes, window functions, `ON CONFLICT`, array types
- Per-test transactional rollback via fixture (`session.begin_nested()` / Django `transactional_db` with savepoint)
- One test per non-trivial query: assert SQL semantics (filter correctness, sort order, eager-load result), not just "method returns something"
- N+1 detection: enable `engine.echo=True` or use `sqlalchemy.event` listener counting queries; for Django, `django.test.TestCase.assertNumQueries` or `CaptureQueriesContext`
- Custom indexes / constraints: insert violating data and assert the right exception is raised

**Pydantic schema tests (FastAPI):**

- Direct schema validation: `OrderCreate.model_validate({...})` returns the model or raises `ValidationError`
- Edge cases: missing fields, wrong types, out-of-range values, `extra="forbid"` rejecting unknown keys
- Custom validators (`@field_validator`, `@model_validator`) tested in isolation - faster than going through a full endpoint test

**DRF serializer tests (Django):**

- `serializer.is_valid()` returns False for invalid payloads; `serializer.errors` keys asserted
- `read_only_fields` not writable; `write_only_fields` not in serialized output
- Object-level permissions tested via `has_object_permission` directly when complex

**Celery task tests:**

- `CELERY_TASK_ALWAYS_EAGER = True` for synchronous-execution tests (fast, no broker)
- `pytest-celery` for tests that need a real worker (broker integration, `acks_late` semantics)
- Idempotency test: invoke the task twice with the same input, assert side effect happens once
- Retry test: stub the external call to fail twice then succeed; assert task completes; assert `self.request.retries` increments
- DLT / max-retries test: stub the external call to fail forever; assert task ends in failure state without infinite loop

**E2E / full-context tests:**

- Reserve for tests that genuinely need the full stack: auth flow end-to-end, transactional commit + Celery dispatch, scheduled-job behavior
- Use `pytest-docker` or `testcontainers` to spin up the broker / Redis / Postgres
- Avoid for tests that an endpoint test could cover - context-load cost compounds

### Step 5 - Test Boundaries (Python-Specific)

**What deserves a unit test:**

- Service logic, mappers, Pydantic validators, DRF serializer validators, custom permission classes (the `has_permission` / `has_object_permission` logic in isolation)
- Domain rules, calculation, state-machine transitions
- Framework-independent helpers / utilities

**What deserves an endpoint test:**

- Every endpoint: happy path + 401 + 403 + 4xx validation
- Pagination contract (`limit` / `offset` or cursor)
- Filtering / sorting / search query params
- Custom error handlers (`@app.exception_handler` / DRF `EXCEPTION_HANDLER`)

**What deserves an integration / Testcontainers test:**

- Every repository method with a non-trivial query (filter on multiple columns, eager-load, aggregate)
- ORM constraints (unique, check, FK ON DELETE behavior)
- Migration smoke test: apply all migrations on a clean Testcontainers DB; useful when migrations are squashed

**What deserves a Celery test:**

- Every task with retry logic, idempotency requirements, or external side effects
- Tasks chained / grouped / chorded - assert the workflow completes and aggregates correctly
- Tasks dispatched via `transaction.on_commit` / post-commit dispatch - assert they fire after the parent commits, not before

**What does NOT need a test:**

- Framework-provided behavior: FastAPI route resolution, Django URL routing, default Pydantic / DRF validation rule engines (test that you wired things correctly via endpoint tests, not that the framework works)
- Generated boilerplate: dataclasses with no logic, `@property` getters with one return statement
- Trivial delegation: `service.get(id) -> repository.get(id)` with no logic

### Step 6 - Test Data and Fixtures

- Prefer factory frameworks (`factory_boy`, `model_bakery`, or `polyfactory`) over hand-rolled `dict(...)` literals; configure factories per project convention (factory_boy session-scoped factory, model_bakery for Django)
- For repository tests with Testcontainers, use factories to insert; isolate per-test data inside the test
- Pydantic v2: instantiate directly via constructor with positional / keyword args - factories only for nested / repeated cases
- **Avoid `expire_on_commit` flips** in tests - fix the fixture isolation instead
- Test data must be minimal and focused - 100-row `IntStream`-equivalent setups signal the test belongs at integration / load-test layer

### Step 7 - Prioritization (when coverage is low)

If line coverage (or your equivalent project signal) is below ~50%, **run this step before scaffolding** - it determines _which_ tests to scaffold first. Scaffolding alphabetically or by file is wrong when authorization holes go untested while plumbing endpoints get full coverage.

When starting from low test coverage, prioritize by Python-specific risk:

**Priority 1 - Authorization and authentication:**

- Endpoint test per protected endpoint asserting 401 anonymous + 403 wrong-role
- OAuth2 / JWT flow tests covering issuer, audience, signature, expiry validation (FastAPI)
- DRF `permission_classes` tested at the endpoint level; custom permission classes unit-tested

**Priority 2 - Data integrity:**

- Repository / ORM integration tests for every non-trivial query
- Service tests for write operations (one happy path + one rollback per write)
- Celery task idempotency for any task with side effects

**Priority 3 - Business-critical flows:**

- Revenue paths (checkout, billing, subscription state transitions)
- State-machine transitions (Pydantic / Django enum / `TextChoices`)
- Scheduled jobs touching billing or notifications

**Priority 4 - High-churn code:**

- Files with frequent recent commits (`git log --since="3 months ago"`)
- Files with bug-fix history (`git log --grep="fix"`)

**Priority 5 - Plumbing:**

- Pass-through endpoints, simple CRUD - lower risk, can wait

### Step 8 - Test Infrastructure Hygiene

- [ ] Testcontainers reused across tests via session-scoped fixture and `testcontainers.reuse=True` in `~/.testcontainers.properties` for local fast cycles
- [ ] `pytest-asyncio` `asyncio_mode = "auto"` so individual tests do not need `@pytest.mark.asyncio` decorators
- [ ] Test profile / settings overrides only what differs from prod - never silently disables auth / CSRF
- [ ] pytest parallelism (`pytest-xdist`) enabled where safe (`-n auto`); per-test isolation for stateful tests
- [ ] Mock strict-spec mode: `pytest-mock` `mocker.patch.object(spec=True)` to catch typo'd method names
- [ ] HTTP stubs via `respx` (httpx) / `pytest-httpx` / `responses` (requests); never real network calls
- [ ] `pytest --durations=10` reviewed; long-running fixtures flagged for refactoring
- [ ] Coverage tool (coverage.py / `pytest-cov`) wired to CI with per-package thresholds; coverage exclusions documented

## Python Review Checklist

Quick-reference checklist for reviewing existing Python tests:

- [ ] Test type matches what is being tested (endpoint -> ASGI / APIClient, repository -> Testcontainers, service -> unit + mocks)
- [ ] Every endpoint has at least happy + 401 + 403 + validation-error
- [ ] Every non-trivial repository query has an integration test against Testcontainers (not SQLite)
- [ ] Every `permission_classes` / security dependency has a passing-and-denied test
- [ ] Test data created via factories, not raw dict literals
- [ ] No `verify(repository).save(any())`-style mocks when an integration test could assert real DB state
- [ ] No full-stack E2E tests for what an endpoint test could cover
- [ ] No `CELERY_TASK_ALWAYS_EAGER` masking a missing real-broker test for at-least-once semantics

## Output Format

**Which output to produce:**

- User asks "what tests are missing?" or "review our test coverage" -> Coverage Assessment
- User asks "write tests for X" or "scaffold tests" -> Test Scaffolds
- User asks "test strategy", "test plan", or coverage is below 50% with no scaffolds requested -> Strategy Doc (optionally include Coverage Assessment)
- User asks for **two or more deliverables in the same invocation** ("review coverage AND scaffold tests", "what's missing and write the tests") -> produce them in this order, separated by a horizontal rule (`---`): Coverage Assessment, then Strategy Doc (if requested), then Test Scaffolds. Do not silently drop one.
- If unclear, produce Strategy Doc as the default.

**Coverage Assessment:**

```markdown
## Python Test Coverage Assessment

**Stack:** Python <version>
**Framework:** FastAPI <version> | Django <version>
**Test framework:** pytest, pytest-asyncio, factory_boy / model_bakery, Testcontainers
**Coverage gaps:**

- **Unit tests:** [services / validators / mappers without test coverage]
- **Endpoint tests:** [endpoints without tests; endpoints missing 401/403/validation paths]
- **Integration tests:** [repositories with non-trivial queries without tests; tests running on SQLite for a Postgres app]
- **Auth tests:** [endpoints without authorization tests; missing JWT / OAuth2 flow tests]
- **Celery tests:** [tasks without tests; tasks without idempotency / retry tests]
- **Contract tests:** [OpenAPI / Pact contracts without verification]

**Recommended pyramid balance:**

- Unit (services, validators, helpers): [count target]
- Endpoint + integration (ASGI / APIClient + Testcontainers): [count target]
- E2E (full stack with broker / Redis): [count target - keep small]

**Prioritization** _(include when current coverage is below ~50% or the assessment surfaces > 5 gaps)_

Apply the Step 7 risk bands. Order follow-up work as:

1. **P1 - Authorization & authentication:** [list specific endpoints / flows missing 401/403/ownership tests]
2. **P2 - Data integrity:** [repositories with non-trivial queries / write paths without rollback tests / Celery tasks with unguarded side effects]
3. **P3 - Business-critical flows:** [revenue, state machines, scheduled jobs touching billing or notifications]
4. **P4 - High-churn code:** [files with frequent recent commits or bug-fix history]
5. **P5 - Plumbing:** [pass-through endpoints / simple CRUD - lowest risk]
```

**Test Scaffolds** (when generating boilerplate):

Produce ready-to-run pytest test files using project conventions. Each scaffold must include:

- The right test type (endpoint / integration / unit / Celery)
- Factories for test data instead of raw dict literals
- For endpoint tests: happy path + 401 + 403 + validation-error
- For repository tests: Testcontainers PostgreSQL; assertions against PostgreSQL semantics
- For auth tests: anonymous + wrong-role + correct-role cases
- For Celery tests: idempotency + retry + max-retries cases when applicable
- Inline comments explaining non-obvious setup (e.g., why `app.dependency_overrides` is required)

**Strategy Doc** (when designing a test strategy):

```markdown
## Python Test Strategy

**Objective:** [what this strategy achieves]
**Pyramid balance:** Unit {x}% / Endpoint + Integration {y}% / E2E {z}%
**Tooling:** pytest, pytest-asyncio (FastAPI) / pytest-django (Django), factory_boy / model_bakery, Testcontainers PostgreSQL, respx / responses, pytest-celery
**Database isolation:** Testcontainers PostgreSQL + per-test transactional rollback (savepoint)
**Concurrency:** [pytest-xdist config]
**Gaps to close (prioritized):**

1. [Highest risk gap - typically authorization or repository correctness]
2. [...]
```

## Self-Check

**Always (any deliverable):**

- [ ] Stack confirmed as Python; framework (FastAPI / Django / mixed) recorded before any framework-specific guidance applied (Step 1)
- [ ] Code under test and a representative sample of existing tests + `conftest.py` files read directly so output matches project conventions (Step 2)
- [ ] `python-testing-patterns` consulted for canonical Python test patterns
- [ ] Auth testing approach explicit (FastAPI: dependency override or token fixture; Django: `force_authenticate` / `client.login`)
- [ ] Spec-aware mode honored when `--spec` was passed (one test per AC, NFR coverage from plan.md, no out-of-scope tests)

**Strategy Doc / Coverage Assessment only:**

- [ ] Test pyramid mapped to Python idioms (unit -> pytest + mock; endpoint -> ASGI / APIClient; integration -> Testcontainers; Celery -> task_always_eager / pytest-celery)
- [ ] Boundaries clearly defined: each layer covers what it does best; no duplicated assertions across layers
- [ ] Prioritization by risk applied when coverage is low - P1 authorization, P2 data integrity, P3 business-critical, P4 high-churn, P5 plumbing
- [ ] Testcontainers used for repository and full-context tests; SQLite flagged as a smell for production-Postgres apps

**Test Scaffolds only:**

- [ ] Test data created via factories, not raw dict literals; factory_boy session binding shown explicitly when applicable
- [ ] Endpoint scaffolds include happy path + 401 + 403 + validation-error; IDOR test for any per-owner / per-tenant resource
- [ ] Repository scaffolds run against Testcontainers PostgreSQL with per-test SAVEPOINT rollback - never SQLite for Postgres apps
- [ ] Celery scaffolds include idempotency + retry; real-broker (`pytest-celery`) variant present for tasks declared `acks_late=True`
- [ ] `app.dependency_overrides` for `get_db` / `get_current_user` shown in conftest, not invented per-test
- [ ] Pydantic schema unit tests scaffolded for any non-trivial validator or `model_config = ConfigDict(extra="forbid")` contract

**Review-existing-tests mode only:**

- [ ] Review checklist items addressed for every test file in scope

## Avoid

- Scaffolding tests without first reading existing tests + `conftest.py` - the result imports the wrong factory, uses the wrong HTTP-stub library, or duplicates the integration-test base fixture
- Chasing a coverage number instead of prioritizing by risk - 100% line coverage with no auth tests misses the bigger threat
- Full E2E tests (`pytest-docker` + real broker) for what an endpoint test could cover - context cost compounds across the suite
- SQLite / in-memory DB in repository tests for apps that use PostgreSQL features (JSONB, partial indexes, `ON CONFLICT`, array types) - tests pass, prod fails
- Writing endpoint tests with `requests.get(...)` against a real running server when `ASGITransport` / `APIClient` is faster and more deterministic
- Duplicating factories per test class - share via `tests/factories.py` and / or `conftest.py`
- Using `mocker.patch("app.repositories.order.session.commit")`-style internal mocks when a Testcontainers integration test could assert real DB state
- Skipping CSRF tokens on Django form tests by setting `CsrfViewMiddleware` to a no-op - the test is now incorrect for the prod config
- Skipping Pydantic validator tests because the endpoint has an integration test - validators are unit-tested separately so they can be reused
- Testing framework internals (e.g., that `Depends` resolves, that DRF routers route) - test your wiring, not the framework
- `CELERY_TASK_ALWAYS_EAGER = True` as a substitute for a real-broker test on tasks with `acks_late=True` - eager skips the broker and masks at-least-once semantics
