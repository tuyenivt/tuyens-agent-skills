---
name: task-python-refactor
description: Python refactor planning for fat routers / views, anemic services, god modules, sync-in-async mixing, blocking I/O on the event loop, Pydantic validators that should be model validators, Django signals dispatching business logic, SQLAlchemy `relationship()` lazy traps, and Celery task fan-out. Produces a step-by-step sequence of independently-committable Python refactoring steps with a pytest coverage gate. Stack-specific override of task-code-refactor for Python.
agent: python-tech-lead
metadata:
  category: backend
  tags: [python, fastapi, django, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Python Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Python target (FastAPI router, Django view / ViewSet, service module, repository, SQLAlchemy model, Django model, Celery task module, Pydantic schema). Identifies Python-specific smells (fat router / view, anemic services, god modules, async-sync mixing, blocking I/O in event loop, Django signal abuse, SQLAlchemy relationship lazy traps) and proposes independently-committable refactoring steps with pytest gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Python.

## When to Use

- Python code-smell identification and resolution
- Python technical-debt reduction with a concrete plan
- Safe refactoring of a router / view / service / repository / model / Celery task module
- Pre-merge "this PR grew the fat-router / god-service problem - what's the cleanup?"

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-python-implement`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-python-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                               |
| --------------------- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, module, or package to refactor (e.g., `app/routers/orders.py`, `orders/views.py`, `app/services/order_service.py`)                  |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `place_order` service, kill `post_save` signal chain, split `OrderService` god module) |
| Test coverage status  | Recommended | Whether pytest / Testcontainers / endpoint coverage exists for the target area                                                            |
| Shared/public surface | Recommended | Whether the target is used across module / library / team boundaries                                                                      |

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If invoked as a subagent of a Python-aware parent, accept the pre-confirmed stack. If the detected stack is not Python, stop and tell the user to invoke `/task-code-refactor` instead.

Detect framework: FastAPI vs Django (or mixed). Record `Framework: FastAPI | Django | mixed` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target module top-to-bottom; note function / method count, longest function, sync-vs-async signature mix, transaction placement, every external collaborator (`httpx.AsyncClient`, `requests.Session`, Celery `task.delay`, mailers).
2. Read the matching test file(s) (e.g., `test_order_service.py`, `test_orders_api.py`); count cases by outcome (happy path, validation failure, external failure, auth denial).
3. If callers are obvious (router calling the service, scheduled task calling the service), read the immediate caller too - removing or reshaping a public function without seeing call sites is how silent breakage happens.

If the user named only the goal without a target file / module, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat modules. If the file containing the target also contains other smells (e.g., the user names `create_order` but the same router file has IDOR in `get_order` and a pickle deserialization in `bulk_import`), do **not** action them in this plan and do **not** ignore them silently. List them under a `Sibling Smells (Out of Scope)` heading in the output, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-python-review-security`), and recommend follow-up invocations. This disambiguates "while we're here cleanup" (forbidden) from "name the deferred work for hand-off" (required).

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (`test_<target>.py`, `test_<target>_api.py`, integration tests against Testcontainers, Celery task tests), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                   | What the workflow does                                                                                                                        |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., validation failure, auth denial, external failure, not-found) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                               | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                        | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-python-test` first             |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves validation, authorization, or error behavior - you would be flying blind.

**Output of this step:** explicit coverage status using one of the three labels above. Do not proceed past Step 4 if status is `Inadequate`.

### Step 4 - Identify Python Smells

Inspect the target for these Python-specific smells. Use judgment - these are signals, not hard rules.

**Router / View smells (FastAPI / Django):**

| Smell                                   | Signal                                                                                                                                                                                            | Risk   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Router / View                       | Endpoint > 15 lines of orchestration (multiple service calls, conditional dispatch, response shaping)                                                                                             | High   |
| Logic in Router / View                  | Business rules, validation beyond Pydantic / DRF, calculation, or domain decisions inside the handler                                                                                             | High   |
| Direct Repository / ORM in Router       | Routers / views call `session.execute(...)` / `Order.objects.filter(...)` directly, bypassing the service layer                                                                                   | Medium |
| ORM Model Returned from Endpoint        | FastAPI endpoint returns a SQLAlchemy `Mapped[...]` instance; Django view returns `JsonResponse(model_to_dict(obj))` (mass-assignment + lazy-load risk on serialization)                          | High   |
| Manual Validation Duplicating Pydantic  | Router body re-checks `Field(min_length=...)` constraints already on the schema                                                                                                                   | Low    |
| `extra="allow"` on Input Schema         | Pydantic input schema defaults to `extra="allow"` (or no `extra=` config) - silently accepts unknown fields including privilege-bearing ones                                                      | High   |
| Response Schema Exposes Internal Fields | Pydantic `*Response` / DRF serializer declares server-internal fields (`internal_audit_log`, `is_test`, `internal_notes`) - leaks via `response_model` even when the ORM is not returned directly | High   |

**Service smells:**

| Smell                                | Signal                                                                                                                                                 | Risk   |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| God Service Module                   | `service.py` > 500 lines; mixes orchestration, persistence, mapping, external clients, scheduling                                                      | High   |
| Anemic Domain                        | Models are pure data containers; business rules live in `helpers.py` with names like `calculate_total(order)` and could belong on the model            | High   |
| Single-Implementation ABC / Protocol | `OrderServiceProtocol` + single `OrderService` with no test double, no second implementation                                                           | Medium |
| Sync-in-Async (FastAPI)              | `async def` function calls a sync helper that does I/O - blocks the event loop. Reverse: sync function in a sync app marked `async def` for no benefit | High   |
| External I/O Inside DB Transaction   | HTTP call, message publish, or file write inside `@transaction.atomic()` / `async with session.begin()` (defers commit, holds DB locks long)           | High   |
| Service Returning Boolean            | Service returns `bool`; caller cannot distinguish failure cases (validation vs not-found vs external)                                                  | Medium |

**Persistence / ORM smells:**

| Smell                                          | Signal                                                                                                                                                                                                                 | Risk   |
| ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Model                                      | Django / SQLAlchemy model > 300 lines; mixes mapping, computed properties, business operations, validation                                                                                                             | High   |
| Django `pre_save` / `post_save` Signal Abuse   | Signal dispatching emails, publishing events, calling external services - races commit and silently breaks                                                                                                             | High   |
| SQLAlchemy `event.listen` Abuse                | `before_insert` / `after_update` listener doing cross-aggregate writes - hidden control flow                                                                                                                           | High   |
| `relationship(lazy="select")` Default          | Default lazy traversal in `async_session` raises `MissingGreenlet`; in sync code, it triggers N+1                                                                                                                      | High   |
| `FetchType.EAGER` equivalent (`lazy="joined"`) | Eager load on collections - cartesian explosion + locks lazy semantics elsewhere                                                                                                                                       | High   |
| Repository Returning Unbounded `all()`         | `session.scalars(select(X)).all()` / `Model.objects.all()` without pagination                                                                                                                                          | Medium |
| Django `default` Manager Side Effects          | Custom default Manager that filters out soft-deleted rows globally - surprises every query                                                                                                                             | High   |
| `text()` String Concatenation                  | Dynamic JPQL / SQL built via string concat instead of parameterized `text(":param")`                                                                                                                                   | High   |
| ORM Instance Stored Outside Session Scope      | ORM model assigned to a module-level cache, sent to a queue, or serialized via `model.__dict__` after session close - lazy attributes, detached-instance traps, identity-map confusion. Cache IDs and re-fetch instead | High   |

**Configuration / DI smells:**

| Smell                           | Signal                                                                                              | Risk   |
| ------------------------------- | --------------------------------------------------------------------------------------------------- | ------ |
| Module-level Mutable State      | `_cache: dict = {}` / `_config: list = []` mutated by import-time code or runtime handlers          | High   |
| `os.environ.get` Sprinkled      | `os.environ.get("X")` scattered across modules; should be a `BaseSettings` / `django-environ` field | Medium |
| Hardcoded `settings.X` Defaults | Default values inline in code rather than a typed settings module                                   | Medium |
| Service Locator Pattern         | Module imports another module just to call its function for "DI" - obscures the dependency graph    | High   |

**Async / Celery smells:**

| Smell                                        | Signal                                                                                                       | Risk   |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| Blocking I/O in `async def`                  | `requests.get`, `time.sleep`, sync DB call, sync file `open()` for large files inside an async handler       | High   |
| Sync-Only Code Marked `async def`            | `async def` function with no `await` - just adds overhead, no benefit                                        | Medium |
| Unbounded `asyncio.gather` Fan-out           | `asyncio.gather(*[call(x) for x in big_list])` - exhausts pool / file descriptors                            | High   |
| `.delay()` Inside DB Transaction             | Celery task dispatched inside `@transaction.atomic()` - worker may pick up before commit                     | High   |
| Celery Task Without Idempotency              | Task that re-runs side effects when delivered twice (no dedup, no upsert, no state check)                    | High   |
| Celery Task Without `acks_late` for Critical | Critical task (payment, billing) running with default `acks_late=False` - lost on worker crash               | High   |
| Pydantic Validator Doing I/O                 | `@field_validator` calling DB or HTTP - validators run on every request, including OpenAPI schema generation | High   |

**Test smells (when refactoring brings tests into scope):**

| Smell                                       | Signal                                                                         | Risk   |
| ------------------------------------------- | ------------------------------------------------------------------------------ | ------ |
| `mocker.patch` Chains for ORM               | Patching `Session.commit` instead of using a Testcontainers integration test   | Medium |
| SQLite in Repository Tests for Postgres App | Tests pass on SQLite but fail in prod on JSONB / partial index / `ON CONFLICT` | High   |
| `CELERY_TASK_ALWAYS_EAGER` Masking Reality  | Eager mode hides at-least-once / `acks_late` semantics                         | Medium |

**General OO smells (apply with Python judgment):**

Use skill: `backend-coding-standards` for the cross-language smell catalog.
Use skill: `complexity-review` when the target shows over-engineering signals (single-impl ABCs, base classes for two children, premature `Protocol`/`Factory`, redundant mapping layers) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply Python judgment - a 25-line service function orchestrating clearly named private helpers is fine; a 10-line function doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and deployments are affected by the refactor.

Python-specific blast-radius signals:

- [ ] **Public API surface**: target is a router / view used by external clients - refactor risks API contract change
- [ ] **Library / package boundary**: target is in a published package on PyPI or an internal monorepo library consumed by other apps
- [ ] **Signal with broad receiver**: refactoring a Django signal connected to many models / a SQLAlchemy event listener bound to `Session` affects every dispatch
- [ ] **Service injected widely**: target is imported by > 10 modules - signature changes cascade
- [ ] **ORM model used in many queries**: refactoring a model affects every `select(...)` / `Manager.filter` / repository
- [ ] **Pydantic schema reused across endpoints**: schema field rename / removal cascades into every dependent endpoint and its tests

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single module / app, multiple callers) / **Wide** (cross-module, public API, broad signal) / **Critical** (published package, model used by 5+ services).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase imports cleanly and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`, see below)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing pytest suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target (e.g., a fat router that also has `extra="allow"`, blocks the event loop, and stashes ORM instances in a module cache), do **not** concatenate the recipes - that produces a 25-step plan mixing concerns. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly in the output via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs rather than one mega-plan.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a service that derives `owner_id` from the authenticated principal _requires_ the principal to be available, so adding `Depends(get_current_user)` is a structural prerequisite, not "while-we're-here cleanup"). When this happens, label the step `coupled-fix` in the Output Format with its own test gate and rationale. This is **not** a bundling violation - it is an explicit prerequisite. Do not silently fold it into an extraction step.

