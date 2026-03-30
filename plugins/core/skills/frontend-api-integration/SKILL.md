---
name: frontend-api-integration
description: Frontend data fetching patterns - loading/error states, caching, optimistic updates, pagination, request deduplication. Adapts to detected stack (TanStack Query, SWR, Apollo, useFetch, etc.).
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
- Reviewing existing API integration patterns for correctness

## Rules

- Every data-fetching component must handle three states: loading, success, and error - no exceptions
- Server state must be managed by a data-fetching library, not in a UI state store
- Requests must be deduplicated - identical concurrent requests should result in one network call
- Mutations must invalidate or update affected query caches - stale data after writes is a bug
- Pagination must use cursor-based pagination for real-time data or keyset pagination for large datasets - offset pagination only for static/small datasets
- API error responses must surface user-friendly messages, not raw server errors or stack traces

---

## Patterns

### Data Fetching Library Selection

| Library        | Framework  | Best For                                    |
| -------------- | ---------- | ------------------------------------------- |
| TanStack Query | React, Vue | REST/GraphQL, caching, background refetch   |
| SWR            | React      | Simple REST, stale-while-revalidate         |
| Apollo Client  | React, Vue | GraphQL-first projects                      |
| useFetch       | Nuxt       | Nuxt server-side + client-side fetching     |
| useAsyncData   | Nuxt       | Nuxt SSR data fetching with key-based cache |
| HttpClient     | Angular    | Angular's built-in HTTP with interceptors   |

### Loading, Error, and Empty States

**Bad** - Missing states:

```
function UserList() {
  const [users, setUsers] = useState([])
  useEffect(() => {
    fetch("/api/users").then(r => r.json()).then(setUsers)
  }, [])
  return users.map(u => <UserCard key={u.id} user={u} />)
}
```

Problem: No loading indicator, no error handling, no empty state. Users see a blank screen during fetch, and errors fail silently.

**Good** - All states handled:

```
function UserList() {
  const { data: users, isLoading, error } = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
  })

  if (isLoading) return <UserListSkeleton />
  if (error) return <ErrorState message="Failed to load users" onRetry={refetch} />
  if (users.length === 0) return <EmptyState message="No users found" />
  return users.map(u => <UserCard key={u.id} user={u} />)
}
```

### Skeleton Loading

Prefer skeleton screens over spinners for content areas:

- Skeletons reduce perceived loading time by showing the content structure
- Spinners are appropriate for actions (button loading state, form submission)
- Never show a spinner for more than 3 seconds without additional context ("Still loading...")

### Optimistic Updates

Update the UI immediately before the server confirms, then reconcile:

```
// Optimistic update pattern
mutate({
  onMutate: async (newTodo) => {
    // Cancel outgoing refetches
    await queryClient.cancelQueries({ queryKey: ["todos"] })
    // Snapshot previous value
    const previous = queryClient.getQueryData(["todos"])
    // Optimistically update
    queryClient.setQueryData(["todos"], old => [...old, newTodo])
    return { previous }
  },
  onError: (err, newTodo, context) => {
    // Rollback on error
    queryClient.setQueryData(["todos"], context.previous)
    toast.error("Failed to add todo")
  },
  onSettled: () => {
    // Refetch to ensure consistency
    queryClient.invalidateQueries({ queryKey: ["todos"] })
  },
})
```

**When to use optimistic updates:**

- Low-latency actions where the server almost always succeeds (toggling a favorite, adding a comment)
- Actions where the UI should feel instant

**When NOT to use:**

- Complex operations with validation that can fail (payment, multi-step forms)
- Actions where rollback would be confusing to the user

### Pagination Patterns

| Pattern         | When to Use                    | Pros                          | Cons                             |
| --------------- | ------------------------------ | ----------------------------- | -------------------------------- |
| Cursor-based    | Real-time data, large datasets | Stable across inserts/deletes | Cannot jump to arbitrary page    |
| Offset-based    | Static data, admin tables      | Simple, supports page jumping | Skips/duplicates on data changes |
| Infinite scroll | Social feeds, content browsing | Seamless UX for browsing      | Hard to bookmark, back-nav       |
| Load more       | Search results, catalogs       | User-controlled, accessible   | Extra click per page             |

**Infinite scroll must provide:**

- A "Load more" button fallback for keyboard users
- Announcement of new content count for screen readers
- Scroll position restoration on back navigation
- A way to reach the page footer

### Request Coordination

When a component needs data from multiple independent endpoints, fetch in parallel rather than sequentially:

**Bad** - Waterfall fetching (sequential requests):

```
// Each request waits for the previous one - total time is sum of all requests
const user = await fetchUser(id)
const notifications = await fetchNotifications(id)
const activity = await fetchActivity(id)
```

**Good** - Parallel fetching (independent requests):

