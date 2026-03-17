---
name: vue-styling-patterns
description: Vue styling patterns - scoped styles, CSS v-bind, Tailwind CSS, UnoCSS, Vuetify/PrimeVue component libraries, design tokens, responsive design, and dark mode for Vue 3.5+.
metadata:
  category: frontend
  tags: [vue, styling, scoped-styles, css-v-bind, tailwind, unocss, vuetify, primevue, dark-mode]
user-invocable: false
---

# Vue Styling Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a styling approach for a Vue project
- Using Vue-specific styling features (scoped styles, CSS v-bind)
- Implementing responsive design, dark mode, or design tokens
- Integrating component libraries (Vuetify, PrimeVue, Headless UI)
- Reviewing styling patterns for consistency and maintainability

## Rules

- Use the project's established styling approach - do not mix paradigms without good reason
- Tailwind CSS is the primary recommendation for new projects
- Scoped styles are the default for component-specific CSS in Vue SFCs
- CSS v-bind for reactive dynamic styles - not inline `:style` bindings for static values
- Responsive design must be mobile-first (min-width breakpoints)
- Dark mode must use CSS custom properties or Tailwind's `dark:` variant
- Styling must not break accessibility (sufficient contrast, visible focus indicators)

## Patterns

### Styling Approach Selection

| Approach      | When to Use                                       | Vue Integration       |
| ------------- | ------------------------------------------------- | --------------------- |
| Tailwind CSS  | New projects, rapid development, design systems   | Native, Nuxt module   |
| Scoped Styles | Component-specific CSS, minimal tooling           | Built-in              |
| UnoCSS        | Tailwind alternative, faster build, Nuxt-native   | @unocss/nuxt          |
| Vuetify       | Material Design apps, comprehensive component set | vuetify-nuxt-module   |
| PrimeVue      | Enterprise apps, unstyled mode for customization  | @primevue/nuxt-module |
| Headless UI   | Fully custom design with accessible primitives    | @headlessui/vue       |

### Scoped Styles

```vue
<style scoped>
/* Only applies to this component - no leaking to children */
.card {
  border-radius: 0.5rem;
  padding: 1rem;
}

/* Deep selector to style child component internals */
.card :deep(.child-class) {
  color: red;
}

/* Slotted selector for styles on slotted content */
.card :slotted(.slot-content) {
  font-weight: bold;
}

/* Global selector within scoped block */
:global(.some-global-class) {
  color: blue;
}
</style>
```

### CSS v-bind (Reactive Styles)

```vue
<script setup lang="ts">
const theme = ref({
  primary: "#3b82f6",
  radius: "0.5rem",
});

const progress = ref(75);
</script>

<style scoped>
.button {
  background-color: v-bind("theme.primary");
  border-radius: v-bind("theme.radius");
}

.progress-bar {
  width: v-bind("progress + '%'");
  transition: width 0.3s ease;
}
</style>
```

### Tailwind CSS with Vue

```vue
<script setup lang="ts">
const props = defineProps<{
  variant?: "primary" | "secondary" | "destructive";
  size?: "sm" | "md" | "lg";
}>();

const variantClasses: Record<string, string> = {
  primary: "bg-blue-600 text-white hover:bg-blue-700",
  secondary: "bg-gray-100 text-gray-900 hover:bg-gray-200",
  destructive: "bg-red-600 text-white hover:bg-red-700",
};

const sizeClasses: Record<string, string> = {
  sm: "h-8 px-3 text-sm",
  md: "h-10 px-4 text-sm",
  lg: "h-12 px-6 text-base",
};
</script>

<template>
  <button
    :class="[
      'inline-flex items-center justify-center rounded-lg font-medium transition-colors',
      'focus-visible:outline-none focus-visible:ring-2',
      variantClasses[variant ?? 'primary'],
      sizeClasses[size ?? 'md'],
    ]"
  >
    <slot />
  </button>
</template>
```

### Tailwind with Nuxt