**Transaction-boundary watch.** When extracting orchestration that runs inside `@transaction.atomic()` or `async with session.begin()`, the extracted unit inherits the transaction context if called from the original entry point. If the extracted code makes HTTP calls, publishes to Celery, or writes files, they now happen mid-transaction (a regression). State the transaction stance per step: "callee runs inside caller's transaction" or "callee uses `transaction.on_commit` / async post-commit hook to defer side effects." Never silently move I/O across a transaction boundary.

**Async-boundary watch.** Adding `async def` or removing it crosses an event-loop boundary. State whether the new signature is sync or async, and ensure callers are updated (`await` added or removed). Never silently change a function from sync to async without auditing every call site - the async function returns a coroutine if not awaited, and the bug is silent.

**Common Python refactor recipes:**

**Recipe: Extract service from fat router (FastAPI)**

1. Add `<verb>_<noun>.py` service module (e.g., `app/services/place_order.py`) with a single intention-revealing async function returning a domain result type (Pydantic model / dataclass / sealed `Union`); copy logic from router; router still does the original work
2. Add `tests/test_<verb>_<noun>.py` with one test per outcome (success, validation failure, external failure)
3. Update router to call the service; preserve response shape; ensure endpoint tests pass unchanged
4. Remove the original logic from the router; verify endpoint tests pass
5. Add a router-level test asserting service failure surfaces as the expected error response (likely via `@app.exception_handler`)

