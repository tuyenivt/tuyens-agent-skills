---
name: vue-component-patterns
description: Vue SFC composition - script setup, props/emits typing, typed slots, provide/inject, Suspense, Teleport, dynamic components, and error handling for Vue 3.5+.
metadata:
  category: frontend
  tags: [vue, components, composition, script-setup, props, slots, provide-inject, teleport]
user-invocable: false
---

# Vue Component Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing component architecture for a new Vue feature
- Choosing SFC composition patterns (props/emits, slots, provide/inject)
- Typing components with generics, typed slots, and discriminated props
- Adding error handling with Suspense and error boundaries
- Reviewing component design for reusability and correctness

## Rules

- `<script setup lang="ts">` for all new SFCs - no Options API
- Props defined with `defineProps<T>()` using interface for 3+ props; inline for simple components
- Emits defined with `defineEmits<T>()` with typed payloads
- Slots typed with `defineSlots<T>()` when consumers need type safety
- Composition over configuration - prefer slots over prop-heavy components
- Single responsibility - each component does one thing; split when responsibilities diverge
- Never use mixins - use composables for shared logic
- Use `v-bind` in `<style>` for dynamic styles instead of inline styles

## Patterns

### Script Setup SFC Structure

```vue
<script setup lang="ts">
import { ref, computed } from "vue";

interface Props {
  title: string;
  items: readonly Item[];
  variant?: "default" | "compact";
}

const props = withDefaults(defineProps<Props>(), {
  variant: "default",
});

const emit = defineEmits<{
  select: [item: Item];
  remove: [id: string];
}>();

const search = ref("");
const filteredItems = computed(() =>
  props.items.filter((item) =>
    item.name.toLowerCase().includes(search.value.toLowerCase()),
  ),
);

function handleSelect(item: Item) {
  emit("select", item);
}
</script>

<template>
  <div>
    <input v-model="search" placeholder="Search..." />
    <ul>
      <li v-for="item in filteredItems" :key="item.id">
        <button @click="handleSelect(item)">{{ item.name }}</button>
      </li>
    </ul>
  </div>
</template>
```

### Props Patterns

**Reactive props destructure (Vue 3.5+):**

```vue
<script setup lang="ts">
// Vue 3.5+: destructured props remain reactive
const { title, count = 0 } = defineProps<{
  title: string;
  count?: number;
}>();

// count is reactive - works in computed, watch, and template
const doubled = computed(() => count * 2);
</script>
```

**Bad** - Destructuring props in Vue < 3.5:

```vue
<script setup lang="ts">
const props = defineProps<{ title: string; count: number }>();
const { count } = props; // loses reactivity! count is now a plain number
const doubled = computed(() => count * 2); // always stale
</script>
```

**Good** - Using props object or toRefs in Vue < 3.5:

```vue
<script setup lang="ts">
const props = defineProps<{ title: string; count: number }>();
const { count } = toRefs(props); // count is Ref<number>, stays reactive
const doubled = computed(() => count.value * 2);
</script>
```

### Typed Slots

```vue
<script setup lang="ts">
defineSlots<{
  default: (props: { item: Item; index: number }) => any;
  header: () => any;
  empty: () => any;
}>();
</script>

<template>
  <div>
    <header>
      <slot name="header" />
    </header>
    <template v-if="items.length">
      <div v-for="(item, index) in items" :key="item.id">
        <slot :item="item" :index="index" />
      </div>
    </template>
    <template v-else>
      <slot name="empty">
        <p>No items found</p>
      </slot>
    </template>
  </div>
</template>
```

### Provide/Inject (Compound Components)

**Bad** - Prop drilling through multiple levels:

```vue
<!-- GrandParent passes theme to Parent, Parent passes to Child -->
<GrandParent :theme="theme">
  <Parent :theme="theme">
    <Child :theme="theme" />
  </Parent>
</GrandParent>
```

**Good** - Provide/inject with typed injection key:

```ts
// keys.ts
import type { InjectionKey, Ref } from "vue";

export interface TabsContext {
  activeTab: Ref<string>;
  setActiveTab: (tab: string) => void;
}

export const TabsKey: InjectionKey<TabsContext> = Symbol("Tabs");
```

```vue
<!-- Tabs.vue -->
<script setup lang="ts">
import { provide, ref } from "vue";
import { TabsKey } from "./keys";

const props = defineProps<{ defaultTab: string }>();
const activeTab = ref(props.defaultTab);

provide(TabsKey, {
  activeTab,
  setActiveTab: (tab: string) => {
    activeTab.value = tab;
  },
});
</script>

<template>
  <div role="tablist">
    <slot />
  </div>
</template>
```

