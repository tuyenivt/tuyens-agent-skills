---
name: task-angular-implement
description: End-to-end Angular feature implementation - standalone components, signals, services, routing, RxJS, styling, a11y, tests.
agent: angular-engineer
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

### Step 3 - Gather

Feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints.

### Step 4 - Design

Use skill: `angular-component-patterns`. Propose component tree, file structure, routes. If routing is non-trivial (nested, lazy, guards), also Use skill: `angular-routing-patterns`. For Nx workspaces, also Use skill: `angular-nx-patterns` to place libraries and apply tag boundaries. Present for user approval before generating code.

### Step 5 - State

Use skill: `angular-state-patterns`. Classify state (local, shared, global, server, URL, form) and assign owners. Filters/sort/pagination/search default to route query params. State the URL contract: param schema, sync direction (form → URL, URL → fetch), debounce on URL writes, and cancellation strategy. (Component-level reactive state primitives live in `angular-signals-patterns`; load only if the design needs a `linkedSignal`, custom `resource`, or BehaviorSubject migration plan.)

### Step 6 - Data

Use skill: `angular-data-fetching` (primary - HttpClient, `resource()`/`httpResource()`, TanStack Query, Apollo, cache invalidation, optimistic updates, SSR transfer cache). Use `angular-service-patterns` for service shape, DI scope, functional interceptors. Use `angular-rxjs-patterns` only if RxJS-specific timing (retry, multicast, complex flattening) is in scope. **Real-time / WebSocket / SSE:** wrap the connection in a service exposing a signal (`toSignal(socket$, { initialValue: [] })`), keep reconnection logic in the service. **File export (CSV / XLSX):** generate via a util in a `type:util` lib; trigger via `Blob` + anchor download. **Charts / heavy widgets:** lazy via `@defer (on viewport)` - see Step 7. Skip Step 6 entirely for pure-UI features.

### Step 7 - Components

Generate standalone OnPush components with signals, typed DI, content projection, project styling (Use skill: `angular-styling-patterns`). Use `@defer` for heavy below-the-fold subtrees only when present. On SSR, guard browser APIs with `isPlatformBrowser` and hydrate via `TransferState`.

### Step 8 - Forms

Use skill: `angular-forms-patterns` (typed Reactive Forms, validators, FormArray, ControlValueAccessor, server validation surfacing). For multi-step wizards, state explicitly: one `FormGroup` per step, parent group aggregates, navigation gated on `step.valid`. Skip if the feature has no form.

### Step 9 - A11y

Use skill: `frontend-accessibility`. Audit generated components for WCAG 2.1 AA. Apply Angular-specific patterns: CDK `FocusTrap`/`LiveAnnouncer`/`FocusMonitor`, `NgOptimizedImage` alt, `host: {'aria-*': ...}`, `MatDialog` focus management.

### Step 10 - I18n (conditional)

When the feature has user-facing strings and the project ships in multiple locales, Use skill: `angular-i18n-patterns` for `$localize` / `i18n` attribute / ICU and `LOCALE_ID` wiring. Skip if single-locale.

### Step 11 - Tests

Use skill: `angular-testing-patterns`. Component, service, integration tests; flag critical paths for e2e.

### Step 12 - Validate

Run `ng build` + `ng test` + `ng lint`. For features touching user-facing surfaces, also run an `axe` scan against the new route (Playwright + `@axe-core/playwright` or `vitest-axe` in component tests). For features adding lazy chunks or new dependencies, check the `angular.json` bundle budget and report the delta. Present file list, component tree, test count, and bundle delta.

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

## Bundle Delta (if lazy chunks or new deps added)

- {chunk}: {+X KB gzip} (budget: {limit}; {within | exceeds})
```

## Self-Check

- [ ] Principles loaded; stack detected
- [ ] Requirements captured
- [ ] Component tree designed and approved by user; Nx library placement decided when workspace is Nx
- [ ] State classified and owned; URL state used for pagination/filters/search with explicit contract
- [ ] Data layer defined with loading/error/empty states, cache invalidation strategy stated; or skipped for pure UI
- [ ] Components are standalone, OnPush, signal-driven; SSR guards in place when applicable
- [ ] Forms use typed Reactive Forms with validation, or step skipped
- [ ] WCAG 2.1 AA audit passed
- [ ] i18n strategy applied when multi-locale, or step skipped
- [ ] Tests cover components, services, integration, and critical flows
- [ ] `ng build`, `ng test`, `ng lint` all pass; `axe` scan run on new user-facing routes; bundle delta reported when lazy chunks or new deps added

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
