---
name: task-domain-sync
description: Build or refresh a domain knowledge base from service repos: preflight, discover surfaces, trace flows, rank, analyse rules and debt, record.
metadata:
  category: domain
  tags: [domain, knowledge-base, sync, init, update, rebuild, flows, surfaces]
  type: workflow
user-invocable: true
---

# Domain Sync

Builds the knowledge base `domain-kb-layout` defines from the service repositories under `repos/`, or refreshes it from the commits since the last run. Runs at the knowledge-base project root, writes files as each pass completes, and never commits.

## When to Use

- `init`: a fresh root with repos under `repos/` and no recorded sync
- `update`: a synced root after new commits in any repo, or after a repo was added under `repos/`
- `rebuild`: a synced root whose layout drifted or whose contract changed; regenerates every generated file, keeping `## Notes`, `## Audience`, `## Capabilities`, aliases, priorities and ids

**Not for:** reading the knowledge base (`task-domain-explain`) or answering a question from it (`task-domain-ask`).

## Inputs

| Input   | Required | Notes                                                                                                                              |
| ------- | -------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Command | no       | `init`, `update`, or `rebuild`; default `init` when `_index/sync-state.json` is absent or records no `sha`, `update` otherwise      |
| Window  | no       | Days for recent changes, ranking, and runtime corroboration; default `window` in `_index/sync-state.json`, else 30; used by every step and recorded at the end |
| Notes   | no       | Text the user pastes for a named flow, rule, or capability; appended to that file's `## Notes` once the file exists in this run     |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Preflight

Read only; nothing is written until every row passes.

| Check                                                          | Pass                                                       | Fail                                                                                       |
| -------------------------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Root is writable                                               | yes                                                        | stop                                                                                       |
| `repos/` exists with at least one subdirectory                 | yes                                                        | `Setup required`, stop                                                                     |
| Each `repos/<repo>/` resolves `git rev-parse HEAD`             | sha                                                        | an added but uninitialised submodule is named with its fix command; a non-git directory as `not a git checkout` |
| `.gitmodules`, when present, agrees with the `repos/` directories | consistent                                              | the missing or extra repo is named                                                         |
| Command gate                                                   | `init` with no recorded `sha`; `update` with one; `rebuild` with `sync-state.json` present | `init` on a synced root names `rebuild`; `update` on an unsynced root names `init` |
| Each repo with a recorded `sha` still has it in history (`update`) | yes                                                    | `base SHA not in history - run rebuild`, stop                                              |
| `in_progress` in `sync-state.json`                             | null, or `{command}:{pass}` to resume                      | resume that command at that pass after this step, reading its inputs from the files earlier passes wrote; the Command input is ignored |

Use skill: `stack-detect` for its marker-file table, and apply that table to each `repos/<repo>/` directory in turn; its single-root detection and conversation cache are not used, since the knowledge-base root has no stack of its own. `Language` and `Framework` form the repo's stack note, `Database` its database, `unknown` accepted. Read each repo's tracing or metrics initialisation for the observability tool and service name; an existing `AGENTS.md` `## Observability` wins when present. A repo with no recorded `sha` on `update` is `new`: it is discovered and traced in full below and recorded at the end. These in-run values feed every later step and are written only in Steps 3 and 10; the `stack-detect` block itself is never emitted.

On any fail the workflow emits the `Setup required` block with the commands in order, reading a URL from `.gitmodules` when it has one and leaving `<url>` otherwise, and stops. It never runs a git write itself.

### Step 3 - Scaffold (`init`, `rebuild`)

Per the layout's Scaffold pass: root files with empty tables, `overview/` stubs, `.gitkeep` in each absent hand-written folder, `AGENTS.md` `## Observability` from Step 2, `sync-state.json` with stack notes, databases, `window`, and on `init` every `sha` unset (`rebuild` keeps the recorded values). A frontmatter-less file at a root path is adopted. `in_progress` is set to `scaffold` here and advanced at every pass below.

### Step 4 - Mark (`update`)

