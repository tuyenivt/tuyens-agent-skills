---
name: frontend-api-integration
description: Frontend data fetching: loading/error states, caching, optimistic updates, pagination, request deduplication. Adapts to detected stack.
metadata:
  category: frontend
  tags: [frontend, api, data-fetching, tanstack-query, swr, apollo, caching, multi-stack]
user-invocable: false
---

# Frontend API Integration

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Implementing data fetching for frontend components
- Designing loading, error, and empty state handling
- Adding caching, pagination, or optimistic updates
- Reviewing existing API integration for correctness

## Rules

- Every data-fetching component handles loading, success, and error states
- Server state lives in a data-fetching library cache, not a UI state store
- Identical concurrent requests must deduplicate to one network call
- Mutations invalidate or update affected caches; stale data after writes is a bug
- Pagination: cursor/keyset for real-time or large datasets; offset only for small static data
- Surface user-friendly error messages, never raw server errors or stack traces

---

## Patterns

### Data-Fetching Library Selection

| Library        | Best For                                            |
| -------------- | --------------------------------------------------- |
| TanStack Query | REST/GraphQL, caching, background refetch (any FW)  |
| SWR            | Simple REST, stale-while-revalidate                 |
| Apollo Client  | GraphQL-first projects                              |
| Framework SDK  | Nuxt `useFetch`/`useAsyncData`, Angular `HttpClient` with RxJS |

### Loading, Error, and Empty States

```
// Bad: blank screen during fetch, errors fail silently
const [users, setUsers] = useState([])
useEffect(() => { fetch("/api/users").then(r => r.json()).then(setUsers) }, [])
return users.map(u => <UserCard key={u.id} user={u} />)

// Good: all states handled
const { data, isLoading, error, refetch } = useQuery({ queryKey: ["users"], queryFn: fetchUsers })
if (isLoading) return <Skeleton />
if (error) return <ErrorState onRetry={refetch} />
if (data.length === 0) return <EmptyState />
return data.map(u => <UserCard key={u.id} user={u} />)
```

Prefer skeletons over spinners for content; spinners for button/submit actions. Show "Still loading..." past 3s.

### Optimistic Updates

Update UI before server confirms, snapshot for rollback, refetch on settle:

```
mutate({
  onMutate: async (next) => {
    await queryClient.cancelQueries({ queryKey: ["todos"] })
    const previous = queryClient.getQueryData(["todos"])
    queryClient.setQueryData(["todos"], old => [...old, next])
    return { previous }
  },
  onError: (_e, _v, ctx) => queryClient.setQueryData(["todos"], ctx.previous),
  onSettled: () => queryClient.invalidateQueries({ queryKey: ["todos"] }),
})
```

Use for low-latency, high-success actions (favorite, comment). Avoid for payments, multi-step validation, or where rollback would confuse.

The snapshot-rollback-settle sequence is library-agnostic: with framework-native fetchers (e.g., Nuxt `useFetch`), patch the `data` ref directly, restore the snapshot on error, and `refresh()` on settle.

### Pagination

| Pattern         | When to Use                    | Tradeoff                         |
| --------------- | ------------------------------ | -------------------------------- |
| Cursor/keyset   | Real-time, large datasets      | No arbitrary page jump           |
| Offset          | Static, small admin tables     | Skips/duplicates on data changes |
| Infinite scroll | Feeds, browsing                | Hard to bookmark; need a11y fallback |
| Load more       | Search results, catalogs       | Extra click per page             |

Infinite scroll requires a "Load more" button fallback, screen-reader announcement of new content, scroll restoration, and a reachable footer.

Loaded pages go stale mid-scroll: cursor pagination tolerates server-side inserts/deletes; when acting on a rendered item returns 404, prune that item from the cache and inform the user - do not refetch every loaded page.

### Request Coordination

Fetch independent data in parallel; use dependent fetches only when one query truly needs another's result.

```
// Parallel
const results = useQueries({ queries: [
  { queryKey: ["user", id], queryFn: () => fetchUser(id) },
  { queryKey: ["activity", id], queryFn: () => fetchActivity(id) },
]})

// Dependent: enabled gates the second query on the first
const { data: user } = useQuery({ queryKey: ["user", id], queryFn: () => fetchUser(id) })
const { data: orders } = useQuery({
  queryKey: ["orders", user?.id],
  queryFn: () => fetchOrders(user.id),
  enabled: !!user,
})
```

### Retry Configuration

Uncapped retries cascade into backend overload. Defaults:

- **Queries:** retry up to 3 with exponential backoff (`Math.min(1000 * 2 ** attempt, 30000)`)
- **Mutations:** do not retry unless idempotency key is set
- **4xx:** no retry (exception: 429 honors `Retry-After`)
- **5xx and network:** retry with backoff

### Caching and Deduplication

Data-fetching libraries deduplicate by query key. Configure:
- `staleTime`: 0 for real-time, 30s-5min for mostly-static
- `gcTime`: how long unused entries persist
- Background refetch on window focus for data that changes while hidden

### Error Handling

| HTTP    | User Experience                              |
| ------- | -------------------------------------------- |
| 400/422 | Inline field-level errors                    |
| 401     | Redirect to login, preserve intended route   |
| 403     | "No permission" message                      |
| 404     | "Not found" page or inline message           |
| 429     | Retry message respecting backoff             |
| 5xx     | Generic error with retry                     |
| Network | Offline indicator with retry                 |

Centralize in an HTTP interceptor or wrapper; allow component-level overrides.

### Request Cancellation

Cancel in-flight requests on unmount, on new search input (debounce + cancel previous), or on route change. Data-fetching libraries handle this when query keys change; for manual `fetch`, always pass an `AbortSignal`.

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms:

- **React**: TanStack Query or SWR; Apollo for GraphQL; Suspense + ErrorBoundary
- **Vue**: TanStack Query Vue or Nuxt `useFetch`/`useAsyncData`; composable patterns
- **Angular**: `HttpClient` with interceptors; RxJS for retry/caching; `toSignal` to bridge to signals

For unknown stacks, apply universal patterns and point the user to the framework's data-fetching docs.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## API Integration Assessment

**Stack:** {detected language / framework}
**Data-fetching library:** {detected or recommended library}

### Endpoints

| Endpoint | Method | Component(s)      | Caching        | States Handled          |
| -------- | ------ | ----------------- | -------------- | ----------------------- |
| {path}   | {verb} | {component names} | {strategy/TTL} | {loading, error, empty} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if API integration is adequate - do not omit this section silently}
```

Include either `Issues Found` or `No Issues Found`, never both. Severity anchor: High = correctness or data integrity (silent failures, stale data after writes, races); Medium = degraded UX or performance (waterfalls, missing empty state); Low = polish.

---

## Avoid

- Raw `useEffect`/`onMounted` fetching without a data-fetching library
- Missing loading, error, or empty states (blank screens, silent failures)
- Server data in UI state stores (manual cache invalidation, stale reads)
- Offset pagination for real-time data (skipped/duplicated items)
- Raw server error messages reaching users (information leak)
- Requests without unmount cancellation (memory leaks, ghost state updates)
- Infinite scroll without keyboard-accessible alternative
- Uncapped retries (backend overload); retrying non-idempotent mutations
- Sequential fetching of independent data (waterfall)
