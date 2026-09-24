---
name: react-data-fetching
description: "Review React 19 data fetching: Server Components, TanStack Query/SWR, Suspense, hydration, optimistic updates, cache invalidation, query keys."
metadata:
  category: frontend
  tags: [react, data-fetching, tanstack-query, swr, suspense, caching, optimistic-updates]
user-invocable: false
---

# React Data Fetching

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing between Server Component fetch, TanStack Query, SWR, or hydration handoff
- Reviewing client fetching for loading/error/empty states, query keys, invalidation, optimistic updates
- Sizing `staleTime`/`gcTime` or diagnosing stale data after mutations

## Rules

- Never `fetch` + `useState` in `useEffect`. Use a Server Component (data needed at render) or TanStack Query / SWR (interactive, user-specific, or revalidating client data).
- Query keys are arrays containing every variable the query depends on. Same key = same cache entry; different inputs = different keys.
- Every mutation invalidates or sets the affected queries. Untouched cache after a write is a bug.
- Components handle `loading`, `error`, and `empty` (data arrived and holds no rows) explicitly. A query that is pending but not fetching (disabled, paused offline) renders the prerequisite's or an offline state. No blank-screen fallthroughs.
- Fetch/transform logic lives in named module-scope functions; the thin `queryFn: () => fetchUser(id)` arrow at the call site is idiomatic. `Inline-Fn` flags fetch logic written inline in the options object, not the thin wrapper.
- For Next.js App Router: fetch on the server, hydrate to TanStack Query via `HydrationBoundary` when the same data must stay interactive on the client.

## Fetching Strategy

| Need                                                | Use                                          |
| --------------------------------------------------- | -------------------------------------------- |
| Render-time data, SEO, no client interactivity      | Server Component (`async`/`await`)           |
| User-specific, mutates, polls, refetches            | TanStack Query in Client Component          |
| Changes on the server while watched (webhook-driven status, live stock) | TanStack Query with `refetchInterval` that returns `false` at a terminal state, or a push channel (SSE / WebSocket) that invalidates the key |
| Same data on server then interactive on client      | RSC prefetch + `HydrationBoundary`           |
| Cacheable public data with ISR                      | Server Component + `revalidate` / tags (Next 16 with Cache Components: `"use cache"` + `cacheLife` / `cacheTag`) |
| Project already standardised on SWR                 | SWR (URL-keyed, simpler API)                 |

TanStack Query is the default client choice for what SWR lacks: `gcTime` control, built-in prefix matching of hierarchical keys (SWR needs a hand-written `mutate(key => ...)` matcher), the mutation lifecycle (`onMutate` / `cancelQueries`), and devtools. SWR covers dependent, infinite and optimistic fetching too and is fine where the team has chosen it.

Cache sizing: `staleTime` = how long serving stale data is acceptable (0 only when per-interaction freshness matters; minutes for reference data); `gcTime` > `staleTime`. The client-setup example's 60s/5min are starting defaults, not law. Polling: `refetchInterval` (TanStack) / `refreshInterval` (SWR). SWR vocabulary: `dedupingInterval` ~ staleTime (SWR has no `gcTime` counterpart - say so in the Cache config cell rather than inventing one), `revalidateOnFocus` ~ refetchOnWindowFocus; conditional fetch = null key (`useSWR(id ? key : null)`); cursor pagination = `useSWRInfinite`.

## Patterns

### Server Component + streamed child

```tsx
// app/products/[id]/page.tsx
export default async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const product = await db.product.findUnique({ where: { id } });
  if (!product) notFound();
  return (
    <>
      <ProductDetails product={product} />
      <Suspense fallback={<ReviewsSkeleton />}>
        <ProductReviews productId={id} />
      </Suspense>
    </>
  );
}
```

### TanStack Query client setup

```tsx
"use client";
const makeQueryClient = () => new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, gcTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false } },
});
let browserClient: QueryClient | undefined;
function getQueryClient() {
  if (typeof window === "undefined") return makeQueryClient(); // a fresh client per server request
  return (browserClient ??= makeQueryClient());                 // one client per browser tab
}
export function Providers({ children }: { children: React.ReactNode }) {
  return <QueryClientProvider client={getQueryClient()}>{children}</QueryClientProvider>;
}
```

The shape of TanStack's Advanced SSR guide. `useState(() => new QueryClient())` also isolates requests, but React discards that client if the first render suspends with no Suspense boundary between the provider and the suspending code.

### Query with all three states

