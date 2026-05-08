---
name: task-angular-review
description: Angular staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with Angular idioms (standalone discipline, OnPush mandate, signal correctness, RxJS subscription hygiene, `bypassSecurityTrust*` audit, `[innerHTML]` audit, new control-flow `track`, functional guards/interceptors, SSR `TransferState`, accessibility regressions). Spawns Angular-specific perf / security / observability subagents for extra scopes. Stack-specific override of task-code-review for Angular. Runs standalone with full PR/branch resolution.
agent: angular-tech-lead
metadata:
  category: frontend
  tags: [angular, typescript, signals, rxjs, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Angular Code Review

## Purpose

Angular-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Angular-specific correctness, architecture, AI-quality, and maintainability checks (standalone-component discipline, OnPush mandate, signal correctness (`signal` / `computed` / `effect` / `linkedSignal` / `resource`), RxJS subscription hygiene (`takeUntilDestroyed`, `async` pipe, `toSignal`), new control-flow (`@for` `track` correctness, `@defer` placement), functional guards / resolvers / interceptors, `provideX` configuration discipline, `bypassSecurityTrust*` audit, `[innerHTML]` audit, SSR `TransferState` correctness, accessibility regressions, anemic input interfaces). Coordinates Angular-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Angular. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional.

## When to Use

- Reviewing an Angular PR before merge
- Post-AI-generation quality gate on an Angular change set
- Architecture drift detection in an Angular codebase
- Pre-merge risk assessment on an Angular branch

**Not for:**

- Pre-implementation feature design (use `task-angular-implement`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-angular-debug`)
- Architecture/design review of a new system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-angular-review-perf`, `task-angular-review-security`, or `task-angular-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Angular staff-level review                                 | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                    |
| --------------- | ---------------------------------------------------------------------------- |
| Core            | Phases A-E only (Angular-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-angular-review-perf`                         |
| + Security      | Core + parallel subagent: `task-angular-review-security`                     |
| + Observability | Core + parallel subagent: `task-angular-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel Angular subagents) |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

**Scope auto-escalation signals (Angular-tuned):**

- New `bypassSecurityTrust*` call, new `[innerHTML]` binding, new functional interceptor / guard, auth library / session config change, new `Router.navigateByUrl` from user input, CSP / `Content-Security-Policy` change, new file upload, new `environment.ts` entries that look secret-like → auto-add **+Security**
- New route / lazy-loaded component, new heavy third-party dep in `dependencies`, new component with Default change detection, new `@defer` block, new `NgRx` store / signal store, new `HttpClient` call without caching, new long list rendered without `track` → auto-add **+Perf**
- New error handler / `ErrorHandler` provider, new Sentry / RUM SDK init, new `web-vitals` reporter, new logging utility, new analytics call, new `TransferState` use → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                      | Meaning                                                                                                                                                                                   |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-angular-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                               |
| `/task-angular-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                         |
| `/task-angular-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants)     |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>`.

Examples:

- `/task-angular-review pr-123 --base release/2026.05`
- `/task-angular-review feature/x --base develop`

Scope and depth flags compose: `/task-angular-review pr-50273 --base release/2026.05 +security deep`.

## Workflow

### Step 1 - Confirm Stack and Detect Configuration

Use skill: `stack-detect` to confirm Angular. If invoked as a delegate of `task-code-review` (parent already detected Angular), accept the pre-detected stack and skip re-detection. If the detected stack is not Angular, stop and tell the user to invoke `/task-code-review` instead.

Detect: Angular major version (Angular 21+ enables `linkedSignal`, `resource`, signal-based forms; Angular 20 stabilized `effect` + signal inputs; Angular 19 enabled `linkedSignal` initial release; Angular 17/18 introduced new control flow + standalone-by-default + signal inputs). Detect zoneless vs zone.js (`provideExperimentalZonelessChangeDetection` / `provideZonelessChangeDetection` in `app.config.ts`). Detect SSR (Angular Universal / `@angular/ssr` / `provideClientHydration`). Record `Angular: <version>`, `Change detection: zone.js | zoneless`, `SSR: enabled | disabled`. Each Phase B / C / D / E checklist below branches on these signals where the idiom differs.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message, surface it verbatim and stop. Do not run any state-changing git command.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Step 3 - Evaluate Scope Auto-Escalation

Scan the file list and diff content for the auto-escalation signals listed under **Scope** above. For each signal that fires, log a one-liner: `signal: <category> -> <file:line>`. Then decide:

- Zero signals or user passed `core-only` → stay on Core
- One signal category → add the matching extra scope
- Two or more signal categories → promote to Full
- User passed an explicit scope → respect it (do not downgrade), but record signals so the Summary documents why

Surface the decision in the Summary's `Scope:` field. If escalated, append `auto-escalated from Core; signals: <list>`.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth config, HTTP interceptors, route configuration, `app.config.ts` / `app.providers.ts`, root `AppComponent`, shared services / NgRx stores), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Step 3.5 - Re-evaluate Depth After Phase A

If `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, set depth to `deep` and surface `Depth auto-promoted: standard -> deep (Blast Radius: <level>)` in the Summary. Do this **before** launching Phases B-E so deep-only behaviors are in scope.

### Phase B - Angular Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting UI integrity, backward compatibility, hydration correctness, accessibility - through an Angular lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding test coverage (Vitest / Jest / Karma + Angular Testing Library / TestBed), raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] when the change is in a critical path - any of: authentication / session UI, HTTP interceptors, money / billing UI, form validation, multi-step flows, error handlers. Do not bury this finding in Key Takeaways.

**Angular-specific correctness checks:**

- [ ] **TypeScript strict mode**: `strict: true` and `strictTemplates: true` not silently disabled; `as any` flagged outside test setup; `noImplicitAny` / `strictNullChecks` not relaxed; component inputs declared via `input<T>()` (signal input) or `@Input() x!: T` with explicit type, never `any`
- [ ] **Standalone components**: every new component / directive / pipe is standalone (`standalone: true` was the default behavior since Angular 19; flag any `standalone: false` without rationale). New code that introduces an `NgModule` is a [High] - the project's existing NgModules are fine to leave but new ones need explicit justification
- [ ] **OnPush change detection**: every new component declares `changeDetection: ChangeDetectionStrategy.OnPush`. Default change detection is a [High] finding in Angular 17+ - signals + OnPush is the canonical shape. Existing Default-CD components in the diff but unchanged are out of scope; flag only when the diff touches the `@Component` decorator
- [ ] **Signal-first state**: new component-local state uses `signal()` / `computed()` / `linkedSignal()` rather than `BehaviorSubject` + `async` pipe. Existing `BehaviorSubject` patterns are fine; flag new ones as a [High] AI-smell unless the surrounding feature is RxJS-heavy and the consistency argument applies
- [ ] **`computed` / `effect` discipline**: `effect()` is for **side effects** only - DOM imperative work, third-party library sync, logging - NOT for deriving state (that's `computed`). Flag `effect(() => { mySignal.set(otherSignal() + 1) })` as a misuse - use `computed` (or `linkedSignal` if you need writability). Flag `effect()` reading signals to call `console.log`-only - use `toObservable` or remove
- [ ] **`effect` cleanup**: side-effect `effect()` registering subscriptions / observers / intervals must use the `onCleanup` callback or run inside `effect((onCleanup) => { ...; onCleanup(() => sub.unsubscribe()) })`. Missing cleanup in a long-lived effect leaks
- [ ] **`linkedSignal` over `computed` + `effect`**: state that derives from inputs but is locally writable (e.g., a search filter that resets when the parent changes the dataset) is the canonical `linkedSignal` shape - flag the older "computed + effect to write back" pattern
- [ ] **Signal inputs over `@Input()`**: new components use `input<T>()` / `input.required<T>()` for inputs and `output<T>()` for outputs. Flag mixed-style components (some signal inputs, some decorator inputs) unless the migration is in progress and called out
- [ ] **`untracked` for breaking dep tracking**: when an `effect` reads a signal but should not re-run on its change, wrap with `untracked(() => signal())`. Flag `effect` re-firing on irrelevant dep reads
- [ ] **RxJS subscription hygiene**: every `.subscribe()` in a component / directive / service uses one of: `takeUntilDestroyed()`, `async` pipe in template, `toSignal(observable)`. Bare `.subscribe()` without cleanup in a component is a [High] memory-leak finding. `takeUntilDestroyed` requires injection context - either at field initialization or `inject(DestroyRef)` + `takeUntilDestroyed(destroyRef)`
- [ ] **`async` pipe over manual subscribe**: new template data binding uses `someValue$ | async` (or `toSignal(someValue$)` + signal read) rather than subscribing in `ngOnInit` and storing in a field. Manual subscribe is a smell unless the value is consumed imperatively
- [ ] **`toSignal` / `toObservable` discipline**: bridges between RxJS and signals are intentional, not casual. Flag round-trips (`toObservable(toSignal(x$))`); flag `toSignal()` without `initialValue` in a context that needs synchronous read (signal read before first emission throws unless `initialValue` or `requireSync: true` is set)
- [ ] **`@for` `track` correctness**: every new `@for` block must declare `track`. `track $index` on a reorderable / filterable / removable list breaks DOM reuse and is a [High] finding. `track item.id` (stable) is right. `track item` (object identity) is fine when items are referentially stable across emissions; flag if items are recreated each tick
- [ ] **`@defer` placement**: `@defer` blocks must specify a trigger (`on idle`, `on viewport`, `on interaction`, `on hover`, `on timer(...)`, `when ...`); a bare `@defer { ... }` defers but with the default `on idle` trigger - flag missing explicit trigger and missing `@placeholder` (for content-shift prevention)
- [ ] **New control flow over structural directives**: new code uses `@if` / `@for` / `@switch`, not `*ngIf` / `*ngFor` / `*ngSwitch`. Flag mixed-style components in new files
- [ ] **`inject()` over constructor injection**: new injection sites prefer `inject(MyService)` over constructor params. Constructor injection is still valid; flag mixed style in a single new component, or constructor injection in a class that needs to inject in field initialization (forces awkward refactor)
- [ ] **Functional guards / resolvers / interceptors**: new guards use `CanActivateFn` / `CanMatchFn` etc.; new interceptors use `HttpInterceptorFn`. Class-based guards / interceptors in new code are a [Medium] - the functional shape is the modern idiom and works with `provideRouter` / `provideHttpClient(withInterceptors([...]))`
- [ ] **`provideHttpClient(withInterceptors([...]))`**: HTTP interceptors registered via the functional `provideHttpClient` setup, not `HTTP_INTERCEPTORS` multi-provider. Flag new `HTTP_INTERCEPTORS` registrations
- [ ] **`provideRouter(routes, withComponentInputBinding(), ...)`**: route configuration via standalone bootstrap, not `RouterModule.forRoot`. Flag new `RouterModule.forRoot` calls in app bootstrap
- [ ] **HTTP error handling**: `HttpClient.get` / `post` calls in services have a `catchError` handler or rely on a global error interceptor; flag bare `.subscribe()` on an HTTP call without error handling - the unhandled error surfaces as an `ErrorHandler.handleError` console log at best, silent failure at worst
- [ ] **Reactive Forms with `FormBuilder` / typed forms**: new forms use `FormBuilder` or typed `FormGroup<{...}>`; flag template-driven forms in new code unless project-wide convention. Validation via `Validators.*` + custom validators; flag inline validation logic in submit handlers (validators belong on the form)
- [ ] **Form validation surfaces errors**: every required / pattern / custom validator has a corresponding error display; flag forms that validate but don't show errors (UX broken). Error association via `aria-describedby` for screen readers
- [ ] **`NgOptimizedImage` for images**: `<img ngSrc="..." width="..." height="...">` for non-decorative images; flag raw `<img>` for hero / above-the-fold or list images. Hero image marked `priority`; missing `priority` on LCP candidate is a [Medium]
- [ ] **`[innerHTML]` audit**: any `[innerHTML]="x"` where `x` originates from user input, URL params, or external API must be sanitized via `DomSanitizer.sanitize(SecurityContext.HTML, ...)` or rendered as text. Angular auto-escapes interpolation but `[innerHTML]` is a direct XSS vector. Flag as Critical when the content path is user-controllable
- [ ] **`bypassSecurityTrust*` discipline**: every `DomSanitizer.bypassSecurityTrustHtml/Url/Script/Style/ResourceUrl` call has a comment justifying why (e.g., "trusted markdown processed at build time"). Bypassing for user-controlled content is Critical
- [ ] **Open redirect**: `Router.navigateByUrl(query.returnTo)` / `window.location.href = userInput` without allowlist or relative-path-only check (`url.startsWith('/') && !url.startsWith('//')`) is an open redirect
- [ ] **`environment.ts` for secrets**: `environment.ts` / `environment.prod.ts` compile into the client bundle - any API key, signing secret, or DB URL there is a Critical leak. Server-only secrets live in build-time-injected env vars on the SSR server, not in the client bundle
- [ ] **SSR `TransferState` for fetched data**: when SSR is enabled, server-fetched data uses `TransferState` (`makeStateKey`, `transferState.set/get`) so the browser does not re-fetch on hydration. Flag `HttpClient` calls in `ngOnInit` / signal init that re-run on hydration without `TransferState` - request waterfall on every page load. Modern Angular: `provideClientHydration(withHttpTransferCacheOptions({...}))` enables HTTP transfer cache automatically; flag SSR projects without it
- [ ] **Browser-only API guards under SSR**: `window`, `document`, `localStorage`, `IntersectionObserver` accessed in component code that runs server-side crashes. Wrap with `if (isPlatformBrowser(this.platformId))` or move into `afterNextRender` / `ngAfterViewInit` (which only runs on client)
- [ ] **Form accessibility**: `<input>` has an associated `<label>` (via `for` or wrapping); error messages associated via `aria-describedby`; submit button has accessible name; required fields use `aria-required` (or `required`) and surface validation errors when invalid
- [ ] **Interactive accessibility**: dialogs use Angular CDK `Dialog` / `Overlay` (which handle focus trap, return-focus, ARIA) rather than hand-rolled `<div>` modals; menus use `MenuModule` / proper key handling; new interactive components built on Angular Material / Angular CDK primitives by default rather than reinventing keyboard handling
- [ ] **Image / media**: `NgOptimizedImage` enforces `width`/`height`; raw `<img>` must declare them to prevent CLS; `alt` attribute present (empty string `alt=""` for decorative); flag missing
- [ ] **Error boundary**: app has a global `ErrorHandler` provider routing to Sentry / structured logging; flag new components with non-trivial render logic that could throw without coverage at the global handler

**Concurrency / state-management safety:**

- [ ] **State categorization**: state lives in the right place - URL (route params + `withComponentInputBinding` for filters / page / sort), server (HTTP service + signal cache, or NgRx for shared), local (`signal` for UI-only). Flag local state for filter values when the URL would deep-link better; flag client-side caching of server state when HTTP cache / `TransferState` would handle it
- [ ] **NgRx granularity**: a single mega-store with all app state vs feature-scoped stores. Feature stores (or NgRx Signal Store with one per feature) reduce blast radius of changes
- [ ] **Service singleton scoping**: `providedIn: 'root'` is the default; `providedIn: 'platform'` / `'any'` / route-scoped are exceptions that need rationale. Flag a service that holds per-user state but is `providedIn: 'root'` (state leaks across users on log-out without explicit reset)
- [ ] **No mutable module-level state**: `let cache = {}` mutated by render or events leaks across SSR requests. Flag for service-scoped state or signal-based state
- [ ] **Subscription leak via `takeUntilDestroyed` outside injection context**: `takeUntilDestroyed()` called outside an injection context (e.g., inside a callback fired after construction) throws or no-ops. Flag for `inject(DestroyRef)` + explicit `takeUntilDestroyed(destroyRef)` form

Use skill: `angular-component-patterns` for canonical component shape.
Use skill: `angular-signals-patterns` for signal correctness.
Use skill: `angular-rxjs-patterns` for RxJS subscription hygiene.
Use skill: `angular-service-patterns` for service / DI / HttpClient patterns.
Use skill: `angular-state-patterns` for state-management patterns.

### Phase C - Angular Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Angular-specific architecture checks:**

- [ ] **Component layering**: presentational vs container distinction not strict, but business logic does not live inside leaf / display components - it lives in route-level / container components / services. Flag HTTP calls inside leaf components, business decisions in display components
- [ ] **Service / component boundary**: HTTP, business rules, cross-component state belong in services (`providedIn: 'root'` or feature-scoped); flag direct `HttpClient.get` calls in components
- [ ] **Route segment cohesion**: route-level components (`loadComponent` targets) are thin orchestrators; business logic belongs in services. Flag route components > 200 lines of orchestration
- [ ] **Lazy-load discipline**: feature routes use `loadComponent` (Angular 14+) / `loadChildren`; flag eager `component:` imports for non-trivial routes that could lazy-load
- [ ] **DI hierarchy correctness**: `providedIn: 'root'` for app-wide singletons, route-scoped providers for per-route state, component providers for per-instance state. Flag a `providedIn: 'root'` service that should be route-scoped (state bleeds), or component-scoped state hoisted to root unnecessarily
- [ ] **Configuration discipline**: typed config injected via `InjectionToken` (`APP_CONFIG`) or via a typed env module. Flag `environment.X` accessed across many components - that's a refactor target
- [ ] **Module / package boundaries**: feature-folder layout (`features/orders/{components,services,routes}.ts`) preferred over flat `components/`, `services/` for everything; cross-feature imports go through a defined public surface (`features/orders/index.ts` re-exports)
- [ ] **Server-only utility imported into Client component**: a component that imports `fs`, `node:crypto`, ORM client into client-evaluated code is a build error / bundle leak under SSR - flag any cross-boundary import
- [ ] **NgModule sandwich**: large legacy `AppModule` with > 30 imports / declarations signals a standalone-migration target. Not a hard rule, but flag for cleanup when the diff touches the module

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**Angular-specific AI smells:**

- [ ] **Pattern inflation**: generic `<DataTable<T>>` for a single use case where a typed concrete component would suffice; content-projection trio when a flat input API would do; `@ViewChild` on every component (each `@ViewChild` widens the public surface)
- [ ] **Over-abstraction**: `BaseFormComponent` parent for 2 children; premature compound components when a flat input API would do; "headless" abstraction for one consumer
- [ ] **Speculative configurability**: inputs with documented but unused values; theme variants for a single design; "extensibility" hooks that no caller uses
- [ ] **Redundant signal transforms**: input signal → `linkedSignal` → `effect` syncing them - just use the input directly via `computed`. The "store input in writable signal" pattern is almost always wrong
- [ ] **`effect` for things that should be `computed`**: `effect(() => { mySignal.set(otherSignal() + 1) })` - use `computed` (or `linkedSignal` if writability is needed)
- [ ] **`effect` for things that should be event handlers**: `effect(() => { if (clicked()) handleClick() })` triggered by setting `clicked` in a `(click)` handler - just call `handleClick()` directly from the handler
- [ ] **`computed` everywhere on cheap values**: `computed(() => count() + 1)` is fine but flag chains of trivial `computed` that obscure data flow
- [ ] **Test verbosity**: `TestBed.configureTestingModule({ providers: [ ...50 mocks... ] })` setup chains; mocking the entire service when a single method would do; full-component snapshots
- [ ] **Comment cruft**: comments restating input names; JSDoc on private internal helpers; `// TODO` markers without owner / date
- [ ] **`as any` / `as unknown as T` proliferation**: legitimate uses are rare; `as any` to bypass a real type bug is a finding
- [ ] **Try-catch noise in observables**: `pipe(catchError(e => { throw e }))` - delete; `pipe(catchError(e => of(null)))` swallows the error and loses telemetry - prefer `catchError(e => { logger.error(e); return throwError(() => e) })` or surface to a global error handler
- [ ] **`@HostBinding` / `@HostListener` decorators in new code**: prefer `host: { ... }` in `@Component` / `@Directive` metadata - more discoverable, no decorator overhead. Existing decorator usage is fine; flag new

### Phase E - Angular Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Angular-specific maintainability checks:**

- [ ] **Naming conventions**: components in PascalCase + `Component` suffix (`OrderListComponent`); services with `Service` suffix; pipes with `Pipe` suffix; selectors kebab-case with project prefix (`app-order-list`); no abbreviations (`OrdLst` is wrong)
- [ ] **File naming**: `order-list.component.ts`, `order-list.component.html`, `order-list.component.spec.ts` colocated; flag mixed-case filenames, missing `.component` / `.service` / `.pipe` discriminators
- [ ] **Magic numbers / strings**: extracted to module-level constants or `InjectionToken`-injected config; route paths declared in a typed `app.routes.ts` constant rather than string literals scattered across `routerLink`
- [ ] **Hardcoded URLs / API endpoints**: in env-driven config (`InjectionToken<AppConfig>` from `environment.ts`), not inline (allows env-specific behavior)
- [ ] **Component length**: components > 200 lines reviewed for extraction; extract sub-components, services, or move logic to utility functions
- [ ] **Conditional rendering ladders**: > 3 nested `@if` / ternary in template → extract to a sub-component or a `computed` returning the right variant
- [ ] **Logging / error reporting hygiene**: surface obvious offenders as Core findings - `console.log` in component constructor / `ngOnInit` / template binding (called on every change detection cycle, leaks PII into devtools and may be picked up by RUM forwarders), `console.log(JSON.stringify(largeObject))` of any non-trivial payload, `console.error` outside of error handlers / dev paths, production errors not routed through `ErrorHandler` to Sentry / RUM SDK. The observability subagent owns depth (sample rates, attribution, instrumentation API); do not duplicate that audit here

Use skill: `frontend-coding-standards` if the project has one (otherwise rely on TS strict + ESLint with `@angular-eslint/*` + project-specific conventions).
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-angular-review-observability` subagent owns depth).

### Step 4 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core).

| Scope                | Subagents spawned                                                                                                                   |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-angular-review-perf`                                                                                       |
| Core + Security      | 1 subagent running `task-angular-review-security`                                                                                   |
| Core + Observability | 1 subagent running `task-angular-review-observability`                                                                              |
| Full                 | 3 subagents running `task-angular-review-perf`, `task-angular-review-security`, `task-angular-review-observability` in parallel    |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Angular) and detected configuration (Angular version, zoneless / zone.js, SSR enabled / disabled) so the subagent skips its own `stack-detect` and configuration branching
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 5 - Synthesize (only if Step 4 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a `[innerHTML]` introduction flagged by both Core/Phase B and Security). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.**
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope>` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity.

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Angular <version> / TypeScript <version>
**Change detection:** zone.js | zoneless
**SSR:** enabled | disabled
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Angular idiom: bare `.subscribe()` without `takeUntilDestroyed`, `[innerHTML]` on user input, Default change detection, missing `track` on `@for`, `effect` writing back to a signal it reads, `bypassSecurityTrustHtml` on user content, `environment.ts` containing a secret, missing `TransferState` causing SSR re-fetch, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Angular change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

### [Question] file:line

- Question: [what is ambiguous in the change]
- Why it matters: [what the right next step depends on - author intent, business rule, deployment topology, etc.]

_Use [Question] when the change is genuinely ambiguous. Do NOT use it as a softer Blocker._

## Architecture Notes

_Summary commentary on systemic patterns. **Do not restate individual findings here.** If a pattern is severe enough to be a finding, keep it in Findings and reference it by file:line._

- Boundary impact:
- Coupling change:
- Drift detected:
- SSR / hydration data flow: when 3+ findings cluster around HTTP calls re-running on hydration, name the systemic pattern here ("Components consistently fetch in `ngOnInit` without `TransferState`; introduce HTTP transfer cache via `provideClientHydration(withHttpTransferCacheOptions({}))`") rather than producing N near-identical findings

## Maintainability Notes

_Same rule as Architecture Notes._

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Add `takeUntilDestroyed()` to the `.subscribe()` in src/app/orders/order-list.component.ts:42 to prevent leaks across navigation"]
2. **[Delegate]** [High] [scope: design-system] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

### Streamlined output (low-risk short-circuit only)

When Phase A short-circuits (Risk Level: Low + Blast Radius: Narrow + no architecture-relevant files), produce the *streamlined* shape below instead of the full template above. Drop Architecture Notes, Maintainability Notes, and any Phase C/D-only sections - they were not run.

```markdown
## Summary

**Assessment:** Approve | Discuss
**Risk Level:** Low
**Blast Radius:** Narrow
**Stack Detected:** Angular <version> / TypeScript <version>
**Change detection:** zone.js | zoneless
**SSR:** enabled | disabled
**Scope:** Core (low-risk short-circuit; Phases C-D skipped)
**Depth:** quick | standard

## Findings

### [High] file:line _(if any)_

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line _(if any)_

- Improvement:

_Omit if no findings._

## Key Takeaways

- 1-2 bullets max - this is a low-risk PR.
```

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Angular conventions, not generic frontend conventions
- Provide actionable feedback with TypeScript / Angular component code examples
- Never comment on trivial formatting or style where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Angular subagent rather than duplicating the check here


### Step 6 - Write Report

Use skill: `review-report-writer` with `report_type: review`.

Write the fully assembled review output to the report file before ending the session. Print the confirmation line to the console.
## Self-Check

- [ ] Stack confirmed as Angular (or accepted from parent dispatcher); Angular version, change-detection mode (zone.js / zoneless), and SSR status detected
- [ ] `review-precondition-check` ran (or its handle was received); refs captured. If `--base` passed, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated in Step 3; promotion (or `core-only` suppression) recorded in Summary along with the firing signals
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B - TypeScript strict + standalone + OnPush + signal-first + new control flow checks applied
- [ ] Phase B - Signal correctness audited (`computed` vs `effect` vs `linkedSignal`, `untracked` for breaking deps, `effect` cleanup, `toSignal` `initialValue`)
- [ ] Phase B - RxJS subscription hygiene (`takeUntilDestroyed`, `async` pipe, `toSignal`) checked
- [ ] Phase B - `@for` `track`, `@defer` triggers + placeholder reviewed
- [ ] Phase B - Functional guards / interceptors / `provideHttpClient` / `provideRouter` discipline checked for new code
- [ ] Phase B - HTTP error handling on `HttpClient` calls checked (no bare `.subscribe()` on HTTP)
- [ ] Phase B - `[innerHTML]`, `bypassSecurityTrust*`, open redirect, `environment.ts` secret leak checked
- [ ] Phase B - SSR `TransferState` / HTTP transfer cache / browser-API guards checked when SSR is enabled
- [ ] Phase B - accessibility (form labels, dialog ARIA via CDK, image alt, `NgOptimizedImage`) checked
- [ ] Phase B - state categorization (URL / NgRx / signal / service) and DI scope reviewed
- [ ] Phase C Angular architecture checks applied: component layering, service/component boundary, lazy loading, DI hierarchy, package boundaries
- [ ] Phase D AI-quality checks applied: pattern inflation, over-abstraction, speculative configurability, `effect` misapplication, `computed` overuse
- [ ] Phase E Angular maintainability checks applied: naming, magic numbers, component length, conditional rendering ladders, logging hygiene
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Angular fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Angular-specific subagents (`task-angular-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle plus configuration detection
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)
- [ ] Review report written to file via `review-report-writer`; confirmation line printed to console

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic frontend conventions when an Angular idiom exists (say "extract to a service", not "extract to a helper module"; say "use `takeUntilDestroyed`", not "manage subscriptions")
- Nitpicking style where no project standard exists
- Providing vague feedback without a concrete Angular fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Angular subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
- Recommending Default change detection, bare `.subscribe()` in components, `[innerHTML]` on user input, `bypassSecurityTrust*` without justification, or `environment.ts` for secrets as acceptable - all are anti-patterns
