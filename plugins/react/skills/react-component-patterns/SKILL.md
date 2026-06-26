---
name: react-component-patterns
description: "React 19 component design: composition, compound components, Server vs Client boundaries, error boundaries, ref forwarding, polymorphic and prop-typing patterns."
metadata:
  category: frontend
  tags: [react, components, composition, server-components, error-boundaries, typescript]
user-invocable: false
---

# React Component Patterns

> Load `Use skill: stack-detect` first to determine the project stack. For Next.js-specific routing, Server Actions, caching, and metadata defer to `react-nextjs-patterns`; this skill covers component shape and boundaries.

## When to Use

- Designing component trees for a new feature or reviewing one for reusability
- Choosing a composition pattern (children/slots, compound, polymorphic)
- Drawing Server vs Client boundaries in Next.js App Router
- Placing error boundaries and typing component props

## Rules

- Function components only. Class components only for error boundaries (until `onCaughtError` is adopted everywhere).
- Server Components are the default in Next.js. Add `"use client"` only for hooks, event handlers, or browser APIs - and push it as deep in the tree as possible.
- Never pass functions or non-serializable values from a Server Component to a Client Component. Pass data; let the Client own its handlers.
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
export default function Page({ id }: { id: string }) {
  const [user, setUser] = useState(null);
  useEffect(() => { fetchUser(id).then(setUser); }, [id]);
  return user ? <Profile user={user} onEdit={openEditor} /> : <Spinner />;
}

// Good - Server fetches data; only the interactive leaf is client.
export default async function Page({ id }: { id: string }) {
  const user = await getUser(id);
  return <Profile user={user} />;       // Profile renders <EditButton/> as the "use client" leaf
}
```

Vite or other client-only stacks: skip this boundary entirely. Set `Component model: Client-only` in the output and use client-side fetching (TanStack Query).

### Composition over configuration

```tsx
// Bad - every feature adds a prop; impossible to extend.
<Card title="Order" subtitle="Pending" icon={<Cart/>} actions={[...]} footer="2h ago" />

// Good - slots; new features compose without changing Card's API.
<Card>
  <Card.Header icon={<Cart/>}><Card.Title>Order</Card.Title></Card.Header>
  <Card.Body>{...}</Card.Body>
  <Card.Footer><Button onClick={onView}>View</Button></Card.Footer>
</Card>
```

### Compound components

Bind parts via context; expose as static members (`Tabs.Tab`, `Tabs.Panel`). Use when sub-parts must share implicit state. Throw from the consumer hook when the context is null - that's how you signal "used outside parent".

### Error boundaries

One per feature region (page section, widget), not per component. Class form is still required for render-phase errors.

```tsx
class ErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { hasError: boolean }> {
  state = { hasError: false };
  static getDerivedStateFromError() { return { hasError: true }; }
  componentDidCatch(err: Error, info: ErrorInfo) { reportError(err, info.componentStack); }
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

```
## Component Design

**Stack:** {Next.js App Router | Next.js Pages | Vite | Other}
**Component model:** {Server + Client | Client-only}

### Component Tree

{Root} ({Server | Client}) - {responsibility}
  |- {Child} ({Server | Client}) - {responsibility}

### Specifications

| Component | Type | Props (key) | State | Pattern |
| --------- | ---- | ----------- | ----- | ------- |
| {name}    | {Server|Client} | {...} | {none|fields} | {pattern} |

`Pattern` values: `Simple` (no composition concern), `Slot` (accepts `children` or named slots), `Compound` (static sub-members sharing context), `Polymorphic` (`as` prop).

### Findings

- [Severity: {High | Medium | Low}] {one-line issue}
  Current: {what the code does}
  Target: {what should happen}
  Fix: {concrete correction; reference Pattern name}
```

One Findings block per issue. Omit no field.

## Avoid

- `"use client"` at the page or layout root when only a leaf needs it
- Passing functions, class instances, or Dates without serialization across the Server/Client boundary
- Prop-heavy "god" components that grow a new prop per feature instead of a new slot
- Prop drilling through 3+ levels - lift the composition or introduce context
- Default exports for non-route components - breaks rename refactors and tooling
- Class components for new code outside error boundaries
- Deeply nested ternaries in JSX - extract a named component or return early
- Polymorphic `as` generics on components that always render the same tag
