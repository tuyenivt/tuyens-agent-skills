---
name: task-angular-implement
description: End-to-end Angular feature implementation: standalone components, signals, services, routing, RxJS, styling, a11y, tests.
metadata:
  category: frontend
  tags: [angular, typescript, standalone, signals, rxjs, feature, implementation, workflow, components, testing]
  type: workflow
user-invocable: true
---

# Implement Angular Feature

## When to Use

- New Angular feature end-to-end (components, services, state, routing, tests)
- New user-facing flow with API integration and form handling
- Complete page or feature module needing coordinated generation across layers

**Not for**: single-component changes, bug fixes (use `task-angular-debug`), or refactors without new functionality.

**Partial input**: if only a feature name is given, ask for components, data sources, interactions, routing, and form needs before DESIGN.

## Workflow

STEP 1 - PRINCIPLES: Use skill: `behavioral-principles`. Governs every step that follows.

STEP 2 - DETECT: Use skill: `stack-detect`. Identify Angular version, SSR (Universal), styling (Material, Tailwind), state library (NgRx, signals), test framework.

STEP 3 - SPEC-AWARE (conditional): If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, Use skill: `spec-aware-preamble`. Follow its mode contract; skip GATHER (and DESIGN when `plan.md` is present). Never edit `spec.md`, `plan.md`, or `tasks.md`; surface conflicts as proposed amendments.

STEP 4 - GATHER: Feature name, user stories, components, data sources (API endpoints), interactions, routing, form inputs, a11y constraints. Skip if STEP 3 ingested a spec.

STEP 5 - DESIGN: Use skill: `angular-component-patterns` + `angular-routing-patterns`. Propose component tree, standalone vs NgModule (default standalone), file structure, routes. Present for user approval before generating code.

STEP 6 - STATE: Use skill: `angular-state-patterns` + `angular-signals-patterns` + `frontend-state-management`. Classify state (local, shared, global, server, URL, form) and assign owners. Pagination, filters, sort, and search default to route query params for shareability.

STEP 7 - DATA: Use skill: `angular-service-patterns` + `angular-rxjs-patterns` + `frontend-api-integration`. Service architecture, HTTP interceptors, loading/error/empty states, caching. Skip for pure-UI features with no API.

STEP 8 - COMPONENTS: Use skill: `angular-component-patterns` + `angular-styling-patterns`. Generate standalone components with OnPush, signals, typed DI, content projection, project styling. Use `@defer` for heavy below-the-fold subtrees. On SSR, guard browser APIs with `isPlatformBrowser` and hydrate via `TransferState`.

STEP 9 - FORMS: Use skill: `frontend-form-handling`. Reactive Forms with validation, error display, submission, dirty tracking. Skip if no form or form-like inputs.

STEP 10 - A11Y: Use skill: `frontend-accessibility`. Audit generated components for WCAG 2.1 AA.

STEP 11 - TESTS: Use skill: `angular-testing-patterns` + `frontend-testing-patterns`. Component, service, integration tests; flag critical paths for e2e.

STEP 12 - VALIDATE: Run `ng build` + `ng test` + `ng lint`. Present file list, component tree, and test count.

## Output Format

```markdown
## Generated Files

### Components

- [ ] `{path}/{component-name}.component.ts`
- [ ] `{path}/{component-name}.component.html`
- [ ] `{path}/{component-name}.component.spec.ts`

### Services

- [ ] `{path}/{service-name}.service.ts`
- [ ] `{path}/{service-name}.service.spec.ts`

### Types

- [ ] `{path}/{model-name}.model.ts`

### Routing

- [ ] `{path}/{feature-name}.routes.ts`

## Component Tree

{ComponentName} (standalone)
├── {ChildA} (standalone)
│ └── {ChildB} (standalone)
└── {ChildC} (standalone)

## State Map

| State        | Category   | Owner       | Mechanism                               |
| ------------ | ---------- | ----------- | --------------------------------------- |
| {state name} | {category} | {component} | {signal / NgRx / service / queryParams} |

## Tests

- Component tests: {count}
- Service tests: {count}
- Integration tests: {count}
- E2E candidates: {list of critical paths}
```

## Self-Check

- [ ] Behavioral principles loaded (STEP 1)
- [ ] Stack detected: Angular version, SSR, styling, state lib, test framework (STEP 2)
- [ ] Spec-aware mode resolved if a spec exists (STEP 3)
- [ ] Requirements captured or spec ingested (STEP 4)
- [ ] Component tree designed and approved by user (STEP 5)
- [ ] State classified and owned; URL state used for pagination/filters/search (STEP 6)
- [ ] Data layer defined with loading/error/empty states, or skipped for pure UI (STEP 7)
- [ ] Components are standalone, OnPush, signal-driven, with `@defer` and SSR guards where applicable (STEP 8)
- [ ] Forms use Reactive Forms with validation, or step skipped (STEP 9)
- [ ] WCAG 2.1 AA audit passed (STEP 10)
- [ ] Tests cover components, services, integration, and critical flows (STEP 11)
- [ ] `ng build`, `ng test`, `ng lint` all pass (STEP 12)

## Avoid

- `any`, unjustified type assertions, or suppressed TS errors
- NgModules for new code (extend existing NgModule projects, but default to standalone)
- BehaviorSubject for component-local state - use signals
- Default change detection - always OnPush
- Manual subscriptions without `takeUntilDestroyed` or `async` pipe
- Direct DOM manipulation in place of Angular templating
- Component-signal storage of pagination, filter, or search state - belongs in route query params
- Skipping loading, error, or empty states on data components
- Tests asserting internal state or method calls
- Generating code before the design is approved
