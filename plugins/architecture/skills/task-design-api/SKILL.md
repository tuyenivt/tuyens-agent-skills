---
name: task-design-api
description: "Design or review REST API contract: endpoint table, DTO schemas, pagination, error format (RFC 9457), backward compat, per-endpoint security."
metadata:
  category: architecture
  tags: [api, rest, api-design, contract, specification, review, multi-stack]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# API Contract Design & Review

## Purpose

Produce a validated, implementation-ready REST API specification: contract-first design, consistency, backward-compat detection, and security defaults. No implementation code.

## When to Use

- Designing a new REST API before implementation
- Reviewing existing controllers/handlers or an OpenAPI spec for design issues
- Checking backward compatibility of API changes

## Workflow

### Step 1 - Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 - Intake

Classify the input:

- **New design** -- natural language or endpoint list → proceed to Step 3 (Design)
- **Review** -- existing code or OpenAPI spec → proceed to Step 3 (Review mode: validate against rules, report violations)

Accept one of:

| Input                            | Description                                                          |
| -------------------------------- | -------------------------------------------------------------------- |
| Natural language description     | Description of the API needed (resources, operations, relationships) |
| Existing controller/handler code | Code to review for API design issues                                 |
| OpenAPI/Swagger spec             | Existing spec to validate against standards                          |
| Endpoint list                    | List of endpoints to design contracts for                            |

For new designs, clarify:

- What resources are involved and their relationships
- What operations are needed per resource
- Who consumes this API (internal service, public client, mobile app)
- Any existing API conventions in the project
- If the description spans more than 5 resource types, ask the user to prioritize which resources to design first

### Step 3 - Design / Review

Use skill: `backend-api-guidelines`

Validate or design against these rules:

**Naming:**

- Plural nouns for resources: `/api/v1/orders` (not `/api/v1/order`)
- Nested resources for relationships: `/api/v1/orders/{id}/items`
- No verbs in URLs: `POST /api/v1/orders` (not `POST /api/v1/createOrder`)
- Consistent casing: kebab-case for URLs, camelCase or snake_case for JSON fields (match stack convention)
- Version prefix: `/api/v1/...`

**HTTP Methods:**

| Method | Purpose                           | Success               | Common Errors |
| ------ | --------------------------------- | --------------------- | ------------- |
| GET    | Read                              | 200                   | 404           |
| POST   | Create                            | 201 + Location header | 400, 409      |
| PUT    | Full replace                      | 200                   | 404, 400      |
| PATCH  | Partial update (JSON Merge Patch) | 200                   | 404, 400      |
| DELETE | Remove                            | 204                   | 404           |

**State Machine Transitions:**

When a resource has a defined lifecycle (e.g., `draft → pending → paid → shipped → canceled`):

- Model transitions as explicit sub-resource actions: `POST /orders/{id}/transitions` with `{ "to": "pending" }` or named actions: `POST /orders/{id}/submit`, `POST /orders/{id}/cancel`
- Do NOT accept arbitrary `status` values via `PUT /orders/{id}` - this bypasses state machine validation
- Invalid transitions return 422 Unprocessable Entity with the reason

**Idempotency for POST (Create):**

- POST is not idempotent by default - duplicate requests create duplicate resources
- For financially or state-sensitive endpoints, support `Idempotency-Key` header: clients generate a unique key per operation; the server returns the same response for repeated requests with the same key
- Document the deduplication window (e.g., "Idempotency-Key honored for 24 hours")

Use skill: `backend-idempotency` for endpoints with financial or state-critical side effects.

**Multi-Tenancy (when applicable):**

If the API serves multiple tenants, define the tenant isolation pattern:

| Pattern                                            | Use When                                                | Trade-off                                       |
| -------------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------- |
| Path segment (`/api/v1/tenants/{tenantId}/orders`) | Tenant ID must be explicit in every request             | Verbose URLs; clear isolation                   |
| JWT claim (tenant derived from auth token)         | Single-tenant context per session                       | Simpler URLs; requires auth on every endpoint   |
| Header (`X-Tenant-ID`)                             | Service-to-service calls with pre-authenticated context | Easy to forget; requires middleware enforcement |

