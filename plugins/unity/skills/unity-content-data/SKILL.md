---
name: unity-content-data
description: Model large static content banks for Unity quiz games - authoring format, import validation, Addressables streaming, content updates post-release.
metadata:
  category: mobile
  tags: [unity, content, scriptableobject, addressables, json, csv, validation, quiz]
user-invocable: false
---

# Unity Content Data

> This skill owns **the structure, validation, loading, and versioning of static content banks**. Player progress and save files belong to `unity-save-persistence`; translating bank text belongs to `unity-i18n`; memory and load-time budgets belong to `unity-performance`; where the loading code lives belongs to `unity-architecture-patterns`.

## When to Use

- A game ships a question bank, word list, flag set, level pack, or balance table
- Deciding between JSON, CSV, and ScriptableObject for authored content
- Content is large enough that loading it all costs memory or startup time
- Content needs to change after release without a store submission
- Reviewing a diff that adds, reshapes, or loads content

## Rules

- **Content is data, never code and never prefabs.** A question, level, or item is a row in a bank. One prefab or one C# constant per question is unshippable at bank scale and unreviewable in a diff. A handful of items passed as code arguments is not yet a bank; once entries number more than a few dozen or are authored outside code, these rules apply
- **A malformed bank fails at import or build, never at runtime.** Validation runs in the editor and in CI, and a validation failure fails the build. A user seeing a question with no correct answer is a shipped defect that validation would have caught
- Every content entry has a **stable identifier** that is independent of its array position, its text, and its locale. Reordering a bank must not invalidate saved progress or analytics
- The correct answer is identified by a stable answer id, not by an index into a shuffled list and not by string comparison against display text
- Content is versioned separately from the app binary, with an explicit `contentVersion` the app checks and can migrate across
- Loading strategy is chosen against a measured bank size. Load the whole bank only when the whole bank is small enough to state a number for; otherwise stream by group
- Remote or downloaded content is untrusted input: check the load result (`AsyncOperationHandle.Status` for Addressables, `UnityWebRequest.result` for a raw fetch), validate shape, size, and identifiers on arrival, and fall back to bundled content on failure

## Patterns

### Authoring format

| Format | Authoring | Diffs | Validation | Best for |
| --- | --- | --- | --- | --- |
| CSV | Spreadsheet, non-engineers, bulk edit | Clean line diffs | Import script | Flat rows at volume - questions, words, flags, balance tables |
| JSON | Text editor or tooling, nested shapes | Readable, noisy on reformat | Schema check at import | Nested or heterogeneous content; remote-delivered content |
| ScriptableObject | Unity inspector, one asset per entry | One YAML file per entry, merge-hostile at volume | Editor validation | Small hand-curated sets that reference other Unity assets |

The workable default for a quiz bank: **author in CSV or JSON, import into one ScriptableObject per load unit as a serializable array** - the whole bank when it is small, one asset per category slice when it is not (Loading and streaming, below). Authors get spreadsheet ergonomics and clean diffs; the runtime gets a single asset load with no per-entry file overhead and no runtime parse.

One ScriptableObject asset per question is the failure mode to name explicitly: 2,000 assets means 2,000 `.meta` files, 2,000 GUIDs, a slow import, an unreviewable diff, and Addressables entries that dominate the catalog.

### Content schema

```csharp
// Bad - correct answer is an index into a list that gets shuffled for display
[Serializable] public class Question { public string text; public string[] answers; public int correctIndex; }

// Good - stable ids survive shuffling, reordering, and localization
[Serializable] public sealed class Answer { public string id; public string textKey; }
[Serializable] public sealed class Question {
    public string id;               // stable, unique, never reused: "de-signs-0142"
    public string promptKey;        // localization key, not display text
    public Answer[] answers;        // each with its own id
    public string correctAnswerId;
    public string[] tags;           // category, difficulty, licence class
}
```

Shuffle the presentation order, resolve correctness by `correctAnswerId`. With `correctIndex`, any shuffle, any locale that reorders answers, and any authoring reorder produces a silently wrong grade.

`promptKey` is the keys-into-string-tables shape. In the per-locale-banks shape (see Localization interaction) the field holds that locale's display text instead - legitimate, as long as correctness and progress still resolve by id, never by text.

Distractors (wrong answers) are authored content, not generated at runtime. A generated distractor can be accidentally correct, duplicate the right answer, or be trivially implausible. Where distractors are pooled across questions, validation must assert the pooled set never contains the correct answer for the question drawing from it.

`tags` carries the filtering axes the game needs - category, difficulty, licence class, region. Encoding those as separate banks instead means every new axis is a new file and a new loading path.

### Import-time validation

