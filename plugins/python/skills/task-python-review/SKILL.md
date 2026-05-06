---
name: task-python-review
description: Python staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with FastAPI / Django idioms (async-in-sync mixing, blocking I/O in event loop, fat routers / views, ORM leak in API, Pydantic v2 misuse, missing `permission_classes`, anemic services). Spawns Python-specific perf / security / observability subagents for extra scopes. Stack-specific override of task-code-review for Python. Runs standalone with full PR/branch resolution.
agent: python-tech-lead
metadata:
  category: backend
  tags: [python, fastapi, django, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Python Code Review

## Purpose

Python-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Python-specific correctness, architecture, AI-quality, and maintainability checks (sync-in-async mixing, blocking I/O in the event loop, fat routers / views, ORM leak in API responses, Pydantic v2 mass assignment via `extra="allow"`, missing `permission_classes`, anemic services hiding behavior in helpers, Django callback-via-signal abuse). Coordinates Python-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Python. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a FastAPI or Django PR before merge
- Post-AI-generation quality gate on a Python change set
- Architecture drift detection in a Python codebase
- Pre-merge risk assessment on a Python branch

**Not for:**

- Pre-implementation feature design (use `task-python-new`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-python-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-python-review-perf`, `task-python-review-security`, or `task-python-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Python staff-level review                                  | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                   |
| --------------- | --------------------------------------------------------------------------- |
| Core            | Phases A-E only (Python-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-python-review-perf`                         |
| + Security      | Core + parallel subagent: `task-python-review-security`                     |
| + Observability | Core + parallel subagent: `task-python-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel Python subagents) |

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (Python-tuned):**

- File uploads (`UploadFile`, Django `request.FILES`), auth dependencies (`Depends(get_current_user)`, `OAuth2PasswordBearer`), DRF `permission_classes` / `authentication_classes` changes, Pydantic / DRF schema changes, raw SQL via `text(...)` / `cursor.execute(...)`, secrets in `settings.py` / `.env`, Celery tasks consuming user-supplied input → auto-add **+Security**
- New Alembic / Django migration, new ORM query (`select(...)` / `.filter(...)`), new `selectinload` / `prefetch_related`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `@cache` / `@lru_cache` / Redis read paths → auto-add **+Perf**
- New service module, new external client (`httpx.AsyncClient`, `requests.Session`), new Celery task or `@shared_task`, change to logging config / `LOGGING` dict / `structlog` setup, new Prometheus metric registration, new `@app.on_event` / lifespan handler, new Django signal → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                     | Meaning                                                                                                                                                                               |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-python-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-python-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-python-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-python-review pr-123 --base release/2026.05` - PR opened against release branch
- `/task-python-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-python-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Python. If invoked as a delegate of `task-code-review` (parent already detected Python), accept the pre-detected stack and skip re-detection. If the detected stack is not Python, stop and tell the user to invoke `/task-code-review` instead.

Detect framework: FastAPI (`fastapi` import + `main.py`) vs Django (`manage.py` + `settings.py`). Record `Framework: FastAPI | Django | mixed`. Each Phase B / C / D / E checklist below branches on this signal where the idiom differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 3 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. Make this explicit because the default of "skip if user did not pass `+security` etc." silently misses the cases where the change itself signals the need.

For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` -> stay on Core
- One signal category -> add the matching extra scope
- Two or more signal categories -> promote to Full
- User passed an explicit scope -> respect it (do not downgrade), but still record signals so the Summary documents why the chosen scope was correct

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`. If the user passed a scope and signals contradicted it, surface a one-line note so reviewers see what was deliberately deferred.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth dependencies / `permission_classes`, middleware, API contracts, shared base classes, `settings.py` / `app/core/config.py`, Alembic / Django migrations), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Phase B - Python Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness - through a Python lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding pytest coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication (OAuth2 / JWT / Django auth), authorization (`permission_classes` / FastAPI security dependencies), money or billing flows, data-integrity writes (multi-table transactions, state machines), Celery tasks that mutate data, migrations that change column semantics. Do not bury this finding in Key Takeaways - a separate, named entry in Findings.

**Python-specific correctness checks (both frameworks):**

- [ ] **Type hints on public functions** - return types and parameters typed; mypy / pyright not silently disabled mid-file
- [ ] **`async def` discipline (FastAPI)**: any function marked `async def` actually `await`s I/O; never blocks the event loop with `time.sleep`, `requests.get`, sync DB calls, CPU-heavy work. Sync handlers are acceptable when no async dependency is needed; mixing sync helpers inside `async def` is a bug
- [ ] **`await` everywhere** - missing `await` on a coroutine returns the coroutine object silently, not the result; lint via `RUF006` / `pyright` strict
- [ ] **Pydantic v2 (FastAPI)**: input schemas declare `model_config = ConfigDict(extra="forbid")` for user-facing endpoints (rejects unknown fields rather than silently dropping); `Field(...)` constraints on every user-supplied field; `from_attributes=True` on response models built from ORM rows
- [ ] **DRF serializer (Django)**: `fields` declared explicitly (never `"__all__"` for user-facing serializers); `read_only_fields` include server-controlled fields; `write_only_fields` for sensitive inputs; nested serializers handle null cases
- [ ] **Authorization on every endpoint**: every router method has explicit security dependency (FastAPI: `Depends(get_current_user)` or stronger) OR every ViewSet has `permission_classes` (Django); empty / missing is a finding regardless of "I forgot in the prototype"
- [ ] **No ORM entities returned from endpoints**: FastAPI endpoints return Pydantic models, not SQLAlchemy `Mapped[...]` instances; Django views serialize via DRF serializers, not raw `model_to_dict` (avoids unintended field exposure and serialization surprises)
- [ ] **Transaction boundaries**: writes happen inside an explicit transaction. FastAPI: session per request via `Depends(get_db)` with commit on success / rollback on exception. Django: `@transaction.atomic()` decorator or context manager for multi-write operations; `select_for_update` only inside transactions
- [ ] **Celery dispatch AFTER commit**: `task.delay(...)` invoked after `session.commit()` (FastAPI) or via `transaction.on_commit(lambda: task.delay(...))` (Django); dispatching inside the transaction is a smell - the worker may pick up before the row is visible
- [ ] **Error handling**: FastAPI `@app.exception_handler` / DRF `EXCEPTION_HANDLER` covers common exceptions (validation, not-found, permission, integrity error) with consistent error response shape; no blanket `except Exception:` swallowing root causes; no `print(traceback...)` / bare `traceback.print_exc()` in production code paths
- [ ] **Migration PRs (any change in `migrations/versions/` or `<app>/migrations/`)**: see the Migration PRs subsection below
- [ ] **Bulk operations**: partial-failure handling defined; idempotency for retryable bulk; `bulk_create` / `bulk_update` (Django) or batched `session.execute(insert(X), [...])` (SQLAlchemy) sized appropriately

**Migration PRs (any change under `migrations/versions/` or `<app>/migrations/`):**

- [ ] Two-phase deploys for column rename / drop (add new → backfill → cut over → remove old)
- [ ] `NOT NULL` on existing columns added via two-step (add nullable → backfill → set NOT NULL via separate migration)
- [ ] Indexes on large tables use `CREATE INDEX CONCURRENTLY` (PostgreSQL); Alembic via `op.execute(...)` with `transaction_per_migration=True`; Django via `RunSQL` with `atomic = False`
- [ ] **`SET lock_timeout`** before DDL on large tables to fail fast
- [ ] Foreign keys added with validation deferred (or as a separate validate step)
- [ ] Data migrations isolated from DDL migrations; long-running data backfills not in the same Alembic / Django migration as the schema change; backfills via keyset pagination, never `WHERE col IS NULL LIMIT N`
- [ ] Rollback path documented or verified
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact
- Use skill: `python-migration-safety` for canonical safe-migration patterns

**Concurrency safety:**

- [ ] No mutable global state in modules; if state is required, it is module-level constant or guarded (`threading.Lock` for sync, `asyncio.Lock` for async)
- [ ] Race-prone updates (counters, balance changes, state transitions) use database-level locking (`SELECT ... FOR UPDATE`, `select_for_update()`, optimistic version field, or Postgres advisory lock)
- [ ] Cache writes thread-safe / async-safe; cache keys deterministic; no race window between cache miss and cache fill on hot keys (use single-flight via `asyncio.Lock` per key or Redis `SET NX EX`)
- [ ] No sharing of `httpx.AsyncClient` / `requests.Session` across event loops or threads in unsafe ways

Use skill: `python-sqlalchemy-patterns` for canonical SQLAlchemy correctness patterns.
Use skill: `python-django-patterns` for canonical Django ORM patterns.
Use skill: `python-async-patterns` for any new or modified `async def` / event-loop code.
Use skill: `python-celery-patterns` for any new Celery task or dispatch path.

### Phase C - Python Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Python-specific architecture checks:**

- [ ] **Layering (FastAPI)**: router → service → repository → model. No business logic in routers; no `httpx` calls in repositories; no Pydantic schema construction in repositories. Repositories return ORM rows or DTOs; mapping to response schemas happens at the service or router boundary, not in the repository
- [ ] **Layering (Django)**: view / ViewSet → service → manager / queryset → model. No business logic in views beyond orchestration; no direct ORM in templates; service layer for cross-model orchestration
- [ ] **Service-layer discipline**: any router / view method with > 10 lines of orchestration is extracted to a service module; services expose intention-revealing names (`fulfill_order(order_id)` not `process_order_step_2`); cross-aggregate orchestration lives in a service, not in Django signals or SQLAlchemy event listeners
- [ ] **Anemic domain antipattern**: when business rules accumulate in services and models are pure data containers (Django) or `Mapped[...]` schemas (SQLAlchemy), flag for refactor (see `task-python-refactor`); push behavior into models / domain objects where it belongs to the aggregate's invariants
- [ ] **Dependency injection style (FastAPI)**: `Depends` used consistently; constructor injection for services where possible; no module-level singletons created on import that hold mutable state
- [ ] **Settings discipline**: typed settings via `pydantic-settings` `BaseSettings` (FastAPI) or `django-environ` (Django); profile-separated config (`Settings(env_file=...)`); no hardcoded values that should be env vars
- [ ] **Module / package boundaries**: feature-package layout (`app/orders/{router,service,repository,schema}.py`) preferred over layer-package layout (`app/routers/`, `app/services/`, `app/repositories/`); cross-feature imports go through public service interfaces, not direct repository imports
- [ ] **Multi-tenant isolation**: tenant scoping enforced at the repository / queryset layer (`with_loader_criteria` / `Manager` override), not at the router / view layer alone
- [ ] **Read replica / multi-database**: when the app uses Django routing or SQLAlchemy `bind` per query, queries declare their target explicitly; no surprise cross-database joins
- [ ] **Signal / event discipline (Django)**: signals (`post_save`, `pre_delete`) used for genuinely cross-cutting concerns (audit, search index sync) - not as a hidden control-flow mechanism dispatching emails / Celery tasks. SQLAlchemy event listeners similarly. Move business logic to explicit service calls

**Multi-service PRs (when change spans 2+ services or this Python app + a separate service):**

- API contract compatibility checked (`schemathesis`, Pact, or OpenAPI diff)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**Python-specific AI smells:**

- [ ] **Pattern inflation**: a service module + abstract base class + single concrete implementation where the ABC adds no value (no second implementation, no test double); a custom `Result[T]` wrapper where domain exceptions or `Optional` would suffice; a class created where a module-level function would do
- [ ] **Over-abstraction**: `BaseService` / `BaseRepository` parent classes for two children; premature `Protocol` for one consumer; `Factory` modules for objects that have one constructor path
- [ ] **Speculative configurability**: settings keys with documented but unused values; profile-conditional code paths for environments that do not exist; feature flags with no off path
- [ ] **Redundant mapping layers**: `Model → DomainObject → ServiceDTO → ResponseSchema` when one mapping would suffice; multiple Pydantic schemas / DRF serializers chained 3+ deep
- [ ] **Test verbosity**: `@pytest.fixture` setup blocks > 30 lines for a single assertion; `mocker.patch` chains that could be a unit test on a smaller surface; `assert response.json() == {...full dict...}` when a few key field assertions would suffice
- [ ] **Async misapplication**: `async def` on functions that do no I/O ("just in case we go async") - the runtime cost without the benefit. Conversely, sync helpers inside `async def` paths that block the loop
- [ ] **Pydantic / DRF noise**: identical schemas reimplemented per endpoint; `Field(default=None, description="...")` boilerplate where defaults are framework-provided
- [ ] **Comment cruft**: comments restating function names; `# end of function foo` markers; docstrings on private helpers that just repeat the signature; auto-generated TODOs left in
- [ ] **`# type: ignore` proliferation**: legitimate uses are rare; `# type: ignore[attr-defined]` to bypass a real bug is a finding

### Phase E - Python Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Python-specific maintainability checks:**

- [ ] **Naming conventions**: services describe their operation (`order_fulfillment.py` over `order_helper.py`); schemas / serializers named after their role (`OrderCreateRequest`, `OrderResponse`); no `Util` / `Manager` / `Helper` modules accumulating unrelated functions; `_private` prefix for module-private helpers
- [ ] **Magic numbers / strings**: extracted to module-level constants or `BaseSettings` keys; date/time constants use `timedelta(minutes=...)` not `60_000`
- [ ] **Hardcoded URLs / credentials**: in env vars, Vault, or settings - never inline in code
- [ ] **Function length**: functions > 30 lines reviewed for extraction; functions > 60 lines flagged unless they are a clearly orchestrating service function calling intention-revealing private helpers
- [ ] **Duplicated query logic**: same `.filter(...)` / `select(...)` predicate in 3+ places extracted to a manager method or repository method
- [ ] **Logging hygiene**: structured logger (`structlog`, stdlib `logging` with formatter) over `print`; parameterized logging (`logger.info("processing order=%s", order_id)`) not f-strings (`logger.info(f"processing order={order_id}")`) - the difference matters when the log format changes; log levels used correctly (`error` for actionable failures, `warning` for recoverable anomalies, `info` for state transitions, `debug` for verbose); structured fields when configured (delegate to `task-python-review-observability` for depth)

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-python-review-observability` subagent owns the depth review).

### Step 4 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                            |
| -------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-python-review-perf`                                                                                 |
| Core + Security      | 1 subagent running `task-python-review-security`                                                                             |
| Core + Observability | 1 subagent running `task-python-review-observability`                                                                        |
| Full                 | 3 subagents running `task-python-review-perf`, `task-python-review-security`, `task-python-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Python) and detected framework (FastAPI / Django / mixed) so the subagent skips its own `stack-detect` and framework branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 5 - Synthesize (only if Step 4 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a synchronous `requests.get` inside an `async def` can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Python idiom: blocking `requests.get` in `async def`, missing `permission_classes`, ORM model returned from endpoint, Celery `.delay()` inside transaction, `extra="allow"` on input schema, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Python change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

## Architecture Notes

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Replace `requests.get(url)` with `await client.get(url)` in OrderService.fetch_inventory; client is the module-level `httpx.AsyncClient` singleton"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Python conventions, not generic backend conventions
- Provide actionable feedback with Python code examples
- Never comment on trivial formatting or style where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Python subagent rather than duplicating the check here

## Self-Check

- [ ] Stack confirmed as Python (or accepted from parent dispatcher); framework detected and recorded
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If user passed `--base`, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated in Step 3; promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; promotion recorded in Summary
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B Python correctness checks applied: `async def` discipline, await everywhere, Pydantic v2 / DRF serializer rules, authorization on every endpoint, ORM-in-API leakage, transaction boundaries, post-commit Celery dispatch
- [ ] Phase C Python architecture checks applied: layering, anemic domain, settings discipline, signal / event listener discipline, package boundaries, multi-tenant
- [ ] Phase D AI-quality checks applied: pattern inflation, single-impl ABCs, over-abstraction, speculative configurability, async misapplication
- [ ] Phase E Python maintainability checks applied: naming, magic numbers, function length, parameterized structured logging
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Python fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Python-specific subagents (`task-python-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus framework detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Python idiom exists (say "extract to a service module", not "extract to a helper class")
- Nitpicking style where no project standard exists; no `[Nitpick]` or `[Praise]` labels
- Providing vague feedback without a concrete Python fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Python subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending `requests` / `urllib3` synchronous calls in `async def` paths, `pickle.loads` / `yaml.load` on untrusted input, or `extra="allow"` on user-facing Pydantic schemas as acceptable patterns - all are anti-patterns
