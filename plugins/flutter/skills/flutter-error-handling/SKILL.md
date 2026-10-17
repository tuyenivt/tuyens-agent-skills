---
name: flutter-error-handling
description: "Model typed Dart failures: sealed hierarchies, exhaustive switch, Result vs throw, error mapping to UI states, Flutter error boundaries."
metadata:
  category: mobile
  tags: [flutter, dart, error-handling, sealed-classes, result, freezed, riverpod]
user-invocable: false
---

# Flutter Error Handling

> This skill owns failure typing and propagation. Transport specifics live in `flutter-networking`.

## When to Use

- Designing the failure type for a new feature, repository, or data source
- Reviewing code that catches, converts, or renders errors
- Deciding `Result` vs `throw` at a layer boundary
- Wiring app-level error boundaries and the uncaught-error handler

## Rules

- A caught error is handled, converted, or rethrown. `catch (_) {}` and `catch (e) { return null; }` are defects, not style.
- The domain layer owns a `sealed` failure type. Foreign exceptions (`DioException`, `SocketException`, `FormatException`, storage errors) are converted at the repository boundary and never escape above it.
- `switch` over failures is exhaustive with no `default` - adding a variant must break the build at every decision site; the presentation switch over `AsyncValue`'s `Object` error keeps one `_` arm.
- Catch by type with `on`. Bare `catch (e, st)` only at a boundary that must not crash, and it logs the stack trace.
- Preserve stack traces: `rethrow`, or `Error.throwWithStackTrace(failure, st)` when rethrowing a converted error. Never `throw e` inside a `catch`.
- Exceptions model expected failures; `Error` subclasses model programmer bugs. Never catch an `Error` for control flow; the one exception is deserializing an untrusted payload, where a bad shape surfaces as `TypeError` or `ArgumentError`.
- Inside a Riverpod async provider, throw the typed failure - `AsyncValue` is already the result type. Wrapping in `Result` as well is duplication. Riverpod 3 retries a failing provider automatically and wraps a failing dependency's error in `ProviderException`: set `retry:` so non-retryable failures are not retried - `retry: (count, e) => e is AppFailure && e.isRetryable && count < 3 ? Duration(seconds: 1 << count) : null` (a `ProviderException` gets `null`: its dependency already retries itself) - and unwrap `ProviderException` before switching on the failure in the UI.
- Reach for `Result` where nothing else forces the caller to consider failure: Dart has no checked exceptions, so a thrown error is invisible in the signature.
- Every failure carries a stable variant, whether retry is meaningful, and the original cause plus stack for reporting.
- User-facing text is derived from the failure variant in the presentation layer and localized. `e.toString()` is never shown to a user.
- Cancellation is not a failure. Map it to a dedicated `CancelledFailure` variant at the repository boundary; every presentation-layer switch renders nothing for it (no banner, no retry) and it is never reported as an error.

## Patterns

### Sealed failure hierarchy

```dart
sealed class AppFailure implements Exception {
  const AppFailure({this.cause, this.stackTrace});
  final Object? cause;
  final StackTrace? stackTrace;

  bool get isRetryable => switch (this) {
        NetworkFailure() || TimeoutFailure() => true,
        ServerFailure(:final status) => status >= 500,
        CancelledFailure() || UnauthorizedFailure() || ParseFailure() || InsecureFailure() => false,
      };
}

final class NetworkFailure extends AppFailure { const NetworkFailure({super.cause, super.stackTrace}); }
final class TimeoutFailure extends AppFailure { const TimeoutFailure({super.cause, super.stackTrace}); }
final class CancelledFailure extends AppFailure { const CancelledFailure({super.cause, super.stackTrace}); }
final class UnauthorizedFailure extends AppFailure { const UnauthorizedFailure({super.cause, super.stackTrace}); }
final class ParseFailure extends AppFailure { const ParseFailure({super.cause, super.stackTrace}); }
final class InsecureFailure extends AppFailure { const InsecureFailure({super.cause, super.stackTrace}); } // pinning / validateCertificate rejection, or a platform TLS failure (arrives as `unknown` with a HandshakeException)
final class ServerFailure extends AppFailure {
  const ServerFailure(this.status, {super.cause, super.stackTrace});
  final int status;
}
```

