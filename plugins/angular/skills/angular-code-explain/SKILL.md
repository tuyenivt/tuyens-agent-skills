---
name: angular-code-explain
description: Explain Angular code - signals, zoneless CD, standalone, DI hierarchy, RxJS/async pipe, lifecycle, routing, forms.
metadata:
  category: frontend
  tags: [explanation, code-understanding, angular, signals, rxjs]
user-invocable: false
---

# Angular Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-code-explain` when stack is Angular.

## When to Use

- Workflow needs Angular-specific explanation for a `.ts` component, service, directive, pipe, guard, interceptor, or module.

## Rules

- Identify the change detection model first (Signal / OnPush / Default-Zone.js / Zoneless). Name both when hybrid (OnPush + signal reads).
- For DI, name the providing scope (`root`, `platform`, route, component) - it determines instance lifetime.
- For async, name the cleanup mechanism (`async` pipe, `toSignal`, `takeUntilDestroyed`, manual).
- Flag standalone vs NgModule. Standalone is default on Angular 19+ - flag missing `standalone: true` only on older versions.
- Note version gates: signals (16+), `inject()` (14+), control flow `@if/@for/@switch` (17+), `model()` (17+), zoneless (18+), `linkedSignal`/`resource()` (19+), `afterNextRender` (16+).

## Patterns

### Change Detection

| Mode         | Re-renders on                                          | Pitfall to flag                                            |
| ------------ | ------------------------------------------------------ | ---------------------------------------------------------- |
| Default-Zone | Any async event app-wide (Zone.js patches)             | Whole-app CD cost in large trees                           |
| `OnPush`     | Input reference change, local event, `async` emission  | In-place mutation of input object silently skips CD        |
| Signal       | Signal read inside template re-reads on `.set/.update` | `effect()` must run in injection context                   |
| Hybrid       | OnPush + signal reads: signal reads auto-mark dirty    | Plain field mutation still does not trigger CD             |
| Zoneless     | Signal-driven only (`provideZonelessChangeDetection`)  | Manual subscriptions don't auto-trigger CD; use `toSignal` |

### Signals + Interop

- `signal(v)` writable: read `s()`, write `s.set(v)` / `s.update(fn)`. Treat values as immutable - mutation does not notify.
- `computed(fn)` derived, auto-tracks reads.
- `effect(fn)` runs on dep change; injection-context only; auto-cleaned on destroy.
- `model<T>()` (17+) two-way binding signal for `[(x)]`.
- `linkedSignal` (19+) computed-but-writable; resets on source change.
- `resource()` (19+) async data driven by signal inputs; exposes `value`/`status`/`error`.
- `toSignal(obs$, { initialValue })`: subscribes once, unsubscribes on injector destroy; without `initialValue` or `requireSync: true` the type is `T | undefined`. Signal reads in template auto-mark OnPush components dirty - no `markForCheck()`.
- `toObservable(sig)` to apply RxJS operators then convert back via `toSignal`.

### Standalone (default 19+)

`@Component({ imports: [Dep, ...] })`. Bootstrap `bootstrapApplication(App, { providers })`. Routes: `provideRouter(routes)`. Lazy: `loadComponent: () => import('./x').then(m => m.X)`.

### DI Hierarchy

App injector -> route injector -> component injector. `providedIn: 'root'` = singleton, tree-shakable. `providedIn: 'platform'` = shared across apps on page. Route `providers` = lifetime of route activation. Component `providers` = per-component instance. `inject()` (14+) works in constructor, field initializer, factory, functional guard - and is preferred; constructor parameter DI is still valid and may appear in legacy code.

### Lifecycle

| Hook              | Fires                                                | Note                                |
| ----------------- | ---------------------------------------------------- | ----------------------------------- |
| `ngOnChanges`     | Before `ngOnInit`, on every input change             | Receives `SimpleChanges`            |
| `ngOnInit`        | After first `ngOnChanges`                            | One-time setup; `@ViewChild` not ready |
| `ngAfterViewInit` | After view + children initialized                    | `@ViewChild` available; prefer `viewChild()` signal |
| `ngOnDestroy`     | Before destroy                                       | Clean timers, manual subs           |
| `afterNextRender` | After client-side render                             | Browser-only; SSR-safe              |

### RxJS and async pipe

- Cold (HttpClient, `interval`): each subscription is its own stream - N subscriptions = N HTTP calls. Use `shareReplay` or single `async` pipe.
- Hot (`Subject`, `BehaviorSubject`, `share`): one shared producer.
- `async` pipe: subscribes in template, unsubscribes on destroy.
- `takeUntilDestroyed()` (16+) replaces `takeUntil(destroy$)` for manual subs.
- Operator intent: `switchMap` (cancel - typeahead), `mergeMap` (parallel), `concatMap` (serial), `exhaustMap` (drop while busy - submit).

### HttpClient and Interceptors

`provideHttpClient(withInterceptors([...]))`. Request pipeline runs top-down (auth attaches first); response pipeline runs bottom-up (error catches last). Cold observable - subscription fires the request.

### Routing

- Guards: `canActivate`, `canMatch` (decide before lazy chunk load), `canDeactivate`, `resolve`.
- Functional guards via `inject()` are the modern form; class-based guards still work.
- `pathMatch: 'full'` for exact match (typical on root redirect).

### Forms

- Reactive (`FormControl`/`FormGroup`/`FormArray`, `nonNullable`) - type-safe; observe via `valueChanges`/`statusChanges`.
- Template-driven (`[(ngModel)]`) - simpler, weaker typing.

### Pipes

- Pure pipe (default) re-runs only on input reference change - array mutation in place won't refresh.
- Impure pipe (`pure: false`) re-runs every CD - expensive.

## Output Format

Emit findings into `task-code-explain` sections. Omit fields that don't apply.

**Flow Context:**

- CD mode (Default-Zone / OnPush / Signal / Hybrid / Zoneless)
- Standalone vs NgModule (only flag if NgModule on Angular 19+, or missing `standalone: true` on 14-18)
- DI providers and scope (omit for leaf components with no providers)
- Lifecycle hooks implemented (omit if none)
- Route guards/resolvers leading here (omit if N/A)
- Async cleanup mechanism

**Non-Obvious Behavior:**

- `OnPush` skipping in-place input mutations
- Cold observable firing one HTTP call per subscription
- `toSignal` requiring `initialValue` or `requireSync`; type widens to `T | undefined` otherwise
- Pure pipes ignoring array mutation
- `effect()`/`inject()` failing outside injection context

**Key Invariants:**

- DI scope = instance lifetime
- `async` pipe / `toSignal` owns subscribe/unsubscribe
- Signal reads in template trigger CD; field mutation does not

**Change Impact Preview:**

- Switching to `OnPush`: in-place mutations stop triggering renders
- Adding component-scoped `providers`: new instance, prior shared state broken
- Migrating RxJS to signals: template `| async` becomes `()`; subscription patterns change
- Adding a parent `canActivate`: cascades to children unless overridden
- Removing `takeUntilDestroyed`: leak until component reload

## Avoid

- Calling `OnPush` a free win - mutation bugs are silent
- Recommending manual subscriptions where `async` pipe / `toSignal` works
- Ignoring `inject()` injection-context rules
- Conflating structural and attribute directives
- Glossing hot/cold semantics when `HttpClient` is involved
- Saying "signals replace RxJS" - signals for state, RxJS for streams
