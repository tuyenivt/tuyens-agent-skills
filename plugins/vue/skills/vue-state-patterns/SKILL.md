---
name: vue-state-patterns
description: Vue state management - Pinia (primary), composable stores, store plugins, SSR hydration, and Vuex migration path for Vue 3.5+.
metadata:
  category: frontend
  tags: [vue, state, pinia, composable-stores, vuex-migration, ssr-hydration]
user-invocable: false
---

# Vue State Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a state management approach for a Vue feature
- Deciding between local state, composable, and Pinia store
- Designing Pinia stores with proper domain boundaries
- Reviewing existing state management for performance or correctness issues
- Migrating from Vuex to Pinia

## Rules

- Start with the simplest state mechanism - upgrade only when proven necessary (ref > composable > Pinia)
- Pinia is the official recommendation - use it for all shared client state
- Server state belongs in useFetch/useAsyncData or TanStack Query - not in Pinia
- Every Pinia store must have a clear domain boundary - one store per domain, not one store for the entire app
- Derived state must be computed via getters - never stored separately
- Prefer Setup Stores (composable syntax) over Option Stores for consistency with Composition API

## Patterns

### State Mechanism Selection

| Mechanism      | When to Use                                        | Example                           |
| -------------- | -------------------------------------------------- | --------------------------------- |
| ref            | Simple, component-local state                      | Toggle, input value, local flag   |
| composable     | Reusable state logic shared across components      | useAuth, useTheme                 |
| Pinia          | Shared client state across components              | Shopping cart, UI preferences     |
| URL state      | State that should survive refresh/share            | Filters, sort, pagination, search |
| useFetch       | Server state (API data)                            | User profile, product list        |
| TanStack Query | Complex server state (caching, optimistic updates) | Real-time data, infinite lists    |

### Pinia Setup Store (Recommended)

```ts
// stores/cart.ts
import { defineStore } from "pinia";

export const useCartStore = defineStore("cart", () => {
  const items = ref<CartItem[]>([]);

  // Getters (computed)
  const totalItems = computed(() => items.value.length);
  const totalPrice = computed(() =>
    items.value.reduce((sum, item) => sum + item.price * item.quantity, 0),
  );

  // Actions
  function addItem(item: CartItem) {
    const existing = items.value.find((i) => i.id === item.id);
    if (existing) {
      existing.quantity++;
    } else {
      items.value.push({ ...item, quantity: 1 });
    }
  }

  function removeItem(id: string) {
    items.value = items.value.filter((i) => i.id !== id);
  }

  function clearCart() {
    items.value = [];
  }

  return { items, totalItems, totalPrice, addItem, removeItem, clearCart };
});

// Usage in components:
const cart = useCartStore();
cart.addItem(product);

// Destructure reactively with storeToRefs (refs only, not actions)
const { items, totalItems, totalPrice } = storeToRefs(cart);
const { addItem, removeItem } = cart; // actions don't need storeToRefs
```

**Bad** - Destructuring store without storeToRefs:

```ts
const { items, totalItems } = useCartStore(); // loses reactivity!
```

**Good** - Using storeToRefs:

```ts
const cart = useCartStore();
const { items, totalItems } = storeToRefs(cart); // stays reactive
```

### Pinia Option Store

```ts
// stores/cart.ts (option syntax - familiar for Vuex users)
export const useCartStore = defineStore("cart", {
  state: () => ({
    items: [] as CartItem[],
  }),
  getters: {
    totalItems: (state) => state.items.length,
    totalPrice: (state) =>
      state.items.reduce((sum, item) => sum + item.price * item.quantity, 0),
  },
  actions: {
    addItem(item: CartItem) {
      const existing = this.items.find((i) => i.id === item.id);
      if (existing) {
        existing.quantity++;
      } else {
        this.items.push({ ...item, quantity: 1 });
      }
    },
    removeItem(id: string) {
      this.items = this.items.filter((i) => i.id !== id);
    },
  },
});
```

### Pinia with Persistence

```ts
// plugins/pinia-persist.ts (Nuxt plugin)
import piniaPluginPersistedstate from "pinia-plugin-persistedstate";

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.$pinia.use(piniaPluginPersistedstate);
});

// In store:
export const useCartStore = defineStore(
  "cart",
  () => {
    const items = ref<CartItem[]>([]);
    // ...
    return { items };
  },
  {
    persist: true, // persists to localStorage
  },
);
```

