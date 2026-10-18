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
- Every mutation invalidates what it changed: a client-library mutation invalidates or sets the affected queries; a Server Action calls `updateTag` when its response shows the user's own write, `revalidateTag(tag, "max")` only where stale-while-revalidate is acceptable, or `revalidatePath` (see Pattern: Server Action + tag invalidation); `refresh()` only re-renders the client router and invalidates nothing. Untouched cache after a write is a bug.
- A shared cache scope (`"use cache"`, `unstable_cache`) never reads request APIs: `cookies()` / `headers()` inside it throws whenever the scope runs, build prerender included (`next-request-in-use-cache` under `"use cache"`, an `unstable_cache()` error under `unstable_cache`); `"use cache: private"` may read them, and is per request. Read the identity outside and pass it in as an argument, so it becomes part of the key.
- Components handle `loading`, `error`, and `empty` (data arrived and holds no rows) explicitly. A query that is pending but not fetching (disabled, paused offline) renders the prerequisite's or an offline state. No blank-screen fallthroughs.
- Fetch/transform logic lives in named module-scope functions; the thin `queryFn: () => fetchUser(id)` arrow at the call site is idiomatic. `Inline-Fn` flags fetch logic written inline in the options object, not the thin wrapper.
- Read on the server first: fetch in a Server Component and pass the data, or a Promise the Client Component unwraps with `use()`. Prefetch into TanStack Query with `HydrationBoundary` only when the same data must also refetch on the client.

## Fetching Strategy

| Need                                                | Use                                          |
| --------------------------------------------------- | -------------------------------------------- |
| Render-time data, SEO, no client interactivity      | Server Component (`async`/`await`), data or a `use()` Promise passed down |
| User-specific, mutates, polls, refetches            | TanStack Query in Client Component          |
| Changes on the server while watched (webhook-driven status, live stock) | TanStack Query with `refetchInterval` that returns `false` at a terminal state, or a push channel (SSE / WebSocket) that invalidates the key |
| Same data on server then interactive on client      | RSC prefetch + `HydrationBoundary`           |
| Cacheable public data                               | `cacheComponents` set in `next.config`: `"use cache"` + `cacheLife("hours")` or `cacheLife({ stale, revalidate, expire })` / `cacheTag`; not set: `fetch` with `next: { revalidate, tags }`, or `unstable_cache(fn, keys, { tags, revalidate })` for non-fetch reads |
| Project already standardised on SWR                 | SWR (URL-keyed, simpler API)                 |

TanStack Query is the default client choice for what SWR lacks: `gcTime` control, built-in prefix matching of hierarchical keys (SWR needs a hand-written `mutate(key => ...)` matcher), the mutation lifecycle (`onMutate` / `cancelQueries`), and devtools. SWR covers dependent, infinite and optimistic fetching too and is fine where the team has chosen it.

Cache sizing: `staleTime` = how long serving stale data is acceptable (0 only when per-interaction freshness matters; minutes for reference data); `gcTime` > `staleTime`. The client-setup example's 60s/5min are starting defaults, not law. Polling: `refetchInterval` (TanStack) / `refreshInterval` (SWR). SWR vocabulary: `dedupingInterval` ~ staleTime (SWR has no `gcTime` counterpart - say so in the Cache config cell rather than inventing one), `revalidateOnFocus` ~ refetchOnWindowFocus; conditional fetch = null key (`useSWR(id ? key : null)`); cursor pagination = `useSWRInfinite`.

## Patterns

### Server Component + streamed child

With `cacheComponents` set, an uncached read or `await params` (without `generateStaticParams`) outside `<Suspense>` fails the build as a blocking route; fixes in Next's own order: stream it (a sibling `loading.tsx`, or the read moved into a child under `<Suspense>`), cache the uncached read (`"use cache"`; `params` is runtime data, so not that), or accept blocking (`export const instant = false`). The page below takes the first: a sibling `app/products/[id]/loading.tsx` covers its own `params` and product read, and `<Suspense>` streams the reviews.

