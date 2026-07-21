---
name: task-react-review-reliability
description: "React / Next.js reliability review: error boundaries, retry and cancellation, optimistic rollback, offline, hydration, chunk-load failure."
agent: react-reliability-engineer
metadata:
  category: frontend
  tags: [react, typescript, nextjs, reliability, error-boundary, tanstack-query, offline, retry, hydration, workflow]
  type: workflow
user-invocable: true
---

# React Reliability Review

Stack-specific delegate of `task-code-review-reliability` for React / Next.js / Vite. Preserves the parent contract (invocation, diff resolution, output shape).

Client reliability: what the UI does when a request hangs, a mutation fails after the screen already showed success, the user's network drops, hydration diverges, or a chunk 404s because the app was redeployed while the tab was open. **The browser is one user, one tab, one build that may already be stale.** Every finding names the failure mode and what the user sees, not just the missing pattern.

## When to Use

- Next.js or Vite + React PR adding or changing a fetch, TanStack Query hook, mutation, or Server Action
- A route reviewed for error-boundary coverage, loading / error / empty completeness, or offline behavior
- Hardening after a blank screen, a stuck spinner, a lost write, or a post-deploy `ChunkLoadError` spike
- Optimistic-update, cache-invalidation, or retry-policy correctness review

**Not for:** general review (`task-react-review`), Core Web Vitals and bundle cost (`task-react-review-perf`), instrumentation coverage (`task-react-review-observability`), XSS / auth / CSP (`task-react-review-security`), a live incident (`/task-oncall-start` - mitigate first), fixing the API's own unreliability (route to the owning service).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns the app doing too much work; this lens owns the app not surviving something else failing. A route stuck on a skeleton because a `fetch` has no timeout is reliability, even though it reads as slowness.
- **vs. Observability:** obs owns whether the failure was reported (`Sentry.captureException` in `error.tsx`, error-rate alerting); this lens owns whether the boundary, retry, and fallback exist at all. A boundary with no capture is obs; a route with no boundary is reliability.
- **vs. Security:** a `fetch` retried against an auth-expired session is reliability; the session handling itself is security.
- **vs. umbrella Phase B:** `task-react-review` Phase B owns happy-path correctness, hook rules, and cleanup; this lens owns partial failure, staleness, and offline. Cleanup sits at the seam - an in-flight request not aborted on unmount belongs here; a `setInterval` never cleared is a Phase B leak. The umbrella dedups.
- **There is no `+api` scope for a client.** How the UI survives a response it did not expect is this lens; whether the contract is well designed belongs to the owning service or the architecture plugin.

## Depth

| Depth      | When                                              | Runs                                     |
| ---------- | ------------------------------------------------- | ---------------------------------------- |
| `standard` | Default                                           | All steps except the Failure-Mode Map    |
| `deep`     | Requested, or handed down by `task-react-review`  | All + `Failure-Mode and User-Impact Map` |

At `deep`, trace each new or changed data dependency with `failure-propagation-analysis` and name, per dependency, what the user sees when it is slow, absent, or returns something unexpected, and what contains it.

