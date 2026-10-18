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

Stack-specific delegate of `task-code-review-reliability` for React on the Next.js App Router. It preserves the parent's invocation and diff-resolution contract; the Findings shape below is this file's own.

Client reliability: what the UI does when a request hangs, a mutation fails after the screen already showed success, the user's network drops, hydration diverges, or a chunk 404s because the app was redeployed while the tab was open. **The browser is one user, one tab, one build that may already be stale.** Every finding names the failure mode and what the user sees, not just the missing pattern.

## When to Use

- Next.js 16 App Router PR adding or changing a fetch, TanStack Query hook, mutation, or Server Action
- A route reviewed for error-boundary coverage, loading / error / empty completeness, or offline behavior
- Hardening after a blank screen, a stuck spinner, a lost write, or a post-deploy `ChunkLoadError` spike
- Optimistic-update, cache-invalidation, or retry-policy correctness review

**Not for:** general review (`task-react-review`), Core Web Vitals and bundle cost (`task-react-review-perf`), instrumentation coverage (`task-react-review-observability`), XSS / auth / CSP (`task-react-review-security`), fixing the API's own unreliability (route to the owning service).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns the app doing too much work; this lens owns the app not surviving something else failing. A route stuck on a skeleton because a `fetch` has no timeout is reliability, even though it reads as slowness. Two surfaces genuinely overlap: a hydration mismatch (perf scores its cost, this lens scores the lost SSR result and dropped state) and `staleTime` (perf scores refetch volume, this lens scores showing a stale value). Raise each once, in the lens whose consequence you are actually describing.
- **vs. Observability:** both lenses look at the boundary tree, so split by question, not by file. Obs owns whether a failure is *reported* and diagnosable (`captureException`, `onRequestError`, error-rate alerting). This lens owns whether the user can *recover*: does a boundary exist, does `retry()` work, is there a way out. A boundary that captures but strands the user is this lens; one that recovers but reports nothing is obs. The umbrella dedups the overlap.
- **vs. Security:** a `fetch` retried against an auth-expired session is reliability; the session handling itself is security. The missing `AbortSignal.timeout` on a user-triggered outbound server-side fetch is scored by both - security as a denial-of-service primitive, this lens as a hang the user sees. Raise it once here and let the umbrella dedup.
- **vs. umbrella Phase B:** `task-react-review` Phase B owns happy-path correctness, hook rules, and cleanup; this lens owns partial failure, staleness, and offline. A write lost to a plain logic bug on the happy path (reading `formData.get` where `getAll` was meant) is Phase B's; a write lost because a failure was mishandled is this lens's. Cleanup sits at the seam: the umbrella's Phase B checks `AbortController` on async setters as a hooks-rule matter, while this lens scores the same code for the stale response it lets through. A `setInterval` never cleared is Phase B's alone. The umbrella dedups.
- **A client consumes contracts it does not own.** How the UI survives a response it did not expect is this lens; whether the contract is well designed belongs to the owning service or the architecture plugin.

## Depth

| Depth      | When                                              | Runs                                     |
| ---------- | ------------------------------------------------- | ---------------------------------------- |
| `standard` | Default                                           | Steps 1-11; the Failure-Mode Map section is omitted |
| `deep`     | Requested, handed down by `task-react-review`, or a whole-app sweep | The same, plus the `Failure-Mode and User-Impact Map` section |

`failure-propagation-analysis` is loaded at every depth in Step 4 - it is what gives each finding its user impact. At `deep` its output is additionally written up per dependency in the Failure-Mode and User-Impact Map.

**Whole-app sweep** (reliability-debt pass with no feature branch): when Step 3 fails fast on trunk in no-argument mode (the current branch is trunk), do not stop; an explicit trunk argument surfaces the fail-fast and stops. Announce it verbatim - `Head is trunk - running a repo-wide reliability sweep at HEAD; findings cite current code.` - then skip the diff gate and run Steps 4-11 repo-wide at `HEAD`, Step 4's categories read in full rather than per changed file. A sweep runs at `deep` unless `standard` was asked for: a debt pass with no Failure-Mode Map answers half the question. Scope it to the application package - a sibling package with its own manifest (a Rails island, a federated remote) is a separate sweep, and name the excluded packages in the Summary's `Notes`; other packages are read only for context. Incident references in the request (`after INC-21`) name the dependencies to trace first; the sweep still covers every category.

