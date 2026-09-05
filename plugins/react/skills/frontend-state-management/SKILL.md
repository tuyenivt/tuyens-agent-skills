---
name: frontend-state-management
description: Place and structure frontend state: local vs global, lifting, derived state, normalization. Adapts to detected stack and store library.
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
| Local UI     | Single component            | Open/closed, hover, input value   | Component state (useState/`ref` in Vue) |
| Shared UI    | Siblings/cousins            | Active tab, selected item, filter | Nearest common ancestor           |
| Global UI    | App-wide                    | Theme, locale, sidebar collapsed  | Global store or context           |
| Server       | Cached backend data         | User profile, product list        | Data-fetching library cache       |
| URL          | Synced to URL               | Page, query, sort                 | Router / URL search params        |
| Form         | Inputs, validation, dirty   | Field values, errors, touched     | Form library or local state       |
| Transient    | Ephemeral, never persisted  | Animation progress, scroll pos    | A non-reactive holder (React `useRef`, a plain variable) |

State owned outside the app - a global a legacy script writes, a host page's variable - takes the category its *use* fits with Owner naming the external writer; the finding is the missing single owner, not the category. Persistence (reload survival) and cross-browser-tab sync are layers on an existing owner, not new owners: keep the state in its category's home and attach a persist plugin / storage adapter, with BroadcastChannel or storage events for cross-tab sync.

URL is the one owner the user can write directly - back button, pasted link, bookmark. Treat navigation as an inbound mutation: read from the URL on every render rather than seeding a copy on mount, or a bookmark opens the app with the wrong state and the back button silently desyncs.

### When to Lift State

Lift only when:
1. Two or more children read the same value
2. A child must update a value a sibling reads
3. State must survive a child's mount/unmount

```
// Bad: every UI flag in a global store
globalStore.setModalOpen(true)
globalStore.setTooltipVisible(false)

// Good: lifted only because two children read the same value
function ProductPage() {
  const [filters, setFilters] = useState({ category: "all" })
  return (
    <>
      <Filters value={filters} onChange={setFilters} />
      <ProductList filters={filters} />
    </>
  )
}
```

Lifting can create prop drilling. Passing through 2-3 layers is fine; deeper, escalate in order: component composition (children/slots), then context or provide/inject for low-frequency values. Drilling depth alone never reaches a store - a store needs the lift conditions above plus a genuinely app-wide reader.

### Derived State

```
// Bad: stored, manually kept in sync, drifts out of date
store.items = [...]
store.itemCount = store.items.length
store.totalPrice = store.items.reduce((s, i) => s + i.price, 0)

// Good: single source of truth; derived values always fresh.
// React: compute in render, or a store selector. Vue: computed(). Angular: a computed signal.
const itemCount = useStore((s) => s.items.length)
const totalPrice = useStore((s) => s.items.reduce((n, i) => n + i.price, 0))
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

Same idea in Redux (`useSelector`) and Zustand (selector argument). Vue and Angular need no equivalent: Pinia tracks per property and signals are per-signal, so each re-renders only for what it reads. `storeToRefs` keeps reactivity when destructuring rather than narrowing a subscription; NgRx narrows with `store.select`/`selectSignal`.

**React Context note:** Context re-renders all consumers when the value object changes. Split into focused contexts (Theme, Auth, Layout) or use a state library with selectors for high-frequency updates.

### Normalization

For entity collections, normalize to prevent nested duplicates and update anomalies:

```
// Bad: Alice duplicated across orders
{ orders: [{ id: 1, user: { id: 10, name: "Alice" } }, { id: 2, user: { id: 10, name: "Alice" } }] }

// Good: entities by ID, relationships by reference
{
  users:  { byId: { 10: { id: 10, name: "Alice" } }, ids: [10] },
  orders: { byId: { 1: { id: 1, userId: 10 }, 2: { id: 2, userId: 10 } }, ids: [1, 2] },
}
// Keep the `ids` array: object keys that look like integers enumerate in numeric order,
// so a keys-only shape silently loses the collection's order.
```

Normalize large or mutable collections. Small read-only nested data is fine as-is.

### Server vs Client State

Server state (API data) belongs in a data-fetching library (TanStack Query, SWR, Apollo, Nuxt `useAsyncData`), not a UI store. Mixing the two means manual cache invalidation, stale reads, and duplicated loading-state machinery.

```
// Bad: API data and UI state mixed
store.theme = "dark"
store.users = await fetchUsers()
store.usersLoading = false

