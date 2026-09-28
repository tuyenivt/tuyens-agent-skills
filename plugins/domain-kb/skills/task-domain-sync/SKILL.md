---
name: task-domain-sync
description: Build, refresh, or import a domain knowledge base from service repos: preflight, fetch, discover, trace, distil, rank, analyse, link, verify, record.
metadata:
  category: domain
  tags: [domain, knowledge-base, sync, init, update, rebuild, import, flows, surfaces, ingest]
  type: workflow
user-invocable: true
---

# Domain Sync

Builds the generated layer `domain-kb-layout` defines from the service repositories under `repos/`, refreshes it from the commits since the last run, seeds the curated layer, and imports facts or whole documents into it through `domain-kb-ingest`. Runs at the knowledge-base project root, writes files as each pass completes, and never commits.

## When to Use

- `init`: a root with repos under `repos/` and no recorded sync; a populated curated layer is fine and is left untouched
- `update`: a synced root after new commits in any repo, or after a repo was added under `repos/`
- `rebuild`: a synced root whose layout drifted or whose contract changed; regenerates every generated file, keeping `## Notes`, the carried `CLAUDE.md` sections, aliases, priorities and ids
- `import`: a fact, a file, or a whole foreign knowledge base to place into the curated layer; needs no prior sync

**Not for:** reading the knowledge base (`task-domain-explain`), answering from it (`task-domain-ask`), or turning a ticket into a plan (`task-domain-solve`).

## Inputs

| Input            | Required | Notes                                                                                                                                       |
| ---------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Command          | no       | `init`, `update`, `rebuild`, or `import`; default `init` when `_index/sync-state.json` is absent or records no `sha`, `update` otherwise      |
| Window           | no       | Days for recent changes, ranking, and runtime corroboration; default `window` in `_index/sync-state.json`, else 30; recorded at the end       |
| Notes            | no       | Text the user pastes for a named flow, rule, or capability; appended to that file's `## Notes` once the file exists in this run               |
| `--repos <csv>`  | no       | Only these repos are fetched, marked, discovered, traced, and distilled; the others keep their recorded state                                |
| `--since <ref \| date>` | no | Per repo, the base of every commit range, resolved against the tracked branch; an ISO date resolves to the last first-parent commit on or before it; default the recorded `sha` |
| `--no-fetch`     | no       | Skip Step 4; ranges are computed against the checkout as found                                                                              |
| `--capabilities <csv>` | no | Trace only triggers assigned to these capabilities; the rest become `missing` cards for a later run                                         |
| `--max-flows <n>` | no      | Trace at most `n` cards in priority order, then stop; the remaining triggers are `missing` cards for the next run                            |
| Text or `--in <path>` | `import` | Inline text, a file, or a directory to ingest; a directory is walked per Step 8                                                       |

## Workflow

Steps name the commands that run them; a command skips the others. `import` on a root with no recorded `sha` runs Steps 1, 2, 3, 8 and its report, then stops.

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

Read only; nothing is written until every row passes. `import` checks only the first, fifth, sixth, and last rows.

| Check                                                          | Pass                                                       | Fail or warn                                                                               |
| -------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Root is writable                                               | yes                                                        | stop                                                                                       |
| `repos/` exists with at least one subdirectory                 | yes                                                        | `Setup required`, stop                                                                     |
| Each `repos/<repo>/` resolves `git rev-parse HEAD`             | sha                                                        | an added but uninitialised submodule is named with its fix command; a non-git directory as `not a git checkout` (discovered and traced, never fetched, marked, or distilled) |
| `.gitmodules`, when present, agrees with the `repos/` directories | consistent                                              | the missing or extra repo is named                                                         |
| Generated paths hold no curated file                      | every file at a generated path carries `generated: domain-sync`, or the path is absent | `generated path occupied by a curated file: <path> - move it (context/ is the usual home) or delete it`, stop |
| Command gate                                                   | `init` with no recorded `sha` (a populated curated layer passes with `curated layer present: {n} files, untouched`); `update` with one; `rebuild` with a recorded `sha`; `import` with `_templates/` present or seedable | `init` on a synced root names `rebuild`; `update` or `rebuild` on an unsynced root names `init` |
| Tracked branch per repo                                        | `.gitmodules` `branch`, else the target of `origin/HEAD`   | neither: `HEAD`'s branch with a warning; the value becomes the `Branch` cell               |
| Local `HEAD` against `origin/<branch>`                         | equal or ahead                                             | behind by `n` commits: warn; Step 4 fixes it unless `--no-fetch`                            |
| Checkout state per repo                                        | clean, on the tracked branch or detached at its tip        | dirty, or parked on another branch: recorded so Step 4 skips the bump and says why          |
| Recorded `sha` still in history (`update`)                     | yes                                                        | warn `base SHA not in history`; the range base becomes `--since` when given, else the window default (`--since=<window> days ago`) |
| Observability MCP reachable                                    | `yes` per tool named in `## Observability`                 | `no - <reason>` per tool; recorded, Step 7 fetches nothing for that tool and every Runtime line carries the reason |
| `in_progress` in `sync-state.json`                             | null, or `{command}:{pass}` to resume                      | resume that command at that pass after this step, reading its inputs from the files earlier passes wrote; the Command input is ignored |