```tsx
// app/products/[id]/page.tsx
export default async function ProductPage({ params }: PageProps<"/products/[id]">) {
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

### Server Action + tag invalidation

```tsx
"use server";
import { updateTag } from "next/cache";
export async function createPost(formData: FormData) {
  const user = await requireUser();                  // authorize inside every action
  await db.post.create({ data: { authorId: user.id, title: String(formData.get("title")) } });
  updateTag(`posts:${user.id}`);                     // reads carry this tag: cacheTag, fetch next.tags, or unstable_cache tags
}
```

`updateTag` (read-your-writes) is Server Actions only; `revalidateTag(tag, "max")` serves stale while revalidating, a Route Handler or webhook expires with `revalidateTag(tag, { expire: 0 })`, and `refresh()` covers uncached data. One-argument `revalidateTag(tag)` still invalidates (as `{ expire: 0 }`) but logs a deprecation warning and is a type error against Next 16's types - a failed build in a type-checked project.

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
  mutationFn: api.createPost,              // a client API call returning the created { id, authorId }
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

When reviewing, emit one Finding per issue, ordered by severity; emit a finding even when a broader refactor would subsume it, naming the subsuming change in Fix. When consulting (strategy choice, cache sizing), emit the prescription table first - one row per data type - then Findings for any defective code shown; the concluding Summary block covers reviewed code only (omit it only when no code is shown).

```
| Data type | Strategy | Key | Cache config | Invalidation trigger | On failure |
| --------- | -------- | --- | ------------ | -------------------- | ---------- |
| {what is read} | {row of the Fetching Strategy table} | {query key or cache tag, every input included} | {staleTime / gcTime / cacheLife profile; SWR: dedupingInterval, no gcTime} | {mutation, webhook, poll terminal state, or `none - static`} | {retry policy and the UI shown} |
```

```
### Finding: <short title>

Category: {Effect-Fetch | Query-Key | Invalidation | State-Handling | Optimistic | Hydration | Stale-Time | RSC-Boundary | Inline-Fn | Client-Setup}

Severity: {Critical | High | Medium | Low}

Location: <file>:<line>[, <file>:<line> ...] or <component>

Issue: <one-line problem>

Fix: <concrete change, naming the Pattern it follows, or "(no Pattern fits)" when none applies>
```

Conclude with:

```
Summary: <N> findings (<C> Critical, <H> High, <M> Medium, <L> Low)

Client Library: {TanStack Query | SWR | Mixed | None}

RSC Usage: {Server-First | Client-First | Mixed | None in scope}

Invalidation Coverage: <mutations with invalidation> / <total mutations - Server Actions, client mutations and inbound webhooks that write>

Not assessed: <input never shown or unverifiable from it - a parent Server Component outside the file set, a module whose behaviour decides a severity; omit when none>

