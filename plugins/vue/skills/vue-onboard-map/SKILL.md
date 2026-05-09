---
name: vue-onboard-map
description: Vue 3.5 / Nuxt / Vite onboarding map: package manager, build, TS config, routing, Pinia, useFetch / TanStack Query, styling, UI library.
metadata:
  category: frontend
  tags: [onboarding, codebase-map, vue, nuxt, vite, pinia]
user-invocable: false
---

# Vue Onboard Map (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-onboard` when the detected stack is Vue.

## When to Use

- A workflow needs Vue-specific orientation: package manager, build framework, routing, state, data fetching, styling, component library.
- Project has `package.json` with `vue` dep.

## Rules

- Identify build framework first: Nuxt 3 (`nuxt.config.*` + `nuxt` dep) or Vite SPA (`vite.config.*` + `@vitejs/plugin-vue`).
- Identify Vue API style: Composition API with `<script setup>` is the modern default; Options API is legacy but possible.
- Identify state management: Pinia (`pinia` dep, `stores/` directory) or Vuex (legacy, `vuex` dep).
- Identify SSR vs CSR: Nuxt is SSR by default with hybrid rendering modes; Vite SPA is client-only.
- Identify component library: Vuetify, Quasar, Element Plus, PrimeVue, Naive UI, Headless UI for Vue, custom.

## Patterns

### Build Framework Inventory

| File                | What it tells you                                                                |
| ------------------- | -------------------------------------------------------------------------------- |
| `nuxt.config.ts`    | Nuxt project; module list, runtime config, build target                          |
| `vite.config.ts`    | Vite SPA; `@vitejs/plugin-vue` and any code-splitting/transform plugins          |
| `tsconfig.json`     | TypeScript config; `vue-tsc` for type checking                                    |
| `package.json`      | Deps; check for `vue`, `nuxt`, `pinia`, `@vue/test-utils`, `vitest`, `playwright` |
| `tailwind.config.*` | Tailwind                                                                          |
| `unocss.config.*`   | UnoCSS (atomic CSS, often with Vue/Nuxt)                                         |

### Bootstrap Path

1. Node toolchain: `engines.node` in `package.json`; Nuxt 3 requires Node 18+.
2. Install: `<manager> install` (npm/pnpm/yarn/bun).
3. Env: `cp .env.example .env`.
4. Run:
   - **Nuxt:** `npm run dev` (port 3000); SSR + HMR.
   - **Vite SPA:** `npm run dev` (port 5173).
5. Verify: open browser; check `/_nuxt/` for Nuxt static; check root path.

### Key File Inventory

**Nuxt 3 (file-based routing):**

| Location                | Purpose                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `app.vue`               | Root component (rendered around all pages)                                |
| `pages/index.vue`       | Home route                                                                 |
| `pages/<route>.vue`     | Route                                                                      |
| `pages/<dyn>/[id].vue`  | Dynamic route (`route.params.id`)                                          |
| `layouts/default.vue`   | Default layout; per-page override via `definePageMeta({ layout: '...' })` |
| `components/`           | Auto-imported components (no explicit `import`)                            |
| `composables/`          | Auto-imported `use*` composables                                           |
| `stores/`               | Pinia stores (auto-imported with `@pinia/nuxt` module)                     |
| `server/api/<route>.ts` | API endpoint (Nitro server)                                                 |
| `server/middleware/`    | Server-side middleware                                                      |
| `middleware/`           | Route middleware (client/SSR)                                               |
| `plugins/`              | Vue plugins (loaded at startup)                                             |
| `nuxt.config.ts`        | Nuxt config; modules, runtime config, build options                          |
| `assets/`               | Processed assets (CSS, fonts, images)                                       |
| `public/`               | Static files served as-is                                                    |

**Vite SPA:**

| Location                | Purpose                                                                  |
| ----------------------- | ------------------------------------------------------------------------ |
| `index.html`            | Entry HTML                                                                 |
| `src/main.ts`           | Mount entry: `createApp(App).use(...).mount('#app')`                       |
| `src/App.vue`           | Root component                                                             |
| `src/router/index.ts`   | Vue Router config (if using Vue Router)                                    |
| `src/views/` or `src/pages/` | Page components                                                       |
| `src/components/`       | Reusable components                                                         |
| `src/composables/`      | `use*` composables                                                          |
| `src/stores/`           | Pinia stores                                                                |
| `src/services/` or `src/api/` | HTTP clients                                                          |
| `src/assets/`           | Static assets                                                                |