`sealed` restricts subtyping to this library, which is what makes downstream `switch` exhaustive. `final` on the variants stops feature code from adding a subclass the mapper has never seen.

freezed unions generate the same shape plus `copyWith` and value equality. Prefer them when failures carry several fields. The class-modifier syntax freezed expects differs across its major versions - follow the version pinned in `pubspec.yaml` rather than a remembered snippet.

One shared failure type for cross-cutting variants every feature meets (network, timeout, auth, parse); a feature declares its own sealed type when its variants are meaningless outside it (validation rules, domain states) or when their UI or retry decision differs from the shared variant's (a declined card, an idempotency conflict), embedding the shared type as a variant's field or implementing the same `isRetryable` contract rather than duplicating transport variants.

### Exhaustive switch, no `default`

```dart
// Bad - default absorbs every future variant silently
String messageFor(AppFailure f) {
  switch (f) {
    case NetworkFailure(): return 'You are offline';
    default: return 'Something went wrong';
  }
}

// Good - no default; adding RateLimitFailure fails compilation here
String messageFor(AppFailure f, AppLocalizations l10n) => switch (f) {
      NetworkFailure() => l10n.offline,
      TimeoutFailure() => l10n.slowConnection,
      UnauthorizedFailure() => l10n.sessionExpired,
      CancelledFailure() => '', // unreachable: presentation filters Cancelled before messageFor
      ParseFailure() || InsecureFailure() => l10n.somethingWentWrong,
      ServerFailure(:final status) => l10n.serverError(status),
    };
```

The compile error is the whole point: a new failure variant should force a decision at every place a user sees an error, not silently inherit the generic message.

### Mapping data-layer errors into domain failures

```dart
// Bad - DioException escapes; now the widget layer imports Dio to read statusCode
Future<User> fetch(String id) async {
  final res = await _dio.get<Map<String, dynamic>>('/users/$id');
  return User.fromJson(res.data!);
}

// Good - one conversion point per data source
Future<User> fetch(String id) async {
  try {
    final res = await _dio.get<Map<String, dynamic>>('/users/$id');
    return User.fromJson(res.data!);
  } on DioException catch (e, st) {
    Error.throwWithStackTrace(_toFailure(e, st), st);
  } on FormatException catch (e, st) {
    Error.throwWithStackTrace(ParseFailure(cause: e, stackTrace: st), st);
  } on TypeError catch (e, st) {
    // generated fromJson surfaces a bad payload as a cast error, not FormatException
    Error.throwWithStackTrace(ParseFailure(cause: e, stackTrace: st), st);
  } on ArgumentError catch (e, st) {
    // an unknown enum value in the payload ($enumDecode)
    Error.throwWithStackTrace(ParseFailure(cause: e, stackTrace: st), st);
  } on CheckedFromJsonException catch (e, st) {
    // json_serializable with checked: true wraps the failure
    Error.throwWithStackTrace(ParseFailure(cause: e, stackTrace: st), st);
  } on BadKeyException catch (e, st) {
    // required: true, disallowNullValue, disallowUnrecognizedKeys violations (json_annotation)
    Error.throwWithStackTrace(ParseFailure(cause: e, stackTrace: st), st);
  }
}

AppFailure _toFailure(DioException e, StackTrace st) => switch (e.type) {
      DioExceptionType.connectionTimeout ||
      DioExceptionType.sendTimeout ||
      DioExceptionType.receiveTimeout =>
        TimeoutFailure(cause: e, stackTrace: st),
      DioExceptionType.connectionError => NetworkFailure(cause: e, stackTrace: st),
      DioExceptionType.cancel => CancelledFailure(cause: e, stackTrace: st),
      DioExceptionType.badResponse when e.response?.statusCode == 401 =>
        UnauthorizedFailure(cause: e, stackTrace: st),
      DioExceptionType.badResponse =>
        ServerFailure(e.response?.statusCode ?? 0, cause: e, stackTrace: st),
      DioExceptionType.badCertificate => InsecureFailure(cause: e, stackTrace: st),
      DioExceptionType.unknown when e.error is FormatException || e.error is TypeError =>
        ParseFailure(cause: e, stackTrace: st), // Dio could not decode the body, or it did not match the requested response type
      DioExceptionType.unknown when e.error is HandshakeException =>
        InsecureFailure(cause: e, stackTrace: st), // platform TLS rejection (dart:io)
      DioExceptionType.unknown => NetworkFailure(cause: e, stackTrace: st),
    };
```