**Tailwind v4** (CSS-native config, no `tailwind.config.ts`):

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@nuxtjs/tailwindcss"],
});
```

```css
/* assets/css/tailwind.css */
@import "tailwindcss";
@theme {
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
}
```

**Tailwind v3** (JS config):

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@nuxtjs/tailwindcss"],
  tailwindcss: {
    cssPath: "~/assets/css/tailwind.css",
  },
});
```

### UnoCSS with Nuxt

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@unocss/nuxt"],
});

// uno.config.ts
import { defineConfig, presetUno, presetIcons } from "unocss";

export default defineConfig({
  presets: [presetUno(), presetIcons()],
});
```

### Responsive Design

Mobile-first with Tailwind breakpoints:

```vue
<template>
  <div
    class="
      flex flex-col gap-4
      md:flex-row md:gap-6
      lg:gap-8
    "
  >
    <aside
      class="
        w-full
        md:w-64 md:shrink-0
      "
    >
      <Sidebar />
    </aside>
    <main class="flex-1 min-w-0">
      <slot />
    </main>
  </div>
</template>
```

### Dark Mode

**Tailwind dark mode (class strategy):**

```ts
// tailwind.config.ts
export default {
  darkMode: "class",
};
```

```vue
<template>
  <div class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <slot />
  </div>
</template>
```

**Color mode with Nuxt:**

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@nuxtjs/color-mode"],
  colorMode: {
    classSuffix: "",
  },
});
```

```vue
<script setup lang="ts">
const colorMode = useColorMode();
</script>

<template>
  <button
    @click="
      colorMode.preference = colorMode.preference === 'light' ? 'dark' : 'light'
    "
  >
    {{ colorMode.preference === "light" ? "Dark" : "Light" }} mode
  </button>
</template>
```

### Design Tokens

```css
/* assets/css/tokens.css */
:root {
  --color-primary: #3b82f6;
  --color-primary-hover: #2563eb;
  --color-surface: #ffffff;
  --color-text: #111827;
  --radius-sm: 0.375rem;
  --radius-md: 0.5rem;
  --radius-lg: 0.75rem;
}

.dark {
  --color-primary: #60a5fa;
  --color-primary-hover: #93c5fd;
  --color-surface: #111827;
  --color-text: #f9fafb;
}
```

### Component Library Integration (PrimeVue Unstyled)

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@primevue/nuxt-module"],
  primevue: {
    options: {
      unstyled: true, // use your own styles
    },
  },
});
```

```vue
<template>
  <DataTable :value="products" :paginator="true" :rows="10">
    <Column field="name" header="Name" sortable />
    <Column field="price" header="Price" sortable />
    <Column field="category" header="Category" />
  </DataTable>
</template>
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Styling Architecture

**Stack:** {detected framework}
**Styling approach:** {Tailwind CSS | Scoped Styles | UnoCSS}
**Component library:** {Vuetify | PrimeVue | Headless UI | None}

### Design Tokens

| Token Category | Source                           |
| -------------- | -------------------------------- |
| Colors         | {CSS vars | Tailwind config}     |
| Spacing        | {Tailwind default | custom}      |
| Typography     | {font families and scale}        |
| Dark mode      | {class strategy | @nuxtjs/color-mode} |

### Component Variants

| Component | Variants                           | Approach        |
| --------- | ---------------------------------- | --------------- |
| Button    | primary, secondary, destructive    | Tailwind classes|
| Card      | default, outlined                  | Scoped + v-bind |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Mixing multiple styling paradigms in the same project without clear boundaries
- Inline `:style` bindings for static values (use CSS v-bind or classes)
- Unscoped styles that leak to child components unexpectedly
- Desktop-first responsive design (mobile-first is the standard)
- Hardcoded color values instead of design tokens or Tailwind classes
- Using `!important` to override scoped styles (use `:deep()` or design tokens)
- Installing Vuetify or PrimeVue (styled mode) in a project already using Tailwind (conflicting design systems)
- CSS v-bind for values that don't change (use static CSS instead)