Per the layout's Stale marking: diff each recorded repo from its `sha` to `HEAD`, mark every card a changed mapped file reaches, propagate to capability and ATLAS, append unmapped files to ATLAS `## Unmapped changes`. A `new` repo has no diff and skips this step.

### Step 5 - Discover

Read every existing spec's rows first, for the `new` and `gone` counts. Use skill: `domain-surface-discovery` once per repo, backend repos first and any repo that serves screens last, passing the other repos with the specs already written this run, the existing spec, the capability table, and this repo's unmapped rows. Write each spec whose rows changed; each trigger row carries its capability in the spec's `Capability` column, which is the Discover set every later step and any resume reads. When `AGENTS.md` `## Capabilities` is empty, write it from every repo's proposals after the last repo. Remove each ATLAS `## Unmapped changes` row the atomic reports under `Placed`. Mark `orphaned` every card whose trigger surface no repo discovered and every spec whose repo directory is gone.

### Step 6 - Trace

Use skill: `domain-flow-trace` once per trigger row of kind `ui screen`, `public api`, `webhook in`, `schedule`, or `message` (`init`, `rebuild`, and a `new` repo), `internal api` rows being hops inside those flows, or once per stale or missing card in priority order (`update`; a trigger row of those kinds with no card is a missing card), passing the row's capability, every repo with its stack note, the KB root including `AGENTS.md`, the surface inventory, the Window, and the Audience language. Write each card as it completes in `regenerate` mode; a `proposed: <name>` capability is written to the spec row before its card is written, and to `## Capabilities` only while that table is still empty. Then, when Step 2 found an observability tool, Use skill: `domain-runtime-evidence` for the card's trigger surface (the first backend hop for a ui screen) with the card's Edge branches, and Use skill: `domain-flow-trace` in its corroborate mode with the card and the blocks, which marks the card's Runtime lines, `Exercised in traces` cells, `verified_by_trace`, Contract `Callers`, Where to watch monitors, Recent changes deploy rows, and a `trace differs` Debt row. Rebuild `_index/file-to-flow.json` from every non-orphaned card's `files` list after the last card. Pasted Notes for a flow are appended here.

### Step 7 - Rank

Per the layout's Rank pass: `priority` and `ranked_by` on every card, revenue path first (a flow whose State changes or Side effects move money or grant access), then commits in the Window (distinct commits from read-only `git log --since` over the card's `files`), then incidents naming the flow, then `unranked`; inside a tier, more commits in the Window first, then spec row order.

### Step 8 - Analyse

- Use skill: `domain-rationale-chain` once over every card's Rules rows; write `rules/ledger.md`, `rules/unknown-rationale.md`, `rules/chains.md`, and mark each card's Rules row. Pasted Notes for a rule are appended to the ledger here.
- Use skill: `domain-behavioral-analysis` over every repo with the Window, the reverse index, and the cards' Monitors lines; write `debt/recent-risk.md` from its Recent risk table and convert its hotspot, single-point, and coupling rows per its Register rows recipe.
- `debt/register.md` takes every card Debt row and every converted analysis row, with `Fix` as the change that removes the finding and `Detection` as the monitor or review gate that would catch it (`none` when there is none); rows with the same class and `Location` across cards merge into one row listing every flow; ids `D-<n>` kept by `Location` plus the class word of `Signal` where a prior row matches and assigned in that order otherwise; `debt/detection-gaps.md` lists every flow whose Monitors line starts `none` or `unknown`, by priority.
- `playbook/by-symptom.md` takes one row per distinct `User sees` across the cards' Failure modes, with its flows, first checks, and the `incidents/` files whose text names that symptom or flow.
- `contracts/<caller>.md` takes one file per caller: every repo whose hop list crosses into another repo's `internal api` surface is a caller of that surface, and every `(external - from traces)` caller in a card's Contract is a caller of its surface; each file lists the surfaces used and the sharp edges the cards' Rules and Edge branches record on them. A caller file no card names any longer is marked `orphaned`.
- Regenerate every spec with `Used by flows` filled from the cards: a row is used by every card whose Trigger Surface or hop list names its surface string, and `none - no flow cites it` otherwise; mark each card's `R-new` and `D-new` ids, `flow to trace:` entries whose card now exists, and Contract `Callers` from `contracts/`.

