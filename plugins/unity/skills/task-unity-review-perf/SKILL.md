---
name: task-unity-review-perf
description: Unity 2D mobile perf review - GC allocation spikes, Update cost, pooling, draw calls and batching, overdraw, texture memory, UI repaint, load time.
agent: unity-performance-engineer
metadata:
  category: mobile
  tags: [unity, csharp, performance, gc-allocation, frame-budget, batching, overdraw, texture-memory, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Unity Performance Review

Client-side perf review naming the Unity idiom: managed allocation in the steady frame loop, `Update` invoked across hundreds of objects, `Instantiate`/`Destroy` where a pool belongs, batches split by material variants, overdraw from stacked transparent 2D sprites, texture import settings that decide runtime memory, UI Toolkit panel repaint, and synchronous scene load. Every finding states player-visible impact and labels its evidence.

## When to Use

- Unity perf regression review of the current change set
- Stutter, hitches, dropped frames, or thermal/battery complaints on a target device
- A game that runs on a flagship and badly on a budget phone
- Slow scene load, slow cold start, or runtime memory growth across a session
- Build size or texture memory growth
- Pre-release perf pass on the gameplay loop, a spawn path, or a new UI screen

**Not for:** general review (`task-unity-review`), security (`task-unity-review-security`), pre-implementation design (`task-unity-implement`).

**Out-of-lens defects are routed, never dropped.** Perceived slowness that is actually a missing loading state, an unhandled offline path, or a permanent spinner is not a perf finding, and neither is a correctness, security, or build-configuration defect the review reads along the way. Each becomes one `## Routed` line naming the workflow that owns it: `task-unity-review` for correctness (a `?.` on a `UnityEngine.Object`), build configuration, and over-engineering (a pool around a single instance, an unmotivated ECS proposal); `task-unity-review-security` for security (a committed keystore password, a client-side grant). A Routed line for code outside the change set ends with `(pre-existing)`. Standalone, each Routed line also becomes a `[Delegate]` Next Step.

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | A capture supplied (device Profiler session, Memory Profiler snapshot, Frame Debugger capture, build report), a perf-critical release, or a parent that passes `deep` | All + a top-level `## Device & Measurement Plan` section |

## Measurement Discipline

- **The Profiler attached to a development build on a real target device is the only valid timing source for finding cost.** Editor Play mode runs extra tooling, often on a different scripting backend than the shipped build (typically IL2CPP), and hides device thermal and GPU limits. An editor number is not evidence.
- **A development build is where you find cost, not where you confirm it.** Profiler instrumentation, and Script Debugging or Deep Profiling Support when enabled, inflate it; the shipped number comes from a non-development build.
- **State the frame budget the project actually targets** - 33ms at 30fps, 16ms at 60fps. Read the `Application.targetFrameRate` call site, opening the unchanged file that sets it. Where it is set nowhere, mobile runs at the platform default of 30fps: grade against **33ms** and record `not set - platform default 30fps`, with no finding. On desktop an unset target follows the display rate while `vSyncCount` (per quality level, `ProjectSettings/QualitySettings.asset`) is above 0 and runs uncapped when it is 0; WebGL follows the browser's frame callback. Record `display rate (VSync)` or `uncapped`. An uncapped desktop target is a finding only when the change set touches frame pacing or quality settings - anchored at `QualitySettings.asset` or the bootstrap script, Owner CPU, Medium `[Recommend]`; High `[Recommend]` when a reported thermal or pacing symptom exists - and an `## Unattributed` entry otherwise.
- **Attribute before fixing.** Every finding names CPU (main thread), GPU (fill rate or draw calls), GC, memory, or load as its owner. The wrong fix costs the same effort as the right one.
- **Impact, not adjective.** "500 `Update` calls per frame on tiles that change once a move" is a finding. "This is slow" is not.

## Excluded Surfaces

Not review surface: `Library/`, `Temp/`, `obj/`, `Build/`, `Logs/`, generated `*.csproj` and `*.sln`, and imported third-party SDK sources (`Assets/Plugins/` and the vendor folders a `.unitypackage` installs). Do not raise a finding *on* a `.meta` file; when a `.meta` carries the defect (an import setting), cite the asset it describes. In subagent mode this list governs this lens.

**Assets are review surface.** `.unity` scenes, `.prefab`, `.asset`, and `.spriteatlasv2` files are reviewable - a texture import setting, a prefab with 300 `Update`-bearing children, or a duplicated material on a prefab variant is a legitimate finding cited at the asset path.

## Invocation

`/task-unity-review-perf [<branch>|pr-<N>] [standard|deep] [--base <branch>]`

Defaults to the current branch vs its base; `pr-<N>` reviews a locally fetched PR ref. `review-precondition-check` fails fast on a dirty working tree and on a trunk head - review compares committed code only; this workflow's own `review-perf-*.md` checkpoint at the repository root does not count as dirt.

**Never modify the working tree.** Read-only git only: `git diff`, `git show`, `git grep`, `git log`, `git rev-parse`, `git ls-tree`. A file's content at the head is read with `git show <head_ref>:<path>` whenever the head is not the checked-out branch.

**Citations, every mode.** A `file:line` is the line number inside that file at the head - read it from the file (`git show <head_ref>:<path>`), or count from the `+<start>` of the hunk header `@@ -a,b +<start>,c @@` - never a line number of the diff output or of a prompt.

When invoked as a subagent (e.g. by `task-unity-review`), the parent supplies the resolved `base_ref` / `head_ref`, the pre-read diff, name-status, and commit log, the depth level, the detected project shape, and its reviewable-surface table: Step 3 is skipped and the diff is not re-read, but `git show <head_ref>:<path>` stays available for Step 4's reads of unchanged files. Step 11 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles` - as a subagent too, unless the spawning prompt inlined its Rules.

### Step 2 - Stack and Project Shape

Accept the project shape from the parent when invoked as a subagent, and derive any field below the parent did not supply. Otherwise read `ProjectSettings/ProjectVersion.txt`; if it is absent, stop - this workflow reviews Unity projects only.

After Step 3's round gate has passed, record, each from its source at the head: engine version (`ProjectVersion.txt`, internal form, e.g. `6000.3.21f1`; the marketing name for any `6000.<minor>` is `Unity 6.<minor>`); render pipeline (the pipeline asset assigned in `GraphicsSettings.asset` / `QualitySettings.asset` and its renderer - a URP package in the manifest only proves it is installed); scripting backend (`ProjectSettings/ProjectSettings.asset`); target frame rate (Measurement Discipline); Addressables presence (`Packages/manifest.json`); UI system (`UIDocument` vs `Canvas` components and `.uxml` assets - the manifest lists both UI packages in a default project); platform targets (Build Profiles under `Assets/Settings/Build Profiles/`, or the per-platform override blocks). A field its source cannot settle is `unknown - <what was seen>`.

**Engine floor is Unity 6.3 LTS (`6000.3.x`).** Compare numerically. Below the floor, state the mismatch and stop rather than emitting guidance the project cannot apply. At or above it (`6000.3.x`, `6000.4.x`, and later) proceed. If `ProjectVersion.txt` is unreadable, say so and proceed with version-independent findings only.

Record a uGUI project as out of scope for the UI step rather than reviewing it under UI Toolkit rules.

### Step 3 - Resolve the Change Set

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-perf`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). Surface any fail-fast verbatim and stop.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface beyond `ProjectVersion.txt`: a valid `prior_checkpoint` whose `head_sha` and `base_sha` both equal the captured ones and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits since prior perf review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (Step 11 overwrites the file) -> `round: 1`, no `prior_head_sha`. On round 2+, the Summary's Round line adds `base advanced since round <N>` when `base_sha` differs, or `same head; re-review at deeper depth` when only the depth changed.

Then read once and reuse:

- `git diff <base_ref>...<head_ref>` for the change body
- `git diff --name-status <base_ref>...<head_ref>` for the file list
- `git log <base_ref>..<head_ref>` for the commit messages Step 10's intent test reads

Restrict findings to the changed paths outside Excluded Surfaces, plus the unchanged code Step 4 follows them into. A binary asset git reports as `Binary files differ` is not diffed - its `.meta` carries the reviewable import settings.

**Skip entirely** when invoked as a subagent and the parent passed the refs plus the pre-read diff.

**No-op exit.** When the change set touches only excluded surfaces, write no report: state `No reviewable change in this change set - <reason>` and stop. Do not manufacture findings from unchanged code.

A `.meta`-only change set is not automatically a no-op. Import settings are a primary review surface (Step 8), so read the `.meta` changes: an import-setting delta (compression, max size, mip generation) is reviewable and the review proceeds, cited at the asset. Importer-version churn with no setting delta is a no-op; a changed `guid:` line is not - it breaks every reference to the asset and routes to `task-unity-review`.

### Step 4 - Read the Performance Surface

Cite real `file:line` or asset path. Open:

- Every changed `MonoBehaviour` with `Update`, `FixedUpdate`, or `LateUpdate`, and every per-entity loop
- Spawn and despawn paths - `Instantiate`, `Destroy`, and any pool
- Changed scenes and prefabs: component counts, how many objects carry an update callback, duplicated materials, particle systems
- Sprite, texture, and atlas import settings via the asset's `.meta` (max size, compression format, mipmaps) and atlas membership via the `.spriteatlasv2` packables, cited at the asset
- UI Toolkit screens and their `Q`/`Query` call sites and per-frame text assignment
- Scene-load and Addressables call sites, plus the entry scene
- `Packages/manifest.json` for added packages, Build Profile assets, and build settings changed in `ProjectSettings/`

If the diff is small but ripples into unchanged code - a new prefab mounting an existing `Update`-heavy component, or a new spawner calling an existing unpooled factory - read the unchanged file. The regression lives there.

A perf defect found only in unchanged code that this change does not mount or call is not this review's finding: it goes to `## Unattributed` with what would attribute it.

### Step 5 - Allocation in the Frame Loop

Use skill: `unity-performance` for the pattern bank. Use skill: `csharp-unity-patterns` for allocation mechanics.

**This is the dominant mobile Unity perf problem.** Steady per-frame garbage forces collections, and a collection during play is a visible hitch. The target is 0 B in the Profiler's GC Alloc column (`GC.Alloc` marker) on a steady frame.

- [ ] **No string building or interpolation per frame** - a score label assigned every frame allocates every frame; gate on value change
- [ ] **No LINQ, no capturing lambda, no `new` collection** in `Update`, `FixedUpdate`, `LateUpdate`, or a per-entity loop
- [ ] **Buffers and collections reused across frames** - cleared, not reallocated
- [ ] **Non-allocating query overloads with a preallocated buffer** for physics and component queries; the `*All` overloads allocate an array per call
- [ ] **No boxing in a hot path** - a `struct` converted to `object` or to any interface type boxes; pass it through a generic `T : IInterface` parameter instead
- [ ] **Incremental GC is not the fix.** It is on by default where the platform supports it (not WebGL); it splits one hitch into several and does not reduce the garbage, so relying on it while allocating per frame converts a stall into sustained frame-time noise

```csharp
// Bad - a string allocated every frame whether or not the score changed
void Update() { label.text = $"Score: {score}"; }

// Good - allocation only when the displayed value changes (_shown starts at -1)
void Update() { if (score != _shown) { _shown = score; label.text = $"Score: {score}"; } }
```

### Step 6 - Update Cost and Instantiation

- [ ] **`Update` count is bounded.** Each `Update` is a native-to-managed interop call per object per frame before the body does anything. Hundreds of tiles each polling a dirty flag is the classic 2D case - tick them from one update manager over a plain interface list
- [ ] **Empty `Update` / `FixedUpdate` / `LateUpdate` bodies deleted**, not left as placeholders - the interop call still costs
- [ ] **Event-driven state is not polled** - work that changes on a move should not run every frame
- [ ] **Pooling on any repeated spawn path.** `Instantiate`/`Destroy` in a spawn loop or per-frame path hitches on wave start and produces destroy garbage. `UnityEngine.Pool.ObjectPool<T>` ships with the engine, so a hand-rolled pool needs a reason
- [ ] **Pooled objects fully reset on get or release** - partial reset leaks state across reuse and is a correctness bug, not just a perf one
- [ ] **Pool pre-warmed at load** rather than paying the first `Instantiate` mid-gameplay
- [ ] **No pool around a single instance or a rarely-spawned object** - that is indirection for no measured gain; route it to `unity-overengineering-review`

### Step 7 - Draw Calls, Batching, and Overdraw

Use skill: `unity-2d-rendering` for atlas, sorting, and material specifics.

- [ ] **No material duplicated per instance to change one colour or tint.** `renderer.material` clones a material per object - a leak and, off the SRP Batcher path, a batch split. Tint through `SpriteRenderer.color`, the built-in per-renderer channel, on one shared material; `SetPropertyBlock` removes a renderer's SRP Batcher compatibility and is not the batch-safe fix
- [ ] **Sprites drawn together share an atlas page** - two sprites from different atlases cannot be merged into one draw by dynamic sprite batching, and an overflowed atlas silently splits into a second page
- [ ] **Sorting order does not interleave objects from different atlases**, which forces a state change between each and defeats a batch that "should" merge
- [ ] **Overdraw bounded on the primary mobile tier.** Transparent sprites do not depth-reject: cost scales with layers times screen coverage, it is invisible in a draw-call count, and it is the usual reason a game runs fine on a flagship and badly on a budget phone
- [ ] **Large backgrounds drawn opaque**, sprite meshes tightened so the quad is not mostly alpha border, particle count and size bounded
- [ ] **Fully covered UI screens deactivated, not left rendering behind a popup**
- [ ] **Batching claims confirmed in the Frame Debugger**, which names the reason a batch broke

### Step 8 - Texture Memory, Physics, and UI Repaint

- [ ] **Import settings decide runtime memory, not the source file size** - a small PNG uploads uncompressed if the import format says so
- [ ] **Max size matched to the drawn size.** `maxTextureSize` is a cap, not the imported size: the importer scales the source so its larger side fits the cap, keeping the aspect ratio, and memory is that size times the format's bits per pixel (+~33% with mipmaps). A 2048 source imported at 2048 for a sprite drawn 200px wide wastes memory proportional to the area ratio, and texture memory is usually the largest runtime memory line in a 2D game
- [ ] **Compression format set per platform** - ASTC is the mobile default on current Android and iOS hardware, ETC2 the older-Android fallback, BC/DXT on desktop. Confirm what the platform override actually sets rather than assuming
- [ ] **Mipmaps off for UI and screen-aligned 2D sprites** - a ~33% memory increase for nothing when the sprite is drawn at a fixed scale
- [ ] **Physics 2D absent from board logic.** Grid legality and adjacency are rules-layer array math; physics belongs to projectiles and casual physics toys only
- [ ] **Anything that moves carries a `Rigidbody2D`** (kinematic is fine) - moving a collider with no rigidbody forces static-geometry rebuilds. Collision matrix restricted so impossible layer pairs are not tested
- [ ] **UI Toolkit queries cached at bind time** - `Q<T>()` per frame re-walks the tree. Per-frame text assignment re-tessellates; gate on value change. Off-screen panels detached or hidden rather than left attached and live

### Step 9 - Scene Load, Build Size, and the ECS Question

Use skill: `unity-build-release` when the diff touches build configuration, Build Profiles, Addressables, or packaging.

- [ ] **`SceneManager.LoadSceneAsync` on any path the player waits through** - the synchronous form blocks the main thread for the whole dependency graph and reads as a freeze
- [ ] **Load time attributed to the asset dependency graph**, not scene file size - a prefab referencing a large atlas pulls it in whole
- [ ] **`Resources` contents are eagerly indexed** in ways Addressables content is not; new content added to `Resources` is a load-time and memory finding
- [ ] **Cold start measured on a real device from process start**, not from the editor's first frame
- [ ] **Build-size delta attributed** to what this change added - a new package, an uncompressed asset set, or a texture import change
- [ ] **ECS / DOTS / Jobs / Burst proposed only with a device profile naming that system as the bottleneck.** For casual 2D it is almost never warranted: the measured bottlenecks in these genres are GC, overdraw, and draw calls, none of which ECS fixes. Burst-compiling one profiled hot job is bounded and reversible; rearchitecting is not. An unmotivated ECS proposal in the diff routes to `unity-overengineering-review`

The composed atomics end with `Deferred: {defect} -> {skill}` lines. One naming a skill this workflow loads resolves at that step; any other becomes a `## Routed` line naming the workflow that loads that skill (`task-unity-review` for `unity-ui-patterns`, `unity-architecture-patterns`, and `unity-overengineering-review`).

### Step 10 - Evidence, Impact, and Intent

Label every finding's evidence. Never present an estimate as a measurement, and never cite an editor Play-mode number at all.

| Evidence | Use when | Example phrasing |
|----------|----------|------------------|
| `measured (device, build)` | A Profiler, Memory Profiler, or Frame Debugger capture from a development build, or a release-build frame-time, memory, or cold-start figure, on a named physical device, **covering the code under review**; a build report's size figure is written `measured (build report)` | `1.4 KB/frame GC Alloc on the cascade resolve, Pixel 6a, development build` |
| `estimated (no profile)` | The pattern is unambiguous but no capture covers it | `500 Update calls per frame across the tile grid` |
| `inferred (what was not seen)` | A finding whose deciding lines were not read - a symptom report, a path named without its content | `inferred (enemy prefab not read)` |

**A capture taken before the change is not a measurement of the change.** It measures the baseline the change lands on. Label findings about the diff `estimated (no profile)` and cite the capture as the baseline in the impact line; reserve `measured` for a condition the capture actually observed. Standalone, a pre-change capture still raises depth to `deep`; in subagent mode the parent's depth governs. A baseline already over budget is stated in the Measurement Basis line; the diff's findings are graded against the budget, and the existing overrun goes to `## Unattributed`.

**Atomic blocks map into this report's fields.** Every composed atomic emits `### [Critical | High | Medium | Low] anchor` blocks; the anchor becomes `Location`.

| Atomic | Categories that map | Field mapping | Routed instead |
| --- | --- | --- | --- |
| `unity-performance` | all | `Evidence`, `Owner`, `Verify` pass through; `Cost` becomes `Player-Visible Impact`, stated as the player experiences it with the figure kept | none |
| `csharp-unity-patterns` | `HotPathAllocation`, `Boxing`, `StringAllocation`, `ClosureCapture`, `CollectionReuse`, `MaterialInstance` | `source` -> `estimated (no profile)`; `Impact` -> `Player-Visible Impact`; this workflow supplies `Owner` and `Verify` | `DestroyedObjectNullCheck`, `AsyncLifetime`, `NullableAnnotation`, `LanguageLevel` |
| `unity-2d-rendering` | `Batching`, `AtlasLayout`, `ImportSettings`, `Overdraw`, `MaterialVariant`, `Tilemap` | same as above | `SortingOrder`, `SortingGroup`, `Lighting2D`, `CameraFit` |
| `unity-build-release` | `BuildSize`, `Addressables` | same as above | every other category |

The same defect raised by several atomics is one finding at the highest band among them. The `Uncapped: Critical.` marker is carried from whichever line the atomic put it on (`Cost` or `Impact`) into `Player-Visible Impact`.

**Severity mapping.** Map `Critical` and `High` to **High Impact**, `Medium` to Medium, `Low` to Low. A `Critical`-origin finding leads the High Impact section and keeps the atomic's rationale (sustained missed frame budget, unbounded memory growth, OOM-risk load on the target tier) in its impact line - do not flatten it into an ordinary High. An `estimated` or `inferred` Critical-origin finding keeps the atomic's `Uncapped: Critical.` wording there. One root cause with one fix is one finding, even across several lines.

**Intent.** Intent never changes a finding's impact tier, which comes from the band. Medium and Low Impact are always `[Recommend]`. For a High Impact finding, intent follows whether the defect's cost is derivable from the change set alone:

| Cost derivable from | Intent | Examples |
| --- | --- | --- |
| The change set itself - the diff, the import setting, the changed asset, or a commit message in the range states every factor, and the arithmetic follows; unchanged files and READMEs outside the range do not count | `[Must]` | per-frame allocation in `Update`; `Instantiate` / `Destroy` per spawn in a loop the diff shows; `renderer.material` cloned per spawned enemy when the atomic bands it High; an uncompressed import of a source whose dimensions the change set states, for a sprite it states is drawn at 96px; 3 or more stacked layers the change set states are full-screen |
| Data only the author or a device has - device tier, board size, atlas contents, the source dimensions behind an import cap, coverage the change set does not state, or whether a duplicate material splits a batch on this pipeline | `[Recommend]`, naming the measurement to run | overdraw of unstated extent; whether an atlas overflows its page; a 4096 cap over a source of unknown size |

`[Must]` at High Impact otherwise requires a measurement.

### Step 11 - Write Report

**Subagent return.** A subagent run returns `## Findings` (with `No performance issues found.` and a `Frame budget:` line when empty), `## Routed` and `## Unattributed` when they have entries, and at `deep` the `## Device & Measurement Plan` - nothing else. No frontmatter, no Summary block, no Recommendations, no Next Steps: the parent owns those and cannot merge two of them. Project-shape values the parent already supplied are not echoed back; the frame budget the findings were graded against goes in the first finding's impact line.

**Round 2+ reconcile (standalone).** Project the prior report (the body of the file at the handle's `report_path`, frontmatter excluded, every impact tier) into reconcile's parse shape: one `## High-Impact Findings` section with one `### [Label] file:line` heading per finding - the label from its `Intent:` line, the path of its `Location` line (for `<mount site> -> <defect body>`, the path the diff touched), then its `_(pre-existing)_` and `_(carried from round <N>)_` groups, each re-emitted on the heading as its own group, never merged - followed by its `Issue` line written as `Issue:`. Where the Location is an asset whose own path is absent from the name-status but whose `.meta` is present, the heading uses the `.meta` path, so reconcile sees the file as touched. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line, and tally render as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this run did not re-derive publishes in its prior impact tier at its prior intent, keeping its `_(pre-existing)_` group, with `_(carried from round <N>)_` (`<N>` = the prior report's `round`) after the `Intent:` value; one this run re-derived publishes once, at this run's intent. Both get a Next Steps entry. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

Use skill: `review-report-writer` with `report_type: review-perf`, `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `mode: full`, `round` and (round 2+) `prior_head_sha` from the round gate, `scope: +perf`, `depth` as resolved from the Depth table, `stack: unity`, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit the report body as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

A Summary field whose observed state matches no listed value is written as the closest value followed by ` - <what was actually observed>`. Every field except `Round` is always present.

```markdown
## Unity Performance Review Summary

- **Stack Detected:** Unity <internal version> (Unity <marketing name>) / {URP 2D Renderer | URP Universal Renderer | Built-in | unknown} / {IL2CPP | Mono | unknown}
- **Frame Budget:** {33ms @ 30fps | 16ms @ 60fps | display rate (VSync) | uncapped} ({from `Application.targetFrameRate` at file:line | not set - platform default 30fps | set per platform - <which>})
- **Measurement Basis:** {Profiler capture on <device>, development build | baseline capture before this change on <device> - <figure against budget> | partial capture - <which tools ran> | estimated from code (no capture supplied)}
- **Platform Targets:** {list}
- **Scope:** Client (Unity)
- **Round:** {N}{; base advanced since round <N-1>}   {round 2+ only}
- **Overall:** {Clean | Issues Found - <count by impact>}
- **Unattributed:** {see `## Unattributed` | none}

## Findings

### High Impact

#### {the idiom, in a few words}

- **Location:** {file:line | asset path | settings asset path | <mount site> -> <defect body>} {_(pre-existing)_}
- **Issue:** {name the Unity idiom: string interpolation per frame, 500 `Update` calls across the tile grid, `Instantiate` per shot with no pool, material cloned per tile, 3 stacked full-screen transparent layers, 2048 import for a 96px sprite, synchronous `LoadScene` on the level transition}
- **Player-Visible Impact:** {what the player experiences: "a hitch every few seconds on the board", "wave start drops ~8 frames", "unplayable on a 3GB-RAM device", "3.2s freeze on level load"}
- **Owner:** {CPU | GPU | GC | Memory | Load}
- **Evidence:** {measured (<device>, <build type>) | estimated (no profile) | inferred (<what was not seen>)}
- **Intent:** {[Must] | [Recommend]} {_(carried from round <N>)_}
- **Fix:** {concrete C#, import-setting, or asset change with code}
- **Verify:** {what to re-measure: GC Alloc column, Frame Debugger batch count, Memory Profiler texture total, cold-start seconds}

### Medium Impact

{same structure}

### Low Impact

{same structure}

## Routed

- {file:line} - {out-of-lens defect} -> {owning workflow} {(pre-existing)}

## Unattributed

- {a reported symptom this change set does not explain, a capture-revealed condition it did not cause, or a perf defect in unchanged code it does not reach} - {what would attribute it}

## Prior Round Reconciliation   {round 2+ standalone runs only}

{table, note line, and tally from `review-prior-findings-reconcile`}

## Recommendations

- {structural improvements not tied to a single finding}

## Device & Measurement Plan   {deep depth only}

{which device tiers to measure on, which capture to take, and the number that decides whether the fix worked}

## Next Steps

1. **[Implement]** [Must] {file:line} - {one-line action}
2. **[Delegate]** [Recommend] [scope: task-unity-review] - {one-line action}
```

Rules for the template:

- Omit an empty impact section; if all are omitted, write `No performance issues found.` under `## Findings`. Omit `## Routed` and `## Unattributed` when empty, with the Summary's Unattributed line reading `none`.
- A finding's Location is a path. A symptom with no attributable path is an `## Unattributed` entry, never a finding. `<mount site> -> <defect body>` is used when the defect body and the change that mounts it are different files; the impact line says which one the diff touched. `_(pre-existing)_` follows a path absent from the name-status, and `_(carried from round <N>)_` a carried finding.
- Owner is the dominant one; a second owner is named in `Player-Visible Impact`.
- Next Steps are tagged `[Implement]` or `[Delegate]` and ordered Must > Recommend; within a band, the finding whose fix others depend on, or which subsumes another, goes first. The label restates the finding's `Intent:`. Every Next Steps entry carries exactly one label, `[Must]` or `[Recommend]`. Each `## Routed` line, and each Unattributed entry with a named next action, is a `[Delegate]` entry labelled `[Recommend]`. Omit Next Steps when there is nothing to act on.
- Cite an asset finding at its asset path where it has no meaningful line; `file:line` is for source.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded, or its Rules inlined in the spawning prompt
- [ ] Step 2: stack confirmed Unity; engine version checked numerically against the `6000.3.x` floor; pipeline asset, scripting backend, target frame rate, Addressables, UI system, and platform targets recorded from their own sources (or derived where the parent did not supply them)
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-perf` (or parent-supplied refs and diff reused); round decided on `head_sha`, `base_sha`, and depth before any surface was read (or the stop line printed); diff and name-status read once and reused; no-op exit taken on an excluded-only change set
- [ ] Step 4: performance surface read directly at the head (update-bearing components, spawn paths, changed scenes and prefabs, import settings, atlas packables, UI screens, scene-load call sites, manifest, Build Profiles, build settings)
- [ ] Step 5: `unity-performance` and `csharp-unity-patterns` consulted; per-frame allocation, LINQ and closures, buffer reuse, allocating query overloads, and boxing checked
- [ ] Step 6: `Update` count, empty callbacks, polling, pooling, pooled-state reset, and pre-warm checked on every spawn path in the diff
- [ ] Step 7: `unity-2d-rendering` consulted; material clones, atlas membership, sorting interleave, and overdraw sources checked
- [ ] Step 8: texture cap vs source and drawn size, compression format, mipmaps, physics use, rigidbody presence, and UI Toolkit query and repaint cost checked
- [ ] Step 9: `unity-build-release` consulted when build config changed; async scene load, dependency graph, `Resources` additions, cold start, size delta, and any ECS proposal assessed; atomic `Deferred:` lines resolved or routed
- [ ] Step 10: every finding labelled `measured`, `estimated`, or `inferred`, with a pre-change capture treated as baseline; no editor timing cited; atomic blocks mapped into the report's fields; intent from the derivable-cost test, Medium and Low always `[Recommend]`
- [ ] Step 11: standalone: on round 2+, prior findings projected with their annotation groups (and `.meta` paths for import findings) and reconciled, unresolved rows carried; report written via `review-report-writer` with every required field (`stack: unity`, `mode: full`, `scope: +perf`, round, both SHAs, `prior_head_sha` on round 2+); confirmation line printed; subagent: Findings, Routed, Unattributed, and the deep-only plan returned with head-file citations, no file written
- [ ] Out-of-lens defects in `## Routed` and unexplained symptoms in `## Unattributed`, none dropped
- [ ] Excluded surfaces raised no findings; `.meta` defects cited at the asset; scenes, prefabs, `.asset`, and `.spriteatlasv2` files treated as reviewable
- [ ] Every finding states player-visible impact and names its owner (CPU / GPU / GC / Memory / Load)
- [ ] Depth honored: `standard` ran all steps; `deep` added the Device & Measurement Plan
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered Must > Recommend

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase/fetch/stash) - the review reads history only
- Writing a report when invoked as a subagent - the parent owns it
- Writing a report at all when the change set touches only excluded surfaces
- Citing an editor Play-mode timing, or a development-build number presented as the shipped number
- Reporting cost without player-visible impact ("this allocates a lot" vs "1.4 KB/frame steady garbage, a visible hitch every few seconds")
- Generic advice where a Unity idiom exists ("tick from an update manager", not "reduce work")
- Raising findings against excluded surfaces, or on a `.meta` file rather than the asset it describes
- Relying on incremental GC while the per-frame allocation stays in place
- Recommending a pool for a single instance or a rarely-spawned object
- Recommending `SetPropertyBlock` as the batch-safe tint fix on URP
- Asserting a batching or compression behaviour without the Frame Debugger or the import settings to back it
- Proposing ECS, DOTS, Jobs, or Burst with no device profile naming that system as the bottleneck
- Filing a missing loading state, a permanent spinner, or an unhandled offline path as a perf finding
- Optimizing without a measurement plan that would show the fix worked
