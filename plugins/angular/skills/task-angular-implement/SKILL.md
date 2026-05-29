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

**STEP 1 - PRINCIPLES:** Use skill: `behavioral-principles`.

**STEP 2 - DETECT:** Use skill: `stack-detect`. Identify Angular version, SSR, styling, state library, test framework.

**STEP 3 - SPEC-AWARE (conditional):** If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, Use skill: `spec-aware-preamble`. Follow its mode contract; skip STEP 4 (GATHER) and STEP 5 (DESIGN) when `plan.md` is present. Never edit `spec.md`/`plan.md`/`tasks.md`.

**STEP 4 - GATHER:** Feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints.

**STEP 5 - DESIGN:** Use skill: `angular-component-patterns`. Propose component tree, file structure, routes. If routing is non-trivial (nested, lazy, guards), also Use skill: `angular-routing-patterns`. Present for user approval before generating code.

**STEP 6 - STATE:** Use skill: `angular-state-patterns` + `angular-signals-patterns`. Classify state (local, shared, global, server, URL, form) and assign owners. Filters/sort/pagination/search default to route query params. State the URL contract: param schema, sync direction (form -> URL, URL -> fetch), debounce on URL writes, and cancellation strategy.

**STEP 7 - DATA:** Use skill: `angular-service-patterns`. Service architecture, HTTP interceptors, loading/error/empty states, caching. Use `angular-rxjs-patterns` only if RxJS-specific timing (retry, multicast, complex flattening) is in scope. Skip entirely for pure-UI features.

**STEP 8 - COMPONENTS:** Generate standalone OnPush components with signals, typed DI, content projection, project styling (Use skill: `angular-styling-patterns`). Use `@defer` for heavy below-the-fold subtrees only when present. On SSR, guard browser APIs with `isPlatformBrowser` and hydrate via `TransferState`.

**STEP 9 - FORMS:** Use skill: `frontend-form-handling`. Reactive Forms with validation, error display, submission, dirty tracking. Skip if no form.

**STEP 10 - A11Y:** Use skill: `frontend-accessibility`. Audit generated components for WCAG 2.1 AA.

**STEP 11 - TESTS:** Use skill: `angular-testing-patterns`. Component, service, integration tests; flag critical paths for e2e.

**STEP 12 - VALIDATE:** Run `ng build` + `ng test` + `ng lint`. Present file list, component tree, and test count.

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
- [ ] Spec-aware mode resolved if a spec exists; STEPS 4-5 skipped if `plan.md` present
- [ ] Requirements captured or spec ingested
- [ ] Component tree designed and approved by user (skipped under spec mode)
- [ ] State classified and owned; URL state used for pagination/filters/search with explicit contract
- [ ] Data layer defined with loading/error/empty states, or skipped for pure UI
- [ ] Components are standalone, OnPush, signal-driven; SSR guards in place when applicable
- [ ] Forms use Reactive Forms with validation, or step skipped
- [ ] WCAG 2.1 AA audit passed
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
