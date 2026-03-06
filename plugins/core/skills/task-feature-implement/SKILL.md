---
name: task-feature-implement
description: Universal feature implementation entry point. Detects your project stack and delegates to the appropriate stack-specific workflow (task-spring-new, task-go-new, task-python-new, etc.).
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

If the detected stack does not match any of the above, proceed with the universal fallback below.

### Step 3 - Universal Fallback (Unknown Stack)

If no matching stack workflow exists, implement the feature using universal best practices:

**Gather:**

- Confirm the feature description with the user
- Identify which layers are affected: data model, business logic, API, background jobs, tests
- Identify external dependencies or integration points

**Design:**

- Propose data model changes (schema, entity design)
- Propose service/business logic structure
- Propose API contract (endpoints, request/response shapes)
- Present design for user approval before generating code

**Implement (in order):**

1. Data layer: schema migrations or model changes
2. Business logic: service or domain objects
3. API layer: controllers, routes, handlers
4. Background jobs (if applicable)
5. Tests: unit tests for business logic, integration tests for API and data layer

**Validate:**

- Run the project's test suite
- Confirm the implementation matches the agreed design

**Output:**

- List of created/modified files
- Endpoint or API summary
- Test count and coverage delta

## Success Criteria

A well-executed feature implementation passes all of these. Use as a self-check before presenting to the user.

### Completeness

- [ ] Stack detected correctly and stack-specific workflow invoked (or fallback applied with explanation)
- [ ] Feature requirements confirmed with user before code generation
- [ ] All affected layers implemented: data, business logic, API, tests
- [ ] Tests pass

### Quality Signal

- [ ] Design presented and approved before implementation
- [ ] No untested public API surfaces
- [ ] Migration or schema change is backward-compatible or explicitly flagged
- [ ] File list and summary presented to user

## Notes

- This skill is a dispatcher. The depth and quality of the output depends on the delegated stack workflow.
- For polyglot monorepos, detect the primary backend stack and note any secondary stacks.
- If the user wants to skip stack detection (e.g., in a context where it always fails), they can invoke the stack-specific workflow directly.
