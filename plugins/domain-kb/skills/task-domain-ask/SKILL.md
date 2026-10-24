---
name: task-domain-ask
description: "Answer from both layers of the domain knowledge base, fact-checked against the repos: question, ticket, alert or stack trace, pasted message."
metadata:
  category: domain
  tags: [domain, knowledge-base, ask, inquiry, ticket, alert, stack-trace, fact-check, precedence]
  type: workflow
user-invocable: true
---

# Domain Ask

Answers from the generated cards `task-domain-sync` built and the curated docs people wrote, checks every cited line against the repos, applies the project's precedence when the two layers disagree, and says `not found in docs` when neither supports an answer. The input's shape decides the answer's shape: a question gets an answer with evidence and unknowns; a ticket gets one block per item with the flows it touches and a size signal; an alert or stack trace gets the flow, first checks, and past incidents; a pasted message gets an answer and a note proposal; a bare name gets the lesson.

## When to Use

- A stakeholder, operator, or integrating team asks how or why the system behaves as it does
- A ticket or epic needs the flows it touches, the side effects, and a size signal before a meeting
- An alert, stack trace, or user report needs the flow it belongs to and what to check first
- A message you copied settles or contradicts something in the knowledge base

**Not for:** reading the atlas (`task-domain-explain`); building the knowledge base (`task-domain-sync`); turning a ticket into an implementation plan (`task-domain-solve`); driving a live incident to a root cause, which happens after this workflow has named the flow.

## Inputs

| Input | Required | Notes                                                                                                                          |
| ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Text or `--in <file>` | yes | The question, ticket text, alert, trace, message, or name, inline or read from the file; a bare tracker URL is not fetched |
| Save  | no       | The word `save` after a pasted message: the message is routed through `domain-kb-ingest`, or appended to a generated `## Notes` when ingest finds no folder for it; held while a sync is unfinished |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate and load the index

