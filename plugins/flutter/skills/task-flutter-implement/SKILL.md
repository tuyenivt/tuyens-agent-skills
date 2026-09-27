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
- Loading and error are modelled explicitly on every screen; empty is modelled on every screen whose data can be a collection or an absent record. Where no empty is reachable (a screen over fixed fields with defaults), state `empty: not reachable` with the reason instead of inventing one. None of the three is inferred from null or an empty list alone
- Data-layer errors are mapped to typed domain failures inside the data layer, at one conversion point per source; raw transport or storage exceptions never reach a widget
- Tokens and credentials go to secure storage, never `shared_preferences`
- No hardcoded user-facing strings - all display text goes through localization
- Generated files are never hand-edited; regenerate instead
- On-device schema changes ship with a migration, because old app versions stay installed
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - PRINCIPLES, DETECT, AND GATHER

Use skill: `behavioral-principles` first; it governs every later step.

Read `pubspec.yaml` to confirm Flutter and record state management, navigation, networking, and persistence packages, plus the platform target directories present. If `pubspec.yaml` is absent or declares no `flutter` dependency, stop and say so - this workflow implements Flutter features and has nothing to fall back on.

If the detected state management is not Riverpod, say so explicitly (`Detected Bloc; Riverpod-specific guidance does not apply`) and fall back to state-management-agnostic design. Load `flutter-riverpod-patterns` in fallback mode rather than skipping it. Do not convert the project.

The fallback is a vocabulary substitution, not a step skip. Every later mention of these reads as the detected library's equivalent:

| Riverpod term | Reads as |
|---------------|----------|
| provider, state holder | that library's state holder (`Bloc` / `Cubit` / `ChangeNotifier`) |
| `ref` | its own read handle (`context.read`, an injected instance) |
| provider override, test seam | its own injection point (`BlocProvider.value`, a constructor argument) |
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

Ask targeted questions for gaps rather than guessing. When answers do not come back, carry each open question into STEP 2 as a stated assumption with the alternative named, so the approval gate is where they get settled - never leave one silently resolved in code.

When the feature touches the on-device schema, record the oldest shipped `schemaVersion`; it fills the migration contract's `Oldest Shipped Version` in STEP 4.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `flutter-riverpod-patterns` for the provider graph. Use skill: `flutter-data-persistence` for store selection. Use skill: `flutter-navigation-patterns` for the route and deep-link table. Use skill: `flutter-error-handling` for the boundary table. Use skill: `flutter-adaptive-responsive` for the tier plan; with one tier it covers the mobile baseline (safe areas, insets, orientation, large screens).

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

Wait for approval. When the request explicitly waived interaction ("don't ask, just build it"), the waiver is the approval: present the design, mark it `Proceeding on the request's explicit waiver`, and continue - carried assumptions resolve to their stated defaults. The waiver covers writing an on-device migration, since code in the working tree is reversible; the migration is the gate `behavioral-principles` names, so the design marks it irreversible once shipped and the report's `Release gate:` line asks for confirmation before release. A run that stops at the approval gate delivers the design with its open assumptions and any `Pre-existing:` and `Not read:` lines found so far, not the Output Format below.

### STEP 3 - MODELS

Use skill: `dart-language-patterns`. When the project uses code generation, freezed + json_serializable for data models; when it does not, hand-write the equivalent (`fromJson`/`toJson`, `copyWith`, `==`/`hashCode`) rather than adding a codegen toolchain the project does not have. Sealed failure types for the error model either way - Dart 3 `sealed` needs no generation. Below an SDK floor of 3.0, `sealed` does not exist: the failure model is an abstract class with subclasses, matched by `is` checks with a `default` that reports, and the design says so. Keep serialization concerns on data-layer models; domain entities stay free of transport shapes.

### STEP 4 - DATA LAYER

Use skill: `flutter-networking` for the remote source. Use skill: `flutter-data-persistence` for the local source. Use skill: `flutter-error-handling` for the mapping.

Repository interface in the domain layer, implementation in data. Remote source configures timeouts and accepts a `CancelToken`. Local source owns the on-device store. Transport and storage errors become domain failures inside the data layer, at one conversion point per source, and never above the repository.

When the on-device schema changes: Use skill: `flutter-local-db-migration`. An older build that meets a newer database takes that skill's `from > to` path. Server payloads are what an older build reads, so new response fields stay optional and unknown ones are tolerated on read.

### STEP 5 - STATE

Use skill: `flutter-riverpod-patterns`. State holders expose loading, error, and data as one value rather than parallel booleans. Side effects live in the holder's methods, not in `build`. Dependencies arrive by provider reference so tests can override them. Anything scoped to a single screen disposes with it.

