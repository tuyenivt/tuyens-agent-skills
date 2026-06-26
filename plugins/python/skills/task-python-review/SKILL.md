---
name: task-python-review
description: "Python / FastAPI / Django code review: async pitfalls, blocking I/O, ORM leaks, Pydantic v2, auth; spawns perf/security/observability subagents."
agent: python-tech-lead
metadata:
  category: backend
  tags: [python, fastapi, django, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.
>
> **Spec-aware mode:** If `--spec <slug>` or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles`. Cross-check every changed surface against `spec.md` / `plan.md`: each change must trace to an AC, NFR, or task; out-of-scope changes are **blockers**; missing in-scope coverage is a gap. Never edit spec artifacts.

# Python Code Review

Staff-level Python / FastAPI / Django code review umbrella. Covers correctness, architecture, AI-quality, and maintainability. Coordinates perf / security / observability subagents in parallel for extra scopes. Runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge review on a FastAPI or Django PR
- Post-AI-generation quality gate
- Architecture drift detection
- Pre-merge risk assessment

**Not for:**
- Pre-implementation design (`task-python-implement`)
- Production incident (`/task-oncall-start`)
- Single-error debug (`task-python-debug`)
- New-system architecture (`task-design-architecture`)
- Single-scope reviews - delegate to `task-python-review-perf` / `-security` / `-observability`

## Depth Levels

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture PRs, post-incident, Principal sign-off | A-E + historical pattern matching + cross-PR context |

**Auto-promote to `deep`:** After Phase A, if `Blast Radius` is Wide or Critical, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E (Python-flavored) |
| + Perf | Core + `task-python-review-perf` subagent |
| + Sec | Core + `task-python-review-security` subagent |
| + Obs | Core + `task-python-review-observability` subagent |
| Full | Core + all three subagents in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Auto-escalation signals (Python-tuned):**

- **+Sec:** file uploads (`UploadFile`, `request.FILES`), auth dependencies (`Depends(get_current_user)`, `OAuth2PasswordBearer`), DRF `permission_classes` / `authentication_classes` changes, Pydantic / DRF schema changes, raw SQL via `text(...)` / `cursor.execute(...)`, secrets in `settings.py` / `.env`, Celery tasks consuming user-supplied input
- **+Perf:** new Alembic / Django migration, new ORM query (`select(...)` / `.filter(...)`), new `selectinload` / `prefetch_related`, new pagination, new endpoints with payloads, loops calling DB or HTTP, new `@cache` / `@lru_cache` / Redis read paths
- **+Obs:** new service module, new external client (`httpx.AsyncClient`, `requests.Session`), new Celery task or `@shared_task`, logging config change (`LOGGING` dict / `structlog`), new Prometheus metric, new `@app.on_event` / lifespan handler, new Django signal
- **2+ categories → Full**

## Invocation

| Form | Meaning |
|------|---------|
| `/task-python-review` | Current branch vs base; fails fast on trunk |
| `/task-python-review <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-python-review pr-<N>` | PR head fetched into local branch `pr-<N>` (user runs the fetch) |

Pass `--base <branch>` when the PR was opened against a non-trunk base. Scope and depth flags compose: `/task-python-review pr-50273 --base release/2026.05 +sec deep`.

**No checkout required.** The workflow reads via ref-qualified diffs; never modifies the working tree.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept parent's confirmation if invoked as a subagent.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept pre-detected stack from parent if applicable. If not Python, stop and recommend `/task-code-review`.

Detect framework: FastAPI (`fastapi` import + `main.py`) vs Django (`manage.py` + `settings.py`). Record `Framework: FastAPI | Django | mixed` for branching in later phases.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Forward `--base` if passed. If it fails fast, surface verbatim and stop.

The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

Once approved, read once and reuse:

- `git diff <base>...<head>`
- `git diff --name-status <base>...<head>`
- `git log --oneline <base>..<head>`

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

**Skip entirely** when invoked as a subagent and the parent passed the handle plus pre-read artifacts.

### Step 3.5 - Decide Mode (re-review auto-detect)

Skip if the handle has no `prior_checkpoint` -> `mode = full`, `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `mode = full`, `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

Otherwise (valid prior checkpoint present):

**Step 3.5a - Auto-fetch the head branch.** Only when a valid prior checkpoint exists, refresh the local tracking ref so a script can re-run the same command without manually fetching:

```bash
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "<head_ref>@{u}" 2>/dev/null)
```

If `upstream` resolves to `<remote>/<branch>` form, split and run:

```bash
git fetch <remote> <branch>
```

No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. After a successful fetch, re-resolve `current_head_sha = git rev-parse <head_ref>`.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `mode = full`, `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten; full re-review.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round> - full re-review.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round> - full re-review.`           |
| None of the above                                                       | `mode = incremental`, `round = prior.round + 1`, `incremental_range = <prior_head_sha>...<current_head_sha>`.                       |

**Step 3.5c - Incremental: re-read the diff scoped to the new range.**

If `mode = incremental`, replace the diff read from Step 3 with:

- `git diff <prior_head_sha>...<current_head_sha>`
- `git diff --name-status <prior_head_sha>...<current_head_sha>`
- `git log --oneline <prior_head_sha>..<current_head_sha>`

The full-range diff from Step 3 is discarded; all Phase A-E analysis operates on the incremental range only.

**Step 3.5d - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary based on mode:

- `mode = incremental`: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.`
- `mode = full`: `Scope expanded round <N>: +<list>.` (the incremental clause does not apply)

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

