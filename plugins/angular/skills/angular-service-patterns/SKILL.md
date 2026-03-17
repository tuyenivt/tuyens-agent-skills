---
name: angular-service-patterns
description: Angular injectable services - DI hierarchy, providedIn scoping, HTTP interceptors, functional interceptors, state services, and HttpClient patterns for Angular 21+.
metadata:
  category: frontend
  tags: [angular, services, dependency-injection, httpinterceptor, httpclient, di-hierarchy]
user-invocable: false
---

# Angular Service Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing service architecture for data fetching, state management, or business logic
- Choosing the correct DI scope for a service (`providedIn: 'root'` vs component-level)
- Implementing HTTP interceptors for auth tokens, logging, or error handling
- Setting up HttpClient patterns with proper error handling and typing
- Reviewing service design for testability and correctness

## Rules

- Services must be `@Injectable()` with explicit scope (`providedIn: 'root'` for singletons)
- HttpClient calls must handle errors and return typed responses
- Use functional interceptors (not class-based HttpInterceptor)
- Never subscribe to observables in services unless managing long-lived subscriptions - return observables and let components subscribe
- Separate data services (HTTP calls) from state services (signal stores)
- Services should be stateless where possible; stateful services must use signals

## Patterns

### Service Scoping

| Scope                 | When to Use                               | Declaration                           |
| --------------------- | ----------------------------------------- | ------------------------------------- |
| Root (singleton)      | Shared state, auth, HTTP wrappers         | `providedIn: 'root'`                  |
| Component (transient) | Component-specific state, form state      | `providers: [MyService]` in component |
| Feature (lazy module) | Feature-scoped services loaded with route | `providers` in route config           |

### Data Service (HTTP)

```typescript
@Injectable({ providedIn: "root" })
export class UserService {
  private readonly http = inject(HttpClient);
  private readonly baseUrl = "/api/users";

  getUsers(params?: UserFilters): Observable<PaginatedResponse<User>> {
    return this.http.get<PaginatedResponse<User>>(this.baseUrl, {
      params: this.buildParams(params),
    });
  }

  getUser(id: string): Observable<User> {
    return this.http.get<User>(`${this.baseUrl}/${id}`);
  }

  createUser(data: CreateUserDto): Observable<User> {
    return this.http.post<User>(this.baseUrl, data);
  }

  updateUser(id: string, data: UpdateUserDto): Observable<User> {
    return this.http.put<User>(`${this.baseUrl}/${id}`, data);
  }

  deleteUser(id: string): Observable<void> {
    return this.http.delete<void>(`${this.baseUrl}/${id}`);
  }

  private buildParams(filters?: UserFilters): HttpParams {
    let params = new HttpParams();
    if (filters?.search) params = params.set("search", filters.search);
    if (filters?.role) params = params.set("role", filters.role);
    if (filters?.page) params = params.set("page", filters.page.toString());
    return params;
  }
}
```

### State Service (Signal-Based)

```typescript
@Injectable({ providedIn: "root" })
export class NotificationService {
  private readonly _notifications = signal<Notification[]>([]);

  readonly notifications = this._notifications.asReadonly();
  readonly unreadCount = computed(
    () => this._notifications().filter((n) => !n.read).length,
  );
  readonly hasUnread = computed(() => this.unreadCount() > 0);

  add(notification: Omit<Notification, "id" | "read" | "createdAt">): void {
    const newNotification: Notification = {
      ...notification,
      id: crypto.randomUUID(),
      read: false,
      createdAt: new Date(),
    };
    this._notifications.update((list) => [newNotification, ...list]);
  }

  markAsRead(id: string): void {
    this._notifications.update((list) =>
      list.map((n) => (n.id === id ? { ...n, read: true } : n)),
    );
  }

  dismiss(id: string): void {
    this._notifications.update((list) => list.filter((n) => n.id !== id));
  }

  clear(): void {
    this._notifications.set([]);
  }
}
```

### Functional HTTP Interceptors