```tsx
const { data, isLoading, error } = useQuery({
  queryKey: ["user", userId],
  queryFn: () => fetchUser(userId),
});
// v5 isLoading is isPending && isFetching - a first load actually in flight.
// Plain isPending stays true forever for a query that never runs (enabled: false, offline).
if (isLoading) return <ProfileSkeleton />;
if (error) return <ErrorState message="Failed to load profile" />;
if (!data) return <ProfileUnavailable />;          // pending, not fetching (paused offline): never a blank
return <ProfileCard user={data} />;
// A list query adds the empty branch: if (data.length === 0) return <EmptyState />;
```

### Dependent query

```tsx
const { data: user } = useQuery({ queryKey: ["users", "detail", userId], queryFn: () => fetchUser(userId) });
const posts = useQuery({
  queryKey: ["users", userId, "posts"],
  queryFn: () => fetchUserPosts(userId),
  enabled: !!user,                       // gate on prerequisite
});
// A gated query is pending, not loading: render the prerequisite's own state until `user` arrives -
// a spinner keyed on `posts.isPending` never clears if the `user` query errors or stays disabled.
```

### Infinite (cursor) pagination

```tsx
const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
  queryKey: ["products", category],
  queryFn: ({ pageParam }) => fetchProducts({ category, cursor: pageParam }),
  initialPageParam: undefined as string | undefined,
  getNextPageParam: (last) => last.nextCursor,
});
const items = data?.pages.flatMap(p => p.items) ?? [];
```

Prefer cursor (`nextCursor`) over `offset` for stability under concurrent writes.

### Mutation + invalidation

```tsx
const qc = useQueryClient();
const m = useMutation({
  mutationFn: createPost,
  onSuccess: (post) => qc.invalidateQueries({ queryKey: ["users", post.authorId, "posts"] }),
  onError: (e) => toast.error(e.message),
});
```

### Optimistic update (cancel, snapshot, set, rollback, settle)

```tsx
const toggleFavorite = useMutation({
  mutationFn: (id: string) => api.toggleFavorite(id),
  onMutate: async (id) => {
    await qc.cancelQueries({ queryKey: ["products"] });
    const prev = qc.getQueryData<Product[]>(["products"]);
    qc.setQueryData<Product[]>(["products"], (old) =>
      old?.map(p => p.id === id ? { ...p, isFavorite: !p.isFavorite } : p));
    return { prev };
  },
  onError: (_e, _id, ctx) => qc.setQueryData(["products"], ctx?.prev),
  onSettled: () => qc.invalidateQueries({ queryKey: ["products"] }),
});
```

### RSC prefetch -> client hydration

```tsx
// app/dashboard/page.tsx (Server Component)
export default async function DashboardPage() {
  const qc = new QueryClient();          // per request, inside the component - never module scope
  await qc.prefetchQuery({ queryKey: ["dashboard-stats"], queryFn: fetchDashboardStats });
  return (
    <HydrationBoundary state={dehydrate(qc)}>
      <DashboardClient />                {/* uses the same queryKey -> instant data */}
    </HydrationBoundary>
  );
}
```

### Query-key factory

```tsx
export const userKeys = {
  all: ["users"] as const,
  detail: (id: string) => [...userKeys.all, "detail", id] as const,
  posts:  (id: string) => [...userKeys.all, id, "posts"] as const,
};
// Invalidate everything under "users":
qc.invalidateQueries({ queryKey: userKeys.all });
```

### SWR equivalents

```tsx
const { data, error, isLoading } = useSWR<User>(`/api/users/${id}`, fetcher);
// Bound to the read key, the mutation revalidates it after trigger (revalidate defaults to true).
const { trigger, isMutating } = useSWRMutation(`/api/users/${id}`, updateUser); // updateUser(key, { arg })
async function save(changes: Partial<User>) {
  await trigger(changes, { optimisticData: (cur) => ({ ...cur!, ...changes }), rollbackOnError: true });
}
// A mutation on another key (POST /api/posts) leaves this read untouched: call
// const { mutate } = useSWRConfig() at the top level, then mutate(readKey) after the write,
// or the read serves pre-write data.
```

## Output Format

When reviewing, emit one Finding per issue, ordered by severity; emit a finding even when a broader refactor would subsume it, naming the subsuming change in Fix. When consulting (strategy choice, cache sizing), emit one prescription row per data type - {Data type | Strategy | Key | Cache config | Invalidation trigger} - then Findings for any defective code shown; the concluding Summary block covers reviewed code only (omit it only when no code is shown).

