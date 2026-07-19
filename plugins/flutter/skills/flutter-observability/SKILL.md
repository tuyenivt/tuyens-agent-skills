---
name: flutter-observability
description: "Instrument a Flutter app: crash reporting, error-surface coverage, symbol upload, analytics events, performance traces, logging, consent gating."
metadata:
  category: mobile
  tags: [flutter, dart, crashlytics, sentry, analytics, logging, performance, privacy]
user-invocable: false
---

# Flutter Observability

> Load `Use skill: stack-detect` first. This skill owns what the app reports and how that report reaches a console you can read. Failure typing and handler wiring live in `flutter-error-handling`; retry/offline behaviour in `flutter-reliability`; frame and startup optimisation in `flutter-performance`.

A device is not a scraped service. Nothing pulls metrics off a phone: the app **pushes** events over a link that is often absent, from a build the user may never update, on hardware you cannot log into. Every gap in instrumentation is permanent - the crash that was not reported is gone.

## When to Use

- Adding or reviewing crash reporting, analytics, or performance monitoring
- Checking that every error surface reaches the reporter, and that reports arrive symbolicated
- Designing analytics event names, parameters, and user properties
- Reviewing logging, PII exposure, or consent gating before a release

## Rules

- All four error surfaces are covered: framework errors, uncaught async errors, zone-scoped errors, and isolate errors. Each missing surface hides an entire class of crash (see the table below).
- Exactly one owner reports uncaught async errors. When an SDK runs your app inside its own zone, do not also install a hand-rolled handler that reports the same error.
- A release built with `--obfuscate --split-debug-info=<dir>` produces stack traces that are unreadable until that build's symbols are uploaded. Symbol upload belongs in CI, on the same job that produces the artifact - never a manual step.
- Every report carries build attribution: version, build number, flavor, and platform. A crash that cannot be tied to a release cannot be triaged.
- Reports carry breadcrumbs and custom keys set before the crash, not after. Attach the screen, the feature flag state, and a non-identifying user key.
- `print` is not logging. Use a logging facade that fans out to console in debug and to the reporter's breadcrumb API in release.
- No PII in event names, event parameters, custom keys, breadcrumbs, or log lines - including anything derived from an email, phone number, address, or free-text field the user typed.
- Collection is off until consent is granted where consent is required, and the toggle is checked at startup before the first event, not after.
- Analytics events use a fixed, documented vocabulary defined in one Dart file. No string literals at call sites and no interpolated event names.
- Sampling and verbosity are configuration, not code branches on `kReleaseMode` scattered through features.

## Patterns

### Error-surface coverage

