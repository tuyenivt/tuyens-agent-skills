---
name: task-domain-explain
description: "Read the domain knowledge base: the atlas and learning path, the stale cards sync will touch, or a flow, capability, or rule as a lesson."
metadata:
  category: domain
  tags: [domain, knowledge-base, explain, lesson, atlas, learning-path]
  type: workflow
user-invocable: true
---

# Domain Explain

The newcomer's entry to the knowledge base `task-domain-sync` built. With no argument it shows what exists and in what order to read it; with a name it renders one artifact as a lesson through `domain-flow-explain`. It writes nothing; a stale card is rendered as stale and refreshed by `task-domain-sync`.

## When to Use

- You do not yet know what to ask: run it with no argument and pick from the atlas
- You want one flow, capability, or rule explained in plain words with its reasons, surprises, and symptoms
- You want to see what the next `task-domain-sync` will touch: run it with `stale`

**Not for:** a question, ticket, alert, or pasted message (`task-domain-ask`); building or refreshing the knowledge base (`task-domain-sync`).

## Inputs

| Input  | Required | Notes                                                                                                              |
| ------ | -------- | ------------------------------------------------------------------------------------------------------------------ |
| Target | no       | Nothing for the atlas view; `stale`, in any case, for the stale view; a `<capability>/<flow>`, a card or `capability.md` path, a bare flow or capability id or alias, or `R-<n>` for a lesson (a flow or capability named `stale` is reached as `<capability>/<flow>` or by its path) |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate the knowledge base

