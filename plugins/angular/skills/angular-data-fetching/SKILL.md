---
name: angular-data-fetching
description: Angular data fetching - HttpClient, resource()/httpResource(), TanStack Query for Angular, Apollo GraphQL, SSR transfer cache, cache invalidation.
metadata:
  category: frontend
  tags: [angular, data-fetching, httpclient, resource, tanstack-query, apollo, graphql, ssr, transfer-cache, cache-invalidation]
user-invocable: false
---

# Angular Data Fetching

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing the data layer for a feature (raw HttpClient vs `resource()`/`httpResource()` vs TanStack Query vs Apollo)
- Designing cache, invalidation, optimistic update, infinite pagination, or dependent-query patterns
- Wiring SSR HTTP transfer cache so server-fetched data hydrates without a refetch
- Reviewing a PR that adds HTTP, mutation, or GraphQL calls

## Rules

- One library per concern: pick HttpClient + signals, TanStack Query, or Apollo per app - do not mix two for the same domain.
- Every mutation declares the cache it invalidates. No mutation ships without a written invalidation plan.
- SSR projects with HTTP must wire `provideClientHydration(withHttpTransferCacheOptions({...}))` or expect a double-fetch.
- Query keys are factory-derived (`userKeys.detail(id)`), never inline literals.
- Read URL state via signal-driven primitives (`resource`/`injectQuery` with signal params); do not subscribe to `params` and call `http.get` imperatively.
- Optimistic updates always pair with a rollback in the error path.

## Patterns

### Decision Matrix

| Need                                             | Pick                                        |
| ------------------------------------------------ | ------------------------------------------- |
| One-off HTTP call, fire-and-forget               | `HttpClient` in a service                   |
| Signal-driven async with auto re-fetch on input  | `resource()` (Angular 20+) / `httpResource()` |
| Multi-route cache, mutations, optimistic updates | TanStack Query for Angular                  |
| GraphQL                                          | Apollo Angular                              |
| Full-app state for non-server data               | NgRx / Signal Store (see `angular-state-patterns`) |

### `httpResource()` (Angular 19+/20+)

Signal-driven HTTP primitive. Re-fetches when input signals change; exposes `value`, `status`, `error`, `isLoading` as signals.

```typescript
@Component({...})
export class UserComponent {
  id = input.required<string>();
  user = httpResource<User>(() => `/api/users/${this.id()}`);
  //         ^ value(), status(), error(), isLoading()
}
```

`httpResource` is experimental in Angular 19, stable from 20+. Pin behind a version check when targeting 19.

### `resource()` (Angular 19+/20+)

Lower-level signal-async primitive. Use for non-HTTP loaders (IndexedDB, WebSocket, computed cache hits) or when you need a custom `loader`.

```typescript
favorites = resource({
  request: () => ({ userId: this.userId() }),
  loader: ({ request, abortSignal }) =>
    fetch(`/api/favorites?u=${request.userId}`, { signal: abortSignal }).then((r) => r.json()),
});
```

Aborts the previous request when the request signal changes. Pair with `signal: abortSignal` in `fetch` / `HttpClient.request({ signal })`.

### TanStack Query for Angular (`@tanstack/angular-query-experimental`)

Use when the app needs multi-route cache, automatic background refetch, optimistic updates, infinite queries, or mutation-driven invalidation.

```typescript
// app.config.ts
export const appConfig: ApplicationConfig = {
  providers: [
    provideHttpClient(),
    provideTanStackQuery(new QueryClient({
      defaultOptions: { queries: { staleTime: 60_000, gcTime: 300_000 } },
    })),
  ],
};

// query-keys.ts - factory pattern
export const userKeys = {
  all: ['users'] as const,
  lists: () => [...userKeys.all, 'list'] as const,
  list: (filters: UserFilters) => [...userKeys.lists(), filters] as const,
  details: () => [...userKeys.all, 'detail'] as const,
  detail: (id: string) => [...userKeys.details(), id] as const,
};

// component
@Component({...})
export class UserListComponent {
  private http = inject(HttpClient);
  filters = signal<UserFilters>({ status: 'active' });

  usersQuery = injectQuery(() => ({
    queryKey: userKeys.list(this.filters()),
    queryFn: ({ signal }) => firstValueFrom(this.http.get<User[]>('/api/users', {
      params: toParams(this.filters()),
      // signal aborts the underlying XHR on key change
    })),
  }));
}
```

### Mutations + Invalidation

```typescript
private queryClient = inject(QueryClient);

createUser = injectMutation(() => ({
  mutationFn: (input: CreateUser) => firstValueFrom(this.http.post<User>('/api/users', input)),
  onSuccess: () => this.queryClient.invalidateQueries({ queryKey: userKeys.lists() }),
}));
```

Invalidate **lists**, not the specific entity you mutated - lists are stale, the cache for the new entity is fresh from the response.

### Optimistic Update + Rollback

