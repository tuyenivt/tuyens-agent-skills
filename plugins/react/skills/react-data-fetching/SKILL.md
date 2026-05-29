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
- Components handle `loading`, `error`, and `empty` (`data` exists but is null/empty) explicitly. No blank-screen fallthroughs.
- Define query/mutation functions at module scope (or via a typed client). Inline closures defeat dedupe and break references.
- For Next.js App Router: fetch on the server, hydrate to TanStack Query via `HydrationBoundary` when the same data must stay interactive on the client.

## Fetching Strategy

| Need                                                | Use                                          |
| --------------------------------------------------- | -------------------------------------------- |
| Render-time data, SEO, no client interactivity      | Server Component (`async`/`await`)           |
| User-specific, mutates, polls, refetches            | TanStack Query in Client Component          |
| Same data on server then interactive on client      | RSC prefetch + `HydrationBoundary`           |
| Cacheable public data with ISR                      | Server Component + `revalidate` / tags       |
| Project already standardised on SWR                 | SWR (URL-keyed, simpler API)                 |

TanStack Query is the default client choice: dependent queries, infinite queries, optimistic updates, and richer cache APIs. SWR is fine where the team has chosen it.

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
const [queryClient] = useState(() => new QueryClient({
  defaultOptions: { queries: { staleTime: 60_000, gcTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false } },
}));
return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
```

`useState` (not module scope) so each request on the server gets its own client.

### Query with all three states

```tsx
const { data, isPending, error } = useQuery({
  queryKey: ["user", userId],
  queryFn: () => fetchUser(userId),
});
if (isPending) return <ProfileSkeleton />;
if (error) return <ErrorState message="Failed to load profile" />;
if (!data) return <EmptyState />;
return <ProfileCard user={data} />;
```

### Dependent query

```tsx
const { data: user } = useQuery({ queryKey: ["user", userId], queryFn: () => fetchUser(userId) });
const posts = useQuery({
  queryKey: ["user", userId, "posts"],
  queryFn: () => fetchUserPosts(userId),
  enabled: !!user,                       // gate on prerequisite
});
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
  onSuccess: () => qc.invalidateQueries({ queryKey: ["posts"] }),
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
const qc = new QueryClient();
await qc.prefetchQuery({ queryKey: ["dashboard-stats"], queryFn: fetchDashboardStats });
return (
  <HydrationBoundary state={dehydrate(qc)}>
    <DashboardClient />                  {/* uses the same queryKey -> instant data */}
  </HydrationBoundary>
);
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
const { trigger, isMutating } = useSWRMutation("/api/posts", postFetcher);
// Cache key is the URL string. Invalidate via mutate(key) or revalidate via useSWRConfig().
```

## Output Format

Emit one Finding per issue:

```
### Finding: <short title>
Category: {Effect-Fetch | Query-Key | Invalidation | State-Handling | Optimistic | Hydration | Stale-Time | RSC-Boundary | Inline-Fn}
Severity: {Critical | High | Medium | Low}
Location: <file>:<line> or <component>
Issue: <one-line problem>
Fix: <concrete change, reference Pattern by name>
```

Conclude with:

```
Summary: <N> findings (<C> Critical, <H> High, <M> Medium, <L> Low)
Client Library: {TanStack Query | SWR | Mixed | None}
RSC Usage: {Server-First | Client-First | Mixed}
Invalidation Coverage: <mutations with invalidation> / <total mutations>
```

Severity guide:
- **Critical**: data loss, wrong-user data, unbounded refetch loops.
- **High**: stale data after writes (missing `invalidateQueries`); a `queryFn`-read variable absent from the `queryKey` (cache collision, wrong data shown); race conditions from manual effects.
- **Medium**: missing empty/error UI; missing optimistic rollback; truly cosmetic key instability (string-vs-array of same data).
- **Low**: inline `queryFn` closures; default `staleTime: 0` where freshness isn't required.

## Avoid

- `useEffect` + `useState` + `fetch` for server data - no dedupe, no cache, race conditions on unmount.
- Sharing one query key across distinct inputs, or omitting a variable the `queryFn` reads (stale-by-id bug).
- Mutations without `invalidateQueries` / `setQueryData` - users see pre-write data until refresh.
- Client fetching data a parent Server Component could fetch and pass down.
- Inline `queryFn: () => fetch(...)` closures that capture changing props without the variable in the key.
- Module-scope `new QueryClient()` in Next.js (cross-request leakage); construct inside `useState` in a Client Component.
- `staleTime: 0` plus `refetchOnWindowFocus: true` for stable data (refetch storm on tab focus).
- Optimistic updates without `cancelQueries` + snapshot + `onError` rollback.
