---
name: vue-data-fetching
description: Vue 3.5 data fetching: Nuxt useFetch/useAsyncData, TanStack Query Vue, mutations, cache invalidation, optimistic updates.
metadata:
  category: frontend
  tags: [vue, data-fetching, usefetch, useasyncdata, tanstack-query, suspense, caching]
user-invocable: false
---

# Vue Data Fetching

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Implementing or reviewing data fetching in Vue 3 components
- Choosing between Nuxt composables and TanStack Query
- Adding caching, mutations, optimistic updates, or infinite queries

## Rules

- Nuxt: use `useFetch`/`useAsyncData` in setup; `$fetch` in event handlers, Pinia actions, or other imperative contexts. Never raw `fetch()`.
- Vite: prefer TanStack Query Vue. Hand-rolled composables only when TanStack Query is unavailable.
- Use `useLazyFetch` for non-critical data that should not block navigation.
- `useAsyncData` requires a unique key.
- Every mutation invalidates or refreshes affected queries.
- Every fetching component renders loading, error, and empty states.

## Patterns

### Choosing a Fetch Strategy

| Project    | Initial render?            | Use                |
| ---------- | -------------------------- | ------------------ |
| Nuxt       | Yes (blocks navigation)    | `useFetch`         |
| Nuxt       | No (renders, then loads)   | `useLazyFetch`     |
| Nuxt/Vite  | Caching, mutations, paging | TanStack Query Vue |

### Nuxt useFetch

```vue
<script setup lang="ts">
const page = ref(1);
const { data: products, status, error, refresh } = await useFetch("/api/products", {
  query: { page },
  watch: [page],
});
</script>

<template>
  <ProductSkeleton v-if="status === 'pending'" />
  <ErrorState v-else-if="error" :message="error.message" @retry="refresh()" />
  <EmptyState v-else-if="!products?.length" message="No products" />
  <template v-else>
    <ProductCard v-for="p in products" :key="p.id" :product="p" />
  </template>
</template>
```

`useLazyFetch` has the same shape but does not block navigation. Use it for below-the-fold or non-critical sections.

### Nuxt useAsyncData

For non-`$fetch` async work or combining multiple requests. Always pass a unique key.

```ts
const { data } = await useAsyncData(`product-${id}`, async () => {
  const [product, reviews] = await Promise.all([
    $fetch(`/api/products/${id}`),
    $fetch(`/api/products/${id}/reviews`),
  ]);
  return { product, reviews };
});
```

### `$fetch` in Imperative Contexts

`useFetch` is setup-only. Event handlers, Pinia actions, and watchers use `$fetch`.

```ts
// Bad: useFetch in event handler
async function submit() { await useFetch("/api/submit", { method: "POST" }); }

// Good
async function submit() { await $fetch("/api/submit", { method: "POST" }); }
```

### TanStack Query Vue

Register once (Nuxt plugin or Vite `app.use`):

```ts
app.use(VueQueryPlugin, {
  queryClientConfig: {
    defaultOptions: { queries: { staleTime: 60_000, gcTime: 5 * 60_000, retry: 1 } },
  },
});
```

Query:

```ts
const { data: user, isLoading, error } = useQuery({
  queryKey: ["user", () => props.userId],
  queryFn: () => $fetch(`/api/users/${props.userId}`),
});
```

Mutation with invalidation:

```ts
const qc = useQueryClient();
const createPost = useMutation({
  mutationFn: (body: NewPost) => $fetch("/api/posts", { method: "POST", body }),
  onSuccess: () => qc.invalidateQueries({ queryKey: ["posts"] }),
});
```

Optimistic update - cancel, snapshot, mutate, rollback on error, refetch on settle:

```ts
const toggleFavorite = useMutation({
  mutationFn: (id: string) => $fetch(`/api/products/${id}/favorite`, { method: "POST" }),
  onMutate: async (id) => {
    await qc.cancelQueries({ queryKey: ["products"] });
    const previous = qc.getQueryData<Product[]>(["products"]);
    qc.setQueryData<Product[]>(["products"], (old) =>
      old?.map((p) => (p.id === id ? { ...p, isFavorite: !p.isFavorite } : p)),
    );
    return { previous };
  },
  onError: (_e, _id, ctx) => qc.setQueryData(["products"], ctx?.previous),
  onSettled: () => qc.invalidateQueries({ queryKey: ["products"] }),
});
```

Infinite query:

```ts
const { data, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
  queryKey: ["products", category],
  queryFn: ({ pageParam }) => $fetch("/api/products", { query: { cursor: pageParam } }),
  initialPageParam: undefined as string | undefined,
  getNextPageParam: (last) => last.nextCursor,
});
const items = computed(() => data.value?.pages.flatMap((p) => p.items) ?? []);
```

### Query Key Organization

Centralize keys so invalidation targets are explicit and typo-proof.

```ts
const keys = {
  products: {
    all: ["products"] as const,
    list: (f: ProductFilters) => [...keys.products.all, "list", f] as const,
    detail: (id: string) => [...keys.products.all, "detail", id] as const,
  },
};
```

## Output Format

```
## Data Fetching Architecture

**Stack:** {Nuxt 3 | Vite + Vue}
**Data library:** {useFetch | TanStack Query Vue | Composable}

### Data Sources

| Data        | Fetch Method     | Cache Strategy   | Invalidation       |
| ----------- | ---------------- | ---------------- | ------------------ |
| {name}      | useFetch         | ISR (3600s)      | refresh()          |
| {name}      | TanStack Query   | staleTime: 60s   | invalidateQueries  |
| {name}      | useLazyFetch     | -                | refresh()          |

### Query Keys (if TanStack Query)

| Key                    | Component(s) | Dependent On |
| ---------------------- | ------------ | ------------ |
| ["products", category] | ProductList  | category     |

### Mutations

| Mutation       | Invalidates  | Optimistic Update |
| -------------- | ------------ | ----------------- |
| {mutationName} | {query keys} | {Yes | No}        |

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Mirroring server data into Pinia when the query library already caches it.
- `staleTime: 0` on data that does not need real-time freshness (refetch storms).
- Inline fetch functions in templates (recreated every render).