```
// Independent requests fire simultaneously - total time is the slowest request
const [user, notifications, activity] = await Promise.all([
  fetchUser(id),
  fetchNotifications(id),
  fetchActivity(id),
])

// With TanStack Query: use useQueries for parallel independent queries
const results = useQueries({
  queries: [
    { queryKey: ["user", id], queryFn: () => fetchUser(id) },
    { queryKey: ["notifications", id], queryFn: () => fetchNotifications(id) },
    { queryKey: ["activity", id], queryFn: () => fetchActivity(id) },
  ],
})
```

**Dependent queries** (when one query needs the result of another):

```
// Fetch user first, then fetch user's orders using the user's ID
const { data: user } = useQuery({ queryKey: ["user", id], queryFn: () => fetchUser(id) })
const { data: orders } = useQuery({
  queryKey: ["orders", user?.id],
  queryFn: () => fetchOrders(user.id),
  enabled: !!user,  // only runs when user data is available
})
```

### Retry Configuration

Configure retry limits to prevent infinite retry loops that can cascade into backend overload:

- **Queries (reads):** Retry up to 3 times with exponential backoff. TanStack Query: `retry: 3, retryDelay: attemptIndex => Math.min(1000 * 2 ** attemptIndex, 30000)`
- **Mutations (writes):** Do not retry by default - mutations may not be idempotent. Only retry with an explicit idempotency key
- **4xx errors:** Do not retry (client error, retrying will not help). Exception: 429 (rate limited) should retry after the `Retry-After` header duration
- **5xx errors:** Retry with backoff (server may recover)
- **Network errors:** Retry with backoff (connection may be restored)

### Request Deduplication and Caching

- Data-fetching libraries (TanStack Query, SWR, Apollo) deduplicate by default using query keys
- Set `staleTime` appropriately: 0 for real-time data, 30s-5min for mostly-static data
- Use `gcTime` (garbage collection time) to control how long unused cache entries persist
- Background refetch on window focus for data that changes while the tab is hidden

### Error Handling Strategy

| Error Type       | HTTP Status | User Experience                            |
| ---------------- | ----------- | ------------------------------------------ |
| Validation error | 400, 422    | Show field-level errors inline             |
| Unauthorized     | 401         | Redirect to login, preserve intended route |
| Forbidden        | 403         | Show "no permission" message               |
| Not found        | 404         | Show "not found" page or inline message    |
| Rate limited     | 429         | Show retry message with backoff            |
| Server error     | 500-599     | Show generic error with retry button       |
| Network error    | No response | Show offline indicator with retry          |

Centralize error handling in an HTTP interceptor or wrapper, but allow individual components to override for specific error types.

### Request Cancellation

Cancel in-flight requests when they are no longer needed:

- Component unmounts before request completes (use AbortController)
- User types in search input (cancel previous search, debounce new one)
- User navigates away from page (cancel pending data fetches)

Data-fetching libraries handle this automatically when configured correctly. For manual fetch calls, always pass an AbortSignal.

## Stack-Specific Guidance

After loading stack-detect, apply API integration patterns using the libraries and idioms of the detected ecosystem:

- **React**: TanStack Query (primary) or SWR for REST, Apollo Client for GraphQL, Suspense boundaries for loading states, ErrorBoundary for error states
- **Vue**: TanStack Query Vue or Nuxt useFetch/useAsyncData, composable-based fetching patterns, Suspense for async components
- **Angular**: HttpClient with typed responses, interceptors for auth/error handling, RxJS operators for caching/retry, toSignal for bridging to signals

If the detected stack is unfamiliar, apply the universal patterns above and recommend the user consult their framework's data-fetching documentation.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## API Integration Assessment

**Stack:** {detected language / framework}
**Data-fetching library:** {detected or recommended library}

### Endpoints

| Endpoint          | Method | Component(s)       | Caching         | States Handled          |
| ----------------- | ------ | ------------------- | --------------- | ----------------------- |
| {path}            | {verb} | {component names}   | {strategy/TTL}  | {loading, error, empty} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description of API integration issue}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if API integration is adequate - do not omit this section silently}
```

---

## Avoid

- Fetching data in useEffect/onMounted without a data-fetching library (no caching, no deduplication, no retry)
- Missing loading, error, or empty states on data-fetching components (blank screens, silent failures)
- Storing server data in UI state stores (manual cache invalidation, stale data)
- Using offset pagination for real-time or frequently changing data (skipped/duplicated items)
- Showing raw server error messages to users (confusing, potential information leak)
- Firing requests without cancellation on unmount (memory leaks, state updates on unmounted components)
- Infinite scroll without keyboard-accessible alternative (accessibility violation)
- Refetching all data on every component render (missing query keys or staleTime configuration)
- Infinite or uncapped retries on failed requests (causes cascading backend load; cap at 3 retries with backoff)
- Retrying mutations without idempotency keys (risk of duplicate writes)
- Sequential fetching of independent data sources when they could be fetched in parallel (waterfall requests)
