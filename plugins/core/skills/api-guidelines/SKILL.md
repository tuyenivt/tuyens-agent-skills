---
name: api-guidelines
description: REST API design - resource naming, HTTP methods, error handling, pagination. Auto-detects project stack and adapts API patterns to the detected ecosystem.
metadata:
  category: governance
  tags: [api, rest, http, conventions, multi-stack]
user-invocable: false
---

# API Guidelines

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing new REST API endpoints
- Reviewing API contracts for consistency
- Ensuring backward-compatible API evolution

## Universal Rules (All Stacks)

- Resource names are plural nouns, lowercase, hyphen-separated (`/order-items`)
- Use HTTP methods correctly: GET (read), POST (create), PUT (full replace), PATCH (partial update), DELETE (remove)
- Return appropriate HTTP status codes: 200, 201, 204, 400, 401, 403, 404, 409, 422, 500
- Error responses follow RFC 9457 (Problem Details): `type`, `title`, `status`, `detail`, `instance`
- Never expose internal IDs, stack traces, or implementation details in error responses
- Paginate all collection endpoints - never return unbounded lists. Use cursor-based pagination for large or frequently updated datasets (stable ordering, no skipped rows); use offset-based only for small datasets with infrequent mutations.
- Version APIs when making breaking changes (`/v1/`, `/v2/` or header-based). Deprecate old versions with a sunset date in the response header (`Sunset: Sat, 01 Jan 2027 00:00:00 GMT`).
- Never expose ORM entities / model objects directly in responses - always use DTOs / serializers / response structs
- For non-idempotent POST endpoints (payments, order creation, message sends), support an `Idempotency-Key` header. Store the key + response for the deduplication window (typically 24h). Return the same response on replay without re-executing the operation.

---

## Endpoint Design Principles

### Request Handling

- Validate all input at the API boundary using the framework's validation mechanism (annotations, struct tags, strong parameters, schema validators, etc.)
- Use the framework's standard request binding/parsing approach
- Return appropriate error responses for validation failures

### Response Shaping

- Always use dedicated response objects (DTOs, serializers, response structs) - never return ORM/model objects directly
- Use projection queries to fetch only needed fields from the data layer
- Paginate collection endpoints with consistent pagination metadata

### Rate Limiting

- Apply rate limiting at the API gateway or middleware level, not inside business logic
- Return `429 Too Many Requests` with `Retry-After` header (seconds until the client can retry)
- Include rate limit headers in responses: `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`
- Use token bucket or sliding window algorithms - fixed window has burst-at-boundary issues
- Rate limit by API key or authenticated user, not by IP alone (IPs are shared behind NATs/proxies)

### Conventions

- Use the framework's standard routing and controller/handler patterns
- Apply global error handling to ensure consistent error response format across all endpoints
- Use middleware for cross-cutting concerns (auth, logging, CORS, rate limiting)

## Stack-Specific Guidance

After loading stack-detect, apply API patterns using the idioms of the detected ecosystem:

- Use the framework's standard controller/handler declaration pattern for endpoints
- Apply the framework's validation mechanism (e.g., annotation-based validation, struct tag validation, strong parameters, schema libraries)
- Use the ecosystem's pagination library or pattern for collection endpoints
- Configure global error handling using the framework's standard mechanism (e.g., error handler middleware, controller advice, rescue handlers)
- Follow the JSON field naming convention standard for the detected ecosystem (camelCase, snake_case, etc.)

If the detected stack is unfamiliar, apply the universal rules above and recommend the user consult their framework's API documentation.

---

## Output Format

Consuming workflow skills depend on this structure to surface API violations consistently.

```
## API Guidelines Assessment

**Stack:** {detected language / framework}

### Violations

- [Severity: High | Medium | Low] {endpoint or file:line if available} - {description of violation}
  - Rule: {the API guideline rule violated}
  - Fix: {concrete correction using the detected stack's idioms}

### No Violations Found

{State explicitly if API design is compliant - do not omit this section silently}
```

**Severity guidance:**

- **High**: ORM entity exposed in response, missing input validation, no error response format, non-idempotent financial POST without `Idempotency-Key` support
- **Medium**: Wrong HTTP method or status code, missing pagination on collection endpoint, offset pagination on high-volume mutable collection
- **Low**: Naming inconsistency (e.g., mixed camelCase/snake_case), missing API version header, missing `Sunset` header on deprecated endpoint

Omit "No Violations Found" if violations were listed.

## Avoid (All Stacks)

- Verbs in endpoint paths (`/getOrder`, `/createOrder`)
- Exposing ORM/entity objects directly in API responses
- Inconsistent status codes across endpoints
- Missing pagination on collection endpoints
- Error responses that leak stack traces or internal details
