---
name: task-flutter-implement
description: End-to-end Flutter feature implementation - freezed models, repository, Riverpod state, adaptive screens, routes, and tests.
agent: flutter-engineer
metadata:
  category: mobile
  tags: [flutter, dart, riverpod, go-router, dio, drift, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Implement Flutter Feature

## When to Use

End-to-end Flutter feature work: models + data layer + state + screens + navigation + tests in one pass.

Not for: single-widget tweaks, bugfixes, pure styling changes, or backend work. A feature that only changes how an existing screen looks is a UI edit, not this workflow.

## Rules

- Widgets render state; state holders own side effects. No I/O, no navigation decisions, and no business logic in `build`
- Every network call carries a timeout and a cancellation path tied to the caller's lifetime
- Loading and error are modelled explicitly on every screen; empty is modelled on every screen whose data can be a collection or an absent record. Where no empty is reachable (a screen over fixed fields with defaults), state `not reachable` with the reason in the Empty cell instead of inventing one. None of the three is inferred from null or an empty list alone
- Data-layer errors are mapped to typed domain failures inside the data layer, at one conversion point per source; raw transport or storage exceptions never reach a widget
- Tokens and credentials go to secure storage, never `shared_preferences`; on web, memory only or a server-held HttpOnly cookie session, because no browser store is secure storage
- No hardcoded user-facing strings - all display text goes through localization
- Generated files are never hand-edited; regenerate instead
- On-device schema changes ship with a migration, because old app versions stay installed
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - PRINCIPLES, DETECT, AND GATHER

Use skill: `behavioral-principles` first; it governs every later step.

Read `pubspec.yaml` to confirm Flutter and record state management, navigation, networking, and persistence packages, plus the platform target directories present. If `pubspec.yaml` is absent or declares no `flutter` dependency, stop and say so - this workflow implements Flutter features and has nothing to fall back on.

If the detected state management is not Riverpod, say so explicitly (`Detected Bloc; Riverpod-specific guidance does not apply`) and fall back to state-management-agnostic design. Load `flutter-riverpod-patterns` in fallback mode rather than skipping it. Do not convert the project. Every later mention of these reads as the detected library's equivalent:

| Riverpod term | Reads as |
|---------------|----------|
| provider, state holder | that library's state holder (`Bloc` / `Cubit` / `ChangeNotifier`) |
| `ref` | its own read handle (`context.read`, an injected instance) |
| provider override, test seam, dependency by provider reference | its own injection point (`BlocProvider.value`, `RepositoryProvider`, get_it, a constructor at the composition root) |
| `autoDispose` / `keepAlive` | its own lifetime vocabulary |
| `AsyncValue` | its own single loading/error/data value |

Keep each delegated skill's output columns; substitute only the values.

Ask before writing code, grouped so each cluster surfaces its own follow-ups. Skip clusters the feature does not touch:

**Feature**
1. Screen(s) and the primary user flow through them
2. Entry points: tab, push from an existing screen, deep link, notification

**Data**
3. Remote API contract (endpoints, request/response shapes, error shapes)
4. Entities, fields, and validation rules
5. What must persist on device, and whether the local schema changes

**Behaviour**
6. Offline expectations: must it work offline, read-only offline, or is online required
7. State ownership and side effects (what triggers loads, what invalidates them)
8. Auth: which parts require a signed-in user

**Reach**
9. Which platform tiers ship this feature (mobile only, plus desktop, plus web)
10. Accessibility and localization expectations beyond the defaults

When answers do not come back, carry each open detail into STEP 2 as a stated assumption with the alternative named, so the approval gate is where they get settled - never leave one silently resolved in code; an unclear goal waits for its answer.

When the feature touches the on-device schema, record the oldest shipped `schemaVersion` from release history, or `unknown` when no release names it (the lowest `from` in the migration ladder is not evidence); it fills the migration contract's `Oldest Shipped Version` in STEP 2.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `flutter-riverpod-patterns` for the provider graph. Use skill: `flutter-data-persistence` for store selection. Use skill: `flutter-navigation-patterns` for the route and deep-link table. Use skill: `flutter-error-handling` for the boundary table. Use skill: `flutter-adaptive-responsive` for the tier plan; with one tier it covers the mobile baseline (safe areas, insets, orientation, large screens). When the feature stores tokens or credentials, adds a deep-link entry point, or adds a capability that guards or stores anything sensitive, Use skill: `flutter-security-patterns` here for its decision table; when the on-device schema changes, Use skill: `flutter-local-db-migration` here for the migration contract (`Change Type`, `Data Impact`, `Downgrade Path`) - both are approval-gate content, and STEPS 4 and 6 apply them.

Present file tree and decisions:

- Widget/screen tree, and which subtrees are invariant enough to be `const` once written
- Provider graph: each state holder, its kind, its dependencies, and its disposal scope
- Data layer: models, repository interface, remote source, local source
- Failure types and how each maps to a UI state
- Routes and deep-link entries
- Loading, error, and empty presentation per screen
- Adaptive layout plan per target tier
- Accessibility and localization intent

When the design deviates from this skill's defaults (a different store, a state holder that outlives its screen, a route outside the existing shell, a biometric gate with no key binding), call out the deviation with its reason so the approver sees the choice rather than discovering it in review.

Wait for approval. When the request explicitly waived interaction ("don't ask, just build it"), the waiver is the approval for the design: present it, open the report with `Proceeding on the request's explicit waiver`, and continue - carried assumptions resolve to their stated defaults, each written as `Assumed: <default> (alternative: <other>)` under that line, blank-separated. The waiver covers writing code - `behavioral-principles` treats an unapplied diff as reversible groundwork; it is not the confirmation that skill asks for before a high-blast-radius part ships - one where a defect would cause data loss or corruption, a security exposure, or incorrect money movement: an on-device migration, token or credential storage, a deep-link entry point, a biometric gate, a payment action, a logout wipe - so the design marks each such part, and the `Release gate:` line under the waiver marker names every one for confirmation before release (`none` when the design marked none). A run that stops at the approval gate delivers, in this order: `## Design` (the STEP 2 decision list and the blocks STEP 2 produced, each under its Output Format heading demoted to `###`), `## Open Assumptions` (one `Assumed:` line each, blank-separated), and `## Fixed in plan, Pre-existing and Not read` as far as found; nothing else from the Output Format below.

### STEP 3 - MODELS

Use skill: `dart-language-patterns`. When the project uses code generation, freezed + json_serializable for data models; when it does not, hand-write the equivalent (`fromJson`/`toJson`, `copyWith`, `==`/`hashCode`) rather than adding a codegen toolchain the project does not have. Sealed failure types for the error model either way - Dart 3 `sealed` needs no generation. Below an SDK floor of 3.0, `sealed` does not exist: the failure model is an abstract class with subclasses, matched by an `is` chain whose final `else` reports the unknown subtype, and the design says so. Keep serialization concerns on data-layer models; domain entities stay free of transport shapes.

### STEP 4 - DATA LAYER

Use skill: `flutter-networking` for the remote source. Use skill: `flutter-data-persistence` for the local source. Use skill: `flutter-error-handling` for the mapping.

Repository interface in the domain layer, implementation in data. Remote source configures timeouts and accepts the client's cancellation handle (Dio's `CancelToken`, `AbortableRequest` on `package:http` 1.5+), or `flutter-networking`'s `unavailable (<library>): <mitigation | unmitigated>` line says what stands in (below `package:http` 1.5, a `Client` the caller owns and closes on dispose); `unmitigated` - a shared client no caller may close - is a STEP 2 decision the approver sees: raise the library floor, or give the caller its own closable client. Server payloads are what an older build reads, so new response fields stay optional and unknown ones are tolerated on read. Local source owns the on-device store. Transport and storage errors become domain failures inside the data layer, at one conversion point per source, and never above the repository.