Use skill: `domain-kb-layout` for every path, section, and empty form named below; read its Rules and the Patterns sections Curated layer, Sync passes (its opening paragraph), Ids and references, index.md, ATLAS.md, Indexes, and Stale marking. The root is the working directory. Check in this order and stop on the first that holds, emitting its stop line from the Output Format: `_index/sync-state.json` is absent or records no `sha` (`no completed sync yet` when it records a non-null `in_progress`, else `no knowledge base`, either with the curated hint when any curated folder holds a Markdown file; this workflow renders the generated layer only, so it stops where the layout lets a reader continue on curated docs); `ATLAS.md` is absent (`no atlas`). A non-null `in_progress` otherwise stops nothing: a sync is running or was interrupted, the output reads the files as they stand, the Sync line opens it, and every `task-domain-sync` remedy this workflow emits (in a slot, a stop line, or a value copied from another file) reads `task-domain-sync --resume` when `in_progress` names `init` or `update`; when it names `import` the remedy keeps its plain form, since `--resume` only clears an interrupted import and itself says to re-run it, which the Sync line's own remedy covers. Then read `CLAUDE.md` `## Audience` `Language:` (default `en`): its first code is the language of the workflow's own text (headings, Next, the `none - <evidence>` rows; the Sync and stop lines keep the layout's wording), the whole list is the Languages passed to the lesson; copied ATLAS and last-sync text keeps its own. Then, for the view the target selects, read nothing more than it renders: the atlas view reads `sync-state.json` for `synced`, `window`, every repo's `sha`, and `curated`; `ATLAS.md` for the counts line, `## Learning path`, every `### {n}. {Capability}` table under `## Capabilities`, `### Untraced`, and `## Unmapped changes` (its `## Notes` and `## Citation drift` are not rendered); `_index/last-sync.md` for the value after the `Start with` and `Flows` labels (a line or the file absent reads `unavailable - not in last-sync.md`; an `n/a - import` value is copied as is); and `index.md` `## Curated` when `curated` is absent or `null`, counting the doc lines under each `### {folder}` (a `- none` line counts 0). The stale view reads `synced`, the counts line, the `## Capabilities` tables, `### Untraced`, and `## Unmapped changes`. A lesson reads nothing else here.

### Step 3 - Atlas or stale view (no target, or `stale`)

Render the matching Output Format block and stop. The atlas view takes Synced, Repos, and Flows from Step 2, the learning path and every capability table verbatim from ATLAS (the `#` column as ATLAS numbers it), `### Untraced` and `### Unmapped changes` when their ATLAS table has a row other than the `none` row, the curated counts on one line, the two last-sync lines, and Next. The stale view lists what the last sync marked (while `in_progress` is set, what the unfinished run has marked so far) and the next `task-domain-sync` will touch (commits after the last fetched tip are not visible until it runs): the ATLAS rows whose Status is `stale`, the `### Untraced` rows (it traces missing cards too), and `## Unmapped changes`; orphaned rows go under their own heading, since `update` leaves them and `task-domain-sync init` deletes an orphan whose `## Notes` is empty.

### Step 4 - Resolve and render the lesson (any other target)

Use skill: `domain-flow-explain` with the target as typed, the KB root, and the Languages (a call from this workflow is non-standalone under its contract: the atomic emits no Sync line, and its `resolved:` line follows the workflow's Sync line when that is set); it resolves the target by its own rule and emits the resolution and stop lines its contract defines. Emit its output after the Sync line when `in_progress` is set, changed only in that every `run task-domain-sync` remedy in its resolution and stop lines takes the Step 2 form (text copied from a card, a Monitors cell included, is not rewritten). When the lesson's Status starts with `stale`, append the Refresh line after the whole lesson, as the Output Format shows.

## Output Format

Atlas view:

```
**Sync:** unfinished at {command}:{pass} - files read as they stand, partly written by the unfinished run; when no sync is running, run task-domain-sync --resume     {only when in_progress is set, then a blank line}

## Domain atlas

- **Synced:** {synced} ({window} days window)
- **Repos:** {repo@first 7 characters of sha | repo@unsynced, ...}
- **Flows:** {the ATLAS counts line's Flows value}

### Read in this order

{the ATLAS learning path list, verbatim}

### {n}. {Capability}

| # | Flow | Trigger | Status | Read before |
| - | ---- | ------- | ------ | ----------- |

### Untraced                                          {only when ATLAS ### Untraced has a row other than the none row}

| Capability | Trigger |
| ---------- | ------- |

### Unmapped changes                                  {only when ATLAS ## Unmapped changes has a row other than the none row}

| File | Commit | Date |
| ---- | ------ | ---- |

### Curated

{{folder} {n}, ... | unavailable - no curated counts}

### Last sync

- **Start with:** {the value of that line in `_index/last-sync.md`, its `run task-domain-sync` in the Step 2 form | unavailable - not in last-sync.md}
- **Flows:** {the value of that line in `_index/last-sync.md`, its `run task-domain-sync` in the Step 2 form | unavailable - not in last-sync.md}

### Next

- {run task-domain-sync{ --resume} - {n} stale, {m} missing{, {k} unmapped} | <capability>/<flow> of the first non-orphaned ATLAS row | none - no non-orphaned flow in ATLAS}
```

`Curated` is one line, comma-separated, one `{folder} {n}` per `curated` key, zeros included, in the layout's curated-folder order, keys as written (`tech-debt`, never `debt`); from the `index.md` fallback, one per `### {folder}` heading under `## Curated`; with neither, the `unavailable` form. Next, in both views, takes the sync form when the counts line shows a stale or missing card, `n` and `m` those counts (orphans are not counted) and `, {k} unmapped` appended when `## Unmapped changes` has a row other than the `none` row (an unmapped row alone never selects the sync form: it is a file to place, not a card to trace); otherwise the atlas view names the first non-orphaned row in ATLAS order, or `none - no non-orphaned flow in ATLAS`, and the stale view reads `nothing to refresh`.

Stale view:

```
**Sync:** unfinished at {command}:{pass} - files read as they stand, partly written by the unfinished run; when no sync is running, run task-domain-sync --resume     {only when in_progress is set, then a blank line}

## Domain atlas - stale

- **Synced:** {synced}
- **Flows:** {the ATLAS counts line's Flows value}

### Stale

| Flow | Capability | Trigger |
| ---- | ---------- | ------- |

### Missing

| Capability | Trigger |
| ---------- | ------- |

### Orphaned

| Flow | Capability |
| ---- | ---------- |

### Unmapped changes

| File | Commit | Date |
| ---- | ------ | ---- |

### Next

- {run task-domain-sync{ --resume} - {n} stale, {m} missing{, {k} unmapped} | nothing to refresh}
```

`Flow` is the Markdown link copied from the ATLAS row, and `Capability` is the capability id the link carries (the directory name, not the heading text); a Missing row copies the `### Untraced` row's cells as written; Next follows the rule under the atlas view. Every table is present; one with nothing to list keeps its header and one row reading `none - <evidence>` (`none - no stale card`, `none - every trigger has a card`, `none - no orphaned card`, `none - no unmapped change since the last sync`).

Lesson: the `domain-flow-explain` output, its remedies in the Step 2 form; when its Status starts with `stale`, a blank line and then `**Refresh:** run task-domain-sync{ --resume}`.

`{ --resume}` is the Step 2 form: ` --resume` while `in_progress` names `init` or `update`, nothing otherwise (null, or `import`). When `sync-state.json` records a non-null `in_progress`, every view, every Step 4 output (a lesson, or a `domain-flow-explain` resolution or stop line), and the `no atlas` stop line opens with `**Sync:** unfinished at {command}:{pass} - files read as they stand, partly written by the unfinished run; when no sync is running, run task-domain-sync --resume` and a blank line, before the view's heading or the line.

Stop lines, each emitted alone (`no atlas` after the Sync line when `in_progress` is set; the other two are the no-`sha` lines, before which no Sync line is emitted):

- `no completed sync yet - {command}:{pass} unfinished; when no sync is running, run task-domain-sync --resume{; curated docs exist - task-domain-ask reads them}`
- `no knowledge base here - run task-domain-sync init{; curated docs exist - task-domain-ask reads them}`
- `no atlas - {run task-domain-sync init | when no sync is running, run task-domain-sync{ --resume}} to rebuild ATLAS.md` (the first form when `in_progress` is null, the second when it is set)

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; `sha`, then `ATLAS.md` checked in that order, a stop line emitted alone on the first that held (`no atlas` after the Sync line when `in_progress` is set); a non-null `in_progress` named on the Sync line, or in the `no completed sync yet` line when no `sha` is recorded, never stopped on by itself, every remedy in the Step 2 form; Language read and applied to the workflow's own text, then only what the selected view renders (`synced`, window, SHAs, curated counts, the ATLAS sections without `## Notes` and `## Citation drift`, both last-sync values)
- [ ] Step 3: atlas view rendered from `sync-state.json` and ATLAS with the learning path and capability tables verbatim, Untraced and Unmapped only when they have real rows, curated keys as written on one line, last-sync values copied with their remedies in the Step 2 form, Next filled in that form while a sync is unfinished; stale view with all four tables and Next, missing rows copied from Untraced, empty tables in the `none` form; nothing written; stopped after the block
- [ ] Step 4: target, KB root, and Languages passed to `domain-flow-explain`; its output emitted after the Sync line when set, including its resolution and stop lines, their remedies alone rewritten to the Step 2 form; Refresh line added only when the lesson's Status starts with `stale`, in that form then; nothing written

## Avoid

- Tracing, refreshing, or writing a card here; that is `task-domain-sync`'s job
- Resolving a name here instead of in `domain-flow-explain`, or rewriting its lesson into a different shape
- Listing flows in the atlas from `capabilities/` instead of `ATLAS.md`, which carries the reading order
