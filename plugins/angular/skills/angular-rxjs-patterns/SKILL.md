---
name: angular-rxjs-patterns
description: RxJS in Angular - async pipe, takeUntilDestroyed, flattening operator selection (switchMap/mergeMap/concatMap), error handling, multicasting, and signals migration path for Angular 21+.
metadata:
  category: frontend
  tags: [angular, rxjs, async-pipe, takeUntilDestroyed, switchmap, observables, subscription]
user-invocable: false
---

# Angular RxJS Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Working with observables in Angular components and services
- Choosing the correct flattening operator (switchMap, mergeMap, concatMap, exhaustMap)
- Managing subscriptions and preventing memory leaks
- Handling errors in observable chains
- Deciding between RxJS and signals for a given use case

## Rules

- Never subscribe manually in components without cleanup - use `async` pipe, `toSignal()`, or `takeUntilDestroyed`
- Choose the correct flattening operator based on cancellation semantics
- Handle errors at the appropriate level - do not let errors propagate to crash the component
- Use `shareReplay` for observables consumed by multiple subscribers
- Prefer signals over observables for component-local state
- Use `takeUntilDestroyed` from `@angular/core/rxjs-interop` for cleanup in components

## Patterns

### Subscription Management

**Bad** - Manual subscribe without cleanup:

```typescript
@Component({})
export class UserListComponent implements OnInit {
  users: User[] = [];

  ngOnInit() {
    this.userService.getUsers().subscribe((users) => {
      this.users = users; // memory leak - no unsubscribe
    });
  }
}
```

**Good** - Option 1: async pipe (template-driven):

