---
name: flutter-reliability
description: "Harden Flutter apps against bad networks: offline-first cache, connectivity checks, backoff retry, cancellation, optimistic rollback, UI states."
metadata:
  category: mobile
  tags: [flutter, dart, offline-first, retry, connectivity, cancellation, background, state-machine]
user-invocable: false
---

# Flutter Reliability

> Load `Use skill: stack-detect` first. This skill owns behaviour when the network, the platform, or the server misbehaves. Client construction, timeouts, and interceptor mechanics live in `flutter-networking`; failure typing in `flutter-error-handling`; local storage schema in `flutter-data-persistence`; crash and event reporting in `flutter-observability`.

The mobile baseline is **offline, interrupted, and out of date**. A phone loses connectivity mid-request, gets suspended by the OS mid-write, and runs a build shipped months ago against a server that has moved on. Reliability here means the app stays usable and honest in those states, not that a dependency is highly available.

## When to Use

- Designing or reviewing a feature that reads or writes over the network
- Deciding what the app shows and does with no connection, a flaky one, or a slow one
- Adding retry, background sync, optimistic updates, or a local cache
- Reviewing loading/error/empty state handling, or how an old build tolerates a server change

## Rules

- Reads render from local state first and refresh in the background. A spinner blocking content the app already has is a defect.
- Connectivity APIs report the network **interface**, not reachability. Treat them as a hint to retry sooner, never as a precondition that gates a request.
- Retry only idempotent operations, bounded, with exponential backoff plus jitter, and only for retryable error classes (see table). A non-idempotent write is retried only when it carries an idempotency key the server honours.
- Every request is cancellable and its cancellation is bound to the lifecycle of whatever started it. Cancellation is never surfaced as an error.
- One timeout budget per user-visible operation. The sum of nested timeouts must not exceed what the user will wait for.
- Optimistic updates capture the pre-update state and restore it on failure. An update with no captured rollback is not optimistic, it is a lie.
- UI state is one sealed value, not parallel booleans. Empty is a distinct state from loading and from error.
- Queued writes are durable, ordered per entity, deduplicated by a stable client-generated id, and drained on reconnect - not held in memory.
- Background execution is opportunistic on every platform. Correctness never depends on a background task running, only freshness does.
- Parsing tolerates additive server change: unknown fields ignored, unknown enum values mapped to a documented fallback, never a crash.
- Repeated failure against one dependency degrades that feature locally and backs off; it does not retry-loop or take down the rest of the app.

## Patterns

### Cache-then-network

```dart
// Bad - blank screen on every open, and an unusable screen with no connection
final orders = await api.fetchOrders();

// Good - emit what is stored, then refresh; staleness is data, not a guess
Stream<Cached<List<Order>>> orders() async* {
  final local = await db.orders();
  if (local.isNotEmpty) yield Cached(local, fetchedAt: await db.ordersFetchedAt());
  try {
    final fresh = await api.fetchOrders();
    await db.putOrders(fresh);
    yield Cached(fresh, fetchedAt: DateTime.now());
  } on AppFailure catch (e) {
    if (local.isEmpty) rethrow;      // nothing to show: a real error state
    yield Cached(local, fetchedAt: ..., staleBecause: e); // otherwise degrade visibly
  }
}
```

Store the fetch timestamp with the data. Without it the UI cannot distinguish fresh from month-old, and cannot decide whether to skip the network entirely. A refresh failure on top of usable cached data is a subtle banner, not a full-screen error that throws away content the user can still act on.

### Connectivity is a hint, not a gate

```dart
// Bad - captive portal, VPN, and "connected to a router with no uplink"
// all report a connection; the request is never attempted
if (await connectivity.checkConnectivity() == ConnectivityResult.none) return;
final res = await api.fetch();

// Good - always attempt; use the signal to schedule the next attempt
try {
  return await api.fetch();
} on NetworkFailure {
  return cache.value; // and let the connectivity stream trigger the retry
}
```

