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

## Rules

- Resource paths are plural nouns, lowercase, hyphen-separated (`/order-items`). No verbs in paths.
- Methods: GET reads, POST creates, PUT replaces, PATCH partial-updates, DELETE removes.
- Status codes: 200, 201, 204, 400, 401, 403, 404, 409, 422, 429, 500. Used consistently.
- Errors follow RFC 9457 (Problem Details): `type`, `title`, `status`, `detail`, `instance`. Never leak stack traces or internal IDs.
- Responses use DTOs / serializers / response structs. Never return ORM entities directly.
- Resource IDs live in path segments (`/users/123`). Query params are for filtering, sorting, pagination on collections.
- Nest sub-resources one level (`/orders/{id}/refunds`). A child that is addressed independently gets its own top-level collection (`/refunds?order_id=`) instead of deeper nesting.
- Paginate every collection. Use cursor-based for large or write-heavy datasets; offset only for small, stable ones.
- Version on breaking change (`/v1/`, `/v2/` or header). Mark deprecated versions with `Sunset` header.
- Non-idempotent POST endpoints (payments, order creation, message sends) accept an `Idempotency-Key` header; cache the response for the dedup window (typically 24h).
- Validate input at the boundary using the framework's mechanism (annotations, struct tags, strong params, schema validators).
- Rate limit at the gateway or middleware, never inside business logic. Return `429` with `Retry-After` and `X-RateLimit-*` headers. Limit by API key or user, not IP.
- Deliberate non-REST endpoints (RPC-style actions, webhook receivers) are exempt from resource-naming rules; status codes, error format, and validation still apply. Prefer modeling actions as resources (`POST /balance-recalculations`, not `POST /recalculate-balances`). Webhook handlers deduplicate by the provider's event ID and acknowledge with 2xx before heavy processing.

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

# Good - Problem Details
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

# Good - cursor with stable ordering
GET /events?cursor=eyJpZCI6MTIzNDV9&limit=20
-> { "items": [...], "next_cursor": "eyJpZCI6MTIzNjV9" }
```

### Idempotent POST

```
# Bad - retry creates duplicate charge
POST /payments  { amount: 100 }

# Good - retry returns cached response
POST /payments
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000
{ amount: 100 }
```

### Stack-specific application

After stack-detect, apply these patterns using the detected ecosystem's idioms: standard controller/handler declaration, native validation mechanism, ecosystem pagination library, global error handler, and JSON field naming convention (camelCase vs snake_case). If the stack is unfamiliar, apply the universal rules and recommend the user consult their framework's API documentation.

## Output Format

Consuming workflows parse this structure. In design mode (no existing code to review), apply Rules as constraints and output the proposed endpoint table (method, path, status codes, pagination) instead of the assessment block.

```
## API Guidelines Assessment

**Stack:** {detected language / framework}

### Violations

- [Severity: High | Medium | Low] {endpoint or file:line} - {description}
  - Rule: {the rule violated}
  - Fix: {concrete correction using the detected stack's idioms}

### No Violations Found

{State explicitly if compliant - do not omit this section silently}
```

**Severity:**

- **High**: ORM entity exposed, missing input validation, missing error format, non-idempotent financial POST without `Idempotency-Key`
- **Medium**: Wrong method or status code, missing pagination, offset pagination on high-write collection
- **Low**: Field naming drift, missing version header, missing `Sunset` on deprecated endpoint

These are examples, not a closed list. For unlisted violations, classify by impact: data exposure or unsafe retries = High, wrong semantics or scalability (verbs in paths, missing pagination) = Medium, naming and metadata hygiene = Low. When a finding matches multiple tiers, report the highest. One finding per rule violated.

Omit "No Violations Found" if violations were listed.

## Avoid

- Verbs in paths (`/getOrder`, `/createOrder`)
- Generic success envelopes (`{status:"success", data:{...}}`) - return the resource directly; reserve envelopes for errors (RFC 9457)
- PUT for partial updates (PUT replaces; use PATCH)
- Same-release deployment of a breaking API change without versioning