### Composable Store Pattern

For reusable state that doesn't need Pinia's devtools or persistence.

**Warning**: Module-level refs are singletons. In Nuxt/SSR, this leaks state across requests. Use `useState()` in Nuxt or Pinia for SSR-safe shared state.

```ts
// composables/useAuth.ts - client-only or Vite projects
const user = ref<User | null>(null);
const isAuthenticated = computed(() => !!user.value);

export function useAuth() {
  async function login(credentials: Credentials) {
    const response = await $fetch("/api/auth/login", {
      method: "POST",
      body: credentials,
    });
    user.value = response.user;
  }

  async function logout() {
    await $fetch("/api/auth/logout", { method: "POST" });
    user.value = null;
    navigateTo("/login");
  }

  return {
    user: readonly(user),
    isAuthenticated,
    login,
    logout,
  };
}
```

### URL State

Sync state with URL for shareable, bookmarkable UI:

```vue
<script setup lang="ts">
const route = useRoute();
const router = useRouter();

// Read from URL
const category = computed(() => (route.query.category as string) || "all");
const page = computed(() => parseInt((route.query.page as string) || "1"));
const sort = computed(() => (route.query.sort as string) || "name");

// Write to URL
function setFilter(key: string, value: string) {
  router.push({
    query: {
      ...route.query,
      [key]: value,
      page: "1", // reset page on filter change
    },
  });
}
</script>
```

### SSR Hydration with Pinia

Nuxt handles Pinia SSR hydration automatically. For manual SSR setups:

```ts
// Nuxt auto-hydrates Pinia state from server to client.
// No manual setup needed. Just use stores normally:
const cart = useCartStore();
// State set during SSR is available on the client.
```

### Vuex Migration Path

**Vuex (old):**

```ts
const store = createStore({
  state: { count: 0 },
  mutations: {
    increment(state) {
      state.count++;
    },
  },
  actions: {
    asyncIncrement({ commit }) {
      commit("increment");
    },
  },
  getters: { doubled: (state) => state.count * 2 },
});
```

**Pinia (new):**

```ts
export const useCounterStore = defineStore("counter", () => {
  const count = ref(0);
  const doubled = computed(() => count.value * 2);

  function increment() {
    count.value++;
  }

  async function asyncIncrement() {
    increment();
  }

  return { count, doubled, increment, asyncIncrement };
});
```

Key migration differences:

- No mutations - actions directly mutate state
- No namespaced modules - each store is its own module
- Full TypeScript support without type gymnastics
- Composable syntax matches Composition API patterns

## Output Format

Consuming workflow skills depend on this structure.

```
## Vue State Architecture

**Stack:** {detected framework}
**State library:** {Pinia | Composable only | URL state}

### State Map

| State          | Category   | Owner             | Mechanism               |
| -------------- | ---------- | ----------------- | ----------------------- |
| {state name}   | Local UI   | {component}       | ref                     |
| {state name}   | Shared UI  | {store}           | Pinia                   |
| {state name}   | Server     | -                 | useFetch / TanStack Query |
| {state name}   | URL        | -                 | route.query             |

### Stores

| Store          | Domain         | Persisted | SSR Hydrated |
| -------------- | -------------- | --------- | ------------ |
| {storeName}    | {domain}       | {Yes|No}  | {Yes|No}     |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Storing server state (API data) in Pinia (use useFetch/useAsyncData or TanStack Query)
- Creating one mega-store for the entire application (couples unrelated domains)
- Option Stores when the rest of the codebase uses Composition API (inconsistency)
- Storing derived values instead of computing them with getters
- Using Vuex in new Vue 3 projects (Pinia is the official recommendation)
- Reactive refs for state that should be in the URL (filters, pagination, sort)
- Destructuring store without `storeToRefs()` (loses reactivity on state and getters)
- Direct store mutation from components bypassing actions (breaks action-based devtools tracking)
- Module-level refs in Nuxt/SSR composables (state leaks across requests - use `useState()` or Pinia)
- Prop drilling through more than 2 levels when a store or provide/inject would be cleaner
