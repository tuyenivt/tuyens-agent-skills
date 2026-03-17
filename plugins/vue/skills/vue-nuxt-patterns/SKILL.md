---
name: vue-nuxt-patterns
description: Nuxt 3 patterns - auto-imports, server routes, useFetch/useAsyncData, Nitro server engine, middleware, SEO with useHead/useSeoMeta, and hybrid rendering for Nuxt 3.
metadata:
  category: frontend
  tags: [nuxt, server-routes, usefetch, useasyncdata, nitro, seo, auto-imports, hybrid-rendering]
user-invocable: false
---

# Nuxt 3 Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building features with Nuxt 3
- Using auto-imports, server routes, and Nuxt composables
- Implementing data fetching with useFetch/useAsyncData
- Configuring SEO, metadata, and hybrid rendering
- Setting up server-side middleware and Nitro API routes

## Rules

- Use Nuxt auto-imports - do not manually import Vue APIs, Nuxt composables, or components in the `components/` directory
- Server routes (`server/api/`, `server/routes/`) must validate all input - they are public HTTP endpoints
- Use `useFetch` or `useAsyncData` for data fetching - never raw `fetch` in components (misses SSR hydration)
- SEO metadata must use `useHead` or `useSeoMeta` - not manual `<head>` manipulation
- Prefer static/ISR rendering by default; opt into SSR only when needed (cookies, real-time personalization)
- Server-only utilities must live in `server/` directory - never import them in client code

## Patterns

### Auto-Imports

Nuxt auto-imports Vue APIs, Nuxt composables, components, and utilities:

```vue
<script setup lang="ts">
// No imports needed - these are all auto-imported:
const route = useRoute();
const { data } = await useFetch("/api/products");
const count = ref(0);
const doubled = computed(() => count.value * 2);
</script>

<template>
  <!-- Components in components/ are auto-imported -->
  <ProductCard v-for="product in data" :key="product.id" :product="product" />
</template>
```

**Bad** - Manual imports of auto-imported APIs:

```vue
<script setup lang="ts">
import { ref, computed } from "vue"; // unnecessary in Nuxt
import { useRoute } from "vue-router"; // unnecessary in Nuxt
</script>
```

### Server Routes (Nitro)

```ts
// server/api/products/index.get.ts
export default defineEventHandler(async (event) => {
  const query = getQuery(event);
  const page = parseInt((query.page as string) || "1");
  const products = await db.product.findMany({
    skip: (page - 1) * 20,
    take: 20,
  });
  return products;
});

// server/api/products/index.post.ts
import { z } from "zod";

const CreateProductSchema = z.object({
  name: z.string().min(1).max(200),
  price: z.number().positive(),
  category: z.string(),
});

export default defineEventHandler(async (event) => {
  const body = await readBody(event);
  const parsed = CreateProductSchema.safeParse(body);

  if (!parsed.success) {
    throw createError({
      statusCode: 400,
      data: parsed.error.flatten(),
    });
  }

  const product = await db.product.create({ data: parsed.data });
  return product;
});

// server/api/products/[id].get.ts
export default defineEventHandler(async (event) => {
  const id = getRouterParam(event, "id");
  const product = await db.product.findUnique({ where: { id } });

  if (!product) {
    throw createError({ statusCode: 404, message: "Product not found" });
  }

  return product;
});
```

### useFetch and useAsyncData

**useFetch** - Convenience wrapper for fetching from API routes:

```vue
<script setup lang="ts">
const {
  data: products,
  status,
  error,
  refresh,
} = await useFetch("/api/products", {
  query: { category: selectedCategory },
});
</script>

<template>
  <div v-if="status === 'pending'">
    <ProductListSkeleton />
  </div>
  <div v-else-if="error">
    <ErrorState :message="error.message" @retry="refresh()" />
  </div>
  <div v-else-if="!products?.length">
    <EmptyState message="No products found" />
  </div>
  <div v-else>
    <ProductCard
      v-for="product in products"
      :key="product.id"
      :product="product"
    />
  </div>
</template>
```

**useAsyncData** - For non-fetch async operations or custom data sources:

```vue
<script setup lang="ts">
const { data: stats } = await useAsyncData("dashboard-stats", () =>
  $fetch("/api/dashboard/stats")
);

// With transform
const { data: productNames } = await useAsyncData(
  "product-names",
  () => $fetch("/api/products"),
  {
    transform: (products) => products.map((p) => p.name),
  }
);
```

**Reactive query parameters:**

```vue
<script setup lang="ts">
const page = ref(1);
const category = ref("all");

const { data: products, status } = await useFetch("/api/products", {
  query: { page, category }, // reactive - refetches when page or category changes
  watch: [page, category],
});
</script>
```

**Lazy fetching** - Don't block navigation:

