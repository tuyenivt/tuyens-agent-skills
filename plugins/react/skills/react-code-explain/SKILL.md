---
name: react-code-explain
description: Explain React components: server vs client boundary, hook triggers, effect deps/cleanup, render identity, context scope, custom-hook composition.
metadata:
  category: frontend
  tags: [explanation, code-understanding, react, nextjs, hooks]
user-invocable: false
---

# React Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is React (Next.js primary, Vite secondary).

## When to Use

- A workflow needs per-component React signals: server vs client boundary, hook order/triggers, effect deps and cleanup, referential identity through render, context subscription scope, custom-hook composition, React 19 (`use`, actions).
- Target is a `.tsx`/`.jsx` component, hook, or route file.

Not for codebase orientation (use `react-onboard-map`) or framework tutorials.

## Rules

- Classify the file first: **Server Component** (App Router default), **Client Component** (`'use client'`), Route Handler, or plain hook module. Capabilities follow from this.
- For each hook call, name what triggers it: every render, mount-only (`[]`), on dep change (`[x]`), or commit-time vs render-time.
- For every `useEffect`/`useCallback`/`useMemo`, verify the dep array against values read inside. Missing dep => stale closure. Object/function dep => fires every render.
- Flag any value that changes identity each render and is passed to a memoized child, context `value`, or hook dep array.
- For data fetching, locate the boundary: server fetch in RSC, route handler, or client hook (`useQuery`/`useSWR`/`useEffect`/`use(promise)`).

## Patterns

### Component classification

| Marker                                | Kind             | Can use                                              | Cannot use                              |
| ------------------------------------- | ---------------- | ---------------------------------------------------- | --------------------------------------- |
| No directive in `app/`                | Server Component | `async`, DB/secrets, `cookies()`, `headers()`        | hooks, state, browser APIs, handlers    |
| `'use client'` at top                 | Client Component | hooks, handlers, browser APIs                        | DB/secrets (ships to browser)           |
| `app/api/*/route.ts`                  | Route Handler    | `Request` -> `Response`, server-only                 | JSX rendering                           |
| Hook module (`useX.ts`)               | Custom hook      | composes other hooks                                 | JSX as return                           |

`'use client'` is a **boundary marker**: every module imported transitively from a client file is client. Server Components can only be passed into Client Components as `children`, not imported.

### Hook trigger taxonomy

| Hook                         | Fires when                                       | Identity stable across renders? |
| ---------------------------- | ------------------------------------------------ | ------------------------------- |
| `useState` setter            | called                                           | yes (same fn ref)               |
| `useEffect(fn, deps)`        | after commit; deps changed (or every render if omitted) | n/a                      |
| `useLayoutEffect`            | after DOM mutation, before paint                 | n/a                             |
| `useMemo(fn, deps)`          | render; recomputes on dep change                 | only if deps stable             |
| `useCallback(fn, deps)`      | render; new fn on dep change                     | only if deps stable             |
| `useRef(init)`               | mount only for `init`                            | yes (same object ref)           |
| `useContext(Ctx)`            | when provider's `value` ref changes              | n/a                             |
| `use(promise)` (R19)         | suspends until resolved                          | n/a                             |

Hooks must run in the same order every render. Conditional/loop/post-return calls violate Rules of Hooks and crash on the next render with a different shape.

### Effect deps - the bug surface

- **Missing dep**: closure captures the value at the render the effect ran; reading state inside an effect with `[]` reads initial state forever.
- **Object/function dep**: `useEffect(..., [{ id }])` or `[onChange]` from a non-memoized parent fires every render.
- **Race**: async fetch in effect must guard with `AbortController` or an `ignore` flag; otherwise late responses overwrite newer state.
- **Strict Mode dev**: effects mount->unmount->mount; missing cleanup surfaces here.
- **Effect-as-derived-state smell**: setting state inside an effect from props/state means it should be `useMemo` or computed inline.

Bad: `useEffect(() => { fetch(url).then(setData); }, [url]);` - no abort; stale `url` overwrites new.
Good: `useEffect(() => { const c = new AbortController(); fetch(url, { signal: c.signal }).then(setData); return () => c.abort(); }, [url]);`

### Referential identity and re-renders

A component re-renders when its state changes, its parent re-renders, or a subscribed context's `value` ref changes - **props equality is not checked unless wrapped in `memo`**.

Identity hazards:

