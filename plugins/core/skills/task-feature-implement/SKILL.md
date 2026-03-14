---
name: task-feature-implement
description: Universal feature implementation entry point for new functionality requiring multiple coordinated layers (API + service + persistence + tests). Detects your stack and delegates to the appropriate workflow (task-spring-new, task-go-new, task-python-new, etc.). Use when implementing a new endpoint, resource, domain aggregate, or cross-layer feature. Not for bug fixes (use task-debug), not for refactoring existing code (use task-code-refactor), and not for single-file or isolated changes.
metadata:
  category: backend
  tags: [feature, implementation, scaffold, stack-agnostic]
  type: workflow
user-invocable: true
---

# Feature Implementation

Stack-agnostic entry point for end-to-end feature implementation. Detects the project stack and delegates to the right stack-specific workflow.

## Inputs

| Field               | Required | Description                                              |
| ------------------- | -------- | -------------------------------------------------------- |
| Feature description | Yes      | What to build (user story, ticket, or plain description) |
| Affected layers     | No       | Which layers are in scope (API, DB, jobs, etc.)          |
| Special constraints | No       | Auth, performance, migration sensitivity, etc.           |

## Steps

### Step 1 - Detect Stack

Use skill: stack-detect

### Step 2 - Delegate to Stack Workflow

Based on the detected stack, invoke the appropriate workflow:

| Detected Stack              | Delegate to       |
| --------------------------- | ----------------- |
| Java / Spring Boot          | `task-spring-new` |
| Kotlin / Spring Boot        | `task-kotlin-new` |
| .NET / ASP.NET Core         | `task-dotnet-new` |
| Python / FastAPI or Django  | `task-python-new` |
| Ruby / Rails                | `task-rails-new`  |
| Node.js / NestJS or Express | `task-node-new`   |
| Go / Gin                    | `task-go-new`     |
| Rust / Axum                 | `task-rust-new`   |

If the detected stack does not match any of the above, proceed with the universal fallback below.

### Step 3 - Universal Fallback (Unknown Stack)

If no matching stack workflow exists, implement the feature using universal best practices:

**GATHER** - Confirm before proceeding:

- Feature name, operations (CRUD / custom actions), affected layers
- Entity relationships and validation constraints
- External dependencies or integration points
- Auth requirements: which endpoints are public vs protected
- Background job or async processing needs

**DESIGN** - Propose and wait for explicit approval before generating any code:

- Data model changes (schema, entity fields, indexes for FK and filter columns)
- Service/business logic structure and transaction boundaries
- API contract: endpoints (method + URI + request/response shapes + status codes)
- Error model: how validation failures and not-found cases are communicated

**IMPLEMENT (in order):**

1. **Data layer**: schema migration with indexes; never modify existing columns destructively
2. **Business logic**: service or domain objects with constructor injection; no business logic in controllers
3. **API layer**: controllers/routes/handlers; never expose data layer entities directly in API responses - always map to response DTOs or structs
4. **Auth**: confirm every endpoint has explicit auth - no implicit defaults
5. **Background jobs** (if applicable): async task processing
6. **Tests**: unit tests for business logic; integration tests for data layer against a real DB; API tests for routing, serialization, and auth

**VALIDATE:**

- Run the project's test suite and confirm all pass
- Confirm the implementation matches the approved design
- Confirm list endpoints are paginated

**Output:**

```markdown
## Generated Files

- [ ] Migration: [path]
- [ ] Model/Entity: [path]
- [ ] Service: [path]
- [ ] Controller/Handler: [path]
- [ ] DTO/Response types: [path]
- [ ] Unit tests: [path]
- [ ] Integration tests: [path]

## Endpoints

| Method | URI | Status | Description |
| ------ | --- | ------ | ----------- |
| ...    | ... | ...    | ...         |

## Tests

- Unit tests: {count}
- Integration tests: {count}
```

## Self-Check

- [ ] Stack detected and stack-specific workflow invoked (or fallback applied with explanation)
- [ ] Requirements confirmed and design approved before any code generated
- [ ] All layers implemented: migration, model, service, controller, DTOs, tests
- [ ] No data layer entities exposed directly in API responses - DTOs/response structs used
- [ ] Every endpoint has explicit auth; list endpoints are paginated
- [ ] Migration is safe: no destructive column changes without expand-contract sequencing
- [ ] Tests pass; file list, endpoint table, and test count presented

## Notes

- This skill is a dispatcher. The depth and quality of the output depends on the delegated stack workflow.
- For polyglot monorepos, detect the primary backend stack and note any secondary stacks.
- If the user wants to skip stack detection (e.g., in a context where it always fails), they can invoke the stack-specific workflow directly.

