---
name: angular-code-explain
description: Explain Angular code: signals, zoneless CD, standalone, DI hierarchy, RxJS/async pipe, lifecycle, routing, forms.
metadata:
  category: frontend
  tags: [explanation, code-understanding, angular, signals, rxjs]
user-invocable: false
---

# Angular Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Angular.

## When to Use

- Workflow needs Angular-specific explanation for a `.ts` component, service, directive, pipe, guard, interceptor, or module.

## Rules

- Identify the change detection model first (Signal / OnPush / Default-Zone.js / Zoneless). It dictates when re-renders fire.
- For DI, name the providing scope (`root`, `platform`, route, component) - it determines instance lifetime.
- For RxJS, name hot vs cold and the cleanup mechanism (`async` pipe, `takeUntilDestroyed`, manual).
- Flag standalone vs NgModule - bootstrap and import surfaces differ.
- Note Angular version gates for signals (16+), `model()` (17+), `linkedSignal` (19+), new control flow `@if/@for` (17+), zoneless (18+).

## Patterns

### Change Detection

| Mode         | Triggers re-render on                                  | Pitfall to flag                                            |
| ------------ | ------------------------------------------------------ | ---------------------------------------------------------- |
| Default-Zone | Any async event app-wide (Zone.js patches)             | Whole-app CD cost in large trees                           |
| `OnPush`     | Input reference change, local event, `async` emission  | In-place mutation of input object silently skips CD        |
| Signal       | Signal read inside template re-reads on `.set/.update` | `effect()` must run in injection context                   |
| Zoneless     | Signal-driven only (`provideExperimentalZonelessCD`)   | Manual subscriptions don't auto-trigger CD; use `toSignal` |

### Signals (16+)

- `signal(v)` writable: read `s()`, write `s.set(v)` / `s.update(fn)`.
- `computed(fn)` derived, auto-tracks reads.
- `effect(fn)` runs on dep change; injection-context only; auto-cleaned on destroy.
- `model<T>()` (17+) two-way binding signal for `[(x)]`.
- `linkedSignal` (19+) computed-but-writable.
- Interop: `toSignal(obs$, { initialValue })`, `toObservable(sig)`.

### Standalone (14+, default 17+)

`@Component({ standalone: true, imports: [Dep, ...] })`. Bootstrap `bootstrapApplication(App, { providers })`. Routes: `provideRouter(routes)`. Lazy: `loadComponent: () => import('./x').then(m => m.X)`.

### DI Hierarchy

App injector -> route injector -> component injector. `providedIn: 'root'` = singleton, tree-shakable. `providedIn: 'platform'` = shared across apps on page. Route `providers` = lifetime of route activation. Component `providers` = per-component instance. `inject(T)` (14+) works in constructor, field initializer, factory, functional guard.

### Lifecycle

| Hook              | Fires                                                | Note                                |
| ----------------- | ---------------------------------------------------- | ----------------------------------- |
| `ngOnChanges`     | Before `ngOnInit`, on every input change             | Receives `SimpleChanges`            |
| `ngOnInit`        | After first `ngOnChanges`                            | One-time setup; `@ViewChild` not ready |
| `ngDoCheck`       | Every CD pass                                        | Expensive; avoid                    |
| `ngAfterViewInit` | After view + children initialized                    | `@ViewChild` available here         |
| `ngOnDestroy`     | Before destroy                                       | Clean timers, manual subs           |

Prefer `viewChild()` signal (17+) over `@ViewChild` decorator.

### RxJS and async pipe

- Cold (HttpClient, `interval`): each subscription is its own stream - N subscriptions = N HTTP calls. Use `shareReplay` or single `async` pipe.
- Hot (`Subject`, `BehaviorSubject(init)`, `share`): one shared producer.
- `async` pipe: subscribes in template, unsubscribes on destroy. Default for templates.
- `takeUntilDestroyed()` (16+) replaces `takeUntil(destroy$)` for manual subs.
- Operator intent: `switchMap` (cancel prior - typeahead), `mergeMap` (parallel), `concatMap` (serial), `exhaustMap` (drop while busy - submit).

### HttpClient and Interceptors

- Cold observable; subscription fires the request.
- `provideHttpClient(withInterceptors([...]))` - order matters; interceptors wrap requests (auth, retry, logging).

### Routing

- Guards: `canActivate`, `canDeactivate` (unsaved-changes), `canMatch` (decide before path match; useful for lazy), `resolve` (pre-fetch).
- Functional guards via `inject()` are the modern form.
- `pathMatch: 'full'` for exact match (typical on root redirect).

### Forms

- Reactive (`FormControl`/`FormGroup`/`FormArray`, `nonNullable`) - type-safe, testable; observe via `valueChanges`/`statusChanges`.
- Template-driven (`[(ngModel)]`) - simpler, weaker typing.

### Pipes and Directives

- Pure pipe (default) re-runs only on input reference change - array mutation in place won't refresh; return new array.
- Impure pipe (`pure: false`) re-runs every CD - expensive.
- New block control flow `@if/@for/@switch` (17+) supersedes `*ngIf/*ngFor/*ngSwitch`.

## Output Format

Emit findings into `task-code-explain` sections:

**Flow Context:**

- CD mode (Default-Zone / OnPush / Signal / Zoneless)
- Standalone vs NgModule
- DI providers and scope
- Lifecycle hooks implemented
- Route guards/resolvers leading here
- RxJS cleanup mechanism

**Non-Obvious Behavior:**

- `OnPush` skipping in-place input mutations
- Cold observable firing one HTTP call per subscription
- View queries undefined before `ngAfterViewInit`
- Pure pipes ignoring array mutation
- `effect()`/`inject()` failing outside injection context

**Key Invariants:**

- DI scope = instance lifetime
- `async` pipe owns subscribe/unsubscribe
- Pure pipes refresh only on reference change

**Change Impact Preview:**

- Switching to `OnPush`: in-place mutations stop triggering renders
- Adding component-scoped `providers`: new instance, prior shared state broken
- Migrating RxJS to signals: template `| async` becomes `()`; subscription patterns change
- Adding a parent `canActivate`: cascades to children unless overridden
- Removing `takeUntilDestroyed`: leak until component reload

## Avoid

- Calling `OnPush` a free win - mutation bugs are silent
- Recommending manual subscriptions where `async` pipe works
- Ignoring `inject()` injection-context rules
- Conflating structural and attribute directives
- Glossing hot/cold semantics when `HttpClient` is involved
- Saying "signals replace RxJS" - signals for state, RxJS for streams
