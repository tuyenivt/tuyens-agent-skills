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

Stack-specific delegate of `task-code-review-reliability` for React / Next.js / Vite. It preserves the parent's invocation and diff-resolution contract; the Findings shape below is this file's own.

Client reliability: what the UI does when a request hangs, a mutation fails after the screen already showed success, the user's network drops, hydration diverges, or a chunk 404s because the app was redeployed while the tab was open. **The browser is one user, one tab, one build that may already be stale.** Every finding names the failure mode and what the user sees, not just the missing pattern.

## When to Use

- Next.js or Vite + React PR adding or changing a fetch, TanStack Query hook, mutation, or Server Action
- A route reviewed for error-boundary coverage, loading / error / empty completeness, or offline behavior
- Hardening after a blank screen, a stuck spinner, a lost write, or a post-deploy `ChunkLoadError` spike
- Optimistic-update, cache-invalidation, or retry-policy correctness review

**Not for:** general review (`task-react-review`), Core Web Vitals and bundle cost (`task-react-review-perf`), instrumentation coverage (`task-react-review-observability`), XSS / auth / CSP (`task-react-review-security`), fixing the API's own unreliability (route to the owning service).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns the app doing too much work; this lens owns the app not surviving something else failing. A route stuck on a skeleton because a `fetch` has no timeout is reliability, even though it reads as slowness. Two surfaces genuinely overlap: a hydration mismatch (perf scores its cost, this lens scores the lost SSR result and dropped state) and `staleTime` (perf scores refetch volume, this lens scores showing a stale value). Raise each once, in the lens whose consequence you are actually describing.
- **vs. Observability:** both lenses look at the boundary tree, so split by question, not by file. Obs owns whether a failure is *reported* and diagnosable (`captureException`, `onRequestError`, error-rate alerting). This lens owns whether the user can *recover*: does a boundary exist, does `reset` work, is there a way out. A boundary that captures but strands the user is this lens; one that recovers but reports nothing is obs. The umbrella dedups the overlap.
- **vs. Security:** a `fetch` retried against an auth-expired session is reliability; the session handling itself is security. The missing `AbortSignal.timeout` on a user-triggered outbound server-side fetch is scored by both - security as a denial-of-service primitive, this lens as a hang the user sees. Raise it once here and let the umbrella dedup.
- **vs. umbrella Phase B:** `task-react-review` Phase B owns happy-path correctness, hook rules, and cleanup; this lens owns partial failure, staleness, and offline. A write lost to a plain logic bug on the happy path (reading `formData.get` where `getAll` was meant) is Phase B's; a write lost because a failure was mishandled is this lens's. Cleanup sits at the seam: the umbrella's Phase B checks `AbortController` on async setters as a hooks-rule matter, while this lens scores the same code for the stale response it lets through. A `setInterval` never cleared is Phase B's alone. The umbrella dedups.
- **A client consumes contracts it does not own.** How the UI survives a response it did not expect is this lens; whether the contract is well designed belongs to the owning service or the architecture plugin.

## Depth

| Depth      | When                                              | Runs                                     |
| ---------- | ------------------------------------------------- | ---------------------------------------- |
| `standard` | Default                                           | Steps 1-11; the Failure-Mode Map section is omitted |
| `deep`     | Requested, handed down by `task-react-review`, or a whole-app sweep | The same, plus the `Failure-Mode and User-Impact Map` section |

`failure-propagation-analysis` is loaded at every depth in Step 4 - it is what gives each finding its user impact. At `deep` its output is additionally written up per dependency in the Failure-Mode and User-Impact Map.

**Whole-app sweep** (reliability-debt pass with no feature branch): when Step 3 fails fast on trunk, do not stop. Announce it verbatim - `Head is trunk - running a repo-wide reliability sweep at HEAD; findings cite current code.` - then skip the diff gate and run Steps 4-11 repo-wide at `HEAD`, Step 4's categories read in full rather than per changed file. A sweep runs at `deep` unless `standard` was asked for: a debt pass with no Failure-Mode Map answers half the question. Scope it to the application package - a sibling package with its own manifest (a Rails island, a federated remote) is a separate sweep, and say which you excluded.

