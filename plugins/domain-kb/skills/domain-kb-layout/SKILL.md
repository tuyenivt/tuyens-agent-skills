---
name: domain-kb-layout
description: Define the domain knowledge-base layout: folders, write modes, ids, frontmatter, flow card template, ATLAS and index shapes, sync state.
metadata:
  category: domain
  tags: [domain, knowledge-base, layout, flow-card, contract]
user-invocable: false
---

# Domain Knowledge-Base Layout

The single source of truth for where every artifact of a domain knowledge base lives, what shape it has, and who may rewrite it. `task-domain-sync` writes to it; `task-domain-explain` and `task-domain-ask` read from it.

## When to Use

- `task-domain-sync` creating (`init`), refreshing (`update`), or regenerating (`rebuild`) the knowledge base
- `task-domain-explain` and `task-domain-ask` locating a card, the atlas, the ledger, or the reverse index
- Invoked standalone: verify an existing knowledge base against this contract, write nothing, and emit the Output Format block

## Rules

- **Root is the project the plugin runs in.** The knowledge base lives at the project root; service repositories live under `repos/<repo>/` (submodules or plain clones). Nothing under `repos/` is written, counted, or verified. The repo set is the directories under `repos/`. A knowledge base is synced when `_index/sync-state.json` records a `sha` for at least one repo; `init` refuses on a synced root and names `rebuild`.
- **Every path has its write modes** (table below). `regenerate` rewrites the whole file and carries the protected parts; `mark` edits these fields in place and nothing else: frontmatter `status` on any generated file, a card's `## Changed since`, `priority`, `ranked_by`, the `Id` numbers that replace `R-new` and `D-new`, a Rules row's `Rationale` and `Confidence` when the chain strengthens them and its `Quirk` from every chain walk, a `flow to trace:` Related entry replaced by `<capability>/<flow>` once that card exists, Contract `Callers`, the corroboration fields (Runtime lines, `Exercised in traces` cells, `verified_by_trace`, Contract `Callers`, a `(from observability tool)` monitor line, `deploy` rows in Recent changes, a `trace differs` Debt row), and a line appended to a generated file's `## Notes`; a capability's Flows `Priority` and `Status` cells; and ATLAS Status cells, counts line and `## Unmapped changes` rows; `index` rewrites a JSON file whole; `never` touches nothing. A Markdown file at a generated path is generated when its frontmatter carries `generated: domain-sync`; a file at a generated path without that key, with or without other frontmatter, is adopted on the next write to that path: regenerated with frontmatter, its prior body carried verbatim under `## Notes`. Every other Markdown file is hand-written and never modified or deleted, wherever it sits.
- **Carried on regenerate:** the `## Notes` section, which is always the last section and runs to end of file; `## Audience` and `## Capabilities` in `AGENTS.md`; `## Unmapped changes` in `ATLAS.md`; the frontmatter `aliases` list (union of old and new), `priority`, and every `R-n` or `D-n` id whose row persists. Every regenerated file ends with `## Notes`, emitted empty when there is nothing to carry.
- **Orphans.** A generated file whose source vanished (a flow whose trigger surface the Discover pass no longer finds, a caller no longer seen, a repo directory removed) gets `status: orphaned`, its body frozen and its reverse-index entries removed; `update` leaves it alone, `rebuild` deletes it only when its `## Notes` is empty. `orphaned` outranks `stale`.
- **Ids are stable.** An id is kebab-case, assigned at creation, never renamed by sync; `caller-` is prefixed to a caller contract's file and id when the name collides with a repo or capability. A flow is re-identified by its Trigger `Surface`, then by the majority of its reverse-index files (ties keep the older card); a changed business name becomes an alias. A rule or debt row keeps its id while its enforcement site (file plus rule text) persists, then by rule text alone; new ids take the next number after the highest in use. Flows are unique within a capability and referenced everywhere as `<capability>/<flow>`.
- **Empty is explicit.** A slot with no value reads `none - <evidence>`, `unknown - not discoverable from the repos`, or `unavailable - <reason>`; a slot whose enum lists `none` reads `none`. A table with no rows keeps its header and one row whose first cell reads `none - <evidence>` and whose other cells are empty; a list section with no items reads `- none - <evidence>`. A conditional section (`## Contract`) exists only when its condition holds and is never drift when absent.
- **Nothing invented.** Monitors, dashboards, job names, hostnames and channels are cited from a file path or config key, or from the observability tool's own list marked `(from observability tool)`, or written `unknown - not discoverable from the repos`.
- **English, with one project-level override.** Generated text is English. When `AGENTS.md` `## Audience` carries `Language:` with an ISO 639-1 code other than `en`, the `**Story:**` line of each flow card carries a second sentence in that language, and `task-domain-ask` answers stakeholder-shaped inputs in it as well as English. Nothing else is translated.
- **Never commit.** Files are written to the working tree; the user versions them.

