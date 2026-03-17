---
name: vue-routing-patterns
description: Vue routing patterns - Vue Router (Vite) and Nuxt file-based routing, layouts, middleware, navigation guards, nested routes, and lazy loading for Vue 3.5+.
metadata:
  category: frontend
  tags: [vue, routing, nuxt, vue-router, layouts, middleware, navigation-guards]
user-invocable: false
---

# Vue Routing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing route structure for a new feature or application
- Choosing between Nuxt file-based routing and Vue Router configuration
- Adding layouts, middleware, or navigation guards
- Implementing nested routes, dynamic segments, or catch-all routes
- Reviewing routing for correctness and performance

## Rules

- Every route must have error handling - unhandled errors should not crash the entire app
- Loading states must be defined for routes that fetch data - no blank screens during navigation
- Route parameters must be validated before use - never trust URL params as safe input
- Middleware must be fast and stateless - it runs on every matching navigation
- Prefer Nuxt file-based routing conventions when using Nuxt - do not fight the framework
- Lazy-load routes that are not part of the initial navigation

## Patterns

### Nuxt File-Based Routing

```
pages/
  index.vue              # / (home)
  about.vue              # /about
  dashboard/
    index.vue            # /dashboard
    settings.vue         # /dashboard/settings
    [teamId].vue         # /dashboard/:teamId (dynamic segment)
  products/
    index.vue            # /products
    [id].vue             # /products/:id
  [...slug].vue          # catch-all: /any/path/here
```

### Nuxt Layouts

```
layouts/
  default.vue            # Default layout for all pages
  dashboard.vue          # Dashboard-specific layout
```

```vue
<!-- layouts/dashboard.vue -->
<template>
  <div class="flex">
    <Sidebar />
    <main class="flex-1">
      <slot />
      <!-- page content renders here -->
    </main>
  </div>
</template>
```

```vue
<!-- pages/dashboard/index.vue -->
<script setup lang="ts">
definePageMeta({
  layout: "dashboard",
});
</script>

<template>
  <div>
    <h1>Dashboard</h1>
  </div>
</template>
```

### Nuxt Middleware

```ts
// middleware/auth.ts (named middleware)
export default defineNuxtRouteMiddleware((to) => {
  const { loggedIn } = useUserSession();

  if (!loggedIn.value) {
    return navigateTo("/login");
  }
});
```

```vue
<!-- pages/dashboard/index.vue -->
<script setup lang="ts">
definePageMeta({
  middleware: "auth",
});
</script>
```

```ts
// middleware/auth.global.ts (global middleware - runs on every route)
export default defineNuxtRouteMiddleware((to) => {
  const publicRoutes = ["/", "/login", "/signup"];
  const { loggedIn } = useUserSession();

  if (!publicRoutes.includes(to.path) && !loggedIn.value) {
    return navigateTo("/login");
  }
});
```

**Bad** - Middleware with unconditional redirect (infinite loop):

```ts
export default defineNuxtRouteMiddleware(() => {
  return navigateTo("/login"); // always redirects, even from /login!
});
```

### Nuxt Route Parameters

```vue
<!-- pages/products/[id].vue -->
<script setup lang="ts">
const route = useRoute();
const productId = computed(() => route.params.id as string);

// Use a computed URL so useFetch refetches when route params change
const { data: product } = await useFetch(
  computed(() => `/api/products/${productId.value}`),
);
</script>
```

### Nuxt Route Validation

```vue
<!-- pages/products/[id].vue -->
<script setup lang="ts">
definePageMeta({
  validate: async (route) => {
    // Only allow numeric IDs
    return /^\d+$/.test(route.params.id as string);
  },
});
</script>
```

### Nuxt Error Pages

```vue
<!-- error.vue (root level - handles all unhandled errors) -->
<script setup lang="ts">
const props = defineProps<{
  error: {
    statusCode: number;
    message: string;
  };
}>();

function handleClear() {
  clearError({ redirect: "/" });
}
</script>

<template>
  <div>
    <h1>{{ error.statusCode }}</h1>
    <p>{{ error.message }}</p>
    <button @click="handleClear">Go Home</button>
  </div>
</template>
```

### Vue Router (Vite) Patterns

```ts
// router/index.ts
import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      component: () => import("@/layouts/DefaultLayout.vue"),
      children: [
        { path: "", component: () => import("@/pages/Home.vue") },
        { path: "about", component: () => import("@/pages/About.vue") },
      ],
    },
    {
      path: "/dashboard",
      component: () => import("@/layouts/DashboardLayout.vue"),
      meta: { requiresAuth: true },
      children: [
        { path: "", component: () => import("@/pages/Dashboard.vue") },
        { path: "settings", component: () => import("@/pages/Settings.vue") },
        {
          path: ":teamId",
          component: () => import("@/pages/Team.vue"),
          props: true,
        },
      ],
    },
  ],
});
```

### Vue Router Navigation Guards

```ts
// Global guard
router.beforeEach((to, from) => {
  const auth = useAuthStore();

  if (to.meta.requiresAuth && !auth.isAuthenticated) {
    return { path: "/login", query: { redirect: to.fullPath } };
  }
});

// Per-route guard
{
  path: "/admin",
  component: AdminPage,
  beforeEnter: (to) => {
    const auth = useAuthStore();
    if (!auth.isAdmin) return { path: "/403" };
  },
}
```

### Vue Router Layout Pattern

```vue
<!-- layouts/DashboardLayout.vue -->
<template>
  <div class="flex">
    <Sidebar />
    <main class="flex-1">
      <RouterView />
      <!-- child routes render here -->
    </main>
  </div>
</template>
```

### Dynamic Route Parameters

```vue
<!-- Vue Router - useRoute composable -->
<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();
const teamId = computed(() => route.params.teamId as string);
</script>
```

### Nuxt Navigation: `navigateTo` vs `useRouter`

In Nuxt, prefer `navigateTo()` over `useRouter().push()` - it works in both server and client contexts:

```ts
// In middleware, plugins, server code - only navigateTo works
export default defineNuxtRouteMiddleware((to) => {
  if (!isAuthenticated()) {
    return navigateTo("/login"); // works server-side
  }
});

// In components - both work, but navigateTo is more universal
async function handleSubmit() {
  await saveData();
  await navigateTo(`/products/${newId}`);
}
```

### Route Transition Animations

```vue
<!-- Nuxt -->
<template>
  <NuxtPage :transition="{ name: 'page', mode: 'out-in' }" />
</template>

<style>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.2s;
}
.page-enter-from,
.page-leave-to {
  opacity: 0;
}
</style>
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Routing Design

**Stack:** {Nuxt 3 | Vue Router (Vite)}

### Route Map

| Path                 | Page Component    | Layout      | Middleware  | Auth       |
| -------------------- | ----------------- | ----------- | ---------- | ---------- |
| /                    | index.vue         | default     | -          | Public     |
| /dashboard           | dashboard/index   | dashboard   | auth       | Protected  |
| /dashboard/:teamId   | dashboard/[teamId]| dashboard   | auth       | Protected  |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Routes without error handling (unhandled errors crash the app)
- Routes without loading states (blank screens during data fetching)
- Middleware with unconditional redirects (infinite loops)
- Using `window.location` for navigation instead of the router (breaks SPA behavior)
- Dynamic segments without validation (trusting URL params as safe data)
- Manual route configuration in Nuxt when file-based routing handles it
- Eager-loading all routes in Vue Router (use lazy loading with dynamic imports)
- Heavy computation in navigation guards (runs on every navigation)
