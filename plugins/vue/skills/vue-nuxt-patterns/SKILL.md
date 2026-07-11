---
name: vue-nuxt-patterns
description: "Nuxt 3 patterns: auto-imports, Nitro server routes, hybrid rendering (SSG/ISR/SSR), useHead/useSeoMeta, server middleware, runtime config."
metadata:
  category: frontend
  tags: [nuxt, server-routes, nitro, seo, auto-imports, hybrid-rendering, middleware]
user-invocable: false
---

# Nuxt 3 Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

For useFetch / useAsyncData / $fetch / useLazyFetch usage, defer to `vue-data-fetching`. This skill covers Nuxt-specific concerns: server routes, rendering, SEO, middleware, config.

## When to Use

- Building or reviewing Nuxt 3 features
- Designing Nitro server routes and middleware
- Choosing per-route rendering strategy (SSG / ISR / SSR / SPA)
- Configuring SEO metadata and runtime config

## Rules

- Do not manually import auto-imported Vue APIs, Nuxt composables, or files in `components/`, `composables/`, `utils/`.
- Server routes (`server/api/`, `server/routes/`) must validate every input with a schema (Zod or equivalent).
- Server-only code must live under `server/` and never be imported from client code.
- SEO metadata uses `useHead` or `useSeoMeta`. No manual `<head>` mutation.
- Secrets go in `runtimeConfig` (server only). Only `runtimeConfig.public` reaches the client.

## Patterns

### Auto-Imports

```vue
<script setup lang="ts">
// All auto-imported in Nuxt - no `import` line needed
const route = useRoute();
const count = ref(0);
const doubled = computed(() => count.value * 2);
</script>

<template>
  <!-- Components in components/ are auto-registered -->
  <ProductCard v-for="p in products" :key="p.id" :product="p" />
</template>
```

Bad - explicit imports of auto-imported APIs add noise and break refactoring:

```ts
import { ref, computed } from "vue";
import { useRoute } from "vue-router";
```

### Nitro Server Routes

File-based routing: `server/api/products/[id].get.ts` -> `GET /api/products/:id`.

```ts
// server/api/products/index.post.ts
import { z } from "zod";

const CreateProduct = z.object({
  name: z.string().min(1).max(200),
  price: z.number().positive(),
  category: z.string(),
});

export default defineEventHandler(async (event) => {
  const parsed = CreateProduct.safeParse(await readBody(event));
  if (!parsed.success) {
    throw createError({ statusCode: 400, data: parsed.error.flatten() });
  }
  return db.product.create({ data: parsed.data });
});
```

Read input via `getQuery(event)`, `getRouterParam(event, "id")`, `readBody(event)`, `getHeader(event, ...)`. Prefer the validating helpers `readValidatedBody(event, schema.safeParse)` and `getValidatedQuery(event, schema.safeParse)` to read and validate in one step. Throw via `createError({ statusCode, message })` -- never return bare error objects.

### Hybrid Rendering

Pick rendering per route in `nuxt.config.ts`:

```ts
export default defineNuxtConfig({
  routeRules: {
    "/": { prerender: true },           // SSG at build
    "/products/**": { swr: 3600 },      // cache on server, revalidate hourly
    "/blog/**": { isr: 3600 },          // cache on CDN (Netlify/Vercel), revalidate hourly
    "/dashboard/**": { ssr: true },     // SSR every request
    "/admin/**": { ssr: false },        // client-only SPA
  },
});
```

Default to `prerender`, `swr`, or `isr` (`isr` when deploying to Netlify/Vercel for CDN-edge caching; `swr` otherwise). Use `ssr: true` only when the response depends on cookies, headers, or per-request personalization. Use `ssr: false` only for authenticated app shells where SEO is irrelevant.

### SEO Metadata

```vue
<script setup lang="ts">
const route = useRoute();
const { data: product } = await useFetch(`/api/products/${route.params.id}`);

// Reactive - functions re-run when product loads
useSeoMeta({
  title: () => product.value?.name ?? "Product",
  description: () => product.value?.description ?? "",
  ogImage: () => product.value?.image ?? "",
});
</script>
```

Use `useSeoMeta` for OG / Twitter / description fields (typed). Use `useHead` only for things `useSeoMeta` cannot express (canonical link, custom scripts, JSON-LD).

### Server Middleware

Runs on every server request, before route handlers.

```ts
// server/middleware/auth.ts
export default defineEventHandler(async (event) => {
  if (!event.path.startsWith("/api/")) return;
  if (event.path === "/api/auth/login") return;

  const token = getHeader(event, "authorization")?.replace("Bearer ", "");
  if (!token) throw createError({ statusCode: 401, message: "Unauthorized" });

  event.context.user = await verifyToken(token);
});
```

Attach derived values to `event.context` so route handlers read them without re-parsing.

### Runtime Config and Secrets

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  runtimeConfig: {
    dbUrl: "",                          // server only
    secretKey: "",                      // server only
    public: { apiBase: "/api" },        // exposed to client
  },
});
```

```ts
const config = useRuntimeConfig();
// config.public.apiBase   - client + server
// config.dbUrl            - server only; undefined on client
```

Keep placeholders empty in `nuxt.config.ts`; real values come from env vars at runtime (`NUXT_DB_URL`, `NUXT_SECRET_KEY`, `NUXT_PUBLIC_API_BASE`). Never hardcode secrets in the config file.

### SSR-Safe Cookies and Header Forwarding

```vue
<script setup lang="ts">
// useCookie - SSR-safe, reactive both sides
const token = useCookie("auth-token", { maxAge: 60 * 60 * 24 * 7 });

// Forward client headers to internal $fetch during SSR
const headers = useRequestHeaders(["cookie", "authorization"]);
const { data } = await useFetch("/api/me", { headers });
</script>
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Nuxt Architecture

**Nuxt version:** {detected version}
**Rendering strategy:** {Static | ISR | SSR | Hybrid}

### Route Configuration

| Route          | Rendering | Revalidation | Data Source  | Auth      |
| -------------- | --------- | ------------ | ------------ | --------- |
| /              | Prerender | -            | None         | Public    |
| /products      | ISR       | 3600s        | Server route | Public    |
| /dashboard     | SSR       | -            | Server route | Protected |

Rendering values: `{Prerender | SWR | ISR | SSR | SPA}`.

### Server Routes

| Route             | Method | Validation       | Auth      |
| ----------------- | ------ | ---------------- | --------- |
| /api/products     | GET    | Query (Zod)      | Public    |
| /api/products     | POST   | Body (Zod)       | Protected |
| /api/products/:id | GET    | Param (Zod)      | Public    |

Validation values: `{Zod | Valibot | Manual | None}`. `None` is always an issue.

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Global `ssr: false` when only an admin shell needs it (kills SEO everywhere).
- Importing `server/` modules from client code (leaks secrets, breaks build).
- Hardcoded API base URLs instead of `runtimeConfig.public`.
- Secrets under `runtimeConfig.public` (ships to the browser).
