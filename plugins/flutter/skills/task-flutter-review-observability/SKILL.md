---
name: task-flutter-review-observability
description: Flutter observability review - crash reporting, error-handler set, symbol upload, analytics events, performance traces, logging, consent, PII.
agent: flutter-observability-engineer
metadata:
  category: mobile
  tags: [flutter, dart, observability, crashlytics, sentry, analytics, logging, privacy, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Flutter Observability Review

Client-side observability review: crash reporting and its native layer, the uncaught-error handler set, symbol and debug-info upload, build attribution, analytics event design, performance traces, on-device logging, and consent/PII gating.

**A device is not a scraped service.** Nothing pulls metrics off a phone. The app pushes to a backend that owns dashboards, alert rules, and service SLOs. Do not review for RED metrics, scrape endpoints, exporters, or distributed-trace spans - those belong to the owning service's plugin. What is reviewable here is what the app emits, whether it can leave the device, and whether it is readable when it arrives.

Stack-specific delegate of `task-code-review-observability` for Flutter.

## When to Use

- Flutter PR touching the app entry point, crash-reporter init, error handlers, logging, or analytics
- Pre-release check that a build's crashes will be visible and symbolicated
- Post-incident review when a client-side failure was invisible or unreadable
- Adopting Crashlytics / Sentry, an analytics SDK, or a logging facade

**Not for:** general review (`task-flutter-review`), frame cost and startup time (`task-flutter-review-perf`), failure survival (`task-flutter-review-reliability`), secure storage and pinning (`task-flutter-review-security`), an active incident (`/task-oncall-start` - mitigate first), backend dashboards and alert routing.

## Seam With Adjacent Lenses

- **vs. Reliability:** this lens owns whether the failure was *seen*; reliability owns whether the app *survived* it. A retry with no log line is obs; a call with no timeout is reliability.
- **vs. Security:** a token in a log line, a crash payload, or an analytics parameter is a finding here as a PII/secret leak in the emitted signal. Storage hardening and transport security route to `task-flutter-review-security`.
- **vs. Perf:** perf owns making the frame cheaper; this lens owns whether the slow path emits a trace at all.

## Depth

| Depth      | What runs                                                             |
| ---------- | --------------------------------------------------------------------- |
| `standard` | All steps                                                             |
| `deep`     | All steps + per-journey signal coverage suggestions                   |

Default: `standard`. Request deep by appending `deep` to the invocation. At `deep`, name each critical user journey (launch, auth, purchase, sync) and state which signal would reveal it failing on a user's device; emit these under `Recommendations`, not as findings.

## Generated Code

Exclude from findings: `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, and generated localization output. When a generated file changed, cite the source that produces it. A diff of only generated files is a no-op - say so rather than manufacturing findings.

## Invocation

| Form | Meaning |
|------|---------|
| `/task-flutter-review-observability` | Current branch vs base; fails fast on trunk |
| `/task-flutter-review-observability <branch>` | `<branch>` vs base (3-dot) |
| `/task-flutter-review-observability pr-<N>` | PR head fetched into local branch (user runs fetch) |

When invoked as a subagent (e.g. by `task-flutter-review`), the parent passes the pre-confirmed stack and project shape, the precondition handle, the pre-read diff and commit log, the depth level, and the generated-file exclusion list. Steps 2-3 consume those instead of re-running, and Step 12 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Load Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation when invoked as a subagent.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept a pre-confirmed stack from the parent and skip detection. If not Flutter, stop and route the user to `/task-code-review-observability`.

Record: crash reporter (Crashlytics / Sentry / both / none), analytics SDK, logging package, state management, and platform targets present.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Read `git diff <base>...<head>` and `git log <base>..<head>` once and reuse. Skip when running as a subagent with the handle and artifacts pre-passed. Surface any fail-fast verbatim.

Capture for the report checkpoint: `current_head_sha = git rev-parse <head_ref>`, `current_base_sha = git rev-parse <base_ref>`.

### Step 4 - Read the Instrumentation Surface

Use skill: `flutter-observability` - it owns the canonical patterns for every step below. Its finding blocks are input to this workflow; emit findings in **this** skill's Output Format. Use skill: `ops-observability` for the cross-cutting presence check.

**Most important output:** a one-line verdict per surface (`wired | partial | absent`) in the Surface Map. A missing wire is itself the finding.

**Grouping rule.** When a whole surface is `absent`, produce a **single High-Impact finding** for that surface listing the missing pieces grouped by file. Per-callsite findings only when the surface exists and a specific callsite misuses it.

Open the files that configure observability so findings cite real lines:

- `lib/main.dart` and any bootstrap / `AppRunner` file - reporter init, handler assignment, `runApp` call site
- Reporter and analytics wiring, the logging facade, and the constants file holding event names
- CI workflow files and `android/app/build.gradle`(`.kts`) - build flags, symbol-upload steps, mapping-file upload
- `pubspec.yaml` - reporter, analytics, performance, logging, and `package_info_plus` dependencies
- Every changed file that calls `print` / `debugPrint`, logs, or emits an analytics event

### Step 5 - The Error-Handler Set

**Highest-value check in this review.** Each handler covers a different class of error; a missing one hides that whole class permanently. Verify all of them are assigned **before** `runApp`, so a startup crash is still captured.

| Handler | Catches | Blind spot if missing |
|---------|---------|-----------------------|
| `FlutterError.onError` | throws inside framework callbacks - `build`, layout, paint, gesture handlers | every widget-lifecycle crash, including the red screen the user saw |
| `PlatformDispatcher.instance.onError` | uncaught async errors in the root zone | unawaited futures, stream `onData` throws, timer callbacks |
| A guarded zone (`runZonedGuarded`, or the SDK's `appRunner` argument) | errors raised inside that zone | required when an SDK owns the zone; without it that SDK sees nothing |
| `Isolate.current.addErrorListener` | errors on a spawned isolate | anything under `compute()` or a background entry point |

- [ ] **Reporter initialized before `runApp`** - init after `runApp` loses startup crashes, which are the ones users cannot work around.
- [ ] **Exactly one owner per surface** - when an SDK's `appRunner` already wraps the app, a hand-rolled `runZonedGuarded` reporting the same error doubles every crash count and corrupts trend data. Pick one.
- [ ] **`PlatformDispatcher.instance.onError` returns `true`** when it has handled the error; returning `false` lets it reach the platform.
- [ ] **Native layer initialized** - Android ANRs, iOS signal crashes, and plugin native code are caught by the reporter's native layer, never by a Dart handler. A Dart-only setup misses them.
- [ ] **`ErrorWidget.builder`** replaces the red screen in release, and never itself throws.

```dart
// Bad - only framework errors are covered; every unawaited-future throw is invisible
FlutterError.onError = (d) => Report.error(d.exception, d.stack);
runApp(const App());

// Good - framework + root-zone async, both before runApp
FlutterError.onError = (d) => Report.error(d.exception, d.stack);
PlatformDispatcher.instance.onError = (e, st) { Report.error(e, st); return true; };
runApp(const App());
```

### Step 6 - Crash Reporting and Symbolication

- [ ] **Symbols uploaded from CI, on the same job that produced the artifact.** A release built with `--obfuscate --split-debug-info=<dir>` reports anonymous frames until that build's Dart symbols are uploaded. Symbols are per-build - a later upload from a laptop does not fix traces already collected.
- [ ] **Native symbols are a separate path** - Android R8/ProGuard mapping files and iOS dSYMs cover native frames. A Flutter app needs both uploads; the Dart symbol step does not cover them.
- [ ] **Fatal vs non-fatal distinguished** - a handled failure reported as fatal inflates crash-free-users and destroys the release gate's meaning.
- [ ] **Breadcrumbs and custom keys set before the crash** - screen name, feature-flag state, non-identifying user key. Values attached after the throw never arrive.
- [ ] **Errors reported with their original stack trace** - a converted failure rethrown without the stack (see `flutter-error-handling`) reports a trace pointing at the mapper, not the fault.

Use skill: `flutter-error-handling` for whether a reported crash should have been a typed failure handled in-app.

### Step 7 - Release and Build Attribution

- [ ] **Version, build number, flavor, and platform on every report**, read from package metadata (`package_info_plus`), not a hardcoded constant that drifts from the real build.
- [ ] **Environment separated** - debug, internal, and production builds report to distinct environments or projects; developer noise in the production console kills triage.
- [ ] **Session or install identifier is pseudonymous and stable**, never an email, phone number, or raw account ID.

A crash that cannot be tied to a release cannot be triaged or rolled back against.

### Step 8 - On-Device Logging

- [ ] **`print` is not logging.** In a release build its output goes to the platform log on a device you cannot read, while anyone with a cable can. It is a leak channel that yields you nothing. `debugPrint` only adds rate limiting - it is a debug tool, not the alternative.
- [ ] **One logging facade** - `dart:developer`'s `log` or the `logging` package behind a single entry point: console in debug, the reporter's breadcrumb API in release, so the last N lines arrive attached to the next crash.
- [ ] **Structured key-values, not interpolated message strings** - a redaction rule cannot scrub free text.
- [ ] **No PII, tokens, or full request/response bodies** in log lines or breadcrumbs, including anything derived from user-typed input.
- [ ] **No logging in a hot loop or per frame** - sample, or drop to debug level.

```dart
// Bad - unreadable to you, readable to anyone with the device, and leaks a token
print('login ok for ${user.email} token=$token');

// Good - facade, structured fields, no PII
log.info('login.success', {'method': 'oauth', 'userKey': user.pseudonymousId});
```

### Step 9 - Analytics Event Design

- [ ] **Closed, documented vocabulary in one Dart file** - no string literals at call sites, no interpolated event names. A funnel cannot be built across names that differ per user; the variable belongs in a parameter.
- [ ] **No PII in event names, parameters, or user properties.**
- [ ] **Screen views from a navigator observer** registered on the app's navigator, not `logEvent` calls scattered in `initState` that miss back-navigation and tab returns.
- [ ] **SDK naming and cardinality limits respected** - event and parameter names are length-limited and character-restricted, string values are truncated, reserved prefixes are rejected, and an app has a bounded number of *distinct* event names before new ones are silently dropped. Confirm current limits against the SDK's docs and validate in its debug view; the failure mode emits no error.
- [ ] **Event added with the parameters that make it answerable** - an event with no dimensions answers "did it happen", never "for whom, and instead of what".

### Step 10 - Performance Monitoring

- [ ] **Custom traces mark the interaction the user waits on**, not the call that is easy to measure. Trace `orders_screen_ready`, not `api_get_orders`.
- [ ] **Network timing is explicit for Dart HTTP traffic** - Flutter's requests bypass the native interception these SDKs rely on, so per-request timing needs a metric recorded from an HTTP-client interceptor or the SDK's own client integration. Assume nothing is auto-captured until verified.
- [ ] **Trace attributes are low-cardinality dimensions; metrics are counters.** Neither takes an identifier.
- [ ] **Frame timings aggregated before sending** - `SchedulerBinding.instance.addTimingsCallback` gives per-frame durations in release; send a percentile, never one event per frame.
- [ ] **No trace left unstopped on an error path** - a trace started before an `await` that throws never stops and never reports.

Frame-cost *causes* are `task-flutter-review-perf`; this lens owns whether the cost is measured at all.

### Step 11 - Consent, PII, and Platform Declarations

- [ ] **Collection defaults to off** where consent is required, and the persisted decision is read at startup **before** the first event can fire - not after the prompt.
- [ ] **The decision is revocable and honored** - opting out stops collection rather than only hiding the toggle.
- [ ] **iOS App Tracking Transparency** is requested only for tracking that reaches an advertising identifier, and not before the app is foreground-ready or the system suppresses the prompt.
- [ ] **Store data-collection declarations match what the app actually reports.** A field added in Dart without updating the declaration is a compliance defect, not only a privacy one.
- [ ] **Web and desktop caveats surfaced** when those targets are present: web has no native crash layer and symbolicates via source maps; desktop native coverage varies by SDK - verify rather than assume.

### Step 12 - Write Report

Standalone only. When spawned by `task-flutter-review`, return findings in the Output Format to the parent and write nothing - the parent owns the single merged report.

Use skill: `review-report-writer` with `report_type: review-observability` and every required input: `report_body`, `branch` (from the handle), refs from the precondition handle, `base_sha` / `head_sha` from Step 3, `stack: flutter`, `scope: +obs`, `depth` as resolved from the Depth table, and `mode: full`, `round: 1` - unless `review-observability-<branch>.md` already exists with valid frontmatter, then increment its `round` and pass its `head_sha` as `prior_head_sha`. (The handle's `prior_checkpoint` is keyed to the general review report - do not use it here.) Write before ending; print confirmation.

## Output Format

**Severity assignment:** High = a class of crash or a whole user journey is invisible in production, or PII leaves the device (missing error surface, reporter init after `runApp`, obfuscated build with no symbol upload, token in a log line or event parameter, collection before consent); Medium = signal arrives but is unreadable, unattributable, or duplicated (missing build attribution, doubled reporting from two owners, `print` as the release logging strategy, untyped event names); Low = naming, cardinality, verbosity, or coverage of a secondary path.

**One finding per root cause:** a defect matching several checklist lines is reported once at the strongest severity with the other aspects folded in.

```markdown
## Flutter Observability Review Summary

**Stack Detected:** Flutter <version> / Dart <version>
**Reporter:** Crashlytics | Sentry | both (justify) | absent
**Reporter Init:** before runApp at file:line | after runApp (defect) | absent
**Error Surfaces:** framework=<Y|N> asyncRoot=<Y|N> zone=<Y|N|N/A> isolate=<Y|N|N/A>
**Symbols:** uploaded in CI at <job> | manual | NOT UPLOADED (obfuscated build) | n/a (not obfuscated)
**Native Symbols:** mapping=<Y|N> dSYM=<Y|N> | n/a
**Analytics:** typed vocabulary at file:line | literals at call sites | absent
**Logging:** facade at file:line | print/debugPrint | mixed
**Consent:** default-off and gated at file:line | default-on | absent | n/a
**Platform Targets:** <list>
**Overall:** Adequate | Gaps Found - [<N> High / <N> Medium / <N> Low] | Greenfield - no surface wired [counts]

## Surface Map

| Surface                  | Verdict                  | Evidence                                    |
| ------------------------ | ------------------------ | ------------------------------------------- |
| Error-handler set        | wired / partial / absent | [file:line, or the missing handler]         |
| Crash reporter (native)  | wired / partial / absent | [...]                                       |
| Symbol upload (CI)       | wired / partial / absent | [...]                                       |
| Build attribution        | wired / partial / absent | [...]                                       |
| Logging facade           | wired / partial / absent | [...]                                       |
| Analytics events         | wired / partial / absent | [...]                                       |
| Performance traces       | wired / partial / absent | [...]                                       |
| Consent gating           | wired / partial / absent / n/a | [...]                                 |

> Use **Greenfield** as the `Overall:` headline when 3+ rows are `absent` - it tells the reader the review is scaffolding, not auditing. Keep the `absent` vocabulary consistent throughout.

## Findings

### High Impact

1. **Location:** [file:line, CI job, or the file where the missing wiring belongs]
   **Issue:** [name the gap: `PlatformDispatcher.instance.onError` unassigned, reporter initialized after `runApp`, obfuscated release with no symbol-upload step, `print` with a token, event name interpolated at the call site]
   **Invisible:** [what an on-call engineer cannot see because of this: "every unawaited-future throw is absent from the console; the crash-free rate is measuring a subset"]
   **Fix:** [concrete Dart, CI, or config change]

### Medium Impact

[Same numbered-block structure; numbering continues across tiers]

### Low Impact / Quick Wins

[Same numbered-block structure]

_Omit empty sections. Group by surface when > 2 findings share one. A wholly absent surface collapses to a single finding per the Step 4 grouping rule._

## Recommendations

[Structural instrumentation improvements not tied to one finding. At `deep`, the per-journey signal coverage list goes here.]

## Next Steps

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: release pipeline] - [one-line action]

