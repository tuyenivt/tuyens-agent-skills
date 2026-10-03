---
name: task-unity-test
description: Unity test strategy and scaffolding - EditMode rules coverage, PlayMode limits, seeded determinism, NSubstitute, test asmdefs, batch-mode CI.
agent: unity-test-engineer
metadata:
  category: mobile
  tags: [unity, testing, edit-mode, play-mode, unity-test-framework, nsubstitute, determinism, asmdef, ci, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Unity Test

Unity-aware test strategy and scaffolding across EditMode and PlayMode, built on the engine-free rules assembly, with determinism and batch-mode CI treated as first-class concerns.

## When to Use

- Test strategy for a new Unity 2D game or feature
- Coverage-gap assessment across the rules core and the engine glue
- Scaffolding tests for an under-covered rules layer, save migration, or screen
- Test pyramid review
- Adding failure-path tests to happy-path-only tests
- Diagnosing a test that passes locally and fails in CI, or passes alone and fails in a suite

**Not for:** debugging a failing test whose production code is wrong (`unity-engineer`), general review (`task-unity-review`).

## Workflow

### STEP 1 - PRINCIPLES, STACK AND PROJECT SHAPE

Use skill: `behavioral-principles` before anything else in this step.

Accept the project shape from a parent workflow when invoked as a subagent. Otherwise read `ProjectSettings/ProjectVersion.txt` and compare `m_EditorVersion` numerically against the **Unity 6.3 LTS floor (`6000.3.x`)**. Below the floor, state the detected version and the floor and **STOP** - guidance for a version the project cannot run is worse than none. At or above the floor (`6000.3.x`, `6000.4.x`, and later) proceeds normally. Unreadable or absent file: say so and ask, rather than assuming; when no answer can arrive in this run, emit the engine gate line with `Unknown - asked` and stop.

Record, each from its source:

- Test Framework: `com.unity.test-framework` in `Packages/manifest.json` or, as another package's dependency, in `Packages/packages-lock.json` - `present` or `absent`. When absent, adding it is the first `Gaps to close` entry, or the first `Order to apply` step in a Flake Diagnosis
- Substitution: NSubstitute (a package or a DLL under `Assets/`), hand-written fakes, or none. A DLL an asmdef lists in `precompiledReferences` that exists nowhere in the project is a broken reference: substitution is `none (broken reference)`, and the reference is reported under Assembly structure
- Domain reload: `ProjectSettings/EditorSettings.asset` - `m_EnterPlayModeOptionsEnabled: 1` with the `DisableDomainReload` flag (value `1`) set in `m_EnterPlayModeOptions` - a value of 1 or 3 - means domain reload is disabled
- UI system, persistence store, and whether Addressables is in use

A value that cannot be read, including one whose file is absent, is recorded as `unknown` and carried forward as `unknown` in the deliverable - never silently defaulted.

### STEP 2 - READ CODE UNDER TEST AND EXISTING TESTS

Ground output in project conventions, not generic templates.

Use skill: `unity-architecture-patterns` for the engine-free boundary and the `IClock` / seeded-generator seams this step looks for.

- Read every `.asmdef`: which assemblies exist, what each references, and whether an engine-free rules assembly exists - one whose `.asmdef` sets `"noEngineReferences": true`. An assembly named for rules without that flag, or whose types use `UnityEngine`, is not engine-free. That answer determines the whole strategy - a project with no engine-free assembly cannot have a fast bulk layer until one exists, and that is the finding to lead with
- Read the target top-to-bottom: the rules types, the MonoBehaviours wiring them, the save DTO and its migration chain
- Find test assemblies by content, not name: any `.asmdef` whose `defineConstraints` holds `UNITY_INCLUDE_TESTS` or whose references include `UnityEngine.TestRunner`. Read one existing EditMode test, one PlayMode test, and any shared setup - learn the project's assertion style, fixture construction, and fake conventions
- Read CI configuration for how tests are invoked, whether EditMode and PlayMode run in separate jobs, and how results surface
- Check whether `Library/` is cached between CI runs

If no existing tests or CI exist: say so, propose conventions explicitly, and give the STEP 8 invocations as the CI starting point rather than designing a whole pipeline.

**When no engine-free assembly exists**, the rules-layer targets are blocked on creating one - and when no asmdef holds the code under test at all, every P1-P4 target is, since a custom asmdef cannot reference `Assembly-CSharp` - and a whole-project re-layering is not the recommendation. Scope the extraction to the P1-P3 targets (the save DTO and its migration chain, the rules the game is graded on, the monetized paths); P4 targets stay blocked and are listed as follow-on extraction; the remaining scripts stay in `Assembly-CSharp`. Say which files move. The DTO types and migration steps move; a `JsonUtility` or other engine call stays in the runtime assembly behind them. State the rejected alternative - testing those rules in PlayMode where they currently sit - and why it loses: a domain reload and scene load per run, forever, and ambient time or randomness still cannot be injected. Write the extraction as the first entry in `Gaps to close`, not as a precondition that stops the deliverable. Scaffolds requested before the extraction exists include the minimal extraction of the types they test - tests cannot compile against code still in `Assembly-CSharp` - and leave the rest of the extraction as the plan. Where the project has no save loader or migration at all, the scaffold defines the first one and says so; it is not presented as extracted code.

### STEP 3 - THE UNITY 2D TEST PYRAMID

| Layer | Tooling | What belongs | Speed |
|-------|---------|--------------|-------|
| EditMode - rules | Unity Test Framework, rules asmdef only | move legality, state transitions, scoring, cascade termination, undo round-trips, economy math | milliseconds; no scene, no Play mode |
| EditMode - data | UTF, plus editor APIs where an asset is read | save migration from each shipped version, corrupt-save recovery, content-bank import validation, asset validation, build-config assertions | fast |
| PlayMode | UTF + `[UnityTest]` | lifecycle order, scene load, prefab wiring, coroutine sequences, a screen's state rendering | seconds each |

**The bulk is EditMode on the rules assembly.** This is the payoff of the engine-free architecture rule: the same logic tested in PlayMode costs a domain reload and a scene load per run, so a project that pushes rules into MonoBehaviours pays for it here, every run, forever.

PlayMode count stays deliberately low. A rule tested in PlayMode is a rule in the wrong assembly - fix the layering rather than the test.

The pyramid percentages in the deliverables are targets for the suite's test count by layer, never a measurement; a project with no tests states them as the split to reach. Default: rules 70%, data 20%, PlayMode 10%, adjusted only for a stated reason (a content-heavy quiz shifts weight to data).

### STEP 4 - DETERMINISM

Non-determinism in a Unity suite is not flakiness to retry; it is a design defect in the code under test.

- **Seeded randomness.** The rules layer takes an injected `IRandom`; tests construct it with a fixed seed. A test touching `UnityEngine.Random` is unreproducible, and its failure cannot be replayed. Assert on a specific sequence only where the PRNG is one the project owns - `System.Random`'s exact sequence is not guaranteed stable across runtime versions
- **Injected clock.** Time-dependent logic takes an `IClock`; tests advance a fake clock rather than waiting. Offline-progress and cooldown tests that sleep are slow and still wrong
- **No frame timing in logic tests.** A rule that needs `Time.deltaTime` to be tested belongs in the rules layer taking a fixed step as a parameter. `yield return null` is for tests of engine behaviour, never for letting a rule "settle"
- **No wall-clock assertions.** `DateTime.UtcNow` inside a test makes it fail at a timezone boundary or on a slow agent

Determinism cases worth having explicitly: same seed produces the same board, replay of a move list reproduces the final state, undo returns exactly the prior state, and a cascade terminates at or below its stated bound.

### STEP 5 - SUBSTITUTION

**The rules layer needs no mocking framework.** Its dependencies are interfaces the test implements directly - a `FakeClock` advancing on command, a `SeededRandom` with a fixed seed, an in-memory save store. Hand-written fakes are clearer in the assertion and cheaper than a mock configuration.

NSubstitute is for the seams where a hand-written fake is more work than the test: a third-party SDK interface, an analytics sink, a remote-config source, or asserting that a call happened at all.

**NSubstitute's presence in the manifest is not a reason to use it.** The test is cost, not category: reach for it only when the fake would be longer than the substitute configuration. A seam the test can implement in a handful of lines - clock, RNG, in-memory save store - is hand-written even when the seam would also qualify by category, and even when the assertion is that a call happened.

```csharp
// Bad - a mock configured to return a value a fake returns in one line (IClock: DateTime UtcNow { get; })
var clock = Substitute.For<IClock>();
clock.UtcNow.Returns(new DateTime(2026, 1, 1));

// Good - a fake the test can also advance
var clock = new FakeClock(new DateTime(2026, 1, 1));
clock.Advance(TimeSpan.FromHours(3));
```

`UnityEngine.Object`-derived types cannot be substituted usefully - they are engine-constructed. Test against an interface the MonoBehaviour delegates to, which is the same seam the production composition root uses.

### STEP 6 - PLAYMODE, COROUTINES, AND ASYNC

`[UnityTest]` returns `IEnumerator` and yields frames (editor updates in EditMode), which is what lets a test observe work across frames:

- `yield return null` advances one frame; use it to let a lifecycle callback or a coroutine step run
- Wait for the condition, capped by a frame or realtime limit that fails the test with a message when exceeded - never a bare fixed frame count (STEP 9 row 2) and never an uncapped wait, which fails only at the framework's default per-test timeout, minutes later and with no diagnostic
- `yield return new WaitForSeconds(...)` uses scaled time and never completes at `Time.timeScale = 0`; use the realtime variant in any test that pauses
- Async methods returning `Task` are supported as test bodies by the Test Framework; verify the supported signature against the installed package version rather than assuming. Every awaited call in a test carries a timeout, so a hung await fails instead of stalling the job
- A PlayMode test that instantiates prefabs or loads scenes tears them down in `[TearDown]` or `[UnityTearDown]`. Leftover objects leak into the next test in the same run

### STEP 7 - TEST ASSEMBLY DEFINITIONS

This is the mechanism that keeps the fast tests fast, and getting it wrong silently converts the whole suite into slow tests.

| Assembly | References | Platforms | Runs in |
| --- | --- | --- | --- |
| `Game.Tests.EditMode` | `Game.Rules`, `UnityEngine.TestRunner`, `UnityEditor.TestRunner`; precompiled `nunit.framework.dll` | Editor only | EditMode - rules |
| `Game.Tests.EditMode.Data` | `Game.Rules`, `Game.Runtime`, `UnityEngine.TestRunner`, `UnityEditor.TestRunner`; precompiled `nunit.framework.dll` | Editor only | EditMode - data |
| `Game.Tests.PlayMode` | `Game.Rules`, `Game.Runtime`, `UnityEngine.TestRunner`; precompiled `nunit.framework.dll` | all target platforms | PlayMode |

- The rules test asmdef references the **rules assembly only**. A runtime reference there lets rule tests couple to MonoBehaviours and recompiles the fast suite on every runtime change; tests that need runtime or editor types (content validation, the engine side of a save) live in the data assembly
- Every test asmdef carries `"defineConstraints": ["UNITY_INCLUDE_TESTS"]`. Without it the test assembly is compiled into the player build, which usually fails to compile there because the TestRunner and NUnit assemblies are not
- Editor-only test assemblies list `Editor` as their only platform; a PlayMode assembly must not reference `UnityEditor` types or it will not compile for a device run
- A DLL such as NSubstitute is declared per assembly: `"overrideReferences": true` and the DLL (with its dependencies, `Castle.Core.dll` among them) in `precompiledReferences` on the test asmdefs that use it, with Auto Reference off and Editor as its only platform in the DLL's plugin importer so it neither leaks into other assemblies nor ships - which means NSubstitute is referenced only from Editor-only test asmdefs
- Every test asmdef sets `"overrideReferences": true`; `precompiledReferences`, NUnit included, is ignored without it

### STEP 8 - CI ON BATCH MODE

```bash
Unity -batchmode -nographics -runTests \
  -projectPath "$PROJECT" \
  -testPlatform EditMode \
  -testResults "$RESULTS/editmode.xml" \
  -logFile -
```

- `-testPlatform` takes `EditMode`, `PlayMode`, or a build target name (which builds a player and runs the PlayMode suite on it - the route for reproducing STEP 9 row 4); run EditMode and PlayMode as **separate invocations**, so the fast EditMode job gates every pull request and the slower PlayMode job can run on a narrower trigger
- `-runTests` implies the editor quits after the run - do not add `-quit`, which can terminate before results are written. This overrides the build-job shape in `unity-build-release`, where `-quit` belongs
- **Gate on the exit code and the `-testResults` XML together.** A failing run exits non-zero, but a run that matched or ran zero tests (a filter mismatch, the wrong platform, a compile skip) exits zero; the XML's test count and result are what catch it. A script that discards the exit code (`Unity ... | tee log` without `set -o pipefail`, `|| true`, a wrapper that never exits non-zero) or never archives the XML is the harness false-green of STEP 9; under `set -e` a failing run already fails the job, so a green job with no results XML points at a run that exited zero without running the tests
- `-logFile -` streams to stdout so CI captures the failure evidence; a log file nobody uploads hides it
- **Licence:** for a serial-based seat, activation runs before the tests and `-returnlicense` after, including on the failure path - an unreleased seat blocks the next run. A licensing-server lease follows that server's release mechanism
- **Coverage**, when `com.unity.testtools.codecoverage` is installed: add `-enableCodeCoverage -coverageResultsPath <dir> -coverageOptions "assemblyFilters:+Game.Rules" -debugCodeOptimization` to the EditMode invocation
- **Cache `Library/`** between runs. A cold agent pays a full asset import and script compile before a single test executes, which usually dominates the job
- `-nographics` is appropriate for EditMode; a PlayMode test that renders or reads back from the GPU may need it removed. Removing it reflexively hides a real failure, so change it only against a specific symptom
- Pin the Unity version to the exact internal version from `ProjectVersion.txt`, not a floating major

### STEP 9 - FLAKE CONTROL

Use skill: `unity-monobehaviour-lifecycle` for static reset and object lifetime (row 1, row 3). Use skill: `unity-build-release` for stripping and preservation (row 4).

Four causes account for nearly all Unity test flake. Diagnose to a named cause before touching the test:

| Symptom | Cause | Fix |
| --- | --- | --- |
| Passes alone, fails in a suite; second run differs from first | **Static state leaking between tests** - the Test Framework does not reload the domain between tests in one run (unless a test yields `RecompileScripts` or `WaitForDomainReload`), so statics and static event subscriptions always survive from one test to the next; in the editor they also survive between EditMode runs, and between PlayMode runs when domain reload is disabled (a fresh batch-mode process resets them) | Reset statics in `[SetUp]`, in every project; the production reset via `[RuntimeInitializeOnLoadMethod]` does not run per test |
| Passes locally, fails on a slower CI agent | **Frame-timing dependence** - the test waits a fixed frame count for work that takes longer under load | Assert on a state change with a bounded wait, not on a frame count |
| Fails depending on which test ran before it | **Scene load order and leftover objects** - a prior test left objects, a `DontDestroyOnLoad` instance, or an additively loaded scene alive | Tear down every instantiated object and unload every additive scene; do not depend on test execution order |
| Fails only in a device or release run | **Stripping or backend divergence** - reflection-dependent code the linker removed | Reproduce on a plain release build - a test-player build includes the test assemblies, whose references can keep a stripped type alive; preserve the type (`unity-build-release`) |

Retrying a flaky test hides one of these four. Quarantine with an issue and a named cause, never with a bare retry.

**One symptom set commonly has several of these at once** - differing failure values across runs are the signal to check every row for a second cause. Diagnose each candidate independently, report every cause that fires and only those, and order the fixes so the cheapest one that unblocks the others goes first.

Two causes sit outside the four rows:

- **Global engine state left non-default by a prior test** - `Time.timeScale` at 0 from an unclosed pause popup, a changed fixed timestep or gravity. It behaves like row 1 but the state is the engine's, not the project's: reset it in `[SetUp]` and fix the test that left it. `WaitForSeconds` never completes at `timeScale = 0`, so this reads as a hang rather than a failure.
- **Harness false-green** - the suite reports success when it did not run: a `-quit` that truncates before results are written, an exit code the script discards, an XML nobody reads, or a job whose `-testPlatform` does not include the failing test. Diagnose against STEP 8. When the reported symptom is a false pass rather than a failure, this is the cause.

Where one fix closes two causes, report both causes and state the shared fix once. Where two causes share a mechanism (a leaked `DontDestroyOnLoad` instance carrying the static state that leaks), file each under its own row and say which one the shared fix removes.

### STEP 10 - COVERAGE TARGETS

State targets by layer, not as one global number, and say the split out loud:

| Layer | Target | Why |
| --- | --- | --- |
| Rules assembly | High - this is where the coverage number means something | Pure, fast, deterministic; every branch is cheap to reach |
| Save migration and content validation | High | Each shipped save version is a fixture; a gap here is player data loss |
| MonoBehaviour glue and presenters | **Low by design** | Delegating wiring with no branches. Chasing coverage here buys slow PlayMode tests that assert the engine works |
| Generated code, editor tooling, third-party | Excluded | Not the project's logic |

**Say the glue target explicitly in the deliverable.** A reviewer who sees 40% overall without the split reads it as under-tested, and the reflex fix - PlayMode tests over the glue - makes the suite slower and no safer.

Measure rather than guess: run the coverage invocation from STEP 8 scoped to the rules assembly when an editor is available; when it cannot run, estimate from test-file density and label the number an estimate.

**Prioritization when coverage is low or the gaps exceed 5** - run this before scaffolding, since it decides what is written first. The Strategy Doc's `Gaps to close` uses these bands:

| Priority | Targets |
|----------|---------|
| P1 - Data integrity | Save migration from each shipped version, corrupt-save recovery, content-bank import validation |
| P2 - Rules correctness | Move legality, cascade termination, undo/replay, scoring, economy accrual and its clamps |
| P3 - Monetized and irreversible | IAP grant and restore, prestige reset, currency spend paths |
| P4 - High-churn | Files with frequent recent commits (`git log --since="3 months ago" --name-only --format= \| sort \| uniq -c \| sort -rn`) or bug-fix history; `n/a - history too short` when the repository's history spans under three months |
| P5 - Presentation glue | Screen wiring and presenters - low risk, low target, can wait |

**Multi-band rule.** When a target qualifies for multiple bands, file it under the highest (lowest number) and note the secondary so the plan covers both axes.

## Output Format

**Which output to produce:**

- "What tests are missing?" -> Coverage Assessment
- "Write tests for X" / "scaffold" -> Test Scaffolds
- "Why does this test fail in CI / only in a suite?" -> Flake Diagnosis
- "Test strategy" / "test plan" -> Strategy Doc
- Unclear -> default to Strategy Doc

More than one rule matching is the normal case, not a conflict: produce every deliverable that matched, in this order, separated by `---`: Coverage Assessment -> Flake Diagnosis -> Strategy Doc -> Test Scaffolds. A coverage question against a project with no engine-free assembly always matches both Coverage Assessment and Strategy Doc, because the extraction plan is the answer and only the Strategy Doc holds it. A request that matches only Flake Diagnosis gets only that deliverable, plus the shared opening lines and any `Outside this deliverable` line.

Where two deliverables share a field, state it once in the deliverable that owns it and reference it from the other rather than restating. The prioritized list and `Coverage targets` are owned by the Strategy Doc: a Coverage Assessment emitted alongside one replaces its `Prioritization` section with a one-line pointer to `Gaps to close`, and its `Coverage targets` line with a pointer to the Strategy Doc's.

The first deliverable opens with these two lines, written once per response; a deliverable after a `---` repeats only the engine line:

```markdown
- **Engine:** {m_EditorVersion | unreadable} | Floor 6000.3.x | {At or above floor | Below floor - stopped | Unknown - asked}
- **Project shape:** Test Framework {present | absent | unknown}; substitution {NSubstitute | hand-written fakes | none | none (broken reference) | unknown}; domain reload {disabled | enabled | unknown}; UI {UI Toolkit | uGUI | mixed | unknown}; store {store}; Addressables {yes | no | unknown}
```

A stopped run (below the floor, or the version unknown with no answer possible) emits the engine line and one sentence saying why, and nothing else.

After the last deliverable, defects seen while reading that no deliverable covers - a production bug, a non-deterministic rule outside the question - are listed under `**Outside this deliverable:**`, one line each: `file:line - defect -> owner` (`task-unity-review` for production code). A defect a deliverable already covers is not repeated there; a CI fix is a `Gaps to close` entry, not an Outside line. Omit the line when there are none.

Only Test Scaffolds carry the `ran | not run` Verification block; a Flake Diagnosis's Verification line states the proof to run, and the other deliverables carry none.

**Coverage Assessment:**

```markdown
## Unity Test Coverage Assessment

- **Engine-free rules assembly:** {name | none - no fast layer exists}
- **Lead finding:** {the one sentence that gates the plan}
- **Coverage gaps:**
  - **EditMode - rules:** {rule types, transitions, or bounds without coverage}
  - **EditMode - data:** {save versions without a migration fixture; banks without import validation}
  - **PlayMode:** {lifecycle, scene-load, or screen-state paths without coverage}
  - **Determinism:** {logic reading ambient time or randomness, so it cannot be tested}
  - **Assembly structure:** {test asmdefs referencing more than they need; a missing `UNITY_INCLUDE_TESTS` constraint; a broken precompiled reference}
  - **CI harness:** {a STEP 8 defect in how tests run or report | none found}
- **Recommended balance:** EditMode rules {target}% / EditMode data {target}% / PlayMode {target}%
- **Measured coverage:** {tool, scope, and figure | not measured - <reason> | estimated from test-file density: <figure>}
- **Coverage targets:** rules high / migration high / MonoBehaviour glue low by design

### Prioritization   {when coverage is low or gaps exceed 5; alongside a Strategy Doc, the section is one line pointing to its `Gaps to close`}

1. **P1 - Data integrity:** {migrations, corrupt-save recovery, bank validation}
2. **P2 - Rules correctness:** {legality, termination, undo, economy}
3. **P3 - Monetized and irreversible:** {IAP grant and restore, prestige, currency spend}
4. **P4 - High-churn:** {files with frequent recent commits or bug-fix history | n/a - history too short}
5. **P5 - Presentation glue:** {screen wiring, presenters}
```

The Lead finding, when no fast layer exists, says it must be extracted and which files move; otherwise it names the largest untested surface.

**Flake Diagnosis:**

```markdown
## Flake Diagnosis: {test name}

- **Causes found:** {count}

### Cause {i} - {name from the STEP 9 table, or one of its two out-of-table causes}

- **Evidence:** {the symptom detail that identifies this cause - a differing failure value, a static that survives, the exact CI flag}
- **Fix:** {the change, in code or CI configuration}

### Order to apply

1. {cheapest fix that unblocks the others first - a harness false-green fix before any test fix, since no fix can be shown to work through a harness that reports green regardless; what each unblocks}

- **Verification:** {how to prove the flake is gone - repeat count, shuffled order, the CI run that must now fail on a broken test}
```

Every cause found gets its own section.

**Test Scaffolds:** ready-to-run files using project conventions:

- Right layer for the behaviour - EditMode unless engine behaviour is genuinely under test
- The test asmdef stated or created, with its references listed and `UNITY_INCLUDE_TESTS` set
- C# 9 syntax only - no file-scoped namespaces, global usings, or other C# 10+ features the 6.3 compiler rejects
- Grouped cases with descriptive names, not copy-pasted bodies
- Fixture builders with sensible defaults and named overrides, over repeated literals
- Fixed seeds and a fake clock; no ambient time or randomness
- Statics reset in `[SetUp]`
- Failure paths alongside the happy path - illegal move, corrupt save, cascade at its bound, clock moved backwards
- Bounded waits in `[UnityTest]`, with teardown for every instantiated object and additive scene
- **Migration fixtures come from real shipped saves** (Use skill: `unity-save-persistence` for the version chain and the newer-save refusal) - one captured file per shipped version, kept under the test assembly. A hand-written payload encodes the shape the team *believes* shipped, which is the same assumption the migration already makes, so it cannot catch a mismatch. Obtain one by running a build of the old tag once, pulling a QA device's profile from `persistentDataPath`, or taking a support-ticket attachment; capture the current version's file at each release tag so the next migration is never in this position. Where none can be obtained, mark the synthetic fixture an unverified shape and make a missing fixture **skip loudly rather than pass** - a green suite over absent fixtures is what ships the data loss. Where the save carries no version field, the shipped versions come from the release tags and changelog, and the scaffold's first case asserts how an unversioned save is recognised

Every scaffold deliverable ends with this block:

```markdown
- **Verification:** {ran - N passed, read from <results path> | not run - <reason>}
- **Unverified:** {compilation, the assertions, and the project symbols the scaffold assumes exist}   {only when not run}
```

Run the suite for the scaffold's platform (`-testPlatform EditMode` or `PlayMode`) in batch mode and read the `-testResults` XML wherever an editor exists and the project is not open in another editor instance; that is the only way `ran` may be written. Where none exists, `not run - <reason>` is the complete and correct value and the scaffold ships with it, labelled a scaffold rather than a passing suite. Delivering with an unrun block filled in is the defect; delivering with `not run` is not.

**Strategy Doc:**

```markdown
## Unity Test Strategy

- **Objective:** {what this strategy achieves}
- **Pyramid balance:** EditMode rules {x}% / EditMode data {y}% / PlayMode {z}%
- **Assembly plan:** {rules asmdef -> rules test asmdef; runtime asmdef -> data and PlayMode test asmdefs}
- **Tooling:** Unity Test Framework, hand-written fakes for the clock and generator, NSubstitute {where a fake costs more | not used}
- **Determinism policy:** {seed source, clock injection, what may never be asserted on frame timing}
- **Coverage targets:** rules high / migration high / glue low by design
- **CI:** {EditMode and PlayMode invocations, licence handling, Library cache, where results are read}
- **Flake policy:** quarantine requires a named cause from STEP 9; no bare retries
- **Gaps to close (prioritized):**
  1. {highest risk - typically save migration or an untestable rules layer}
  2. {next}
```

## Self-Check

**Always:**

- [ ] STEP 1: `behavioral-principles` loaded first; engine version compared numerically to `6000.3.x`, below-floor stopped rather than degraded
- [ ] STEP 1: Test Framework presence, substitution, domain reload (from `EditorSettings.asset`), and project surfaces recorded in the Project shape line; anything unreadable carried as `unknown`
- [ ] STEP 2: `.asmdef` layout read; presence or absence of a `noEngineReferences` rules assembly stated, and where absent, the extraction scoped to the P1-P3 targets
- [ ] STEP 2: code under test, existing tests (found by content), and CI configuration read directly
- [ ] Defects outside every deliverable listed under `Outside this deliverable`, not dropped

**Strategy / Coverage:**

- [ ] Pyramid mapped to Unity layers: EditMode rules as the bulk, EditMode data, PlayMode kept small
- [ ] Determinism policy stated: seeded `IRandom`, injected `IClock`, no frame-timing or wall-clock assertions
- [ ] Substitution boundary stated: fakes for the rules layer, NSubstitute only where a fake costs more
- [ ] PlayMode and async conventions covered: bounded waits, timeouts, teardown
- [ ] Test asmdef plan stated: the rules test assembly referencing the rules assembly only, every test asmdef with `UNITY_INCLUDE_TESTS`, `overrideReferences: true`, and precompiled `nunit.framework.dll`
- [ ] CI invocations given per platform, with licence handling, `Library/` caching, and the verdict read from the exit code and the XML together
- [ ] Coverage targets split by layer, with the low glue target said explicitly
- [ ] Risk-based prioritization when coverage is low (P1 integrity, P2 rules, P3 monetized, P4 churn, P5 glue)

**Flake Diagnosis:**

- [ ] Every flake cause present diagnosed and reported, not just the first; overlapping causes filed separately with the shared fix named
- [ ] Harness false-green diagnosed against STEP 8 where the symptom is a false pass
- [ ] Fixes ordered cheapest-unblocking first, with a verification that would now fail on a broken test

**Scaffolds:**

- [ ] Placed in the right layer, in an asmdef that compiles for that platform; C# 9 syntax only
- [ ] Grouped and descriptive, not copy-pasted
- [ ] Fixture builders over repeated literals
- [ ] Fixed seeds and a fake clock throughout
- [ ] Failure paths covered alongside the happy path
- [ ] Statics reset in `[SetUp]`, unconditionally
- [ ] `[UnityTest]` waits bounded; instantiated objects and additive scenes torn down
- [ ] Verification block present and honest - `ran` only where a suite actually ran, `not run - <reason>` plus the unverified list otherwise

## Avoid

- Scaffolding without reading the `.asmdef` layout and existing tests
- Testing rules logic in PlayMode when an engine-free assembly could test it in EditMode
- The rules test asmdef referencing the runtime assembly
- A test assembly without the `UNITY_INCLUDE_TESTS` define constraint
- `UnityEngine.Random`, `DateTime.UtcNow`, or `Time.deltaTime` inside a test
- Asserting a specific `System.Random` sequence as if it were stable across runtime versions
- Substituting a `UnityEngine.Object`-derived type instead of the interface behind it
- Mocking a clock or RNG that a three-line fake expresses better
- Uncapped `yield` loops waiting for a condition
- `WaitForSeconds` in a test that sets `Time.timeScale` to 0
- Tests that depend on execution order, or leave objects and additive scenes behind
- Treating a suite-only failure as flake instead of static state surviving between tests
- Retrying a flaky test without naming its cause
- Trusting the batch-mode exit code alone, without reading the `-testResults` XML
- `-quit` alongside `-runTests`
- Running EditMode and PlayMode in one invocation
- A CI job with no `Library/` cache and no licence return on the failure path
- Chasing a coverage number on MonoBehaviour glue
- Reporting one global coverage target with no per-layer split
- Presenting a scaffold as verified when no suite ran, or leaving the Verification block off
