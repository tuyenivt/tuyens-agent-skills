---
name: vue-code-explain
description: Vue 3.5 / Nuxt / Vite explain signals: reactivity, Composition vs Options API, watchers, lifecycle, Pinia, Nuxt server/client boundaries.
metadata:
  category: frontend
  tags: [explanation, code-understanding, vue, nuxt, composition-api]
user-invocable: false
---

# Vue Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Vue (Nuxt primary, Vite secondary).

## When to Use

- A workflow needs Vue-specific signals: reactivity primitives, composition vs options API, watchers and watch effect, lifecycle hooks, Pinia stores, Nuxt SSR/CSR boundary.
- Target is a `.vue` SFC, composable, store, or Nuxt page/layout.

## Rules

- Identify the API style first: Composition API with `<script setup>` (modern), Composition API in `setup()` function, or Options API (legacy). Mental model differs significantly.
- For each reactive primitive (`ref`, `reactive`, `computed`, `shallowRef`, `readonly`), identify what triggers updates - and surface common destructuring traps that lose reactivity.
- For watchers, distinguish `watch` (explicit source), `watchEffect` (auto-tracks), and `watchPostEffect`/`watchSyncEffect` (timing variants).
- For Nuxt, identify server-only, client-only, or universal contexts. `process.server`, `process.client`, `useState` (SSR-safe state), `useFetch`/`useAsyncData` matter.
- Surface Pinia store usage - whether the component reads via `storeToRefs` (preserves reactivity) or destructures directly (loses it).

## Patterns

### Reactivity

| Construct                | Behavior                                                                                  | What to flag                                                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `ref(value)`             | Reactive container; access via `.value`                                                   | Forgetting `.value` in `<script>` is the most common Vue bug; unwrapped automatically in `<template>`                       |
| `reactive(obj)`          | Reactive proxy of an object                                                               | Destructuring breaks reactivity (`const { x } = reactive({...})` - `x` is a plain value); use `toRefs` to preserve          |
| `computed(() => ...)`    | Cached, reactive derivation; auto-tracks dependencies                                     | Computed cannot have side effects; if you need them, use `watchEffect`                                                       |
| `computed({ get, set })` | Writable computed                                                                         | The setter must update the underlying state, not a captured local                                                            |
| `shallowRef`             | Like `ref`, but only `.value` itself is reactive (not deep)                               | Useful for large objects you mutate in bulk; mutations require explicit `.value = newValue`                                  |
| `shallowReactive`        | Reactive only at the top level                                                            | Nested mutations do not trigger updates                                                                                      |
| `readonly(obj)`          | Wraps in immutable proxy                                                                  | Mutations log a warning in development, no-op in production                                                                  |
| `toRef(obj, 'key')`      | Creates a `ref` linked to `obj.key`; preserves reactivity through destructuring             | Used for prop pass-through                                                                                                   |
| `toRefs(obj)`            | Converts every property of a `reactive` to refs                                           | Standard pattern after returning from a composable                                                                           |

### `<script setup>` (default modern style)

- All top-level bindings are exposed to the template automatically.
- `defineProps`, `defineEmits`, `defineExpose`, `defineSlots`, `defineModel` (Vue 3.4+) are compiler macros - not imports.
- `defineProps<{...}>()` for type-only props (TypeScript). Runtime defaults via `withDefaults(defineProps<...>(), {...})`.
- Imports in `<script setup>` are component-local; cannot be referenced from outside without `defineExpose`.

### Lifecycle Hooks

| Composition API hook | Options API equivalent | Fires                                                       |
| -------------------- | ---------------------- | ----------------------------------------------------------- |
| `onBeforeMount`      | `beforeMount`          | Before DOM attach                                           |
| `onMounted`          | `mounted`              | After DOM attach                                            |
| `onBeforeUpdate`     | `beforeUpdate`         | Before reactive update applies to DOM                       |
| `onUpdated`          | `updated`              | After reactive update applies to DOM                        |
| `onBeforeUnmount`    | `beforeUnmount`        | Before component is detached                                |
| `onUnmounted`        | `unmounted`            | After component is detached - cleanup subscriptions/timers   |
| `onErrorCaptured`    | `errorCaptured`        | Error from descendant; return false to stop propagation     |
| `onActivated`        | `activated`            | `<KeepAlive>`-managed component is reactivated              |
| `onDeactivated`      | `deactivated`          | `<KeepAlive>`-managed component is deactivated              |

### Watchers

- `watch(source, (newVal, oldVal) => {...})`: explicit source. Source can be ref, reactive object, getter, or array.
- `watch(source, cb, { immediate: true, deep: true, flush: 'post' })`:
  - `immediate`: run on registration with current value.
  - `deep`: deep-watch a reactive object (otherwise only top-level changes trigger).
  - `flush`: `'pre'` (default, before update), `'post'` (after DOM update), `'sync'` (synchronous).
