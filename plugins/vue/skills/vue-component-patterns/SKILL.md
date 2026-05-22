---
name: vue-component-patterns
description: Vue 3.5 SFC patterns: script setup, typed props/emits/slots, provide/inject, Suspense, Teleport, generics, defineModel, error boundaries.
metadata:
  category: frontend
  tags: [vue, components, composition, script-setup, props, slots, provide-inject, teleport]
user-invocable: false
---

# Vue Component Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing Vue 3 SFC component architecture
- Choosing between props/emits, slots, provide/inject, defineModel
- Typing components with generics, typed slots, typed emits
- Adding Suspense, Teleport, or error boundaries

## Rules

- `<script setup lang="ts">` for all new SFCs. No Options API, no mixins (use composables).
- Type `defineProps`, `defineEmits`, `defineSlots` with TypeScript generics. Extract a named `interface Props` once props reach 3+ fields.
- Prefer slots over prop-heavy configuration. Each component owns one responsibility.
- For shared state across nested children, use `provide`/`inject` with a typed `InjectionKey`. Never prop-drill past 2 levels.
- For two-way binding, use `defineModel` (Vue 3.4+), not manual `modelValue` + `update:modelValue`.
- For template refs, use `useTemplateRef` (Vue 3.5+).
- Destructured props are reactive in Vue 3.5+. In <3.5, destructure via `toRefs(props)` only.

## Patterns

### Typed props, emits, slots

```vue
<script setup lang="ts" generic="T extends { id: string }">
interface Props {
  items: readonly T[];
  selected?: T;
  variant?: "default" | "compact";
}
const { items, selected, variant = "default" } = defineProps<Props>();

const emit = defineEmits<{
  select: [item: T];
  remove: [id: string];
}>();

defineSlots<{
  default: (props: { item: T; index: number }) => any;
  empty?: () => any;
}>();
</script>
```

Generic `<script setup>` types slots, emits, and props against `T` so consumers get inferred item types.

### Provide / inject for compound components

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
<!-- Tabs.vue: provider -->
<script setup lang="ts">
import { provide, ref } from "vue";
import { TabsKey } from "./keys";

const { defaultTab } = defineProps<{ defaultTab: string }>();
const activeTab = ref(defaultTab);
provide(TabsKey, { activeTab, setActiveTab: (t) => (activeTab.value = t) });
</script>
```

```vue
<!-- Tab.vue: consumer -->
<script setup lang="ts">
import { inject } from "vue";
import { TabsKey } from "./keys";

const { value } = defineProps<{ value: string }>();
const tabs = inject(TabsKey);
if (!tabs) throw new Error("Tab must be used within <Tabs>");
</script>
```

Always throw when a required inject is missing - silent `undefined` causes opaque runtime bugs.

### v-model with defineModel

```vue
<script setup lang="ts">
const modelValue = defineModel<string>({ required: true });
const focused = defineModel<boolean>("focused", { default: false });
</script>
<!-- Usage: <SearchInput v-model="q" v-model:focused="isFocused" /> -->
```

### Teleport for overlays

Render modals, toasts, tooltips outside the parent DOM tree so they escape `overflow:hidden` and stacking contexts.

```vue
<Teleport to="body">
  <div v-if="open" class="modal-overlay" @click.self="open = false">
    <div role="dialog" aria-modal="true"><slot /></div>
  </div>
</Teleport>
```

### Suspense for async setup

```vue
<Suspense>
  <template #default><AsyncDashboard /></template>
  <template #fallback><DashboardSkeleton /></template>
</Suspense>
```

Any child whose `<script setup>` contains a top-level `await` must sit under a `<Suspense>` ancestor.

### Error boundary with onErrorCaptured

```vue
<script setup lang="ts">
import { ref, onErrorCaptured } from "vue";
const error = ref<Error | null>(null);
onErrorCaptured((err) => {
  error.value = err;
  return false; // stop propagation
});
</script>
<template>
  <div v-if="error" role="alert">{{ error.message }} <button @click="error = null">Retry</button></div>
  <slot v-else />
</template>
```

### Template refs

```vue
<script setup lang="ts">
import { useTemplateRef, onMounted } from "vue";
const inputEl = useTemplateRef<HTMLInputElement>("search-input");
onMounted(() => inputEl.value?.focus());
</script>
<template><input ref="search-input" /></template>
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Component Design

**Stack:** {detected framework}
**Render mode:** {Nuxt SSR + client | Vite client-only}

### Component Tree

{ComponentName} - {responsibility}
  ├── {ChildA} - {responsibility}
  └── {ChildB} - {responsibility}

### Component Specifications

| Component | Props       | Emits        | Slots       | Pattern                              |
| --------- | ----------- | ------------ | ----------- | ------------------------------------ |
| {name}    | {key props} | {key events} | {slot names}| {Composition | Generic | Compound | Async} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- God components mixing unrelated concerns - split by responsibility.
- `v-html` on untrusted input (XSS).
- Deeply nested `v-if`/`v-else-if` chains in templates - extract to computed or named child components.
- Inline `defineProps<{...}>()` once shape grows past ~3 fields - hurts readability and reuse.
- Returning `true` from `onErrorCaptured` unless you intentionally want propagation to parents and the global handler.
