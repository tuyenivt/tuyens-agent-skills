---
name: task-vue-refactor
description: Plan a Vue/Nuxt refactor: god components, prop drilling, watcher overuse, fat composables, untyped props, a11y. Phased, gated.
agent: vue-tech-lead
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

# Vue Refactor

Produce a step-by-step refactor plan for a Vue target (component, composable, page/layout, Pinia store, Nitro endpoint, plugin). Each step is independently committable with `vue-tsc --noEmit` + Vitest gates.

Stack-specific delegate of `task-code-refactor` for Vue.

## When to Use

- Vue code-smell identification with a concrete plan
- Safe refactor of a component / composable / page / Nitro endpoint / store
- Cleanup of god-component / prop-drilling / watcher misuse before merge
- Migrating a single Options API component to Composition API (when explicitly requested)

**Not for:**

- Prioritizing across many candidates (use `task-debt-prioritize`)
- Feature changes (use `task-vue-implement`)
- Cross-module architecture moves (use `task-design-architecture`)
- Bug fixes (use `task-vue-debug`)

## Inputs

| Input                 | Required    | Notes                                                                                                              |
| --------------------- | ----------- | ------------------------------------------------------------------------------------------------------------------ |
| Target                | Yes         | File or route (e.g., `pages/dashboard.vue`, `components/orders/OrderList.vue`, `server/api/account.put.ts`)         |
| Goal                  | Yes         | What the refactor should achieve                                                                                   |
| Test coverage status  | Recommended | Vitest / VTU / Playwright coverage for the target                                                                  |
| Shared/public surface | Recommended | Whether the target is used across feature / route / app boundaries                                                 |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. These rules govern every step that follows.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. If not Vue, stop and route to `/task-code-refactor`. If invoked by a Vue-aware parent, accept the pre-confirmed stack.

Record `Framework` (Nuxt 3 / Vite + Vue Router) and `Vue: <version>` for the output.

### Step 3 - Read the Target

Read the actual files; do not classify from prose alone.

1. Target file top-to-bottom: line count, composable usage, prop interface, conditional rendering depth, `ref`/`reactive`/`watch` declarations, external collaborators (`$fetch`, `useFetch`, Pinia store, navigation, `Sentry.captureException`)
2. Matching tests (`*.test.ts`, Playwright `*.spec.ts`): cases by outcome (happy, error, empty, validation, auth, accessibility)
3. Immediate callers when obvious (page importing feature component, layout wrapping page)
4. For Nitro endpoints, read any page/form that posts to the endpoint - the contract has two sides

If only a goal was given without a target, ask before proceeding.

**Sibling smells.** Other smells in the same file go under `Sibling Smells (Out of Scope)` with deferral rationale and recommended follow-up skill - never silently included, never silently dropped.

**Severity inversion.** If a sibling smell is *higher severity* than the named target (XSS via `v-html`, Nitro endpoint without auth, IDOR), recommend pausing the refactor and routing through `task-vue-review-security` first. Flag in `Sibling Smells`; the refactor PR branches off the security fix, not main.

**Bug-fix smuggled into refactor.** If the user mixes "refactor X" with "and fix that the filter does not persist on refresh," stop and surface the conflict: refactoring assumes behavior preservation, so behavior changes are either a separate PR ahead, or labeled `coupled-fix` in Step 7 with their own gate.

### Step 4 - Coverage Gate (mandatory)

Refactoring without coverage is a rewrite. Identify tests covering the target, then label:

| Status       | Definition                                                        | Action                                                                       |
| ------------ | ----------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** >= 2 boundary outcomes per public entry point | Proceed                                                                      |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                    | Proceed; plan includes non-optional `Step 0` adding the missing boundaries   |
| `Inadequate` | No tests, or happy-path-only                                      | Refuse Steps 1+. Output gate verdict + recommend `task-vue-test`             |

Happy-path-only is `Inadequate`, not `Thin` - a single success case can't prove error handling, empty states, or accessibility preservation.

