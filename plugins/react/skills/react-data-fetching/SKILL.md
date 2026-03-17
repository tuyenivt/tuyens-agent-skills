---
name: react-data-fetching
description: React data fetching patterns - TanStack Query (primary), SWR, Server Components data fetching, Suspense boundaries, optimistic updates, and cache invalidation for React 19+.
metadata:
  category: frontend
  tags: [react, data-fetching, tanstack-query, swr, suspense, caching, optimistic-updates]
user-invocable: false
---

# React Data Fetching

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Implementing data fetching for React components
- Choosing between Server Component fetching and client-side fetching
- Setting up TanStack Query or SWR for client-side data
- Adding caching, optimistic updates, or infinite queries
- Reviewing data fetching patterns for correctness and performance

## Rules

- Never fetch data in useEffect with manual state management - use TanStack Query, SWR, or Server Components
- Server Components fetch data directly (async/await) - no hooks needed
- Client Components use TanStack Query (primary) or SWR for all API data
- Every data-fetching component must handle loading, error, and empty states
- Query keys must be stable and descriptive - include all variables that affect the query result
- Mutations must invalidate affected queries - stale data after writes is a bug
- Prefer Server Components for initial data; hydrate to TanStack Query for client interactivity

## Patterns

### Data Fetching Decision Tree

```
Is the data needed at render time (not interactive)?
  Yes → Server Component (async fetch)
  No → Is the data user-specific or requires real-time updates?
    Yes → TanStack Query in Client Component
    No → Server Component with ISR (revalidate)
```

### Server Component Fetching

```tsx
// Direct data access in Server Components
async function ProductPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const product = await db.product.findUnique({ where: { id } });
  if (!product) notFound();

  return (
    <div>
      <ProductDetails product={product} />
      <Suspense fallback={<ReviewsSkeleton />}>
        <ProductReviews productId={id} /> {/* streams in */}
      </Suspense>
    </div>
  );
}
```

### TanStack Query Setup

```tsx
// providers.tsx
"use client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";
import { useState } from "react";

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60 * 1000, // 1 minute
            gcTime: 5 * 60 * 1000, // 5 minutes
            retry: 1,
            refetchOnWindowFocus: false,
          },
        },
      }),
  );

  return (
    <QueryClientProvider client={queryClient}>
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  );
}
```

### Query Patterns

**Basic query:**

```tsx
function UserProfile({ userId }: { userId: string }) {
  const {
    data: user,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => fetchUser(userId),
  });

  if (isLoading) return <ProfileSkeleton />;
  if (error) return <ErrorState message="Failed to load profile" />;
  if (!user) return <EmptyState message="User not found" />;

  return <ProfileCard user={user} />;
}
```

**Dependent query:**

```tsx
function UserPosts({ userId }: { userId: string }) {
  const { data: user } = useQuery({
    queryKey: ["user", userId],
    queryFn: () => fetchUser(userId),
  });

  const { data: posts, isLoading } = useQuery({
    queryKey: ["user", userId, "posts"],
    queryFn: () => fetchUserPosts(userId),
    enabled: !!user, // only fetch posts after user is loaded
  });
  // ...
}
```

**Infinite query (pagination):**

```tsx
function ProductList({ category }: { category: string }) {
  const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ["products", category],
      queryFn: ({ pageParam }) =>
        fetchProducts({ category, cursor: pageParam }),
      initialPageParam: undefined as string | undefined,
      getNextPageParam: (lastPage) => lastPage.nextCursor,
    });

  const products = data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <>
      {products.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
      {hasNextPage && (
        <button onClick={() => fetchNextPage()} disabled={isFetchingNextPage}>
          {isFetchingNextPage ? "Loading..." : "Load more"}
        </button>
      )}
    </>
  );
}
```

### Mutation Patterns

**Basic mutation with cache invalidation:**

```tsx
function CreatePostForm() {
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: createPost,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["posts"] });
    },
    onError: (error) => {
      toast.error(error.message);
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate(new FormData(e.currentTarget));
      }}
    >
      <input name="title" required />
      <button disabled={mutation.isPending}>
        {mutation.isPending ? "Creating..." : "Create"}
      </button>
    </form>
  );
}
```

**Optimistic update:**

