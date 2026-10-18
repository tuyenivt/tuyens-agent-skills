---
name: frontend-api-integration
description: Next.js frontend data fetching: loading/error states, client caching, optimistic updates, pagination, request deduplication, retries.
metadata:
  category: frontend
  tags: [frontend, api, data-fetching, tanstack-query, swr, apollo, caching, nextjs]
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

- Every data-fetching component handles loading, success, empty, and error states
- Server data is fetched in Server Components and changed through Server Actions; a client data-fetching library caches only data the client fetches interactively (polling, infinite scroll, search-as-you-type); server state never lives in a UI state store
- Identical concurrent requests must deduplicate to one network call
- Mutations invalidate or update affected caches; stale data after writes is a bug
- Pagination: cursor/keyset for real-time or large datasets; offset only for small static data
- Surface user-friendly error messages, never raw server errors or stack traces

---

## Patterns

### Data-Fetching Library Selection

| Library        | Best For                                            |
| -------------- | --------------------------------------------------- |
| Server Components + Server Actions | Page data and mutations; no client cache to keep in sync |
| TanStack Query | Interactive client data: background refetch, infinite lists, polling |
| SWR            | Simple client REST, stale-while-revalidate          |
| RTK Query      | Apps already on Redux Toolkit - one `createApi` slice per base URL, never beside SWR or TanStack for the same data |
| Apollo Client  | GraphQL-first projects                              |

### Loading, Error, and Empty States

```
// Bad: blank screen during fetch, errors fail silently
const [users, setUsers] = useState([])
useEffect(() => { fetch("/api/users").then(r => r.json()).then(setUsers) }, [])
return users.map(u => <UserCard key={u.id} user={u} />)

// Good: interactive client data (search, polling) with all states handled. Server Component data gets
// loading from loading.tsx / <Suspense>, errors from error.tsx, and an empty branch in the component.
const { data, isPending, isFetching, error, refetch } = useQuery({
  queryKey: ["users"],
  queryFn: ({ signal }) => fetchUsers({ signal }),   // forward the signal, or the HTTP request is never aborted
})
// v5: isPending means "no data yet" and stays true for a query that never runs
// (enabled: false, offline): a bare isPending check leaves that case on a skeleton forever, and a bare
// isLoading check lets it fall through to EmptyState - branch on isFetching inside isPending.
if (isPending) return isFetching ? <Skeleton /> : <OfflineOrIdleState />
if (error) return <ErrorState onRetry={refetch} />
if (!data?.length) return <EmptyState />
return data.map(u => <UserCard key={u.id} user={u} />)
```

Prefer skeletons over spinners for content; spinners for button/submit actions. Show "Still loading..." past 3s.

### Optimistic Updates

Update UI before server confirms, snapshot for rollback, refetch on settle:

```
// onMutate is a useMutation option only. onSuccess/onError/onSettled can also be passed
// per call as mutate(vars, { ... }), but those are dropped if the component unmounts.
const addTodo = useMutation({
  mutationFn: createTodo,
  onMutate: async (next) => {
    await queryClient.cancelQueries({ queryKey: ["todos"] })
    const previous = queryClient.getQueryData<Todo[]>(["todos"])   // undefined when the cache was empty
    queryClient.setQueryData<Todo[]>(["todos"], (old = []) => [...old, next])
    return { previous }
  },
  // setQueryData ignores undefined, so an empty-cache rollback must reset the entry instead;
  // writing `?? []` there would fake a successful empty list.
  onError: (_e, _v, ctx) =>
    ctx?.previous === undefined
      ? queryClient.resetQueries({ queryKey: ["todos"] })
      : queryClient.setQueryData(["todos"], ctx.previous),
  onSettled: () => queryClient.invalidateQueries({ queryKey: ["todos"] }),
})
addTodo.mutate(newTodo)
```

Use for low-latency, high-success actions (favorite, comment). Avoid for payments, multi-step validation, or where rollback would confuse.

With a Server Action instead of a client cache, `useOptimistic` from `react` holds the prediction only while the action is pending, then falls back to the real state the action's `updateTag` / `revalidatePath` delivers, so a failed action reverts on its own - surface its error rather than leaving the user guessing.

