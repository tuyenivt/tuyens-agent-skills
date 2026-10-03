---
name: unity-build-release
description: "Ship Unity builds safely: IL2CPP stripping reflection hazards, app bundles, iOS signing, WebGL hosting, Addressables catalogs, batch-mode CI."
metadata:
  category: mobile
  tags: [unity, build, release, il2cpp, code-stripping, addressables, android-app-bundle, ios-signing, webgl, ci, build-size]
user-invocable: false
---

# Unity Build Release

> Confirm the project's target platforms first - they decide which of the packaging, signing, and hosting guidance applies. This skill owns **the build and its shipped artifact**. Build-time configuration (what ships, how it is stripped, compressed, and packaged) is this skill; runtime budget (what it costs once running) is `unity-performance`. A texture that is too large ships here and costs there - report the import/packaging half, defer the memory-budget half. Runtime frame and memory cost belong to `unity-performance`; save durability to `unity-save-persistence`; secrets in game code and tamper exposure to `unity-security-patterns` - signing and store credentials in the repo or `ProjectSettings` are this skill's.

## When to Use

- Setting up build configuration, signing, or CI for a new project
- A bug appears only in a device build and never in the editor
- Preparing a store submission, or shipping content without a store release
- Cutting download size, or diagnosing where the size went
- Adding WebGL as a target

## Rules

- **Anything reflection-based must be preserved against managed code stripping.** IL2CPP strips code the linker cannot see referenced, and reflection is invisible to it. This is the single most common ship-breaking Unity bug - it never reproduces in the editor
- **Test every release-configuration change on a release build on a device.** The editor differs from the shipped artifact in scripting backend, stripping, and optimization; a development build differs in optimization and instrumentation, and in backend or stripping only where its profile overrides them
- **Performance numbers come from a non-development build.** Development builds carry profiler instrumentation and reduced optimization; a frame time measured there is not the shipped frame time (`unity-performance`)
- Android ships as an **app bundle** to Play. A universal APK ships every architecture and locale to every device
- The build number (Android `versionCode`, iOS `CFBundleVersion`) increases on every submitted build and is set by CI, not by hand; the marketing version string changes per release
- Signing credentials, keystores, and store API keys live in CI secrets. Never in the repo, never in `ProjectSettings`
- CI builds run headless, non-interactive, and fail loudly: `-batchmode -nographics -quit` with a non-zero exit on error, and licence activated and released around the build
- A remote content catalog and the build that loads it are a **matched pair**. Shipping one without the other breaks live players

## Patterns

### Build targets and build profiles

Build Profiles (which replaced the Build Settings window in the Unity 6 line, and are the shipped surface on the 6.3 LTS floor) hold per-target scene lists, scripting defines, and player-setting overrides as assets in the project. That makes configuration reviewable in a diff instead of living in one developer's editor state.

Keep at minimum a development profile (development build, profiler, deep-ish diagnostics) and a release profile (stripping on, no development flag, store signing) per target. The divergence between them is exactly where release-only bugs live, so the release profile must be built and smoke-tested regularly, not first on submission day.

CI selects the active profile with `-activeBuildProfile <asset path>`. Note this conflicts with passing `-buildTarget` in the same invocation - some CI templates still pass `-buildTarget` by default, and the combination errors. Confirm which your CI tooling supplies before wiring both.

### IL2CPP, stripping, and the reflection hazard

IL2CPP converts IL to C++ and is required on iOS, Android 64-bit, and WebGL. Managed code stripping runs with it and removes types and members the linker cannot prove are used.

| Stripping level | Behaviour |
| --- | --- |
| Disabled | Mono only; nothing stripped |
| Minimal | IL2CPP's lowest level and default; strips Unity and .NET class libraries, never your assemblies |
| Low / Medium | progressively more assemblies searched for unreachable code |
| High | most aggressive; most likely to remove a reflection target |

The failure mode is specific and confusing: **from Low stripping upward, reflection-based JSON deserialization silently loses fields, or throws a missing-method/missing-type exception, in the player build and never in the editor.** The linker saw no static reference to the type or its members and removed them.

```csharp
// Bad - fields populated by a reflection-based serializer, nothing statically references them
public class SaveData { public int coins; public int[] board; }

// Good - type, constructor, and every field the serializer reads survive (using UnityEngine.Scripting)
[Preserve] public class SaveData { [Preserve] public int coins; [Preserve] public int[] board; }
```

The two preservation mechanisms:

- `[UnityEngine.Scripting.Preserve]` on the type and on each member a reflection path reads - precise, lives next to the code it protects. On a type alone it keeps only the type and its default constructor
- `link.xml` - preserves whole assemblies, namespaces, or types by name. Every `link.xml` under `Assets/` merges automatically; a UPM package's own `link.xml` is ignored unless the package supplies it through `IUnityLinkerProcessor` or embeds it in its assembly. `preserve="all"` on an assembly is the blunt fix; scope it down once the build is green

```xml
<linker>
  <assembly fullname="Game.Save" preserve="all"/>
</linker>
```

What needs preserving: save/DTO types and their members deserialized by reflection, types resolved by `Type.GetType` or by name from data, and third-party SDK entry points invoked by native code.

