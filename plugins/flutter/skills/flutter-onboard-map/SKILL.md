---
name: flutter-onboard-map
description: Flutter onboarding signals - pubspec deps, flavors and entry points, state management, navigation, persistence, codegen, platforms, CI.
metadata:
  category: mobile
  tags: [onboarding, codebase-map, flutter, dart, pubspec, flavors, codegen]
user-invocable: false
---

# Flutter Onboard Map (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-onboard` when the stack is Flutter. Not standalone: this contributes sections to the onboarding report, it does not produce one.

## When to Use

- A workflow needs Flutter-specific orientation: dependency roles, flavors, state management, navigation, data layer, codegen, platform targets, CI
- Project has `pubspec.yaml` with a `flutter:` section or an `sdk: flutter` dependency. A `pubspec.yaml` with neither is a plain Dart package, not a Flutter app

## Rules

- Report the SDK **pin**, not "latest": Dart constraint from `environment:` in `pubspec.yaml`, Flutter version from `.fvmrc` / `fvm_config.json`, `.tool-versions`, or the CI workflow
- Classify direct dependencies by role (table below) instead of restating `pubspec.yaml`. Dev dependencies fold into the codegen and test roles
- State management is whatever is declared, never the house default: `flutter_riverpod`/`riverpod` -> Riverpod, `flutter_bloc` -> Bloc, `provider` -> Provider, `get` -> GetX. Two present usually means an in-flight migration; report both and which one newer code uses
- Determine whether codegen output is committed. Tracked `*.g.dart` / `*.freezed.dart` means `build_runner` is an occasional step; gitignored means the project **does not compile** until it runs. This is the most common first-run failure and belongs in bootstrap either way
- Platform targets are the top-level folders actually present. A folder that no flavor or CI job ever builds is stale - say so rather than implying support
- Flag `path:` / `git:` dependencies and any `dependency_overrides` - they do not resolve from pub.dev and usually carry local setup steps or a worked-around version conflict
- Mark inferred items `(inferred)` and undiscoverable ones `(unknown)`. Never invent a package, flavor name, application id, endpoint, Firebase project, or CI secret

## Patterns

### Dependency roles

| Role | Common packages |
| --- | --- |
| State management | `flutter_riverpod` / `riverpod`, `flutter_bloc`, `provider`, `get`, `signals` |
| Navigation | `go_router`, `auto_route`, bare `Navigator` |
| Networking | `dio` (+ `retrofit`), `http`, `chopper`, `graphql_flutter` |
| Local database | `drift`, `sqflite`, `isar`, `hive`, `objectbox` |
| Key-value and secrets | `shared_preferences`, `flutter_secure_storage` |
| Models and serialization | `freezed` + `json_serializable`, `built_value`, manual |
| Dependency injection | `get_it` + `injectable`, or the state library's own providers |
| Codegen (dev) | `build_runner`, `*_generator`, `pigeon` |
| Observability | `firebase_crashlytics`, `sentry_flutter`, `firebase_analytics`, `logger` |
| Test (dev) | `flutter_test`, `integration_test`, `mocktail` / `mockito`, golden tooling, `patrol` |
| Native bridge | packages declaring a `plugin:` block, plus local `packages/` or `plugins/` entries |

### Project layout

| Convention | Shape | Signal |
| --- | --- | --- |
| **Layer-first** | `lib/{models,services,repositories,screens,widgets,providers}/` | smaller apps, tutorial lineage |
| **Feature-first** | `lib/features/<feature>/{data,domain,presentation}/` plus `lib/core/` | medium and larger apps, often Clean-architecture flavored |

Report the observed one, since it determines where new code lands. `lib/main.dart` should be thin (bootstrap plus `runApp`); substantial logic there is worth noting. Several `lib/main_*.dart` files mean per-flavor entry points.

### Codegen and l10n

| Output | Produced by | Usually |
| --- | --- | --- |
| `*.g.dart`, `*.freezed.dart` | `build_runner` | check `.gitignore` - varies per project |
| `*.gr.dart` | `auto_route` | follows the project's build_runner convention |
| drift table code and `drift_schemas/*.json` | `drift_dev` | schema snapshots committed |
| `app_localizations*.dart` | `flutter gen-l10n`, configured by `l10n.yaml` over ARB files | gitignored |
| Pigeon Dart + native output | `pigeon` | committed |

`dart run build_runner build --delete-conflicting-outputs` is the near-universal invocation; check the Makefile, `melos.yaml`, or scripts for the project's actual wrapper before citing it.

### Bootstrap path

1. Toolchain: Flutter SDK from the pin; if `fvm` is present, every command is prefixed `fvm flutter`
2. Dependencies: `flutter pub get`, or `melos bootstrap` when `melos.yaml` exists
3. Codegen when output is not committed - without this the project does not compile
4. Config: `--dart-define-from-file` JSON, `.env` files, and gitignored native config (`firebase_options.dart`, `google-services.json`, `GoogleService-Info.plist`). Flag these as a required team handoff; do not invent values
5. Native: iOS CocoaPods under `ios/`, Android SDK/NDK requirements from `android/`
6. Run: `flutter run --flavor <f> -t lib/main_<f>.dart`, or the project's script
7. Verify: app reaches its first route; `flutter analyze` and `flutter test` are clean

### Test layout

`test/` for unit and widget tests, `integration_test/` for on-device runs, golden images usually under a `goldens/` folder inside `test/`. Goldens are font- and platform-sensitive: check whether CI loads fonts and which platform generates them, since that determines whether a contributor can regenerate goldens locally at all.

