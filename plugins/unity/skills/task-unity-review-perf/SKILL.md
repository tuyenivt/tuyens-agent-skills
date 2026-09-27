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

Client-side perf review naming the Unity idiom: managed allocation in the steady frame loop, `Update` invoked across hundreds of objects, `Instantiate`/`Destroy` where a pool belongs, batches split by material variants, overdraw from stacked transparent 2D sprites, texture import settings that decide runtime memory, UI Toolkit panel repaint, and synchronous scene load. Every finding states player-visible impact and labels its evidence as measured or estimated.

Performance review for Unity projects.

## When to Use

- Unity perf regression review of the current change set
- Stutter, hitches, dropped frames, or thermal/battery complaints on a target device
- A game that runs on a flagship and badly on a budget phone
- Slow scene load, slow cold start, or runtime memory growth across a session
- Build size or texture memory growth
- Pre-release perf pass on the gameplay loop, a spawn path, or a new UI screen

**Not for:** general review (`task-unity-review`), security (`task-unity-review-security`), pre-implementation design (`task-unity-implement`).

Perceived slowness that is actually a missing loading state, an unhandled offline path, or a permanent spinner is not a perf finding. Route it out rather than dropping it: a `[Delegate]` Next Step naming `task-unity-review` and the defect. The same applies to a build-configuration defect the diff surfaces but does not cause - name it and delegate.

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | All steps |
| `deep` | Profiler capture supplied (device Profiler session, Memory Profiler snapshot, Frame Debugger capture, build report), or a perf-critical release | All + a `### Device & Measurement Plan` subsection under Recommendations |

## Measurement Discipline

- **The Profiler attached to a development build on a real target device is the only valid timing source.** Editor Play mode runs extra tooling on a different scripting backend than the shipped IL2CPP build and hides device thermal and GPU limits. An editor number is not evidence.
- **A development build is where you find cost, not where you confirm it.** Profiler instrumentation and disabled optimizations inflate it; the shipped number comes from a non-development build.
- **State the frame budget the project actually targets** - 33ms at 30fps, 16ms at 60fps. Read `Application.targetFrameRate` rather than assuming 60; casual 2D commonly ships 30 deliberately. Where it is set nowhere in the project, grade against **33ms** and raise the unset target as its own finding (Location `setting`, Owner CPU, Medium `[Recommend]`; High when a reported thermal or pacing symptom exists): the runtime then chases the panel rate, which is what thermally throttles a budget device.
- **Attribute before fixing.** Every finding names CPU (main thread), GPU (fill rate or draw calls), GC, memory, or load as its owner. The wrong fix costs the same effort as the right one.
- **Impact, not adjective.** "500 `Update` calls per frame on tiles that change once a move" is a finding. "This is slow" is not.

## Excluded Surfaces

Not review surface: `Library/`, `Temp/`, `obj/`, `Build/`, generated `*.csproj` and `*.sln`, and imported third-party SDK sources under `Assets/Plugins/`. Do not raise a finding *on* a `.meta` file; when a `.meta` carries the defect (an import setting, a broken GUID reference), cite the asset it describes.

**Assets are review surface.** `.unity` scenes, `.prefab`, and `.asset` files are reviewable - a texture import setting, a prefab with 300 `Update`-bearing children, or a duplicated material on a prefab variant is a legitimate finding cited at the asset path.

## Invocation

`/task-unity-review-perf [<branch>|pr-<N>] [standard|deep] [--base <branch>]`

Defaults to the current branch vs its base; `pr-<N>` reviews a locally fetched PR ref. `review-precondition-check` fails fast on a dirty working tree and on a trunk head - review compares committed code only.

**Never modify the working tree.** Read via `git diff` and `git show` only.

