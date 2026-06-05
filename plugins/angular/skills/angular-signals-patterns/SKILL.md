---
name: angular-signals-patterns
description: Angular Signals - signal/computed/effect, toSignal/toObservable bridge, signal inputs, resource(), linkedSignal, signal services.
metadata:
  category: frontend
  tags: [angular, signals, computed, effect, reactive, state, toSignal]
user-invocable: false
---

# Angular Signals Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Component-local reactive state and derived values
- Bridging RxJS observables and signals
- Side effects triggered by signal changes
- Migrating BehaviorSubject-based component state to signals

## Rules

- Signals are the default for new component state; prefer over BehaviorSubject.
- `computed()` for derived state; `effect()` only for true side effects (DOM, storage, logging, third-party sync).
- Treat signal values as immutable - always pass a new reference on update; deep mutation does not notify.
- `toSignal()` requires `initialValue` or `requireSync: true` unless the source emits synchronously. It subscribes once and unsubscribes on injector destroy.
- Signal reads in templates auto-mark OnPush components dirty - no `markForCheck()` needed.
- Services expose signals via `.asReadonly()`; keep writable signals private.
- No circular dependencies between computed signals.

## Patterns

### Signal Inputs / Outputs / Model (17.1+)

Replace `@Input()` / `@Output()` with signal-based equivalents:

```typescript
@Component({...})
export class UserCard {
  user = input.required<User>();              // ReadonlySignal<User>
  highlighted = input(false);                 // ReadonlySignal<boolean> with default
  selected = output<User>();                  // emits via this.selected.emit(user)
  draft = model<string>('');                  // two-way: draft() reads, draft.set(v) writes; parent: [(draft)]="x"
}
```

`input.required<T>()` raises a compile-time error if the parent forgets the binding. Reads outside templates must be in a reactive context (`computed`, `effect`) or after construction - reading an `input` in `constructor()` returns `undefined` for required inputs until the first CD pass.

### Updating

```typescript
count.set(5);
count.update((c) => c + 1);

// Bad - mutation does not notify
user().name = "Bob";
items().push(newItem);

// Good - new reference (deep updates spread each level)
user.update((u) => ({ ...u, profile: { ...u.profile, name: "Bob" } }));
items.update((list) => [...list, newItem]);
```

### Computed vs Effect

```typescript
// Bad - effect synchronizing derived state
effect(() => this.double.set(this.count() * 2));

// Good - computed
double = computed(() => this.count() * 2);
```

`effect()` is reserved for side effects outside the signal graph (DOM, storage, third-party libraries):

```typescript
effect(() => localStorage.setItem("theme", this.theme()));

effect((onCleanup) => {
  const id = setInterval(() => this.tick(), 1000);
  onCleanup(() => clearInterval(id));
});
```

`untracked()` reads a signal inside a reactive context **without** subscribing to it - used to read config or break dep cycles without re-triggering on every change:

```typescript
effect(() => {
  // re-runs only when `selectedId` changes; reading `config()` here does not subscribe
  const id = this.selectedId();
  this.analytics.track('select', { id, traceId: untracked(() => this.config().traceId) });
});
```

### toSignal / toObservable

```typescript
// Async source - initialValue required
user = toSignal(this.userService.getUser(id), { initialValue: null });

// Synchronous source (BehaviorSubject, store selector)
count = toSignal(this.store.select(selectCount), { requireSync: true });

// Signal -> observable to apply RxJS operators, then back
search = signal("");
results = toSignal(
  toObservable(this.search).pipe(
    debounceTime(300),
    filter((t) => t.length >= 2),
    switchMap((t) => this.searchService.search(t)),
  ),
  { initialValue: [] },
);
```

### resource() - Async Data (stable since Angular 20)

Prefer over manual `toSignal + switchMap` when async data is driven by signal inputs. Exposes `status`, `value`, `error` signals. (Experimental in Angular 19; for HTTP-specific use, see `httpResource` in `angular-data-fetching`.)

```typescript
// Single signal input
productId = input.required<string>();
productResource = resource({
  request: () => this.productId(),
  loader: ({ request: id }) => firstValueFrom(this.api.getProduct(id)),
});

// Multiple signal inputs - return a composite object
filters = signal({ category: "all" });
search = signal("");
productsResource = resource({
  request: () => ({ category: this.filters().category, q: this.search() }),
  loader: ({ request, abortSignal }) =>
    firstValueFrom(this.api.search(request, { signal: abortSignal })),
});
```

For debounced inputs, debounce upstream first then feed the debounced signal into `request`. Use `productsResource.reload()` to force a refetch.

### linkedSignal (Angular 19+)

Writable signal that resets when a source signal changes - use when a selection must follow upstream changes.

```typescript
selectedProductId = linkedSignal(() => this.products()[0]?.id ?? "");
// User can override; resets when products() changes
```

### BehaviorSubject → Signal Migration

| BehaviorSubject               | Signal equivalent                            |
| ----------------------------- | -------------------------------------------- |
| `new BehaviorSubject(v)`      | `signal(v)`                                  |
| `subj.next(v)`                | `sig.set(v)`                                 |
| `subj.value`                  | `sig()` (read)                               |
| `subj.asObservable()`         | `toObservable(sig)` (for RxJS consumers)     |
| `subj.pipe(map(...))`         | `computed(() => fn(sig()))`                  |
| Template `{{ subj$ \| async }}` | Template `{{ sig() }}`                      |

When external consumers still need an observable (e.g., RxJS-heavy effects), bridge with `toObservable(sig)` rather than keeping both side by side.

### Effect Injection Context

`effect()` must run in an injection context - field initializer, `constructor()`, or `runInInjectionContext`. Calling `effect()` from `ngOnInit` throws `NG0203`. To register an effect after construction, capture an injector: `private inj = inject(Injector)`, then `runInInjectionContext(this.inj, () => effect(...))`.

### Signal-Based Service

```typescript
@Injectable({ providedIn: "root" })
export class FeatureFlagsService {
  private readonly _flags = signal<Record<string, boolean>>({});
  readonly flags = this._flags.asReadonly();
  readonly isEnabled = (key: string) => computed(() => this._flags()[key] ?? false);

  set(key: string, value: boolean): void {
    this._flags.update((f) => ({ ...f, [key]: value }));
  }
}
```

Writable signals stay private; consumers read via `.asReadonly()`. For service patterns with domain-specific examples (cart, auth), see `angular-state-patterns` and `angular-service-patterns`.

## Output Format

```
## Signals Architecture

**Angular version:** {detected}

### Signals

| Signal       | Type                                                            | Scope                | Source                              |
| ------------ | --------------------------------------------------------------- | -------------------- | ----------------------------------- |
| {name}       | Writable | Computed | Bridged | Linked | Resource          | Component | Service  | signal() | computed() | toSignal() | linkedSignal() | resource() |

### Resources (if any)

| Resource | Request inputs        | Loader                  | Reads          |
| -------- | --------------------- | ----------------------- | -------------- |
| {name}   | {signal deps}         | {service.method(...)}   | value/status   |

### Effects

| Purpose      | Triggers      | Cleanup |
| ------------ | ------------- | ------- |
| {desc}       | {signal deps} | Yes | No |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

Omit sections without entries; omit `Issues Found` for greenfield design.

## Avoid

- `effect()` that writes to other signals (use `computed()` / `linkedSignal`)
- Calling `effect()` outside an injection context - throws `NG0203`
- Circular computed dependencies
- Manual observable subscriptions where `toSignal()` fits
