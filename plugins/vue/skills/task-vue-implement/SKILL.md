---
name: task-vue-implement
description: Implement Vue 3.5 / Nuxt 3 / Vite feature end-to-end - SFCs, composables, Pinia, data, routing, forms, a11y, tests.
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## When to Use

Building a new Vue feature spanning components, state, data fetching, routing, and tests. Not for single-component edits, bug fixes (use `task-vue-debug`), or refactors without new behavior.

If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, load `Use skill: spec-aware-preamble` after Step 2 and follow its mode contract; skip GATHER (and DESIGN when `plan.md` is present). Never edit spec artifacts from this workflow.

## Workflow

**Step 1 - Behavioral principles.** Use skill: `behavioral-principles`.

**Step 2 - Detect stack.** Use skill: `stack-detect`. Confirm Vue 3 + (Nuxt 3 | Vite + Vue Router); identify styling, state lib (Pinia), test framework, and any monolith backend (Rails/Django/Laravel). Halt and ask if mismatched. Vite branch: skip Nuxt server routes and auto-imports, use Vue Router and client fetching.

**Step 3 - Gather.** Ask: feature name, user stories, components, data sources, interactions, routing, form inputs, a11y constraints. UI-only feature: skip data and form steps. Existing components: read and compose, do not duplicate.

**Step 4 - Design.** Use skill: `vue-component-patterns` + `vue-routing-patterns`. If monolith detected: Use skill: `vue-monolith-integration` to choose mount strategy (Inertia | islands | widget). Propose component tree (page vs reusable), file layout, routes. Request approval before code:

```
pages/<feature>/index.vue                          # Nuxt route (or src/views/ for Vite)
components/<feature>/<Component>.vue + .test.ts
composables/use<Name>.ts + .test.ts
server/api/<resource>/index.get.ts                 # Nuxt only
stores/<feature>.ts                                # Pinia, when shared/global
types.ts
```

**Step 5 - State.** Use skill: `vue-state-patterns` + `frontend-state-management`. Categorize: local | shared | global | server | URL | form. Assign owner. Filters and pagination belong in URL state; server data in `useFetch`/`useAsyncData` or TanStack Query; no server state in Pinia.

**Step 6 - Data.** Use skill: `vue-data-fetching` + `frontend-api-integration`. Define keys, cache invalidation, loading/error/empty states, optimistic updates if needed.

**Step 7 - Components.** Use skill: `vue-composables-patterns` + `vue-styling-patterns`. Nuxt: Use skill: `vue-nuxt-patterns`. Generate `<script setup lang="ts">` SFCs with `defineProps<T>()` / `defineEmits<T>()`; composables named `use*`, single concern.

**Step 8 - Forms.** Use skill: `frontend-form-handling` (skip if no forms). Validation, error display, submit protection, dirty tracking.

**Step 9 - A11y.** Use skill: `frontend-accessibility`. Audit to WCAG 2.1 AA: semantic HTML, keyboard nav, ARIA, focus management.

**Step 10 - Tests.** Use skill: `vue-testing-patterns` + `frontend-testing-patterns`. Component tests (Vue Test Utils), composable tests, integration with MSW. Assert behavior, not internals. List e2e candidates.

**Step 11 - Validate.** Run `npx nuxi typecheck` (Nuxt) or `npx vue-tsc --noEmit` (Vite), lint, test. Fix failures before reporting.

## Output Format

```markdown
## Files Generated

[grouped: routes/pages, components, composables, stores, server routes (Nuxt), types, tests]

## Component Tree

<Root> - {responsibility}
├── <ChildA> - {responsibility}
└── <ChildB> - {responsibility}

## State Map

| State | Category | Owner | Mechanism |
| ----- | -------- | ----- | --------- |
| ...   | local/shared/global/server/URL/form | ... | ref / Pinia / useFetch / useAsyncData / route query / VeeValidate |

## Endpoints / Queries

| Method | Path | Key | Loading | Error | Empty |
| ------ | ---- | --- | ------- | ----- | ----- |

## Tests

- Component: {count} (Vue Test Utils)
- Composable: {count}
- Integration: {count} (MSW)
- E2E candidates: {list}
```

## Self-Check

- [ ] Step 1-2: behavioral principles loaded; stack confirmed (Nuxt or Vite branch chosen; monolith strategy chosen if applicable)
- [ ] Step 3-4: requirements gathered; component tree and file layout approved before code
- [ ] Step 5: state categorized; URL state for filters/pagination; no server state in Pinia
- [ ] Step 6: data calls have keys, cache invalidation, and loading/error/empty states
- [ ] Step 7: `<script setup lang="ts">`, Composition API, typed props/emits, composables single-concern
- [ ] Step 8: forms have validation, error display, submit protection, dirty tracking (if applicable)
- [ ] Step 9: WCAG 2.1 AA - semantic HTML, keyboard, ARIA, focus
- [ ] Step 10: tests assert behavior (Vue Test Utils + MSW); critical paths flagged for e2e
- [ ] Step 11: typecheck, lint, tests pass

## Avoid

- `any` or suppressed TS errors; Options API or mixins in new code
- Server state in Pinia - use `useFetch`/`useAsyncData` or TanStack Query
- `reactive()` for primitives - use `ref()`
- Missing loading/error/empty states on data-fetching components
- Tests asserting internal state, watchers, or method calls
- Generating code before design approval
- Fighting Nuxt conventions (manual routing, manual imports) when Nuxt is detected
