---
name: flutter-networking
description: "Call HTTP APIs from Flutter with Dio: timeouts, CancelToken, interceptors, typed failure mapping, token refresh, backoff retry, caching."
metadata:
  category: mobile
  tags: [flutter, dart, dio, http, timeout, cancellation, retry, auth-token]
user-invocable: false
---


Single owner for outbound HTTP from the app. The device is a **client**: it consumes a contract it does not own, over a link that is slow, metered, and frequently absent. Typed failure shapes live in `flutter-error-handling`; cert pinning and secret storage in `flutter-security-patterns`. This skill owns client construction, timeouts, cancellation, interceptors, error mapping, and retry.

## When to Use

- Adding or reviewing any call to a remote API from a repository or data source
- Wiring auth headers, token refresh, logging, retry, or caching into the HTTP layer
- Deciding where a network error becomes a UI-visible failure
- Reviewing whether in-flight requests are cancelled when the screen that started them is gone

## Rules

- One `Dio` instance per API host, built once and injected. Never construct a client inside `build()`, a widget method, or per repository call
- Every request carries `connectTimeout` and `receiveTimeout`; requests with a body also carry `sendTimeout`. Dio applies no timeouts by default, and a stalled mobile radio hangs indefinitely without them
- Cross-cutting concerns (auth header, retry, logging, caching) live in interceptors, not at call sites
- Every cancellable request carries a `CancelToken` whose `cancel()` is wired to the disposal of whatever owns the request (`ref.onDispose`, `State.dispose`)
- No `DioException` escapes the data layer. Map it to a typed failure at the repository boundary (see `flutter-error-handling`)
- Token refresh is serialized and deduplicated: N concurrent 401s trigger one refresh, not N. Refresh and replay go through a client without the auth interceptor, and a replayed request is never refreshed twice
- Retry only idempotent requests (`GET`, `HEAD`, `PUT`, `DELETE`), bounded, with jitter, honouring `Retry-After`. Replaying any method once after a 401 refresh is not a retry: the server refused it unprocessed. A user-blocking call gets a short budget; longer waits belong to a background retry, not a spinner
- Tokens are read from secure storage, never `shared_preferences` (see `flutter-security-patterns`), and never written to logs or crash reports
- Base URLs come from `--dart-define` / flavor config, not string literals in Dart. An API key in either is compiled into the binary and public; keep it server-side

## Patterns

### One configured client, timeouts on every call

```dart
// Bad - fresh client per call, no timeouts: a dead radio hangs the screen forever
Future<Order> fetch(String id) => Dio().get('$base/orders/$id').then(...);

// Good - one instance, timeouts in BaseOptions, injected everywhere
final dio = Dio(BaseOptions(
  baseUrl: const String.fromEnvironment('API_BASE_URL'),
  connectTimeout: const Duration(seconds: 10),
  receiveTimeout: const Duration(seconds: 15),
  sendTimeout: const Duration(seconds: 15),
));
```

`connectTimeout` covers establishing the connection, `receiveTimeout` the gap while waiting on response data, `sendTimeout` the gap while uploading a body. A GET with no body is unaffected by `sendTimeout`. Override per call - `Options(receiveTimeout: ...)` for a slow report, `Options(sendTimeout: ...)` for an upload - rather than raising the global ceiling.

### Cancellation tied to disposal

```dart
// Bad - user leaves the screen, response still arrives and writes to dead state
final res = await dio.get('/orders');

// Good - token cancelled when the provider/State goes away
final token = CancelToken();
ref.onDispose(() => token.cancel('disposed'));           // Riverpod; State.dispose() otherwise
final res = await dio.get('/orders', cancelToken: token);
```

Screens on mobile are disposed constantly (back navigation, tab switch, low memory). An uncancelled request keeps the socket, the response bytes, and the closed-over state alive. Cancellation surfaces as `DioExceptionType.cancel`, which must map to a "cancelled" failure the UI ignores rather than an error banner.

### Transport errors to typed domain failures

```dart
// Bad - DioException reaches the widget; the UI switches on strings
} catch (e) { state = AsyncError(e, StackTrace.current); }

// Good - one translation point per data source; the mapper (cause, stack, 401, parse) is flutter-error-handling's
} on DioException catch (e, st) {
  Error.throwWithStackTrace(_toFailure(e, st), st);
}
```

