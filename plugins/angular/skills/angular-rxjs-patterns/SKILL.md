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
- Pick the flattening operator by cancellation semantics (see table).
- Handle errors so the UI shows a state; never swallow into `EMPTY` silently.
- Multicast shared HTTP/state with `shareReplay({ bufferSize: 1, refCount: true })`.
- Prefer signals for component-local state; keep RxJS for streams and complex async timing.

## Patterns

### Subscription cleanup

**Bad** - leaks on destroy:

```typescript
ngOnInit() {
  this.userService.getUsers().subscribe(users => this.users = users);
}
```

**Good** - pick one:

```typescript
// async pipe (template)
users$ = this.userService.getUsers();

// toSignal (preferred for one-shot HTTP)
users = toSignal(this.userService.getUsers());

// takeUntilDestroyed (imperative side effects)
constructor() {
  this.notifications$
    .pipe(takeUntilDestroyed())          // auto-injects DestroyRef in injection context
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
// search: cancel stale requests
results$ = this.searchControl.valueChanges.pipe(
  debounceTime(300),
  distinctUntilChanged(),
  filter(t => t.length >= 2),
  switchMap(t => this.searchService.search(t)),
);

// submit: ignore clicks while in-flight
submit$ = new Subject<void>();
constructor() {
  this.submit$.pipe(
    exhaustMap(() => this.paymentService.process(this.formData())),
    takeUntilDestroyed(),
  ).subscribe({ next: r => this.onSuccess(r), error: e => this.onError(e) });
}
```

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
// combineLatest: re-emits on any change (live dashboards)
dashboard$ = combineLatest({ users: users$, orders: orders$ });

// forkJoin: waits for all to complete (one-shot init)
initial$ = forkJoin({ users: users$, categories: categories$ });
```

### RxJS vs signals

| Use Case                              | Prefer          | Reason                              |
| ------------------------------------- | --------------- | ----------------------------------- |
| Component-local state                 | signal          | No subscription management          |
| Derived values                        | computed()      | Automatic dependency tracking       |
| One-shot HTTP                         | toSignal()      | Convert at component edge           |
| Signal-dependent async (Angular 19+)  | resource()      | Built-in loading/error states       |
| Streams (WebSocket, events)           | RxJS            | Continuous event streams            |
| Complex timing (retry, debounce)      | RxJS            | Operators handle timing             |

## Output Format

Consuming workflow skills depend on this structure.

```
## RxJS Assessment

**Stack:** {detected framework}
**Signal migration:** {Not started | Partial | Complete}

### Observable Patterns

| Observable          | Source          | Flattening      | Cleanup           |
| ------------------- | --------------- | --------------- | ----------------- |
| {name}              | {HTTP/Subject}  | {switchMap/etc} | {async/toSignal}  |

### Subscription Management

| Component           | Strategy              | Issues         |
| ------------------- | --------------------- | -------------- |
| {component}         | {async/toSignal/take} | {None/Leak}    |

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if RxJS usage is correct - do not omit this section silently}
```

## Avoid

- `switchMap` for mutations (cancels in-flight saves) -- use `concatMap` or `exhaustMap`.
- `mergeMap` for search (stale results overwrite latest) -- use `switchMap`.
- Nested `subscribe()` inside `subscribe()` -- use a flattening operator.
- `catchError(() => EMPTY)` without surfacing state to the user.
- `shareReplay` without `refCount: true` (subscription never drops, blocks GC).
- `Subject` for component-local state a signal would handle.