Use skill: `domain-kb-layout` for every path, section, and empty form named below; read its Rules and the Patterns sections Curated layer, Sync passes (its opening paragraph and Verify citations), Ids and references, Generated-file frontmatter, CLAUDE.md, index.md, ATLAS.md, Flow card, capability.md, Overview files, Ledger, playbook, contracts, debt, surfaces, and Indexes. A text that is only a tracker URL gets `paste the ticket text - URLs are not fetched` and the workflow stops; an `--in` file that does not exist stops with `no input file at <path>`. The root is the working directory. A non-null `in_progress` in `_index/sync-state.json` means a sync is running or was interrupted: the workflow continues on the files as they stand, carries the Sync line directly after the Shape line, and saves nothing; every `task-domain-sync` remedy this workflow emits (in a slot or a stop line; text copied from a card, a Monitors line or a `Detected by` cell included, stays as written) takes the layout's remedy form (`--resume` while `in_progress` names `init` or `update`, plain when it names `import`). The generated layer exists when `sync-state.json` records a `sha`; the curated layer exists when any curated folder holds a Markdown file. When neither exists, emit `no knowledge base here - run task-domain-sync init or import` (`no completed sync yet - {command}:{pass} unfinished; when no sync is running, run task-domain-sync --resume` when `in_progress` is set) and stop; when only one exists, the line after Shape and any Sync line says `- **Layers:** generated only` or `curated only` and the workflow continues with it. From the generated layer read `index.md`, `ATLAS.md` (with `## Citation drift`), `CLAUDE.md` (read whenever it exists, whichever layers exist) `## Audience` (`Language:` default `en`, also when `CLAUDE.md` is absent), `## Observability` (absent: `Tracing` and `Errors` are `none`), `## Precedence` (absent: the layout's scaffold text applies), `## Capabilities`, and its `## Notes`, every `ledger/rules.md` row whole (the chain's input for a non-code rule), the `## R-n` blocks of `ledger/chains.md`, the `overview/` files and every `capability.md`, the frontmatter `id`, `aliases`, and `freshness` of every card and `capability.md`, every card's `## Where to watch` Monitors, Error tracker, and Trace search lines and `## How to see it` Log lines, and, when `_index/file-to-flow.json` is absent, every card's frontmatter `files` list. Walk every curated folder for each doc's path, title, status, `superseded_by`, and tags (the walk, not `index.md` `## Curated`, which may lag). A generated file this workflow names that does not exist yet (`playbook/`, `contracts/`, `ledger/chains.md`, `overview/glossary.md`, `debt/register.md`, `_index/file-to-flow.json`) is skipped and its fallback below applies (`debt/register.md`: the Coupling slot reads `unknown - debt/register.md not generated yet` and Size counts no coupling row, its reason saying so; `_index/file-to-flow.json`: a frame is mapped through the cards' frontmatter `files` lists instead), or the slot it feeds reads `unknown - <file> not generated yet`. Nothing under `repos/` is read yet.

### Step 3 - Classify the input

Take the first matching row; the shape is the first line of the answer.

| Shape        | Signals                                                                                                                          |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| bare name    | The whole text is a `<capability>/<flow>` id, an `R-<n>` id as written, or a name `domain-flow-explain`'s resolution rule matches: ignoring case, a capability id or alias (the `capabilities/` directories plus the names ATLAS `### Untraced` and `CLAUDE.md` `## Capabilities` list) or a flow id or alias, loaded in Step 2 |
| alert        | A monitor name, an error-tracker capture string, or a log line loaded in Step 2; a stack trace (file paths with line numbers or frames); or a service name from `## Observability` with an error rate, latency, or count |
| ticket       | A title followed by asks, acceptance criteria, or numbered items                                                                  |
| pasted text  | Quoted or forwarded prose attributed to someone else (a name, a channel, a date) rather than addressed to this workflow            |
| question     | Anything else                                                                                                                    |

### Step 4 - Retrieve

Walk `index.md`'s Need table to the cards, ledger, playbook, contracts, and register rows the input names, and search the curated docs by title, tags, headings, and body for the surfaces, entities, constants, and terms the input names, in every `## Audience` language as the layout's Languages rule searches. A frame is mapped through `_index/file-to-flow.json` by the longest path suffix that matches a key across repos (matches of equal suffix length, in one repo or several: every match is kept); every flow the key lists is kept. A monitor, capture string, or log line maps to the cards whose Where to watch or How to see it carries it; a service metric maps to the cards whose Trace search names the service. A ticket item is retrieved by the surfaces, entities, and terms it names, matched against the inventories, the glossary, the cards' Story lines, and the curated `rules/`, `specs/`, `incidents/`, and `tech-debt/` docs. A bare name skips to Step 6.

### Step 5 - Fact-check and precedence

Every claim the answer makes cites one source: a card row (Trigger, hop `n`, a State changes, Side effects, Rules `R-n`, Edge branches, Failure modes, Where to watch, Contract, or Debt row), a ledger row, a chains block, a playbook row, a contract row, a register row, an inventory row, a glossary row, an overview file's section, a `capability.md` section, a row of any other generated file (`debt/detection-gaps.md`, `debt/recent-risk.md`, `ledger/unknown-rationale.md`, an ATLAS table, `_index/priority.json`), a curated doc's section, a `## Notes` line of a generated file, or, for pasted text, the paste itself; a claim that rests on a link inside a rationale-chain block (a comment, test, commit, or PR) cites `chains R-n`, or `chains R-new` when the chain ran in this answer for a row the card still writes as `R-new`.

- **Verified.** A generated row's `file:line` is read in the repo's checkout as it stands (its `HEAD`, which may be ahead of the card's `sources`): `verified` when the cited condition, write, or call is on that line, `moved` when the same code sits at another line of the file, `gone` when it is not in the file. A curated doc's `file:line` takes its ATLAS `## Citation drift` status when it has a row there (the section absent is the no-row case), else it is checked as the layout's Verify citations pass checks it, against the checkout `HEAD`. A source with no `file:line` is `n/a`. A `gone` row stays in Evidence marked `gone`, is not evidence for its claim, whose confidence is `unknown`, and adds an Open unknowns line naming the card as stale for `task-domain-sync`, or the doc as stale.
- **Confidence per claim.** A ledger or card Rules row carries its `Confidence`, or the stronger one a `domain-rationale-chain` run for it returned. A curated doc section is `documented` when the doc is `active` and `inferred` when `draft`, when it has no frontmatter, or when its `status` is outside the enum; a `deprecated` doc is cited only together with its `superseded_by` target, which carries the claim (target missing or not a path: the doc is cited alone as `unknown`, and an Open unknowns line reads `doc missing: <target or unknown> - ask the doc's owner`). A `## Notes` line, the paste itself, and a hop marked `(unverified)` or `(external - not in repos)` are `inferred`. A `chains R-n` or `chains R-new` block carries its own `Confidence`; any other generated row is `documented`, `unknown` when its citation is `gone`.
- **Precedence.** When a card row and a doc state different things about the same case, apply `CLAUDE.md` `## Precedence` as written (the scaffold text ranks a card citation above every doc; a `gone` one is no citation); a folder that `## Precedence` does not rank (`adr/`, `incidents/`, `consumers/`, `tech-debt/`, `patterns/`) ranks below generated cards and equal to `context/` and to every other unranked folder. The winner answers, both texts are quoted, and a Drift line names the loser first, then the winner. A card whose citation is `gone` gives way to a doc that ranks above cards; against a doc ranked below cards, the claim is `unknown`. Two docs that disagree follow the `## Precedence` order, the lower one named in a Drift line; two docs of the same rank (one folder, or both at the unranked level) that disagree leave the claim `unknown`, both quoted in one Drift line ending `- neither settles it`. A doc silent on the case is not drift.
- **Why.** For a "why" whose ledger `Confidence` (the card row's own for an `R-new` row) is below `documented`: Use skill: `domain-rationale-chain` with the card's Rules row and its `<capability>/<flow>` (the ledger row for a non-code rule) and the KB root; its block, without the ledger rows it emits after the bullets, is shown under `## Why`, and nothing is written. Who to ask is that block's `Ask` value, else the rule's block in `ledger/chains.md`, used as given (a name, `none needed`, or an `unknown - ...` value); with neither, a name a `## Notes` line gives for the rule, written `{name} (inferred)`, else `unknown - no author recorded`.

Nothing is written in this step.

### Step 6 - Answer by shape

- **bare name**: Use skill: `domain-flow-explain` with the text, the KB root, and the Audience languages; the Shape line, the Sync and Layers lines when they apply, then its output verbatim (the atomic already writes its resolution and stop lines in the layout's remedy form); no fact-check is applied to a lesson.
- **question**: the answer in prose, then evidence, confidence, and unknowns per the Output Format. When no source supports an answer, the Answer section opens with `not found in docs`, then `Nearest:` with up to three artifact ids or doc paths (`none` when nothing is near) and one line saying the topic can be checked under `repos/` and is not documented; Evidence keeps its header and one row `none - no source`, Overall reads `unknown - no source`, and Open unknowns names the topic with `ask unknown - not documented`.
- **ticket**: one block per item: the flows touched, the state changes and side effects on those flows, the curated `rules/`, `specs/`, `incidents/`, and `tech-debt/` docs naming the item's surfaces (an `adr/` doc that bears on the item goes to Unknowns), the `debt/register.md` rows whose `Signal` starts `coupling` and whose `Location` names a file of a touched flow, the `contracts/` callers who would see a change (`consumers/` docs when `contracts/` does not exist), a size, and the unknowns. Size, the largest whose condition holds: `S` for one flow and no coupling row; `M` for two or three flows, or one coupling row; `L` for four or more flows, or two or more coupling rows; `L - new surface` when no flow matches, or the item adds a surface no inventory row lists (a trigger, an outbound client, a `webhook out`, an `event out`, or a table) (`unknown - no cards` on a curated-only root). A rule is `documented` when its ledger `Confidence` is `documented` or an `active` `rules/` doc states it; an item that contradicts a `documented` rule, a ticket that sets out to change it included, moves up one size (`L`, `L - new surface`, and `unknown - no cards` stay) and the reason names the rule. Unknowns are what the knowledge base could not settle for the item: a `gone` citation, a rule with `unknown` rationale, a surface no card and no doc covers, or an `adr/` doc that bears on the item, named with its path.
- **alert**: the flows the signal maps to, each marked `(stale)` or `(orphaned)` from its card's `freshness`; for a stack trace, every frame whose path matches a file under `repos/` read there: `verified` when the line calls or raises inside the function the frame names, `moved` when that call sits at another line of the function, `gone` when the function is not in the file or no longer holds the call or raise; a frame outside `repos/` (a library or runtime) is not listed; each playbook row's first checks (when `playbook/` does not exist, the Failure modes rows of the mapped cards whose `What breaks`, `User sees`, or `Detected by` cell names the signal, the raised error, or the monitor), preceded by any card row the signal contradicts (an error the card says is rescued, a branch it says is unreachable), marked `signal disagrees`; the past incidents those rows name (without a playbook, the `incidents/` docs the card's `## Related` lists whose text names the failure or the signal); and runtime evidence. `Tracing` is reachable only when it is `Datadog` and the session lists a Datadog MCP tool (any other tracer is unreachable, with the atomic's reason `<tool> not supported (Datadog MCP only)`; none listed, `Datadog MCP not connected`); `Errors` is reachable when the session lists an MCP tool for it (else `<tool> MCP not connected`); when either is, or tool output was pasted with the alert, Use skill: `domain-runtime-evidence` once per flow (a card whose `## Sequence` list holds only its `- none - <evidence>` item (a no-backend-route card) gets no call, and its Runtime sub-block is that card's Runtime lines) with its Surface (for a ui screen the card's hop 1 under the `Services:` name its repo's tracing initialisation sets, else the trigger surface under the first service the card's Trace search names, `unknown` when it names none), each Edge branches row with its guard and the log message string or exception name the guard emits, read at the row's `Enforced at`, `Tracing` and `Errors` as read (`none` passed as is; the atomic writes its own `unavailable` reason per tool), and, as Paste, the pasted tool output when it names that flow's service, or names no service (the atomic marks a paste for another resource `-> unmapped`, its service-level `monitors` and `deploys` still applying); a paste naming another service only is not passed, and that flow is fetched or carries the atomic's own `unavailable` reasons, and show, one sub-block per flow, its summary line and its `volume`, `error_rate`, `branches`, `monitors`, and `deploys` blocks as returned. The answer stops at the flows and first checks.
- **pasted text**: the answer as for a question, stating what the cited code holds today where the message differs from it (an Open unknowns line for a claim only the paste supports asks the paste's name or channel, `unknown - paste names no source` when both are unstated); then a note proposal: one call of Use skill: `domain-kb-ingest` in `fact` mode with the message as `Text`, `Citation` `Source: {name or channel, date}` from the paste (a part the paste lacks reads `unstated`), `Hint` the curated kind the message reads as (the first piece's when it holds several), in ingest's kind words (`rule`, `incident`, `service`, `data-flow`, `tech-debt`, `adr`, `consumer`, `pattern`, `context`), the KB root, the Audience languages, and `Write: no`; its signal gate, search, decision tree, and conflict rule decide the curated kind and file, its `## Files` `proposed:` and `held:` lines are shown under the proposal, and nothing is written. A message it rejects as `no folder fits` names instead the generated card or `capability.md` whose `## Notes` it belongs to; any other rejection is not saved. `in_progress` is re-read immediately before any save; set at Step 2 or at the re-read, nothing is saved, the proposal stands as decided, and `Saved:` takes its sync-unfinished form unless ingest rejected or held the piece (the Output Format order); a value first seen at the re-read adds the Sync line after Shape. Otherwise, with `save`, make the same call with `Write: yes`, or append the sentence with its `(Source: {name or channel, date})` to that `## Notes` (a `mark` under the layout); `index.md` `## Curated` picks up a new curated file at the next `task-domain-sync`.

### Step 7 - Language

The first `## Audience` `Language:` code is the language of every answer. When the list has a second code and the shape is `question`, `ticket`, or `pasted text`, the answer's prose is repeated in it under `## Answer ({code})`; evidence, confidence, and unknowns are not repeated, and a third code adds no block.

## Output Format

Question and pasted text:

```
- **Shape:** {question | pasted text}
- **Sync:** unfinished at {command}:{pass} - files read as they stand, partly written by the unfinished run; when no sync is running, run task-domain-sync --resume     {only when in_progress is set}
- **Layers:** {generated only | curated only}     {only when one layer exists}

## Answer

{prose, one to three paragraphs, every claim traceable to the Evidence table; or `not found in docs`, then `Nearest: {up to three ids or paths | none}` and `Not documented; the code under repos/ can be checked directly`}

## Evidence

| Claim | Source | Verified |
| ----- | ------ | -------- |
| {claim} | {<capability>/<flow> <section>{ R-n \| R-new \| hop n \| D-n \| D-new} \| ledger R-n \| chains R-n \| chains R-new \| playbook row \| contracts/<caller> \| register D-n \| surfaces/<repo> row \| glossary term \| overview/<file> <section> \| <capability> capability.md <section> \| <generated path> row \| doc <path> <section> \| notes <path> \| paste <name, channel, date>}{ - file:line} | {verified \| moved \| gone \| n/a} |

## Why                                                 {only when the rationale chain ran}

{the domain-rationale-chain block, verbatim, without its ledger rows}

## Confidence

- **Overall:** {documented | inferred | unknown} - {the claim that sets it, the weakest confidence among the claims the Answer rests on | no source}
- {claim}: {confidence} - {why}     {one per claim; `none - no source` in the not-found case}
- **Drift:** {{loser} says {its text}; {winner} ({verified | moved | gone | n/a}) says {its text} - {the doc's owner corrects it | a superseding ADR replaces it | the card is stale - run task-domain-sync{ --resume} | neither settles it} | none - no disagreement}    {one line per disagreement Step 5 found, loser and winner each a doc path or a card row; the second remedy for an accepted ADR, the third when the card lost on a gone citation}

## Open unknowns

- {what could not be settled} - ask {name{ (inferred)} | {name or channel} (paste source) | the doc's owner | none needed | unknown - ...}
- {card or doc} is stale at {file:line} - {run task-domain-sync{ --resume} | its owner updates it}
{or}
- none - every claim is settled

## Proposed note                                       {pasted text only; the four lines repeat per piece ingest proposes, writes, or holds}

- **Kind:** {rules/ | incidents/ | specs/services/ | specs/data-flow/ | tech-debt/ | adr/ | consumers/ | patterns/ | context/ | generated Notes | none}
- **File:** {curated path ingest names | generated file path | none - restatement of <path> | none - <ingest reason>}
- **Add:** {sentence} (Source: {name or channel, date})
- **Saved:** {ingested - Accepted - <paths> | ingested - Downscoped - <paths> | held - conflict with <path> | held - accepted ADR - <path> | rejected - <ingest reason> | appended to Notes | no - say save to write | no - sync unfinished, say save once it finishes}

{after a `Write: yes` call: its `## Signal check`, `## Files`, `## Conflicts`, and `## Links added` blocks, verbatim, in that order, each heading demoted to `###`; otherwise: the `Write: no` call's `## Files` `proposed:` and `held:` lines, or its `No files written. Reason: ...` line on a rejection (one call covers every piece, so the blocks appear once, after the last piece's four lines; a Notes append adds nothing here)}

## Answer ({second code})                               {only when a second language is listed}

{prose}
```

Ticket:

```
- **Shape:** ticket
- **Sync:** unfinished at {command}:{pass} - files read as they stand, partly written by the unfinished run; when no sync is running, run task-domain-sync --resume     {only when in_progress is set}
- **Layers:** {generated only | curated only}     {only when one layer exists}

## Ticket: {title}

### {n}. {item}

- **Flows:** {<capability>/<flow>, ... | none - no card covers this surface}
- **Docs:** {rules/, specs/, incidents/, tech-debt/ paths | none - not found in docs}
- **Changes:** {state change or side effect - file:line (verified | moved | gone) | none - no flow}
- **Drift:** {the question form's Drift lines, one per disagreement | none - no disagreement}
- **Coupling:** {register rows | none - no coupling row shares these files | unknown - debt/register.md not generated yet}
- **Callers affected:** {contracts/<caller>.md or consumers/<name>.md | none}
- **Size:** {S | M | L | L - new surface | unknown - no cards} - {reason}
- **Unknowns:** {what to confirm} - ask {name{ (inferred)} | the doc's owner | none needed | unknown - ...} | none - every claim is settled

## Answer ({second code})                               {only when a second language is listed}

{one paragraph per item}
```

Alert:

```
- **Shape:** alert
- **Sync:** unfinished at {command}:{pass} - files read as they stand, partly written by the unfinished run; when no sync is running, run task-domain-sync --resume     {only when in_progress is set}
- **Layers:** {generated only | curated only}     {only when one layer exists}

## Alert: {signal as given}

- **Flows:** {<capability>/<flow>{ (stale | orphaned)} - frame | monitor | capture string | log line | service metric, ...}            {each flow once, the frames that map to it after it}
- **Frames:** {file:line (verified | moved | gone), ... | none - no frame under repos/}            {stack trace only}
- **First checks:** {from the playbook rows or the cards' Failure modes, in order, each file:line they carry marked (verified | moved | gone); a contradicted card row first, ending `- signal disagrees` | none - no row names the signal}
- **Past incidents:** {paths | none}
- **Drift:** {the question form's Drift lines, one per disagreement | none - no disagreement}
- **Runtime:** {one sub-block per flow: the runtime-evidence summary line, then its volume, error_rate, branches, monitors, deploys blocks as returned, or, for a no-backend-route card, that card's Runtime lines verbatim | unavailable - {<tool> not supported (Datadog MCP only) | <tool> MCP not connected | Tracing none | Errors none}, {the same for the other tool} | unavailable - Tracing and Errors are none | unavailable - no flow}
- **Next:** investigate from the flows and first checks above
```

`Flows` reads `none - {signal} maps to no card` when nothing maps, and every line below Flows but Frames, Runtime, and Next then reads `none - no flow`, Runtime `unavailable - no flow`. When at least one flow maps and no `domain-runtime-evidence` call is made because neither tool is reachable and no tool output was pasted, Runtime's paired `unavailable` form is written when at least one tool is not `none`, the `Tracing and Errors are none` form when both are, followed by one sub-block per no-backend-route card holding that card's Runtime lines verbatim (such a card shows its own lines whatever the tools). Every shape's block opens with the Shape line, then the Sync line when `in_progress` is set, then the Layers line when only one layer exists, as the fences show. `Saved:` takes the first form that applies: `rejected - ...` when ingest's gate or tree rejects (a `no folder fits` with a Notes target excepted), `held - ...` when ingest holds the piece (a conflict, or an accepted ADR), `no - sync unfinished, ...` while `in_progress` is set, `no - say save to write` without `save`, else the outcome of the `Write: yes` call or the Notes append. Every `task-domain-sync` remedy in these blocks takes the form Step 2 gives while `in_progress` is set. The stop lines Step 2 names are emitted alone.

Bare name: `- **Shape:** bare name`, the Sync and Layers lines when they apply, then the `domain-flow-explain` output verbatim.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; URL-only and missing `--in` stops checked first; a non-null `in_progress` named on the Sync line, or in the stop line when neither layer exists, nothing saved, every remedy in the Step 2 form; both layers located, otherwise stopped only when neither exists, the single layer named; index, atlas with citation drift, audience (default `en`), observability, precedence, Capabilities, Notes, ledger rows whole, `ledger/chains.md` blocks, overview files, capability files, aliases and freshness, Where to watch and How to see it lines loaded; curated folders walked; absent generated files noted; no repo file read
- [ ] Step 3: shape classified by the first matching row, a bare name being what `domain-flow-explain` resolves plus `<capability>/<flow>` and `R-<n>` as written, and written as the first line
- [ ] Step 4: retrieval walked the Need table and searched the curated docs in every Audience language; frames mapped by longest suffix; every mapped flow kept
- [ ] Step 5: every generated citation read at the checkout; curated citations taken from Citation drift or the layout's Verify check; a `gone` row kept in Evidence, its claim `unknown`, and the stale card or doc named; per-claim confidence set; precedence applied with unranked folders below cards and equal to `context/`, a Drift line per disagreement naming the loser first; rationale chain run for a below-documented why and shown without its ledger row; Ask carried as given, a Notes-sourced name marked `(inferred)`
- [ ] Step 6: the shape's block emitted with every slot; the `not found in docs` forms used when nothing supports the answer; size taken as the largest condition that holds, `documented` read from the ledger or an active rules doc, the bump capped at `L`; alert frames under `repos/` marked, contradicted card rows first as `signal disagrees`, runtime fetched only from a Datadog MCP, an errors MCP, or a paste, with each branch's guard and marker, a no-backend-route card skipped, the paste passed only to the flow it names, and the blocks shown as returned, the answer stopped at first checks; note proposal made as a `Write: no` ingest call, a `no folder fits` message routed to a generated `## Notes`, `in_progress` re-read before any save, saved only on `save` with `Write: yes` or the Notes append, and the outcome stated with ingest's blocks
- [ ] Step 7: answers in the first listed language; second-language prose added only for the stated shapes and only for the second code

## Avoid

- Answering from memory of how such systems usually work instead of a cited source
- Citing a `file:line` without reading it in the repo first (a lesson's citations are `domain-flow-explain`'s)
- Resolving a card-versus-doc disagreement silently, in either direction
- Investigating an alert past naming the flows and first checks
- Writing any file other than a `domain-kb-ingest` call or a generated `## Notes` append on `save`, or either while `in_progress` is set
- Guessing who to ask when no chain block records one