Use skill: `stack-detect` for its marker-file table, and apply that table to each `repos/<repo>/` directory in turn; its single-root detection and conversation cache are not used, since the knowledge-base root has no stack of its own. `Language` and `Framework` form the repo's stack note, `Database` its database, `unknown` accepted. Read each repo's tracing initialisation for `Tracing:` and its error-tracker initialisation for `Errors:`, plus the service names both declare; an existing `CLAUDE.md` `## Observability` wins when present. Read each repo's `Scope` from `CLAUDE.md` `## Repos` (`all` when absent) and its `Branch` from the row above; `--repos` narrows the repo set for Steps 4 to 8. A repo with no recorded `sha` on `update` is `new`: it is discovered and traced in full below and recorded at the end. These in-run values feed every later step and are written only in Steps 3, 13, and 14; the `stack-detect` block itself is never emitted.

On any stop the workflow emits the `Setup required` block with the commands in order, reading a URL from `.gitmodules` when it has one and leaving `<url>` otherwise, and stops. It runs no git write to fix a preflight failure.

### Step 3 - Scaffold (`init`, `rebuild`; `import` seeds `_templates/` only)

Per the layout's Scaffold pass: root files with empty tables, `overview/` stubs, `CLAUDE.md` with `## Observability` from Step 2, `Branch` and `Scope` cells, and the fixed `## Audience`, `## Solve`, and `## Precedence` text; `sync-state.json` with stack notes, databases, branches, scopes, `window`, and on `init` every `sha` unset (`rebuild` keeps the recorded values). Every `seed` path that is absent is created: `README.md`, `.gitignore`, the nine `_templates/` files, and each curated folder with a `.gitkeep`; a `seed` path that exists is not read or touched. The report lists `seeded: {paths}`. `in_progress` is set to `{command}:scaffold` here and advanced at every pass below.

### Step 4 - Fetch (`init`, `update`, `rebuild`; skipped by `--no-fetch` or for a repo with no `origin`)

Per repo, with `BRANCH` from Step 2:

```
git -C repos/<repo> fetch --quiet origin "+refs/heads/${BRANCH}:refs/remotes/origin/${BRANCH}"
```

The braces are mandatory: in zsh a bare `$BRANCH:` parses as a history modifier. Then the guarded bump: skip when the checkout is dirty; `git -C repos/<repo> checkout --detach origin/${BRANCH}` when detached; `git -C repos/<repo> merge --ff-only origin/${BRANCH}` when on the tracked branch; skip and report when on any other branch. After a successful bump, `git add repos/<repo>` in the root so the gitlink survives `git submodule update`; nothing is committed. A fetch failure warns, uses the local `origin/<branch>` ref as found, and leaves that repo's recorded `sha` unchanged at Step 14. Every range below (Mark, Distil, Recent changes, Rank) runs from the base to the tip this step leaves, which is the checkout `HEAD`.

### Step 5 - Mark (`update`)

Per the layout's Stale marking, within each repo's scope: diff each recorded repo from its base (`sha`, or the Step 2 fallback) to `HEAD`, mark every card a changed mapped file reaches, propagate to capability and ATLAS, append unmapped files to ATLAS `## Unmapped changes`. Changed files a curated doc cites are left to Step 12. A `new` repo has no diff and skips this step. Files out of scope are counted, not marked.

