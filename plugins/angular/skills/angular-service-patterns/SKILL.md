---
name: angular-service-patterns
description: Angular services - DI scoping (providedIn vs component), functional HTTP interceptors, signal-based state services, HttpClient typing.
metadata:
  category: frontend
  tags: [angular, services, dependency-injection, httpinterceptor, httpclient, di-hierarchy]
user-invocable: false
---

# Angular Service Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing service architecture (data fetching, state, business logic)
- Choosing DI scope (`providedIn: 'root'` vs component-level)
- Implementing functional HTTP interceptors
- Reviewing service design for typing and testability

## Rules

- `@Injectable` with explicit scope: `providedIn: 'root'` for singletons, no `providedIn` when provided by a component
- Separate data services (HTTP) from state services (signals); never mix
- HttpClient calls return typed `Observable<T>` - never `any`
- Services return observables; components subscribe. Only subscribe inside a service for owned long-lived streams
- State lives in signals exposed via `asReadonly()`; mutations via service methods
- Interceptors are functional (`HttpInterceptorFn`), not class-based

## Patterns

### Service Scoping

| Scope                 | When                                      | Declaration                           |
| --------------------- | ----------------------------------------- | ------------------------------------- |
| Root (singleton)      | Shared state, auth, HTTP wrappers         | `providedIn: 'root'`                  |
| Component (transient) | Per-instance state (form, dialog)         | `providers: [Svc]` in component       |
| Feature (lazy route)  | Feature-scoped, loaded with route         | `providers` in route config           |

### Data Service

```typescript
@Injectable({ providedIn: "root" })
export class UserService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = "/api/users";

  list(filters?: UserFilters): Observable<PaginatedResponse<User>> {
    return this.http.get<PaginatedResponse<User>>(this.baseUrl, { params: toParams(filters) });
  }

  get(id: string): Observable<User> {
    return this.http.get<User>(`${this.baseUrl}/${id}`);
  }

  create(data: CreateUserDto): Observable<User> {
    return this.http.post<User>(this.baseUrl, data);
  }
}
```

### Signal-Based State Service

```typescript
@Injectable({ providedIn: "root" })
export class NotificationService {
  private readonly _items = signal<Notification[]>([]);

  readonly items = this._items.asReadonly();
  readonly unreadCount = computed(() => this._items().filter((n) => !n.read).length);

  add(input: Omit<Notification, "id" | "read">): void {
    const item: Notification = { ...input, id: crypto.randomUUID(), read: false };
    this._items.update((list) => [item, ...list]);
  }

  markRead(id: string): void {
    this._items.update((list) => list.map((n) => (n.id === id ? { ...n, read: true } : n)));
  }
}
```

### Component-Scoped Service

Omit `providedIn` and provide in the component - each instance gets a fresh service. Use for form, dialog, or wizard state tied to a component lifetime.

```typescript
@Injectable()
export class FormStateService {
  private readonly _dirty = signal(false);
  readonly dirty = this._dirty.asReadonly();
  markDirty(): void { this._dirty.set(true); }
}

@Component({ providers: [FormStateService] })
export class EditUserComponent {
  private readonly formState = inject(FormStateService);
}
```

### Functional Interceptors

```typescript
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const token = inject(AuthService).getToken();
  return next(token ? req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }) : req);
};

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401) router.navigate(["/auth/login"]);
      return throwError(() => error);
    }),
  );
};

// app.config.ts - order matters: auth runs before error
export const appConfig: ApplicationConfig = {
  providers: [provideHttpClient(withInterceptors([authInterceptor, errorInterceptor]))],
};
```

### Injection Tokens for Config

```typescript
export const API_BASE_URL = new InjectionToken<string>("API_BASE_URL");

// app.config.ts
providers: [{ provide: API_BASE_URL, useValue: "https://api.example.com" }];

// service
private readonly baseUrl = inject(API_BASE_URL);
```

### Service-Level Error Handling

Use only when a specific failure needs domain meaning beyond the global error interceptor (e.g., 404 -> "not found" entity error).

```typescript
this.http.get<Product>(`/api/products/${id}`).pipe(
  catchError((error: HttpErrorResponse) =>
    throwError(() => new Error(error.status === 404 ? `Product ${id} not found` : "Failed to load product")),
  ),
);
```

## Output Format

```
## Service Architecture

**Stack:** {detected framework}

### Services

| Service       | Scope     | Type   | Dependencies |
| ------------- | --------- | ------ | ------------ |
| {name}        | Root      | Data   | HttpClient   |
| {name}        | Component | State  | -            |

### Interceptors

| Interceptor | Purpose       | Order |
| ----------- | ------------- | ----- |
| {name}      | {what}        | {1-N} |

### Injection Tokens

| Token        | Type   | Purpose       |
| ------------ | ------ | ------------- |
| {TOKEN_NAME} | {type} | {configures}  |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Circular service dependencies (A injects B, B injects A)
- Providing a root-scoped service again in component `providers` (creates duplicate instances)
- Subscribing in a service and caching the result in a plain property (use signals)
- Catch-all error handling that swallows errors silently (rethrow or surface)
- Mixing HTTP calls and state mutation in the same service