// Good: UI store for client state; query library for server state
setTheme("dark")                       // through the store's own setter, never direct assignment
const { data: users, isPending } = useQuery({ queryKey: ["users"], queryFn: fetchUsers })
```

**Optimistic updates** look like an exception to one-owner - a client prediction of server state - but they are not: the owner stays the query cache, and the prediction is written *into* it, then rolled back or reconciled on the response. Use the data layer's own mechanism (TanStack Query `onMutate` with a snapshot for rollback, SWR `optimisticData`, Apollo `optimisticResponse`). A parallel `optimisticItems` array in a UI store creates the second owner the rule forbids, and every rendering component then has to merge two sources in the right order.

### Migrating Between Approaches

First decide what actually hurts. Boilerplate, devtools, and bundle size are library problems a migration fixes; duplicated owners, stored derivations, and server data in a UI store are architecture problems that survive any migration - porting reducers one-for-one into a new library reproduces every one of them.

Migrate by slice, never wholesale: move server state out to a query library first (usually the largest win and independent of which store you keep), then move one feature's slice at a time, running both stores during the transition with each piece of state owned by exactly one of them. A slice is done when nothing reads it from the old store.

## Stack-Specific Guidance

After `stack-detect`, apply patterns using ecosystem idioms:

- **React**: `useState`/`useReducer` local; Zustand or Redux Toolkit global; TanStack Query for server; Context for low-frequency global (theme, auth)
- **Vue**: `ref`/`reactive` local; Pinia global; composable stores; Nuxt `useAsyncData` or TanStack Query Vue for server
- **Angular**: Signals local/shared; NgRx for app-wide state, `@ngrx/signals` SignalStore or `@ngrx/component-store` for feature state; RxJS `BehaviorSubject` for service state; `toSignal` to bridge observables

For unknown stacks, apply universal patterns and point the user to the framework's state docs.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## State Management Assessment

**Stack:** {detected language / framework}

**State library:** {detected or recommended library; list each when more than one is in use and mark any that is installed but unread `(unused)`; write `{current} -> {target}` in migration mode}

### State Map

| State        | Category   | Owner                     | Mechanism                       |
| ------------ | ---------- | ------------------------- | ------------------------------- |
| {state name} | {category} | {component or store name} | {useState / Pinia / NgRx / ...} |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Location: {file}:{line}
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack, or the universal pattern when the stack is unknown}

### No Issues Found

{Emit only when Issues Found is empty: in review mode state that the state management is adequate; in design mode state that the proposed placement carries no residual risk}
```

Include exactly one of `Issues Found` / `No Issues Found`. A clean run emits every header field, the in-scope table, `Recommendations` when any apply, and `No Issues Found`; only the `Issues Found` blocks are omitted. Order Issues Found by severity, highest first; within a band, file order. The State Map covers the state in scope - the change's touched state when reviewing, the feature's state when designing or migrating - never a whole-app inventory. In review mode, `Owner` is the current owner; the recommended owner goes in the issue's Fix. In migration mode, write `Owner` as `{current} -> {target}` so the table is the migration map. In design mode (new feature, no code yet), `Owner` is the planned owner and Issues Found carries only residual risks knowingly accepted. Severity calibration: High = correctness or staleness bugs (duplicated server state, stored derived values, multiple owners); Medium = performance or maintainability (form drafts in global store, whole-store subscriptions, missing memoization of expensive derivations); Low = style and minor structure.

---

## Avoid

- Global state for values only one component reads
- Storing derived values instead of computing them
- Mixing server and client state in one store
- Duplicating entity data across stores or nested structures
- Context for high-frequency updates (re-renders all consumers)
- Spinning up a new global store per feature (proliferation)
- Direct mutation outside reducers/actions/signals (breaks reactivity and devtools)