For each endpoint, verify:

- Tenant isolation: can a request from Tenant A access Tenant B's data?
- Tenant-scoped rate limiting: are limits per-tenant, not global?
- Cross-tenant queries: are admin/superuser endpoints explicitly marked?

**Pagination (mandatory for collections):**

Request: `?page=0&size=20&sort=createdAt,desc`

Response envelope:

```json
{
  "content": [],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 100,
    "totalPages": 5
  }
}
```

Default page size: 20, max: 100

**Error Format (RFC 9457 -- consistent across all endpoints):**

```json
{
  "type": "https://api.example.com/errors/validation-failed",
  "title": "Validation Failed",
  "status": 400,
  "detail": "Request body has 2 validation errors",
  "errors": [{ "field": "email", "message": "must be a valid email" }]
}
```

### Step 4 - Framework Patterns

Apply the detected ecosystem's standards for input validation, response shaping (DTOs/serializers/schemas), pagination, and JSON field casing. If the stack is unfamiliar, fall back to the universal rules in Step 3.

### Step 5 - Backward Compatibility Check

Use skill: `ops-backward-compatibility`

If modifying an existing API, check for breaking changes:

| Change                           | Impact   |
| -------------------------------- | -------- |
| Removed fields from response     | BREAKING |
| Renamed fields                   | BREAKING |
| Changed field types              | BREAKING |
| Added required fields to request | BREAKING |
| Changed URL path or method       | BREAKING |
| Narrowed accepted values         | BREAKING |
| Added optional fields to request | SAFE     |
| Added fields to response         | SAFE     |
| Added new endpoints              | SAFE     |
| Widened accepted values          | SAFE     |

For each breaking change found:

- State what breaks and for which consumers
- Propose a migration path (versioning, deprecation period, dual-write)

### Step 6 - Security Review

For each endpoint, verify:

- **Authentication** -- required or public? Which mechanism (JWT, OAuth2, API key)?
- **Authorization** -- role-based or resource-based (owner check)?
- **Rate limiting** -- applies? What limits?
- **Input validation** -- all request bodies and parameters validated
- **Sensitive data** -- no passwords, tokens, or PII in URLs or logs
- **CORS** -- if consumed by browser clients (SPA, mobile web), specify allowed origins, methods, and headers; preflight caching (`Access-Control-Max-Age`)

### Step 7 - Output

**Endpoint Table:**

| Method | Path           | Description  | Auth | Request         | Response            | Status |
| ------ | -------------- | ------------ | ---- | --------------- | ------------------- | ------ |
| GET    | /api/v1/orders | List orders  | USER | Pageable params | Page<OrderResponse> | 200    |
| POST   | /api/v1/orders | Create order | USER | OrderRequest    | OrderResponse       | 201    |

**DTO/Schema Definitions**: Use the detected ecosystem's standard approach.

**Error Response Examples:**

- 400 Validation Error
- 404 Not Found
- 409 Conflict

**Compatibility Warnings** (if reviewing changes):

- List of breaking changes with migration guidance
- List of safe changes

## Rules

- No implementation code (controllers, service classes, repository methods)
- Every endpoint specifies auth mechanism (not just "required: yes"), request/response shapes, and pagination if a collection
- Error format follows RFC 9457 consistently
- Breaking changes flagged with explicit migration path
- Findings ordered breaking -> warning -> info; omit empty sections

## Self-Check

- [ ] Every endpoint specifies auth mechanism, request/response, and status codes
- [ ] Every collection endpoint has consistent pagination params and response envelope
- [ ] Errors follow RFC 9457 across all endpoints
- [ ] Breaking changes have a stated migration path
- [ ] DTO/schema uses the detected ecosystem's standard approach
- [ ] If reviewing code: every violation states the fix
- [ ] Idempotency-Key documented on state-mutating, financially or irreversibly significant endpoints
- [ ] Multi-tenancy isolation pattern defined when API serves multiple tenants

## Avoid

- Implicit "probably public" endpoints; missing auth statement on any endpoint
- Generic naming advice that ignores the detected stack convention
- Inconsistent pagination shape across endpoints
