---
name: task-unity-review
description: Unity 2D code review - engine-free core discipline, lifecycle traps, prefab and scene hygiene; spawns perf and security subagents.
agent: unity-tech-lead
metadata:
  category: mobile
  tags: [unity, csharp, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Unity Code Review

Staff-level Unity 2D review umbrella. Covers correctness, architecture, AI quality, maintainability. Coordinates perf / security subagents in parallel.

## When to Use

- Pre-merge review of a Unity branch or fetched PR ref against its base
- Post-AI-generation quality gate
- Architecture drift detection - specifically, erosion of the engine-free rules boundary
- Pre-merge risk assessment

**Not for:** pre-implementation design (`task-unity-implement`), single-error triage (`unity-engineer`), new-system architecture, single-scope reviews (delegate to perf/security).

## Depth

| Depth | When | Runs |
|-------|------|------|
| `standard` | Default | Phases A-E |
| `deep` | Architecture changes, post-incident, Principal sign-off, or Risk High/Critical | A-E + the touched files' history: `git log -p -n 10 <head_ref> -- <path>` per touched source file, read for a reverted fix, a recurring defect, or the same shape in a prior commit (Phase C's anemic-rules evidence) |

**Auto-promote to `deep`** happens at Step 5; a depth the user passed wins.

## Scope

| Scope | What runs |
|-------|-----------|
| Core | Phases A-E |
| + Perf | Core + `task-unity-review-perf` subagent |
| + Sec | Core + `task-unity-review-security` subagent |
| Full | Core + both in parallel |

Default: **Core with auto-escalation**. Pass `core-only` to suppress.

This client consumes API contracts rather than designing them: a finding that the game mishandles a contract belongs to Core, and a finding that the contract itself is wrong routes to the owning service's team.

**Auto-escalation signals:**

- **+Sec:** a reward, currency, or entitlement granted in client code; an IAP purchase handler; a rewarded-ad completion callback; a save write with no integrity check; an API key, signing key, or SDK secret in source or a committed config; a new deep-link handler; a remote-config value driving economy or unlocks; a new third-party SDK; a consent or ATT/GDPR/COPPA-related change
- **+Perf:** allocation inside `Update`, `FixedUpdate`, `LateUpdate`, or a per-frame callback; a new `Instantiate`/`Destroy` on a repeating path; LINQ or string concatenation in a hot path; a new sprite, texture import setting, or material variant; a new transparent or overlapping 2D layer; a `Find`/`GetComponent` call in a per-frame path; a new scene load; a large collection held in memory
- **2+ categories -> Full**

Signals are matched syntactically, then checked for direction: a texture import change that lowers max size or adds compression, a `Destroy` removed in favour of a pool, or an allocation deleted from `Update` is the fix, not the defect. Log it as `signal: <category> -> <path> (improving - not escalated)` and do not escalate on it alone.

There is no `+Ux` scope. Accessibility, aspect-ratio adaptivity, and localization are reviewed at baseline depth in Phase E, and designed in `task-unity-implement`; there is no dedicated UX lens to escalate to.

## Reviewable Surface

Unity projects mix source, generated output, and authored assets. The three are not reviewed the same way.

| Surface | Treatment |
| --- | --- |
| `.cs` under `Assets/` (excluding third-party SDK folders) | full review surface |
| `.unity`, `.prefab`, `.asset`, `.inputactions`, `.uxml`, `.uss`, `.spriteatlasv2`, `.controller`, and any other hand-authored asset under `Assets/` | **review surface** - a scene wiring change, a prefab override, an atlas membership change, or a config asset edit is a legitimate finding, cited at the asset path. An extension absent from this list is authored surface unless it is build output |
| `ProjectSettings/*.asset`, Build Profile assets, `Packages/manifest.json` | review surface for build configuration, packages, and SDK additions |
| `.meta` | not a finding surface on its own. A deleted, regenerated, or GUID-changed `.meta` that breaks references **is** a finding, cited at the asset whose reference breaks - when that asset is itself the deleted one, cite the deletion and name the referencing asset even though it sits outside the change set. An import-setting delta in a `.meta` is reviewable, cited at the asset it describes |
| `Library/`, `Temp/`, `obj/`, `Build/`, `Logs/`, generated `*.csproj` / `*.sln` | excluded - build output, never reviewed |
| `Assets/Plugins/` and imported third-party SDK folders | excluded from style and structure findings; still in scope for security data-flow and version concerns |

Unlike a code-generation stack, Unity's assets are hand-authored and carry real defects. A change set touching only build output is a no-op; say so rather than manufacturing findings. A `.meta`-only change set is **not** automatically a no-op - an import-setting delta (compression, max size, mip generation) or a changed `guid:` line is reviewable. Importer-version churn with no setting delta is the no-op case.