`connectivity_plus` documents this explicitly: it reports the active interface, so Wi-Fi behind a captive portal reads as connected. Its result shape changed across major versions (single value in v5 and earlier, a list in v6+) - read the version pinned in `pubspec.yaml` before writing the comparison. Real reachability needs an actual request; a dedicated checker package or a cheap authenticated ping is the only honest answer, and both cost a round trip.

### Retryable vs terminal

| Class | Examples | Action |
|-------|----------|--------|
| Transient transport | connect/receive timeout, connection reset, DNS failure | retry with backoff; unlimited attempts only in background |
| Server transient | 408, 429, 500, 502, 503, 504 | retry with backoff; honour `Retry-After` when present |
| Auth recoverable | 401 with a usable refresh token | refresh once, replay once, then treat as terminal |
| Terminal client | 400, 403, 404, 409, 422 | never retry; surface to the user or fix the request |
| Terminal local | parse failure, schema mismatch, disk full | never retry; report and degrade |
| Not an error | cancellation, dispose race | drop silently |

```dart
// Bad - fixed delay, so every device that dropped off Wi-Fi retries in lockstep
await Future.delayed(const Duration(seconds: 2));

// Good - exponential with full jitter, capped
final base = min(maxDelay.inMilliseconds, initial.inMilliseconds * (1 << attempt));
await Future.delayed(Duration(milliseconds: rnd.nextInt(base + 1)));
```

Jitter matters more on mobile than on a server: a tower reconnecting or an app resuming from background releases thousands of clients into the same millisecond. Retry budgets differ by context - a user staring at a spinner gets a short one and a fast failure with a Retry affordance; a background sync gets a long one.

### Cancellation bound to lifecycle

```dart
// Bad - user leaves; the write lands and the callback touches disposed state
Future<void> load() async { state = await repo.fetch(); }

// Good - one token per owner, cancelled on disposal, and a post-await guard
final token = CancelToken();
ref.onDispose(token.cancel);                      // State.dispose() outside Riverpod
final data = await repo.fetch(cancelToken: token);
```

Beyond the token, any `await` in a `State` method needs a `mounted` check before touching `context` or calling `setState`, because the widget can be gone by the time the future completes. Cancellation must reach the UI as "nothing happened" - a cancelled request rendered as an error banner trains users to ignore error banners.

### Timeout budget across a chain

```dart
// Bad - three 30s timeouts in series: 90s of spinner
final a = await stepA().timeout(const Duration(seconds: 30));

// Good - one deadline, each step gets what remains
final deadline = DateTime.now().add(const Duration(seconds: 10));
Duration left() => deadline.difference(DateTime.now());
final a = await stepA().timeout(left());
final b = await stepB().timeout(left());
```

Set the budget from what the user will tolerate for that interaction, then divide it, rather than setting a per-call timeout and discovering the total by accident. `Future.timeout` throws `TimeoutException` and, critically, **does not stop the underlying work** - pair it with the request's cancellation token or the socket stays open.

### Optimistic update with rollback

```dart
// Bad - state changed, failure swallowed, UI now disagrees with the server forever
state = state.copyWith(liked: true);
unawaited(api.like(id));

// Good - snapshot, apply, restore on failure
final previous = state;
state = state.copyWith(liked: true);
try {
  await api.like(id);
} on AppFailure catch (e) {
  state = previous;                 // exact restore, not a manual inverse
  ref.read(toastProvider).show(messageFor(e));
}
```

Restore the captured snapshot rather than applying an inverse operation - inverses drift once a second change lands between the two. Apply optimism only where the server almost always agrees and the failure is cheap to explain: a like, a reorder, a local flag. Never for payments, bookings, or anything the user reads back as confirmation.

### Queued writes and conflict resolution

A write made offline needs a durable queue row carrying a client-generated id, the entity key, the payload, an attempt count, and a `nextAttemptAt`. The id is what makes a replay safe: send it as the idempotency key so a retry after an ambiguous timeout does not create a second order.

