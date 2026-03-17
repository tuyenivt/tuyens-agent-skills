---
name: react-state-patterns
description: React-specific state management - useState/useReducer, Zustand (primary), Redux Toolkit (enterprise), Jotai (atomic), context pitfalls, and state library selection for React 19+.
metadata:
  category: frontend
  tags: [react, state, zustand, redux-toolkit, jotai, context, useReducer]
user-invocable: false
---

# React State Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing a state management approach for a React feature
- Deciding between local state, context, and external stores
- Selecting a state library (Zustand, Redux Toolkit, Jotai)
- Reviewing existing state management for performance or correctness issues
- Migrating from one state management approach to another

## Rules

- Start with the simplest state mechanism - upgrade only when proven necessary (useState > useReducer > Zustand > Redux Toolkit)
- Context is for low-frequency values (theme, auth, locale) - never for high-frequency updates (form fields, mouse position, animations)
- Server state belongs in TanStack Query / SWR - not in Zustand or Redux
- Every Zustand store must have a clear domain boundary - one store per domain, not one store for the entire app
- Derived state must be computed via selectors - never stored separately
- State updates must be immutable - no direct mutation even when the library allows it

## Patterns

### State Mechanism Selection

| Mechanism      | When to Use                                         | Example                            |
| -------------- | --------------------------------------------------- | ---------------------------------- |
| useState       | Simple, component-local state                       | Toggle, input value, local flag    |
| useReducer     | Complex local state with multiple related updates   | Multi-field form, state machine    |
| Context        | Low-frequency global values                         | Theme, auth user, locale           |
| Zustand        | Shared client state across components               | Shopping cart, UI preferences      |
| Redux Toolkit  | Enterprise apps needing middleware, devtools, sagas | Large team, complex workflows      |
| Jotai          | Fine-grained atomic state                           | Independent pieces of shared state |
| URL state      | State that should survive refresh/share             | Filters, sort, pagination, search  |
| TanStack Query | Server state (API data)                             | User profile, product list         |

### useState and useReducer

**useState** for independent state values:

```tsx
const [isOpen, setIsOpen] = useState(false);
const [search, setSearch] = useState("");
```

**useReducer** for related state with complex transitions:

```tsx
interface FilterState {
  category: string;
  priceRange: [number, number];
  sortBy: string;
  page: number;
}

type FilterAction =
  | { type: "SET_CATEGORY"; category: string }
  | { type: "SET_PRICE_RANGE"; range: [number, number] }
  | { type: "SET_SORT"; sortBy: string }
  | { type: "RESET" };

function filterReducer(state: FilterState, action: FilterAction): FilterState {
  switch (action.type) {
    case "SET_CATEGORY":
      return { ...state, category: action.category, page: 1 }; // reset page on filter change
    case "SET_PRICE_RANGE":
      return { ...state, priceRange: action.range, page: 1 };
    case "SET_SORT":
      return { ...state, sortBy: action.sortBy };
    case "RESET":
      return initialState;
  }
}
```

### Zustand (Primary Recommendation)

```tsx
import { create } from "zustand";
import { devtools, persist } from "zustand/middleware";

interface CartStore {
  items: CartItem[];
  addItem: (item: CartItem) => void;
  removeItem: (id: string) => void;
  clearCart: () => void;
  total: () => number;
}

const useCartStore = create<CartStore>()(
  devtools(
    persist(
      (set, get) => ({
        items: [],
        addItem: (item) =>
          set(
            (state) => ({ items: [...state.items, item] }),
            false,
            "cart/addItem", // action name for devtools
          ),
        removeItem: (id) =>
          set(
            (state) => ({ items: state.items.filter((i) => i.id !== id) }),
            false,
            "cart/removeItem",
          ),
        clearCart: () => set({ items: [] }, false, "cart/clear"),
        total: () =>
          get().items.reduce(
            (sum, item) => sum + item.price * item.quantity,
            0,
          ),
      }),
      { name: "cart-storage" }, // localStorage key
    ),
    { name: "CartStore" }, // devtools label
  ),
);

// Usage with selectors (prevents unnecessary re-renders)
function CartCount() {
  const count = useCartStore((state) => state.items.length);
  return <span>{count}</span>;
}

function CartTotal() {
  const total = useCartStore((state) => state.total());
  return <span>${total.toFixed(2)}</span>;
}
```

### Redux Toolkit (Enterprise)

```tsx
import { createSlice, configureStore } from "@reduxjs/toolkit";

const cartSlice = createSlice({
  name: "cart",
  initialState: { items: [] as CartItem[] },
  reducers: {
    addItem: (state, action: PayloadAction<CartItem>) => {
      state.items.push(action.payload); // Immer handles immutability
    },
    removeItem: (state, action: PayloadAction<string>) => {
      state.items = state.items.filter((i) => i.id !== action.payload);
    },
  },
});

const store = configureStore({
  reducer: { cart: cartSlice.reducer },
});

// Typed hooks
type RootState = ReturnType<typeof store.getState>;
type AppDispatch = typeof store.dispatch;

const useAppSelector = useSelector.withTypes<RootState>();
const useAppDispatch = useDispatch.withTypes<AppDispatch>();
```

### Context Pitfalls

**Bad** - Context for high-frequency updates:

```tsx
const FormContext = createContext<{
  values: Record<string, string>;
  onChange: (field: string, value: string) => void;
}>({ values: {}, onChange: () => {} });

// Every keystroke re-renders ALL consumers of FormContext
```

**Good** - Context for low-frequency values only:

```tsx
// Theme changes rarely - context is appropriate
const ThemeContext = createContext<{
  theme: "light" | "dark";
  toggle: () => void;
}>({
  theme: "light",
  toggle: () => {},
});

// For form values, use React Hook Form, Zustand, or local state
```

### URL State

Sync state with URL for shareable, bookmarkable UI:

```tsx
// Next.js - useSearchParams
"use client";
import { useSearchParams, useRouter, usePathname } from "next/navigation";

function ProductFilters() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  function setFilter(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    params.set(key, value);
    params.set("page", "1"); // reset page on filter change
    router.push(`${pathname}?${params.toString()}`);
  }

  const category = searchParams.get("category") || "all";
  const sort = searchParams.get("sort") || "name";
  // render filters...
}
```

## Output Format

Consuming workflow skills depend on this structure.

```
## React State Architecture

**Stack:** {detected framework}
**State library:** {Zustand | Redux Toolkit | Jotai | Context only}

### State Map

| State          | Category   | Owner             | Mechanism               |
| -------------- | ---------- | ----------------- | ----------------------- |
| {state name}   | Local UI   | {component}       | useState                |
| {state name}   | Shared UI  | {store/context}   | Zustand                 |
| {state name}   | Server     | -                 | TanStack Query          |
| {state name}   | URL        | -                 | useSearchParams         |

### Stores

| Store          | Domain         | Persisted | Middleware    |
| -------------- | -------------- | --------- | ------------- |
| {storeName}    | {domain}       | {Yes|No}  | {devtools, persist} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Using Redux for simple apps that only need useState + Context (unnecessary complexity)
- Putting server state (API data) in Zustand or Redux (use TanStack Query)
- Using Context for high-frequency updates (every consumer re-renders on every change)
- Creating one mega-store for the entire application (couples unrelated domains)
- Storing derived values instead of computing them with selectors
- Direct state mutation without the library's update mechanism
- Using Redux without Redux Toolkit (too much boilerplate)
- Prop drilling through more than 2 levels when a store or context would be cleaner