```vue
<!-- Tab.vue -->
<script setup lang="ts">
import { inject } from "vue";
import { TabsKey } from "./keys";

const props = defineProps<{ value: string }>();
const tabs = inject(TabsKey);
if (!tabs) throw new Error("Tab must be used within <Tabs>");
</script>

<template>
  <button
    role="tab"
    :aria-selected="tabs.activeTab.value === value"
    @click="tabs.setActiveTab(value)"
  >
    <slot />
  </button>
</template>
```

### Generic Components

```vue
<!-- GenericList.vue -->
<script setup lang="ts" generic="T extends { id: string }">
defineProps<{
  items: T[];
  selected?: T;
}>();

defineEmits<{
  select: [item: T];
}>();

defineSlots<{
  default: (props: { item: T }) => any;
}>();
</script>

<template>
  <ul>
    <li
      v-for="item in items"
      :key="item.id"
      :class="{ selected: selected?.id === item.id }"
      @click="$emit('select', item)"
    >
      <slot :item="item" />
    </li>
  </ul>
</template>
```

### Teleport

Render content outside the component's DOM hierarchy:

```vue
<template>
  <button @click="showModal = true">Open</button>

  <Teleport to="body">
    <div v-if="showModal" class="modal-overlay" @click.self="showModal = false">
      <div class="modal" role="dialog" aria-modal="true">
        <slot />
        <button @click="showModal = false">Close</button>
      </div>
    </div>
  </Teleport>
</template>
```

### Suspense (Async Components)

```vue
<template>
  <Suspense>
    <template #default>
      <AsyncDashboard />
    </template>
    <template #fallback>
      <DashboardSkeleton />
    </template>
  </Suspense>
</template>
```

**Async setup** - Components with async operations in `<script setup>`:

```vue
<script setup lang="ts">
// This component must be wrapped in <Suspense>
const { data } = await useFetch("/api/dashboard");
</script>
```

### Error Handling

Vue 3 `onErrorCaptured` for component-level error boundaries:

```vue
<script setup lang="ts">
import { ref, onErrorCaptured } from "vue";

const error = ref<Error | null>(null);

onErrorCaptured((err) => {
  error.value = err;
  return false; // prevent propagation
});
</script>

<template>
  <div v-if="error" role="alert">
    <p>Something went wrong: {{ error.message }}</p>
    <button @click="error = null">Retry</button>
  </div>
  <slot v-else />
</template>
```

### Template Refs (Vue 3.5+)

```vue
<script setup lang="ts">
import { useTemplateRef, onMounted } from "vue";

// Vue 3.5+: useTemplateRef for type-safe template refs
const inputEl = useTemplateRef<HTMLInputElement>("search-input");

onMounted(() => {
  inputEl.value?.focus();
});
</script>

<template>
  <input ref="search-input" type="text" />
</template>
```

**Bad** - String ref with type assertion (pre-3.5 pattern):

```vue
<script setup lang="ts">
const input = ref<HTMLInputElement | null>(null);
</script>
<template>
  <input ref="input" />
  <!-- ref name must match variable name exactly -->
</template>
```

### v-model with defineModel (Vue 3.4+)

```vue
<!-- SearchInput.vue -->
<script setup lang="ts">
const modelValue = defineModel<string>({ required: true });
const focused = defineModel<boolean>("focused", { default: false });
</script>

<template>
  <input
    :value="modelValue"
    @input="modelValue = ($event.target as HTMLInputElement).value"
    @focus="focused = true"
    @blur="focused = false"
  />
</template>

<!-- Usage -->
<!-- <SearchInput v-model="search" v-model:focused="isSearchFocused" /> -->
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Component Design

**Stack:** {detected framework}
**Component model:** {Nuxt (SSR + client) | Vite (client-only)}

### Component Tree

{ComponentName} - {responsibility}
  ├── {ChildA} - {responsibility}
  └── {ChildB} - {responsibility}

### Component Specifications

| Component      | Props                  | Emits          | Slots          | Pattern            |
| -------------- | ---------------------- | -------------- | -------------- | ------------------ |
| {name}         | {key props}            | {key events}   | {slot names}   | Composition / Generic |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Options API or mixins in new code (use Composition API and composables)
- `this` keyword anywhere in `<script setup>` (it's undefined)
- Destructuring props without `toRefs()` in Vue < 3.5 (loses reactivity)
- Prop drilling through more than 2 levels (use provide/inject or Pinia)
- God components that handle multiple unrelated concerns
- Using `v-html` without sanitization (XSS risk)
- Inline prop types on complex components (use named interfaces)
- Deeply nested v-if/v-else chains in templates (extract to named components or computed)
