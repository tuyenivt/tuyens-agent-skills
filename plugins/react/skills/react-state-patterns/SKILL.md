---
name: react-state-patterns
description: "Review React 19 state: pick useState/useReducer/Context/Zustand/Redux Toolkit/Jotai/URL, server state in TanStack Query, context re-render pitfalls."
metadata:
  category: frontend
  tags: [react, state, zustand, redux-toolkit, jotai, context, useReducer]
user-invocable: false
---

# React State Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For server-cache concerns (TanStack Query / SWR) defer to `react-data-fetching` if present.

## When to Use

- Choosing a mechanism for a new piece of state, or auditing an existing slice
- Splitting a mega-context or mega-store that re-renders too widely
- Migrating between useState, Context, Zustand, Redux Toolkit, or Jotai

## Rules

- Climb the ladder only when forced: useState -> useReducer -> Context -> Zustand/Jotai -> Redux Toolkit.
- Server data read at render is fetched in a Server Component and reaches Client Components as props or a Promise unwrapped with `use()`; interactive client data (refetch, poll, client mutation) lives in a server-cache library (TanStack Query, SWR, RTK Query). Never hand-copy either into Zustand, Redux slices, or Context.
- Context carries low-frequency values (theme, auth identity, locale). Never form fields, mouse, or animation state.
- One store per domain boundary. Cart, auth, and notifications are separate stores.
- Derived values are selectors, not stored fields. State updates go through the library's setter; no direct mutation outside Immer-backed reducers.
- State that should survive a refresh, a shared link, or (without `cacheComponents`) a Back navigation belongs in the URL, not memory. With `cacheComponents` on, `useState` also survives navigation, so state that must start fresh on each visit needs an explicit reset (Returning to a hidden route).

## Patterns

### Mechanism Selection

| Mechanism      | Use for                                              | Example                            |
| -------------- | ---------------------------------------------------- | ---------------------------------- |
| useState       | Independent component-local values                   | Toggle, single input               |
| useReducer     | Related local fields with coupled transitions        | Multi-field form, state machine    |
| Context *or* tiny Zustand | Low-frequency, app-wide identity                | Theme, auth user, locale           |
| Zustand        | Shared client state across unrelated components      | Cart, toast queue, UI prefs        |
| Jotai          | Many independent atoms read by different consumers   | Per-cell values in a large grid    |
| Redux Toolkit  | Large team needing middleware, time-travel, sagas    | Complex workflows, audited apps    |
| URL            | Shareable, bookmarkable, back-button-safe state      | Filters, sort, page, search query  |
| Server Component | Server data read at render (props or a `use()` Promise) | Product page, dashboard stats   |
| TanStack Query | Server data the client refetches, polls or mutates   | Live order status, infinite list   |

Identity values (theme, auth, locale) work in either Context or a tiny Zustand store. Pick Context when the value is written once per session at the app shell; pick a store when it is toggled at runtime, persisted, or written from several places.

### useReducer for coupled fields

```tsx
type Action =
  | { type: "setCategory"; value: string }
  | { type: "setSort"; value: string }
  | { type: "reset" };

function reducer(s: Filters, a: Action): Filters {
  switch (a.type) {
    case "setCategory": return { ...s, category: a.value, page: 1 }; // coupling: filter resets page
    case "setSort":     return { ...s, sort: a.value };
    case "reset":       return initial;
  }
}
```

Reach for `useReducer` when one input must move several fields atomically; otherwise stay on `useState`.

### Zustand store with selector subscription

```tsx
import { create } from "zustand";

type CartStore = {
  items: CartItem[];
  add: (i: CartItem) => void;
  remove: (id: string) => void;
};

export const useCart = create<CartStore>((set, get) => ({
  items: [],
  add: (i) => set((s) => ({ items: [...s.items, i] })),
  remove: (id) => set((s) => ({ items: s.items.filter((x) => x.id !== id) })),
}));

// Derived values are selectors at the call site, never fields on the store.
// Subscribe to the slice you read, not the whole store.
function CartBadge() {
  const count = useCart((s) => s.items.length);
  const total = useCart((s) => s.items.reduce((n, i) => n + i.price * i.quantity, 0));
  return <span>{count} items - {total}</span>;
}
```