## Patterns

### Layout and write modes

```
AGENTS.md                      regenerate         how agents use this KB; Repos, Observability, Audience
index.md                       regenerate         agent entry: what is where, by artifact type
ATLAS.md                       regenerate, mark   human entry: learning path, capabilities, flows, stale marks
overview/domain-model.md       regenerate         actors, core entities, value flow, external systems
overview/state-machines.md     regenerate         lifecycle entities: transition graph and the guard on each edge
overview/glossary.md           regenerate         Term | Also called | Code identifier | Flows
overview/not-supported.md      regenerate         what the system deliberately does not do, with evidence
capabilities/<capability>/capability.md        regenerate, mark   owning services, flows, monitors, top risks
capabilities/<capability>/flows/<flow>.md      regenerate, mark   one flow card per end-to-end business flow
rules/ledger.md                regenerate         every rule with site, flows, rationale, confidence, quirk flag
rules/unknown-rationale.md     regenerate         the ledger rows whose confidence is unknown
rules/chains.md                regenerate         one `## R-n` block per rule: the evidence chain behind its rationale
playbook/by-symptom.md         regenerate         symptom -> flows -> first checks -> past incidents
contracts/<caller>.md          regenerate         per integrating caller: surfaces used, sharp edges
debt/register.md               regenerate         hotspots, coupling, SPOFs: trade-off, cost, fix, detection
debt/detection-gaps.md         regenerate         flows without a monitor that fires before a user notices
debt/recent-risk.md            regenerate         flows with 3 or more commits in the window
specs/<repo>.md                regenerate         surface inventory per repo, each trigger row with its capability, each row with Used by flows
_index/file-to-flow.json       index              source file -> flow ids, rebuilt from the `files` list of every non-orphaned card
_index/sync-state.json         index              repo -> synced SHA, stack, database, surface count; window; in_progress
adr/  incidents/  patterns/    never              hand-written; init creates each absent folder with a .gitkeep
repos/<repo>/                  never              the service repositories
```

`patterns/` holds the conventions agents follow when they implement or review in these repos; the plugin never writes it.

### Sync passes

Every command runs these passes in order. A command sets `in_progress` in `sync-state.json` to `{command}:{pass}` for the pass it is running and the Record pass clears it; a run started while `in_progress` is set resumes that command at that pass instead of starting over.

1. **Scaffold** (`init`, `rebuild`): root files with empty tables, `overview/` stubs, `.gitkeep` folders, `sync-state.json` with every repo's stack note and database from `stack-detect`, `window`, and `sha` unset on `init` (kept on `rebuild`). `update` skips this pass.
2. **Mark** (`update` only): the Stale marking recipe. The recorded `sha` is not advanced here.
3. **Discover**: `domain-surface-discovery` runs over every repo on every command and writes `specs/<repo>.md` where rows changed, carrying `Used by flows` for rows that persist, and proposes the capability set (`AGENTS.md` `## Capabilities` first, then one capability per business area the handler modules name), each trigger assigned to one. A discovered surface that an ATLAS `## Unmapped changes` file registers removes that row. A card whose trigger surface is no longer discovered is marked `orphaned`.
4. **Trace**: one flow card per discovered trigger (`init`, `rebuild`), or per stale or missing card in priority order (`update`), each passed its capability from the Discover set; a `proposed: <name>` the trace returns is added to the set. Rule and debt rows are written as `R-new` and `D-new`; `file-to-flow.json` is rebuilt from the `files` list of every non-orphaned card.
5. **Rank**: `priority` and `ranked_by` on every card (a `mark`) by revenue path, then commits in the window, then incidents naming the flow; flows none of the three reaches rank after them in trigger order, `ranked_by: unranked`.
6. **Analyse**: `rules/` (ledger, unknown-rationale, chains via `domain-rationale-chain`), `playbook/`, `contracts/` (callers of each surface, from the cards' hop lists and Contract sections), `debt/` (`Location` from each card's Debt row, `Fix` and `Detection` written here as the change and the monitor that would close it); then `specs/` regenerated with `Used by flows`, and in the cards (a `mark`) `R-new` / `D-new` replaced by numbers, `flow to trace:` entries replaced by `<capability>/<flow>` where the card now exists, and Contract `Callers` filled from `contracts/`.
7. **Finalise**: `capability.md`, `overview/`, and the root files regenerate with the final tables.
8. **Record**: `sync-state.json` rewritten whole: `synced` today, `window`, every repo's `sha` at `HEAD` (the same `HEAD` the cards' `sources` cite), stack note, database, `surfaces` from its spec, `in_progress` cleared.

