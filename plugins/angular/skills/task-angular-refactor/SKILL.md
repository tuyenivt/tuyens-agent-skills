---
name: task-angular-refactor
description: Angular refactor planning for god components, prop drilling, RxJS subscription leaks, BehaviorSubject-to-signal migration, Default change-detection migration, fat services, scattered state, missing functional guard / interceptor migration, untyped inputs, accessibility gaps, inline business logic in templates. Produces a step-by-step sequence of independently-committable refactoring steps with a test coverage gate. Stack-specific override of task-code-refactor for Angular.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Angular Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Angular target (component, service, guard, interceptor, route configuration, NgRx store / signal store). Identifies Angular-specific smells (god component, prop drilling, BehaviorSubject for component-local state, Default change detection, manual `.subscribe()` without `takeUntilDestroyed`, fat service, conditional rendering ladder, scattered state, class-based guard / interceptor still in use, NgModule for new code, inline business logic in template, untyped inputs) and proposes independently-committable refactoring steps with test gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Angular.

## When to Use

- Angular code-smell identification and resolution
- Angular technical-debt reduction with a concrete plan
- Safe refactoring of a component / service / guard / interceptor / route configuration
- Pre-merge "this PR grew the god-component / subscription-leak problem - what's the cleanup?"
- Migrating BehaviorSubject to signals on a single component (when explicitly requested)
- Migrating NgModule to standalone (when explicitly requested)
- Migrating Default change detection to OnPush + signals (when explicitly requested)

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-angular-new`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-angular-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                                                                              |
| --------------------- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, module, or route to refactor (e.g., `src/app/orders/order-list.component.ts`, `src/app/auth/auth.service.ts`, `src/app/auth/auth.guard.ts`, `src/app/orders/orders.routes.ts`)                    |
| Goal                  | Yes         | What the refactoring should achieve (e.g., migrate `BehaviorSubject` to signals, replace manual `.subscribe()` with `takeUntilDestroyed`, split `Dashboard` god component, kill prop drilling, NgModule → standalone) |
| Test coverage status  | Recommended | Whether test coverage exists for the target area                                                                                                                                                         |
| Shared/public surface | Recommended | Whether the target is used across feature / route / app boundaries                                                                                                                                       |

## Workflow

### Step 1 - Confirm Stack and Detect Configuration

Use skill: `stack-detect` to confirm Angular. If invoked as a subagent of an Angular-aware parent, accept the pre-confirmed stack. If not Angular, stop and tell the user to invoke `/task-code-refactor` instead.

Detect: Angular major version, change detection mode (zone.js / zoneless), SSR enabled. Record `Angular: <version>`, `Change detection: zone.js | zoneless`, `SSR: enabled | disabled` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target component / service / guard / interceptor / module top-to-bottom; note line count, change-detection mode, signal vs RxJS state, input/output declarations, conditional rendering depth, subscriptions, lifecycle hook usage, external collaborators (`HttpClient`, NgRx store, `Sentry.captureException`, `Router.navigate`)
2. Read the matching test file(s) (`*.spec.ts`, Playwright `*.spec.ts`); count cases by outcome (happy path, error state, empty state, validation failure, auth denial, accessibility check)
3. If callers / parents are obvious (a route component importing a feature component, a layout wrapping a route), read the immediate caller too - removing or reshaping inputs without seeing call sites is how silent breakage happens
4. For services consumed by many components, run a mental impact-check on the public surface

If the user named only the goal without a target file / module, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat modules. If the file containing the target also contains other smells (e.g., the user names `OrderListComponent` but the same file has `bypassSecurityTrustHtml` in `OrderActions` and inline IDOR in `OrderActionsService`), do **not** action them in this plan and do **not** ignore them silently. List under a `Sibling Smells (Out of Scope)` heading, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-angular-review-security`), and recommend follow-up invocations.

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (`*.spec.ts`, integration tests, Playwright specs), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                | What the workflow does                                                                                                                        |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., empty state, error state, validation failure, auth denial) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                            | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                     | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-angular-test` first            |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves error handling, empty states, or accessibility - you would be flying blind.

**Internal-coupled tests count negatively.** Inspect each test's assertions for `fixture.componentInstance.<internal>`, render-count spies, or signal-name reads that the planned refactor will rename or remove (e.g., a test asserts on `filteredCount$` and Step 6 deletes that observable in favor of a `computed` signal). When this is true, the test will fail on the refactor for an **implementation reason** rather than catch a **behavior regression** - the inverse of what the gate is for. Surface this in the Coverage Gate as `internal-coupled: <test:line> asserts <internal-name> which Step <N> will remove` and require the test to be rewritten as DOM/event assertions in `Step 0 - Coverage prerequisite` before the renaming/extraction step runs. This rule applies even when overall coverage is `Adequate` - one tightly-coupled test against a soon-to-be-deleted internal still blocks the affected step.

**Output of this step:** explicit coverage status using one of the three labels. Do not proceed past Step 4 if status is `Inadequate`.

**Preview rules when Inadequate.** Step 4's smell catalog still runs to populate the Smells Identified and Sibling Smells (Out of Scope) preview - that is what the catalog is for. The refusal is on producing Steps 1+, not on diagnostic output. The preview helps the author scope the follow-up `task-angular-test` invocation.

**Bug-fix smuggled into a refactor request.** If the user's prose mixes "refactor X" with "and also fix that the filter does not persist on refresh," stop and surface the conflict: refactoring assumes behavior preservation, so a behavior change must either (a) be a separate PR ahead of the refactor, or (b) be explicitly labeled `coupled-fix` in Step 6 with its own test gate. Do not silently fold it into an extraction step.

### Step 4 - Identify Angular Smells

Inspect the target for these Angular-specific smells. Use judgment - these are signals, not hard rules.

**Component smells:**

| Smell                                   | Signal                                                                                                                                    | Risk   |
| --------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Component                           | Component file > 300 lines; mixes data fetching, state, business logic, multiple sub-rendering paths                                      | High   |
| Default Change Detection                | `@Component({})` without `changeDetection: ChangeDetectionStrategy.OnPush` in new code; under zone.js this dirties on every event in the zone | High   |
| Inline Business Logic in Template       | Calculations, branching > 3 levels, formatting inside `{{ }}` / `@if` chains - extract to `computed` or sub-components                    | Medium |
| Conditional Rendering Ladder            | > 3 nested `@if` / ternaries in the template; readability degrades fast                                                                   | Medium |
| Untyped Inputs                          | `@Input() x` (no type) or `input<any>()` - typed via `input<T>()` / `input.required<T>()` or `@Input() x!: T` is the idiom                | High   |
| Inline Event Handler > 3 Lines          | Heavy logic inline in `(click)="..."` - extract to a method                                                                               | Low    |
| Class-based Lifecycle for One-Time Work | `ngAfterViewInit` for browser-only DOM work - prefer `afterNextRender` (Angular 16+) which only runs on the client                        | Low    |
| Old `*ngIf` / `*ngFor` in New Code      | New components written with structural directives instead of `@if` / `@for` - migration value is incremental                              | Medium |
| NgModule for New Code                   | New `@NgModule({...})` declaration when standalone components are the modern shape                                                        | Medium |

**State / signal / RxJS smells:**

| Smell                                       | Signal                                                                                                                                                  | Risk   |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| BehaviorSubject for Component-Local State   | `private state$ = new BehaviorSubject(...)` for state internal to one component - signal is the modern idiom                                            | Medium |
| Bare `.subscribe()` without Cleanup         | `obs$.subscribe(v => ...)` in component / service without `takeUntilDestroyed`, `async` pipe, or `toSignal` - memory leak                               | High   |
| `effect()` for Derived State                | `effect(() => mySignal.set(otherSignal() + 1))` - use `computed` (or `linkedSignal` if writability is needed)                                           | High   |
| `effect()` for Event Handler                | `effect(() => { if (clicked()) handleClick() })` triggered by setting `clicked` in `(click)` - just call `handleClick()` from the handler              | High   |
| Missing `effect` Cleanup                    | Long-lived `effect` with subscription / interval / observer registered without `onCleanup` callback                                                     | High   |
| `computed` for Trivial Value                | `computed(() => count() + 1)` - fine; flag chains of trivial computed obscuring data flow                                                               | Low    |
| Manual `markForCheck` / `detectChanges`     | Calling `cdr.markForCheck()` or `cdr.detectChanges()` to bypass OnPush; almost always indicates a missed signal / async pipe                            | Medium |
| Mixed signal / `BehaviorSubject` in Same Component | New code adds `BehaviorSubject` alongside existing signals - pick one direction; flag mixed-style as inconsistency unless migration documented   | Medium |

**Service / DI smells:**

| Smell                                 | Signal                                                                                                                                                       | Risk   |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------ |
| Fat Service                           | Service with 8+ methods covering unrelated concerns - extract or split                                                                                       | High   |
| `providedIn: 'root'` for Per-User State | Service holding per-user state but `providedIn: 'root'` - state leaks across users at logout without explicit reset                                        | High   |
| Direct `HttpClient` in Component      | Component injecting `HttpClient` and calling `.get()` directly - extract to a service                                                                        | High   |
| Constructor Injection in New Component / Function-Like Class | New code using `constructor(private svc: MyService)` instead of `private svc = inject(MyService)` field initialization                          | Low    |
| Class-Based Guard / Resolver / Interceptor | New code declaring `class AuthGuard implements CanActivate` instead of `export const authGuard: CanActivateFn = ...`                                    | Medium |
| `HTTP_INTERCEPTORS` Multi-Provider    | New interceptor registered via `{ provide: HTTP_INTERCEPTORS, ... }` instead of `provideHttpClient(withInterceptors([...]))`                                | Medium |

**Routing smells:**

| Smell                              | Signal                                                                                                          | Risk   |
| ---------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------ |
| Eager Route Component              | Non-trivial route declared with `component:` instead of `loadComponent: () => import(...)`                      | Medium |
| `RouterModule.forRoot` in New Bootstrap | New app using `RouterModule.forRoot(...)` instead of `provideRouter(routes)`                                | Low    |
| `CanActivate` Guarding Lazy Route  | Lazy route protected by `CanActivate` (loads chunk first, then redirects); `CanMatch` prevents the chunk load   | Medium |

**Template smells:**

| Smell                              | Signal                                                                                                                                                                              | Risk   |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `@for` without `track`             | `@for (item of items) { ... }` (Angular requires `track`; will not compile, but `track $index` on dynamic list is the silent variant)                                              | High   |
| `track $index` on Dynamic List     | `@for (item of items; track $index)` on a reorderable / filterable / removable list - breaks DOM reuse and re-creates child components                                              | High   |
| Missing `@defer` on Heavy Below-Fold | Heavy chart / editor / map component eagerly rendered when it's below the fold or behind interaction                                                                              | Medium |
| `@defer` Without Explicit Trigger  | `@defer { ... }` without `on viewport` / `on interaction` / `when condition()` - defaults to `on idle` which is rarely the intended trigger                                         | Low    |
| Missing `NgOptimizedImage`         | Raw `<img src="...">` for non-decorative images instead of `<img ngSrc="..." width height>`                                                                                         | Medium |
| `[innerHTML]` Without Sanitizer    | User-controlled HTML rendered raw - XSS                                                                                                                                             | High   |

**State / configuration smells:**

| Smell                                           | Signal                                                                                                | Risk   |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------ |
| Input Drilling > 4 Layers                        | Same input threaded through 4+ component layers - hoist to a service, NgRx store, or co-locate       | Medium |
| `environment.X` Sprinkled Across Components     | Should be a typed `InjectionToken<AppConfig>` injected once                                            | Medium |
| NgRx Mega-Store                                  | One store for all app state - feature-scoped stores (or NgRx Signal Store, one per feature) reduce blast radius | Medium |
| Mutable Module-Level State                       | `let cache = {}` mutated by render or events - in SSR leaks across requests                          | High   |

**Accessibility smells:**

| Smell                                 | Signal                                                                                                          | Risk   |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------ |
| `<input>` Without `<label>`           | Inputs without associated labels - screen readers miss them                                                     | High   |
| Custom Dialog Without Focus Trap      | Modal built from `<div>` without `role="dialog"`, focus trap, or keyboard close - keyboard / SR users blocked. CDK `Dialog` solves this | High   |
| `<div (click)>` Instead of `<button>` | Clickable `<div>` without `role="button"`, `tabindex`, key handling                                              | High   |
| Image Without `alt`                   | `<img>` / `<img ngSrc>` without `alt` (or `alt=""` for decorative)                                              | Medium |

**Test smells (when refactoring brings tests into scope):**

| Smell                                       | Signal                                                                                                                  | Risk   |
| ------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ------ |
| `getByTestId` Everywhere                    | Tests rely on `data-testid` instead of user-centric queries                                                             | Medium |
| Asserting `fixture.componentInstance.<internal>` | Tests on internal component state - couples to implementation; break on every refactor                             | High   |
| Mocking HTTP Service Methods Instead of `HttpTestingController` | Bypasses request-shape verification                                                                       | Medium |
| Snapshot Tests on Visual Layout             | Churns on every styling change; no signal                                                                               | Medium |
| Render Counts Asserted                      | `expect(spy).toHaveBeenCalledTimes(2)` for render counts - tests implementation; rewrite for behavior                   | High   |

**General smells (apply with TypeScript / Angular judgment):**

Use skill: `complexity-review` when the target shows over-engineering signals (single-impl content-projection abstraction, generic types for one consumer, premature compound components) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply Angular judgment - a 250-line component that orchestrates clearly named sub-components is fine; a 100-line component doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and routes are affected.

Angular-specific blast-radius signals:

- [ ] **Public design-system component**: target is a primitive in a shared component library used across many features
- [ ] **Top-level `app.component` / root layout**: refactoring root component, `app.config.ts`, or a global service affects every page
- [ ] **Service used widely**: target service is injected by > 10 components; signature changes cascade
- [ ] **Route segment used in many places**: refactoring a route component affects every page using it as a parent
- [ ] **Component input interface**: input rename / removal cascades into every parent that renders the component
- [ ] **HTTP interceptor**: refactoring affects every HTTP call in the app
- [ ] **Auth guard**: refactoring affects every protected route
- [ ] **NgRx store used cross-feature**: refactoring affects every feature that reads / dispatches

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single feature, multiple callers) / **Wide** (cross-feature, public component, root layout) / **Critical** (design-system primitive, root config, shared store, HTTP interceptor).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles with `ng build` cleanly and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing test suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target, do **not** concatenate the recipes - that produces a 25-step plan. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting an HTTP service method that derives `ownerId` from the auth context _requires_ adding the auth context lookup, which changes the error mode for unauthenticated callers). Label such steps `coupled-fix` with their own test gate and rationale. This is **not** a bundling violation - it is an explicit prerequisite. Do not silently fold it into an extraction step.

**Change-detection-boundary watch.** When converting `BehaviorSubject` + `async` pipe to `signal()` + signal read, OnPush components dirty-check differently. Audit consumers reading the value across change-detection boundaries.

**Subscription-boundary watch.** When introducing `takeUntilDestroyed()`, ensure the call site is in an injection context (field initializer, constructor, factory). Outside an injection context, you must `inject(DestroyRef)` first and pass it explicitly: `takeUntilDestroyed(destroyRef)`. State the injection-context stance per step.

**Common Angular refactor recipes:**

**Recipe: Migrate `BehaviorSubject` to `signal()` for component-local state**

1. Identify the `BehaviorSubject`: `private count$ = new BehaviorSubject(0)` exposed via `count$.asObservable()` and consumed via `async` pipe
2. Replace with `count = signal(0)`; mutators (`count$.next(v)`) become `count.set(v)` (or `count.update(prev => ...)`)
3. Update template: `{{ count$ | async }}` becomes `{{ count() }}`; remove `async` pipe
4. Update consumers: any external code subscribing to `count$` either reads `count()` synchronously, uses `toObservable(count)` to keep RxJS interop, or migrates too
5. Run tests; assert observable behavior unchanged
6. Audit other components for the same pattern - opportunity to migrate (do not bundle this audit; surface it as a follow-up)

**Recipe: Add `takeUntilDestroyed()` to manual subscriptions**

1. Identify the bare `.subscribe()` call: `obs$.subscribe(v => this.x = v)` in a component
2. Determine injection context: if the call is in field initializer or constructor, use `obs$.pipe(takeUntilDestroyed()).subscribe(...)`; if in a method called later, inject `DestroyRef` (`private destroyRef = inject(DestroyRef)`) and use `obs$.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(...)`
3. Or convert to `async` pipe in template (`{{ obs$ | async }}`) when the value is template-only - cleaner
4. Or convert to signal: `x = toSignal(obs$, { initialValue: ... })` and read `x()` - cleanest when downstream is also signal-based
5. Run tests; verify subscription is cleaned up by stubbing destroy and asserting observer not called

**Recipe: Migrate Default change detection to OnPush + signals**

1. Identify the component using Default CD; verify all state mutations either go through signals (good - works with OnPush) or `BehaviorSubject` + `async` pipe (good - `async` pipe calls `markForCheck()` on emission)
2. If the component uses imperative state mutation (`this.count = this.count + 1` and template re-renders), this is the load-bearing step: migrate state to signals first (separate Recipe), then add `changeDetection: ChangeDetectionStrategy.OnPush`
3. Add `changeDetection: ChangeDetectionStrategy.OnPush` to `@Component` decorator
4. Run tests; especially test interactions that mutate state and assert UI updates correctly under OnPush
5. Audit `cdr.markForCheck()` / `cdr.detectChanges()` calls - if they exist, the component is fighting against OnPush; the previous step missed a state-mutation source

**Recipe: Convert `@for` `track $index` to `track item.id`**

1. Identify the `@for` block: `@for (item of items; track $index) { ... }`
2. Verify `item` has a stable identifier (`id`, `uuid`, key); if not, the data shape needs a stable key first
3. Replace: `@for (item of items; track item.id) { ... }`
4. Run tests; verify list rendering preserves child component state across reorders / filters / removals
5. (Coupled-fix) If items lacked a stable key and one was added via `crypto.randomUUID()` at fetch time, document the shape change

**Recipe: Migrate class-based guard / interceptor / resolver to functional**

_Class-based guards / interceptors / resolvers are still valid and supported - migration is for consistency with `provideRouter` / `provideHttpClient` and the modern functional shape, not because the old form is broken._

1. Identify the class: `class AuthGuard implements CanActivate { canActivate(...) { ... } }`
2. Convert to function: `export const authGuard: CanActivateFn = (route, state) => { const router = inject(Router); ...; }`
3. Update route config: `{ path: 'admin', canActivate: [authGuard] }` (just the function reference, no `inject()` array wrapper needed)
4. Remove the class; remove its registration from any module's `providers` array
5. Run tests; rewrite tests to use `TestBed.runInInjectionContext(() => authGuard(...))` per the test recipe
6. (Same recipe for `CanMatchFn`, `CanDeactivateFn`, `ResolveFn`, `HttpInterceptorFn`)

**Recipe: Migrate `HTTP_INTERCEPTORS` to `provideHttpClient(withInterceptors([...]))`**

1. Identify `HTTP_INTERCEPTORS` registration: `{ provide: HTTP_INTERCEPTORS, useClass: AuthInterceptor, multi: true }`
2. Convert the class interceptor to a functional interceptor (separate Recipe if needed)
3. Update bootstrap: `provideHttpClient(withInterceptors([authInterceptor, errorInterceptor]))` in `app.config.ts`
4. Remove the multi-provider; remove the imports
5. Run tests; verify request transformations still happen

**Recipe: Migrate NgModule component to standalone**

1. Identify the NgModule-declared component: `declarations: [MyComponent]` in some module
2. Add `standalone: true` to `@Component` decorator (Angular 19+ default; older versions need explicit), and move the module's `imports` into the component's `imports` array
3. Remove from the module's `declarations`; if the module exported the component, update consumers to import the component directly
4. If the module had no other declarations, delete the NgModule entirely; update bootstrap config to remove its registration
5. Run tests; component tests now import the component directly (`imports: [MyComponent]` in TestBed)
6. Audit consumers for any `imports: [SomeModule]` that needs to be replaced with direct component imports

**Recipe: Extract service from fat component**

1. Identify the cohesive state + logic + HTTP trio inside the component (e.g., filter state + filter URL sync + filter HTTP fetch)
2. Create `useXxxService` (or `Xxx.service.ts`) with the same shape; copy logic; write a service test (`HttpTestingController` for HTTP; signal / observable assertions for state)
3. Replace the inlined logic in the component with `private filterSvc = inject(FilterService)`; component still does the original work via the service
4. Verify component tests pass unchanged
5. Audit other components for the same pattern - opportunity to reuse the service (do not bundle this audit; surface it as a follow-up)

**Recipe: Untangle input drilling**

1. Identify the input chain (which input, which layers it passes through)
2. Decide on the right primitive: (a) **co-locate state** with the consumer (move the `signal` / state to the leaf if no other consumer needs it), (b) **service** with `providedIn: 'root'` or route-scoped for cross-cutting state, (c) **NgRx store** for app-state shared by multiple features. Choosing the primitive is the first decision; not every input drill is a NgRx candidate
3. Implement: extract the state into the chosen primitive; remove the input from intermediate layers; consumers read directly via `inject` / store
4. Verify intermediate layers are simpler (fewer inputs); run tests
5. If using a service, ensure it's correctly scoped (`providedIn: 'root'` for app-wide; route-scoped for per-route state)

**Recipe: Split god component into focused components**

1. Identify the orthogonal concerns inside the component (e.g., `DashboardComponent` doing filters + list + summary + actions panel)
2. Extract one concern at a time into a new standalone component file with explicit `input<T>()` / `output<T>()` interface; original god component renders the new one via `<app-filters />` etc.
3. Update tests if the new component has its own test surface
4. Repeat until the god component is a thin layout coordinator
5. Verify route-level tests / Playwright E2E still pass

**Recipe: Replace mutable module-level state**

1. Identify the mutable state (`let cache = {}`, `const handlers = []`)
2. Move into a `providedIn: 'root'` service (`signal()` for state, methods for mutation), an NgRx store, or per-component state if appropriate. For SSR, this is mandatory - module-level state leaks across requests
3. Update consumers to inject the service / select from store
4. Run tests; assert cross-test isolation (test order should not matter)

**Recipe: Project SSR `TransferState` payload to DTO**

1. Identify the data placed in `TransferState` during SSR-side fetch: `transferState.set(USER_KEY, await prisma.user.findUnique({ where }))` - the entire row serializes into the HTML payload
2. Project at the data-fetch layer: `prisma.user.findUnique({ where, select: { id: true, email: true, name: true } })` (Prisma `select` whitelist) or define a DTO type and a mapper function
3. Update consumers to read only the projected fields (TypeScript will surface any caller still reading `passwordHash`)
4. Run tests; verify SSR payload (`view-source` on a rendered page) no longer contains the leaked fields

**Recipe: Add accessibility for custom interactive component**

1. Identify the violation (e.g., `<div (click)>` for a button)
2. Replace with the right semantic element (`<button>`, `<a>`, `<input>`) or add proper ARIA + key handlers (`role`, `tabindex`, `(keydown)` dispatching click on Enter / Space)
3. Add label / `aria-label` / `aria-describedby` as needed; or wrap in CDK Dialog primitives for modals
4. Run `axe` test asserting no violations

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end)
- [ ] Steps ordered low-risk first (extracts, additions) before high-risk (deletions, input removals, change-detection migration)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Angular Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Angular refactor recipes" - this is the spine]
**Stack:** Angular <version> / TypeScript <version>
**Change detection:** zone.js | zoneless
**SSR:** enabled | disabled

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-angular-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce **Smells Identified** and **Sibling Smells (Out of Scope)** as a *preview*; mark them clearly as preview-only.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure / invalid input, error state, empty state, loading state, accessibility (when interactive). Layer options: component test (TestBed/ATL), service test (`HttpTestingController`), guard test (`runInInjectionContext`), interceptor test (`provideHttpClient(withInterceptors([...]))`), Playwright E2E. Example: `OrderListComponent | empty-state visible when 0 orders | component test`.

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/module that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                               |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-angular-review-security` / `task-angular-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - component / service / guard / interceptor / E2E]
- **CD stance:** [Default | OnPush | unchanged | converting from Default to OnPush]
- **Subscription stance:** [bare `.subscribe()` (legacy) | `takeUntilDestroyed` | `async` pipe | `toSignal` | unchanged | converting from X to Y]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it. Always state why the coupling is structural.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `ng build` clean and test suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No silent change-detection-mode flips; descendants audited
- [ ] No silent subscription-management changes; consumers audited

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderListComponent` to `OrdersTableComponent` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as Angular (or accepted from parent dispatcher); change-detection mode and SSR status recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin` (Step 3)
- [ ] Internal-coupled tests audited: each test's assertions checked against the internals the refactor will remove or rename; matches surfaced as `internal-coupled` and pinned to a `Step 0` rewrite (Step 3)
- [ ] When refusal triggered (Inadequate), Step 4 catalog still ran to produce the Smells preview; not skipped (Step 3)
- [ ] Bug-fix smuggled into a refactor request was surfaced and split into a separate PR or labeled `coupled-fix` - never silently folded (Step 3)
- [ ] Angular-specific smells identified using Step 4 catalog (component, signal/RxJS, service/DI, routing, template, state, accessibility, test) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate` (Output Format)
- [ ] CD stance and subscription stance stated per step (no silent conversions) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, conversions, input removals) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `ng build` clean and test suite passes between every step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing a `.subscribe()` without verifying the surrounding logic preserves the original observable behavior - some subscriptions compensate for genuinely external state and removal regresses
- Migrating `BehaviorSubject` to `signal` without auditing every consumer - external subscribers may need `toObservable(signal)` interop
- Migrating Default CD to OnPush without first auditing state mutation paths - imperative `this.x = ...` mutations stop reflecting in template
- Converting class-based guards / interceptors to functional without rewriting their tests for `runInInjectionContext` - tests fail
- Migrating to standalone without auditing every NgModule consumer - imports cascade
- Replacing `@for ... track $index` with `track item.id` without verifying every item has a stable id - reactivity breaks silently
- Replacing input drilling with NgRx as a default - co-located state is often the right answer; service for cross-cutting state, NgRx for app-shared
- Refactoring a design-system component without a backward-compatibility plan - that is a public API
- Replacing `getByTestId` queries with `getByRole` queries during a refactor - that is a test improvement, deserves its own PR