The distinction the UI needs is retryable-vs-not and offline-vs-server-broken. `connectionError` means "no route to the server" and deserves an offline affordance; `badResponse` with 422 is the server rejecting the input: never retried, and shown against the form.

### Auth attach plus single-flight refresh

```dart
// Same adapter (TLS, pinning, test stub) and options, but no auth interceptor: refresh and replay go here
final retryDio = Dio(dio.options)..httpClientAdapter = dio.httpClientAdapter;
String? rejectedToken;                              // access token whose refresh the server rejected
DioException? lastFailure;                          // last transient refresh failure, and when
DateTime? lastFailureAt;

dio.interceptors.add(QueuedInterceptorsWrapper(     // queued: 401s handled one at a time
  onRequest: (options, handler) async {
    String? t;
    try { t = await secureStore.accessToken(); } catch (_) {} // a keystore fault must not stall the queue
    if (t != null) options.headers['Authorization'] = 'Bearer $t';
    handler.next(options);
  },
  onError: (e, handler) async {
    final req = e.requestOptions;
    if (e.response?.statusCode != 401 || req.extra['retried'] == true) return handler.next(e);
    if (req.data is FormData) req.data = (req.data as FormData).clone(); // a sent FormData cannot be resent
    final String? current;
    try {
      current = await secureStore.accessToken();
    } catch (err) {
      return handler.next(DioException(requestOptions: req, error: err)); // keystore fault: unknown, not offline
    }
    if (current == null || current == rejectedToken) return handler.next(e); // session already dead
    final String fresh;
    var refreshed = false;
    if (req.headers['Authorization'] != 'Bearer $current') {
      fresh = current;                              // already refreshed, or sent with no token: replay, no refresh
    } else if (lastFailureAt != null &&
        DateTime.now().difference(lastFailureAt!) < const Duration(seconds: 5)) {
      return handler.next(lastFailure!.copyWith(requestOptions: req)); // no second attempt yet
    } else {
      try {
        fresh = await refreshTokens(retryDio);      // rotates and stores both tokens
        refreshed = true;
      } on DioException catch (re) {
        if (const {400, 401}.contains(re.response?.statusCode)) {
          rejectedToken = current;                  // holds even if the delete below fails
          try { await secureStore.clearTokens(); } catch (_) {}
          return handler.next(e);                   // the 401 forces one logout
        }
        lastFailure = re;
        lastFailureAt = DateTime.now();
        return handler.next(re.copyWith(requestOptions: req)); // offline or 5xx as itself, attributed to the caller: the session survives
      } catch (err) {                               // the new tokens could not be stored
        lastFailure = DioException(requestOptions: req, error: err);
        lastFailureAt = DateTime.now();
        return handler.next(lastFailure!);
      }
    }
    try {
      handler.resolve(await retryDio.fetch(req
        ..headers['Authorization'] = 'Bearer $fresh'
        ..extra['retried'] = true));
    } on DioException catch (replayError) {
      if (refreshed && replayError.response?.statusCode == 401) { // a just-refreshed token was refused: end the session once
        rejectedToken = fresh;
        try { await secureStore.clearTokens(); } catch (_) {}
      }
      handler.next(replayError);                    // the replay's own failure
    }
  },
));
```

The stampede: an app resuming from background fires six parallel requests, all 401, all refresh. Without gating you burn six refresh tokens, and a server that rotates refresh tokens invalidates the session. The queued interceptor runs the six error handlers one at a time; the first refreshes, and each later handler sees that the stored token no longer matches the one its request carried, so it replays without refreshing; a request that went out with no token (a keystore fault in `onRequest`) replays the same way rather than spending a refresh. Every path ends in `next` or `resolve`, or the queue stalls. Refresh and replay go through `retryDio`, which shares the adapter so pinning covers the refresh call: replaying on the same `Dio` deadlocks when the replay fails, because its error handler queues behind the handler awaiting it. A failed replay surfaces as its own error rather than the original 401: a 401 on a replay that carried a just-refreshed token means that token was refused, so the handler records it as rejected and clears the tokens; a 401 on a no-refresh replay passes through as itself; anything else leaves the session intact. The `retried` marker stops a second refresh if the replay client ever gains an auth interceptor. Only a token the server has refused - at refresh, or on the replay that carried a just-refreshed token - ends the session, once; later handlers holding a refused token pass their 401s through. Any other refresh failure reaches the caller as itself (offline, timeout, 5xx, a keystore write fault), and the handlers queued within a few seconds get the same error instead of refreshing again. With rotating refresh tokens, a refresh whose response was lost or whose new pair could not be stored leaves the client holding a spent token; the server needs a short grace window for the previous refresh token, or that user is logged out.