### Step 4 - Evaluate Scope Auto-Escalation

Scan the file list and diff for the signals listed under **Scope**. Log each fire as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` → stay Core
- One signal category → add matching extra scope
- 2+ categories → promote to Full
- User passed an explicit scope → respect it; still log signals so the Summary documents why

**Scope precedence on round 2+:** user flag > firing signals > inherit from `prior_checkpoint.scope`. If the user passed no flag and the diff (incremental, in incremental mode) fires no signals, inherit the prior round's scope so reviewer coverage does not silently narrow. Surface as `Scope: <inherited> (inherited from round <prior.round>)`.

Surface the decision in Summary; if escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk` for cross-cutting risk signals
- Use skill: `review-blast-radius` for failure propagation scope

Output risk level and blast radius before any findings.

**Low-risk short-circuit:** if Risk Level is Low, Blast Radius is Narrow, **and** the change does not touch architecture-relevant files (auth dependencies / `permission_classes`, middleware, API contracts, shared base classes, `settings.py` / `app/core/config.py`, Alembic / Django migrations), skip Phases C-D and run **B + E only** (E still covers naming/clarity, the common content of low-risk PRs). On an incremental round, Step 6.5 reconciliation still runs.

### Step 4.5 - Re-evaluate Depth After Phase A

If Blast Radius is Wide / Critical, set depth to `deep` and surface promotion in Summary **before** Phases B-E.

### Phase B - Python Correctness and Safety

Apply atomic skills. Each owns the canonical patterns; this phase flags deviations and surfaces what they did not see:

- Use skill: `python-sqlalchemy-patterns` (SQLAlchemy) or `python-django-patterns` (Django ORM) - transactions, eager loading, post-commit dispatch
- Use skill: `python-async-patterns` for any new or modified `async def` / event-loop code
- Use skill: `python-celery-patterns` if diff touches Celery tasks or `@shared_task`
- Use skill: `python-migration-safety` if diff touches `migrations/versions/` or `<app>/migrations/`. Also use skill: `ops-backward-compatibility` for client/in-flight impact

**Additional Python-specific checks the atomics don't own:**

