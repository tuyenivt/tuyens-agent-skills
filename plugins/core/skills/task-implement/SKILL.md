---
name: task-implement
description: Feature implementation entry point: scaffolds API, service, persistence, tests across layers. Detects stack and delegates to stack workflow.
metadata:
  category: code
  tags: [feature, implementation, scaffold, stack-agnostic]
  type: workflow
user-invocable: true
---

# Feature Implementation (Router)

Detects the project stack and delegates to the matching implementation workflow. Falls back to a universal GATHER -> DESIGN -> IMPLEMENT -> VALIDATE protocol for unknown stacks.

## When to Use

- New features spanning multiple layers (API, service, persistence, tests)
- New routes, pages, or components for a frontend stack

**Not for:** bug fixes (`task-code-debug`), refactors (`task-code-refactor`), isolated single-file edits, spec authoring (`task-spec-write`).

## Inputs

| Field               | Required | Notes                                                      |
| ------------------- | -------- | ---------------------------------------------------------- |
| Feature description | Yes      | User story, ticket, or plain description                   |
| Affected layers     | No       | API, DB, jobs, UI, etc.                                    |
| Constraints         | No       | Auth, performance, migration sensitivity                   |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

**Spec-aware mode:** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after `behavioral-principles` and `stack-detect`. The preamble selects mode (`no-spec`, `spec-only`, `spec+plan`, `full-spec`) and decides which fallback phases to skip. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface conflicts as proposed amendments.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Delegate to Stack Workflow

**Backend:**

| Detected stack              | Delegate to              |
| --------------------------- | ------------------------ |
| Java / Spring Boot          | `task-spring-implement`  |
| Kotlin / Spring Boot        | `task-kotlin-implement`  |
| .NET / ASP.NET Core         | `task-dotnet-implement`  |
| Python / FastAPI or Django  | `task-python-implement`  |
| Ruby / Rails                | `task-rails-implement`   |
| Node.js / NestJS or Express | `task-node-implement`    |
| Go / Gin                    | `task-go-implement`      |
| Rust / Axum                 | `task-rust-implement`    |
| PHP / Laravel               | `task-laravel-implement` |

**Frontend:**

| Detected stack         | Delegate to              |
| ---------------------- | ------------------------ |
| React / Next.js / Vite | `task-react-implement`   |
| Vue / Nuxt / Vite      | `task-vue-implement`     |
| Angular                | `task-angular-implement` |

**Fullstack (`Stack Type: fullstack`):** decide which side the feature belongs to from the user's description. If it spans both, delegate backend first for the API contract, then frontend; if parallel work is required, fix the API contract up front and mock data on the frontend until the backend lands. Include an integration test from UI action to DB persistence. Ask the user when the split is ambiguous.

On match: delegate, stop. Skip Step 4.

### Step 4 - Universal Fallback (unknown stack only)

The fallback adapts to the detected `Stack Type`. Phases are: GATHER -> DESIGN -> IMPLEMENT -> VALIDATE.

**GATHER** - confirm before proceeding:

- *Backend / unknown:* feature name and operations; entity relationships and validation; external dependencies; auth per endpoint (public vs protected); async/job needs.
- *Frontend:* feature behavior and affected pages/routes; component hierarchy and data needs; state scope (local/shared/global/URL); API endpoints to consume; form inputs and validation; accessibility requirements.

**DESIGN** - propose and wait for explicit approval before generating code:

- *Backend:* schema changes (entities, fields, indexes for FK and filter columns); service / business logic boundaries and transactions; API contract (method, URI, request/response shapes, status codes); error model.
- *Frontend:* component tree with responsibilities; routing changes (pages, layouts, guards); state strategy (local, store, URL); data-fetching strategy (hooks, server components, caching); form handling (validation library, submission flow).

**IMPLEMENT** in order:

- *Backend:* (1) data layer - migration with indexes; never modify columns destructively. (2) business logic - constructor injection; no logic in controllers. (3) API layer - never expose data-layer entities directly; map to DTOs. (4) auth - explicit per endpoint, no implicit defaults. (5) background jobs if applicable. (6) tests - unit (logic), integration (DB), API (routing, serialization, auth).
- *Frontend:* (1) routing - new routes, layouts, navigation. (2) components - single responsibility. (3) state - local first, lift or store only when sharing requires it. (4) data fetching - loading, error, caching, retry. (5) forms - validation, submission, errors. (6) accessibility - semantic HTML, ARIA, keyboard, focus. (7) tests - component, integration, E2E for critical flows.

**VALIDATE:**

- Run the project test suite; all pass.
- Implementation matches the approved design.
- *Backend:* list endpoints paginated.
- *Frontend:* keyboard navigable, labels present, correct heading hierarchy.

## Output Format

When dispatched (Step 3): the stack workflow owns the output.

When fallback runs (Step 4), output adapts to Stack Type:

```markdown
## Generated Files

[Backend]
- [ ] Migration: [path]
- [ ] Model/Entity: [path]
- [ ] Service: [path]
- [ ] Controller/Handler: [path]
- [ ] DTO/Response: [path]
- [ ] Unit tests / Integration tests: [paths]

[Frontend]
- [ ] Route/Page: [path]
- [ ] Components: [paths]
- [ ] State/Store: [path] (if applicable)
- [ ] Hooks/Composables: [path] (if applicable)
- [ ] Tests: [paths]

## Endpoints (backend) / Routes (frontend)

| Method/Path | Handler/Component | Auth/Guard | Description |
| ----------- | ----------------- | ---------- | ----------- |

## Tests

- Unit: {count}  Integration: {count}  E2E: {count}
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded; spec-aware preamble loaded if applicable
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: stack matched -> dispatched and stopped; Step 4 skipped
- [ ] Step 4 (backend/fullstack): GATHER confirmed; DESIGN approved before code; all layers (migration, model, service, controller, DTOs, tests) present; no entities in API responses; explicit auth per endpoint; list endpoints paginated; migrations non-destructive
- [ ] Step 4 (frontend/fullstack): GATHER confirmed; DESIGN approved before code; components single-responsibility; state scope appropriate; accessibility verified
- [ ] Tests pass; file list, route/endpoint table, and test counts presented

## Avoid

- Generating code before the user approves the design
- Skipping the data layer (migration, indexes) and jumping to business logic
- Exposing ORM entities directly in API responses
- Endpoints without explicit auth configuration
- Implementing features without tests
