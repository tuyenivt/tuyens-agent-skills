---
name: react-component-patterns
description: React component design - composition, compound components, render props, Server Components vs Client Components, error boundaries, and TypeScript patterns for React 19+.
metadata:
  category: frontend
  tags: [react, components, composition, server-components, error-boundaries, typescript]
user-invocable: false
---

# React Component Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing component architecture for a new feature
- Choosing between composition patterns (compound, render props, HOC)
- Deciding Server Component vs Client Component boundaries (Next.js)
- Adding error boundaries for graceful failure handling
- Reviewing component design for reusability and correctness

## Rules

- Function components only - no class components (except error boundaries until React 19 `onCaughtError`)
- Named exports for reusable components; default exports only for route pages (Next.js)
- Props typed with interfaces for components with more than 2 props; inline for simple components
- Server Components by default in Next.js - add `"use client"` only when needed (hooks, event handlers, browser APIs)
- Composition over configuration - prefer children and slots over prop-heavy components
- Single responsibility - each component does one thing; split when responsibilities diverge
- Never pass functions or non-serializable values from Server to Client Components

## Patterns

### Server vs Client Components (Next.js App Router)

| Concern                           | Server Component | Client Component           |
| --------------------------------- | ---------------- | -------------------------- |
| Data fetching                     | Yes (async)      | Via hooks (TanStack Query) |
| Access backend resources          | Yes (direct)     | No (via API)               |
| Sensitive data (tokens, keys)     | Yes              | No                         |
| Event handlers (onClick, etc.)    | No               | Yes                        |
| useState, useEffect, hooks        | No               | Yes                        |
| Browser APIs (window, document)   | No               | Yes                        |
| Large dependencies (charts, etc.) | No (use Client)  | Yes (code-split)           |

**Bad** - Everything as Client Component:

```tsx
"use client"; // unnecessary - this component has no interactivity
export default function UserProfile({ userId }: { userId: string }) {
  const [user, setUser] = useState(null);
  useEffect(() => {
    fetchUser(userId).then(setUser);
  }, [userId]);
  if (!user) return <Spinner />;
  return <div>{user.name}</div>;
}
```

Problem: Ships unnecessary JavaScript, loses SSR benefits, adds loading state complexity.

**Good** - Server Component with async data fetching:

```tsx
// No "use client" - this is a Server Component
export default async function UserProfile({ userId }: { userId: string }) {
  const user = await getUser(userId); // direct backend access
  return <div>{user.name}</div>;
}
```

**Vite / Client-only projects**: When stack-detect identifies Vite (no Next.js), all components are Client Components. Skip Server/Client boundary decisions. Use client-side data fetching (TanStack Query) and client-side routing (React Router). The output format `Component model` field should be `Client-only`.

### Composition Pattern

**Bad** - Prop-heavy configuration:

```tsx
<Card
  title="Order #123"
  subtitle="Pending"
  icon={<ShoppingCart />}
  actions={[{ label: "View", onClick: handleView }]}
  footer="Last updated 2h ago"
  variant="outlined"
/>
```

Problem: Every new feature adds another prop; component becomes unwieldy.

**Good** - Compound component with composition:

```tsx
<Card variant="outlined">
  <Card.Header>
    <Card.Icon>
      <ShoppingCart />
    </Card.Icon>
    <Card.Title>Order #123</Card.Title>
    <Card.Subtitle>Pending</Card.Subtitle>
  </Card.Header>
  <Card.Body>{/* flexible content */}</Card.Body>
  <Card.Footer>
    <Card.Action onClick={handleView}>View</Card.Action>
  </Card.Footer>
</Card>
```

### Compound Components

Use React Context to share implicit state between compound component parts:

```tsx
interface TabsContextValue {
  activeTab: string;
  setActiveTab: (tab: string) => void;
}

const TabsContext = createContext<TabsContextValue | null>(null);

function useTabsContext() {
  const context = useContext(TabsContext);
  if (!context) throw new Error("Tab components must be used within <Tabs>");
  return context;
}

function Tabs({
  defaultTab,
  children,
}: {
  defaultTab: string;
  children: ReactNode;
}) {
  const [activeTab, setActiveTab] = useState(defaultTab);
  return (
    <TabsContext value={{ activeTab, setActiveTab }}>{children}</TabsContext>
  );
}

function TabList({ children }: { children: ReactNode }) {
  return <div role="tablist">{children}</div>;
}

function Tab({ value, children }: { value: string; children: ReactNode }) {
  const { activeTab, setActiveTab } = useTabsContext();
  return (
    <button
      role="tab"
      aria-selected={activeTab === value}
      onClick={() => setActiveTab(value)}
    >
      {children}
    </button>
  );
}

function TabPanel({ value, children }: { value: string; children: ReactNode }) {
  const { activeTab } = useTabsContext();
  if (activeTab !== value) return null;
  return <div role="tabpanel">{children}</div>;
}

Tabs.TabList = TabList;
Tabs.Tab = Tab;
Tabs.TabPanel = TabPanel;
```

### Error Boundaries

Wrap component subtrees to catch rendering errors gracefully:

```tsx
// React 19: use the built-in error boundary pattern via onCaughtError
// For class-based error boundary (still needed for render-phase errors):
class ErrorBoundary extends Component<
  { fallback: ReactNode; children: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Component error:", error, info.componentStack);
  }

  render() {
    if (this.state.hasError) return this.props.fallback;
    return this.props.children;
  }
}

// Usage: wrap feature boundaries, not individual components
<ErrorBoundary fallback={<ErrorFallback />}>
  <Dashboard />
</ErrorBoundary>;
```

Place error boundaries at feature boundaries (page sections, widget areas), not around every component.

### Props Interface Patterns

```tsx
// Simple component - inline props are fine
function Badge({
  label,
  color,
}: {
  label: string;
  color: "green" | "red" | "yellow";
}) {
  return <span className={`badge-${color}`}>{label}</span>;
}

// Complex component - use interface
interface DataTableProps {
  data: readonly Row[];
  columns: readonly Column[];
  onSort?: (column: string, direction: "asc" | "desc") => void;
  onRowClick?: (row: Row) => void;
  emptyMessage?: string;
  isLoading?: boolean;
}

function DataTable({
  data,
  columns,
  onSort,
  onRowClick,
  emptyMessage,
  isLoading,
}: DataTableProps) {
  // ...
}
```

### Polymorphic Components

Use the `as` prop pattern for components that need to render as different elements:

```tsx
interface ButtonProps<T extends ElementType = "button"> {
  as?: T
  variant: "primary" | "secondary"
  children: ReactNode
}

type PolymorphicProps<T extends ElementType> = ButtonProps<T> &
  Omit<ComponentPropsWithoutRef<T>, keyof ButtonProps>

function Button<T extends ElementType = "button">({
  as,
  variant,
  children,
  ...props
}: PolymorphicProps<T>) {
  const Component = as || "button"
  return <Component className={`btn-${variant}`} {...props}>{children}</Component>
}

// Usage:
<Button variant="primary" onClick={handleClick}>Click</Button>
<Button as="a" variant="secondary" href="/about">About</Button>
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Component Design

**Stack:** {detected framework}
**Component model:** {Server Components + Client | Client-only}

### Component Tree

{ComponentName} (Server | Client) - {responsibility}
  ├── {ChildA} (Server | Client) - {responsibility}
  └── {ChildB} (Client) - {responsibility}

### Component Specifications

| Component      | Type   | Props                  | State          | Pattern            |
| -------------- | ------ | ---------------------- | -------------- | ------------------ |
| {name}         | Server | {key props}            | None           | Async data fetch   |
| {name}         | Client | {key props}            | {state fields} | Compound / Simple  |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Class components for new code (except error boundaries)
- `"use client"` on components that don't need interactivity
- Prop drilling through more than 2 levels (use composition, context, or state library)
- God components that handle multiple unrelated concerns
- Passing functions from Server to Client Components (non-serializable)
- Default exports for non-route components (makes refactoring harder)
- Inline prop types on complex components (use named interfaces)
- Deeply nested ternaries in JSX (extract to named components or early returns)
