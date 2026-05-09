---
name: task-react-debug
description: Debug React 19 / Next.js / Vite errors: hydration mismatches, hook violations, render loops, RSC errors, build and runtime failures.
metadata:
  category: frontend
  tags: [react, debug, hydration, hooks, nextjs, error, troubleshooting]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Debug - React Debugging Workflow

## When to Use

- React error or warning you need help understanding
- Hydration mismatch in Next.js or SSR setup
- Hook rule violation (called conditionally, wrong order, missing dependency)
- Infinite render loop or excessive re-renders
- Server Component / Client Component boundary error
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

| Input                           | Required | Description                              |
| ------------------------------- | -------- | ---------------------------------------- |
| Error message or console output | Yes      | The primary failure signal               |
| Relevant source file            | No       | Component or hook where the error occurs |
| Steps to reproduce              | No       | What triggers the error                  |
| Expected vs actual behavior     | No       | For logic bugs without exceptions        |
| Browser / Node version          | No       | For environment-specific issues          |

## Rules

- Always classify the error before reading code
- Show the exact code change needed - no vague suggestions
- Explain WHY the error happened, not just how to fix it
- Prefer minimal fixes over refactors - fix the bug, don't redesign
- If confidence is LOW, say so and state what additional info would help
- Do not suggest unrelated improvements or style changes
- Reference atomic skills only when the fix involves a pattern they cover

## Workflow

STEP 1 - INTAKE: Accept one or more of: React error message, Next.js build/runtime error, browser console output, TypeScript compilation error, test failure output, or description of unexpected behavior. If the input is ambiguous, ask one clarifying question before proceeding.

STEP 2 - CLASSIFY: Identify the error category to guide investigation:

**Hydration error** → Server/client HTML mismatch:

| Error Pattern                     | Likely Cause                         | Load Skill                            |
| --------------------------------- | ------------------------------------ | ------------------------------------- |
| "Hydration failed"                | Server/client render difference      | Use skill: `react-nextjs-patterns`    |
| "Text content does not match"     | Dynamic value (date, random, window) | Use skill: `react-nextjs-patterns`    |
| "Expected server HTML to contain" | Conditional render using browser API | Use skill: `react-component-patterns` |

**Hook error** → Hook rules violation:

| Error Pattern                                     | Likely Cause                              | Load Skill                        |
| ------------------------------------------------- | ----------------------------------------- | --------------------------------- |
| "Rendered more hooks than during previous render" | Conditional hook call                     | Use skill: `react-hooks-patterns` |
| "Invalid hook call"                               | Hook outside component/hook               | Use skill: `react-hooks-patterns` |
| "Maximum update depth exceeded"                   | Infinite render loop (setState in render) | Use skill: `react-hooks-patterns` |
| Missing dependency warning                        | useEffect dependency array incomplete     | Use skill: `react-hooks-patterns` |

**Server Component error** → RSC boundary violation:

| Error Pattern                                   | Likely Cause                            | Load Skill                            |
| ----------------------------------------------- | --------------------------------------- | ------------------------------------- |
| "useState/useEffect in Server Component"        | Missing `"use client"` directive        | Use skill: `react-nextjs-patterns`    |
| "Event handlers cannot be passed to Client"     | onClick in Server Component             | Use skill: `react-component-patterns` |
| "Functions cannot be passed directly to Client" | Non-serializable prop crossing boundary | Use skill: `react-nextjs-patterns`    |

**Build / TypeScript error** → compilation or bundling issue

**Runtime error** → JavaScript exception during render or event handling

**Test failure** → assertion mismatch, async timing, mock setup

**Performance issue** → slow renders, memory leak, bundle size → Use skill: `frontend-performance`

**No-error / wrong-behavior intake.** When the user reports "no exception, but the value is wrong / missing / stale," the bug almost always lives at a boundary where data crosses a closure, hydration, or serialization seam. There is no stack trace to follow - work the seams. React-flavored surfaces:

