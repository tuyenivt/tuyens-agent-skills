---
name: react-code-explain
description: React 19 / Next.js / Vite framework signals for code explanation - hooks rules and dependencies, component render lifecycle, server vs client components, suspense and streaming, and React 19 actions/use(). Used by task-code-explain to explain React code with stack-aware gotchas.
metadata:
  category: frontend
  tags: [explanation, code-understanding, react, nextjs, hooks]
user-invocable: false
---

# React Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is React (Next.js primary, Vite secondary).

## When to Use

- A workflow needs React-specific signals: hooks rules, render cycles, effect dependencies, server vs client component boundaries (Next.js App Router), Suspense, React 19 actions and `use()`.
- Target uses JSX, hooks (`useState`, `useEffect`, `useMemo`, `useCallback`, `useContext`, etc.), or React 19 features (`use`, `useActionState`, `useFormStatus`).

## Rules

- Identify whether the file is a **Server Component** (default in Next.js App Router) or a **Client Component** (`'use client'` directive). They have different capabilities and interaction models.
- For each hook, name what triggers it: every render, mount only, on dependency change. Effect dependencies are the most common bug source.
- For event handlers and callbacks, identify whether they capture stale state via closure - this is the closure-over-state issue.
- For data fetching, identify whether it is server-side (Server Component, `getServerSideProps`, route handler) or client-side (`useEffect`, `useQuery`, `use(promise)`).
- Surface React 19 vs 18 differences when relevant - `use()` for Promise/Context, `useActionState`, automatic batching.

## Patterns

### Server vs Client Components (Next.js App Router)

| Component type     | Default in App Router  | Can use                                                                                       | Cannot use                                                                                   |
| ------------------ | ---------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Server Component   | Yes                    | `async`/`await`, direct DB/API calls, `cookies()`, `headers()`, `redirect()`, `notFound()`    | `useState`, `useEffect`, browser APIs, event handlers, refs                                  |
| Client Component   | Marked with `'use client'` at top of file | All hooks, event handlers, browser APIs, state                                | Direct DB calls, secrets - the bundle ships to the browser                                   |

- Importing a Client Component into a Server Component: works; renders on the client.
- Importing a Server Component into a Client Component: **does not work directly**; pass it as a `children` prop instead.
- The `'use client'` boundary marks the **start** of the client tree; everything imported from a client file is also client.

### Hooks Rules

1. Only call hooks at the top level of a component or another hook.
2. Do not call hooks inside conditions, loops, or after early returns.
3. Hook order must be stable across renders - violating this causes "Rendered more hooks than during the previous render".

The linter enforces these via `react-hooks/rules-of-hooks`; check `eslint-plugin-react-hooks` is configured.

### Render Cycle and Re-renders

A component re-renders when:

- Its state (`useState`) changes.
- Its parent re-renders (props change or parent's parent re-rendered) - **even if the props themselves did not change**.
- A context it subscribes to changes.

Common causes of unintended re-renders:

- **Inline objects/arrays/functions in JSX:** `<Child config={{ foo: 1 }} />` creates a new object on every render; if `Child` is memoized, memoization breaks because `config` is a new reference.
- **Inline event handlers:** `<Child onClick={() => setX(x + 1)} />` - new function each render. Wrap in `useCallback` if the child is memoized.
- **Context value recreated:** `<Ctx.Provider value={{ user, logout }}>` - new object each render rerenders all consumers. Memoize the value.

### useState

- `setState(value)` schedules a re-render. State updates are batched in event handlers and effects (and async paths in React 18+).
- `setState(prev => prev + 1)`: functional update; uses the most recent value, avoiding stale closures.
- `setState` does not merge objects (unlike class `this.setState`); use the spread operator: `setState({ ...prev, name: x })`.
- Updating state during render (outside `useEffect` or event handler) without conditions causes an infinite loop.

### useEffect

- Runs **after** render commits. Default: every render. With `[]` dependency: once on mount + cleanup on unmount. With `[x]`: when `x` changes.
- The cleanup function runs **before** the next effect run AND on unmount.
- Strict Mode in development: effects run twice (mount + unmount + mount) to surface bugs from missing cleanup.
- Stale closure: an effect captures values at the moment it ran; reading `state` inside an effect with `[]` deps reads the initial state forever.
- Race conditions: an effect that fetches data must guard against the response arriving after the component unmounted or the parameter changed - typically with an AbortController or a flag.
- Common smells: effect that runs on every render (forgot deps), effect that should be derived state (could be computed from props/state without effect), effect for syncing two states (could be one).

### useMemo and useCallback

- `useMemo(() => compute(x), [x])`: caches the computation across renders.
- `useCallback(fn, [x])`: same as `useMemo(() => fn, [x])`.
- These are **optimizations**, not semantic changes. Adding them everywhere harms more than helps.
- Use when: result is expensive to compute, OR the value is passed as a prop to a memoized child, OR it is in a dependency array of another hook.

### useRef

- `useRef(initial)`: returns `{ current: initial }`. Mutating `.current` does not re-render.
- Used for: DOM refs (`<input ref={ref} />`), holding mutable values across renders without causing re-render, holding the latest version of a callback for use in stable handlers.

### useContext

- `useContext(MyCtx)`: subscribes to the nearest `<MyCtx.Provider>`.
- Every consumer re-renders when the provider's `value` changes (referentially).
- Splitting context (separate providers for state vs dispatch) reduces re-render scope. The `use-context-selector` library narrows further.

### React 19 Specifics

- `use(promise)`: unwraps a Promise inside a component; suspends the component until resolved (works inside Suspense boundaries).
- `use(context)`: alternative to `useContext`; can be called conditionally.
- `useActionState(action, initialState)`: pairs with `<form action={...}>` for form submission state.
- `useFormStatus()`: reads the parent form's pending state.
- Server Actions (`'use server'`): functions that run on the server, can be called from client components, integrate with forms.
- Automatic batching: state updates in promises, timeouts, and native event handlers are batched.

### Suspense and Error Boundaries

- `<Suspense fallback={...}>`: shows fallback while children "throw" Promises (legacy: `lazy(() => import(...))`; new: `use(promise)`).
- Error Boundaries (class components with `componentDidCatch` or `react-error-boundary`): catch errors from children. Function components cannot be error boundaries directly.
- Suspense boundary catches the **nearest** suspending component; nest carefully to control fallback granularity.

### Data Fetching Libraries

- **TanStack Query (React Query):** `useQuery({ queryKey, queryFn })` for server state. Cache, refetch, retries, suspense mode.
- **SWR:** `useSWR(key, fetcher)`; similar API to React Query, smaller surface.
- **Apollo / urql:** GraphQL clients with their own cache and hooks.
- **Built-in `fetch` in Server Components:** Next.js extends `fetch` with caching (`{ cache: 'no-store' }`, `{ next: { revalidate: 60 } }`).

### Forms

- Controlled: input value comes from state, change handler updates state. Standard React pattern.
- Uncontrolled: refs read on submit. Faster, less code, harder to derive UI from.
- React Hook Form, Formik, Zod for schema validation.
- React 19 `<form action={serverAction}>`: form submission triggers Server Action with `FormData`.

### Next.js Specifics

- App Router (`app/` directory): Server Components by default, file-based routing, layouts, loading states (`loading.tsx`), error boundaries (`error.tsx`).
- Pages Router (`pages/` directory): older; `getServerSideProps`, `getStaticProps`, `getStaticPaths`.
- Route Handlers (`app/api/*/route.ts`): replace `pages/api/*`. Export named functions per HTTP method.
- Middleware (`middleware.ts`): runs on the edge before route handlers; for auth, redirects, header manipulation.
- Caching: Next.js aggressively caches; understand `cache()`, `unstable_cache`, `revalidatePath`, `revalidateTag`.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Server Component vs Client Component
- For Next.js App Router: which segment (page, layout, loading, error, route handler) the file represents
- Hooks used and what triggers them
- Suspense / Error Boundary tree if relevant
- Data fetching layer (server fetch, React Query, SWR, etc.)

**Into "Non-Obvious Behavior":**

- Stale closures in `useEffect` with insufficient deps
- Inline objects/functions causing memoization breakage
- Effect race conditions on async state updates after unmount
- Strict Mode double-invoking effects in dev
- Importing Server Components into Client Components (forbidden direct)
- Suspense boundary granularity catching unexpected components

**Into "Key Invariants":**

- Hooks must be called at the top level, in the same order every render
- Server Components cannot use state, effects, or browser APIs
- `'use client'` marks the start of the client tree; everything below is client
- `useEffect` runs after commit, not during render

**Into "Change Impact Preview":**

- Removing a hook dependency: stale values inside the hook
- Adding state to a parent: every render of the parent triggers child renders unless memoized
- Adding `'use client'` to a previously-Server Component: bundle ships to the browser; remove any server-only imports
- Changing `useEffect` deps `[]` to `[x]`: cleanup/setup pattern changes drastically
- Memoizing a child without memoizing its props: memoization is silently broken

## Avoid

- Recommending `useMemo`/`useCallback` everywhere - they are optimizations, not best practice
- Treating Server Components as just "components that fetch data" - they cannot use any client features
- Skipping `'use client'` boundary when explaining a component's capabilities
- Confusing controlled and uncontrolled inputs - they have different mental models
- Listing every hook without naming what triggers each
- Saying "React 18 and 19 are the same" - hooks like `use()`, `useActionState`, and Server Actions are React 19+