Add `persist` only when reload must preserve state; add `devtools` in development. Stores stay flat per domain - do not nest `cart`, `auth`, `ui` inside one store. With SSR (Next.js), a `persist` store backed by `localStorage` rehydrates while the module evaluates - before the first client render - so the client's first paint disagrees with the server HTML that was rendered without it. Gate on a mounted flag (or `persist`'s `skipHydration` + a manual `rehydrate()`) before rendering persisted values. Separately, a module-scope store is one instance per server process and is shared across concurrent requests - a `"use client"` module still runs on the server during SSR, so moving it there changes nothing. Create it per request behind a provider, or keep it module-scope only if nothing writes per-request data into it during a server render.

### Jotai for independent atoms

```tsx
import { atom, useAtom } from "jotai";
import { atomFamily } from "jotai-family"; // Jotai 3 no longer exports atomFamily from jotai/utils

// One atom per cell - editing a cell re-renders only that cell, not the grid.
const cellAtom = atomFamily((id: string) => atom(""));

function Cell({ id }: { id: string }) {
  const [value, setValue] = useAtom(cellAtom(id));
  return <input value={value} onChange={(e) => setValue(e.target.value)} />;
}
```

Reach for Jotai over Zustand when consumers read disjoint slices that would otherwise force a shared store to re-render broadly (large grids, per-row selection, many independent toggles). `atomFamily` caches one atom per key and never evicts on its own, so a family keyed by churning ids grows without bound - call `remove(key)` when a row unmounts, or set an eviction policy with `setShouldRemove`.

### Context re-render pitfall

```tsx
// Bad - every keystroke re-renders every consumer of FormContext.
const FormContext = createContext<{ values: Record<string, string>; set: (k: string, v: string) => void } | null>(null);

// Good - form values in useReducer / React Hook Form / Zustand; Context holds only stable identity.
const AuthContext = createContext<{ user: User; logout: () => void } | null>(null);
```

Splitting one Context into a value-Context and a setter-Context only helps if setters are stable; for high-frequency updates, switch mechanism.

### URL state (Next.js App Router)

```tsx
"use client";
import { useSearchParams, useRouter, usePathname } from "next/navigation";

function useFilters() {
  const params = useSearchParams();
  const router = useRouter();
  const path = usePathname();
  return (key: string, value: string) => {
    const next = new URLSearchParams(params);
    next.set(key, value);
    if (key !== "page") next.set("page", "1"); // a filter change resets paging; a page change does not
    router.push(`${path}?${next}`);
  };
}
```

With `cacheComponents` set, the component calling this always sits under `<Suspense>` (search params are known only at request time; with no boundary the build fails). Without it, a statically prerendered route needs the boundary (`useSearchParams` makes the subtree up to it render on the client) and a dynamic route (`await connection()` in the Server Component) needs none. Alternative: pass the page's `searchParams` Promise to the Client Component and unwrap it with `use()` (it suspends, so it still sits under `<Suspense>`).

Read filters directly from `searchParams` per render - that *is* the source of truth.

### Returning to a hidden route (Cache Components)

With `cacheComponents: true`, Next hides the route you leave with `<Activity>` (up to 3 routes) instead of unmounting it, so component state survives back/forward and push navigations alike. State that should start fresh - a create form after submit, a stale success message, an open dropdown - resets, in order of preference, in the event handler that submits or navigates, through a `key` derived from data (a draft id), in a `useLayoutEffect` cleanup (it runs on hide), and only as a last resort through `key={useRouter().bfcacheId}` (new on push/replace, unchanged on back/forward). Preserved state shown where a fresh start was needed is `Stale-On-Return`.

### Redux Toolkit (when justified)

```tsx
const cart = createSlice({
  name: "cart",
  initialState: { items: [] as CartItem[] },
  reducers: {
    add: (s, a: PayloadAction<CartItem>) => { s.items.push(a.payload); }, // Immer
    remove: (s, a: PayloadAction<string>) => { s.items = s.items.filter(i => i.id !== a.payload); },
  },
});
```

Use only when the project already needs middleware (sagas, undo/redo, cross-cutting logging). RTK Query already in the tree is a server-cache library and fine where it is, but it is not on its own a reason to keep Redux for client state. For a greenfield slice, Zustand is shorter and cheaper.

## Output Format