_Tag `[Implement]` (localized) or `[Delegate]` (CI, release pipeline, backend, product). High -> `[Must]`; Medium / Low -> `[Recommend]`; `[Question]` when the fix depends on the author's answer (consent regime, analytics ownership, target platforms). Order Must > Recommend > Question. Omit if none._
```

## Self-Check

Mark a line N/A when the diff has no matching surface (e.g. no analytics SDK, no isolates).

- [ ] Step 1: behavioral principles loaded (or accepted from parent)
- [ ] Step 2: stack confirmed Flutter; reporter, analytics SDK, logging package, and platform targets recorded
- [ ] Step 3: precondition check ran (or handle received); diff + log read once; `current_head_sha` and `current_base_sha` captured
- [ ] Step 4: `flutter-observability` + `ops-observability` consulted; entry point, CI config, `pubspec.yaml`, and changed emit sites read; Surface Map verdicts assigned; absent surfaces grouped into one finding each
- [ ] Step 5: all four error surfaces checked; init before `runApp`; single owner per surface; native layer present; `ErrorWidget.builder` checked
- [ ] Step 6: CI symbol upload, native mapping/dSYM upload, fatal vs non-fatal, breadcrumbs, stack-trace preservation checked
- [ ] Step 7: version, build, flavor, platform attribution; environment separation; pseudonymous identifier
- [ ] Step 8: no `print`/`debugPrint` in production paths; single facade; structured fields; no PII; no hot-loop logging
- [ ] Step 9: closed event vocabulary, no PII, navigator-observer screen views, SDK limits, answerable parameters
- [ ] Step 10: traces mark user-waited boundaries; Dart HTTP timing explicit; bounded attribute cardinality; frame timings aggregated; traces stopped on error paths
- [ ] Step 11: consent default-off and read before first event, revocable, ATT gating, store declarations, web/desktop caveats
- [ ] Step 12: standalone: report written via `review-report-writer`, confirmation printed; subagent: findings returned to parent, no file written
- [ ] Generated files excluded from findings; source cited instead
- [ ] Findings name what an on-call engineer cannot see, not just the missing wire
- [ ] Backend framing avoided - no scrape, RED, exporter, or distributed-span recommendations
- [ ] Depth honored: `standard` ran all; `deep` added per-journey signal coverage under Recommendations
- [ ] Next Steps tagged `[Implement]` / `[Delegate]` and ordered Must > Recommend > Question (omit if none)

## Avoid

- Backend framing on a client: RED metrics, scrape endpoints, exporters, service SLOs, distributed-trace spans. The device pushes to a backend that owns those
- Writing a report when invoked as a subagent - the parent owns it
- Chaining `mode` / `round` off the general review's checkpoint instead of `review-observability-<branch>.md`
- `git fetch` / `git checkout` from this workflow
- Raising findings against `*.g.dart`, `*.freezed.dart`, `*.gr.dart`, `*.config.dart`, `*.mocks.dart`, or generated localization output
- Calling crash reporting done when only `FlutterError.onError` is wired
- Accepting an obfuscated release build with no CI symbol-upload step
- Accepting a Dart symbol upload as covering native frames - mapping files and dSYMs are separate
- Approving two reporters or two zone owners hooked to the same surface
- `print` / `debugPrint` as the release logging strategy
- Any email, phone number, raw account ID, token, or free-text input in an event, key, breadcrumb, or log line
- Event names containing a variable, screen index, or item id
- One trace per list item, or unsampled per-frame events from every device
- Prescribing a DSN, API key, or endpoint value - that is release config, not source review
- One finding per missing checkbox when the whole surface is absent
- Reviewing dashboards, alert rules, or on-call routing - they are not in this repo's source
- Duplicating reliability depth (timeouts, retries, offline) - route to `task-flutter-review-reliability`
- Emitting `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]`, `[Recommend]`, or `[Question]`, don't write it down.