A generic instantiation only ever built via reflection - `Dictionary<string, ItemState>` constructed by a JSON deserializer, say - was never compiled ahead of time. Since 2022.1, IL2CPP's full generic sharing runs it through a shared fallback body, so it works, more slowly; a static reference in shipped code (a field, or a dummy method naming the closed type) makes the compiler emit the fast version. The element types (`ItemState`) still need preserving either way.

Raising the stripping level is a build-size lever with a correctness cost. Raise it one step at a time and **re-run a full smoke test of save/load, IAP, ads, and analytics on a device build after each step** - these are exactly the reflection-heavy surfaces.

### Android packaging

| Artifact | Use | Note |
| --- | --- | --- |
| App Bundle (`.aab`) | Play store submission | required for new Play apps; the store generates per-device APKs, cutting download size |
| APK | direct distribution, testing, other stores | a universal APK carries every ABI and every density |
| Split APKs by ABI | direct distribution where a bundle is unavailable | one artifact per architecture |

- **Target API level** is set by store policy and moves annually; Play rejects submissions below the current floor. Read the current requirement rather than trusting a number written here or in an older project
- **Minimum API level** is a market-reach decision. Lower reaches more devices and drags in older, slower hardware that will fail the performance targets - decide it with the device tier the game is actually built for
- ARM64 is mandatory for Play. Shipping ARMv7 alongside it roughly doubles the native code in the bundle (players still download one ABI), so include it only if the min API and target market genuinely need 32-bit
- **Split application binary** moves assets out of the base and is a separate concern from the ABI split
- Keystore in CI secrets; a lost upload keystore is recoverable only through Play's key-reset process, so back it up outside the repo

### iOS signing and provisioning

The Unity build produces an Xcode project; signing happens in the Xcode/`xcodebuild` step, not in Unity. Consequences:

- The bundle identifier, team, and provisioning profile must agree across Unity player settings, the generated Xcode project, and the profile. A mismatch fails at archive time, not at Unity build time
- CI needs the signing certificate and provisioning profile installed into a keychain it unlocks non-interactively; the automation-friendly route is a dedicated CI keychain plus API-key-based upload rather than an Apple ID password
- Post-process build steps (added frameworks, capabilities, plist entries such as usage-description strings and tracking permission) must be scripted, because the Xcode project is regenerated each build. A manual Xcode edit is lost on the next CI run
- Push and Sign in with Apple are capabilities that must be enabled on the App ID *and* present in the profile (IAP needs no profile entitlement); missing entitlements fail at upload or, worse, at runtime on a real device

### WebGL

- **Compression**: Brotli gives the smallest payload and gzip the broader compatibility. Either requires the **server** to send the matching `Content-Encoding` header. Serving Brotli-compressed files with no header is the single most common WebGL deployment failure - the browser downloads bytes it cannot decode and the loader errors. A host whose headers you cannot configure needs Decompression Fallback, at a size and startup cost
- **Memory ceiling**: the WebGL heap is a bounded allocation, and exceeding it is an unrecoverable out-of-memory in the tab, not a degraded frame rate. Texture memory dominates - the mobile-oriented import settings in `unity-performance` matter more here, not less. On 6000.3 the Player settings are Initial Memory Size, Maximum Memory Size, and Memory Growth Mode, with growth capped at 4 GB
- IL2CPP is the only backend and there is no JIT: reflection targets need preserving as on any IL2CPP target, and reflection-only generic instantiations run on the slower shared fallback
- Native-only SDKs (store IAP, mobile ad networks) are excluded from the Web build profile through scripting defines or assembly platform filters
- Remote bundles served from another origin need CORS headers that allow the game's origin
- Managed C# threads are unavailable (at 6000.3, Web multithreading covers native code only), and `System.IO` durability does not apply (`unity-save-persistence`)
- Initial download is the whole loader plus data payload before anything renders; Addressables with a remote catalog is how a WebGL build stops shipping all content up front

### Addressables and remote catalogs

Addressables separates *what is in the build* from *what is downloaded at runtime*, which is what makes content updates without a store release possible.

- **Local groups** ship inside the build. **Remote groups** are hosted and downloaded on demand
- The **catalog** maps addresses to bundles. A remote catalog lets an already-installed build discover new or changed content, provided the build was made with Build Remote Catalog enabled and a remote load path
- Content update requires the **addressables build state from the shipped build** to be preserved (checked into version control or stored as a CI artifact). Without it, a content update rebuilds bundle identity and installed players break. This is the classic Addressables mistake and it is not recoverable after the fact
- Code cannot be shipped this way. A content update delivers assets and data; anything requiring new C# needs a store release
- Bundle a fallback: a remote fetch that fails must leave the game playable
- Version the remote catalog path per build version so an old build keeps loading the content it was built against, rather than pulling a catalog that references bundles it cannot use

The plugin floor is Addressables 2.x: script the pipeline against `AddressableAssetSettings.BuildPlayerContent` and `ContentUpdateScript.BuildContentUpdate`, and read the exact version from `Packages/manifest.json`.