When the on-device schema changes: Use skill: `flutter-local-db-migration`. This build and later ones can meet a database a newer build wrote (sideload, reinstall, a TestFlight downgrade): the contract's `Downgrade Path` slot cites the guard (`explicit at file:line`) and the design states what it does - refuse to open with an update-required screen (default) or open read-only; `unhandled` never ships, so a guard added where none was (inside drift's `onUpgrade`; an `onDowngrade` added to sqflite's `openDatabase`) is a `Fixed in plan:` line.

### STEP 5 - STATE

Use skill: `flutter-riverpod-patterns`. State holders expose loading, error, and data as one value rather than parallel booleans. Side effects live in the holder's methods, not in `build`. Dependencies arrive by provider reference (the fallback table's injection point in a non-Riverpod project) so tests can override them. Anything scoped to a single screen disposes with it.

### STEP 6 - UI

Use skill: `flutter-widget-patterns`. Use skill: `flutter-adaptive-responsive` for the tier plan from STEP 2. Use skill: `flutter-accessibility` for labels, touch targets, focus order, and text scaling. Use skill: `flutter-i18n` for all user-facing strings.

Screens and widgets composed small and `const` where possible. Keys on list items whose identity matters. Routes wired per `flutter-navigation-patterns`. Every screen renders loading, error, and its reachable empty state, not just the happy path.

