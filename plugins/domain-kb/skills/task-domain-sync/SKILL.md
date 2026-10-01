---
name: task-domain-sync
description: "Build, refresh, or import a domain knowledge base from service repos: flow cards, ledger, debt, links to curated docs, imported documents."
metadata:
  category: domain
  tags: [domain, knowledge-base, sync, init, update, import, flows, surfaces, ingest]
  type: workflow
user-invocable: true
---

# Domain Sync

Builds the generated layer `domain-kb-layout` defines from the service repositories under `repos/`, refreshes it from the commits since the last run, seeds the curated layer, and imports facts or whole documents into it through `domain-kb-ingest`. Runs at the knowledge-base project root, writes files as each pass completes, and never commits.

## When to Use

- No command (`update`): a synced root after new commits in any repo, or after a repo was added under `repos/`
- `init`: a root with repos under `repos/`, built from scratch; on a synced root (layout drifted, contract changed, a fresh start wanted) it regenerates every generated file, keeping `## Notes`, the carried `CLAUDE.md` sections, aliases, priorities and ids, and deletes the orphans whose `## Notes` is empty; a populated curated layer is left untouched
- `import`: a fact, a file, or a whole foreign knowledge base to place into the curated layer; needs no prior sync

**Not for:** reading the knowledge base (`task-domain-explain`), answering from it (`task-domain-ask`), or turning a ticket into a plan (`task-domain-solve`).

## Inputs

| Input            | Required | Notes                                                                                                                                       |
| ---------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Command          | no       | `init` or `import`; with no command the run is an `update`, or an `init` when `_index/sync-state.json` is absent or records no `sha`         |
| Window           | no       | Days for recent changes, ranking, and runtime corroboration; default `window` in `_index/sync-state.json`, else 30; recorded at the end       |
| Notes            | no       | Text the user pastes for a named flow, rule, or capability; appended to that file's `## Notes` once the file exists in this run               |
| `--repos <csv>`  | no       | Only these repos are fetched, marked, discovered, traced, and distilled; the others keep their recorded state and their cards               |
| `--since <ref \| date>` | no | Per repo, the base of the Mark and Distil range; a ref resolves against the tracked branch, an ISO date to `git -C repos/<repo> rev-list -1 --first-parent --before="<date> 23:59:59" HEAD`; default the recorded `sha` |
| `--no-fetch`     | no       | Skip Step 4; ranges are computed against the checkout as found                                                                              |
| `--capabilities <csv>` | no | Trace only triggers assigned to these capabilities; the rest stay `stale` or `missing` for a later run                                                 |
| `--max-flows <n>` | no      | Trace at most `n` cards in Step 7 order, then stop; the remaining triggers stay `missing` for the next run                                  |
| Text or `--in <path>` | `import` | Inline text, a file, or a directory to ingest; a directory is walked per Step 8                                                       |

## Workflow

Steps name the commands that run them; a command skips the others. Every command but an `import` on an unsynced root sets `in_progress` to `{command}:{pass}` in `sync-state.json` at the start of each pass after Step 2, per the layout. `import` runs Steps 1, 2, 3, 8, and, on a synced root, 11 to 14; on a root with no recorded `sha` it stops after Step 8 with its report emitted and nothing else written.

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

Use skill: `domain-kb-layout` for every path, section, and empty form named below. Read only; nothing is written until every row passes. `import` checks only the writable root, generated-path occupancy, command gate, and `in_progress` rows.