- **Test coverage finding (named, not buried).** PR adds logic without pytest coverage -> `[Recommend]`; escalate to `[Must]` when the change is critical path: auth (OAuth2 / JWT / Django auth), authorization (`permission_classes` / FastAPI security dependencies), money / billing, multi-table writes, state machines, Celery mutators, migrations changing column semantics. Surface as a dedicated finding.
- **Type hints on public functions.** Return types and parameters typed; mypy / pyright not silently disabled mid-file.
- **`async def` discipline + `await` everywhere (FastAPI).** No blocking I/O on the event loop, no missing `await` returning a coroutine object. Catalog in `python-async-patterns`.
- **Pydantic v2 (FastAPI).** Input schemas declare `model_config = ConfigDict(extra="forbid")` for user-facing endpoints; `Field(...)` constraints on user inputs; `from_attributes=True` on response models built from ORM rows. `extra="allow"` on user input is a mass-assignment surface.
- **DRF serializer (Django).** `fields` declared explicitly (never `"__all__"` user-facing); `read_only_fields` for server-controlled fields; `write_only_fields` for sensitive inputs.
- **Authorization + IDOR.** Authn (`Depends(get_current_user)` / `permission_classes`) proves identity, not object access. Per-owner / per-tenant endpoints must scope at the repository: `where(...id == user.id)`, `tenant_id` injected by middleware.
- **Response model field hygiene.** Compare the Pydantic / DRF response model against ORM columns. Flag `password_hash` / `mfa_secret` / `internal_notes` / `audit_log` / `is_test` / `last_login_ip` on the wire. Returning a `Mapped[...]` row or `model_to_dict` directly is `[Recommend]` regardless of current fields - a new sensitive column silently leaks later.
- **HTTP `Idempotency-Key` on retry-prone POSTs.** `/payments`, `/orders`, `/refunds`, `/subscriptions`, `/webhooks` accept the header and dedupe via DB unique constraint. Distinct from worker-side task idempotency.
- **Transaction boundaries + post-commit Celery dispatch.** Writes inside explicit transaction; `task.delay(...)` after `session.commit()` (FastAPI) or via `transaction.on_commit(...)` (Django).
- **Multi-replica race safety.** Counters / balances / state transitions use DB locking (`SELECT ... FOR UPDATE`, `select_for_update()`, advisory lock) or optimistic version field, not module globals.
- **HTTP client sharing.** `httpx.AsyncClient` / `requests.Session` shared at module level. Per-request instantiation breaks connection reuse and event-loop discipline.
- **SSRF + edge middleware presence.** User-controlled values in outbound URLs flagged here; `CORSMiddleware`, `TrustedHostMiddleware`, HTTPS redirect confirmed when app construction changes. Depth in security subagent.
- **New ORM column with predicate use.** Any new `Mapped[...]` / model field referenced in `.where(...)` / `.filter(...)` / `.order_by(...)` has an index migration in the same PR, or an explicit "indexed later" note.
- **Error handling.** Framework exception handler covers validation / not-found / permission / integrity with consistent shape; no blanket `except Exception:` swallowing root causes.

### Phase C - Python Architecture Guardrails

Use skill: `architecture-guardrail` for layer violations and coupling.

**Python-specific:**

- **Layering (FastAPI):** router → service → repository → model. No business logic in routers; no `httpx` in repositories; Pydantic mapping at the service / router boundary, not in repositories
- **Layering (Django):** view / ViewSet → service → manager / queryset → model. No business logic in views beyond orchestration; service layer for cross-model orchestration
- **Service-layer discipline:** router / view methods > 10 lines of orchestration extracted to a service; intention-revealing names (`fulfill_order` not `process_order_step_2`); cross-aggregate orchestration in services, not in Django signals or SQLAlchemy event listeners
- **Dependency injection (FastAPI):** `Depends` used consistently; constructor injection for services; no module-level singletons holding mutable state created on import
- **Settings discipline:** typed settings via `pydantic-settings` `BaseSettings` (FastAPI) or `django-environ` (Django); no hardcoded values that should be env vars
- **Feature-package layout** (`app/orders/{router,service,repository,schema}.py`) preferred over layer-package; cross-feature imports go through public service interfaces, not direct repository imports
- **Multi-tenant isolation** enforced at the repository / queryset layer (`with_loader_criteria` / `Manager` override), not at routers / views alone
- **Signal / event discipline:** Django `post_save` / `pre_delete` and SQLAlchemy event listeners reserved for genuinely cross-cutting concerns (audit, search-index) - not as hidden control flow dispatching emails / Celery tasks
- **Anemic domain (deep depth only):** business rules accumulating in services while ORM models stay pure data - flag for `task-python-refactor`. Do not raise on a single PR's evidence alone