When migrating, write `Primary library` as `{incumbent} -> {target}`, `Owner` as `{current} -> {target}` per slice, and order Findings as the migration sequence - server state out first, then one slice at a time; a slice nobody reads from the old store is done. When designing, the State Map and Stores describe the proposed architecture and Findings flag risks in it, using the same Issue values to name the mistake the design would otherwise make; state that has no owner yet takes the proposed name. When auditing, the consuming workflow owns the finding envelope; invoked standalone, emit the State Map and Stores as the target state, order Findings by severity, one finding per root cause (Location may name several files); `Primary library` is then the recommendation, not the incumbent. A design spanning several mechanisms names the one holding the largest client-state surface as `Primary library` and a scoped store as `Secondary`.

```
## React State Architecture

Stack: {stack-detect's Framework value, e.g. `React (Next.js)`}

Primary library: {Zustand | Redux Toolkit | Jotai | Context-only | none - useState/useReducer plus a server-cache library}

Secondary (scoped): {client-state library - the one domain it serves | none}

### State Map

| Slice           | Category   | Owner            | Mechanism        | Rationale            |
| --------------- | ---------- | ---------------- | ---------------- | -------------------- |
| {slice name}    | {Local UI \| Shared UI \| Server \| URL \| Identity} | {component/store} | {mechanism}    | {1-line why}         |

### Stores

| Store        | Domain    | Persisted | Middleware           |
| ------------ | --------- | --------- | -------------------- |
| {name}       | {domain}  | {Yes \| No \| partial (<fields>)}  | {devtools, persist}  |

### Findings

- Severity: {Critical | High | Medium | Low}
  Issue: {Wrong-Mechanism | Server-State-In-Store | Context-Re-render | Mega-Store | Stored-Derived | Mutation | URL-Candidate | Over-Subscription | Hydration-Mismatch | Duplicate-Source | Stale-On-Return}
  Location: {file/component or "design"}
  Fix: {one-line action}

Not assessed: {input the review needed but never saw - a file referenced but not provided, a module whose behaviour decides a severity, a symptom whose trigger lies outside scope; never a guessed finding; omit when none}
```

Derived values are not slices - they never get a State Map row; a stored one is a `Stored-Derived` finding. Jotai atom families take a Stores row with Middleware `-`; Context providers and server-cache libraries do not get Stores rows, and a target with no store at all writes one row `none`. A migration map lists unchanged slices too, owner unchanged; a slice written but never read takes the row with Owner `{current} -> removed` and no finding. A context bundling unrelated values is `Context-Re-render` (the re-render is the defect); a store bundling domains is `Mega-Store`. Category `Identity` covers auth/theme/locale; feature-scoped shared values (grid atoms) are `Shared UI`. `Duplicate-Source`: the same state has two owners (URL copied into `useState`, one slice duplicated across stores); the Fix names the surviving owner. Server data mirrored into a store stays `Server-State-In-Store`.

Severity: **Critical** = wrong data shown or updates lost (store mutation without a new reference, two sources of truth disagreeing); **High** = broad re-render or staleness (server data mirrored into a store, context re-rendering per keystroke, SSR hydration mismatch); **Medium** = structure debt (mega-store, stored derived, URL candidate, over-subscription) and stale-on-return; **Low** = convention drift (a `Wrong-Mechanism` that costs only idiom - Context where a tiny store would read better, with no re-render cost). An Issue value's row is set by the condition named; `Wrong-Mechanism` is Low when it costs only idiom, Medium otherwise, High when it is already producing staleness or a broad re-render. `Duplicate-Source` owners that still agree are High (a staleness risk); once they disagree - a stored derived value already out of step with its source included - Critical. A defect matching a named example takes that row's severity; where a named example and a general clause both fit, the named example wins; where two named examples fit, the higher row wins. The general clauses cover unnamed cases.

If stack-detect's Framework is not React and the project has no React sources, emit `Findings: none (no React detected)` and stop - a greenfield design on a React stack proceeds.

## Avoid

- Server data hand-copied into Zustand/Redux slices/Context - pass it from a Server Component or use a server-cache library.
- Context for inputs, mouse, scroll, drag, animation - re-renders every consumer.
- One mega-store/mega-context coupling unrelated domains.
- Storing derived values (totals, filtered lists) instead of computing in a selector.
- Reaching for Redux when useState + one Zustand store would do.
- Mirroring URL state into memory - the URL is the source.
- Prop drilling past 2 levels when a store or scoped context fits.
- Reading a whole store/slice when you use one field (`Over-Subscription`) - subscribe via a narrow selector so only relevant changes re-render. High-frequency writes (per-keystroke dispatch) compound this; debounce or move to local/URL state.