The mapper switch names every `DioExceptionType` member, so a new member is a compile error rather than a silent `NetworkFailure`. A parse boundary that catches only `FormatException` still crashes on a malformed payload: `json_serializable`'s generated casts throw `TypeError`, and an unknown enum value throws `ArgumentError`; with `checked: true` the generated code throws `CheckedFromJsonException` instead, and `required: true`, `disallowNullValue`, and `disallowUnrecognizedKeys` violations throw `BadKeyException` subclasses from `json_annotation`. This is the one place catching an `Error` subtype is correct: untrusted server data is input, not a local bug. A body Dio itself fails to decode arrives as `DioException` of type `unknown` with the `FormatException` in `error`; a body that does not match the requested response type arrives the same way with the `TypeError` in `error` - `fetch` wraps both.

`DioException`/`DioExceptionType` exist from Dio 5.2; Dio 5.0-5.1 expose the same members as `DioError`/`DioErrorType`, while Dio 4's `DioErrorType` has a different member set (`connectTimeout`, `response`, `other`; no `badCertificate` or `connectionError`), so the mapper is rewritten there, not renamed.

### `Result` vs `throw`

```dart
sealed class Result<T> {
  const Result();
}
final class Ok<T> extends Result<T> { const Ok(this.value); final T value; }
final class Err<T> extends Result<T> { const Err(this.failure); final AppFailure failure; }
```

| Boundary | Choice | Why |
|----------|--------|-----|
| Repository consumed by a Riverpod `AsyncNotifier` / `FutureProvider` | `throw` | `AsyncValue` already captures the error; `Result` would nest two error models |
| Synchronous validation and parsing | `Result` | failure is an ordinary outcome, and the signature forces the caller to handle it |
| A loop that must finish despite per-item failures | `Result` | `try`/`catch` per iteration reads worse and loses which items failed; the service returning per-item `Result`s can sit under a throwing notifier, where a whole-batch failure (unreadable file, missing header) still throws |

Pick one per layer and stay consistent. A codebase where half the repositories throw and half return `Result` forces every call site to check which convention applies.

### Failure to UI state

```dart
final userProvider = FutureProvider.family<User, String>(
  (ref, id) => ref.watch(userRepoProvider).fetch(id),
  // Riverpod 3: pass the retry: callback from the Rules so non-retryable failures are not retried
);

// Widget - the only place a failure becomes words
ref.watch(userProvider(id)).when(
      loading: () => const LoadingView(),
      data: (user) => UserView(user),
      error: (e, st) {
        final err = e is ProviderException ? e.exception : e; // Riverpod 3 wraps the thrown failure
        return switch (err) {
          CancelledFailure() => const SizedBox.shrink(), // cancellation renders nothing
          final AppFailure f => ErrorView(
              message: messageFor(f, l10n),
              onRetry: f.isRetryable ? () => ref.invalidate(userProvider(id)) : null,
            ),
          _ => ErrorView(message: l10n.somethingWentWrong),
        };
      },
    );
```

The `_` arm is required because `AsyncValue`'s error is typed `Object` - anything can be thrown. A hit on that arm is a mapping bug: it renders the generic view, and the bug is reported once from a `ref.listen` on the provider, never from `build`, which reruns on every rebuild.

### App-level error boundaries

