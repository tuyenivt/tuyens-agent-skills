---
name: backend-api-guidelines
description: Review REST API design for resource naming, HTTP methods, status codes, pagination, errors, versioning, and idempotency. Stack-adaptive.
metadata:
  category: governance
  tags: [api, rest, http, conventions, multi-stack]
user-invocable: false
---

# API Guidelines

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing new REST endpoints
- Reviewing API contracts for consistency
- Planning backward-compatible API evolution

For a GraphQL or gRPC API, the transport rules (paths, methods, status codes, pagination params) do not apply - reviewing against them manufactures violations from design choices the paradigm made. What carries over is boundary validation, error-shape consistency (GraphQL `errors[]` entries carrying `extensions.code`; gRPC status codes with `google.rpc.Status` details), no ORM entities on the wire, idempotency on non-idempotent mutations (the key is a required mutation argument in GraphQL, request metadata in gRPC), bounded collections (paginated via the paradigm's own mechanism, e.g. GraphQL connections with `first`/`after`), and versioning on breaking change. Express fixes in the paradigm's idiom (a GraphQL breaking change gets a `@deprecated` cycle, not `/v2` paths). Review that subset and append the assessed paradigm to the **Stack:** line. In design mode for such a paradigm, the API Design table's columns become the paradigm's equivalents: operation or message in place of method and path, error shape in place of status codes, the paradigm's pagination mechanism, and the same Idempotency column, where `Idempotency-Key required` means the required mutation argument or metadata key.

## Rules

- Resource paths are plural nouns, lowercase, hyphen-separated (`/order-items`). No verbs in paths. A read-only aggregate a parent has exactly one of is a singular noun sub-resource (`GET /events/{id}/waitlist-summary`).
- Methods: GET reads, POST creates, PUT replaces, PATCH partial-updates, DELETE removes.
- Status codes: 200, 201, 202, 204, 400, 401, 403, 404, 409, 422, 429, 500. Used consistently. A filter query parameter naming a nonexistent parent returns `200` with an empty collection; a nonexistent path segment returns `404`; a body field naming a nonexistent resource returns `422`; a request the resource's current state refuses (insufficient balance, already cancelled) returns `409` - `422` is for a body that cannot be processed as sent (fails validation, names a nonexistent resource, reuses an `Idempotency-Key` with a different body).
- Errors follow RFC 9457 (Problem Details): media type `application/problem+json`, members `type`, `title`, `status`, `detail`, `instance`. Never leak stack traces or internal IDs.
- Responses use DTOs / serializers / response structs, including a webhook acknowledgement body (or `204` with none). Never return ORM entities directly (a struct that is both the row mapping and the response body is the entity); an ad-hoc dict or map is not a DTO either, and a declared DTO whose serializer cannot read the entity (a direct Pydantic v2 `model_validate(entity)` without `from_attributes=True`; FastAPI's `response_model` reads attributes without it) is a broken DTO, graded as a wrong status code, not as exposure.
- Resource IDs live in path segments (`/users/123`). Query params are for filtering, sorting, pagination on collections.
- Nest sub-resources one level (`/orders/{id}/refunds`). A child that is addressed independently (fetched, updated, or reversed by its own ID) gets its own top-level collection (`/refunds?order_id=`) instead of nesting; each resource has one canonical path, never a nested and a top-level form side by side. A path a design document has already fixed is kept verbatim in design mode; a proposed change to it goes in the Conventions line.
- Paginate every unbounded collection. Use cursor-based for large or write-heavy datasets; offset only for small, stable ones. A collection bounded by the domain itself (a shipment's events, an order's line items) may return whole with a documented maximum; a per-account history that grows for the life of the account is unbounded. A paginated endpoint caps its page-size parameter (`limit`, `size`) at a documented maximum.
- Version on breaking change (`/v1/`, `/v2/` or header). A new API surface starts at `/v1/`; a new endpoint on an existing surface follows that surface's scheme, versioned or not. Mark a deprecated version with the `Deprecation` header (RFC 9745) and, once its removal is scheduled, `Sunset` (RFC 8594) carrying the removal date.
- Every non-idempotent POST or PATCH endpoint (any POST that creates a resource or sends a message - a payment, an order, a hold; a recompute whose repeat yields the same state is idempotent and exempt, while an endpoint whose repeat emits another external effect - a re-sent webhook or email - is a message send; a webhook receiver deduplicates by the provider's event ID instead) requires an `Idempotency-Key` header - a request without one is rejected with `400`, not processed unprotected. The stored key binds to a fingerprint of the request body: same key and body replays the stored response for the dedup window (typically 24h), same key with a different body is `422`, a key whose first request is still in flight is `409`. Rules for the store itself are `backend-idempotency`'s. An obligation the handler delegates (the fingerprint, the in-flight `409`) is checked in the code it calls.
- Validate input at the boundary using the framework's mechanism (annotations, struct tags, strong params, schema validators).
- Rate limit at the gateway or middleware, never inside business logic. Return `429` with `Retry-After` and the `RateLimit` / `RateLimit-Policy` fields (IETF httpapi draft); `X-RateLimit-*` is the legacy vendor convention. Limit by API key or user, not IP.
- Deliberate non-REST endpoints inside a REST surface (RPC-style actions, webhook receivers) follow the surface's versioning scheme and are not versioned separately; status codes, error format, and validation still apply, and resource naming is downgraded: an action modelled as a verb path is one Low finding proposing the resource form (`POST /balance-recalculations`, not `POST /recalculate-balances`). Webhook handlers deduplicate by the provider's event ID and acknowledge with `202` (`200` when processing completes synchronously; `204` when the acknowledgement has no body) before heavy processing; signature verification is a security review's concern, not this skill's.

## Patterns

### Error response (RFC 9457)

```
# Bad - leaks internals, ad-hoc shape
{ "status": "error", "msg": "NullPointerException at OrderService.java:42" }

# Good - Problem Details, Content-Type: application/problem+json
{
  "type": "https://api.example.com/errors/order-not-found",
  "title": "Order not found",
  "status": 404,
  "detail": "No order with the given ID exists for this account.",
  "instance": "/v1/orders/123"
}
```

### Pagination shape

A cursor response is `{ "items": [...], "next_cursor": "<opaque>" }`. A cursor is correct only when it encodes the full sort key and that sort is total. Sorting by a non-unique column (`created_at DESC`) with a cursor on a different one (`id`) skips or repeats rows whenever values tie - append a unique tiebreaker and encode both (`ORDER BY created_at DESC, id DESC`, cursor `{created_at, id}`). A well-shaped cursor API with a partial sort key is the common silent defect here.

### Stack-specific application

After stack-detect, express Fixes in the detected ecosystem's idioms (its validation mechanism, pagination library, global error handler, JSON field naming). When `Language` is `unknown`, apply the universal rules and append ` - unfamiliar stack, verify against framework docs` to the Stack line. Write `<language> (no framework detected)` when stack-detect reports a known `Language` and `Framework: unknown`.

## Output Format

Consuming workflows parse this structure. Order violations by severity, High first. An obligation checked in code outside the reviewed scope (a delegated fingerprint check, rate limiting at a gateway) yields a finding only when the reviewed code shows it broken (a fingerprint helper called without the body) or shows every layer the Rules allow for it is missing (a reviewed middleware chain and gateway config, neither with a rate limiter) - a handler or a single layer that simply does not contain it is not evidence; a finding resting on a call into unread code ends `(unverified - <file or config path> not read)`, one that read every allowed layer carries no suffix.

```
## API Guidelines Assessment

**Stack:** {language / framework | <language> (no framework detected) | unknown}{ - <paradigm: GraphQL, gRPC>}{ - unfamiliar stack, verify against framework docs}

### Violations                                  {when at least one violation}

- [Severity: High | Medium | Low] {endpoint or file:line; when one rule is broken the same way at several endpoints, all sites comma-separated} - {description}{ (unverified - <file or config path> not read)}
  - Rule: {the rule violated}
  - Fix: {concrete correction using the detected stack's idioms; for a raised convention, the migration cost}

### No Violations Found                         {instead, when none: one sentence stating the API is compliant}

Notes: {a decision or scope boundary the findings cannot hold}       {only when one exists}
```

In design mode (no existing code to review), apply Rules as constraints and emit this instead, with the same Stack line:

```
## API Design

**Stack:** {as above}

| Method | Path | Status codes | Pagination | Idempotency |
| ------ | ---- | ------------ | ---------- | ----------- |
| {GET \| POST \| PUT \| PATCH \| DELETE} | {path} | {the codes this endpoint can return; 500 is implied everywhere} | {cursor (limit max <N>) \| offset (size max <N>) \| whole (bounded by <domain fact>, max <N>) \| -} | {Idempotency-Key required \| natural (idempotent method: GET, PUT, DELETE, or a PATCH that only sets fields) \| natural (repeat yields the same state) \| provider event ID dedup} |

Conventions: {error format, versioning scheme, rate-limit posture, field naming; any proposed change to a path a design document fixed, as `<fixed path> -> <proposed path>`}

Notes: {decisions the table cannot hold - ownership (403 vs 404), auth scheme, dedup window}       {only when one exists}
```

**Severity:**

- **High**: ORM entity exposed, missing input validation (a body field or path parameter accepted with no constraint; a field constrained incompletely is Medium), an error response leaking stack traces or internal IDs, non-idempotent POST or PATCH (payment, order creation, message send) without a required `Idempotency-Key`
- **Medium**: Wrong method or status code, an error body not in RFC 9457 shape, missing pagination (including an uncapped page size), offset pagination on high-write collection, a raw dict/map in place of a DTO, a deviation existing clients would break on (envelope shape, a breaking change without a deprecation cycle)
- **Low**: Field naming drift, no version indicator (path or header) on a surface that has shipped a breaking change, missing `Deprecation` on a deprecated endpoint or missing `Sunset` on one whose removal is scheduled, verb path on a deliberate RPC endpoint

These are examples, not a closed list. For unlisted violations, classify by impact: data exposure or unsafe retries = High, wrong semantics or scalability = Medium, naming and metadata hygiene = Low. When a finding matches multiple tiers, report the highest. One finding per obligation per endpoint: a rule with several independent obligations (webhook dedup and early ack; idempotency's required header, body fingerprint, and in-flight `409`) yields one finding per obligation broken, each with its own Fix; the same obligation broken the same way at N endpoints is one finding listing all N sites. Density is not capped - a file with eight distinct obligations broken gets eight findings.

A convention the project has documented and built clients against (a response envelope, a field-naming scheme) is the baseline for consistency findings, not a violation - report deviation *from it*, and raise the convention itself only once, as Low, with the migration cost in its Fix. A convention is documented when the project's instruction file or the client's contract states it. Correctness and safety rules (validation, error leakage, idempotency, ORM exposure) hold regardless of local convention.

## Avoid

- Introducing a generic success envelope (`{status:"success", data:{...}}`) where none is documented - return the resource directly (a collection's `items` plus `next_cursor` wrapper is pagination metadata, not an envelope); reserve envelopes for errors (RFC 9457)