When the feature adds a platform capability - biometrics, permissions, background work, a native SDK - Use skill: `flutter-platform-channels` for the channel boundary; a plugin that only reads device state (connectivity, battery level) emits its capability block with `Mechanism: existing plugin: <name>` for its platform coverage, and no channel of its own. Use skill: `flutter-security-patterns` when the feature stores tokens or credentials, adds a deep-link entry point, or adds a capability that guards or stores anything sensitive. Native-side configuration (`AndroidManifest.xml`, `Info.plist`, entitlements, activity base class) ships with the Dart code in the same pass; a feature whose native side is unconfigured does not run, and a native file it needs that is absent from the repository is created and listed as created.

### STEP 7 - TESTS

Use skill: `flutter-testing-patterns`. Unit tests for domain logic and failure mapping. Widget tests for each screen including its loading, error, and empty states. Golden tests for the key UI, tagged `@Tags(['golden'])` with the tag declared in `dart_test.yaml`, fonts and tolerance pinned so they survive CI. One `integration_test` for the critical flow. Fakes injected through the project's own dependency seam; the network stubbed at the client boundary, and any platform capability faked at the service that wraps its channel.

### STEP 8 - VALIDATE

Run in order, fixing failures in code the feature touched before reporting done; a failure in untouched code that breaks the build is `Fixed in plan:` (the atomics' rule), one in code the feature calls or reads goes on a `Pre-existing:` line, and one elsewhere is reported under Validation only:

1. `flutter pub get`, then `flutter gen-l10n` when the feature added ARB keys (the generated class lands in `output-dir`, default `arb-dir`)
2. `dart run build_runner build --delete-conflicting-outputs` when the project uses `build_runner` - Drift always does; and when the schema changed, `dart run drift_dev schema dump lib/<database>.dart drift_schemas/`, `schema steps drift_schemas/ lib/<database>.steps.dart`, and `schema generate --data-classes --companions drift_schemas/ test/generated/` for the snapshot, the `stepByStep` helper, and the migration-test helpers with the old-version data classes the seeded rows need
3. `flutter analyze`
4. `dart format --set-exit-if-changed <the files the feature wrote>` (`dart format` has no exclude option; generated output - `lib/l10n`, `*.g.dart`, `*.freezed.dart`, the schema helpers - is never hand-edited and stays out of it)
5. `flutter test --exclude-tags golden`, then `flutter test --tags golden` on the pinned platform (a new golden has no baseline: its first run there is `--update-goldens`, followed by a look at the image), then `flutter test integration_test` on a device, emulator, or desktop target
6. One build per shipped platform: `flutter build apk` or `appbundle`, `flutter build ios --no-codesign` (macOS host only), `flutter build web`, and `flutter build windows` / `macos` / `linux` each on its own host OS - a platform that ships unbuilt is unvalidated, and web and desktop fail for reasons mobile never surfaces

A command that cannot run here is reported under Validation with the reason and the exact command the user runs on the right host or device before merging - never as a clean run; a toolchain that cannot resolve the project's SDK constraint makes every command from `pub get` on unrunnable, and results from a patched scratch copy are reported as such, never as the project's.

## Edge Cases

- Vague input: an unclear goal is asked in STEP 1 and waits for the answer, waiver or not; an open detail is asked and, unanswered, carried as an `Assumed:` line per STEP 1
- No `pubspec.yaml`, or no `flutter` dependency: stop at STEP 1; do not produce generic advice
- No persistence: skip the local source in STEP 4
- No remote API (fully local feature): skip the remote source; the repository still maps storage errors to failures
- Existing screen being extended: read it first and match its existing state and layout conventions
- No code generation in the project: hand-write the models and skip the `build_runner` step - unless the design adds a Drift store, which brings `drift_dev` and `build_runner` with it
- Code generation in use but generated outputs not committed: write the sources; STEP 8's `build_runner` produces the outputs, and when it cannot run, Validation names the missing ones
- Defects already in code the feature edits or depends on, including a screen with no route to it: the atomics' rule decides - a defect in code the change edits, or one the new code would misbehave on at first run (the migration it extends lacking a downgrade path, a `default` arm hiding the sealed variant it adds, a build break anywhere), is `Fixed in plan:`; a defect in code the new code only calls or reads is `Pre-existing:`
- No localization set up: the feature adds `gen_l10n` per `flutter-i18n`'s setup pattern for its own strings and reports `Setup: l10n.yaml at <path>` with the file listed as created; hardcoded strings on the lines the feature edits are `Fixed in plan:`, on lines it calls or reads `Pre-existing:`, elsewhere unlisted (`flutter-i18n`'s rule)
- Web tier included: flag `dart:io`, platform-channel, and plugin unavailability at STEP 2 (a capability the web tier cannot offer sits behind the capability check the atomics prescribe, with its fallback recorded in Platform Tiers and the capability block, never left to fail at runtime), and confirm the on-device store has a web story (drift needs a WASM setup) before the schema is designed
- Deep-link entry point: validate link parameters before use. A custom scheme carries no ownership claim; an `https://` link opens the app only once verified (Android `assetlinks.json` with `autoVerify`; iOS the Associated Domains entitlement plus the hosted `apple-app-site-association` file), and on web it is an ordinary URL, whose path URL strategy needs a host rewrite to `index.html`
- Feature triggered by app lifecycle (resume, background, app-switcher): name the `AppLifecycleState` transitions that drive it at STEP 2, and inject the clock so any time threshold is testable; a lock or gate that must cover every route is an overlay above the router, not a route, and a "PIN fallback" names the device credential (`biometricOnly: false`) unless the request says an app-managed PIN

