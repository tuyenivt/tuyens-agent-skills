---
name: task-python-refactor
description: "Python / FastAPI / Django refactor plan: fat routers, anemic services, sync-in-async, Celery fan-out; phased steps with pytest coverage gate."
agent: python-tech-lead
metadata:
  category: backend
  tags: [python, fastapi, django, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Python Refactor

Safe, step-by-step refactoring plan for a Python target (FastAPI router, Django view / ViewSet, service module, repository, SQLAlchemy / Django model, Celery task, Pydantic schema). Identifies smells, proposes independently-committable steps with pytest gates between each.

Stack-specific delegate of `task-code-refactor` for Python.

## When to Use

- Python code-smell resolution
- Technical-debt reduction with a concrete plan
- Safe refactor of a router / view / service / repository / model / Celery task
- "This PR grew the fat-router / god-service problem - what's the cleanup?"

**Not for:**

- Choosing which debt to tackle (`task-debt-prioritize`)
- Feature changes (`task-python-implement`)
- Cross-module restructuring (`task-design-architecture`)
- Bug fixes (`task-python-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                              |
| --------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------------ |
| Target scope          | Yes         | File / module to refactor (e.g., `app/routers/orders.py`, `orders/views.py`, `app/services/order_service.py`)            |
| Goal                  | Yes         | What the refactor should achieve (e.g., extract `place_order`, kill `post_save` chain, split `OrderService` god module)  |
| Test coverage status  | Recommended | Whether pytest / Testcontainers / endpoint / Celery coverage exists                                                      |
| Shared/public surface | Recommended | Whether the target crosses module / package / team boundaries                                                            |

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-confirmed stack from a Python-aware parent. If not Python, redirect to `/task-code-refactor`. Record `Framework: FastAPI | Django | mixed`.

### Step 2 - Read the Target

Plans grounded in user prose hallucinate smells. Before classifying:

1. Read the target module top-to-bottom; note function count, longest function, sync-vs-async signature mix, transaction placement, every external collaborator (`httpx.AsyncClient`, `requests.Session`, Celery `task.delay`, mailers).
2. Read matching tests (`test_<target>.py`, `test_<target>_api.py`); count cases by outcome (happy, validation, external failure, auth denial).
3. Read the immediate caller (router calling the service, scheduled task calling the service) - signature changes cascade.

If only a goal was given without a target file, ask for the target.

**Sibling-smell disposition.** If the file contains smells beyond the named target (IDOR in `get_order`, pickle deserialization in `bulk_import`), do **not** action them and do **not** ignore them. List under `Sibling Smells (Out of Scope)` with brief deferral rationale and a recommended follow-up invocation (e.g., security findings -> `task-python-review-security`).

### Step 3 - Coverage Gate (mandatory)

Refactoring without tests is a rewrite. Assign one of three statuses:

| Status       | Definition                                                                                                          | Action                                                                                  |
| ------------ | ------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path + >= 2 boundary outcomes per public entry (validation, auth denial, external failure, not-found)        | Proceed to Step 4                                                                       |
| `Thin`       | Happy path + exactly 1 boundary outcome                                                                             | Proceed; plan must include non-optional `Step 0 - Coverage prerequisite`                |
| `Inadequate` | No tests, or happy-path-only                                                                                        | **Refuse Steps 1+.** Output verdict + recommendation to run `task-python-test` first    |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot verify the refactor preserves validation, authorization, or error behavior.

Output the explicit status before proceeding.

### Step 4 - Identify Python Smells

Use skill: `python-fastapi-overengineering-review` (FastAPI targets) or `python-django-overengineering-review` (Django targets) for: Pydantic / DRF validators duplicating DB constraints or type hints, defensive guards on typed values, single-impl ABCs / Protocols, redundant DI layers, premature mapping classes, custom exception hierarchies. Those are simplification opportunities, not extractions.

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` for premature factory / strategy / redundant mapping layers.

**Additional Python smells not covered above:**

| Smell                                          | Signal                                                                                                                                                  | Risk   |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Router / View                              | Endpoint > 15 lines orchestrating multiple service calls, dispatch, response shaping                                                                    | High   |
| Logic in Router / View                         | Business rules, calculation, domain decisions inside the handler                                                                                        | High   |
| Direct ORM in Router / View                    | `session.execute(...)` / `Order.objects.filter(...)` in handler, bypassing service                                                                      | Medium |
| ORM Instance Returned from Endpoint            | FastAPI returns `Mapped[...]`; Django returns `JsonResponse(model_to_dict(obj))` (mass-assignment + lazy-load risk)                                     | High   |
| `extra="allow"` on Input Schema                | Pydantic input schema silently accepts unknown fields including privilege-bearing ones                                                                  | High   |
| Response Schema Exposes Internal Fields        | Pydantic / DRF declares `internal_audit_log`, `is_test` - leaks via `response_model` even when ORM not returned                                          | High   |
| God Service Module                             | `service.py` > 500 lines mixing orchestration + persistence + clients                                                                                   | High   |
| Anemic Domain                                  | Business rules in `helpers.py` (`calculate_total(order)`) that could be methods on the model                                                             | High   |
| Sync-in-Async / Async-without-await            | `async def` calling sync I/O, or `async def` with no `await`                                                                                            | High   |
| External I/O Inside DB Transaction             | HTTP / `task.delay` / mailer inside `@transaction.atomic()` / `async with session.begin()`                                                               | High   |
| Service Returning Boolean                      | Caller cannot distinguish validation vs not-found vs external                                                                                           | Medium |
| Fat Model                                      | Model > 300 lines mixing mapping + computed + business + validation                                                                                     | High   |
| Django `post_save` / SQLAlchemy `event.listen` | Hook dispatching emails / events / external calls; races commit, hidden control flow                                                                    | High   |
| `relationship(lazy="select")` Default          | `MissingGreenlet` in async session; N+1 in sync code                                                                                                    | High   |
| `lazy="joined"` on Collections                 | Cartesian explosion + locks lazy semantics elsewhere                                                                                                    | High   |
| Repository Returning Unbounded `all()`         | `session.scalars(...).all()` / `Model.objects.all()` without pagination                                                                                 | Medium |
| Django `default` Manager Side Effects          | Custom default Manager filters globally - surprises every query                                                                                         | High   |
| `text()` String Concatenation                  | Dynamic SQL built via concat instead of parameterized `text(":param")`                                                                                  | High   |
| ORM Instance Outside Session Scope             | Model in module cache, queue payload, or `model.__dict__` after session close. Cache IDs and re-fetch                                                   | High   |
| Module-level Mutable State                     | `_cache: dict = {}` mutated at import time or by handlers                                                                                               | High   |
| `os.environ.get` Sprinkled                     | Should be a `BaseSettings` / `django-environ` field                                                                                                     | Medium |
| Blocking I/O in `async def`                    | `requests.get`, `time.sleep`, sync DB, sync `open()` of large files inside async handler                                                                | High   |
| Unbounded `asyncio.gather` Fan-out             | `asyncio.gather(*[call(x) for x in big_list])` - exhausts pool / FDs                                                                                    | High   |
| `.delay()` Inside DB Transaction               | Worker may pick up before commit                                                                                                                        | High   |
| Celery Task Without Idempotency                | Re-runs side effects on retry; no dedup, upsert, state check                                                                                            | High   |
| Critical Task Without `acks_late`              | Payment / billing task with default `acks_late=False` - lost on worker crash                                                                            | High   |
| Pydantic Validator Doing I/O                   | `@field_validator` calling DB or HTTP - runs on every request including OpenAPI schema gen                                                              | High   |

**Test smells (when refactoring brings tests into scope):** `mocker.patch` chains for ORM instead of Testcontainers; SQLite in repository tests for a Postgres app (JSONB, partial index, `ON CONFLICT` diverge); `CELERY_TASK_ALWAYS_EAGER` masking at-least-once / `acks_late` semantics.

Apply Python judgment: a 25-line service function orchestrating clearly named helpers is fine; a 10-line function doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius`.

Python-specific signals: public router / view used by external clients; published package surface; Django signal with broad receiver / SQLAlchemy listener bound to `Session`; service injected by > 10 modules; ORM model used in many queries; Pydantic schema reused across endpoints.

State blast radius: **Narrow** / **Moderate** / **Wide** / **Critical**.

### Step 6 - Propose the Step Sequence

Each step must be:

1. **Independently committable** - imports clean and pytest suite passes after each step
2. **Behaviorally invariant** unless labeled `coupled-fix`
3. **Reversible** in one revert
4. **Tested** - existing suite still passes; new tests when extracting new units

**Recipe interleaving.** When multiple recipes apply (a fat router that also has `extra="allow"`, blocks the event loop, and stashes ORM instances in a module cache), don't concatenate - identify the **primary** refactor (usually the one in the user's goal), name it as `Primary recipe:`, fold supporting recipes as sub-steps. If the spine > 8 steps, split into two PRs.

**Coupled-fix language.** When a refactor depends on a behavior change (extracting a service that derives `owner_id` from the principal requires `Depends(get_current_user)` - a structural prerequisite), label the step `coupled-fix` with its own test gate. Not a bundling violation; an explicit prerequisite.

**Per-step disclosures** - state explicitly:

- **Transaction stance:** callee runs inside caller's transaction | post-commit dispatch (`transaction.on_commit` / async hook) | not transactional. Never silently move I/O across a transaction boundary.
- **Async stance:** sync | async | unchanged. Never silently change a function from sync to async without auditing every call site - an un-awaited coroutine is a silent bug.

**Common Python refactor recipes:**

**Extract service from fat router (FastAPI)**

1. Add `app/services/<verb>_<noun>.py` with one intention-revealing async function returning a domain result type (Pydantic model / dataclass / sealed `Union`); copy logic; router still does original work
2. Add `tests/test_<verb>_<noun>.py` with cases for success, validation failure, external failure
3. Router calls the service via `Depends`; preserve response shape
4. Remove original logic from router; endpoint tests still pass
5. Add a router-level test asserting service failure surfaces via `@app.exception_handler`

**Extract service from fat ViewSet (Django)**

1. Add `<app>/services/<verb>_<noun>.py` with a single function taking simple args and returning a domain result
2. Add `tests/test_<verb>_<noun>.py` covering validation / business-rule paths
3. ViewSet `perform_create` / `perform_update` / custom `@action` calls the service
4. Remove original logic from ViewSet
5. Add endpoint test asserting service failure surfaces via DRF exception handler

**Convert Django `post_save` to `transaction.on_commit`**

1. Add an endpoint / service test reproducing observable behavior (record updated, email sent, event published)
2. Replace signal body with `transaction.on_commit(lambda: send_email_task.delay(instance.id))`; tests pass
3. If signal does cross-aggregate work, extract handler into a service called from the model or service; remove the signal
4. Run full suite; verify no orphan code paths rely on the signal

**Move side effects out of an open DB transaction**

The case: `task.delay(...)`, mailer, webhook call issued before commit - worker may observe pre-commit state; an exception after the side effect cannot un-send it. Pick **one** option; do not stack.

_Option A - Post-commit dispatch_ (default; simpler):

1. **FastAPI:** restructure to `write -> await session.commit() -> side effect`. If service delegates commit to `Depends(get_db)` teardown, invert control - service owns `async with session.begin():` and dispatches after the block exits cleanly.
2. **Django:** wrap dispatch in `transaction.on_commit(lambda: task.delay(payload))`. Caveat: exceptions inside the lambda are logged but swallowed by Django's hook runner - if the side effect must be guaranteed, use Option B.
3. Test asserts: side effect fires on commit; nothing fires on rollback.
4. Failure mode: process crash between commit and dispatch drops the side effect. Acceptable for non-critical; use Option B for billing / regulatory events.

_Option B - Transactional outbox_ (durable, at-least-once):

1. Add `outbox` table (`id`, `payload`, `created_at`, `processed_at`). Service writes domain + outbox row in the same transaction; commit is atomic.
2. Separate worker (Celery beat / dedicated consumer) reads outbox via `SELECT ... FOR UPDATE SKIP LOCKED`, dispatches, marks `processed_at = now()`.
3. Side-effect handlers must be idempotent (idempotency keys, business-key upsert).
4. Test: outbox row exists post-commit; relay picks up; second run does not re-dispatch.
5. Cost: extra table, worker, monitoring surface. Use only when a missed side effect is unacceptable.

**Untangle fat ViewSet + signal-driven side effects (combined Django case)**

A ViewSet `create` triggers a model save whose `post_save` fans out (mailers, Celery, audits). Removing the signal and extracting a service must happen as one logical change, but in safe sub-steps so the suite stays green between commits.

Do **not** introduce a `threading.local` skip-flag or `_skip_signals` attribute. `threading.local` does not propagate across `await`; state leaks across prefork Celery workers; the flag ships as a permanent footgun.

1. **Pin behavior** with an endpoint + service test asserting every observable side effect (record, mailer, task, audit row) - this is the contract.
2. **Promote signal dispatch to `transaction.on_commit`** first; side effects fire post-commit; tests pass.
3. **Introduce a service function** that performs the write _without_ side effects; signal still fans out; service is an empty shell. Tests pass.
4. **Migrate every caller** (`ViewSet.perform_create`, direct `Model.objects.create`, scheduled tasks, management commands) to the service. Signal still does side-effect work; tests pass.
5. **Atomic swap**: move side effects from signal into the service body **and** delete the signal handler in one commit. Because step 4 routed every caller through the service, no caller reaches the entity without the side effects.
6. **Audit other write paths** (`bulk_create`, `update()`, raw SQL, migrations) that bypass `save()` and never triggered the signal - if they need the side effects now, they call the service or re-derive.

If step 4 finds a caller that cannot move yet, pause: keep the signal and defer, or split across releases. Do not paper over with a skip-flag.

**Eliminate blocking I/O in async path (FastAPI)**

1. Identify the blocking call (`requests.get`, `time.sleep`, sync DB driver, sync file I/O, CPU-heavy hashing)
2. HTTP: `await client.get(url)` on a module-level `httpx.AsyncClient` singleton (add via lifespan if missing)
3. Sleep: `time.sleep(s)` -> `await asyncio.sleep(s)`
4. Sync DB: replace with `AsyncSession` / `await session.execute(...)`; interim wrap via `await loop.run_in_executor(None, sync_fn)`
5. CPU work: Celery task or `loop.run_in_executor` thread pool
6. Run endpoint tests; assert tail latency improvement if a perf fixture exists

**Split god service into focused services**

1. Identify orthogonal concerns (`order_service.py` doing place + cancel + refund + reporting -> `place_order.py`, `cancel_order.py`, `refund_order.py`, `order_report.py`)
2. Extract one concern at a time; god service delegates temporarily
3. Update callers to import the focused module directly; remove delegation
4. Repeat; delete god service when empty

**Make Celery task idempotent**

1. Test asserting the side effect fires exactly once when the same task is dispatched twice (different request IDs, same business key)
2. Idempotency guard: dedup table keyed by message UUID, business-key upsert via `ON CONFLICT DO NOTHING`, or version check
3. Configure DLT / retries (`autoretry_for`, `max_retries`, `retry_backoff`) so poison messages don't loop forever
4. Set `acks_late=True` + `task_reject_on_worker_lost=True` for at-least-once on critical tasks

**Eliminate `extra="allow"` mass-assignment risk (Pydantic)**

1. Add `model_config = ConfigDict(extra="forbid")` to the input schema
2. Run endpoint tests; tests POSTing unknown fields will start failing with 422 - fix or document each
3. Audit other input schemas; default to `extra="forbid"` for user-facing schemas
4. Internal-only schemas (queue payloads, RPC) may keep `extra="ignore"` with a justifying comment

**Replace module-level mutable state**

1. Identify the mutable state (`_cache: dict = {}`, `_handlers: list = []`)
2. Move into a class with explicit lifecycle, a `BaseSettings` field if config, or request scope (`request.state` FastAPI; `request._cache` Django) if per-request
3. Callers receive the dependency explicitly (FastAPI `Depends`, Django middleware-attached attribute, service constructor arg)
4. Tests pass; assert cross-test isolation (no leaking state between tests)

### Step 7 - Validate Plan Against Goal

- [ ] Goal achieved at the end of the sequence
- [ ] Each step small enough to review in < 30 minutes
- [ ] Test coverage runs between every step
- [ ] Low-risk steps first (additions, extractions) before high-risk (deletions, signature changes, signal removals)
- [ ] Rollback is one revert per step
- [ ] No step bundles unrelated cleanup

## Output Format

```markdown
## Python Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Python refactor recipes"]
**Stack:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[If Adequate: one sentence on boundary cases.]
[If Thin: list missing boundary tests; Step 0 covers them.]
[If Inadequate: state what coverage must exist; recommend running `task-python-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, Verification. You may still produce **Smells Identified** and **Sibling Smells** as a preview; mark preview-only.]

**Coverage prerequisite list shape (when `Thin` or `Inadequate`):** one row per public entry point: `entry-point | outcome | recommended layer`. Outcomes cover validation failure (4xx), authorization denial (401/403), not-found / IDOR, external-collaborator failure. Layer options: endpoint test (httpx ASGITransport / DRF APIClient), service unit test, repository integration (Testcontainers), Celery task test. Example: `POST /orders/ | unknown-field rejected (extra="forbid") | endpoint test`.

## Smells Identified

| Smell | Location | Risk | Notes |
| ----- | -------- | ---- | ----- |

## Sibling Smells (Out of Scope)

| Smell | Location | Why deferred | Recommended follow-up |
| ----- | -------- | ------------ | --------------------- |

_Omit if no other smells in target._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Adequate)_

- **Change:** add boundary tests from Coverage Gate
- **Risk:** Low
- **Test gate:** new tests pass; existing suite green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass - unit / endpoint / Testcontainers / Celery]
- **Transaction stance:** [inside caller's tx | post-commit dispatch | not transactional]
- **Async stance:** [sync | async | unchanged]
- **Rollback:** [how to revert]

### Step 2 - [...]

[`Step kind: coupled-fix` for any step that intentionally changes behavior; state why the coupling is structural.]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] pytest suite passes between every step
- [ ] No bundled cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No silent sync / async signature changes; every call site updated

## Out of Scope

[Adjacent improvements explicitly NOT in this plan]
```

## Self-Check

**Plan-time:**

- [ ] Stack confirmed; framework recorded (Step 1)
- [ ] Target files and matching tests read directly before classification (Step 2)
- [ ] Sibling smells listed with deferral rationale (or section omitted) (Step 2)
- [ ] Coverage gate evaluated using sharp boundaries; happy-path-only treated as `Inadequate`; plan refused if `Inadequate` (Step 3)
- [ ] Python smells identified using Step 4 catalog and overengineering-review delegations (Step 4)
- [ ] Blast radius stated before steps (Step 5)
- [ ] `Primary recipe:` named; supporting recipes folded as sub-steps (Step 6)
- [ ] Step 0 included if `Thin`; omitted if `Adequate` (Output Format)
- [ ] Transaction stance per step (Step 6)
- [ ] Async stance per step (Step 6)
- [ ] `Step kind: coupled-fix` labeled for any intentional behavior change with rationale (Step 6)
- [ ] Steps ordered low-risk first (Step 6)
- [ ] Plan length <= 8 steps or split (Step 6)
- [ ] Goal mapped to end state (Step 7)

**Execution-time (commitments for the implementer):**

- [ ] pytest suite passes between every step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Refactor without a coverage gate - that's a rewrite
- "While we're here" unrelated cleanup; renames bundled into refactors
- Removing Django signals / SQLAlchemy event listeners without a test pinning observable behavior
- `threading.local` skip-flag / `_skip_signals` attribute to silence a signal for "the new path" - audit and delete instead
- Replacing `requests.get` with `httpx.AsyncClient` on a sync code path with no async benefit (`httpx.Client` sync is the right swap)
- Replacing module-level mutable state with `threading.local` without checking that the codebase actually uses threading vs asyncio
- Refactoring a published package without a backward-compatibility plan
