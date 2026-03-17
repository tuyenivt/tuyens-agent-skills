---
name: vue-data-fetching
description: Vue data fetching patterns - Nuxt useFetch/useAsyncData, TanStack Query Vue, composable-based fetching, Suspense integration, and cache management for Vue 3.5+.
metadata:
  category: frontend
  tags: [vue, data-fetching, usefetch, useasyncdata, tanstack-query, suspense, caching]
user-invocable: false
---

# Vue Data Fetching

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Implementing data fetching for Vue components
- Choosing between Nuxt composables and TanStack Query
- Adding caching, optimistic updates, or infinite queries
- Setting up composable-based data fetching for Vite projects
- Reviewing data fetching patterns for correctness and performance

## Rules

- Never use raw `fetch()` in Nuxt components - use `useFetch` or `useAsyncData` (misses SSR hydration)
- In Vite projects, use TanStack Query Vue for all API data
- Every data-fetching component must handle loading, error, and empty states
- Prefer `useLazyFetch` for non-critical data that shouldn't block navigation
- Mutations must refresh affected queries - stale data after writes is a bug
- Use `$fetch` (not `fetch`) in Nuxt for type-safe, SSR-compatible requests outside composables

## Patterns

### Data Fetching Decision Tree

```
Nuxt project?
  Yes -> Is the data needed at initial render?
    Yes -> useFetch (blocks navigation, SSR-rendered)
    No  -> useLazyFetch (non-blocking, client-side)
  No (Vite) -> TanStack Query Vue
Need complex caching, optimistic updates, or infinite scroll?
  Yes -> TanStack Query Vue (works in both Nuxt and Vite)
```

### Nuxt useFetch

```vue
<script setup lang="ts">
// Basic fetch - blocks navigation, SSR-rendered
const {
  data: products,
  status,
  error,
  refresh,
} = await useFetch("/api/products");

// With reactive query parameters
const page = ref(1);
const category = ref("all");

const { data, status: fetchStatus } = await useFetch("/api/products", {
  query: { page, category },
  watch: [page, category],
});

// With transform for type narrowing
const { data: names } = await useFetch("/api/products", {
  transform: (products) => products.map((p) => p.name),
});
</script>

<template>
  <div v-if="status === 'pending'"><ProductSkeleton /></div>
  <div v-else-if="error">
    <ErrorState :message="error.message" @retry="refresh()" />
  </div>
  <div v-else-if="!products?.length">
    <EmptyState message="No products found" />
  </div>
  <ul v-else>
    <li v-for="product in products" :key="product.id">
      <ProductCard :product="product" />
    </li>
  </ul>
</template>
```

### Nuxt useLazyFetch (Non-Blocking)

```vue
<script setup lang="ts">
// Doesn't block navigation - page renders immediately with loading state
const { data: recommendations, status } = useLazyFetch("/api/recommendations");
</script>

<template>
  <section>
    <h2>Recommended for You</h2>
    <div v-if="status === 'pending'"><RecommendationSkeleton /></div>
    <ProductGrid
      v-else-if="recommendations?.length"
      :products="recommendations"
    />
  </section>
</template>
```

### Nuxt useAsyncData

```vue
<script setup lang="ts">
// For non-fetch async operations
const { data: stats } = await useAsyncData("dashboard-stats", () =>
  $fetch("/api/dashboard/stats")
);

// Combine multiple fetches
const { data } = await useAsyncData("product-detail", async () => {
  const [product, reviews] = await Promise.all([
    $fetch(`/api/products/${route.params.id}`),
    $fetch(`/api/products/${route.params.id}/reviews`),
  ]);
  return { product, reviews };
});
```

### TanStack Query Vue

For complex caching, optimistic updates, or Vite projects:

```ts
// plugins/vue-query.ts (Nuxt plugin)
import {
  VueQueryPlugin,
  type VueQueryPluginOptions,
} from "@tanstack/vue-query";

export default defineNuxtPlugin((nuxt) => {
  const options: VueQueryPluginOptions = {
    queryClientConfig: {
      defaultOptions: {
        queries: {
          staleTime: 60 * 1000,
          gcTime: 5 * 60 * 1000,
          retry: 1,
        },
      },
    },
  };

  nuxt.vueApp.use(VueQueryPlugin, options);
});
```

**Basic query:**

```vue
<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";

const props = defineProps<{ userId: string }>();

const {
  data: user,
  isLoading,
  error,
} = useQuery({
  queryKey: ["user", props.userId],
  queryFn: () => $fetch(`/api/users/${props.userId}`),
});
</script>

<template>
  <ProfileSkeleton v-if="isLoading" />
  <ErrorState v-else-if="error" :message="error.message" />
  <EmptyState v-else-if="!user" message="User not found" />
  <ProfileCard v-else :user="user" />
</template>
```

**Mutation with cache invalidation:**

```vue
<script setup lang="ts">
import { useMutation, useQueryClient } from "@tanstack/vue-query";

const queryClient = useQueryClient();

const createPost = useMutation({
  mutationFn: (data: NewPost) =>
    $fetch("/api/posts", { method: "POST", body: data }),
  onSuccess: () => {
    queryClient.invalidateQueries({ queryKey: ["posts"] });
  },
  onError: (error) => {
    toast.error(error.message);
  },
});
</script>
```

