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

- Choosing a state mechanism for a Vue feature
- Designing Pinia stores with proper domain boundaries
- Reviewing existing state for performance, correctness, or SSR safety
- Migrating from Vuex to Pinia

## Rules

- Escalate only when justified: `ref` -> composable -> Pinia. Use Pinia for all shared client state.
- One store per domain. No mega-store coupling unrelated domains.
- Use Setup Stores (Composition API). Option Stores only in legacy/Vuex-migration code.
- Derived state is a `computed`/getter. Never store it.
- Server state lives in `useFetch`/`useAsyncData` or TanStack Query, never Pinia.
- URL-shareable state (filters, sort, pagination, search) lives in `route.query`, not refs.
- Destructure stores via `storeToRefs()` for state/getters; actions destructure directly.
- Mutate store state only through actions (preserves devtools timeline).

## Patterns

### State Mechanism Selection

| Mechanism      | When to Use                                  | Example                         |
| -------------- | -------------------------------------------- | ------------------------------- |
| ref            | Component-local state                        | Toggle, input value             |
| composable     | Reusable logic, client-only or per-request   | useAuth, useTheme               |
| Pinia          | Shared client state across components        | Cart, UI preferences            |
| URL state      | Shareable/bookmarkable state                 | Filters, sort, pagination       |
| useFetch       | Server state (API data)                      | User profile, product list      |
| TanStack Query | Complex server state (cache, optimistic)     | Real-time data, infinite lists  |

### Pinia Setup Store

```ts
// stores/cart.ts
export const useCartStore = defineStore("cart", () => {
  const items = ref<CartItem[]>([]);
  const totalItems = computed(() => items.value.length);
  const totalPrice = computed(() =>
    items.value.reduce((sum, i) => sum + i.price * i.quantity, 0),
  );

  function addItem(item: CartItem) {
    const existing = items.value.find((i) => i.id === item.id);
    if (existing) existing.quantity++;
    else items.value.push({ ...item, quantity: 1 });
  }

  return { items, totalItems, totalPrice, addItem };
}, { persist: true }); // optional: pinia-plugin-persistedstate
```

**Consuming the store:**

```ts
// Bad - loses reactivity
const { items, totalItems } = useCartStore();

// Good
const cart = useCartStore();
const { items, totalItems } = storeToRefs(cart); // state + getters
const { addItem } = cart;                         // actions
```

### Composable Store (Module-Level Ref)

For shared state without devtools/persistence needs. **SSR hazard**: module-level refs are singletons and leak across requests in Nuxt/SSR. Use `useState()` in Nuxt or Pinia instead.

```ts
// composables/useAuth.ts - client-only (Vite) or Nuxt useState
const user = ref<User | null>(null); // unsafe in SSR
export function useAuth() {
  const isAuthenticated = computed(() => !!user.value);
  return { user: readonly(user), isAuthenticated };
}
```

Nuxt-safe alternative:

```ts
export function useAuth() {
  const user = useState<User | null>("auth.user", () => null);
  return { user, isAuthenticated: computed(() => !!user.value) };
}
```

### URL State

```ts
const route = useRoute();
const router = useRouter();
const category = computed(() => (route.query.category as string) ?? "all");

function setFilter(key: string, value: string) {
  router.push({ query: { ...route.query, [key]: value, page: "1" } });
}
```

### SSR Hydration

Nuxt auto-hydrates Pinia state from server to client; no manual wiring. For custom SSR setups, serialize `pinia.state.value` into the HTML payload and call `pinia.state.value = window.__INITIAL_STATE__` on the client before app mount.

### Vuex -> Pinia Migration

Map Vuex concepts directly:

| Vuex                  | Pinia (Setup)                     |
| --------------------- | --------------------------------- |
| `state`               | `ref()` declarations              |
| `getters`             | `computed()`                      |
| `mutations`           | Removed - actions mutate directly |
| `actions`             | Plain functions                   |
| Namespaced modules    | Separate stores (`defineStore`)   |

```ts
// Before (Vuex)
mutations: { increment(state) { state.count++ } },
actions:   { asyncInc({ commit }) { commit("increment") } },

// After (Pinia setup)
const count = ref(0);
function increment() { count.value++; }
async function asyncInc() { increment(); }
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Vue State Architecture

**Stack:** {detected framework}
**State library:** {Pinia | Composable only | URL state}

### State Map

| State        | Category   | Owner       | Mechanism                 |
| ------------ | ---------- | ----------- | ------------------------- |
| {state name} | Local UI   | {component} | ref                       |
| {state name} | Shared UI  | {store}     | Pinia                     |
| {state name} | Server     | -           | useFetch / TanStack Query |
| {state name} | URL        | -           | route.query               |

### Stores

| Store       | Domain   | Persisted | SSR Hydrated |
| ----------- | -------- | --------- | ------------ |
| {storeName} | {domain} | {Yes|No}  | {Yes|No}     |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Server state (API data) in Pinia stores
- Mega-store coupling unrelated domains
- Stored derived values instead of getters
- Module-level refs in Nuxt/SSR composables (request leakage)
- Vuex in new Vue 3 projects
- Prop drilling beyond 2 levels when a store or `provide`/`inject` fits
