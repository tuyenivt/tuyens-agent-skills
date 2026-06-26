---
name: react-overengineering-review
description: "Flag React overengineering: premature memo/useCallback, trivial Context, Redux for 2 fields, single-use custom hooks, generic HoC/compound for one consumer."
metadata:
  category: frontend
  tags: [react, overengineering, complexity, memoization, context, redux, custom-hooks, anti-patterns]
user-invocable: false
---

# React Overengineering Review

> Load `Use skill: stack-detect` first to determine the project stack. For framework-neutral complexity heuristics defer to `complexity-review`; this skill owns React-specific overengineering.

## When to Use

- Phase B (Code Quality) of `task-react-review` and `task-react-implement` post-merge checks
- Pre-step of `task-react-refactor` to surface simplifications before adding structure
- After AI-assisted scaffolding, when generated code reaches for advanced patterns ahead of need

The bar: an abstraction earns its keep when **at least two real consumers exist now**, or **a measured performance / correctness problem forces it**. Speculative or single-consumer abstractions are findings.

## Rules

- One real consumer is not a reusable abstraction. Inline first; extract on the second use.
- Memoization (`useMemo`, `useCallback`, `React.memo`) requires a named reason: a memoized child whose identity drives renders, an expensive computation profiled, or a value in a downstream effect's dep array. "Just in case" is not a reason.
- Context with one consumer is a prop chain in disguise. Pass the prop.
- Global state libraries (Redux, Zustand, Jotai) for fewer than three shared slices are overhead. `useState` + lift state.
- Generic types (`<T>`) on a component or hook with one concrete usage are wrong - delete the parameter, hardcode the type.
- A custom hook used once that wraps `useState` + one effect is a function pretending to be infrastructure. Inline it.
- Compound components (`<X.Root><X.Trigger>`) are for multi-piece interactions (Dialog, Tabs, Menu). For single-shape components, a flat API is correct.

## Patterns

### Premature Memoization

```tsx
// Bad - memoizing a primitive computed from primitives.
const total = useMemo(() => price * qty, [price, qty]);

// Bad - useCallback on a handler with no memoized child below.
const onClick = useCallback(() => setOpen(true), []);
return <button onClick={onClick}>Open</button>;

// Good - compute inline; React's reconciler is faster than memo bookkeeping for cheap values.
const total = price * qty;
return <button onClick={() => setOpen(true)}>Open</button>;
```

Reason it earns its place: `<Child>` is wrapped in `React.memo`, or the callback feeds an effect's deps. Otherwise delete.

### React.memo Overuse

```tsx
// Bad - memo on a component whose parent rarely re-renders and props change every render.
const Row = memo(function Row({ item, onSelect }) { ... });
<Row item={item} onSelect={() => select(item.id)} />  // new fn every render -> memo never hits
```

`React.memo` only helps when (a) parent re-renders often, (b) props are stable, and (c) the component is expensive. Without all three, it's pure cost. The unstable-callback case above guarantees memo never wins.

### Context for One Consumer

```tsx
// Bad
const SidebarOpenContext = createContext(false);
<SidebarOpenContext.Provider value={open}>
  <Sidebar />  {/* only consumer */}
</SidebarOpenContext.Provider>

// Good
<Sidebar open={open} />
```

Context earns its place at 3+ consumers across the same subtree, *or* when a deep descendant needs the value and intermediate layers don't.

### Mega-Provider Re-Render Bomb

```tsx
// Bad - any change to anything re-renders every consumer of AppContext.
<AppContext.Provider value={{ user, cart, theme, ui, prefs, notifications }}>

// Good - split per-update-frequency; a theme change does not re-render cart consumers.
<AuthContext.Provider value={user}>
  <ThemeContext.Provider value={theme}>
    <CartContext.Provider value={cart}>{children}</CartContext.Provider>
  </ThemeContext.Provider>
</AuthContext.Provider>
```

The fix is *not* `useMemo` on the whole bag - it's smaller contexts (or a store like Zustand for high-churn slices).

### Redux / Zustand for Two Pieces of State

```tsx
// Bad - Redux Toolkit slice + store wiring + <Provider> for "is the sidebar open?".
const sidebar = createSlice({ name: "sidebar", initialState: false, reducers: { toggle: (s) => !s } });
// + configureStore + <Provider> + useDispatch + useSelector at every call site.

// Good - useState in the layout that owns the sidebar.
const [open, setOpen] = useState(false);
<Sidebar open={open} onToggle={() => setOpen(o => !o)} />
```

Bar: 3+ shared slices, OR cross-cutting devtools / middleware needs, OR a team that already runs the store. Otherwise local state + lift.

### Single-Use Custom Hook