**Internal-coupled tests.** Inspect each test for `wrapper.vm.<internal>`, render-count spies, or ref-name reads that the planned refactor will rename or remove. Surface as `internal-coupled: <test:line> asserts <ref> which Step <N> will remove` and pin to `Step 0` as a DOM/event rewrite before the affected step runs. Applies even when overall coverage is `Adequate`.

When status is `Thin` or `Inadequate`, render prerequisite tests as: `entry-point | outcome | recommended layer`. Outcomes must include validation failure, error state, empty state, loading state, and (when interactive) accessibility. Layers: component test (VTU/TLV + `user-event`), composable test (`withSetup` or probe component), Nitro endpoint test (`@nuxt/test-utils` `$fetch`), Playwright E2E.

When refusal triggers, Step 5 catalog still runs to produce a preview of Smells Identified + Sibling Smells. Refusal is on Steps 1+, not on diagnostic output.

### Step 5 - Identify Smells

Use judgment - these are signals, not rules. A 250-line component orchestrating clearly named sub-components is fine; a 100-line component doing three unrelated things is not.

**Component:**

| Smell                                   | Signal                                                                                                       | Risk   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ------ |
| God component                           | > 300 lines mixing fetching, state, logic, multiple rendering paths                                          | High   |
| Inline business logic in template       | Calculations, > 3-level branching, formatting inside `{{ }}` / `v-if` chains                                 | Medium |
| Conditional rendering ladder            | > 3 nested `v-if` / ternaries                                                                                | Medium |
| Untyped props                           | `defineProps(['x'])` (runtime-only) or `defineProps<{ x: any }>` - prefer typed `defineProps<{...}>`         | High   |
| Inline event handlers > 3 lines         | Heavy logic in `@click="..."` - extract to a method                                                          | Low    |
| Anonymous default filename              | `Index.vue` deep in a feature folder - rename or set `defineOptions({ name: '...' })`                        | Low    |
| Mass-imported barrel                    | `import { X } from '@/components'` defeats tree-shake                                                        | Medium |
| `<script setup>` mixed with Options API | A single component using both - pick one; new code uses `<script setup>`                                     | Medium |

**Composables:**

| Smell                                 | Signal                                                                                              | Risk   |
| ------------------------------------- | --------------------------------------------------------------------------------------------------- | ------ |
| Fat composable                        | 8+ params and 12+ return fields - extract or split                                                  | High   |
| `watch` for derived state             | `watch([a, b], () => state.sum = a.value + b.value)` - use `computed`                               | High   |
| `watch` for event handling            | `watch(clicked, () => { if (clicked) doThing() })` triggered by `@click` - call `doThing()` direct  | High   |
| Missing watcher / listener cleanup    | Subscriptions / observers / intervals in `onMounted` without `onUnmounted` cleanup                  | High   |
| `ref` for derived value               | State always computed from other state / props - use `computed`                                     | Medium |
| `ref` for lifetime constant           | `const config = ref({...})` initialized once and never set - module-level const                     | Low    |
| `reactive` for primitive              | `reactive({ count: 0 })` - use `ref(0)` for primitives                                              | Low    |
| Deep `reactive` over large data       | `reactive(largeArray)` for a 5K-row dataset - use `shallowRef` / `shallowReactive`                  | High   |
| Destructure / spread loses reactivity | `const { a } = reactive({ a })` - use `toRefs` or props destructure (Vue 3.5+)                      | High   |
| `ref` for URL-synced state            | Filters/page/sort in `ref` instead of route query - breaks deep links, back button, refresh        | Medium |
| Composable called conditionally       | Composable inside `if` or after early return - violates Composition API rules                       | High   |

**Data fetching:**

