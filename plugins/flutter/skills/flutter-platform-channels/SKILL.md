---
name: flutter-platform-channels
description: "Bridge Dart to native with MethodChannel, EventChannel, Pigeon, and FFI: plugin packages, permissions, threading, argument validation."
metadata:
  category: mobile
  tags: [flutter, dart, platform-channel, pigeon, ffi, plugin, permissions, native]
user-invocable: false
---

# Flutter Platform Channels

> Platform-tier sensitive: mobile is the default target, desktop support varies per plugin, and **web has no native host** - a channel call on web reaches only a Dart web-plugin implementation, if one is registered.

The channel is a trust and failure boundary, not a function call. Everything crossing it is asynchronous, weakly typed, and untrusted in both directions.

## When to Use

- Calling a native API Flutter does not expose, or consuming a stream of native events
- Choosing between an existing plugin, `MethodChannel`, Pigeon, and FFI
- Building or reviewing a plugin package: federated structure, platform registration, test doubles
- Requesting and handling runtime permissions
- Diagnosing `MissingPluginException`, `PlatformException`, a call that never returns, or UI freezing while native work runs

## Rules

- Search pub.dev before writing a channel. A maintained plugin already carries the per-platform implementations, the permission plumbing, and the edge cases you have not hit yet
- Pick the mechanism from the shape of the call (table below), not from familiarity
- Prefer Pigeon over hand-written `MethodChannel` beyond a couple of methods: string method names and untyped maps are exactly the failure mode it removes
- **Arguments crossing the boundary are untrusted in both directions.** Dart -> native arguments frequently originate in deep links, WebViews, or server responses; native -> Dart return values are dynamic and cast at runtime. Validate on the receiving side, on both sides
- Only codec-supported types cross: null, bool, int, double, String, byte and typed-number lists, List, Map. Encode anything else explicitly - there is no object graph transfer
- Every call can fail three ways: `PlatformException` (native raised), a missing implementation on this platform (`MissingPluginException` from a `MethodChannel`; `PlatformException(code: 'channel-error')` from a Pigeon client; an `EventChannel` that never emits, because the framework swallows its activation failure), and never returning. Bound it with a timeout (omitted only where the user drives the native UI, a picker) and handle all three
- Channel calls are wrapped by a repository or service; widgets and notifiers never hold a channel
- Native handlers run on the platform's main/UI thread. Long work moves to a background thread and replies on the main thread - a blocking handler freezes the native UI and stalls the Dart future
- Calling a channel from a background isolate requires initializing the messenger with the root isolate token; the default binary messenger is only wired on the root isolate
- Permissions are **declared** (Android manifest entry, iOS `Info.plist` usage-description string), and those the Permissions table marks runtime are **requested at runtime**. A missing iOS usage string crashes on first access and fails store review

## Patterns

### Mechanism selection

| Need | Mechanism | Why |
| --- | --- | --- |
| A few native calls, request/response | `MethodChannel` | lowest setup cost |
| More than a couple of methods, or a signature that will evolve | **Pigeon** | generates typed Dart + Kotlin/Swift; a signature change breaks the build instead of a user's device |
| Native pushes events over time (sensors, connectivity, playback position) | `EventChannel` | maps directly to a Dart `Stream`; send decoded results, not raw frames - frames for display go through a `Texture`, and pixels Dart must process go through FFI |
| Existing C/C++ library, or per-call overhead matters | **FFI** (`dart:ffi` + `ffigen`) | direct call, no serialization, no message hop |
| Capability reused across apps, or needing third-party platform impls | plugin package (federated) | per-platform packages behind one interface |
| Web | JS interop (`dart:js_interop`, `package:web`) | there is no native host to receive a channel message |

### Three failure modes, not one

```dart
// Bad - the cast, a native error, and an unimplemented platform all reach the widget as raw crashes
final level = await _channel.invokeMethod('getBatteryLevel') as int;

// Good - bounded, and the result is checked before it is trusted; the catch below maps failures
final raw = await _channel
    .invokeMethod<Object?>('getBatteryLevel')
    .timeout(const Duration(seconds: 5));
final level = switch (raw) {
  int v when v >= 0 && v <= 100 => v,
  _ => throw FormatException('battery level: $raw'),
};
```

