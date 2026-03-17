---
name: task-vue-new
description: End-to-end Vue feature implementation workflow - SFC components, composables, state management, API integration, routing, styling, accessibility, and tests for Vue 3.5+ / Nuxt 3 / Vite projects.
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, feature, implementation, workflow, composables, pinia, testing]
  type: workflow
user-invocable: true
---

# Implement Vue Feature

## When to Use

- Implementing a new Vue feature end-to-end (components, state, data fetching, routing, tests)
- Scaffolding a complete page or feature module with production-ready patterns
- Adding a new user-facing flow with API integration and form handling
- Any daily frontend coding task that requires coordinated generation of multiple Vue layers

**Not for**: Single-component changes, bug fixes (use `task-vue-debug`), or refactoring without new functionality.

**Edge cases**:

- **Partial input**: If the user provides only a feature name without details, ask for components needed, data requirements, user interactions, and routing before proceeding to design.
- **No API**: If the feature is purely UI (e.g., static page, settings toggle), skip data fetching and API integration steps; generate only components, state, styling, and tests.
- **Existing components**: If the user references components that already exist, read them and extend or compose with them rather than creating duplicates.
- **Vite project**: If stack-detect identifies Vite instead of Nuxt, skip server routes and Nuxt-specific features; use client-side routing (Vue Router) and client-side data fetching patterns.
- **No forms**: If the feature has no form inputs, skip the form handling step entirely.
- **Monolith detected**: If stack-detect identifies Rails, Django, or Laravel alongside Vue, load `vue-monolith-integration` in the design step to determine mount strategy (Inertia, islands, or widget).

## Rules

- TypeScript strict mode - no `any` types, no type assertions without justification
- `<script setup lang="ts">` by default for all SFCs
- Composition API only - no Options API in new code
- Props typed with `defineProps<T>()` using interface; emits typed with `defineEmits<T>()`
- Composables must start with `use` and encapsulate a single concern
- Colocate tests with components (`ComponentName.test.ts` next to `ComponentName.vue`)
- Each step must complete and be reviewed before proceeding to the next
- Present the design to the user for approval before generating code
- Run typecheck and lint after all files are generated

## Workflow

STEP 1 - DETECT: Use skill: `stack-detect` to determine framework (Nuxt 3 vs Vite + Vue Router), TypeScript config, styling approach, state management library, test framework, and whether a monolith backend is present (Rails/Django/Laravel).

STEP 2 - GATHER: Requirements - feature name, user stories, components needed, data sources (API endpoints), user interactions, routing needs, form inputs, accessibility requirements.

STEP 3 - DESIGN: Use skill: `vue-component-patterns` + `vue-routing-patterns`. If monolith detected (Rails/Django/Laravel): Use skill: `vue-monolith-integration`. Propose component tree with responsibility breakdown, file structure (using Nuxt conventions: `pages/`, `components/`, `composables/`, `server/api/` when Nuxt is detected), and routing. Distinguish page components from reusable components. Present for user approval before generating code.

STEP 4 - STATE: Use skill: `vue-state-patterns` + `frontend-state-management`. Identify state categories (local, shared, global, server, URL, form) and assign ownership to components or stores. Filters, pagination, and sort parameters should default to URL state for shareability.

STEP 5 - DATA: Use skill: `vue-data-fetching` + `frontend-api-integration`. Define data fetching strategy - composable design, cache invalidation, loading/error states, optimistic updates if needed.

STEP 6 - COMPONENTS: Use skill: `vue-composables-patterns` + `vue-styling-patterns`. If Nuxt: Use skill: `vue-nuxt-patterns`. Generate SFC components with proper composable usage, styling, and Nuxt conventions.

STEP 7 - FORMS: Use skill: `frontend-form-handling` (if feature has forms). Implement form validation, error display, submission handling, and dirty tracking.

STEP 8 - A11Y: Use skill: `frontend-accessibility`. Audit generated components for WCAG 2.1 AA compliance - semantic HTML, keyboard navigation, ARIA attributes, focus management.

STEP 9 - TESTS: Use skill: `vue-testing-patterns` + `frontend-testing-patterns`. Generate component tests (Vue Test Utils), composable tests, integration tests (MSW), and identify critical paths for e2e.

STEP 10 - VALIDATE: Run `npx nuxi typecheck` (Nuxt) or `npx vue-tsc --noEmit` (Vite) + lint + test. Present file list, component tree, and test count.

## Self-Check

- [ ] Stack detected and framework identified (STEP 1)
- [ ] Requirements gathered - components, data sources, interactions, routing documented (STEP 2)
- [ ] Component tree designed with mount strategy and approved by user (STEP 3)
- [ ] State management categorized and assigned - no duplicated state, server state separated (STEP 4)
- [ ] Data fetching uses useFetch/useAsyncData or TanStack Query with loading/error/empty states (STEP 5)
- [ ] Components use proper composables, styling approach, and TypeScript types (STEP 6)
- [ ] Forms have validation, error display, submission protection, and dirty tracking if applicable (STEP 7)
- [ ] Accessibility audit passed - semantic HTML, keyboard accessible, ARIA attributes correct (STEP 8)
- [ ] Tests cover components, composables, integration with MSW, and critical user flows (STEP 9)
- [ ] TypeScript compiles with no errors; lint passes; tests pass (STEP 10)

## Output Format

Present a checklist of generated files:

```markdown
## Generated Files

### Components

- [ ] `{path}/{ComponentName}.vue`
- [ ] `{path}/{ComponentName}.test.ts`

### Composables (if custom composables created)

- [ ] `{path}/use{ComposableName}.ts`
- [ ] `{path}/use{ComposableName}.test.ts`

### Types

- [ ] `{path}/types.ts`

### API / Data

- [ ] `{path}/{queryName}.ts` (query functions)

### Server Routes (Nuxt only)

- [ ] `server/api/{resource}/index.get.ts`
- [ ] `server/api/{resource}/[id].get.ts`

## Component Tree

{ComponentName} - {responsibility}
├── {ChildA} - {responsibility}
│ └── {ChildB} - {responsibility}
└── {ChildC} - {responsibility}

## State Map

| State        | Category   | Owner       | Mechanism                             |
| ------------ | ---------- | ----------- | ------------------------------------- |
| {state name} | {category} | {component} | {ref / Pinia / useFetch / URL params} |

## Tests

- Component tests: {count}
- Composable tests: {count}
- Integration tests: {count}
- E2E candidates: {list of critical paths}
```

## Avoid

- Using `any` type or suppressing TypeScript errors
- Options API or mixins in new code
- Storing server state in Pinia (use useFetch/useAsyncData or TanStack Query)
- Using `reactive()` for primitives or simple values (use `ref()`)
- Inline styles instead of the project's styling approach
- Skipping loading, error, or empty states on data-fetching components
- Tests that assert implementation details (internal state, watchers)
- Generating code before the design is approved
- Fighting Nuxt conventions (manual routing, manual imports) when Nuxt is detected