```typescript
@Component({
  imports: [AsyncPipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (users$ | async; as users) {
      @for (user of users; track user.id) {
        <app-user-card [user]="user" />
      }
    } @else {
      <app-spinner />
    }
  `,
})
export class UserListComponent {
  private readonly userService = inject(UserService);
  users$ = this.userService.getUsers();
}
```

**Good** - Option 2: toSignal (signal-based):

```typescript
@Component({
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (users(); as users) {
      @for (user of users; track user.id) {
        <app-user-card [user]="user" />
      }
    } @else {
      <app-spinner />
    }
  `,
})
export class UserListComponent {
  private readonly userService = inject(UserService);
  users = toSignal(this.userService.getUsers());
}
```

**Good** - Option 3: takeUntilDestroyed (imperative):

```typescript
@Component({})
export class DashboardComponent {
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit() {
    this.notificationService.notifications$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(notification => {
        this.showToast(notification);
      });
  }
}

// In constructor context, no DestroyRef needed:
constructor() {
  someObservable$
    .pipe(takeUntilDestroyed()) // auto-injects DestroyRef
    .subscribe(value => this.handleValue(value));
}
```

### Flattening Operator Selection

| Operator     | Behavior                          | When to Use                                      |
| ------------ | --------------------------------- | ------------------------------------------------ |
| `switchMap`  | Cancels previous inner observable | Search, autocomplete, navigation (latest wins)   |
| `mergeMap`   | Runs all in parallel              | Independent actions (favorite, delete batch)     |
| `concatMap`  | Queues sequentially               | Order matters (form saves, sequential API calls) |
| `exhaustMap` | Ignores new until current done    | Prevent double-submit (login, payment)           |

**switchMap - Search (cancel previous):**

```typescript
searchResults$ = this.searchControl.valueChanges.pipe(
  debounceTime(300),
  distinctUntilChanged(),
  filter((term) => term.length >= 2),
  switchMap((term) => this.searchService.search(term)), // cancels stale requests
);
```

**concatMap - Sequential saves:**

```typescript
saveAll(items: Item[]): Observable<Item[]> {
  return from(items).pipe(
    concatMap(item => this.http.put<Item>(`/api/items/${item.id}`, item)),
    toArray(),
  );
}
```

**exhaustMap - Prevent double submit:**

```typescript
@Component({
  template: ` <button (click)="submit$.next()">Submit</button> `,
})
export class PaymentComponent {
  submit$ = new Subject<void>();

  private readonly payment$ = this.submit$.pipe(
    exhaustMap(() => this.paymentService.processPayment(this.formData())),
    takeUntilDestroyed(),
  );

  constructor() {
    this.payment$.subscribe({
      next: (result) => this.handleSuccess(result),
      error: (err) => this.handleError(err),
    });
  }
}
```

### Error Handling

**Component-level error handling:**

```typescript
@Component({
  template: `
    @switch (state()) {
      @case ("loading") {
        <app-spinner />
      }
      @case ("error") {
        <app-error-state [message]="errorMessage()" (retry)="load()" />
      }
      @case ("success") {
        <app-user-list [users]="users()" />
      }
      @case ("empty") {
        <app-empty-state message="No users found" />
      }
    }
  `,
})
export class UserPageComponent {
  private readonly userService = inject(UserService);

  state = signal<"loading" | "error" | "success" | "empty">("loading");
  users = signal<User[]>([]);
  errorMessage = signal("");

  constructor() {
    this.load();
  }

  load() {
    this.state.set("loading");
    this.userService
      .getUsers()
      .pipe(takeUntilDestroyed())
      .subscribe({
        next: (users) => {
          this.users.set(users);
          this.state.set(users.length > 0 ? "success" : "empty");
        },
        error: (err) => {
          this.errorMessage.set(err.message ?? "Failed to load users");
          this.state.set("error");
        },
      });
  }
}
```

**Retry with backoff:**

```typescript
getUsers(): Observable<User[]> {
  return this.http.get<User[]>('/api/users').pipe(
    retry({
      count: 3,
      delay: (error, retryCount) => timer(Math.pow(2, retryCount) * 1000),
    }),
  );
}
```

### Multicasting

```typescript
@Injectable({ providedIn: "root" })
export class ConfigService {
  // shareReplay caches the last emission for late subscribers
  readonly config$ = this.http
    .get<AppConfig>("/api/config")
    .pipe(shareReplay({ bufferSize: 1, refCount: true }));

  constructor(private readonly http: HttpClient) {}
}
```

### Combining Observables

```typescript
// combineLatest - wait for all, re-emit on any change
dashboard$ = combineLatest({
  users: this.userService.getUsers(),
  orders: this.orderService.getOrders(),
  stats: this.statsService.getStats(),
});

// forkJoin - wait for all to complete (one-shot)
initialData$ = forkJoin({
  users: this.userService.getUsers(),
  categories: this.categoryService.getCategories(),
});
```

### When to Use RxJS vs Signals

| Use Case                              | Prefer          | Reason                              |
| ------------------------------------- | --------------- | ----------------------------------- |
| Component-local state                 | Signal          | Simpler, no subscription management |
| Derived/computed values               | computed()      | Automatic dependency tracking       |
| HTTP response (one-shot)              | toSignal()      | Convert to signal at component edge |
| Signal-dependent async data           | resource()      | Built-in loading/error states (19+) |
| Streams (WebSocket, events)           | RxJS            | Built for continuous event streams  |
| Complex async flows (retry, debounce) | RxJS            | Operators handle complex timing     |
| Template rendering                    | Signal or async | Both work; signals are simpler      |

## Output Format

Consuming workflow skills depend on this structure.

```
## RxJS Assessment

**Stack:** {detected framework}
**Signal migration:** {Not started | Partial | Complete}

### Observable Patterns

| Observable          | Source          | Flattening     | Cleanup           |
| ------------------- | --------------- | -------------- | ----------------- |
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

- Manual `subscribe()` in components without cleanup (memory leak)
- Using `switchMap` for mutations (cancels in-flight saves)
- Using `mergeMap` for search/autocomplete (stale results appear after current)
- `subscribe()` inside `subscribe()` (nested subscriptions - use flattening operators)
- Catching errors and returning `EMPTY` without notifying the user
- Using `Subject` when a signal would suffice for component-local state
- `shareReplay` without `refCount: true` (prevents garbage collection)
- Subscribing to the same observable multiple times without multicasting