When invoked as a subagent (e.g. by `task-unity-review`), the parent supplies the resolved `base_ref` / `head_ref`, the pre-read diff and name-status, the depth level, the detected project shape, and the excluded-surface list: Step 3 is skipped, no git is re-run, and Step 11 returns findings instead of writing - the parent owns the report.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`. Accept the parent's confirmation if invoked as a subagent.

### Step 2 - Stack and Project Shape

Accept the project shape from the parent when invoked as a subagent. Otherwise read `ProjectSettings/ProjectVersion.txt`; if it is absent, stop - this workflow reviews Unity projects only.

Record from `ProjectSettings/ProjectVersion.txt` and `Packages/manifest.json`: engine version (internal form, e.g. `6000.3.21f1`), render pipeline (URP 2D / Built-in), scripting backend and target frame rate, Addressables presence, UI system, and the platform targets present.

**Engine floor is Unity 6.3 LTS (`6000.3.x`).** Compare numerically. Below the floor, state the mismatch and stop rather than emitting guidance the project cannot apply. Above it (`6000.5.x`) proceeds normally. If `ProjectVersion.txt` is unreadable, say so and proceed with version-independent findings only.

Record a uGUI project as out of scope for the UI step rather than reviewing it under UI Toolkit rules.

### Step 3 - Resolve the Change Set

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review-perf`, so the handle's `report_path` is this lens's checkpoint and its `prior_checkpoint` that file's frontmatter (or `legacy`). Surface any fail-fast verbatim and stop.

**Round gate.** Capture `base_sha` / `head_sha` via `git rev-parse` on the handle's refs and decide the round before reading any surface: a valid `prior_checkpoint` whose `head_sha` equals the captured `head_sha` and whose `depth` covers the requested one (`deep` covers `standard`) -> print `No new commits since prior perf review.` and stop - no review, no report. Otherwise `round` = its `round` + 1 and `prior_head_sha` = its `head_sha`; no `prior_checkpoint`, or `legacy` (Step 11 overwrites the file) -> `round: 1`, no `prior_head_sha`.

Then read once and reuse:

- `git diff <base_ref>...<head_ref>` for the change body
- `git diff --name-status <base_ref>...<head_ref>` for the file list

Restrict analysis to the changed paths outside Excluded Surfaces. A binary asset git reports as `Binary files differ` is not diffed - its `.meta` carries the reviewable import settings.

**Skip entirely** when invoked as a subagent and the parent passed the refs plus the pre-read diff.

**No-op exit.** When the change set touches only excluded surfaces, write no report: state `No reviewable change in this change set - <reason>` and stop. Do not manufacture findings from unchanged code.

A `.meta`-only change set is not automatically a no-op. Import settings are a primary review surface (Step 8), so read the `.meta` changes: an import-setting delta (compression, max size, mip generation, atlas membership) is reviewable and the review proceeds, cited at the asset. GUID or importer-version churn with no setting delta is a no-op.

### Step 4 - Read the Performance Surface

Cite real `file:line` or asset path. Open:

- Every changed `MonoBehaviour` with `Update`, `FixedUpdate`, or `LateUpdate`, and every per-entity loop
- Spawn and despawn paths - `Instantiate`, `Destroy`, and any pool
- Changed scenes and prefabs: component counts, how many objects carry an update callback, duplicated materials, particle systems
- Sprite, texture, and atlas import settings via the asset's `.meta` (max size, compression format, mipmaps), cited at the asset
- UI Toolkit screens and their `Q`/`Query` call sites and per-frame text assignment
- Scene-load and Addressables call sites, plus the entry scene
- `Packages/manifest.json` for added packages, and build settings changed in `ProjectSettings/`

If the diff is small but ripples into unchanged code - a new prefab mounting an existing `Update`-heavy component, or a new spawner calling an existing unpooled factory - read the unchanged file. The regression lives there.

### Step 5 - Allocation in the Frame Loop

Use skill: `unity-performance` for the pattern bank. Use skill: `csharp-unity-patterns` for allocation mechanics.

**This is the dominant mobile Unity perf problem.** Steady per-frame garbage forces collections, and a collection during play is a visible hitch. The target is 0 B in the `GC.Alloc` column of a steady frame.

- [ ] **No string building or interpolation per frame** - a score label assigned every frame allocates every frame; gate on value change or use a cached table
- [ ] **No LINQ, no capturing lambda, no `new` collection** in `Update`, `FixedUpdate`, `LateUpdate`, or a per-entity loop
- [ ] **Buffers and collections reused across frames** - cleared, not reallocated
- [ ] **Non-allocating query overloads with a preallocated buffer** for physics and component queries; the `*All` overloads allocate an array per call
- [ ] **No boxing in a hot path** - a `struct` passed as `object` or through a non-generic interface boxes
- [ ] **Incremental GC is not the fix.** It splits one hitch into several and does not reduce the garbage; enabling it while allocating per frame converts a stall into sustained frame-time noise

