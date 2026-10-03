---
name: unity-monobehaviour-lifecycle
description: Order Unity callbacks correctly - Awake/OnEnable/Start traps, static state surviving disabled domain reload, coroutine lifetime, DontDestroyOnLoad.
metadata:
  category: mobile
  tags: [unity, monobehaviour, lifecycle, domain-reload, coroutines, execution-order, singleton]
user-invocable: false
---

# Unity MonoBehaviour Lifecycle

> This skill owns **engine callback timing and object lifetime**. Where code lives and what it may depend on belongs to `unity-architecture-patterns`; what the serializer persists belongs to `unity-serialization-prefabs`; C# language mechanics including `async` cancellation belong to `csharp-unity-patterns`; per-frame cost belongs to `unity-performance`.

## When to Use

- A reference is null in `Awake` but populated by the time `Start` runs
- Behaviour differs between the first Play session and the second
- A coroutine stops without being told to
- Wiring a persistent manager, scene load, or app pause/resume handling

## Rules

- **`Awake` initializes self; `Start` reads others.** Any cross-object reference resolved in `Awake` depends on undefined ordering between objects
- Never depend on `Awake` ordering across GameObjects. If order genuinely matters, make it explicit with Script Execution Order or an initializer that calls its dependents
- **Assume domain reload may be off.** Unity 6.3 reloads the domain on entering Play mode by default, but projects switch that off for fast iteration, and then statics and static event subscriptions carry over between Play sessions. Reset every static explicitly via `[RuntimeInitializeOnLoadMethod]`
- Unsubscribe in `OnDisable` from anything subscribed in `OnEnable`, and in `OnDestroy` from anything subscribed in `Awake`. Symmetric pairs, always
- Coroutines are owned by the MonoBehaviour that started them: deactivating its GameObject or destroying it stops them, silently. Disabling only the component (`enabled = false`) leaves them running
- `DontDestroyOnLoad` objects survive scene loads, so a scene containing one that is loaded twice produces duplicates. The instance must guard against that itself
- Do not put per-frame work in `Update` when the state only changes on an event

## Patterns

### Callback order

Within a single object:

| Phase | Callbacks | Runs |
| --- | --- | --- |
| Initialization | `Awake` -> `OnEnable` -> `Start` | `Awake` on first activation, `OnEnable` on every activation, `Start` once, before the first `Update` after the first enablement |
| Physics | `FixedUpdate` -> physics step -> `OnCollision*` / `OnTrigger*` | zero or more times per frame, on the fixed timestep |
| Logic | `Update` -> coroutine resumption -> `LateUpdate` | once per frame |
| Teardown | `OnDisable` -> `OnDestroy` | on disable, destroy, and application quit |

`Awake` runs when an object first becomes active: at instantiation for an active prefab, but deferred to first activation for one instantiated inactive or under an inactive parent. `Start` is deferred until the object is enabled, and never runs if it never is. `LateUpdate` is where you read a transform another script moved this frame - camera follow belongs there, not in `Update`.

Pooled objects live on exactly these semantics: `Awake` runs once, at first activation (a pool that instantiates inactive defers it to the first `Get`), `OnEnable` on every activation, and `Start` once, before its first `Update` - never again on reuse. One-time setup goes in `Awake`, per-use reset in `OnEnable`.

### Awake versus Start

```csharp
// Bad - other's Awake may not have run yet; _board is null or half-built
void Awake() { _board = FindAnyObjectByType<BoardController>().Board; }

// Good - self-init in Awake, cross-object reads in Start
void Awake() { _cells = new Cell[Width * Height]; }
void Start() { _board = _boardController.Board; }
```

The safest structure removes the question: inject the reference through a serialized field and have a single composition root call an explicit `Initialize(...)`, so ordering is code rather than engine policy (`unity-architecture-patterns`).

### Script Execution Order

Project Settings -> Script Execution Order assigns a numeric order; lower runs first, and it applies to `Awake`, `Start`, `Update`, and the rest. Use it only for one or two genuine infrastructure scripts (a bootstrap or service registry). Prefer `[DefaultExecutionOrder(n)]` on the class, which is visible in source; a Project Settings entry for the same type overrides it and is invisible from the file, so a class depending on that route needs a comment saying so. More than a handful of entries means the initialization design is wrong.

### Domain reload disabled: the session-two trap

When Project Settings -> Editor -> Enter Play Mode Settings skips the domain reload (Unity 6.3 reloads by default; projects switch it off for fast iteration), entering Play mode does **not** reset the C# domain. Statics keep the values the previous session left, and static event subscriptions from destroyed objects remain subscribed.

```csharp
// Bad - session 2 starts with session 1's score, and the stale handler still fires
public static int HighScore;
static event Action OnGameOver;

// Good - explicit reset before any scene loads
[RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
static void ResetStatics() { HighScore = 0; OnGameOver = null; }
```

`SubsystemRegistration` is the earliest load type and runs before scene objects exist, which is what you want for a reset. This is editor-only behaviour - a fresh build always resets - so the symptom is "works in a build, wrong in the editor on the second Play", which is easy to misdiagnose as a save bug. Every static field and static event needs a line in a reset method; a static holding a `UnityEngine.Object` reference from a prior session is worse than stale, it is destroyed (`csharp-unity-patterns`).

### Singletons and DontDestroyOnLoad

