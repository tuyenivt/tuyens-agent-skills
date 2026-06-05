---
name: vue-composables-patterns
description: Vue 3.5 composables: extraction rules, ref vs reactive, watchEffect vs watch, lifecycle, cleanup, VueUse integration.
metadata:
  category: frontend
  tags: [vue, composables, ref, reactive, watch, watchEffect, lifecycle, vueuse]
user-invocable: false
---

# Vue Composables Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing composables for reusable logic
- Choosing between `ref` / `reactive`, `watch` / `watchEffect`
- Auditing cleanup, lifecycle, and memory-leak risk
- Deciding whether to use VueUse instead of hand-rolling

## Rules

- Name `useXxx`; one concern per composable.
- Default to `ref()`. Use `reactive()` only for objects mutated in place; never for primitives or reassignment.
- Return refs (or `readonly(ref)`), not raw `.value`.
- Accept reactive inputs as `MaybeRefOrGetter<T>`; read with `toValue()`.
- `watchEffect` for auto-tracked effects; `watch` for explicit sources, old/new values, or lazy execution.
- Release every subscription/listener/timer via `onUnmounted`, `onCleanup`, or `onWatcherCleanup` (3.5+).
- Use VueUse for utilities it already ships.

## Patterns

### ref vs reactive

```ts
// Good - ref for primitives and reassignable values
const count = ref(0);
const items = ref<Item[]>([]);
items.value = [...items.value, newItem];

// Good - reactive for a stable object mutated in place
const form = reactive({ name: "", errors: {} as Record<string, string> });
form.errors.name = "Required";

// Bad - reassignment severs reactive bindings
let state = reactive({ items: [] });
state = reactive({ items: newItems });
```

### Composable design

One concern per composable; split unrelated data.

```ts
// Bad - mixes user, posts, theme, notifications
function useUser(id: string) { /* fetches all four */ }

// Good - split, accept reactive input, return refs
function useUser(userId: MaybeRefOrGetter<string>) {
  const { data: user, status, error } = useFetch(
    computed(() => `/api/users/${toValue(userId)}`),
  );
  const fullName = computed(
    () => user.value && `${user.value.firstName} ${user.value.lastName}`,
  );
  return { user, fullName, status, error };
}
```

### watchEffect vs watch

```ts
// Good - watchEffect auto-tracks; runs immediately
watchEffect(() => fetchResults(search.value, page.value));

// Good - watch when you need old value or lazy behaviour
watch(
  () => props.userId,
  async (newId, oldId) => { if (newId !== oldId) user.value = await fetchUser(newId); },
);

// Bad - watch + { immediate: true } reinventing watchEffect
watch([search, page], ([s, p]) => fetchResults(s, p), { immediate: true });
```

Use `{ deep: true }` only with a narrow source selector; deep-watching large objects is expensive.

### Cleanup

Every resource acquired in setup must be released. Pick one mechanism per case:

```ts
// onUnmounted - listeners, timers, sockets acquired in setup
function useEventListener(
  target: MaybeRefOrGetter<EventTarget>,
  event: string,
  handler: EventListener,
) {
  onMounted(() => toValue(target).addEventListener(event, handler));
  onUnmounted(() => toValue(target).removeEventListener(event, handler));
}

// watchEffect onCleanup - abort in-flight work between runs
watchEffect((onCleanup) => {
  const ctrl = new AbortController();
  fetchData(search.value, { signal: ctrl.signal });
  onCleanup(() => ctrl.abort());
});

// Vue 3.5+ onWatcherCleanup - same idea inside watch callbacks
watch(search, (q) => {
  const ctrl = new AbortController();
  fetchData(q, { signal: ctrl.signal });
  onWatcherCleanup(() => ctrl.abort());
});
```

### MaybeRefOrGetter input

```ts
function useCounter(initial: MaybeRefOrGetter<number>) {
  const count = ref(toValue(initial));
  return { count: readonly(count), reset: () => (count.value = toValue(initial)) };
}
// All valid: useCounter(0), useCounter(ref(0)), useCounter(() => props.start)
```

### VueUse first

```ts
import { useLocalStorage, useDebounceFn, useIntersectionObserver } from "@vueuse/core";

const theme = useLocalStorage("theme", "light");
const debouncedSearch = useDebounceFn(() => fetchResults(search.value), 300);
useIntersectionObserver(target, ([entry]) => (isVisible.value = entry.isIntersecting));
```

### Lifecycle inside `<KeepAlive>`

`onActivated` / `onDeactivated` fire on cache enter/exit; use them (not `onMounted`/`onUnmounted`) to resume/pause work for cached components.

```ts
onActivated(() => poller.resume());
onDeactivated(() => poller.pause());
```

### SSR-safe IDs with useId (3.5+)

Bad - hand-rolled ID collides on SSR rehydration:

```ts
function useFieldId() {
  return { id: Math.random().toString(36).slice(2) }; // SSR/client mismatch
}
```

Good - `useId` is stable across SSR and client; unique per call site:

```ts
import { useId } from "vue";
const id = useId();
```

(For typed template refs see `vue-component-patterns`.)

## Output Format

Consuming workflow skills depend on this structure.

```
## Composables Assessment

**Stack:** {detected framework}
**Vue version:** {detected version}

### Composables

| Composable | Concern | Dependencies (refs/router/store/external) | Cleanup Required |
| ---------- | ------- | ------------------------------------------ | ---------------- |
| {name}     | {what}  | {deps}                                     | {Yes / No}       |

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

State "No issues found" explicitly when composables are correct.
```

## Avoid

- `watch` with `{ immediate: true }` where `watchEffect` is cleaner
- Returning `.value` (raw) from composables - breaks consumer reactivity
- Deep-watching large objects without a property selector
- Suppressing reactivity warnings instead of fixing the source
- Re-implementing utilities VueUse already ships
