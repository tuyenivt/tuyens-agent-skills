---
name: task-implement
description: Universal feature implementation entry point for new functionality requiring multiple coordinated layers (API + service + persistence + tests). Detects your stack and delegates to the appropriate workflow. Use when implementing a new endpoint, resource, domain aggregate, or cross-layer feature.
metadata:
  category: code
  tags: [feature, implementation, scaffold, stack-agnostic]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for this feature, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. The preamble decides between modes (`no-spec`, `spec-only`, `spec+plan`, `full-spec`); follow its contract - skip GATHER (and DESIGN, when `plan.md` is present) and treat the spec as the source of truth. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface conflicts as proposed amendments.

# Feature Implementation

## Purpose

Universal entry point for implementing new features that span multiple layers. Detects the project stack and delegates to the appropriate stack-specific workflow. Provides a comprehensive fallback workflow when no stack-specific skill exists.

**Not for:** Bug fixes (use `task-code-debug`), refactoring existing code (use `task-code-refactor`), single-file or isolated changes, feature discovery (use `task-spec-write`).

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

**Backend stacks:**

| Detected Stack              | Delegate to        |
| --------------------------- | ------------------ |
| Java / Spring Boot          | `task-spring-new`  |
| Kotlin / Spring Boot        | `task-kotlin-new`  |
| .NET / ASP.NET Core         | `task-dotnet-new`  |
| Python / FastAPI or Django  | `task-python-new`  |
| Ruby / Rails                | `task-rails-new`   |
| Node.js / NestJS or Express | `task-node-new`    |
| Go / Gin                    | `task-go-new`      |
| Rust / Axum                 | `task-rust-new`    |
| PHP / Laravel               | `task-laravel-new` |

**Frontend stacks:**

| Detected Stack         | Delegate to        |
| ---------------------- | ------------------ |
| React / Next.js / Vite | `task-react-new`   |
| Vue / Nuxt / Vite      | `task-vue-new`     |
| Angular                | `task-angular-new` |

**Fullstack projects:** If `Stack Type: fullstack` is detected, determine which side the feature belongs to based on user input. If the feature spans both (e.g., "add a new page with API endpoint"), delegate to the backend workflow for the API layer and the frontend workflow for the UI layer. If unclear, ask the user which side to focus on.

**Fullstack coordination (when the feature spans backend + frontend):**
1. Run DESIGN for both sides first - agree on the API contract (endpoints, request/response shapes, status codes) before either side begins implementation.
2. Implement backend first so the frontend can integrate against real endpoints.
3. If parallel development is needed, define the API contract explicitly and use mock data on the frontend until the backend is ready.
4. Include an integration test that exercises the full flow from UI action to database persistence.

If the detected stack does not match any of the above, proceed with the universal fallback below.

### Step 3 - Universal Fallback (Unknown Stack)

If no matching stack workflow exists, implement the feature using universal best practices. The fallback adapts based on the detected `Stack Type`.

#### Fallback for Backend or Unknown Stack Type

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

#### Fallback for Frontend Stack Type

**GATHER** - Confirm before proceeding:

- Feature name, user-facing behavior, and affected pages/routes
- Component hierarchy and data requirements
- State management needs (local, shared, global, URL)
- Data sources: API endpoints to consume, loading/error states
- Form inputs and validation rules (if applicable)
- Accessibility requirements

**DESIGN** - Propose and wait for explicit approval before generating any code:

- Component tree with responsibility annotations
- Routing changes (new pages, layouts, guards)
- State management approach (local state, store, URL params)
- Data fetching strategy (hooks/composables, server components, caching)
- Form handling approach (validation library, submission flow)

**IMPLEMENT (in order):**

1. **Routing**: new routes, layouts, or navigation entries
2. **Components**: page components, feature components, shared UI components - each with single responsibility
3. **State management**: local state first, lift or use stores only when sharing is required
4. **Data fetching**: loading states, error states, caching, retry logic
5. **Forms** (if applicable): validation, submission, error display
6. **Accessibility**: semantic HTML, ARIA attributes, keyboard navigation, focus management
7. **Tests**: component tests for rendering and interaction; integration tests for data flows; E2E for critical user flows

**VALIDATE:**

- Run the project's test suite and confirm all pass
- Confirm the implementation matches the approved design
- Verify accessibility (no missing labels, keyboard navigable, correct heading hierarchy)

**Output:**

```markdown
## Generated Files

- [ ] Route/Page: [path]
- [ ] Components: [paths]
- [ ] State/Store: [path] (if applicable)
- [ ] Hooks/Composables: [path] (if applicable)
- [ ] Tests: [paths]

## Routes

| Path | Component | Guard | Description |
| ---- | --------- | ----- | ----------- |
| ...  | ...       | ...   | ...         |

## Tests

- Component tests: {count}
- Integration tests: {count}
- E2E tests: {count}
```

## Self-Check

- [ ] Stack detected and stack-specific workflow invoked (or fallback applied with explanation)
- [ ] Requirements confirmed and design approved before any code generated
- [ ] **Backend/fullstack**: All layers implemented: migration, model, service, controller, DTOs, tests
- [ ] **Backend/fullstack**: No data layer entities exposed directly in API responses - DTOs/response structs used
- [ ] **Backend/fullstack**: Every endpoint has explicit auth; list endpoints are paginated
- [ ] **Backend/fullstack**: Migration is safe: no destructive column changes without expand-contract sequencing
- [ ] **Frontend/fullstack**: Components have single responsibility; no business logic in components
- [ ] **Frontend/fullstack**: State management approach is appropriate (local first, stores only when needed)
- [ ] **Frontend/fullstack**: Accessibility verified: semantic HTML, keyboard navigable, ARIA labels
- [ ] Tests pass; file list, route/endpoint table, and test count presented

## Avoid

- Generating code before the design is explicitly approved by the user
- Skipping the data layer (migration, indexes) and jumping straight to business logic
- Exposing ORM entities directly in API responses
- Leaving endpoints without explicit auth configuration
- Implementing features without tests

## Notes

- This skill is a dispatcher. The depth and quality of the output depends on the delegated stack workflow.
- For polyglot monorepos or fullstack projects, detect the primary stack and note any secondary stacks. Use `Stack Type` to determine whether to delegate to backend, frontend, or both workflows.
- If the user wants to skip stack detection (e.g., in a context where it always fails), they can invoke the stack-specific workflow directly.
