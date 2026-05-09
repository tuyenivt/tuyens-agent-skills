---
name: task-vue-refactor
description: Vue / Nuxt refactor plan: god components, prop drilling, watcher overuse, fat composables, untyped props, a11y; phased steps with Vitest gate.
agent: vue-tech-lead
metadata:
  category: frontend
  tags: [vue, typescript, nuxt, vite, refactoring, code-quality, technical-debt, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Vue Refactor

## Purpose

Produce a safe, step-by-step refactoring plan for a specific Vue target (component, composable, page / layout, Pinia store, Nitro endpoint, plugin). Identifies Vue-specific smells (god component, prop drilling, `watch` for derived state, deep `reactive` over large data, fat composable, conditional rendering ladder, scattered state, missing Zod on Nitro endpoint, inline business logic in template, untyped props) and proposes independently-committable refactoring steps with Vitest gates between each.

This workflow is the stack-specific delegate of `task-code-refactor` for Vue.

## When to Use

- Vue code-smell identification and resolution
- Vue technical-debt reduction with a concrete plan
- Safe refactoring of a component / composable / page / Nitro endpoint / store
- Pre-merge "this PR grew the god-component / prop-drilling problem - what's the cleanup?"
- Migrating Options API to Composition API on a single component (when explicitly requested)

**Not for:**

- Deciding which debt to tackle first (use `task-debt-prioritize`)
- Feature changes (use `task-vue-implement`)
- Architecture-level restructuring across many modules (use `task-design-architecture`)
- Bug fixes (use `task-vue-debug`)

## Inputs

| Input                 | Required    | Description                                                                                                                                                                       |
| --------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Target scope          | Yes         | File, module, or route to refactor (e.g., `pages/dashboard.vue`, `components/orders/OrderList.vue`, `server/api/account.put.ts`, `stores/orders.ts`, `composables/useFilters.ts`) |
| Goal                  | Yes         | What the refactoring should achieve (e.g., extract `useOrderFilters` composable, replace `watch` with `computed`, split `Dashboard` god component, kill prop drilling)            |
| Test coverage status  | Recommended | Whether Vitest / VTU / Playwright coverage exists for the target area                                                                                                             |
| Shared/public surface | Recommended | Whether the target is used across feature / route / app boundaries                                                                                                                |

## Workflow

### Step 1 - Confirm Stack and Detect Framework

Use skill: `stack-detect` to confirm Vue. If invoked as a subagent of a Vue-aware parent, accept the pre-confirmed stack. If not Vue, stop and tell the user to invoke `/task-code-refactor` instead.

Detect framework: Nuxt 3 vs Vite + Vue Router. Record `Framework: ...`, `Vue: <version>` for the output.

### Step 2 - Read the Target

Read the actual file(s) named in the Inputs table before classifying smells. A refactor plan grounded in the user's prose summary instead of the source will hallucinate smells that aren't there and miss ones that are. Specifically:

1. Read the target component / composable / module top-to-bottom; note line count, composable usage, prop interface, conditional rendering depth, `ref` / `reactive` declarations, watcher declarations, external collaborators (`$fetch`, `useFetch`, Pinia store, `Sentry.captureException`, navigation calls)
2. Read the matching test file(s) (`*.test.ts`, Playwright `*.spec.ts`); count cases by outcome (happy path, error state, empty state, validation failure, auth denial, accessibility check)
3. If callers / parents are obvious (a page importing a feature component, a layout wrapping a page), read the immediate caller too - removing or reshaping props without seeing call sites is how silent breakage happens
4. For Nuxt Nitro endpoints, read any Nuxt page / form that posts to the endpoint to understand the contract on both sides

If the user named only the goal without a target file / module, ask for the target before proceeding. Do not guess.

**Sibling-smell disposition.** Real targets live inside fat modules. If the file containing the target also contains other smells (e.g., the user names `OrderList` but the same file has IDOR risk in `OrderActions` and `v-html` in `OrderDescription`), do **not** action them in this plan and do **not** ignore them silently. List under a `Sibling Smells (Out of Scope)` heading, briefly state why each is deferred (separate target, separate severity, separate skill - e.g., security findings belong in `task-vue-review-security`), and recommend follow-up invocations.

### Step 3 - Coverage Gate (mandatory)

Refactoring without test coverage is a rewrite with extra steps. Identify the tests covering the target (`*.test.ts`, integration tests, Playwright specs), then assign one of three statuses with sharp boundaries:

| Status       | Definition                                                                                                                                | What the workflow does                                                                                                                        |
| ------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `Adequate`   | Happy path **plus** at least 2 boundary outcomes per public entry point (e.g., empty state, error state, validation failure, auth denial) | Proceed to Step 4 normally                                                                                                                    |
| `Thin`       | Happy path **plus** exactly 1 boundary outcome                                                                                            | Proceed, but the plan **must** include a non-optional `Step 0 - Coverage prerequisite` adding the missing boundaries before any refactor step |
| `Inadequate` | No tests, or **happy-path-only** (success case alone)                                                                                     | **Refuse to produce Steps 1+.** The only output is the Coverage Gate verdict and a recommendation to run `task-vue-test` first                |

**Happy-path-only is `Inadequate`, not `Thin`.** A single success-case test cannot tell you whether the refactor preserves error handling, empty states, or accessibility - you would be flying blind.

**Internal-coupled tests count negatively.** Inspect each test's assertions for `wrapper.vm.<internal>`, render-count spies, or ref-name reads that the planned refactor will rename or remove (e.g., a test asserts on `filteredCount` and Step 6 deletes that ref). When this is true, the test will fail on the refactor for an **implementation reason** rather than catch a **behavior regression** - the inverse of what the gate is for. Surface this in the Coverage Gate as `internal-coupled: <test:line> asserts <ref-name> which Step <N> will remove` and require the test to be rewritten as DOM/event assertions in `Step 0 - Coverage prerequisite` before the renaming/extraction step runs. This rule applies even when overall coverage is `Adequate` - one tightly-coupled test against a soon-to-be-deleted internal still blocks the affected step.

**Output of this step:** explicit coverage status using one of the three labels. Do not proceed past Step 4 if status is `Inadequate`.

**Preview rules when Inadequate.** Step 4's smell catalog still runs to populate the Smells Identified and Sibling Smells (Out of Scope) preview - that is what the catalog is for. The refusal is on producing Steps 1+, not on diagnostic output. The preview helps the author scope the follow-up `task-vue-test` invocation.

**Bug-fix smuggled into a refactor request.** If the user's prose mixes "refactor X" with "and also fix that the filter does not persist on refresh," stop and surface the conflict: refactoring assumes behavior preservation, so a behavior change must either (a) be a separate PR ahead of the refactor, or (b) be explicitly labeled `coupled-fix` in Step 6 with its own test gate. Do not silently fold it into an extraction step.

### Step 4 - Identify Vue Smells

Inspect the target for these Vue-specific smells. Use judgment - these are signals, not hard rules.

**Component smells:**

| Smell                                   | Signal                                                                                                                                      | Risk   |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| God Component                           | Component file > 300 lines; mixes data fetching, state, business logic, multiple sub-rendering paths                                        | High   |
| Inline Business Logic in Template       | Calculations, branching > 3 levels, formatting inside `{{ }}` / `v-if` chains - extract to `computed` or sub-components                     | Medium |
| Conditional Rendering Ladder            | > 3 nested `v-if` / ternaries in the template; readability degrades fast                                                                    | Medium |
| Untyped Props                           | `defineProps(['x'])` (runtime-only) or `defineProps<{ x: any }>` - typed via `defineProps<{...}>` is the idiom; flag missing types or `any` | High   |
| Inline Event Handlers > 3 Lines         | Heavy logic inline in `@click="..."` - extract to a method                                                                                  | Low    |
| Scoped Slot Abuse                       | Render-prop / scoped slot for what could be a flat prop API                                                                                 | Low    |
| Anonymous Default Filename              | `Index.vue` deep inside a feature folder makes Vue DevTools show "Index" everywhere - rename or set `defineOptions({ name: '...' })`        | Low    |
| Mass-Imported Barrel                    | `import { X } from '@/components'` defeats tree-shake and pulls unrelated components into the bundle                                        | Medium |
| `<script setup>` Mixed With Options API | A single component using both - pick one; new code uses `<script setup>`                                                                    | Medium |

**Composable / hook smells:**

| Smell                                 | Signal                                                                                                                                 | Risk   |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| Fat Composable                        | Composable with 8+ params and 12+ return fields - extract or split                                                                     | High   |
| `watch` for Derived State             | `watch(a, () => state.x = a.value + b.value)` - use `computed`                                                                         | High   |
| `watch` for Event Handling            | `watch(clicked, () => { if (clicked) doThing() })` triggered by setting `clicked` in `@click` - just call `doThing()` from the handler | High   |
| Missing Watcher / Listener Cleanup    | Subscriptions / observers / intervals registered in `onMounted` without `onUnmounted` cleanup - memory leak                            | High   |
| `ref` for Derived Value               | State that is always computed from other state / props - eliminate; use `computed`                                                     | Medium |
| `ref` for Lifetime Constant           | `const config = ref({...})` initialized once and never set - move to a module-level constant or plain `const`                          | Low    |
| `reactive` for Primitive              | `reactive({ count: 0 })` - use `ref(0)` for primitives                                                                                 | Low    |
| Deep `reactive` Over Large Data       | `reactive(largeArray)` for a 5K-row dataset proxies every nested item - use `shallowRef` / `shallowReactive`                           | High   |
| Destructure / Spread Loses Reactivity | `const { a } = reactive({ a })` - `a` is now a plain value; use `toRefs` or props destructure (Vue 3.5+)                               | High   |
| `ref` for URL-Synced State            | Filters, page, sort kept in `ref` instead of route query - breaks deep-linking, breaks back-button, doesn't survive reload             | Medium |
| Composable Called Conditionally       | Composable called inside `if` or after early return - violates Composition API rules                                                   | High   |

**Data fetching smells:**

| Smell                                           | Signal                                                                                                                                               | Risk   |
| ----------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | ------ |
| `onMounted(() => $fetch(...))` for Initial Data | Pattern works but loses SSR, cache, dedup - prefer `useFetch` / `useAsyncData` (Nuxt) or TanStack Query (Vite)                                       | High   |
| Server-Fetchable Data Fetched on Client (Nuxt)  | Component does `onMounted(() => $fetch(...))` for data the parent could fetch via `useFetch` (which runs server-side during SSR) - request waterfall | High   |
| Sequential `await` for Independent Fetches      | `const a = await useFetch(...); const b = await useFetch(...);` instead of `Promise.all` - waterfall doubles SSR latency                             | Medium |
| Missing `key` for Cacheable `useFetch`          | `useFetch(url)` without a `key` synthesizes one from call site - fine for unique callsites, broken for parameterized fetches                         | Medium |
| Missing Cache Invalidation After Mutation       | A mutation succeeds but no `refreshNuxtData(key)` / `queryClient.invalidateQueries(...)` - UI shows stale data                                       | High   |

**State / configuration smells:**

| Smell                                           | Signal                                                                                        | Risk   |
| ----------------------------------------------- | --------------------------------------------------------------------------------------------- | ------ |
| Prop Drilling > 4 Layers                        | Same prop threaded through 4+ component layers - hoist to provide/inject, Pinia, or co-locate | Medium |
| `provide` Re-Renders Every Consumer             | Provided value rebuilt every render; split into stable + changing, or memoize                 | High   |
| Single-Consumer `provide`                       | `provide` for state read by exactly one component - remove and lift / pass directly           | Low    |
| Mutable Module-Level State                      | `let cache = {}` mutated by render or events - in SSR (Nuxt) it leaks across requests         | High   |
| `import.meta.env.X` Sprinkled Across Components | Should be `useRuntimeConfig()` / typed config module                                          | Medium |
| Pinia Mega-Store                                | One store for all app state - feature-scoped stores reduce blast radius                       | Medium |
| Plugin Sandwich at Root                         | > 5 nested `app.use(plugin)` calls at app entry; consolidate                                  | Low    |

**Nitro endpoint smells (Nuxt):**

| Smell                                 | Signal                                                                                                                           | Risk |
| ------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---- |
| Nitro Endpoint Without Zod            | `defineEventHandler` reading body without `readValidatedBody(event, Schema.parse)` - mass-assignment risk if data flows into ORM | High |
| Nitro Endpoint Without Auth           | Mutation endpoint without `requireUserSession(event)` (or session check) at the top                                              | High |
| Nitro Endpoint Returns Entire ORM Row | `prisma.user.findUnique({ where })` returned to client - serializes `passwordHash` / internal fields                             | High |
| `v-html` Without Sanitizer            | User-controlled HTML rendered raw - XSS                                                                                          | High |

**Accessibility smells:**

| Smell                                | Signal                                                                                                        | Risk   |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------- | ------ |
| `<input>` Without `<label>`          | Inputs without associated labels - screen readers miss them                                                   | High   |
| Custom Dialog Without Focus Trap     | Modal built from `<div>` without `role="dialog"`, focus trap, or keyboard close - keyboard / SR users blocked | High   |
| `<div @click>` Instead of `<button>` | Clickable `<div>` without `role="button"`, `tabindex`, key handling                                           | High   |
| Image Without `alt`                  | `<img>` / `<NuxtImg>` without `alt` (or `alt=""` for decorative)                                              | Medium |

**Test smells (when refactoring brings tests into scope):**

| Smell                             | Signal                                                                                                | Risk   |
| --------------------------------- | ----------------------------------------------------------------------------------------------------- | ------ |
| `getByTestId` Everywhere          | Tests rely on `data-testid` instead of user-centric queries                                           | Medium |
| Asserting `wrapper.vm.<internal>` | Tests on internal component state - couples to implementation; break on every refactor                | High   |
| `fireEvent` Without Reason        | Skips focus / key events real users trigger (when Testing Library Vue is the helper)                  | Medium |
| Snapshot Tests on Visual Layout   | Churns on every styling change; no signal                                                             | Medium |
| Render Counts Asserted            | `expect(spy).toHaveBeenCalledTimes(2)` for render counts - tests implementation; rewrite for behavior | High   |

**General smells (apply with TypeScript / Vue judgment):**

Use skill: `complexity-review` when the target shows over-engineering signals (single-impl render-prop, generic abstractions for one consumer, premature compound components) - those are simplification opportunities, not refactor steps to extract more abstractions.

Apply Vue judgment - a 250-line component that orchestrates clearly named sub-components is fine; a 100-line component doing three unrelated things is not.

### Step 5 - Cross-Module Risk Assessment

Use skill: `review-blast-radius` to estimate how many callers, tests, and routes are affected.

Vue-specific blast-radius signals:

- [ ] **Public design-system component**: target is a primitive in a shared component library used across many features
- [ ] **Top-level layout / plugin**: refactoring `app.vue`, root layout, or a global plugin / Nuxt module affects every page
- [ ] **Composable used widely**: target composable is imported by > 10 components; signature changes cascade
- [ ] **Route segment used in many places**: refactoring a Nuxt layout affects every page using it
- [ ] **Component prop interface**: prop rename / removal cascades into every parent that renders the component
- [ ] **Nitro endpoint consumed by multiple forms / pages**: refactoring breaks every caller
- [ ] **Pinia store used cross-feature**: refactoring affects every feature that reads / mutates it

State the blast radius before proposing steps: **Narrow** (single file, single caller) / **Moderate** (single feature, multiple callers) / **Wide** (cross-feature, public component, root layout) / **Critical** (design-system primitive, root plugin, shared store).

### Step 6 - Propose the Step Sequence

Each refactoring step must be:

1. **Independently committable** - the codebase compiles with `tsc --noEmit` / `vue-tsc --noEmit` cleanly and the test suite passes after each step
2. **Behaviorally invariant** - no behavior change unless explicitly noted as a separate step (or labeled `coupled-fix`)
3. **Reversible** - rollback is one revert away
4. **Tested** - the existing Vitest / Playwright suite continues to pass; new tests added when extracting new units

**Recipe interleaving.** When more than one Common Recipe applies to a single target, do **not** concatenate the recipes - that produces a 25-step plan. Identify the **primary** refactor (usually the one named in the user's goal), use that recipe as the spine, and fold supporting recipes in as additive sub-steps where dependencies require it. State the primary recipe explicitly via the `Primary recipe:` field. If the spine grows past ~8 steps, split into two plans / two PRs.

**Coupled-fix language.** Sometimes a refactor genuinely depends on a behavior change (e.g., extracting a Nitro endpoint that derives `ownerId` from the session _requires_ a session check be added to the endpoint, which changes the failure mode for unauthenticated callers). Label such steps `coupled-fix` with their own test gate and rationale. This is **not** a bundling violation - it is an explicit prerequisite. Do not silently fold it into an extraction step.

**SSR-boundary watch (Nuxt).** When converting between SSR-rendered and client-only rendering, state which boundary the result lives on. Wrapping with `<ClientOnly>` or guarding with `import.meta.client` changes when the code runs - audit imports for browser-only modules that must move out of `<script setup>` body, and audit data flow for SSR payload changes.

**Reactivity-boundary watch.** When converting `reactive` ↔ `ref` ↔ `shallowRef`, callers may break. `ref` access goes through `.value` (in JS, not template); `reactive` does not. Destructuring a `reactive` loses reactivity, destructuring `toRefs(reactive)` does not. State the conversion explicitly per step.

**Common Vue refactor recipes:**

**Recipe: Replace `watch` for derived state with `computed`**

1. Identify the watcher: `watch([a, b], () => { state.sum = a.value + b.value })` (or similar)
2. Replace with: `const sum = computed(() => a.value + b.value)`; delete the `state.sum` ref and the watcher
3. Update template / consumers from `state.sum` to `sum.value` (or just `sum` in template)
4. Run tests; assert observable behavior unchanged (the prior version had a transient render with stale `sum` between change and watcher run; now `sum` is always consistent)
5. Audit other components for the same pattern

**Recipe: Replace `onMounted(() => $fetch(...))` with `useFetch` (Nuxt) or TanStack Query (Vite)**

1. **If on Nuxt and the parent could fetch via `useFetch`** (which runs server-side during SSR + reuses on hydration): replace `onMounted` + `ref` + manual loading state with `const { data, pending, error } = await useFetch(url, { key, transform })`. Pass through to template directly; remove the `onMounted`, the ref, the loading flag
2. **Else** (Vite, or genuinely client-only fetch): replace with `useQuery({ queryKey, queryFn })` (TanStack Query Vue); handle `isLoading` / `error` from the hook return
3. Add cache invalidation on relevant mutations: `refreshNuxtData(key)` / `queryClient.invalidateQueries(...)`
4. Run tests; add tests for empty / error / loading states (boundary outcomes the `onMounted` version probably didn't cover)

**Recipe: Replace deep `reactive` over large dataset with `shallowRef`**

1. Identify the `reactive` declaration over a large array / API response: `const orders = reactive([])` filled with 5K rows
2. Replace with `const orders = shallowRef<Order[]>([])`; mutations via `orders.value = [...orders.value, newRow]` (immutable update) or `orders.value = nextOrders` (replace)
3. Update template usage - templates auto-unwrap refs at top level; nested `.value` access in `<script setup>` JS code now required
4. Run tests; verify list rendering still works; profile if available (deep reactive overhead should drop noticeably for large datasets)

**Recipe: Move filter / pagination / sort state to URL query (Nuxt + Vue Router)**

This is a behavior-aware refactor: moving filter state to the URL means refresh, deep links, and back-button now preserve filter state. That is a UX contract change. Treat it as `coupled-fix` Step 1 in the plan and tell the user explicitly so the change is not surprising.

1. Define the URL contract: which params, types, defaults (e.g., `status: 'open' | 'closed' | 'all' = 'all'`, `page: number = 1`, `q: string = ''`). Validate via Zod / a small parser; reject malformed values to defaults rather than crashing on bad input
2. Replace each `ref` filter with a read from `useRoute().query` via `computed`
3. Replace each setter with `useRouter().push({ query: { ...currentQuery, status: 'closed' } })`; for filters that should not pollute history, use `router.replace`
4. Update the data fetcher: `useFetch` / `useQuery` keys now derive from route query; the URL is the source of truth
5. Run tests: deep-linking renders filtered list immediately, back-button restores prior filter, refresh preserves filter, validation fallback for malformed params
6. (Coupled-fix) Note that this changes back-button behavior - document in PR description

**Recipe: Extract composable from fat component**

1. Identify the cohesive state + watcher + handler trio inside the component (e.g., filter state + URL sync watcher + setter handlers)
2. Create `useXxx.ts` with the same shape; copy logic; write a composable test (`withSetup` + boundary cases - state transitions, watcher cleanup, edge cases)
3. Replace the inlined logic in the component with `const filterApi = useFilters(...)`; component still does the original work via the composable
4. Verify component tests pass unchanged
5. Audit other components for the same pattern - opportunity to reuse the composable (do not bundle this audit; surface it as a follow-up)

**Recipe: Untangle prop drilling**

1. Identify the prop chain (which prop, which layers it passes through)
2. Decide on the right primitive: (a) **co-locate state** with the consumer (move the `ref` to the leaf if no other consumer needs it), (b) **provide / inject** for cross-cutting state local to a subtree (theme, modal context), (c) **Pinia store** for app-state shared by multiple features. Choosing the primitive is the first decision; not every prop drill is a Pinia candidate
3. Implement: extract the state into the chosen primitive; remove the prop from intermediate layers; consumers read directly via `inject` / store
4. Verify intermediate layers are simpler (fewer props); run tests
5. If using `provide`, ensure value is stable (`computed` returning the right shape, or `readonly(reactive({ ... }))`) so consumers don't re-render unnecessarily

**Recipe: Split god component into focused components**

1. Identify the orthogonal concerns inside the component (e.g., `Dashboard.vue` doing filters + list + summary + actions panel)
2. Extract one concern at a time into a new component file with explicit `defineProps<{...}>` interface; original god component renders the new one via `<Filters />` etc.
3. Update tests if the new component has its own test surface
4. Repeat until the god component is a thin layout coordinator
5. Verify route-level tests / Playwright E2E still pass

**Recipe: Add Zod validation to Nitro endpoint**

1. Define a Zod schema for the endpoint's input
2. Replace `const body = await readBody(event)` with `const body = await readValidatedBody(event, Schema.parse)` (throws on invalid - `createError({ statusCode: 400, ... })` for typed error response). Use `getValidatedQuery(event, Schema.parse)` for query params and `getValidatedRouterParams(event, Schema.parse)` for path params
3. Audit the endpoint for any `body.<field>` references that were previously untyped
4. Add a test: invalid input rejected with the expected error shape; valid input proceeds
5. Audit other endpoints in the file for the same gap - surface as follow-up if not in this plan's scope

**Recipe: Stabilize `provide` value to prevent re-render storm**

1. Identify the provider: `provide('myKey', { a, b, fn })`
2. Memoize the value: `const value = computed(() => ({ a: a.value, b: b.value, fn }))`; use referentially stable function (declare `fn` once, hoisted out of `<script setup>` if pure)
3. **Or split** into two provides: state and actions - actions are referentially stable, state changes per mutation; consumers inject only what they need
4. Run tests; profile if available (re-render counts in Vue DevTools should drop)

**Recipe: Replace mutable module-level state**

1. Identify the mutable state (`let cache = {}`, `const handlers = []`)
2. Move into a Pinia store, a composable + `provide`, or per-component state if appropriate. For SSR (Nuxt), this is mandatory - module-level state leaks across requests
3. Update consumers to read via the new primitive
4. Run tests; assert cross-test isolation (Vitest test order should not matter)

**Recipe: Project Pinia / `useState` payload to DTO (Nuxt SSR leak)**

1. Identify the data placed in store / state during SSR: `const userStore = useUserStore(); userStore.user = await prisma.user.findUnique({ where })` - the entire row serializes into `__NUXT__` payload
2. Project at the data-fetch layer: `prisma.user.findUnique({ where, select: { id: true, email: true, name: true } })` (Prisma `select` whitelist) or define a DTO type and a mapper function
3. Update store / state shape to match the DTO; update consumers to read only the projected fields (TypeScript will surface any caller still reading `passwordHash`)
4. Run tests; verify SSR payload (`view-source` on a rendered page) no longer contains the leaked fields

**Recipe: Add accessibility for custom interactive component**

1. Identify the violation (e.g., `<div @click>` for a button)
2. Replace with the right semantic element (`<button>`, `<a>`, `<input>`) or add proper ARIA + key handlers (`role`, `tabindex`, `@keydown` dispatching click on Enter / Space)
3. Add label / `aria-label` / `aria-describedby` as needed
4. Run `vitest-axe` test asserting no violations

### Step 7 - Validate Plan Against Goal

Before finalizing the plan, check:

- [ ] Goal is achieved at the end of the sequence
- [ ] Each step is small enough to review in < 30 minutes
- [ ] Test coverage runs between every step (not just at the end)
- [ ] Steps ordered low-risk first (extracts, additions) before high-risk (deletions, prop removals, reactivity-conversion)
- [ ] Rollback path is one revert per step
- [ ] No step bundles "while we're here" unrelated cleanup

## Output Format

```markdown
## Vue Refactor Plan

**Target:** [file:line or path]
**Goal:** [what this refactor achieves]
**Primary recipe:** [name from "Common Vue refactor recipes" - this is the spine]
**Stack:** Vue <version> / TypeScript <version>
**Framework:** Nuxt 3 <version> | Vite + Vue Router <version>

## Coverage Gate

**Status:** Adequate | Thin | Inadequate

[If Adequate: one sentence on the boundary cases that exist.]
[If Thin: list the missing boundary tests; Step 0 below covers them.]
[If Inadequate: state what coverage must exist before refactor begins, and recommend running `task-vue-test` first. **Stop the workflow here** - omit Blast Radius, Step Sequence, and Verification. You may still produce **Smells Identified** and **Sibling Smells (Out of Scope)** as a *preview*; mark them clearly as preview-only.]

**Coverage prerequisite list shape (when status is `Thin` or `Inadequate`).** List required tests as one row per public entry point with this shape: `entry-point | outcome | recommended layer`. Outcomes cover at minimum: validation failure / invalid input, error state, empty state, loading state, accessibility (when interactive). Layer options: component test (VTU/TLV + `user-event`), composable test (`withSetup` or probe component), Nitro endpoint test (`@nuxt/test-utils` `$fetch`), Playwright E2E. Example: `OrderList | empty-state visible when 0 orders | component test`.

## Smells Identified

| Smell        | Location  | Risk | Notes                                  |
| ------------ | --------- | ---- | -------------------------------------- |
| [Smell name] | file:line | High | [Why this is the smell - one sentence] |

## Sibling Smells (Out of Scope)

_Other smells in the same file/module that this plan does NOT address. Listed for hand-off, not action._

| Smell   | Location  | Why deferred                                                                                | Recommended follow-up                                                           |
| ------- | --------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| [Smell] | file:line | [separate target / separate severity / belongs to security review / belongs to perf review] | [`task-vue-review-security` / `task-vue-refactor` on a different target / etc.] |

_Omit this section if the target file has no other smells._

## Blast Radius

[Narrow | Moderate | Wide | Critical] - [one-paragraph rationale citing callers, tests, public surface]

## Step Sequence

### Step 0 - Coverage prerequisite _(skip if Coverage Gate is Adequate)_

- **Change:** add the missing boundary tests identified in the Coverage Gate
- **Risk:** Low (tests-only change)
- **Test gate:** new tests pass; existing suite still green
- **Rollback:** revert added test files

### Step 1 - [Action verb + noun]

- **Change:** [what is added / extracted / moved]
- **Risk:** [Low | Medium | High]
- **Step kind:** [refactor | coupled-fix]
- **Test gate:** [which tests must pass after this step - component / composable / E2E / Nitro endpoint]
- **SSR stance:** [server-rendered | client-only | unchanged | converting] _(Nuxt only)_
- **Reactivity stance:** [`ref` | `reactive` | `shallowRef` | `shallowReactive` | unchanged | converting from X to Y]
- **Rollback:** [how to revert in one git revert]

### Step 2 - [Action verb + noun]

[Same structure. Use `Step kind: coupled-fix` for any step that intentionally changes behavior because the refactor depends on it. Always state why the coupling is structural.]

[... continue numbering ...]

## Verification

- [ ] Goal achieved at end of sequence: [restate goal]
- [ ] Each step independently committable
- [ ] `vue-tsc --noEmit` clean and Vitest suite passes between every step
- [ ] No bundled unrelated cleanup
- [ ] Rollback path is one revert per step
- [ ] No silent SSR ↔ client boundary changes; descendants audited (Nuxt)
- [ ] No silent `reactive` ↔ `ref` conversions; consumers audited

## Out of Scope

[Adjacent improvements explicitly NOT in this plan - e.g., "renaming `OrderList` to `OrdersTable` is a follow-up; this plan only extracts behavior, not renames"]
```

## Self-Check

**Plan-time checks (verifiable now from the plan itself):**

- [ ] Stack confirmed as Vue (or accepted from parent dispatcher); framework recorded (Step 1)
- [ ] Target file(s) and matching tests read directly before smell classification - no smells inferred from prose alone (Step 2)
- [ ] Sibling smells in the target file listed under `Sibling Smells (Out of Scope)` with deferral rationale, or section omitted because none exist (Step 2)
- [ ] Coverage gate evaluated using the sharp boundaries (`Adequate` / `Thin` / `Inadequate`); plan refused if `Inadequate`; happy-path-only treated as `Inadequate` not `Thin` (Step 3)
- [ ] Internal-coupled tests audited: each test's assertions checked against the refs/internals the refactor will remove or rename; matches surfaced as `internal-coupled` and pinned to a `Step 0` rewrite (Step 3)
- [ ] When refusal triggered (Inadequate), Step 4 catalog still ran to produce the Smells preview; not skipped (Step 3)
- [ ] Bug-fix smuggled into a refactor request was surfaced and split into a separate PR or labeled `coupled-fix` - never silently folded (Step 3)
- [ ] Vue-specific smells identified using Step 4 catalog (component, composable, data fetching, state, Nitro endpoint, accessibility, test) (Step 4)
- [ ] Cross-module risk (blast radius) stated before proposing steps (Step 5)
- [ ] `Primary recipe:` named in the output; supporting recipes folded as sub-steps, not concatenated (Step 6)
- [ ] Step 0 included if Coverage Gate is `Thin`; omitted if `Adequate` (Output Format)
- [ ] SSR stance (Nuxt only) stated per step; reactivity stance stated per step (no silent conversions) (Step 6)
- [ ] `Step kind:` set to `coupled-fix` for any step that intentionally changes behavior because the refactor depends on it; rationale stated; otherwise `refactor` (Step 6)
- [ ] Steps ordered low-risk first (additions, extractions) before high-risk (deletions, conversions, prop removals) (Step 6)
- [ ] Plan length ≤ ~8 steps, or split into multiple PRs explicitly (Step 6)
- [ ] No step bundles unrelated cleanup (Step 6)
- [ ] Goal explicitly mapped to the end state of the sequence (Step 7)

**Execution-time gates (commitments the plan makes for the implementer):**

- [ ] `vue-tsc --noEmit` clean and Vitest suite passes between every step
- [ ] Each step independently committable
- [ ] Rollback path is one revert per step

## Avoid

- Proposing a refactor without a test-coverage gate - that's a rewrite, not a refactor
- Bundling behavior changes with refactoring steps - keep them separate, label clearly
- Making "while we're here" unrelated cleanups - they belong in their own PR
- Renaming during a refactor (rename PRs are separate; mixing the two doubles the review surface)
- Removing a `watch` without verifying the surrounding logic preserves the original observable behavior - some watchers compensate for genuinely external state and removal regresses
- Converting `reactive` to `ref` (or vice versa) without auditing every consumer - destructure / spread patterns break silently
- Converting deep `reactive` to `shallowRef` without auditing mutation sites - in-place mutation (`obj.field = x`) doesn't trigger reactivity on shallow refs; full assignment (`ref.value = next`) does
- Wrapping a component in `<ClientOnly>` to silence a hydration error - that masks the underlying SSR mismatch; fix the cause
- Replacing `onMounted(() => fetch(...))` with `useFetch` when the component is genuinely client-only and depends on browser-only APIs - the recipe doesn't apply here
- Replacing prop drilling with `provide` as a default - co-located state is often the right answer; `provide` for cross-cutting state local to a subtree, Pinia for app-shared
- Replacing `provide` with Pinia without checking that the additional dep is justified - sometimes a stable provide is enough
- Refactoring a design-system primitive without a backward-compatibility plan - that is a public API
- Replacing `getByTestId` queries with `getByRole` queries during a refactor - that is a test improvement, deserves its own PR
