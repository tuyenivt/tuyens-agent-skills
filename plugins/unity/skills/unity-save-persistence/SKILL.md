---
name: unity-save-persistence
description: "Design durable Unity saves: format choice, atomic writes, corruption recovery, schema migration, cloud conflicts, PlayerPrefs and WebGL limits."
metadata:
  category: mobile
  tags: [unity, save, persistence, serialization, migration, atomic-write, playerprefs, cloud-save, webgl, mobile]
user-invocable: false
---

# Unity Save Persistence

> Confirm the project's target platforms first - they decide which path and durability guidance applies. This skill owns **save format, durability, and migration**. Tamper resistance and integrity signing belong to `unity-security-patterns`; what Unity's serializer does to scene and prefab assets to `unity-serialization-prefabs`; what save state is shaped like in the rules layer to `unity-architecture-patterns`.

## When to Use

- Designing or reviewing a save system for a new game
- A player reports lost progress, a reset profile, or a save that will not load
- Shipping an update that changes the save model
- Adding cloud save, or a second device to an existing single-device save
- Targeting WebGL and needing persistence that survives a page reload

## Rules

- **PlayerPrefs is never the primary save store.** It is a registry key on Windows, a plist on macOS/iOS, and shared preferences on Android - trivially editable by the player, size-limited, and wiped by common uninstall/clear-data paths. It is for non-critical local preferences only: volume, last locale, tutorial-seen flags
- **Every save write is atomic.** Write to a temp file, flush, then replace the real file. A process kill mid-write must never leave a truncated save - the OS kills backgrounded mobile apps routinely and without warning
- **Every save carries an explicit schema version field**, written from the first release. A save without a version cannot be migrated later without guessing
- **An old save must load in a new build.** Players update from any prior version and old versions stay installed on devices for years. Migration runs forward from whatever version was read
- Load must survive a corrupt, truncated, empty, or unreadable file without crashing or silently starting a new game as if nothing was lost
- Save to `Application.persistentDataPath` and never to a hardcoded path or `Application.dataPath`, which is read-only on most platforms
- Save data is the rules layer's state, serialized through an explicit DTO. Never serialize MonoBehaviours, scene references, or engine types into a save
- Cloud save needs a stated conflict-resolution rule chosen before shipping, not discovered when two devices disagree
- **On mobile, `OnApplicationPause(true)` is the save point, not `OnApplicationQuit`** - the OS kills a backgrounded app without delivering quit. Mark state dirty on mutation and flush at checkpoints plus pause. Atomic writes protect the save's integrity; checkpoint spacing bounds how much a foreground crash loses - space checkpoints by what a player would mind losing, not per mutation

## Patterns

### Choosing a format

| Store | Use for | Durability | Player-editable |
| --- | --- | --- | --- |
| JSON file in `persistentDataPath` | the primary save - progress, board state, currency, inventory | durable with atomic write | yes, plainly - integrity is `unity-security-patterns` |
| Binary file in `persistentDataPath` | large saves where parse time or size is measured as a problem | durable with atomic write | yes, with slightly more effort |
| `PlayerPrefs` | volume, locale, tutorial flags - anything a player losing costs nothing | not durable, wipeable, size-limited | yes, trivially |
| Cloud save service | cross-device continuity and reinstall recovery | depends on service and sign-in | server-side rules apply |

JSON is the default: human-readable when debugging a player's corrupted save, diffable, and trivially versionable. `JsonUtility` is engine-fast but limited - no dictionaries, no polymorphism, no nullable primitives, and it serializes fields, not properties. A third-party JSON serializer handles those at the cost of reflection, which **managed code stripping can break in any player build stripped above Minimal unless the types are preserved** (`unity-build-release`). That failure never appears in the editor.

Binary is not a security measure. It is a size and parse-time measure, and only after measuring.

### Atomic write and corruption recovery

```csharp
// Bad - a kill mid-write leaves a truncated file and the save is gone
File.WriteAllText(savePath, json);

// Good - the real file is only ever replaced by a complete, flushed temp file
var tmp = savePath + ".tmp";
using (var fs = new FileStream(tmp, FileMode.Create, FileAccess.Write)) {
    var bytes = Encoding.UTF8.GetBytes(json);
    fs.Write(bytes, 0, bytes.Length);
    fs.Flush(true);                                   // on disk before the swap
}
if (File.Exists(savePath)) File.Replace(tmp, savePath, savePath + ".bak");
else File.Move(tmp, savePath);                        // first save: Replace throws without a destination
```

