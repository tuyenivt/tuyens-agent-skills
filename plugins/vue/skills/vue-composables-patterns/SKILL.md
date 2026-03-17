---
name: vue-composables-patterns
description: Vue composable design - extraction rules, ref vs reactive, watchEffect vs watch, lifecycle hooks, cleanup patterns, and VueUse integration for Vue 3.5+.
metadata:
  category: frontend
  tags: [vue, composables, ref, reactive, watch, watchEffect, lifecycle, vueuse]
user-invocable: false
---

# Vue Composables Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing composables for reusable logic
- Choosing between ref and reactive
- Setting up watchers and lifecycle hooks correctly
- Reviewing composable usage for correctness (cleanup, memory leaks)
- Integrating VueUse for common utilities

## Rules

- Composables must start with `use` and encapsulate exactly one concern
- Prefer `ref()` over `reactive()` as the default - `reactive()` only for objects where you need deep reactivity and will not reassign
- `watchEffect` for side effects that should run whenever dependencies change; `watch` for specific value tracking or accessing old/new values
- Every composable that subscribes, connects, or adds listeners must clean up on unmount
- Never use `reactive()` for primitives - use `ref()`
- Return refs from composables (not raw values) to maintain reactivity
- Use `toValue()` (Vue 3.3+) to accept both refs and plain values as composable parameters

## Patterns

### ref vs reactive

**ref** - Use for primitives and when you may reassign the whole value:

```ts
const count = ref(0);
const user = ref<User | null>(null);
const items = ref<Item[]>([]);

// Reassignment works with ref
items.value = [...items.value, newItem];
user.value = await fetchUser(id);
```

**reactive** - Use only for objects where deep reactivity is needed and you won't reassign:

```ts
const form = reactive({
  name: "",
  email: "",
  errors: {} as Record<string, string>,
});

// Mutate properties directly
form.name = "Alice";
form.errors.name = "Required";
```

**Bad** - reactive with reassignment:

```ts
let state = reactive({ items: [] });
state = reactive({ items: newItems }); // loses reactivity for existing watchers!
```

**Bad** - reactive for primitives:

```ts
const state = reactive({ count: 0 }); // overkill for a single primitive
```

**Good** - ref for primitives:

```ts
const count = ref(0);
count.value++;
```

### Composable Design

Each composable should encapsulate one concern and return a clear API:

**Bad** - Kitchen sink composable:

```ts
function useUser(userId: string) {
  const user = ref(null);
  const posts = ref([]);
  const theme = ref("light");
  const notifications = ref([]);
  // fetches user, posts, theme, and notifications...
}
```

**Good** - Single concern:

```ts
function useUser(userId: MaybeRefOrGetter<string>) {
  // Pass the ref/getter directly to useFetch for reactivity - don't toValue() eagerly
  const { data: user, status, error } = useFetch(
    computed(() => `/api/users/${toValue(userId)}`),
  );

  const fullName = computed(
    () => user.value && `${user.value.firstName} ${user.value.lastName}`,
  );

  return { user, fullName, status, error };
}

function useUserPosts(userId: MaybeRefOrGetter<string>) {
  return useFetch(computed(() => `/api/users/${toValue(userId)}/posts`));
}
```

### MaybeRefOrGetter Pattern (Vue 3.3+)

Accept flexible input types in composables:

```ts
import { toValue, type MaybeRefOrGetter } from "vue";

function useCounter(initialValue: MaybeRefOrGetter<number>) {
  const count = ref(toValue(initialValue));

  function increment() {
    count.value++;
  }
  function decrement() {
    count.value--;
  }
  function reset() {
    count.value = toValue(initialValue);
  }

  return { count: readonly(count), increment, decrement, reset };
}

// All valid:
useCounter(0);
useCounter(ref(0));
useCounter(() => props.startValue);
```

### watchEffect vs watch

**watchEffect** - Auto-tracks reactive dependencies, runs immediately:

```ts
// Runs immediately, re-runs when search or page changes
watchEffect(() => {
  fetchResults(search.value, page.value);
});
```

**watch** - Explicit sources, access old/new, lazy by default:

```ts
// Only runs when userId changes, not on mount
watch(
  () => props.userId,
  async (newId, oldId) => {
    if (newId !== oldId) {
      user.value = await fetchUser(newId);
    }
  },
);

// Watch multiple sources
watch([search, category], ([newSearch, newCategory]) => {
  fetchProducts(newSearch, newCategory);
});

// Deep watch for reactive objects
watch(
  () => form,
  (newForm) => {
    validate(newForm);
  },
  { deep: true },
);
```

