---
name: task-code-review-api
description: API review entry point: contract compatibility, REST/HTTP design, versioning, pagination, error shape, OpenAPI drift. Detects stack, dispatches.
metadata:
  category: review
  tags: [api, rest, http, contract, compatibility, versioning, openapi, multi-stack, router]
  type: workflow
user-invocable: true
---

# API Review (Router)

Detects the project stack and delegates to the matching stack-specific API review (`task-{stack}-review-api`). For unknown stacks, runs a minimal generic API review.

API review = the contract the service exposes - its shape, evolution, and honesty. It owns whether an endpoint follows REST/HTTP conventions, whether a change breaks existing consumers, and whether the published contract (OpenAPI) matches the code. It does not own whether auth is enforced (that is security) or whether the handler survives a slow dependency (that is reliability).

## When to Use

- New or changed REST endpoint, request/response schema, or public event contract
- Pre-merge breaking-change check on a versioned or externally consumed API
- Pagination, error-envelope, status-code, or resource-naming consistency pass
- OpenAPI / generated-client drift check against the implementation

**Not for:** General review (`task-code-review`), endpoint auth / input-validation enforcement (`task-code-review-security`), handler behavior under failure (`task-code-review-reliability`), throughput (`task-code-review-perf`), a live incident (oncall plugin `/task-oncall-start`).

## Seam With Adjacent Lenses

- **vs. Security:** API owns the contract *declaring* an auth scheme, a validation constraint, or a rate-limit header; security owns that scheme being *enforced* and *unbypassable*. A missing `401` in the documented responses is API; an endpoint that accepts an unauthenticated request that should be rejected is security. Report the contract gap here; route the enforcement gap to `task-code-review-security`.
- **vs. Reliability:** API owns the `Idempotency-Key` header being *part of the contract*; reliability owns the dedup being *atomic and correct under retry*. The header absent from a payment endpoint's spec is API; the read-then-write dedup race is reliability.
- **vs. core correctness:** core Phase B owns the handler returning the right data; API owns that data's shape being conventional, versioned, and stable. Response-DTO-vs-ORM-entity leakage sits at the seam - the umbrella synthesis dedups.

## Invocation

`/task-code-review-api [<branch> | pr-<N>] [standard | deep] [--base <branch>]`

When invoked as a subagent by `task-code-review` (extra scope), the parent supplies the detected stack, precondition handle, and read-once diff/log: skip Steps 2-3, run Step 4 on the supplied diff, return findings per Output Format, and skip Step 5 - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Dispatch to Stack Workflow

| Detected stack       | Delegate to               |
| -------------------- | ------------------------- |
| Java / Spring Boot   | `task-spring-review-api`  |
| Python               | `task-python-review-api`  |
| Ruby / Rails         | `task-rails-review-api`   |
| Node.js / TypeScript | `task-node-review-api`    |
| Go / Gin             | `task-go-review-api`      |

Rows match on language/runtime - the framework named is the plugin's primary flavor, not a filter (Go + Echo still dispatches to `task-go-review-api`; the stack workflow adapts or bounces back here).

Forward arguments and stop. **If matched, skip Steps 4-5.** If the matched workflow is unavailable (stack plugin not installed), tell the user which plugin provides it, then run Steps 4-5. Stacks with no matching plugin fall through to the Step 4 generic fallback.

### Step 4 - Generic Fallback (no dispatch)

Use skill: `review-precondition-check` when running standalone (skip if the parent supplied a handle). Read diff and commit log once. Depth `standard` (default): review changed endpoints, schemas, and serializers, plus every unchanged endpoint a changed schema or serializer ripples to (a changed response shape pulls in each endpoint returning it); `deep`: read each touched contract surface in full and trace every response field to its source and every consumer of a changed contract.

**Whole-service sweep** (API-consistency pass with no feature branch): when the precondition check fails fast on trunk, do not stop - skip the diff gate and review the API surface repo-wide at `HEAD`; findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

Cover the applicable categories. Use skill: `backend-api-guidelines` for the canonical REST/HTTP design rules and `ops-backward-compatibility` for the compatibility judgment and expand-contract plan.

**Contract compatibility.** Every changed request/response schema and event contract judged from the consumer's view: added optional field safe; removed field, renamed field, type change, tightened constraint, new required request field, new enum value in a response, changed status code, or changed error shape is breaking until proven otherwise. Breaking change without a version bump or expand-contract plan is a finding. "No external callers" requires a search, not an assumption.

**REST / HTTP design.** Resource paths plural nouns, no verbs; correct method semantics (GET/POST/PUT/PATCH/DELETE); status codes used consistently (200/201/204/400/401/403/404/409/422/429/500); IDs in path, filters in query; sub-resources nested one level. Deliberate RPC-style and webhook endpoints are exempt from naming but still follow status/error/validation rules.