| Smell                                              | Signal                                                                                                              | Risk   |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------ |
| `onMounted(() => $fetch(...))` for initial data    | Loses SSR, cache, dedup - prefer `useFetch` / `useAsyncData` (Nuxt) or TanStack Query (Vite)                        | High   |
| Server-fetchable data fetched on client (Nuxt)     | Component does `onMounted(() => $fetch(...))` where parent could use `useFetch` server-side - waterfall             | High   |
| Sequential `await` for independent fetches         | `const a = await useFetch(...); const b = await useFetch(...);` instead of `Promise.all` - doubles SSR latency      | Medium |
| Missing `key` for cacheable `useFetch`             | `useFetch(url)` without `key` synthesizes one from call site - broken for parameterized fetches                     | Medium |
| Missing cache invalidation after mutation          | Mutation succeeds without `refreshNuxtData(key)` / `queryClient.invalidateQueries(...)` - UI shows stale data       | High   |

**State / configuration:**

| Smell                                | Signal                                                                                              | Risk   |
| ------------------------------------ | --------------------------------------------------------------------------------------------------- | ------ |
| Prop drilling > 4 layers             | Same prop through 4+ layers - hoist to provide/inject, Pinia, or co-locate                          | Medium |
| `provide` re-renders every consumer  | Provided value rebuilt every render - split stable + changing, or memoize                           | High   |
| Single-consumer `provide`            | `provide` read by exactly one component - lift / pass directly                                      | Low    |
| Mutable module-level state           | `let cache = {}` mutated by render/events - in SSR (Nuxt) leaks across requests                     | High   |
| `import.meta.env.X` sprinkled        | Should be `useRuntimeConfig()` / typed config module                                                | Medium |
| Pinia mega-store                     | One store for all app state - feature-scoped stores reduce blast radius                             | Medium |
| Plugin sandwich at root              | > 5 nested `app.use(plugin)` calls at app entry - consolidate                                       | Low    |

**Nitro endpoint (Nuxt):**

| Smell                                 | Signal                                                                                                                   | Risk |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---- |
| Nitro endpoint without Zod            | `defineEventHandler` reading body without `readValidatedBody(event, Schema.parse)` - mass-assignment risk                | High |
| Nitro endpoint without auth           | Mutation without `requireUserSession(event)` (or session check) at the top                                               | High |
| Nitro endpoint returns entire ORM row | `prisma.user.findUnique({ where })` returned to client - serializes `passwordHash` / internal fields                     | High |
| `v-html` without sanitizer            | User-controlled HTML rendered raw - XSS                                                                                  | High |

**Accessibility:**

| Smell                                | Signal                                                                                                | Risk   |
| ------------------------------------ | ----------------------------------------------------------------------------------------------------- | ------ |
| `<input>` without `<label>`          | Screen readers miss them                                                                              | High   |
| Custom dialog without focus trap     | `<div>` modal without `role="dialog"`, focus trap, keyboard close                                     | High   |
| `<div @click>` for a button          | Not focusable, not announced as button                                                                | High   |
| Image without `alt`                  | `<img>` / `<NuxtImg>` without `alt` (or `alt=""` for decorative)                                      | Medium |

**Tests (when in scope):**

| Smell                             | Signal                                                                                          | Risk   |
| --------------------------------- | ----------------------------------------------------------------------------------------------- | ------ |
| `getByTestId` everywhere          | Couples to implementation - prefer user-centric queries                                         | Medium |
| Asserting `wrapper.vm.<internal>` | Tests on internal component state - breaks on every refactor                                    | High   |
| `fireEvent` without reason        | Skips focus/key events real users trigger (when Testing Library Vue is the helper)              | Medium |
| Snapshot tests on visual layout   | Churn on every styling change; no signal                                                        | Medium |
| Render counts asserted            | `expect(spy).toHaveBeenCalledTimes(2)` for render counts - tests implementation                 | High   |

**Over-engineering signals** (single-impl render-prop, generic abstractions for one consumer, premature compound components): Use skill: `complexity-review` - these are simplifications, not new abstractions.

### Step 6 - Blast Radius

Use skill: `review-blast-radius`. State `Narrow | Moderate | Wide | Critical` before proposing steps.

Vue signals: design-system primitive used cross-feature, root layout / global plugin / Nuxt module, composable imported by > 10 components, prop interface change cascading to all parents, Nitro endpoint consumed by multiple forms, Pinia store shared cross-feature, route segment under many pages.

