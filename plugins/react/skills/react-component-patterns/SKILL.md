---
name: react-component-patterns
description: "React 19 component design: composition, compound components, Server vs Client boundaries, error boundaries, ref forwarding, polymorphic and prop-typing patterns."
metadata:
  category: frontend
  tags: [react, components, composition, server-components, error-boundaries, typescript]
user-invocable: false
---

# React Component Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For Next.js-specific routing, Server Actions, caching, and metadata defer to `react-nextjs-patterns`; for effect, timer, and subscription mechanics to `react-hooks-patterns`; this skill covers component shape and boundaries.

## When to Use

- Designing component trees for a new feature or reviewing one for reusability
- Choosing a composition pattern (children/slots, compound, polymorphic)
- Drawing Server vs Client boundaries in Next.js App Router
- Placing error boundaries and typing component props

## Rules

- Function components only. Error boundaries are the sole exception: render-phase errors still require a class, and `onCaughtError` on `createRoot`/`hydrateRoot` reports what a boundary caught rather than replacing it.
- Server Components are the default in Next.js. Add `"use client"` only for hooks, event handlers, or browser APIs - and push it as deep in the tree as possible.
- From a Server Component, pass plain data, `Date`/`Map`/`Set`, a Promise for the client to unwrap with `use`, or a Server Action (a `"use server"` function, which is a serializable reference and the normal way to wire mutations). Never pass an ordinary closure or a class instance. Prisma rows are plain objects and cross fine; what fails is a class-valued field on them (`Decimal`) or a true entity instance from TypeORM or Sequelize.
- Compose with `children` and slots before adding more props. A prop that injects open-ended content or a whole region (header, footer, body) becomes a slot; a prop that selects a variant (`variant`, `size`), carries data, or sets a single fixed adornment (`icon`) stays a prop. New feature => new slot, not a new boolean prop.
- One responsibility per component; split when state or props diverge.
- Named exports for reusable components; default export only for route files (`page.tsx`, `layout.tsx`).
- Props typed inline for <=2 fields; named `interface` once props grow or repeat across call sites.
- Prop-drilling beyond two levels is a smell - reach for composition, context, or a state library.

## Patterns

### Server vs Client boundary (Next.js)

| Capability                  | Server | Client |
| --------------------------- | :----: | :----: |
| `async` body, direct DB/API |   Y    |   N    |
| Secrets, server-only deps   |   Y    |   N    |
| `useState`/`useEffect`/hooks|   N    |   Y    |
| Event handlers, browser API |   N    |   Y    |

```tsx
// Bad - "use client" forces the whole subtree client, ships JS for static content.
"use client";
export default function Page({ params }: { params: { id: string } }) {
  const [user, setUser] = useState<User | null>(null);
  useEffect(() => { fetchUser(params.id).then(setUser); }, [params.id]);
  return user ? <Profile user={user} /> : <Spinner />;
}

// Good - Server fetches data; only the interactive leaf is client.
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;          // Next 15+: params is a Promise
  const user = await getUser(id);
  return <Profile user={user} />;       // Profile renders <EditButton/> as the "use client" leaf
}
```

Vite or other client-only stacks: skip this boundary entirely. Set `Component model: Client-only` in the output and use client-side fetching (TanStack Query).

### Composition over configuration

```tsx
// Bad - every feature adds a prop; impossible to extend.
<Card title="Order" subtitle="Pending" icon={<Cart/>} actions={orderActions} footer="2h ago" />

// Good - slots; new features compose without changing Card's API.
<Card>
  <Card.Header icon={<Cart/>}><Card.Title>Order</Card.Title></Card.Header>
  <Card.Body><OrderLines order={order} /></Card.Body>
  <Card.Footer><Button onClick={onView}>View</Button></Card.Footer>
</Card>
```

### Compound components

Bind parts via context; expose as static members (`Tabs.Tab`, `Tabs.Panel`). Use when sub-parts must share implicit state. Throw from the consumer hook when the context is null - that's how you signal "used outside parent".

### Error boundaries

One per feature region (page section, widget), not per component. Class form is still required for render-phase errors. In App Router the class boundary is a Client Component - add `"use client"` to its file (route-level `error.tsx` belongs to `react-nextjs-patterns`).

```tsx
"use client";                                     // required: a class boundary is a Client Component
class ErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(err: Error, info: ErrorInfo) { logToService(err, info.componentStack ?? ""); }
  render() { return this.state.hasError ? this.props.fallback : this.props.children; }
}
```