**Whole-app sweep** (reliability-debt pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-11 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-react-review-reliability` | Current branch vs base; fails fast on trunk |
| `/task-react-review-reliability <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-react-review-reliability pr-<N>` | PR head in local branch `pr-<N>` (user runs the fetch) |

Append `deep` for the deep pass; `--base <branch>` for a non-trunk base. When invoked as a subagent of `task-react-review` or `task-code-review-reliability`, the parent passes the pre-confirmed stack and framework, the precondition handle, the pre-read diff and commit log, and the depth level; Steps 2-3 consume those instead of re-running, and Step 11 returns findings instead of writing.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows; accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept a pre-confirmed stack from the parent and skip detection. If not React, stop and route the user to `/task-code-review-reliability`.

Record for the Summary block:

- `Framework:` Next.js (App Router) | Next.js (Pages Router) | Vite + React Router
- `Data Layer:` Server Components + `fetch` | TanStack Query | SWR | mixed
- `Boundary Library:` `error.tsx` segments | `react-error-boundary` | hand-rolled `componentDidCatch` | none detected

Heuristics: `next.config.*` -> Next.js (App Router unless `pages/` without `app/`); `vite.config.*` without `next` -> Vite; both present -> ask the user. React 19 adds `useActionState`, `useOptimistic`, and `createRoot` error options (`onCaughtError` / `onUncaughtError` / `onRecoverableError`) - note the version, later steps branch on it.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once; reuse. Skip entirely when the parent passed the handle and artifacts. Surface any fail-fast verbatim. No state-changing git.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 4 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into - a small diff ripples: a new hook calling an unchanged untimed fetch wrapper is a new hang at the call site.

- Boundary files: `app/**/error.tsx`, `app/global-error.tsx`, `app/**/loading.tsx`, `<ErrorBoundary>` mounts, `errorElement` in the Vite router
- Fetch layer: `fetch` wrappers, `axios` / `ky` instances, Server Component `fetch` calls, Route Handlers the client calls
- TanStack Query / SWR: `QueryClient` defaults, `useQuery` / `useMutation` call sites, query-key factories
- Mutation and write paths: Server Actions (`"use server"`), `useActionState` / `useOptimistic` consumers, `revalidatePath` / `revalidateTag` calls
- Route and boundary structure: `<Suspense>` placement, `next/dynamic` and `React.lazy` sites, third-party `<Script>` tags
- `next.config.*` and deploy config where chunk retention / `deploymentId` is set

Use skill: `react-data-fetching` - it owns the canonical query, mutation, invalidation, and optimistic-rollback patterns. Use skill: `ops-resiliency` for retry / backoff / fallback framing, applied to browser-to-API calls. Use skill: `failure-propagation-analysis` to trace how each new or changed dependency's failure reaches the user - this gives each finding its user impact.

### Step 5 - Error Boundaries and Render-Time Failure

Use skill: `react-component-patterns` for boundary placement and fallback shape. Use skill: `react-nextjs-patterns` (Next.js) for segment-file semantics.

- [ ] **A boundary above every route that renders remote data.** With none, one throw unmounts the whole tree and the user gets a blank white page with no way back.
- [ ] **Granularity matches the blast radius wanted.** A single root boundary turns a failed sidebar widget into a dead app; wrap optional regions so a partial failure degrades that region only.
- [ ] **Next.js segment semantics respected:** `error.tsx` is a Client Component receiving `{ error, reset }`, and it does **not** catch errors thrown by the layout of its own segment - that needs a boundary in the parent segment. `global-error.tsx` catches root-layout errors, must render its own `<html>` and `<body>`, and is only active in production.
- [ ] **`reset` / `resetKeys` actually recover.** A `reset()` that re-renders the same failed state is a dead button; reset must be paired with re-running the query or with `resetKeys` on the value that changed (`react-error-boundary`).
- [ ] **Event-handler and async errors are routed to a boundary explicitly.** Boundaries catch render, lifecycle, and constructor errors only - a `throw` inside `onClick` or after an `await` never reaches them. Use `useErrorBoundary().showBoundary(error)` or handle it as local state; do not assume the boundary sees it.
- [ ] **The fallback is usable:** what failed, a retry affordance, and a way out (back / home). No raw `error.message`, stack trace, or blank `<div>`. `error.digest` is the correlation id to show, not the message.

```tsx
// Bad - reset re-renders the same failed query; the button does nothing
export default function Error({ error, reset }) {
  return <button onClick={reset}>Retry</button>;
}

// Good - clear the cached failure, then reset
export default function Error({ error, reset }) {
  const qc = useQueryClient();
  return (
    <>
      <p>Could not load orders. Reference {error.digest}</p>
      <button onClick={() => { qc.resetQueries({ queryKey: ["orders"] }); reset(); }}>Retry</button>
      <Link href="/">Go home</Link>
    </>
  );
}
```

### Step 6 - Fetch Failure, Retry, and Cancellation

Use skill: `react-hooks-patterns` for the effect-cleanup contract behind hand-rolled fetch cancellation.

- [ ] **A timeout on every request.** Browser `fetch` and Node's `fetch` in a Server Component both wait forever by default: use `AbortSignal.timeout(ms)`, composed with the caller's signal via `AbortSignal.any([signal, AbortSignal.timeout(ms)])`. An untimed `fetch` inside an RSC stalls the stream and the route never resolves.
- [ ] **Retryable is decided by status, not by retrying everything.** TanStack Query defaults to `retry: 3` for queries - which retries a 404 and a 403 three times, turning a fast failure into a slow one. Gate it: retry 408 / 429 / 5xx and network errors, never other 4xx.
- [ ] **Backoff is capped.** TanStack's default `retryDelay` is exponential capped at 30s; a hand-rolled loop needs the same cap plus jitter, or a recovering API gets a synchronized retry wave from every open tab.
- [ ] **`Retry-After` honored when present** - it is seconds or an HTTP-date, never milliseconds; never wait less than the server asks.
- [ ] **In-flight requests are cancelled on unmount and on route change.** Pass the `signal` TanStack Query hands the `queryFn` straight into `fetch` so a key change or unmount aborts the request; a hand-rolled `useEffect` fetch needs its own `AbortController` aborted in the cleanup. Without it the response resolves into an unmounted tree and a fast navigation leaves a stale response overwriting a newer one.
- [ ] **An aborted request is not an error.** `AbortError` is dropped, never rendered as a failure banner on a route the user already left.
- [ ] **`throwOnError` is a deliberate choice per query.** It routes the failure to the nearest boundary (whole region replaced); leaving it off keeps the failure inline in `error`. Picking neither means the component silently renders with `data === undefined`.

```tsx
// Bad - retries a 403 three times, never cancels, never times out
useQuery({ queryKey: ["orders"], queryFn: () => fetch("/api/orders").then(r => r.json()) });

// Good - transient-only retry, request bound to the query's lifetime and a deadline
useQuery({
  queryKey: ["orders"],
  retry: (n, e: HttpError) => n < 3 && (e.status >= 500 || e.status === 429),
  queryFn: async ({ signal }) => {
    const res = await fetch("/api/orders", {
      signal: AbortSignal.any([signal, AbortSignal.timeout(10_000)]),
    });
    if (!res.ok) throw new HttpError(res.status);
    return res.json();
  },
});
```

### Step 7 - Mutations, Optimistic Rollback, and Server Actions

- [ ] **Every optimistic update has a rollback path.** The `onMutate` / `onError` / `onSettled` flow is not optional: `cancelQueries` (so an in-flight refetch cannot overwrite the rollback), snapshot via `getQueryData`, apply, restore the snapshot in `onError`, `invalidateQueries` in `onSettled`. An optimistic UI with no rollback is a lie the user acts on. `useOptimistic` (React 19) reverts automatically when the action settles - the gap there is failing to tell the user it reverted.
- [ ] **Mutations are not retried blind.** TanStack defaults mutations to `retry: 0`; turning retry on for a non-idempotent write double-applies it, because the client cannot distinguish a lost response from a lost request. Retry a write only with an idempotency key the server dedups on.
- [ ] **Server Actions are idempotent or guarded.** A user double-submitting, or React re-running the action after a transient failure, must not create two records. Disable the submit via `useFormStatus().pending`, and dedup server-side on a key.
- [ ] **Server Action failure reaches the UI.** Return a typed error state and surface it through `useActionState`; a thrown error in a Server Action becomes an opaque digest in production, so the user sees the generic boundary instead of "email already taken". Validation failures are returned state, not throws.
- [ ] **A rollback does not clobber a concurrent edit.** Restoring a whole list snapshot discards an item edited while the request was in flight; reconcile at the item level where concurrent edits are possible.

### Step 8 - Cache Staleness and Invalidation

- [ ] **Every mutation invalidates what it changed.** An untouched cache after a write is the most common stale-UI bug: the user saves, navigates back, and sees the old value.
- [ ] **`revalidateTag` over full-route `revalidatePath`**, and both must run on the server after the write - inside the Server Action or Route Handler, not during render (Next 15 no-ops a revalidate called in a render pass). Missing it leaves the RSC payload cached and the fresh client cache disagreeing with the server-rendered shell.
- [ ] **Invalidation covers every affected key**, including list + detail + count queries and any parallel route sharing the entity. A key factory makes this auditable; ad-hoc string keys make it guesswork.
- [ ] **`staleTime` is a stated decision per query.** The default `0` refetches on every mount; a long `staleTime` on data another user can change shows one tab a value the other tab already changed.
- [ ] **Cross-tab consistency is defined where it matters.** Auth state, feature flags, and entitlement changes propagate via `BroadcastChannel` or the `storage` event; without it a logged-out tab keeps issuing requests with a dead session and shows repeated failures instead of a login prompt.

### Step 9 - Offline and Degraded Network

- [ ] **`navigator.onLine` reports a network interface, not reachability.** A captive portal, a VPN, or a dead API all report `true`. Treat it as a hint for the affordance to show; treat the request result as the truth.
- [ ] **Offline is a defined state with its own affordance**, distinct from "the server broke" - not a generic error toast and not an empty list.
- [ ] **Refetch on reconnect is wired and bounded.** TanStack's `onlineManager` drives `refetchOnReconnect`; verify it is not disabled globally, and that reconnect does not fire every stale query at once against an API that just came back.
- [ ] **Cached data is served as a fallback rather than blanking the page.** A full-screen skeleton over data already in `gcTime` is a defect; render the cached value with a staleness indicator.
- [ ] **Offline writes have a defined answer** - rejected with a clear message, or queued with the queue's durability and ordering stated. A queue in a module-level array dies with the tab.
- [ ] **Rendering an empty list on failure is never acceptable** - "failed to load" and "you have none" must not look identical.

### Step 10 - Hydration, Streaming, and Chunk-Load Failure

- [ ] **No hydration-mismatch sources in render:** `Date.now()`, `Math.random()`, `new Date().toLocaleString()`, `window` / `localStorage` reads, or browser-extension-sensitive markup. React 19 recovers by discarding the server HTML and client-rendering the root, so a mismatch is not cosmetic - it costs the SSR result and can flash or drop state. `suppressHydrationWarning` silences one element; it is not a fix for the underlying divergence.
- [ ] **Suspense boundaries are placed so a slow or failing segment cannot hold the shell.** In the App Router `loading.tsx` is the segment's implicit Suspense boundary; `error.tsx` catches what that segment throws. Both belong to the same segment - `loading.tsx` alone means a failure has no boundary, `error.tsx` alone means a slow fetch blocks the shell.
- [ ] **Streaming failure is handled after the shell flushed.** Once streaming begins the status code is already sent, so an error later in the stream cannot become a 500 - it must resolve to an inline boundary fallback, or the user gets a half-rendered page. Errors thrown before the first flush can still redirect or 500.
- [ ] **Dynamic `import()` failure has a recovery path.** After a redeploy, a tab open on the old build requests chunks that no longer exist and every lazy route throws `ChunkLoadError` on click. Catch it in a boundary that detects the error and forces `location.reload()`, and keep prior build assets available (or set a stable `deploymentId`) so the window is survivable. This is the most commonly missed React reliability defect and it fires on every deploy.
- [ ] **Third-party scripts fail closed.** A blocked or timed-out analytics / chat / tag-manager script must not break the page: `next/script` with `strategy="lazyOnload"` and an `onError`, and no render path that assumes `window.<vendor>` exists.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and include its tally in the Summary. Subagent runs skip this - the parent verifies the merged set once.

### Step 11 - Write Report

**Subagent mode:** when invoked by `task-react-review` or `task-code-review-reliability`, return the findings in this skill's Output Format for the parent to merge and write nothing - the parent owns the report and `review-report-writer` rejects subagent writes. At `deep`, return the Failure-Mode and User-Impact Map with the findings so the parent preserves it as its own section. Skip the rest of this step.

Standalone: use skill: `review-report-writer` with `report_type: review-reliability` and every required field: `report_body`, `branch`, `base_ref` / `head_ref` from the precondition handle, `base_sha` / `head_sha` from Step 3 (whole-app sweep: both = `HEAD`), `scope: +rel`, `depth` as resolved from the Depth table, `stack: react`, and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Write before ending; print the confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = the user hits an unrecoverable or wrong state on a plausible failure (a route with no error boundary, `ChunkLoadError` with no recovery, an optimistic update with no rollback, a retried non-idempotent mutation or Server Action, an untimed `fetch` in an RSC render, a hydration mismatch, a `reset` that cannot recover); Medium = the failure is bounded but recovery or comprehension is impaired (missing invalidation after a mutation, retry on non-retryable 4xx, no cancellation on unmount, no offline affordance, error fallback with no next action, `loading.tsx` with no sibling `error.tsx`); Low = hardening with no immediate failure path (no jitter, `staleTime` undocumented, no cross-tab propagation on low-stakes state). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`.

**One finding per root cause:** a defect matching several checklist lines (an uncancelled query that also retries a 403) is reported once at the strongest severity with the other aspects folded in.

```markdown
## React Reliability Review Summary

**Stack Detected:** React <version> / TypeScript <version>
**Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
**Data Layer:** Server Components + `fetch` | TanStack Query | SWR | mixed
**Boundary Coverage:** every remote-data route | PARTIAL: <routes uncovered> | NONE
**Timeouts:** all requests bounded | PARTIAL: <where missing> | NONE
**Cancellation:** signal threaded at file:line | absent
**Offline:** defined per path | partial | undefined
**Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line]
   **Issue:** [name the React idiom: no `error.tsx` above the route, `retry: 3` on a 4xx, `signal` not threaded into `queryFn`, optimistic update with no `onError` rollback, `import()` with no `ChunkLoadError` recovery, hydration mismatch from `Date.now()`]
   **Failure Mode:** [what fails and how: "the orders `fetch` has no timeout, so a stalled API leaves the RSC stream open and the route never resolves"]
   **User Impact:** [what the person in the browser sees: "an indefinite skeleton on /orders; reloading reproduces it"]
   **Fix:** [concrete React / Next.js change]

### Medium Impact

[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins

[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural reliability improvements not tied to a single finding - a shared fetch wrapper with a default timeout, a query-key factory to make invalidation auditable, a root `ChunkLoadError` reload boundary.]

## Failure-Mode and User-Impact Map

_(`deep` only - omit at `standard`.)_
Per new or changed data dependency: **what happens when it is slow, absent, or returns something unexpected**, what the user sees in each case, and what contains it (a timeout, a bounded retry, a cached fallback, an offline state, an error boundary).

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: API contract] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (API contract, deploy config, platform). Order Must > Recommend. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no mutations, no dynamic imports).

- [ ] Step 1 - `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2 - stack confirmed React; `Framework`, `Data Layer`, `Boundary Library`, and React version recorded
- [ ] Step 3 - `review-precondition-check` ran (or parent handle accepted); diff + log read once; `current_head_sha` and `current_base_sha` captured
- [ ] Step 4 - boundary files, fetch layer, query/mutation sites, Server Actions, Suspense and lazy sites, deploy config read; `react-data-fetching`, `ops-resiliency`, and `failure-propagation-analysis` consulted for patterns and user impact
- [ ] Step 5 - `react-component-patterns` + `react-nextjs-patterns` consulted; boundary presence and granularity, segment semantics, working `reset` / `resetKeys`, async-error routing, usable fallback audited
- [ ] Step 6 - `react-hooks-patterns` consulted; timeout on every request, transient-only retry with capped backoff, `Retry-After`, `signal` threaded for unmount / route-change cancellation, `AbortError` not surfaced, `throwOnError` chosen deliberately
- [ ] Step 7 - optimistic rollback complete (cancel / snapshot / set / rollback / settle), no blind mutation retry, Server Actions idempotent and their failures surfaced via `useActionState`, rollback safe against concurrent edits
- [ ] Step 8 - mutations invalidate every affected key, `revalidateTag` / `revalidatePath` called server-side after the write, `staleTime` stated, cross-tab consistency defined where it matters
- [ ] Step 9 - `navigator.onLine` treated as a hint, offline a distinct state, bounded refetch-on-reconnect, cache used as fallback, offline writes defined, no empty-list-on-failure
- [ ] Step 10 - hydration-mismatch sources checked, `loading.tsx` / `error.tsx` paired per segment, post-flush streaming failure handled, `ChunkLoadError` recovery present, third-party scripts fail closed
- [ ] Step 11 - standalone: report written via `review-report-writer` (`scope: +rel`, `stack: react`), confirmation printed; subagent: findings returned to parent, no file written
- [ ] Every finding names the failure mode and what the user experiences, never just the missing pattern
- [ ] Client framing held - no connection pools, server middleware, graceful shutdown, or distributed-transaction recommendations
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and User-Impact Map
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend (omit if none)

## Avoid

- State-changing git (`fetch`, `checkout`, `reset`) - the user runs these to protect uncommitted work
- Reporting a missing pattern without the failure mode and user impact ("add a timeout" vs "an untimed `fetch` leaves an indefinite skeleton on /orders")
- Server framing on a client: connection pools, middleware, `SIGTERM` draining, service mesh, distributed transactions. The browser is one user, one tab, one build
- Writing a report when invoked as a subagent - the parent owns it
- Chaining `mode` / `round` off the general review's checkpoint instead of `review-reliability-<branch>.md`
- Accepting a single root error boundary as coverage for a page whose regions should fail independently
- Assuming an error boundary catches a `throw` in an event handler or after an `await` - it does not; route it with `showBoundary`
- Treating `error.tsx` as catching its own segment's layout errors, or omitting `<html>` / `<body>` from `global-error.tsx`
- Leaving TanStack's default `retry: 3` on a query whose 4xx failures are terminal
- Retrying a mutation or Server Action with no server-side idempotency key
- Accepting an optimistic update with no `onError` rollback, or a snapshot restore that clobbers a concurrent edit
- Landing a mutation with no `invalidateQueries` / `revalidateTag`, or calling revalidate during render
- Trusting `navigator.onLine` as proof the API is reachable
- Rendering an empty list on error, so "failed" is indistinguishable from "you have none"
- Showing raw `error.message` or a stack trace in a fallback - show `error.digest` and a next action
- `suppressHydrationWarning` used to silence a real mismatch rather than fix its source
- Shipping `next/dynamic` / `React.lazy` routes with no `ChunkLoadError` recovery - every redeploy breaks open tabs
- Reviewing whether the API's contract is well designed - that belongs to the owning service or the architecture plugin
- Duplicating perf depth (bundle size, render churn, Core Web Vitals) or observability depth (Sentry wiring, log fields)
- Mitigating a live incident here - route to `/task-oncall-start` first
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