With no handle, a sweep skips the round gate and reconciliation (`reconciliation skipped - whole-app sweep` in `Notes`) and writes round 1, resolving the writer's fields itself: `branch` = `git symbolic-ref -q HEAD` with `refs/heads/` stripped (a detached HEAD already stopped in Step 3), `base_ref` = `head_ref` = that name, or `heads/<name>` when `refs/tags/<name>` also exists (`--abbrev-ref` prints that form, which would put `heads/<name>` into `branch` and the checkpoint filename), and `base_sha` = `head_sha` = `git rev-parse HEAD` - a full SHA, never the literal `HEAD`. `review-finding-verify` requires a diff a sweep does not have, so Step 10 does not invoke it: apply its claim check inline at `HEAD` - confirm each finding's cited `file:line` still says what the finding says (correcting a stale cite), drop a claim the file contradicts as a false positive, keep a claim the file cannot settle with `_(unverified: <reason>)_`, and keep every label. Skip diff-attribution (no `Pre-existing` verdicts, no `_(pre-existing)_` annotations) and write the tally as `<N> confirmed, 0 reattributed, <U> unverified, <K> dropped`, plus `(<F> false positive, 0 resolved by diff)` only when K > 0.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-react-review-reliability` | Current branch vs base; on trunk, runs the whole-app sweep (see Depth) |
| `/task-react-review-reliability <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-react-review-reliability pr-<N>` | PR head in local branch `pr-<N>` (user runs the fetch) |

Append `deep` for the deep pass; `--base <branch>` for a non-trunk base. `task-react-review` spawns this workflow as a subagent and passes the pre-confirmed stack and framework (`Next.js <version>` with its router suffix), the React version, the below-floor note or none, `base_ref` / `head_ref`, the pre-read diff, name-status list and commit log, and the depth level; Steps 2-3 consume those instead of re-running, and Step 11 returns findings instead of writing. `task-code-review-reliability` does **not** spawn a subagent - it forwards the invocation arguments and stops, so that path is a normal standalone run that owns its own report and must write one.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows; always runs, including in subagent mode.

### Step 2 - Confirm Stack and Detect Framework

When run as the umbrella's subagent (`task-react-review` passed the pre-confirmed stack and framework - `Next.js <version>` with its router suffix - the React version, and the below-floor note or none), accept those, write a passed note in the Summary's `Notes`, and skip detection, the scope stop and the floor check below; a standalone run always does all three.

Standalone: Use skill: `stack-detect`. `stack-detect` keys the primary stack on the root manifest, so in a polyglot repo (a React app under `apps/<name>` beside a Rails root) React may appear only under `Additional`; that counts as React when the diff or request sits inside that package - confirm React against the package's own `package.json`, scope the run to it, and name the package in the Summary's `Notes`. If not React, stop and name the detected stack so the user can invoke that stack's reliability workflow - do not route back to `/task-code-review-reliability`, which is what dispatched here. With no `next` dependency (Vite, React Router, Remix): print `task-react-review-reliability covers Next.js App Router projects only; <project framework> is out of scope - use core's /task-code-review-reliability for a generic review.` and stop. Record the `next`, React and TypeScript versions (resolution below) and the Framework as `Next.js <version>`, suffixed ` (Pages Router)` or ` (App + Pages Router)` when `pages/` routes exist. A declared `next` < 16.3 or `react` < 19.2: write `<package> <declared> is below the plugin floor (Next.js 16.3, React 19.2); output targets Next.js 16.3 and React 19.2 - upgrade first.` in the Summary's `Notes` (`<package>` is `Next.js` or `React`; both below is one line, `Next.js 15.5.4 and React 18.3.1 are below the plugin floor ...`) and continue. Every recorded version (`<declared>` and TypeScript included) is the one the nearest lockfile at or above the package resolves for it (its own, else the workspace root's), else the lower bound of the `package.json` range (the package's, else the root's for a hoisted dependency; `^16.1.0` -> `16.1.0`), written in full, not as the major; a package with no `tsconfig.json` of its own records `JavaScript` in place of `TypeScript <version>` (the writer's `stack` is then `javascript-nextjs`).

Either way (standalone after the scope stop), read Data Layer, Boundary Library and the TanStack major from the manifest, and the TypeScript version per the resolution above (`JavaScript` with no `tsconfig.json`) - the parent passes none of these.

Record for the Summary block:

- `Framework:` `Next.js <version>` with the router suffix
- `Data Layer:` Server Components + `fetch` | TanStack Query | SWR | mixed
- `Boundary Library:` `error.tsx` segments | `catchError` (`next/error`) | `react-error-boundary` | hand-rolled `componentDidCatch` | mixed: <those found> | none detected

Record the TanStack Query major: every default cited in Steps 6-9 is v5 (`throwOnError` was `useErrorBoundary` in v4, `gcTime` was `cacheTime`).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-reliability`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy` when the frontmatter is missing, unparseable, or belongs to another lens or branch). A trunk fail-fast in no-argument mode runs the whole-app sweep (see Depth) instead; any other fail-fast is surfaced verbatim, writes no report, and stops. No state-changing git.

