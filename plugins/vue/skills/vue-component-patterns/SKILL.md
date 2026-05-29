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
- Type `defineProps`/`defineEmits`/`defineSlots` with generics; extract `interface Props` once shape exceeds ~3 fields.
- Prefer slots over prop-heavy config. One responsibility per component.
- Use `provide`/`inject` with typed `InjectionKey` for cross-cutting state; never prop-drill past 2 levels.
- Use `defineModel` (3.4+) for v-model and `useTemplateRef` (3.5+) for refs.
- Destructured props are reactive in 3.5+; pre-3.5 use `toRefs(props)`.

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
export interface TabsContext { activeTab: Ref<string>; setActiveTab: (t: string) => void }
export const TabsKey: InjectionKey<TabsContext> = Symbol("Tabs");

// Tabs.vue (provider)
provide(TabsKey, { activeTab, setActiveTab: (t) => (activeTab.value = t) });

// Tab.vue (consumer) - throw on missing inject; silent undefined hides bugs
const tabs = inject(TabsKey);
if (!tabs) throw new Error("Tab must be used within <Tabs>");
```

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

### Component Specifications

| Component | Props       | Emits        | Slots       | Pattern                              |
| --------- | ----------- | ------------ | ----------- | ------------------------------------ |
| {name}    | {key props} | {key events} | {slot names}| {Composition | Generic | Compound | Async} |

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- God components mixing unrelated concerns.
- `v-html` on untrusted input (XSS).
- Nested `v-if`/`v-else-if` chains - extract to computed or sub-components.
- Returning `true` from `onErrorCaptured` unless propagation is intentional.
