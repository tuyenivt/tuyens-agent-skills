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

For a GraphQL or gRPC API, the transport rules (paths, methods, status codes, pagination params) do not apply - reviewing against them manufactures violations from design choices the paradigm made. What carries over is boundary validation, error-shape consistency, no ORM entities on the wire, idempotency on non-idempotent mutations, bounded collections (paginated via the paradigm's own mechanism, e.g. GraphQL connections with `first`/`after`), and versioning on breaking change. Express fixes in the paradigm's idiom (a GraphQL breaking change gets a `@deprecated` cycle, not `/v2` paths). Review that subset and append the assessed paradigm to the **Stack:** line. In design mode for such a paradigm, the API Design table's columns become the paradigm's equivalents: operation or message in place of method and path, error shape in place of status codes, the paradigm's pagination mechanism, and the same Idempotency column.

## Rules

- Resource paths are plural nouns, lowercase, hyphen-separated (`/order-items`). No verbs in paths.
- Methods: GET reads, POST creates, PUT replaces, PATCH partial-updates, DELETE removes.
- Status codes: 200, 201, 202, 204, 400, 401, 403, 404, 409, 422, 429, 500. Used consistently. A filter query parameter naming a nonexistent parent returns `200` with an empty collection; a nonexistent path segment returns `404`.
- Errors follow RFC 9457 (Problem Details): media type `application/problem+json`, members `type`, `title`, `status`, `detail`, `instance`. Never leak stack traces or internal IDs.
- Responses use DTOs / serializers / response structs, including a webhook acknowledgement body (or `204` with none). Never return ORM entities directly; an ad-hoc dict or map is not a DTO either, and a declared DTO whose serializer cannot read the entity (a missing ORM-mode setting) is a broken DTO, graded as a wrong status code, not as exposure.
- Resource IDs live in path segments (`/users/123`). Query params are for filtering, sorting, pagination on collections.
- Nest sub-resources one level (`/orders/{id}/refunds`). A child that is addressed independently (fetched, updated, or reversed by its own ID) gets its own top-level collection (`/refunds?order_id=`) instead of nesting; each resource has one canonical path, never a nested and a top-level form side by side. A path a design document has already fixed is kept verbatim in design mode; a proposed change to it goes in the Conventions line.
- Paginate every unbounded collection. Use cursor-based for large or write-heavy datasets; offset only for small, stable ones. A collection bounded by the domain itself (a shipment's events, an order's line items) may return whole with a documented maximum; a per-account history that grows for the life of the account is unbounded.
- Version on breaking change (`/v1/`, `/v2/` or header); a new API starts at `/v1/`. Mark a deprecated version with the `Deprecation` header (RFC 9745) and, once its removal is scheduled, `Sunset` (RFC 8594) carrying the removal date.
- Every non-idempotent POST or PATCH endpoint (payments, order creation, message sends are the common cases; a recompute whose repeat yields the same state is idempotent and exempt) requires an `Idempotency-Key` header - a request without one is rejected with `400`, not processed unprotected. The stored key binds to a fingerprint of the request body: same key and body replays the stored response for the dedup window (typically 24h), same key with a different body is `422`, a key whose first request is still in flight is `409`. Rules for the store itself are `backend-idempotency`'s.
- Validate input at the boundary using the framework's mechanism (annotations, struct tags, strong params, schema validators).
- Rate limit at the gateway or middleware, never inside business logic. Return `429` with `Retry-After` and the `RateLimit` / `RateLimit-Policy` fields (IETF httpapi draft); `X-RateLimit-*` is the legacy vendor convention. Limit by API key or user, not IP.
- Deliberate non-REST endpoints inside a REST surface (RPC-style actions, webhook receivers) follow the surface's versioning scheme and are not versioned separately; status codes, error format, and validation still apply, and resource naming is downgraded: an action modelled as a verb path is one Low finding proposing the resource form (`POST /balance-recalculations`, not `POST /recalculate-balances`). Webhook handlers deduplicate by the provider's event ID and acknowledge with `202` (`200` when processing completes synchronously) before heavy processing; signature verification is a security review's concern, not this skill's.

## Patterns

### Resource identifiers in the path

```
# Bad - identifier in query string
GET /users?id=123

# Good - identifier in path
GET /users/123
```

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

```
# Bad - offset on a high-write collection, no metadata
GET /events?page=500&size=20

# Good - cursor encoding the full sort key (created_at DESC, id DESC)
GET /events?cursor=eyJjcmVhdGVkX2F0IjoiMjAyNi0wOS0xMlQxMDowMDowMFoiLCJpZCI6MTIzNDV9&limit=20
-> { "items": [...], "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNi0wOS0xMlQwOTo1ODowMFoiLCJpZCI6MTIzMjV9" }
```

A cursor is correct only when it encodes the full sort key and that sort is total. Sorting by a non-unique column (`created_at DESC`) with a cursor on a different one (`id`) skips or repeats rows whenever values tie - append a unique tiebreaker and encode both (`ORDER BY created_at DESC, id DESC`, cursor `{created_at, id}`). A well-shaped cursor API with a partial sort key is the common silent defect here.

### Idempotent POST

```
# Bad - retry creates duplicate charge
POST /payments  { "amount": 100 }

# Good - retry with the same key and body returns the stored response
POST /payments
Idempotency-Key: "550e8400-e29b-41d4-a716-446655440000"
{ "amount": 100 }
```

### Stack-specific application

After stack-detect, apply these patterns using the detected ecosystem's idioms: standard controller/handler declaration, native validation mechanism, ecosystem pagination library, global error handler, and JSON field naming convention (camelCase vs snake_case). When `Language` is `unknown`, apply the universal rules and append ` - unfamiliar stack, verify against framework docs` to the Stack line.

## Output Format

Consuming workflows parse this structure. Order violations by severity, High first.

```
## API Guidelines Assessment

**Stack:** {language / framework | unknown}{ - <paradigm: GraphQL, gRPC>}{ - unfamiliar stack, verify against framework docs}

### Violations                                  {when at least one violation}

- [Severity: High | Medium | Low] {endpoint or file:line; when one rule is broken the same way at several endpoints, all sites comma-separated} - {description}
  - Rule: {the rule violated}
  - Fix: {concrete correction using the detected stack's idioms; for a raised convention, the migration cost}

### No Violations Found                         {instead, when none: one sentence stating the API is compliant}
```

In design mode (no existing code to review), apply Rules as constraints and emit this instead, with the same Stack line:

```
## API Design

**Stack:** {as above}

| Method | Path | Status codes | Pagination | Idempotency |
| ------ | ---- | ------------ | ---------- | ----------- |
| {GET \| POST \| PUT \| PATCH \| DELETE} | {path} | {the codes this endpoint can return; 500 is implied everywhere} | {cursor \| offset \| whole (bounded by <domain fact>) \| -} | {Idempotency-Key required \| natural (idempotent method: GET, PUT, DELETE, or a PATCH that only sets fields)} |

Conventions: {error format, versioning scheme, rate-limit posture, field naming}
```

**Severity:**

- **High**: ORM entity exposed, missing input validation, missing error format, non-idempotent POST or PATCH (payment, order creation, message send) without a required `Idempotency-Key`
- **Medium**: Wrong method or status code, missing pagination, offset pagination on high-write collection, a raw dict/map in place of a DTO, a deviation existing clients would break on (envelope shape, a breaking change without a deprecation cycle)
- **Low**: Field naming drift, no version indicator (path or header) on a surface that has shipped a breaking change, missing `Deprecation`/`Sunset` on a deprecated endpoint, verb path on a deliberate RPC endpoint

These are examples, not a closed list. For unlisted violations, classify by impact: data exposure or unsafe retries = High, wrong semantics or scalability = Medium, naming and metadata hygiene = Low. When a finding matches multiple tiers, report the highest. One finding per obligation per endpoint: a rule with several independent obligations (webhook dedup and early ack; idempotency's required header, body fingerprint, and in-flight `409`) yields one finding per obligation broken, each with its own Fix; the same obligation broken the same way at N endpoints is one finding listing all N sites. Density is not capped - a file with eight distinct obligations broken gets eight findings.

A convention the project has documented and built clients against (a response envelope, a field-naming scheme) is the baseline for consistency findings, not a violation - report deviation *from it*, and raise the convention itself only once, as Low, with the migration cost in its Fix. A convention is documented when the project's instruction file or the client's contract states it. Correctness and safety rules (validation, error leakage, idempotency, ORM exposure) hold regardless of local convention.

## Avoid

- Verbs in paths (`/getOrder`, `/createOrder`)
- Introducing a generic success envelope (`{status:"success", data:{...}}`) where none is documented - return the resource directly (a collection's `items` plus `next_cursor` wrapper is pagination metadata, not an envelope); reserve envelopes for errors (RFC 9457)
- PUT for partial updates (PUT replaces; use PATCH)
- Same-release deployment of a breaking API change without versioning