When the server computes the authoritative result rather than echoing yours - reordering a list, assigning a position, resolving a conflict - the response is the truth and must replace the prediction, not merge with it. Take the server's value on success rather than keeping the optimistic one, and let `onSettled` reconcile. Track in-flight mutations so a settling refetch does not overwrite a newer optimistic change the user has already made: while any mutation for that key is pending, apply the refetch result under the still-pending predictions. The same holds for any concurrent optimistic writes to one key, not only server-computed ones: give them a shared `mutationKey` and invalidate on settle only when `queryClient.isMutating({ mutationKey }) === 1`.

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
  queryFn: () => fetchOrders(user!.id),   // `enabled` does not narrow the closure under strict TS
  enabled: !!user,
})
```

### Retry Configuration

Uncapped retries cascade into backend overload. Recommended policy (TanStack's client-side query default is 3 retries on every error, 4xx included, and it never reads `Retry-After` - the 4xx and 429 lines need a custom `retry: (count, err) => ...` plus `retryDelay`; mutations default to 0). One retry layer only - the library's; a fetch wrapper retrying on its own multiplies attempts and is a finding. The policy:

- **Queries:** retry up to 3 with exponential backoff (`Math.min(1000 * 2 ** attempt, 30000)`)
- **Mutations:** do not retry unless idempotency key is set
- **4xx:** no retry (exceptions: 408, and 429 honoring `Retry-After`)
- **5xx and network:** retry with backoff

Scale retries down as request cost rises: three retries of a 90-second call is six minutes of backend load and six minutes before the user sees an error. Past a few seconds of work, stop holding the connection - have the endpoint return a job id immediately, then poll its status (`refetchInterval` starting near 1s, doubling to a 30s cap, returning `false` at a terminal status; past the job's maximum duration, stop and show a timeout) or subscribe over SSE/WebSocket, so the browser is not betting on one long request surviving proxies, timeouts, and sleeping laptops. When the terminal status arrives, refresh the server-rendered view it affects - `router.refresh()`, or a Server Action that invalidates its tag.

### Caching and Deduplication

Data-fetching libraries deduplicate by query key, so the key lists every input the request depends on (filters, scope, page, user) - a key missing one collides two different responses on one entry. Two fetch paths for one endpoint (a library hook and a raw call, or two libraries) defeat deduplication and are one dedupe finding listing both locations; the cache the mutations invalidate is authoritative, and the other path's readers move to it. Configure:
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

Client fetches: centralize in one fetch wrapper or interceptor; allow component-level overrides. Server Components and Server Actions fetch on the server, where no client interceptor sees the response: a 401 there calls `redirect()` to login (or `proxy.ts` redirects unauthenticated requests before render), and a Server Action re-checks auth itself.

**Token refresh is single-flight.** Across tabs sharing a stored refresh token, the flight is shared through a Web Lock (`navigator.locks.request`) whose holder re-reads the stored token before refreshing - another tab may already have rotated it - not a module-level promise alone (a BroadcastChannel announces the new token but excludes nothing). When several requests get a 401 at once, they must await one shared refresh promise, not start one each - with rotating refresh tokens, concurrent refreshes invalidate each other and log the user out spuriously. Hold a module-level promise: the first 401 starts the refresh, the rest await it, then all retry once with the new token. A second 401 after a completed refresh is a real auth failure - go to the 401 row above rather than looping.

### Request Cancellation

Cancel in-flight requests on unmount, on new search input (debounce + cancel previous), or on route change. A query library only cancels what its fetcher cooperates with: TanStack Query hands the `queryFn` an `AbortSignal`; once the `queryFn` reads it, losing the last observer (unmount or key change) or `cancelQueries` aborts that signal and discards the result, but the network request is aborted only when the fetcher forwards the signal to `fetch`/axios. A `queryFn` that never reads `signal` is not cancelled on unmount: the request finishes and writes its result to the cache, and `cancelQueries` only discards the late result. SWR does not abort at all (a late response lands in the cache under its key, which is harmless; it is a defect only for manual `fetch` writing into component state). For manual `fetch`, always pass your own `AbortSignal`.

## Next.js Bindings

- Loading: `loading.tsx` or `<Suspense>`. Errors: `error.tsx` (`{ error, retry }`), or `catchError` from `next/error` for a component-level boundary that lets `redirect()` / `notFound()` through
- One `QueryClient` per browser and per server request: a `getQueryClient()` returning `new QueryClient()` when `isServer` and a module singleton in the browser (`useState(() => new QueryClient())` only when a Suspense boundary sits between the provider and every suspending query). A module-scope client created in a `"use client"` provider is shared across SSR requests and serves one user's data to another - High
- Caching of server-rendered data (`"use cache"` with `cacheLife` / `cacheTag`, the previous model's `unstable_cache` or `fetch(..., { next: { revalidate, tags } })`) is recorded in the Endpoints `Caching` cell as `server cache: <profile or tag>`. A Server Action that writes without `updateTag`, `revalidatePath` or `revalidateTag(tag, { expire: 0 })` for the data it changes, or with only a stale-while-revalidate `revalidateTag` (`'max'` or another profile whose `expire` is not 0: the writer sees the old data once), is a stale-after-write Issue (High); a one-argument `revalidateTag(tag)` expires immediately but is deprecated - `Notes:`; cache-profile and tag-design defects go to `Notes:`

---

## Output Format

Consuming workflow skills depend on this structure.

```
## API Integration Assessment

