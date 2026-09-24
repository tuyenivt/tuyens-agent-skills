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

State owned outside the app - a global a legacy script writes, a host page's variable - takes the category its *use* fits with Owner naming the external writer; the finding is the missing single owner, not the category. Persistence (reload survival) and cross-browser-tab sync are layers on an existing owner, not new owners: keep the state in its category's home and attach a persist plugin / storage adapter, with storage events for a localStorage-backed owner (they fire only on storage writes in other tabs) and BroadcastChannel for everything else, such as telling other tabs to invalidate a query cache. State whose owner differs by session (guest in local storage, signed-in on the server) takes one State Map row per owner; the hand-off at login (post the local entries, then clear the local owner) is a Recommendation.

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

Same idea in Redux (`useSelector`) and Zustand (selector argument). Pinia and Angular signals need no equivalent: Pinia tracks per property and signals are per-signal, so each re-renders only for what it reads; `storeToRefs` keeps reactivity when destructuring rather than narrowing a subscription. NgRx Store is Observable-based and does need it - narrow with `store.select` / `selectSignal`.

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
setTheme("dark")                       // through the store's setter (Pinia and Vue refs take direct assignment)
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

For any framework not bound above - `unknown`, or a detected one such as Svelte or Solid - apply the universal patterns and point the user to that framework's state docs.

---

## Output Format

Consuming workflow skills depend on this structure.

```
## State Management Assessment

**Stack:** {Framework and Language as a display name (`Next.js 15.5 / TypeScript` for stack-detect's `React (Next.js)`) - the major.minor from the owning app's `package.json` (`^15.5.0` -> 15.5); with no `tsconfig.json`, the extensions of the files in scope decide JS vs TS, overriding stack-detect's Language; in a monorepo, the app owning the reviewed code; "unknown - universal patterns applied" when inconclusive}

**State library:** {detected or recommended library; list each when more than one is in use and mark any that is installed but unread `(unused)` - a library reached through an import in scope counts as read; write `{current} -> {target}` in migration mode}

### State Map

| State        | Category   | Owner                     | Mechanism                       |
| ------------ | ---------- | ------------------------- | ------------------------------- |
| {state name} | {category} | {component or store name} | {useState / Pinia / NgRx / ...} |

### Recommendations {when at least one applies}

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Location: {file}:{line}, or `design` for a planned owner with no file yet
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack, or the universal pattern when the stack is unknown}

### No Issues Found

{Emit only when Issues Found is empty: in review mode state that the state management is adequate; in design mode that the proposed placement carries no residual risk; in migration mode that the target placement introduces no new owner or stored derivation}

Not assessed: {input the review needed but never saw - a file referenced but not provided, a module whose behaviour decides a severity, a symptom whose trigger lies outside scope; never a guessed finding; omit when none}

Notes: {observations outside this skill's concern, each naming the owning concern; omit when none}
```

Include exactly one of `Issues Found` / `No Issues Found`. A clean run emits every header field, the in-scope table, `Recommendations` when any apply, and `No Issues Found`; only the `Issues Found` blocks are omitted. Order Issues Found by severity, highest first; within a band, file order (the order the input lists the files; ascending line within a file). `Location` may list several `file:line` entries (or several lines of one file), comma-separated, when one root cause spans them; lead with the file the fix changes (the recommended owner's file when the fix is an owner decision; the earliest in file order on a tie), and sort the finding by that lead file. `stack-detect` has no field for this (it carries versions only when a `## Tech Stack` section declares them): read `State library` (framework-built-in stores such as Nuxt `useState` count) from `package.json` dependencies (the owning app's manifest in a monorepo) and the imports in the files in scope. Two owners merging keep the one most readers already use; the Fix names it. The State Map covers the state in scope - the change's touched state when reviewing, the feature's state when designing or migrating - never a whole-app inventory. In review mode, `Owner` is the current owner; the recommended owner goes in the issue's Fix. In migration mode, write `Owner` as `{current} -> {target}` so the table is the migration map, and Issues Found carries the architecture problems the migration would otherwise carry over. In design mode (new feature, no code yet), `Owner` is the planned owner and Issues Found carries residual risks knowingly accepted. When the build or design touches existing code, defects already in it are ordinary Issues Found entries marked `(pre-existing)` at their own severity; the residual-risk reading covers only the new work. Severity calibration: High = correctness or staleness bugs (duplicated server state, stored derived values, multiple owners); Medium = performance or maintainability (form drafts in global store, whole-store subscriptions, missing memoization of expensive derivations, URL-shaped state held outside the URL, two client-state libraries serving overlapping concerns); Low = style and minor structure.

---

## Avoid

- Global state for values only one component reads
- Storing derived values instead of computing them
- Mixing server and client state in one store
- Duplicating entity data across stores or nested structures
- Context for high-frequency updates (re-renders all consumers)
- Spinning up a new global store per feature (proliferation)
- In-place mutation in an immutable-update store (Redux, Zustand, NgRx) or of a signal's value without `set`/`update` (breaks change detection and devtools); in Pinia and Vue, direct assignment is the mechanism