Asset diffs are YAML and often large and low-signal. Review what the change *means* (a reference rewired, a component removed, an override added), not the serialized line noise. Cite a line inside asset YAML as `<asset path>:<line>` at the line that carries the meaning (the changed reference or override). When an asset diff is unreadable, say so and ask for the intent rather than guessing.

## Invocation

`/task-unity-review [<branch>|pr-<N>] [--base <branch>] [+perf|+sec|full|core-only] [standard|deep]`

Defaults to the current branch vs its base; `pr-<N>` reviews a locally fetched PR ref. `core-only` suppresses auto-escalation and `deep` forces depth; both are accepted bare or with `--`. `+obs` / `+rel` (forwarded by `task-code-review`'s `full` expansion) have no Unity lens: drop them and resolve the rest - `+perf +sec` is `Full`, and a lone `+obs` or `+rel` leaves the scope flagless. Any other forwarded flag this workflow does not define is ignored and named in Summary Notes. `review-precondition-check` fails fast on a dirty working tree and on a trunk head - review compares committed code only; this workflow's own `review-*.md` checkpoint at the repository root does not count as dirt.

**Never modify the working tree.** Read via `git diff`, `git show`, and `git grep` only. A file's content at the head is read with `git show <head_ref>:<path>` whenever the head is not the checked-out branch.

**Citations, every mode.** A `file:line` is the line number inside that file at the head - read it from the file (`git show <head_ref>:<path>`), or count from the `+<start>` of the hunk header `@@ -a,b +<start>,c @@` - never a line number of the diff output or of a prompt. An asset finding takes `<asset path>:<line>` of the YAML line that carries the meaning, or the bare asset path for a binary asset reviewed through its `.meta`.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack and Project Shape

Read `ProjectSettings/ProjectVersion.txt`. If it is absent, stop - this workflow reviews Unity projects only. If it is present but unparseable, say so in Summary Notes and review with version-independent findings only.

After Step 3.5 has not stopped the run, record from the head, each from its source: render pipeline (the asset assigned in `GraphicsSettings.asset` / `QualitySettings.asset` and its renderer); input system; UI system; persistence; server presence (the Server Presence table in `task-unity-review-security`); scripting backend (`ProjectSettings/ProjectSettings.asset`); target frame rate (the `Application.targetFrameRate` call site, or `not set`); Addressables presence; platform targets. A field its source cannot settle is `unknown - <what was seen>`. The lens subagents receive these.

**Engine floor.** The plugin targets Unity 6.3 LTS (`6000.3.x`) and newer. Compare numerically by component, not by string prefix. Below the floor, note in Summary: `Detected <version>; this plugin targets 6000.3.x and newer - version-specific guidance may not apply.` and review rather than stopping; a review that refuses to run helps nobody mid-change. This workflow alone continues below the floor - `task-unity-implement`, `task-unity-test`, and both lens workflows stop. A below-floor run therefore keeps scope at Core, and records `Scope incomplete: <scope> - below engine floor` only for a lens that *would otherwise have run*. A lens the user suppressed with `core-only` was declined, not lost: its signals go to the Summary's Signals line and no `Scope incomplete` line is written. At or above the floor (`6000.3.x`, `6000.4.x`, and later), proceed normally. The Stack Detected marketing name for any `6000.<minor>` is `Unity 6.<minor>`.

Reduced confidence is concrete, not an adjective: findings resting on version-specific API surface are annotated inline with the version they assume, and no finding is downgraded on version grounds alone.

**UI system.** If the diff's UI is uGUI, note once in Summary: `uGUI detected; UI Toolkit guidance does not apply.` Review uGUI changes for correctness and layering only - do not flag uGUI for not being UI Toolkit, and do not propose a migration.

### Step 3 - Resolve the Change Set

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review`. Surface fail-fast messages verbatim and stop. Hold the handle's `prior_checkpoint` (a block, the scalar `legacy`, or absent) for Step 3.5.

Fix `branch` = the handle's `head_short_name` (never `HEAD`, never remote-prefixed); it names the review target in the no-op message and the writer's `branch` field. `head_ref` passes through unchanged to the diff commands and the writer. Capture `current_head_sha = git rev-parse <head_ref>` and `current_base_sha = git rev-parse <base_ref>` - Step 3.5 needs only these. Once Step 3.5 has not stopped the run, read once and reuse:

- `git diff <base_ref>...<head_ref>` for the change body
- `git diff --name-status <base_ref>...<head_ref>` for the file list
- `git log --oneline <base_ref>..<head_ref>`

The name-status list is the changed set; the Reviewable Surface table decides which of it is analysed. A binary asset git reports as `Binary files differ` is not diffed - its `.meta` carries the reviewable import settings. Where the changed and reviewed counts differ, state both once in Summary's `Files:` line.

### Step 3.5 - Decide Round

Every round analyses the full `<base_ref>...<head_ref>` range; round 2+ differs only in reconciling against the prior report (Step 7.5). Apply the first matching row:

| Handle's `prior_checkpoint` | Decision |
| --- | --- |
| absent | `round = 1` |
| `legacy` | `round = 1`; note `Prior report lacks checkpoint metadata - treated as round 1.` (Step 8 overwrites it) |
| `head_sha == current_head_sha`, `base_sha == current_base_sha`, and its `scope` / `depth` cover the invocation's flags (`+perf +sec` or `full` covers every scope, any scope covers `core-only`, an invocation with no scope flag is covered by any prior scope - an unchanged diff resolves to the same scope, and a user who wants a lens after a `core-only` run passes it - `deep` covers `standard`, and an invocation with no depth flag is covered by either; compare in the writer enum per Step 8) | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` (`<sha_short>` = first 7 chars of `current_head_sha`) and stop - no review, no report write |
| any other valid checkpoint | `round = prior.round + 1`, `prior_head_sha = prior.head_sha` |

On round 2+, note in Summary each that applies: `Same head as round <prior.round>; re-review for expanded <scope or depth>.` (head unchanged), `Base branch advanced since round <prior.round>.` (`base_sha` differs), `Prior checkpoint unreachable - history rewritten.` (`git merge-base --is-ancestor <prior.head_sha> <current_head_sha>` fails). Scope and depth resolve on the full range exactly as on round 1; nothing is inherited from the checkpoint.

### Step 4 - Scope Auto-Escalation

Scan file list / diff for signals listed under **Scope**, ignoring excluded surfaces. Log each as `signal: <category> -> <file:line>`. Then:

- Zero signals or `core-only` -> Core
- One category -> add matching scope
- 2+ categories -> Full
- Explicit scope -> respect; still log signals

**Scope precedence:** user flag > firing signals. Every logged signal - escalating, declined by `core-only`, or improving - goes to the Summary's Signals line.

### Phase A - Risk Snapshot

Assess cross-cutting risk for the change set as a whole, on this scale:

| Risk | When |
| --- | --- |
| Critical | A defect on a critical path that reaches every player with no fallback - save loss or corruption on upgrade, a purchase or a reward of real value granted or lost, economy math wrong for everyone |
| High | The change touches a critical path (save migration, purchase or reward grant, economy math, progression unlock, scoring) or a shared surface (the rules assembly, any `.asmdef`, the bootstrap scene, a shared prefab, the save layer, the composition root, `ProjectSettings/`) |
| Medium | Feature-local change with player-visible behaviour, no critical path, no shared surface |
| Low | Isolated change - no critical path, no shared surface, no player-visible behaviour change |

Output the risk level before any findings.

**Low-risk short-circuit:** if Risk is Low **and** the change does not touch an architecture-relevant file (the shared surfaces above) **and** does not touch a localized string, string table, font asset, or asset identity (a deleted or regenerated `.meta`), skip Phases C-E. A prefab is shared when more than one scene or prefab references it: search for its GUID at the head (`git grep <guid> <head_ref> -- Assets`) rather than defaulting - the change set alone never shows it, and defaulting to shared would retire the short-circuit entirely. Where the search cannot run, say so and treat it as shared. Escalated scopes still run (a Step 4 signal fired for a reason); their merged findings join High-Impact Findings. The streamlined report contains Summary, Prior Round Reconciliation (round 2+), High-Impact Findings (Phase B + any subagent findings), Next Steps, and Lens Detail when a lens returned one; Steps 7.5 and 8 still run.

### Step 5 - Re-evaluate Depth After Phase A

If Risk is High / Critical, set depth to `deep` and surface `auto-promoted from standard; Risk: <level>` on the Summary's Depth line **before** Phases B-E. A depth the user passed wins over auto-promotion.

### Phase B - Unity Correctness and Safety

Apply atomic skills; each owns canonical patterns:

- Use skill: `csharp-unity-patterns` - the `UnityEngine.Object` lifetime `==` overload, allocation in hot paths, async correctness
- Use skill: `unity-monobehaviour-lifecycle` - callback order, initialization traps, static state across Play sessions, coroutine lifetime
- Use skill: `unity-architecture-patterns` - the engine-free rules boundary, injectability, global lookups
- Use skill: `unity-serialization-prefabs` if the diff touches serialized fields, prefabs, scenes, or `.meta` files
- Use skill: `unity-2d-rendering` if the diff touches sprites, atlases, materials, or sorting - Core owns their correctness (atlas membership, sorting, a broken material reference) whether or not `+perf` runs
- Use skill: `unity-2d-gameplay-patterns` if the diff touches board, turn, or rule logic
- Use skill: `unity-game-economy-progression` if the diff touches currency, rewards, progression, or offline accrual
- Use skill: `unity-2d-physics-input` if the diff touches input actions, `.inputactions`, colliders, or rigidbodies
- Use skill: `unity-ui-patterns` if the diff touches a UI Toolkit screen, UXML, or USS
- Use skill: `unity-content-data` if the diff touches a content bank, ScriptableObject catalog, or Addressables content
- Use skill: `unity-save-persistence` if the diff changes the save schema. Check installed-version impact directly: a save written by an older installed build must load in this one (or migrate), a save this build writes that an older build meets (downgrade, backup restore, cloud sync from a newer device) is refused with an explanation rather than loaded as if the fields matched, and the server contract an installed build expects must still hold

**Atomic blocks become findings.** Each atomic emits `### [Critical | High | Medium | Low] anchor` blocks. Each becomes one finding: label `[Must]` for Critical / High, `[Recommend]` for Medium / Low; heading `### [Label] <anchor as file:line>` (per the citation rule); `Issue:` the block's `Category` value plus the first clause of its `Impact`; `Impact:` and `Fix:` from the block. Two blocks are not findings: `unity-ui-patterns`' `OutOfScopeUI` blocks become the Summary's uGUI note, and `unity-i18n`'s single-locale scope header goes to Summary Notes.

**Named checks.** Several overlap the atomics above by design - they are the highest-recurrence Unity defects and must not be lost in a long atomic report. Emit one finding per defect: when an atomic already raised it, keep that finding; never file the same defect twice.

- **Test coverage finding (named, not buried).** The change adds rule logic without a matching EditMode test -> `[Recommend]`; escalate to `[Must]` when critical path: save migration, purchase or reward grant, economy math, progression unlock, or scoring. Rules that cannot be tested without Play mode are themselves the finding - cite the engine coupling
- **Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance
- **Destroyed-object access.** `?.`, `??`, `??=`, `is null`, and `is not null` bypass Unity's lifetime `==` overload, so a destroyed object passes those checks and then throws. Any of them applied to a `UnityEngine.Object` is a finding
- **Await on a destroyed object.** Any `await` inside a `MonoBehaviour` that resumes and touches `this`, a component, or a `GameObject` needs a cancellation path tied to the object's lifetime
- **Engine-free boundary.** Rule logic added to a `MonoBehaviour` when a rules assembly exists is architectural drift, not a style preference
- **Loading, error, and empty states.** Any screen driven by async work renders all of them, not just the happy path
- **Secrets and grants.** No API keys, signing keys, or SDK secrets in source or committed config. No currency, reward, or entitlement of real value granted by client code alone - a `[Must]` in Core whether or not `+sec` runs. Where Step 2 found no server, the server half is recorded as accepted exposure and the finding is `[Must]` only through its client-side remainders (a grant with no precondition, a missing durable write), `[Recommend]` when none exist
- **Untrusted input at the edges.** Deep-link parameters, remote-config values, and downloaded content are attacker-controllable and validated before use
- **Save schema changes** follow the installed-version rule above
- **Build configuration.** Use skill: `unity-build-release` if the diff touches `ProjectSettings/`, a Build Profile, an `.asmdef`'s platform set, or packaging. A scripting-backend switch or a raised managed-stripping level is a Core finding regardless of whether `+sec` runs: stripping removes reflection-reached types, so a reflection-based save DTO deserializes in the editor and returns a default profile in the release build. Name the serializer or require the release-build load test

**Perf defects with +Perf not running.** A per-frame allocation or a cloned material an atomic raises stays a Core finding at its mapped label; Core does not run the lens's checklist to find more.

**Atomic `Deferred:` lines.** A `Deferred:` line naming another Core atomic resolves at the phase that applies that atomic - and makes that phase apply it for that defect when its trigger above did not fire. One naming a lens-owned skill (`unity-performance`, `unity-security-patterns`) is a scope signal: log it on the Signals line and re-resolve scope with it before Step 6 (a user flag still wins), so escalation - or its logged decline - carries it rather than dropping it. On the low-risk short-circuit, a deferral to a Phase C-E atomic still runs that atomic for that defect.

**Out-of-diff defects.** A defect read in a file the change set does not touch - one a step already opens (the Step 2 settings reads, a ripple read, a GUID search hit); this review does not go hunting outside the change set - is filed only when it would be `[Must]` or when this change makes it newly reachable; its heading carries `_(pre-existing)_`, plus `_(newly reachable via <file:line>)_` as a separate group when that applies. A lesser one is a Maintainability Notes line. Either way it is never dropped.

### Phase C - Architecture Guardrails

Check layer violations and coupling: a dependency pointing the wrong way across a boundary, a module reaching past its seam, a shared surface gaining a consumer-specific concern.

**Unity-specific:**

- **The engine-free rules boundary is the primary guardrail.** A rules assembly that loses `"noEngineReferences": true`, or rule logic written into a `MonoBehaviour`, is the highest-value architectural finding this review makes
- **Assembly definitions:** a new `.asmdef` reference is a cascading change; a reference from rules outward is a violation
- **`MonoBehaviour` only for engine hooks.** A class with no lifecycle callback, serialized field, coroutine, or collision hook does not need one
- **ScriptableObjects hold configuration, not runtime state.** Runtime mutation of a SO persists in the editor and diverges from a build
- **Dependency injection at the seam,** not `GameObject.Find` / `FindAnyObjectByType` / `FindObjectsByType` / static singletons reached from inside logic
- **Scene and prefab ownership:** shared prefabs and the bootstrap scene are global surfaces; changes to them affect every consumer
- **Anemic rules layer:** logic in presenters while the rules layer only holds data. Raise it as a finding only when a second file in this change set, or a prior commit read at `deep`, shows the same shape; otherwise record it in `Architecture Notes` as a watch item. `deep` widens where the evidence may be looked for; it never substitutes for it

**Multi-platform changes:** when a change affects a platform target, confirm the tier caveats were handled - WebGL has no threads by default and no durable `System.IO`; desktop changes input modality and window handling.

### Phase D - AI-Generated Code Quality

- Check verbosity and over-engineering directly: overly complex methods, deep nesting, oversized files, and over-abstraction
- Use skill: `unity-overengineering-review` for `MonoBehaviour` without engine hooks, ECS or a DI container for a small casual game, ScriptableObject-per-constant, event buses for two callers, pooling one instance, single-implementer interfaces, and dead feature flags. Its `[Must]` / `[Recommend]` blocks become findings at their own label: `Unnecessary because:` or `Missing because:` -> `Issue:`, `Cost:` -> `Impact:` (on `[Must]`; a `[Recommend]` states the impact from the block), `Recommendation:` -> `Fix:`
- The atomic's per-category `No <category> findings.` lines are this workflow's evidence the check ran and are not reproduced in the report; its `Justified as-is:` lines are reader-facing and land in Maintainability Notes

**Additional AI smells** (not owned by the atomics above):

- Test verbosity (a PlayMode test with full scene setup for an assertion an EditMode test covers)
- Comment cruft (restating method names, doc comments on private helpers)
- Defensive null checks on serialized fields that every scene and prefab instance assigns (verified in their YAML)

### Phase E - Maintainability

Check that failure paths added by the change leave a log or error record behind rather than failing silently. Use skill: `unity-accessibility` for baseline touch-target, contrast, and non-colour-only signalling presence. Use skill: `unity-i18n` if the diff touches a user-facing string, a string table, or a font asset - a font swap on a localized label is a glyph-coverage change, and a locale whose glyphs are missing ships blank boxes.

**Unity-specific:**

- Naming: `PascalCase` types and methods, `camelCase` locals and private fields, including serialized ones (the inspector prettifies the name); renaming a serialized field needs `[FormerlySerializedAs]` or the saved value is lost
- Magic numbers extracted to named constants or config assets
- Hardcoded user-facing strings routed through localization
- `Debug.Log` on per-frame paths, or verbose logging left in release without `[Conditional]`
- Duplicated prefab or UXML subtrees: the same structure in 3+ places becomes a shared prefab or a reusable UI component
- Asset hygiene: no orphaned `.meta`, no missing script references, no unintended prefab overrides
- Accessibility baseline: touch targets meet minimum size, no state signalled by colour alone

### Step 6 - Delegate Extra Scopes in Parallel

Skip if scope is **Core only**. For each selected scope, spawn one independent subagent **in parallel** with the main thread. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; a security review is not a `unity-tech-lead` spawn:

| Scope | Skill | Subagent (`subagent_type`) |
| ----- | ----- | -------------------------- |
| +Perf | `task-unity-review-perf` | `unity-performance-engineer` |
| +Sec | `task-unity-review-security` | `unity-security-engineer` |

`Full` = 2 subagents. Where subagents cannot be spawned, run each lens inline in its subagent mode, with the same inputs and the same return shape, and note `Lenses run inline` in Summary Notes.

**Subagent prompt contract:**

- Resolved `base_ref` / `head_ref` + the pre-read diff, name-status, and commit log; the lens does not re-read them, and reads file content at the head with `git show <head_ref>:<path>` (security also `git log -p` for removed controls)
- The `behavioral-principles` Rules inlined in the prompt, or an instruction to load it as the lens's Step 1
- Depth level - the parent's resolved depth, which overrides the perf lens's depth table (security always runs `deep`)
- The Step 2 project shape: engine version, render pipeline, input system, UI system, persistence, scripting backend, target frame rate, Addressables presence, platform targets
- The Reviewable Surface table above
- The citation rule above: `file:line` citations are lines in the file at the head, never lines of the diff or of this prompt
- Return findings in own Output Format

**Failure isolation:** if a subagent fails or times out, continue with the rest. Note the missing scope in Summary.

### Step 7 - Synthesize (only if Step 6 ran)

Merge subagent findings into single Output Format. Do not append raw reports.

**Project each lens finding first.** It becomes a `### [Label] file:line` heading - the first path of its `Location` line (for perf's `<mount site> -> <defect body>`, the path the diff touched), then its `_(pre-existing)_` and `_(carried from round <N>)_` groups as separate groups - followed by `- Issue:`, `- Impact:`, `- System Risk:` (on `[Must]`, written here from Phase A and the lens's stated exposure), `- Fix:`, and the lens's `- Control type:` (+Sec) or `- Evidence:` (+Perf) line. Label: +Perf's `Intent:` value; +Sec's severity, Critical / High -> `[Must]`, Medium / Low -> `[Recommend]` - except that a +Sec finding whose Control type is `accepted exposure` is `[Must]` only when it names a client-side remainder, and `[Recommend]` otherwise, its severity kept in the Impact prefix. Issue: the lens's Issue, with +Sec's `Regression of:` appended when present. Impact opens with the lens band (`+Sec Critical:`, `+Perf High Impact:`), then +Perf's `Player-Visible Impact` and `Owner`, or +Sec's `Attack` and `Impact` joined in one line. Fix: the lens's Fix, with +Perf's `Verify:` appended. An import-setting finding cited at an asset whose own path is absent from the name-status takes the `.meta` path in the heading. `review-prior-findings-reconcile` parses only this shape on the next round, so nothing downstream reads lens headings.

- Deduplicate cross-cutting findings (one entry citing all scopes)
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend`
- Preserve `file:line` citations
- Order by intent, not scope
- Note missing scopes as `Scope incomplete: <scope>`
- Build Next Steps from the merged findings with `[Implement]` / `[Delegate]` tags. A +Sec finding whose Control type names `server authority`, or whose fix is a console or store declaration, also yields a `[Delegate]` entry; an `accepted exposure` server half yields none
- +Perf `## Routed` lines naming `task-unity-review` are checked against Core's findings (Phase D's for over-engineering): one Core already filed is dropped, one it did not is filed now at the label its atomic would give. Lines naming `task-unity-review-security` are checked against +Sec's findings when +Sec ran, and logged as a +Sec signal when it did not
- Lens non-finding returns have fixed homes: +Perf's `## Unattributed` becomes the Summary's `**Unattributed:**` line; +Perf's `## Device & Measurement Plan` and +Sec's `## Asset Triage`, `## Reviewed, Not Filed`, `## Limitations`, and `## Lens Context` are preserved verbatim under `## Lens Detail` at any depth

**Lens seams.** One defect can legitimately surface in two lenses: a save re-serialized every frame is both security (an unverified write is a tamper surface) and perf (the allocation and I/O cost). Keep the integrity finding under +Sec and the frame-cost finding under +Perf, deduped to one line at the strongest intent. A batching or atlas change that breaks how something looks (wrong sort, a missing sprite) is Core's via `unity-2d-rendering`; its frame cost is +Perf's. A hardcoded user-facing string is a Phase E maintainability finding, not +Sec, unless the string is itself a secret.

**Seam fallback.** Two lenses claiming one defect with no rule above: keep it under the lens whose fix removes the defect, and name the other lens in the finding. Never drop it because ownership was unclear.

**Cross-phase same root cause.** When one defect spans multiple phases (rule logic in a `MonoBehaviour` that is also untestable), file the finding once under the phase where the root cause sits and reference its `file:line` from `Architecture Notes` or `Maintainability Notes`. Do not double-count.

### Step 7.5 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise Use skill: `review-prior-findings-reconcile` with `prior_report` (the body of the file at the handle's `report_path`, frontmatter excluded), the Step 3 diff and name-status, `head_sha = current_head_sha`, and `head_files` (`git ls-tree -r --name-only <current_head_sha>`) when the name-status has a `D` entry.

Its table, note line, and tally render under `## Prior Round Reconciliation`. A `Still open` or `Needs re-check` row this round re-derived publishes once in High-Impact Findings at this round's label. One it did not re-derive is still unresolved: publish it there at its prior label and its prior heading verbatim, with its `_(pre-existing)_` group kept and `_(carried from round <prior.round>)_` as its own group, replacing any earlier carried group - reconcile parses only that section, so a row kept out of it is invisible to round 3. Re-deriving means reading the cited site at the head; a re-derived row publishes at the site where the smell now sits, and an untouched `_(pre-existing)_` row is carried without a read. Both kinds fold into Next Steps with an `(open since round <prior.round>)` suffix. A prior label outside `[Must]` / `[Recommend]` stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried.

### Step 8 - Write Report

**Assessment** follows the open-label set, first match wins: `Request Changes` when any `[Must]` is open - this round's findings and carried `Still open` / `Needs re-check` rows alike; `Discuss` when no `[Must]` is open but a `[Recommend]` rests on an assumption only the author can settle; `Approve` otherwise.

Use skill: `review-report-writer` with `report_type: review`, `report_body` (the assembled report), `branch` (Step 3), `base_ref` / `head_ref` as the handle emitted them, `base_sha = current_base_sha`, `head_sha = current_head_sha`, `mode: full`, `round` and (round 2+) `prior_head_sha` from Step 3.5, `scope` (Step 4's resolution in the writer enum: `Core` -> `core-only`, `+Perf` -> `+perf`, `+Sec` -> `+sec`, `Full` -> `+perf +sec`), `depth` (resolved/auto-promoted), `stack: unity`, and `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` when present. Print the writer's confirmation line.

## Feedback Labels

| Label | Meaning |
| ----- | ------- |
| [Must] | Do not merge until this is fixed. |
| [Recommend] | Fix, or push back with reasoning. Cannot be silently acked. |

Every finding carries exactly one label: `[Must]` or `[Recommend]`. No other label is written.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit the report body as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence. Omit empty sections, and a `[Must]` or `[Recommend]` heading level with no findings.

```markdown
## Summary

- **Assessment:** {Approve | Request Changes | Discuss} - {open [Must] count, and on Discuss the assumption to settle}
- **Risk Level:** {Low | Medium | High | Critical}
- **Stack Detected:** Unity <internal version> (Unity <marketing name>)
- **Render Pipeline:** {URP 2D Renderer | URP Universal Renderer | HDRP | Built-in | unknown}
- **Input:** {Input System | legacy | both}
- **UI:** {UI Toolkit | uGUI | both | none}
- **Persistence:** {<store> | none}
- **Scope:** {Core | +Sec | +Perf | Full}{; auto-escalated from Core}   {suffix only when auto-escalated}
- **Signals:** {each logged line as written in Step 4 - `signal: <category> -> <file:line>`, with ` (improving - not escalated)` where that applies - separated by `; ` | none}
- **Depth:** {standard | deep}{; auto-promoted from standard; Risk: <level>}   {suffix only when auto-promoted}
- **Round:** {N}   {round 2+ only}
- **Files:** {N} changed{; <M> reviewed - <what was excluded>}   {suffix only when the two differ}
- **Unattributed:** {carried from the +Perf lens's `## Unattributed`}   {only when a lens returned one}
- **Notes:** {the Step 2 floor and uGUI notes, Step 3.5 round notes, `Scope incomplete: <scope>` lines, `Lenses run inline`, ignored flags, and the handle's `notes`}   {only when any exist}

## Prior Round Reconciliation   {round 2+ only}

{the reconcile skill's table, its note line when it emitted one, and its tally line}

## High-Impact Findings

### [Must] {file:line} {_(pre-existing)_} {_(newly reachable via <file:line>)_} {_(carried from round <N>)_}   {each group only when it applies}

- Issue: {name the Unity or C# pattern}
- Impact: {player-visible or operational}
- System Risk: {why this is system-level}
- Fix: {concrete C# or asset change}
- Control type: {carried verbatim from +Sec - server authority (<team>) | client control | cost-raising only | accepted exposure (<reason>) | <primary> + <secondary>}   {+Sec findings only}
- Evidence: {carried verbatim from +Perf - measured (<device>, <build>) | estimated (no profile) | inferred (<what was not seen>)}   {+Perf findings only}

### [Recommend] {file:line} {same annotation groups}

- Issue: {pattern}
- Impact: {impact}
- Fix: {change}

## Architecture Notes

- Engine-free boundary: {state, referencing findings by file:line}
- Assembly and coupling change: {change | none}
- Drift detected: {drift | none}
- Watch items: {single-file shapes Phase C records rather than files}   {only when any}

## Maintainability Notes

- Over-engineering detected: {finding references | none}
- Simplification opportunities: {opportunities | none}
- Justified as-is: {carried from `unity-overengineering-review`}   {only when it returned any}
- Below the filing bar: {out-of-diff defects not filed, one per line}   {only when any}

## Key Takeaways

- {2-4 bullets on systemic impact}

## Next Steps

1. **[Implement]** [Must] {file:line} - {one-line action}
2. **[Delegate]** [Recommend] [scope: server contract] - {one-line action}

## Lens Detail   {only when a lens returned a non-finding section}

### <Lens> - <section title as returned>

{the subagent's section, unmodified}
```

Next Steps order: Must > Recommend; within a band, by fix dependency - the item another item's fix depends on goes first. Next Steps is omitted when there are no actionable findings. Lens Detail sections are analysis, not findings - never merged into High-Impact Findings and never dropped.

## Rules

- Review whole-change system impact, not file-by-file
- Lead with risk; line-level findings follow
- Apply C# and Unity conventions
- Actionable feedback with C# code or a concrete asset change
- Build output is excluded from findings; authored assets are review surface
- Default Core; auto-escalate; honor `core-only`
- Delegate perf / security depth to subagents

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: stack confirmed; engine version, render pipeline asset, input, UI system, persistence, scripting backend, target frame rate, Addressables, and platform targets recorded from the head
- [ ] Engine version compared numerically against the `6000.3.x` floor; below-floor noted, scope held at Core, and version-specific findings annotated inline
- [ ] uGUI, where present, surfaced once rather than flagged as a defect
- [ ] Step 3 - `review-precondition-check` ran with `report_type: review`; `branch` = `head_short_name`; both SHAs captured before the diff, name-status, and log were read once
- [ ] Step 3.5 - round decided (1 / prior + 1 / no-op) before any surface was read; no-op exits without writing; round notes in Summary
- [ ] Build output excluded from findings and signal scanning; authored assets and `ProjectSettings/` treated as review surface; reviewed count stated in Summary where it differs from the changed count
- [ ] Step 4 - scope auto-escalation evaluated; every logged signal on the Signals line
- [ ] Phase A - Risk stated on the scale before any finding; short-circuit decided with a GUID search at the head
- [ ] Step 5 - depth auto-promoted to `deep` when Risk is High/Critical, unless the user passed a depth
- [ ] Phase B: atomic skills applied and their blocks mapped to labelled findings with `Issue:` lines; test coverage, destroyed-object access, await lifetime, engine-free boundary, UI states, secrets and grants, untrusted input, save installed-version impact checked; atomic `Deferred:` lines routed; out-of-diff defects filed with `_(pre-existing)_` or noted below the bar
- [ ] Phase C: rules boundary, assembly references, MonoBehaviour necessity, SO mutation, injection seams, shared-asset ownership
- [ ] Phase D: complexity and over-engineering checked; `unity-overengineering-review` applied
- [ ] Phase E: naming, magic numbers, logging hygiene, asset hygiene, accessibility baseline; `unity-i18n` applied where a string, string table, or font asset changed
- [ ] Missing tests raised as named finding (not buried)
- [ ] Every Must cites system risk
- [ ] Every finding has label + `file:line` + concrete fix
- [ ] Step 6 - extra scopes ran in parallel (or inline, noted) with the resolved refs, pre-read diff, full project shape, and the head-file citation rule
- [ ] Step 7 - lens findings projected to `### [Label] file:line` with their annotation groups, merged into one intent-ordered list; `[Delegate]` entries derived from +Sec Control types; +Perf Routed lines resolved; no raw reports appended
- [ ] Step 7.5 - on round 2+, `review-prior-findings-reconcile` ran with `head_sha`; table under `## Prior Round Reconciliation`; unresolved rows carried with their groups into High-Impact Findings and Next Steps; legacy labels mapped
- [ ] Lens seams (sec/perf, perf/rendering overlap) deduped to one line at strongest intent; unlisted seams resolved by the fallback rather than dropped
- [ ] Lens non-finding returns routed to their fixed homes under `## Lens Detail` or the Summary's Unattributed line - none merged into findings, none dropped
- [ ] Failed / missing subagent scope noted as `Scope incomplete: <scope>`
- [ ] Next Steps produced with `[Implement]` / `[Delegate]` tags, ordered by intent
- [ ] Step 8 - Assessment derived from the open-label set; report written via `review-report-writer` with every required field (`stack: unity`, `mode: full`, round, both SHAs, `prior_head_sha` on round 2+); confirmation line printed

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase/fetch/stash) - the review reads history only
- Raising findings against `Library/`, `Temp/`, `obj/`, `Build/`, or generated `*.csproj` / `*.sln`
- Treating an authored asset (`.unity`, `.prefab`, `.asset`, `.uxml`) as generated output and skipping it
- Quoting serialized YAML line noise instead of stating what the asset change means
- Reviewing without reading the full diff first
- Flagging a project for using uGUI, a DI container, or ECS it already standardized on
- Reviewing the server's API contract here - it belongs to the owning service's team
- Generic backend conventions where a Unity idiom exists ("move it off the rules assembly", not "optimize the query")
- Vague feedback ("this could be better")
- Blocking on personal preference
- Running extra scopes when `core-only` was passed
- Duplicating perf / security depth here
- Sequential extra scopes that could parallelize
- Appending raw subagent reports