| Surface | Catches | Blind spot if missing |
|---------|---------|-----------------------|
| `FlutterError.onError` | errors thrown inside framework callbacks - `build`, layout, paint, gesture handlers | every widget-lifecycle crash, including the red screen the user actually saw |
| `PlatformDispatcher.instance.onError` | uncaught errors from async work in the root zone | unawaited futures, stream `onData` throws, timer callbacks |
| A guarded zone (`runZonedGuarded`, or an SDK's `appRunner` argument) | errors raised inside that zone | required when an SDK owns the zone; without it that SDK sees nothing |
| `Isolate.current.addErrorListener` | errors on a spawned isolate | anything under `compute()` or a background task entry point |

Native crashes (Android ANRs, iOS signal crashes, plugin native code) are caught by the reporter's native layer, not by any Dart handler - which is why the native SDK must be initialised even in an app that is Dart-only in practice.

The handler bodies themselves are wired in `flutter-error-handling`; this skill's concern is that all four are present and that the reporter is initialised before `runApp`, so a crash during startup is still captured.

### Symbolication is part of the build

```yaml
# Bad - obfuscated release, no symbol step: every crash reports as anonymous frames
- run: flutter build appbundle --release --obfuscate --split-debug-info=build/symbols

# Good - symbols uploaded from the same job that produced the artifact
- run: flutter build appbundle --release --obfuscate --split-debug-info=build/symbols
- run: firebase crashlytics:symbols:upload --app=$FIREBASE_APP_ID build/symbols
```

Dart symbols are per-build: a rebuild with the same version produces different mappings, so uploading from a developer laptop later does not fix the traces already collected. Android R8/ProGuard mapping files and iOS dSYMs are a **separate** upload path covering native frames - a Flutter app needs both, and the Crashlytics Gradle plugin handles the Android mapping only if its upload flag is left enabled. Sentry's equivalent is a build-time plugin step (`sentry_dart_plugin`) or a `sentry-cli` invocation pointed at the same `--split-debug-info` directory; confirm the exact task name against the version in `pubspec.yaml`.

### Analytics event vocabulary

```dart
// Bad - name built at the call site; the console fills with unqueryable variants
analytics.logEvent(name: 'checkout_$step_completed', parameters: {'user': user.email});

// Good - closed vocabulary, no PII, typed wrapper
abstract final class Ev {
  static const checkoutStepCompleted = 'checkout_step_completed';
}
analytics.logEvent(name: Ev.checkoutStepCompleted, parameters: {'step': 'payment'});
```

The variable goes in a parameter, never in the name: a funnel cannot be built across event names that differ per user. GA4 caps apply and are silently enforced - event and parameter names are length-limited and must be alphanumeric with underscores, string parameter values are truncated, reserved prefixes are rejected, and an app has a bounded number of *distinct* event names before new ones are dropped. Check the current limits in the Firebase docs rather than guessing; the failure mode is silent, so validate in DebugView before shipping.

Screen views come from a navigator observer wired into `MaterialApp`, not from `logEvent` calls sprinkled in `initState`.

### Performance monitoring

Automatic instrumentation covers app start and screen rendering (slow and frozen frames). Network calls are **not** automatically traced for Dart HTTP traffic - Flutter requests bypass the native interception the SDK relies on, so per-request timing needs an explicit metric recorded from a Dio interceptor, or the tracing integration the SDK ships for your HTTP client.

Custom traces mark the work a user waits on, not the work that is easy to measure:

```dart
// Bad - traces the HTTP call the user never sees in isolation
final t = perf.newTrace('api_get_orders')..start();

// Good - traces the interaction boundary, with a metric that explains the outcome
final t = perf.newTrace('orders_screen_ready')..start();
final orders = await repo.load();
t.putAttribute('source', fromCache ? 'cache' : 'network');
t.setMetric('count', orders.length);
await t.stop();
```

Attributes are low-cardinality dimensions you slice by; metrics are counters. Neither takes an identifier. For raw frame timings, `SchedulerBinding.instance.addTimingsCallback` gives per-frame durations in release builds - aggregate them into a percentile before sending, never one event per frame.

### Logging that survives release

```dart
// Bad - goes to logcat/oslog on the user's device, where you cannot read it,
// but anyone with a cable can
print('login ok for ${user.email} token=$token');

// Good - one facade: console in debug, breadcrumbs in release, no PII
log.info('login.success', {'method': 'oauth', 'userKey': user.pseudonymousId});
```

`print` output in a release build is not discarded - it is written to the platform log, which makes it a leak channel and still leaves you with nothing, because you have no access to that device. `debugPrint` only adds rate limiting to avoid Android dropping lines; it is a debug tool, not an alternative. Use `dart:developer`'s `log` or the `logging` package behind a single facade, and route release output into the reporter's breadcrumb API so the last N lines arrive attached to the next crash.

### Attribution and consent

Set build attribution and a stable pseudonymous key once at startup, before the first event can fire. Version and build number come from the package metadata (`package_info_plus`), not a hardcoded constant that drifts from the real build.

Consent gates collection at the source. Initialise with collection disabled, enable only after the user opts in, and persist the decision:

```dart
// Bad - events fire during the consent prompt itself
await analytics.logEvent(name: Ev.appOpened);
final granted = await showConsentSheet();

// Good - collection stays off until the answer is known
await analytics.setAnalyticsCollectionEnabled(false);
await crashlytics.setCrashlyticsCollectionEnabled(false);
final granted = await consentStore.readOrPrompt();
if (granted) { /* enable both, then log */ }
```

On iOS, tracking that reaches an advertising identifier additionally requires the App Tracking Transparency prompt, and it must not be shown before the app has been foreground-ready or the system suppresses it. Both stores require a declared data-collection manifest; a report field you add in Dart without updating that declaration is a compliance defect, not just a privacy one.

### Platform tiers

Mobile is the default assumption. On **desktop**, crash-reporter native layers vary by SDK and may cover Dart frames only - verify rather than assume. On **web**, there is no native crash layer at all, symbolication uses source maps instead of Dart symbol files, and any identifier you set is subject to browser storage rules.

## Output Format

When invoked from an implementation workflow, emit the instrumentation contract:

```
Reporter: {Crashlytics | Sentry | both (justify) | none}
Init Site: {file:line, before runApp | after runApp (defect) | none}
Error Surfaces: {framework=<Y|N> asyncRoot=<Y|N> zone=<Y|N|N/A> isolate=<Y|N>}
Symbols: {uploaded in CI at <job> | manual | NOT UPLOADED (obfuscated build)}
Native Symbols: {mapping=<Y|N> dSYM=<Y|N> | N/A}
Attribution: {version+build+flavor at file:line | PARTIAL: <missing> | none}
Analytics: {vocabulary at file:line | literals at call sites | none}
Screen Views: {navigator observer | manual calls | none}
Performance: {auto only | auto + <n> custom traces | none}
Logging: {facade at file:line | print/debugPrint | mixed}
Consent: {default-off + gated at file:line | default-on | none}
```

When invoked from a review workflow, emit one block per finding:

```
### [Blocker | High | Medium | Low] lib/path/file.dart:LINE

- Evidence: {one-line citation, or the missing wiring and where it belongs}
- Gap: {Blind-Spot | Unsymbolicated | Unattributed | PII-Leak | Unconsented | Untyped-Event | Noise}
- Invisible: {what an on-call engineer cannot see because of this}
- Fix: {concrete edit}
```

| Gap | Meaning |
|-----|---------|
| `Blind-Spot` | an error surface, screen, or user-waited path emits nothing |
| `Unsymbolicated` | obfuscated build whose symbols are not uploaded from CI |
| `Unattributed` | reports cannot be tied to a version, build, flavor, or session |
| `PII-Leak` | identifiers or user-entered text in events, keys, breadcrumbs, or logs |
| `Unconsented` | collection active before consent, or no persisted decision |
| `Untyped-Event` | event name built at the call site or duplicated as a literal |
| `Noise` | per-frame, per-item, or unsampled high-volume events |

Severity: `Blocker` = a crash class is entirely invisible in production, or PII is shipped off-device. `High` = reports arrive but are unreadable or unattributable. `Medium` = a significant path is uninstrumented. `Low` = naming, cardinality, or verbosity.

## Avoid

- Shipping an obfuscated release without a CI symbol-upload step
- Initialising the reporter after `runApp`, so startup crashes are lost
- Covering framework errors only, and calling crash reporting done
- Two reporters both hooked to the same surfaces, doubling every crash count
- `print` or `debugPrint` as the release logging strategy
- Emails, phone numbers, raw user IDs, tokens, or free-text input in any event, key, or breadcrumb
- Event names containing a variable, a screen index, or an item id
- Enabling collection before the consent answer exists, or prompting for ATT at launch
- A custom trace around a call the user never waits on, or one trace per list item
- Frame-level or per-request events sent unsampled from every device
- Backend framing: no scrape endpoint, no pull-based metrics, no RED dashboard on the device - the app pushes to a backend that owns those
