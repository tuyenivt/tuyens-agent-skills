---
name: react-hooks-patterns
description: React hooks patterns - custom hooks, hook rules, useEffect discipline, cleanup, refs, context usage, and React 19 hooks (use, useOptimistic, useActionState) for React 19+.
metadata:
  category: frontend
  tags: [react, hooks, useEffect, custom-hooks, react-19, refs, context]
user-invocable: false
---

# React Hooks Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing custom hooks for reusable logic
- Reviewing hook usage for correctness (rules of hooks, dependency arrays)
- Fixing useEffect issues (missing deps, infinite loops, missing cleanup)
- Adopting React 19 hooks (use, useOptimistic, useActionState, useFormStatus)
- Managing refs, context, and side effects

## Rules

- Hooks must only be called at the top level - never inside conditions, loops, or nested functions
- Custom hooks must start with `use` and encapsulate exactly one concern
- useEffect is for synchronization with external systems - not for data fetching, not for derived state
- Every useEffect that subscribes, connects, or adds listeners must return a cleanup function
- Dependency arrays must be exhaustive - never suppress the ESLint rule with `// eslint-disable`
- Prefer useCallback only when passing callbacks to memoized children; do not memoize everything by default
- useMemo is for expensive computations proven by profiling - not for simple derivations

## Patterns

### useEffect Discipline

**Bad** - useEffect for data fetching:

```tsx
const [users, setUsers] = useState<User[]>([]);
const [loading, setLoading] = useState(true);

useEffect(() => {
  fetch("/api/users")
    .then((r) => r.json())
    .then((data) => {
      setUsers(data);
      setLoading(false);
    });
}, []);
```

Problem: No error handling, no caching, no request cancellation, no deduplication, race conditions on fast navigation.

**Good** - Data fetching with TanStack Query:

```tsx
const {
  data: users,
  isLoading,
  error,
} = useQuery({
  queryKey: ["users"],
  queryFn: fetchUsers,
});
```

**Bad** - useEffect for derived state:

```tsx
const [items, setItems] = useState<Item[]>([]);
const [total, setTotal] = useState(0);

useEffect(() => {
  setTotal(items.reduce((sum, item) => sum + item.price, 0));
}, [items]);
```

Problem: Extra render cycle, state duplication, can drift out of sync.

**Good** - Compute during render:

```tsx
const [items, setItems] = useState<Item[]>([]);
const total = items.reduce((sum, item) => sum + item.price, 0);
// Or for expensive computations:
const total = useMemo(
  () => items.reduce((sum, item) => sum + item.price, 0),
  [items],
);
```

**Good** - useEffect for external system synchronization:

```tsx
useEffect(() => {
  const connection = createWebSocket(roomId);
  connection.connect();
  return () => connection.disconnect(); // cleanup on unmount or roomId change
}, [roomId]);
```

### Custom Hook Design

Each custom hook should encapsulate one concern and return a clear API:

**Bad** - Kitchen sink hook:

```tsx
function useUser(userId: string) {
  const [user, setUser] = useState(null);
  const [posts, setPosts] = useState([]);
  const [theme, setTheme] = useState("light");
  const [notifications, setNotifications] = useState([]);
  // fetches user, posts, theme, and notifications...
}
```

**Good** - Single concern:

```tsx
function useUser(userId: string) {
  return useQuery({
    queryKey: ["user", userId],
    queryFn: () => fetchUser(userId),
  });
}

function useUserPosts(userId: string) {
  return useQuery({
    queryKey: ["user", userId, "posts"],
    queryFn: () => fetchUserPosts(userId),
    enabled: !!userId,
  });
}
```

### Cleanup Patterns

```tsx
// Event listener cleanup
useEffect(() => {
  const handler = (e: KeyboardEvent) => {
    if (e.key === "Escape") onClose();
  };
  document.addEventListener("keydown", handler);
  return () => document.removeEventListener("keydown", handler);
}, [onClose]);

// AbortController for fetch
useEffect(() => {
  const controller = new AbortController();
  fetchData(controller.signal).then(setData);
  return () => controller.abort();
}, [fetchData]);

// Timer cleanup
useEffect(() => {
  const id = setInterval(() => setCount((c) => c + 1), 1000);
  return () => clearInterval(id);
}, []);
```