```typescript
// interceptors/auth.interceptor.ts
export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const token = authService.getToken();

  if (token) {
    req = req.clone({
      setHeaders: { Authorization: `Bearer ${token}` },
    });
  }

  return next(req);
};

// interceptors/error.interceptor.ts
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const router = inject(Router);
  const notificationService = inject(NotificationService);

  return next(req).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status === 401) {
        router.navigate(["/auth/login"]);
      } else if (error.status === 403) {
        notificationService.add({
          type: "error",
          message: "You do not have permission to perform this action",
        });
      } else if (error.status >= 500) {
        notificationService.add({
          type: "error",
          message: "An unexpected error occurred. Please try again.",
        });
      }
      return throwError(() => error);
    }),
  );
};

// interceptors/logging.interceptor.ts
export const loggingInterceptor: HttpInterceptorFn = (req, next) => {
  const startTime = performance.now();

  return next(req).pipe(
    tap({
      next: () => {
        const duration = Math.round(performance.now() - startTime);
        console.log(`${req.method} ${req.url} completed in ${duration}ms`);
      },
      error: (error: HttpErrorResponse) => {
        console.error(`${req.method} ${req.url} failed with ${error.status}`);
      },
    }),
  );
};

// Register in app config
export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(
      withInterceptors([authInterceptor, errorInterceptor, loggingInterceptor]),
    ),
  ],
};
```

### DI Hierarchy and Injection Tokens

```typescript
// Define injection token for configuration
export const API_BASE_URL = new InjectionToken<string>("API_BASE_URL");

// Provide in app config
export const appConfig: ApplicationConfig = {
  providers: [{ provide: API_BASE_URL, useValue: "https://api.example.com" }],
};

// Use in service
@Injectable({ providedIn: "root" })
export class ApiService {
  private readonly baseUrl = inject(API_BASE_URL);
  private readonly http = inject(HttpClient);

  get<T>(path: string): Observable<T> {
    return this.http.get<T>(`${this.baseUrl}${path}`);
  }
}
```

### Component-Scoped Service

```typescript
// Service scoped to a component instance
@Injectable() // no providedIn - must be provided by component
export class FormStateService {
  private readonly _isDirty = signal(false);
  private readonly _isSubmitting = signal(false);

  readonly isDirty = this._isDirty.asReadonly();
  readonly isSubmitting = this._isSubmitting.asReadonly();

  markDirty(): void {
    this._isDirty.set(true);
  }
  markClean(): void {
    this._isDirty.set(false);
  }
  startSubmit(): void {
    this._isSubmitting.set(true);
  }
  endSubmit(): void {
    this._isSubmitting.set(false);
  }
}

@Component({
  providers: [FormStateService], // each instance gets its own
})
export class EditUserComponent {
  private readonly formState = inject(FormStateService);
}
```

### Error Handling in Services

```typescript
@Injectable({ providedIn: "root" })
export class ProductService {
  private readonly http = inject(HttpClient);

  getProduct(id: string): Observable<Product> {
    return this.http.get<Product>(`/api/products/${id}`).pipe(
      catchError((error: HttpErrorResponse) => {
        if (error.status === 404) {
          return throwError(() => new Error(`Product ${id} not found`));
        }
        return throwError(() => new Error("Failed to load product"));
      }),
    );
  }
}
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Service Architecture

**Stack:** {detected framework}

### Services

| Service          | Scope       | Type     | Dependencies          |
| ---------------- | ----------- | -------- | --------------------- |
| {serviceName}    | Root        | Data     | HttpClient            |
| {serviceName}    | Root        | State    | -                     |
| {serviceName}    | Component   | Form     | -                     |

### Interceptors

| Interceptor      | Purpose              | Order |
| ---------------- | -------------------- | ----- |
| {name}           | {what it does}       | {1-N} |

### Injection Tokens

| Token            | Type     | Purpose                    |
| ---------------- | -------- | -------------------------- |
| {TOKEN_NAME}     | {type}   | {what it configures}       |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Class-based HTTP interceptors (use functional `HttpInterceptorFn`)
- Services without explicit scope (always specify `providedIn` or provide in component)
- Subscribing to observables in services and storing results in mutable properties (use signals)
- Circular service dependencies (A injects B, B injects A)
- Using `any` as HTTP response type (always type responses)
- Catch-all error handling that swallows errors silently (always rethrow or handle explicitly)
- Providing root-scoped services in component providers (creates duplicate instances)
- Mixing data fetching and state management in a single service (separate concerns)