**Bad** - watch when watchEffect suffices:

```ts
// Unnecessary explicit source tracking
watch(
  [search, page],
  ([newSearch, newPage]) => {
    fetchResults(newSearch, newPage);
  },
  { immediate: true },
);
```

**Good** - watchEffect for auto-tracking:

```ts
watchEffect(() => {
  fetchResults(search.value, page.value);
});
```

### Cleanup Patterns

```ts
// Event listener cleanup
function useEventListener(
  target: MaybeRefOrGetter<EventTarget>,
  event: string,
  handler: EventListener,
) {
  onMounted(() => {
    toValue(target).addEventListener(event, handler);
  });

  onUnmounted(() => {
    toValue(target).removeEventListener(event, handler);
  });
}

// watchEffect with cleanup (onCleanup parameter)
watchEffect((onCleanup) => {
  const controller = new AbortController();
  fetchData(search.value, { signal: controller.signal });

  onCleanup(() => {
    controller.abort();
  });
});

// Vue 3.5+: onWatcherCleanup (alternative - works in watch/watchEffect callbacks)
import { onWatcherCleanup } from "vue";

watch(search, (newSearch) => {
  const controller = new AbortController();
  fetchData(newSearch, { signal: controller.signal });

  onWatcherCleanup(() => {
    controller.abort();
  });
});

// Timer cleanup
function useInterval(callback: () => void, ms: MaybeRefOrGetter<number>) {
  const intervalId = ref<ReturnType<typeof setInterval>>();

  onMounted(() => {
    intervalId.value = setInterval(callback, toValue(ms));
  });

  onUnmounted(() => {
    if (intervalId.value) clearInterval(intervalId.value);
  });
}

// WebSocket cleanup
function useWebSocket(url: MaybeRefOrGetter<string>) {
  const data = ref<string | null>(null);
  const status = ref<"connecting" | "open" | "closed">("connecting");
  let ws: WebSocket | null = null;

  function connect() {
    ws = new WebSocket(toValue(url));
    ws.onopen = () => (status.value = "open");
    ws.onmessage = (e) => (data.value = e.data);
    ws.onclose = () => (status.value = "closed");
  }

  onMounted(connect);
  onUnmounted(() => ws?.close());

  return { data: readonly(data), status: readonly(status) };
}
```

### VueUse Integration

Prefer VueUse for common utilities instead of writing from scratch:

```ts
import {
  useLocalStorage,
  useDebounceFn,
  useIntersectionObserver,
} from "@vueuse/core";

// Persistent state
const theme = useLocalStorage("theme", "light");

// Debounced search
const search = ref("");
const debouncedSearch = useDebounceFn(() => {
  fetchResults(search.value);
}, 300);

// Intersection observer for lazy loading
const target = ref<HTMLElement | null>(null);
const isVisible = ref(false);
useIntersectionObserver(target, ([entry]) => {
  isVisible.value = entry.isIntersecting;
});
```

### Lifecycle Hooks

```ts
import {
  onMounted,
  onUnmounted,
  onBeforeMount,
  onBeforeUnmount,
  onActivated,
  onDeactivated,
} from "vue";

// onMounted - DOM is available
onMounted(() => {
  inputRef.value?.focus();
});

// onActivated/onDeactivated - for components inside <KeepAlive>
onActivated(() => {
  // component re-entered the DOM from cache
  refreshData();
});

onDeactivated(() => {
  // component removed from DOM but kept in cache
  pausePolling();
});
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Composables Assessment

**Stack:** {detected framework}
**Vue version:** {detected version}

### Composables

| Composable      | Concern           | Dependencies         | Cleanup Required |
| --------------- | ----------------- | -------------------- | ---------------- |
| {composableName}| {what it manages} | {external deps}      | {Yes | No}       |

### Issues Found

- [Severity: High | Medium | Low] {description of composable issue}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if composable usage is correct - do not omit this section silently}
```

## Avoid

- Using `reactive()` for primitives or values that will be reassigned
- Returning raw values from composables instead of refs (breaks reactivity for consumers)
- Missing cleanup in composables that add listeners, timers, or subscriptions
- Using `watch` with `{ immediate: true }` when `watchEffect` would be cleaner
- Creating composables that manage multiple unrelated concerns
- Deep watching large objects without a specific property selector (performance)
- Suppressing reactivity warnings instead of fixing the root cause
- Writing custom utilities already provided by VueUse