### Step 7 - Propose the Sequence

Each step must be: independently committable (`vue-tsc --noEmit` + Vitest pass), behaviorally invariant (unless labeled `coupled-fix`), reversible in one revert, tested.

**Primary recipe.** Pick one recipe matching the user's goal as the spine. Fold supporting recipes as additive sub-steps where dependencies require. Never concatenate. State `Primary recipe:` in the output. If the spine exceeds ~8 steps, split into two PRs.

**Coupled-fix.** When a refactor requires a behavior change (e.g., extracting a Nitro endpoint that derives `ownerId` from session requires adding a session check, changing failure mode for unauthenticated callers), label `coupled-fix` with its own gate and rationale.

**Per-step stances (recorded in Output Format).** Every step states:

- **SSR stance (Nuxt only)** - server-rendered | client-only | unchanged | converting. Wrapping with `<ClientOnly>` or guarding with `import.meta.client` changes when the code runs; audit imports for browser-only modules and audit SSR payload changes.
- **Reactivity stance** - `ref` | `reactive` | `shallowRef` | `shallowReactive` | unchanged | converting X to Y. Destructuring a `reactive` loses reactivity; `toRefs(reactive)` preserves it. `.value` access in JS differs by primitive.

**Common recipes:**

**R1 - Replace `watch` for derived state with `computed`.**
1. Identify `watch([a, b], () => state.sum = a.value + b.value)`
2. Replace with `const sum = computed(() => a.value + b.value)`; delete the ref and watcher
3. Update consumers (`sum.value` in JS, `sum` in template)
4. Tests pass; observable behavior unchanged (prior version had a transient render with stale `sum`)

**R2 - Replace `onMounted(() => $fetch(...))` with `useFetch` (Nuxt) or TanStack Query (Vite).**
1. **If on Nuxt and parent could use `useFetch`** (runs server-side during SSR + reuses on hydration): `const { data, pending, error } = await useFetch(url, { key, transform })`; remove the `onMounted`, ref, loading flag
2. **Else** (Vite or genuinely client-only): `useQuery({ queryKey, queryFn })`; handle `isLoading` / `error` from the return
3. Add `refreshNuxtData(key)` / `queryClient.invalidateQueries(...)` on relevant mutations
4. Tests; add boundary tests (empty / error / loading) the `onMounted` version probably missed

**R3 - Replace deep `reactive` over large dataset with `shallowRef`.**
1. Identify `const orders = reactive([])` filled with 5K rows
2. Replace with `const orders = shallowRef<Order[]>([])`; mutations via `orders.value = [...orders.value, newRow]` or `orders.value = nextOrders`
3. Update template usage; nested `.value` access now required in `<script setup>` JS
4. Tests; profile if available (deep-reactive overhead should drop)

**R4 - Move filter/pagination/sort state to URL query (Nuxt + Vue Router).**

This is `coupled-fix` (refresh, deep links, back button now preserve state - UX contract change). Tell the user explicitly.

1. Define the URL contract: params, types, defaults (e.g., `status: 'open' | 'closed' | 'all' = 'all'`); validate via Zod; reject malformed to defaults
2. Replace each `ref` filter with a `computed` reading `useRoute().query`
3. Replace each setter with `useRouter().push({ query: { ...currentQuery, status: 'closed' } })`; `router.replace` for filters that shouldn't pollute history
4. Update fetcher: `useFetch` / `useQuery` keys derive from route query
5. Tests: deep link, back-button restore, refresh preserves, malformed param fallback

**R5 - Extract composable from fat component.**
1. Identify the cohesive state + watcher + handler trio (e.g., filter state + URL sync watcher + setters)
2. Create `useXxx.ts`; copy logic; add composable test (`withSetup` + boundary cases - state transitions, cleanup, edges)
3. Replace inlined logic with `const filterApi = useFilters(...)`
4. Component tests pass unchanged
5. Surface "audit other components for this pattern" as a follow-up, not a bundled step