## Output Format

Atomic skills invoked during the run emit their own structured blocks. Each section below names the blocks it carries - reproduce those blocks under the heading, never restated in prose; an atomic invoked at STEP 2 and again later contributes its final emission, and the STEP 2 one is working content. Blocks no section names (the `dart-language-patterns` and `flutter-widget-patterns` decision tables) are working content for STEPS 3 and 6, not report content; `dart-language-patterns`' `Dart SDK:` and `Targets:` lines open Files Generated. Implement-mode atomics end with `Fixed in plan:`, `Pre-existing:`, and `Not read:` lines (`flutter-navigation-patterns` after its route lines); `Fixed in plan:` names the defects the code written here corrects, including the content atomics route there (`Window floor: set by this plan`, migration repairs and added guards, a replaced stringly-typed exception), and `Not read:` names any file the plan needs that is absent, could not be read, or was not read. The report carries all three once, merged across atomics and deduplicated by cited location, under `## Fixed in plan, Pre-existing and Not read`; `Not checked:` lines (`dart-language-patterns` below Dart 3.0) join them there; `Fixed in plan: none`, `Pre-existing: none`, or `Not read: none` is written when no atomic produced that kind, and `Not checked:` appears only with content. A section whose surface the feature does not touch states `none - <reason>` on one line instead of carrying an empty block.

