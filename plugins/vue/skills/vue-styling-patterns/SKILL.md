---
name: vue-styling-patterns
description: Vue 3.5 styling review: scoped styles, CSS v-bind, Tailwind/UnoCSS, component libraries, design tokens, dark mode, responsive.
metadata:
  category: frontend
  tags: [vue, styling, scoped-styles, tailwind, dark-mode]
user-invocable: false
---

# Vue Styling Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing or reviewing a styling approach for a Vue/Nuxt project
- Applying Vue-specific features (scoped styles, `:deep()`, CSS `v-bind`)
- Implementing dark mode, responsive layout, or design tokens
- Integrating component libraries (Vuetify, PrimeVue, Headless UI)

## Rules

- Use the project's established styling approach; do not mix paradigms without an explicit boundary.
- Tailwind CSS is the default recommendation for new projects.
- Scoped styles are the default for component-local CSS in SFCs; reach for `:deep()` before `!important`.
- Use CSS `v-bind` only for reactive values; static styling stays in classes or plain CSS.
- Responsive design is mobile-first (`min-width` breakpoints).
- Dark mode uses Tailwind's `dark:` variant or CSS custom properties; never hardcoded color pairs in templates.
- Preserve accessibility: WCAG contrast, visible focus indicators.

## Patterns

### Approach Selection

| Approach      | When to Use                                      | Vue/Nuxt Integration  |
| ------------- | ------------------------------------------------ | --------------------- |
| Tailwind CSS  | New projects, design systems, rapid iteration    | `@nuxtjs/tailwindcss` |
| Scoped Styles | Component-local CSS, minimal tooling             | Built-in              |
| UnoCSS        | Tailwind alternative with faster build           | `@unocss/nuxt`        |
| Vuetify       | Material Design apps                             | `vuetify-nuxt-module` |
| PrimeVue      | Enterprise apps; use `unstyled` with Tailwind    | `@primevue/nuxt-module` |
| Headless UI   | Custom design with accessible primitives         | `@headlessui/vue`     |

### Scoped Styles and Selectors

```vue
<style scoped>
.card :deep(.child)   { color: red; }   /* style child component internals */
.card :slotted(.item) { font-weight: bold; } /* style slotted content */
:global(.app-toast)   { color: blue; }  /* escape scope */
</style>
```

### CSS `v-bind` (reactive only)

```vue
<script setup lang="ts">
const theme = ref({ primary: "#3b82f6" });
const progress = ref(75);
</script>

<style scoped>
.button       { background-color: v-bind("theme.primary"); }
.progress-bar { width: v-bind("progress + '%'"); }
</style>
```

### Tailwind Variant Composition

Centralize variant maps; avoid string concatenation in templates.

```vue
<script setup lang="ts">
const props = defineProps<{ variant?: "primary" | "destructive"; size?: "sm" | "md" }>();
const variants = {
  primary: "bg-blue-600 text-white hover:bg-blue-700",
  destructive: "bg-red-600 text-white hover:bg-red-700",
};
const sizes = { sm: "h-8 px-3 text-sm", md: "h-10 px-4 text-sm" };
</script>

<template>
  <button
    :class="[
      'inline-flex items-center justify-center rounded-lg font-medium transition-colors',
      'focus-visible:outline-none focus-visible:ring-2',
      variants[props.variant ?? 'primary'],
      sizes[props.size ?? 'md'],
    ]"
  >
    <slot />
  </button>
</template>
```

### Tailwind with Nuxt

`modules: ["@nuxtjs/tailwindcss"]` in `nuxt.config.ts`. Config style depends on Tailwind major: v4 uses CSS-first `@theme` in the imported CSS; v3 uses `tailwind.config.ts`.

### Dark Mode

Class strategy (Tailwind) plus `@nuxtjs/color-mode` for Nuxt apps:

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@nuxtjs/tailwindcss", "@nuxtjs/color-mode"],
  colorMode: { classSuffix: "" }, // emits `dark` (not `dark-mode`) on <html>
});
```

```vue
<template>
  <div class="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100">
    <slot />
  </div>
</template>
```

### Design Tokens

```css
:root { --color-primary: #3b82f6; --color-surface: #ffffff; --radius-md: 0.5rem; }
.dark { --color-primary: #60a5fa; --color-surface: #111827; }
```

Reference tokens from Tailwind via `@theme` (v4) or `theme.extend.colors` (v3) so classes and tokens stay in sync.

### Component Library Integration

Run PrimeVue/Vuetify in **unstyled mode** when Tailwind is already in use; otherwise their design system fights Tailwind utilities.

```ts
// nuxt.config.ts
export default defineNuxtConfig({
  modules: ["@primevue/nuxt-module"],
  primevue: { options: { unstyled: true } },
});
```

## Output Format

Consuming workflow skills parse this structure; preserve field names and enums.

```
## Styling Architecture

**Stack:** {Vue 3 + Vite | Nuxt 3 | Nuxt 4}
**Primary approach:** {Tailwind v4 | Tailwind v3 | UnoCSS | Scoped Styles | Vuetify | PrimeVue}
**Component library:** {Vuetify | PrimeVue (styled) | PrimeVue (unstyled) | Headless UI | None}
**Dark mode:** {Tailwind class | @nuxtjs/color-mode | CSS vars | None}
**Design tokens:** {Tailwind config | CSS custom properties | both | None}

### Findings

| Area              | Status                                | Notes                              |
| ----------------- | ------------------------------------- | ---------------------------------- |
| Approach mixing   | {Consistent | Mixed (justified) | Mixed (issue)} | {boundary or conflict}    |
| Scoped styles     | {OK | Leaking | Overusing :deep}      | {file:line}                        |
| CSS v-bind usage  | {OK | Misused for static values}      | {file:line}                        |
| Responsive        | {Mobile-first | Desktop-first}        | {breakpoints used}                 |
| Dark mode         | {Working | Partial | Missing}         | {strategy gaps}                    |
| Accessibility     | {OK | Contrast issue | Focus missing}| {component}                        |

### Recommendations

- {recommendation with rationale}

### Issues

- [Severity: {High | Medium | Low}] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction with file path}
```

## Avoid

- Mixing paradigms without an explicit boundary (Tailwind + Vuetify styled).
- `!important` to override scoped styles - use `:deep()` or tokens.
- Hardcoded colors in templates - use tokens or Tailwind classes.
- Scattered `dark:`/`.dark` pairs instead of token swaps.
