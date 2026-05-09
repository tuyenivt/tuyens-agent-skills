---
name: angular-code-explain
description: Explain Angular code: signals, zoneless change detection, standalone components, DI hierarchy, RxJS, async pipe, lifecycle, routing.
metadata:
  category: frontend
  tags: [explanation, code-understanding, angular, signals, rxjs]
user-invocable: false
---

# Angular Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Angular.

## When to Use

- A workflow needs Angular-specific signals: signals vs Zone.js change detection, standalone components, DI hierarchy, RxJS observables and the async pipe, component lifecycle, routing.
- Target is a `.ts` Angular component, service, directive, pipe, guard, interceptor, or module.

## Rules

- Identify the change detection model first: signal-based (Angular 16+), `OnPush` (manual), or default (Zone.js full app). The model determines when the component re-renders.
- Distinguish standalone components (Angular 14+; default in 17+) from NgModule-based components - they have different bootstrap and import surfaces.
- For DI, identify the providing scope: app-level (`providedIn: 'root'`), module, route-scoped, component-scoped. Each gives a different instance lifecycle.
- For RxJS, name the observable's hot/cold semantics and the subscription cleanup mechanism (`async` pipe, `takeUntilDestroyed`, manual `unsubscribe`). Memory leaks are common.
- For routing, identify guards (`canActivate`, `canDeactivate`, `canMatch`), resolvers, and lazy-loaded routes.

## Patterns

### Change Detection Model

| Mode                | Trigger                                                                                          | What to flag                                                                                                                  |
| ------------------- | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- |
| Default (Zone.js)   | Any async event in the app (DOM events, HTTP, timers) triggers full app CD                        | Performance cliff in large apps; mutating arrays/objects in place still triggers CD via Zone, but template `==` comparison may miss |
| `OnPush`            | Input reference change, event from this component, observable emits via `async` pipe            | Mutating an input object in place does NOT trigger CD; replace the reference                                                  |
| Signal-based        | Signal mutations within the component                                                            | Angular 16+ signals; full zoneless mode in Angular 18+ (`provideExperimentalZonelessChangeDetection`)                         |

### Signals (Angular 16+)

- `signal(initial)`: writable; access via `count()`, mutate via `count.set(5)` or `count.update(n => n + 1)`.
- `computed(() => signal())`: derived signal; auto-tracks dependencies.
- `effect(() => { ... })`: runs on signal changes; lifecycle-aware (cleaned up on injector destroy). Must be in injection context (constructor, field initializer, or `inject()`).
- `signal.asReadonly()`: expose-only; consumers cannot write.
- `linkedSignal` (Angular 19+): a signal whose value is computed but writable.
- `model()` (Angular 17+): two-way binding signal: `count = model<number>(0)` exposes `count` (signal) and `count.set` for `[(count)]`.

### Standalone Components

- `@Component({ standalone: true, imports: [CommonModule, OtherComponent] })` - no NgModule needed.
- Imports list specifies what the template can use (other components, directives, pipes).
- Bootstrap: `bootstrapApplication(AppComponent, { providers: [...] })`.
- Routes: `provideRouter(routes)`. Lazy: `loadComponent: () => import('./feature').then(m => m.FeatureComponent)`.
- `providedIn: 'root'` services are tree-shakable; module-bound services are not.

### Dependency Injection Hierarchy

- Angular has a hierarchical injector: app injector -> module injector -> route-level injector -> component injector.
- `providedIn: 'root'` (modern default): single instance for the whole app.
- `@Injectable({ providedIn: 'platform' })`: shared across multiple Angular apps on the same page.
- Provided in route's `providers`: instance created when route activates, destroyed when route leaves.
- Provided in component's `providers`: per-component instance (via `@Component({ providers: [...] })`).
- `inject(Service)` (Angular 14+): functional injection; works in constructor, field initializer, factory function, route guard.

### Component Lifecycle

| Hook               | Fires                                                                          |
| ------------------ | ------------------------------------------------------------------------------ |
| `ngOnChanges`      | Before `ngOnInit` and on every input change; receives `SimpleChanges`          |
| `ngOnInit`         | After first `ngOnChanges`; one-time setup                                      |
| `ngDoCheck`        | Every change detection run; rare, expensive                                    |
| `ngAfterContentInit` | After `<ng-content>` is projected                                            |
| `ngAfterContentChecked` | After every CD pass on projected content                                  |
| `ngAfterViewInit`  | After view (and child views) initialized; `@ViewChild` refs available now      |
| `ngAfterViewChecked` | After every CD pass on the view                                              |
| `ngOnDestroy`      | Before component destroyed; clean up subscriptions, timers, intervals          |

`@ViewChild` is undefined in `ngOnInit` (view not initialized yet); use `ngAfterViewInit` or `viewChild()` signal (Angular 17+).

### RxJS and the async pipe

