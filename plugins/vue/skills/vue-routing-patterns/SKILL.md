---
name: vue-routing-patterns
description: Vue 3.5 routing - Nuxt file-based pages, Vue Router (Vite), layouts, middleware, guards, nested/dynamic routes, lazy loading.
metadata:
  category: frontend
  tags: [vue, routing, nuxt, vue-router, layouts, middleware, navigation-guards]
user-invocable: false
---

# Vue Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing route structure for a new feature or app
- Adding layouts, middleware, guards, nested or dynamic routes
- Reviewing routing for correctness, safety, and performance

## Rules

- Validate dynamic params before use (treat URL as untrusted input)
- Every navigation has defined error and loading states
- Middleware/guards read state but do not mutate it; run fast; always exclude their own redirect target to avoid loops
- Lazy-load non-initial routes via dynamic `import()` in Vue Router. Nuxt code-splits file-based pages by default - no manual `import()` needed
- In Nuxt, use file-based routing; do not hand-roll route configs. In middleware/plugins/server use `navigateTo()`, not `useRouter().push()`

## Patterns

### Nuxt file-based routing

```
pages/
  index.vue              # /
  dashboard/
    index.vue            # /dashboard
    [teamId].vue         # /dashboard/:teamId
  products/[id].vue      # /products/:id
  [...slug].vue          # catch-all
```

Layout via `<slot />` in `layouts/<name>.vue`; page opts in with `definePageMeta({ layout: '<name>' })`.

### Nuxt middleware (named + global)

```ts
// middleware/auth.ts  -> opt-in via definePageMeta({ middleware: 'auth' })
export default defineNuxtRouteMiddleware(() => {
  const { loggedIn } = useUserSession();
  if (!loggedIn.value) return navigateTo("/login");
});

// middleware/auth.global.ts  -> runs on every navigation
export default defineNuxtRouteMiddleware((to) => {
  const publicRoutes = ["/", "/login", "/signup"];
  const { loggedIn } = useUserSession();
  if (!publicRoutes.includes(to.path) && !loggedIn.value) return navigateTo("/login");
});
```

### Nuxt params, validation, fetch

```vue
<!-- pages/products/[id].vue -->
<script setup lang="ts">
definePageMeta({
  validate: (route) => /^\d+$/.test(route.params.id as string),
});
const route = useRoute();
// computed URL so useFetch refetches when params change
const { data: product } = await useFetch(() => `/api/products/${route.params.id}`);
</script>
```

### Nuxt error page

```vue
<!-- error.vue (root) -->
<script setup lang="ts">
defineProps<{ error: { statusCode: number; message: string } }>();
</script>
<template>
  <div>
    <h1>{{ error.statusCode }}</h1>
    <p>{{ error.message }}</p>
    <button @click="clearError({ redirect: '/' })">Go Home</button>
  </div>
</template>
```

### Vue Router (Vite) lazy + nested routes

Dynamic `import()` per route splits each branch into its own chunk; `children` mount under a parent layout's `<RouterView />`. `props: true` passes route params as component props - test components in isolation without `useRoute()`.

```ts
// router/index.ts
import { createRouter, createWebHistory } from "vue-router";

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/dashboard",
      component: () => import("@/layouts/DashboardLayout.vue"),
      children: [
        { path: "", component: () => import("@/pages/Dashboard.vue") },
        { path: ":teamId", component: () => import("@/pages/Team.vue"), props: true },
      ],
    },
  ],
});
```

Layout renders children via `<RouterView />` (mirrors Nuxt's `<slot />`). Access params with `useRoute()` or declare them as props with `props: true`.

### Route guards and meta

Attach guard inputs to `meta` so the guard reads declarative data instead of branching on path. `beforeEach` runs before every navigation; `beforeEnter` scopes to one route. **Always exclude the redirect target** from the predicate, else the guard loops.

```ts
// router/index.ts (route definition)
{
  path: "/dashboard",
  meta: { requiresAuth: true, roles: ["admin", "editor"] },
  component: () => import("@/layouts/DashboardLayout.vue"),
}

// router/guards.ts
router.beforeEach((to) => {
  const auth = useAuthStore();
  if (to.path === "/login") return; // allow - never guard the redirect target
  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
  const roles = to.meta.roles as string[] | undefined;
  if (roles && !roles.includes(auth.user.role)) return { path: "/forbidden" };
});
```

Compose per-route guards via `beforeEnter: [requireAuth, requireRole('admin')]`. Keep guards synchronous when possible; if a guard awaits, surface a loading state in the layout to avoid blank-screen navigations.

## Output Format

```
## Routing Design

**Stack:** {Nuxt 3 | Vue Router (Vite)}

### Route Map

| Path               | Page              | Layout    | Middleware/Guard | Access    |
| ------------------ | ----------------- | --------- | ---------------- | --------- |
| /                  | index.vue         | default   | -                | Public    |
| /dashboard         | dashboard/index   | dashboard | auth             | Protected |
| /dashboard/:teamId | dashboard/[teamId]| dashboard | auth             | Protected |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: {High | Medium | Low}] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Unconditional redirects in middleware/guards (infinite loops)
- `window.location` for navigation (breaks SPA + SSR)
- Hand-rolled route configs in Nuxt
- Eager-loading every route in Vue Router
- Heavy work in guards or middleware (runs on every matching navigation)
