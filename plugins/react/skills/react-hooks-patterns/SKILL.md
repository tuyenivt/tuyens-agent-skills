---
name: react-hooks-patterns
description: "Review React 19 hooks: rules of hooks, useEffect discipline, stale closures, cleanup, custom hooks, refs, context, use/useOptimistic/useActionState."
metadata:
  category: frontend
  tags: [react, hooks, useEffect, custom-hooks, react-19, refs, context]
user-invocable: false
---

# React Hooks Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing or reviewing custom hooks
- Diagnosing stale closures, missing deps, infinite loops, missing cleanup
- Choosing between useEffect, useMemo, useCallback, useRef, and render-time computation
- Adopting React 19 hooks (`use`, `useOptimistic`, `useActionState`, `useFormStatus`)

## Rules

- Hooks run only at the top level of a component or another hook -- never inside conditions, loops, nested functions, or after early returns. `use` is the sole exception: it may sit inside conditions and loops and after early returns, but still only in a component or hook body - not in a nested function or a try/catch.
- Custom hooks start with `use` and own exactly one concern.
- `useEffect` synchronizes with external systems. It is not for derived state or event-driven state transitions, and not for data fetching (with no server-cache library, the AbortController form below is the minimum).
- Every subscription, listener, timer, or connection started in an effect returns a cleanup. Every in-flight fetch is cancellable (`AbortController`); the one exception is a final flush on unmount, `pagehide`, or `visibilitychange` to hidden, sent with `fetch(..., { keepalive: true })` so it completes.
- Dependency arrays are exhaustive. Never suppress `rules-of-hooks`, `exhaustive-deps` or an error-level compiler rule; fix the closure instead (list the value, move the non-reactive read into `useEffectEvent`, or move it out of the effect). `eslint-config-next` ships `eslint-plugin-react-hooks` 7, whose recommended set adds compiler-derived error rules (`set-state-in-effect`, `refs`, `purity`, `immutability`, `preserve-manual-memoization`) to `rules-of-hooks` and `exhaustive-deps`, plus the warn-level `incompatible-library` / `unsupported-syntax`, which mark code the compiler skips and have no closure fix; run it with the ESLint CLI (`next lint` is removed).
- `useMemo`/`useCallback` require a measured reason: referential identity for a memoized child or for an effect dependency that must not re-fire, or a profiled expensive computation. Default is no memoization. With the React Compiler on (`reactCompiler` in `next.config`, or a leftover `experimental.reactCompiler`; in `compilationMode: 'annotation'` only `"use memo"` components), new manual memoization is unnecessary there; `react-overengineering-review` judges memoization on a compiler-on project.
- `useRef` for values that must persist without triggering re-render; `useState` when a change must re-render.

## Patterns

### useEffect is for external synchronization

```tsx
// Bad - data fetching in useEffect: no cancellation, race on fast nav, no caching.
useEffect(() => {
  fetch(`/api/users/${id}`).then(r => r.json()).then(setUser);
}, [id]);

// Good - read in a Server Component and pass the data (or a Promise the client unwraps with use()) as props.
// Good - interactive client data: a query library handles key-scoped races, dedupe, errors; it aborts only if the fetcher takes the signal.
const { data: user } = useQuery({ queryKey: ["user", id], queryFn: ({ signal }) => fetchUser(id, { signal }) });

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

### Stale closures: deps, functional update, or `useEffectEvent`

```tsx
// Bad - count captured once as 0; every tick sets 0 + 1, so it sticks at 1.
useEffect(() => {
  const id = setInterval(() => setCount(count + 1), 1000);
  return () => clearInterval(id);
}, []); // adding `count` would tear down + reschedule the interval every tick.

// Good - functional update reads latest state without depending on it.
useEffect(() => {
  const id = setInterval(() => setCount(c => c + 1), 1000);
  return () => clearInterval(id);
}, []);

// Good - useEffectEvent for values the effect must read but should not re-subscribe on
// (CallbackIdentityChurn: callback prop in deps tears down/re-subscribes every render).
const onMsg = useEffectEvent((m: Message) => onMessage(m));
useEffect(() => {
  const conn = createWebSocket(roomId);
  conn.connect();
  conn.on("message", (m) => onMsg(m));
  return () => conn.disconnect();
}, [roomId]);
```

State keyed to an identity (a room's messages) does not reset itself when the key changes; remount the component with `key={roomId}` or reset via a render-time previous-key comparison - never by clearing it inside the effect. Inside a custom hook only the render-time comparison is available, since the hook cannot set its caller's `key`.

### Custom hook = one concern, clear return shape

```tsx
// Bad - kitchen sink: fetches user, posts, theme, notifications in one hook.
function useUser(id: string) { /* multiple unrelated states and effects */ }