- Inline `{...}` / `[...]` / `() => ...` in JSX: new ref each render, breaks `memo` and triggers dep arrays.
- Context provider `value={{ user, logout }}`: new object each render rerenders every consumer. Wrap in `useMemo`.
- Functions from props that aren't `useCallback`-wrapped by the parent.

Bad: `<Ctx.Provider value={{ user, setUser }}>` rerenders all consumers on every parent render.
Good: `const value = useMemo(() => ({ user, setUser }), [user]); <Ctx.Provider value={value}>`.

`useMemo`/`useCallback` are optimizations, not defaults. Apply when the value crosses a `memo` boundary, feeds a dep array, or computation is expensive.

### Custom hooks

- A function whose name starts with `use` and calls hooks. Hook order applies across the composition.
- Returns plain values, tuples, or objects - **fresh on every render unless the hook itself memoizes**.
- The component re-renders when any `useState`/`useReducer`/`useSyncExternalStore` inside the custom hook updates.
- Calling the same custom hook in two components creates two independent state instances (no sharing without context/store).

### Context scope

- `useContext(Ctx)` subscribes to the **nearest** `<Ctx.Provider>` above. No provider => default value from `createContext(default)`.
- All consumers rerender on `value` identity change, regardless of which field they read. Split providers (state vs dispatch) or use `use-context-selector` to narrow.
- `use(Ctx)` (R19) is the same subscription, callable conditionally.

### React 19 deltas

- `use(promise)`: unwraps in render, suspends to nearest `<Suspense>`.
- `useActionState(action, init)`: form action result + pending state.
- `useFormStatus()`: pending state of the enclosing `<form>`.
- Server Actions (`'use server'`): callable from Client Components, receive `FormData` or args.
- `<form action={fn}>`: triggers action on submit; works with `useActionState`.

### Data fetching boundary

| Where                              | Mechanism                                           |
| ---------------------------------- | --------------------------------------------------- |
| Server Component                   | top-level `await fetch(...)` with Next cache opts   |
| Route Handler                      | `Request` -> `Response`                             |
| Client, declarative                | `useQuery`/`useSWR` (cache, retry, refetch)         |
| Client, imperative                 | `useEffect` + fetch (manual race/abort handling)    |
| Client, suspending                 | `use(promise)` inside `<Suspense>`                  |

## Output Format

This atomic emits signals consumed by `task-code-explain`. Produce exactly four blocks with the field enums below.

```
Flow Context:
- Kind: {Server Component | Client Component | Route Handler | Custom Hook | Plain module}
- Boundary: {none | 'use client' at top | imports client-only X}
- Hooks: <name(deps) -> trigger; ...>
- Custom hooks: {none | <list and what each owns>}
- Context: {none | reads <Ctx>; provides <Ctx>}
- Data fetching: {none | RSC fetch | route handler | useQuery/useSWR | useEffect+fetch | use(promise)}
- React 19 features: {none | use() | useActionState | useFormStatus | server action}

Non-Obvious Behavior:
- <stale closures / missing deps>
- <identity hazards: inline objects, unstable context value, props to memo>
- <effect race / missing AbortController>
- <Strict Mode double-invoke implications>
- <hook order violations (conditional, post-return)>
- <Server <-> Client import direction issues>

Key Invariants:
- <hook call order stable across renders>
- <which values must stay referentially stable and why>
- <server-only vs client-only capabilities for this kind>
- <Suspense/Error boundary nesting if relevant>

Change Impact Preview:
- <adding 'use client': bundle ships; remove server-only imports>
- <changing deps [] -> [x]: cleanup/setup cadence shifts>
- <splitting context value: which consumers stop rerendering>
- <wrapping child in memo: which props now need stable identity>
- <moving fetch from client effect to RSC: loading/error UX changes>
```

If a block has no findings, emit `- (none)`. Omit React 19 features if the project is on R18; do not fabricate.

## Avoid

- Recommending `useMemo`/`useCallback` blanket-wide; name the specific consumer that needs the stable ref.
- Treating Server Components as "components that fetch" - they cannot use any client feature.
- Listing hooks without naming each one's trigger.
- Conflating `'use client'` with "this file runs only on client" - it runs on both; the directive marks the boundary.
- Calling out effect deps without distinguishing missing-dep (stale) from unstable-dep (thrash).
- Drifting into ecosystem tutorials (data libs, form libs) instead of explaining the target file.