```csharp
// Bad - a string allocated every frame whether or not the score changed
void Update() { label.text = $"Score: {score}"; }

// Good - allocation only when the displayed value changes
void Update() { if (score != _shown) { _shown = score; label.text = _cached[score]; } }
```

### Step 6 - Update Cost and Instantiation

- [ ] **`Update` count is bounded.** Each `Update` is a native-to-managed interop call per object per frame before the body does anything. Hundreds of tiles each polling a dirty flag is the classic 2D case - tick them from one update manager over a plain interface list
- [ ] **Empty `Update` / `FixedUpdate` / `LateUpdate` bodies deleted**, not left as placeholders - the interop call still costs
- [ ] **Event-driven state is not polled** - work that changes on a move should not run every frame
- [ ] **Pooling on any repeated spawn path.** `Instantiate`/`Destroy` in a spawn loop or per-frame path hitches on wave start and produces destroy garbage. `UnityEngine.Pool.ObjectPool<T>` ships with the engine, so a hand-rolled pool needs a reason
- [ ] **Pooled objects fully reset on get or release** - partial reset leaks state across reuse and is a correctness bug, not just a perf one
- [ ] **Pool pre-warmed at load** rather than paying the first `Instantiate` mid-gameplay
- [ ] **No pool around a single instance or a rarely-spawned object** - that is indirection for no measured gain; raise it as overengineering, not a perf win

### Step 7 - Draw Calls, Batching, and Overdraw

Use skill: `unity-2d-rendering` for atlas, sorting, and material specifics.

- [ ] **No material duplicated to change one colour or tint.** This is the recurring 2D batch-breaker: every copy is a separate binding that splits one batch into many. Use a material property block or a shader parameter the SRP Batcher keeps in the per-object buffer
- [ ] **Sprites drawn together share an atlas page** - two sprites from different atlases cannot batch however identical their material, and an overflowed atlas silently splits into a second page
- [ ] **Sorting order does not interleave objects from different atlases**, which forces a state change between each and defeats a batch that "should" merge
- [ ] **Overdraw bounded on the primary mobile tier.** Transparent sprites do not depth-reject: cost scales with layers times screen coverage, it is invisible in a draw-call count, and it is the usual reason a game runs fine on a flagship and badly on a budget phone
- [ ] **Large backgrounds drawn opaque**, sprite meshes tightened so the quad is not mostly alpha border, particle count and size bounded
- [ ] **Fully covered UI screens deactivated, not left rendering behind a popup**
- [ ] **Batching claims confirmed in the Frame Debugger**, which names the reason a batch broke - SRP Batcher compatibility of a given material-property mechanism is URP-version-dependent and is not asserted

### Step 8 - Texture Memory, Physics, and UI Repaint

- [ ] **Import settings decide runtime memory, not the source file size** - a small PNG uploads uncompressed if the import format says so
- [ ] **Max size matched to the drawn size.** A 2048 source imported at 2048 for a sprite drawn 200px wide wastes memory proportional to the area ratio, and texture memory is usually the largest runtime memory line in a 2D game
- [ ] **Compression format set per platform** - ASTC is the mobile default on current Android and iOS hardware, ETC2 the older-Android fallback, BC/DXT on desktop. Confirm what the platform override actually sets rather than assuming
- [ ] **Mipmaps off for UI and screen-aligned 2D sprites** - a ~33% memory increase for nothing when the sprite is drawn at a fixed scale
- [ ] **Physics 2D absent from board logic.** Grid legality and adjacency are rules-layer array math; physics belongs to projectiles and casual physics toys only
- [ ] **Anything that moves carries a `Rigidbody2D`** (kinematic is fine) - moving a collider with no rigidbody forces static-geometry rebuilds. Collision matrix restricted so impossible layer pairs are not tested
- [ ] **UI Toolkit queries cached at bind time** - `Q<T>()` per frame re-walks the tree. Per-frame text assignment re-tessellates; gate on value change. Off-screen panels detached or hidden rather than left attached and live

### Step 9 - Scene Load, Build Size, and the ECS Question

