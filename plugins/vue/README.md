# Tuyen's Agent Skills - Vue

Claude Code plugin for Vue 3.5+ / TypeScript / Nuxt 3 (primary), Vite (secondary) development.

## Stack

- Vue 3.5+
- TypeScript (strict mode)
- Nuxt 3 (primary), Vite + Vue Router (secondary)

## Key Features

- **Composition API**: `<script setup>` by default, composables for reusable logic, typed props/emits
- **Vue 3.5 Features**: Reactive props destructure, useId, useTemplateRef, Suspense (stable)
- **Data Fetching**: Nuxt useFetch/useAsyncData (primary), TanStack Query Vue, composable-based fetching
- **State Management**: Pinia (primary), composable stores, SSR hydration, Vuex migration path
- **Nuxt 3**: Auto-imports, server routes, Nitro server engine, file-based routing, middleware, SEO (useHead/useSeoMeta)
- **Styling**: Tailwind CSS (primary), scoped styles, CSS v-bind, UnoCSS, Vuetify/PrimeVue
- **Testing**: Vitest + Vue Test Utils, composable testing, @nuxt/test-utils, Playwright for e2e
- **Monolith Integration**: Rails (Inertia.js), Django (django-vite), Laravel (Inertia.js) mount strategies
- **TypeScript-First**: Strict mode, generic components, typed slots, no `any` types

## Workflow Skills

Workflow skills (`task-*`) orchestrate multiple atomic skills into task-oriented workflows. They are invoked as slash commands.

| Skill            | Purpose                                                                     |
| ---------------- | --------------------------------------------------------------------------- |
| `task-vue-new`   | End-to-end Vue feature implementation (components + state + data + tests)   |
| `task-vue-debug` | Debug Vue errors (reactivity, hydration, template compilation, Nuxt, build) |

## Atomic Skills (Reusable Patterns)

9 atomic skills provide focused, reusable Vue patterns. These are hidden from the slash menu (`user-invocable: false`) and referenced by workflow skills and agents.

| Skill                      | Purpose                                                                             |
| -------------------------- | ----------------------------------------------------------------------------------- |
| `vue-component-patterns`   | SFC composition: script setup, props/emits typing, slots, provide/inject, Teleport  |
| `vue-composables-patterns` | Composable design: ref vs reactive, watchEffect vs watch, VueUse integration        |
| `vue-routing-patterns`     | Vue Router (Vite) / Nuxt file-based routing: layouts, middleware, guards            |
| `vue-nuxt-patterns`        | Nuxt 3: auto-imports, server routes, useFetch/useAsyncData, Nitro, SEO              |
| `vue-state-patterns`       | Pinia: store design, composable stores, plugins, SSR hydration                      |
| `vue-data-fetching`        | Nuxt useFetch/useAsyncData, TanStack Query Vue, composable fetching, Suspense       |
| `vue-styling-patterns`     | Scoped styles, CSS v-bind, Tailwind CSS, UnoCSS, Vuetify/PrimeVue                   |
| `vue-testing-patterns`     | Vitest + Vue Test Utils, composable testing, @nuxt/test-utils, Playwright e2e       |
| `vue-monolith-integration` | Vue in Rails/Django/Laravel monoliths: Inertia.js, asset pipeline, mount strategies |

## Agents

| Agent                      | Focus                                                                     |
| -------------------------- | ------------------------------------------------------------------------- |
| `vue-architect`            | Vue 3/Nuxt 3 architecture: Composition API, SFC design, Pinia, TypeScript |
| `vue-tech-lead`            | Code review with session context - tracks recurring patterns              |
| `vue-performance-engineer` | Core Web Vitals, Nuxt SSR/SSG, bundle analysis, computed vs method        |
| `vue-security-engineer`    | XSS prevention, CSP, v-html sanitization, auth patterns, Nuxt middleware  |
| `vue-test-engineer`        | Testing strategy: Vitest, Vue Test Utils, @nuxt/test-utils, Playwright    |

## Usage Examples

**Implement a full feature (components + state + data + tests):**

```
/task-vue-new
Feature: Product catalog with filtering and search
Components: ProductList, ProductCard, FilterSidebar, SearchBar
Data: GET /api/products with category, search, pagination
State: URL-synced filters, local UI state for sidebar toggle
```

**Debug a Vue error:**

```
/task-vue-debug
Error: "[Vue warn]: Computed property 'filteredProducts' is already defined in Props"
Component: ProductList
Steps: Added a computed with the same name as a prop
```

## Core Plugin Skills

The following workflows are provided by `core` (install separately):

- `/task-code-review` - Staff-level code review with risk assessment, framework-aware
- `/task-code-secure-review` - Security review
- `/task-code-test` - Test strategy
- `/task-code-refactor` - Refactoring plan
- `/task-code-perf-review` - Performance review
- `/task-docs-generate` - Documentation generation
