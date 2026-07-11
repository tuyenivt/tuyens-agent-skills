---
name: task-vue-debug
description: Debug Vue 3.5 / Nuxt 3 / Vite - reactivity, hydration mismatches, template/compile errors, Nuxt auto-imports, stale data, build failures.
agent: vue-tech-lead
metadata:
  category: frontend
  tags: [vue, debug, reactivity, hydration, nuxt, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug - Vue Debugging Workflow

## When to Use

- Vue/Nuxt error, warning, or compile/build failure
- Reactivity issue (ref not updating, watch not firing, computed stale, destructured prop frozen)
- Hydration mismatch in Nuxt / SSR
- Test failure tied to Vue (async render, composable-outside-setup)
- "No error, wrong result" - data missing, stale, or unequal across renders

Not for: production incident triage (`/task-oncall-start`), perf tuning (`task-vue-review-perf`), new feature work (`task-vue-implement`).

## Workflow

### STEP 1 - BEHAVIORAL PRINCIPLES

Use skill: `behavioral-principles`. These rules govern every step below.

### STEP 2 - STACK DETECT

Use skill: `stack-detect`. Confirm Vue major (3.4 / 3.5+), Nuxt vs Vite, state layer (Pinia, `useState`), data layer (`useFetch`/`useAsyncData`, TanStack Query). Output drives which atomic skill loads in STEP 4.

### STEP 3 - INTAKE

Accept one of: error message, console output, build/test failure, "wrong result, no error" report. For partial input, ask once for the missing piece:

- Error path: exact console text, file:line, repro steps, dev vs prod
- No-error path: expected vs observed value, which boundary it crosses (SSR payload -> client store, `useFetch` cache, prop -> child, watcher source, server module scope), frequency (every nav / intermittent / under load)

### STEP 4 - CLASSIFY

Match one row; load the listed skill. Stop at the first match. If no row matches, do not force the nearest one - name the layer from the evidence, load that layer's skill (Component -> `vue-component-patterns`, Composable -> `vue-composables-patterns`, State -> `vue-state-patterns`, Data Fetching -> `vue-data-fetching`, Routing -> `vue-routing-patterns`, Nuxt/SSR -> `vue-nuxt-patterns`), and report Classification as `Off-table`.

**Reactivity**

| Symptom | Cause | Skill |
|---|---|---|
| Destructured prop never updates | Pre-3.5 destructure loses reactivity; use `toRefs(props)` / `() => props.x` | `vue-component-patterns` |
| Destructured Pinia field frozen | Missing `storeToRefs(useFooStore())` | `vue-state-patterns` |
| `computed` stale | Non-reactive dependency, or read inside non-reactive context | `vue-composables-patterns` |
| `watch` never fires | `watch(state.x, fn)` passes a value; rewrite as `watch(() => state.x, fn)` | `vue-composables-patterns` |
| `reactive()` reassignment does nothing | `state = next` swaps local; mutate with `Object.assign(state, next)` or use `ref` | `vue-composables-patterns` |
| `shallowRef` field write ignored | Only whole-value assignment triggers; do `r.value = { ...r.value, x }` | `vue-composables-patterns` |
| "Maximum recursive updates exceeded" | Watcher/computed mutates its own source | `vue-composables-patterns` |

**Hydration** (server/client HTML differs)

| Symptom | Cause | Skill |
|---|---|---|
| "Hydration text content mismatch" | Dynamic value (`Date.now()`, `Math.random`, `window`) in render | `vue-nuxt-patterns` |
| "Hydration node mismatch" | Conditional render gated by browser-only API | `vue-component-patterns` |
| `useState` collision across components | Same key in different files maps to one slot; namespace keys | `vue-nuxt-patterns` |
| SSR payload field undefined on client | Store/`useState` shape diverged from API; project to typed DTO at fetch layer | `vue-data-fetching` |

**Template / compile**

| Symptom | Cause | Skill |
|---|---|---|
| "Component is already defined" | Auto-import + manual import collision | `vue-nuxt-patterns` |
| "Property X was accessed during render" | Undefined reactive property | `vue-composables-patterns` |
| "Invalid prop: type check failed" | Wrong prop type passed | `vue-component-patterns` |
| `defineModel` updates don't propagate | Child mixes `defineProps` + `defineEmits` half-implemented | `vue-component-patterns` |

**Nuxt / routing**

| Symptom | Cause | Skill |
|---|---|---|
| "500 [nuxt] unhandled error" | Server route / middleware throws | `vue-nuxt-patterns` |
| Auto-import unresolved | File outside `components/`, `composables/`, `utils/` | `vue-nuxt-patterns` |
| Middleware redirect loop | Unconditional redirect | `vue-routing-patterns` |
| `readBody` accepts unknown fields | Replace with `readValidatedBody(event, Schema.parse)` | `vue-data-fetching` |
| One user briefly sees another user's data (intermittent, SSR/prod) | Module-scope variable in a composable is shared across server requests; move to `useState` or Pinia | `vue-state-patterns` |

**Stale data / wrong result, no error** - bug lives at a data boundary

| Symptom | Cause | Skill |
|---|---|---|
| `useFetch` returns first-call data forever | Unstable or missing `key` (esp. `JSON.stringify` key) | `vue-data-fetching` |
| `useFetch` `transform` returns stale shape | `transform` mutates input; must be pure and return a new object | `vue-data-fetching` |
| Pinia mutation invisible in template | Destructured store without `storeToRefs` | `vue-state-patterns` |

**Build / type / test**

| Symptom | Cause | Skill |
|---|---|---|
| TS / Vite build error | First error in output; later ones cascade. Common: `.vue` path alias missing, CJS/ESM interop | - |
| Type X not assignable to Y on prop/emit | Prop/emit type contract mismatch | `vue-component-patterns` |
| `wrapper.find()` empty / "Cannot access X before initialization" | Async render not awaited (`flushPromises`) or composable called outside `setup` | `vue-testing-patterns` |
| Performance / slow render / leak | Render or memory hotspot | `frontend-performance` |

### STEP 5 - LOCATE

Open the failing file plus ~50 lines of context. Trace upstream: page -> layout -> parent -> failing component, OR fetch -> SSR payload -> store -> template. Name the layer: Component | Composable | State | Data Fetching | Routing | Build.

For stale-data: instrument each boundary the value crosses (server fetch result, hydration payload, store after mutation, prop into child) with `console.log` or a `watchEffect` logger. Compare expected vs observed shape.

### STEP 6 - ROOT CAUSE

Explain **why**, citing `file:line`. State confidence:

- **HIGH** - reproduced or evidence is direct
- **MEDIUM** - strong pattern match, alternative causes exist
- **LOW** - need more info; list what

### STEP 7 - FIX

Before/after diff, smallest change that resolves the root cause. Rank alternatives by (1) correctness, (2) change surface, (3) alignment with existing patterns.

### STEP 8 - PREVENT

One guard:

- Test that exercises the exact path (Vitest + `@vue/test-utils` for component/composable; Playwright for hydration / SSR round-trip)
- Lint rule re-enabled if it was disabled (`vue/no-mutating-props`, `vue/no-setup-props-destructure`)
- `grep` for the same anti-pattern elsewhere; list occurrences

Skip if fix is trivial (typo, missing import).

## Output Format

```
## Classification
[Reactivity | Hydration | Template | Nuxt | Stale data | Build | Test | Off-table]: [specific row, or evidence-based layer if Off-table]
Layer: [Component | Composable | State | Data Fetching | Routing | Build]

## Root Cause (confidence: HIGH | MEDIUM | LOW)
[Why, citing file:line]

## Fix
[Before/after diff]

## Prevention
[Test, lint, or grep result - omit if trivial]
```

If confidence is LOW, add `## Needs Clarification` listing the missing input.

## Self-Check

- [ ] STEP 1: behavioral-principles loaded
- [ ] STEP 2: stack-detect loaded; Vue major, Nuxt vs Vite, state and data layers identified
- [ ] STEP 3: full error or wrong-result spec captured; one clarifying question max if partial
- [ ] STEP 4: classified into one row (or explicit Off-table fallback) before reading code; correct atomic skill loaded
- [ ] STEP 5: failing file located; layer named; for stale-data, boundaries instrumented
- [ ] STEP 6: root cause cites file:line; confidence stated
- [ ] STEP 7: before/after fix is minimal and targets root cause
- [ ] STEP 8: prevention guard added, or skipped with reason

## Avoid

- Reading code before classifying.
- Generic advice without naming the boundary.
- Fixing a symptom (`key: Math.random()` to force refetch) instead of the missing stable key.
- `<ClientOnly>` / `any` / `eslint-disable` to silence a hydration mismatch.
- Switching to Options API to dodge a Composition API bug.