Use skill: `unity-build-release` when the diff touches build configuration, Addressables, or packaging.

- [ ] **`SceneManager.LoadSceneAsync` on any path the player waits through** - the synchronous form blocks the main thread for the whole dependency graph and reads as a freeze
- [ ] **Load time attributed to the asset dependency graph**, not scene file size - a prefab referencing a large atlas pulls it in whole
- [ ] **`Resources` contents are eagerly indexed** in ways Addressables content is not; new content added to `Resources` is a load-time and memory finding
- [ ] **Cold start measured on a real device from process start**, not from the editor's first frame
- [ ] **Build-size delta attributed** to what this change added - a new package, an uncompressed asset set, or a texture import change
- [ ] **ECS / DOTS / Jobs / Burst proposed only with a device profile naming that system as the bottleneck.** For casual 2D it is almost never warranted: the measured bottlenecks in these genres are GC, overdraw, and draw calls, none of which ECS fixes. Burst-compiling one profiled hot job is bounded and reversible; rearchitecting is not. An unmotivated ECS proposal in the diff is a finding against the diff

### Step 10 - Evidence and Impact

Label every finding's evidence. Never present an estimate as a measurement, and never cite an editor Play-mode number at all.

| Evidence | Use when | Example phrasing |
|----------|----------|------------------|
| `measured (device, build)` | A Profiler, Memory Profiler, Frame Debugger, or build-report capture from a development build on a named physical device, **covering the code under review** | `1.4 KB/frame GC.Alloc on the cascade resolve, Pixel 6a, development build` |
| `estimated (no profile)` | The pattern is unambiguous but no capture covers it | `500 Update calls per frame across the tile grid` |

**A capture taken before the change is not a measurement of the change.** It measures the baseline the change lands on. Label findings about the diff `estimated (no profile)` and cite the capture as the baseline in the impact line; reserve `measured` for a condition the capture actually observed. A pre-change capture still raises depth to `deep` - the Device & Measurement Plan is exactly what a baseline-only capture calls for.

`unity-performance` emits these values, plus `inferred (no source read)` when the review ran without source access. **With no profile supplied, cap the finding at High Impact** - the atomic applies the same cap. `inferred` is capped at High for the same reason.

**Intent precedence over the cap.** The cap bounds *impact*, not *intent*. A finding whose cost depends on data only the author has stays `[Recommend]` and names the measurement to run, **even at High Impact**. `[Must]` at High Impact requires either a measurement or a defect whose cost is unconditional on the shipped path.

The test is whether the defect's cost is derivable from the diff alone:

| Cost derivable from | Intent | Examples |
| --- | --- | --- |
| The diff itself - the code or the import setting *is* the evidence, and the arithmetic follows | `[Must]` | per-frame allocation in `Update`; a material split per instance; a 2048 RGBA32 import for a 96px sprite - the memory figure is arithmetic, not estimation |
| Data only the author or a device has - device tier, board size, atlas contents, or a coverage the diff does not state | `[Recommend]` | overdraw whose layer coverage is unknown; whether an atlas overflows its page; anything whose magnitude needs a capture |

Coverage the diff states is diff-derivable: *N* stacked **full-screen** transparent layers is `[Must]`, because the multiplier is given. *N* transparent layers of unstated extent is `[Recommend]`.

Within a band, order by fix dependency. A `Critical`-origin finding capped to High keeps the atomic's rationale in its impact line, and where fix dependency would place it below another finding, say so in one clause rather than reordering.

**Severity mapping.** `unity-performance`, `csharp-unity-patterns`, `unity-2d-rendering`, and `unity-build-release` grade findings `Critical | High | Medium | Low`; this report groups by impact. Map `Critical` and `High` to **High Impact**, `Medium` to Medium, `Low` to Low. A `Critical`-origin finding leads the High Impact section and keeps the atomic's rationale (sustained missed frame budget, unbounded memory growth, OOM-risk load on the target tier) in its impact line - do not flatten it into an ordinary High.

Confirm that a hot path introduced here is observable at all; if it is not, raise Low.

### Step 11 - Write Report