**Round gate (standalone only).** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` and `base_sha` equal the captured ones and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits on <head_short_name> since prior reliability review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (the report write overwrites the file) -> `round: 1`, no `prior_head_sha` (`legacy` adds `legacy prior report treated as round 1` to `Notes`). Then read `git diff <base>...<head>`, `git diff --name-status <base>...<head>` and `git log <base>..<head>` once and reuse.

**Subagent mode** = a parent passed `base_ref` / `head_ref` plus the pre-read diff, name-status list and log (also when the parent runs this lens inline): skip the precondition, the round gate and the diff reads; the surface read still runs.

### Step 4 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into - a small diff ripples: a new hook calling an unchanged untimed fetch wrapper is a new hang at the call site. Follow one hop by default, and a second only when the first hop's file is itself part of a finding's failure path. Code added by the diff but not yet imported anywhere is still in scope - it ships. Outside a whole-app sweep, a defect in an unchanged file the diff calls into is a Finding (verify attributes it `Pre-existing`, or `Pre-existing (newly reachable)` when the diff changes how it is reached, and sets its label); one in a file the diff never reaches is a Recommendations line.

- Boundary files: `app/**/error.tsx`, `app/global-error.tsx`, `app/**/loading.tsx`, `catchError` wrappers (`next/error`), `<ErrorBoundary>` mounts
- Fetch layer: `fetch` wrappers, `axios` / `ky` instances, Server Component `fetch` calls, Route Handlers the app's own clients call (browser or mobile). An inbound webhook handler is server-to-server and out of this lens. A defect outside this lens that can lose, double-apply or hide a write (stale data served after it), break the build or expose data (a webhook's missing expiry, `ssr: false` in a Server Component, an infra-layer cache rule) goes on an `out of lens:` line at the end of `## Findings` plus a `[Delegate]` Next Step (labelled `[Recommend]`, `[Must]` when it can lose or double-apply a write), one of each per owning workflow
- TanStack Query / SWR: `QueryClient` defaults, `useQuery` / `useMutation` call sites, query-key factories
- Mutation and write paths: Server Actions (`"use server"`), `useActionState` / `useOptimistic` consumers, `revalidatePath` / `revalidateTag` / `updateTag` / `refresh` calls
- Route and boundary structure: `<Suspense>` placement, `next/dynamic` and `React.lazy` sites, third-party `<Script>` tags
- `next.config.*` and deploy config where chunk retention / `deploymentId` is set; when that config is in the surface, Use skill: `react-selfhost-operations` for version-skew and `deploymentId` semantics

Use skill: `react-data-fetching` - it owns the canonical query, mutation, invalidation, and optimistic-rollback patterns. Use skill: `ops-resiliency` for the retry, backoff and fallback vocabulary only - it is written for servers, so its connection pools, bulkheads, circuit-breaker libraries and per-dependency client modules do not translate to one browser tab and must not be recommended here. Use skill: `failure-propagation-analysis` for its tracing method only - follow one dependency's failure forward to what the user sees. Its incident-shaped sections (`Shared Resources on Path`, `Containment Assessment`) and its always-produce-all-sections rule do not apply: a browser client answers "none on path" for nearly all of them.

Consulted skills inform findings; this workflow's Output Format is the only envelope emitted (`failure-propagation-analysis` supplies the tracing method, not its own incident-shaped sections). Open every file read in full - changed files and the unchanged files the diff calls into - at the head with `git show <head_ref>:<path>`, unless standalone with `head_matches_current: true` and `head_is_remote: false` (then the working tree is the head); a whole-app sweep reads the working tree at `HEAD`. Subagent mode takes changed hunks from the parent's pre-read diff and whole files from `git show`.

### Step 5 - Error Boundaries and Render-Time Failure

Use skill: `react-component-patterns` for boundary placement and `react-nextjs-patterns` for the special-file semantics and `retry()` vs `reset()`. This step owns whether recovery actually works, navigation through component boundaries, async-error routing, and the fallback's shape.

- [ ] **A boundary above every route that renders remote data.** With none, one throw unmounts the whole tree and the user gets a blank white page with no way back.
- [ ] **Granularity matches the blast radius wanted.** A single root boundary turns a failed sidebar widget into a dead app; wrap optional regions so a partial failure degrades that region only.
- [ ] **Next.js segment semantics respected:** `error.tsx` is a Client Component receiving `{ error, retry, reset }`, and it does **not** catch errors thrown by the layout of its own segment - that needs a boundary in the parent segment. `global-error.tsx` catches root-layout errors, is itself a Client Component, and must render its own `<html>` and `<body>` (it renders in development too, beside the error overlay).
- [ ] **The recovery control actually recovers.** `retry()` (on `error.tsx`, `global-error.tsx` and `catchError` fallbacks) refreshes the route's server data (`router.refresh()`) and clears the boundary in one transition; `reset()` only clears the error state and re-renders without re-fetching, so it cannot recover a Server Component failure: a fallback wired to `reset()` alone over Server Component output (an `error.tsx` over a Server Component page or layout, `global-error.tsx`, a `catchError` around server-rendered children) is a dead button; over client-only children it can recover, but `retry()` is still the control to use. A `react-error-boundary` reset needs `resetKeys` on the value that changed or a re-run of the failed query - for a TanStack query that threw to the boundary (`throwOnError`), `QueryErrorResetBoundary` / `useQueryErrorResetBoundary().reset` wired to `onReset`, or `resetQueries` on its key; otherwise the remounted query has `retryOnMount` forced off and re-throws the cached error.
- [ ] **Component-level boundaries let navigation through.** `redirect()` and `notFound()` work by throwing; any component boundary other than `catchError` (hand-rolled or `react-error-boundary`) between the call and the segment catches them and renders a fallback instead of navigating. Use `catchError` from `next/error`, which passes them through and clears on client navigation; any other boundary that stays must rethrow them.
- [ ] **Event-handler and async errors are routed to a boundary explicitly.** Boundaries catch render, lifecycle and constructor errors, plus errors thrown inside a `useTransition` transition (caught by the boundary above the calling component), form actions and `useActionState` actions, `await` included. A `throw` in a plain event handler, an async callback outside a transition, or the standalone `startTransition` imported from `react` (it reports to the global handler) never reaches them. Route it with `showBoundary` when the Boundary Library is or includes `react-error-boundary` (its hook throws without that ancestor), otherwise with `useTransition`'s `startTransition` or local error state.
- [ ] **The fallback is usable:** what failed, a retry affordance, and a way out (back / home). No raw `error.message`, stack trace, or blank `<div>`. `error.digest` is the correlation id to show - but it is set only for errors that originated on the server, so render it conditionally rather than printing a bare `Reference ` with nothing after it.