// Good - one hook per concern, composable at the call site.
function useUser(id: string)      { return useQuery({ queryKey: ["user", id], queryFn: ({ signal }) => fetchUser(id, { signal }) }); }
function useUserPosts(id: string) { return useQuery({ queryKey: ["user", id, "posts"], queryFn: ({ signal }) => fetchUserPosts(id, { signal }), enabled: !!id }); }
```

### Cleanup is mandatory for any external acquisition

```tsx
const onEscape = useEffectEvent(() => onClose());
useEffect(() => {
  const handler = (e: KeyboardEvent) => e.key === "Escape" && onEscape();
  document.addEventListener("keydown", handler);
  return () => document.removeEventListener("keydown", handler);
}, []);
```

`useEffectEvent` keeps the callback prop out of the dep array; listing `onClose` there re-binds the listener every render, which is the `CallbackIdentityChurn` finding below. Call an Effect Event only from inside an effect. A hand-rolled ref mirror (`ref.current = onClose` in an effect) is `LegacyHookUsage` in new code.

Same shape for `setInterval`/`setTimeout`, subscriptions, observers, `AbortController`.

Writes need ordering too: tag each save with an increasing sequence number and apply a response only if its number is still the latest, so an older save never overwrites a newer one - aborting the previous request is the other half.

### Hidden routes (Cache Components)

With `cacheComponents: true` in `next.config`, Next hides a route you leave with `<Activity mode="hidden">` instead of unmounting it (up to 3 routes): state and DOM survive, cleanups run on hide, and effects re-run on every re-show. An effect must therefore be safe to repeat: a mount-time analytics event or one-time setup guards first mount with a ref (refs survive hide/show), and `<video>` / `<audio>` keep playing under `display: none` until a `useLayoutEffect` cleanup pauses them. Without the flag navigation unmounts the route, but an `<Activity>` the code renders itself hides and re-shows the same way.

### React 19 hooks

| Hook | Use when |
| ---- | -------- |
| `use(promise)` | Read a promise in render; may be called inside conditions, loops, and after early returns (unlike all other hooks). Suspends. |
| `useOptimistic` | Show a mutation result immediately; reconcile when the server confirms. Call its updater inside the submitting action/transition. |
| `useActionState` | Form action with pending + returned state (replaces `useFormState`). |
| `useFormStatus` | Read parent `<form>` pending state from a descendant - no prop drilling. |
| `useEffectEvent` | Wrap the non-reactive part of an effect (a callback prop, a latest-value read) so it never enters the dep array. Replaces the hand-rolled ref mirror; call it only from inside an effect. |
| `<Activity mode>` | Hide UI while keeping its state; effects clean up when hidden and re-run when shown (see Hidden routes). |

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

Form schemas, validation, and submission flow are owned by `frontend-form-handling`. Here, only the React-19 wiring matters: bind a Server Action with `useActionState`; read pending state with `useFormStatus` from any `<form>` descendant; share the Zod schema between client and Server Action (one source of truth, parsed inside the action as `frontend-form-handling` prescribes).

### Refs and Context (boundary)

`useRef` keeps a mutable value that must not trigger re-render; `useState` triggers re-render. One hook-level trap: when an effect must re-run because the observed DOM node was replaced (a conditionally rendered subtree, a remounted row), store the node in state via a ref **callback** (`const [node, setNode] = useState<HTMLElement | null>(null)`, then `<div ref={setNode} />`) and list `node` as a dep. A `useRef` object mutation triggers no re-render, so the node swap alone schedules no re-run of an effect depending on `ref.current`, and the observer can stay attached to the old node. Deeper ref ergonomics (ref as a prop, polymorphic ref types) and `"use client"` placement belong to `react-component-patterns`. Context value memoization, split-by-update-frequency, and "state lib vs context" choices belong to `react-state-patterns`. This skill flags only: hook called conditionally inside a custom hook, ref used where state is needed (or vice versa), an overbroad context a hook exposes.

## Output Format

When reviewing, open with one line `Scope: <files or components reviewed>`, then emit one block per finding. When designing or authoring a hook, emit the hook code, design notes mapping each decision to a Rule or Pattern by name, then a self-review of the new code in this same envelope, opened with `Scope: <hook> (authored)` (or the closing no-issues line); for code not yet written to a file, `Location:` names the hook and the line within the block you just emitted (`useAutosaveDraft:12`).

```
Scope: <files or components reviewed>