Standalone only. A subagent run returns the `## Findings` sections and, at `deep`, the `## Device & Measurement Plan` - nothing else. No frontmatter, no Summary block, no Recommendations, no Next Steps: the parent owns those and cannot merge two of them. Project-shape values the parent already supplied are not echoed back.

A subagent that has something for `Unattributed` - a reported symptom the change set does not explain, or a capture-revealed condition it did not cause - returns it as a final `## Unattributed` section for the parent to fold into its Summary. Intent (`[Must]` / `[Recommend]`) is stated per finding on the template's `Intent:` line so the parent can order Next Steps without re-deriving it.

**Round 2+ reconcile (standalone).** Project the prior report (the file at the handle's `report_path`, every impact tier) into reconcile's parse shape: one `## High-Impact Findings` section with one `### [Label] file:line` heading per finding - the label from its `Intent:` line (a trailing `_(carried from round <N>)_` group re-emitted on the heading as its own group), the `file:line` or asset-path prefix of its `Location` line - followed by its `Issue` line written as `Issue:`. Then Use skill: `review-prior-findings-reconcile` with that projection, the diff, the name-status, `head_sha`, and `git ls-tree -r --name-only <head_sha>` as `head_files` when the name-status has a `D` entry. Its table, note line, and tally render as `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this run did not re-derive publishes in its prior impact tier at its prior intent with `_(carried from round <N>)_` (`<N>` = the prior report's `round`) after the `Intent:` value; one this run re-derived publishes once, at this run's intent. Both get a Next Steps entry. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

Use skill: `review-report-writer` with `report_type: review-perf`, `report_body` (the assembled body), `branch` (the handle's `head_short_name`), `base_ref` / `head_ref` as the handle emitted them, `base_sha` / `head_sha` from the Step 3 round gate, `mode: full`, `round` and `prior_head_sha` from the round gate, `scope: +perf`, `depth` as resolved from the Depth table, `stack: unity`, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Emit the report body in chat, then the writer's confirmation line.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit the report body as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Unity Performance Review Summary

- **Stack Detected:** Unity <marketing name> (<internal version>) / URP 2D | Built-in
- **Frame Budget:** 33ms @ 30fps | 16ms @ 60fps (from `Application.targetFrameRate` at file:line | set outside the diff at file:line - unconfirmed | set per platform - state which | not set - assumed)
- **Measurement Basis:** Profiler capture on <device>, development build | partial capture - state which tools ran | estimated from code (no capture supplied)
- **Platform Targets:** <list>
- **Scope:** Client (Unity)
- **Round:** <N>   {round 2+ only}
- **Overall:** Clean | Issues Found - [count by impact]
- **Unattributed:** [reported symptoms this change set does not explain, and any capture-revealed condition the diff did not cause - each with what would attribute it | none]


Summary field whose observed state matches no listed value: write the closest value followed by ` - <what was actually observed>` rather than forcing a wrong one or omitting the line. Every field except `Round` is always present.

## Findings

### High Impact

- **Location:** [file:line | asset path | setting | symptom, when no source was supplied. Where the defect body and the change that mounts it are different files, write `<mount site> -> <defect body>` and name which one the diff touched]
- **Issue:** [name the Unity idiom: string interpolation per frame, 500 `Update` calls across the tile grid, `Instantiate` per shot with no pool, material duplicated per tile splitting the batch, 6 stacked full-screen transparent layers, 2048 atlas imported for a 200px sprite, synchronous `LoadScene` on the level transition]
- **Player-Visible Impact:** [what the player experiences: "a hitch every few seconds on the board", "wave start drops ~8 frames", "unplayable on a 3GB-RAM device", "3.2s freeze on level load"]
- **Owner:** CPU | GPU | GC | Memory | Load - name the dominant one and cite the second in `Player-Visible Impact` when a defect genuinely has two (a per-frame string assign is GC for the allocation and CPU for the re-tessellation it triggers)
- **Evidence:** measured (<device>, <build type>) | estimated (no profile) | inferred (no source read)
- **Intent:** [Must] | [Recommend] - from Step 10's derivable-cost test; the Next Steps label restates this value; a carried finding appends `_(carried from round <N>)_`
- **Fix:** [concrete C#, import-setting, or asset change with code]
- **Verify:** [what to re-measure: `GC.Alloc` column, Frame Debugger batch count, Memory Profiler texture total, cold-start seconds]

### Medium Impact / Low Impact

[Same structure]

_Omit empty sections. If all are omitted: "No performance issues found."_

## Prior Round Reconciliation   {round 2+ standalone runs only}

[table, note line, and tally from `review-prior-findings-reconcile`]

## Recommendations

[Structural improvements not tied to a single finding]

## Device & Measurement Plan _(deep depth only)_

[Which device tiers to measure on, which capture to take, and the number that decides whether the fix worked. A top-level section, so a subagent returns it without its parent]

## Next Steps

Each tagged `[Implement]` or `[Delegate]`. Order: Must > Recommend.
Every finding carries exactly one label: `[Must]` or `[Recommend]`. No other label is written.
Intent comes from Step 10, not from the impact band: High Impact is `[Must]` only with a measurement or an unconditional shipped-path cost, and `[Recommend]` otherwise; Medium and Low are always `[Recommend]`.
Within a band, order by fix dependency - the finding whose fix others depend on, or which subsumes another, goes first.
Cite an asset finding at its asset path where it has no meaningful line; `file:line` is for source.

1. **[Implement]** [Must] file:line - [one-line action]
2. **[Delegate]** [Recommend] [scope: server contract] - [one-line action]

_Omit if no actionable findings._
```

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded (or accepted from parent)
- [ ] Step 2: stack confirmed Unity; engine version checked numerically against the `6000.3.x` floor; pipeline, target frame rate, Addressables, UI system, and platform targets recorded
- [ ] Step 3: `review-precondition-check` ran with `report_type: review-perf` (or parent-supplied refs and diff reused); round decided before any surface was read (or the stop line printed); diff and name-status read once and reused; excluded surfaces left out; no-op exit taken on an excluded-only change set
- [ ] Step 4: performance surface read directly (update-bearing components, spawn paths, changed scenes and prefabs, import settings, UI screens, scene-load call sites, manifest and build settings)
- [ ] Step 5: `unity-performance` and `csharp-unity-patterns` consulted; per-frame allocation, LINQ and closures, buffer reuse, allocating query overloads, and boxing checked
- [ ] Step 6: `Update` count, empty callbacks, polling, pooling, pooled-state reset, and pre-warm checked on every spawn path in the diff
- [ ] Step 7: `unity-2d-rendering` consulted; material variants, atlas membership, sorting interleave, and overdraw sources checked
- [ ] Step 8: texture max size, compression format, mipmaps, physics use, rigidbody presence, and UI Toolkit query and repaint cost checked
- [ ] Step 9: `unity-build-release` consulted when build config changed; async scene load, dependency graph, `Resources` additions, cold start, size delta, and any ECS proposal assessed
- [ ] Step 10: every finding labelled `measured (device, build)` or `estimated (no profile)`, with a pre-change capture treated as baseline rather than measurement; no editor timing cited; estimated findings capped at High; atomic severities mapped to impact bands; intent taken from the derivable-cost test, not from the impact band
- [ ] Step 11: standalone: on round 2+, prior findings projected and reconciled, unresolved rows carried; report written via `review-report-writer` with every required field (`stack: unity`, `mode: full`, round, both SHAs); confirmation line printed; subagent: Findings (plus the deep-only plan) returned to parent, no Summary or Next Steps, no file written
- [ ] Reported symptoms the change set does not explain, and excluded non-perf defects, recorded in `Unattributed` or delegated rather than dropped
- [ ] Excluded surfaces raised no findings; `.meta` defects cited at the asset; scenes, prefabs, and `.asset` files treated as reviewable
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
- Raising findings against `Library/`, `Temp/`, `obj/`, `Build/`, generated `*.csproj` / `*.sln`, or `Assets/Plugins/` SDK sources
- Raising a finding on a `.meta` file rather than the asset it describes
- Enabling incremental GC and leaving the per-frame allocation in place
- Recommending a pool for a single instance or a rarely-spawned object
- Asserting a batching or compression behaviour without the Frame Debugger or the import settings to back it
- Proposing ECS, DOTS, Jobs, or Burst with no device profile naming that system as the bottleneck
- Filing a missing loading state, a permanent spinner, or an unhandled offline path as a perf finding
- Optimizing without a measurement plan that would show the fix worked
