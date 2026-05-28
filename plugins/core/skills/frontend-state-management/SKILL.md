---
name: frontend-state-management
description: Frontend state management: local vs global, lifting state, derived state, normalization. Adapts to detected stack and store library.
metadata:
  category: frontend
  tags: [frontend, state, redux, pinia, ngrx, zustand, signals, multi-stack]
user-invocable: false
---

# Frontend State Management

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing state architecture for a feature or app
- Deciding where state lives (component, shared, global, server)
- Reviewing existing state for complexity, duplication, staleness bugs
- Migrating between state approaches

## Rules

- Each piece of state has exactly one owner; no duplication across stores
- Prefer the least powerful mechanism that works (local > shared > global)
- Server state and client UI state live in separate stores
- Derived values are computed, not stored (stored derivations drift)
- Normalize entity collections to avoid nested duplicates
- Never mutate state outside the designated mutation mechanism

---

## Patterns

### State Classification

Classify each piece of state before choosing a tool:

| Category     | Scope                       | Examples                          | Lives In                          |
| ------------ | --------------------------- | --------------------------------- | --------------------------------- |
| Local UI     | Single component            | Open/closed, hover, input value   | Component state (useState, ref)   |
| Shared UI    | Siblings/cousins            | Active tab, selected item, filter | Nearest common ancestor           |
| Global UI    | App-wide                    | Theme, locale, sidebar collapsed  | Global store or context           |
| Server       | Cached backend data         | User profile, product list        | Data-fetching library cache       |
| URL          | Synced to URL               | Page, query, sort                 | Router / URL search params        |
| Form         | Inputs, validation, dirty   | Field values, errors, touched     | Form library or local state       |
| Transient    | Ephemeral, never persisted  | Animation progress, scroll pos    | Refs or local variables           |

### When to Lift State

Lift only when:
1. Two or more children read the same value
2. A child must update a value a sibling reads
3. State must survive a child's mount/unmount

```
// Bad: every UI flag in a global store
globalStore.setModalOpen(true)
globalStore.setTooltipVisible(false)

// Good: local where possible, lifted only where coordination is needed
const [isOpen, setIsOpen] = useState(false)
<ProductPage>
  <Filters value={filters} onChange={setFilters} />
  <ProductList filters={filters} />
</ProductPage>
```

### Derived State

```
// Bad: stored, manually kept in sync, drifts out of date
store.items = [...]
store.itemCount = store.items.length
store.totalPrice = store.items.reduce((s, i) => s + i.price, 0)

// Good: single source of truth; derived values always fresh
const itemCount = computed(() => store.items.length)
const totalPrice = computed(() => store.items.reduce((s, i) => s + i.price, 0))
```

Memoize expensive derivations (large filter/sort/group) with selectors (`useMemo`, Vue `computed`, Angular `computed` signal, `createSelector`). Trivial derivations (`.length`, booleans) need no memoization.

### Selector Pattern

Subscribe to slices, not whole stores, to avoid unnecessary re-renders:

```
// Bad: re-renders on any store change
const state = useStore()
return <div>Theme: {state.theme}</div>

// Good: re-renders only on theme change
const theme = useStore(s => s.theme)
return <div>Theme: {theme}</div>
```

Same idea across libraries: Redux `useSelector`, Zustand selectors, Pinia `storeToRefs`.

**React Context note:** Context re-renders all consumers when the value object changes. Split into focused contexts (Theme, Auth, Layout) or use a state library with selectors for high-frequency updates.

### Normalization

For entity collections, normalize to prevent nested duplicates and update anomalies:

```
// Bad: Alice duplicated across orders
{ orders: [{ id: 1, user: { id: 10, name: "Alice" } }, { id: 2, user: { id: 10, name: "Alice" } }] }

// Good: entities by ID, relationships by reference
{
  users:  { 10: { id: 10, name: "Alice" } },
  orders: { 1: { id: 1, userId: 10 }, 2: { id: 2, userId: 10 } },
}
```

Normalize large or mutable collections. Small read-only nested data is fine as-is.

### Server vs Client State

Server state (API data) belongs in a data-fetching library (TanStack Query, SWR, Apollo, Nuxt `useAsyncData`), not a UI store. Mixing the two means manual cache invalidation, stale reads, and duplicated loading-state machinery.

```
// Bad: API data and UI state mixed
store.theme = "dark"
store.users = await fetch("/api/users")
store.usersLoading = false

// Good: UI store for client state; query library for server state
store.theme = "dark"
const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: fetchUsers })
```

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms:

- **React**: `useState`/`useReducer` local; Zustand or Redux Toolkit global; TanStack Query for server; Context for low-frequency global (theme, auth)
- **Vue**: `ref`/`reactive` local; Pinia global; composable stores; Nuxt `useAsyncData` or TanStack Query Vue for server
- **Angular**: Signals local/shared; NgRx or ComponentStore for complex global; RxJS `BehaviorSubject` for service state; `toSignal` to bridge observables

For unknown stacks, apply universal patterns and point the user to the framework's state docs.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## State Management Assessment

**Stack:** {detected language / framework}
**State library:** {detected or recommended library}

### State Map

| State        | Category   | Owner                     | Mechanism                       |
| ------------ | ---------- | ------------------------- | ------------------------------- |
| {state name} | {category} | {component or store name} | {useState / Pinia / NgRx / ...} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found

{State explicitly if state management is adequate - do not omit this section silently}
```

---

## Avoid

- Global state for values only one component reads
- Storing derived values instead of computing them
- Mixing server and client state in one store
- Duplicating entity data across stores or nested structures
- Context for high-frequency updates (re-renders all consumers)
- Spinning up a new global store per feature (proliferation)
- Direct mutation outside reducers/actions/signals (breaks reactivity and devtools)