**Optimistic update:**

```ts
const toggleFavorite = useMutation({
  mutationFn: (productId: string) =>
    $fetch(`/api/products/${productId}/favorite`, { method: "POST" }),
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
  },
  onSettled: () => {
    queryClient.invalidateQueries({ queryKey: ["products"] });
  },
});
```

**Infinite query:**

```vue
<script setup lang="ts">
import { useInfiniteQuery } from "@tanstack/vue-query";

const { data, fetchNextPage, hasNextPage, isFetchingNextPage } =
  useInfiniteQuery({
    queryKey: ["products", category],
    queryFn: ({ pageParam }) =>
      $fetch("/api/products", {
        query: { cursor: pageParam, category: category.value },
      }),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) => lastPage.nextCursor,
  });

const products = computed(
  () => data.value?.pages.flatMap((page) => page.items) ?? [],
);
</script>

<template>
  <ProductCard
    v-for="product in products"
    :key="product.id"
    :product="product"
  />
  <button
    v-if="hasNextPage"
    :disabled="isFetchingNextPage"
    @click="fetchNextPage()"
  >
    {{ isFetchingNextPage ? "Loading..." : "Load more" }}
  </button>
</template>
```

### `$fetch` vs `useFetch` in Nuxt

`useFetch` is for component setup (reactive, SSR-aware). `$fetch` is for imperative contexts:

```ts
// Event handlers - use $fetch, not useFetch
async function handleAddToCart(productId: string) {
  await $fetch("/api/cart", { method: "POST", body: { productId } });
}

// Pinia actions - use $fetch
export const useCartStore = defineStore("cart", () => {
  async function addItem(productId: string) {
    const item = await $fetch(`/api/cart/items`, {
      method: "POST",
      body: { productId },
    });
    items.value.push(item);
  }
});
```

**Bad** - useFetch in event handler:

```ts
async function handleSubmit() {
  const { data } = await useFetch("/api/submit", { method: "POST" }); // wrong context!
}
```

### Composable-Based Fetching (Vite, no TanStack Query)

```ts
// composables/useProducts.ts (Vite projects only - not for Nuxt)
export function useProducts(category: MaybeRefOrGetter<string>) {
  const products = ref<Product[]>([]);
  const loading = ref(true);
  const error = ref<Error | null>(null);

  async function fetchProducts() {
    loading.value = true;
    error.value = null;
    try {
      const response = await fetch(
        `/api/products?category=${toValue(category)}`,
      );
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      products.value = await response.json();
    } catch (e) {
      error.value = e as Error;
    } finally {
      loading.value = false;
    }
  }

  watchEffect(() => {
    fetchProducts();
  });

  return {
    products: readonly(products),
    loading,
    error,
    refresh: fetchProducts,
  };
}
```

Note: This pattern is a fallback for Vite projects without TanStack Query. Prefer TanStack Query for caching, deduplication, and retry.

### Query Key Organization

```ts
const queryKeys = {
  products: {
    all: ["products"] as const,
    lists: () => [...queryKeys.products.all, "list"] as const,
    list: (filters: ProductFilters) =>
      [...queryKeys.products.lists(), filters] as const,
    details: () => [...queryKeys.products.all, "detail"] as const,
    detail: (id: string) => [...queryKeys.products.details(), id] as const,
  },
  users: {
    all: ["users"] as const,
    detail: (id: string) => [...queryKeys.users.all, id] as const,
  },
};
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Data Fetching Architecture

**Stack:** {Nuxt 3 | Vite + Vue}
**Data library:** {useFetch | TanStack Query Vue}

### Data Sources

| Data              | Fetch Method        | Cache Strategy   | Invalidation        |
| ----------------- | ------------------- | ---------------- | ------------------- |
| {data name}       | useFetch (SSR)      | ISR (3600s)      | refresh()           |
| {data name}       | TanStack Query      | staleTime: 60s   | invalidateQueries   |
| {data name}       | useLazyFetch        | -                | refresh()           |

### Query Keys (if TanStack Query)

| Key                        | Component(s)        | Dependent On     |
| -------------------------- | ------------------- | ---------------- |
| ["products", category]     | ProductList         | -                |
| ["user", userId]           | UserProfile         | -                |

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

- Using raw `fetch()` in Nuxt components (breaks SSR hydration)
- Using `useFetch` for non-critical data that blocks navigation (use `useLazyFetch`)
- Forgetting to handle loading, error, and empty states
- Storing API data in Pinia when useFetch or TanStack Query handles it (duplication)
- Forgetting to invalidate/refresh after mutations (stale data)
- Setting staleTime to 0 for data that doesn't need real-time freshness (excessive refetching)
- Creating fetch functions inline in templates (recreated every render)
- Using `useAsyncData` without a unique key (cache collisions)
- Using `useFetch` in event handlers or Pinia actions (use `$fetch` for imperative contexts)
