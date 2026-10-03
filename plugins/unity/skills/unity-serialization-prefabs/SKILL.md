---
name: unity-serialization-prefabs
description: Control what Unity's serializer keeps and drops - SerializeField, SerializeReference, prefab overrides, .meta GUID stability, YAML merge conflicts.
metadata:
  category: mobile
  tags: [unity, serialization, prefabs, scriptableobject, meta-files, guid, merge-conflicts]
user-invocable: false
---

# Unity Serialization and Prefabs

> This skill owns **what the serializer persists and how prefab and asset identity is preserved**. Where code lives and what it may depend on belongs to `unity-architecture-patterns`; callback timing belongs to `unity-monobehaviour-lifecycle`; C# language mechanics belong to `csharp-unity-patterns`; save-file format and schema migration belong to `unity-save-persistence`.

## When to Use

- A field is set in the inspector and null at runtime, or resets itself
- Adding a polymorphic or interface-typed field to a serialized class
- Reviewing prefab, prefab variant, scene, or `.meta` changes in a diff
- A merge produced a broken scene, or every reference in a folder went missing

## Rules

- **A field the default inspector does not show is a field Unity does not save.** If it is not visible and not `[HideInInspector]`, it is not serialized (a custom `Editor` or `PropertyDrawer` can hide serialized fields - check the attribute, not the panel)
- Private fields need `[SerializeField]`; a property is never serialized itself (an auto-property marked `[field: SerializeField]` serializes its backing field, YAML key `<Name>k__BackingField`); `static`, `const`, and `readonly` fields are never serialized
- `Dictionary` does not serialize, nor do interface- or abstract-typed fields. A by-value field holding a subclass serializes as its declared type and drops the subclass data. `[SerializeReference]` lifts all three
- **A `.meta` file is the asset's identity.** Deleting or regenerating one breaks every reference to that asset across every scene and prefab. `.meta` files are committed, always, alongside their asset in the same commit
- Serialized structs and custom classes cannot be null. Unity replaces a null with a default-constructed instance on load
- A prefab override is a divergence from the prefab and must be intentional. Review every override in a diff as a change, not as noise
- Never hand-merge scene or prefab YAML without Unity's merge tool; resolve by choosing one side when the tool is unavailable

## Patterns

### What serializes