```vue
<script setup lang="ts">
// useLazyFetch doesn't block navigation - page renders immediately
const { data, status } = useLazyFetch("/api/products");
</script>
```

### Hybrid Rendering

Configure per-route rendering strategy:

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  routeRules: {
    "/": { prerender: true }, // SSG at build time
    "/products/**": { swr: 3600 }, // ISR: revalidate every hour
    "/dashboard/**": { ssr: true }, // SSR on every request
    "/admin/**": { ssr: false }, // SPA only (client-side)
  },
});
```

### SEO and Metadata

```vue
<script setup lang="ts">
// Static metadata
useSeoMeta({
  title: "Product Catalog",
  description: "Browse our complete product catalog",
  ogTitle: "Product Catalog",
  ogDescription: "Browse our complete product catalog",
  ogImage: "/og-products.png",
});

// Dynamic metadata
const { data: product } = await useFetch(`/api/products/${route.params.id}`);

useSeoMeta({
  title: () => product.value?.name ?? "Product",
  description: () => product.value?.description ?? "",
  ogImage: () => product.value?.image ?? "",
});
</script>
```

```vue
<script setup lang="ts">
// useHead for full control
useHead({
  title: "My App",
  meta: [{ name: "description", content: "App description" }],
  link: [{ rel: "canonical", href: "https://example.com" }],
  script: [{ src: "https://analytics.example.com/script.js", defer: true }],
});
</script>
```

### Nuxt Plugins

```ts
// plugins/api.ts
export default defineNuxtPlugin(() => {
  const api = $fetch.create({
    baseURL: "/api",
    onRequest({ options }) {
      const { token } = useAuth();
      if (token.value) {
        options.headers = new Headers(options.headers);
        options.headers.set("Authorization", `Bearer ${token.value}`);
      }
    },
    onResponseError({ response }) {
      if (response.status === 401) {
        navigateTo("/login");
      }
    },
  });

  return {
    provide: { api },
  };
});

// Usage in components: const { $api } = useNuxtApp();
```

### Server Middleware

```ts
// server/middleware/log.ts (runs on every server request)
export default defineEventHandler((event) => {
  console.log(`[${event.method}] ${getRequestURL(event)}`);
});

// server/middleware/auth.ts
export default defineEventHandler(async (event) => {
  // Only protect /api/ routes
  if (!event.path.startsWith("/api/")) return;
  // Skip auth for public endpoints
  if (event.path === "/api/auth/login") return;

  const token = getHeader(event, "authorization")?.replace("Bearer ", "");
  if (!token) {
    throw createError({ statusCode: 401, message: "Unauthorized" });
  }

  event.context.user = await verifyToken(token);
});
```

### Cookies and Request Headers

```vue
<script setup lang="ts">
// useCookie - SSR-safe cookie access (works on both server and client)
const token = useCookie("auth-token", { maxAge: 60 * 60 * 24 * 7 });
token.value = "new-token"; // sets the cookie

// useRequestHeaders - forward headers from client request during SSR
const headers = useRequestHeaders(["cookie", "authorization"]);
const { data } = await useFetch("/api/me", { headers });
</script>
```

### Runtime Config

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  runtimeConfig: {
    // Server-only (not exposed to client)
    dbUrl: "",
    secretKey: "",
    // Public (available on client)
    public: {
      apiBase: "/api",
      appName: "My App",
    },
  },
});
```

```vue
<script setup lang="ts">
const config = useRuntimeConfig();
// config.public.apiBase is available
// config.dbUrl is only available server-side
</script>
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Nuxt Architecture

**Nuxt version:** {detected version}
**Rendering strategy:** {Static | ISR | SSR | Hybrid}

### Route Configuration

| Route              | Rendering  | Revalidation | Data Source      | Auth       |
| ------------------ | ---------- | ------------ | ---------------- | ---------- |
| /                  | Prerender  | -            | None             | Public     |
| /products          | ISR        | 3600s        | Server route     | Public     |
| /dashboard         | SSR        | -            | Server route     | Protected  |

### Server Routes

| Route                  | Method | Validation    | Auth     |
| ---------------------- | ------ | ------------- | -------- |
| /api/products          | GET    | Query params  | Public   |
| /api/products          | POST   | Zod schema    | Protected|
| /api/products/:id      | GET    | -             | Public   |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Manual imports of auto-imported APIs (ref, computed, useRoute, useFetch)
- Using raw `fetch()` instead of `useFetch` / `useAsyncData` (breaks SSR hydration)
- Manual `<head>` manipulation instead of useHead/useSeoMeta
- Server routes without input validation (they are public HTTP endpoints)
- Importing server utilities in client code (exposes secrets, breaks build)
- Using `ssr: false` globally when only specific routes need client-side rendering
- Blocking navigation with heavy `useFetch` calls (use `useLazyFetch` for non-critical data)
- Hardcoding API base URLs instead of using runtime config
