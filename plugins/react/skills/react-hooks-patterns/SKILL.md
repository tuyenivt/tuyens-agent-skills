---
name: react-hooks-patterns
description: "Review React 19 hooks: rules of hooks, useEffect discipline, stale closures, cleanup, custom hooks, refs, context, use/useOptimistic/useActionState."
metadata:
  category: frontend
  tags: [react, hooks, useEffect, custom-hooks, react-19, refs, context]
user-invocable: false
---

# React Hooks Patterns

> Load `Use skill: stack-detect` first to determine the project stack and React version.

## When to Use

- Designing or reviewing custom hooks
- Diagnosing stale closures, missing deps, infinite loops, missing cleanup
- Choosing between useEffect, useMemo, useCallback, useRef, and render-time computation
- Adopting React 19 hooks (`use`, `useOptimistic`, `useActionState`, `useFormStatus`)

## Rules

- Hooks run only at the top level of a component or another hook -- never inside conditions, loops, nested functions, or after early returns.
- Custom hooks start with `use` and own exactly one concern.
- `useEffect` synchronizes with external systems. It is not for data fetching, derived state, or event-driven state transitions.
- Every subscription, listener, timer, or connection started in an effect returns a cleanup. Every in-flight fetch is cancellable (`AbortController`).
- Dependency arrays are exhaustive. Never suppress `react-hooks/exhaustive-deps`; fix the closure instead (move value into deps, into a ref, or out of the effect).
- `useMemo`/`useCallback` require a measured reason: referential identity for a memoized child, or a profiled expensive computation. Default is no memoization.
- `useRef` for values that must persist without triggering re-render; `useState` when a change must re-render.

## Patterns

### useEffect is for external synchronization

```tsx
// Bad - data fetching in useEffect: no cancellation, race on fast nav, no caching.
useEffect(() => {
  fetch(`/api/users/${id}`).then(r => r.json()).then(setUser);
}, [id]);

// Good - server cache library handles cancellation, dedupe, errors.
const { data: user } = useQuery({ queryKey: ["user", id], queryFn: () => fetchUser(id) });

// Good - effect when you actually sync with an external system.
useEffect(() => {
  const conn = createWebSocket(roomId);
  conn.connect();
  return () => conn.disconnect();
}, [roomId]);
```

If no server-cache library is available, still cancel on cleanup:

```tsx
useEffect(() => {
  const ctrl = new AbortController();
  fetch(`/api/users/${id}`, { signal: ctrl.signal })
    .then(r => r.json()).then(setUser)
    .catch(e => { if (e.name !== "AbortError") setError(e); });
  return () => ctrl.abort();
}, [id]);
```

### Derived state is computed during render

```tsx
// Bad - extra render, drift risk.
const [total, setTotal] = useState(0);
useEffect(() => { setTotal(items.reduce((s, i) => s + i.price, 0)); }, [items]);

// Good - derive directly; wrap in useMemo only if profiled expensive.
const total = items.reduce((s, i) => s + i.price, 0);
```

### Stale closures: deps, ref, or functional update

```tsx
// Bad - count is captured once; interval always increments from the initial 0.
useEffect(() => {
  const id = setInterval(() => setCount(count + 1), 1000);
  return () => clearInterval(id);
}, []); // missing `count`; adding it resets the interval every tick.

// Good - functional update reads latest state without depending on it.
useEffect(() => {
  const id = setInterval(() => setCount(c => c + 1), 1000);
  return () => clearInterval(id);
}, []);

// Good - ref for values the effect must read but should not re-subscribe on.
const onMessageRef = useRef(onMessage);
useEffect(() => { onMessageRef.current = onMessage; });
useEffect(() => {
  const conn = createWebSocket(roomId);
  conn.on("message", (m) => onMessageRef.current(m));
  return () => conn.close();
}, [roomId]);
```

### Custom hook = one concern, clear return shape

```tsx
// Bad - kitchen sink: fetches user, posts, theme, notifications in one hook.
function useUser(id: string) { /* multiple unrelated states and effects */ }

// Good - one hook per concern, composable at the call site.
function useUser(id: string)      { return useQuery({ queryKey: ["user", id], queryFn: () => fetchUser(id) }); }
function useUserPosts(id: string) { return useQuery({ queryKey: ["user", id, "posts"], queryFn: () => fetchUserPosts(id), enabled: !!id }); }
```

### Cleanup is mandatory for any external acquisition

```tsx
useEffect(() => {
  const handler = (e: KeyboardEvent) => e.key === "Escape" && onClose();
  document.addEventListener("keydown", handler);
  return () => document.removeEventListener("keydown", handler);
}, [onClose]);
```

Same shape for `setInterval`/`setTimeout`, subscriptions, observers, `AbortController`.

### React 19 hooks

```tsx
// `use` - read a promise or context in render; may be called conditionally (unlike useContext).
function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  const user = use(userPromise); // suspends
  return <div>{user.name}</div>;
}

// `useOptimistic` - show the update immediately; reconcile when the server confirms.
const [optimisticTodos, addOptimistic] = useOptimistic(
  todos,
  (state, t: Todo) => [...state, t],
);

// `useActionState` - form action with pending + returned state (replaces useFormState).
const [state, formAction, isPending] = useActionState(submitAction, { error: null });
```

### Refs

```tsx
const inputRef = useRef<HTMLInputElement>(null);
useEffect(() => { inputRef.current?.focus(); }, []);

// Callback ref when you need to measure or react to mount of a dynamic node.
const measuredRef = useCallback((node: HTMLDivElement | null) => {
  if (node) setHeight(node.getBoundingClientRect().height);
}, []);
```

### Context: typed, narrow, split by update frequency

```tsx
const AuthContext = createContext<AuthValue | null>(null);
export function useAuth() {
  const v = useContext(AuthContext);
  if (!v) throw new Error("useAuth must be used within <AuthProvider>");
  return v;
}

// Split contexts so a theme change does not re-render auth consumers.
const ThemeContext  = createContext<Theme>("light");
const UserContext   = createContext<User | null>(null);
```

For values that change every keystroke (form fields, cursor), use local state or a state library -- not context.

## Output Format

When reviewing hook code, emit one block per finding:

```
- Location: <file>:<line> (<hook or component>)
  Issue: {RulesOfHooks | StaleClosure | MissingDeps | MissingCleanup | EffectForFetch | EffectForDerivedState | ConflictingWriters | CallbackIdentityChurn | UnboundedMemo | RefVsStateMisuse | KitchenSinkHook | ContextOverbroad | UncancelledRequest}
  Severity: {Critical | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name>
```

`ConflictingWriters`: same state mutated by two sources (e.g., incremented in a handler and overwritten by a derivation effect). Usually means the state is derivable and should be computed in render. `CallbackIdentityChurn`: a callback prop in a dep array tears down/re-subscribes the effect every render; use a ref.

Severity guide:
- **Critical**: hook called conditionally; memory leak from missing cleanup on long-lived component; race condition setting state after unmount.
- **High**: stale closure producing wrong values; uncancelled fetch on unmount; effect-driven infinite loop.
- **Medium**: derived state in effect; useEffect for fetching when a query library is available; suppressed exhaustive-deps.
- **Low**: unnecessary useMemo/useCallback; overbroad context.

If no issues, emit a single line: `No hook issues found in <scope>.`