### Prop typing

```tsx
// <=2 props or one-off: inline.
function Badge({ label, color }: { label: string; color: "green" | "red" | "yellow" }) { ... }

// >2 props, optional fields, or reused shape: named interface with readonly arrays.
interface DataTableProps {
  data: readonly Row[];
  columns: readonly Column[];
  onSort?: (col: string, dir: "asc" | "desc") => void;
  isLoading?: boolean;
}
```

### Polymorphic `as` prop

Use only when one component must render as different elements (Button-as-link). Otherwise the generics are noise.

### Ref forwarding

React 19: `ref` is a normal prop - declare it in the props type and forward it to the DOM node. No `forwardRef` for new code. Forward a ref only when callers need imperative access (focus, scroll, measure); don't expose one by default. On a polymorphic component the ref type tracks `as` (`<button>` => `Ref<HTMLButtonElement>`).

```tsx
function TextInput({ ref, ...props }: { ref?: Ref<HTMLInputElement> } & InputHTMLAttributes<HTMLInputElement>) {
  return <input ref={ref} {...props} />;
}
```

`forwardRef` is still required only when supporting React 18 and earlier.

## Output Format

When designing, emit this block for the proposed tree; a Findings block then flags a risk in the requested design (`Current` = the wiring the requirement naively implies). When reviewing, the consuming workflow owns the finding envelope; invoked standalone, emit this block with the Component Tree and Specifications recording what the code does today, and put the target shape in each finding's Fix; order Findings High first. Emit one tree per root that nothing in scope renders - two components in one import graph share a tree, two unconnected entry points get one each. An error boundary appears in the Component Tree as its own node, `(Client)`, whose responsibility names the region it guards; a missing or mis-scoped boundary is a Finding rather than a node. In review mode `Current` records what the code does and `Target` the shape it should take, so the Fix carries the change rather than restating the target.

```
## Component Design

**Stack:** {Next.js App Router | Next.js Pages | Vite | Other} - `stack-detect` reports a framework string, not a router; read `app/` vs `pages/` to pick, and write `Other` when neither is visible. `Next.js Pages` and `Other` both take `Component model: Client-only`: they server-render but have no RSC boundary, so the Server/Client rules do not apply and the rest of the skill does

**Component model:** {Server + Client | Client-only}

### Component Tree

{Root} ({Server | Client}) - {responsibility}
  |- {Child} ({Server | Client}) - {responsibility}

### Specifications

| Component | Type | Props (key) | State | Pattern |
| --------- | ---- | ----------- | ----- | ------- |
| {name}    | {Server \| Client} | {...} | {none \| fields} | {pattern} |

`Pattern` values: `Simple` (no composition concern), `Slot` (accepts `children` or named slots), `Compound` (static sub-members sharing context), `Polymorphic` (`as` prop). Static sub-members alone are `Slot`; `Compound` requires implicit shared state via context.

### Findings

- [Severity: {High | Medium | Low}] {one-line issue}
  Location: {file:line, component, or "design"}
  Current: {what the code does}
  Target: {what should happen}
  Fix: {concrete correction; reference Pattern name}
```

One Findings block per root cause (a god component's twelve props are one finding, not twelve); omit no field within a block. Severity: **High** = wrong or breaking behavior (non-serializable values crossing the Server/Client boundary, `"use client"` forcing a large static subtree client, compound context consumed without a null guard, a class error boundary missing `"use client"`, a feature region with no boundary above it); **Medium** = design debt that spreads (god components, prop drilling 3+, class components outside error boundaries, `forwardRef` in new React 19 code); **Low** = convention drift (default exports, inline types past the threshold, nested ternaries, polymorphic `as` generics on a component that always renders one tag).

## Avoid

- `"use client"` at the page or layout root when only a leaf needs it
- Passing ordinary closures or class instances (a Prisma `Decimal` field, a TypeORM entity) across the Server/Client boundary - RSC serialization handles plain data, `Date`/`Map`/`Set`, Promises and Server Actions, not class instances or arbitrary functions
- Prop-heavy "god" components that grow a new prop per feature instead of a new slot
- Prop drilling through 3+ levels - lift the composition or introduce context
- Default exports for non-route components - breaks rename refactors and tooling
- Class components for new code outside error boundaries
- Deeply nested ternaries in JSX - extract a named component or return early
- Polymorphic `as` generics on components that always render the same tag
