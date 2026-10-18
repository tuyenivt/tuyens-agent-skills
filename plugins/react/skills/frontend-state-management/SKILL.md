---
name: frontend-state-management
description: Place and structure Next.js client state: local vs global, lifting, URL state, derived state, normalization, server vs client ownership.
metadata:
  category: frontend
  tags: [frontend, state, redux, zustand, url-state, nextjs]
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
- Server state and client UI state have separate owners: server data in Server Components (a client query cache only for data fetched interactively), UI state in component state or a store
- Derived values are computed, not stored (stored derivations drift)
- Normalize entity collections to avoid nested duplicates
- Never mutate state outside the designated mutation mechanism

---

## Patterns

### State Classification

Classify each piece of state before choosing a tool:

| Category     | Scope                       | Examples                          | Lives In                          |
| ------------ | --------------------------- | --------------------------------- | --------------------------------- |
| Local UI     | Single component            | Open/closed, hover, input value   | Component state (`useState`)      |
| Shared UI    | Siblings/cousins            | Active tab, selected item, filter | Nearest common ancestor           |
| Global UI    | App-wide                    | Theme, locale, sidebar collapsed  | Global store or context           |
| Server       | Cached backend data         | User profile, product list, the signed-in user (a Context only carries it to Client Components) | Server Component props; client query cache for interactive data |
| URL          | Synced to URL               | Page, query, sort                 | URL search params (`await searchParams` page prop, `useSearchParams`) |
| Form         | Inputs, validation, dirty   | Field values, errors, touched     | Form library or local state       |
| Transient    | Ephemeral, never persisted  | Animation progress, scroll pos    | A non-reactive holder (React `useRef`, a plain variable) |

State owned outside the app - a global a legacy script writes, a host page's variable - takes the category its *use* fits with Owner naming the external writer; the finding is the missing single owner, not the category. Persistence (reload survival) and cross-browser-tab sync are layers on an existing owner, not new owners: keep the state in its category's home and attach a persist plugin / storage adapter, with storage events for a localStorage-backed owner (they fire only on storage writes in other tabs) and BroadcastChannel for everything else, such as telling other tabs to invalidate a query cache. State whose owner differs by session (guest in local storage, signed-in on the server) takes one State Map row per owner; the hand-off at login (post the local entries, then clear the local owner) is a Recommendation.

URL is the one owner the user can write directly - back button, pasted link, bookmark. Treat navigation as an inbound mutation: read from the URL on every render rather than seeding a copy on mount, or a bookmark opens the app with the wrong state and the back button silently desyncs.

### When to Lift State

Lift only when:
1. Two or more children read the same value
2. A child must update a value a sibling reads
3. State must survive a child's mount/unmount - not route navigation under `cacheComponents: true`, where Activity already keeps a left route's state (Next keeps up to 3 route entries per layout segment, the visible one included, so at most 2 left routes stay hidden)

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

Lifting can create prop drilling. Passing through 2-3 layers is fine; deeper, escalate in order: component composition (`children`), then context for low-frequency values. Drilling depth alone never reaches a store - a store needs the lift conditions above plus a genuinely app-wide reader (the one exception: a high-frequency external feed, Next.js Bindings).

### Derived State

```
// Bad: stored, manually kept in sync, drifts out of date
store.items = [...]
store.itemCount = store.items.length
store.totalPrice = store.items.reduce((s, i) => s + i.price, 0)

// Good: single source of truth; derived values always fresh.
// Compute in render, or in a store selector.
const itemCount = useStore((s) => s.items.length)
const totalPrice = useStore((s) => s.items.reduce((n, i) => n + i.price, 0))
```

Memoize expensive derivations (large filter/sort/group): Redux `createSelector`; in Zustand, select the source slice and derive with `useMemo` - `useShallow` only stabilises a small derived array or object (it prevents the loop, not the recomputation), and a selector that returns a new array or object on every call loops in Zustand 5 (`Maximum update depth exceeded`). Trivial derivations (`.length`, booleans) need no memoization.

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

Same idea in Redux (`useSelector`) and Zustand (selector argument).

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

Server data is fetched in Server Components and passed down as props; Server Actions change it and refresh it (`updateTag`, `revalidatePath`). A client query library (TanStack Query, SWR, Apollo) owns only data the client fetches interactively. Neither belongs in a UI store: mixing the two means manual cache invalidation, stale reads, and duplicated loading-state machinery.

```
// Bad: API data and UI state mixed
store.theme = "dark"
store.users = await fetchUsers()
store.usersLoading = false

// Good: UI store for client state; server data from a Server Component, passed as props
setTheme("dark")                        // client: through the store's setter
<UserList users={await fetchUsers()} /> // server: useQuery only when the list is fetched interactively
```

**Optimistic updates** look like an exception to one-owner - a client prediction of server state - but they are not: the owner stays the server-data owner (the query cache, or the Server Component props a Server Action refreshes), and the prediction is layered on it, then rolled back or reconciled on the response. Use the data layer's own mechanism (TanStack Query `onMutate` with a snapshot for rollback, SWR `optimisticData`, Apollo `optimisticResponse`, `useOptimistic` around a Server Action). A parallel `optimisticItems` array in a UI store creates the second owner the rule forbids, and every rendering component then has to merge two sources in the right order.