A repo whose recorded `sha` is no longer in its history (force-push, shallow clone, submodule reset) stops `update` before Mark with `base SHA not in history - run rebuild`.

### Ids and references

| File                        | Id                                                                     | Frontmatter `id`             |
| --------------------------- | ---------------------------------------------------------------------- | ---------------------------- |
| root files                  | `agents`, `index`, `atlas`                                             | as named                     |
| overview files              | `domain-model`, `state-machines`, `glossary`, `not-supported`          | as named                     |
| capability                  | directory name                                                         | `<capability>`               |
| flow                        | file name without `.md`                                                | `<flow>`, plus `capability:` |
| caller contract             | file name without `.md`                                                | as named                     |
| ledger, playbook, debt, specs | file name without `.md`; specs as `spec-<repo>`                      | as named                     |
| rule row, debt row          | `R-<n>`, `D-<n>`                                                       | column `Id`                  |

The examples in this file group the refund flow under `payments`, a grouping a project sets through `## Capabilities`; the discovery rule alone would name it by its handler module. Every `Flows` column, every reverse-index value, every ATLAS row, and every flow entry under `Related` that has a card uses `<capability>/<flow>` (a hand-off with no card yet reads `flow to trace: <kind>: <surface>`); ATLAS links it to `capabilities/<capability>/flows/<flow>.md`. Every `file:line` is root-relative under `repos/` (`repos/orders/app/services/refund_service.rb:18`); line numbers refresh only when the file is regenerated. A trigger cell reads `<kind>: <surface>`. A `Surface` slot ends with `- file:line`.

### Generated-file frontmatter

```yaml
---
generated: domain-sync
id: order-refund
status: current                # current | stale | orphaned
synced: 2026-09-26
sources:                       # repo@sha, first 7 characters of `git rev-parse HEAD` when the file was written
  - orders@3f2a1c9
  - payments@b77e0d2
aliases: []                    # business names this artifact was known by
---
```

Flow cards append `capability: <capability>`, `priority: <integer>` (rank across all flows, 1 first to learn, `0` until ranked; unranked sorts last), `ranked_by: {revenue path | most changed | most incidents | unranked}`, `verified_by_trace: <true | false>` (`true` only when a runtime trace matched the hop list hop for hop), and `files:`, the root-relative list of every repo file the card cites, which is the card's contribution to `file-to-flow.json`. `status: stale` is set only on flow cards.

### AGENTS.md

```markdown
# {Domain} knowledge base

{One paragraph: what the domain does, which repos it spans, and that agents read `index.md` first and `_index/file-to-flow.json` to map a file or stack trace to a flow.}

## Repos

| Repo | Path | Stack | Database | Synced SHA |
| ---- | ---- | ----- | -------- | ---------- |

## Observability

- **Tool:** {tool name | none}
- **Services:** {service names as the tracing config declares them, or unknown - not discoverable from the repos}

## Audience

- **Language:** en
- **Readers:** the tech lead

## Capabilities

| Capability | Triggers |
| ---------- | -------- |

## Notes
```