**Multi-service PRs:**

- API contract compatibility (OpenAPI diff, `schemathesis`, Pact)
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility`

### Phase D - AI-Generated Code Quality

- Use skill: `complexity-review` for verbosity, over-engineering, simplification
- Load **one** framework-specific necessity skill from Step 2's detection:
  - **FastAPI:** Use skill: `python-fastapi-overengineering-review`
  - **Django:** Use skill: `python-django-overengineering-review`

**Additional Python AI smells the atomics don't own:**

- Test verbosity (`@pytest.fixture` setup > 30 lines for one assertion; full deep-equal when a few field assertions would do)
- Async misapplication (`async def` on functions doing no I/O; sync helpers blocking inside `async def` paths)
- Comment cruft (docstrings on private helpers restating the signature; auto-generated TODOs left in)
- `# type: ignore[...]` proliferation in non-test code to silence a real type bug

### Phase E - Maintainability and Clarity

Use skill: `backend-coding-standards` for cross-language naming. Use skill: `ops-observability` for cross-cutting logging/metrics presence (depth belongs to `task-python-review-observability`).

**Python-specific:**

- **Naming:** services describe their operation (`order_fulfillment.py` over `order_helper.py`); schemas named after role (`OrderCreateRequest`, `OrderResponse`); no `Util` / `Manager` / `Helper` modules; `_private` prefix for module-private helpers
- **Magic numbers / strings:** extracted to module-level constants or `BaseSettings`; `timedelta(minutes=...)` over `60_000`
- **Hardcoded URLs / credentials:** env / Vault / settings, not inline
- **Function length:** > 30 lines extracted; > 60 lines flagged unless clearly orchestrating
- **Duplicated query logic:** same `.filter(...)` / `select(...)` predicate in 3+ places extracted to a manager or repository method
- **Logging hygiene:** surface `print(...)` in prod paths, f-string log calls (`logger.info(f"...")` over parameterized `logger.info("processing order=%s", order_id)`), wrong levels as `[Recommend]` (depth in observability subagent)

### Step 5 - Delegate Extra Scopes in Parallel

If scope is **Core only**, skip.

For each extra scope, spawn an independent subagent **in parallel** with the main thread:

| Scope | Subagents |
|-------|-----------|
| + Perf | `task-python-review-perf` |
| + Sec | `task-python-review-security` |
| + Obs | `task-python-review-observability` |
| Full | All three in parallel |

**Subagent prompt contract** - each must include:

- The resolved review target (`base_ref`, `head_ref`) plus the pre-read diff and commit log (no re-running git)
- The depth level
- Pre-confirmed stack (Python) + framework (FastAPI / Django / mixed)
- Instruction to return findings in its own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 6 - Synthesize (only if Step 5 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate** cross-cutting findings (one entry citing all scopes that raised it)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend` > `Question`
- **Preserve `file:line` citations**
- **Order by intent**, not by scope
- **Note missing scopes** in Summary as `Scope incomplete: <scope>`
- **Merge Next Steps** with `[Implement]` / `[Delegate]` tags preserved; re-sort by intent

### Step 6.5 - Reconcile Prior Findings (incremental mode only)

Skip if `mode = full`. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `incremental_diff`: from Step 3.5c
- `name_status`: from Step 3.5c

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

### Step 7 - Write Report

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode` (from Step 3.5), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = python-<framework>` (e.g., `python-fastapi`, `python-django`)

Write before ending; print the confirmation line.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |
| [Question]   | Author must answer; reviewer decides if a fix follows.                   |

No `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide | Critical
**Stack Detected:** Python <version>
**Framework:** FastAPI <version> | Django <version> | mixed
**Scope:** Core | +Sec | +Perf | +Obs | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_
**Round:** <N>                                _(include from round 2 onward)_
**Mode:** incremental (since <prior_head_sha_short>) | full _(include from round 2 onward)_
**Diff Range:** <range_short> (<N> commits, <M> files) _(incremental rounds only)_

## Prior Round Reconciliation _(incremental rounds only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line

- Issue: [name the Python idiom: blocking `requests.get` in `async def`, missing `permission_classes`, ORM model returned from endpoint, Celery `.delay()` inside transaction, `extra="allow"` on input schema, etc.]
- Impact: [user-visible or operational]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Python change with code]

