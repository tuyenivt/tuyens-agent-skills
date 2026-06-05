---
name: task-angular-implement
description: End-to-end Angular feature implementation - standalone components, signals, services, routing, RxJS, styling, a11y, tests.
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
- Complete page or feature module needing coordinated generation

**Not for:** single-component changes, bug fixes (use `task-angular-debug`), refactors without new functionality.

If only a feature name is given, ask for components, data sources, interactions, routing, and form needs before DESIGN.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Identify Angular version, SSR, styling, state library, test framework.

### Step 3 - Spec-Aware (conditional)

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, Use skill: `spec-aware-preamble`. Follow its mode contract; skip Step 4 (Gather) and Step 5 (Design) when `plan.md` is present. Never edit `spec.md`/`plan.md`/`tasks.md`.

### Step 4 - Gather

Feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints.

### Step 5 - Design

Use skill: `angular-component-patterns`. Propose component tree, file structure, routes. If routing is non-trivial (nested, lazy, guards), also Use skill: `angular-routing-patterns`. For Nx workspaces, also Use skill: `angular-nx-patterns` to place libraries and apply tag boundaries. Present for user approval before generating code.

### Step 6 - State

Use skill: `angular-state-patterns` + `angular-signals-patterns`. Classify state (local, shared, global, server, URL, form) and assign owners. Filters/sort/pagination/search default to route query params. State the URL contract: param schema, sync direction (form -> URL, URL -> fetch), debounce on URL writes, and cancellation strategy.

### Step 7 - Data

Use skill: `angular-data-fetching` (primary - HttpClient, `resource()`/`httpResource()`, TanStack Query for Angular, Apollo, cache invalidation, optimistic updates, SSR transfer cache). Use `angular-service-patterns` for service shape, DI scope, functional interceptors. Use `angular-rxjs-patterns` only if RxJS-specific timing (retry, multicast, complex flattening) is in scope. Skip entirely for pure-UI features.

### Step 8 - Components

Generate standalone OnPush components with signals, typed DI, content projection, project styling (Use skill: `angular-styling-patterns`). Use `@defer` for heavy below-the-fold subtrees only when present. On SSR, guard browser APIs with `isPlatformBrowser` and hydrate via `TransferState`.

### Step 9 - Forms

Use skill: `angular-forms-patterns` (typed Reactive Forms, validators, FormArray, ControlValueAccessor, server validation surfacing). Fall back to `frontend-form-handling` only for non-Reactive patterns. Skip if no form.

### Step 10 - A11y

Use skill: `frontend-accessibility`. Audit generated components for WCAG 2.1 AA. Apply Angular-specific patterns: CDK `FocusTrap`/`LiveAnnouncer`/`FocusMonitor`, `NgOptimizedImage` alt, `host: {'aria-*': ...}`, `MatDialog` focus management.

### Step 11 - I18n (conditional)

When the feature has user-facing strings and the project ships in multiple locales, Use skill: `angular-i18n-patterns` for `$localize` / `i18n` attribute / ICU and `LOCALE_ID` wiring. Skip if single-locale.

### Step 12 - Tests

Use skill: `angular-testing-patterns`. Component, service, integration tests; flag critical paths for e2e.

### Step 13 - Validate

Run `ng build` + `ng test` + `ng lint`. Present file list, component tree, and test count.

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

{ComponentName}
├── {ChildA}
│   └── {ChildB}
└── {ChildC}

## State Map

| State | Category | Owner | Mechanism |
| ----- | -------- | ----- | --------- |
| {state} | {Local/Shared/Server/URL/Form} | {component/service} | {signal/computed/queryParams/HTTP/ReactiveForm/NgRx} |

## URL Contract (if URL state used)

| Param | Type | Default | Owner | Sync direction |
| ----- | ---- | ------- | ----- | -------------- |
| {q}   | string | "" | {component} | form -> URL (debounced 300ms); URL -> fetch (switchMap cancel) |

## Tests

- Component tests: {count}
- Service tests: {count}
- Integration tests: {count}
- E2E candidates: {list of critical paths}
```

## Self-Check

- [ ] Principles loaded; stack detected
- [ ] Spec-aware mode resolved if a spec exists; Steps 4-5 skipped if `plan.md` present
- [ ] Requirements captured or spec ingested
- [ ] Component tree designed and approved by user (skipped under spec mode); Nx library placement decided when workspace is Nx
- [ ] State classified and owned; URL state used for pagination/filters/search with explicit contract
- [ ] Data layer defined with loading/error/empty states, cache invalidation strategy stated; or skipped for pure UI
- [ ] Components are standalone, OnPush, signal-driven; SSR guards in place when applicable
- [ ] Forms use typed Reactive Forms with validation, or step skipped
- [ ] WCAG 2.1 AA audit passed
- [ ] i18n strategy applied when multi-locale, or step skipped
- [ ] Tests cover components, services, integration, and critical flows
- [ ] `ng build`, `ng test`, `ng lint` all pass

## Avoid

- `any`, unjustified type assertions, or suppressed TS errors
- NgModules for new code (extend existing NgModule projects only)
- BehaviorSubject for component-local state - use signals
- Default change detection - always OnPush
- Manual subscriptions without `takeUntilDestroyed` or `async` pipe
- Direct DOM manipulation in place of Angular templating
- Storing pagination/filter/search state in component signals - belongs in route query params
- Skipping loading, error, or empty states on data components
- Tests asserting internal state or method calls
- Generating code before the design is approved