Wrap it: a value that fails the check maps to a typed bad-response failure, `on PlatformException` maps `e.code` to a typed failure, `on MissingPluginException` (or Pigeon's `channel-error` code) selects the fallback for platforms without an implementation, and `TimeoutException` covers a native side that never calls `result`. A dropped `result` callback is a permanently pending Dart future, which looks like a hung screen rather than an error.

### Untrusted in both directions

```kotlin
// Bad - a path that arrived from a deep link reaches the filesystem unchecked
val path = call.argument<String>("path")!!
result.success(File(path).readText())
```

```kotlin
// Good - presence, type, and domain checked before the argument reaches a sink
val path = call.argument<Any>("path") as? String   // argument<String> would throw ClassCastException and reply a generic error; this replies BAD_ARG
    ?: return@setMethodCallHandler result.error("BAD_ARG", "path required", null)
if (!isInsideAppSandbox(path)) return@setMethodCallHandler result.error("BAD_ARG", "path not allowed", null)
```

The native side is the last check before a real sink (filesystem, intent, SQL, shell, WebView, keychain), and Dart-side validation does not survive a repackaged app. In the other direction, treat a return value as unvalidated input: `invokeMethod<T>` still casts at runtime, so a native-side type change throws `TypeError` either way. Request `Object?` and pattern-match on the value and its elements, then null-check and range-check before use; `invokeMapMethod`/`invokeListMethod` return lazily cast views that fail later, at the access site.

### Pigeon

```dart
// pigeons/messages.dart - the source of truth, not compiled into the app
@HostApi()
abstract class BatteryApi {
  int getLevel();
}
```

Running pigeon generates the Dart client plus a Kotlin/Swift protocol to implement natively; `@FlutterApi()` generates the reverse direction. Renaming a method now fails the native build. Treat generated output like all other codegen in the project - committed or CI-generated, consistently, never hand-edited.

### EventChannel lifecycle

```dart
// Bad - in a State: the subscription outlives the widget; native keeps the sensor running
_channel.receiveBroadcastStream().listen(_onEvent);

// Good - in the repository that owns the channel: held, error-handled, released with its owner
_sub = _channel.receiveBroadcastStream().listen(_onEvent, onError: _onError);
void dispose() => _sub?.cancel();   // called from ref.onDispose or the owner's teardown
```

The native `onListen`/`onCancel` pair must actually start and stop the underlying resource. An `onCancel` that does not release the sensor, camera, or location updates is a battery drain no Dart-side fix can reach. A missing native implementation never reaches `onError`: the framework reports the activation failure and the stream stays silent, so a platform without a handler is caught by `platform-coverage`, not by this listener.

### FFI

```dart
// Bad - a long synchronous native call on the UI isolate; the app freezes, no frames
final result = _bindings.compressImage(ptr, len);

// Good - the blocking call runs off the UI isolate; a Pointer is not sendable, so pass its address
final address = ptr.address;
final result = await Isolate.run(
    () => bindings.compressImage(Pointer<Uint8>.fromAddress(address), len)); // bindings is top-level
```

FFI has no exception boundary: a native crash takes the process down, unsymbolicated. Memory is yours - pointers allocated through `package:ffi` are not garbage collected and must be freed on every path including error paths. Bundling the native library is per-platform build configuration (podspec, Gradle/CMake, a library beside the desktop executable) or a Dart build hook (native assets) on SDKs that support it, so it is part of the change, not an afterthought.

### Plugin packages

- The `flutter: plugin: platforms:` block in `pubspec.yaml` declares which platforms have an implementation and the native entry class for each. A platform absent there throws `MissingPluginException` at runtime, not compile time
- Federated split (app-facing package -> platform interface -> per-platform implementations) is worth it when platforms ship on separate cadences or third parties add implementations. A single-team, single-package plugin is simpler and legitimate
- Tests substitute the platform interface, not the channel. The `example/` app is the real integration harness

### Permissions

| Step | Android | iOS |
| --- | --- | --- |
| Declare | `<uses-permission>` in `AndroidManifest.xml` (`POST_NOTIFICATIONS` on API 33+) | usage-description key in `Info.plist`; push needs the Push Notifications capability (`aps-environment`), not a usage string |
| Request | runtime request for dangerous permissions | explicit authorization request (location, notifications); camera, microphone, and photos prompt on first access |
| Refused for good | deep link to app settings | deep link to app settings |

macOS adds an entitlement (`com.apple.security.device.camera`, `...device.audio-input`) beside the usage string. With `permission_handler` on iOS, each permission also needs its `PERMISSION_*` macro in the Podfile, or the request returns denied. Every permission path handles granted, denied, and permanently denied - plus `limited`, `restricted`, and `provisional` where the platform has them; on iOS the first denial already reports permanently denied. A flow that handles only granted and denied strands the user with no way forward. Request at the point of need rather than at launch. The system photo picker needs no media permission (`image_picker` on every supported Android, iOS 14+); `CAMERA` is declared only when the app owns the camera session.

### Platform tiers

- **Mobile:** full support; the default assumption
- **Desktop:** channels and FFI work, but a given pub.dev package may declare no `windows`/`macos`/`linux` implementation. Check the plugin's declared platforms before designing around it; a missing one is a runtime `MissingPluginException`. For an app-level channel, coverage is wherever a handler is registered in each runner (`MainActivity`, `AppDelegate`, `MainFlutterWindow`); a runner without one throws the same exception
- **Web:** no native host and no `dart:ffi`. Web support means a Dart implementation of the platform interface written against JS interop. Guard entry points with `kIsWeb` and provide a fallback or an explicitly disabled state rather than letting the exception surface

## Output Format

When invoked from an implementation workflow:

```
Capability: {<native capability>}

Mechanism: {MethodChannel | EventChannel | Pigeon | FFI | federated plugin package | JS interop | existing plugin: <name>}

Channel Name: {<reverse-dns>/<feature> | N/A}

Direction: {Dart->native | native->Dart | bidirectional | N/A (existing plugin)}

Payload Types: {<codec-supported types> | N/A (FFI: native types) | N/A (existing plugin | JS interop)}

Argument Validation: native {file:line | MISSING | N/A (existing plugin | JS interop)} / Dart {file:line | MISSING}

Threading: {handler offloads to background | main-thread only (justified: <why>) | FFI on <ui|helper> isolate | N/A (existing plugin | JS interop)}

Failure Handling: {PlatformException -> <mapping>; missing implementation -> <fallback>; timeout <duration> | EventChannel: onError -> <mapping>; silent stream -> <fallback> | FFI: return codes -> <mapping>, native crash unguarded | existing plugin: <exceptions> -> <mapping>; <fallback> | UNHANDLED: <which>}

Lifecycle: Dart {subscription cancelled at file:line | N/A}; native {onCancel releases <resource> | N/A}

Platforms: {android | ios | macos | windows | linux | web} -> {implemented | unsupported: <observed behavior>}

Permissions: {<permission> declared at <file>, requested at file:line | <permission> declared at <file>, prompts on first access | see <capability> | none}
```

One block per channel, or per capability when the mechanism is an existing plugin or JS interop - a capability pairing a MethodChannel with an EventChannel emits two. An FFI call is `Dart->native`. In implement mode, fill `unsupported:` with the designed fallback (`feature disabled on web`, `gallery only on macOS: the plugin has no camera source there`) rather than observed behavior; a plugin's returned value is Dart-side input, and its check is the Dart `Argument Validation` entry. A permission shared by several blocks is written in full on the first and as `see <capability>` on the rest; several platforms on the `Permissions` or `Platforms` line are `;`-separated. A timeout is omitted where the user drives the native UI (a picker).

```
Fixed in plan: {<file:line> - <defect> | none}

Pre-existing: {<file:line> - <defect> | none}

Not read: {<path> - <reason> | none}
```

Implement mode describes the state after the plan and ends with these lines, each on its own line with a blank line between: `Fixed in plan: <file:line> - <defect>` per defect in existing code the plan corrects, or `Fixed in plan: none`; `Pre-existing: <file:line> - <defect>` per defect left in place, or `Pre-existing: none`; `Not read: <path> - <reason>` per file the plan needs that is absent, could not be read, or was not read, or `Not read: none`. A defect is fixed in the plan when it sits in code the change edits, or when the new code would misbehave on first run on top of it; every other defect in code the new code calls or reads is `Pre-existing`; code the new code neither edits, calls, nor reads is not listed, except a defect that breaks the build, which is always `Fixed in plan`. Code not yet written is cited as `<path> (new)`.

When invoked from a review workflow or directly to diagnose a channel symptom (`MissingPluginException`, hung call, frozen UI), emit one finding block per issue:

```
### [{Critical | High | Medium | Low}] {file:line}

- Rule: {mechanism-choice | argument-validation | codec-type | failure-handling | threading | subscription-lifecycle | ffi-memory | platform-coverage | permission-declaration | permission-outcomes | channel-in-widget | plugin-reinvention | naming}
- Code: {one-line citation}
- Problem: {what breaks at runtime, on which platform}
- Recommendation: {concrete edit}
```

The heading severity is one of Critical, High, Medium, Low. Critical = an unvalidated argument reaching a native sink, a native path that can crash the process (including a missing iOS usage description on a capability the app accesses), or a leaked subscription holding the camera, microphone, or location. High = a hang or crash under realistic use (no timeout, unhandled MissingPluginException on a shipped platform, blocking main-thread work, unchecked casts, a non-codec value sent over a channel, a runtime permission requested without its Android `<uses-permission>`), or a leaked subscription holding any other native resource (sensors, receivers). Native memory leaked on every call is High; leaked on an error path only is Medium. Medium = fragile but working (hand-rolled channel where Pigeon or a plugin fits, missing permission outcome handling, a widget or notifier holding a channel). Low = `naming` (names, channel-string placement). When a finding matches two bands, the higher band wins. A dangerous Android permission, or an iOS explicit-authorization permission, declared but never requested at runtime is High under `permission-declaration` (the feature fails silently, or throws on Android's dangerous-permission APIs); a shipped platform with no handler is `platform-coverage`, High; a missing iOS usage string is Critical only on a platform with a handler, otherwise part of the `platform-coverage` finding; a missing macOS entitlement is `permission-declaration`; a native handler that never calls `result` is `failure-handling`; an unchecked cast on a returned value is `argument-validation`. A platform-wide absence anchors on the runner entry file (`AppDelegate.swift`, `MainFlutterWindow.swift`, `web/index.html`) or `<path> (missing)`, and its `Code:` cites the Dart call that fails; the absence is `platform-coverage` and the unhandled exception at the call site is `failure-handling` - two blocks.



Blocks are one per defect, ordered by severity, then file path (repository-relative, byte order), then line, then enum order. A defect is one rule at one fix site: the same rule broken at N sites that each need their own edit is N blocks; the same rule broken at N sites that one edit fixes (a declaration, a shared helper, a config key) is one block anchored on the line to edit, naming the other sites as `also <file:line>` on its citation line (the block's `Code:` line); one line breaking two rules with two different fixes is two blocks, with one fix it is one block under the rule naming the worse failure (on a tie, the earlier enum value).

Review output is, in order: any opening lines this skill defines, the finding blocks, one `Also seen: <file:line> - <defect> (owner: <skill>)` line per defect in the files read that no value of this skill's enum covers - one per line, blank-separated, in file order (no block, no severity; the owner is whichever of dart-language-patterns, flutter-widget-patterns, flutter-riverpod-patterns, flutter-navigation-patterns, flutter-networking, flutter-data-persistence, flutter-local-db-migration, flutter-adaptive-responsive, flutter-accessibility, flutter-i18n, flutter-performance, flutter-security-patterns, flutter-error-handling, flutter-testing-patterns, flutter-build-release, flutter-overengineering-review covers it, or `unowned`), one `Not checked: <names> - <reason>` line (names are this skill's `Rule` values, or the path of a file that could not be read) when any check could not be exercised, then `No platform-channel findings.` when there are no blocks. A check is `Not checked` when the files read reference its subject but the code that decides it was not read (an imported file, a test or platform directory, release history); a check whose subject nothing in the files read references is clean; the sentinel is emitted only when there are no blocks, `Not checked` lines or not. A check with a finding is never `Not checked`. A file in scope that could not be read is its own `Not checked` entry, `<path> - not readable`; when the file that decides a finding is unknown, `<path>` in the unconfirmed suffix reads `unknown file`. A finding whose confirmation lies in a file not read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to its `Problem:` line, and does not move its check to `Not checked`. Invoked directly, a request to write or change code takes the implement shape, a request to review or audit takes the review shape, and a supplied symptom or bug report takes diagnose mode.

The closing lines - `Also seen` and `Not checked` only when they have content, the sentinel only when there are no blocks:

```
Also seen: {<file:line> - <defect> (owner: <skill>)}

Not checked: {<names> - <reason>}

No platform-channel findings.
```

Diagnose mode opens with one line per reported symptom, `Symptom <n>: <the report's title or first sentence>`, a title that lists two symptoms is two lines, naming on each any premise the files read contradict (a flag the report says is on, a version it names) - the diagnosis then proceeds on what the code shows - and stating when the files read cannot cause the symptom. Blocks for the causes of the reported symptoms come first, grouped by symptom in reported order and within a group by severity, each such block's `Problem:` line opening with `Symptom <n>:`; a cause shared by two symptoms is one block opening `Symptom 1, 2:`, placed with the lower-numbered symptom; every other defect seen in the files read follows, ordered as in review mode. The sentinel is omitted in diagnose mode; `Also seen` and `Not checked` lines are kept.

## Avoid

- Hand-rolling a channel for something a maintained plugin already does
- Trusting arguments in either direction, or validating only on the Dart side
- `as T` or `invokeMethod<T>` trusted as validation - request `Object?` and check the value
- Calls with no timeout - a native side that never calls `result` produces a permanently pending future
- Catching only `PlatformException` and letting `MissingPluginException` crash the platform that lacks an implementation
- Passing arbitrary objects and expecting the codec to carry them
- Long-running work on the platform main thread, or a blocking FFI call on the UI isolate
- `receiveBroadcastStream().listen(...)` with no cancellation, or a native `onCancel` that does not release the resource
- Allocating native memory without freeing it on every path, error paths included
- Declaring platform support the plugin does not implement
- A dangerous Android permission, or an iOS permission that needs explicit authorization, declared without a runtime request; or a runtime request with no declaration
- Treating a permanently-denied permission as a dead end with no route to app settings
- Assuming a native host exists on web, or that a mobile plugin has desktop implementations