### Step 6 - Discover (`init`, `update`, `rebuild`)

Read every existing inventory's rows first, for the `new` and `gone` counts. Use skill: `domain-surface-discovery` once per repo, backend repos first and any repo that serves screens last, passing the repo's scope, the other repos with the inventories already written this run, the existing inventory, the capability table, and this repo's unmapped rows. Write each `surfaces/<repo>.md` whose rows changed; each trigger row carries its capability in the `Capability` column (`infrastructure` rows are hops, never traced as triggers), which is the Discover set every later step and any resume reads. When `CLAUDE.md` `## Capabilities` is empty, write it from every repo's proposals after the last repo. Remove each ATLAS `## Unmapped changes` row the atomic reports under `Placed`. Collect every `External callers named` entry for Step 11. Mark `orphaned` every card whose trigger surface no repo discovered and every inventory whose repo directory is gone.

### Step 7 - Trace (`init`, `update`, `rebuild`)

Use skill: `domain-flow-trace` once per trigger row of kind `ui screen`, `public api`, `webhook in`, `schedule`, or `message` whose capability is not `infrastructure` (`init`, `rebuild`, and a `new` repo), `internal api` rows being hops inside those flows, or once per stale or missing card in priority order (`update`; a trigger row of those kinds with no card is a missing card), limited by `--capabilities` and stopped after `--max-flows` cards; every trigger left untraced is written to ATLAS `### Untraced`. Pass the row's capability, every repo with its stack note, the KB root with both layers, the inventories, the Window, the `## Observability` values, and the Audience languages. Write each card as it completes in `regenerate` mode; a `proposed: <name>` capability is written to the inventory row before its card is written, and to `## Capabilities` only while that table is still empty. Then, for each tool Step 2 found reachable, Use skill: `domain-runtime-evidence` for the card's trigger surface (the first backend hop for a ui screen) with the card's Edge branches, and Use skill: `domain-flow-trace` in its corroborate mode with the card and the blocks, which marks the card's Runtime lines, `Exercised in traces` cells, `verified_by_trace`, Contract `Callers`, Where to watch monitors, Recent changes deploy rows, and a `trace differs` Debt row; when no tool is reachable, every Runtime line reads `unavailable - <the Step 2 reason>`. Rebuild `_index/file-to-flow.json` from every non-orphaned card's `files` list after the last card. Pasted Notes for a flow are appended here.

### Step 8 - Distil and ingest (`update`, `import`)

Every write to the curated layer in this step is one `Use skill: domain-kb-ingest` call per input; no script, shell loop, or copy writes a curated file, and each call's `## Signal check` and `Kind` line goes into the report. Languages come from `CLAUDE.md` `## Audience`.

**Distil (`update`).** For the commits in each repo's range touching in-scope files, read messages and diffs and produce candidate facts: one English sentence each with the citation `repos/<repo>/<path>:<line> (commit <short sha>{, <ticket id>})`, the line being where the fact sits at the tip. Keep contract, behaviour, threshold, data-shape, failure-mode, flow, and decision changes; drop tests-only changes, renames, formatting, dependency bumps with no behaviour change, and log tweaks; rationale comes only from commit or PR text in the range. Route each candidate, grouped when several target one topic, through `domain-kb-ingest` in `fact` mode. Count accepted, updated, created, rejected-dup, and flagged-conflict for the summary. A range that yields no candidate is a quiet Distil, a valid outcome the summary states as `Candidates: 0 routed - quiet`.

**Ingest (`import`).** Inline text or one file is one call in `fact` mode with `Hint` from the text's shape. A directory is walked for every `*.md` under it, excluding `tmp/`, `_templates/`, `repos/`, `.claude/`, `README.md`, `CLAUDE.md`, `index.md`, and any file with `generated: domain-sync`; `index.md` is regenerated by sync, never imported. Each remaining file is one call in `document` mode: the whole file is `Text`, its source folder is `Hint`, `Citation` carries `imported_from` as the `--in` path as typed joined with the file's relative path, and the source is never copied or moved. The document is placed whole under the kind ingest chose (the source folder wins only a tie); its tags keep the kind first and every original tag after it; `Split candidates` from every call are collected for the report and no curated document is split. After the last file of the last folder, relative links across every file written this run are rewritten once to their new paths; a target that never existed in the source is reported under `Dangling in source`, a target that existed and was placed elsewhere under `Broken by move`, and both lists are re-checked after the rewrite. The per-folder line counts every source folder walked, `adr/` included, and a source folder absent from that line fails the Self-Check.

