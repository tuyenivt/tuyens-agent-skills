---
name: task-vue-debug
description: Debug Vue errors - reactivity gotchas, template compilation, hydration mismatches, Nuxt-specific issues, build failures, and runtime errors for Vue 3.5+ / Nuxt 3 / Vite projects.
metadata:
  category: frontend
  tags: [vue, debug, reactivity, hydration, nuxt, error, troubleshooting]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Debug - Vue Debugging Workflow

## When to Use

- Vue error or warning you need help understanding
- Reactivity not working as expected (ref not updating, watch not firing, computed stale)
- Hydration mismatch in Nuxt or SSR setup
- Template compilation error or runtime template warning
- Nuxt-specific errors (auto-import failures, server route issues, middleware errors)
- Build or TypeScript compilation error
- Test failure you can't figure out
- Behavior that doesn't match expectations (no error, but wrong result)

**Not for**: Production incident response with containment and blast radius assessment - use `/task-oncall-start` instead.

**Approach**: Classify before fixing. Understand the error, trace through the codebase, explain why (not just what), and apply the smallest correct change aligned with project patterns.

**Edge cases**:

- **Vague description, no error message**: Ask for the exact console output, the component where it occurs, and steps to reproduce before classifying.
- **Multiple errors**: Identify the root error (usually the first in the console) and focus on that. Mention secondary errors only if they are independent.
- **No source code available**: If the error points to framework internals only, explain the framework behavior and ask the user for the application code that triggered it.
- **Intermittent/non-deterministic bug**: Note that the issue may be race-condition or timing-related; ask for reproduction steps and whether it occurs in development, production, or both.

## Inputs

| Input                           | Required | Description                             |
| ------------------------------- | -------- | --------------------------------------- |
| Error message or console output | Yes      | The primary failure signal              |
| Relevant source file            | No       | Component or composable where it occurs |
| Steps to reproduce              | No       | What triggers the error                 |
| Expected vs actual behavior     | No       | For logic bugs without exceptions       |
| Browser / Node version          | No       | For environment-specific issues         |

## Rules

- Always classify the error before reading code
- Show the exact code change needed - no vague suggestions
- Explain WHY the error happened, not just how to fix it
- Prefer minimal fixes over refactors - fix the bug, don't redesign
- If confidence is LOW, say so and state what additional info would help
- Do not suggest unrelated improvements or style changes
- Reference atomic skills only when the fix involves a pattern they cover

## Workflow

STEP 1 - INTAKE: Accept one or more of: Vue warning/error message, Nuxt build/runtime error, browser console output, TypeScript compilation error, test failure output, or description of unexpected behavior. If the input is ambiguous, ask one clarifying question before proceeding.

STEP 2 - CLASSIFY: Identify the error category to guide investigation:

**Reactivity error** -> Unexpected behavior with refs, reactive, computed, or watchers:

| Error Pattern                       | Likely Cause                                 | Load Skill                            |
| ----------------------------------- | -------------------------------------------- | ------------------------------------- |
| Prop not reactive after destructure | Destructured props lose reactivity (pre-3.5) | Use skill: `vue-component-patterns`   |
| Computed not updating               | Non-reactive dependency in computed          | Use skill: `vue-composables-patterns` |
| Watch not firing                    | Watching wrong ref level (.value vs ref)     | Use skill: `vue-composables-patterns` |
| `reactive()` losing reactivity      | Reassignment instead of property mutation    | Use skill: `vue-composables-patterns` |

**Hydration error** -> Server/client HTML mismatch:

| Error Pattern                                 | Likely Cause                         | Load Skill                          |
| --------------------------------------------- | ------------------------------------ | ----------------------------------- |
| "Hydration node mismatch"                     | Server/client render difference      | Use skill: `vue-nuxt-patterns`      |
| "Hydration text content mismatch"             | Dynamic value (date, random, window) | Use skill: `vue-nuxt-patterns`      |
| "Hydration completed but contains mismatches" | Conditional render using browser API | Use skill: `vue-component-patterns` |

**Template error** -> Compilation or runtime template issue:

| Error Pattern                           | Likely Cause                                 | Load Skill                            |
| --------------------------------------- | -------------------------------------------- | ------------------------------------- |
| "Component is already defined"          | Name collision (auto-import + manual import) | Use skill: `vue-nuxt-patterns`        |
| "Property X was accessed during render" | Accessing undefined reactive property        | Use skill: `vue-composables-patterns` |
| "Invalid prop: type check failed"       | Wrong prop type passed                       | Use skill: `vue-component-patterns`   |

**Nuxt-specific error** -> Auto-imports, server routes, middleware:

| Error Pattern                  | Likely Cause                         | Load Skill                        |
| ------------------------------ | ------------------------------------ | --------------------------------- |
| "500 - [nuxt] unhandled error" | Server route or middleware failure   | Use skill: `vue-nuxt-patterns`    |
| Auto-import not resolving      | File not in expected directory       | Use skill: `vue-nuxt-patterns`    |
| Middleware redirect loop       | Unconditional redirect in middleware | Use skill: `vue-routing-patterns` |

**Build / TypeScript error** -> compilation or bundling issue:

| Error Pattern                          | Likely Cause                           | Load Skill                          |
| -------------------------------------- | -------------------------------------- | ----------------------------------- |
| "Cannot find module" in .vue file      | Missing type declaration or path alias | -                                   |
| "Type X is not assignable to type Y"   | Props/emits type mismatch              | Use skill: `vue-component-patterns` |
| Vite build fails with "default export" | CJS/ESM module interop issue           | -                                   |

**Runtime error** -> JavaScript exception during render or event handling:

| Error Pattern                         | Likely Cause                        | Load Skill                            |
| ------------------------------------- | ----------------------------------- | ------------------------------------- |
| "Cannot read properties of undefined" | Accessing ref before data loads     | Use skill: `vue-data-fetching`        |
| "Maximum recursive updates exceeded"  | Infinite watch/computed cycle       | Use skill: `vue-composables-patterns` |
| "Failed to resolve component"         | Missing registration or auto-import | Use skill: `vue-nuxt-patterns`        |

**Test failure** -> assertion mismatch, async timing, mock setup:

| Error Pattern                           | Likely Cause                             | Load Skill                        |
| --------------------------------------- | ---------------------------------------- | --------------------------------- |
| "wrapper.find() returned empty"         | Async render not awaited (flushPromises) | Use skill: `vue-testing-patterns` |
| "Cannot access X before initialization" | Composable called outside setup context  | Use skill: `vue-testing-patterns` |
| Snapshot mismatch after upgrade         | Component output changed                 | Use skill: `vue-testing-patterns` |

**Performance issue** -> slow renders, memory leak, bundle size -> Use skill: `frontend-performance`

**No-error / wrong-behavior intake.** When the user reports "no exception, but the value is wrong / missing / stale," the bug almost always lives at a boundary where data crosses a reactivity, hydration, or serialization seam. There is no stack trace to follow - work the seams. Vue-flavored surfaces:

| Surface                                       | Symptom                                                                                                | Diagnostic                                                                                                                         |
| --------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------- |
| Pinia destructure without `storeToRefs`       | Component renders the initial value forever; mutations to the store do nothing in the template          | Grep for `const { x } = useFooStore()` in the failing component; replace with `const { x } = storeToRefs(useFooStore())`           |
| `useFetch` without stable `key`               | Same callsite called with different args returns the cached first call's data                          | Confirm the call has `{ key }` derived from the actual variant; flag dynamic keys built via `JSON.stringify` (cache miss every time) |
| Nitro `readBody` without Zod                  | Extra fields silently flow into ORM (or get silently dropped); no error, just wrong stored shape       | Replace `await readBody(event)` with `await readValidatedBody(event, Schema.parse)`; round-trip-test the endpoint                  |
| Reactive `props` destructure pre-Vue-3.5      | Child receives a snapshot at mount, never updates when parent changes the prop                          | Confirm Vue version; if < 3.5, use `toRefs(props)` or `computed(() => props.x)` instead of bare destructure                        |
| `shallowRef` mutation via property write      | `obj.value.field = x` runs but template doesn't update; only `obj.value = next` triggers reactivity   | Audit mutation sites; assign whole-value (`shallow.value = { ...shallow.value, field: x }`) or convert to `ref`                    |
| `watch` source mismatch                       | Watcher never fires (or fires only once at registration with wrong value)                              | `watch(state.x, fn)` passes the current value, not a getter; rewrite as `watch(() => state.x, fn)`                                 |
| `reactive` reassignment                       | `state = { ...next }` swaps the local but the original proxy consumers held is unchanged              | Mutate keys (`Object.assign(state, next)`) or convert to `ref` and assign `.value`                                                  |
| SSR payload field drift                       | Pinia store / `useState` shape diverged from the API response; client reads as undefined silently      | Compare hydration payload (`view-source` for `__NUXT__`) against store schema; project to a typed DTO at the data-fetch layer       |
| `useFetch` `transform` mutation               | `transform: (data) => { data.foo = 'bar'; return data }` runs once on server, returns cached data on client | `transform` must be pure - return a new object; cached payload reuses the function's output, not its side effects                |
| `defineModel` two-way drift (Vue 3.4+)        | Parent's `v-model` is read but updates from child don't propagate                                      | Confirm child uses `defineModel()` (not `defineProps` + `defineEmits` half-implemented); audit modifier mismatch                   |
| `useState` SSR key collision                  | Two unrelated components share state because they used the same key                                    | `useState('user')` and `useState('user')` in different files map to the same slot; namespace keys per concern                      |

Recommended diagnostic instrumentation for these cases: add `console.log` (or a `watchEffect` logger) at each boundary the data crosses - input to the failing function, output to the next layer - and compare expected vs observed shape. The bug is almost always a missing field, a `.value` access vs identity, or a stale cache key. Pair with a round-trip test at the boundary so the regression is caught next time.

STEP 3 - LOCATE: Read the error to identify the source file and component name. Open the file and surrounding context (~50 lines above and below). Trace the component tree: page -> layout -> parent component -> failing component. Identify which layer the bug is in (Component | Composable | State | Data Fetching | Routing | Build).

STEP 4 - ROOT CAUSE: Explain WHY this error occurred, not just what happened. Reference the specific code that causes the issue. If it's a pattern violation (not just a one-off bug), name the pattern. Rate confidence: HIGH (certain, evidence is clear), MEDIUM (likely, but alternative causes exist), or LOW (need more info to confirm).

STEP 5 - FIX: Show the exact code change needed (before / after). If multiple fixes are possible, rank by: (1) Correctness, (2) Minimal change surface, (3) Alignment with project patterns. Explain any trade-offs between alternatives.

STEP 6 - PREVENT: Suggest a test that would have caught this bug. If it's a pattern violation, reference the relevant atomic skill. If the same bug could exist elsewhere, identify other occurrences (grep for similar patterns).

## Output Format

Present the analysis in this structure:

**Bug Analysis** - error type, confidence (HIGH/MEDIUM/LOW), layer (Component/Composable/State/Data Fetching/Routing/Build)

**Root Cause** - explanation of why this happened, referencing specific code

**Fix** - before/after code diff showing the exact change, with explanation

**Prevention** (omit if fix is trivial) - test that would catch this bug, pattern reference, other occurrences found via grep

### Output Constraints

- Keep the analysis focused - one bug, one fix
- Omit Prevention section if the fix is trivial (e.g., typo, missing import)
- If confidence is LOW, add a **Needs Clarification** section listing what info would help
- No code style commentary unrelated to the bug
- No suggestions for unrelated improvements

## Self-Check

- [ ] Error input accepted and clarified if ambiguous (STEP 1)
- [ ] Error classified into category before any code is read or fix proposed (STEP 2)
- [ ] Source file and component located; layer identified (STEP 3)
- [ ] Root cause explains WHY with specific code reference; confidence level stated (STEP 4)
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom (STEP 5)
- [ ] Test suggested that would catch this bug; other occurrences identified if pattern is widespread (STEP 6)

## Avoid

- Generic debugging advice ("add console.log", "clear cache")
- Fixing symptoms instead of root causes
- Suggesting refactors when a targeted fix suffices
- Analysis without reading the actual source code
- Proposing fixes that introduce new anti-patterns (adding `any`, suppressing ESLint, using Options API)
- Mixing incident response concerns into developer debugging