The invariant: a complete save always exists at the main path or its `.bak`, never only a partial one (on platforms where `Replace` is two renames, a kill between them leaves only `.bak`, which the load order below recovers). After a load recovered from `.bak`, move the unreadable main file aside (`save.corrupt`) before the next write, or that write rotates it over the good backup.

Load order on start: try the main file; on parse failure or a failed integrity check, try the backup; if both fail, start fresh **and tell the player**, rather than silently presenting an empty profile as normal.

```csharp
// Bad - a corrupt file reads as "no save", and the player's progress vanishes without a word
if (!File.Exists(path)) return NewGame();
try { return JsonUtility.FromJson<SaveData>(File.ReadAllText(path)); } catch { return NewGame(); }

// Good - distinguish "no save" from "unreadable save"
if (!File.Exists(path) && !File.Exists(path + ".bak")) return NewGame();
if (TryLoad(path, out var s) || TryLoad(path + ".bak", out s)) return s;
return NewGameAfterCorruption();   // surfaces a message; keeps the bad file for diagnosis
```

Whether `File.Replace` and flush semantics guarantee durability against a device power loss is filesystem- and platform-dependent; the pattern protects against process kill, which is the mobile case that actually happens. Preserve the unreadable file rather than deleting it - it is the only evidence for the bug report.

### Schema versioning and migration

```csharp
// Bad - no version; every future change is a guess about what shape this is
[Serializable] public class SaveData { public int coins; public int[] board; }

// Good - version is the first field and is written from release 1
[Serializable] public class SaveData {
    public int schemaVersion;   // set to SaveSchema.Current when writing; no initializer, so a missing key reads 0
    public int coins;
    public int[] board;
}
```

Migration runs as an ordered chain from the file's version up to current, each step handling one bump. Chained single-version steps stay testable; a single branch per old-version-to-current does not.

| Change | Migration needed |
| --- | --- |
| Added a field with a usable default | Deserializer default may suffice - still bump and state the default explicitly |
| Renamed a field | Yes - read the old name, write the new one. A rename with no migration reads as data loss |
| Changed a field's type or units (seconds to milliseconds, int to long) | Yes - silent misinterpretation is worse than a load failure |
| Removed a field | Bump; ignore the old key on read |
| Restructured (flat currency fields into a dictionary) | Yes, explicitly |

Rules that hold regardless of the change: never renumber existing versions; keep migration steps forever, because a player can return after a year on an ancient version; test migration with a real saved file from each shipped version, kept as a fixture; where releases shipped before versioning began, pin "version field absent" to mean the last unversioned shape and make it the chain's first step, never a per-load guess; and treat a save whose version is **newer than the build** as a distinct case - it happens when a player downgrades or restores a backup from a newer install, and the correct behaviour is to refuse and explain, never to load it as if the fields matched.

### Storage paths per platform

`Application.persistentDataPath` is the only correct root, and it resolves per platform: an app-container path on iOS, app-specific external storage on Android (`Android/data/<package>/files`, internal storage when external is unavailable), a user-profile application-data path on desktop, and a virtual IndexedDB-backed path on WebGL. Never build a path by string concatenation with platform assumptions baked in, and never write to `Application.dataPath` (read-only in a build on most platforms) or `StreamingAssets` (read-only, and compressed inside the APK on Android).

Two consequences worth designing around: the path is not stable across reinstall on all platforms, so it is not a device identity; and on iOS, files in the wrong container subdirectory are backed up to iCloud when they should not be, or excluded when they should not be - see below.

### Cloud save and conflict resolution

Two devices playing offline will produce two divergent saves. The resolution rule must be chosen deliberately:

| Rule | Fits | Cost |
| --- | --- | --- |
| Last-write-wins by server timestamp | simple linear progress | silently discards the other device's session |
| Highest-progress-wins (a monotonic score: level, total currency earned) | most casual/puzzle progression | needs a genuinely monotonic metric; loses non-monotonic state |
| Field-level merge | idle games with independent counters | most work; needs per-field merge semantics |
| Ask the player | anything where either side may be the one they want | a UI surface, and a player who picks wrong |