| Serializes | Does not serialize |
| --- | --- |
| `public` fields of a serializable type | properties (a `[field: SerializeField]` auto-property's backing field excepted) |
| `private`/`protected` with `[SerializeField]` | `static`, `const`, `readonly` |
| primitives, `string`, `enum`, Unity built-in structs | `Dictionary`, `HashSet`, multidimensional and jagged arrays |
| `UnityEngine.Object` references | interface-typed and abstract fields (without `[SerializeReference]`) |
| `List<T>` and `T[]` of a serializable `T` | `List<List<T>>`, nullable value types |
| plain classes marked `[System.Serializable]` | anything not in a serializable field type |

```csharp
// Bad - none of these persist; all are silently empty at runtime
public Dictionary<string, int> scores;
public int Level { get; set; }
private float speed;

// Good
[SerializeField] private List<ScoreEntry> scores;   // with [System.Serializable] on ScoreEntry
[SerializeField] private int level;
public int Level => level;
```

The failure is silent: no warning, no error, just a value that reverts. For a dictionary, serialize parallel lists or a `List<KeyValuePair>`-shaped serializable struct and rebuild the dictionary in `OnAfterDeserialize`.

`JsonUtility` runs this same serializer, so this table governs what reaches a JSON string too: a `Dictionary` or `int[,]` field is silently absent from the output whether or not the field carries `[SerializeField]`. That consequence is this skill's finding. It has its own further limit: no top-level array or primitive. Whether the resulting file is written durably, versioned, and migrated belongs to `unity-save-persistence`.

### Null is not preserved for serializable classes and structs

```csharp
// Bad - `config` reads as null in code, but loads back as a default instance
[System.Serializable] public class Config { public int rounds; }
[SerializeField] private Config config;    // never null after a domain reload or load
```

A serialized custom class or struct field is always instantiated. Code branching on `config == null` never takes the null path after deserialization. Use an explicit `bool hasConfig` flag, or `[SerializeReference]`, which does preserve null.

### [SerializeReference]

`[SerializeReference]` stores the field by managed reference rather than by value, which buys polymorphism, interface-typed fields, null preservation, and shared references between fields.

```csharp
// Bad - stores the base slice only; subclass data is dropped on reload
[SerializeField] private List<Effect> effects;

// Good - each element keeps its concrete type
[SerializeReference] private List<Effect> effects;
```

Its pitfalls are real and cost data:

- The reference stores the concrete type by assembly, namespace, and class name. Renaming or moving the type breaks every existing asset unless the type carries `[MovedFrom]` (`UnityEngine.Scripting.APIUpdating`), which is the attribute the serializer consults for this - there is no separate managed-reference-specific attribute. Apply it to the class *before* the rename ships; any of assembly, namespace, and class name may change, and a null argument means "unchanged". Its signature is `[MovedFrom(autoUpdateAPI, sourceNamespace, sourceAssembly, sourceClassName)]`, e.g. `[MovedFrom(false, sourceNamespace: "Game.Effects", sourceClassName: "BurnEffect")]`. A rename that reaches an asset without it surfaces as `ManagedReferenceMissingType`: the field reads null, but Unity keeps the stored data and writes it back on save, so adding `[MovedFrom]` afterwards (or restoring the name) recovers it - unless `SerializationUtility.ClearAllManagedReferencesWithMissingTypes` has run. `[FormerlySerializedAs]` does not help here: it renames a *field*, not a stored type. The rewrite-and-retain ordering under Renaming a serialized field (steps 2-4) binds a type rename the same way - assets keep the old type string until re-saved, and the attribute stays until every asset, branch, and stash is rewritten.
- Instances are added from code or a custom editor, not by dragging in the inspector as with a `UnityEngine.Object` reference.
- Managed references have their own YAML block, which makes diffs noisier and merges harder.
- Serialization cost and file size exceed plain by-value fields; it is not the default choice.

Where the polymorphism is really "one of several authored configurations", a `ScriptableObject` reference is simpler, diffs better, and is shared rather than copied.

Note that `[SerializeReference]` list *elements* can be null, unlike by-value serialized fields - a null element is the visible symptom of `ManagedReferenceMissingType`, so guard elements individually rather than assuming the list is dense.

### Renaming a serialized field

`[FormerlySerializedAs("oldName")]` (`UnityEngine.Serialization`) is the field-rename counterpart to `[MovedFrom]`. The serializer matches stored data to fields by name, so a rename without it leaves every existing asset with an orphaned entry and the new field at its initializer value - silent data loss across every prefab and scene at once.

The ordering is what makes it safe, and it is easy to get wrong:

1. Add the attribute in the **same commit** as the rename. A commit that renames without it loses each asset's value the next time that asset is saved.
2. **Force a rewrite** with `AssetDatabase.ForceReserializeAssets(paths)` over every prefab, scene, and ScriptableObject that holds the field or type. Until an asset is re-saved, its file still carries the old key and the attribute is load-bearing.
3. Commit the rewritten assets with their `.meta` files. Nothing here changes a GUID: `ForceReserializeAssets` may rewrite `.meta` formatting, but a changed `guid:` line means something else happened - investigate before merging. Find assets still carrying the old key by searching the YAML for it, and keep that search in CI until it returns nothing. The field and type attributes may ship in one commit.
4. Keep the attribute for at least one release after every asset is rewritten. A branch merged after the rewrite brings old keys back, so re-run the rewrite after each such merge. Removing the attribute while any unrewritten asset, branch, or stash remains drops those values.

### Prefab variants, nested prefabs, and overrides

A **nested prefab** is a prefab instance inside another prefab; it keeps its own link to its source. A **prefab variant** inherits from a base prefab and stores only its differences, so a base change propagates to every variant except where the variant overrode it.

An **override** is a per-instance divergence: a changed value, an added component, an added child, or a removed component. Overrides are the review surface: the Inspector marks them (bold, with a blue margin bar) only on the instance you select, and the Overrides dropdown lists only the selected instance's, so across a scene only the YAML diff shows them.

```
# Bad - a scene instance quietly diverges; the prefab fix never reaches this one
m_Modifications:
- target: {fileID: 200, guid: ...}
  propertyPath: moveSpeed
  value: 12          # prefab says 5

# Good - the value lives on the prefab, no instance modification
```

Rules that keep this tractable: tune on the prefab and apply, do not tune on the instance and forget; put per-instance data (spawn point, level index) in overrides deliberately and nowhere else; treat an unexpected `m_Modifications` entry in a diff as a defect until justified. Every instance carries default overrides (`m_Name`, the root transform's position and rotation) that are not findings. When only the instance YAML is supplied, the prefab's own value is unseen and the override block is `inferred`. An added component on an instance cannot be removed by the prefab, and a component the variant added is not removable from the base - so component composition decisions belong on the base.

### .meta files and GUID stability

Every asset and folder has a sibling `.meta` holding a GUID and the importer settings. References are stored as that GUID, not as a path, which is why moving or renaming an asset inside Unity keeps references intact.

- Move and rename assets **from the Unity Project window**, not from Explorer or a shell. The editor moves the `.meta` with the asset; a shell move leaves it orphaned and Unity mints a new GUID, breaking every reference.
- Commit the `.meta` in the same commit as its asset. An asset without its `.meta` gets a fresh GUID on every machine that imports it, so references break for teammates and not for the author - the hardest version of this bug to see.
- Never add `*.meta` to `.gitignore`. Do ignore `Library/`, `Temp/`, `Logs/`, `obj/`, `Build/`, and the generated `.csproj`/`.sln`.
- A `.meta` deleted in a diff, with its asset still present, is a Critical finding.

### Scene and prefab YAML merge

Scenes and prefabs are YAML, but with `fileID` cross-references that a text merge reorders or duplicates into an unopenable file. Prevention beats resolution:

1. Set `Asset Serialization` to Force Text in Project Settings -> Editor (required for any merge or readable diff at all).
2. Register Unity's `UnityYAMLMerge` (Smart Merge) for `*.unity` and `*.prefab`: as a merge driver (`merge=unityyamlmerge` in `.gitattributes`, plus a `[merge "unityyamlmerge"]` driver entry in git config), or as a `git mergetool` in git config.
3. Split large scenes so two people rarely edit the same one; move shared content into prefabs, which conflict less.
4. Without the merge tool, take one side whole (`git checkout --ours/--theirs`) and redo the other change by hand. A partially hand-merged scene often opens and is subtly wrong, which is worse than one that fails to open.

### Missing scripts and recovery

A component whose script cannot be resolved shows as "Missing (Mono Script)" and its serialized data is retained in the YAML but unreachable. MonoBehaviours and ScriptableObjects bind through the script file's `.meta` GUID, not a stored type name. Causes: the script file was deleted, its GUID changed, the class no longer matches its file name, or its assembly failed to compile.

Recovery in order: fix the compile error first, because a broken assembly can leave every script in it unresolved on a fresh import; if the class was renamed, rename the file to match through the editor (`[MovedFrom]` does not apply to script binding); if a `.meta` GUID changed, restore the old GUID from git history rather than reassigning references by hand.

### ISerializationCallbackReceiver

```csharp
// Good - dictionary rebuilt from serializable lists around the serializer
[System.Serializable] public class Table : ISerializationCallbackReceiver {
    [SerializeField] private List<string> keys = new();
    [SerializeField] private List<int> values = new();
    public Dictionary<string, int> Map = new();
    public void OnBeforeSerialize() { keys.Clear(); values.Clear(); foreach (var kv in Map) { keys.Add(kv.Key); values.Add(kv.Value); } }
    public void OnAfterDeserialize() { Map = new(); for (int i = 0; i < System.Math.Min(keys.Count, values.Count); i++) Map[keys[i]] = values[i]; }
}
```

Both callbacks can run on a background thread, so neither may touch scene or object APIs - no `GameObject`, no component access, no `Resources.Load` (`Debug.Log` is thread-safe). They also run far more often than expected in the editor (every inspector repaint, undo, and reload), so keep them cheap and free of side effects. Throwing inside either can leave the object partially deserialized.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {NotSerialized | NullNotPreserved | SerializeReferenceRisk | FieldRename | PrefabOverride | PrefabVariant | MetaFileGuid | MergeHazard | MissingScript | SerializationCallback | RepoHygiene}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {what is lost - "value reverts on reload", "every reference to this asset breaks for other clones"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path and YAML key for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

`RepoHygiene` covers `.gitignore` and commit-pairing defects that put asset identity at risk without being a specific asset's defect (an asset committed without its `.meta` is one).

Where one defect caused another (a `*.meta` ignore rule and the deleted `.meta` it dropped), the cause is the block and the consequence is named in its `Impact`.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = a `.meta` deleted or GUID-changed for an asset that still exists, `.meta` files gitignored or committed apart from their asset, or a scene or prefab committed hand-merged or with conflict markers. High = a field that does not serialize where the surrounding code reads or writes it as if it does, a serialized field or `[SerializeReference]` type renamed without its persistence attribute, or a prefab override that contradicts the prefab's intent. Medium = a missing script with recoverable data, `ISerializationCallbackReceiver` touching scene or object APIs, or code branching on null for a by-value serialized class. Low = a serialization nit with no data loss. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: where the effect logic lives -> unity-architecture-patterns`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No serialization findings.` |
| A review was requested with nothing to judge | `Serialization check not run: no source supplied.` |

## Avoid

- Expecting a property, `static`, `readonly`, or bare `private` field to persist
- `Dictionary`, `HashSet`, or a nested `List<List<T>>` as a serialized field
- Null checks on a serialized custom class or struct field
- `[SerializeReference]` on a type that is renamed or moved without a persistence attribute
- Moving, renaming, or deleting assets outside the Unity Project window
- `*.meta` in `.gitignore`, or an asset committed without its `.meta`
- Hand-resolving a `*.unity` or `*.prefab` conflict in a text editor
- Instance overrides used as the place to tune values that belong on the prefab
- Scene or object API calls inside `OnBeforeSerialize` or `OnAfterDeserialize`