### CI on batch mode

```bash
# Headless build; -quit is required or the editor stays open and the job hangs
Unity -batchmode -nographics -quit \
  -projectPath "$PROJECT" \
  -executeMethod BuildScript.BuildAndroid \
  -logFile - \
  || exit 1
```

- `-nographics` skips GPU initialization on a headless agent. It is not appropriate where the build step needs graphics (some asset processing), so a failure here is a signal to check, not to remove the flag reflexively
- `-logFile -` streams to stdout so CI captures it. A build that writes only to the default log file leaves you with no failure evidence
- **A failed build can still exit zero.** An exception thrown inside `-executeMethod` exits 1, but `BuildPipeline.BuildPlayer` returns a failed `BuildReport` without throwing. The build method checks `report.summary.result` and calls `EditorApplication.Exit(1)` on anything but `Succeeded`
- **Licence activation** runs before the build and **return** runs after, including on failure - an unreleased seat leaks and blocks the next run. Credentials come from CI secrets
- Domain reload and asset import on a cold CI agent dominate build time; a persisted `Library` cache between runs is the main lever
- Determinism: pin the Unity version to the exact internal version from `ProjectSettings/ProjectVersion.txt` (for example `6000.3.4f1`) rather than a floating major or patch
- The release-build device smoke test (save/load, IAP, ads, analytics) is a named pipeline stage or a named manual gate before store upload, not an unstated convention

### Build size analysis

The Editor log written by the build contains a build report: size by asset type and a list of the largest individual assets. Read it rather than guessing.

Typical order of payoff for a casual 2D game: oversized source textures and import max-size settings (usually the largest single line), duplicated assets pulled into multiple bundles by overlapping dependencies, uncompressed or unnecessarily long audio, fonts carrying full glyph coverage for scripts the game does not ship, and unused packages left in `manifest.json`. Stripping level and ABI/architecture choices are code-side levers and are usually smaller than the asset side in these genres.

The number to optimize is the **store download size**, not the artifact on disk - Play and the App Store recompress and, for a bundle, deliver a per-device subset. Compare against the store-reported size after upload.

### Development versus release builds

| Aspect | Development build | Release build |
| --- | --- | --- |
| Profiler / deep profiling | available | not available |
| Script debugging | attachable | off |
| Managed code stripping | at the level its profile sets | at the configured level - where reflection breaks |
| Optimization | reduced | full |
| `Debug.Log` output | visible on device | still executes unless compiled out |
| Frame timings | instrumented, slower | the number that ships |

Use development builds to locate cost and to reproduce logic bugs; confirm both the final frame numbers and every reflection-dependent surface in a release build. A release-only bug that "makes no sense" is stripping until proven otherwise.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, a setting or build profile, a CI script, or a report of a symptom (a CI log, a device crash, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {Stripping | ScriptingBackend | AndroidPackaging | iOSSigning | WebGLHosting | Addressables | CIPipeline | BuildSize | ProfileConfig | Secrets}
- Evidence: {source (the file, setting path, or CI step cited) | inferred (what was not seen)}
- Platform: {Android | iOS | WebGL | Desktop | All}
- Impact: {shipped consequence - "release build fails to deserialize saves", "content update breaks installed players", "universal APK ships every ABI"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the setting path or asset path for a setting or asset; the job and step for a CI finding; a short paraphrase of the reported symptom when nothing was read. A setting that lives in two files is anchored where the fix goes, with the other named in `Impact`.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = the shipped artifact is broken, or a change breaks already-installed players (a stripped reflection target, discarded addressables build state, a signing credential in the repo). High = a store rejection, a build CI cannot reproduce, a pipeline that can report success on a failed build, or a size or configuration defect on the primary target. Medium = a maintainability or size gap with a known workaround, or a CI licence seat not returned on failure. Low = a hygiene issue with no shipped consequence. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; a CI log is source for what it records (the flags passed, the result line) and inferred for the code behind it, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a file named but not supplied, or a read line whose band turns on something unseen (the stripping level, which assets ship); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: memory budget of remote content -> unity-performance`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, a setting, a CI script, or a symptom report was supplied, and it yields no finding | `No build findings.` |
| A review was requested with nothing to judge | `Build check not run: no source supplied.` |

## Avoid

- Reflection-based serialization with no `[Preserve]` or `link.xml` coverage
- Raising the stripping level without re-smoke-testing save, IAP, ads, and analytics on a device build
- Testing only in the editor or only in a development build before submission
- Reporting a frame time from a development build as the shipped number
- A universal APK where an app bundle is available
- Manual Xcode project edits that the next build regenerates away
- Serving Brotli or gzip WebGL builds without the matching server `Content-Encoding` header
- Discarding the addressables build state from a shipped build
- Shipping a remote catalog update that the installed build cannot load
- `-batchmode` without `-quit`, or a build method that never checks `report.summary.result`
- Licence activation with no matching return on the failure path
- Keystores, certificates, or store API keys committed to the repo
- Hand-incremented version codes
- Guessing which asset is large instead of reading the build report
- Asserting a store API level requirement or an Addressables API from memory instead of checking the current policy and package version