Pick one conflict policy per entity and write it down:

| Policy | Fits | Cost |
|--------|------|------|
| Server wins | reference data, anything the client only reads | local edits made offline are silently discarded |
| Last write wins (server timestamp) | independent scalar fields, flags | a stale device can overwrite a newer edit |
| Per-field merge | documents edited on several devices | needs per-field versions and a merge implementation |
| Explicit user resolution | high-value or unmergeable content | a UI to build and a state to hold |

"Last write wins by device clock" is not a policy - phone clocks are wrong. Order by a server-assigned timestamp or version.

### UI state as a machine

```dart
// Bad - four booleans, sixteen combinations, most impossible
bool isLoading; bool hasError; List<Order> orders; bool isEmpty;

// Good - one sealed value; the impossible states cannot be constructed
sealed class OrdersState {}
final class OrdersLoading extends OrdersState {}
final class OrdersEmpty extends OrdersState {}
final class OrdersData extends OrdersState { OrdersData(this.orders, {this.stale = false}); ... }
final class OrdersError extends OrdersState { OrdersError(this.failure, {this.cached}); ... }
```

With Riverpod, `AsyncValue` is already this machine: it carries loading, data, and error, and distinguishes a first load from a refresh over existing data. Do not wrap it in a second parallel flag. What it does not model is **empty** - a successful response with zero rows is `AsyncData`, and rendering it as a blank list is the most common reliability bug that never gets reported, because it looks exactly like a screen that is still loading. Branch on emptiness explicitly and give it its own affordance.

### Background execution

Background work is opportunistic and platform-limited. `workmanager` exposes one-off and periodic tasks; Android enforces a minimum period around 15 minutes and applies Doze and app-standby restrictions, while iOS schedules background refresh at times the system chooses and grants no guarantee that a task ever runs. A user force-quitting an iOS app stops its background work until the next manual launch.

Two consequences: schedule refresh, never correctness - a queued write must also drain on next foreground - and remember the callback runs in a **separate isolate** with no access to your app's state, so it re-initialises plugins and dependencies itself and communicates through storage, not memory.

### Old builds against a moved server

An installed build keeps calling the server for months after release. Two defences, both client-side:

1. **Tolerant parsing.** Ignore unknown fields; map an unknown enum value to a documented fallback variant instead of throwing; treat a newly-nullable field as nullable now, not in the next release.
2. **A version floor the app can act on.** A remote-config or unauthenticated endpoint that returns a minimum supported version lets the app show a blocking upgrade prompt instead of failing in twenty different ways. Feature flags let the server disable a client feature whose contract it can no longer serve.

```dart
// Bad - a value the server adds next quarter crashes every installed build
Status.values.byName(json['status'] as String);

// Good - unknown maps to a fallback the UI already renders
Status fromWire(String? s) =>
    Status.values.firstWhere((e) => e.name == s, orElse: () => Status.unknown);
```

### Local degradation on a flapping dependency

After N consecutive failures against one endpoint, stop attempting it for a cool-off window and render that feature's degraded state directly. This protects the app - battery, the user's data allowance, and a UI that would otherwise thrash between spinner and error - and is scoped to one client. Reset the counter on the first success, and keep the rest of the app fully usable.

### Platform tiers

Mobile is the default assumption. On **desktop**, there is no OS suspension to design around and background work is just an isolate, but the process can be killed at any time, so queue durability still applies. On **web**, `dart:io` is unavailable, storage is subject to browser eviction, and there is no background execution after the tab closes - offline support degrades to what a service worker and browser storage provide.

## Output Format

When invoked from an implementation workflow, emit the reliability contract per feature:

```
Feature: {name}
Read Path: {cache-then-network | network-only | cache-only}
Staleness: {timestamp stored + surfaced | stored, not surfaced | not tracked}
Connectivity: {hint for scheduling | used as a gate (defect) | unused}
Retry: {none | <n> attempts, expo+jitter, classes=<list> | unbounded (defect)}
Idempotency: {client id sent as key | none | N/A (read-only)}
Cancellation: {token bound to <dispose site> | unbound | none}
Timeout Budget: {<total> across <n> steps | per-call only | none}
Optimistic: {snapshot+rollback at file:line | no rollback (defect) | none}
Write Queue: {durable + deduped + drains on <trigger> | in-memory | none}
Conflict Policy: {Server-Wins | Last-Write-Wins | Field-Merge | User-Resolves | undefined}
UI States: {sealed: loading/data/empty/error | AsyncValue + explicit empty | booleans (defect)}
Background: {workmanager <task> - freshness only | correctness depends on it (defect) | none}
Contract Tolerance: {unknown fields+enums tolerated | strict parse | version floor at file:line}
```

When invoked from a review workflow, emit one block per finding:

```
### [Blocker | High | Medium | Low] lib/path/file.dart:LINE

- Evidence: {one-line citation, or the missing handling and where it belongs}
- Defect: {Offline-Blind | Gate-On-Connectivity | Unbounded-Retry | Unsafe-Retry | Leaked-Work | No-Budget | No-Rollback | Lost-Write | Undefined-Conflict | Boolean-State | Missing-Empty | Background-Dependent | Brittle-Parse}
- Failure Mode: {what the user experiences, and in which network or lifecycle condition}
- Fix: {concrete edit}
```

| Defect | Meaning |
|--------|---------|
| `Offline-Blind` | no usable state without a live network, though data was available locally |
| `Gate-On-Connectivity` | a request suppressed because a connectivity check said no |
| `Unbounded-Retry` | no cap, no backoff, or no jitter |
| `Unsafe-Retry` | a non-idempotent write retried without an idempotency key |
| `Leaked-Work` | in-flight work not cancelled on dispose, or state written after disposal |
| `No-Budget` | nested timeouts whose total exceeds the interaction's tolerance, or no timeout |
| `No-Rollback` | optimistic mutation with no captured pre-state |
| `Lost-Write` | an offline write held only in memory, or dropped on failure |
| `Undefined-Conflict` | concurrent edits with no stated resolution policy, or device-clock ordering |
| `Boolean-State` | parallel flags encoding states that a sealed type should make unrepresentable |
| `Missing-Empty` | zero-result success rendered as a blank or loading-looking screen |
| `Background-Dependent` | correctness relies on a background task the OS may never run |
| `Brittle-Parse` | unknown field or enum value crashes an installed build |

Severity: `Blocker` = data loss, a duplicate write, or the app unusable in a common network state. `High` = a plausible condition leaves the user stuck with no path forward. `Medium` = degraded or confusing behaviour with a workaround. `Low` = polish on an already-correct path.

## Avoid

- A full-screen spinner over content already in the local store
- `checkConnectivity()` as a precondition for making a request
- Retrying without jitter, without a cap, or on a 4xx that will never succeed
- Retrying a POST with no idempotency key after an ambiguous timeout
- `Future.timeout` alone as cancellation - the underlying work keeps running
- Timeouts chosen per call, with the end-to-end wait discovered in production
- Optimistic mutation with a hand-written inverse instead of a restored snapshot
- Optimistic UI for payments, bookings, or anything the user treats as confirmed
- An offline write queue in memory, or one that retries out of order per entity
- Ordering conflicting edits by device clock
- `isLoading` + `hasError` + a nullable list as the state model
- Treating an empty successful response as a loading or error state
- Assuming a periodic background task runs on schedule, or at all on iOS
- Sharing app state with a background isolate through memory
- `values.byName` / a non-exhaustive parse on a server-controlled enum
- Backend framing: no service-mesh circuit breaking, no server-side saga or outbox, no fleet-level health checks - a client degrades itself, it does not protect a server