`## Repos` mirrors `sync-state.json`, which is authoritative. `Tool` and `Services` come from the tracing or metrics initialisation in the repos. `## Audience` is written by scaffold with the defaults shown and carried verbatim afterwards; the user edits it. `## Capabilities` is written once by the first Discover pass with its proposals (one row per capability, `Triggers` holding surface patterns such as `POST /api/orders/*`) and carried verbatim afterwards; a trigger matching a row's pattern takes that capability before any other rule, so the user steers grouping by editing the table.

### index.md

```markdown
# Index

| Need | Read |
| ---- | ---- |
| A file or stack trace -> which business flow | `_index/file-to-flow.json`, then the card |
| Why a rule exists | `rules/ledger.md`, then the card its `Flows` cell names |
| An alert or symptom -> where to look | `playbook/by-symptom.md` |
| What an integrating caller uses | `contracts/<caller>.md` |
| What is fragile and why | `debt/register.md` |

## Files

- `overview/domain-model.md` - {one line}
- `capabilities/payments/flows/order-refund.md` - {story sentence}

## Notes
```

The Need table is fixed text. `## Files` lists every generated Markdown file except the root files, one line each, in layout order and then by path; a card's line is its Story sentence, any other file's line is its purpose from the layout table; hand-written folders get one line each naming the folder.

### ATLAS.md

```markdown
# Atlas

- **Synced:** {date}
- **Repos:** {n}
- **Flows:** {n} ({n} stale, {n} orphaned)

## Learning path

1. `overview/domain-model.md`, then `overview/state-machines.md`, then `overview/glossary.md`
2. {capability} ({revenue path | most changed | most incidents | unranked}) - flows in the order below
3. ...

## Capabilities

### {n}. {Capability}

| # | Flow | Trigger | Status | Read before |
| - | ---- | ------- | ------ | ----------- |
| 1 | [payments/order-refund](capabilities/payments/flows/order-refund.md) | ui screen: /orders/[id]/refund | current | payments/order-capture |

## Unmapped changes

| File | Commit | Date |
| ---- | ------ | ---- |

## Notes
```

`Flows` counts every card, orphaned included. Capabilities are ordered by their best flow priority, and the learning-path reason is that flow's `ranked_by`. `#` restarts per capability and is the reading order inside it. `Read before` names the flow whose state this one depends on, `none` when there is none.

### Flow card

```markdown
# {Flow name}

**Story:** {one sentence: actors and business outcome, no service or endpoint names}

## Trigger

- **Kind:** {ui screen | public api | internal api | schedule | webhook in | message}
- **Surface:** {route, screen path, job, or topic as the code registers it} - {file:line}
- **Actor:** {who or what initiates}
- **Preconditions:** {entity state and permissions required}{ (no producer in repos)}

## Sequence

{Mermaid sequenceDiagram: one participant per service or external system, each arrow labelled with the surface it crosses}

1. {surface} - {file:line}{ (unverified)}{ (external - not in repos)}
2. {surface} - {file:line}
   - branch a: {surface} - {file:line}
   - branch b: {surface} - {file:line}

## State changes

| Entity | From | To | Guard | Enforced at |
| ------ | ---- | -- | ----- | ----------- |

## Side effects

| Kind | Target | When | Enforced at |
| ---- | ------ | ---- | ----------- |

## Rules

| Id | Rule | Enforced at | Rationale | Confidence | Quirk |
| -- | ---- | ----------- | --------- | ---------- | ----- |

## Edge branches

| Branch | Guard | Enforced at | Exercised in traces ({window}d) |
| ------ | ----- | ----------- | ------------------------------- |

## Failure modes

| What breaks | User sees | Detected by | First check |
| ----------- | --------- | ----------- | ----------- |

## Where to watch

- **Monitors:** {names - file:line, or name (from observability tool)}
- **Dashboards:** {names - file:line}
- **Log query:** {query built from the log message strings on the path}
- **Trace search:** {service and resource names}

## Contract {only when Kind is public api or webhook in}

- **Request:** {shape and required fields}
- **Response:** {shape}
- **Errors:** {codes and when}
- **Idempotency:** {key and window}
- **Callers:** {from contracts/ when it exists, then traces marked (external - from traces)}

## Runtime

- **Callers:** {services and external callers seen in traces}
- **Volume:** {requests per day over the window}
- **Latency p50 / p95:** {ms / ms}
- **Error rate:** {percent}

## Recent changes

| Date | Change | Source | Files |
| ---- | ------ | ------ | ----- |

## Debt

- {D-n: class: finding - file:line - trade-off made - cost today}

## How to see it

- **Screens:** {routes or screen paths involved}
- **Job:** {class or schedule name}
- **Log lines:** {messages to expect, in order}
- **Tables to inspect:** {tables and the rows or columns that change}

## Related

- {flows as <capability>/<flow> or flow to trace: <kind>: <surface>, rules as R-n, incidents and ADRs by path}

## Notes
```

