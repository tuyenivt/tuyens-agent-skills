---
name: vue-onboard-map
description: "Map Vue onboarding signals: Nuxt 3 vs Vite SPA, Vue 3.5, TS + vue-tsc, Pinia, useFetch / TanStack Query, styling, UI library."
metadata:
  category: frontend
  tags: [onboarding, codebase-map, vue, nuxt, vite, pinia]
user-invocable: false
---

# Vue Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is Vue.

## When to Use

Workflow needs Vue-specific orientation: build framework, routing, state, data fetching, styling, component library, SSR boundary. Project has `package.json` with `vue`.

## Rules

- Detect build framework first - Nuxt 3 (`nuxt.config.*` + `nuxt` dep) vs Vite SPA (`vite.config.*` + `@vitejs/plugin-vue`). Routing, SSR, and auto-imports diverge.
- Detect API style - `<script setup>` + Composition API is the modern default; Options API is legacy.
- Detect state - Pinia (`pinia` dep, `stores/`); Vuex is legacy.
- Detect package manager from lockfile (`package-lock.json`, `pnpm-lock.yaml`, `yarn.lock`, `bun.lock` / `bun.lockb`).
- Detect data fetching - Nuxt: `useFetch` / `useAsyncData` / `$fetch`; Vite SPA: TanStack Query Vue, axios, native fetch.

## Patterns

### Build Inventory

| File                  | What it tells you                                            |
| --------------------- | ------------------------------------------------------------ |
| `nuxt.config.*`       | Nuxt; modules, runtime config, render mode                   |
| `vite.config.*`       | Vite SPA; check `@vitejs/plugin-vue`                         |
| `tsconfig.json`       | TS config; `vue-tsc` for type-checking SFCs                  |
| `tailwind.config.*` / `unocss.config.*` | Tailwind or UnoCSS                         |
| `.env.example`        | Env vars; Nuxt `NUXT_PUBLIC_*`, Vite `VITE_*` (client-exposed) |
| `vitest.config.*`     | Vitest unit/component tests                                  |
| `playwright.config.*` | E2E framework                                                |

### Bootstrap

1. Install: `<manager> install` (manager from lockfile; `engines.node` in `package.json`; Nuxt 3 needs Node 18+).
2. Env: `cp .env.example .env`.
3. Run: `<manager> run dev` - Nuxt defaults to `:3000` (SSR + HMR), Vite to `:5173`.
4. Verify: open entry route; Nuxt shows `/_nuxt/` static assets.

### Key Files

**Nuxt 3 (file-based routing, auto-imports)**

| Location                | Purpose                                                   |
| ----------------------- | --------------------------------------------------------- |
| `app.vue`               | Root component wrapping all pages                         |
| `pages/<route>.vue`     | Route (`[id].vue` for dynamic)                            |
| `layouts/<name>.vue`    | Layout; per-page via `definePageMeta({ layout })`         |
| `components/`           | Auto-imported components                                  |
| `composables/`          | Auto-imported `use*` composables                          |
| `stores/`               | Pinia stores (with `@pinia/nuxt`)                         |
| `server/api/<route>.ts` | Nitro API endpoint                                        |
| `middleware/`           | Route middleware; `server/middleware/` for server-side    |
| `plugins/`              | Vue plugins; `.client.ts` / `.server.ts` for SSR scoping  |
| `nuxt.config.ts`        | Modules, runtime config, build options                    |
| `public/`               | Static files served as-is                                 |

**Vite SPA**

| Location                | Purpose                                                    |
| ----------------------- | ---------------------------------------------------------- |
| `index.html` + `src/main.ts` | HTML entry + `createApp(App).mount('#app')`           |
| `src/App.vue`           | Root component                                             |
| `src/router/index.ts`   | Vue Router config                                          |
| `src/views/` or `src/pages/` | Page components                                       |
| `src/components/`, `src/composables/`, `src/stores/` | UI, composables, Pinia stores |
| `src/api/` or `src/services/` | HTTP clients                                         |

### Conventions

- **`<script setup>`** with Composition API; Options API is legacy.
- **TS** with `vue-tsc` (separate from Vite's transpile).
- **Pinia setup-style** stores (`defineStore('id', () => ({ ... }))`) preferred over options-style.
- **Auto-imports in Nuxt:** components, composables, Vue/Nuxt utilities (no manual `import`).
- **Component library:** Vuetify, Quasar, Element Plus, PrimeVue, Naive UI, or custom - call out the one the project commits to.
- **Styling:** scoped `<style>`, CSS Modules, Tailwind, UnoCSS, or library theme.
- **Forms:** VeeValidate, FormKit, or `v-model` + manual validation.
- **i18n:** `vue-i18n`, `@nuxtjs/i18n`.
- **Tests:** Vitest + Vue Test Utils + happy-dom; Playwright for E2E.

### Risk Hotspots

- **Reactivity loss** - destructuring `reactive` / Pinia state without `storeToRefs`: see `vue-state-patterns`, `vue-composables-patterns`.
- **Watcher misuse** - `watch` for derived state, `deep: true` on wide objects, missing cleanup: see `vue-composables-patterns`.
- **`v-for` issues** - missing/index keys on reorderable lists, `v-for` + `v-if` on same element: see `vue-component-patterns`.
- **Data fetching** - `useFetch` missing `key` / `transform`, mutation invalidation gaps, `$fetch` in setup running twice on SSR: see `vue-data-fetching`.
- **SSR boundary** - browser APIs in `<script setup>` top level, async setup without `<Suspense>`, `useState` vs `ref` for cross-request state, `.client.ts` / `.server.ts` plugin suffix: see `vue-nuxt-patterns`.
- **Server -> client leaks** - full ORM rows in `__NUXT__` payload, `v-html` XSS, `NUXT_PUBLIC_*` / `VITE_*` secret leak, Nitro endpoint without Zod/auth: see `task-vue-review-security`.
- **Nuxt context syntax** - prefer `import.meta.server` / `import.meta.client` over legacy `process.server` / `process.client`.

### First-PR Safe Zones

Safe: new page in `pages/` (Nuxt) or new route in `src/router/` (Vite); new component in `components/`; new composable in `composables/`; new env var in `.env.example`.

Riskier: `app.vue` / `App.vue` (every page); `plugins/` (startup); `nuxt.config.ts` (rebuild); auth flow.

## Output Format

Inject into `task-onboard` output sections (names match its template):

- **Stack**: package manager, build framework (Nuxt vs Vite SPA), Vue version, TS + vue-tsc, state (Pinia/Vuex), styling, component library, data fetching.
- **Local Quickstart**: install command, env file, run command, default port.
- **Repository Structure / Architecture**: routing (file-based for Nuxt, config for Vite), components/composables/stores layout, plugins, server API for Nuxt.
- **Key Patterns and Conventions**: `<script setup>`, Pinia store style, styling, auto-imports (Nuxt), data fetching pattern.
- **Tech Debt and Risk Hotspots**: reactive destructuring, Pinia without `storeToRefs`, `v-for` keys, SSR-incompatible code, `useState` vs `ref` in Nuxt.
- **First-PR Safe Zones**: scoped to observed structure.

## Avoid

- Treating Vue 2 / Options API as current.
- Listing every Nuxt module - call out architectural ones.
- Glossing over Pinia destructuring as a top reactivity bug class.