```dart
void main() {
  WidgetsFlutterBinding.ensureInitialized();

  FlutterError.onError = (details) {
    Report.error(details.exception, details.stack); // framework: build, layout, paint
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    Report.error(error, stack); // async errors outside the framework
    return true; // handled; returning false lets it reach the platform
  };
  ErrorWidget.builder = (details) => const CrashPlaceholder();

  runApp(const ProviderScope(child: App()));
}
```

`PlatformDispatcher.instance.onError` covers what `runZonedGuarded` used to be needed for. Use one or the other, not both: an error caught by the zone never reaches `PlatformDispatcher`, so coverage splits across two handlers, and calling `ensureInitialized` outside the zone triggers a zone-mismatch warning.

`ErrorWidget.builder` replaces the red error screen for a failed subtree build. It must never itself throw, and it is a last resort - it means a widget escaped local handling.

### A caught error is handled or rethrown

```dart
// Bad - failure vanishes; the UI shows an empty list forever with no way to retry
Future<List<Order>> load() async {
  try {
    return await repo.fetchOrders();
  } catch (_) {
    return [];
  }
}

// Good - a deliberate fallback is stated, and the failure is still reported
Future<List<Order>> load() async {
  try {
    return await repo.fetchOrders();
  } on NetworkFailure catch (e, st) {
    Report.warn(e, st);
    return _cache.orders(); // documented degraded path, not a silent empty state
  }
}
```

Empty-on-error is the most common Flutter error bug: it renders identically to "no data", so the user sees a legitimate-looking empty screen and support cannot tell the two apart.

## Output Format

When invoked from an implementation workflow, emit one row per boundary:

```
| Boundary | Failure Type | Propagation | Rationale |
|----------|--------------|-------------|-----------|
| UserRemoteDataSource | AppFailure (sealed) | Throw | consumed by FutureProvider; AsyncValue carries it |
| CheckoutFormValidator | ValidationFailure | Result | sync, caller must branch |
| ImportBatchService | AppFailure per item | Result | partial success must survive one bad row |
```

`Propagation: {Throw | Result | Degrade | Silent-Cancel | None}` - `Degrade` means a documented fallback value plus a report call, and the Failure Type cell names the failure degraded; `Silent-Cancel` means the boundary throws `CancelledFailure` and every presentation switch renders nothing for it, never reporting it (the one row value that also prescribes presentation); `None` means by design no failure crosses this boundary, with the reason in Rationale. Rows are data, service, and state boundaries, plus one row for the app-level handlers (`FlutterError.onError` + `PlatformDispatcher.onError`, Propagation `None`, Rationale naming the reporter); presentation mapping is not a row. A boundary that produces several failure types is one row listing them. Device failures more than one feature meets (`PermissionDeniedFailure`, `StorageFullFailure`) are variants of the shared type; a feature declares its own sealed type under the rule in the Patterns section. An existing stringly-typed exception class the new boundaries would throw through is replaced by the sealed type (`Fixed in plan`); one the new code never touches is `Pre-existing`. An open, server-defined reason code stays a `String` field, mapped to copy through a lookup with a generic fallback - exhaustiveness applies to the variant, not the code. A feature variant gets its own class when the UI or retry decision differs from the shared variant (a declined card, an idempotency conflict); server-supplied reason codes stay a field on that variant.

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow, emit one finding block per defect:

```
### [{Blocker | High | Medium | Low}] {file:line}

- Code: {one-line citation}
- Defect: {Swallowed | Untyped | Unmapped | Leaked | Stack-Lost | Raw-Message | Boundary-Config | Error-Caught | Double-Wrapped | Incomplete-Failure | Cancellation-Surfaced | Provider-Retry | Duplicated-Mapping}
- Impact: {what the user sees, or what is lost from reporting}
- Fix: {concrete edit}
```