Never trust the **device clock** for last-write-wins - a player can change it, and a wrong device clock will hand victory to the stale save permanently. Use the service's server-assigned timestamp or a monotonic save counter incremented on every write.

Cross-device continuity needs an identity that survives reinstall: anonymous sign-in is per-install, so link a platform account (Google Play Games, Game Center) before promising it, and keep a build with no platform account (a WebGL demo) on a separate, local-only profile with no cloud sync. Local save stays authoritative during play; cloud sync happens at defined points (launch, resume, deliberate save), and a sync failure is not a reason to block play. Cloud save is also not a backup of a corrupt local save - validate before upload, or corruption propagates to every device.

### WebGL persistence

WebGL writes go to a browser-backed virtual filesystem in memory, persisted to **IndexedDB**, and the flush is asynchronous. A write that returned is not necessarily persisted - close the tab before the sync completes and it is gone.

- File writes to `persistentDataPath` reach IndexedDB only after a filesystem sync: set `autoSyncPersistentDataPath: true` in the loader config passed to `createUnityInstance` (manual `JS_FileSystem_Sync()` is deprecated)
- IndexedDB is per-origin and cleared by ordinary browser privacy actions, private browsing, and storage-pressure eviction. Treat WebGL local persistence as a convenience, not durable storage; anything valuable needs a server-side save
- `System.IO` durability guarantees do not apply. Nothing survives an origin wipe
- Save at meaningful checkpoints and sync explicitly rather than relying on unload handlers, which browsers do not reliably run

### Platform backup interaction

iCloud (iOS) and Android Auto Backup will, by default, include app data and restore it onto a new device. Two failure modes follow:

- **Unwanted backup**: large caches and re-downloadable content inflate the user's backup quota. Keep them in `Application.temporaryCachePath`, not beside the save; on iOS, `UnityEngine.iOS.Device.SetNoBackupFlag(path)` excludes a file that must stay in the backed-up container
- **Unwanted restore**: a restored save arrives on a device that never played, and can arrive *older* than a cloud save, or newer than the installed build (the newer-than-build case above). Restore-aware games validate the save's version and reconcile against cloud state on first launch rather than assuming local is current

Backup restore also duplicates any device-local identifier stored in the save. Anything meant to be per-install must be derived at first run, not persisted and restored.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {FormatChoice | PlayerPrefsMisuse | AtomicWrite | CorruptionRecovery | SchemaVersion | Migration | SavePoint | StoragePath | CloudConflict | WebGLPersistence | BackupInteraction}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {what the player loses - "kill during autosave truncates the file and wipes progress", "v1 save fails to load in v2 with no migration path"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

`SavePoint` covers when saving happens: a save that depends on `OnApplicationQuit`, a load path never wired, or checkpoints spaced so a crash loses more than a player would accept. `FormatChoice` also covers what the save holds: an incomplete DTO, or engine types inside it.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = progress lost with no way back, or made unloadable (a non-atomic write, a save point that misses the mobile kill, a missing migration for a shipped shape change, primary progress in PlayerPrefs, a corrupt save deleted rather than kept). High = recoverable data loss, a corrupt save handled as a fresh start without telling the player while the bad file is kept, or a save model with no `schemaVersion` before its first shape change. Medium = a durability or conflict gap on a path that is reachable but uncommon, or writes far more frequent than the loss bound needs. Low = a hygiene issue with no data-loss path. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: save integrity signing -> unity-security-patterns`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No persistence findings.` |
| A review was requested with nothing to judge | `Persistence check not run: no source supplied.` |

## Avoid

- PlayerPrefs holding progress, currency, inventory, or anything a player would file a ticket about losing
- `File.WriteAllText` straight over the live save file
- A save model with no `schemaVersion` field
- Migration written as one branch from every old version to current, rather than an ordered chain
- Deleting or overwriting a save that failed to parse, instead of preserving it for diagnosis
- Treating "file missing" and "file unreadable" as the same outcome
- Hardcoded paths, `Application.dataPath`, or writes into `StreamingAssets`
- Device-clock timestamps deciding a cloud save conflict
- Uploading a local save to cloud without validating it first
- Assuming a WebGL write is persisted when the call returned
- Serializing MonoBehaviours, scene references, or engine types into save data
- Relying on reflection-based serialization in a player build stripped above Minimal without preserving the types