| Surface                                       | Symptom                                                                                                        | Diagnostic                                                                                                                                |
| --------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Stale closure in `useEffect([])`              | Effect reads a state value that never updates - logs the initial value forever                                  | Either add the value to deps, OR use `useRef` to read latest, OR rewrite as event handler. ESLint `react-hooks/exhaustive-deps` warns; check for disable comments |
| `useEffect` for derived state                 | Value flickers between renders; child sees stale derived state for one frame                                    | Compute during render: `const x = a + b`. Delete the `useState`+`useEffect` pair                                                          |
| `setState(value)` vs `setState(prev => ...)`  | Two consecutive `setCount(count + 1)` calls only increment by 1 (not 2) under batching                         | Use functional form `setCount(prev => prev + 1)` whenever the next value depends on the current value                                     |
| RSC → Client prop drop                        | Client component reads `props.user.email` as `undefined`; server fetched a row but the field never crosses    | Check Prisma `select` / `omit` matches the prop interface; check serialization (`Date`, `Map`, class instances don't survive the boundary) |
| Server Action success but stale UI            | Action returns `{ ok: true }`, DB updated, but the page still shows old data                                   | Missing `revalidatePath('/dashboard')` / `revalidateTag('orders')` in the action; OR TanStack Query cache not invalidated via `queryClient.invalidateQueries({ queryKey: ['orders'] })` in `onSuccess` |
| `useOptimistic` rollback eaten                | Action fails, but the optimistic UI never reverts; user sees fake success                                       | Confirm component still mounted when action rejects; if it unmounts mid-flight, the rollback runs against a torn-down state. Use a parent-level optimistic state, or guard the rollback |
| `useFormStatus` reads wrong form              | `useFormStatus()` returns `{ pending: false }` even while the form is submitting                                | Hook must be called from a child component **inside** `<form>`, never on the form itself. Verify `<SubmitButton />` is rendered inside the form, not as a sibling |
| `next/navigation` `useSearchParams` stale     | `useSearchParams()` returns a value that's one navigation behind                                                | Suspense boundary missing - `useSearchParams()` opts the route into dynamic rendering and requires a `<Suspense>` wrapper for stable behavior on streaming pages |
| TanStack Query key collision                  | Different components fetch different data but get each other's results                                         | Inspect `queryKey` arrays for unstable references (`['orders', filters]` where `filters` is a new object literal each render) - the key compares by value but inline objects break memoization upstream. Stabilize via `useMemo` or pass primitive fields |
| `<form action={action}>` extra fields stripped | User submits a field but the action never sees it                                                              | If using `zod-form-data` `.strict()`, extra fields parse OK but get stripped; if validation is loose, unexpected fields silently drop. Add the field to the schema or to the form's input list |
| Hydration agrees but state diverges           | Server and client render the same HTML, but `useState(() => readLocalStorage())` returns `undefined` on server, then real value on client - causing a re-render after hydration | Move the read into `useEffect`: `useState(undefined)` + `useEffect(() => setX(readLocalStorage()))`. OR use Next.js dynamic import with `{ ssr: false }`. OR `suppressHydrationWarning` on the specific node (last resort)              |
| Context value rebuilt every render            | Consumers re-render on every parent render even when the context "didn't change"                                | `<Provider value={{ a, b }}>` - the object literal is new every render. Wrap with `useMemo(() => ({ a, b }), [a, b])`, OR split into separate providers (state vs dispatch)                                                              |
| `React.memo` no-op                            | Memoized child still re-renders when parent renders                                                             | Parent passes new object/array/function each render; `React.memo` shallow-compares props and sees a new ref. Stabilize the prop via `useMemo`/`useCallback`, OR pass primitives only                                                     |

Recommended diagnostic instrumentation for these cases: add `console.log` (or React DevTools Profiler) at each boundary the data crosses - server fetch result, props going into Client Component, state after `setState`, action return value, query cache after invalidation - and compare expected vs observed shape. The bug is almost always a missing `revalidate*`, a stale closure, a new object identity in a memo dep, or a serialization boundary that drops a field. Pair with a round-trip test (Playwright for the Server Action / RSC path; RTL for the closure / memo path) so the regression is caught next time.

STEP 3 - LOCATE: Read the error to identify the source file and component name. Open the file and surrounding context (~50 lines above and below). Trace the component tree: page -> layout -> parent component -> failing component. Identify which layer the bug is in (Component | Hook | State | Data Fetching | Routing | Build).

STEP 4 - ROOT CAUSE: Explain WHY this error occurred, not just what happened. Reference the specific code that causes the issue. If it's a pattern violation (not just a one-off bug), name the pattern. Rate confidence: HIGH (certain, evidence is clear), MEDIUM (likely, but alternative causes exist), or LOW (need more info to confirm).

STEP 5 - FIX: Show the exact code change needed (before / after). If multiple fixes are possible, rank by: (1) Correctness, (2) Minimal change surface, (3) Alignment with project patterns. Explain any trade-offs between alternatives.

STEP 6 - PREVENT: Suggest a test that would have caught this bug. If it's a pattern violation, reference the relevant atomic skill. If the same bug could exist elsewhere, identify other occurrences (grep for similar patterns).

## Output Format

Present the analysis in this structure:

**Bug Analysis** - error type, confidence (HIGH/MEDIUM/LOW), layer (Component/Hook/State/Data Fetching/Routing/Build)

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
- Proposing fixes that introduce new anti-patterns (adding `any`, suppressing ESLint, using `useEffect` for fetching)
- Mixing incident response concerns into developer debugging