```csharp
// Bad - trusts the file; the failure surfaces in front of a player
var bank = JsonUtility.FromJson<QuestionBankDto>(text);   // used as-is

// Good - an editor validation entry point CI runs in batch mode; every defect reported, the job fails on any
var errors = new List<string>(); var seen = new HashSet<string>();
for (var i = 0; i < bank.questions.Length; i++) {
    var q = bank.questions[i];
    if (string.IsNullOrEmpty(q.id)) errors.Add($"row {i}: empty id");
    else if (!seen.Add(q.id)) errors.Add($"duplicate id {q.id}");
    if (Array.FindIndex(q.answers, a => a.id == q.correctAnswerId) < 0) errors.Add($"{q.id}: correctAnswerId matches no answer");
}
if (errors.Count > 0) throw new BuildFailedException(string.Join("\n", errors));
```

The validation set that catches real bank defects:

| Check | Failure it prevents |
| --- | --- |
| Non-empty, unique ids | Save/analytics collisions; unresolvable progress |
| `correctAnswerId` resolves to an answer | Ungradeable question shown to a player |
| Answer ids unique within a question (multi-select uses a `correctAnswerIds` array with its own count check) | Ambiguous grading |
| Answer count within the range the UI renders | Truncated or clipped options |
| No duplicate answer text within a question | Two identical options, one of them "wrong" |
| Referenced assets (images, audio, flags) resolve | Missing sprite at runtime |
| Localization key exists for every shipped locale | Blank or key-shaped text in the UI |
| Prompt and answer lengths within layout limits | Overflow in fixed-width 2D layouts |

Run this as an editor validation entry point that CI invokes in batch mode, with a non-zero exit on failure. Validation that only runs when a developer clicks a menu item is not validation.

### Loading and streaming

| Bank size | Strategy |
| --- | --- |
| Small, fully needed | One Addressables asset load at session start; hold for the session |
| Large, sliced by category or level | One Addressables group per slice; load the slice, release on exit |
| Very large or update-driven | Remote Addressables group with a catalog; download on demand, cache on device |

```csharp
// Bad - the whole 5,000-question bank plus every image resident for a 10-question round
var bank = Resources.Load<QuestionBank>("AllQuestions");

// Good - load the slice the round needs, release when the round ends
var handle = Addressables.LoadAssetAsync<QuestionBank>(categoryKey);
var bank = await handle.Task;
if (handle.Status != AsyncOperationStatus.Succeeded) { /* bundled fallback */ }
// ...
Addressables.Release(handle);
```

`Resources/` is the legacy path: everything under it ships in the build, is indexed at startup, and cannot be partially updated. Use Addressables.

Every `LoadAssetAsync` needs a matching `Release`. Unreleased handles are the standard Addressables memory leak, and they compound across rounds. Handles held by a screen are released when the screen pops.

Text is cheap; referenced media is not. A 5,000-row question bank is a few megabytes of strings, but 5,000 referenced sprites resident at once is a memory failure on a low-end Android device. Reference media by Addressables key and load it per presented question, not per bank entry. See `unity-performance` for the budget, `unity-2d-rendering` for atlas grouping.

Group content so a group is the unit the game actually needs - by category, licence class, or level pack. Groups split by authoring convenience produce downloads that fetch content the player will not see.

### Content updates without a store release

Remote Addressables groups plus a hosted catalog let a bank change without a binary submission:

```
build -> remote catalog + content bundles -> CDN
app start -> check catalog hash -> download changed bundles -> use
```

What this can and cannot do: content bundles can change data, text, and referenced assets. They never carry code, on any scripting backend - a rules change still needs a store release. Build content updates with the same Unity and Addressables versions and the shipped build's content state. A serialized field the installed player does not know is silently dropped on load (bundles carry type trees by default), which is what `minAppVersion` below guards against.

Every remote fetch needs the offline path: bundled content ships in the build and is the fallback when the catalog is unreachable, the download fails, or validation of the downloaded bank fails. A first-run experience that requires a download is a first-run failure on a plane.

Version explicitly:

```csharp
// Bad - swap the file and hope every install agrees
public QuestionBank bank;   // no version: an old binary loads a bank it cannot fully read

// Good - the app knows what it holds and what it needs
public sealed class BankManifest : ScriptableObject {
    public int contentVersion;      // bumped on every shipped bank change
    public int minAppVersion;       // CI-stamped integer build number, shipped in a ScriptableObject; below it, keep bundled content
}
```

`minAppVersion` is what stops a bank that uses a new field from loading into an old binary that will silently drop it. Content that references saved progress by id must never reuse an id for different content - retire ids, do not recycle them.

### Localization interaction

A bank multiplies by locale. Two shapes, and the choice is structural - keys when the UI already uses string tables or translators work per string, per-locale banks when translation arrives as whole files:

| Shape | Bank holds | Cost |
| --- | --- | --- |
| Keys into string tables | `promptKey`, answer keys | One bank; translations live in `unity-i18n` string tables; loads one locale |
| Per-locale banks | Full text per locale | N banks; simplest for bulk-translated static content; must load only the active locale |

