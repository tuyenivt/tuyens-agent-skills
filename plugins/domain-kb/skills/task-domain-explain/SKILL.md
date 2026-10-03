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

Use skill: `domain-kb-layout` for every path, section, and empty form named below; read its Rules and the Patterns sections Ids and references, index.md, ATLAS.md, Indexes, and Stale marking. The root is the working directory. Check in this order and stop on the first that holds, emitting its stop line from the Output Format: `_index/sync-state.json` records a non-null `in_progress` (`interrupted`); it is absent or records no `sha` (`no knowledge base`, with the curated hint when any curated folder holds a Markdown file); `ATLAS.md` is absent (`no atlas`). Then read `CLAUDE.md` `## Audience` `Language:` (default `en`) and, for the view the target selects, nothing more than it renders: the atlas view reads `sync-state.json` for `synced`, `window`, every repo's `sha`, and `curated`; `ATLAS.md` for the counts line, `## Learning path`, every `## Capabilities` table, `### Untraced`, and `## Unmapped changes` (its `## Notes` is not rendered); `_index/last-sync.md` for the value after the `Start with` and `Flows` labels (a line or the file absent, as after an `import`, reads `unavailable - not in last-sync.md`); and `index.md` `## Curated` when `curated` is absent, counting the doc lines under each `### {folder}` (a `- none` line counts 0). The stale view reads `synced`, the counts line, the `## Capabilities` tables, `### Untraced`, and `## Unmapped changes`. A lesson reads nothing else here.

### Step 3 - Atlas or stale view (no target, or `stale`)

Render the matching Output Format block and stop. The atlas view takes Synced, Repos, and Flows from Step 2, the learning path and every capability table verbatim from ATLAS (the `#` column as ATLAS numbers it), `### Untraced` and `### Unmapped changes` when their ATLAS table has a row other than the `none` row, the curated counts, the two last-sync lines, and Next. The stale view lists what the last sync marked and the next bare `task-domain-sync` will touch (commits after the recorded `sha` are not visible until it runs): the ATLAS rows whose Status is `stale`, the `### Untraced` rows (it traces missing cards too), and `## Unmapped changes`; orphaned rows go under their own heading, since `update` leaves them and `task-domain-sync init` deletes an orphan whose `## Notes` is empty.

### Step 4 - Resolve and render the lesson (any other target)

Use skill: `domain-flow-explain` with the target as typed, the KB root, and the Languages; it resolves the target by its own rule and emits the resolution and stop lines its contract defines. Emit its output unchanged. When the lesson's Status starts with `stale`, append the Refresh line after the whole lesson, as the Output Format shows.

## Output Format

Atlas view:

```
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

{folder} {n}, ...

### Last sync

- **Start with:** {the value of that line in `_index/last-sync.md` | unavailable - not in last-sync.md}
- **Flows:** {the value of that line in `_index/last-sync.md` | unavailable - not in last-sync.md}

### Next

- {run task-domain-sync - {n} stale, {m} missing{, {k} unmapped} | <capability>/<flow> of the first non-orphaned ATLAS row | none - no flow in ATLAS}
```

`Curated` lists one `{folder} {n}` per `curated` key, zeros included, in the layout's curated-folder order, keys as written (`tech-debt`, never `debt`); from the `index.md` fallback, one per `### {folder}` heading under `## Curated`; with neither, the line reads `unavailable - no curated counts`. Next, in both views, takes the sync form when the counts line shows a stale or missing card, `n` and `m` those counts (orphans are not counted) and `, {k} unmapped` appended when `## Unmapped changes` has a row other than the `none` row (an unmapped row alone never selects the sync form, since a file no card cites stays listed); otherwise the atlas view names the first non-orphaned row in ATLAS order, or `none - no flow in ATLAS`, and the stale view reads `nothing to refresh`.

Stale view:

```
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

- {run task-domain-sync - {n} stale, {m} missing{, {k} unmapped} | nothing to refresh}
```

`Flow` is `<capability>/<flow>` linked as ATLAS links it, and `Capability` is the capability id the link carries (the directory name, not the heading text); Next follows the rule under the atlas view. Every table is present; one with nothing to list keeps its header and one row reading `none - <evidence>` (`none - no stale card`, `none - every trigger has a card`, `none - no orphaned card`, `none - no unmapped change since the last sync`).

Lesson: the `domain-flow-explain` output verbatim; when its Status starts with `stale`, a blank line and then `**Refresh:** run task-domain-sync`.

Stop lines, each emitted alone:

- `sync interrupted at {command}:{pass} - run task-domain-sync to finish`
- `no knowledge base here - run task-domain-sync init{; curated docs exist - task-domain-ask reads them}`
- `no atlas - run task-domain-sync init to rebuild ATLAS.md`

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; non-null `in_progress`, then `sha`, then `ATLAS.md` checked in that order, a stop line emitted alone on the first that held; Languages read, then only what the selected view renders (`synced`, window, SHAs, curated counts, the ATLAS sections, both last-sync values)
- [ ] Step 3: atlas view rendered from `sync-state.json` and ATLAS with the learning path and capability tables verbatim, Untraced and Unmapped only when they have real rows, curated keys as written, Next filled; stale view with all four tables, missing cards included, empty tables in the `none` form; stopped after the block
- [ ] Step 4: target, KB root, and Languages passed to `domain-flow-explain`; its output emitted unchanged, including its resolution and stop lines; Refresh line added only when the lesson's Status starts with `stale`; nothing written

## Avoid

- Tracing, refreshing, or writing a card here; that is `task-domain-sync`'s job
- Resolving a name here instead of in `domain-flow-explain`, or rewriting its lesson into a different shape
- Listing flows in the atlas from `capabilities/` instead of `ATLAS.md`, which carries the reading order
