---
name: task-rails-review-api
description: Rails API-contract review - REST design, breaking-change/versioning, serializers over AR models, RFC 9457 errors, pagination, OpenAPI drift.
agent: rails-api-engineer
metadata:
  category: backend
  tags: [ruby, rails, api, rest, contract, compatibility, versioning, openapi, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Rails API Review

Rails-aware API-contract review naming `config/routes.rb` routes and controller actions, AR-model-to-serializer boundaries, breaking-change detection from the consumer's view, `/v1/` versioning and `Sunset` deprecation, RFC 9457 error envelopes, pagination shape, and rswag / OpenAPI drift. API review = the contract the service exposes: its REST shape, its evolution across versions, and its honesty about what it returns. Every finding names who breaks and how, with concrete fixes for Rails 7.2+.

Stack-specific delegate of `task-code-review-api` for Rails.

## When to Use

- Rails PR adding or changing a route, controller action, strong-params, or serializer
- Pre-merge breaking-change check on a versioned or externally consumed endpoint
- Response-shape / error-envelope / status-code / pagination / resource-naming consistency pass
- OpenAPI / rswag drift check against the serializers

**Not for:** general review (`task-rails-review`), auth enforcement, strong-params bypass, or mass assignment (`task-rails-review-security`), idempotency-dedup correctness or behavior under a slow dependency (`task-rails-review-reliability`), throughput (`task-rails-review-perf`), an active incident (`/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Security:** this lens owns the contract *declaring* an auth scheme, a permitted-params shape, or a rate-limit header; security owns that scheme being *enforced* and the `permit` being unbypassable / not mass-assignable. A missing `401` in the documented responses is API; an endpoint accepting an unauthenticated request that should be rejected is security. Note the contract gap here; route the enforcement gap to `task-rails-review-security`.
- **vs. Reliability:** this lens owns the `Idempotency-Key` header being *part of the contract*; reliability owns the dedup being *atomic under retry*. The header absent from a payment endpoint is API; the read-then-write dedup race is reliability.
- **vs. core Step 5:** `task-rails-review` Step 5 owns the action returning the right data; this lens owns that data's shape being conventional, versioned, and stable. Raw-AR-model-vs-serializer leakage sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                            | Runs                                          |
| ---------- | ----------------------------------------------- | --------------------------------------------- |
| `standard` | Default                                         | All steps except the Consumer-Impact Map      |
| `deep`     | Requested, or handed down by `task-rails-review`| All + `Consumer-Impact Map`                   |

At `deep`, trace each changed contract with `ops-backward-compatibility`: what changed, whether it is breaking from the consumer's view, which consumers are affected, and the expand-contract step that keeps them working - captured in the Consumer-Impact Map.

**Whole-service sweep** (API-consistency pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-9 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file; Step 5's changed-contract checks are N/A); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-rails-review-api` | Current branch vs base; fails fast on trunk |
| `/task-rails-review-api <branch>` | `<branch>` vs base (3-dot) |
| `/task-rails-review-api pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass (e.g. `/task-rails-review-api <branch> deep`); `standard` is accepted explicitly. A `--base <branch>` argument (forwarded by `task-code-review-api`) passes to `review-precondition-check` as the explicit base override. When invoked as subagent (e.g. by `task-rails-review`), the parent passes the pre-confirmed stack and precondition handle + pre-read diff; Steps 2-3 consume those instead of re-running, and Step 9 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent (`task-rails-review`) and skip detection. If not Rails, stop and route the user to `/task-code-review-api`.

Detect the serializer approach in use (ActiveModel::Serializer / Jbuilder / Alba / Blueprinter / none - raw `render json:`) and whether an OpenAPI spec is published (rswag request specs, a committed `openapi.yaml` / `swagger.yaml`, or a codegen step) - these gate Steps 7 and 8. This detection is always this skill's own job: a pre-confirmed stack covers language / framework only, so run it (read the repo) even as a subagent.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>` (standalone only - subagent runs write no report, so skip the capture).

### Step 4 - Contract-Change Gate, then Read the API Surface

**Quick scan first (before loading any guideline atomic).** Scan the diff for a contract-change signal: a changed `config/routes.rb` entry, a changed `params.require(...).permit(...)` shape, a changed / added / removed serializer or presenter, a changed `render json:` shape or status code, a `rescue_from` / error-envelope change, a pagination change, or an rswag / `openapi.yaml` / `swagger.yaml` edit. If **none** is present, the PR carries no contract change: emit `No contract change detected - API review skipped` and stop **before** loading `backend-api-guidelines` / `ops-backward-compatibility` / `rails-activerecord-patterns`. A skip writes **no report file** - a prior `review-api-<branch>.md` (with its findings and round state) stays byte-identical, mirroring the umbrella's no-op rule. Standalone runs print the skip line; subagent runs return it to the parent. Whole-service sweeps skip this gate (they review current code, not a diff).

If a signal is present, read every changed file in these categories plus any unchanged file the diff calls into (a changed serializer ripples to every action rendering it). Checklists apply to the whole surface read: a pre-existing gap on a changed or rippled contract is a finding (note it as pre-existing), not out of scope.

- Route registration: `config/routes.rb` `resources` / `namespace` / `member` / `collection` / explicit verb wiring - paths, methods, version namespaces
- Strong params and their `params.require(...).permit(...)` shape - required fields, permitted attributes, field names on the wire
- Serializers / presenters rendered via `render json:` - and whether any action renders a raw AR model directly
- Error handling on the response path - `rescue_from` in `ApplicationController`, `render json:` error shapes, status-code mapping
- Pagination: collection actions and their query params / response envelope
- rswag request specs / committed OpenAPI spec (if Step 2 found one)

Use skill: `backend-api-guidelines` for the canonical REST / method / status / error / pagination / versioning rules. Use skill: `ops-backward-compatibility` to judge each changed contract from the consumer's view and to produce the expand-contract plan for any breaking change.

### Step 5 - Contract Compatibility

Use skill: `ops-backward-compatibility` for the consumer-view judgment.

- [ ] **Response changes judged from the consumer** - a removed, renamed, or retyped serializer attribute; a status-code change; a new enum value in a response field; or a changed error shape is **breaking** until a search proves no consumer. Added optional attributes are safe. Enum widening resolves by verify-then-emit: when the search proves every consumer tolerates unknown values and the spec is updated, it is compatible; emitting before that proof is a High finding.
- [ ] **Request changes judged from the consumer** - a new **required** `permit`-ted request field, a tightened validation (`presence`, `inclusion`, `length`), or a removed accepted field breaks existing callers. New optional fields are safe.
- [ ] **Breaking change carries a version or expand-contract plan** - a `/v2/` namespace (or version header) plus a `Sunset` header on the deprecated one, or a dual-read / dual-write transition. A breaking change on `/v1/` in place is a High finding.
- [ ] **"No callers" is proven, not assumed** - `grep` for the attribute / route across the repo and known consumers; absence of a search is not evidence of no consumer.

### Step 6 - REST / HTTP Design

Use skill: `backend-api-guidelines` for the design rules.

- [ ] **Resource naming** - plural-noun paths via `resources`, lowercase, hyphen-separated, no verbs (`POST /balance-recalculations`, not `POST /recalculate_balance`); IDs in path segments, filters / sort / pagination in query. Deliberate RPC-style and webhook endpoints are exempt from naming but not from the rules below.
- [ ] **Method semantics** - GET pure-read (no side effect), POST creates, PUT replaces, PATCH partial-updates, DELETE removes; no state change behind a GET.
- [ ] **Status codes consistent** - 201 + `Location` on create, 204 on empty-body success, 400 vs 422 used deliberately, 409 on conflict, 429 on rate limit; no 200-with-error-body.
- [ ] **Sub-resource nesting** - one level (`/orders/:id/refunds` via nested `resources`); an independently addressed child gets a top-level collection (`/refunds?order_id=`) instead of deeper nesting.

### Step 7 - Response Shape, Errors, and Pagination

Preload associations at the controller boundary (`includes` / `preload`) before the serializer renders them - a serializer walking associations per row is an N+1 behind the contract (throughput depth -> `task-rails-review-perf`). The serializer-boundary rules are this workflow's own, below. (The one preload rule this lens needs is inlined on purpose - do not re-delegate to `rails-activerecord-patterns`; its full query mechanics are perf's concern, not the API contract's.)

- [ ] **Explicit serializer, never a raw AR model** - actions render a dedicated serializer / presenter, not `render json: @model`. Rendering the model calls `as_json` over every column and over-exposes internal attributes (`password_digest`, internal FKs, `deleted_at`) and couples the wire contract to the DB schema, so a column rename silently breaks clients.
- [ ] **RFC 9457 error envelope** - errors return `type` / `title` / `status` / `detail` / `instance`, consistently across actions via `rescue_from` in `ApplicationController`. No Ruby backtrace, no leaked `ActiveRecord::RecordNotFound` internal, no internal ID leaked to the client.
- [ ] **Every collection paginated** - a list endpoint returns a bounded page (Kaminari / Pagy) with a consistent envelope (`items` + `next_cursor` / total / meta), never an unbounded `render json: Model.all`. Cursor for large / write-heavy collections, offset only for small / stable ones.
- [ ] **Field naming and nullability consistent** - serializer keys follow one convention (snake_case or camelCase, not mixed); an attribute that can be absent is documented nullable, not a silent `nil` on a renamed column.

### Step 8 - Versioning and OpenAPI Drift

Use skill: `backend-api-guidelines` for versioning and the idempotency-key contract.

- [ ] **Version on breaking change** - a new major version is a new `/v2/` namespace / header, not a mutated `/v1/`; the deprecated version carries a `Sunset` header and a migration note.
- [ ] **Idempotency-Key in the contract** - a non-idempotent `POST` on money / notification / provisioning declares an `Idempotency-Key` header in its documented request (the dedup *correctness* routes to `task-rails-review-reliability`).
- [ ] **OpenAPI matches code** _(only if Step 2 found a published spec)_ - changed routes, serializer attributes, status codes, and error shapes are reflected in the rswag specs / `openapi.yaml`. An attribute in the serializer but absent from the spec (or a documented attribute the action no longer returns) is drift, and generated clients will be wrong.

```ruby
# Bad - renders the AR model: as_json leaks password_digest + couples the wire to the DB schema
def show
  @user = User.find(params[:id])
  render json: @user
end

# Good - explicit serializer; only the attributes the contract promises
def show
  @user = User.find(params[:id])
  render json: UserSerializer.new(@user)
end
```

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 9 - Write Report

Standalone only - subagent runs return findings in the Output Format to the parent, which writes the single merged report. At `deep`, a subagent returns the Consumer-Impact Map with its findings so the parent can preserve it as its own section.

Use skill: `review-report-writer` with `report_type: review-api` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: both = `HEAD`), `stack: ruby-rails`, `scope: +api`, `depth` as resolved from the Depth table, and `mode: full`, `round: 1` - unless `review-api-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no collection endpoint, no published OpenAPI spec).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Ruby 3.4+ / Rails 7.2+ (or pre-confirmed stack accepted from parent); serializer approach and OpenAPI-spec presence recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once; `current_head_sha` and `current_base_sha` captured (standalone only)
- [ ] Step 4: contract-change gate applied first - on skip, the line emitted and **no report file written** (prior report untouched); otherwise routes, strong params, serializers, error paths, pagination, and any OpenAPI spec read; `backend-api-guidelines` + `ops-backward-compatibility` consulted
- [ ] Step 5: every changed request / response contract judged from the consumer's view; breaking changes flagged with a version / expand-contract requirement; "no callers" proven by search
- [ ] Step 6: resource naming, method semantics, status codes, sub-resource nesting checked
- [ ] Step 7: explicit serializer (no raw AR model), RFC 9457 errors, pagination, field-naming consistency checked
- [ ] Step 8: versioning on breaking change; `Idempotency-Key` in the contract for non-idempotent POST; OpenAPI drift checked (if a spec exists)
- [ ] Step 9: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names who breaks and how, never just the deviated convention
- [ ] Depth honored: `standard` ran all; `deep` filled the Consumer-Impact Map
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unversioned breaking change to an externally consumed contract, or a leaked internal shape (raw AR model rendered, backtrace / `ActiveRecord::RecordNotFound` in the response); Medium = a breaking change to an internal contract with no coordinated-deploy note, an inconsistent status code / error envelope, an unpaginated unbounded collection, a method-semantics violation (state change behind GET - High when the side effect is destructive or money-moving), a non-idempotent POST with no `Idempotency-Key` in the contract, or OpenAPI drift on a published spec; Low = naming / convention / field-casing drift with no consumer impact, or OpenAPI drift on an internal-only spec. When consumption is unknown, treat a published or versioned surface (`/v1/` route, published spec) as externally consumed. Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on an external contract; Low -> `[Recommend]`.

**One finding per root cause:** when a defect satisfies multiple checklist items (a raw model rendered that is also unversioned), report it once at the strongest severity and fold the other aspects into that finding - do not emit one finding per checklist line.

```markdown
## Rails API Review Summary

**Stack Detected:** Ruby <version> / Rails <version>
**Serializer:** ActiveModel::Serializer | Jbuilder | Alba | Blueprinter | none (raw render json:)
**OpenAPI Spec:** rswag | committed openapi.yaml | none detected
**Overall:** Conventional & Compatible | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line or route]
   **Issue:** [name the gap: raw AR model in `render json:`, removed serializer attribute on `/v1/`, error leaks `ActiveRecord::RecordNotFound`, unbounded `render json: Model.all`, verb in path, etc.]
   **Who Breaks:** [which consumer and how: "mobile v3 reads `total`; removing it from the serializer silently zeroes the displayed price"]
   **Blast Radius:** [scope: which contract version, which callers, coordinated-deploy need]
   **Fix:** [specific: serializer, `/v2/` + `Sunset`, RFC 9457 envelope, Kaminari / Pagy pagination, `Idempotency-Key` header, etc.]

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

- Writing any report file on a no-contract-change skip - a prior `review-api-<branch>.md` must stay byte-identical
- Reporting a deviated convention without naming who breaks ("use a serializer" vs "rendering the `User` model exposes `password_digest` and breaks every client when a column is renamed")
- Rendering a raw AR model via `render json: @model` (`as_json` over-exposure + DB-schema-to-wire coupling)
- Leaking a Ruby backtrace, `ActiveRecord::RecordNotFound`, or an internal ID in an error response
- Calling a change "additive" without a consumer-view check, or "no callers" without a search
- Mutating `/v1/` in place for a breaking change instead of versioning
- An unbounded `render json: Model.all` returned as a collection with no pagination
- Reviewing auth enforcement, strong-params bypass, or mass assignment here - name the contract gap and route to `task-rails-review-security`
- Reviewing idempotency-dedup correctness or timeout behavior here - route to `task-rails-review-reliability`
- Overlapping into perf (throughput) - own the response *shape*, not its cost
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
