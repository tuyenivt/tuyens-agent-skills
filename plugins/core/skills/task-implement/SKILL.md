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

Detects the project stack and delegates to the matching implementation workflow. Falls back to a universal GATHER -> DESIGN -> IMPLEMENT -> VALIDATE protocol when no stack workflow matches.

## When to Use

- New features spanning multiple layers (API, service, persistence, tests)
- New routes, pages, or components for a frontend stack

**Not for:** bug fixes, refactors, isolated single-file edits.

## Inputs

| Field               | Required | Notes                                                      |
| ------------------- | -------- | ---------------------------------------------------------- |
| Feature description | Yes      | User story, ticket, or plain description                   |
| Affected layers     | No       | API, DB, jobs, UI, etc.                                    |
| Constraints         | No       | Auth, performance, migration sensitivity                   |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Detect Stack

Use skill: `stack-detect`.

### Step 3 - Delegate to Stack Workflow

| Detected stack              | Delegate to              |
| --------------------------- | ------------------------ |
| Java / Spring Boot          | `task-spring-implement`  |
| Python / FastAPI or Django  | `task-python-implement`  |
| Ruby / Rails                | `task-rails-implement`   |
| Node.js / NestJS or Express | `task-node-implement`    |
| Go / Gin                    | `task-go-implement`      |
| React / Next.js             | `task-react-implement`   |

A row matches only when the detected framework matches it (Python / Flask does not match Python / FastAPI or Django - use the fallback); dispatch keys on the detection's primary `Language`/`Framework` pair (the React / Next.js row keys on the detected framework family - React or Next.js - whatever the language). A detected frontend stack other than React (Vue, Angular, Svelte) has no dedicated workflow - run Step 4, whose IMPLEMENT phase covers the frontend layers. When no row matches at all, note it in one line (`No stack implement workflow for <stack> - universal fallback.`) and run Step 4.

**Fullstack (`Stack Type: fullstack`):** when the primary pair matches a single row whose workflow owns both sides (a meta-framework spanning server and UI - React / Next.js is the only such row), delegate the whole feature to it - announce in one line (`Delegating to task-react-implement.`), pass the feature description and any Inputs in hand, and stop, exactly as a single-stack match. The split below applies only when backend and frontend belong to different stacks. On a split, decide which side(s) the feature needs from the user's description, then delegate the backend side to the table workflow first, announcing it (`Delegating backend to task-go-implement.`) - its DESIGN phase authors the API contract, which the frontend side then treats as fixed input; the frontend may start as soon as the contract is fixed, full backend delivery need not precede it. Build the frontend side via the Step 4 frontend path. If parallel work is required, fix the API contract up front and mock data on the frontend until the backend lands. Include an integration test from UI action to DB persistence, built and reported on the frontend side (its E2E tier). Ask the user when the split is ambiguous.