**R6 - Untangle prop drilling.**
1. Identify the prop chain (which prop, which layers)
2. Choose primitive: (a) **co-locate state** with the consumer if no other consumer needs it, (b) **provide/inject** for cross-cutting state local to a subtree (theme, modal context), (c) **Pinia** for app-state shared by multiple features. This choice is the first decision; not every drill is a Pinia candidate
3. Extract state into the chosen primitive; remove from intermediate layers
4. If using `provide`, stabilize the value (`computed` returning the shape, or `readonly(reactive({...}))`) so consumers don't re-render unnecessarily
5. Tests; intermediate layers are simpler

**R7 - Split god component into focused components.**
1. Identify orthogonal concerns (e.g., `Dashboard.vue` doing filters + list + summary + actions)
2. Extract one concern per commit into a new file with explicit `defineProps<{...}>`; god component renders `<Filters />` etc.
3. Add tests for the new component if it has its own surface
4. Repeat until the original is a thin layout coordinator
5. Route-level / Playwright tests still pass

**R8 - Add Zod validation to Nitro endpoint.**
1. Define a Zod schema for input
2. Replace `await readBody(event)` with `await readValidatedBody(event, Schema.parse)`; use `getValidatedQuery` / `getValidatedRouterParams` for query / path params. Throw `createError({ statusCode: 400, ... })` for typed error response
3. Audit `body.<field>` references that were previously untyped
4. Test: invalid input rejected with expected error shape; valid input proceeds
5. Audit other endpoints in the file - surface as follow-up if not in scope

**R9 - Stabilize `provide` value to prevent re-render storm.**
1. Memoize: `const value = computed(() => ({ a: a.value, b: b.value, fn }))`; declare `fn` once (hoist if pure)
2. **Or split** into two provides: state and actions - actions are stable, state changes per mutation; consumers inject only what they need
3. Tests; profile in Vue DevTools (re-render counts drop)

**R10 - Replace mutable module-level state with injection.**
1. Move `let cache = {}` / `const handlers = []` into a Pinia store, composable + `provide`, or per-component state. For SSR (Nuxt) this is mandatory - module-level state leaks across requests
2. Update consumers to read via the new primitive
3. Assert cross-test isolation (Vitest test order should not matter)

**R11 - Project Pinia / `useState` payload to DTO (Nuxt SSR leak).**
1. Identify data placed in store/state during SSR: `userStore.user = await prisma.user.findUnique({ where })` - the entire row serializes into `__NUXT__` payload
2. Project at the data-fetch layer: Prisma `select` whitelist or DTO mapper
3. Update store/state shape; TypeScript surfaces any caller reading `passwordHash`
4. Tests; verify SSR payload (`view-source` on a rendered page) no longer contains leaked fields

**R12 - Add accessibility for custom interactive component.**
1. Identify the violation (`<div @click>` for a button)
2. Use the semantic element (`<button>`, `<a>`, `<input>`) or add `role`, `tabindex`, `@keydown` dispatching click on Enter/Space
3. Add `label` / `aria-label` / `aria-describedby` as needed
4. `vitest-axe` test asserts no violations

### Step 8 - Validate Plan Against Goal

- [ ] Goal achieved at end of sequence
- [ ] Each step reviewable in < 30 min
- [ ] `vue-tsc --noEmit` + Vitest between every step
- [ ] Low-risk first (additions, extractions) before high-risk (deletions, prop removals, reactivity conversions)
- [ ] Rollback is one revert per step
- [ ] No "while we're here" cleanup bundled

## Output Format

