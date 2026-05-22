---
name: vue-code-explain
description: Vue 3.5 / Nuxt / Vite explain signals - reactivity, Composition vs Options API, watchers, Pinia, SSR/CSR boundary.
metadata:
  category: frontend
  tags: [explanation, code-understanding, vue, nuxt, composition-api]
user-invocable: false
---

# Vue Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. Composed by `task-code-explain` when stack is Vue (Nuxt primary, Vite secondary).

## When to Use

Workflow needs Vue-specific signals on a `.vue` SFC, composable, Pinia store, or Nuxt page/layout/server route.

## Rules

- Identify the API style first: `<script setup>` (modern), Composition `setup()`, or Options API. Mental model differs.
- For each reactive primitive, name what triggers updates and flag reactivity-loss traps (destructure, replacement, missing `.value`).
- Distinguish `watch` (explicit), `watchEffect` (auto-track), and flush timing (`pre`/`post`/`sync`).
- For Nuxt, classify each block as server-only, client-only, or universal; name the data-fetching composable (`useFetch`/`useAsyncData`/`$fetch`/`useState`).
- For Pinia, state whether the consumer used `storeToRefs` (preserves state/getter reactivity) or destructured directly (loses it). Actions destructure safely.

## Patterns

### Reactivity primitives

| Construct           | Triggers update on                       | Trap to flag                                                       |
| ------------------- | ---------------------------------------- | ------------------------------------------------------------------ |
| `ref(v)`            | `.value` assignment                      | Missing `.value` in `<script>`; auto-unwrap only in `<template>`   |
| `reactive(obj)`     | Property mutation                        | Destructure or whole-object replace loses reactivity; use `toRefs` |
| `computed(getter)`  | Tracked dep change                       | No side effects; use `watchEffect` instead                         |
| `shallowRef`        | `.value` assignment only                 | Nested mutations are not tracked                                   |
| `readonly(obj)`     | Never (warns in dev)                     | -                                                                  |

### `<script setup>`

- Top-level bindings auto-exposed to template.
- `defineProps`, `defineEmits`, `defineModel` (3.4+), `defineExpose`, `defineSlots` are compiler macros, not imports.
- `defineProps<T>()` + `withDefaults(...)` for typed props with runtime defaults.

### Lifecycle (Composition API)

`onBeforeMount`, `onMounted`, `onBeforeUpdate`, `onUpdated`, `onBeforeUnmount`, `onUnmounted` mirror Options hooks. `onErrorCaptured` (return `false` stops propagation), `onActivated`/`onDeactivated` (under `<KeepAlive>`). Must be registered synchronously in `setup` or a composable.

### Watchers

- `watch(src, (n, o) => ...)`. Source: ref, reactive, getter, or array.
- Options: `immediate`, `deep`, `flush: 'pre' | 'post' | 'sync'`.
- `watchEffect(fn)`: auto-tracks deps used inside, no `oldValue`.
- `(onCleanup) => { onCleanup(() => ...) }`: cancel previous run; essential for async.

### Pinia

- `defineStore('id', setup-fn | options-obj)`.
- `const store = useMyStore()`; `storeToRefs(store)` to destructure state/getters reactively. Actions can be destructured directly.
- `$patch`, `$reset`, `$onAction`, `$subscribe` for batch mutation, reset, interception.

### Nuxt 3

- File routing: `pages/foo/[id].vue`; params via `useRoute().params.id`.
- Layouts: `layouts/default.vue`; per-page override `definePageMeta({ layout: '...' })`.
- Server: `server/api/*.ts`, `server/middleware/*.ts` run on Nitro.
- Data: `useFetch(url)` SSR-aware (returns `{ data, error, pending, refresh }`); `useAsyncData(key, fn)` custom fetcher; `$fetch` low-level, manual SSR; `useState(key, init)` SSR-safe shared state.
- Context: `import.meta.server` / `import.meta.client` (3.10+). Older `process.server`/`process.client` still works but is legacy.
- `<ClientOnly>` wrapper: renders children only on client; flag for SSR-incompatible components (charts, browser-API widgets).

### Pitfalls

- `const { x } = reactive({ x: 1 })`: `x` is a plain value.
- `state = { ...new }` on a `reactive`: external holders keep the old proxy. Mutate keys, or wrap in `ref`.
- `props` are read-only; use `defineEmits` or `defineModel`.
- `v-for :key="index"`: equivalent to no key for reorders/inserts; identity bugs. Use a stable id.
- Pinia `const { items, total } = useCartStore()`: state/getters lose reactivity. Use `storeToRefs`.

### TypeScript

`<script setup lang="ts">`; `defineProps<T>()`, `defineEmits<{(e:'update', v:string):void}>()`. Types: `Ref<T>`, `ComputedRef<T>`, `MaybeRef<T>`. Project type-check via `vue-tsc`.

## Output Format

Signals consumed by `task-code-explain`:

**Flow Context:**

- API style (`<script setup>` | Composition `setup()` | Options)
- Reactive primitives in use and what each tracks
- Lifecycle hooks registered
- Nuxt: render context per block (server | client | universal), data-fetching composables
- Pinia: stores used and reactivity-preservation method (`storeToRefs` | direct destructure | full store)

**Non-Obvious Behavior:**

- Reactivity loss from destructure/replacement
- `useFetch` SSR execution with payload rehydration on client
- `<ClientOnly>` skipping SSR for child tree
- `v-for` key choice (stable id vs index vs missing)
- `defineModel` two-way binding vs `props` read-only

**Key Invariants:**

- `.value` for refs in `<script>`
- Lifecycle hooks registered synchronously in `setup` or composable
- `props` read-only
- `useFetch` server payload must be serializable

**Change Impact Preview:**

- `ref` <-> `reactive` swap: every consumer's access pattern changes
- Drop `storeToRefs`: silent template reactivity loss
- Add `deep: true` watch on large object: traversal cost per change
- `useFetch` -> client-only: loses SSR/SEO and delays first paint
- Switch `v-for` key from stable id to index: reorder bugs

## Avoid

- Treating `ref` and `reactive` as interchangeable
- Recommending Options API patterns inside `<script setup>`
- Enumerating every lifecycle hook when only one is used
- Listing `process.server` as canonical for Nuxt 3.10+ (use `import.meta.*`)
- Flagging direct destructure of Pinia actions as a bug (only state/getters need `storeToRefs`)