**Response shape and honesty.** Responses returned through DTOs / serializers / response structs, never raw ORM entities (over-exposure and accidental contract coupling). Error responses follow RFC 9457 Problem Details; no stack traces or internal IDs leaked. Collections paginated (cursor for large/write-heavy, offset only for small/stable) with consistent envelope and metadata.

**Versioning and evolution.** Breaking changes carry a version bump (`/v1/`, `/v2/`, or header) and deprecated versions a `Sunset` header. Non-idempotent POST endpoints (payments, order creation, message sends) declare an `Idempotency-Key` header in the contract (the dedup *correctness* is reliability's - route it).

**OpenAPI / documentation drift.** If the project publishes an OpenAPI spec or generated client, the changed endpoints, schemas, status codes, and error shapes match the code. A response field present in code but absent from the spec (or vice versa) is drift.

Every finding names who breaks and how (not just the deviated convention) and states blast radius (which consumers, which version). One finding per root cause - fold overlapping aspects (a raw entity that is also unversioned) into the strongest finding. **Severity:** High = an unversioned breaking change to an externally consumed contract, or a leaked internal shape (raw ORM entity, stack trace); Medium = a breaking change to an internal contract without a coordinated-deploy note, an inconsistent status code / error envelope, an unpaginated unbounded collection, a method-semantics violation (state change behind GET - High when the side effect is destructive or money-moving), or a non-idempotent POST with no `Idempotency-Key` in the contract; Low = naming / convention drift with no consumer impact. When consumption is unknown, treat a published or versioned surface (`/v1/` path, OpenAPI-documented) as externally consumed. Next Steps map severity to intent: High -> `[Must]`, Medium -> `[Recommend]`, Low -> `[Recommend]` or `[Question]`.

### Step 5 - Write Report

Standalone only - subagent runs return findings to the parent instead. Use skill: `review-report-writer` with `report_type: review-api` and every required input: `report_body`, `branch` (from the handle), the handle's refs, `base_sha` / `head_sha` via `git rev-parse`, `scope: +api`, `depth` as invoked (default `standard`), `stack` from `stack-detect` (kebab-case language-framework, or `unknown`), and `mode: full`, `round: 1` - unless `review-api-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`.

## Output Format

When Step 3 dispatched: the stack workflow owns the output. When fallback ran:

```markdown
## API Review Summary

**Stack Detected:** [detected stack, or unknown] (generic fallback applied)
**Overall:** Conventional & Compatible | Gaps Found - [High/Medium/Low counts]

## Findings

### High Impact

- **Location:** [file:line or endpoint]
- **Issue:** [name the gap: unversioned breaking change, raw ORM entity exposed, error leaks internals, unpaginated collection, etc.]
- **Who Breaks:** [which consumers and how: "mobile v3 deserializer rejects the removed `total` field"]
- **Blast Radius:** [scope: which contract version, which callers]
- **Fix:** [specific: version bump + expand-contract, wrap in DTO, add pagination, RFC 9457 envelope, etc.]

### Medium Impact

[Same structure]

### Low Impact / Quick Wins

[Same structure]

_Omit sections with no findings. If all are omitted, state "No API contract or design gaps found." and omit Next Steps._

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: security] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (cross-cutting - e.g. enforcement to security, dedup correctness to reliability, gateway rate limits to platform). Order Must > Recommend > Question. Omit if none._
```

At `deep`, append a `## Consumer-Impact Map` section before Next Steps - per changed contract: what changed, whether it is breaking from the consumer's view, which consumers are affected, and the expand-contract step that keeps them working. A brand-new contract with no consumers yet gets a row stating that - fix its shape before the first consumer ships.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: if matched and installed, stack workflow ran with arguments forwarded; Steps 4-5 skipped
- [ ] Step 4: if no dispatch, every applicable category (compatibility / REST design / response shape / versioning / OpenAPI drift) covered (repo-wide at `HEAD` on a trunk sweep); every finding names who breaks, blast radius, and a rubric-based severity
- [ ] Step 5: report written via `review-report-writer` with all required inputs (standalone fallback only; subagent runs return findings to the parent)

## Avoid

- Running both Step 3 dispatch and Step 4 fallback
- Writing a report when invoked as a subagent - the parent owns it
- API findings without naming who breaks ("rename the field" vs "removing `total` breaks mobile v3, which has no fallback")
- Reviewing endpoint auth enforcement or input-validation bypass here - name the contract gap and route to `task-code-review-security`
- Reviewing idempotency-dedup correctness or timeout behavior here - route to `task-code-review-reliability`
- Judging a change "additive" without a consumer-view check, or "no callers" without a search
- Overlapping into security (enforcement) or reliability (behavior under failure) - own the contract, route the rest
- Emitting labels outside `[Must]` / `[Recommend]` / `[Question]`