The second Story sentence, in the Audience language, follows the first on the same line when `Language:` is not `en`. Enums: `Kind` as listed; Side effects `Kind` is `{webhook out | event | email | third-party call | file}`; `From` is `new` for a row creation and `To` is `deleted` for a row deletion; `Confidence` is `{documented | inferred | unknown}`; `Quirk` is `{yes | no}`; `Exercised in traces` is `{yes | no | unavailable}`; `Source` in Recent changes is a commit short SHA, a PR number, or `deploy`. A Debt row's `class` is one of `swallowed error`, `write outside transaction`, `no monitor`, `missing containment`, `trace differs`, `unreachable precondition`, `hotspot`, `single point of knowledge`, `coupling`. Markers: `(unverified)` on a hop the code implies but cannot pin; `(external - not in repos)` on a hop that leaves the repos; `(external - from traces)` on a caller only a trace names; `(from observability tool)` on a monitor the tool lists that no file defines; `(no producer in repos)` on a precondition no code in scope produces; a Side effects `Target` outside the repos reads `<name> (external - not in repos)` or `consumer not in repos`. Every `Enforced at` is `file:line`. Recent changes covers the window; `## Changed since` covers commits since the previously recorded SHA, exists only on a stale card, and accumulates across updates until the card regenerates. The Runtime block reads `unavailable - <reason>` on every line when traces cannot be fetched. `domain-flow-trace` fills the card, `files` included; the sync passes above set `Id` numbers and `priority`.

### capability.md

```markdown
# {Capability}

**Purpose:** {one sentence}

## Services

| Service | Repo | Role in this capability |
| ------- | ---- | ----------------------- |

## Flows

| Flow | Trigger | Priority | Status |
| ---- | ------- | -------- | ------ |

## Monitors

- {name - file:line}

## Top risks

1. {risk - evidence - flow}

## Notes
```

`## Services` lists every repo a flow of the capability touches, frontends included. `## Top risks` holds at most three `debt/register.md` rows whose `Flows` belong to the capability, highest cost first.

### Overview files

Each has an H1 and these sections, in order, then `## Notes`.

- `domain-model.md`: `## Actors` (`| Actor | Kind | Does |`, kind `{person | system}`), `## Entities` (`| Entity | Owned by | Lifecycle | Key relations |`), `## Value flow` (one paragraph and a Mermaid flowchart of money or work moving between actors and services), `## External systems` (`| System | Direction | Used by flows | Integration code |`, direction `{in | out | both}`).
- `state-machines.md`: `## {Entity}` per lifecycle entity, each with a Mermaid stateDiagram and `| From | To | Guard | Enforced at | Flow |`.
- `glossary.md`: `## Terms` with `| Term | Also called | Code identifier | Flows |`; `Also called` holds every alias found in code, docs and Notes, in whatever language it appears.
- `not-supported.md`: `## Not supported` with `- {statement} - {evidence: a hardcoded value, an explicit rejection, an absent branch}`.

### Ledgers, playbook, contracts, debt, specs

Each has an H1, the sections named here, then `## Notes`.