On a single-stack match: announce in one line (`Delegating to task-spring-implement.` - substitute the target name; the announcement is the router's only output, the detection block stays internal), then delegate, passing the Inputs-table fields as in hand (Feature description / Affected layers / Constraints) - do not run GATHER first; the stack workflow owns elicitation. Stop; skip Step 4. A fullstack detection follows the fullstack rule above instead. If the matched workflow's plugin is not installed (skill does not resolve), say so and run Step 4 instead.

### Step 4 - Universal Fallback (no matching stack workflow)

Runs when the stack is unknown, unsupported by any table row, or the matched plugin is not installed. The fallback adapts to the detected `Stack Type`. Phases are: GATHER -> DESIGN -> IMPLEMENT -> VALIDATE.

**GATHER** - resolve from the feature description and the codebase; ask the user only for items that remain unknown and would change the design (when Step 4 owns both sides, cover both lists; on a split, the frontend list only - the delegate owns the backend list):

- *Backend / unknown:* feature name and operations; entity relationships and validation; external dependencies; auth per endpoint (guard, public vs protected, ownership scope); async/job needs.
- *Frontend:* feature behavior and affected pages/routes; component hierarchy and data needs; state scope (local/shared/global/URL); API endpoints to consume; form inputs and validation; accessibility requirements.

**DESIGN** - propose and wait for explicit approval before generating code:

- *Backend:* schema changes (entities, fields, indexes for FK and filter columns); service / business logic boundaries and transactions; API contract (method, URI, request/response shapes, status codes); error model.
- *Frontend:* component tree with responsibilities; routing changes (pages, layouts, guards); state strategy (local, store, URL); data-fetching strategy (hooks, server components, caching); form handling (validation library, submission flow).

**IMPLEMENT** in order. Load the atomic skill named at each applicable step; Use skill: `backend-coding-standards` throughout backend work:

- *Backend:* (1) data layer - migration with indexes; never modify columns destructively; Use skill: `backend-db-migration`. (2) business logic - constructor injection; no logic in controllers; Use skill: `backend-idempotency` for side-effecting external calls (payments, notifications, provisioning). (3) API layer - never expose data-layer entities directly; map to DTOs; Use skill: `backend-api-guidelines`. (4) auth - explicit per endpoint, no implicit defaults. (5) background jobs if applicable; Use skill: `backend-idempotency` for retried or externally-triggered work. (6) tests - unit (logic), integration (DB), API (routing, serialization, auth).
- *Frontend:* (1) routing - new routes, layouts, navigation. (2) components - single responsibility. (3) state - local first, lift or store only when sharing requires it; Use skill: `frontend-state-management`. (4) data fetching - loading, error, caching, retry; Use skill: `frontend-api-integration`. (5) forms - validation, submission, errors; Use skill: `frontend-form-handling`. (6) accessibility - semantic HTML, ARIA, keyboard, focus; Use skill: `frontend-accessibility`. (7) tests - component, integration, E2E for critical flows; Use skill: `frontend-testing-patterns`.

**VALIDATE:**

- Run the project test suite; all pass. If no runner is configured or the suite cannot run, state that in the output with the command(s) attempted - do not claim validation.
- Implementation matches the approved design.
- *Backend:* list endpoints paginated (`N/A - no list endpoints` when none were added or changed).
- *Frontend:* keyboard navigable, labels present, correct heading hierarchy.

## Output Format

When dispatched (Step 3): the stack workflow owns the output. On a fullstack split (backend and frontend in different stacks), the stack workflow reports the backend side; the Step 4 output below covers only the frontend side.

When fallback runs (Step 4), emit only the block(s) matching the Stack Type (on a split, the frontend block only - the delegate reports the backend), trimming the combined headings to the side emitted. The file checklist is a floor, not an enum - append rows for artifacts outside the fixed slots (policies, jobs, routes), mark modified files `(updated)`, and emit boxes checked for what was generated. The Tests line carries one count per tier the IMPLEMENT test step defines for the side built (backend: Unit / Integration / API; frontend: Component / Integration / E2E):

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

- [tier]: {count}  [tier]: {count}  [tier]: {count}

## Validation

- [test command]: [pass/fail counts, or the commands attempted when no runner ran]  Design match: [yes/no]  [side-specific checks, or `N/A - <reason>`]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: `stack-detect` ran
- [ ] Step 3: single-stack or meta-framework match -> delegated (feature context forwarded) and stopped, Step 4 skipped; split -> backend delegated first for the contract, frontend built via Step 4
- [ ] Step 4 (backend/fullstack): GATHER confirmed; DESIGN approved before code; all layers (migration, model, service, controller, DTOs, tests) present; no entities in API responses; explicit auth per endpoint; list endpoints paginated; migrations non-destructive (N/A on a split - the delegate owns the backend layers)
- [ ] Step 4 (frontend/fullstack): GATHER confirmed; DESIGN approved before code; components single-responsibility; state scope appropriate; accessibility verified
- [ ] Tests pass; file list, route/endpoint table, and test counts presented

## Avoid

- Generating code before the user approves the design
- Skipping the data layer (migration, indexes) and jumping to business logic
- Exposing ORM entities directly in API responses
- Endpoints without explicit auth configuration
- Implementing features without tests