With no handle, resolve the writer's fields yourself: `branch` = `base_ref` = `head_ref` = `git rev-parse --abbrev-ref HEAD`, and `base_sha` = `head_sha` = `git rev-parse HEAD` - a full SHA, never the literal `HEAD` (only `branch` drives the report filename; `base_ref` and `head_ref` are recorded as the branch name). The Step 10 verify pass has no diff, so run it in claims-only form: confirm each finding's cited `file:line` still says what the finding says and drop the ones that do not. Everything is pre-existing by construction, so skip diff-attribution and its de-escalation, annotate every finding `_(pre-existing)_` on its `Location` line - the next round's reconcile keys its `untouched` classification on that annotation - and write the tally as `<N> confirmed, 0 reattributed, <K> dropped`.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-react-review-reliability` | Current branch vs base; on trunk, runs the whole-app sweep (see Depth) |
| `/task-react-review-reliability <branch>` | `<branch>` vs base (3-dot diff) |
| `/task-react-review-reliability pr-<N>` | PR head in local branch `pr-<N>` (user runs the fetch) |

Append `deep` for the deep pass; `--base <branch>` for a non-trunk base. `task-react-review` spawns this workflow as a subagent and passes the pre-confirmed stack and framework, `base_ref` / `head_ref`, the pre-read diff and commit log, and the depth level; Steps 2-3 consume those instead of re-running, and Step 11 returns findings instead of writing. `task-code-review-reliability` does **not** spawn a subagent - it forwards the invocation arguments and stops, so that path is a normal standalone run that owns its own report and must write one.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Governs every step that follows; always runs, including in subagent mode.

### Step 2 - Confirm Stack and Detect Framework

Use skill: `stack-detect`. Accept a pre-confirmed stack from the parent and skip detection. If not React, stop and name the detected stack so the user can invoke that stack's reliability workflow - do not route back to `/task-code-review-reliability`, which is what dispatched here.

Record for the Summary block:

- `Framework:` Next.js (App Router) | Next.js (Pages Router) | Vite + React Router
- `Data Layer:` Server Components + `fetch` | TanStack Query | SWR | mixed
- `Boundary Library:` `error.tsx` segments | `react-error-boundary` | hand-rolled `componentDidCatch` | none detected

