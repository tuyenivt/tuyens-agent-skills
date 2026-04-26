---
name: task-angular-new
description: End-to-end Angular feature implementation workflow - standalone components, signals, services, routing, RxJS, styling, accessibility, and tests for Angular 21+ projects.
metadata:
  category: frontend
  tags: [angular, typescript, standalone, signals, rxjs, feature, implementation, workflow, components, testing]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for this feature, load `Use skill: spec-aware-preamble` immediately after `behavioral-principles` and `stack-detect`. The preamble decides between modes (`no-spec`, `spec-only`, `spec+plan`, `full-spec`); follow its contract - skip GATHER (and DESIGN, when `plan.md` is present) and treat the spec as the source of truth. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow; surface conflicts as proposed amendments.

# Implement Angular Feature

## When to Use

- Implementing a new Angular feature end-to-end (components, services, state, routing, tests)
- Scaffolding a complete page or feature module with production-ready patterns
- Adding a new user-facing flow with API integration and form handling
- Any daily frontend coding task that requires coordinated generation of multiple Angular layers

**Not for**: Single-component changes, bug fixes (use `task-angular-debug`), or refactoring without new functionality.

**Edge cases**:

- **Partial input**: If the user provides only a feature name without details, ask for components needed, data requirements, user interactions, and routing before proceeding to design.
- **No API**: If the feature is purely UI (e.g., static page, settings toggle), skip data fetching and API integration steps; generate only components, state, styling, and tests.
- **Existing components**: If the user references components that already exist, read them and extend or compose with them rather than creating duplicates.
- **SSR project**: If stack-detect identifies Angular SSR (Angular Universal), apply server-side rendering considerations: use `isPlatformBrowser` for browser-only APIs, `TransferState` for state hydration, and avoid direct DOM manipulation.
- **No forms**: If the feature has no form inputs, skip the form handling step entirely.
- **Legacy NgModules**: If the project uses NgModules instead of standalone components, adapt patterns accordingly but recommend migration to standalone.
- **Heavy component trees**: If the feature includes lists with complex child components (e.g., product cards with images), use `@defer` with `@placeholder` and `@loading` blocks for lazy rendering below the fold.

## Rules

- TypeScript strict mode - no `any` types, no type assertions without justification
- Standalone components by default - no NgModules for new code unless the existing project requires it
- Signals for state management in new code - avoid BehaviorSubject for component-local state
- OnPush change detection on every component
- Services must use `providedIn: 'root'` for singletons or be scoped to component providers
- Components must have a clear single responsibility
- Colocate tests with components (`component-name.component.spec.ts` next to `component-name.component.ts`)
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code
- Run typecheck and lint after all files are generated

## Workflow

STEP 1 - DETECT: Use skill: `stack-detect` to determine Angular version, SSR configuration, styling approach (Angular Material, Tailwind CSS), state management library (NgRx, signals), and test framework.

STEP 2 - GATHER: Requirements - feature name, user stories, components needed, data sources (API endpoints), user interactions, routing needs, form inputs, accessibility requirements.

STEP 3 - DESIGN: Use skill: `angular-component-patterns` + `angular-routing-patterns`. Propose component tree with responsibility breakdown, standalone vs NgModule approach, file structure, and routing. Present for user approval before generating code.

STEP 4 - STATE: Use skill: `angular-state-patterns` + `angular-signals-patterns` + `frontend-state-management`. Identify state categories (local, shared, global, server, URL, form) and assign ownership to components or services. Filters, pagination, sort, and search parameters should default to URL state (route query params) for bookmarkability and shareability.

STEP 5 - DATA: Use skill: `angular-service-patterns` + `angular-rxjs-patterns` + `frontend-api-integration`. Define data fetching strategy - service architecture, HTTP interceptors, loading/error states, caching approach.

STEP 6 - COMPONENTS: Use skill: `angular-component-patterns` + `angular-styling-patterns`. Generate components with signals, OnPush change detection, proper DI, content projection where appropriate, and styling following the project's approach. Use `@defer` for heavy child components that benefit from lazy rendering.

STEP 7 - FORMS: Use skill: `frontend-form-handling` (if feature has forms or form-like inputs such as search, filters, or toggles). Implement Angular Reactive Forms with validation, error display, submission handling, and dirty tracking. For search inputs, add debouncing. For filters, add reset/apply patterns.

STEP 8 - A11Y: Use skill: `frontend-accessibility`. Audit generated components for WCAG 2.1 AA compliance - semantic HTML, keyboard navigation, ARIA attributes, focus management.

STEP 9 - TESTS: Use skill: `angular-testing-patterns` + `frontend-testing-patterns`. Generate component tests (Angular Testing Library), service tests, integration tests, and identify critical paths for e2e.

STEP 10 - VALIDATE: Run `ng build` + `ng test` + `ng lint`. Present file list, component tree, and test count.

## Self-Check

- [ ] Stack detected and Angular version identified (STEP 1)
- [ ] Requirements gathered - components, data sources, interactions, routing documented (STEP 2)
- [ ] Component tree designed with standalone components and approved by user (STEP 3)
- [ ] State management categorized and assigned - signals for local, NgRx/services for shared, route query params for pagination/filters/search (STEP 4)
- [ ] Data fetching uses services with HttpClient, interceptors configured, loading/error/empty states handled (STEP 5)
- [ ] Components use OnPush change detection, signals, proper DI, @defer where appropriate, and project styling approach (STEP 6)
- [ ] Forms and form-like inputs (search, filters) use Reactive Forms with validation, debouncing, and reset patterns if applicable (STEP 7)
- [ ] Accessibility audit passed - semantic HTML, keyboard accessible, ARIA attributes correct (STEP 8)
- [ ] Tests cover components, services, integration, and critical user flows (STEP 9)
- [ ] Angular builds with no errors; lint passes; tests pass (STEP 10)

## Output Format

Present a checklist of generated files:

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

## Avoid

- Using `any` type or suppressing TypeScript errors
- NgModules for new standalone components
- BehaviorSubject for simple component-local state (use signals)
- Default change detection strategy (always use OnPush)
- Manual subscription management without `takeUntilDestroyed` or `async` pipe
- Direct DOM manipulation instead of Angular templating
- Skipping loading, error, or empty states on data-fetching components
- Storing pagination, filter, or search state in component signals when it belongs in route query params
- Tests that assert implementation details (internal state, method calls)
- Generating code before the design is approved