```tsx
// app/orders/error.tsx
"use client";

import Link from "next/link";
import { useQueryClient } from "@tanstack/react-query";

type ErrorProps = { error: Error & { digest?: string }; retry: () => void };

// Bad - reset() clears the error state without re-fetching, so a failed
// Server Component renders the same failure; the button does nothing.
export function BadError({ reset }: { reset: () => void }) {
  return <button onClick={() => reset()}>Retry</button>;
}

// Good - retry() refreshes the route's server data and clears the boundary. Clearing the query
// cache first only matters when the failure came from a client query.
export default function OrdersError({ error, retry }: ErrorProps) {
  const qc = useQueryClient();
  return (
    <>
      <p>Could not load orders.{error.digest ? ` Reference ${error.digest}` : ""}</p>
      <button
        onClick={() => {
          qc.resetQueries({ queryKey: ["orders"] });
          retry();
        }}
      >
        Retry
      </button>
      <Link href="/">Go home</Link>
    </>
  );
}
```

`useQueryClient()` needs a `QueryClientProvider` above it - true for a segment `error.tsx` under the root layout, false for `global-error.tsx`, which replaces that layout.

### Step 6 - Fetch Failure, Retry, and Cancellation

Use skill: `react-hooks-patterns` for the effect-cleanup contract behind hand-rolled fetch cancellation.

- [ ] **A timeout on every request.** Browser `fetch` waits indefinitely; Node's `fetch` (undici) defaults to a ~300s headers/body timeout, which is far past any useful budget. Use `AbortSignal.timeout(ms)`, composed with the caller's signal via `AbortSignal.any([signal, AbortSignal.timeout(ms)])`. So an untimed `fetch` inside an RSC holds the stream open for five minutes, or until the platform's own request ceiling kills it - either way far past any budget the page can absorb.
- [ ] **A timeout abort is distinguishable from a cancellation.** `AbortSignal.timeout` rejects with a `TimeoutError` DOMException, not `AbortError`, so code that keys on `signal.aborted` or swallows every abort silently discards real deadline failures. Branch on `err.name`.
- [ ] **Retryable is decided by status, not by retrying everything.** TanStack Query defaults to `retry: isServer ? 0 : 3`, so in the browser a 404 or 403 is retried three times, turning a fast failure into a slow one (server prefetches do not retry). This only bites once the `queryFn` actually throws on a non-`ok` response - `fetch` does not reject on 4xx, so a `queryFn` without an `res.ok` check caches a JSON error body as data, or fails on an HTML error page with a misleading `SyntaxError` after three retries. Gate it: retry 408 / 429 / 5xx, network errors and timeouts, never other 4xx.
- [ ] **Backoff is capped.** TanStack's default `retryDelay` is exponential capped at 30s; a hand-rolled loop needs the same cap plus jitter, or a recovering API gets a synchronized retry wave from every open tab.
- [ ] **`Retry-After` honored when present** - it is seconds or an HTTP-date, never milliseconds; never wait less than the server asks.
- [ ] **In-flight requests are cancelled on unmount and on route change.** Pass the `signal` TanStack Query hands the `queryFn` straight into `fetch` so a key change or unmount aborts the request; a hand-rolled `useEffect` fetch needs its own `AbortController` aborted in the cleanup. Under TanStack an unthreaded `signal` only wastes the abandoned request (the per-key cache already stops cross-key overwrites) - Medium at most; a hand-rolled fetch with no aborted controller lets a slow earlier response overwrite a newer one - High.
- [ ] **An aborted request is not an error.** `AbortError` is dropped, never rendered as a failure banner on a route the user already left.
- [ ] **SWR equivalents, when SWR is the data layer:** `dedupingInterval` for `staleTime` (a window in which mount / focus / reconnect revalidations are suppressed; `revalidateIfStale: false` / `revalidateOnFocus: false` for never-refetch), `shouldRetryOnError` (a boolean or `(err) => boolean`) for the retry predicate, `errorRetryCount` for its cap (unset by default, so stock SWR retries an erroring key without limit; honored only by the default `onErrorRetry` - a custom one enforces its own cap), the last `data` SWR keeps beside `error` for the cached-fallback rule (`keepPreviousData` covers key changes only), and an explicit `mutate(key)` for invalidation. `react-data-fetching` covers `dedupingInterval`, `revalidateOnFocus`, conditional null keys and explicit `mutate`; the retry predicate and the stale-data-beside-error behaviour are SWR's own. The failure modes and severities in this lens are identical either way.
- [ ] **`throwOnError` is a deliberate choice per query.** It routes the failure to the nearest boundary (whole region replaced); leaving it off keeps the failure inline in `error`. Leaving it off without rendering `error` / `isError` means the component silently renders with `data === undefined`.

```tsx
class HttpError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`);
  }
}

// Bad - never throws on 4xx, so a JSON error body is cached as data and the
// default retry never even fires; no cancellation, no deadline.
useQuery({
  queryKey: ["orders"],
  queryFn: () => fetch("/api/orders").then((r) => r.json()),
});