- Observable: lazy by default; nothing happens until subscribed.
- Hot observable: shares a single underlying source (Subjects, replay, share).
- Cold observable: each subscription gets its own emission stream (HttpClient calls, intervals).
- `async` pipe: subscribes in template, unsubscribes on component destroy. Best practice over manual subscriptions.
- `takeUntilDestroyed()` (Angular 16+): RxJS operator that completes when injection context is destroyed; replaces the legacy `takeUntil(this.destroy$)` pattern.
- Common operators:
  - `map`, `filter`, `tap` - transformation/inspection
  - `switchMap` - cancel previous on new emission (search-as-you-type)
  - `mergeMap` - keep all in flight (parallel)
  - `concatMap` - sequence one after another
  - `exhaustMap` - ignore new emissions while one is in flight (login submit)
- `BehaviorSubject(initial)`: hot, replays last value to new subscribers.
- `signal()` integration with RxJS: `toSignal(observable, { initialValue })` and `toObservable(signal)` for interop.

### HttpClient

- Returns cold observables; subscription triggers the request.
- Multiple subscriptions to the same observable -> multiple HTTP calls. Use `share`, `shareReplay`, or `async` pipe (which subscribes once).
- Interceptors (`HttpInterceptor`): wrap requests; auth token, error handling, logging. Order matters - registered in `provideHttpClient(withInterceptors([...]))`.
- `HttpResource` (Angular 19+ experimental): signal-based wrapper.

### Routing

- `provideRouter(routes)` or `RouterModule.forRoot(routes)` (legacy NgModule).
- Path matching: full vs prefix; `pathMatch: 'full'` for exact match (common on root redirects).
- Guards (functional or class-based):
  - `canActivate`: before route activation
  - `canDeactivate`: before leaving (unsaved-changes confirmation)
  - `canMatch`: before path matching (lazy loading; can choose between routes)
  - `resolve`: pre-fetch data before activation; component sees data via `route.data` or `route.paramMap`
- Lazy loading (standalone): `loadComponent: () => import(...)` on a route.
- Route data and params: `inject(ActivatedRoute).paramMap` (Observable) or `injectParam('id')` patterns.

### Forms

- Two systems: Template-driven (`FormsModule`, `[(ngModel)]`) and Reactive (`ReactiveFormsModule`, `FormControl`/`FormGroup`/`FormArray`).
- Reactive: explicit, type-safe (with `nonNullable`), unit-testable.
- `Validators.required`, `Validators.email`, custom validators returning `ValidationErrors | null`.
- `valueChanges` and `statusChanges` are observables.

### Pipes and Directives

- Pure pipes (default): only re-run on input reference change. Mutating an array does not re-run; produce a new array.
- Impure pipes (`pure: false`): re-run every CD; expensive.
- Built-in pipes: `async`, `date`, `currency`, `number`, `percent`, `keyvalue`, `slice`, `json`, `i18nPlural`.
- Structural directives (`*ngIf`, `*ngFor`, `*ngSwitch`): manipulate DOM. New control flow (Angular 17+): `@if`, `@for`, `@switch` block syntax.
- Attribute directives (`[ngClass]`, `[ngStyle]`): modify behavior/appearance of an existing element.

### Memory Leak Patterns

- Manual subscription without `unsubscribe`: `this.foo$.subscribe(...)` in `ngOnInit` without `takeUntilDestroyed` or `ngOnDestroy` cleanup.
- Long-running timers (`setInterval`, RxJS `interval`) without cleanup.
- DOM event listeners attached without `Renderer2.listen` (which auto-cleans).

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Change detection mode (Default / OnPush / Signal / Zoneless)
- Standalone vs NgModule-based component
- DI providers and scope
- Lifecycle hooks implemented
- For routing: guards and resolvers leading to this route
- RxJS subscription cleanup mechanism

**Into "Non-Obvious Behavior":**

- `OnPush` not detecting in-place mutations
- Cold observable triggering one HTTP request per subscription
- `@ViewChild` undefined before `ngAfterViewInit`
- Pure pipe not re-running on array mutation
- `effect()` running on every signal change including cascades
- `inject()` failing outside injection context

**Into "Key Invariants":**

- DI scope determines instance lifetime
- `async` pipe handles subscribe and unsubscribe
- View queries (`@ViewChild`, `viewChild()`) available only after `ngAfterViewInit`
- Pure pipes re-run only on reference change

**Into "Change Impact Preview":**

- Switching to `OnPush`: every input mutation that mutated in place will silently stop triggering re-render
- Adding a service to a component's `providers`: gets a new instance; previously-shared state is broken
- Migrating from RxJS to signals: subscription patterns change; `async` pipe replaced with direct `()` call
- Adding a route guard: cascades to every child route unless `canActivate` is overridden
- Removing `takeUntilDestroyed`: subscription leaks until component reload

## Avoid

- Treating `OnPush` as a free perf win - in-place mutations break it silently
- Recommending manual subscriptions where `async` pipe works
- Ignoring `inject()` injection context rules - it cannot be called from arbitrary functions
- Confusing structural and attribute directives
- Glossing over hot/cold observable distinction when `HttpClient` is involved
- Saying "signals replace RxJS" - they coexist; signals for state, RxJS for streams/events