| Check                                                          | Pass                                                       | Fail or warn                                                                               |
| -------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Root is writable                                               | yes                                                        | stop                                                                                       |
| `repos/` exists with at least one subdirectory                 | yes                                                        | `Setup required`, stop                                                                     |
| Each `repos/<repo>/` is its own git checkout                   | `git -C repos/<repo> rev-parse --show-toplevel` prints that directory, compared as normalised absolute paths (a parent repo's path means it is not one) | a `.gitmodules` entry not initialised: stop with `git submodule update --init repos/<repo>`; any other directory: stop with `not a git checkout - clone it or remove it` |
| `.gitmodules`, when present, agrees with the `repos/` directories | consistent                                              | the missing or extra repo is named                                                         |
| Generated paths hold no curated file                           | the layout's occupancy rule holds                          | stop with the layout's `generated path occupied by a curated file` line, naming the path   |
| Command gate                                                   | no command resolves to `update` with a recorded `sha` and to `init` without one; `init` with no recorded `sha` (a populated curated layer passes with `curated layer present: {n} files, untouched`); `import` with `_templates/` present or seedable | `init` on a synced root: warn `synced root - regenerating all {n} generated files; Notes, aliases, priorities and ids carried`, then continue |
| Tracked branch per repo                                        | the `CLAUDE.md` `## Repos` `Branch` cell, else `.gitmodules` `branch` (`.` meaning the root's current branch), else the target of `origin/HEAD` | none of these: `HEAD`'s branch with a warning; the value becomes the `Branch` cell |
| Local `HEAD` against `origin/<branch>`                         | equal; `n/a` when the repo has no `origin`                 | behind: warn, Step 4 fixes it unless `--no-fetch`; ahead or diverged: recorded, Step 4 skips the bump and says why |
| Checkout state per repo                                        | clean, on the tracked branch or detached on its history    | dirty, or on another branch: recorded so Step 4 skips the bump and says why               |
| Recorded `sha` still in history (`update`)                     | yes                                                        | warn `base SHA not in history`; the base becomes `--since` when given, else the commit `rev-list -1 --first-parent --before="<window> days ago" HEAD` names |
| Observability MCP reachable                                    | per `Tracing` and `Errors` tool (from `## Observability`, else derived below): an MCP server for it is connected | `no - <reason>` per tool; recorded, and Step 7 passes no runtime evidence for that tool |
| `in_progress` in `sync-state.json`                             | null, or `{command}:{pass}` to resume                      | resume that command at that pass after this step, reading its inputs from the files earlier passes wrote; the Command input is ignored |

Use skill: `stack-detect` for its marker-file table, and apply that table to each `repos/<repo>/` directory in turn; its single-root detection and conversation cache are not used, since the knowledge-base root has no stack of its own. `Language` and `Framework` form the repo's stack note, `Database` its database, `unknown` accepted; they are derived on `init` and for a `new` repo, and on `update` the recorded values are kept. Read each repo's tracing initialisation for `Tracing:` and its error-tracker initialisation for `Errors:`, plus the service names both declare; an existing `CLAUDE.md` `## Observability` wins when present. Read each repo's `Scope` from `CLAUDE.md` `## Repos` (`all` when absent); `--repos` narrows the repo set for Steps 4 to 8. A repo with no recorded `sha` on `update` is `new`: it is discovered and traced in full, not marked or distilled, and recorded at the end. These in-run values feed every later step; the `stack-detect` block itself is never emitted.

On any stop the workflow emits the `Setup required` block with the commands in order, reading a URL from `.gitmodules` when it has one and leaving `<url>` otherwise, and stops. It runs no git write to fix a preflight failure.

### Step 3 - Scaffold (`init`; `import` seeds `_templates/` only)

Per the layout's Scaffold pass: absent root files with header-only tables (an existing one is regenerated in Step 13 with its carried sections), `overview/` stubs, and, for an absent `CLAUDE.md`, `## Observability` from Step 2, the `Branch` and `Scope` cells, and the fixed `## Audience`, `## Solve`, and `## Precedence` text; `sync-state.json` with stack notes, databases, branches, scopes, `window`, and every recorded `sha` kept, unset where none is recorded. Every `seed` path that is absent is created; a `seed` path that exists is not read or touched.

### Step 4 - Fetch (`init`, `update`; skipped by `--no-fetch` or for a repo with no `origin`)

Per repo, with `BRANCH` from Step 2:

```
git -C repos/<repo> fetch --quiet origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}"
```

The braces are mandatory: in zsh a bare `$BRANCH` followed by `:` and a letter is read as a parameter modifier. Then the guarded bump, only after a successful fetch: skip when Step 2 recorded the checkout dirty, ahead, diverged, or on another branch; `git -C repos/<repo> checkout --detach origin/${BRANCH}` when detached; `git -C repos/<repo> merge --ff-only origin/${BRANCH}` when on the tracked branch, a refused merge (the remote was rewritten or diverged since Step 2) leaving the checkout as found and reported `skipped (ff failed)`. After a bump, for a repo `.gitmodules` lists, `git add repos/<repo>` in the root so the gitlink survives `git submodule update`; a plain clone has no gitlink and nothing is staged. A failed fetch warns and leaves the checkout as found. The tip the run records for each repo is its checkout `HEAD` after this step; Mark and Distil run from the base to that tip, Rank and Recent changes over the window ending today.

### Step 5 - Mark (`update`)

Per the layout's Stale marking, within each repo's scope: diff each recorded repo from its base (`sha`, `--since`, or the Step 2 fallback) to the tip, mark every card a changed mapped file reaches, propagate to capability and ATLAS, append unmapped files to ATLAS `## Unmapped changes`. Changed files a curated doc cites are left to Step 12. Files out of scope are counted, not marked.

### Step 6 - Discover (`init`, `update`)

Read every existing inventory's rows first, for the `new` and `gone` counts. Use skill: `domain-surface-discovery` once per repo in the run's repo set, backend repos first and any repo that serves screens last, passing the repo's scope, the other repos with the inventories already written this run, the existing inventory, the capability table, and this repo's unmapped rows. Write each `surfaces/<repo>.md` whose rows changed; each trigger row carries its capability, which is the Discover set every later step and any resume reads. When `CLAUDE.md` `## Capabilities` is empty, write it from every repo's proposals after the last repo. Remove each ATLAS `## Unmapped changes` row the atomic reports under `Placed`. Collect every `External callers named` entry for Step 11. A card whose trigger lives in a repo discovered this run is marked `orphaned` when the layout's Ids rule matches it to no discovered trigger; an orphaned card whose trigger is discovered again keeps its frozen body and `orphaned` until Step 7 re-traces it with the stale cards. An inventory whose repo directory is gone is marked `orphaned`.

### Step 7 - Trace (`init`, `update`)

A card is due for every trigger row of kind `ui screen`, `public api`, `webhook in`, or `schedule`, and every `message` row no card crosses as a hop, whose capability is not `infrastructure`; `message` rows are traced after every other kind, each only when no card written so far crosses it; an `internal api` row, and a `message` row a card crosses, is a hop inside that card and never `missing`. `init`, and a `new` repo, trace every due trigger, repo by repo in `## Repos` order with backend repos first, each inventory in its row order; `update` traces every stale card (a rediscovered orphan included) and every due trigger with no card (`missing`), stale cards first by `priority`, then missing ones in inventory order. `--capabilities` limits the set and `--max-flows` stops it; every due trigger left without a card is an ATLAS `### Untraced` row. Use skill: `domain-flow-trace` per card, passing the row's surface (or the stale card's id) as Trigger, the row's capability, every repo with its stack note, the KB root with both layers, the inventories, the Window, the `## Observability` values, and the Audience languages; write each card whole as it completes (a `regenerate` write). Then, when Step 2 found a tool reachable, Use skill: `domain-runtime-evidence` once per card with the `## Observability` service that serves the card's trigger surface (the first backend hop for a ui screen), that surface, the card's Edge branches with the log message each emits, `Tracing` and `Errors` (an unreachable tool passed as `none`, its blocks then marked with its Step 2 reason), and the Window; then Use skill: `domain-flow-trace` in corroborate mode with the card and the blocks, and mark the fields it emits into the card. When no tool is reachable, mark every Runtime line `unavailable - <the Step 2 reason>`. Rebuild `_index/file-to-flow.json` from every non-orphaned card's `files` list after the last card. Pasted Notes for a flow are appended here.

### Step 8 - Distil and ingest (`update`, `import`)

Every write to the curated layer in this step is one call per input of Use skill: `domain-kb-ingest`; no script, shell loop, or copy writes a curated file, and each call's `## Signal check`, `## Files`, and `## Conflicts` go into the report. Languages come from `CLAUDE.md` `## Audience` (`en` when absent).

**Distil (`update`).** For the commits in each recorded repo's range touching in-scope files, read messages and diffs and produce candidate facts: one sentence each in the first Audience language with the citation `repos/<repo>/<path>:<line> (commit <short sha>{, <ticket id>})`, the line being where the fact sits at the tip. Keep contract, behaviour, threshold, data-shape, failure-mode, flow, and decision changes, a code comment that states one included; drop tests-only changes, renames, formatting, dependency bumps with no behaviour change, and log tweaks; rationale comes only from commit or PR text in the range. Route each candidate, grouped when several target one topic, through `domain-kb-ingest` in `fact` mode. A range that yields no candidate is a quiet Distil.

**Ingest (`import`).** Inline text or one file is one call in `fact` mode with `Hint` from the text's shape, and for a file `Imported from` as below. A directory is walked for every `*.md` under it, excluding `tmp/`, `_templates/`, `repos/`, dot-folders, `README.md`, `CLAUDE.md`, `index.md`, and any file with `generated: domain-sync`. Each remaining file is one call in `document` mode: the whole file is `Text`, its source folder is `Hint`, `Imported from` is the `--in` path as typed joined with the file's relative path, and the source is never copied or moved. `Split candidates` from every call are collected for the report; no curated document is split. After the last file, every relative link in the files written this run is checked: a target that never existed in the source is listed under `Dangling in source`, a target that was placed at another path under `Broken by move` with its new path; links are not rewritten, since only `domain-kb-ingest` writes curated files.

### Step 9 - Rank (`init`, `update`)

Per the layout's Rank tiers: `priority` and `ranked_by` on every card. `most changed` counts the distinct commits over the card's in-scope `files` whose committer date (`%cs`) falls in the window. In-degree counts the cards naming the flow under `## Related`, a `flow to trace:` entry whose surface equals the card's Trigger Surface included.

### Step 10 - Analyse (`init`, `update`)

- Use skill: `domain-rationale-chain` once over every card's Rules rows and every ledger row no card holds whose `Doc` is a `rules/` path (a row an earlier Link pass added, kept with its id); write `ledger/rules.md`, `ledger/unknown-rationale.md`, `ledger/chains.md`, and mark each card's Rules row. Pasted Notes for a rule are appended to the ledger here.
- Use skill: `domain-behavioral-analysis` over every repo with its scope, the Window, the reverse index, and every card's Monitors line and `ranked_by`; write `debt/recent-risk.md` from its Recent risk table and convert its hotspot, single-point, and coupling rows per its Register rows recipe.
- `debt/register.md` takes every card Debt row and every converted analysis row, with `Fix` as the change that removes the finding and `Detection` as the existing monitor, capture, or review gate that would catch it (`none` when there is none); rows with the same class and `Location` across cards merge into one row listing every flow; ids `D-<n>` are kept where a prior row has the same `Location` file (line number ignored) and the same class word of `Signal`, and assigned after the highest otherwise. `debt/detection-gaps.md` classifies every card by its Monitors and Error tracker lines and rows the `no signal` and `capture only` flows by priority, with the class in `Signal`.
- `playbook/by-symptom.md` takes one row per distinct `User sees` across the cards' Failure modes, with its flows and first checks; `Past incidents` is filled in Step 11.
- `contracts/<caller>.md` takes one file per caller: every repo whose hop list crosses into another repo's `internal api` surface is a caller of that surface, and every `(external - from traces)` caller in a card's Contract is a caller of its surface; each file lists the surfaces used and the sharp edges the cards' Rules and Edge branches record on them, with `Doc` left `none` for Step 11. A caller file no card names any longer is marked `orphaned`.
- Regenerate every inventory with `Used by flows` filled from the cards: a row is used by every card whose Trigger Surface or hop list equals its whole surface string, and `none - no flow cites it` otherwise. Mark each card's `R-new` and `D-new` ids and Contract `Callers` from `contracts/`; resolve every `flow to trace: <kind>: <surface>` entry whose surface string, parenthetical stripped, equals a card's Trigger Surface exactly, to `<capability>/<flow>`.

### Step 11 - Link (`init`, `update`; `import` on a synced root)

Read the curated layer once and point the generated layer at it, in this order, each a `mark`: (1) for every `rules/` doc, the ledger row whose `Enforced at` or rule text the doc names gets `Doc: <path>`; a doc no row matches becomes a new ledger row numbered after the highest id, its `Kind` the doc's `## Enforcement` `Kind:` value (absent: `code` when `Where enforced` is a `file:line`, else `process`), `Enforced at` the doc's `Where enforced` `file:line` for `code` and `process - <path>` otherwise, `Doc` the path, `Flows` from the cards whose surfaces the doc names; Use skill: `domain-rationale-chain` for each new row; its block fills the row's `Rationale`, `Confidence`, `Quirk`, and `Last touched`, is appended to `ledger/chains.md`, and an `unknown` row is copied to `unknown-rationale.md`; (2) every register row whose `Location` a `tech-debt/` item names gets `Doc: tech-debt/<file>.md#<anchor>`; (3) every `contracts/<caller>.md` gets `Doc: consumers/<name>.md` when a doc of that name, or of a name the caller's aliases hold, exists; (4) every playbook row gets `Past incidents` from the `incidents/` files whose text names its symptom or a flow in the row; (5) every card's `## Related` gets `doc: <path>` for each curated doc whose text names the card's Trigger Surface, an entity in its State changes, or a rule text in its Rules, and `consumer: consumers/<name>.md` for each external target or caller with a doc. External callers Step 6 named that have no `consumers/` doc are listed under `Consumers without a doc`. Nothing curated is written.

### Step 12 - Verify citations (`init`, `update`; `import` on a synced root)

Read-only. Run the layout's Verify citations pass against the tip this run records (`import`: the recorded `sha`), rewrite ATLAS `## Citation drift` whole from the result, and count it for the summary; no doc is edited.

### Step 13 - Finalise (`init`, `update`; `import` on a synced root)

Regenerate `capability.md` for every capability with at least one card (pasted Notes for a capability appended here); `overview/domain-model.md` (actors from Triggers, entities from State changes, external systems from `(external - not in repos)` targets, value flow from the `moves money` flows); `overview/state-machines.md` from every State changes row grouped by entity; `overview/glossary.md` from entity, status, and capability names with the code identifiers the cards cite and the `Also called` aliases the curated docs use; `overview/not-supported.md` from rules and error branches that reject a business case outright; then `ATLAS.md` with the counts line, `### Untraced`, and the carried tables; `CLAUDE.md` with its carried sections and `## Repos` holding the `sha` Step 14 records for each repo; and `index.md` with `## Files` and `## Curated` rebuilt from every curated doc's frontmatter. Remove a `.gitkeep` from every curated folder that now holds a Markdown file. On `import` only `index.md`, the `.gitkeep` removal, and the `CLAUDE.md` `## Repos` table run.

### Step 14 - Record

On `init`, delete every orphaned generated file whose `## Notes` is empty. Write `sync-state.json` whole per the layout's Record pass (`sha` per repo at the tip this run used, a repo outside `--repos` and every repo on `import` keeping its recorded `sha`; `branch`, `scope`, `fetch`, `curated` with every curated folder as a key, zeros included; `in_progress` cleared); then write the Output Format block to `_index/last-sync.md` and emit it, every count read back from the files written.

## Output Format

````
## Domain sync

- **Command:** {init | update | import}
- **Root:** {absolute path}
- **Repos:** {repo@short sha, ...}{ (new: repo)}{ (only: repo, repo)}
- **Window:** {n} days{; since {ref or date}}
- **Fetch:** {repo: old -> new (detached | ff) | skipped (dirty | ahead | diverged | branch <x> | no origin | ff failed) | fetch failed - checkout as found | disabled}, ...
- **Scope:** {repo: {n} changed in / {n} out (update) | {n} files in / {n} out (init)}, ...
- **Surfaces:** {n} ({n} new, {n} gone, {n} infrastructure)
- **Capabilities:** {n} ({n} proposed this run)
- **Flows:** {n} cards ({n} traced this run, {n} stale, {n} orphaned, {n} missing)
- **Rules:** {n} ({n} documented, {n} inferred, {n} unknown; {n} code, {n} process, {n} policy, {n} rollout gate)
- **Debt:** {n} rows ({n} high, {n} medium, {n} low; {n} hotspots, {n} single points of knowledge, {n} coupling)
- **Runtime evidence:** {used for {n} flows | unavailable - <the Step 2 reason per tool>}
- **Candidates:** {{n} routed ({n} accepted, {n} downscoped, {n} held, {n} rejected) | 0 routed - quiet | n/a - {init | import}}
- **Linked:** {n} ledger rows ({n} added), {n} register rows, {n} contracts, {n} playbook rows, {n} card entries | n/a - unsynced root
- **Citation drift:** {n} moved, {n} gone | n/a - unsynced root
- **Curated:** {n} files ({n} written this run | untouched)
- **Consumers without a doc:** {names | none}
- **Unmapped changes:** {n}
- **Start with:** {run task-domain-sync again to finish {n} stale cards | run task-domain-sync to trace {n} missing cards | <capability>/<flow> at priority 1}
- **Layout:** {created | updated}
- **Files:** {n} written, {n} verified, {n} seeded, {n} deleted, {n} curated read
- **Deleted:** {paths | none}
- **Seeded:** {paths | none}
- **Drift:**                                              {only when any layout check failed}
  - {path} - {the layout's drift value}

## Distil                                          {update with at least one candidate}

| Candidate | Citation | Signal check | Kind | Files | Conflicts |
| --------- | -------- | ------------ | ---- | ----- | --------- |

## Import                                          {import only}

| Source | Target | Kind | Existing match | Action |
| ------ | ------ | ---- | -------------- | ------ |
| {source path \| inline} | {target path \| -} | {decision-tree folder}{ (hint overruled: <reason>)} | {none \| covering path} | {created \| updated \| downscoped - dropped <what> \| held - conflict with <path> \| rejected - <reason>} |

- **Per folder:** {folder}: {n} source / {n} placed / {n} held / {n} rejected; ...
- **Other files changed:** {the ingest `## Files` lines for files other than a row's target | none}
- **Split candidates:** {target path: kind - section | none}
- **Dangling in source:** {source path -> missing target | none}
- **Broken by move:** {written path -> old target, now at new path | none}
- **Conflicts:** {the ingest ## Conflicts entries | none}

## Setup required                                  {instead of the blocks above, when Step 2 stops}

- {check that failed} - {what was found}

```
{commands in order}
```
````

`Surfaces` counts rows across every inventory; `new` and `gone` compare to the rows Step 6 read before writing, both `0` when no inventory existed. `Start with` takes the first form that applies, in the order shown. The `Root` line and the `Layout` through `Drift` lines are the layout's Output Format with `Seeded` added; `Drift` lists the failures this run's writes did not fix. On `import` the lines no step of the command ran read `n/a`. The Distil table holds one row per ingest call, its cells from that call's blocks. The import table holds one row per source `*.md` outside the skip list in walk order, or one row for inline text or a single file; a `fact` mode split gives one row per piece.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; every preflight row checked before any write, each repo confirmed its own checkout by `--show-toplevel`; occupied generated paths stopped the run per the layout's rule; branch taken from `## Repos` first; ahead, diverged, dirty, and off-branch checkouts recorded; `stack-detect`'s table applied per repo; `Tracing`, `Errors`, scopes, and MCP reachability read; `new` repos identified; `Setup required` emitted with exact commands on a stop and nothing written; resume pass honoured
- [ ] Step 3: absent root files and seed paths created, existing ones untouched, every recorded `sha` kept and none invented, `in_progress` set at the start of every pass (none written on an unsynced `import`)
- [ ] Step 4: fetch run per repo with the braced ref, bump applied only after a successful fetch and under the guard, gitlink staged only for a `.gitmodules` repo, failures reported, skipped entirely under `--no-fetch`
- [ ] Step 5: stale marks and unmapped rows written before any regeneration, within scope, from the stated base; `new` repos skipped
- [ ] Step 6: prior inventory rows read; discovery run backend repos first with scope and the other repos supplied; capability table written once, after the last repo; placed rows removed; external callers collected; orphans marked by the layout's Ids rule only for repos discovered this run, rediscovered orphans made stale
- [ ] Step 7: due triggers per the kind rule, covered hops never missing; traced in the stated order within `--capabilities` and `--max-flows`, `### Untraced` written for the rest; every trace input passed; runtime evidence fetched once per card from reachable tools with its inputs, corroborate fields marked into the card, the Step 2 reason marked otherwise; reverse index rebuilt; flow Notes appended
- [ ] Step 8: every curated write was one `domain-kb-ingest` call with its three blocks reported; Distil candidates cited at the tip and trivia dropped, a quiet Distil stated; import walked every folder with the skip list applied, `document` mode used, `Imported from` as typed, no split of a curated doc, links checked and never rewritten, both link lists separated
- [ ] Step 9: `priority` and `ranked_by` on every card by tier, then in-degree (with `flow to trace:` entries), incidents, commits in the window by `%cs`
- [ ] Step 10: ledger from card rows and the prior Link rows with ids kept, chains, register with severity, category, ids keyed by file and class, converted analysis rows with `ranked_by` passed, recent risk, detection gaps, playbook, contracts written; inventories' `Used by flows` by whole-surface match; card marks updated; `flow to trace:` entries whose surface has a card all resolved; rule Notes appended
- [ ] Step 11: ledger `Doc` and new rows with their `Kind:` and chain, register `Doc`, contract `Doc`, playbook `Past incidents`, card `doc:` and `consumer:` entries filled in that order; consumers without a doc listed; no curated file written
- [ ] Step 12: the layout's Verify pass run against the tip this run records; `## Citation drift` rewritten; no doc edited
- [ ] Step 13: capability files only for capabilities with a card; overview and root files regenerated with carried sections and the tips this run records; `## Curated` rebuilt; `.gitkeep` removed where a doc exists
- [ ] Step 14: orphans with empty Notes deleted on `init`; `sync-state.json` written with `sha` advanced only for repos this run synced, `in_progress` cleared; `_index/last-sync.md` written last; every count read back from files

## Avoid

- Writing any file before the preflight passes, or running a git write other than the Step 4 fetch, guarded bump, and submodule gitlink stage
- Advancing a repo's recorded `sha` before the Record pass, or on `import`
- Regenerating a card without carrying its `## Notes`, aliases, priority, and ids
- Inventing a repository URL for the `Setup required` block
- Fetching runtime evidence before the card exists, or from a tool the preflight found unreachable
- Writing, moving, or copying a curated file by any means other than a `domain-kb-ingest` call, or reading one into `## Notes`