### [Recommend] file:line
- Issue: ...
- Impact: ...
- Fix: ...

### [Question] file:line
- Question: [what is ambiguous]
- Why it matters: [what the right next step depends on]

_Use [Question] for genuine ambiguity, not as a softer Must._

## Architecture Notes

_Cross-cutting commentary. Do not restate individual findings; reference them by file:line._

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

2-4 bullets on systemic impact and what to address before merge.

## Next Steps

Each item tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend > Question. On incremental rounds, prior-round `Still open` items are folded in with `(open since round <N>)` suffix and ordered by intent alongside new findings.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Implement]** [Recommend] old_file.py:88 - missing await on async DB call (open since round 1)
3. **[Delegate]** [Recommend] [scope: cross-service] - [one-line action]

_Omit if no actionable findings._
```

**Omit empty sections.** No Must heading if there are none.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply Python conventions, not generic backend conventions
- Provide actionable feedback with Python code examples
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security / observability depth to subagents

## Self-Check

- [ ] `behavioral-principles` loaded (or accepted from parent)
- [ ] Stack confirmed as Python; framework recorded (FastAPI / Django / mixed)
- [ ] `review-precondition-check` ran (or handle received); diff/log read once and reused; `current_head_sha` and `current_base_sha` captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Scope auto-escalation evaluated; promotion (or `core-only`) recorded; scope expansion vs. prior round noted when applicable
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical
- [ ] Risk level + blast radius stated before any finding
- [ ] Phase B: applied atomic skills; checked test coverage, async discipline, Pydantic/DRF rules, authorization, response model hygiene, Idempotency-Key, race safety
- [ ] Phase B migration safety delegated to `python-migration-safety` when migrations changed
- [ ] Phase C: layering, DI, settings discipline, signal/listener discipline, package boundaries, multi-tenant
- [ ] Phase D: `complexity-review` + the framework-matching necessity skill applied; Python AI smells covered
- [ ] Phase E: naming, magic numbers, function length, logging hygiene
- [ ] Missing tests raised as a named finding (not buried)
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + actionable Python fix
- [ ] If `--spec` passed: every finding traces to AC/NFR/task or is flagged as out-of-scope blocker
- [ ] Extra scopes ran in parallel with the pre-resolved diff/log handle + framework detection
- [ ] Subagent findings merged into one intent-ordered Findings list; no raw reports appended
- [ ] Failed/missing subagent scope noted as `Scope incomplete: <scope>`
- [ ] Step 6.5 - on incremental rounds, `review-prior-findings-reconcile` ran; reconciliation table inserted; `Still open` rows folded into Next Steps with `(open since round <N>)` suffix
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by intent; carry-overs from prior round inline-suffixed, not in a separate section
- [ ] Review report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack); confirmation line printed

## Avoid

- State-changing git from this workflow (`checkout`/`merge`/`pull`/`rebase`). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Generic backend conventions when a Python idiom exists ("extract to a service module", not "extract to a helper class")
- Vague feedback ("this could be better"); blocking on personal preference
- Duplicating perf / security / observability depth here when the dedicated subagent owns them
- Sequential extra scopes that could parallelize
- Appending raw subagent reports instead of merging
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Recommending `pickle.loads` / `yaml.load` on untrusted input, or `extra="allow"` on user-facing Pydantic schemas, as acceptable patterns