### Step 9 - Finalise

Regenerate `capability.md` per capability from its cards (pasted Notes for a capability appended here); `overview/domain-model.md` (actors from Triggers, entities from State changes, external systems from `(external - not in repos)` targets, value flow from the flows that move money); `overview/state-machines.md` from every State changes row grouped by entity; `overview/glossary.md` from entity, status, and capability names with the code identifiers the cards cite; `overview/not-supported.md` from rules and error branches that reject a business case outright; then `index.md`, `ATLAS.md`, and `AGENTS.md` `## Repos` with the `HEAD` SHAs this run records, and `## Observability` from Step 2.

### Step 10 - Record

On `rebuild`, delete every orphaned generated file whose `## Notes` is empty. Write `sync-state.json` whole per the layout's Record pass, clear `in_progress`, and emit the Output Format with every count read back from the files written.

## Output Format

````
## Domain sync

- **Command:** {init | update | rebuild}
- **Root:** {absolute path}
- **Repos:** {repo@sha, repo@sha}{ (new: repo)}
- **Window:** {n} days
- **Surfaces:** {n} ({n} new, {n} gone)
- **Capabilities:** {n} ({n} proposed this run)
- **Flows:** {n} cards ({n} traced this run, {n} stale, {n} orphaned)
- **Rules:** {n} ({n} documented, {n} inferred, {n} unknown)
- **Debt:** {n} rows ({n} hotspots, {n} single points of knowledge, {n} coupling)
- **Runtime evidence:** {used for {n} flows | unavailable - <reason>}
- **Unmapped changes:** {n}
- **Layout:** {created | updated}, {n} written, {n} hand-written skipped
- **Start with:** {<capability>/<flow> at priority 1, or `run update again to finish {n} stale cards`}

## Setup required                                  {instead of the block above, when Step 2 fails}

- {check that failed} - {what was found}

```
{commands in order}
```
````

`Surfaces` counts rows across every spec; `new` and `gone` compare to the rows Step 5 read before writing, both `0` on `init`.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: every preflight row checked before any write; `stack-detect`'s table applied per repo; observability tool and services read; `new` repos identified; `Setup required` emitted with exact commands on failure and nothing written; resume pass honoured
- [ ] Step 3: scaffold written with `## Observability`, `sha` unset on `init` only, and `in_progress` set (`init`, `rebuild`)
- [ ] Step 4: stale marks and unmapped rows written before any regeneration; `new` repos skipped (`update`)
- [ ] Step 5: prior spec rows read; discovery run backend repos first with the other repos and their specs supplied; specs written with the `Capability` column; capability table written once, after the last repo; placed rows removed; orphans marked for cards and specs
- [ ] Step 6: one card per trigger row or per stale or missing card, written as completed with every trace input passed; runtime evidence fetched after the trace with the card's branches and applied through the trace atomic's corroborate mode; reverse index rebuilt from `files`; flow Notes appended
- [ ] Step 7: `priority` and `ranked_by` on every card by the stated order
- [ ] Step 8: ledger, chains, register with ids and converted analysis rows, recent risk, detection gaps, playbook, contracts from hops and evidence written; specs' `Used by flows` from the cards' surfaces; card marks updated; rule Notes appended
- [ ] Step 9: capability, overview, and root files regenerated with the final tables and the SHAs this run records; capability Notes appended
- [ ] Step 10: orphans with empty Notes deleted on `rebuild`; `sync-state.json` written last with `in_progress` cleared; every count read back from files

## Avoid

- Writing any file before the preflight passes, or running a git write to fix a preflight failure
- Advancing a repo's recorded `sha` before the Record pass
- Regenerating a card without carrying its `## Notes`, aliases, priority, and ids
- Inventing a repository URL for the `Setup required` block
- Fetching runtime evidence before the card exists, or for a root with no observability tool
