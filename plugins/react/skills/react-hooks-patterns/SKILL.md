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

- Hooks run only at the top level of a component or another hook -- never inside conditions, loops, nested functions, or after early returns. `use` is the sole exception and may be called in any of those positions.
- Custom hooks start with `use` and own exactly one concern.
- `useEffect` synchronizes with external systems. It is not for data fetching, derived state, or event-driven state transitions.
- Every subscription, listener, timer, or connection started in an effect returns a cleanup. Every in-flight fetch is cancellable (`AbortController`).
- Dependency arrays are exhaustive. Never suppress `react-hooks/exhaustive-deps`; fix the closure instead (move value into deps, into a ref, or out of the effect). Omitting the array entirely is legal only for the ref-mirror effect that must run every render.
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
// Bad - count captured once; interval increments from initial 0 forever.
useEffect(() => {
  const id = setInterval(() => setCount(count + 1), 1000);
  return () => clearInterval(id);
}, []); // adding `count` would tear down + reschedule the interval every tick.

// Good - functional update reads latest state without depending on it.
useEffect(() => {
  const id = setInterval(() => setCount(c => c + 1), 1000);
  return () => clearInterval(id);
}, []);

// Good - ref for values the effect must read but should not re-subscribe on
// (CallbackIdentityChurn: callback prop in deps tears down/re-subscribes every render).
const onMessageRef = useRef(onMessage);
useEffect(() => { onMessageRef.current = onMessage; });
useEffect(() => {
  const conn = createWebSocket(roomId);
  conn.connect();
  conn.on("message", (m) => onMessageRef.current(m));
  return () => conn.disconnect();
}, [roomId]);
```

State keyed to an identity (a room's messages) does not reset itself when the key changes; remount the component with `key={roomId}` or reset via a render-time previous-key comparison - never by clearing it inside the effect. Inside a custom hook only the render-time comparison is available, since the hook cannot set its caller's `key`.

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
const onCloseRef = useRef(onClose);
useEffect(() => { onCloseRef.current = onClose; });
useEffect(() => {
  const handler = (e: KeyboardEvent) => e.key === "Escape" && onCloseRef.current();
  document.addEventListener("keydown", handler);
  return () => document.removeEventListener("keydown", handler);
}, []);
```

The ref mirror keeps the callback prop out of the dep array; listing `onClose` there re-binds the listener every render, which is the `CallbackIdentityChurn` finding below. On React 19.2+ `useEffectEvent` replaces the mirror: declare the handler with it and call it from the effect, with no dep entry either way.

Same shape for `setInterval`/`setTimeout`, subscriptions, observers, `AbortController`.

### React 19 hooks

| Hook | Use when |
| ---- | -------- |
| `use(promise)` | Read a promise in render; may be called inside conditions, loops, and after early returns (unlike all other hooks). Suspends. |
| `useOptimistic` | Show a mutation result immediately; reconcile when the server confirms. Call its updater inside the submitting action/transition. |
| `useActionState` | Form action with pending + returned state (replaces `useFormState`). |
| `useFormStatus` | Read parent `<form>` pending state from a descendant - no prop drilling. |
| `useEffectEvent` | React 19.2+. Wrap the non-reactive part of an effect (a callback prop, a latest-value read) so it never enters the dep array. Replaces the hand-rolled ref mirror; call it only from inside an effect. |

```tsx
function UserProfile({ userPromise }: { userPromise: Promise<User> }) {
  const user = use(userPromise);
  return <div>{user.name}</div>;
}

const [optimisticTodos, addOptimistic] = useOptimistic(
  todos,
  (state, t: Todo) => [...state, t],
);

const [state, formAction, isPending] = useActionState(submitAction, { error: null });
```

### Form hooks (boundary)

Form schemas, validation, and submission flow are owned by `frontend-form-handling`. Here, only the React-19 wiring matters: bind a Server Action with `useActionState`; read pending state with `useFormStatus` from any `<form>` descendant; share the Zod schema between client and Server Action (one source of truth, parsed inside the action with `zod-form-data`).

### Refs and Context (boundary)

