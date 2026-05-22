---
name: task-react-debug
description: Debug React 19 / Next.js / Vite: hydration mismatches, hook violations, render loops, RSC boundary errors, stale data, build failures.
metadata:
  category: frontend
  tags: [react, debug, hydration, hooks, nextjs, troubleshooting]
  type: workflow
user-invocable: true
---

# Debug - React Debugging Workflow

## When to Use

- React error / warning, hydration mismatch, hook violation, infinite render
- Server Component / Client Component boundary error
- RSC or Server Action runs but UI shows stale data
- Build, TypeScript, or test failure tied to React/Next
- "No error, wrong result" - data flickers, missing, stale, or unequal across renders

Not for: production incident triage (`/task-oncall-start`), perf tuning (`task-react-review-perf`), new feature work (`task-react-implement`).

## Workflow

### STEP 1 - BEHAVIORAL PRINCIPLES

Use skill: `behavioral-principles`. These rules govern every step below.

### STEP 2 - STACK DETECT

Use skill: `stack-detect`. Confirm React major, Next.js vs Vite vs CRA, router (App vs Pages), data layer (RSC + Server Actions, TanStack Query, SWR, Redux). Output drives which atomic skill loads in STEP 4.

### STEP 3 - INTAKE

Accept one of: error message, console output, build/test failure, or a "wrong result, no error" report. For partial input, ask once for the missing piece:

- Error path: exact console text, file:line, repro steps, dev vs prod
- No-error path: expected vs observed value, which boundary it crosses (server fetch -> Client prop, action -> revalidate, query cache -> render), frequency (every nav / intermittent / under load)

### STEP 4 - CLASSIFY

Match one row; load the listed skill. Stop at the first match.

**Hydration** (server/client HTML differs)

| Symptom | Cause | Skill |
|---|---|---|
| "Hydration failed" / "Text content does not match" | Dynamic value (date, random, `window`) read during render | `react-nextjs-patterns` |
| "Expected server HTML to contain" | Browser-only API gated by `typeof window` | `react-component-patterns` |
| Same HTML, but state re-renders post-hydration | `useState(() => readLocalStorage())` returns different value on server | `react-nextjs-patterns` |

**Hook rules**

| Symptom | Cause | Skill |
|---|---|---|
| "Rendered more hooks than during previous render" | Conditional hook call | `react-hooks-patterns` |
| "Invalid hook call" | Hook outside component / hook | `react-hooks-patterns` |
| "Maximum update depth exceeded" | `setState` in render, or effect that always re-runs | `react-hooks-patterns` |
| Missing-dependency warning | `useEffect` deps incomplete | `react-hooks-patterns` |

**RSC / Server Component boundary**

| Symptom | Cause | Skill |
|---|---|---|
| "useState/useEffect in Server Component" | Missing `"use client"` | `react-nextjs-patterns` |
| "Event handlers cannot be passed to Client" | `onClick` defined in Server Component | `react-component-patterns` |
| "Functions cannot be passed directly to Client" | Non-serializable prop crossing boundary | `react-nextjs-patterns` |

**Stale data / wrong result, no error** - the bug lives at a data boundary. Walk the seams:

| Symptom | Likely cause | Skill |
|---|---|---|
| Server Action succeeds, UI shows old data | Missing `revalidatePath` / `revalidateTag`; or TanStack `queryClient.invalidateQueries` not called in `onSuccess` | `react-data-fetching` |
| Dashboard stale after route back-nav | Next.js Router Cache serving stale RSC payload; need `revalidatePath` on mutation or `router.refresh()` | `react-data-fetching` |
| Client component reads `undefined` for a server-fetched field | Prisma `select` / serialization drops the field (`Date`, `Map`, class instances don't cross RSC boundary) | `react-nextjs-patterns` |
| Two components fetch same data, get each other's | TanStack `queryKey` instability - inline object literal each render | `react-data-fetching` |
| Effect logs initial state forever | Stale closure in `useEffect([])`; deps incomplete or eslint-disable suppressed | `react-hooks-patterns` |
| `setCount(count+1)` twice only increments once | Use functional `setCount(prev => prev + 1)` | `react-hooks-patterns` |
| Memoized child still re-renders | Parent passes new object/array/function ref; `React.memo` shallow-compares | `react-hooks-patterns` |
| Context consumers re-render every parent render | `<Provider value={{a,b}}>` new ref each render; wrap in `useMemo` | `react-state-patterns` |

**Build / type / test**

| Symptom | Where to look |
|---|---|
| TS / build error | Compilation output's first error; later errors usually cascade |
| Test failure | Async timing, mock setup, RTL query type (`getBy` vs `findBy`) - Use skill: `react-testing-patterns` |
| Performance / slow render | Use skill: `frontend-performance` |

### STEP 5 - LOCATE

Open the failing file plus ~50 lines of context. Trace upstream: page -> layout -> parent -> failing component, OR fetch -> serialization -> Client prop -> render. Name the layer: Component | Hook | State | Data Fetching | Routing | Build.

For stale-data: instrument each boundary the value crosses (server fetch result, Client prop, state after `setState`, action return, query cache after invalidation) with `console.log` or React DevTools Profiler. Compare expected vs observed shape.

### STEP 6 - ROOT CAUSE

Explain **why**, citing `file:line`. State confidence:

- **HIGH** - reproduced or evidence is direct
- **MEDIUM** - strong pattern match, alternative causes exist
- **LOW** - need more info; list what

### STEP 7 - FIX

Before/after diff, smallest change that resolves the root cause. Rank alternatives by (1) correctness, (2) change surface, (3) alignment with existing patterns.

### STEP 8 - PREVENT

One guard:

- Test that exercises the exact path (Playwright for RSC / Server Action round-trip; RTL for closure / memo / effect dep)
- ESLint rule re-enabled if it was disabled (`react-hooks/exhaustive-deps`)
- `grep` for the same anti-pattern elsewhere; list occurrences

Skip if fix is trivial (typo, missing import).

## Output Format

```
## Classification
[Hydration | Hook | RSC | Stale data | Build | Runtime | Test]: [specific row]
Layer: [Component | Hook | State | Data Fetching | Routing | Build]

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
- [ ] STEP 2: stack-detect loaded; React major, framework, router, data layer identified
- [ ] STEP 3: full error or wrong-result spec captured; one clarifying question max if partial
- [ ] STEP 4: classified into one row before reading code; correct atomic skill loaded
- [ ] STEP 5: failing file located; layer named; for stale-data, boundaries instrumented
- [ ] STEP 6: root cause cites file:line; confidence stated
- [ ] STEP 7: before/after fix is minimal and targets root cause
- [ ] STEP 8: prevention guard added, or skipped with reason

## Avoid

- Reading code before classifying
- Generic advice ("add console.log", "clear cache") without naming the boundary
- Fixing a symptom (`router.refresh()` everywhere) instead of the missing `revalidate*`
- Refactor when a targeted fix suffices
- `any`, `eslint-disable`, `suppressHydrationWarning` to silence the error
- `useEffect` for derived state or data fetching - compute during render / use a query lib
- Mixing incident-response (containment, blast radius) into developer debugging