**Recipe: Extract service from fat ViewSet (Django)**

1. Add `<app>/services/<verb>_<noun>.py` with a single function taking simple args and returning a domain result; copy logic from ViewSet
2. Add `tests/test_<verb>_<noun>.py`; test cases include the validation / business-rule paths
3. Update ViewSet `perform_create` / `perform_update` / custom `@action` to call the service
4. Remove the original logic from the ViewSet
5. Add an endpoint test asserting service failure surfaces via DRF exception handler

**Recipe: Convert Django `post_save` signal side effects to `transaction.on_commit`**

1. Add an endpoint test (or service test) reproducing the current observable behavior (record updated, email sent, event published)
2. Replace the signal handler body with `transaction.on_commit(lambda: send_email_task.delay(instance.id))`. Side effects now fire post-commit instead of mid-transaction
3. Run tests; confirm pass
4. If signal was doing cross-aggregate work, extract the side-effect handler into a service function and call it from the model's save method or a service - remove the signal entirely
5. Run the full suite; verify no orphan code paths still rely on the signal

**Recipe: Untangle fat ViewSet + signal-driven side effects (combined case)**

The most common Django refactor: a ViewSet `create` triggers a model save whose `post_save` signal fans out (mailers, Celery dispatches, audit writes). Removing the signal and extracting a service must happen as one logical change, but in safe sub-steps so the suite stays green between commits.