```typescript
toggleFavorite = injectMutation(() => ({
  mutationFn: (id: string) => firstValueFrom(this.http.post(`/api/favorites/${id}/toggle`, {})),
  onMutate: async (id) => {
    await this.queryClient.cancelQueries({ queryKey: favoriteKeys.list() });
    const previous = this.queryClient.getQueryData<Favorite[]>(favoriteKeys.list());
    this.queryClient.setQueryData<Favorite[]>(favoriteKeys.list(), (old = []) =>
      old.map((f) => (f.id === id ? { ...f, on: !f.on } : f)),
    );
    return { previous };
  },
  onError: (_err, _id, ctx) => ctx && this.queryClient.setQueryData(favoriteKeys.list(), ctx.previous),
  onSettled: () => this.queryClient.invalidateQueries({ queryKey: favoriteKeys.list() }),
}));
```

The `onError` rollback is non-negotiable. The `onSettled` refetch reconciles with server truth.

### Dependent + Infinite Queries

```typescript
// dependent: only fetch profile after we have a userId
profile = injectQuery(() => ({
  queryKey: ['profile', this.user.data()?.id],
  queryFn: () => firstValueFrom(this.http.get(`/api/profile/${this.user.data()!.id}`)),
  enabled: !!this.user.data(),
}));

// infinite scroll
posts = injectInfiniteQuery(() => ({
  queryKey: ['posts'],
  queryFn: ({ pageParam, signal }) =>
    firstValueFrom(this.http.get<Page<Post>>(`/api/posts`, { params: { cursor: pageParam ?? '' } })),
  initialPageParam: '' as string,
  getNextPageParam: (lastPage) => lastPage.nextCursor,
}));
```

### Apollo Angular (GraphQL)

```typescript
// app.config.ts
export const appConfig: ApplicationConfig = {
  providers: [provideApollo(() => ({
    link: inject(HttpLink).create({ uri: '/graphql' }),
    cache: new InMemoryCache(),
  }))],
};

// component
private apollo = inject(Apollo);

userQuery = this.apollo.watchQuery<{ user: User }>({
  query: gql`query User($id: ID!) { user(id: $id) { id name email } }`,
  variables: { id: this.id() },
});

user = toSignal(this.userQuery.valueChanges.pipe(map((r) => r.data.user)));
```

For mutations, use `apollo.mutate(...)` with `refetchQueries` or manual `cache.modify` for surgical updates.

### SSR Transfer Cache

```typescript
// app.config.ts (browser)
providers: [
  provideClientHydration(
    withHttpTransferCacheOptions({
      includePostRequests: false,         // POSTs default to off; opt in deliberately
      includeRequestsWithAuthHeaders: false, // never cache per-user auth responses in transfer cache
      includeHeaders: ['x-locale'],
      filter: (req) => !req.url.includes('/realtime/'),
    }),
  ),
  provideHttpClient(withFetch()),
],
```

Without `withHttpTransferCacheOptions`, every server-fetched URL is re-fetched on hydration -> double round-trip on every cold page load.

### Shared Cache for Hot Endpoints (no TanStack)

```typescript
@Injectable({ providedIn: 'root' })
export class ConfigService {
  private http = inject(HttpClient);
  readonly config$ = this.http.get<AppConfig>('/api/config').pipe(
    shareReplay({ bufferSize: 1, refCount: true }),
  );
}
```

Use only for low-mutation, app-wide singletons (config, current user). For anything keyed by inputs or invalidated by mutations, use TanStack Query.

### Cancellation

Whatever the library, prefer signal-driven inputs so re-fetches auto-cancel via abort signals. Manual subscriptions need `takeUntilDestroyed()` - see `angular-rxjs-patterns`.

## Output Format

```
## Data Layer

**Angular version:** {detected}
**Primary library:** HttpClient + signals | TanStack Query | Apollo | mixed (justify)
**SSR transfer cache:** wired | absent | n/a

### Queries / Resources

| Name | Library | Key / URL | Inputs (signals) | Stale time |
| ---- | ------- | --------- | ---------------- | ---------- |

### Mutations

| Name | Endpoint | Invalidates | Optimistic? |
| ---- | -------- | ----------- | ----------- |

### Recommendations

- {recommendation}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

Omit `Issues Found` for greenfield design.

## Avoid

- Calling `http.get` inside templates - re-fires every CD cycle
- Mixing TanStack Query and a parallel signal cache for the same domain
- Inline query keys (`['users', id]`) sprinkled across components - use a key factory
- Mutations without an invalidation entry
- Optimistic update with no rollback path
- `includeRequestsWithAuthHeaders: true` on the transfer cache (cross-user leak on shared SSR)
- Subscribing to `route.queryParamMap` and calling `http.get` imperatively when a signal-driven `resource`/`injectQuery` would auto-cancel
- Apollo `cache: new InMemoryCache()` without a `typePolicies` entry for paginated fields (cache thrashes on every page)