| Defect | Meaning |
|--------|---------|
| `Swallowed` | caught and discarded, replaced by an empty/null value or a stored message with no report, or an awaited mutation whose failure leaves a loading state with no handler |
| `Untyped` | failures modelled as `Exception`/`String` instead of a sealed variant |
| `Unmapped` | a `switch` over failures, or a mapper over a foreign error enum, uses `default`/`_` outside the presentation `Object` guard, so new variants fall through |
| `Leaked` | a data-layer exception type is visible above the repository boundary, or a failure reaches the zone handler instead of a boundary (an un-awaited call, a stream `listen` without `onError`) |
| `Stack-Lost` | `throw e` inside `catch`, a conversion that drops the original stack, or a bare `catch (e)` that never captures the stack |
| `Raw-Message` | `e.toString()` or an untranslated string rendered to the user |
| `Boundary-Config` | app-level handlers misconfigured: split coverage (`runZonedGuarded` + `PlatformDispatcher.onError`), missing `FlutterError.onError`/`PlatformDispatcher.onError`, an `ErrorWidget.builder` that can throw |
| `Error-Caught` | an `Error` subtype caught for control flow outside untrusted-payload decoding |
| `Double-Wrapped` | `Result` returned into a Riverpod async provider |
| `Incomplete-Failure` | a failure type missing a stable variant, retryability, or cause and stack |
| `Cancellation-Surfaced` | cancellation, or a completion after dispose, shown to the user, reported as an error, or never modelled |
| `Provider-Retry` | Riverpod 3 `retry:` left at its default for non-retryable failures, or `ProviderException` not unwrapped before switching |
| `Duplicated-Mapping` | the same error mapping repeated across data sources instead of one mapper per source |

`Blocker` = failure invisible or app unable to report (Swallowed, Boundary-Config with no reporting path, an `ErrorWidget.builder` that can throw). `High` = wrong handling on a user-facing path (Leaked, Raw-Message, Unmapped, Cancellation-Surfaced, Error-Caught). `Medium` = degraded diagnostics or fragile typing (Stack-Lost, Untyped, Incomplete-Failure, Double-Wrapped, Boundary-Config that still reports - split coverage, or one of the two app-level handlers missing while the other reports). `Medium` also covers Provider-Retry, emitted even when the failure is currently swallowed. `Low` = a finding whose only cost is readability (Duplicated-Mapping). When a finding matches two bands, the higher band wins.

Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-platform-channels, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Defect` values, or the path of a file that could not be read) when any check could not be exercised, then `No error-handling findings.` when there are no blocks. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean; the sentinel is emitted only when there are no blocks, `Not checked` lines or not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Impact:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape and a request to review, audit, or explain a failure takes the review shape.

The closing lines - `Also seen` and `Not checked` only when they have content, the sentinel only when there are no blocks:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

No error-handling findings.
```

On a non-Riverpod stack (Bloc, Provider), a caught failure lands in the framework's error state as the typed failure, never as `e.toString()`; `Leaked` and `Raw-Message` apply unchanged, while `Double-Wrapped` and `Provider-Retry` are Riverpod-only and are neither reported nor counted. On `package:http`, the boundary maps `ClientException`, `SocketException`, `TimeoutException`, and non-2xx status codes into the sealed type; with no cancellation mechanism in the stack, `Cancellation-Surfaced` is clean. `PlatformException` and `MissingPluginException` map at the same repository boundary (see `flutter-platform-channels`).

## Avoid

- `catch (_) {}`, or returning `null`/`[]`/`false` from a `catch` without a report
- `default` or `_` in a `switch` over the sealed failure type outside the presentation `Object` guard
- `throw e` inside a `catch` block - use `rethrow` or `Error.throwWithStackTrace`
- `DioException`, `SocketException`, `SqliteException` or `PlatformException` in a widget, notifier, or use case
- `Result<T>` returned from a repository that a Riverpod async provider consumes - `AsyncValue` is the result
- Catching `Error` subtypes for control flow, except deserialization of untrusted payloads
- A single `AppException` with a `String code` field - that is a stringly-typed enum with no exhaustiveness
- Showing `e.toString()`, a status code, or a stack trace to the user
- Surfacing `CancelToken` cancellation or post-dispose errors as user-visible failures
- `runZonedGuarded` alongside `PlatformDispatcher.instance.onError` - split coverage
- Error-mapping logic duplicated across data sources instead of one mapper per source
