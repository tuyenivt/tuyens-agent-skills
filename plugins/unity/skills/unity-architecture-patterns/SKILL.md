---
name: unity-architecture-patterns
description: Structure Unity 2D games around an engine-free rules core - assembly definitions, ScriptableObject config, composition over MonoBehaviour inheritance.
metadata:
  category: mobile
  tags: [unity, csharp, architecture, assembly-definition, scriptableobject, testability, composition]
user-invocable: false
---

# Unity Architecture Patterns

> This skill owns **where code lives and what it may depend on**. Engine callback timing belongs to `unity-monobehaviour-lifecycle`; what the serializer persists belongs to `unity-serialization-prefabs`; rule algorithms themselves belong to `unity-2d-gameplay-patterns`; allocation and C# language mechanics belong to `csharp-unity-patterns`; measured frame cost belongs to `unity-performance`.

## When to Use

- Starting a new 2D game or a new feature within one
- Deciding what belongs in a `MonoBehaviour` versus plain C#
- Reviewing a diff for testability, coupling, or scene-dependence
- A rule cannot be tested without entering Play mode

## Rules

- **Game rules are plain C# with no `UnityEngine` dependency.** Board state, move legality, scoring, economy, and progression compile and run without the engine. This is the plugin's central constraint - every other architectural choice follows from it
- Enforce the boundary with an assembly definition, not discipline. Every `.asmdef` gets the engine implicitly; only `"noEngineReferences": true` (No Engine References in the Inspector) on the rules `.asmdef` turns a `using UnityEngine` there into a compile error rather than a review comment
- `MonoBehaviour` is for engine hooks only: lifecycle callbacks, inspector wiring, coroutines, collisions. A class needing none of these is a plain class
- Prefer composition over inheritance. Deep `MonoBehaviour` hierarchies couple unrelated concerns to a shared base and are untestable in isolation
- ScriptableObjects hold **configuration and shared assets**, not mutable runtime state. A SO edited at runtime persists that edit in the editor and silently diverges from a build
- Scene and prefab references are injected at the seam (serialized field, initializer), never fetched from deep inside logic via `GameObject.Find` or singletons
- Every dependency a rule needs - time, randomness, persistence - arrives as an interface the test can substitute

## Patterns

### The three-assembly layout

The minimum structure that makes the engine-free rule enforceable:

| Assembly | References | Contains |
| --- | --- | --- |
| `Game.Rules` | nothing; `noEngineReferences: true` | board state, move legality, scoring, economy, progression, and the `IClock`/`IRandom` seams |
| `Game.Runtime` | `Game.Rules` (engine implicit) | MonoBehaviours, presenters, ScriptableObjects, scene wiring, engine-backed `IClock`/`IRandom` |
| `Game.Tests.EditMode` | `Game.Rules`, `UnityEngine.TestRunner`, `UnityEditor.TestRunner`, `nunit.framework.dll`; Editor platform only | fast rule tests, no scene, no Play mode |

`Game.Rules` reaching `UnityEngine` is the single failure that collapses the whole design - it is what makes rules untestable and Play-mode-bound. Leaving the engine out of `references` prevents nothing; the flag does. A new game mode adds its rules to `Game.Rules`, or to its own engine-free assembly (which may reference `Game.Rules`) when it shares no rules; an unenforced `Game.Rules` is fixed before anything builds on it.

Assembly definitions also cut compile time: a runtime change no longer recompiles the rules or their tests.

### Engine-free rules

```csharp
// Bad - rules trapped in a MonoBehaviour; needs a scene, a GameObject, and Play mode to test
public class Board2048 : MonoBehaviour {
    void Update() { if (Keyboard.current.leftArrowKey.wasPressedThisFrame) SlideLeft(); }
    void SlideLeft() { /* merge logic reading Time.deltaTime and Random.Range */ }
}

// Good - pure, deterministic, instant to test
public readonly struct MoveResult {
    public readonly BoardState Board; public readonly int ScoreGained; public readonly bool Changed;
    public MoveResult(BoardState board, int gained, bool changed) { Board = board; ScoreGained = gained; Changed = changed; }
}

public static class Board2048 {
    public static MoveResult SlideLeft(BoardState board) { /* ... */ }
}
```

The good version has no engine dependency, no hidden global state, and returns the outcome rather than mutating the world. A `MonoBehaviour` calls it and renders the result.

### Substituting time and randomness

`Time`, `Random`, and `DateTime.Now` read ambient state, which makes any rule touching them non-deterministic and untestable.