```tsx
// Bad - "extract for reusability" with one caller.
function useDialogState() {
  const [open, setOpen] = useState(false);
  return { open, openDialog: () => setOpen(true), closeDialog: () => setOpen(false) };
}

// Good - until a second component needs it, this is just `useState` with verbose accessors.
const [open, setOpen] = useState(false);
```

When the second consumer arrives, extract then.

### Generic Component for One Usage

```tsx
// Bad - generic for one concrete type.
function DataTable<T>({ rows, columns }: { rows: T[]; columns: Column<T>[] }) { ... }
<DataTable<Order> rows={orders} columns={orderColumns} />

// Good - concrete component; extract the generic when the second table is real.
function OrderTable({ rows }: { rows: Order[] }) { ... }
```

### Premature Compound Components

```tsx
// Bad - compound API for a non-compound widget.
<Card.Root>
  <Card.Header><Card.Title>{title}</Card.Title></Card.Header>
  <Card.Body>{children}</Card.Body>
</Card.Root>

// Good - flat props; compound earns its place when consumers compose ordering / omission.
<Card title={title}>{children}</Card>
```

Compound is correct for `<Dialog>`, `<Tabs>`, `<Menu>` - where consumers need to mix and order parts. For "header + body" with no variation, flat wins.

### Headless / Render-Prop / HoC for One Consumer

```tsx
// Bad - render prop, HoC, and hook trio shipped together for one screen.
withAuth(<ProtectedRoute><RenderUser>{(u) => ...}</RenderUser></ProtectedRoute>)

// Good - one of these, picked deliberately; usually the hook.
const user = useAuth();
if (!user) return <Redirect to="/login" />;
```

### Redundant Prop -> State -> Effect Sync

```tsx
// Bad - mirror prop into state, sync via effect.
function Greeting({ name }) {
  const [n, setN] = useState(name);
  useEffect(() => setN(name), [name]);
  return <p>Hi {n}</p>;
}

// Good - use the prop.
function Greeting({ name }) { return <p>Hi {name}</p>; }
```

`useEffect` to sync a prop into state is almost always wrong. Either compute during render or lift state to the parent.

### Speculative Configurability

```tsx
// Bad - props the codebase never passes.
type ButtonProps = { variant?: "primary" | "secondary" | "ghost" | "outline" | "subtle" | "destructive"; ... };
// Audit shows: 100% of call sites use "primary" or "destructive".

// Good - ship the two; add when a real third caller arrives.
```

## Output Format

When auditing, emit one block per finding:

```
- Location: <file>:<line> (<component / hook / module>)
  Issue: {PrematureMemo | ReactMemoOveruse | ContextSingleConsumer | MegaProvider | StoreForTwoSlices | SingleUseHook | GenericForOneUsage | PrematureCompound | RenderPropOverkill | PropStateEffectSync | SpeculativeConfigurability | RedundantHoC}
  Severity: {High | Medium | Low}
  Verdict: {Finding | Question}
  Evidence: <quoted snippet or symbol>
  Consumers found: <count + locations; "n/a" when the issue is not consumer-counted, e.g. PrematureMemo, PropStateEffectSync>
  Fix: <one-line action; reference a Pattern by name>
```

Set `Verdict: Question` (not `Finding`) when an abstraction is under-bar now but plausibly justified soon - a second consumer in flight, a design-system component hosted for future use. A Question asks the author to confirm; a Finding asserts overengineering. When in doubt, prefer Question.

Severity guide:
- **High**: `PropStateEffectSync` (correctness drift, not just complexity); `MegaProvider` causing measurable re-render cost; `StoreForTwoSlices` adding a global concept the team must learn for trivial benefit.
- **Medium**: `ContextSingleConsumer`; `SingleUseHook`; `PrematureCompound`; `GenericForOneUsage`.
- **Low**: `PrematureMemo` on cheap values; `SpeculativeConfigurability` on unused variants; `RedundantHoC` parallel to an existing hook.

If no issues, emit a single line: `No overengineering signals found in <scope>.`

## Avoid

- Flagging memoization that has a stated reason (downstream `React.memo` child, expensive computation, effect dep). Read the surrounding code first.
- Recommending the opposite extreme: "delete all memoization" is as wrong as memoizing everything. The rule is: a named reason.
- Calling all custom hooks overengineering. A hook with three call sites that cleanly factors state + effect is not the target.
- Mistaking a *partial* implementation for overengineering. A generic with one usage now and one in the same PR is fine.
- Recommending inlining a generic component when the team's design system explicitly hosts it for future use - flag as `[Question]` instead.
- Suggesting Redux / Zustand removal during a refactor without confirming no other slice depends on the same store wiring.
- Flagging `useCallback` / `useMemo` inside a custom hook whose return value is documented as referentially stable (consumers depend on the contract).