Heuristics: `next.config.*` -> Next.js (App Router unless `pages/` without `app/`); `vite.config.*` without `next` -> Vite; both present -> ask the user. React 19 adds `useActionState`, `useOptimistic`, and the `createRoot` error options `onCaughtError` / `onUncaughtError` (`onRecoverableError` shipped in React 18) - note the version, later steps branch on it. Record the TanStack Query major too: every default cited in Steps 6-9 is v5 (`throwOnError` was `useErrorBoundary` in v4, `gcTime` was `cacheTime`).

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`, forwarding `--base <branch>` when the invocation carried one. On approval, read `git diff <base>...<head>` and `git log <base>..<head>` once; reuse. Skip entirely when the parent passed `base_ref` / `head_ref` and the pre-read diff and log. Surface any fail-fast verbatim. No state-changing git.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 4 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into - a small diff ripples: a new hook calling an unchanged untimed fetch wrapper is a new hang at the call site. Follow one hop by default, and a second only when the first hop's file is itself part of a finding's failure path. Code added by the diff but not yet imported anywhere is still in scope - it ships.

- Boundary files: `app/**/error.tsx`, `app/global-error.tsx`, `app/**/loading.tsx`, `<ErrorBoundary>` mounts, `errorElement` in the Vite router
- Fetch layer: `fetch` wrappers, `axios` / `ky` instances, Server Component `fetch` calls, Route Handlers the client calls
- TanStack Query / SWR: `QueryClient` defaults, `useQuery` / `useMutation` call sites, query-key factories
- Mutation and write paths: Server Actions (`"use server"`), `useActionState` / `useOptimistic` consumers, `revalidatePath` / `revalidateTag` calls
- Route and boundary structure: `<Suspense>` placement, `next/dynamic` and `React.lazy` sites, third-party `<Script>` tags
- `next.config.*` and deploy config where chunk retention / `deploymentId` is set

Use skill: `react-data-fetching` - it owns the canonical query, mutation, invalidation, and optimistic-rollback patterns. Use skill: `ops-resiliency` for the retry, backoff and fallback vocabulary only - it is written for servers, so its connection pools, bulkheads, circuit-breaker libraries and per-dependency client modules do not translate to one browser tab and must not be recommended here. Use skill: `failure-propagation-analysis` for its tracing method only - follow one dependency's failure forward to what the user sees. Its incident-shaped sections (`Shared Resources on Path`, `Containment Assessment`) and its always-produce-all-sections rule do not apply: a browser client answers "none on path" for nearly all of them.

Consulted skills inform findings; this workflow's Output Format is the only envelope emitted (`failure-propagation-analysis` supplies the tracing method, not its own incident-shaped sections). Subagent mode: read changed files from the parent's pre-read diff; open unchanged files the diff calls into from the working tree.

### Step 5 - Error Boundaries and Render-Time Failure

Use skill: `react-component-patterns` for boundary placement. The segment-file semantics and the fallback's shape are defined in this step - no loaded atomic owns them.

- [ ] **A boundary above every route that renders remote data.** With none, one throw unmounts the whole tree and the user gets a blank white page with no way back.
- [ ] **Granularity matches the blast radius wanted.** A single root boundary turns a failed sidebar widget into a dead app; wrap optional regions so a partial failure degrades that region only.
- [ ] **Next.js segment semantics respected:** `error.tsx` is a Client Component receiving `{ error, reset }`, and it does **not** catch errors thrown by the layout of its own segment - that needs a boundary in the parent segment. `global-error.tsx` catches root-layout errors, is itself a Client Component, must render its own `<html>` and `<body>`, and is only active in production.
- [ ] **`reset` / `resetKeys` actually recover.** A `reset()` that re-renders the same failed state is a dead button; reset must be paired with re-running the query or with `resetKeys` on the value that changed (`react-error-boundary`).
- [ ] **Event-handler and async errors are routed to a boundary explicitly.** Boundaries catch render, lifecycle, and constructor errors only - a `throw` inside `onClick` or after an `await` never reaches them. Use `useErrorBoundary().showBoundary(error)` or handle it as local state; do not assume the boundary sees it.
- [ ] **The fallback is usable:** what failed, a retry affordance, and a way out (back / home). No raw `error.message`, stack trace, or blank `<div>`. `error.digest` is the correlation id to show - but it is set only for errors thrown on the server in production, so render it conditionally rather than printing a bare `Reference ` with nothing after it.

```tsx
// app/orders/error.tsx
"use client";

import Link from "next/link";
import { startTransition } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";

type ErrorProps = { error: Error & { digest?: string }; reset: () => void };

// Bad - reset re-renders the same failed state; the button does nothing.
export function BadError({ reset }: ErrorProps) {
  return <button onClick={reset}>Retry</button>;
}