// Good - throws on non-ok so failures are failures, retries only what is
// transient (including network errors and timeouts, which carry no status),
// and binds the request to both the query's lifetime and a deadline.
useQuery({
  queryKey: ["orders"],
  retry: (n, e) => {
    if (n >= 3) return false;
    if (e instanceof HttpError) return e.status >= 500 || e.status === 408 || e.status === 429;
    return true; // TypeError (network) and TimeoutError have no status
  },
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

- [ ] **Every optimistic update has a rollback path.** The `onMutate` / `onError` / `onSettled` flow is not optional: `cancelQueries` (so an in-flight refetch cannot overwrite the rollback), snapshot via `getQueryData`, apply, restore the snapshot in `onError`, `invalidateQueries` in `onSettled`. An optimistic UI with no rollback is a lie the user acts on. `useOptimistic` reverts when the action settles - **including on success**, back to whatever the underlying state is at that moment. Without an update to the underlying state inside the same transition (a `setState` after the `await`, or `updateTag` for read-your-writes or `revalidatePath` in the Server Action - `refresh()` from `next/cache` lands the real value only for uncached data), a successful mutation visibly snaps back.
- [ ] **Mutations are not retried blind.** TanStack defaults mutations to `retry: 0`; turning retry on for a non-idempotent write double-applies it, because the client cannot distinguish a lost response from a lost request. Retry a write only with an idempotency key the server dedups on.
- [ ] **Server Actions are idempotent or guarded.** React does not retry a Server Action; Next does only under `experimental.useOffline`, which re-sends one that failed with a network error - in flight included - once connectivity returns, so a write whose response, not its request, was lost applies twice. The other risks are the user double-submitting and a client-side retry wrapper. Disable the submit via `useFormStatus().pending`, and dedup server-side on a key.
- [ ] **Server Action failure reaches the UI.** Return a typed error state and surface it through `useActionState`; a thrown error in a Server Action becomes an opaque digest in production, so the user sees the generic boundary instead of "email already taken". Validation failures are returned state, not throws.
- [ ] **A rollback does not clobber a concurrent edit.** Restoring a whole list snapshot discards an item edited while the request was in flight; reconcile at the item level where concurrent edits are possible.
- [ ] **State that survives a navigation is intended.** With `cacheComponents` set in `next.config`, Next keeps up to 3 route entries per layout segment, the visible one included, so the 2 most recently left routes stay hidden in `<Activity>` instead of unmounting: Effect cleanup runs on hide, but React state - a form draft, an error banner, a failed optimistic value - survives and reappears on return. Reset what must not survive in an Effect cleanup or on re-show - there is no unmount to clear it.

### Step 8 - Cache Staleness and Invalidation

- [ ] **Every mutation invalidates what it changed.** An untouched cache after a write is the most common stale-UI bug: the user saves, navigates back, and sees the old value.
- [ ] **Tag invalidation over full-route `revalidatePath`**, run on the server after the write - inside the Server Action or Route Handler, never during render. A Server Action that must show the user their own write uses `updateTag(tag)`, since `revalidateTag(tag, 'max')` serves stale once; `updateTag` is Server-Action-only, so a Route Handler the app's own clients call that needs immediate expiry uses `revalidateTag(tag, { expire: 0 })` (a webhook's missing expiry is an `out of lens:` line per Step 4). Missing it leaves the RSC payload cached and the fresh client cache disagreeing with the server-rendered shell.
- [ ] **Invalidation covers every affected key**, including list + detail + count queries and any parallel route sharing the entity. A key factory makes this auditable; ad-hoc string keys make it guesswork.
- [ ] **`staleTime` is a stated decision per query.** The default `0` refetches on every mount; a long `staleTime` on data another user can change shows one tab a value the other tab already changed.
- [ ] **Cross-tab consistency is defined where it matters.** Auth state, feature flags, and entitlement changes propagate via `BroadcastChannel` or the `storage` event; without it a logged-out tab keeps issuing requests with a dead session and shows repeated failures instead of a login prompt.

### Step 9 - Offline and Degraded Network

- [ ] **`navigator.onLine` reports a network interface, not reachability.** A captive portal, a VPN, or a dead API all report `true`. Treat it as a hint for the affordance to show; treat the request result as the truth.
- [ ] **Offline is a defined state with its own affordance**, distinct from "the server broke" - not a generic error toast and not an empty list.
- [ ] **Refetch on reconnect is wired and bounded.** TanStack's `onlineManager` drives `refetchOnReconnect` (default on). Note what v5's default `networkMode: 'online'` actually does offline: queries are **paused** (`fetchStatus: 'paused'`, no error), so a component must render that state rather than a spinner - and every paused query resumes at once on reconnect, which is the burst to bound.
- [ ] **Next's offline mode is wired when the app opts in.** `experimental.useOffline: true` detects connectivity (a failed framework request counts even while `navigator.onLine` is `true`) and retries blocked navigation, prefetch and Server Action requests on reconnect; `useOffline()` from `next/offline` reads that state for the offline affordance and always returns `false` with the flag unset.
- [ ] **Cached data is served as a fallback rather than blanking the page.** A full-screen skeleton over data already in `gcTime` is a defect; render the cached value with a staleness indicator.
- [ ] **Offline writes have a defined answer** - rejected with a clear message, or queued with the queue's durability and ordering stated. A queue in a module-level array dies with the tab.
- [ ] **Rendering an empty list on failure is never acceptable** - "failed to load" and "you have none" must not look identical.

### Step 10 - Hydration, Streaming, and Chunk-Load Failure

- [ ] **No hydration-mismatch sources in render:** `Date.now()`, `Math.random()`, `new Date().toLocaleString()`, or `window` / `localStorage` reads. (React tolerates unexpected tags injected into `<head>` / `<body>` by extensions and third-party scripts, so those are not a mismatch source.) React recovers by discarding the server HTML and client-rendering from the nearest Suspense boundary above the mismatch - the whole root only when none exists. In the App Router a segment's `loading.tsx` is such a boundary, so the usual blast radius is that segment. It is still not cosmetic: the SSR result for that subtree is thrown away and state can flash or drop. `suppressHydrationWarning` silences one element; it is not a fix for the underlying divergence.
- [ ] **Suspense boundaries are placed so a slow or failing segment cannot hold the shell.** In the App Router `loading.tsx` is the segment's implicit Suspense boundary; `error.tsx` catches what that segment throws. Both belong to the same segment - `loading.tsx` alone means this segment's failure escapes to whatever boundary sits above it (High when none does, Medium when one does), `error.tsx` alone means a slow fetch blocks the shell.
- [ ] **Streaming failure is handled after the shell flushed.** Once streaming begins the status code is already sent, so an error later in the stream cannot become a 500 - it must resolve to an inline boundary fallback, or the user gets a half-rendered page. Errors thrown before the first flush can still redirect or 500.
- [ ] **Dynamic `import()` failure has a recovery path.** After a redeploy, a tab open on the old build requests chunks that no longer exist and every lazy route fails on click. Detect it by `err.name === "ChunkLoadError"` in a boundary that forces `location.reload()`, and keep prior build assets available so an open tab can still fetch them. `deploymentId` is the other half and is only useful when it changes per deployment: it stamps asset requests with `?dpl=` and sends `x-deployment-id`, so a stale client is detected and forced through a hard navigation. Next does not validate uniqueness, so reusing a value silently disables the mechanism. A host that retains immutable prior assets narrows this a lot; a host that does not breaks every open tab on each deploy.
- [ ] **Third-party scripts fail safe.** A blocked or timed-out analytics / chat / tag-manager script must not break the page: use `next/script` with `strategy="lazyOnload"` and an `onError` (`onLoad` / `onError` are unsupported with `beforeInteractive`, where the docs point to `onReady`, and all three work only inside a Client Component). No render path may assume `window.<vendor>` exists.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, each with its row's corrected `file:line`, `Label` and `Annotation` (the table itself is not published), and fill the Summary's `Findings verified` line from its tally. Outside a whole-app sweep, a finding whose first `Location` file the round's name-status does not list carries `_(pre-existing)_` as its first annotation group after the `file:line` when its `Annotation` has no group opening `pre-existing` (verify leaves an `Unverified` row unattributed, so this is where it gets its marker) - that is what the next round's reconcile keys an untouched file on. A finding only carried from a prior round, not re-derived this round, is not re-verified. Subagent runs skip this - the parent verifies the merged set once.

### Step 11 - Write Report

**Subagent mode** (see Step 3): return its Output Format document - Summary, Findings, Recommendations, Next Steps, and at `deep` the Failure-Mode and User-Impact Map - and write nothing; the parent owns the report, merges the Findings and Next Steps, and carries Recommendations and (at `deep`) the Failure-Mode and User-Impact Map into its `## Scope Sections`; the Summary is not reproduced. Each finding already carries its `Label`; the parent does not re-derive labels. Skip the rest of this step.

**Reconcile (standalone, round 2+).** Re-project the prior report (the file at the handle's `report_path`) into reconcile's parse shape: one `## High-Impact Findings` section and, per prior finding in every tier, a `### [<Label>] <file:line>` heading - the label bracketed exactly once (`Must` and `[Must]` both project as `[Must]`), the bare `file:line` prefix of its `Location` slot (the first when it lists several), then each annotation as its own `_(...)_` group: `_(pre-existing)_` kept, verify's combined `_(pre-existing; newly reachable via <path>)_` written as two groups `_(pre-existing)_ _(newly reachable via <path>)_` (reconcile matches `_(pre-existing)_` exactly), and a prior `_(carried from round <N>)_` re-emitted - followed by `- Issue: <its Issue text>`. Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status list and `head_sha`, and render its table, any note lines and its tally under `## Prior Round Reconciliation`. `Still open` and `Needs re-check` rows carry into the tier the prior report filed them under, at their prior label, with the prior annotation kept and `_(carried from round <N>)_` on the `Location` line (`<N>` = the round the finding first appeared: the prior's own carried marker when present, else the prior report's `round`); a carried finding this round's own pass re-derives publishes once, in this round's tier at the higher of the two labels, keeping the fresh verify annotation plus `_(carried from round <N>)_`. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

Then Use skill: `review-report-writer` with `report_type: review-reliability` and every field it requires: `report_body`, `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` and `round` / `prior_head_sha` from the Step 3 round gate, `scope: +rel`, `depth` as resolved from the Depth table, `stack: typescript-nextjs` (`javascript-nextjs` when Step 2 recorded `JavaScript`), `mode: full`, and `pr_url` when the request carried a PR/MR URL, else `prior_checkpoint.pr_url` when present. Print the confirmation line after the report body. Whole-app sweep: the refs and full SHAs resolved under Depth, `round: 1`.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment** (a defect fitting two tiers takes the higher; an atomic's `Critical` or `Blocker` is High): High = the user hits an unrecoverable or wrong state on a plausible failure (a route with no error boundary, `ChunkLoadError` with no recovery, an optimistic update with no rollback, a retried non-idempotent mutation or Server Action, an untimed `fetch` in an RSC render, a hand-rolled fetch whose stale response overwrites a newer one, a hydration mismatch, a fallback whose recovery control cannot recover (`reset()` alone over Server Component output; a `react-error-boundary` reset with no `resetKeys` or refetch; over a `throwOnError` TanStack query, a reset that neither calls `QueryErrorResetBoundary`'s `reset` (via `onReset`) nor runs `resetQueries` on its key), a failure rendered as empty content - `data ?? []` making "failed" indistinguishable from "none"); Medium = the failure is bounded but recovery or comprehension is impaired (missing invalidation after a mutation, retry on non-retryable 4xx, an unthreaded TanStack `signal`, no offline affordance, error fallback with no next action, a `reset()`-only fallback over client-only children, `loading.tsx` with no sibling `error.tsx` while a boundary exists higher in the tree - with none anywhere it is High's no-boundary case); Low = hardening with no immediate failure path (no jitter, `staleTime` undocumented, no cross-tab propagation on low-stakes state). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`. Each finding's `Label` slot carries the result as the bracketed label itself, written exactly (the verify pass's `Label` column overrides when it ran).

**One finding per root cause:** a defect matching several checklist lines (an uncancelled query that also retries a 403) is reported once at the strongest severity with the other aspects folded in.

```markdown
## React Reliability Review Summary

- **Stack Detected:** React <version> / TypeScript <version> | React <version> / JavaScript _(from Step 2; `not detected` for either when the project does not reveal it)_
- **Framework:** Next.js <version>{ <Step 2 router suffix>}
- **Data Layer:** Server Components + `fetch` | TanStack Query | SWR | mixed
- **Boundary Library:** `error.tsx` segments | `catchError` (`next/error`) | `react-error-boundary` | hand-rolled `componentDidCatch` | mixed: <those found> | none detected
- **Boundary Coverage:** every remote-data route | PARTIAL: <routes uncovered> | NONE _(from Step 5; a boundary that exists but cannot recover counts as uncovered - name it in the PARTIAL list)_
- **Timeouts:** all requests bounded | PARTIAL: <where missing> | NONE _(from Step 6)_
- **Cancellation:** signal threaded at file:line | absent _(from Step 6)_
- **Offline:** defined per path | partial | undefined | not in scope _(from Step 9; `not in scope` when nothing reviewed touches connectivity)_
- **Round:** <N> _(from the Step 3 round gate; include from round 2 onward)_
- **Depth:** standard | deep
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped (<F> false positive, <R> resolved by diff) _(the parenthetical only when K > 0)_. _In subagent mode write exactly `not run (subagent; parent verifies the merged set)`._
- **Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]
- **Notes:** <the Step 2 passed-stack note or below-floor line, the package the run was scoped to, `legacy prior report treated as round 1`, packages or files excluded from a sweep, `reconciliation skipped - whole-app sweep`; omit when none>

## Findings

### High Impact

1. **Location:** [file:line, comma-separated when one root cause spans several; carry the verify pass's `Annotation` when it is not `-`: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `_(unverified: <reason>)_`, `_(mechanism: <actual>)_`; a carried finding appends `_(carried from round <N>)_`; outside a whole-app sweep and outside subagent mode, a finding whose first file the name-status does not list, with no group opening `pre-existing`, carries `_(pre-existing)_` as its first annotation group after the `file:line` (added at publish); a finding spanning changed and unchanged files leads with a file the name-status lists unless verify attributed it `Pre-existing` or `Pre-existing (newly reachable)` (verify cites those at the unchanged defect)]
   - **Label:** [Must] | [Recommend]
   - **Issue:** [name the React idiom: no `error.tsx` above the route, `retry: 3` on a 4xx, `signal` not threaded into `queryFn`, optimistic update with no `onError` rollback, `import()` with no `ChunkLoadError` recovery, hydration mismatch from `Date.now()`]
   - **Failure Mode:** [what fails and how: "the orders `fetch` has no timeout, so a stalled API leaves the RSC stream open and the route never resolves"]
   - **User Impact:** [what the person in the browser sees: "an indefinite skeleton on /orders; reloading reproduces it"]
   - **Fix:** [concrete React / Next.js change]

### Medium Impact

[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins

[Same numbered-block structure]

_Omit empty sections; with no finding in any tier, `## Findings` contains `No reliability gaps found.` Whether or not any tier has findings, it ends with one `out of lens: <file:line> - <defect> (route to <workflow>)` line per owning workflow for the qualifying defects outside this lens (Step 4, further defects for the same workflow appended as `; <file:line> - <defect>` before the parenthetical; `<workflow>` names the owning team when no workflow covers the defect), unnumbered and outside the tier counts._

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

<reconcile note lines> {only when reconcile emitted any}

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Recommendations

[Structural reliability improvements not tied to a single finding - a shared fetch wrapper with a default timeout, a query-key factory to make invalidation auditable, a root `ChunkLoadError` reload boundary; plus one `<file:line> - <defect>` line per defect in a file the diff never reaches (Step 4).]

## Failure-Mode and User-Impact Map

_(`deep` only - omit at `standard`.)_

A table with the header `| Dependency (file:line) | Slow | Absent / error | Unexpected response | Contained by |`, one row per new or changed data dependency (every traced dependency in a sweep); each failure cell names what the user sees, and `Contained by` names the control (a timeout, a bounded retry, a cached fallback, an offline state, an error boundary).

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: API contract] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (API contract, deploy config, platform, another workflow's out-of-lens defect). Order Must > Recommend. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no mutations, no dynamic imports).

- [ ] Step 1 - `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2 - as the umbrella's subagent, the parent's stack, framework, React version and below-floor note accepted; standalone: a `next` dependency confirmed (none: the out-of-scope line printed and the run stopped), a below-floor `next` / `react` noted in `Notes`; router-suffixed `Framework` and React version recorded; either way `Data Layer`, `Boundary Library`, the TanStack major and the TypeScript (or `JavaScript`) version read
- [ ] Step 3 - `review-precondition-check` ran with `report_type: review-reliability` (or subagent mode); round decided from the handle before the diff was read, or the no-op line printed; diff, name-status and log read once. Whole-app sweep: the sweep announcement printed verbatim (not the fail-fast text), refs and full SHAs resolved from `HEAD`, round 1
- [ ] Step 4 - boundary files, fetch layer, query/mutation sites, Server Actions, Suspense and lazy sites, deploy config read (`react-selfhost-operations` loaded when it is in the surface), one hop out from the diff; `react-data-fetching`, `ops-resiliency` (vocabulary only) and `failure-propagation-analysis` (method only) consulted for patterns and user impact
- [ ] Step 5 - `react-component-patterns` (placement) and `react-nextjs-patterns` (special-file semantics, `retry()`) consulted; boundary presence and granularity, working `retry()` (a `reset()`-only fallback rated by what it wraps) / `resetKeys`, `redirect()` / `notFound()` passing every non-`catchError` boundary, async-error routing, usable fallback audited
- [ ] Step 6 - `react-hooks-patterns` consulted; timeout on every request, a timeout abort distinguished from a cancellation, transient-only retry with capped backoff, `Retry-After`, `signal` threaded for unmount / route-change cancellation, `AbortError` not surfaced, `throwOnError` chosen deliberately, SWR equivalents applied when SWR is the data layer
- [ ] Step 7 - optimistic rollback complete (cancel / snapshot / set / rollback / settle), no blind mutation retry, Server Actions idempotent and their failures surfaced via `useActionState`, rollback safe against concurrent edits, state kept by hidden routes (Cache Components) intended
- [ ] Step 8 - mutations invalidate every affected key, `updateTag` / two-argument `revalidateTag` / `revalidatePath` called server-side after the write, `staleTime` stated, cross-tab consistency defined where it matters
- [ ] Step 9 - `navigator.onLine` treated as a hint, offline a distinct state, bounded refetch-on-reconnect, cache used as fallback, offline writes defined, `useOffline` wired when opted in, no empty-list-on-failure
- [ ] Step 10 - hydration-mismatch sources checked, `loading.tsx` / `error.tsx` paired per segment, post-flush streaming failure handled, `ChunkLoadError` recovery present, third-party scripts fail safe
- [ ] Step 10 (verify) - `review-finding-verify` ran on the assembled findings (a sweep: not invoked, its claim check applied inline at `HEAD`); `Dropped` rows excluded; its `Label` and `Annotation` columns applied, an untouched-file finding marked `_(pre-existing)_` at publish (not in a sweep); tally in Summary. Subagent runs skip it and write the stated subagent string
- [ ] Step 11 - standalone: prior round reconciled through the projection when round > 1, report written via `review-report-writer` (`branch` = `head_short_name`, `scope: +rel`, `stack: typescript-nextjs`, or `javascript-nextjs` after a `JavaScript` record), confirmation printed; subagent: Output Format document returned to parent, no file written
- [ ] Every finding names the failure mode and what the user experiences, never just the missing pattern
- [ ] Client framing held - no connection pools, server middleware, graceful shutdown, or distributed-transaction recommendations
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and User-Impact Map
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend (omit if none)

## Avoid

- State-changing git (`fetch`, `checkout`, `reset`) - the user runs these to protect uncommitted work
- Reporting a missing pattern without the failure mode and user impact ("add a timeout" vs "an untimed `fetch` leaves an indefinite skeleton on /orders")
- Server framing on a client: connection pools, middleware, `SIGTERM` draining, service mesh, distributed transactions. The browser is one user, one tab, one build
- Writing a report when spawned as a subagent by `task-react-review` - the parent owns it. Arriving via `task-code-review-reliability`'s dispatch is not that case: there you write the report
- Chaining `mode` / `round` off the general review's checkpoint instead of `review-reliability-<branch>.md`
- Accepting a single root error boundary as coverage for a page whose regions should fail independently
- Reviewing whether the API's contract is well designed - that belongs to the owning service or the architecture plugin
- Duplicating perf depth (bundle size, render churn, Core Web Vitals) or observability depth (Sentry wiring, log fields)
- Recommending a server resiliency control (`ops-resiliency`'s circuit breakers, bulkheads, connection pools) in a browser tab