**Stack:** {Framework and Language as a display name (`Next.js 16.3 / TypeScript` for stack-detect's `React (Next.js)`) - the major.minor from the owning app's `package.json` (`^16.3.0` -> 16.3); with no `tsconfig.json`, the extensions of the files in scope decide JS vs TS, overriding stack-detect's Language; in a monorepo, the app owning the reviewed code; `unknown` for a part that is inconclusive}

**Data-fetching library:** {what the code uses today - a library name, `Mixed - <libs>` naming every library, or framework-native `Server Components + Server Actions`; prefix `Server Components + ` to a library value when both fetch paths exist; append ` plus raw fetch/axios` to any of these when raw paths exist too (a bare thunk or effect fetch is a raw path, not a library); or `none - raw fetch/axios`. In implement or design mode, where nothing exists yet, name what is prescribed (`Server Components + TanStack Query`)}

### Endpoints

| Endpoint | Method | Component(s)      | Caching        | States Handled          |
| -------- | ------ | ----------------- | -------------- | ----------------------- |
| {path}   | {verb} | {component names} | {strategy/TTL} | {loading, success, empty, error - list those handled} |

### Recommendations {when at least one applies}

- {recommendation with rationale}

### Issues Found {when at least one finding}

- [Severity: High | Medium | Low] {description}
  - Location: {file}:{line}[, {file}:{line}]
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found {instead, when none}

{one sentence: API integration is adequate for the scope reviewed}

Not assessed: {input the review needed but never saw - a file referenced but not provided, a module whose behaviour decides a severity, a symptom whose trigger lies outside scope; never a guessed finding; omit when none}

Notes: {observations outside this skill's concern, each naming the owning concern; omit when none}
```

Order Issues Found by severity, highest first; within a band, file order (the order the input lists the files; ascending line within a file). `Location` lists every `file:line` one root cause spans, comma-separated; the finding sorts by its lead file, the one the fix changes. `Recommendations` carries proactive improvements only; a defect and its fix belong in `Issues Found` and appear in one place, never both.

Severity anchor: High = correctness, data integrity, information leak, or a feature unusable for some users (silent failures, stale data after writes including an optimistic write left in place after the server rejects it, races, a raw server error reaching the user, offset pagination on a live list, infinite scroll with no keyboard-reachable alternative); Medium = degraded UX, client performance, or load the backend absorbs (waterfalls, missing empty state, uncapped retries); Low = polish. A defect not named here takes the band whose description fits; when two fit, the higher wins.

The Endpoints table covers the integrations in scope - the change's touched endpoints when reviewing, the feature's endpoints when implementing - never a whole-app inventory; one row per endpoint and method, with every component or fetch path that calls it in `Component(s)`. In implement or design mode (writing new integration, not reviewing), the table documents what was built or planned, and Issues Found carries residual risks knowingly accepted. When the build or design touches existing code, defects already in it are ordinary Issues Found entries marked `(pre-existing)` at their own severity; the residual-risk reading covers only the new work. `stack-detect` has no field for this: read the `Data-fetching library` value from `package.json` dependencies (the owning app's manifest in a monorepo) and the imports in the files in scope.

---

## Avoid

- Raw `useEffect` fetching in a Client Component, where a Server Component or a data-fetching library belongs
- Manual `fetch` with no `AbortSignal`, where a late response overwrites newer component state
- Uncapped retries (backend overload); retrying non-idempotent mutations
- Sequential fetching of independent data (waterfall)
