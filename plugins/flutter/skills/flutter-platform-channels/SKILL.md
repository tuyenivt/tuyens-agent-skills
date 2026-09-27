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
- Every call can fail three ways: `PlatformException` (native raised), `MissingPluginException` (no implementation on this platform), and never returning. Bound it with a timeout and handle all three
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
| Native pushes events over time (sensors, connectivity, playback position) | `EventChannel` | maps directly to a Dart `Stream`; send decoded results, not raw frames - pixels Dart must process go through a texture or FFI |
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

Wrap it: a value that fails the check maps to a typed bad-response failure, `on PlatformException` maps `e.code` to a typed failure, `on MissingPluginException` selects the fallback for platforms without an implementation, and `TimeoutException` covers a native side that never calls `result`. A dropped `result` callback is a permanently pending Dart future, which looks like a hung screen rather than an error.

### Untrusted in both directions

```kotlin
// Bad - a path that arrived from a deep link reaches the filesystem unchecked
val path = call.argument<String>("path")!!
result.success(File(path).readText())
```

```kotlin
// Good - presence, type, and domain checked before the argument reaches a sink
val path = call.argument<Any>("path") as? String   // argument<String> is an unchecked cast
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
// Bad - the subscription outlives the widget; native keeps the sensor running
_channel.receiveBroadcastStream().listen(_onEvent);

// Good - held, error-handled, cancelled in dispose
_sub = _channel.receiveBroadcastStream().listen(_onEvent, onError: _onError);
```

The native `onListen`/`onCancel` pair must actually start and stop the underlying resource. An `onCancel` that does not release the sensor, camera, or location updates is a battery drain no Dart-side fix can reach.

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
| Declare | `<uses-permission>` in `AndroidManifest.xml` | usage-description key in `Info.plist` |
| Request | runtime request for dangerous permissions | explicit authorization request (location, notifications, photos); camera and microphone prompt on first access |
| Refused for good | deep link to app settings | deep link to app settings |

macOS adds an entitlement (`com.apple.security.device.camera`, `...device.audio-input`) beside the usage string. With `permission_handler` on iOS, each permission also needs its `PERMISSION_*` macro in the Podfile, or the request returns denied. Every permission path handles granted, denied, and permanently denied - plus `limited`, `restricted`, and `provisional` where the platform has them; on iOS the first denial already reports permanently denied. A flow that handles only granted and denied strands the user with no way forward. Request at the point of need rather than at launch.

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
Direction: {Dart->native | native->Dart | bidirectional} - an FFI call is Dart->native
Payload Types: {<codec-supported types> | N/A (FFI: native types)}
Argument Validation: native {file:line | MISSING | N/A (existing plugin)} / Dart {file:line | MISSING}
Threading: {handler offloads to background | main-thread only (justified: <why>) | FFI on <ui|helper> isolate}
Failure Handling: {PlatformException -> <mapping>; MissingPluginException -> <fallback>; timeout <duration> | EventChannel: onError -> <mapping> | FFI: return codes -> <mapping>, native crash unguarded} | UNHANDLED: <which>
Lifecycle: Dart {subscription cancelled at file:line | N/A}; native {onCancel releases <resource> | N/A}
Platforms: {android | ios | macos | windows | linux | web} -> {implemented | unsupported: <observed behavior>}
Permissions: {<permission> declared at <file>, requested at file:line | none}
```

One block per channel - a capability pairing a MethodChannel with an EventChannel emits two. In implement mode, fill `unsupported:` with the designed fallback (e.g. `feature disabled on web`) rather than observed behavior. A permission shared by several blocks is written in full on the first and as `see <capability>` on the rest.

Implement mode ends with `Pre-existing: <file:line> - <defect>` for each defect in code the plan edits or depends on but does not fix, or `Pre-existing: none`. Code not yet written is cited as `<path> (new)`. A file the plan depends on that is absent or could not be read is listed as `Not read: <path> - <reason>`. A defect the change cannot ship on top of is fixed in the plan, not listed as `Pre-existing`.

When invoked from a review workflow or directly to diagnose a channel symptom (`MissingPluginException`, hung call, frozen UI), emit one finding block per issue:

```
### [Severity] file:line

- Rule: {mechanism-choice | argument-validation | codec-type | failure-handling | threading | subscription-lifecycle | ffi-memory | platform-coverage | permission-declaration | permission-outcomes | channel-in-widget | plugin-reinvention | naming}
- Code: {one-line citation}
- Problem: {what breaks at runtime, on which platform}
- Recommendation: {concrete edit}
```

`Severity: {Critical | High | Medium | Low}`. Critical = an unvalidated argument reaching a native sink, a native path that can crash the process (including a missing iOS usage description on a capability the app accesses), or a leaked subscription holding the camera, microphone, or location. High = a hang or crash under realistic use (no timeout, unhandled MissingPluginException on a shipped platform, blocking main-thread work, unchecked casts, a non-codec value sent over a channel, a runtime permission requested without its Android `<uses-permission>`), or a leaked subscription holding any other native resource (sensors, receivers). Native memory leaked on every call is High; leaked on an error path only is Medium. Medium = fragile but working (hand-rolled channel where Pigeon or a plugin fits, missing permission outcome handling, a widget or notifier holding a channel). Low = naming, channel-string placement. When a finding matches two bands, the higher band wins.

If there are no findings, emit exactly `No platform-channel findings.` so the workflow knows the check ran.

Blocks are one per defect, ordered by severity, then file and line, then enum order. Each site of a repeated rule is its own defect; a single defect that needs edits in several places anchors on the line to edit and names the others as `also <file:line>` on its citation line.

A finding that depends on code outside the files read is still emitted at the severity it would have if confirmed, with `(unconfirmed: depends on <path>)` appended to the line describing its effect. A check whose subject does not appear in the files read is clean; a check the files read cannot exercise is listed once as `Not checked: <names> - <reason>` and gets no clean or zero-finding line. A file in scope that could not be read is named on that line.

In diagnose mode, blocks for defects that cause the reported symptoms come first, in the order the symptoms were reported; every other defect seen in the files read follows at its own severity.

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