### Migrating Between Approaches

First decide what actually hurts. Boilerplate, devtools, and bundle size are library problems a migration fixes; duplicated owners, stored derivations, and server data in a UI store are architecture problems that survive any migration - porting reducers one-for-one into a new library reproduces every one of them.

Migrate by slice, never wholesale: move server state out first - into Server Components, or a query library for interactive data (usually the largest win and independent of which store you keep), then move one feature's slice at a time, running both stores during the transition with each piece of state owned by exactly one of them. A slice is done when nothing reads it from the old store.

## Next.js Bindings

- `useState`/`useReducer` local; Zustand or Redux Toolkit for app-wide client state; Context (`<ThemeContext value={...}>`) for low-frequency global values (theme, auth)
- Server data in Server Components; TanStack Query for interactive client data
- Stores exist only in Client Components; a module-scope store is shared across server requests, so create it per request behind a provider (`react-state-patterns` owns the details). A new feature's slices join the existing store of their domain; a new store needs a different lifetime or persistence, never just a new feature. A high-frequency external feed (WebSocket presence, remote cursors) is the one Shared UI value whose Owner is a store, because update frequency, not reader count, decides it: the socket handler writes it outside React (`store.setState` in Zustand, `store.dispatch` in Redux Toolkit) and readers subscribe by selector. While `pages/` and `app/` both serve routes, each tree mounts that provider (`_app` and the root layout) over the same store factory

---

## Output Format

Consuming workflow skills depend on this structure.

```
## State Management Assessment

**Stack:** {Framework and Language as a display name (`Next.js 16.3 / TypeScript` for stack-detect's `React (Next.js)`) - the major.minor from the owning app's `package.json` (`^16.3.0` -> 16.3); with no `tsconfig.json`, the extensions of the files in scope decide JS vs TS, overriding stack-detect's Language; in a monorepo, the app owning the reviewed code; `unknown` for a part that is inconclusive}

**State library:** {detected or recommended library; list each when more than one is in use and mark any that is installed but unread `(unused)` - a library reached through an import in scope counts as read; a theming or query library counts only when it owns a State Map row; write `{current} -> {target}` in migration mode}

### State Map

| State        | Category   | Owner                     | Mechanism                       |
| ------------ | ---------- | ------------------------- | ------------------------------- |
| {state name} | {category} | {component or store name} | {useState / Zustand / Redux Toolkit / Server Component / ...} |

### Recommendations {when at least one applies}

- {recommendation with rationale}

### Issues Found {when at least one finding}

- [Severity: High | Medium | Low] {description}
  - Location: {file}:{line}[, {file}:{line}], or `design` for a planned owner with no file yet
  - Problem: {what is wrong}
  - Fix: {concrete correction for the detected stack}

### No Issues Found {instead, when none}

{one sentence: in review mode, state management is adequate for the scope reviewed; in design mode, the proposed placement carries no residual risk; in migration mode, the target placement introduces no new owner or stored derivation}

Not assessed: {input the review needed but never saw - a file referenced but not provided, a module whose behaviour decides a severity, a symptom whose trigger lies outside scope; never a guessed finding; omit when none}

Notes: {observations outside this skill's concern, each naming the owning concern; omit when none}
```

Order Issues Found by severity, highest first; within a band, file order (the order the input lists the files; ascending line within a file). `Location` lists every `file:line` one root cause spans, comma-separated; the lead file is the one the fix changes (the recommended owner's file when the fix is an owner decision; the earliest in file order on a tie), and the finding sorts by it. `stack-detect` has no field for this: read `State library` from `package.json` dependencies (the owning app's manifest in a monorepo) and the imports in the files in scope. Two owners merging keep the one most readers already use (reader counts unknown: the one in the category's `Lives In` column; where that column offers two, the one its condition selects - Server: Server Component props unless the client fetches the data interactively - else the one already in use in scope); the Fix names it. The State Map covers the state in scope - the change's touched state when reviewing, the feature's state when designing or migrating - never a whole-app inventory. In review mode, `Owner` is the current owner; the recommended owner goes in the issue's Fix. In migration mode, write `Owner` as `{current} -> {target}` so the table is the migration map, and Issues Found carries the architecture problems the migration would otherwise carry over (all pre-existing by definition, so the marker is omitted; a field nothing reads or an action nothing dispatches is Low, Fix `remove`). In design mode (new feature, no code yet), `Owner` is the planned owner and Issues Found carries residual risks knowingly accepted. In review or design mode, when the build or design touches existing code, defects already in it are ordinary Issues Found entries marked `(pre-existing)` at their own severity; the residual-risk reading covers only the new work. Severity calibration: High = correctness or staleness bugs (server data held in a UI store, stored derived values, multiple owners of one piece of state - including a URL value copied into `useState`; a Zustand selector returning a new array or object that `useShallow` does not stabilise - none applied, or fresh objects inside it - a render loop); Medium = performance or maintainability (form drafts in global store, whole-store subscriptions, missing memoization of expensive derivations, URL-shaped state held outside the URL, two client-state libraries in use with no piece of state held in both); Low = style and minor structure.

---

## Avoid

- Global state for values only one component reads
- Context for high-frequency updates (re-renders all consumers)
- Spinning up a new global store per feature (proliferation)