```csharp
// Bad - returning to the menu scene a second time creates a second AudioManager
void Awake() { Instance = this; DontDestroyOnLoad(gameObject); }

// Good - the duplicate destroys itself before it can register
void Awake() {
    if (Instance != null && Instance != this) { Destroy(gameObject); return; }
    Instance = this; DontDestroyOnLoad(gameObject);
}
void OnDestroy() { if (Instance == this) Instance = null; }   // the duplicate never registered
```

`Destroy` is deferred to the end of the frame, so the duplicate's `OnEnable` still runs - a subscription there needs the same `Instance == this` guard.

`DontDestroyOnLoad` moves the object to a separate scene, so it does not appear in the loaded scene hierarchy and is not unloaded with it. Combined with disabled domain reload, `Instance` also survives into the next Play session pointing at a destroyed object - so the static needs the reset from the previous pattern too. Prefer a single bootstrap scene that creates persistent services once over one self-registering singleton per service.

### Coroutine lifetime

```csharp
// Bad - deactivating the GameObject silently stops this mid-sequence, leaving the flag set
IEnumerator Resolve() { _busy = true; yield return _delay; _busy = false; }

// Good - cleanup lives outside the coroutine body and also stops it on component disable
void OnDisable() { StopAllCoroutines(); _busy = false; }
```

Deactivating the GameObject stops its coroutines, and reactivating does not resume them; destroying the object kills them; disabling only the component leaves them running. None of these logs anything, so a half-completed sequence leaves whatever invariant it was holding broken. `StopCoroutine` needs the `Coroutine` handle `StartCoroutine` returned, or the same `IEnumerator` instance - a fresh iterator from calling the method again matches nothing. A coroutine that must outlive its object belongs on a persistent host, or should be an `Awaitable` with an explicit token (`csharp-unity-patterns`).

Note `WaitForSeconds` uses scaled time, so it never completes while `Time.timeScale` is 0 - use `WaitForSecondsRealtime` for pause menus. One owner sets `Time.timeScale`; other pausers request through it. The owner restores it in `OnDisable`, or a killed routine leaves the game frozen.

### Pause, focus, and quit on mobile

```csharp
// Bad - OnApplicationQuit is not reliably called when a mobile OS kills a backgrounded app
void OnApplicationQuit() { SaveGame(); }

// Good - persist at the last guaranteed point
void OnApplicationPause(bool paused) { if (paused) SaveGame(); }
```

On mobile, backgrounding raises `OnApplicationPause(true)`; a subsequent kill may deliver no further callback at all. Treat pause as the save point. `OnApplicationFocus` also fires around backgrounding, and the exact pairing and ordering of pause and focus differs by platform, OS version, and interruption type (call, notification shade, app switcher). Do not encode a specific sequence - make the handler idempotent and verify on device.

### Scene load callbacks

`SceneManager.sceneLoaded` fires after the new scene's objects have run `Awake` and `OnEnable`, but before their first `Start`. `activeSceneChanged` and `sceneUnloaded` cover the other transitions. Subscribe from a persistent object and unsubscribe symmetrically - a subscription from an object in the outgoing scene, with domain reload disabled, becomes a stale handler firing into destroyed objects. An additive load leaves both scenes' objects live simultaneously, so anything assuming "one board controller exists" needs to hold under additive loading.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {InitOrder | CallbackPlacement | StaticNotReset | SubscriptionLeak | CoroutineLifetime | ScaledTimeWait | SingletonDuplication | PauseSaveGap | SceneCallback | ExecutionOrderDependency}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {observable failure - "null on first frame in a build", "session 2 starts with session 1 state"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

`CallbackPlacement` covers work in the wrong callback (a transform read in `Update` that belongs in `LateUpdate`, per-frame polling of event-driven state). `ScaledTimeWait` covers a wait that stalls at `Time.timeScale == 0`. A static event a destroyed subscriber still holds is `StaticNotReset` when domain reload is off, `SubscriptionLeak` otherwise.

`Fix` opens with the one check that confirms the diagnosis (for the session-two signature: Project Settings -> Editor -> Enter Play Mode Settings). When that setting was not seen, an unreset static is Critical-band and `inferred`: `[High]` with `Uncapped: Critical.`

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = unreset static or static event under disabled domain reload, or progress lost because saving depends on `OnApplicationQuit`. High = an initialization read that legal activation order can break (a cross-object reference resolved in `Awake`, `Start`-deferred state used while the object is still disabled), subscription without its symmetric unsubscribe, a coroutine holding an invariant that disablement breaks, or a wait that stalls a core loop at `timeScale` 0. Medium = singleton without a duplicate guard, callback placement that another script can observe mid-frame, or undocumented Script Execution Order dependence. Low = a lifecycle nit with no reachable failure. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: service registration shape -> unity-architecture-patterns`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No lifecycle findings.` |
| A review was requested with nothing to judge | `Lifecycle check not run: no source supplied.` |

## Avoid

- Cross-object reference lookups in `Awake`
- Static fields or static events with no `[RuntimeInitializeOnLoadMethod]` reset
- Subscribing in `OnEnable`/`Awake` without the matching unsubscribe
- Saving in `OnApplicationQuit` on a mobile target
- `DontDestroyOnLoad` without a duplicate-instance guard
- Coroutines holding state whose cleanup only exists in the coroutine body
- `WaitForSeconds` in a path that must run while `Time.timeScale` is 0
- Silent reliance on Script Execution Order, uncommented at the call site
- Assuming a fixed `OnApplicationPause`/`OnApplicationFocus` sequence across platforms