1. **Pin behavior with an endpoint + service test** asserting every observable side effect (record updated, mailer queued, task dispatched, audit row written) - this is the contract the refactor must preserve
2. **Promote signal dispatch to `transaction.on_commit`** first so side effects fire post-commit; tests still pass
3. **Introduce a service function** (`<verb>_<noun>`) that performs the write _and_ the side effects in one call; ViewSet calls the service _but the signals still run_ - this duplicates side effects intentionally and temporarily
4. **Make signals no-op when called from the service** via a `threading.local` flag set by the service or a flag on the model instance (`if getattr(instance, "_skip_signals", False): return`); verify tests still pass with side effects firing exactly once
5. **Delete the signal handlers entirely**; the service is now the single source of orchestration; remove the bypass flag; tests still green
6. **Audit other call sites** (`Model.objects.create`, `bulk_create`, migrations, scheduled tasks) - any caller relying on the old signal is now broken and must be updated to call the service or have the side effects re-derived

The intermediate "signals no-op when called from service" step is the safety net - it keeps the codebase shippable between the introduction of the service (step 3) and the deletion of the signals (step 5).

**Recipe: Eliminate blocking I/O in async path (FastAPI)**

1. Identify the blocking call (`requests.get`, `time.sleep`, sync DB driver, sync file I/O, CPU-heavy hashing)
2. For HTTP: replace `requests.get(url)` with `await client.get(url)` where `client` is the module-level `httpx.AsyncClient` singleton; if no client exists, add one to app state via lifespan
3. For sleep: `time.sleep(s)` → `await asyncio.sleep(s)`
4. For sync DB: replace with `AsyncSession` / `await session.execute(...)`; if migration is large, wrap the legacy sync call in `await loop.run_in_executor(None, sync_fn)` as an interim
5. For CPU work: move to a Celery task or `loop.run_in_executor` thread pool
6. Run endpoint tests; assert latency under load (if perf test fixture exists) shows tail latency improvement

**Recipe: Split god service into focused services**

1. Identify the orthogonal concerns inside the service module (e.g., `order_service.py` doing place + cancel + refund + reporting → split into `place_order.py`, `cancel_order.py`, `refund_order.py`, `order_report.py`)
2. Extract one concern at a time into a new module with explicit imports; original god service delegates to it temporarily
3. Update callers to import the new focused module directly; remove delegation from god service
4. Repeat until god service is empty; delete it. Each extraction commits independently
5. Verify all endpoint / service tests still pass

**Recipe: Eliminate single-implementation ABC / Protocol**

1. Confirm the ABC / Protocol has no test doubles, no second implementation, no DI requirement
2. Inline: rename `OrderService` (concrete) to live where the ABC was, delete the ABC, update callers (most cases the IDE rename handles it)
3. Run tests; confirm pass. Caller code is shorter and clearer
4. **Skip if** the Protocol is part of a published library API or has a real second implementation - the smell is fake

