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
- Server data lives in TanStack Query / SWR. Never mirror it into Zustand, Redux, or Context.
- Context carries low-frequency values (theme, auth identity, locale). Never form fields, mouse, or animation state.
- One store per domain boundary. Cart, auth, and notifications are separate stores.
- Derived values are selectors, not stored fields. State updates go through the library's setter; no direct mutation outside Immer-backed reducers.
- State that should survive refresh, share, or back-button belongs in the URL, not memory.

## Patterns

### Mechanism Selection

| Mechanism      | Use for                                              | Example                            |
| -------------- | ---------------------------------------------------- | ---------------------------------- |
| useState       | Independent component-local values                   | Toggle, single input               |
| useReducer     | Related local fields with coupled transitions        | Multi-field form, state machine    |
| Context *or* tiny Zustand | Low-frequency, app-wide identity                | Theme, auth user, locale           |
| Zustand        | Shared client state across unrelated components      | Cart, toast queue, UI prefs        |
| Jotai          | Many independent atoms read by different consumers   | Per-row selection in a large grid  |
| Redux Toolkit  | Large team needing middleware, time-travel, sagas    | Complex workflows, audited apps    |
| URL            | Shareable, bookmarkable, back-button-safe state      | Filters, sort, page, search query  |
| TanStack Query | Server data (fetch, cache, revalidate)               | User profile, product list         |

Identity values (theme, auth, locale) work in either Context or a tiny Zustand store. Pick Context when the value is set once at the app shell; pick a store when multiple writers / persistence / devtools matter.

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
  total: () => number;
};

export const useCart = create<CartStore>((set, get) => ({
  items: [],
  add: (i) => set((s) => ({ items: [...s.items, i] })),
  remove: (id) => set((s) => ({ items: s.items.filter((x) => x.id !== id) })),
  total: () => get().items.reduce((n, i) => n + i.price * i.quantity, 0),
}));

// Subscribe to the slice you read, not the whole store.
const count = useCart((s) => s.items.length);
```

Add `persist` only when reload must preserve state; add `devtools` in development. Stores stay flat per domain - do not nest `cart`, `auth`, `ui` inside one store.

### Context re-render pitfall

```tsx
// Bad - every keystroke re-renders every consumer of FormContext.
const FormContext = createContext<{ values: Record<string,string>; set: (k:string,v:string)=>void }>(...);

// Good - form values in useReducer / React Hook Form / Zustand; Context holds only stable identity.
const AuthContext = createContext<{ user: User; logout: () => void }>(...);
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
    next.set("page", "1"); // filter change resets page
    router.push(`${path}?${next}`);
  };
}
```

Read filters directly from `searchParams` per render - that *is* the source of truth.

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

Use only when the project already needs middleware (sagas, RTK Query already in tree, undo/redo, cross-cutting logging). For a greenfield slice, Zustand is shorter and cheaper.

## Output Format

```
## React State Architecture

Stack: {framework}
Primary library: {Zustand | Redux Toolkit | Jotai | Context-only}

### State Map

| Slice           | Category   | Owner            | Mechanism        | Rationale            |
| --------------- | ---------- | ---------------- | ---------------- | -------------------- |
| {slice name}    | {Local UI | Shared UI | Server | URL | Identity} | {component/store} | {mechanism}    | {1-line why}         |

### Stores

| Store        | Domain    | Persisted | Middleware           |
| ------------ | --------- | --------- | -------------------- |
| {name}       | {domain}  | {Yes|No}  | {devtools, persist}  |

### Findings

- Severity: {Critical | High | Medium | Low}
  Issue: {Wrong-Mechanism | Server-State-In-Store | Context-Re-render | Mega-Store | Stored-Derived | Mutation | URL-Candidate}
  Location: {file/component or "design"}
  Fix: {one-line action}
```

If the project has no React sources, emit `Findings: none (no React detected)` and stop.

## Avoid

- Server data in Zustand/Redux/Context - use TanStack Query / SWR.
- Context for inputs, mouse, scroll, drag, animation - re-renders every consumer.
- One mega-store/mega-context coupling unrelated domains.
- Storing derived values (totals, filtered lists) instead of computing in a selector.
- Reaching for Redux when useState + one Zustand store would do.
- Mirroring URL state into memory - the URL is the source.
- Prop drilling past 2 levels when a store or scoped context fits.
