---
name: task-python-review-api
description: Python API-contract review - REST design, breaking-change/versioning, Pydantic response models over ORM rows, RFC 9457 errors, OpenAPI drift.
agent: python-api-engineer
metadata:
  category: backend
  tags: [python, fastapi, django, api, rest, contract, compatibility, versioning, openapi, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Python API Review

Python-aware API-contract review naming FastAPI routes and Pydantic schemas, the SQLAlchemy-row-to-Pydantic-response boundary, breaking-change detection from the consumer's view, `/v1/` versioning and `Sunset` deprecation, RFC 9457 error envelopes, pagination shape, and OpenAPI drift (with Django / DRF notes). API review = the contract the service exposes: its REST shape, its evolution across versions, and its honesty about what it returns. Every finding names who breaks and how, with concrete fixes for Python 3.11+ / FastAPI (or Django / DRF).

Stack-specific delegate of `task-code-review-api` for Python.

## When to Use

- FastAPI or Django PR adding or changing a route, request schema, or response model
- Pre-merge breaking-change check on a versioned or externally consumed endpoint
- Response-shape / error-envelope / status-code / pagination / resource-naming consistency pass
- OpenAPI drift check against the routes and schemas

**Not for:** general review (`task-python-review`), auth enforcement or validation bypass (`task-python-review-security`), idempotency-dedup correctness or behavior under a slow dependency (`task-python-review-reliability`), throughput (`task-python-review-perf`), an active incident (`/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Security:** this lens owns the contract *declaring* an auth scheme, a `Field(...)` constraint, or a rate-limit header; security owns that scheme being *enforced* and unbypassable. A missing `401` in the documented responses is API; an endpoint accepting an unauthenticated request that should be rejected, or `extra="allow"` / `"__all__"` enabling mass assignment, is security. Note the contract gap here; route the enforcement gap to `task-python-review-security`.
- **vs. Reliability:** this lens owns the `Idempotency-Key` header being *part of the contract*; reliability owns the dedup being *atomic under retry*. The header absent from a payment endpoint is API; the read-then-write dedup race is reliability.
- **vs. core Phase B:** `task-python-review` Phase B owns the handler returning the right data; this lens owns that data's shape being conventional, versioned, and stable. Raw-ORM-row-vs-Pydantic-response leakage sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                              | Runs                                          |
| ---------- | ------------------------------------------------- | --------------------------------------------- |
| `standard` | Default                                           | All steps except the Consumer-Impact Map      |
| `deep`     | Requested, or handed down by `task-python-review` | All + `Consumer-Impact Map`                   |

At `deep`, trace each changed contract with `ops-backward-compatibility`: what changed, whether it is breaking from the consumer's view, which consumers are affected, and the expand-contract step that keeps them working - captured in the Consumer-Impact Map.

**Whole-service sweep** (API-consistency pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-9 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-python-review-api` | Current branch vs base; fails fast on trunk |
| `/task-python-review-api <branch>` | `<branch>` vs base (3-dot) |
| `/task-python-review-api pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass (e.g. `/task-python-review-api <branch> deep`); `standard` is accepted explicitly. A `--base <branch>` argument (forwarded by `task-code-review-api`) passes to `review-precondition-check` as the explicit base override. When invoked as subagent (e.g. by `task-python-review`), the parent passes the pre-confirmed stack and precondition handle + pre-read diff; Steps 2-3 consume those instead of re-running, and Step 9 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent (`task-python-review`) and skip detection. If not Python, stop and route the user to `/task-code-review-api`.

Detect the framework: FastAPI (`fastapi` import + `main.py`) vs Django (`manage.py` + `settings.py`) - record `Framework: FastAPI | Django | mixed`. Detect whether OpenAPI is published: **FastAPI always exposes it** (auto-generated at `/openapi.json` from the routes + Pydantic models), so drift is against `response_model` / `status_code` / hand-written dicts; **Django** publishes a schema only when **drf-spectacular** (or drf-yasg) is installed - record its presence. This gates Step 8. Serializer / response-model and spec detection is always this skill's own job even as a subagent - a pre-confirmed stack from a parent covers language / framework only, not the response-model surface or published-spec presence.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim.

Capture for the report checkpoint (standalone only - a subagent run writes no report, so skip the capture): `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 4 - Read the API Surface

**Contract-change quick-scan gate.** Before loading any guideline atomic, scan the diff for a contract-change signal: a changed route registration (`APIRouter` / `urls.py` / DRF router), a changed request schema / `Field(...)` constraint / serializer input field, a changed / added / removed `response_model` or serializer, a changed response shape or `status_code`, an error-envelope change, a pagination change, or an OpenAPI / drf-spectacular schema edit. If NONE is present, emit `No contract change detected - API review skipped` and STOP before loading the guideline atomics - write no report (see the no-write rule below). The whole-service sweep skips this gate (it reviews current code, not a diff).

**No-write-on-skip.** A skip writes NO report file: a prior `review-api-<branch>.md` (with its findings + round state) must stay byte-identical, mirroring the umbrella's no-op rule. Standalone prints the skip line; a subagent returns it to the parent. Nothing is written - do not introduce an `Overall: No contract change` report enum.

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a changed response model ripples to every route returning it). Checklists apply to the whole surface read: a pre-existing gap on a changed or rippled contract is a finding (note it as pre-existing), not out of scope.

- Route registration: FastAPI `APIRouter` / `@router.get` / `@router.post` / `@router.put` / `@router.patch` / `@router.delete` wiring (or Django `urls.py` / DRF router registration) - paths, methods, version prefixes
- Request schemas and their `Field(...)` constraints / `model_config` - required fields, validators, field names on the wire (Django: serializer input fields, `required=`)
- Response models declared via `response_model=` and returned from routes - and whether any route returns a SQLAlchemy row directly (or a DRF `ModelSerializer` with `"__all__"`)
- Error handling on the response path - FastAPI exception handlers / `HTTPException` shapes, DRF exception handling, status-code mapping
- Pagination: collection routes and their query params / response envelope (FastAPI `limit`/`offset` or cursor; Django DRF pagination class)
- OpenAPI surface: `response_model` / `status_code` / `responses={}` declarations (FastAPI), or the drf-spectacular schema (if Step 2 found one)

Use skill: `backend-api-guidelines` for the canonical REST / method / status / error / pagination / versioning rules. Use skill: `ops-backward-compatibility` to judge each changed contract from the consumer's view and to produce the expand-contract plan for any breaking change.

### Step 5 - Contract Compatibility

Use skill: `ops-backward-compatibility` for the consumer-view judgment.

- [ ] **Response changes judged from the consumer** - a removed, renamed, or retyped response-model field; a `status_code` change; a new enum value in a response field; or a changed error shape is **breaking** until a search proves no consumer. Added optional fields are safe.
- [ ] **Request changes judged from the consumer** - a new **required** request field, a tightened validator (`Field(min_length=...)`, `pattern`, `gt`, a new `field_validator`, or `extra="forbid"` added where callers sent extra keys; Django: `required=True`, a tightened serializer validator), or a removed accepted field breaks existing callers. New optional fields are safe.
- [ ] **Breaking change carries a version or expand-contract plan** - a `/v2/` route (or version header) plus a `Sunset` header on the deprecated one, or a dual-read / dual-write transition. A breaking change on `/v1/` in place is a High finding.
- [ ] **"No callers" is proven, not assumed** - `grep` for the field / route across the repo and known consumers; absence of a search is not evidence of no consumer.

### Step 6 - REST / HTTP Design

Use skill: `backend-api-guidelines` for the design rules. Use skill: `python-fastapi-patterns` for FastAPI routing and response conventions (Django: `python-django-patterns` for ViewSet / router conventions).

- [ ] **Resource naming** - plural-noun paths, lowercase, hyphen-separated, no verbs (`POST /balance-recalculations`, not `POST /recalculateBalance`); IDs in path segments, filters / sort / pagination in query. Deliberate RPC-style and webhook endpoints are exempt from naming but not from the rules below.
- [ ] **Method semantics** - GET pure-read (no side effect), POST creates, PUT replaces, PATCH partial-updates, DELETE removes; no state change behind a GET.
- [ ] **Status codes consistent** - 201 + `Location` on create, 204 on empty-body success, 400 vs 422 used deliberately (FastAPI validation defaults to 422), 409 on conflict, 429 on rate limit; no 200-with-error-body.
- [ ] **Sub-resource nesting** - one level (`/orders/{id}/refunds`); an independently addressed child gets a top-level collection (`/refunds?order_id=`) instead of deeper nesting.

### Step 7 - Response Shape, Errors, and Pagination

Use skill: `python-fastapi-patterns` for router / dependency conventions (Django: `python-django-patterns`), and `python-sqlalchemy-patterns` for query-layer pagination mechanics. Their internal-facing examples show a `{code, errors}` validation envelope and limit/offset pagination; where any of them differs from this workflow's contract rules (RFC 9457 fields, cursor-first), **this workflow's rules win** - it reviews the published contract; they build internals.

- [ ] **Pydantic response model, never a raw ORM row** - FastAPI routes declare `response_model=` and return a dedicated Pydantic model (mapped from the row via `ConfigDict(from_attributes=True)`), not a SQLAlchemy `Mapped[...]` row. Returning the row over-exposes internal fields (`hashed_password`, internal FKs, soft-delete timestamps) and couples the wire contract to the ORM schema, so a column rename silently breaks clients. Django: serializer `fields` declared explicitly, never `ModelSerializer` with `"__all__"` user-facing.
- [ ] **RFC 9457 error envelope** - errors return `type` / `title` / `status` / `detail` / `instance`, consistently across routes via a FastAPI exception handler (or DRF custom exception handler). No Python traceback, no SQLAlchemy / `IntegrityError` string, no internal ID leaked to the client.
- [ ] **Every collection paginated** - a list endpoint returns a bounded page with a consistent envelope (`items` + `next_cursor` / total), never an unbounded `.all()` / `session.scalars(select(Model))` returned whole. Cursor for large / write-heavy collections, `limit`/`offset` only for small / stable ones. Django: a DRF pagination class (`CursorPagination` / `LimitOffsetPagination`), not a bare `.all()`.
- [ ] **Field naming and nullability consistent** - response fields follow one convention (snake_case, not mixed with camelCase unless aliased); a field that can be absent is `Optional[...] = None` or documented nullable, not a silent default.

### Step 8 - Versioning and OpenAPI Drift

Use skill: `backend-api-guidelines` for versioning and the idempotency-key contract.

- [ ] **Version on breaking change** - a new major version is a new prefix / header, not a mutated `/v1/`; the deprecated version carries a `Sunset` header and a migration note.
- [ ] **Idempotency-Key in the contract** - a non-idempotent `POST` on money / notification / provisioning declares an `Idempotency-Key` header in its documented request (the dedup *correctness* routes to `task-python-review-reliability`).
- [ ] **OpenAPI matches code** - FastAPI auto-generates the schema, so drift is subtler: a route returning a hand-written `dict` that does not match its `response_model` (a missing declared field 500s at runtime - High), a `status_code=` inconsistent with the documented response, or `response_model_exclude` / `response_model_by_alias` dropping a documented field. A bare `payload: dict` request body publishes an undocumented request contract - flag it (Medium). _(Django, only if Step 2 found drf-spectacular)_: changed routes, serializer fields, status codes, and error shapes are reflected in the generated schema; a serializer field absent from the schema (or vice versa) is drift, and generated clients will be wrong.

```python
# Bad - returns the SQLAlchemy row with no response_model: leaks hashed_password + couples the wire to the ORM schema
@router.get("/users/{user_id}")
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)) -> User:
    return await session.get(User, user_id)

# Good - explicit Pydantic response model; only the fields the contract promises
class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    name: str

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, session: AsyncSession = Depends(get_session)) -> UserResponse:
    user = await session.get(User, user_id)
    return UserResponse.model_validate(user)
```

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 9 - Write Report

Standalone only - subagent runs return findings in the Output Format to the parent, which writes the single merged report. At `deep`, a subagent returns the Consumer-Impact Map with its findings so the parent can preserve it as its own section.

Use skill: `review-report-writer` with `report_type: review-api` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: both = `HEAD`), `stack: python-fastapi` (or `python-django` / `python-mixed` as detected), `scope: +api`, `depth` as resolved from the Depth table, and `mode: full`, `round: 1` - unless `review-api-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. Round 2+ is still a full re-review (`mode: full`; `prior_head_sha` chains history, it does not scope the diff); open the report body with a one-line round note - findings resolved since the prior round vs still open. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no collection endpoint, no published Django schema).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Python 3.11+; framework recorded (FastAPI / Django / mixed); OpenAPI-spec presence recorded (FastAPI always-on; Django needs drf-spectacular) - response-model + spec detection done here even as a subagent
- [ ] Step 3: precondition check ran (or handle received); diff + log read once; `current_head_sha` / `current_base_sha` captured (standalone only)
- [ ] Step 4: contract-change quick-scan gate ran (skip + no write when no contract signal); on a real change, routes, request schemas, response models, error paths, pagination, and the OpenAPI surface read; `backend-api-guidelines` + `ops-backward-compatibility` consulted
- [ ] Step 5: every changed request / response contract judged from the consumer's view; breaking changes flagged with a version / expand-contract requirement; "no callers" proven by search
- [ ] Step 6: resource naming, method semantics, status codes, sub-resource nesting checked
- [ ] Step 7: Pydantic response model (no raw ORM row / no `"__all__"`), RFC 9457 errors, pagination, field-naming consistency checked
- [ ] Step 8: versioning on breaking change; `Idempotency-Key` in the contract for non-idempotent POST; OpenAPI drift checked (`response_model` / `status_code` / hand-written dicts for FastAPI; drf-spectacular schema for Django if present)
- [ ] Step 9: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names who breaks and how, never just the deviated convention
- [ ] Depth honored: `standard` ran all; `deep` filled the Consumer-Impact Map
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unversioned breaking change to an externally consumed contract, or a leaked internal shape (raw SQLAlchemy row exposed / `ModelSerializer` `"__all__"`, traceback / ORM error in the response); Medium = a breaking change to an internal contract with no coordinated-deploy note, an inconsistent status code / error envelope, an unpaginated unbounded collection, a method-semantics violation (state change behind GET - High when the side effect is destructive or money-moving), a non-idempotent POST with no `Idempotency-Key` in the contract, or OpenAPI drift on a published spec; Low = naming / convention / field-casing drift with no consumer impact, or OpenAPI drift on an internal-only spec. When consumption is unknown, treat a published or versioned surface (`/v1/` route, published spec) as externally consumed. Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on an external contract; Low -> `[Recommend]`.

**One finding per root cause:** when a defect satisfies multiple checklist items (a raw row exposed that is also unversioned), report it once at the strongest severity and fold the other aspects into that finding - do not emit one finding per checklist line.

```markdown
## Python API Review Summary