### React 19 Hooks

**`use` hook** - Read promises and context in render:

```tsx
// Read a promise (replaces useEffect + useState for simple cases)
function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  const user = use(userPromise); // suspends until resolved
  return <div>{user.name}</div>;
}

// Read context conditionally (unlike useContext, can be called in conditions)
function AdminPanel({ isAdmin }: { isAdmin: boolean }) {
  if (!isAdmin) return <p>Access denied</p>;
  const theme = use(ThemeContext); // OK - use() can be conditional
  return <div className={theme.panel}>Admin content</div>;
}
```

**`useOptimistic` hook** - Optimistic UI updates:

```tsx
function TodoList({ todos }: { todos: Todo[] }) {
  const [optimisticTodos, addOptimistic] = useOptimistic(
    todos,
    (state, newTodo: Todo) => [...state, newTodo],
  );

  async function addTodo(formData: FormData) {
    const newTodo = {
      id: crypto.randomUUID(),
      title: formData.get("title") as string,
    };
    addOptimistic(newTodo); // immediately show in UI
    await createTodo(newTodo); // server request
  }

  return (
    <ul>
      {optimisticTodos.map((todo) => (
        <li key={todo.id}>{todo.title}</li>
      ))}
    </ul>
  );
}
```

**`useActionState` hook** - Form action state (replaces useFormState):

```tsx
async function submitAction(
  prevState: FormState,
  formData: FormData,
): Promise<FormState> {
  const result = await createUser(formData);
  if (result.error) return { error: result.error };
  return { success: true };
}

function SignupForm() {
  const [state, formAction, isPending] = useActionState(submitAction, {
    error: null,
  });

  return (
    <form action={formAction}>
      <input name="email" type="email" />
      {state.error && <p role="alert">{state.error}</p>}
      <button disabled={isPending}>
        {isPending ? "Submitting..." : "Sign Up"}
      </button>
    </form>
  );
}
```

### Ref Patterns

```tsx
// DOM element ref
const inputRef = useRef<HTMLInputElement>(null);
useEffect(() => {
  inputRef.current?.focus();
}, []);

// Mutable value ref (not triggering re-render)
const renderCount = useRef(0);
renderCount.current += 1;

// Callback ref for dynamic elements
function MeasuredComponent() {
  const [height, setHeight] = useState(0);
  const measuredRef = useCallback((node: HTMLDivElement | null) => {
    if (node) setHeight(node.getBoundingClientRect().height);
  }, []);
  return <div ref={measuredRef}>Content</div>;
}
```

### Context Usage

```tsx
// Create typed context with null check
const AuthContext = createContext<AuthContextValue | null>(null);

function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within <AuthProvider>");
  return context;
}

// Split context to prevent unnecessary re-renders
// Bad: one context for everything
const AppContext = createContext({ theme: "light", user: null, locale: "en" });

// Good: separate contexts for separate concerns
const ThemeContext = createContext<Theme>("light");
const UserContext = createContext<User | null>(null);
const LocaleContext = createContext<string>("en");
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Hooks Assessment

**Stack:** {detected framework}
**React version:** {detected version}

### Custom Hooks

| Hook          | Concern           | Dependencies         | Cleanup Required |
| ------------- | ----------------- | -------------------- | ---------------- |
| {hookName}    | {what it manages} | {external deps}      | {Yes | No}       |

### Issues Found

- [Severity: High | Medium | Low] {description of hook issue}
  - Problem: {what is wrong}
  - Fix: {concrete correction}

### No Issues Found

{State explicitly if hook usage is correct - do not omit this section silently}
```

## Avoid

- Calling hooks conditionally or inside loops (breaks hook ordering)
- Using useEffect for data fetching (use TanStack Query, SWR, or Server Components)
- Using useEffect to compute derived state (compute during render instead)
- Suppressing the exhaustive-deps ESLint rule instead of fixing the dependency
- Creating custom hooks that manage multiple unrelated concerns
- Using useRef to store values that should trigger re-renders (use useState)
- Wrapping every callback in useCallback without evidence of performance need
- Using Context for high-frequency updates (theme/auth OK; form field values not OK)
