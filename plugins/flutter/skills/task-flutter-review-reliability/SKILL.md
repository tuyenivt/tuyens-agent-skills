---
name: task-flutter-review-reliability
description: Flutter reliability review - timeouts, cancellation, offline and connectivity, retry backoff, optimistic rollback, UI states, background tasks.
agent: flutter-reliability-engineer
metadata:
  category: mobile
  tags: [flutter, dart, reliability, offline, retry, timeout, cancellation, background-tasks, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Flutter Reliability Review

Client reliability review: what the app does when the network is slow, absent, or lying; when a write fails after the UI already showed it succeeded; when the process is killed mid-sync; and when the server changes a contract that an installed older build still speaks.

**The network is not available, it is merely sometimes reachable.** Every call needs a timeout, a cancellation path tied to the lifetime of whatever started it, and a defined thing the user sees while it is in flight and after it fails. Every finding names the failure mode and what the user experiences, not just the missing pattern.

Stack-specific delegate of `task-code-review-reliability` for Flutter.

## When to Use

- Flutter PR adding or changing a network call, repository, sync path, or cache
- A screen that renders remote data reviewed for loading, error, and empty coverage
- Offline behaviour, connectivity handling, retry, or background scheduling being added
- Hardening after a hang, a stuck spinner, a lost write, or a crash on an old installed version

**Not for:** general review (`task-flutter-review`), frame cost and jank (`task-flutter-review-perf`), instrumentation coverage (`task-flutter-review-observability`), secure storage and transport hardening (`task-flutter-review-security`), an active incident (`/task-oncall-start` - mitigate first), fixing the server's own unreliability (route to the owning service).

## Seam With Adjacent Lenses

- **vs. Perf:** perf owns the app doing too much work; this lens owns the app not surviving something else being slow. A screen stuck on a spinner because a call has no timeout is reliability, even though it looks like slowness.
- **vs. Observability:** obs owns whether the failure was reported; this lens owns whether the retry, timeout, and fallback exist. A retry with no log line is obs; a retry with no cap is reliability.
- **vs. core Phase B:** `task-flutter-review` Phase B owns happy-path correctness, disposal, and `BuildContext` across async gaps; this lens owns partial failure, offline, and staleness. Disposal sits at the seam - a `CancelToken` never cancelled on dispose belongs here; a `StreamSubscription` never cancelled is a Phase B leak. The umbrella dedups.
- **There is no UX lens.** A missing loading, error, or empty state is a reliability finding here - it is a hole in the screen's state machine and has no other home.
- **There is no `+api` scope.** This client consumes contracts it does not own. How the client survives a contract it did not expect is this lens; whether the contract is well designed belongs to the owning service or the architecture plugin.

## Depth

| Depth      | When                                              | Runs                                       |
| ---------- | ------------------------------------------------- | ------------------------------------------ |
| `standard` | Default                                           | All steps except the Failure-Mode Map      |
| `deep`     | Requested, or handed down by `task-flutter-review` | All + `Failure-Mode and User-Impact Map`   |

At `deep`, trace each new or changed dependency's failure path with `failure-propagation-analysis` and name, per dependency, what the user sees and what stops the failure from spreading.

**Whole-app sweep** (reliability-debt pass with no feature branch): when Step 3 fails fast on trunk, do not stop - skip the diff gate and run Steps 4-12 repo-wide at `HEAD` (Step 4's categories read in full, not per changed file); findings cite current code; checkpoint `base_sha` = `head_sha` = `HEAD`.

## Generated Code

Exclude from findings: `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, and generated localization output. When a generated file changed, cite the source that produces it - the annotated model, the route declaration. A diff of only generated files is a no-op - say so rather than manufacturing findings.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-flutter-review-reliability` | Current branch vs base; fails fast on trunk |
| `/task-flutter-review-reliability <branch>` | `<branch>` vs base (3-dot) |
| `/task-flutter-review-reliability pr-<N>` | PR head fetched into local branch (user runs fetch) |

Append `deep` to request the deep pass. When invoked as a subagent (e.g. by `task-flutter-review`), the parent passes the pre-confirmed stack and project shape, the precondition handle, the pre-read diff and commit log, the depth level, and the generated-file exclusion list. Steps 2-3 consume those instead of re-running, and Step 12 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from the parent and skip detection. If not Flutter, stop and route the user to `/task-code-review-reliability`.

Record: HTTP client (Dio / http / chopper / retrofit / mixed), state management, persistence store, connectivity package, background scheduler, and platform targets.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with the handle and artifacts pre-passed. Surface any fail-fast verbatim.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 4 - Read the Reliability Surface

Read every changed file in these categories plus any unchanged file the diff calls into - a small diff ripples: a new repository method calling an unchanged untimed client is a new hang at the call site.

- HTTP client construction and interceptors - timeouts, retry, cancellation, error mapping
- Repositories and data sources - failure conversion, cache reads, offline fallbacks
- State holders (notifiers, blocs, providers) that own async work - cancellation on dispose, error state, rollback
- Screens rendering remote data - loading, error, empty, and data branches
- Local persistence and sync paths - write ordering, conflict handling, interrupted-run recovery
- Background task registration and app-lifecycle handlers
- Model deserialization touched by a server contract change - unknown fields, new enum values, newly-null fields

Use skill: `flutter-reliability` - it owns the canonical patterns for every step below (cache-then-network, retryable-vs-terminal classes, timeout budget, rollback, queued writes, conflict policy, UI state machine, background limits, tolerant parsing). Its finding blocks are input to this workflow; emit findings in **this** skill's Output Format. Use skill: `ops-resiliency` for retry / backoff / breaker / fallback framing, applied to client-to-server calls. Use skill: `failure-propagation-analysis` to trace how a failure at each new or changed dependency reaches the user - this gives each finding its user impact.

### Step 5 - Timeouts and Cancellation

Use skill: `flutter-networking` for client construction, timeout fields, and `CancelToken` wiring.

- [ ] **A timeout on every outbound call.** Dio applies none by default: set `connectTimeout` and `receiveTimeout` on the shared instance, plus `sendTimeout` for requests with a body. With `package:http` the equivalent is `.timeout(...)` on the future - hand-rolled per call, which is exactly why it gets forgotten.
- [ ] **A cancellation path tied to the caller's lifetime** - a `CancelToken` cancelled from `ref.onDispose` / `State.dispose`. Screens on mobile are disposed constantly (back navigation, tab switch, memory pressure); an uncancelled request keeps the socket, the response bytes, and the closed-over state alive, then writes to dead state.
- [ ] **`Future.timeout` alone is not cancellation.** It throws `TimeoutException` but leaves the underlying work running and the socket open; pair it with the request's cancellation token.
- [ ] **Cancellation is not an error.** A cancelled request maps to a "cancelled" outcome the UI drops, never an error banner on a screen the user already left.
- [ ] **Non-HTTP waits are bounded too** - platform-channel calls, plugin futures, local database work, and stream awaits can hang; an unbounded `await` inside a state holder is a permanent spinner.
- [ ] **End-to-end timeout budget on chained calls.** A screen that awaits three sequential calls at 15s each can make the user wait 45s. Derive a budget for the interaction, and let a slow first leg shorten what remains rather than each leg getting a full ceiling independently.

```dart
// Bad - no timeout, no cancellation: the user backs out, the spinner state lives on
final res = await dio.get('/orders');

// Good - bounded, and cancelled when the owner goes away
final token = CancelToken();
ref.onDispose(() => token.cancel('disposed'));
final res = await dio.get('/orders', cancelToken: token);
```

### Step 6 - Retry, Backoff, and Error Classification

Use skill: `ops-resiliency` for backoff, jitter, and budget rules. Use skill: `flutter-error-handling` for the typed failure that carries retryability.

- [ ] **Retryable vs terminal is decided once, by type, not by string matching.** Timeouts, connection errors, 408, 429, and 5xx are retryable; 4xx other than those is terminal and retrying it only spends battery. A 422 form error retried three times shows the user a slow failure instead of a fast one.
- [ ] **Bounded attempts with exponential backoff and jitter.** An uncapped retry on a dead backend drains the battery and, across a user base, becomes a thundering herd when the backend recovers.
- [ ] **`Retry-After` honoured when present** - it is seconds or an HTTP-date, never milliseconds. Never wait less than the server asks, and jitter your own backoff rather than the server's value.
- [ ] **Non-idempotent writes are not retried without an idempotency key.** A retried purchase or transfer double-applies; the client cannot tell a lost response from a lost request.
- [ ] **Retry layers are not stacked** - a retry interceptor on top of a library's built-in retry multiplies attempts silently.
- [ ] **A user-blocking retry has a short budget.** If the wait exceeds what someone will stare at, fail fast with a retry affordance and move the work to next screen entry or a background path.
- [ ] **Repeated failure against one endpoint degrades that feature locally and backs off.** After N consecutive failures, stop attempting for a cool-off window and render the degraded state instead of thrashing between spinner and error. This is the client form of a breaker - it protects battery, data allowance, and the UI, and is scoped to this one install; it does not protect the server.

### Step 7 - Connectivity and Offline Behaviour

- [ ] **Connectivity APIs report the transport, not reachability.** A device on a captive-portal wifi, or with a working radio and a dead backend, reports connected. Treat a connectivity signal as a hint for the affordance you show; treat the actual request result as the truth.
- [ ] **Offline is a defined state, not an error string.** The failure maps to an offline variant with its own affordance, distinct from "the server broke".
- [ ] **Reads render from local state first and refresh behind it.** A full-screen spinner over content the app already has stored is a defect, and it is the version of this bug that ships most often. Store the fetch timestamp with the data so the UI can tell fresh from month-old and show staleness rather than guess at it.
- [ ] **A defined answer for every read path with no network** - cached data with a staleness indicator, or an explicit empty-with-reason state. Silently rendering an empty list is the most damaging version, because it is indistinguishable from "you have no orders".
- [ ] **A defined answer for every write path with no network** - rejected with a clear message, or queued with the queue's durability, ordering, and failure handling stated. A queue that lives only in memory loses the write on process death.
- [ ] **Recovery on reconnect is bounded** - resuming does not fire every queued request at once, and does not re-fire work already completed.

### Step 8 - Optimistic Updates, Cache Staleness, and Conflict

- [ ] **Every optimistic update has a rollback path.** The pre-update state is captured before the mutation and restored on failure, and the user is told the change did not stick. An optimistic UI with no rollback is a lie the user acts on.
- [ ] **Rollback survives an intervening change** - restoring a whole snapshot can clobber an edit made while the request was in flight. Reconcile at the item level where concurrent edits are possible.
- [ ] **Cache invalidation is defined per entity**, with a stated staleness tolerance. "Cached forever until the app restarts" is a decision that must be deliberate.
- [ ] **Conflict resolution is named where local and remote can both change** - last-write-wins, server-authoritative, or merge. An unnamed policy is silently last-writer-wins with whoever synced last.
- [ ] **Sync is resumable and idempotent.** The process can be killed at any point: a partially applied sync must be re-runnable without duplicating or dropping records.
- [ ] **Correctness never depends on an evictable cache.** A low-storage device can clear an HTTP cache at any time; data the user expects to see belongs in the local database (see `flutter-data-persistence`).

### Step 9 - UI State Completeness

Use skill: `flutter-error-handling` for failure-to-state mapping. Use skill: `flutter-riverpod-patterns` (or the project's state library) for how the states are expressed.

Treat every screen that renders remote data as a state machine that must cover **loading, data, empty, and error** - plus **refreshing** wherever pull-to-refresh or re-fetch exists, because refreshing while showing stale data is a different render than a first load.

- [ ] **Empty is distinguished from error and from loading.** Inferring emptiness from a null check collapses three states into one.
- [ ] **Every error state offers a next action** - retry, go back, or a stated reason it cannot be retried. A dead end with a message is a support ticket.
- [ ] **Error text is derived from the failure variant and localized.** `e.toString()` and raw status codes are never shown.
- [ ] **No terminal loading state.** Every path that sets loading has a path that clears it, including the throw path. A loading flag set in a `try` and cleared only on success is a permanent spinner.
- [ ] **State writes after an await are guarded** - a disposed owner is not written to (this is the reliability face of the `BuildContext`-across-async-gaps rule in Phase B).
- [ ] **A failure inside a partial region degrades that region**, not the whole screen: an optional widget's data failing should not blank the page.

```dart
// Bad - the throw path never clears loading; the spinner is permanent
state = const Loading();
final orders = await repo.load();   // throws
state = Data(orders);

// Good - every exit clears it, and empty is its own state
state = const Loading();
try {
  final orders = await repo.load();
  state = orders.isEmpty ? const Empty() : Data(orders);
} on AppFailure catch (f) {
  state = ErrorState(f);
}
```

### Step 10 - Background Work and Platform Limits

- [ ] **Background execution is opportunistic, never guaranteed.** iOS schedules background tasks at the OS's discretion with a hard execution window and the user can disable background refresh entirely; Android defers work under Doze and app-standby buckets and OEM battery managers kill it outright. Any design that assumes a task runs at a fixed interval is wrong on both platforms.
- [ ] **Background work is idempotent and interruptible** - it can be killed mid-run and re-run later, so it must be safe to repeat and must checkpoint rather than assume completion.
- [ ] **The foreground path does not depend on the background path having run.** Schedule freshness, never correctness: a queued write must also drain on next foreground. Opening the app re-checks rather than trusting a sync that may never have happened.
- [ ] **The background callback runs in a separate isolate** with no access to the app's state. It re-initializes its own plugins and dependencies and communicates through storage, never through memory shared with the UI isolate.
- [ ] **Long work is not attempted on the UI isolate** - heavy parse or transform moves off it (`compute` / a background isolate), or the app freezes and the OS may kill it.
- [ ] **App-lifecycle transitions are handled** - work started while foregrounded is cancelled, paused, or made safe when the app is backgrounded; a resumed app refreshes state that may have gone stale rather than showing whatever was on screen an hour ago.
- [ ] **Notification and push-triggered paths handle a cold start** - the handler cannot assume providers, auth, or the router are already initialized.

### Step 11 - Version Skew and Contract Change

Use skill: `ops-backward-compatibility` for the compatibility matrix and expand-contract framing, read from the **consumer** side. Use skill: `flutter-data-persistence` when the change touches on-device storage.

Old app versions stay installed for months. Users on metered connections, locked-down devices, or an OS the latest build no longer supports may never update. Every server change must be survivable by the oldest build still in the field.

- [ ] **Deserialization tolerates the unexpected** - unknown fields ignored, a new enum value mapped to a known fallback rather than throwing, a field that becomes nullable handled. An exhaustive `switch` over a server-supplied enum crashes the moment the server adds a case; the parse layer must widen it to a fallback variant before the domain sees it.
- [ ] **The PR states which installed versions this change breaks**, or states that it breaks none. "No old callers" needs evidence, not assumption.
- [ ] **A removed or renamed field is not read unconditionally** by code that ships before the server change lands, and vice versa - deploy order is stated.
- [ ] **A minimum-version gate exists for changes that cannot be made compatible** - a server-driven force-update or feature gate, so an incompatible old build shows a clear screen rather than crashing or corrupting data.
- [ ] **Local schema changes are forward-safe** - a user can downgrade, reinstall, or restore a backup; a migration that only moves forward must at least fail loudly rather than corrupt.

### Step 12 - Write Report

Standalone only. When spawned by `task-flutter-review`, return findings in the Output Format to the parent and write nothing - the parent owns the single merged report. At `deep`, a subagent returns the Failure-Mode and User-Impact Map with its findings so the parent can preserve it as its own section.

Use skill: `review-report-writer` with `report_type: review-reliability` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha` / `head_sha` from Step 3 (whole-app sweep: both = `HEAD`), `stack: flutter`, `scope: +rel`, `depth` as resolved from the Depth table, and `mode: full`, `round: 1` - unless `review-reliability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

**Severity assignment:** High = the app hangs, loses a write, double-applies one, corrupts local data, or crashes on a plausible failure (a call with no timeout, an optimistic update with no rollback, a retried non-idempotent write, a terminal loading state, a `switch` that throws on a new server enum value); Medium = the failure is bounded but recovery or comprehension is impaired (missing empty state, an error with no retry affordance, no offline affordance, uncapped-but-short retry, unstated conflict policy); Low = hardening with no immediate failure path (staleness tolerance undocumented, backoff without jitter on a cold path). Labels: High -> `[Must]`; Medium -> `[Recommend]`, escalated to `[Must]` when the fix is one line on a critical path; Low -> `[Recommend]`.

**One finding per root cause:** a defect matching several checklist lines (an uncancelled call that also writes to disposed state) is reported once at the strongest severity with the other aspects folded in.

```markdown
## Flutter Reliability Review Summary

**Stack Detected:** Flutter <version> / Dart <version>
**HTTP Client:** Dio <version> | http | chopper | retrofit+Dio | mixed
**State Management:** Riverpod | Bloc | Provider | GetX | none
**Persistence:** <store> | none
**Timeouts:** all calls bounded | PARTIAL: <where missing> | NONE
**Cancellation:** bound to disposal at file:line | unbound | absent
**Offline:** defined per path | partial | undefined
**Background Work:** <scheduler> | none
**Platform Targets:** <list>
**Overall:** Resilient | Gaps Found - [<N> High / <N> Medium / <N> Low]

## Findings

### High Impact

1. **Location:** [file:line]
   **Issue:** [name the gap: no `receiveTimeout` on the shared client, `CancelToken` never cancelled, optimistic update with no rollback, loading never cleared on the throw path, exhaustive `switch` over a server enum]
   **Failure Mode:** [what fails and how: "the radio stalls, the request never returns, and the notifier stays in Loading"]
   **User Impact:** [what the person holding the phone sees: "an indefinite spinner on the orders screen; force-quitting the app is the only exit"]
   **Fix:** [concrete Dart change]

### Medium Impact

[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins

[Same numbered-block structure]

_Omit empty sections._

## Recommendations

[Structural reliability improvements not tied to a single finding]

## Failure-Mode and User-Impact Map

_(`deep` only - omit at `standard`.)_
Per new or changed dependency: **what happens when it is slow, absent, or returns something unexpected**, what the user sees in each case, and what contains it (a timeout, a bounded retry, a cached fallback, an offline state, a version gate).

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: server contract] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (server contract, release gating, platform config). Order Must > Recommend. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no background tasks, no optimistic updates).

- [ ] Step 1: behavioral principles loaded (or accepted from parent)
- [ ] Step 2: stack confirmed Flutter; HTTP client, state management, persistence, connectivity package, background scheduler, and platform targets recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once; `current_head_sha` and `current_base_sha` captured
- [ ] Step 4: clients, repositories, state holders, screens, sync paths, background registration, and deserialization read; `flutter-reliability`, `ops-resiliency`, and `failure-propagation-analysis` consulted for patterns and user impact
- [ ] Step 5: `flutter-networking` consulted; timeout on every call, cancellation bound to disposal, `Future.timeout` not mistaken for cancellation, cancellation not surfaced as error, non-HTTP waits bounded, end-to-end budget
- [ ] Step 6: `flutter-error-handling` consulted; retryable vs terminal by type, capped backoff with jitter, `Retry-After`, idempotency key before retrying a write, no stacked retry layers, local degradation on a flapping endpoint
- [ ] Step 7: connectivity treated as a hint not a truth; local-first reads with stored staleness; offline a defined state; read and write paths defined offline; bounded reconnect recovery
- [ ] Step 8: optimistic rollback present and safe; cache invalidation and staleness stated; conflict policy named; sync resumable; no correctness on an evictable cache
- [ ] Step 9: loading / data / empty / error (and refreshing) covered per screen; every error offers a next action; localized text; no terminal loading; post-await writes guarded; partial-region degradation
- [ ] Step 10: background work treated as opportunistic, idempotent, interruptible; foreground independent of it; separate-isolate callback contract respected; heavy work off the UI isolate; lifecycle transitions and cold-start entry points handled
- [ ] Step 11: `ops-backward-compatibility` consulted; tolerant deserialization, broken installed versions named, deploy order stated, minimum-version gate, forward-safe local schema
- [ ] Step 12: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Generated files excluded from findings; source cited instead
- [ ] Every finding names the failure mode and what the user experiences, never just the missing pattern
- [ ] Client framing held - no server pool, middleware, or service-mesh recommendations
- [ ] Depth honored: `standard` ran all; `deep` filled the Failure-Mode and User-Impact Map
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend (omit if none)

## Avoid

- Reporting a missing pattern without the failure mode and user impact ("add a timeout" vs "no `receiveTimeout`, so a stalled radio leaves an indefinite spinner the user can only escape by force-quitting")
- Server framing on a client: connection pools, middleware, graceful shutdown, service mesh, distributed transactions. The device is one user, one process, one install
- Writing a report when invoked as a subagent - the parent owns it
- Chaining `mode` / `round` off the general review's checkpoint instead of `review-reliability-<branch>.md`
- `git fetch` / `git checkout` from this workflow
- Raising findings against `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, or generated localization output
- Any request without a timeout - Dio applies none by default and `package:http` requires `.timeout(...)` per call
- `Future.timeout` alone treated as cancellation - the underlying work keeps running
- A full-screen spinner over content already sitting in the local store
- Awaiting after disposal with no cancellation, then writing to dead state
- Treating a cancelled request as a user-visible error
- Retrying a non-idempotent write with no idempotency key, or retrying a 4xx other than 408 / 429
- Stacking a retry interceptor on a library's built-in retry
- Trusting a connectivity signal as proof the backend is reachable
- Accepting an optimistic update with no rollback, or a rollback that clobbers a concurrent edit
- Rendering an empty list on error, so "failed" is indistinguishable from "you have none"
- Showing `e.toString()`, a status code, or a stack trace to the user
- Assuming a background task runs at the interval it was registered with
- An exhaustive `switch` over a server-supplied enum with no fallback - the next server release crashes every installed build
- Reviewing whether the server's contract is well designed - that belongs to the owning service or the architecture plugin
- Duplicating perf depth (rebuild cost, frame budget) or observability depth (crash reporting, log fields)
- Mitigating a live incident here - route to `/task-oncall-start` first
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