Either way: **never ship every locale's text resident at once**, and never key correctness off translated text. The correct-answer id is locale-invariant; the display string is not. `unity-i18n` owns table structure, glyph coverage, and text expansion; this skill owns that the bank's identifiers stay stable across all of it.

## Output Format

Two modes, chosen by what the request supplies.

**Authoring mode** - the request asks for code or a design. Emit, in order: any `Precondition: {defect in existing code the design depends on fixing}` lines; the code or design; one-line notes after it, one per decision this skill governs; then any `Deferred:` lines. No finding blocks, no severity, no status line.

**Review mode** - the request supplies something to judge: source, a diff, an asset or setting, or a report of a symptom (a QA ticket, a crash or CI log, a verbal description). Emit, in order: the finding blocks, any `Deferred:` lines, and - only when no block was emitted - the status line. Nothing else precedes the first block. A review requested with nothing to judge is still review mode.

```
### [{Critical | High | Medium | Low}] {anchor}

- Category: {Format | Schema | Validation | Identifier | Loading | Memory | Versioning | RemoteContent | LocaleStructure}
- Evidence: {source | inferred (what was not seen)}
- Code: {one-line citation | not supplied}
- Impact: {what a player or author hits - "shuffled answers grade wrong", "whole bank resident for a 10-question round"}
- Fix: {concrete change}
```

The anchor is the first that applies: `file:line` when the source carries paths (a diff hunk by its new-file line); `Type.Member` when it arrived without paths; the asset path for an asset or setting; a short paraphrase of the reported symptom when nothing was read. `Code` is `not supplied` when nothing was read.

**One block per defect** - one root cause with one fix. The same defect at several sites is one block: anchor the clearest site and list the others in `Impact`. One line carrying two defects with separate fixes is two blocks. A reported symptom gets one block per cause - among those this skill's Patterns name for it - that the evidence cannot rule out, most likely first, each `Fix` opening with the check that confirms or eliminates it.

`Category` takes exactly one value. Where a defect fits two, take the one whose failure is worse and name the other in `Impact`; where it fits none, take the closest and name the real concern in `Impact`. A value in this enum is this skill's finding even where a sibling owns adjacent mechanics.

Severity bands - Critical = content defect reaches a player (ungradeable or wrongly graded question, no import validation at all, unvalidated remote bank, no offline fallback) or a content id collides with saved progress. High = whole-bank load where a slice is needed, unreleased Addressables handles, or validation that exists but does not fail the build. Medium = format or grouping choice that costs authoring or download efficiency with no correctness impact. Low = schema or naming nit. A defect no band names takes the band of the listed defect with the closest consequence, and `Impact` names that comparison.

`Evidence: source` means the lines that decide the defect and its band were read; an absence is source when the whole file that would hold it was read, and a diff hunk is source for the lines it shows. `Evidence: inferred` means some were not - a symptom report, a diff summary naming only a path, or a read line whose band turns on something unseen (a declaration, a caller, whether an asset is referenced); state what was not seen. Inferred caps the header at High: a Critical-band defect is written `[High]` and its `Impact` ends with `Uncapped: Critical.` Evidence never raises a band.

Order blocks by band, Critical first; a capped `[High]` block sorts before the other High blocks. Within a band, a root cause comes before the symptoms it produces, then the defect with the wider player impact; where neither separates two blocks, keep the order the input presents them in.

A defect owned by a sibling skill this file names is not emitted here. Write it after the findings as `Deferred: {defect} -> {owning skill}`, one line per defect. When a finding's fix needs a sibling's decision, emit the finding and add a `Deferred:` line for that part. In authoring mode the same line routes a design decision the sibling owns (`Deferred: string-table structure -> unity-i18n`). `Deferred:` lines may precede any status line; omit them when there are none.

When no block was emitted, close with exactly one status line - the first row whose condition holds:

| Condition | Line |
| --- | --- |
| The project ships no static content bank | `No content bank in scope.` |
| Source, a diff, an asset or setting, or a symptom report was supplied, and it yields no finding | `No content findings.` |
| A review was requested with nothing to judge | `Content check not run: no source supplied.` |

## Avoid

- One prefab or one ScriptableObject asset per content entry at bank scale
- Content entries hardcoded in C# arrays or switch statements
- `correctIndex` into a list that is shuffled, reordered, or localized
- Distractors generated at runtime with no correctness check
- Validation that runs only on a developer's menu click, or only at runtime
- Content ids reused, renamed, or derived from array position
- `Resources.Load` for content banks
- `LoadAssetAsync` with no matching `Release`
- Every referenced sprite or audio clip resident because the bank references them directly
- Remote content trusted without shape validation, or shipped with no bundled fallback
- Every locale's text loaded when one locale is active