`useRef` keeps a mutable value that must not trigger re-render; `useState` triggers re-render. One hook-level trap: when an effect must re-run because the observed DOM node was replaced (a conditionally rendered subtree, a remounted row), store the node in state via a ref **callback** (`const [node, setNode] = useState<HTMLElement | null>(null)`, then `<div ref={setNode} />`) and list `node` as a dep. A `useRef` object mutation triggers no re-render, so an effect depending on `ref.current` never re-runs and the observer stays attached to the old node. Deeper ref ergonomics (`forwardRef`, ref-prop conventions) and `"use client"` placement belong to `react-component-patterns`. Context value memoization, split-by-update-frequency, and "state lib vs context" choices belong to `react-state-patterns`. This skill flags only: hook called conditionally inside a custom hook, ref used where state is needed (or vice versa), context provider value rebuilt every render.

## Output Format

When reviewing, open with one line `Scope: <files or components reviewed>`, then emit one block per finding. When designing or authoring a hook, emit the hook code, design notes mapping each decision to a Rule or Pattern by name, then a self-review of the new code in this same envelope (or the closing no-issues line); for code not yet written to a file, `Location:` names the hook and the line within the block you just emitted (`useAutosaveDraft:12`).

```
Scope: <files or components reviewed>

- Location: <file>:<line> (<hook or component>)
  Issue: {RulesOfHooks | StaleClosure | MissingDeps | MissingCleanup | EffectForFetch | EffectForDerivedState | InfiniteLoop | ConflictingWriters | CallbackIdentityChurn | UnstableDepIdentity | UnnecessaryMemo | RefVsStateMisuse | KitchenSinkHook | ContextOverbroad | UncancelledRequest | LegacyHookUsage | StaleStateAcrossKeyChange}
  Severity: {Critical | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name>
```

`ConflictingWriters`: same state mutated by two *independent* sources (e.g., incremented in a handler and overwritten by a derivation effect) - several writes within one effect's lifecycle are one source. Usually means the state is derivable and should be computed in render. `LegacyHookUsage`: pre-React-19 wiring a React 19 hook replaces (`useFormState`, manual pending flag, hand-rolled optimistic copy). `StaleStateAcrossKeyChange`: state keyed to an identity survives the identity switch (old room's messages after `roomId` changes); fix by `key` remount or render-time previous-key reset. `CallbackIdentityChurn`: a callback prop in a dep array tears down/re-subscribes the effect every render; use a ref. `UnstableDepIdentity`: a non-primitive dep (object/array literal, inline-built `config`/`options`) recreated every render re-fires the effect every render - hoist to a module constant, wrap in `useMemo`, or depend on its primitive fields. Use this for plain data; use `CallbackIdentityChurn` for functions.

Severity guide:
- **Critical**: a hook other than `use` called conditionally; memory leak from missing cleanup on a long-lived component; an out-of-order response overwriting newer state because the request was never cancelled.
- **High**: stale closure producing wrong values; uncancelled fetch on unmount; effect-driven infinite loop; unstable dep identity causing a refetch/re-subscribe loop; a callback prop in deps re-subscribing a long-lived connection (socket, observer); previous key's data shown after an identity switch; legacy form wiring that is behaviorally broken (action state never bound).
- **Medium**: derived state in effect; useEffect for fetching when a query library is available (the merged finding is High when the fetch is also uncancelled); suppressed exhaustive-deps; unstable dep identity causing redundant (non-looping) effect runs; `CallbackIdentityChurn` re-adding a cheap listener; working `LegacyHookUsage`.
- **Low**: unnecessary useMemo/useCallback; overbroad context; ref/state misuse without observable consequence.

Every Issue value sits in exactly one severity band above; a value named in no band is Medium. `MissingDeps`, `ConflictingWriters` and `KitchenSinkHook` are Medium unless the closure they create produces a wrong value, which raises them to High.

Emit one finding per distinct root cause, ordered by severity; Location may span a range (`file:8-14`). Symptoms sharing one root cause merge into a single finding at the highest applicable severity: an uncancelled fetch merges into `EffectForFetch` when a query library is available, a lint suppression merges into the closure finding on its dep array, manual pending + unbound action state merge into one `LegacyHookUsage`. Split only when the fixes are independent. When two Issue values describe one defect, the one whose Fix you are prescribing wins: a dep the effect should simply list is `MissingDeps`, a dep that cannot be listed without breaking the effect is `StaleClosure`, and a value that should not be in an effect at all is `EffectForDerivedState`. `EffectForFetch` applies whether or not a query library is present; with none available the fix is the AbortController pattern and the severity is High when the request is also uncancelled.

Non-finding observations (a call confirmed legal, an out-of-scope compile error) go in a single trailing `Notes:` line.

If no issues, emit a single line: `No hook issues found in <scope>.` The trailing `Notes:` line may follow it.