- Location: <file>:<line> (<hook or component>)
  Issue: {RulesOfHooks | StaleClosure | MissingDeps | MissingCleanup | EffectForFetch | EffectForDerivedState | InfiniteLoop | ConflictingWriters | CallbackIdentityChurn | UnstableDepIdentity | UnnecessaryMemo | RefVsStateMisuse | KitchenSinkHook | ContextOverbroad | UncancelledRequest | LegacyHookUsage | StaleStateAcrossKeyChange | ActivityReshow}
  Severity: {Critical | High | Medium | Low}
  Evidence: <quoted snippet or symbol>
  Fix: <one-line action; reference a Pattern by name>
```

`ConflictingWriters`: same state mutated by two *independent* sources (e.g., incremented in a handler and overwritten by a derivation effect) - several writes within one effect's lifecycle are one source. Usually means the state is derivable and should be computed in render. `LegacyHookUsage`: hand-rolled wiring a React 19 API replaces (`useFormState`, manual pending flag, hand-rolled optimistic copy, a ref mirror feeding an effect). `StaleStateAcrossKeyChange`: state keyed to an identity survives the identity switch (old room's messages after `roomId` changes), including state seeded from a prop and never resynced when that prop changes; fix by `key` remount or render-time previous-key reset. `UncancelledRequest` covers requests fired from event handlers too (a double-click racing two POSTs): guard with the pending state of a transition or apply only the latest response. `CallbackIdentityChurn`: a callback prop in a dep array tears down/re-subscribes the effect every render; wrap the callback in `useEffectEvent`. `ActivityReshow`: under `cacheComponents` or inside an `<Activity>` the code renders, an effect that is wrong to repeat when a hidden route is shown again (a duplicate analytics event, a re-run one-time setup), or media still playing while hidden. `UnstableDepIdentity`: a non-primitive dep (object/array literal, inline-built `config`/`options`) recreated every render re-fires the effect every render - hoist to a module constant, wrap in `useMemo`, or depend on its primitive fields. Use this for plain data; use `CallbackIdentityChurn` for functions.

Severity guide:
- **Critical**: any `RulesOfHooks` violation (a hook other than `use` called conditionally, in a loop, in a nested function or after an early return; `use` in a nested function or try/catch); memory leak from missing cleanup on a long-lived component; an uncancelled request that can overwrite newer state (its input changes while it is in flight).
- **High**: stale closure producing wrong values; uncancelled fetch on unmount (no newer request to overwrite); missing cleanup on a short-lived component whose leak repeats per mount (a custom hook with no call site in scope takes this band); effect-driven infinite loop; unstable dep identity causing a refetch/re-subscribe loop; a callback prop in deps re-subscribing a long-lived connection (socket, observer); previous key's data shown after an identity switch; legacy form wiring that is behaviorally broken (action state never bound).
- **Medium**: derived state in effect; useEffect for fetching when a query library is available (the merged finding takes the uncancelled-request band when the fetch is also uncancelled); `MissingDeps` via a suppressed exhaustive-deps lint; unstable dep identity causing redundant (non-looping) effect runs; `CallbackIdentityChurn` re-adding a cheap listener; working `LegacyHookUsage`.
- **Low**: unnecessary useMemo/useCallback; overbroad context; ref/state misuse without observable consequence (with one - a stale render, a missed update - it is Medium).

An Issue value's band is set by the condition named in the bands above; a value named in no band is Medium. `MissingDeps` and `ConflictingWriters` are Medium unless the closure they create produces a wrong value, which raises them to High; `KitchenSinkHook` is Medium, High when its bundled state produces a wrong value.

Emit one finding per distinct root cause, ordered by severity; Location may span a range (`file:8-14`). `Location` may list several `file:line` entries (or several lines of one file), comma-separated, when one root cause spans them; lead with the file the fix changes, and sort the finding by that lead file. (State that survives in a child but is fixed by a `key` in its caller leads with the caller.) Symptoms sharing one root cause merge into a single finding at the highest applicable severity: an uncancelled fetch merges into `EffectForFetch`, a lint suppression merges into the closure finding on its dep array, manual pending + unbound action state merge into one `LegacyHookUsage`. Split only when the fixes are independent. When two Issue values describe one defect, the one whose Fix you are prescribing wins: a dep the effect should simply list is `MissingDeps`, a dep that cannot be listed without breaking the effect is `StaleClosure`, and a value that should not be in an effect at all is `EffectForDerivedState`. `EffectForFetch` applies whether or not a query library is present; with none available the fix is the AbortController pattern and the severity follows the uncancelled-request bands.

Non-finding observations (a call confirmed legal, an out-of-scope compile error) go in a single trailing `Notes:` line.

If no issues, emit a single line: `No hook issues found in <scope>.` The trailing `Notes:` line may follow it.