```markdown
## Vue Refactor Plan

**Target:** [file:line or path]
**Goal:** [what the refactor achieves]
**Primary recipe:** [R# from Step 7 - the spine]
**Stack:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[Adequate: one sentence on boundary cases that exist.]
[Thin: list missing boundary tests; Step 0 covers them.]
[Inadequate: state required coverage; recommend `task-vue-test` first. Stop here - omit Blast Radius, Step Sequence, Verification. You may still produce **Smells Identified** and **Sibling Smells** as preview-only.]

**Prerequisite tests** (when Thin or Inadequate):

| Entry point  | Outcome                            | Recommended layer                          |
| ------------ | ---------------------------------- | ------------------------------------------ |
| `OrderList`  | empty-state visible when 0 orders  | component test (VTU/TLV + `user-event`)    |
| `useFilters` | resets on route change             | composable test (`withSetup`)              |

## Smells Identified

| Smell    | Location  | Risk | Notes          |
| -------- | --------- | ---- | -------------- |
| [Smell]  | file:line | High | [one-line why] |

## Sibling Smells (Out of Scope)

_Other smells in the target file; listed for hand-off, not action. Omit if none._

| Smell    | Location  | Why deferred                                | Recommended follow-up                          |
| -------- | --------- | ------------------------------------------- | ---------------------------------------------- |
| [Smell]  | file:line | separate target / separate severity / etc.  | `task-vue-review-security` / other             |

[If a sibling smell is higher severity than the named target, state prominently: "Severity inversion: pause this refactor; route through `task-vue-review-security` first; branch the refactor PR off the security fix, not main."]

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip only if Adequate and no internal-coupled tests)_
- **Change:** add missing boundary tests from Prerequisite Tests; rewrite internal-coupled tests flagged in Step 4
- **Risk:** Low (tests only)
- **Test gate:** new tests pass; suite green
- **Rollback:** revert added test files

### Step 1 - [Verb + noun]
- **Change:** [what is added / extracted / moved]
- **Risk:** Low | Medium | High
- **Step kind:** refactor | coupled-fix
- **Test gate:** [component / composable / E2E / Nitro endpoint]
- **SSR stance:** [server-rendered | client-only | unchanged | converting] _(Nuxt only)_
- **Reactivity stance:** [`ref` | `reactive` | `shallowRef` | `shallowReactive` | unchanged | converting X to Y]
- **Rollback:** [one git revert]

### Step 2 - [Verb + noun]
[Same structure. `coupled-fix` requires rationale for the coupling.]

## Verification

- [ ] Goal achieved at end of sequence
- [ ] Each step independently committable
- [ ] `vue-tsc --noEmit` + Vitest between every step
- [ ] No bundled unrelated cleanup
- [ ] One revert per step
- [ ] No silent SSR <-> client boundary changes; descendants audited (Nuxt)
- [ ] No silent `reactive` <-> `ref` conversions; consumers audited

## Out of Scope

[Adjacent improvements explicitly NOT in this plan.]
```

## Self-Check

- [ ] Steps 1-2: behavioral principles loaded; Vue stack + framework recorded
- [ ] Step 3: target + tests read; sibling smells listed; severity inversion flagged if applicable; smuggled bug-fix split or labeled `coupled-fix`
- [ ] Step 4: Coverage Gate verdict applied with sharp boundaries; `Inadequate` refuses Steps 1+ but still produces Step 5 preview; internal-coupled tests pinned to `Step 0`
- [ ] Step 5: smells classified using the catalog
- [ ] Step 6: blast radius stated
- [ ] Step 7: `Primary recipe:` named; spine <= ~8 steps; every step states SSR (Nuxt) + Reactivity stance; behavior changes labeled `coupled-fix`; ordered low-risk first
- [ ] Step 8: goal mapped to end state; no bundled cleanup

## Avoid

- Producing Steps 1+ when Coverage Gate is `Inadequate`.
- Bundling behavior changes with refactor steps - use `coupled-fix` or split the PR.
- "While we're here" cleanup or renames during a refactor.
- Removing a `watch` without verifying observable behavior is preserved.
- Converting `reactive` <-> `ref` <-> `shallowRef` without auditing consumers.
- `<ClientOnly>` to silence hydration mismatch - fix the cause.
- `useFetch` replacement when component is genuinely client-only with browser-API dependencies.
- `provide`/Pinia as the default fix for prop drilling - co-location is often right.
- Refactoring a design-system primitive without a back-compat plan.
