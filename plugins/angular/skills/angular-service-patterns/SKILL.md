---
name: angular-service-patterns
description: Angular services - DI scoping, functional HTTP interceptors with retry/refresh, signal-based state services, HttpClient typing.
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
- Implementing functional HTTP interceptors (auth, error, retry)
- Reviewing service design for typing and testability

## Rules

- `@Injectable` with explicit scope: `providedIn: 'root'` for singletons; omit for component/route-scoped.
- Prefer separation of data services (HTTP) and state services (signals). Exception: domain-coherent services like `AuthService` legitimately combine HTTP + signal state when the token lifecycle is the domain.
- HttpClient calls return typed `Observable<T>`; never `any`.
- Services return observables; components subscribe via `async`/`toSignal()`. Subscribe inside a service only for owned long-lived streams.
- State lives in signals exposed via `asReadonly()`; mutations via service methods.
- Interceptors are functional (`HttpInterceptorFn`), not class-based.

## Patterns

### Service Scoping

| Scope                 | When                                      | Declaration                     |
| --------------------- | ----------------------------------------- | ------------------------------- |
| Root (singleton)      | Shared state, auth, HTTP wrappers         | `providedIn: 'root'`            |
| Component (transient) | Per-instance state (form, dialog)         | `providers: [Svc]` in component |
| Feature (lazy route)  | Feature-scoped, loaded with route         | `providers` in route config     |

### Data Service

```typescript
@Injectable({ providedIn: "root" })
export class UserService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = inject(API_BASE_URL);

  list(filters?: UserFilters): Observable<PaginatedResponse<User>> {
    return this.http.get<PaginatedResponse<User>>(`${this.baseUrl}/users`, { params: toParams(filters) });
  }

  get(id: string): Observable<User> {
    return this.http.get<User>(`${this.baseUrl}/users/${id}`);
  }
}
```

### `httpResource()` (signal-driven HTTP, 19+/20+)

When the component owns the request inputs as signals, expose data via `httpResource` instead of subscribing manually. Auto-cancels prior requests when inputs change.

```typescript
@Component({...})
export class UserDetailComponent {
  id = input.required<string>();
  user = httpResource<User>(() => `/api/users/${this.id()}`);
  //         ^ value(), status(), error(), isLoading()  - all signals
}
```

Experimental in 19, stable from 20+. For full data-layer patterns (TanStack Query, cache invalidation, optimistic updates), see `angular-data-fetching`.

### Signal-Based State Service

```typescript
@Injectable({ providedIn: "root" })
export class NotificationService {
  private readonly _items = signal<Notification[]>([]);
  readonly items = this._items.asReadonly();
  readonly unreadCount = computed(() => this._items().filter((n) => !n.read).length);

  add(input: Omit<Notification, "id" | "read">): void {
    this._items.update((list) => [{ ...input, id: crypto.randomUUID(), read: false }, ...list]);
  }
}
```

### Hybrid Auth Service (HTTP + State)

Combining HTTP and signal state is appropriate when token lifecycle is the domain.

```typescript
@Injectable({ providedIn: "root" })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly _user = signal<User | null>(null);
  readonly user = this._user.asReadonly();
  readonly isAuthenticated = computed(() => this._user() !== null);
  private accessToken: string | null = null;

  getToken(): string | null { return this.accessToken; }

  login(creds: Credentials): Observable<User> {
    return this.http.post<AuthResponse>("/api/auth/login", creds).pipe(
      tap((res) => { this.accessToken = res.token; this._user.set(res.user); }),
      map((res) => res.user),
    );
  }

  logout(): void {
    this.accessToken = null;
    this._user.set(null);
  }
}
```

### Component-Scoped Service

Omit `providedIn` and declare in component `providers` - each instance gets a fresh service. Use for form/dialog/wizard state tied to component lifetime.

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
  const auth = inject(AuthService);
  const apiBase = inject(API_BASE_URL);
  const token = auth.getToken();
  // Scope token to own origin only
  if (!token || !req.url.startsWith(apiBase)) return next(req);
  return next(req.clone({ setHeaders: { Authorization: `Bearer ${token}` } }));
};

export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  return next(req).pipe(
    retry({
      count: 2,
      delay: (err, attempt) =>
        err.status === 503 || err.status === 0 ? timer(2 ** attempt * 500) : throwError(() => err),
    }),
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401) router.navigate(["/auth/login"]);
      return throwError(() => error);
    }),
  );
};

// app.config.ts - request pipeline runs top-down (auth attaches token first);
// response pipeline runs bottom-up (error catches after retry)
export const appConfig: ApplicationConfig = {
  providers: [provideHttpClient(withInterceptors([authInterceptor, errorInterceptor]))],
};
```

### Token Refresh + Replay (401)

```typescript
export const refreshInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  return next(req).pipe(
    catchError((err: HttpErrorResponse) =>
      err.status === 401
        ? auth.refresh().pipe(switchMap(() => next(req.clone({
            setHeaders: { Authorization: `Bearer ${auth.getToken()}` },
          }))))
        : throwError(() => err),
    ),
  );
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

## Output Format

```
## Service Architecture

**Angular version:** {detected}

### Services

| Service       | Scope     | Type            | Dependencies |
| ------------- | --------- | --------------- | ------------ |
| {name}        | Root      | Data | State | Hybrid | HttpClient   |

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

Omit `Issues Found` for greenfield design. Interceptor order matters: list in execution order (request phase).

## Avoid

- Circular service dependencies (A injects B, B injects A)
- Providing a root-scoped service again in component `providers` (creates duplicate instances)
- Subscribing in a service and caching the result in a plain property (use signals)
- Catch-all error handling that swallows errors silently (rethrow or surface)
- Unconditional token attachment in interceptor (leaks token to third-party hosts)