### Step 9 - Rank (`init`, `update`, `rebuild`)

Per the layout's Rank tiers: `priority` and `ranked_by` on every card, `moves money` first, then `grants access`, then `most changed` (distinct commits from read-only `git log --since` over the card's in-scope `files`), then `most incidents`, then `unranked` in trigger order; inside a tier, in-degree first, then incidents naming the flow, then commits.

### Step 10 - Analyse (`init`, `update`, `rebuild`)

- Use skill: `domain-rationale-chain` once over every card's Rules rows; write `ledger/rules.md`, `ledger/unknown-rationale.md`, `ledger/chains.md`, and mark each card's Rules row. Pasted Notes for a rule are appended to the ledger here.
- Use skill: `domain-behavioral-analysis` over every repo with its scope, the Window, the reverse index, and the cards' Monitors lines; write `debt/recent-risk.md` from its Recent risk table and convert its hotspot, single-point, and coupling rows per its Register rows recipe.
- `debt/register.md` takes every card Debt row and every converted analysis row, with `Fix` as the change that removes the finding and `Detection` as the monitor, capture, or review gate that would catch it (`none` when there is none); rows with the same class and `Location` across cards merge into one row listing every flow; ids `D-<n>` kept by `Location` plus the class word of `Signal` where a prior row matches and assigned in that order otherwise. `debt/detection-gaps.md` classifies every card by its Monitors and Error tracker lines and rows the `no signal` and `capture only` flows by priority, with the class in `Signal`.
- `playbook/by-symptom.md` takes one row per distinct `User sees` across the cards' Failure modes, with its flows and first checks; `Past incidents` is filled in Step 11.
- `contracts/<caller>.md` takes one file per caller: every repo whose hop list crosses into another repo's `internal api` surface is a caller of that surface, and every `(external - from traces)` caller in a card's Contract is a caller of its surface; each file lists the surfaces used and the sharp edges the cards' Rules and Edge branches record on them, with `Doc` left `none` for Step 11. A caller file no card names any longer is marked `orphaned`.
- Regenerate every inventory with `Used by flows` filled from the cards: a row is used by every card whose Trigger Surface or hop list equals its whole surface string, and `none - no flow cites it` otherwise. Mark each card's `R-new` and `D-new` ids and Contract `Callers` from `contracts/`; resolve every `flow to trace: <kind>: <surface>` entry whose surface string, parenthetical stripped, equals a card's Trigger Surface exactly, to `<capability>/<flow>`.

### Step 11 - Link (`init`, `update`, `rebuild`; `import` on a synced root)

Read the curated layer once and point the generated layer at it, in this order, each a `mark`: (1) for every `rules/` doc, the ledger row whose `Enforced at` or rule text the doc names gets `Doc: <path>`, and a doc no row matches becomes a new ledger row of its `Validation type`'s kind (`process`, `policy`, or `rollout gate`; `code` when the doc cites a `file:line` no card holds) with `Enforced at` `process - <path>`, `Doc` the path, `Flows` from the cards whose surfaces the doc names, and `Rationale` from its `## Rationale`; (2) every register row whose `Location` a `tech-debt/` item names gets `Doc: tech-debt/<file>.md#<anchor>`; (3) every `contracts/<caller>.md` gets `Doc: consumers/<name>.md` when a doc of that name, or of a name the caller's aliases hold, exists; (4) every playbook row gets `Past incidents` from the `incidents/` files whose text names its symptom or a flow in the row; (5) every card's `## Related` gets `doc: <path>` for each curated doc whose text names the card's Trigger Surface, an entity in its State changes, or a rule text in its Rules, and `consumer: consumers/<name>.md` for each external target or caller with a doc. External callers Step 6 named that have no `consumers/` doc are listed in the summary under `Consumers without a doc`. Nothing curated is written.

