---
name: task-python-review
description: "Python / FastAPI / Django code review: async pitfalls, blocking I/O, ORM leaks, Pydantic v2, auth; spawns perf/security/obs/reliability subagents."
agent: python-tech-lead
metadata:
  category: backend
  tags: [python, fastapi, django, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Python Code Review

Staff-level Python / FastAPI / Django code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability / reliability subagents in parallel for extra scopes. Runs standalone with full PR / branch resolution.

## When to Use

- Pre-merge review on a FastAPI or Django PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-python-implement`), single-error debugging, new-system architecture design, or a single-scope review - delegate to `task-python-review-perf` / `-security` / `-observability` / `-reliability`.

## Depth Levels

| Depth      | When                                                | Runs                                                                                                                      |
| ---------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `standard` | Default                                             | Phases A-E on diff hunks plus immediate context                                                                           |
| `deep`     | Architecture PRs, post-incident, Principal sign-off | A-E with touched files read in full, plus `git log -S<smell>` / `--follow` on touched files for prior fixes of the same smell and prior PRs on the same module, cited in Key Takeaways |

**Auto-promote to `deep`:** after Phase A, if `Blast Radius` is Wide or Critical, set depth to `deep` before Phases B-E and record it on the Summary's Depth line as `deep; auto-promoted from standard; Blast Radius: <level>`. On round 2+, user flag > this round's auto-promotion; nothing is inherited. When the resolved depth falls below the checkpoint's, the Depth line gains `narrowed vs round <prior.round> - re-run with deep to re-cover`.

## Scope

| Scope  | What runs                                       |
| ------ | ----------------------------------------------- |
| Core   | Phases A-E (Python-flavored)                    |
| + Perf | Core + `task-python-review-perf` subagent        |
| + Sec  | Core + `task-python-review-security` subagent    |
| + Obs  | Core + `task-python-review-observability` subagent |
| + Rel  | Core + `task-python-review-reliability` subagent |
| Full   | Core + all four subagents in parallel            |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Python-tuned):**

- **+Sec:** file uploads (`UploadFile`, `request.FILES`), auth dependencies (`Depends(get_current_user)`, `OAuth2PasswordBearer`), DRF `permission_classes` / `authentication_classes` changes, Pydantic / DRF schema changes, raw SQL via `text(...)` / `cursor.execute(...)`, secrets in `settings.py` / `.env`, Celery tasks consuming user-supplied input
- **+Perf:** new Alembic / Django migration, new ORM query (`select(...)` / `.filter(...)`), new `selectinload` / `prefetch_related`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `@cache` / `@lru_cache` / Redis read paths
- **+Obs:** new service module, new external client (`httpx.AsyncClient`, `requests.Session`), new Celery task or `@shared_task`, logging config change (`LOGGING` dict / `structlog`), new Prometheus metric, new lifespan handler, new Django signal
- **+Rel:** new `httpx` / external client without an explicit `Timeout`, new `tenacity` / retry config, new Celery task without `acks_late` / an idempotency guard, `BackgroundTasks` for a critical side effect (payment, email), unbounded `asyncio.gather`, `save` + publish dual write or `.delay()` inside a transaction
- **2+ categories -> Full**

## Invocation

`/task-python-review [<branch> | pr-<N>] [core-only | +perf | +sec | +obs | +rel | full] [standard | deep] [--base <branch>] [--req <path>]` - flags compose: `/task-python-review pr-50273 --base release/2026.05 +sec deep`. No argument reviews the current branch vs its base and fails fast on trunk; `pr-<N>` needs the local branch the user fetched (`git fetch origin pull/<N>/head:pr-<N>`). `--req <path>` names a requirement source (ticket export, PRD, spec) for Phase 0; without it, Phase 0 uses whatever requirement is already in context.

**No checkout required.** The workflow reads via ref-qualified diffs and never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Framework

Use skill: `stack-detect`. If `Language` is not Python, stop and recommend `/task-code-review`. `Framework` comes from the block (`FastAPI 0.115`, `Django 5.1`); the dependency manifest fills `unknown` and reveals a second framework - `fastapi` -> FastAPI, `django` -> Django; both named -> the one framework the name-status (Step 4) touches, else `mixed` (files under both or neither; both framework branches of Phases B, C and D run); neither names FastAPI or Django (Flask, plain Python) -> `unknown`: Phases B and C run their framework-neutral checks, only the APIs a check names from a framework the project does not use go N/A, and Phase D loads no necessity skill. Record `Framework: FastAPI | Django | mixed | unknown` - FastAPI / Django with a version (the block's when it names that framework with one, else its manifest pin, else omitted) - and the Python version (`Language`, else `requires-python` / `.python-version`, else `unknown`).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with `argument`, `base` (from `--base`), and `report_type: review`. On failure, surface its message verbatim and stop. Hold the handle's `prior_checkpoint` and `report_path` for Step 4.

Capture `current_base_sha = git rev-parse <base_ref>` and `current_head_sha = git rev-parse <head_ref>`. Nothing else is read until Step 4 has decided the round.

### Step 4 - Decide the Round

**Every round analyzes the full `<base_ref>...<head_ref>` range.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change every round, so a small follow-up commit cannot under-score a large PR and a defect missed in round 1 stays reachable in round 2. Rounds differ only in that round 2+ reconciles against the prior report.

- No `prior_checkpoint` -> `round = 1`.
- `prior_checkpoint: legacy` -> `round = 1`; Summary note `Prior report lacks checkpoint metadata - treated as round 1.`
- Valid checkpoint: when `handle.head_is_remote` is true, `git fetch <remote> <branch>` (the one state-changing git command this workflow runs; failure is silent) and re-capture `current_head_sha`. Then compare:

| Condition                                                                                   | Decision                                                                                                     |
| ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `prior.head_sha == current_head_sha` and the invocation adds no scope or depth beyond the checkpoint | **No-op.** Print `No new commits on <head_short_name> since prior review at <first 7 of current_head_sha>. Prior report unchanged.` and stop - no report write |
| `prior.head_sha == current_head_sha`, scope or depth expanded                               | `round = prior.round + 1`; note `Same head as round <prior.round>; re-review for expanded <scope\|depth>.`  |
| `git merge-base --is-ancestor <prior.head_sha> <current_head_sha>` fails                     | `round = prior.round + 1`; note `Prior checkpoint unreachable - history rewritten.`                          |
| `prior.base_sha != current_base_sha` or `prior.base_ref != base_ref`                        | `round = prior.round + 1`; note `Base advanced since round <prior.round>.`                                   |
| None of the above                                                                           | `round = prior.round + 1`                                                                                    |

Scope expanded vs the prior round (round 1 `core-only`, round 2 `full`): the new scopes have no prior findings to reconcile; the Scope line gains `expanded round <N>: +<list>`.

After the decision (the no-op exit excluded), read once and reuse: `git diff <base_ref>...<head_ref>`, `git diff --name-status <base_ref>...<head_ref>`, `git log <base_ref>..<head_ref>` (full messages - Phase 0 reads criteria from commit bodies).

### Step 5 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals under **Scope**. Note each fire as `<category> -> <file:line>`; the Scope line carries them - `auto-escalated from Core; signals: <list>` when escalated, `signals: <list>` when an explicit scope was respected, `suppressed: <list>` under `core-only`. Zero signals or `core-only` -> Core; one category -> that scope; 2+ -> Full; an explicit user scope is respected. On round 2+, user flag > firing signals, nothing inherited; when the resolved scope falls below the checkpoint's, the Scope line gains `narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover`.

### Phase 0 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and full commit log, the `--req <path>` file when passed, and the handle's `report_path` (as `prior_report_path`) when round > 1.

Its `## Change Brief` goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into the Summary, and its findings join the set verified in Step 7. With no requirement source the Brief still renders and the traceability block and both Summary lines are omitted. Runs before Phase A - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it. A Phase 0 finding and a Phase B finding making the same claim on the same `file:line` merge into one entry at the stronger label; different claims stay separate.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure-propagation scope; gate on its mitigated (second) value only when the `Mitigation:` tag is `in-place:`, otherwise on the unmitigated value

Output risk level and blast radius before any findings.

**Low-risk short-circuit:** when Risk Level is Low, Blast Radius is Narrow, **and** the change touches no architecture-relevant file (auth dependencies / `permission_classes`, middleware, API contracts, shared base classes, `settings.py` / `app/core/config.py`, migrations), skip Phases C-D and run **B + E only**; Phase 0 outputs still render and round 2+ still reconciles.

### Phase B - Python Correctness and Safety

Apply the atomic skills; each owns the canonical patterns, this phase flags deviations and adds what they do not see:

- Use skill: `python-sqlalchemy-patterns` (SQLAlchemy) or `python-django-patterns` (Django ORM) - transactions, eager loading, post-commit dispatch
- Use skill: `python-async-patterns` for any new or modified `async def` / event-loop code
- Use skill: `python-celery-patterns` if the diff touches Celery tasks or `@shared_task`
- Use skill: `python-migration-safety` if the diff touches Alembic revision files (`<script_location>/versions/`, `alembic/versions/` after `alembic init alembic`) or `<app>/migrations/`; also use skill: `ops-backward-compatibility` for client / in-flight impact
- **API contract change** - when the diff carries a contract-change signal (a removed / renamed / retyped response-model field, a changed `status_code`, a new **required** request field or tightened validator (`Field(...)`, `pattern`, `extra="forbid"`), a new public route on a `/v1/`-versioned or externally consumed API, a route returning a raw ORM row with no `response_model` or a DRF `ModelSerializer` with `"__all__"`, or a drf-spectacular schema edit), use skill: `backend-api-guidelines` and use skill: `ops-backward-compatibility`. Judge breakage from the consumer's view ("no external callers" needs a search; when consumption is unknown, a `/v1/`-versioned or spec-published surface counts as externally consumed); responses go through a `response_model` / serializer, never a raw ORM row; errors follow RFC 9457; collections paginated; a committed OpenAPI artifact or generated client matches the code (framework-served auto-docs with no committed artifact have nothing to drift). Each finding names who breaks and how. High -> `[Must]` = unversioned breaking change to an externally consumed contract, or a leaked ORM shape on an externally consumed / versioned surface; Medium -> `[Recommend]` = internal breaking change with no coordinated-deploy note, inconsistent status / error envelope, unpaginated unbounded collection, committed schema or client out of sync; Low = naming drift with no consumer impact - below the bar, write nothing. A leaked ORM shape on an internal-only surface stays with **Response model field hygiene** at `[Recommend]`; one finding per `file:line` either way

**Additional Python-specific checks the atomics don't own:**

- **Test coverage finding (named, not buried).** PR adds logic without pytest coverage -> `[Recommend]`; `[Must]` when the change is critical path: auth (OAuth2 / JWT / Django auth), authorization (`permission_classes` / FastAPI security dependencies), money / billing, multi-table writes, state machines, Celery mutators, migrations changing column semantics. **Test files are reviewed for coverage only:** the only finding on a test file is a coverage gap, anchored to the untested production `file:line` with the case to cover - never style, structure, duplication, or performance of test code.
- **Type hints on public functions.** Return types and parameters typed; mypy / pyright not silently disabled mid-file.
- **`async def` discipline + `await` everywhere (FastAPI).** No blocking I/O on the event loop (sync drivers, `requests`, `time.sleep`, Celery `.delay()` without `run_in_threadpool`), no missing `await` returning a coroutine object. Catalog in `python-async-patterns`.
- **Pydantic v2 (FastAPI).** Input schemas declare `model_config = ConfigDict(extra="forbid")` for user-facing endpoints; `Field(...)` constraints on user inputs; `from_attributes=True` on response models built via `model_validate(orm_row)`. A declared privilege field (`tenant_id`, `role`, `owner_id`) or `extra="allow"` on user input is a mass-assignment surface.
- **DRF serializer (Django).** `fields` declared explicitly (never `"__all__"` user-facing); `read_only_fields` for server-controlled fields; write-only via `extra_kwargs={"password": {"write_only": True}}` - a `write_only_fields` Meta option is silently ignored.
- **Authorization + IDOR.** Authn (`Depends(get_current_user)` / `permission_classes`) proves identity, not object access. Per-owner / per-tenant endpoints scope at the repository: `where(...id == user.id)`, `tenant_id` injected by middleware.
- **Response model field hygiene.** Compare the Pydantic / DRF response model against ORM columns. Flag `password_hash` / `mfa_secret` / `internal_notes` / `audit_log` / `is_test` / `last_login_ip` on the wire. Returning a `Mapped[...]` row or `model_to_dict` with no `response_model` / serializer is `[Recommend]` regardless of current fields - a new sensitive column leaks later.
- **HTTP `Idempotency-Key` on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` accept the header and dedupe via a DB unique constraint. Distinct from worker-side task idempotency.
- **Transaction boundaries + post-commit Celery dispatch.** Writes inside an explicit transaction; FastAPI `await run_in_threadpool(task.delay, id)` after `session.commit()`; Django `transaction.on_commit(...)`.
- **Multi-replica race safety.** Counters / balances / state transitions use DB locking (`SELECT ... FOR UPDATE`, `select_for_update()`, advisory lock) or an optimistic version field, not module globals.
- **HTTP client sharing.** `httpx.AsyncClient` constructed once in the lifespan handler and held on `app.state` (`requests.Session` once per Celery worker process); per-request instantiation breaks connection reuse; module-level construction ties pooled connections to whichever loop first used them (`RuntimeError: Event loop is closed` under a second loop) and nothing closes the client on shutdown.
- **SSRF + edge middleware presence.** User-controlled values in outbound URLs flagged here; `CORSMiddleware`, `TrustedHostMiddleware`, HTTPS redirect confirmed when app construction changes. Depth in the security subagent.
- **New ORM column with predicate use.** A new `Mapped[...]` / model field referenced in `.where(...)` / `.filter(...)` / `.order_by(...)` has an index migration in the same PR, or an explicit "indexed later" note.
- **Error handling.** Framework exception handler covers validation / not-found / permission / integrity with a consistent shape; no blanket `except Exception:` swallowing root causes.

### Phase C - Python Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Python-specific:**

- **Layering (FastAPI):** router -> service -> repository -> model. No business logic in routers; no `httpx` in repositories; Pydantic mapping at the service / router boundary, not in repositories
- **Layering (Django):** view / ViewSet -> service -> manager / queryset -> model. No business logic in views beyond orchestration; a service layer for cross-model orchestration
- **Service-layer discipline:** router / view methods > 10 lines of orchestration extracted to a service; intention-revealing names (`fulfill_order` not `process_order_step_2`); cross-aggregate orchestration in services, not in Django signals or SQLAlchemy event listeners
- **Dependency injection (FastAPI):** `Depends` used consistently; constructor injection for services; no module-level singletons holding mutable state created on import
- **Settings discipline:** typed settings via `pydantic-settings` `BaseSettings` (FastAPI) or `django-environ` (Django); no hardcoded values that should be env vars
- **Feature-package layout** (`app/orders/{router,service,repository,schema}.py`) preferred over layer-package; cross-feature imports go through public service interfaces, not direct repository imports
- **Multi-tenant isolation** enforced at the repository / queryset layer (`with_loader_criteria` / `Manager` override), not at routers / views alone
- **Signal / event discipline:** Django `post_save` / `pre_delete` and SQLAlchemy event listeners reserved for genuinely cross-cutting concerns (audit, search index) - not hidden control flow dispatching emails / Celery tasks
- **Anemic domain (deep only):** business rules accumulating in services while ORM models stay pure data - flag for refactoring; never on a single PR's evidence alone

**Multi-service PRs:** API contract compatibility (OpenAPI diff, `schemathesis`, Pact); deployment order documented or independent; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering, simplification
- Load the necessity skill for the resolved `Framework` (both under `mixed`, none under `unknown`), passing each its own framework as the detected `Framework:` line, which its gate reads: **FastAPI:** use skill: `python-fastapi-overengineering-review`; **Django:** use skill: `python-django-overengineering-review`

**Additional Python AI smells the atomics don't own:** test verbosity (`@pytest.fixture` setup > 30 lines for one assertion; full deep-equal where a few field assertions would do); async misapplication (`async def` on functions doing no I/O; sync helpers blocking inside `async def` paths); comment cruft (docstrings on private helpers restating the signature; auto-generated TODOs left in); `# type: ignore[...]` proliferation in non-test code silencing a real type bug.

### Phase E - Maintainability and Clarity

Use skill: `backend-coding-standards` for cross-language naming. Use skill: `ops-observability` for cross-cutting logging / metrics presence (depth belongs to `task-python-review-observability`).

**Python-specific:**

- **Naming:** services describe their operation (`order_fulfillment.py` over `order_helper.py`); schemas named after role (`OrderCreateRequest`, `OrderResponse`); no `Util` / `Manager` / `Helper` modules; `_private` prefix for module-private helpers
- **Magic numbers / strings:** extracted to module-level constants or `BaseSettings`; `timedelta(minutes=...)` over `60_000`
- **Hardcoded URLs / credentials:** env / Vault / settings, not inline
- **Function length:** > 30 lines extracted; > 60 lines flagged unless clearly orchestrating
- **Duplicated query logic:** the same `.filter(...)` / `select(...)` predicate in 3+ places extracted to a manager or repository method
- **Logging hygiene:** `print(...)` in prod paths, f-string log calls (`logger.info(f"...")` over `logger.info("order=%s", order_id)`), wrong levels as `[Recommend]` (depth in the observability subagent)

### Step 6 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip. For each selected scope, spawn one subagent **in parallel** with the main thread, using the **declared `subagent_type`** - never infer the agent from the scope name:

| Scope  | Skill                              | Subagent (`subagent_type`)      |
| ------ | ---------------------------------- | ------------------------------- |
| + Perf | `task-python-review-perf`          | `python-performance-engineer`   |
| + Sec  | `task-python-review-security`      | `python-security-engineer`      |
| + Obs  | `task-python-review-observability` | `python-observability-engineer` |
| + Rel  | `task-python-review-reliability`   | `python-reliability-engineer`   |

**Subagent prompt contract** - each prompt carries: the precondition handle plus the pre-read diff, name-status and commit log (no re-running git); the depth; the stack-detect block and `Framework`; the instruction to load `behavioral-principles` and return findings in its own Output Format's subagent envelope (no report file). **Failure isolation:** a subagent that fails or times out does not stop the review; note the scope in the Summary's Scope line as `incomplete: <scope>`.

**Synthesize** (only when Step 6 ran): merge subagent findings into the single Output Format below - never append raw reports. Deduplicate cross-cutting findings (one entry citing all scopes that raised it); lens impact maps to intent (High / Critical -> `[Must]`, Medium / Low -> `[Recommend]`) and the strongest intent wins when they differ; preserve `file:line`; order by intent, not scope; lens `out of lens` lines become candidate findings for the owning phase; the security lens's `## OWASP Triage` and the observability lens's `## Surface Map` are dedupe input only and are not emitted; Next Steps are built from the published findings; keep deep-only sections subagents return (perf's `Capacity and Load Plan`, reliability's `Failure-Mode and Blast-Radius Map`) as their own sections after Next Steps.

### Step 7 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the assembled findings (Phase 0, Phases B-E, merged subagent findings), the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, taking each row's `file:line`, `Label`, and `Annotation`; its tally is the Summary's `Findings verified:` line and the table itself is not rendered. Runs before reconciliation so prior-round matching sees the corrected set.

### Step 8 - Reconcile Prior Findings (round 2+ only)

Use skill: `review-prior-findings-reconcile` with `prior_report` (the body of the file at the handle's `report_path`, frontmatter excluded - its `## High-Impact Findings` headings already carry `[Label] file:line` and annotation groups), the full-range `diff`, the full-range `name_status`, and `head_sha = current_head_sha`. Its output renders verbatim under `## Prior Round Reconciliation`.

A `Still open` / `Needs re-check` row this round did not re-derive publishes in `## High-Impact Findings` at its prior label (`[Blocker]` / `[High]` / `[Critical]` -> `[Must]`; other legacy labels -> `[Recommend]`; `[Praise]` never carried) with `_(carried from round <N>)_` as the last annotation group, and in Next Steps with the suffix `(open since round <N>)`; a row this round re-derived publishes once, as this round's finding. No separate carry-over section.

### Step 9 - Write Report

Use skill: `review-report-writer` with `report_type: review`, `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` from the handle, `base_sha = current_base_sha`, `head_sha = current_head_sha`, `mode: full`, `round` (from Step 4) and `prior_head_sha` (round > 1), `scope` mapped to the writer's enum (`Core` -> `core-only`; lenses that completed - an `incomplete` lens is excluded - as space-joined `+perf +sec +obs +rel` in that order; all four -> `full`; none completed -> `core-only`), `depth` (resolved / auto-promoted), `stack` from `Framework` (`python-fastapi | python-django | python-mixed | python`), and `pr_url` when the prior checkpoint has it. Write before ending; print the confirmation line.

## Output Format

The fence delimits the template for display only; emit `report_body` as raw Markdown, never wrapped in a fence. Every finding carries exactly one label, `[Must]` (do not merge until fixed) or `[Recommend]` (fix, or push back with reasoning; never silently acked); verify's published `Label` governs every slot naming one. A finding on a file absent from the name-status whose Annotation has no group opening `pre-existing` gets `_(pre-existing)_`, written first; an `Unverified` row gets none, and an old line in a touched file takes verify's attribution. Verify's combined `_(pre-existing; newly reachable via X)_` is published as two groups, `_(pre-existing)_ _(newly reachable via X)_`. Brace annotations are authoring notes and are never emitted; empty sections are omitted.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical
- **Stack:** Python <version>
- **Framework:** FastAPI{ <version>} | Django{ <version>} | mixed | unknown
- **Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full{; auto-escalated from Core; signals: <list>}{; signals: <list>}{; suppressed: <list>}{; incomplete: <scope>}{; expanded round <N>: +<list>}{; narrowed vs round <N>: <list> - re-run with <flags> to re-cover}
- **Depth:** standard | deep{; auto-promoted from standard; Blast Radius: <level>}{; narrowed vs round <N> - re-run with deep to re-cover}
- **Round:** <N>{; <Step 4 note>}   {round 2+, or round 1 when the legacy note applies}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}
- **Requirement Source:** <path or origin> (Specified | Self-attested)   {with the next line, only when Phase 0 resolved a source}
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when none resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability   {only when Phase 0 resolved a source}

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line{ (pre-existing)}, or `-`> | <file:line or verification note{ (pre-existing)}, or `-`> |

## Prior Round Reconciliation   {round 2+ only}

[reconcile's output verbatim - table, note lines, tally]

## High-Impact Findings

### [Must] file:line{ _(annotation)_}{ _(carried from round <N>)_}

- Issue: [the Python idiom: blocking `requests.get` in `async def`, missing `permission_classes`, ORM row returned from an endpoint, `.delay()` inside a transaction, declared `tenant_id` on an input schema]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not a local bug]
- Fix: [concrete Python change with code]

### [Recommend] file:line{ _(annotation)_}{ _(carried from round <N>)_}

- Issue: ...
- Impact: ...
- Fix: ...

## Architecture Notes

_Cross-cutting commentary; reference findings by file:line, never restate them._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge; at `deep`, the prior fixes and PRs the history search surfaced.

## Next Steps   {when at least one published finding}

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] file:line - [one-line action] (open since round <N>)
3. **[Delegate]** [Recommend] file:line [scope: cross-service] - [one-line action]

