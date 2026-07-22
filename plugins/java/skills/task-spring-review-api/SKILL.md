---
name: task-spring-review-api
description: Spring Boot API-contract review - REST design, breaking-change/versioning, DTOs over JPA entities, RFC 9457 errors, pagination, OpenAPI drift.
agent: java-api-engineer
metadata:
  category: backend
  tags: [java, spring-boot, api, rest, contract, compatibility, versioning, openapi, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spring API Review

Spring-aware API-contract review naming `@RestController` routes and `@RequestBody` DTOs, JPA-entity-to-response-DTO boundaries, breaking-change detection from the consumer's view, `/v1/` versioning and `Sunset` deprecation, RFC 9457 `ProblemDetail` error envelopes, pagination shape, and springdoc-openapi drift. API review = the contract the service exposes: its REST shape, its evolution across versions, and its honesty about what it returns. Every finding names who breaks and how, with concrete fixes for Java 21+ / Spring Boot 3.5+.

Stack-specific delegate of `task-code-review-api` for Java.

## When to Use

- Spring Boot PR adding or changing a `@RestController` route, `@RequestBody` DTO, or response DTO
- Pre-merge breaking-change check on a versioned or externally consumed endpoint
- Response-shape / error-envelope / status-code / pagination / resource-naming consistency pass
- springdoc-openapi drift check against the controllers and DTOs

**Not for:** general review (`task-spring-review`), auth enforcement or validation bypass (`task-spring-review-security`), idempotency-dedup correctness or behavior under a slow dependency (`task-spring-review-reliability`), throughput (`task-spring-review-perf`), an active incident (`/task-oncall-start` - mitigate first).

## Seam With Adjacent Lenses

- **vs. Security:** this lens owns the contract *declaring* an auth scheme, a Bean Validation constraint (`@NotNull`, `@Size`), or a rate-limit header; security owns that scheme being *enforced* and `@Valid` being unbypassable. A missing `401` in the documented responses is API; an endpoint accepting an unauthenticated request that should be rejected is security. Note the contract gap here; route the enforcement gap to `task-spring-review-security`.
- **vs. Reliability:** this lens owns the `Idempotency-Key` header being *part of the contract*; reliability owns the dedup being *atomic under retry*. The header absent from a payment endpoint is API; the read-then-write dedup race is reliability.
- **vs. core Phase B:** `task-spring-review` Phase B owns the controller returning the right data; this lens owns that data's shape being conventional, versioned, and stable. Raw-JPA-entity-vs-response-DTO leakage sits at the seam - the umbrella dedups.

## Depth

| Depth      | When                                              | Runs                                          |
| ---------- | ------------------------------------------------- | --------------------------------------------- |
| `standard` | Default                                           | All steps except the Consumer-Impact Map      |
| `deep`     | Requested, or handed down by `task-spring-review` | All + `Consumer-Impact Map`                   |

At `deep`, trace each changed contract with `ops-backward-compatibility`: what changed, whether it is breaking from the consumer's view, which consumers are affected, and the expand-contract step that keeps them working - captured in the Consumer-Impact Map.

**Whole-service sweep** (API-consistency pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-9 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file; Step 5's changed-contract checks are N/A); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-spring-review-api` | Current branch vs base; fails fast on trunk |
| `/task-spring-review-api <branch>` | `<branch>` vs base (3-dot) |
| `/task-spring-review-api pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass (e.g. `/task-spring-review-api <branch> deep`); `standard` is accepted explicitly. A `--base <branch>` argument (forwarded by `task-code-review-api`) passes to `review-precondition-check` as the explicit base override. When invoked as subagent (e.g. by `task-spring-review`), the parent passes the pre-confirmed stack and precondition handle + pre-read diff; Steps 2-3 consume those instead of re-running, and Step 9 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from a parent (`task-spring-review`) and skip detection. If not Spring Boot, stop and route the user to `/task-code-review-api`.

Detect whether an OpenAPI spec is published (springdoc-openapi on the classpath, `@Operation` / `@Schema` annotations, a committed `openapi.yaml` / `swagger.json`, or a codegen step) - this gates Step 8. Record which form: annotated / committed file / **bare springdoc** (classpath only, no annotations - the spec auto-tracks the code). Response-DTO / record convention and OpenAPI-spec detection is always this skill's own job even as a subagent - a pre-confirmed stack covers language / framework only, not the spec form; still run this detection - the parent's handle does not carry it.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with handle + artifacts pre-passed. Surface any fail-fast verbatim.

Standalone only - capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`. Subagent runs write no report, so skip the SHA capture.

### Step 4 - Read the API Surface

**Contract-change quick-scan gate (before loading any guideline atomic).** Scan the diff for a contract-change signal: a changed `@RestController` / `@RequestMapping` route registration, a changed request-body / DTO / `@RequestParam` schema, a changed / added / removed response DTO or record, a changed response shape or status code, an error-envelope (`ProblemDetail` / `@RestControllerAdvice`) change, a pagination change, or a springdoc / OpenAPI spec edit. If NONE is present: emit `No contract change detected - API review skipped` and STOP before loading `backend-api-guidelines` / `ops-backward-compatibility`. This gate does not apply to a whole-service sweep (it reviews current code, not a diff). A skip writes NO report file - a prior `review-api-<branch>.md` with its findings and round state stays byte-identical (standalone prints the skip line; subagent returns it to the parent).

Before applying checklists, read every changed file in these categories plus any unchanged file the diff calls into (a changed response DTO ripples to every controller returning it):

- Route registration: `@RestController` / `@RequestMapping` class prefixes and `@GetMapping` / `@PostMapping` / `@PutMapping` / `@PatchMapping` / `@DeleteMapping` methods - paths, methods, version prefixes
- Request DTOs and their Bean Validation annotations (`@NotNull`, `@Size`, `@Pattern`) and field names on the wire - required fields, constraints
- Response DTOs / records returned from controllers - and whether any handler returns a JPA `@Entity` directly
- Error handling on the response path - `@RestControllerAdvice` / `@ExceptionHandler`, `ProblemDetail` shapes, status-code mapping
- Pagination: collection endpoints and their `Pageable` params / `Page<T>` / `Slice<T>` envelope
- springdoc-openapi annotations / committed OpenAPI spec (if Step 2 found one)

Use skill: `backend-api-guidelines` for the canonical REST / method / status / error / pagination / versioning rules. Use skill: `ops-backward-compatibility` to judge each changed contract from the consumer's view and to produce the expand-contract plan for any breaking change.

### Step 5 - Contract Compatibility

Use skill: `ops-backward-compatibility` for the consumer-view judgment.

- [ ] **Response changes judged from the consumer** - a removed, renamed, or retyped response-DTO field; a status-code change; a new enum value in a response field; or a changed error shape is **breaking** until a search proves no consumer. Added optional fields are safe.
- [ ] **Request changes judged from the consumer** - a new **required** request field, a tightened Bean Validation constraint (`@NotNull`, `@Size`, `@Pattern`), or a removed accepted field breaks existing callers. New optional fields are safe.
- [ ] **Breaking change carries a version or expand-contract plan** - a `/v2/` route (or version header) plus a `Sunset` header on the deprecated one, or a dual-read / dual-write transition. A breaking change on `/v1/` in place is a High finding.
- [ ] **"No callers" is proven, not assumed** - search for the field / route across the repo and known consumers; absence of a search is not evidence of no consumer.

### Step 6 - REST / HTTP Design

Use skill: `backend-api-guidelines` for the design rules.

- [ ] **Resource naming** - plural-noun paths, lowercase, hyphen-separated, no verbs (`POST /balance-recalculations`, not `POST /recalculateBalance`); IDs in `@PathVariable` segments, filters / sort / pagination in `@RequestParam`. Deliberate RPC-style and webhook endpoints are exempt from naming but not from the rules below.
- [ ] **Method semantics** - GET pure-read (no side effect), POST creates, PUT replaces, PATCH partial-updates, DELETE removes; no state change behind a `@GetMapping`.
- [ ] **Status codes consistent** - 201 + `Location` on create, 204 on empty-body success, 400 vs 422 used deliberately, 409 on conflict, 429 on rate limit; no 200-with-error-body.
- [ ] **Sub-resource nesting** - one level (`/orders/{id}/refunds`); an independently addressed child gets a top-level collection (`/refunds?orderId=`) instead of deeper nesting.

### Step 7 - Response Shape, Errors, and Pagination

DTO-projection rule (inlined on purpose - do not re-delegate to `spring-jpa-performance`; its full query mechanics - N+1, fetch join, JDBC batching - are perf's concern): project the entity to a response record before serialization so no lazy association or internal column reaches the wire. Use skill: `spring-exception-handling` for the RFC 9457 error envelope.

- [ ] **Response DTO, never a raw entity** - controllers return a dedicated response DTO / record, not a JPA `@Entity`. Returning the entity over-exposes internal fields (`passwordHash`, internal FKs, soft-delete timestamps), triggers lazy-loading serialization surprises, and couples the wire contract to the JPA schema, so a column rename silently breaks clients.
- [ ] **RFC 9457 error envelope** - errors return a `ProblemDetail` (`type` / `title` / `status` / `detail` / `instance`), consistently across handlers via `@RestControllerAdvice`. No Java stack trace, no `EntityNotFoundException` message, no internal ID leaked to the client.
- [ ] **Every collection paginated** - a list endpoint returns a bounded page with a consistent envelope (`Page<T>` with total, or `Slice<T>` with `hasNext`), never an unbounded `findAll()`. Keyset / cursor for large / write-heavy collections, offset only for small / stable ones.
- [ ] **Field naming and nullability consistent** - JSON field names follow one convention (snake_case or camelCase, not mixed - set via `spring.jackson.property-naming-strategy` or `@JsonProperty`); a field that can be absent is `@JsonInclude(NON_NULL)` or documented nullable, not a silent default value.

### Step 8 - Versioning and OpenAPI Drift

Use skill: `backend-api-guidelines` for versioning and the idempotency-key contract.

- [ ] **Version on breaking change** - a new major version is a new prefix / header, not a mutated `/v1/`; the deprecated version carries a `Sunset` header and a migration note.
- [ ] **Idempotency-Key in the contract** - a non-idempotent `@PostMapping` on money / notification / provisioning declares an `Idempotency-Key` header in its documented request (the dedup *correctness* routes to `task-spring-review-reliability`).
- [ ] **OpenAPI matches code** _(only if Step 2 found a published spec)_ - changed routes, DTO fields, status codes, and error shapes are reflected in the springdoc-openapi `@Operation` / `@Schema` annotations / spec. A field on the record but absent from the `@Schema` (or a documented field the controller no longer returns) is drift, and generated clients will be wrong. **Bare springdoc** (no annotations): the published spec mutates silently with every contract change - fold that silent-mutation risk into the compatibility finding, and flag undocumented status codes / error shapes on changed endpoints as a published-spec gap.

```java
// Bad - returns the JPA @Entity: leaks passwordHash + couples the wire to the JPA schema + lazy-load surprises
@GetMapping("/{id}")
public User get(@PathVariable Long id) {
    return userRepository.findById(id).orElseThrow();
}

// Good - explicit response record; only the fields the contract promises
@GetMapping("/{id}")
public UserResponse get(@PathVariable Long id) {
    User u = userRepository.findById(id).orElseThrow();
    return new UserResponse(u.getId(), u.getEmail(), u.getName());
}
```

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 9 - Write Report

Standalone only - subagent runs return the full Output Format body (findings, Recommendations, and at `deep` the Consumer-Impact Map as its own section) to the parent, which writes the single merged report.

Use skill: `review-report-writer` with `report_type: review-api` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha` / `head_sha` from Step 3 (whole-service sweep: both = `HEAD`), `stack: java-spring-boot`, `scope: +api`, `depth` as resolved from the Depth table, and `mode: full`, `round: 1` - unless `review-api-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no collection endpoint, no published OpenAPI spec).

- [ ] Step 1: behavioral principles loaded
- [ ] Step 2: stack confirmed Java 21+ / Spring Boot 3.5+ (or pre-confirmed stack accepted from parent); OpenAPI-spec presence recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once; standalone captured `current_head_sha` / `current_base_sha` (subagent skips)
- [ ] Step 4: contract-change quick-scan gate ran (skip + no-write if none, except whole-service sweep); then routes, request DTOs, response DTOs, error paths, pagination, and any OpenAPI spec read; `backend-api-guidelines` + `ops-backward-compatibility` consulted
- [ ] Step 5: every changed request / response contract judged from the consumer's view; breaking changes flagged with a version / expand-contract requirement; "no callers" proven by search
- [ ] Step 6: resource naming, method semantics, status codes, sub-resource nesting checked
- [ ] Step 7: response DTO (no raw `@Entity`), RFC 9457 `ProblemDetail` errors, pagination, field-naming consistency checked
- [ ] Step 8: versioning on breaking change; `Idempotency-Key` in the contract for non-idempotent `@PostMapping`; OpenAPI drift checked (if a spec exists)
- [ ] Step 9: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names who breaks and how, never just the deviated convention
- [ ] Depth honored: `standard` ran all; `deep` filled the Consumer-Impact Map
- [ ] Next Steps tagged and ordered by intent (omit if none)

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = an unversioned breaking change to an externally consumed contract, or a leaked internal shape (raw JPA `@Entity` exposed, stack trace / `EntityNotFoundException` message in the response); Medium = a breaking change to an internal contract with no coordinated-deploy note, an inconsistent status code / error envelope, an unpaginated unbounded collection, a method-semantics violation (state change behind a `@GetMapping` - High when the side effect is destructive or money-moving), a non-idempotent `@PostMapping` with no `Idempotency-Key` in the contract, or OpenAPI drift on a published spec; Low = naming / convention / field-casing drift with no consumer impact, or OpenAPI drift on an internal-only spec. When consumption is unknown, treat a published or versioned surface (`/v1/` route, published spec) as externally consumed. Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on an external contract; Low -> `[Recommend]`.

**One finding per root cause:** when a defect satisfies multiple checklist items (a raw entity exposed that is also unversioned), report it once at the strongest severity and fold the other aspects into that finding - do not emit one finding per checklist line.

```markdown
## Spring API Review Summary

**Stack Detected:** Java <version> / Spring Boot <version>
**OpenAPI Spec:** springdoc-openapi | committed openapi.yaml | none detected
**Overall:** Conventional & Compatible | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line or route]
   **Issue:** [name the gap: raw JPA `@Entity` returned, removed response field on `/v1/`, error leaks `EntityNotFoundException` message, unpaginated `findAll()`, verb in path, etc.]
   **Who Breaks:** [which consumer and how: "mobile v3 deserializes `total`; removing it from the response silently zeroes the displayed price"]
   **Blast Radius:** [scope: which contract version, which callers, coordinated-deploy need]
   **Fix:** [specific: response record, `/v2/` + `Sunset`, `ProblemDetail` envelope, keyset pagination, `Idempotency-Key` header, etc.]

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
- Returning a raw JPA `@Entity` from a `@RestController` (over-exposure + lazy-load serialization surprises + JPA-schema-to-wire coupling)
- Leaking a Java stack trace, `EntityNotFoundException` message, or an internal ID in an error response
- Calling a change "additive" without a consumer-view check, or "no callers" without a search
- Mutating `/v1/` in place for a breaking change instead of versioning
- An unbounded `findAll()` returned as a collection with no `Pageable` / `Page<T>` pagination
- Reviewing auth enforcement or `@Valid` bypass here - name the contract gap and route to `task-spring-review-security`
- Reviewing idempotency-dedup correctness or timeout behavior here - route to `task-spring-review-reliability`
- Overlapping into perf (throughput, N+1, `LazyInitializationException`) - own the response *shape*, not its cost
- Writing any report file on a no-contract-change skip - a prior `review-api-<branch>.md` must stay byte-identical
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
