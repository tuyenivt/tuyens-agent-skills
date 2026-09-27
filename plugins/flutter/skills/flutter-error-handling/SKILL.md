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
- `switch` over failures is exhaustive with no `default` - adding a variant must break the build at every decision site.
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
final class InsecureFailure extends AppFailure { const InsecureFailure({super.cause, super.stackTrace}); } // TLS or pinning rejection
final class ServerFailure extends AppFailure {
  const ServerFailure(this.status, {super.cause, super.stackTrace});
  final int status;
}
```

`sealed` restricts subtyping to this library, which is what makes downstream `switch` exhaustive. `final` on the variants stops feature code from adding a subclass the mapper has never seen.

freezed unions generate the same shape plus `copyWith` and value equality. Prefer them when failures carry several fields. The class-modifier syntax freezed expects differs across its major versions - follow the version pinned in `pubspec.yaml` rather than a remembered snippet.

One shared failure type for cross-cutting variants every feature meets (network, timeout, auth, parse); a feature declares its own sealed type only when its variants are meaningless outside it (validation rules, domain states), and may embed the shared type as a variant's field rather than duplicating transport variants.

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
      DioExceptionType.unknown when e.error is FormatException =>
        ParseFailure(cause: e, stackTrace: st), // Dio's transformer failed to decode the body
      DioExceptionType.unknown => NetworkFailure(cause: e, stackTrace: st),
    };
```

The mapper switch names every `DioExceptionType` member, so a new member is a compile error rather than a silent `NetworkFailure`. A parse boundary that catches only `FormatException` still crashes on a malformed payload: `json_serializable`'s generated casts throw `TypeError`, and an unknown enum value throws `ArgumentError`; with `checked: true` the generated code throws `CheckedFromJsonException` instead. This is the one place catching an `Error` subtype is correct: untrusted server data is input, not a local bug. A body Dio itself fails to decode arrives as `DioException` of type `unknown`, not `FormatException`.

`DioException`/`DioExceptionType` exist from Dio 5.2; Dio 5.0-5.1 and Dio 4 expose `DioError`/`DioErrorType`.

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
        final err = e; // Riverpod 3: e is ProviderException ? e.exception : e
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

`Propagation: {Throw | Result | Degrade | Silent-Cancel | None}` - `Degrade` means a documented fallback value plus a report call; `Silent-Cancel` means cancellation mapped to `CancelledFailure`, rendered as nothing and never reported; `None` means by design no failure crosses this boundary, with the reason in Rationale. Rows are data, service, and state boundaries; presentation mapping is not a row. An open, server-defined reason code stays a `String` field, mapped to copy through a lookup with a generic fallback - exhaustiveness applies to the variant, not the code. A feature variant gets its own class when the UI or retry decision differs from the shared variant (a declined card, an idempotency conflict); server-supplied reason codes stay a field on that variant.

Implement mode ends with `Pre-existing: <file:line> - <defect>` for each defect in code the plan edits or depends on but does not fix, or `Pre-existing: none`. Code not yet written is cited as `<path> (new)`. A file the plan depends on that is absent or could not be read is listed as `Not read: <path> - <reason>`. A defect the change cannot ship on top of is fixed in the plan, not listed as `Pre-existing`.

When invoked from a review workflow, emit one finding block per defect:

```
### [Blocker | High | Medium | Low] lib/path/file.dart:LINE

- Code: {one-line citation}
- Defect: {Swallowed | Untyped | Unmapped | Leaked | Stack-Lost | Raw-Message | Boundary-Config | Error-Caught | Double-Wrapped | Incomplete-Failure | Cancellation-Surfaced | Provider-Retry | Duplicated-Mapping}
- Impact: {what the user sees, or what is lost from reporting}
- Fix: {concrete edit}
```

| Defect | Meaning |
|--------|---------|
| `Swallowed` | caught and discarded, or replaced by an empty/null value or a stored message with no report |
| `Untyped` | failures modelled as `Exception`/`String` instead of a sealed variant |
| `Unmapped` | a `switch` over failures, or a mapper over a foreign error enum, uses `default`/`_`, so new variants fall through |
| `Leaked` | a data-layer exception type is visible above the repository boundary |
| `Stack-Lost` | `throw e` inside `catch`, a conversion that drops the original stack, or a bare `catch (e)` that never captures the stack |
| `Raw-Message` | `e.toString()` or an untranslated string rendered to the user |
| `Boundary-Config` | app-level handlers misconfigured: split coverage (`runZonedGuarded` + `PlatformDispatcher.onError`), missing `FlutterError.onError`/`PlatformDispatcher.onError`, an `ErrorWidget.builder` that can throw |
| `Error-Caught` | an `Error` subtype caught for control flow outside untrusted-payload decoding |
| `Double-Wrapped` | `Result` returned into a Riverpod async provider |
| `Incomplete-Failure` | a failure type missing a stable variant, retryability, or cause and stack |
| `Cancellation-Surfaced` | cancellation shown to the user, reported as an error, or never modelled |
| `Provider-Retry` | Riverpod 3 `retry:` left at its default for non-retryable failures, or `ProviderException` not unwrapped before switching |
| `Duplicated-Mapping` | the same error mapping repeated across data sources instead of one mapper per source |

`Blocker` = failure invisible or app unable to report (Swallowed, Boundary-Config with no reporting path, an `ErrorWidget.builder` that can throw). `High` = wrong handling on a user-facing path (Leaked, Raw-Message, Unmapped, Cancellation-Surfaced, Error-Caught). `Medium` = degraded diagnostics or fragile typing (Stack-Lost, Untyped, Incomplete-Failure, Double-Wrapped, Boundary-Config that still reports - e.g. split coverage). `Medium` also covers Provider-Retry. `Low` = a finding whose only cost is readability (Duplicated-Mapping). When a finding matches two bands, the higher band wins. If there are no findings, emit exactly `No error-handling findings.` so the workflow knows the check ran.

Blocks are one per defect, ordered by severity, then file and line, then enum order. Each site of a repeated rule is its own defect; a single defect that needs edits in several places anchors on the line to edit and names the others as `also <file:line>` on its citation line.

A finding that depends on code outside the files read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to the line describing its effect. A check whose subject does not appear in the files read is clean; a check the files read cannot exercise is listed once as `Not checked: <names> - <reason>` and gets no clean or zero-finding line. A file in scope that could not be read is named on that line.

On a non-Riverpod stack (Bloc, Provider), a caught failure lands in the framework's error state as the typed failure, never as `e.toString()`; `Leaked` and `Raw-Message` apply unchanged. On `package:http`, the boundary maps `ClientException`, `SocketException`, `TimeoutException`, and non-2xx status codes into the sealed type.

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
