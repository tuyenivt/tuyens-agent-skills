---
name: task-domain-explain
description: Read the domain knowledge base: no argument lists the atlas and learning path; a flow, capability, or rule name renders it as a lesson.
metadata:
  category: domain
  tags: [domain, knowledge-base, explain, lesson, atlas, learning-path]
  type: workflow
user-invocable: true
---

# Domain Explain

The newcomer's entry to the knowledge base `task-domain-sync` built. With no argument it shows what exists and in what order to read it; with a name it renders one artifact as a lesson through `domain-flow-explain`. It reads and writes nothing; a stale card is rendered as stale and refreshed by `task-domain-sync update`.

## When to Use

- You do not yet know what to ask: run it with no argument and pick from the atlas
- You want one flow, capability, or rule explained in plain words with its reasons, surprises, and symptoms
- You want to see which cards the next `update` will touch: run it with `stale`

**Not for:** a question, ticket, alert, or pasted message (`task-domain-ask`); building or refreshing the knowledge base (`task-domain-sync`).

## Inputs

| Input  | Required | Notes                                                                                                              |
| ------ | -------- | ------------------------------------------------------------------------------------------------------------------ |
| Target | no       | Nothing, or `stale`, for the atlas view; a `<capability>/<flow>`, a bare flow or capability name or alias, or `R-<n>` for a lesson |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate the knowledge base

Use skill: `domain-kb-layout` for the file shapes. The root is the working directory. When `_index/sync-state.json` is absent or records no `sha`, emit `no knowledge base here - run task-domain-sync init` (adding `; hand-written docs exist - task-domain-ask reads them` when any hand-written folder holds a Markdown file) and stop; when it records `in_progress`, emit `sync interrupted at {pass} - run task-domain-sync {command} to finish` and stop. Read `ATLAS.md` for the counts line, the flows, the reading order, and `### Untraced`, `_index/sync-state.json` for the repos, SHAs, window, and `hand_written` counts, `_index/last-sync.md` for its `Start with` and `Flows` lines, `index.md` `## Hand-written` for the per-folder counts when `hand_written` is absent, and the frontmatter `aliases` of every card and `capability.md`.

### Step 3 - Atlas view (no target, or `stale`)

Render the Output Format's atlas block: Synced and Repos from `sync-state.json`, Flows from the ATLAS counts line, the learning path and every capability with its flows in reading order from `ATLAS.md`, the untraced triggers, the hand-written counts, and the last sync's two lines. With `stale`, list only the flows whose Status is `stale` and the `## Unmapped changes` rows, so the reader sees what the next `update` will touch; orphaned flows are listed under their own heading, since `rebuild` is what removes them. Stop after the block.

### Step 4 - Resolve the target

A `<capability>/<flow>` id resolves directly when its card exists. Otherwise apply `domain-flow-explain`'s resolution rule: capability ids and aliases first, then flow ids and aliases across every capability, then `R-<n>` against `ledger/rules.md`. A single match continues; an ambiguous name emits the candidates and stops; a name matching nothing emits `no such flow, capability, or rule: <name>` with the three nearest ids from ATLAS and stops.

### Step 5 - Render the lesson

Use skill: `domain-flow-explain` with the resolved target and the KB root; emit its lesson unchanged, preceded by the `resolved:` line when the target was a bare name. A stale card's lesson carries `stale since` in its Status line and its `## Changed since` rows under Read next, as the atomic renders them; the closing line names `task-domain-sync update` as the way to refresh it.

## Output Format

Atlas view:

```
## Domain atlas

- **Synced:** {date} ({n} days window)
- **Repos:** {repo@sha, ...}
- **Flows:** {n} ({n} stale, {n} orphaned, {n} missing)

### Read in this order

1. {learning path line from ATLAS}
2. ...

### {n}. {Capability}

| # | Flow | Trigger | Status | Read before |
| - | ---- | ------- | ------ | ----------- |

### Untraced                                          {only when ATLAS ### Untraced has rows}

| Capability | Trigger |
| ---------- | ------- |

### Hand-written

{n} rules, {n} specs, {n} incidents, {n} context, {n} debt, {n} adr, {n} consumers, {n} patterns

### Last sync

- **Start with:** {the line from `_index/last-sync.md` | unavailable - no last-sync.md}
- **Flows:** {the line from `_index/last-sync.md` | unavailable - no last-sync.md}

### Orphaned                                          {only with `stale`, when any flow is orphaned}

| Flow | Capability |
| ---- | ---------- |

### Unmapped changes                                  {only with `stale`, or when the table has rows}

| File | Commit | Date |
| ---- | ------ | ---- |

### Next

- {the first flow of the first capability, or `run task-domain-sync update - {n} stale cards` when any is stale}
```

Lesson: `resolved: <id>` when the target was a bare name, then the `domain-flow-explain` lesson verbatim, then `- **Refresh:** run task-domain-sync update` when the card is stale.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; knowledge base located by a recorded `sha` and no `in_progress`; absence or interruption reported, with the hand-written hint when docs exist, and nothing else emitted; `last-sync.md` and hand-written counts read
- [ ] Step 3: Synced and Repos from `sync-state.json`, counts, flows, order and untraced from `ATLAS.md`, hand-written counts and the two last-sync lines rendered; `stale` filter applied with orphans under their own heading; stopped after the block
- [ ] Step 4: target resolved by the atomic's rule; ambiguity and no-match stopped with candidates
- [ ] Step 5: lesson emitted verbatim from `domain-flow-explain`, with the `resolved:` line and the refresh line when they apply; nothing written

## Avoid

- Tracing, refreshing, or writing a card here; that is `task-domain-sync`'s job
- Rewriting the atomic's lesson into a different shape
- Listing flows in the atlas from `capabilities/` instead of `ATLAS.md`, which carries the reading order