### STEP 6 - UI

Use skill: `flutter-widget-patterns`. Use skill: `flutter-adaptive-responsive` for the tier plan from STEP 2. Use skill: `flutter-accessibility` for labels, touch targets, focus order, and text scaling. Use skill: `flutter-i18n` for all user-facing strings.

Screens and widgets composed small and `const` where possible. Keys on list items whose identity matters. Routes wired per `flutter-navigation-patterns`. Every screen renders loading, error, and its reachable empty state, not just the happy path.

When the feature adds a platform capability - biometrics, permissions, background work, a native SDK - Use skill: `flutter-platform-channels` for the channel boundary; a plugin that only reads device state (connectivity, battery level) emits its capability block with `Mechanism: existing plugin: <name>` for its platform coverage, and no channel of its own. Use skill: `flutter-security-patterns` when the feature stores tokens or credentials, adds a deep-link entry point, or adds a capability that guards or stores anything sensitive. Native-side configuration (`AndroidManifest.xml`, `Info.plist`, entitlements, activity base class) ships with the Dart code in the same pass; a feature whose native side is unconfigured does not run, and a native file it needs that is absent from the repository is created and listed as created.

### STEP 7 - TESTS

Use skill: `flutter-testing-patterns`. Unit tests for domain logic and failure mapping. Widget tests for each screen including its loading, error, and empty states. Golden tests for the key UI, with fonts and tolerance pinned so they survive CI. One `integration_test` for the critical flow. Fakes injected through the project's own dependency seam; the network stubbed at the client boundary, and any platform capability faked at the service that wraps its channel.

### STEP 8 - VALIDATE

Run in order, fixing failures in code the feature touched before reporting done; a failure only in untouched code goes on a `Pre-existing:` line:

1. `dart run build_runner build --delete-conflicting-outputs` (only if the project uses `build_runner`; `gen_l10n` output regenerates on `flutter pub get` when `generate: true`, and is not this step)
2. `flutter analyze`
3. `dart format --set-exit-if-changed .`
4. `flutter test`
5. `flutter build <target>` once per shipped platform (Android and iOS both, for the mobile tier) - a platform that ships unbuilt is unvalidated, and web and desktop fail for reasons mobile never surfaces

If a command is unavailable in the environment, say which one and why rather than reporting a clean run.

## Edge Cases

- Vague input: ask in STEP 1; never guess
- No `pubspec.yaml`, or no `flutter` dependency: stop at STEP 1; do not produce generic advice
- No persistence: skip the local source in STEP 4
- No remote API (fully local feature): skip the remote source; the repository still maps storage errors to failures
- Existing screen being extended: read it first and match its existing state and layout conventions
- Non-Riverpod project: state holders, dependency handles, and test seams read as the detected library's equivalents throughout; no step is skipped
- No code generation in the project: skip the `build_runner` step and hand-write the models
- Code generation in use but generated outputs not committed: write the sources; STEP 8's `build_runner` produces the outputs, and when it cannot run, Validation names the missing ones
- Defects already in code the feature edits or depends on, including a screen with no route to it: fixed only when the feature cannot ship on top of them - a defect on the path the feature changes counts (the `onUpgrade` it extends lacking `from > to` handling, a `default` arm hiding the sealed variant it adds) - otherwise carried on `Pre-existing:` lines
- No localization set up: the feature adds `gen_l10n` per `flutter-i18n`'s setup pattern for its own strings and reports `Setup: l10n.yaml at <path> (new)`; existing hardcoded strings go on `Pre-existing:` lines
- Web tier included: flag `dart:io` and platform-channel unavailability at STEP 2, and confirm the on-device store has a web story (drift needs a WASM setup) before the schema is designed
- Deep-link entry point: validate link parameters before use. A custom scheme carries no ownership claim; an `https://` link opens the app only once verified (Android `assetlinks.json`, iOS associated domains), and on web it is an ordinary URL, whose path URL strategy needs a host rewrite to `index.html`
- Feature triggered by app lifecycle (resume, background, app-switcher): name the `AppLifecycleState` transitions that drive it at STEP 2, and inject the clock so any time threshold is testable

## Output Format