```
### Finding: <short title>

Category: {Effect-Fetch | Query-Key | Invalidation | State-Handling | Optimistic | Hydration | Stale-Time | RSC-Boundary | Inline-Fn | Client-Setup}

Severity: {Critical | High | Medium | Low}

Location: <file>:<line> or <component>

Issue: <one-line problem>

Fix: <concrete change, reference Pattern by name>
```

Conclude with:

```
Summary: <N> findings (<C> Critical, <H> High, <M> Medium, <L> Low)

Client Library: {TanStack Query | SWR | Mixed | None}

RSC Usage: {Server-First | Client-First | Mixed | None in scope | N/A (SPA)}

Invalidation Coverage: <mutations with invalidation> / <total mutations>

Not assessed: <input never shown or unverifiable from it - a parent Server Component outside the file set, a module whose behaviour decides a severity; omit when none>

Notes: <off-enum observations; omit when none>
```

`Client-Setup`: QueryClient construction or provider defects (an unguarded module-scope client on a server runtime, missing provider). A server cache keyed without an input its function reads (`unstable_cache` key parts omitting the user) is `Query-Key`. A fetch dispatched into a UI store (a Redux thunk in an effect) is `Effect-Fetch`; the store holding server data belongs to state architecture and goes in `Notes:`. A prefetch/client key mismatch is `Hydration`, not `Query-Key`. `Mixed` Client Library = two libraries, or a library plus raw effect-fetches. A mutation counts as covered when it invalidates or sets the affected queries on success or settlement (`onSuccess`, `onSettled`, or after `mutateAsync`); an `onMutate` optimistic write alone does not count; with no mutation in scope, write `0 / 0`. One Finding per root cause: occurrences with the same Category and the same fix in one file merge into one Finding listing each location; different Categories never merge. An effect that triggers fetches without calling fetch (an observer calling `setSize`) is `Effect-Fetch` when it leaks or duplicates them; a raw call fetching what a hook in scope already caches is `Effect-Fetch` on the raw path, the Fix naming the hook. Non-finding observations (out-of-enum defects, confirmed-fine calls) go in a single trailing `Notes:` line.

Severity guide:
- **Critical**: data loss, wrong-user data, unbounded refetch loops; an unguarded module-scope `QueryClient` on a server runtime (cross-request leakage; a `"use client"` module still runs during SSR).
- **High**: stale data after writes (missing `invalidateQueries`); a missing `QueryClientProvider` (throws at runtime); an effect-fetch that races, refetches unboundedly, leaks on unmount, or omits an input it reads from its deps (another entity's data stays after the id or the signed-in user changes) (a correctly guarded one is still `Effect-Fetch`, at Medium, since the Rule is absolute); a `queryFn`-read variable absent from the `queryKey` (cache collision, wrong data shown; Critical when the missing input is the user's identity, since another user's data is then served; Low when the value is a build-time constant); a prefetch/client key mismatch defeating hydration; race conditions from manual effects.
- **Medium**: missing empty/error UI (High when a failed load leaves the UI stuck, e.g. a spinner that never clears); missing optimistic rollback; client-fetching public data a Server Component should own (`RSC-Boundary`); truly cosmetic key instability (string-vs-array of same data).
- **Low**: fetch logic written inline in the options object (`Inline-Fn`; the thin `queryFn: () => fetchUser(id)` wrapper is idiomatic and never a finding); default `staleTime: 0` where freshness isn't required and focus refetch is off.

No Category value is left unscored. Where a value appears in more than one band, the band naming your defect's condition wins; where two fit equally, take the higher. `staleTime: 0` with `refetchOnWindowFocus` on (its default) on stable data is `Stale-Time` at Medium - bounded, but a refetch on every tab focus.

## Avoid

- `useEffect` + `useState` + `fetch` for server data - no dedupe, no cache, race conditions on unmount.
- Sharing one query key across distinct inputs, or omitting a variable the `queryFn` reads (stale-by-id bug).
- Mutations without `invalidateQueries` / `setQueryData` - users see pre-write data until refresh.
- Client fetching data a parent Server Component could fetch and pass down.
- Inline `queryFn: () => fetch(...)` closures that capture changing props without the variable in the key.
- An unguarded module-scope `new QueryClient()` in Next.js (cross-request leakage); use `getQueryClient()` or construct inside `useState` in a Client Component.
- `staleTime: 0` plus `refetchOnWindowFocus: true` for stable data (refetch storm on tab focus).
- Optimistic updates without `cancelQueries` + snapshot + `onError` rollback.
