---
name: csharp-unity-patterns
description: Write C# as Unity runs it - the destroyed-object == overload, allocation in Update, boxing, closures, coroutines vs async/await and Awaitable.
metadata:
  category: mobile
  tags: [unity, csharp, allocation, gc, async, coroutines, nullable, boxing]
user-invocable: false
---

# C# Unity Patterns

> This skill owns **C# language mechanics under the Unity runtime**. Where code lives and what it may depend on belongs to `unity-architecture-patterns`; callback timing, event-subscription lifetime, and coroutine lifetime belong to `unity-monobehaviour-lifecycle`; what the serializer persists belongs to `unity-serialization-prefabs`; measured frame budget and profiling belong to `unity-performance`.

## When to Use

- Writing or reviewing C# that runs per-frame or per-entity
- A null check passes but the next line throws `MissingReferenceException`
- Choosing between a coroutine, `async`/`await`, and `Awaitable`
- GC spikes appear in the profiler with no obvious `new`

## Rules

- **Never use `?.`, `??`, `??=`, `is null`, or `is not null` on a `UnityEngine.Object`.** They test the runtime's real null, not Unity's overloaded `==`. A destroyed object is not real null, so `?.` invokes on it, and the call throws once it touches native engine state. Compare with `== null` / `!= null`, or `if (obj)`
- Do not allocate on any per-frame path - `Update`, `FixedUpdate`, `LateUpdate`, a coroutine or async loop resuming every frame - or in per-entity loops. LINQ, lambdas capturing locals, string concatenation, and `new` collections all allocate
- Reuse collections and buffers across frames; clear, do not reallocate
- A `struct` passed to a parameter typed `object` or a non-generic interface boxes. Keep hot-path generics constrained and concrete
- `async void` gives the caller nothing to await or cancel; Unity logs its exceptions, but no caller can handle them. Use it only for an event handler that catches internally. Elsewhere return `Task` or `Awaitable` and await it - an un-awaited `Task` or `Awaitable` drops its exception silently
- Async work started from a MonoBehaviour must be cancelled when that object dies (`destroyCancellationToken`). Work that must also stop on disable takes its own `CancellationTokenSource`, cancelled in `OnDisable`. Nothing cancels it for you
- Unity 6.3 compiles C# 9: no `record struct`, file-scoped namespaces, `required` members, global usings, or primary constructors on classes. An allocation claim that depends on the scripting backend is confirmed with the profiler on that backend

## Patterns

### The `==` overload: the one that bites hardest

`UnityEngine.Object` overloads `==` so a **destroyed but not garbage-collected** object compares equal to `null`. That overload is a static method on the type. The null-conditional and null-coalescing operators bypass operator overloads entirely and test for real reference null - the managed wrapper of a destroyed object is still a live reference, so it passes them and the call proceeds. It throws `MissingReferenceException` once that call touches native engine state, which is what any component member worth calling does.

```csharp
// Bad - the managed wrapper is alive, so `?.` calls into a destroyed object
target?.TakeDamage(10);            // runs on the destroyed object; throws once it touches engine state
var a = cached ?? FindTarget();    // returns the destroyed object

// Good - goes through the overload, so destroyed reads as null
if (target != null) target.TakeDamage(10);
var b = cached != null ? cached : FindTarget();
```

The same trap applies to `is null`, `is not null`, and pattern matching against `null` - all bypass the overload. Cost note: the overload is not free, so a per-frame `!= null` on a cached reference is worth hoisting out of the loop.

Nullable reference types (`#nullable enable`) compound this. The compiler's flow analysis knows nothing about the overload, so it will mark a destroyed-but-assigned field as non-null and suppress warnings on a reference that is about to throw.

```csharp
// Bad - NRT says this is non-null; at runtime it is destroyed
[SerializeField] private Rigidbody2D body = null!;
body.linearVelocity = Vector2.zero;    // MissingReferenceException

// Good - the runtime check still runs, NRT or not
if (body != null) body.linearVelocity = Vector2.zero;
```

Treat NRT annotations on `UnityEngine.Object`-derived fields as documentation of intent, never as a runtime guarantee.

### LINQ and closures in hot paths

```csharp
// Bad - per frame: an enumerator, a delegate for the lambda, a List
void Update() {
    var near = enemies.Where(e => e.Distance < range).ToList();
}

// Good - reused buffer, no closure, no delegate
private readonly List<Enemy> _near = new();
void Update() {
    _near.Clear();
    for (int i = 0; i < enemies.Count; i++)
        if (enemies[i].Distance < range) _near.Add(enemies[i]);
}
```

A lambda that captures nothing is cached by the compiler and allocates once. A lambda capturing a local or parameter allocates a closure object plus a delegate on every evaluation; one capturing only `this` (a field or instance method) allocates a new delegate each time. Both show in the profiler as steady per-frame garbage, and both survive "we removed all the LINQ".

An editor capture includes editor-only allocations, and Deep Profile adds timing overhead rather than a truer allocation figure. Attribute allocation from a capture on the target device, with allocation call stacks enabled, before sizing a fix.

### Strings

```csharp
// Bad - two allocations per frame, 60/s, forever
scoreLabel.text = "Score: " + score;

// Good - assign only when the value actually changed
if (score != _lastScore) { _lastScore = score; scoreLabel.text = "Score: " + score; }   // _lastScore starts at -1
```