### Step 12 - Verify citations (`init`, `update`, `rebuild`; `import` on a synced root)

Read-only. For every `repos/<repo>/<path>:<line>` in the curated layer, read that line at the recorded tip: `verified` when the cited code is there, `moved` when it sits at another line in the file, `gone` when it is not in the file. Write the `moved` and `gone` rows to ATLAS `## Citation drift` and count them for the summary; no doc is edited. After an `import`, re-check the `Dangling in source` and `Broken by move` lists from Step 8 against the files as written.

### Step 13 - Finalise (`init`, `update`, `rebuild`; `import` on a synced root)

Regenerate `capability.md` for every capability with at least one card (pasted Notes for a capability appended here); `overview/domain-model.md` (actors from Triggers, entities from State changes, external systems from `(external - not in repos)` targets, value flow from the `moves money` flows); `overview/state-machines.md` from every State changes row grouped by entity; `overview/glossary.md` from entity, status, and capability names with the code identifiers the cards cite and the `Also called` aliases the curated docs use; `overview/not-supported.md` from rules and error branches that reject a business case outright; then `ATLAS.md` with the counts line, `### Untraced`, and the carried tables; `CLAUDE.md` `## Repos` with the tips this run records and the `Branch` and `Scope` cells carried; and `index.md` with `## Files` and `## Curated` rebuilt from every curated doc's frontmatter. Remove a `.gitkeep` from every curated folder that now holds a Markdown file. On `import` only `index.md`, the `.gitkeep` removal, and the `CLAUDE.md` `## Repos` table run.

### Step 14 - Record

On `rebuild`, delete every orphaned generated file whose `## Notes` is empty. Write `sync-state.json` whole per the layout's Record pass (`sha` per repo at the tip this run used, `branch`, `scope`, `fetch`, `curated` counts, `in_progress` cleared), then write the Output Format block to `_index/last-sync.md` and emit it, every count read back from the files written.

## Output Format

````
## Domain sync

- **Command:** {init | update | rebuild | import}
- **Root:** {absolute path}
- **Repos:** {repo@sha, repo@sha}{ (new: repo)}{ (only: repo, repo)}
- **Window:** {n} days{; since {ref or date}}
- **Fetch:** {repo: old -> new (detached | ff) | skipped (dirty | branch <x> | fetch failed | no origin) | disabled}, ...
- **Scope:** {repo: {n} in / {n} out}, ...
- **Surfaces:** {n} ({n} new, {n} gone, {n} infrastructure)
- **Capabilities:** {n} ({n} proposed this run)
- **Flows:** {n} cards ({n} traced this run, {n} stale, {n} orphaned, {n} missing)
- **Rules:** {n} ({n} documented, {n} inferred, {n} unknown; {n} code, {n} process, {n} policy, {n} rollout gate)
- **Debt:** {n} rows ({n} high, {n} medium, {n} low; {n} hotspots, {n} single points of knowledge, {n} coupling)
- **Runtime evidence:** {used for {n} flows | unavailable - <the Step 2 reason per tool>}
- **Candidates:** {n} routed ({n} accepted, {n} rejected-dup, {n} flagged) | 0 routed - quiet
- **Linked:** {n} ledger rows, {n} register rows, {n} contracts, {n} playbook rows, {n} card entries | n/a - unsynced root
- **Citation drift:** {n} moved, {n} gone
- **Curated:** {n} files, untouched
- **Consumers without a doc:** {names | none}
- **Unmapped changes:** {n}
- **Layout:** {created | updated}, {n} written, {n} seeded ({paths | none}), {n} curated read
- **Start with:** {<capability>/<flow> at priority 1, or `run update again to finish {n} stale cards`, or `run update to trace {n} missing cards`}

## Import                                          {import only}

| Source | Target | Kind | Existing match | Action |
| ------ | ------ | ---- | -------------- | ------ |
| {source path} | {target path \| -} | {decision-tree folder}{ (hint overruled: <reason>)} | {none \| covering path} | {created \| updated \| conflict \| rejected - <reason> \| skipped - <reason>} |