**Stack Detected:** Python <version> / FastAPI <version> (or Django <version> / DRF)
**OpenAPI Spec:** FastAPI auto-generated | drf-spectacular | none detected
**Overall:** Conventional & Compatible | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line or route]
   **Issue:** [name the gap: raw SQLAlchemy row with no `response_model`, removed response field on `/v1/`, error leaks `IntegrityError`, unpaginated `.all()`, `ModelSerializer` `"__all__"`, verb in path, etc.]
   **Who Breaks:** [which consumer and how: "mobile v3 unmarshals `total`; removing it from the response silently zeroes the displayed price"]
   **Blast Radius:** [scope: which contract version, which callers, coordinated-deploy need]
   **Fix:** [specific: `response_model=UserResponse`, `/v2/` + `Sunset`, RFC 9457 handler, cursor pagination, `Idempotency-Key` header, etc.]

### Medium Impact
[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins
[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural contract improvements not tied to a single finding]

## Consumer-Impact Map

_(`deep` only - omit at `standard`.)_
Per changed contract: **what changed**, whether it is **breaking** from the consumer's view, **which consumers** are affected, and the **expand-contract step** that keeps them working during rollout.

## Next Steps

1. **[Implement]** [Must] file:line - [action]
2. **[Delegate]** [Recommend] [scope: security] - [action]
3. **[Implement]** [Recommend] file:line - [action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting - enforcement to security, dedup correctness to reliability, gateway rate limits to platform). Order Must > Recommend. Omit if none._
```

## Avoid

- Reporting a deviated convention without naming who breaks ("use a response model" vs "returning the `User` row exposes `hashed_password` and breaks every client when a column is renamed")
- Returning a raw SQLAlchemy row with no `response_model`, or a DRF `ModelSerializer` with `"__all__"` (over-exposure + ORM-schema-to-wire coupling)
- Leaking a Python traceback, a SQLAlchemy / `IntegrityError` string, or an internal ID in an error response
- Writing any report file on a no-contract-change skip - a prior `review-api-<branch>.md` must stay byte-identical
- Calling a change "additive" without a consumer-view check, or "no callers" without a search
- Mutating `/v1/` in place for a breaking change instead of versioning
- An unbounded `.all()` returned as a collection with no pagination
- Reviewing auth enforcement or validation bypass (`extra="allow"` / `"__all__"`) here - name the contract gap and route to `task-python-review-security`
- Reviewing idempotency-dedup correctness or timeout behavior here - route to `task-python-review-reliability`
- Overlapping into perf (throughput) - own the response *shape*, not its cost
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