// Good - clear whatever cached the failure, then reset. A server-rendered
// segment needs router.refresh() inside a transition; reset() alone re-runs
// the render with the same RSC payload. Clearing the query cache only helps
// when the failure came from a client query.
export default function OrdersError({ error, reset }: ErrorProps) {
  const router = useRouter();
  const qc = useQueryClient();
  return (
    <>
      <p>Could not load orders.{error.digest ? ` Reference ${error.digest}` : ""}</p>
      <button
        onClick={() =>
          startTransition(() => {
            qc.resetQueries({ queryKey: ["orders"] });
            router.refresh();
            reset();
          })
        }
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
- [ ] **Retryable is decided by status, not by retrying everything.** TanStack Query defaults to `retry: isServer ? 0 : 3`, so in the browser a 404 or 403 is retried three times, turning a fast failure into a slow one (server prefetches do not retry). This only bites once the `queryFn` actually throws on a non-`ok` response - `fetch` does not reject on 4xx, so a `queryFn` without an `res.ok` check silently caches an error body instead. Gate it: retry 408 / 429 / 5xx, network errors and timeouts, never other 4xx.
- [ ] **Backoff is capped.** TanStack's default `retryDelay` is exponential capped at 30s; a hand-rolled loop needs the same cap plus jitter, or a recovering API gets a synchronized retry wave from every open tab.
- [ ] **`Retry-After` honored when present** - it is seconds or an HTTP-date, never milliseconds; never wait less than the server asks.
- [ ] **In-flight requests are cancelled on unmount and on route change.** Pass the `signal` TanStack Query hands the `queryFn` straight into `fetch` so a key change or unmount aborts the request; a hand-rolled `useEffect` fetch needs its own `AbortController` aborted in the cleanup. Without it the response resolves into an unmounted tree and a fast navigation leaves a stale response overwriting a newer one.
- [ ] **An aborted request is not an error.** `AbortError` is dropped, never rendered as a failure banner on a route the user already left.
- [ ] **SWR equivalents, when SWR is the data layer:** `dedupingInterval` for `staleTime`, `shouldRetryOnError` + `onErrorRetry` for the retry predicate and its cap, `keepPreviousData` for the cached-fallback rule, and an explicit `mutate(key)` for invalidation. `react-data-fetching` covers `dedupingInterval`, `revalidateOnFocus`, conditional null keys and explicit `mutate`; the retry predicate and cached-fallback options are SWR's own. The failure modes and severities in this lens are identical either way.
- [ ] **`throwOnError` is a deliberate choice per query.** It routes the failure to the nearest boundary (whole region replaced); leaving it off keeps the failure inline in `error`. Picking neither means the component silently renders with `data === undefined`.

```tsx
class HttpError extends Error {
  constructor(readonly status: number) {
    super(`HTTP ${status}`);
  }
}

// Bad - never throws on 4xx, so the "error" is cached as data and the default
// retry never even fires; no cancellation, no deadline.
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

- [ ] **Every optimistic update has a rollback path.** The `onMutate` / `onError` / `onSettled` flow is not optional: `cancelQueries` (so an in-flight refetch cannot overwrite the rollback), snapshot via `getQueryData`, apply, restore the snapshot in `onError`, `invalidateQueries` in `onSettled`. An optimistic UI with no rollback is a lie the user acts on. `useOptimistic` (React 19) reverts when the action settles - **including on success**, back to whatever the underlying state is at that moment. Without a `revalidatePath` / `revalidateTag` or a `router.refresh()` that lands the new value first, a successful mutation visibly snaps back.
- [ ] **Mutations are not retried blind.** TanStack defaults mutations to `retry: 0`; turning retry on for a non-idempotent write double-applies it, because the client cannot distinguish a lost response from a lost request. Retry a write only with an idempotency key the server dedups on.
- [ ] **Server Actions are idempotent or guarded.** Neither React nor Next retries a Server Action - the risk is the user double-submitting, or a client-side retry wrapper. Disable the submit via `useFormStatus().pending`, and dedup server-side on a key.
- [ ] **Server Action failure reaches the UI.** Return a typed error state and surface it through `useActionState`; a thrown error in a Server Action becomes an opaque digest in production, so the user sees the generic boundary instead of "email already taken". Validation failures are returned state, not throws.
- [ ] **A rollback does not clobber a concurrent edit.** Restoring a whole list snapshot discards an item edited while the request was in flight; reconcile at the item level where concurrent edits are possible.

### Step 8 - Cache Staleness and Invalidation

- [ ] **Every mutation invalidates what it changed.** An untouched cache after a write is the most common stale-UI bug: the user saves, navigates back, and sees the old value.
- [ ] **`revalidateTag` over full-route `revalidatePath`**, and both must run on the server after the write - inside the Server Action or Route Handler, not during render (Next 15 throws `Route "/x" used "revalidatePath /x" during render which is unsupported` - it fails loudly, it does not silently no-op). Missing it leaves the RSC payload cached and the fresh client cache disagreeing with the server-rendered shell.
- [ ] **Invalidation covers every affected key**, including list + detail + count queries and any parallel route sharing the entity. A key factory makes this auditable; ad-hoc string keys make it guesswork.
- [ ] **`staleTime` is a stated decision per query.** The default `0` refetches on every mount; a long `staleTime` on data another user can change shows one tab a value the other tab already changed.
- [ ] **Cross-tab consistency is defined where it matters.** Auth state, feature flags, and entitlement changes propagate via `BroadcastChannel` or the `storage` event; without it a logged-out tab keeps issuing requests with a dead session and shows repeated failures instead of a login prompt.

### Step 9 - Offline and Degraded Network

- [ ] **`navigator.onLine` reports a network interface, not reachability.** A captive portal, a VPN, or a dead API all report `true`. Treat it as a hint for the affordance to show; treat the request result as the truth.
- [ ] **Offline is a defined state with its own affordance**, distinct from "the server broke" - not a generic error toast and not an empty list.
- [ ] **Refetch on reconnect is wired and bounded.** TanStack's `onlineManager` drives `refetchOnReconnect` (default on). Note what v5's default `networkMode: 'online'` actually does offline: queries are **paused** (`fetchStatus: 'paused'`, no error), so a component must render that state rather than a spinner - and every paused query resumes at once on reconnect, which is the burst to bound.
- [ ] **Cached data is served as a fallback rather than blanking the page.** A full-screen skeleton over data already in `gcTime` is a defect; render the cached value with a staleness indicator.
- [ ] **Offline writes have a defined answer** - rejected with a clear message, or queued with the queue's durability and ordering stated. A queue in a module-level array dies with the tab.
- [ ] **Rendering an empty list on failure is never acceptable** - "failed to load" and "you have none" must not look identical.

### Step 10 - Hydration, Streaming, and Chunk-Load Failure

- [ ] **No hydration-mismatch sources in render:** `Date.now()`, `Math.random()`, `new Date().toLocaleString()`, or `window` / `localStorage` reads. (React 19 tolerates unexpected tags injected into `<head>` / `<body>` by extensions and third-party scripts, so those are no longer a mismatch source.) React 19 recovers by discarding the server HTML and client-rendering from the nearest Suspense boundary above the mismatch - the whole root only when none exists. In the App Router a segment's `loading.tsx` is such a boundary, so the usual blast radius is that segment. It is still not cosmetic: the SSR result for that subtree is thrown away and state can flash or drop. `suppressHydrationWarning` silences one element; it is not a fix for the underlying divergence.
- [ ] **Suspense boundaries are placed so a slow or failing segment cannot hold the shell.** In the App Router `loading.tsx` is the segment's implicit Suspense boundary; `error.tsx` catches what that segment throws. Both belong to the same segment - `loading.tsx` alone means this segment's failure escapes to whatever boundary sits above it (High when none does, Medium when one does), `error.tsx` alone means a slow fetch blocks the shell.
- [ ] **Streaming failure is handled after the shell flushed.** Once streaming begins the status code is already sent, so an error later in the stream cannot become a 500 - it must resolve to an inline boundary fallback, or the user gets a half-rendered page. Errors thrown before the first flush can still redirect or 500.
- [ ] **Dynamic `import()` failure has a recovery path.** After a redeploy, a tab open on the old build requests chunks that no longer exist and every lazy route fails on click - `ChunkLoadError` on webpack, a `TypeError: Failed to fetch dynamically imported module` (surfaced via `vite:preloadError`) on Vite. Catch it in a boundary that detects the error and forces `location.reload()`, and keep prior build assets available so an open tab can still fetch them. `deploymentId` is the other half and is only useful when it changes per deployment: it stamps asset requests with `?dpl=` and sends `x-deployment-id`, so a stale client is detected and forced through a hard navigation. Next does not validate uniqueness, so reusing a value silently disables the mechanism. A host that retains immutable prior assets narrows this a lot; a host that does not breaks every open tab on each deploy.
- [ ] **Third-party scripts fail safe.** A blocked or timed-out analytics / chat / tag-manager script must not break the page: on Next use `next/script` with `strategy="lazyOnload"` and an `onError` (note `onLoad` / `onReady` / `onError` are unsupported with `beforeInteractive`, and using them makes the file a Client Component); on Vite, a plain `<script async>` with an `onerror` handler. Either way, no render path may assume `window.<vendor>` exists.

**Verify findings before writing.** Use skill: `review-finding-verify` with this lens's findings, the diff already read, and `base_ref` / `head_ref`. Publish only rows whose Verdict is not `Dropped`, carrying its `Label` column, and put its tally in the Summary's `Findings verified` slot - the verify table itself is not published. Subagent runs skip this - the parent verifies the merged set once.

### Step 11 - Write Report

**Subagent mode:** when `task-react-review` spawned this workflow, return its Output Format document - Summary, Findings, Recommendations, Next Steps, and at `deep` the Failure-Mode and User-Impact Map - and write nothing; the parent owns the report, merges the Findings and Next Steps, and carries the rest into its own `## Scope Sections`. Each finding already carries its `Label`; the parent does not re-derive labels. Skip the rest of this step.

**Round gate (standalone only).** Run this immediately after Step 3 resolves the refs, before reading any surface - a no-op exit should cost one `git rev-parse`, not a whole review. Resolve `<branch>` first, exactly as the writer call below does: the head's short name, or the handle's `current_branch` when `head_ref` is the literal `HEAD`. The prior-report key is `review-reliability-<branch>.md` with the writer's filename sanitization applied (`/` and any character outside `[A-Za-z0-9_-]` replaced, runs collapsed, ends stripped), so a `feature/x` branch looks up `review-reliability-feature-x.md`. The `prior_checkpoint` in the precondition handle names the **core** `review-<branch>.md` and is a different report - ignore it. If that file exists with valid frontmatter and its `head_sha` equals the current head, and this run adds no depth, print `No new commits on <branch> since prior reliability review at <sha_short>. Prior report unchanged.` and stop - no review, no report. Treat missing or invalid frontmatter as round 1 and overwrite.

**Reconcile (standalone, round 2+).** When a valid prior report exists and this is a diff-based run, Use skill: `review-prior-findings-reconcile`. It parses a `## High-Impact Findings` section containing one `### [<Label>] <file:line>` heading per finding followed by an `Issue:` line, which is not this workflow's report shape, so **re-project the prior report first**: emit that exact section heading, then per prior finding a `### [<Label>] <file:line>` heading taking the label from its `Label` slot and the location from its `Location` slot, followed by `- Issue: <its Issue text>` (reconcile reads that line as the finding's summary and cannot match without it). Pass the projection as `prior_report` along with the diff, the `git diff --name-status <base>...<head>` list from Step 3, and `head_sha`. Put the returned table under `## Prior Round Reconciliation`. Carry its `Still open` and `Needs re-check` rows into this round's Findings, in the section the prior report filed them under (the table returns a label, not a bucket - re-read the prior report for the bucket), with `(open since round <N>)` appended to the `Location` line and any `_(pre-existing)_` annotation preserved, since next round's reconcile keys on it. Map any legacy label the table preserved (`[Blocker]`, `[High]`, `[Suggestion]`, `[Question]`, `[Nitpick]`) into `[Must]` or `[Recommend]` before publishing anything outside the reconciliation table itself, which keeps them verbatim. Skip reconciliation entirely when there is no diff (audit mode or a whole-app sweep) and say so in the Summary.

Then Use skill: `review-report-writer` with `report_type: review-reliability` and every required field: `report_body`, `branch`, `base_ref` / `head_ref` from the precondition handle - when the handle's `head_ref` is the literal `HEAD` (no-argument mode), pass its `current_branch` instead, or the writer produces a `-HEAD.md` file the next round's lookup never finds, `base_sha` / `head_sha` from Step 3 (whole-app sweep: both = `git rev-parse HEAD`), `scope: +rel`, `depth` as resolved from the Depth table, `stack: typescript-nextjs` (Vite: `typescript-react`), and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha` (check for that file yourself; `review-precondition-check` looks up `review-<branch>.md`, a different report). Write before ending; print the confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = the user hits an unrecoverable or wrong state on a plausible failure (a route with no error boundary, `ChunkLoadError` with no recovery, an optimistic update with no rollback, a retried non-idempotent mutation or Server Action, an untimed `fetch` in an RSC render, a hydration mismatch, a `reset` that cannot recover, a failure rendered as empty content - `data ?? []` making "failed" indistinguishable from "none"); Medium = the failure is bounded but recovery or comprehension is impaired (missing invalidation after a mutation, retry on non-retryable 4xx, no cancellation on unmount, no offline affordance, error fallback with no next action, `loading.tsx` with no sibling `error.tsx` while a boundary exists higher in the tree - with none anywhere it is High's no-boundary case); Low = hardening with no immediate failure path (no jitter, `staleTime` undocumented, no cross-tab propagation on low-stakes state). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`. Each finding's `Label` slot carries the result (the verify pass's `Label` column overrides when it ran).