- **Per folder:** {folder}: {n} source / {n} placed / {n} rejected / {n} skipped; ...
- **Split candidates:** {target path: kind - section | none}
- **Dangling in source:** {source path -> missing target | none}
- **Broken by move:** {source path -> old target, now at new path | none}
- **Conflicts:** {the ingest ## Conflicts entries | none}

## Setup required                                  {instead of the blocks above, when Step 2 stops}

- {check that failed} - {what was found}

```
{commands in order}
```
````

`Surfaces` counts rows across every inventory; `new` and `gone` compare to the rows Step 6 read before writing, both `0` on `init`. On `import` the sync lines that no step of the command ran read `n/a`. The import table holds one row per source `*.md` outside the skip list, in walk order.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: every preflight row checked before any write; occupied generated paths stopped the run; `stack-detect`'s table applied per repo; `Tracing`, `Errors`, branches, scopes, and MCP reachability read; `new` repos identified; `Setup required` emitted with exact commands on a stop and nothing written; resume pass honoured
- [ ] Step 3: scaffold written with the carried `CLAUDE.md` sections, `sha` unset on `init` only, every absent seed path created and every present one untouched, `seeded:` listed, `in_progress` set
- [ ] Step 4: fetch run per repo with the braced ref, bump applied only under the guard, gitlink staged after a bump, failures reported without advancing `sha`, skipped entirely under `--no-fetch`
- [ ] Step 5: stale marks and unmapped rows written before any regeneration, within scope; `new` repos skipped (`update`)
- [ ] Step 6: prior inventory rows read; discovery run backend repos first with scope and the other repos supplied; inventories written with the `Capability` column, `infrastructure` never proposed; capability table written once, after the last repo; placed rows removed; external callers collected; orphans marked
- [ ] Step 7: one card per non-infrastructure trigger row or per stale or missing card, within `--capabilities` and `--max-flows`, `### Untraced` written for the rest; every trace input passed; runtime evidence fetched only from reachable tools and applied through corroborate mode, the Step 2 reason on every Runtime line otherwise; reverse index rebuilt; flow Notes appended
- [ ] Step 8: every curated write was one `domain-kb-ingest` call reported with its `Signal check` and `Kind`; Distil candidates cited at the tip and trivia dropped, a quiet Distil stated; import walked every folder with the skip list applied, `document` mode used, `imported_from` as typed, no split of a curated doc, links rewritten once after the last file, both link lists separated; the per-folder line names every source folder walked
- [ ] Step 9: `priority` and `ranked_by` on every card by tier, then in-degree, incidents, commits
- [ ] Step 10: ledger with `Kind` and `Doc`, chains, register with severity, category, ids and converted analysis rows, recent risk, detection gaps with `Signal`, playbook, contracts written; inventories' `Used by flows` by whole-surface match; card marks updated; `flow to trace:` entries whose surface has a card all resolved (count them; any left is a fail); rule Notes appended
- [ ] Step 11: ledger `Doc` and non-code rows, register `Doc`, contract `Doc`, playbook `Past incidents`, card `doc:` and `consumer:` entries filled from the curated layer in that order; consumers without a doc listed; no curated file written
- [ ] Step 12: every curated citation read at the tip; `moved` and `gone` rows in `## Citation drift`; no doc edited; import link lists re-checked
- [ ] Step 13: capability files only for capabilities with a card; overview and root files regenerated with the final tables, the tips this run records, and `Branch` and `Scope` carried; `## Curated` rebuilt; `.gitkeep` removed where a doc exists
- [ ] Step 14: orphans with empty Notes deleted on `rebuild`; `sync-state.json` written last with `in_progress` cleared; `_index/last-sync.md` written; every count read back from files

## Avoid

- Writing any file before the preflight passes, or running a git write other than the Step 4 fetch, guarded bump, and gitlink stage
- Advancing a repo's recorded `sha` before the Record pass, or after a failed fetch
- Regenerating a card without carrying its `## Notes`, aliases, priority, and ids
- Inventing a repository URL for the `Setup required` block
- Fetching runtime evidence before the card exists, or from a tool the preflight found unreachable
- Writing, moving, or copying a curated file by any means other than a `domain-kb-ingest` call, or reading one into `## Notes`