Notes: <observations outside this skill's concern, each naming the owning concern; omit when none>
```

`Client-Setup`: QueryClient construction or provider defects (an unguarded module-scope client on a server runtime, missing provider). A server cache keyed without an input its function reads is `Query-Key`: `"use cache"` keys arguments and captured closure variables automatically, so the case there is a value read from module scope; without `cacheComponents`, `unstable_cache` key parts omitting the user. A request API (`cookies()` / `headers()`) read inside a shared scope is also `Query-Key`, at High: it throws, so the route fails to render or build (Fix: read it outside and pass it in). A fetch dispatched into a UI store (a Redux thunk in an effect) is `Effect-Fetch`; the store holding server data belongs to state architecture and goes in `Notes:`. A prefetch/client key mismatch is `Hydration`, not `Query-Key`. A poll on a resource with a terminal state that never stops at it is `Stale-Time` (a resource with none, such as live stock, polls by design). `Mixed` Client Library = two libraries, or a library plus raw effect-fetches; two libraries fetching the same read is `Effect-Fetch` on the path the mutations do not invalidate, the Fix naming the other. A mutation counts as covered when it invalidates or sets the affected queries on success or settlement (`onSuccess`, `onSettled`, or after `mutateAsync`); an `onMutate` optimistic write alone does not count; a Server Action counts when it calls `updateTag`, `revalidateTag` or `revalidatePath` for what it wrote (`refresh()` alone does not count), a Route Handler or webhook when it calls `revalidateTag` or `revalidatePath` (`updateTag` and `refresh()` throw outside a Server Action); one-argument `revalidateTag(tag)` counts as covered in both, its deprecated form going to `Notes:` as Next.js patterns' `DeprecatedApi`; one that calls none is an `Invalidation` finding, except that an optimistic mutation's missing invalidation is scored inside its `Optimistic` finding; `revalidateTag(tag, "max")` counts only where stale-while-revalidate is acceptable - an action whose response shows its own write (it redirects to or returns a view of it) needs `updateTag`, otherwise it is an `Invalidation` finding at High (stale data after writes); with no mutation in scope, write `0 / 0`. One Finding per root cause: occurrences with the same Category and the same fix merge into one Finding listing each location, across files too; different Categories never merge. An effect that triggers fetches without calling fetch (an observer calling `setSize`) is `Effect-Fetch` when it leaks or duplicates them; a raw call fetching what a hook in scope already caches is `Effect-Fetch` on the raw path, the Fix naming the hook. A finding spanning several files leads with the file the fix changes and sorts by it. Observations outside this skill's concern (auth and ownership checks, server data held in a store, a blocking-route build failure) and confirmed-fine calls go in the single trailing `Notes:` line, each naming its owner.

Severity guide:
- **Critical**: data loss (`Optimistic` with neither rollback nor settle invalidation, so a failed write stays on screen as saved), wrong-user data (a user-keyed read cached without the user: `unstable_cache` key parts, or a module-scope value read inside `"use cache"`), unbounded refetch loops or a poll that never stops at its terminal state; an unguarded module-scope `QueryClient` on a server runtime (cross-request leakage; a `"use client"` module still runs during SSR).
- **High**: stale data after writes (missing `invalidateQueries`, or a Server Action, Route Handler or webhook with no tag/path invalidation); a missing `QueryClientProvider` (throws at runtime); an effect-fetch that races or omits an input it reads from its deps (another entity's data stays after the id or the signed-in user changes) (a correctly guarded one is still `Effect-Fetch`, at Medium, since the Rule is absolute - an un-aborted fetch whose response lands after unmount is harmless on React 18+, so that alone is Medium); a `queryFn`-read variable absent from the `queryKey` (cache collision, wrong data shown; Critical when the missing input is the user's identity, since another user's data is then served; Low when the value is a build-time constant); a prefetch/client key mismatch defeating hydration; race conditions from manual effects.
- **Medium**: missing empty/error UI (High when a failed load leaves the UI stuck, e.g. a spinner that never clears); an optimistic update missing its rollback (settle invalidation present), `cancelQueries`, or settle invalidation (rollback present) (`Optimistic`); client-fetching public data a Server Component should own (`RSC-Boundary`); truly cosmetic key instability (string-vs-array of same data).
- **Low**: fetch logic written inline in the options object (`Inline-Fn`; the thin `queryFn: () => fetchUser(id)` wrapper is idiomatic and never a finding); default `staleTime: 0` where freshness isn't required and focus refetch is off.

No Category value is left unscored. Where a value appears in more than one band, the band naming your defect's condition wins; where two fit equally, take the higher. `staleTime: 0` with `refetchOnWindowFocus` on (its default) on stable data is `Stale-Time` at Medium - bounded, but a refetch on every tab focus.

## Avoid

- Inline `queryFn: () => fetch(...)` closures that capture changing props without the variable in the key.
- An unguarded module-scope `new QueryClient()` in Next.js (cross-request leakage); use `getQueryClient()` or construct inside `useState` in a Client Component.
- `staleTime: 0` plus `refetchOnWindowFocus: true` for stable data (refetch storm on tab focus).
- Optimistic updates without `cancelQueries` + snapshot + `onError` rollback.