**Recipe: Make Celery task idempotent**

1. Add a task test asserting the side effect happens exactly once when the same task is dispatched twice (different request IDs, same business key)
2. Add an idempotency guard: dedup table keyed by message UUID, business-key upsert via PostgreSQL `ON CONFLICT DO NOTHING`, or version check
3. Verify retries on transient failures still complete the work
4. Configure DLT / max-retries (`autoretry_for`, `max_retries`, `retry_backoff`) so poison messages do not loop forever
5. Set `acks_late=True` + `task_reject_on_worker_lost=True` for at-least-once semantics on critical tasks

**Recipe: Eliminate `extra="allow"` mass-assignment risk (Pydantic)**

1. Add `model_config = ConfigDict(extra="forbid")` to the input schema
2. Run endpoint tests; expect any test that POSTed unknown fields to start failing with 422 - fix or document each
3. Audit every other input schema in the codebase; default to `extra="forbid"` for user-facing schemas
4. Internal-only schemas (queue payloads, internal RPC) may keep `extra="ignore"` or `extra="allow"` with a comment justifying

**Recipe: Replace module-level mutable state**

1. Identify the mutable state (`_cache: dict = {}`, `_handlers: list = []`)
2. Move into a class with explicit lifecycle, or into a `BaseSettings` field if it is config, or into the request scope (`request.state` for FastAPI; `request._cache` for Django) if it is per-request
3. Update callers to receive the new dependency explicitly (FastAPI `Depends`, Django middleware-attached attribute, or service constructor arg)
4. Run tests; confirm pass; assert cross-test isolation (no leaking state between tests)

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end)
- [ ] Steps are ordered low-risk first (extracts, additions) before high-risk (deletions, signature changes, signal removals)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Python Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Python refactor recipes" - this is the spine]
**Stack:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-python-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce the **Smells Identified** and **Sibling Smells (Out of Scope)** sections as a *preview* so the implementer has a target list when filling the coverage gap; mark them clearly as preview-only.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure (4xx), authorization denial (401/403), not-found / IDOR, external-collaborator failure. Layer options: endpoint test (httpx ASGITransport / DRF APIClient), service unit test, repository integration test (Testcontainers), Celery task test. Example: `POST /orders/ | unknown-field rejected (extra="forbid") | endpoint test`. This makes the prerequisite directly actionable rather than a vague "add boundary tests."

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/module that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                                 |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-python-review-security` / `task-python-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - unit / endpoint / Testcontainers integration / Celery]
- **Transaction stance:** [callee runs inside caller's transaction | callee uses `transaction.on_commit` / async post-commit | not transactional]
- **Async stance:** [sync | async | unchanged]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it (e.g., adding a security dependency that lets the extracted service derive `owner_id` from the principal). Always state why the coupling is structural, not cosmetic.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] Test suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No I/O silently moved across transaction boundaries
- [ ] No silent sync ↔ async signature changes; every call site updated

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderProcessor` to `OrderFulfiller` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as Python (or accepted from parent dispatcher); framework recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin` (Step 3)
- [ ] Python-specific smells identified using Step 4 catalog (router/view, service, persistence, configuration/DI, async/Celery) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate` (Output Format)
- [ ] Transaction stance stated per step (no I/O silently moved across transaction boundary) (Step 6)
- [ ] Async stance stated per step (no silent sync ↔ async signature changes) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, signal removals, signature changes) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] Test suite passes between every step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing Django signals or SQLAlchemy event listeners without a test asserting the original behavior is preserved
- Extracting an ABC / Protocol with one implementation - wait for the second use case before generalizing
- Moving HTTP calls or Celery dispatches from a non-transactional context to inside a transactional one (or vice versa) without explicitly stating the transaction stance
- Changing a function from sync to async (or back) without auditing every call site - missing `await` returns a coroutine silently and the bug evades simple tests
- Refactoring a published package without a backward-compatibility plan - that is a public API
- Replacing `requests.get` with `httpx.AsyncClient` on a sync code path with no async benefit (premature change; `httpx.Client` sync is the right swap there)
- Replacing module-level mutable state by adding a thread-local without checking that the codebase actually uses threading vs asyncio - `threading.local` does not propagate across event loop tasks
