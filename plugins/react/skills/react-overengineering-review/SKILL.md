---
name: react-overengineering-review
description: "Flag React overengineering: premature memo/useCallback, trivial Context, Redux for 2 fields, single-use hooks, generic HoC/compound for one consumer."
metadata:
  category: frontend
  tags: [react, overengineering, complexity, memoization, context, redux, custom-hooks, anti-patterns]
user-invocable: false
---

# React Overengineering Review

> Load `Use skill: stack-detect` first to confirm the project is React; the detection is context, not an output field. `stack-detect` carries no compiler or store-library field: read `reactCompiler` from `next.config.*`, and the compiler plugin and store libraries from `package.json` dependencies (the owning app's manifest in a monorepo) and the imports in the files in scope. For framework-neutral complexity heuristics defer to `complexity-review`; this skill owns React-specific overengineering.

## When to Use

- The code-quality phase of a React review, where a workflow owns the finding envelope and this skill supplies the findings
- A standalone audit of a directory or changeset, where this skill owns the whole block below
- After any change that introduced new abstractions
- After AI-assisted scaffolding, when generated code reaches for advanced patterns ahead of need

The bar: an abstraction earns its keep when **at least two real consumers exist now**, or **a measured performance / correctness problem forces it**. Speculative or single-consumer abstractions are findings.

## Rules

- One real consumer is not a reusable abstraction. Inline first; extract on the second use.
- **Establish whether the React Compiler is on before judging memoization.** It is on when `next.config` sets `reactCompiler: true` or `reactCompiler: { compilationMode: 'annotation' }`, transformed by `babel-plugin-react-compiler` or by `experimental.turbopackRustReactCompiler: true` (no Babel plugin); a leftover `experimental.reactCompiler` goes in `Notes:` as a key to move to top-level `reactCompiler`. Where it is on and compiling the file - `compilationMode: 'annotation'` compiles only functions marked `"use memo"`, and `"use no memo"` or a Rules-of-React violation bails a component out - new manual memoization is not needed, so flag it in code being written. Existing manual memoization is a different question: the compiler preserves it deliberately, React's own guidance is to leave it alone, and `useMemo`/`useCallback` remain the supported escape hatch for a value an effect depends on. Never file a bulk-delete finding.
- Memoization added by hand requires a named reason: a memoized child whose identity drives renders, an expensive computation profiled, or a value in a downstream effect's dep array. "Just in case" is not a reason.
- Context with one consumer is a prop chain in disguise. Pass the prop - unless that one consumer is a deep descendant the intermediate layers never read (see the Context bar).
- A global store for fewer than three shared slices is overhead whatever the library - the bar in the Pattern below is library-neutral. The library only changes how much the overhead costs: Redux adds store wiring, a `<Provider>` and `useDispatch`/`useSelector` at every call site, while Zustand and Jotai are lighter (though in the App Router both still need a per-request store behind a client provider to be SSR-safe). Weigh that cost in the Fix, not in whether to flag.
- Generic types (`<T>`) on a component or hook with one concrete usage are wrong - delete the parameter, hardcode the type.
- A custom hook used once that wraps `useState` + one effect is a function pretending to be infrastructure. Inline it.
- Compound components (`<X.Root><X.Trigger>`) are for multi-piece interactions (Dialog, Tabs, Menu). For single-shape components, a flat API is correct. The right shape still owes the consumer bar: a hand-rolled compound with one consumer and no hosting design system is `PrematureCompound` too, its Verdict set by the Question rule below.

## Patterns

### Premature Memoization

```tsx
// Bad - memoizing a primitive computed from primitives.
const total = useMemo(() => price * qty, [price, qty]);

// Bad - useCallback on a handler with no memoized child below.
const onClick = useCallback(() => setOpen(true), []);
return <button onClick={onClick}>Open</button>;

// Good - compute inline; the multiplication costs less than useMemo's dep comparison and cache slot.
const total = price * qty;
return <button onClick={() => setOpen(true)}>Open</button>;
```

Reason it earns its place: the callback is passed to a child wrapped in `React.memo`, or feeds an effect's deps. Otherwise delete.

### React.memo Overuse

```tsx
// Bad - memo on a cheap leaf whose parent re-renders rarely: pure bookkeeping cost.
const Badge = memo(function Badge({ label }: { label: string }) { return <span>{label}</span>; });

// Bad - memo defeated by a prop rebuilt every render, so it never hits.
const Row = memo(function Row({ item, onSelect }: RowProps) { ... });
<Row item={item} onSelect={(id) => select(id)} />   // Row calls onSelect(item.id)

// Good - drop memo from the cheap leaf; keep it on the expensive one and stabilise its props.
function Badge({ label }: { label: string }) { return <span>{label}</span>; }
const onSelect = useCallback((id: string) => select(id), [select]);
<Row item={item} onSelect={onSelect} />
```

`React.memo` only helps when (a) parent re-renders often, (b) props are stable, and (c) the component is expensive. Without all three, it's pure cost. The unstable-callback case above guarantees memo never wins.

### Context for One Consumer

```tsx
// Bad
const SidebarOpenContext = createContext(false);
<SidebarOpenContext value={open}>     {/* React 19: render the context directly */}
  <Sidebar />  {/* only consumer */}
</SidebarOpenContext>

// Good
<Sidebar open={open} />
```

Context earns its place at 3+ consumers across the same subtree, *or* when a deep descendant needs the value and intermediate layers don't. This bar is deliberately higher than the general two-consumer bar - a prop reaches two consumers cheaply.

### Mega-Provider Re-Render Bomb

```tsx
// Bad - any change to anything re-renders every consumer of AppContext.
<AppContext value={{ user, cart, theme, ui, prefs, notifications }}>

// Good - split per-update-frequency; a theme change does not re-render cart consumers.
<AuthContext value={user}>
  <ThemeContext value={theme}>
    <CartContext value={cart}>{children}</CartContext>
  </ThemeContext>
</AuthContext>
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

Bar: 3+ shared slices, OR cross-cutting devtools / middleware needs, OR a team that already runs the store (adding a slice to the store library already in place - not introducing a second library beside it). Otherwise local state + lift.

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
const Guarded = withAuth(ProtectedRoute);   // HoC takes a component, not an element
<Guarded><RenderUser>{(u) => ...}</RenderUser></Guarded>

// Good - one of these, picked deliberately; for an auth gate, a check in the page Server Component
// (it guards that page only; nested segments and Server Actions re-check through the DAL).
const user = await getUser();
if (!user) redirect("/login");
```

### Redundant Prop -> State -> Effect Sync

```tsx
// Bad - mirror prop into state, sync via effect.
function Greeting({ name }: { name: string }) {
  const [n, setN] = useState(name);
  useEffect(() => setN(name), [name]);
  return <p>Hi {n}</p>;
}

// Good - use the prop.
function Greeting({ name }: { name: string }) { return <p>Hi {name}</p>; }
```

`useEffect` to sync a prop into state is almost always wrong. Either compute during render or lift state to the parent. `eslint-config-next` flags it through `react-hooks/set-state-in-effect`; a suppression of that rule belongs in the finding's Evidence.

### Speculative Configurability

```tsx
// Bad - props the codebase never passes.
type ButtonProps = { variant?: "primary" | "secondary" | "ghost" | "outline" | "subtle" | "destructive" };
// Audit shows: 100% of call sites use "primary" or "destructive".

// Good - ship the two the callers use; add the third when a real caller arrives.
type ButtonProps = { variant?: "primary" | "destructive" };
```

## Output Format

When auditing, open with one line `Scope: <files reviewed>`, then emit one block per finding, ordered by severity (a Question sorts with its severity; within a band, file order (the order the input lists the files, a glob expanding alphabetically; ascending line within a file)), one finding per root cause - an under-bar hook's internal memoization folds into the hook finding; an HoC + wrapper + render-prop trio for one concern is one `RedundantHoC` (`RenderPropOverkill` covers a lone render-prop); repeated instances of one Issue in the same component merge into one block listing each location:

```
Scope: <files reviewed>

- Location: <file>:<line or symbol> (<component / hook / module>)
  Issue: {PrematureMemo | ReactMemoOveruse | ContextSingleConsumer | MegaProvider | StoreForTwoSlices | SingleUseHook | GenericForOneUsage | PrematureCompound | RenderPropOverkill | PropStateEffectSync | SpeculativeConfigurability | RedundantHoC}
  Severity: {High | Medium | Low}
  Verdict: {Finding | Question}
  Evidence: <quoted snippet or symbol>
  Consumers found: <count + locations; "n/a" when the issue is not consumer-counted, e.g. PrematureMemo, PropStateEffectSync; a counted value wins over "many (not enumerated)", the provider-bag fallback>
  Fix: <one-line action; reference a Pattern by name>

Cleared: <reviewed and justified - one line, no blocks; `none` when nothing was cleared>

Tally: <N> findings, <Q> questions

Notes: <off-scope defects noticed in passing, each naming the concern that owns it (hooks discipline, state architecture, accessibility) rather than a skill filename; omit when none>
```

Set `Verdict: Question` (not `Finding`) when an abstraction is under-bar now but plausibly justified soon - a second consumer in flight, a component the team says it is about to reuse. A Question asks the author to confirm; a Finding asserts overengineering. When in doubt, prefer Question. Design-system intent already documented in the repo (a README or spec naming the surface as a hosted primitive) is settled, internal Context included, so it is neither: list it under `Cleared:`. A Question carries the severity the issue would have if confirmed. `ContextSingleConsumer` covers any under-bar context (one or two consumers); a consumer in the provider's own file still counts as one. `SingleUseHook` also covers a `use*` function that calls no hooks at all. `SpeculativeConfigurability` covers props declared but never read and props declared but never implemented alike. A stated reason the code contradicts (the profiled route never renders the component) is not a reason: say so in Evidence.

One block per root cause. Repeated instances of one Issue in a component merge into a single block listing each location; two different Issue values in one component stay separate blocks, because their fixes are independent.

Severity guide:
- **High**: `PropStateEffectSync` (correctness drift, not just complexity); `MegaProvider` bundling slices that change at different rates (breadth is the evidence; measurement not required); `StoreForTwoSlices` adding a global concept the team must learn for trivial benefit (a single-slice store included).
- **Medium**: `ContextSingleConsumer`; `SingleUseHook`; `PrematureCompound`; `GenericForOneUsage`; `RedundantHoC` (a lone single-consumer HoC, or an HoC/wrapper/render-prop trio shipped together for one concern).
- **Low**: `PrematureMemo`; `SpeculativeConfigurability` (unused variants, props never read or never implemented); `RenderPropOverkill` for a lone render prop; `ReactMemoOveruse`.

No Issue value is left unscored: where a value appears in more than one band the band naming your defect's condition wins, and a defect matching two takes the higher. `MegaProvider` is High whenever the provider bundles slices that change at different rates, whether or not their domains are related - breadth of re-render is the harm; slices that all change together are not a `MegaProvider` finding. `StoreForTwoSlices` is High for any under-bar store, single-slice included, whatever the library. `RedundantHoC` is Medium for a lone single-consumer HoC and for the shipped-together trio alike. `PrematureMemo` and `ReactMemoOveruse` stay Low regardless of what is memoized.

Count consumers as the distinct modules that read the value - one file reading it three times is one consumer; a store's consumers are the components and hooks that call it. Files outside Scope may be read to count consumers or to establish the incumbent store; defects found there go in `Notes:`. `Consumers found: n/a` applies to exactly `PrematureMemo`, `ReactMemoOveruse`, `PropStateEffectSync` and `SpeculativeConfigurability`; every other value carries a count, except that a `MegaProvider` whose readers cannot be enumerated from the files in scope writes `many (not enumerated)`. A finding whose one root cause spans a definition and its call sites lists them in `Location` separated by commas.

With no findings, emit `Scope:`, any Question blocks, then `No overengineering findings in <scope>.`, then the same `Cleared:`, `Tally: 0 findings, <Q> questions` and `Notes:` lines as any other run.

## Avoid

- Flagging memoization that has a stated reason (downstream `React.memo` child, expensive computation, effect dep). Read the surrounding code first.
- Recommending the opposite extreme: "delete all memoization" is as wrong as memoizing everything, and that holds on a compiler-enabled project too - the compiler preserves what is already there by design. The rule is: a named reason.
- Calling all custom hooks overengineering. A hook with three call sites that cleanly factors state + effect is not the target.
- Mistaking a *partial* implementation for overengineering. A generic with one usage now and one in the same PR is fine.
- Flagging a component the repo documents as a hosted design-system primitive - that intent is settled, so it belongs in `Cleared:`, not a Question.
- Suggesting Redux / Zustand removal during a refactor without confirming no other slice depends on the same store wiring.
- Flagging `useCallback` / `useMemo` inside a custom hook whose return value is documented as referentially stable (consumers depend on the contract).
