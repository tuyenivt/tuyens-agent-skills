---
name: task-node-review-api
description: Node API-contract review - REST design, breaking-change/versioning, response DTOs over ORM entities, RFC 9457 errors, pagination, OpenAPI drift.
agent: node-api-engineer
metadata:
  category: backend
  tags: [node, nestjs, express, api, rest, contract, compatibility, versioning, openapi, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Node API Review

Node-aware API-contract review naming NestJS `@Controller` / `@Get` / `@Post` routes and request DTOs (or Express routers and zod schemas), entity-to-response-DTO boundaries, breaking-change detection from the consumer's view, `/v1/` versioning and `Sunset` deprecation, RFC 9457 error envelopes, pagination shape, and `@nestjs/swagger` / swagger-jsdoc / OpenAPI drift. API review = the contract the service exposes: its REST shape, its evolution across versions, and its honesty about what it returns. Every finding names who breaks and how, with concrete fixes for NestJS / Express.

Stack-specific delegate of `task-code-review-api` for Node.

## When to Use

- NestJS / Express PR adding or changing a route, request DTO, or response DTO
- Pre-merge breaking-change check on a versioned or externally consumed endpoint
- Response-shape / error-envelope / status-code / pagination / resource-naming consistency pass
- OpenAPI / `@nestjs/swagger` / swagger-jsdoc drift check against the DTOs

**Not for:** general review (`task-node-review`), auth enforcement or validation bypass (`task-node-review-security`), idempotency-dedup correctness or behavior under a slow dependency (`task-node-review-reliability`), throughput (`task-node-review-perf`), an active incident (`/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Security:** this lens owns the contract *declaring* an auth scheme, a class-validator / zod constraint, or a rate-limit header; security owns that scheme being *enforced* and unbypassable. A missing `401` in the documented responses is API; an endpoint accepting an unauthenticated request that should be rejected is security. Note the contract gap here; route the enforcement gap to `task-node-review-security`.
- **vs. Reliability:** this lens owns the `Idempotency-Key` header being *part of the contract*; reliability owns the dedup being *atomic under retry*. The header absent from a payment endpoint is API; the read-then-write dedup race is reliability.
- **vs. core Phase B:** `task-node-review` Phase B owns the handler returning the right data; this lens owns that data's shape being conventional, versioned, and stable. Raw-entity-vs-response-DTO leakage sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                             | Runs                                          |
| ---------- | ------------------------------------------------ | --------------------------------------------- |
| `standard` | Default                                          | All steps except the Consumer-Impact Map      |
| `deep`     | Requested, or handed down by `task-node-review`  | All + `Consumer-Impact Map`                   |

At `deep`, trace each changed contract with `ops-backward-compatibility`: what changed, whether it is breaking from the consumer's view, which consumers are affected, and the expand-contract step that keeps them working - captured in the Consumer-Impact Map. A brand-new contract with no consumers yet gets a row stating that - fix its shape before the first consumer ships.

**Whole-service sweep** (API-consistency pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-9 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-node-review-api` | Current branch vs base; fails fast on trunk |
| `/task-node-review-api <branch>` | `<branch>` vs base (3-dot) |
| `/task-node-review-api pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass (e.g. `/task-node-review-api <branch> deep`); `standard` is accepted explicitly. A `--base <branch>` argument (forwarded by `task-code-review-api`) passes to `review-precondition-check` as the explicit base override. When invoked as subagent (e.g. by `task-node-review`), the parent passes the pre-confirmed stack and precondition handle + pre-read diff; Steps 2-3 consume those instead of re-running, and Step 9 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack and Framework

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent (`task-node-review`) and skip detection. If not Node, stop and route the user to `/task-code-review-api`.

Detect framework: NestJS (`nest-cli.json` + `@nestjs/*`) vs Express (`express` without NestJS). Record it - route registration, DTO validation, and OpenAPI tooling all branch on it.

Detect whether an OpenAPI spec is published (`@nestjs/swagger` `@ApiProperty` / `@ApiResponse` decorators, swagger-jsdoc annotations, a committed `swagger.json` / `openapi.yaml`, or a codegen step) - this gates Step 8.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 4 - Read the API Surface

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a changed response DTO ripples to every handler returning it). Checklists apply to the whole surface read: a pre-existing gap on a changed or rippled contract is a finding (note it as pre-existing), not out of scope.

- Route registration: NestJS `@Controller` / `@Get` / `@Post` / `@Put` / `@Patch` / `@Delete` decorators and their path / version prefixes; Express `router.get` / `.post` / `.use` wiring
- Request DTOs and their class-validator decorators (or zod / joi schemas) - required fields, constraints, field names on the wire
- Response DTOs returned from controllers - and whether any handler returns a TypeORM / Prisma entity directly
- Error handling on the response path - NestJS `@Catch` exception filters, Express error middleware, status-code mapping
- Pagination: collection handlers and their query params / response envelope
- `@nestjs/swagger` decorators / swagger-jsdoc annotations / committed OpenAPI spec (if Step 2 found one)

Use skill: `backend-api-guidelines` for the canonical REST / method / status / error / pagination / versioning rules. Use skill: `ops-backward-compatibility` to judge each changed contract from the consumer's view and to produce the expand-contract plan for any breaking change.

### Step 5 - Contract Compatibility

Use skill: `ops-backward-compatibility` for the consumer-view judgment.

- [ ] **Response changes judged from the consumer** - a removed, renamed, or retyped response field; a status-code change; a new enum value in a response field; or a changed error shape is **breaking** until a search proves no consumer. Added optional fields are safe. Enum widening resolves by verify-then-emit: when the search proves every consumer tolerates unknown values and the spec is updated, it is compatible; emitting before that proof is a High finding.
- [ ] **Request changes judged from the consumer** - a new **required** request field, a tightened class-validator / zod constraint (`@IsNotEmpty`, `@MinLength`, `.min()`, adding `@IsEnum`), or a removed accepted field breaks existing callers. New optional fields are safe.
- [ ] **Breaking change carries a version or expand-contract plan** - a `/v2/` route (NestJS URI versioning or a version header) plus a `Sunset` header on the deprecated one, or a dual-read / dual-write transition. A breaking change on `/v1/` in place is a High finding.
- [ ] **"No callers" is proven, not assumed** - `grep` for the field / route across the repo and known consumers; absence of a search is not evidence of no consumer.

### Step 6 - REST / HTTP Design

Use skill: `backend-api-guidelines` for the design rules. Use skill: `node-nestjs-patterns` (NestJS) or `node-express-patterns` (Express) for routing and response conventions.

- [ ] **Resource naming** - plural-noun paths, lowercase, hyphen-separated, no verbs (`POST /balance-recalculations`, not `POST /recalculateBalance`); IDs in path segments, filters / sort / pagination in query. Deliberate RPC-style and webhook endpoints are exempt from naming but not from the rules below.
- [ ] **Method semantics** - GET pure-read (no side effect), POST creates, PUT replaces, PATCH partial-updates, DELETE removes; no state change behind a GET.
- [ ] **Status codes consistent** - 201 + `Location` on create, 204 on empty-body success, 400 vs 422 used deliberately, 409 on conflict, 429 on rate limit; no 200-with-error-body. NestJS: `@HttpCode(204)` where the default 200/201 is wrong.
- [ ] **Sub-resource nesting** - one level (`/orders/{id}/refunds`); an independently addressed child gets a top-level collection (`/refunds?orderId=`) instead of deeper nesting.

### Step 7 - Response Shape, Errors, and Pagination

Use skill: `node-nestjs-patterns` / `node-express-patterns` for the entity-to-DTO boundary and JSON response shape. Use skill: `node-exception-handling` for the filter / middleware wiring and domain-error hierarchy. These atomics' internal-facing examples emit `{error, message}` bodies; where any of them differs from this workflow's contract rules (RFC 9457 fields, no ad-hoc envelopes), **this workflow's rules win** - it reviews the published contract; they build internals.

- [ ] **Response DTO, never a raw entity** - handlers return a dedicated response DTO (class-transformer `@Expose` / `plainToInstance`, or a mapped plain object), not a TypeORM / Prisma entity. Returning the entity over-exposes internal fields (`passwordHash`, internal FKs, soft-delete timestamps) and couples the wire contract to the DB schema, so a column rename silently breaks clients.
- [ ] **RFC 9457 error envelope** - errors return `type` / `title` / `status` / `detail` / `instance`, consistently across handlers, from a `@Catch` filter (NestJS) or terminal error middleware (Express). No JS stack trace, no `QueryFailedError` / `PrismaClientKnownRequestError` message, no internal ID leaked to the client.
- [ ] **Every collection paginated** - a list endpoint returns a bounded page with a consistent envelope (`items` + `nextCursor` / total), never an unbounded `find()` / `findMany()` returned whole. Cursor for large / write-heavy collections, offset only for small / stable ones.
- [ ] **Field naming and nullability consistent** - response fields follow one convention (snake_case or camelCase, not mixed); a field that can be absent is optional / documented nullable, not a silent `undefined` dropped by `JSON.stringify`.

### Step 8 - Versioning and OpenAPI Drift

Use skill: `backend-api-guidelines` for versioning and the idempotency-key contract.

- [ ] **Version on breaking change** - a new major version is a new prefix / header (NestJS URI or header versioning), not a mutated `/v1/`; the deprecated version carries a `Sunset` header and a migration note.
- [ ] **Idempotency-Key in the contract** - a non-idempotent `POST` on money / notification / provisioning declares an `Idempotency-Key` header in its documented request (the dedup *correctness* routes to `task-node-review-reliability`).
- [ ] **OpenAPI matches code** _(only if Step 2 found a published spec)_ - changed routes, DTO fields, status codes, and error shapes are reflected in the `@nestjs/swagger` decorators (`@ApiProperty` / `@ApiResponse`) / swagger-jsdoc annotations. A field on the DTO but absent from the decorators (or a documented field the handler no longer returns) is drift, and generated clients will be wrong.

```typescript
// Bad - returns the TypeORM entity: leaks passwordHash + couples the wire to the DB schema
@Get(':id')
async get(@Param('id') id: string): Promise<User> {
  return this.users.findOneByOrFail({ id });
}

// Good - explicit response DTO via class-transformer; only the fields the contract promises
@Get(':id')
async get(@Param('id') id: string): Promise<UserResponseDto> {
  const user = await this.users.findOneByOrFail({ id });
  return plainToInstance(UserResponseDto, user, { excludeExtraneousValues: true });
}
```

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 9 - Write Report

Standalone only - subagent runs return findings in the Output Format to the parent, which writes the single merged report. At `deep`, a subagent returns the Consumer-Impact Map with its findings so the parent can preserve it as its own section.

Use skill: `review-report-writer` with `report_type: review-api` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: both = `HEAD`), `stack: node-nestjs` (or `node-express` as detected in Step 2), `scope: +api`, `depth` as resolved from the Depth table, and `mode: full`, `round: 1` - unless `review-api-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no collection endpoint, no published OpenAPI spec).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Node (or pre-confirmed stack accepted from parent); framework (NestJS / Express) recorded; OpenAPI-spec presence recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once; `current_head_sha` and `current_base_sha` captured
- [ ] Step 4: routes, request DTOs, response DTOs, error paths, pagination, and any OpenAPI spec read; `backend-api-guidelines` + `ops-backward-compatibility` consulted
- [ ] Step 5: every changed request / response contract judged from the consumer's view; breaking changes flagged with a version / expand-contract requirement; "no callers" proven by search
- [ ] Step 6: resource naming, method semantics, status codes, sub-resource nesting checked
- [ ] Step 7: response DTO (no raw entity), RFC 9457 errors, pagination, field-naming consistency checked
- [ ] Step 8: versioning on breaking change; `Idempotency-Key` in the contract for non-idempotent POST; OpenAPI drift checked (if a spec exists)
- [ ] Step 9: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names who breaks and how, never just the deviated convention
- [ ] Depth honored: `standard` ran all; `deep` filled the Consumer-Impact Map
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unversioned breaking change to an externally consumed contract, or a leaked internal shape (raw TypeORM / Prisma entity exposed, stack trace / ORM error in the response); Medium = a breaking change to an internal contract with no coordinated-deploy note, an inconsistent status code / error envelope, an unpaginated unbounded collection, a method-semantics violation (state change behind GET - High when the side effect is destructive or money-moving), a non-idempotent POST with no `Idempotency-Key` in the contract, or OpenAPI drift on a published spec; Low = naming / convention / field-casing drift with no consumer impact, or OpenAPI drift on an internal-only spec. When consumption is unknown, treat a published or versioned surface (`/v1/` route, published spec) as externally consumed. Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on an external contract; Low -> `[Recommend]`.

**One finding per root cause:** when a defect satisfies multiple checklist items (a raw entity exposed that is also unversioned), report it once at the strongest severity and fold the other aspects into that finding - do not emit one finding per checklist line. A defect chain triggered by one change (a tightened schema routing new errors into a leaking handler) is one root cause.

```markdown
## Node API Review Summary

**Stack Detected:** Node.js <version> / TypeScript <version>
**Framework:** NestJS <version> | Express <version>
**OpenAPI Spec:** @nestjs/swagger | swagger-jsdoc | committed openapi.yaml | none detected
**Overall:** Conventional & Compatible | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line or route]
   **Issue:** [name the gap: raw TypeORM / Prisma entity returned from controller, removed response field on `/v1/`, error leaks `QueryFailedError`, unpaginated `findMany()`, verb in path, etc.]
   **Who Breaks:** [which consumer and how: "mobile v3 unmarshals `total`; removing it from the response silently zeroes the displayed price"]
   **Blast Radius:** [scope: which contract version, which callers, coordinated-deploy need]
   **Fix:** [specific: response DTO via `plainToInstance`, `/v2/` + `Sunset`, RFC 9457 envelope, cursor pagination, `Idempotency-Key` header, etc.]

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

- Reporting a deviated convention without naming who breaks ("use a DTO" vs "returning the `User` entity exposes `passwordHash` and breaks every client when a column is renamed")
- Returning a raw TypeORM / Prisma entity from a controller (over-exposure + DB-schema-to-wire coupling)
- Leaking a JS stack trace, `QueryFailedError` / `PrismaClientKnownRequestError`, or an internal ID in an error response
- Calling a change "additive" without a consumer-view check, or "no callers" without a search
- Mutating `/v1/` in place for a breaking change instead of versioning
- An unbounded `find()` / `findMany()` returned as a collection with no pagination
- Reviewing auth enforcement or `ValidationPipe` / zod bypass here - name the contract gap and route to `task-node-review-security`
- Reviewing idempotency-dedup correctness or timeout behavior here - route to `task-node-review-reliability`
- Overlapping into perf (throughput) - own the response *shape*, not its cost
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