### Bounded retry honouring `Retry-After`

```dart
const retryable = {408, 429, 500, 502, 503, 504};
final wait = _retryAfter(e.response) ??            // server's number wins
    Duration(milliseconds: (200 * (1 << attempt) * (0.5 + rnd.nextDouble())).round());
```

Only retry when the request is idempotent and the status is in the set above; a retried non-idempotent POST double-charges. `Retry-After` is **seconds or an HTTP-date**, not milliseconds; parse both forms (`HttpDate.parse` handles the date form but comes from `dart:io`, so guard it on web). Jitter your own backoff, never the server's value, and never wait less than it asks. If the wait exceeds the budget for a call a user is staring at, fail fast and let the retry happen on next screen entry. `dio_smart_retry` implements backoff, but by default it retries by status regardless of method: restrict its evaluator to idempotent methods and check its `Retry-After` handling before relying on it; do not stack it on top of a second retry layer.

Polling a status endpoint is not a retry: poll at a fixed interval with a maximum duration, wait out `Retry-After` on 429, and stop when the owner disposes. A large upload is a streamed `MultipartFile.fromFile`, rejected before sending when it exceeds the server limit, with a per-call `sendTimeout` sized to the body and `onSendProgress` for the UI; it is never retried automatically. Polling pauses while the app is in the background. A queued upload resubmitted when connectivity returns is not a retry either: each attempt is a new request carrying the same client-generated idempotency key, which the server deduplicates. Size a per-call `sendTimeout` to the body at the slowest supported uplink (about 1 MB per minute on poor cellular) plus margin.

### Caching

Prefer HTTP validators the server already sends: send back `If-None-Match` / `If-Modified-Since`, treat 304 as "reuse what you have". `dio_cache_interceptor` wires this into Dio with a pluggable store. Distinguish two caches and do not conflate them: an **HTTP cache** exists to save bytes and is disposable, while **offline data the user expects to see** is a local database concern and belongs in `flutter-data-persistence`. Never make correctness depend on a cache that a low-storage device can evict.

### Alternatives to Dio

`package:http` is the minimal choice: no interceptors and no `CancelToken`. `.timeout()` on the future stops waiting but does not abort the request; since `http` 1.5 an `AbortableRequest` with an `abortTrigger` future aborts it. Cross-cutting concerns become `BaseClient` wrappers, retry outermost:

```dart
class AuthClient extends http.BaseClient {
  AuthClient(this._inner, this._token);
  final http.Client _inner;
  final Future<String?> Function() _token;
  @override
  Future<http.StreamedResponse> send(http.BaseRequest r) async {
    final t = await _token();
    if (t != null) r.headers['Authorization'] = 'Bearer $t';
    return _inner.send(r);
  }
}

// package:http/retry.dart; RetryClient retries every method unless `when` says otherwise
final client = RetryClient(
  AuthClient(http.Client(), store.accessToken),
  when: (r) => r.statusCode == 502 && r.request?.method == 'GET',
);
```

`RetryClient` is that stack's built-in retry for the no-stacking rule, but its delay sees only the attempt count: it cannot honour `Retry-After` and adds no jitter. Where the server sends `Retry-After` (429, 503), retry in one wrapper of your own that reads the response instead. Fine for an app with a handful of endpoints. `chopper` generates a typed client over `http` and has its own interceptor model. `retrofit` generates a typed client over Dio and keeps everything in this skill applicable. Pick one and stay on it: two HTTP stacks means two timeout policies and two places auth can be wrong.

### Platform tiers

Mobile is the default assumption. On **web**, `dart:io` is unavailable (no `HttpDate`, no IO adapter, no cert pinning), CORS governs every request, and cookies are managed by the browser. On **desktop**, behaviour matches mobile; `AppLifecycleListener` reports a hidden or inactive window, a weaker signal than mobile backgrounding for triggering a refresh.

## Output Format

When invoked from an implementation workflow, emit the client contract:

```
Client: {Dio | http | chopper | retrofit+Dio | mixed - needs consolidation}

Instance: {file:line of the shared instance | planned: <module/provider> | constructed per call (defect)}

Timeouts: {connect=<d> receive=<d> send=<d> | PARTIAL: <missing> | MISSING}

Cancellation: {CancelToken bound to <dispose site> | AbortableRequest (http >= 1.5) bound to <dispose site> | CancelToken unbound | NONE}

Auth: {interceptor at file:line | per-call header | none}

Refresh: {single-flight + queued | single-flight on the auth client (deadlock) | unguarded (stampede) | none | N/A (static key, no refresh)}

Retry: {none | <n> attempts on <methods>, <backoff>, Retry-After <honoured | ignored> | outbox: resubmitted on reconnect with idempotency key <name> | UNBOUNDED or non-idempotent (defect) | stacked: <layers> (defect)}

Error Mapping: {DioExceptionType -> <failure type> at file:line | raw DioException reaches UI | swallowed into empty result at file:line | cancellation surfaced at file:line}

Caching: {none | HTTP validators (ETag/Last-Modified) | local store}
```

On a non-Dio stack, fill each line with the library's equivalent (a whole-future `.timeout()` budget goes under Timeouts). When the library has no such mechanism, write `unavailable (<library>): <mitigation | unmitigated>` in place of the line's absence value (`NONE`, `MISSING`, or `none`), so a missing feature is distinguishable from an unwired one. A `Dio` built inside a getter or factory is `constructed per call` unless its only reader caches the instance, in which case `Instance` names that reader. Cancelling an in-flight upload on screen exit leaves its outbox row queued. `Error Mapping` lists every value that applies, comma-separated; `Timeouts` holds the global values, then `; per-call: <endpoint> <d>` for overrides.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one block per finding:

```
### [{Blocker | Major | Minor}] {file:line}

- Call: {endpoint and one-line citation}
- Risk: {hang | leak | duplicate write | token invalidation | secret exposure | error leak to UI | swallowed error | retry storm | wasted bytes | config drift}
- Recommendation: {concrete edit}
```

`Blocker` = the Risk fires under normal use (no timeouts, ungated refresh, a refresh routed through its own interceptor, a replay on the auth client, or through a client with an auth interceptor and no `retried` guard, retried POST, retry without a bound, logged secrets, tokens in `shared_preferences`, an API key in source). `Major` = fires under realistic failure or scale (timeouts only partly set, a whole-future `.timeout()` alone included, retrying a 4xx other than 408/429, a notifier or widget calling the client with no repository boundary, a `Dio` built per call or in `build`, no or unbound `CancelToken` - `Risk: leak`, also when the library offers no cancellation - cancellation shown as an error, Retry-After ignored, a poll with no maximum duration or not stopped on dispose, an upload retried automatically, a user-blocking call with no short retry budget, raw errors to UI, errors swallowed into an empty result). `also <file:line>` goes on the `Call:` line; when two Risks apply, `Risk` names the worse one; a compiled-in key anchors on its declaration. `Minor` = cost or hygiene (missing cache validators, backoff without jitter, two stacks, a hardcoded base URL, a library floor in pubspec below the mechanism the fix needs). When a finding matches two bands, the higher band wins. Review mode emits no client contract; that block is implement mode's.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Call:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Risk` values, or the path of a file that could not be read) when any check could not be exercised, then `No networking findings.` when there are no blocks. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean; the sentinel is emitted only when there are no blocks, `Not checked` lines or not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Risk:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape and a request to review, audit, or explain a failure takes the review shape.

The closing lines - `Also seen` and `Not checked` only when they have content, the sentinel only when there are no blocks:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

No networking findings.
```

## Avoid

- `Dio()` inside `build()`, a widget method, or a repository method body
- Any request without `connectTimeout` and `receiveTimeout` - Dio has no defaults
- Awaiting a response after disposal with no `CancelToken`, then writing to disposed state
- Treating `DioExceptionType.cancel` as an error worth showing the user
- Refresh-on-401 without single-flight gating, or a refresh call that routes through its own auth interceptor
- Retrying POST, or retrying 4xx other than 408 / 429
- Reading `Retry-After` as milliseconds, or jittering the server's value downward
- Stacking a retry interceptor on top of a library's built-in retry
- `DioException`, status codes, or response maps reaching widgets
- Tokens in `shared_preferences`, or logging interceptors that print `Authorization` headers and PII bodies
- Hardcoded base URLs or API keys in Dart source
- Two HTTP stacks in one app
