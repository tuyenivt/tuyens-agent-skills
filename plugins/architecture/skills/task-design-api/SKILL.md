---
name: task-design-api
description: Design or review a REST API contract -- produces an endpoint table, DTO schemas, pagination, error format (RFC 9457), backward compatibility assessment, and per-endpoint security requirements.
metadata:
  category: architecture
  tags: [api, rest, api-design, contract, specification, review, multi-stack]
  type: workflow
user-invocable: true
---

# API Contract Design & Review

## Purpose

Catch API design issues before implementation by producing a validated, implementation-ready API specification:

- **Contract-first** -- design the API contract before writing code
- **Consistency enforcement** -- naming, methods, status codes, error format
- **Compatibility awareness** -- detect breaking changes before they ship
- **Security by default** -- authentication, authorization, and input validation on every endpoint

This skill produces an API specification. It does not generate implementation code.

## When to Use

- Designing a new REST API before implementation
- Reviewing existing controller/handler code for API design issues
- Validating an OpenAPI/Swagger spec against organizational standards
- Checking backward compatibility of API changes
- Pre-implementation API contract review

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

Use skill: `api-guidelines`

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

Use skill: `idempotency` for endpoints with financial or state-critical side effects.

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

### Step 4 - Framework-Specific Patterns

After loading stack-detect, apply API implementation patterns appropriate to the detected ecosystem:

- **Input validation**: Use the framework's standard validation mechanism (annotations, struct tags, strong parameters, schema validators, etc.)
- **Response shaping**: Use dedicated response objects appropriate to the ecosystem (DTOs, serializers, response structs, schemas)
- **Pagination**: Use the framework's pagination library or implement a consistent pagination pattern
- **JSON field naming**: Follow the convention standard for the detected ecosystem (camelCase, snake_case, etc.)

If the detected stack is unfamiliar, apply the universal API design rules from Step 3 and recommend the user consult their framework's documentation.

### Step 5 - Backward Compatibility Check

Use skill: `backward-compatibility-analysis`

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

| Method | Path                | Description   | Auth  | Request           | Response              | Status   |
| ------ | ------------------- | ------------- | ----- | ----------------- | --------------------- | -------- |
| GET    | /api/v1/orders      | List orders   | USER  | Pageable params   | Page\<OrderResponse\> | 200      |
| POST   | /api/v1/orders      | Create order  | USER  | OrderRequest      | OrderResponse         | 201      |
| GET    | /api/v1/orders/{id} | Get order     | USER  | --                | OrderResponse         | 200, 404 |
| PUT    | /api/v1/orders/{id} | Replace order | ADMIN | OrderRequest      | OrderResponse         | 200, 404 |
| PATCH  | /api/v1/orders/{id} | Update order  | USER  | OrderPatchRequest | OrderResponse         | 200, 404 |
| DELETE | /api/v1/orders/{id} | Delete order  | ADMIN | --                | --                    | 204, 404 |

**DTO/Schema Definitions** (language-appropriate):

Use the detected ecosystem's standard approach for defining request/response schemas.

**Error Response Examples:**

- 400 Validation Error
- 404 Not Found
- 409 Conflict

**Compatibility Warnings** (if reviewing changes):

- List of breaking changes with migration guidance
- List of safe changes

### Output Constraints

- No implementation code (no service classes, no repository code)
- Every endpoint must specify auth requirements
- Every collection endpoint must include pagination
- Error format must be consistent (RFC 9457)
- Findings ordered by severity (breaking → warning → info)
- Omit empty sections

## Rules

- Never generate implementation code -- produce API specifications only
- Every endpoint must have defined request/response shapes
- Every collection endpoint must support pagination
- Error format must follow RFC 9457 (Problem Details for HTTP APIs)
- All endpoints must state authentication and authorization requirements
- Breaking changes must be explicitly flagged with migration guidance

## Self-Check

- [ ] Every endpoint has defined auth requirements (not just "required: yes" but which mechanism)
- [ ] Every collection endpoint has pagination in request params and response envelope
- [ ] Error format follows RFC 9457 consistently across all endpoints
- [ ] Breaking changes explicitly identified with migration path - not just flagged
- [ ] DTO/schema definitions use the detected ecosystem's standard approach
- [ ] No implementation code generated - specification only
- [ ] If reviewing existing code: every violation states the fix, not just the rule
- [ ] Framework-specific patterns applied for the detected stack, not generic advice
- [ ] Idempotency-Key documented on state-mutating endpoints with financial or irreversible side effects
- [ ] Multi-tenancy isolation pattern defined when API serves multiple tenants

## Avoid

- Generating implementation code (service classes, repository methods, or controllers)
- Omitting auth requirements on any endpoint - no implicit "this one is probably public"
- Collections without pagination - every list endpoint must have it
- Inconsistent error formats across endpoints
- Breaking change warnings without migration guidance
- Generic naming advice without checking against the actual detected stack convention
- Treating OpenAPI/Swagger spec validation as a separate concern from design quality
- Inconsistent pagination across endpoints -- same envelope and parameter names everywhere
