---
name: angular-rxjs-patterns
description: Review Angular RxJS - subscription cleanup, flattening operators, error handling, multicasting, signals interop.
metadata:
  category: frontend
  tags: [angular, rxjs, async-pipe, takeUntilDestroyed, switchmap, observables, subscription]
user-invocable: false
---

# Angular RxJS Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Observables in Angular components or services
- Choosing a flattening operator (switchMap/mergeMap/concatMap/exhaustMap)
- Subscription cleanup, multicasting, error handling
- Deciding between RxJS and signals

## Rules

- Never subscribe in components without cleanup. Use `async` pipe, `toSignal()`, or `takeUntilDestroyed()`.
- Subscribe results must never go into a mutable field (`this.x = value`) - convert via `toSignal()` or `async` pipe.
- Pick the flattening operator by cancellation semantics (see table).
- Surface errors to the UI; never swallow into `EMPTY` silently.
- Multicast shared HTTP/state with `shareReplay({ bufferSize: 1, refCount: true })`.
- Prefer signals for component-local state; keep RxJS for streams and complex async timing.

## Patterns

### Subscription cleanup

**Bad** - leaks on destroy, mutable field:

```typescript
ngOnInit() {
  this.userService.getUsers().subscribe(users => this.users = users);
}
```

**Good** - pick one:

```typescript
// async pipe (template) or toSignal (preferred for one-shot HTTP)
users = toSignal(this.userService.getUsers(), { initialValue: [] });

// takeUntilDestroyed for imperative side effects
constructor() {
  this.notifications$
    .pipe(takeUntilDestroyed())  // auto-injects DestroyRef in injection context
    .subscribe(n => this.showToast(n));
}
```

Outside an injection context, pass `DestroyRef`: `takeUntilDestroyed(inject(DestroyRef))`.

### Flattening operator selection

| Operator     | Behavior                          | Use for                                          |
| ------------ | --------------------------------- | ------------------------------------------------ |
| `switchMap`  | Cancels previous inner observable | Search, autocomplete, navigation (latest wins)   |
| `mergeMap`   | Runs in parallel                  | Independent actions (batch delete, favorite)     |
| `concatMap`  | Queues sequentially               | Order matters (sequential saves)                 |
| `exhaustMap` | Ignores new until current done    | Prevent double-submit (login, payment)           |

```typescript
// search: cancel stale requests (debounce + switchMap)
results$ = this.searchControl.valueChanges.pipe(
  debounceTime(300),
  distinctUntilChanged(),
  filter(t => t.length >= 2),
  switchMap(t => this.searchService.search(t)),
);

// submit: ignore clicks while in-flight
constructor() {
  this.submit$.pipe(
    exhaustMap(() => this.paymentService.process(this.formData())),
    takeUntilDestroyed(),
  ).subscribe({ next: r => this.onSuccess(r), error: e => this.onError(e) });
}
```

Captured component state (e.g., `this.formData()`) inside `exhaustMap`/`switchMap` reads at emission time - prefer a signal read to avoid stale closures.

### Error handling

Surface error state to the template; do not swallow.

```typescript
state = signal<'loading' | 'error' | 'success' | 'empty'>('loading');

load() {
  this.state.set('loading');
  this.userService.getUsers().pipe(takeUntilDestroyed()).subscribe({
    next: users => {
      this.users.set(users);
      this.state.set(users.length ? 'success' : 'empty');
    },
    error: err => {
      this.errorMessage.set(err.message ?? 'Failed to load users');
      this.state.set('error');
    },
  });
}
```

Retry transient failures with backoff:

```typescript
this.http.get<User[]>('/api/users').pipe(
  retry({ count: 3, delay: (_, n) => timer(2 ** n * 1000) }),
);
```

### Multicasting

```typescript
readonly config$ = this.http.get<AppConfig>('/api/config').pipe(
  shareReplay({ bufferSize: 1, refCount: true }),  // refCount lets GC reclaim when unused
);
```

### Combining

```typescript
combineLatest({ users: users$, orders: orders$ });  // re-emits on any change (live)
forkJoin({ users: users$, categories: categories$ }); // waits for all to complete (one-shot)
```

### RxJS vs signals

| Use Case                              | Prefer          | Reason                              |
| ------------------------------------- | --------------- | ----------------------------------- |
| Component-local state                 | signal          | No subscription management          |
| Derived values                        | computed()      | Automatic dependency tracking       |
| One-shot HTTP                         | toSignal()      | Convert at component edge           |
| Signal-dependent async (19+)          | resource()      | Built-in loading/error states       |
| Streams (WebSocket, events)           | RxJS            | Continuous event streams            |
| Complex timing (retry, debounce)      | RxJS            | Operators handle timing             |

## Output Format

```
## RxJS Assessment

### Observable Patterns

| Observable          | Source          | Flattening      | Cleanup           |
| ------------------- | --------------- | --------------- | ----------------- |
| {name}              | {HTTP/Subject}  | {switchMap/etc} | {async/toSignal}  |

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

Severity: **High** = leak, lost data, or broken UX (wrong operator on mutations, missing cleanup, subscribe-to-field). **Medium** = wrong operator with correct UX, missing retry/error surfacing. **Low** = style (e.g., redundant `Subject` where signal fits).

State "No issues found" explicitly when usage is correct.

## Avoid

- Nested `subscribe()` inside `subscribe()` - use a flattening operator.
- `catchError(() => EMPTY)` without surfacing state to the user.
- `shareReplay` without `refCount: true` (subscription never drops, blocks GC).
- `Subject` for component-local state a signal would handle.