Atomic skills invoked during the run emit their own structured blocks. Each section below names the blocks it carries - reproduce those blocks under the heading, never restated in prose. Blocks no section names (the `dart-language-patterns` and `flutter-widget-patterns` decision tables) are working content for STEPS 3 and 6, not report content; `dart-language-patterns`' `Dart SDK inferred:` and `Dart 3 patterns unavailable:` lines open Files Generated. Implement-mode atomics end with `Pre-existing:` and `Not read:` lines, a `Not read:` line naming any file the plan needed but could not read, absent or denied. The report carries them once, merged across atomics and deduplicated by cited location, under `## Pre-existing and Not read`; `Not checked:` lines (`dart-language-patterns` below Dart 3.0) join them there; `Pre-existing: none` is written when no atomic found one. A section whose surface the feature does not touch states `none - <reason>` on one line instead of carrying an empty block.

```markdown
## Files Generated
[grouped by layer: models / data / state / ui / navigation / tests; mark each created or modified]

## Screens and Routes
[the route table from `flutter-navigation-patterns` with its `Shell:`, `Guard source:`, `Error route:`, `Web URL strategy:`, and `Gate order:` lines, then one line per screen naming its entry points]

## State Holders
[the provider graph from `flutter-riverpod-patterns`, in that skill's columns; in fallback mode, opened by its `Detected <X>` line and in its fallback-mode terms]

## Data and Storage
[the client contract from `flutter-networking`; the per-item store table from `flutter-data-persistence`, with its `Tiers:` line when it emits one; and when the on-device schema changed, the migration contract blocks from `flutter-local-db-migration`, one per step, then `Release gate: confirm the migration before release` when the schema changed]

## Platform Tiers
| Tier | Shipped | Caveats applied |

[the adaptive plan from `flutter-adaptive-responsive`; with one tier it is the mobile baseline plan, summarized in `Caveats applied`]

## UI States
| Screen | Loading | Error | Empty |

[`empty: not reachable` with its reason where no empty state exists]

## Failure Mapping
[the boundary table from `flutter-error-handling`, then:]

| Failure | UI state |

[one row per failure the repository can produce and what the user sees]

## Platform Capability

[the capability block from `flutter-platform-channels`, one per channel or existing plugin, when STEP 6 fired it]

## Security Decisions

[the decision table from `flutter-security-patterns`, when STEP 6 fired it]

## Localization and Accessibility

[the localization plan from `flutter-i18n` and the accessibility plan from `flutter-accessibility`]

## Tests
[the per-target plan table and `### Coverage Gaps` from `flutter-testing-patterns`, then test files per layer:]
- Unit: {count}
- Widget: {count}
- Golden: {count}
- Integration: {count}
- Migration: {how many of the Unit rows test migration steps, when the schema changed}

## Pre-existing and Not read
[the merged `Pre-existing:`, `Not read:`, and `Not checked:` lines]

## Validation
[command -> result for each STEP 8 command; name any command that could not run and why]
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] `pubspec.yaml` confirms Flutter; non-Riverpod state management surfaced rather than converted
- [ ] Requirements gathered; design approved before code
- [ ] Deviations from the skill's defaults called out at the approval gate
- [ ] Each block the Output Format names reproduced under its heading
- [ ] Models typed; failures sealed and exhaustively handled (below Dart 3.0, the abstract-class form); hand-written where the project has no codegen
- [ ] Repository maps every transport and storage error to a domain failure
- [ ] Network calls carry timeouts and a cancellation path
- [ ] Local schema change ships a migration, an older build meeting a newer database takes the `from > to` path, and the `Release gate:` line is written
- [ ] State holders own side effects; nothing I/O-bound in `build`
- [ ] Every screen renders loading, error, and its reachable empty state; unreachable empties recorded with a reason
- [ ] Adaptive layout applied for each shipped platform tier
- [ ] When a capability was added: channel boundary and native configuration covered
- [ ] Security decision table produced whenever STEP 6 fired `flutter-security-patterns`
- [ ] Routes wired per `flutter-navigation-patterns`; deep-link parameters validated before use
- [ ] Accessibility labels present; no hardcoded user-facing strings
- [ ] Tests at all four layers, plus migration tests when the schema changed; fakes injected through the project's own dependency seam
- [ ] `build_runner` (codegen projects), `analyze`, `format`, `test`, and a build for every shipped platform pass, or each command that could not run is named with the reason
- [ ] `Pre-existing:` and `Not read:` lines carried under their own heading

## Avoid

- Business logic, I/O, or navigation decisions inside `build`
- Raw transport or storage exceptions surfacing in the widget layer
- Parallel `isLoading` / `error` / `data` booleans instead of one state value
- Tokens or credentials in `shared_preferences`
- Hardcoded user-facing strings
- Hand-editing generated files
- Non-`const` widgets that could be `const`
- Unbounded list rendering where the item count is dynamic
- Changing the on-device schema without a migration
- Using a deep-link parameter without validating it
- Generating code before design approval
- Reporting done without running the STEP 8 commands
