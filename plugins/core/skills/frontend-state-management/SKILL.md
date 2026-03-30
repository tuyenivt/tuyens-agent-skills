---
name: frontend-state-management
description: State management patterns for frontend applications - local vs global state, when to lift state, derived state, state normalization. Adapts to detected stack (Redux, Pinia, NgRx, Zustand, Jotai, signals, etc.).
metadata:
  category: frontend
  tags: [frontend, state, redux, pinia, ngrx, zustand, signals, multi-stack]
user-invocable: false
---

# Frontend State Management

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing state architecture for a new feature or application
- Deciding where state should live (component, shared, global, server)
- Reviewing existing state management for complexity or correctness
- Migrating between state management approaches

## Rules

- Every piece of state must have exactly one owner - no duplicated state across stores
- Prefer the least powerful state mechanism that solves the problem (local > shared > global)
- Server state (API data) and client state (UI state) must be managed separately
- Derived values must be computed, not stored - storing derived state causes staleness bugs
- State shape must be normalized for entities (no nested duplicates)
- Never mutate state directly outside the designated mutation mechanism (reducers, actions, signals)

---

## Patterns

### State Classification

Before choosing a tool, classify each piece of state:

| Category     | Scope                                | Examples                                  | Where It Lives                          |
| ------------ | ------------------------------------ | ----------------------------------------- | --------------------------------------- |
| Local UI     | Single component                     | Toggle open/closed, input value, hover    | Component state (useState, ref, signal) |
| Shared UI    | Sibling/cousin components            | Active tab, selected item, filter state   | Lifted to nearest common ancestor       |
| Global UI    | App-wide                             | Theme, locale, sidebar collapsed          | Global store or context                 |
| Server state | Cached backend data                  | User profile, product list, order history | Data-fetching library cache             |
| URL state    | Synced with browser URL              | Current page, search query, sort order    | Router / URL search params              |
| Form state   | Form inputs, validation, dirty flags | Field values, errors, touched state       | Form library or local state             |
| Transient    | Ephemeral, never persisted           | Animation progress, scroll position       | Refs or local variables                 |

### When to Lift State

Lift state to a parent only when:

1. Two or more children need to read the same value
2. A child needs to update a value that a sibling reads
3. The state must survive a child's mount/unmount cycle

**Bad** - Lifting everything to global:

```
// Every piece of UI state in a global store
globalStore.setModalOpen(true)
globalStore.setTooltipVisible(false)
globalStore.setDropdownIndex(2)
```

Problem: Global store becomes a dumping ground; unnecessary re-renders; hard to trace ownership.

**Good** - State lives at the appropriate level:

```
// Modal open/close is local to the component that owns it
const [isOpen, setIsOpen] = useState(false)

// Only shared filter state is lifted to the page that coordinates list + filters
<ProductPage>
  <Filters value={filters} onChange={setFilters} />
  <ProductList filters={filters} />
</ProductPage>
```

### Derived State

**Bad** - Storing computed values:

```
// Stored separately, must be manually kept in sync
store.items = [...]
store.itemCount = store.items.length
store.totalPrice = store.items.reduce((sum, i) => sum + i.price, 0)
```

Problem: `itemCount` and `totalPrice` can drift out of sync with `items`.

**Good** - Compute on read:

```
// Single source of truth; derived values are always fresh
store.items = [...]
const itemCount = computed(() => store.items.length)
const totalPrice = computed(() => store.items.reduce((sum, i) => sum + i.price, 0))
```

For expensive derivations (filtering, sorting, grouping large collections), use memoized selectors (`useMemo` in React, `computed` in Vue, `computed` signal in Angular, `createSelector` with Redux/Pinia) to avoid recomputation on every render. For trivial derivations (`.length`, boolean checks), direct computation is fine - no memoization needed.

### Selector Pattern

Subscribe to specific slices of global state rather than the entire store to avoid unnecessary re-renders:

**Bad** - Full store subscription:

```
// Re-renders on ANY store change, even unrelated fields
const state = useStore()
return <div>Theme: {state.theme}</div>
```

**Good** - Selective subscription:

```
// Re-renders only when theme changes
const theme = useStore(s => s.theme)
return <div>Theme: {theme}</div>
```

This applies across libraries: Redux `useSelector(s => s.theme)`, Zustand `useStore(s => s.theme)`, Pinia `storeToRefs(useStore())`.

**React Context performance note:** Context re-renders all consumers when the value object changes. Split large contexts into focused contexts (ThemeContext, AuthContext, LayoutContext) or use a state library with selectors instead.

### State Normalization

For entity collections (users, products, orders), normalize to prevent nested duplicates:

**Bad** - Nested / denormalized:

```
{
  orders: [
    { id: 1, user: { id: 10, name: "Alice" }, items: [...] },
    { id: 2, user: { id: 10, name: "Alice" }, items: [...] }  // Alice duplicated
  ]
}
```

**Good** - Normalized with IDs:

```
{
  users: { 10: { id: 10, name: "Alice" } },
  orders: {
    1: { id: 1, userId: 10, itemIds: [100, 101] },
    2: { id: 2, userId: 10, itemIds: [102] }
  },
  items: { 100: {...}, 101: {...}, 102: {...} }
}
```

Normalization is essential for large collections. For small, read-only data that is never updated in place, nested structures are acceptable.

### Server State Separation

Server state (data fetched from APIs) should not live in the same store as client UI state. Use a dedicated data-fetching library (TanStack Query, SWR, Apollo Client, useAsyncData) that handles:

- Caching and cache invalidation
- Background refetching
- Loading/error states
- Optimistic updates
- Deduplication of concurrent requests

**Bad** - API data in UI store:

```
// Global store holding both UI state and server data
store.theme = "dark"
store.sidebarOpen = true
store.users = await fetch("/api/users")  // server data mixed with UI state
store.usersLoading = false
```

**Good** - Separated concerns:

```
// UI store: only client state
store.theme = "dark"
store.sidebarOpen = true

// Server state: managed by data-fetching library
const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: fetchUsers })
```

## Stack-Specific Guidance

After loading stack-detect, apply state management patterns using the libraries and idioms of the detected ecosystem:

- **React**: useState/useReducer for local, Zustand or Redux Toolkit for global, TanStack Query for server state, Context for low-frequency global values (theme, auth)
- **Vue**: ref/reactive for local, Pinia for global, composable stores for domain logic, useFetch/useAsyncData (Nuxt) or TanStack Query Vue for server state
- **Angular**: Signals for local and shared state, NgRx or ComponentStore for complex global state, RxJS BehaviorSubject for service-based state, toSignal for bridging observables

If the detected stack is unfamiliar, apply the universal patterns above and recommend the user consult their framework's state management documentation.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## State Management Assessment

**Stack:** {detected language / framework}
**State library:** {detected or recommended state management library}

### State Map

| State                | Category    | Owner                     | Mechanism                    |
| -------------------- | ----------- | ------------------------- | ---------------------------- |
| {state name}         | {category}  | {component or store name} | {useState / Pinia / NgRx / ...} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description of state management issue}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if state management is adequate - do not omit this section silently}
```

---

## Avoid

- Using global state for values that only one component reads (unnecessary coupling and re-renders)
- Storing derived values instead of computing them (staleness bugs)
- Mixing server state and client state in the same store (cache invalidation becomes manual)
- Duplicating entity data across multiple stores or nested structures (update anomalies)
- Using context/provide-inject for high-frequency updates (performance degradation)
- Creating a new global store for every feature (store proliferation)
- Mutating state directly outside designated mutation mechanisms (breaks reactivity and devtools)