**One finding per root cause:** a defect matching several checklist lines (an uncancelled query that also retries a 403) is reported once at the strongest severity with the other aspects folded in.

```markdown
## React Reliability Review Summary

- **Stack Detected:** React <version> / TypeScript <version> _(from Step 2; `not detected` for either when the project does not reveal it)_
- **Framework:** Next.js (App Router) <version> | Next.js (Pages Router) <version> | Vite + React Router <version>
- **Data Layer:** Server Components + `fetch` | TanStack Query | SWR | mixed
- **Boundary Library:** `error.tsx` segments | `react-error-boundary` | hand-rolled `componentDidCatch` | none detected
- **Boundary Coverage:** every remote-data route | PARTIAL: <routes uncovered> | NONE _(from Step 5; a boundary that exists but cannot recover counts as uncovered - name it in the PARTIAL list)_
- **Timeouts:** all requests bounded | PARTIAL: <where missing> | NONE _(from Step 6)_
- **Cancellation:** signal threaded at file:line | absent _(from Step 6)_
- **Offline:** defined per path | partial | undefined _(from Step 9)_
- **Round:** <N> _(from Step 11; include from round 2 onward)_
- **Depth:** standard | deep
- **Findings verified:** <N> confirmed, <M> reattributed, <K> dropped (<F> false positive, <R> resolved by diff) _(the parenthetical only when K > 0)_; <U> of these unverified _(that clause only when a surviving row is unverified)_. _In subagent mode write exactly `not run (subagent; parent verifies the merged set)`._
- **Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line; carry the verify pass's annotation when it set one: `_(pre-existing)_`, `_(pre-existing; newly reachable via <path>)_`, `(unverified: <reason>)`]
   - **Label:** [Must | Recommend]
   - **Issue:** [name the React idiom: no `error.tsx` above the route, `retry: 3` on a 4xx, `signal` not threaded into `queryFn`, optimistic update with no `onError` rollback, `import()` with no `ChunkLoadError` recovery, hydration mismatch from `Date.now()`]
   - **Failure Mode:** [what fails and how: "the orders `fetch` has no timeout, so a stalled API leaves the RSC stream open and the route never resolves"]
   - **User Impact:** [what the person in the browser sees: "an indefinite skeleton on /orders; reloading reproduces it"]
   - **Fix:** [concrete React / Next.js change]

### Medium Impact

[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins

[Same numbered-block structure]

_Omit empty sections._

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

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
- [ ] Step 3 - `review-precondition-check` ran (or parent artifacts accepted); diff + log read once; `current_head_sha` and `current_base_sha` captured (Step 11 passes these as `head_sha` / `base_sha`). Whole-app sweep: the precondition fail-fast was announced verbatim and refs and full SHAs resolved from `HEAD` instead
- [ ] Step 4 - boundary files, fetch layer, query/mutation sites, Server Actions, Suspense and lazy sites, deploy config read, one hop out from the diff; `react-data-fetching`, `ops-resiliency` (vocabulary only) and `failure-propagation-analysis` (method only) consulted for patterns and user impact
- [ ] Step 5 - `react-component-patterns` consulted for boundary placement (segment semantics and fallback shape are defined in this step, not in an atomic); boundary presence and granularity, working `reset` / `resetKeys`, async-error routing, usable fallback audited
- [ ] Step 6 - `react-hooks-patterns` consulted; timeout on every request, a timeout abort distinguished from a cancellation, transient-only retry with capped backoff, `Retry-After`, `signal` threaded for unmount / route-change cancellation, `AbortError` not surfaced, `throwOnError` chosen deliberately, SWR equivalents applied when SWR is the data layer
- [ ] Step 7 - optimistic rollback complete (cancel / snapshot / set / rollback / settle), no blind mutation retry, Server Actions idempotent and their failures surfaced via `useActionState`, rollback safe against concurrent edits
- [ ] Step 8 - mutations invalidate every affected key, `revalidateTag` / `revalidatePath` called server-side after the write, `staleTime` stated, cross-tab consistency defined where it matters
- [ ] Step 9 - `navigator.onLine` treated as a hint, offline a distinct state, bounded refetch-on-reconnect, cache used as fallback, offline writes defined, no empty-list-on-failure
- [ ] Step 10 - hydration-mismatch sources checked, `loading.tsx` / `error.tsx` paired per segment, post-flush streaming failure handled, `ChunkLoadError` recovery present, third-party scripts fail safe
- [ ] Step 10 (verify) - `review-finding-verify` ran on the assembled findings (claims-only in a sweep); `Dropped` rows excluded; its `Label` column applied; tally in Summary. Subagent runs skip it and write the stated subagent string
- [ ] Step 11 - standalone: same-SHA no-op gate applied, prior round reconciled when a valid prior report existed, report written via `review-report-writer` (`scope: +rel`, `stack: typescript-nextjs` / `typescript-react`) with a real branch name, confirmation printed; subagent: Output Format document returned to parent, no file written
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
- Assuming an error boundary catches a `throw` in an event handler or after an `await` - it does not; route it with `showBoundary`
- Treating `error.tsx` as catching its own segment's layout errors, or omitting `<html>` / `<body>` from `global-error.tsx`
- Leaving TanStack's default `retry: 3` on a query whose 4xx failures are terminal
- Retrying a mutation or Server Action with no server-side idempotency key
- Accepting an optimistic update with no `onError` rollback, or a snapshot restore that clobbers a concurrent edit
- Landing a mutation with no `invalidateQueries` / `revalidateTag`, or calling revalidate during render
- Trusting `navigator.onLine` as proof the API is reachable
- Rendering an empty list on error, so "failed" is indistinguishable from "you have none"
- Showing raw `error.message` or a stack trace in a fallback - show `error.digest` when it is set, and a next action
- `suppressHydrationWarning` used to silence a real mismatch rather than fix its source
- Shipping `next/dynamic` / `React.lazy` routes with no stale-chunk recovery (the error name differs by bundler - match on both), or reusing a `deploymentId` across deployments so stale clients are never detected
- Reviewing whether the API's contract is well designed - that belongs to the owning service or the architecture plugin
- Duplicating perf depth (bundle size, render churn, Core Web Vitals) or observability depth (Sentry wiring, log fields)
- Reporting a bundler-specific error name without checking which bundler the project uses
- Recommending a server resiliency control (`ops-resiliency`'s circuit breakers, bulkheads, connection pools) in a browser tab