## Capacity and Load Plan   {only when a deep perf subagent returned one}

[the subagent's section verbatim]

## Failure-Mode and Blast-Radius Map   {only when a deep reliability subagent returned one}

[the subagent's table verbatim]
```

`[Must]` first, then `[Recommend]`, then by `file:line` - in High-Impact Findings and Next Steps alike. `[Implement]` = a localized fix; `[Delegate]` = cross-cutting or cross-service work, `[scope: <owner>]` free text.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed Python; `Framework` and Python version taken from stack-detect or the manifest; `mixed` settled from the name-status
- [ ] Step 3: precondition called with `argument` / `base` / `report_type: review`; SHAs captured; nothing else read yet
- [ ] Step 4: round decided (1 / prior + 1 / no-op) on the full range; fetch attempted only for a remote head with a valid checkpoint; no-op path exited before any read; diff, name-status and full log read once after the decision
- [ ] Step 5: scope signals logged; escalation, `core-only` suppression, expansion / narrowing recorded on the Scope line
- [ ] Phase 0: `review-change-intent` ran on the full range; Change Brief carried verbatim; requirement lines present or all three requirement outputs omitted; its findings verified with the rest
- [ ] Phase A: risk level and blast radius stated before any finding; mitigated value used only under `in-place:`; depth auto-promoted on Wide / Critical; low-risk short-circuit applied only when no architecture-relevant file changed
- [ ] Phase B: atomics applied (ORM, async, Celery, migration safety, API contract gate when a route / model / serializer / schema changed); coverage finding named; async discipline, Pydantic / DRF rules, authorization, response hygiene, Idempotency-Key, race safety, client lifetime checked
- [ ] Phase C: layering, DI, settings, signal / listener discipline, package boundaries, multi-tenant checked; `architecture-guardrail` applied
- [ ] Phase D: `complexity-review` applied, plus the necessity skill per resolved framework (both under `mixed`, none under `unknown`), each passed its own `Framework:` line; AI smells covered
- [ ] Phase E: naming, magic numbers, function length, duplicated queries, logging hygiene checked
- [ ] Step 6: extra scopes spawned in parallel with the declared `subagent_type` and the prompt contract; findings merged (dedupe, impact -> intent, strongest wins); failed scope noted `incomplete: <scope>`; deep-only sections kept
- [ ] Step 7: `review-finding-verify` ran on every assembled finding; Dropped excluded; `file:line` / `Label` / `Annotation` published; tally in Summary
- [ ] Step 8: round 2+ reconciled with `head_sha` and the handle's `report_path`; unresolved rows carried into High-Impact Findings and Next Steps with `(open since round <N>)`
- [ ] Step 9: report written via `review-report-writer` with every field (branch, refs, SHAs, mode, round, prior_head_sha, writer-enum scope, depth, stack, pr_url); confirmation printed
- [ ] Every `[Must]` cites system risk; every finding has a label, `file:line`, and an actionable Python fix

## Avoid

- State-changing git from this workflow - the one exception is `git fetch <remote> <branch>` in Step 4 for a remote head with a valid prior checkpoint
- Scoping round 2+ analysis to `<prior_head_sha>...<head_sha>` - every round scores the full range
- Writing the report on a no-op exit - the file stays byte-identical
- Generic backend conventions when a Python idiom exists ("extract to a service module", not "extract to a helper class")
- Vague feedback ("this could be better"); blocking on personal preference
- Duplicating perf / security / observability / reliability depth here when the dedicated subagent owns it, or running extra scopes sequentially
- Appending raw subagent reports instead of merging
- Reconciling against prior Architecture / Maintainability notes - only `## High-Impact Findings` rows count
- Recommending `pickle.loads` / `yaml.load` on untrusted input, or `extra="allow"` on user-facing Pydantic schemas, as acceptable patterns