- `rules/ledger.md`: `## Rules` with `| Id | Rule | Flows | Enforced at | Rationale | Confidence | Quirk | Last touched |`; `Last touched` is the author and date of the last commit to the enforcing lines. `unknown-rationale.md`: `## Unknown` with the same columns, only the rows whose confidence is `unknown`. `chains.md`: `## R-n` per rule holding the block `domain-rationale-chain` emits.
- `playbook/by-symptom.md`: `## Symptoms` with `| Symptom | Flows | First checks | Past incidents |`; past incidents cite `incidents/` files by path.
- `contracts/<caller>.md`: `- **Kind:** {team | external system | ui app}`, then `## Surfaces used` with `| Surface | Flow | Sharp edges |`.
- `debt/register.md`: `## Register` with `| Id | Location | Signal | Trade-off made | Cost today | Fix | Detection | Flows |`. `detection-gaps.md`: `## Gaps` with `| Flow | Priority | Monitor | Gap |`. `recent-risk.md`: `## Recent risk` with `| Flow | Commits ({window}d) | Monitor | Risk |`, one row per flow with 3 or more commits in the window.
- `specs/<repo>.md`: `## Surfaces` with `| Kind | Surface | Enforced at | Capability | Used by flows |`, `Capability` filled for trigger kinds and `-` otherwise; `Kind` is a trigger kind (`ui screen`, `public api`, `internal api`, `schedule`, `webhook in`, `message`) or `webhook out`, `event out`, `outbound client`, `table`. Real rows, not the `none` placeholder, are the repo's `surfaces` count.

### Indexes

`_index/file-to-flow.json`, keyed by root-relative path, rebuilt whole from the `files` list of every non-orphaned card; a key with no flows is omitted:

```json
{ "repos/orders/app/services/refund_service.rb": ["payments/order-refund"] }
```

`_index/sync-state.json`, the authoritative sync record, written by the Record pass; `sha` is the full `git rev-parse HEAD` at the last completed sync, `window` the day count both windows use, `in_progress` the `{command}:{pass}` a running command is in or `null`:

```json
{
  "version": 1,
  "synced": "2026-09-26",
  "window": 30,
  "in_progress": null,
  "repos": {
    "orders": { "path": "repos/orders", "sha": "3f2a1c9e0b7d4c2a91f6e8d5b3a7c1e2f4d6a8b0", "stack": "Ruby / Rails 7.2", "database": "PostgreSQL", "surfaces": 42 }
  }
}
```

### Stale marking

The Mark pass diffs each repo from its recorded `sha` to `HEAD`. A changed file the reverse index maps marks every flow it maps to: the card's `status` becomes `stale` and a `## Changed since` section is inserted before `## Notes` (or extended when present) with `| Date | Commit | Files |`, one row per commit in the diff touching the flow's mapped files, ascending. The mark propagates to the capability's Flows `Status`, the ATLAS row, and the ATLAS counts line. A changed file the index does not map is appended to ATLAS `## Unmapped changes` until surface discovery places it. Regenerating the card restores `current`, removes `## Changed since`, and refreshes line numbers. A `## Changed since` section on a stale card is not drift. The recorded `sha` advances only in the Record pass, so an interrupted `update` diffs from the same base next time.

## Output Format

Emitted by every sync command and by standalone verification.

```
- **Layout:** {created | updated | verified | drifted}
- **Root:** {absolute path}
- **Files:** {n} written, {n} verified, {n} hand-written skipped
- **Drift:**                                              {only when drifted}
  - {path} - {missing | missing folder | adoptable | key missing: <key> | sections missing: <a>, <b> | index invalid | status mismatch: <file> vs <file> | id renamed: <old> -> <new>}
```

`created` is `init` and `rebuild`; `updated` is `update`, counting the files it wrote or marked, JSON indexes included; `verified` and `drifted` are standalone results. `written` counts files created, regenerated, or marked; `verified` counts generated files read and found conforming; `hand-written skipped` counts hand-written Markdown files outside `repos/`. Standalone verification writes nothing, so `written` is `0`, and the drift list is what the next `rebuild` corrects. `adoptable` is a frontmatter-less file at a generated path; `id renamed` is a frontmatter `id` that differs from the path-derived id and is resolved by restoring the path-derived id and recording the other as an alias.

## Avoid

- Treating `ATLAS.md` as the agent entry point or `index.md` as the human one
- Adding a `## Notes` section or frontmatter to the JSON indexes
- Writing a flow reference in any form other than `<capability>/<flow>`
- Advancing a repo's recorded `sha` anywhere but the Record pass
