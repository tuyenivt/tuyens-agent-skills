---
name: task-unity-implement
description: End-to-end Unity 2D feature implementation - engine-free rules core, ScriptableObject config, MonoBehaviour wiring, UI Toolkit screens, save, tests.
agent: unity-engineer
metadata:
  category: mobile
  tags: [unity, csharp, 2d, gameplay, ui-toolkit, scriptableobject, save, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Implement Unity 2D Feature

## When to Use

End-to-end Unity 2D feature work: rules core + runtime wiring + presentation + persistence + tests in one pass. STEPS 3-7 write the files; the report lists what was written. STEP 2 is the gate that decides what gets written, and nothing lands before it is approved.

Not for: a sprite or palette swap, an inspector value tweak, a scene-layout nudge, or engine-version upgrade work. A change that *only* restyles an existing screen is a UI edit, not this workflow.

It does apply when presentation work also adds behaviour, locales, or persistence - the steps that produce nothing are written as skipped rather than being a reason to decline. A feature built entirely on existing rules is an anticipated shape, not an out-of-scope one. The fixes a review produced, and a measured performance fix, run through the same steps: the steps the fix does not touch are written `skipped - not touched`, and a performance fix also loads Use skill: `unity-performance` at the step it changes.

## Rules

- **Game rules are plain C# with no `UnityEngine` dependency**, in a rules assembly whose `.asmdef` sets `"noEngineReferences": true` - every assembly gets the engine implicitly, so leaving it out of `references` enforces nothing. Every other decision in this workflow follows from that one
- `MonoBehaviour` only where an engine hook is needed - lifecycle callback, collision, coroutine, inspector wiring. A class needing none is a plain class
- ScriptableObjects hold authored configuration, never mutable runtime state
- Time reaches rules through an injected `IClock`; randomness through a seeded generator whose state lives inside the rules state, so undo, replay, and a resumed save reproduce it (move-driven, `unity-2d-gameplay-patterns`), or an injected `IRandom` (fixed-tick sim). A seam exists only where the feature uses it - its absence is said, never invented. No `DateTime.Now` / `DateTime.UtcNow`, unseeded `System.Random`, `Stopwatch`, `Time.deltaTime`, or `UnityEngine.Random` inside a rule
- Never `?.`, `??`, `??=`, `is null`, or `is not null` on a `UnityEngine.Object` - use `== null` / `!= null`
- Every screen with an async or failable source renders loading, error, and empty, not just the happy path
- User-facing strings resolve through a localization key. The Localization package installed with no String Table yet counts as a localization system: this feature adds its table. Where the project has no localization system at all, keep every string in one holder type so extraction is mechanical, and report it in Deviations rather than installing a localization system this feature did not ask for
- Any save-shape change bumps the schema version, because old saves exist on installed devices; data that cannot load as-is under the new shape also gets a migration step (`unity-save-persistence` - an added field with a usable default needs only the default)
- Each step completes before the next; design approved before code

## Workflow

### STEP 1 - PRINCIPLES, DETECT AND GATHER

Use skill: `behavioral-principles` before anything else in this step.

**Engine floor gate.** Read `ProjectSettings/ProjectVersion.txt` and compare `m_EditorVersion` numerically against the **Unity 6.3 LTS floor (`6000.3.x`)**. Below the floor, emit only `## Engine Gate` with the detected version and `Below floor - stopped`, and **STOP** - this is a detect-and-report boundary, not a degradation path. Do not emit guidance the project cannot compile. At or above the floor (`6000.3.x`, `6000.4.x`, and later) proceeds normally; the gate is a minimum, not an equality check. When `ProjectVersion.txt` is unreadable or absent, say so and ask for the editor version rather than assuming one.

Then confirm from `Packages/manifest.json`, project settings, and the code. UI Toolkit ships in the engine, so the manifest cannot show it: the code (`UIDocument` vs `Canvas`) settles UI; no render-pipeline package means Built-in. A value the files cannot settle (the package is present but the assigned asset or the code path is not visible) is recorded as `unknown` with what was seen:

| Concern | Confirm | If it differs |
| --- | --- | --- |
| Render pipeline | URP with the 2D Renderer asset assigned | Built-in RP, or URP with the Universal (3D) Renderer: state the mismatch; 2D lights guidance does not apply |
| Input | Input System package, used by the code | Legacy `Input` manager, or the package present while the code calls `Input.*`: flag it and use the project's existing input path; do not convert the project |
| UI | UI Toolkit | **uGUI only: report the UI portion out of scope and stop it.** Continue the non-UI steps. Mixed: build this feature's screens in UI Toolkit and leave uGUI screens untouched |
| Persistence | JSON in `Application.persistentDataPath` | PlayerPrefs as the primary store: report it at STEP 6 as a standing condition - Critical when it holds primary progress, per `unity-save-persistence`'s bands - and say whether this feature's data goes into it or into a new store |
| Content loading | Addressables | `Resources/`: report at STEP 6 as a standing project condition, and say whether this feature adds to it |
| Rules assembly | An `.asmdef` with `"noEngineReferences": true` | **None anywhere, or the existing one lacks the flag: report at STEP 2 as the blocking design finding.** Do not build rules into MonoBehaviours around it |

Ask before writing code, grouped so each cluster surfaces its own follow-ups. Skip clusters the feature does not touch:

**Feature**
1. Genre and core loop (board/turn, cascade, wave, idle accrual, quiz round)
2. Entry point: new scene, existing screen, popup over gameplay

**Rules**
3. State the rules layer owns, and what a single move or step produces
4. Legality, scoring, and termination conditions
5. Whether undo, replay, or a daily seed is required

**Data**
6. What persists, and whether the save shape changes
7. Static content banks involved (question set, level pack, balance table)

**Presentation**
8. Screens, HUD, and what each renders while loading or on failure
9. Animation and juice, and what carries the information without it

**Server** - skip only when the feature never leaves the device
10. Which endpoint the feature calls, whether the server or the client is authoritative for each value it exchanges, and which player identity survives a reinstall (an account, or anonymous auth that does not)
11. What happens when the two disagree, and what the client does while offline

**Reach**
12. Platform tiers shipping this feature (mobile primary; desktop secondary; WebGL tertiary)
13. Locales, accessibility expectations beyond the defaults, and the declared audience (a children's or families audience changes which ads and analytics SDK modes are legal)

Ask targeted questions for gaps. Do not guess. When the requester has explicitly waived interaction ("just build it", a non-interactive run), a stated default recorded in Open Assumptions replaces each question - the waiver must be explicit; silence is not one.

When questions are open, no waiver exists, and no answer can arrive in this run, stop after STEP 1: emit the report with Engine Gate and Project Surfaces filled, the numbered questions under `## Open Questions`, any blocking finding already known under `## Design Findings`, and `skipped - awaiting answers to Open Questions` in every other slot. No design is drafted and no file is written.

### STEP 2 - DESIGN (APPROVAL GATE)

Use skill: `unity-architecture-patterns` for the assembly plan and the injection seams. Use skill: `unity-overengineering-review` to check the design against the feature's actual size before it is built.

Present the plan:

- **Assembly plan**: which types go in the engine-free rules assembly (`"noEngineReferences": true`), which in runtime, which in the EditMode and PlayMode test assemblies, and each `.asmdef`'s references. An existing seam this feature needs that the new rules assembly cannot reference (it lives in `Assembly-CSharp` or in an engine-referencing assembly) is declared in the rules assembly under the rules namespace, and the old type implements or adapts to it rather than a second unrelated seam of the same name - name both
- **Rules model**: state type, move type, result type, phase enum, and the clock and randomness seams (generator state inside the rules state for a move-driven game - a value-type generator such as `unity-2d-gameplay-patterns`' `SeededRandom` struct, not a wrapper around `System.Random`, which exposes no state to snapshot or save)
- **Scene and prefab plan**: new scenes, prefabs and variants, the composition root, and what each MonoBehaviour exists for
- **Config ScriptableObjects**: which authored values become assets, and why each is configuration rather than runtime state
- **UI plan**: screens, the navigation stack position of each, and the loading/error/empty presentation per async surface
- **Save impact**: fields added or reshaped, the schema version bump, and the migration step where old data cannot load as-is
- **Content impact**: banks touched, identifier stability, and loading strategy
- **Server exchange** (when the feature calls one): which side is authoritative for each value, the conflict rule when they disagree, the offline behaviour, and how an installed older build survives this contract - the client consumes the contract rather than designing it, so a contract that must change, or an endpoint the backend does not have, is a finding routed to the owning service. Build the client against the contract you assume, and record that assumption in Open Assumptions
- **Platform tiers and locales** in scope, with each tier's constraints on this feature's persistence, threading, and durability stated here rather than discovered later. A requested locale the composed atomics say not to ship unverified (an RTL script without verified shaping) is built behind a flag and named in Deviations

Where the design deviates from this skill's defaults (a MonoBehaviour holding rule state, a ScriptableObject mutated at runtime, a DI container introduced), call out the deviation with its reason so the approver sees the choice rather than discovering it in review. The blocking assembly finding, the composed atomics' `Precondition:` lines, and the `unity-overengineering-review` result land in `## Design Findings`.

Wait for approval. When interaction is explicitly waived, proceed without waiting: the report's design sections (Assemblies through Platform Tiers) are the presented plan, and every choice the approver would have ruled on lands in Open Assumptions.

### STEP 3 - RULES CORE

Use skill: `unity-architecture-patterns` for the boundary. Use skill: `unity-2d-gameplay-patterns` for state modelling, move application, cascade termination, and seeded randomness. Use skill: `csharp-unity-patterns` for allocation and language mechanics. Use skill: `unity-game-economy-progression` when the feature accrues currency, progression, or offline time.

Plain C#, no `UnityEngine`. For move-driven state, a move returns a new state plus whether it changed anything, so undo is a snapshot pop rather than a hand-written inverse; a fixed-tick sim (waves, idle accrual) may step one mutable state in place, as `unity-2d-gameplay-patterns` allows. Resolution loops carry a stated bound. Grid indexing goes through one accessor. `IClock` arrives as a constructor parameter; the generator travels in the state.

A feature that adds only small engine-free logic (a preference mapping, a locale resolver, a settings migration) still puts it here when it has branches worth a test; STEP 3 produces nothing only when the feature adds no such logic.

### STEP 4 - RUNTIME WIRING

Use skill: `unity-monobehaviour-lifecycle` for callback placement and static reset. Use skill: `unity-serialization-prefabs` for what the inspector actually persists.

Self-initialization in `Awake`, cross-object reads in `Start`. One composition root constructs the rules objects and hands them to presenters through serialized fields or an explicit `Initialize`, rather than `GameObject.Find` or a singleton per service. Subscriptions pair symmetrically with their unsubscribes. Every runtime-assembly static and static event gets a `[RuntimeInitializeOnLoadMethod]` reset, because domain reload may be disabled (Enter Play Mode Settings). The rules assembly cannot use that attribute: it avoids statics, or exposes a `Reset()` a runtime-assembly reset method calls. Config ScriptableObjects are read, never written.

New `.cs` files need no `.meta`; the editor generates one on import. An edit to an existing scene, prefab, or ScriptableObject is written as YAML only when the asset shows the format and every GUID it references can be read from an existing `.meta`. A new asset whose GUID would have to be minted - a new prefab, ScriptableObject instance, or String Table (which loads at runtime only with its shared table data and their Addressables entries, wiring the editor's String Table Collection creates) - and any reference to a new script's GUID are listed under Files Generated as `(manual - <editor step>)`.

### STEP 5 - PRESENTATION

Use skill: `unity-ui-patterns` for UXML/USS structure, query caching, panel scaling, and the screen stack. Use skill: `unity-2d-rendering` for sprites, atlases, sorting, camera fit, and overdraw. Use skill: `unity-2d-physics-input` for the input actions and gesture thresholds that feed moves into the rules layer. Use skill: `unity-accessibility` for redundant non-colour signalling, touch targets, contrast, text scaling, and a reduced-motion path. Use skill: `unity-i18n` for every user-facing string.

The rules layer resolves a move completely; the presenter animates the resulting step list afterwards. **Rule progression is never gated on animation completion** - no move, resolution step, or state transition waits on a tween. Gating a *UI control* on a presentation finishing is a different thing and is allowed: a button disabled until a reveal completes needs a skip that fast-forwards to the end state, a reduced-motion path that reaches the enabled state immediately, and an `OnDisable` that clears the gate so a disabled component cannot strand it. Queries resolve once in `OnEnable` and are cached. Every screen with an async or failable source renders loading, error, and empty states, not just the populated one. A setting this feature adds that governs existing behaviour (reduced motion over existing shakes and tweens, text scale over existing screens) is wired into those existing sites, each marked `(modified)`; a setting that changes nothing it claims to govern is not done.

Skip the UI Toolkit portion when STEP 1 detected uGUI, and say that it was skipped.

### STEP 6 - PERSISTENCE

Run when the feature persists anything, touches a content bank, grants value, accepts external input, integrates a third-party SDK, or calls a server; skip and say so when it does none of these.

Use skill: `unity-security-patterns` when the feature grants currency, an entitlement, or a reward, accepts a deep link, remote-config value, or downloaded content, or integrates an ads, analytics, or attribution SDK. Its authoring mode emits no severity; where no server can make a grant authoritative, the workflow itself writes that exposure, one sentence, into Accepted Exposure. Use skill: `unity-save-persistence` when the feature persists state: atomic write, corruption recovery, `schemaVersion` bump, and a migration step from the previous version where old data cannot load as-is - old saves exist on installed devices and must load in this build. The persisted state includes the generator state of a seeded rules core. An older build that meets a save this build wrote (a downgrade, a backup restore, a cloud sync from a newer device) refuses it with an explanation rather than loading it as if the fields matched. Use skill: `unity-content-data` for content banks: stable identifiers, import-time validation that fails the build, and a loading strategy sized to the bank.

Write the save on pause, not on quit - a mobile process is killed without a quit callback. Give every async surface the feature adds a timeout, a cancellation path, and a defined resume behaviour.

**When the feature syncs with a server**, the exchange is built here to the STEP 2 decisions: the authoritative side per value, the merge applied when they disagree, a queue that survives a kill so an offline completion is not lost, and a retry that backs off rather than spinning. Merge logic is a rule - it belongs in the rules assembly with a test per conflict case, not in the networking class. The client never blocks a local grant on the round-trip landing; that is what makes the offline path work. Where an existing client path overwrites the same value from the server (a wallet mirror refreshed after a purchase), the merge says which write wins while a queued local grant is unacknowledged.

### STEP 7 - TESTS

The rules assembly is engine-free, which is what makes this cheap. Write **EditMode** tests against it: move legality, state transitions, scoring, cascade termination at its bound, undo/redo round-trips, migration from each shipped save version, and economy math driven by a fake `IClock`. No scene, no Play mode, no mocking framework where dependencies are already interfaces.

Write **PlayMode** tests only where engine behaviour is genuinely under test: lifecycle ordering, scene load, prefab wiring, and a screen's state rendering. Keep the count low - PlayMode is slow, and a rule tested there is a rule in the wrong layer.

Set up an EditMode test `.asmdef` referencing the rules assembly so rule tests compile and run without the runtime assembly; tests that need the engine side (a migration test that parses a real shipped save, content validation) go in a second EditMode `.asmdef` that also references the runtime assembly; and, when PlayMode tests exist, a PlayMode test `.asmdef` for all target platforms referencing the rules and runtime assemblies. Every test asmdef references `UnityEngine.TestRunner` (the EditMode ones also `UnityEditor.TestRunner`, with `Editor` as their only platform), sets `"overrideReferences": true` with `nunit.framework.dll` in `precompiledReferences`, and carries `"defineConstraints": ["UNITY_INCLUDE_TESTS"]` so none ships in the player. The shape matches `task-unity-test`'s STEP 7. An engine-free assembly the design added beyond the rules core gets the same treatment: its own EditMode assembly referencing only what it needs. For a full strategy, coverage assessment, determinism policy, or CI wiring, hand off to `task-unity-test`.

When STEP 3 produced nothing, EditMode still covers whatever engine-free logic the feature added - a display-model mapping, a format under each shipped locale, a table's key coverage. `EditMode: 0` is correct only when the feature genuinely added no engine-free code; say which it is rather than leaving the count unexplained.

### STEP 8 - VALIDATE

Unity validation is batch-mode based. Run in order, fixing failures before reporting done:

1. Compile check - `Unity -batchmode -nographics -quit -projectPath <project> -logFile -`, confirming zero compile errors in the log, including in the test assemblies
2. `Unity -batchmode -nographics -runTests -testPlatform EditMode -testResults <path> -projectPath <project> -logFile -`
3. `Unity -batchmode -nographics -runTests -testPlatform PlayMode -testResults <path> -projectPath <project> -logFile -` - remove `-nographics` only for a test that renders or reads back from the GPU
4. A build for the primary target tier - Use skill: `unity-build-release` for the invocation and the stripping hazards a release build exposes

`-runTests` quits by itself; a `-runTests` invocation never takes `-quit`, which can end the run before results are written. Read the `-testResults` XML and the build report for the result. A zero process exit is not proof of a pass in batch mode. If a command is unavailable in this environment (no editor installed, no licence, no device), name which one and why, and give the command the user runs before merging, rather than reporting a clean run.

## Edge Cases

The stop, skip, and caveat paths (below floor, unreadable version, uGUI, Built-in RP, legacy input, no STEP 6 trigger, presentation-only, WebGL, vague input) are stated at the step they belong to. One case needs its own rule:

- No rules assembly exists, or the existing one lacks `"noEngineReferences": true`: report at STEP 2 as the blocking design finding and scope the fix to **this feature only** - create an engine-free rules assembly and its EditMode test assembly for the types this feature adds, and leave the project's existing scripts where they are. A file moves only when this feature modifies an existing rule type it needs; mark it `(moved from <path>)`. A whole-project re-layering is not this workflow's scope, and building rules into MonoBehaviours because no assembly exists is not an option. When the feature adds no engine-free logic (STEP 3 produces nothing), there is nothing to house: report the missing assembly as a standing condition, not a blocker

## Output Format

Every slot below is written. A step that did not run is written as `skipped - {reason}` rather than omitted; a run that stopped at STEP 1 follows the stop rule there, and a below-floor run emits only `## Engine Gate`. `## Open Questions` exists only in a run that stopped at STEP 1.

Design Findings carries, as bullets: the blocking assembly finding; standing project conditions STEP 1 or a later step detected (PlayerPrefs as the primary store with its severity, content shipped via `Resources/`, a test asmdef without `UNITY_INCLUDE_TESTS`, a defect this feature routes around); `Precondition:` lines, written by this workflow in the atomics' authoring-mode form, one per existing defect the design depends on fixing; and the `unity-overengineering-review` result - each block as `[{label}] {anchor} - {Unnecessary or Missing because} - {Recommendation}`, each `Justified as-is:` line verbatim, and its `No <category> findings.` lines collapsed into one `Necessity: no findings in {categories}` line. These standing conditions stay here even when STEP 6 is skipped and the Store and Loading lines read `n/a`.

```markdown
## Engine Gate

Detected: {m_EditorVersion} | Floor: 6000.3.x | Result: {At or above floor | Below floor - stopped | Unknown - asked}

## Project Surfaces

| Surface | Detected | Applied |
|---|---|---|
| Render pipeline | {URP 2D Renderer \| URP Universal Renderer \| URP - renderer not visible \| Built-in \| unknown} | {yes \| caveated \| unused - present but this feature does not touch it \| absent \| unknown} |
| Input | {Input System \| legacy \| package present, legacy calls \| unknown} | {yes \| caveated \| unused - present but this feature does not touch it \| absent} |
| UI | {UI Toolkit \| uGUI \| mixed \| unknown} | {yes \| out of scope \| UI Toolkit only - uGUI untouched \| n/a} |
| Persistence | {JSON file \| PlayerPrefs \| binary file \| other: <name> \| mixed: <stores> \| none \| unknown} | {yes \| caveated \| unused - present but this feature does not touch it \| absent} |
| Content loading | {Addressables \| Resources \| mixed \| none \| unknown} | {yes \| caveated \| unused - present but this feature does not touch it \| absent} |

## Open Questions   {only in a run stopped at STEP 1}

1. {question, grouped by the STEP 1 cluster it belongs to}

## Design Findings

- {blocking finding, standing condition, `Precondition:` line, or overengineering line, one per bullet | none}

## Assemblies

| Assembly | References | Contains |
|---|---|---|
| {name} (`noEngineReferences: true` on the rules assembly) | {references} | {types} |

## Files Generated

- {path, one per bullet, grouped by layer: rules / runtime / config assets / scenes and prefabs / ui / tests; an existing file the feature changed marked `(modified)`, a moved one `(moved from <path>)`, an asset that needs the editor `(manual - <editor step>)`}

## Open Assumptions

- {each STEP 1 gap the approver did not close, and the answer built on | none - every question answered}

## Rules Model

- State: {type | unchanged - feature adds no rules state}

- Move: {type -> result type | none - feature adds no move}

- Phases: {enum values | none - no phase enum added}

- Seams: {IClock, generator in state, IRandom, others | none added}

## Scenes and Prefabs

| Asset | Kind | Composition root | Purpose |
|---|---|---|---|
| {asset} | {scene \| prefab \| variant} | {yes \| no} | {why it exists} |

## Screens

| Screen | Stack position | Loading | Error | Empty |
|---|---|---|---|---|
| {screen} | {position} | {state} | {state} | {state} |

## Save Impact

- Schema version: {old | none - unversioned legacy store} -> {new}

- Migration: {step | none - bump only: added field with default | none - no save-shape change}

- Offline queue: {where it lives, its drain trigger, and the key that makes a replayed entry idempotent | n/a - nothing queued}

- Store: {the store this feature's data goes into - the existing one, or a new one with the reason | n/a - nothing persisted}

## Content Impact

- Banks: {banks touched, with identifier stability and import-time validation | none - no content bank touched}

- Loading: {strategy sized to the bank | n/a}

## Deviations

- {each place the build departs from this skill's rules, with the reason - a MonoBehaviour holding rule state, a mutated ScriptableObject, strings not behind a localization key, a DI container, a flagged locale | none}

## Deferred

- {each `Deferred:` line an atomic emitted whose owning skill this workflow did not invoke in this run, verbatim | none}

## Accepted Exposure

- {one sentence each: the clock-trust level chosen and the exploit it accepts (accrual), and each grant no server makes authoritative (security) | n/a - nothing accrued or granted}

## Server Exchange

| Value | Authoritative side | Conflict rule | Offline behaviour |
|---|---|---|---|
| {value} | {server \| client} | {rule} | {behaviour} |

- Old-build compatibility: {how an installed older version behaves against this contract}

## Platform Tiers

| Tier | Shipped | Caveats applied |
|---|---|---|
| {mobile \| desktop \| WebGL} | {yes \| no} | {caveats} |

## Tests

- EditMode: {count | 0 - feature added no engine-free code}

- PlayMode: {count | 0 - no engine behaviour under test}

## Performance   {only for a performance fix}

- Before -> after: {figure, device, build | not measured - <reason>}

## Validation

**Status:** {verified - every applicable check ran and passed (PlayMode n/a with 0 tests) | unverified - <which checks could not run, and why>; run before merging: <exact commands>}

- {command -> result, one bullet per STEP 8 check}
```

`## Server Exchange` is the single line `n/a - feature makes no server call` when there is none, with no table and no Old-build line.

## Self-Check

- [ ] STEP 1: `behavioral-principles` loaded first
- [ ] Engine version read from `ProjectVersion.txt` and compared numerically to `6000.3.x`; below-floor stopped rather than degraded
- [ ] Render pipeline, input, UI, persistence, and content loading confirmed; uGUI reported out of scope where detected
- [ ] Requirements gathered by cluster; design approved before code, an explicit waiver honored with every default recorded in Open Assumptions, or the run stopped after STEP 1 with its questions
- [ ] STEP 2: deviations, the blocking assembly finding, `Precondition:` lines, and the `unity-overengineering-review` result written under Design Findings
- [ ] Rules assembly sets `"noEngineReferences": true`; where none existed, one was created for this feature's types and any moved file marked
- [ ] Move-driven state: moves return new state plus a changed flag; resolution loops carry a stated bound
- [ ] Time and randomness reach rules only through the seams the feature uses (`IClock`; generator in state for move-driven, `IRandom` for fixed-tick); no ambient time or randomness in a rule
- [ ] MonoBehaviours exist only for engine hooks; composition root wires them, no `GameObject.Find`
- [ ] Statics and static events reset via `[RuntimeInitializeOnLoadMethod]`; subscriptions paired
- [ ] ScriptableObjects hold configuration only, never mutated at runtime
- [ ] Rule progression never waits on an animation; a UI control gated on a presentation has a skip, a reduced-motion path, and an `OnDisable` reset
- [ ] Queries cached at bind time; every screen renders loading, error, and empty; a new setting is wired into the existing sites it governs
- [ ] Non-colour redundancy, touch targets, text scaling, and a reduced-motion path present
- [ ] User-facing strings behind localization keys, or held in one type with the deviation stated where the project has no localization system
- [ ] Deviations, accepted exposure, and unresolved `Deferred:` lines written in the report, `none` / `n/a` where there are none
- [ ] Save-shape change bumps the version, with a migration where old data cannot load as-is; save written on pause; every async surface has a timeout, a cancellation path, and a resume behaviour
- [ ] Where the feature calls a server: authoritative side, conflict rule, offline queue, and old-build compatibility stated; merge logic lives in the rules assembly with a test per conflict case
- [ ] Content bank identifiers stable and validated at import
- [ ] EditMode tests cover the rules core; PlayMode limited to engine behaviour; test asmdefs carry `UNITY_INCLUDE_TESTS`, the EditMode one referencing the rules assembly
- [ ] Compile, EditMode run, PlayMode run, and a primary-target build all executed with no `-quit` on `-runTests`, or the unavailable ones named with the commands to run before merging

## Avoid

- Game rules written inside `Update` or any other lifecycle callback
- A rules assembly without `"noEngineReferences": true`
- `MonoBehaviour` on a class with no engine callback
- ScriptableObjects used as mutable runtime state
- `?.`, `??`, `??=`, `is null`, or `is not null` applied to a `UnityEngine.Object`
- `GameObject.Find`, `FindAnyObjectByType`, `FindFirstObjectByType`, or `FindObjectsByType` inside logic
- Mutating board state in place where undo or replay is required
- Resolution loops with no bound
- Rule progression gated on animation completion (a UI control gated on a presentation is not this - see STEP 5)
- `Q`/`Query` called per frame instead of cached at bind time
- Colliders, rigidbodies, or trigger overlaps used to model a grid board
- Colour as the only carrier of a game-relevant distinction
- Hardcoded user-facing strings
- A save-shape change with no schema version bump, or an old shape that cannot load with no migration
- Saving in `OnApplicationQuit` on a mobile target
- PlayMode tests for logic that the engine-free rules assembly could test in EditMode
- Writing code before design approval
- Proceeding with guidance on a below-floor engine version
- Reporting a clean run without executing the STEP 8 commands