- `watchEffect(() => {...})`: auto-tracks reactive deps used inside; reruns when any change. Cannot access `oldValue`.
- `watchEffect((onCleanup) => { onCleanup(() => ...) })`: cleanup before next run or on unmount - essential for cancellable async.

### Common Reactivity Pitfalls

- Destructuring `reactive`: `const { x } = reactive({ x: 1 })` - `x` is a plain number, no longer reactive.
- Replacing a `reactive` object whole: `state = { ...newState }` - the original proxy is replaced; consumers still hold the old reference. Mutate keys instead, or use `ref` and assign `.value`.
- `props` are read-only. Mutating directly throws warnings; use `defineEmits` or `defineModel` to two-way bind.
- `v-for` without `key`: identity confusion on reorder; updates wrong DOM nodes.

### Pinia Stores

- Defined via `defineStore('id', () => { ... })` (setup-style) or `defineStore('id', { state, getters, actions })` (options-style).
- Setup-style: returns an object of refs/computed/functions. Component uses `const store = useMyStore()`.
- `storeToRefs(store)`: destructure store reactively. Plain destructuring loses reactivity for `state` and `getters`.
- Actions can be sync or async; `$patch(...)` for batched mutations; `$reset()` returns to initial state.
- `$onAction`, `$subscribe` for store-level interception (logging, persistence).

### Nuxt 3 Specifics

- File-based routing: `pages/index.vue`, `pages/users/[id].vue`. Route params via `useRoute().params.id`.
- Layouts: `layouts/default.vue` wraps every page; `definePageMeta({ layout: 'auth' })` per-page override.
- Server-only: API routes in `server/api/*.ts`, server middleware in `server/middleware/*.ts`. Run on Nitro server.
- Universal data fetching:
  - `useFetch(url)`: SSR-aware; runs on server during SSR, hydrated on client; returns `{ data, error, pending, refresh }`.
  - `useAsyncData(key, fetcher)`: same idea but with a custom fetcher.
  - `$fetch(url)`: low-level fetch (Ofetch); manual SSR handling.
- `useState(key, init)`: SSR-safe shared state; serialized into the page payload and rehydrated on client.
- `useCookie(name)`: SSR-safe cookie access.
- `process.server` / `process.client`: branch-only logic. Note: `import.meta.server` / `import.meta.client` in Nuxt 3.10+.

### Composables

- Functions starting with `use*` (convention).
- Encapsulate stateful logic; return refs/computed/functions.
- Composables called inside `setup()` or another composable can register lifecycle hooks; calling outside silently misses lifecycle.
- Standard composables: `useRoute`, `useRouter`, `useFetch`, `useAsyncData`, `useState`, `useHead`, `useCookie` (Nuxt); `useMouse`, `useDebounce`, etc. (VueUse).

### Slots

- Default slot: `<slot />`.
- Named: `<slot name="header" />` consumed via `<template #header>` in parent.
- Scoped: `<slot :user="currentUser" />` consumed via `<template #default="{ user }">`.
- `useSlots()` and `useAttrs()` in setup; provide programmatic access.

### TypeScript

- `<script setup lang="ts">`. Props typed via `defineProps<T>()`. Emits via `defineEmits<{ (e: 'update', value: string): void }>()`.
- `Ref<T>`, `ComputedRef<T>`, `MaybeRef<T>` types.
- Vite + `vue-tsc` for project-wide type-check (not built into Vite by default).

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- API style: `<script setup>`, Composition `setup()`, or Options API
- Reactive primitives in use and what they track
- Lifecycle hooks registered
- For Nuxt: SSR/CSR boundary, data fetching composables
- Pinia store dependencies and reactivity preservation method

**Into "Non-Obvious Behavior":**

- Destructuring `reactive` losing reactivity
- Computed without side effects vs watchEffect with side effects
- `props` mutation warnings vs `defineModel` two-way binding
- `v-for` without `key` causing identity bugs
- Nuxt fetch returning during SSR with state preserved across hydration
- `process.server`/`process.client` branching

**Into "Key Invariants":**

- `.value` required for ref access in `<script>`
- Lifecycle hooks must be registered synchronously inside `setup` or a composable
- `props` are read-only
- `useFetch` on the server must produce serializable data (no functions, no cycles)

**Into "Change Impact Preview":**

- Switching `ref` to `reactive` (or vice versa): every consumer accesses the value differently
- Removing `storeToRefs` and destructuring directly: silent reactivity loss in templates
- Adding a `watch` with `deep: true`: performance cost on large objects
- Changing a `useFetch` to client-only: SEO and initial paint regress
- Adding a v-for without a stable key: list reorder bugs

## Avoid

- Treating `ref` and `reactive` as interchangeable - access patterns differ
- Recommending Options API patterns in `<script setup>` files
- Glossing over `storeToRefs` - destructuring is the #1 Pinia bug
- Confusing `watchEffect` and `computed` - one has side effects, the other does not
- Using `process.server` syntax in Nuxt 3.10+ examples (now `import.meta.server`)
- Listing every lifecycle hook when only one is used
