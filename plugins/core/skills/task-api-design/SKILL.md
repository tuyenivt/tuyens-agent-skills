---
name: task-api-design
description: REST API contract design and review. Auto-detects project stack from CLAUDE.md and adapts API patterns to the detected language and framework.
metadata:
  category: architecture
  tags: [api, rest, api-design, contract, specification, review, multi-stack]
  type: workflow
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

### Step 1 — Detect Stack

Use skill: `stack-detect` to identify language, framework, and tooling.

### Step 2 — Intake

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

### Step 3 — Design / Review

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

### Step 4 — Framework-Specific Patterns

After loading stack-detect, apply API implementation patterns appropriate to the detected ecosystem:

- **Input validation**: Use the framework's standard validation mechanism (annotations, struct tags, strong parameters, schema validators, etc.)
- **Response shaping**: Use dedicated response objects appropriate to the ecosystem (DTOs, serializers, response structs, schemas)
- **Pagination**: Use the framework's pagination library or implement a consistent pagination pattern
- **JSON field naming**: Follow the convention standard for the detected ecosystem (camelCase, snake_case, etc.)

If the detected stack is unfamiliar, apply the universal API design rules from Step 3 and recommend the user consult their framework's documentation.

### Step 5 — Backward Compatibility Check

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

### Step 6 — Security Review

For each endpoint, verify:

- **Authentication** -- required or public? Which mechanism (JWT, OAuth2, API key)?
- **Authorization** -- role-based or resource-based (owner check)?
- **Rate limiting** -- applies? What limits?
- **Input validation** -- all request bodies and parameters validated
- **Sensitive data** -- no passwords, tokens, or PII in URLs or logs

### Step 7 — Output

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

## Key Skills Reference

**API Design and Governance:**

- Use skill: `api-guidelines` for naming, method, and documentation standards
- Use skill: `backward-compatibility-analysis` for breaking change detection

**Related Workflows:**

- Use skill: `task-architecture-design` for broader system architecture beyond API contracts
- Use skill: `task-code-review-advanced` for reviewing implementation against this API spec

## Avoid

- Generating controller, service, or repository implementation code
- Designing internal architecture (that belongs to `task-architecture-design`)
- Ignoring backward compatibility for existing APIs
- Inconsistent error formats across endpoints
- Missing pagination on collection endpoints
- Verb-based endpoint naming
- Designing endpoints without stating auth requirements
- Generic advice without context-specific reasoning
- Applying API conventions from one framework to another