### CI

Read `.github/workflows/`, `codemagic.yaml`, `bitrise.yml`, `.gitlab-ci.yml`, `fastlane/Fastfile`. Capture the SDK pin, whether codegen runs, which gates exist (analyze, test, golden), which flavors build, the store upload target, and signing secret **names** only.

### Risk hotspots (delegate depth)

- Provider lifecycle, rebuild scope, disposal -> `flutter-riverpod-patterns`, `flutter-widget-patterns`
- Store choice and secret placement -> `flutter-data-persistence`
- Persisted schema changes across app updates -> `flutter-local-db-migration`
- Timeouts, retries, cancellation, offline behavior -> `flutter-networking`, `flutter-reliability`
- Crash reporting and error zones -> `flutter-observability`, `flutter-error-handling`
- Deep links, redirects, route guards -> `flutter-navigation-patterns`
- Native bridges and permissions -> `flutter-platform-channels`
- Flavors, signing, symbols, size -> `flutter-build-release`

### First-PR safe zones

Scope to the observed layout rather than the generic list. In a feature-first repo that means a file under `lib/features/<feature>/presentation/`; in a layer-first repo, a widget under `lib/widgets/`.

Generic safe zones (replace with concrete paths from the tree):

- A new widget in the feature's presentation folder plus its widget test
- A new field on an existing model, with codegen rerun - check whether it also needs a local DB migration
- A new string in the ARB files

Riskier: `main.dart` and bootstrap, router configuration (global), Dio interceptors (every request), the Drift schema, `android/` and `ios/` native config, CI workflows.

## Output Format

Inject into `task-onboard` as Markdown sections in this exact order and shape. Flag inferred items as `(inferred)` rather than fabricating values not visible in the tree.

```markdown
### Stack and Tooling
- **Flutter:** 3.27.1 (pinned in `.fvmrc`); **Dart:** SDK `>=3.5.0 <4.0.0`
- **State:** Riverpod (`flutter_riverpod` + `riverpod_generator`)
- **Navigation:** go_router (`lib/core/router/app_router.dart`)
- **Networking:** Dio + retrofit; interceptors in `lib/core/network/`
- **Persistence:** Drift (schema v7), `flutter_secure_storage` for tokens
- **Models:** freezed + json_serializable
- **Codegen:** build_runner; output **gitignored** - must run before the first build
- **l10n:** gen_l10n via `l10n.yaml`, ARB in `lib/l10n/`
- **Platforms:** android, ios (a `web/` folder exists but no CI job builds it - stale)
- **Observability:** Firebase Crashlytics + Analytics
- **Test:** flutter_test, integration_test, mocktail; goldens under `test/goldens/`
- **CI:** GitHub Actions - analyze, test, build appbundle for stg/prod

### Local Bootstrap
- `fvm flutter pub get`
- `dart run build_runner build --delete-conflicting-outputs` (required - output is gitignored)
- Obtain `google-services.json` / `GoogleService-Info.plist` from the team (gitignored)
- `fvm flutter run --flavor dev -t lib/main_dev.dart`
- Verify: app opens the login route; `flutter analyze` and `flutter test` clean

### Flavors
| Flavor | Entry | Config | Android applicationId | iOS scheme |
| ------ | ----- | ------ | --------------------- | ---------- |
| dev | `lib/main_dev.dart` | `config/dev.json` | `com.acme.app.dev` | `dev` |
| prod | `lib/main_prod.dart` | `config/prod.json` | `com.acme.app` | `prod` |

### Architecture Map
- Entry: `lib/main_<flavor>.dart` (thin; shared setup in `lib/bootstrap.dart`)
- Layout: **feature-first** under `lib/features/{auth,orders,profile}/{data,domain,presentation}/`
- Shared: `lib/core/{network,router,theme,storage}/`
- Data layer: repository per feature over Dio remote + Drift local
- State: Riverpod notifiers in each feature's `presentation/providers/`

### Conventions
- Screens are `ConsumerWidget`; side effects via `ref.listen` (inferred)
- Failures modeled as freezed sealed classes in `lib/core/error/`
- Generated files are never hand-edited
- Strings come from ARB; hardcoded UI text is a review finding (inferred)

### Risk Hotspots
- Drift schema v7 with no committed snapshots (`flutter-local-db-migration`)
- Auth-refresh interceptor is global to every request (`flutter-networking`)
- Deep-link handlers in the router take untrusted input (`flutter-navigation-patterns`)
- `web/` target unbuilt and untested (`flutter-build-release`)

### First-PR Safe Zones
- New widget + widget test under `lib/features/profile/presentation/`
- New ARB string, both locales
- Avoid for a first PR: `lib/bootstrap.dart`, `lib/core/router/`, `lib/core/network/`, the Drift schema, `android/`, `ios/`
```

## Avoid

- Assuming Riverpod, go_router, Dio, or Drift when `pubspec.yaml` does not declare them
- Listing dependencies verbatim instead of classifying them by role
- Reporting a platform folder as a supported target without checking flavors and CI
- Omitting the codegen step from bootstrap when its output is gitignored
- Treating generated files as source, or citing `*.g.dart` / `*.freezed.dart` as evidence of project convention
- Ignoring `fvm` or `melos` when present - the bare `flutter` command may be the wrong version or skip workspace linking
- Fabricating flavor names, application ids, endpoints, Firebase projects, or CI secret values
- Backend framing: there is no server, connection pool, deploy window, or health endpoint here