### Conventions

- **`<script setup>`** as default in modern Vue 3 projects; Composition API.
- **TypeScript** with `vue-tsc` for type checking (separate from Vite).
- **Pinia setup-style stores** (`defineStore('id', () => ({ ... }))`) more common than options-style.
- **Auto-imports in Nuxt:** components, composables, Vue/Nuxt utilities (no manual `import`).
- **Styling:** scoped CSS in SFCs (`<style scoped>`), CSS modules, Tailwind, UnoCSS, or component library themes.
- **Forms:** VeeValidate, FormKit, native v-model + manual validation.
- **Data fetching (Nuxt):** `useFetch`, `useAsyncData`, `$fetch`. (Vite SPA: TanStack Query Vue, axios, fetch).
- **i18n:** `vue-i18n`, `@nuxtjs/i18n`.
- **Tests:** Vitest + Vue Test Utils + happy-dom; Playwright for E2E.

### Risk Hotspots Specific to Vue

- **Destructuring `reactive`** loses reactivity: `const { x } = reactive({...})` - `x` is a plain value.
- **Pinia destructuring** without `storeToRefs` loses reactivity in templates.
- **`v-for` without `key`:** identity confusion on reorder; updates wrong DOM nodes.
- **`watch` with `deep: true`** on large objects - perf cost.
- **Nuxt `useFetch` caching:** keyed cache by URL; same URL + same args = cached. May need explicit `key` for dynamic refetching.
- **`process.server` / `process.client`** legacy syntax (Nuxt 3.10+ uses `import.meta.server` / `import.meta.client`).
- **`useState` (Nuxt) vs `ref`:** the former survives SSR hydration with serialized payload; the latter does not.
- **SSR-incompatible code:** browser-only APIs (`window`, `document`, `localStorage`) in setup must be guarded with `import.meta.client`.
- **Plugins running on both server and client:** check the file naming convention (`.client.ts` / `.server.ts` suffix in Nuxt).
- **Composable lifecycle binding:** composables that register lifecycle hooks must be called inside `setup()`, not from arbitrary points.
- **Component auto-import collisions:** Nuxt auto-imports are by file path; deeply nested same-named files require explicit imports.

### First-PR Safe Zones

- New page in `pages/` (Nuxt) or new route in `src/router/` (Vite).
- New component in `components/`.
- New composable in `composables/`.
- New env var in `.env.example` with safe default.

Riskier:

- `app.vue` / `App.vue` - affects every page.
- Plugins - run at startup.
- Nuxt `nuxt.config.ts` - rebuild required.
- Auth flow.

### Ecosystem Currency

- Vue 3.5+ with reactivity transform out (manual `.value` is back).
- Nuxt 3 stable; Nuxt 4 (Vite-only with rolldown) in development.
- Pinia 2.1+ standard for state.
- Vite 5/6.
- Vitest replacing Jest in new projects.
- VueUse for composable utilities.

## Output Format

Inject into `task-onboard` sections:

**Stack and Tooling:** package manager, build framework (Nuxt vs Vite SPA), Vue version, TS + vue-tsc, state (Pinia/Vuex), styling, component library, data fetching.

**Local Bootstrap:** install command, env file, run command, default port.

**Architecture Map:** routing (file-based for Nuxt, config-based for Vite), components/composables/stores layout, plugins, server API for Nuxt.

**Conventions:** `<script setup>`, Pinia store style (setup vs options), styling approach, auto-imports (Nuxt), data fetching pattern.

**Risk Hotspots:** reactive destructuring, Pinia destructuring without storeToRefs, v-for keys, SSR-incompatible code, useState vs ref in Nuxt.

**First-PR Safe Zones:** scoped to observed structure.

## Avoid

- Treating Vue 2 patterns as current
- Recommending Vuex on a Pinia project
- Listing every Nuxt module - focus on the architectural ones
- Skipping `process.server`/`import.meta.server` distinction in Nuxt 3.10+
- Glossing over Pinia destructuring as a top reactivity bug class
- Recommending Options API in `<script setup>` files