```csharp
// Bad - unrepeatable; a failing test cannot be reproduced
int roll = Random.Range(0, 6);

// Good - seeded and injected; the same seed replays the same game
public interface IRandom { int Next(int minInclusive, int maxExclusive); }
public sealed class SeededRandom : IRandom {
    private readonly System.Random _rng;
    public SeededRandom(int seed) => _rng = new System.Random(seed);
    public int Next(int minInclusive, int maxExclusive) => _rng.Next(minInclusive, maxExclusive);
}
```

Same move for time: rules take an `IClock` rather than reading `DateTime.Now`. Offline-progress math depends on this being substitutable - see `unity-game-economy-progression` for the wall-clock-versus-monotonic correctness boundary.

### MonoBehaviour or plain class

| Needs | Type |
| --- | --- |
| Lifecycle callback, collision, coroutine, inspector wiring | `MonoBehaviour` |
| Configuration authored in the editor, shared across scenes | `ScriptableObject` |
| Rules, algorithms, state machines, pure data | plain C# class / `struct` (a C# 9 `record` needs an `IsExternalInit` shim and is not Unity-serializable) |
| A single shared service (audio, save) | plain C# behind an interface, with one `MonoBehaviour` owning its lifetime |

A `MonoBehaviour` with no engine callback and no serialized field is a plain class wearing a costume: it forces a `GameObject` to exist, blocks constructor injection, and cannot be `new`ed in a test.

### ScriptableObject configuration

```csharp
// Bad - mutable runtime state on a SO; the editor persists changes between plays
[CreateAssetMenu] public class PlayerData : ScriptableObject { public int currentScore; }

// Good - immutable config; runtime state lives in the rules layer
[CreateAssetMenu] public class LevelConfig : ScriptableObject {
    [SerializeField] private int targetScore;
    public int TargetScore => targetScore;
}
```

The distinction is authored-and-fixed versus changes-during-play. Balance tables, level definitions, and enemy stats are configuration. Current score, board state, and wave number are runtime state and belong in the rules layer where they can be saved and tested.

Config crosses the assembly boundary as values: the runtime layer reads the ScriptableObject and hands plain values or structs into `Game.Rules` at the seam. The rules assembly never references a ScriptableObject type.

### Wiring without global lookups

```csharp
// Bad - couples logic to scene shape; on a rename Find returns null and the chained call throws
var mgr = GameObject.Find("GameManager").GetComponent<GameManager>();

// Good - the dependency arrives at the seam
[SerializeField] private BoardPresenter presenter;
```

`GameObject.Find` and the `FindAnyObjectByType` / `FindObjectsByType` family (which supersede the obsolete `FindObjectOfType`) are also linear scene scans; in `Awake` across many objects they add measurable startup cost. For genuinely global services, one composition root - a single scene-entry `MonoBehaviour` that constructs and hands out dependencies - beats a static singleton per service, which is untestable and carries domain-reload hazards (`unity-monobehaviour-lifecycle`).

A DI container (Zenject, VContainer) is respected where a project already uses one, but is not required. For a casual 2D game a composition root is usually sufficient - see `unity-overengineering-review`.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {EngineCoupling | AssemblyBoundary | Inheritance | SOMisuse | GlobalLookup | Injectability | CompositionRoot}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {what it prevents - "rule untestable without Play mode", "SO mutation persists into the editor"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = game rules carry a `UnityEngine` dependency (inside a rules assembly, or because no rules layer exists yet), or runtime state mutates a ScriptableObject. High = a rule untestable without a scene, or engine-free rules whose boundary is unenforced (no rules `.asmdef`, or one without `"noEngineReferences": true`). Medium = a global lookup, avoidable inheritance, or a System ambient read (`DateTime.Now`, an unseeded `System.Random`) in a contained spot; engine `Time` or `Random` in a rule is the Critical engine dependency. Low = a structural nit with no current cost. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: move-resolution algorithm -> unity-2d-gameplay-patterns`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No architecture findings.` |
| A review was requested with nothing to judge | `Architecture check not run: no source supplied.` |

## Avoid

- `UnityEngine` reachable from the rules assembly, or a rules `.asmdef` without `noEngineReferences: true`
- Game rules written inside `Update` or any other lifecycle callback
- `MonoBehaviour` on a class with no engine callback and no serialized field
- ScriptableObjects mutated at runtime as a state store
- `GameObject.Find` / `FindAnyObjectByType` / `FindObjectsByType` inside logic
- Static singletons as the default service mechanism
- Deep `MonoBehaviour` inheritance where composition would do
- `Random` or `DateTime.Now` read directly inside a rule
- A DI container introduced for a game with a handful of services