```tsx
const toggleFavorite = useMutation({
  mutationFn: (productId: string) => api.toggleFavorite(productId),
  onMutate: async (productId) => {
    await queryClient.cancelQueries({ queryKey: ["products"] });
    const previous = queryClient.getQueryData<Product[]>(["products"]);

    queryClient.setQueryData<Product[]>(["products"], (old) =>
      old?.map((p) =>
        p.id === productId ? { ...p, isFavorite: !p.isFavorite } : p,
      ),
    );

    return { previous };
  },
  onError: (_err, _productId, context) => {
    queryClient.setQueryData(["products"], context?.previous);
    toast.error("Failed to update favorite");
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: ["products"] });
  },
});
```

### Server-to-Client Hydration

Prefetch on server, hydrate on client for instant interactivity:

```tsx
// app/dashboard/page.tsx (Server Component)
import {
  dehydrate,
  HydrationBoundary,
  QueryClient,
} from "@tanstack/react-query";

export default async function DashboardPage() {
  const queryClient = new QueryClient();
  await queryClient.prefetchQuery({
    queryKey: ["dashboard-stats"],
    queryFn: fetchDashboardStats,
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <DashboardClient />{" "}
      {/* Client Component uses same query key - instant data */}
    </HydrationBoundary>
  );
}
```

### SWR Alternative

When the project uses SWR instead of TanStack Query:

```tsx
import useSWR from "swr";
import useSWRMutation from "swr/mutation";

const fetcher = (url: string) => fetch(url).then((r) => r.json());

function UserProfile({ userId }: { userId: string }) {
  const {
    data: user,
    error,
    isLoading,
  } = useSWR<User>(`/api/users/${userId}`, fetcher);

  if (isLoading) return <ProfileSkeleton />;
  if (error) return <ErrorState message="Failed to load profile" />;
  if (!user) return <EmptyState message="User not found" />;

  return <ProfileCard user={user} />;
}

// SWR mutation with revalidation
function CreatePostButton() {
  const { trigger, isMutating } = useSWRMutation(
    "/api/posts",
    async (url, { arg }: { arg: NewPost }) => {
      const res = await fetch(url, {
        method: "POST",
        body: JSON.stringify(arg),
      });
      return res.json();
    },
  );

  return (
    <button
      onClick={() => trigger({ title: "New Post" })}
      disabled={isMutating}
    >
      {isMutating ? "Creating..." : "Create"}
    </button>
  );
}
```

SWR uses the fetch URL as the cache key by default. TanStack Query is preferred for complex scenarios (dependent queries, optimistic updates, infinite queries) due to its richer API.

### Query Key Organization

```tsx
// Centralize query keys for consistency
const queryKeys = {
  users: {
    all: ["users"] as const,
    lists: () => [...queryKeys.users.all, "list"] as const,
    list: (filters: UserFilters) => [...queryKeys.users.lists(), filters] as const,
    details: () => [...queryKeys.users.all, "detail"] as const,
    detail: (id: string) => [...queryKeys.users.details(), id] as const,
  },
  posts: {
    all: ["posts"] as const,
    byUser: (userId: string) => [...queryKeys.posts.all, "user", userId] as const,
  },
}

// Usage:
useQuery({ queryKey: queryKeys.users.detail(userId), queryFn: ... })
queryClient.invalidateQueries({ queryKey: queryKeys.users.all })  // invalidates all user queries
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Data Fetching Architecture

**Stack:** {Next.js | Vite + React}
**Data library:** {TanStack Query | SWR}

### Data Sources

| Data              | Fetch Method        | Cache Strategy   | Invalidation        |
| ----------------- | ------------------- | ---------------- | ------------------- |
| {data name}       | Server Component    | ISR (3600s)      | revalidateTag       |
| {data name}       | TanStack Query      | staleTime: 60s   | invalidateQueries   |

### Query Keys

| Key                        | Component(s)        | Dependent On     |
| -------------------------- | ------------------- | ---------------- |
| ["users", userId]          | UserProfile         | -                |
| ["users", userId, "posts"] | UserPosts           | user query       |

### Mutations

| Mutation          | Invalidates          | Optimistic Update |
| ----------------- | -------------------- | ----------------- |
| {mutationName}    | {query keys}         | {Yes | No}        |

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Fetching data in useEffect with useState (no caching, no deduplication, race conditions)
- Using the same query key for different data (cache collisions)
- Forgetting to invalidate queries after mutations (stale data)
- Setting staleTime to 0 for data that doesn't need real-time freshness (excessive refetching)
- Fetching in Client Components when a Server Component could fetch directly
- Creating query functions inline (recreated every render, defeats memoization)
- Not handling loading and error states (blank screens, silent failures)
- Using fetch directly instead of query functions (loses type safety and reusability)