```markdown
Proceeding on the request's explicit waiver {this block only on a waiver run}

Assumed: <default> (alternative: <other>) {one per carried assumption, blank-separated}

Release gate: {<part>; <part> | none} {every high-blast-radius part the design marked}

## Files Generated
[`Dart SDK:` and `Targets:` lines from `dart-language-patterns`, then the files grouped by layer: models / data / state / ui / navigation / tests; mark each created or modified]

## Screens and Routes
[the route table from `flutter-navigation-patterns` with its `Shell:`, `Guard source:`, `Error route:`, `Web URL strategy:`, and `Gate order:` lines, then one `- ` bullet per screen naming its entry points]

## State Holders
[the provider graph from `flutter-riverpod-patterns`, in that skill's columns; in fallback mode, opened by its `Detected <X>` line and in its fallback-mode terms]

## Data and Storage
[the client contract from `flutter-networking`; the per-item store table from `flutter-data-persistence` opened by its `Tiers:` line; when the on-device schema changed, the migration contract blocks from `flutter-local-db-migration`, one per step]

## Platform Tiers
[the adaptive plan from `flutter-adaptive-responsive`, opened by its `Tiers:` line; with one tier it is the mobile baseline plan; a surface designed out of a tier lists only the tiers it exists on in its `Tiers` cell, and the capability block's `Platforms:` line carries the designed fallback]

## UI States
| Screen | Loading | Error | Empty |
|--------|---------|-------|-------|
| {screen} | {widget or state} | {widget or state} | {widget or state \| not reachable - <reason>} |

## Failure Mapping
[the boundary table from `flutter-error-handling`, then:]

| Failure | UI state |
|---------|----------|
| {a failure the repository can produce} | {what the user sees} |

## Platform Capability

[the capability block from `flutter-platform-channels`, one per channel or existing plugin, when STEP 6 fired it]

## Security Decisions

[the decision table from `flutter-security-patterns`, when STEP 6 fired it]

## Localization and Accessibility

[the localization plan from `flutter-i18n` and the accessibility plan from `flutter-accessibility`]

## Tests
[the per-target plan table from `flutter-testing-patterns`, its `### Coverage Gaps` block when it emitted one, then test files per layer - counts are files:]
- Unit: {count}
- Widget: {count}
- Golden: {count}
- Integration: {count}
- Migration: {how many of the Unit files test migration steps} {only when the schema changed}

## Fixed in plan, Pre-existing and Not read
[the merged `Fixed in plan:`, `Pre-existing:`, `Not read:`, and `Not checked:` lines]

## Validation
[one `- ` bullet per STEP 8 command: `<command> -> <result>`, or for a command that could not run `<command> -> not run: <reason>; Run before merging: <exact command> on <host or device>`]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] `pubspec.yaml` confirms Flutter; non-Riverpod state management surfaced rather than converted
- [ ] Requirements gathered; unanswered questions carried into the design as `Assumed:` lines with the alternative named
- [ ] Design approved before code, or the waiver marker written and every high-blast-radius part named on `Release gate:`
- [ ] Deviations from the skill's defaults, the security decision table, and the migration contract in front of the approver
- [ ] Each block the Output Format names reproduced under its heading (final emission when an atomic ran twice)
- [ ] Models typed; failures sealed and exhaustively handled (below Dart 3.0, the abstract-class form); hand-written where the project has no codegen
- [ ] Repository maps every transport and storage error to a domain failure
- [ ] Network calls carry timeouts and a cancellation path; new response fields optional and unknown ones tolerated
- [ ] Local schema change ships a migration with its `Downgrade Path` explicit
- [ ] State holders own side effects; nothing I/O-bound in `build`
- [ ] Every screen renders loading, error, and its reachable empty state; unreachable empties recorded with a reason
- [ ] Adaptive layout applied for each shipped platform tier
- [ ] When a capability was added: channel boundary and native configuration covered
- [ ] Security decision table produced whenever STEP 6 fired `flutter-security-patterns`; tokens and credentials in secure storage (web: memory or an HttpOnly cookie session)
- [ ] Routes wired per `flutter-navigation-patterns`; deep-link parameters validated before use
- [ ] Accessibility labels present; no hardcoded user-facing strings
- [ ] Tests at all four layers, plus migration tests when the schema changed; fakes injected through the project's own dependency seam
- [ ] `pub get` and `gen-l10n`, `build_runner` and drift_dev schema tooling (when used), `analyze`, `format`, unit and widget tests, goldens on the pinned platform, the integration test, and a build for every shipped platform pass, or each command that could not run is named with the reason and the command the user runs before merging
- [ ] `Fixed in plan:`, `Pre-existing:`, and `Not read:` lines carried under their own heading

## Avoid

- Unbounded list rendering where the item count is dynamic