Interpolation, `ToString()` on a numeric, `string.Format`, and `+` all allocate. For a small bounded range, precompute the strings; otherwise gate the assignment on change so the cost is per-change rather than per-frame.

### Boxing and value types

```csharp
// Bad - boxes the struct on every call
void Log(object payload) { }
Log(new Vector2Int(x, y));

// Good - generic, no boxing
void Log<T>(T payload) where T : struct { }
```

Other boxing sources: a `struct` implementing an interface then stored as that interface; `Enum` used as a `Dictionary` key without a comparer on older toolchains; `params object[]`. Passing a large `readonly struct` by value copies it - take it by `in` in hot code.

`foreach` boxing its enumerator is folklore from an old Mono compiler bug, fixed in Unity 5.5: on the 6000.3 floor, `foreach` over a concrete `List<T>` or `Dictionary<K,V>` does not allocate. It still boxes when the collection is iterated through an interface (`IEnumerable<T>`).

### Coroutines, async/await, and Awaitable

| Need | Use |
| --- | --- |
| Frame-paced sequencing tied to a GameObject's life | Coroutine |
| Awaiting engine work (frame, seconds, scene load) with `await` syntax | `Awaitable` |
| I/O, file, or CPU work with a return value and cancellation | `async Task` / `Awaitable` with a `CancellationToken`; CPU work also switches off the main thread (`Awaitable.BackgroundThreadAsync()` or `Task.Run`) |
| Anything that must survive the object being disabled | Neither on that object - move ownership |

`Awaitable` is Unity's engine-aware awaitable type: pooled, integrated with the player loop (frame, fixed-update, and seconds waits need no timer thread), and able to switch threads explicitly (`BackgroundThreadAsync`, `MainThreadAsync`). An `Awaitable` instance is awaited exactly once. Coroutines cannot return a value or be awaited; `async` methods are not stopped by the engine when the object dies. A need matching several rows takes the topmost matching row, except that the last row overrides the others.

```csharp
// Bad - keeps running after the object is destroyed, then touches a dead transform
async void Start() { await Task.Delay(5000); transform.position = target; }

// Good - cancelled with the object; the expected cancellation is caught here
async Awaitable Start() {
    try {
        await Awaitable.WaitForSecondsAsync(5f, destroyCancellationToken);
        transform.position = target;
    } catch (OperationCanceledException) { }   // destroyed mid-wait
}
```

`destroyCancellationToken` is a `MonoBehaviour` property that cancels when the object is destroyed. The engine invokes `async Awaitable Start` without awaiting it, so nothing observes its exceptions: it catches its own, including the `OperationCanceledException` a mid-wait destroy raises.

### Collection reuse

```csharp
// Bad - a new array every physics query, every frame
var hits = Physics2D.OverlapCircleAll(pos, r);

// Good - preallocated, non-allocating overload
private readonly Collider2D[] _hits = new Collider2D[16];
private ContactFilter2D _filter;   // built once with the layer mask
int n = Physics2D.OverlapCircle(pos, r, _filter, _hits);
```

Unity's non-allocating overloads exist across physics, mesh, and component APIs; their exact names and signatures differ per API and have changed across versions - look up the concrete overload rather than assuming a `NonAlloc` suffix. Fixed-size buffers silently truncate when the result exceeds capacity, so size for the worst case and check the returned count.

`renderer.material` clones the material on first access, and the clone outlives the renderer unless destroyed. Read `sharedMaterial`, and `Destroy` any clone you create.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {DestroyedObjectNullCheck | HotPathAllocation | Boxing | StringAllocation | ClosureCapture | AsyncLifetime | CollectionReuse | MaterialInstance | NullableAnnotation | LanguageLevel}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {runtime consequence - "throws MissingReferenceException on a destroyed target", "1.2 KB/frame steady garbage"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

When the band turns on an unseen declaration (whether a field is a `UnityEngine.Object`), `Fix` opens with the check that settles it. `DestroyedObjectNullCheck` also covers a reference to an object that can be destroyed, used with no check at all. `LanguageLevel` covers syntax the C# 9 compiler rejects.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = `?.`, `??`, `??=`, `is null`, or `is not null` applied to a `UnityEngine.Object`. High = C# 10+ syntax (a compile failure), a destroyed-capable reference used with no check, allocation on any per-frame path (`Update`/`FixedUpdate`/`LateUpdate`, or a coroutine or async loop resuming every frame), async work that outlives its object (no `destroyCancellationToken`), or an exception path nothing observes (an un-awaited `Task` or `Awaitable`). Medium = allocation on a per-interaction path, boxing in a warm loop, or a `renderer.material` instance created per object. Low = a cold-path allocation with no measured cost. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: pool ownership and scene placement -> unity-architecture-patterns`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No C# findings.` |
| A review was requested with nothing to judge | `C# check not run: no source supplied.` |

## Avoid

- `?.`, `??`, `??=`, `is null`, or `is not null` applied to any `UnityEngine.Object`
- Treating a nullable-reference annotation as proof a component reference is alive
- LINQ, string concatenation, or capturing lambdas inside per-frame code
- `async void` outside an event handler that catches internally
- A `Task` or `Awaitable` started and never awaited, so its exception is lost
- Async work started on a `MonoBehaviour` without `destroyCancellationToken`
- Allocating a new collection or array per frame where a reused buffer fits
- Passing a `struct` as `object` or through a non-generic interface in a hot loop
- C# 10+ syntax, or an allocation claim about a scripting backend you did not profile
