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
| Save  | no       | The word `save` after a pasted message: the message is routed through `domain-kb-ingest`, or appended to a generated `## Notes` when ingest finds no folder for it |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate and load the index

Use skill: `domain-kb-layout` for every path, section, and empty form named below. A text that is only a tracker URL gets `paste the ticket text - URLs are not fetched` and the workflow stops. The root is the working directory. When `_index/sync-state.json` records `in_progress`, emit `sync interrupted at {command}:{pass} - run task-domain-sync to finish` and stop. The generated layer exists when `sync-state.json` records a `sha`; the curated layer exists when any curated folder holds a Markdown file. When neither exists, emit `no knowledge base here - run task-domain-sync init or import` and stop; when only one exists, the answer's first line after Shape says `- **Layers:** generated only` or `curated only` and the workflow continues with it. From the generated layer read `index.md`, `ATLAS.md` (with `## Citation drift`), `CLAUDE.md` `## Audience` (`Language:` default `en`, also when `CLAUDE.md` is absent), `## Observability`, `## Precedence`, and its `## Notes`, the `Id`, `Confidence`, and `Doc` columns of `ledger/rules.md`, the frontmatter `id` and `aliases` of every card and `capability.md`, and every card's `## Where to watch` Monitors and Error tracker lines and `## How to see it` Log lines. Walk every curated folder for each doc's path, title, status, `superseded_by`, and tags (the walk, not `index.md` `## Curated`, which may lag). A generated file this workflow names that does not exist yet (`playbook/`, `contracts/`, `ledger/chains.md`, `overview/glossary.md`, `debt/register.md`, `_index/file-to-flow.json`) is skipped and its fallback below applies, or the slot it feeds reads `unknown - <file> not generated yet`. Nothing under `repos/` is read yet.

### Step 3 - Classify the input

Take the first matching row; the shape is the first line of the answer.

| Shape        | Signals                                                                                                                          |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| bare name    | The whole text is a `<capability>/<flow>` id, or matches a capability or flow id or alias, or a ledger `Id`, loaded in Step 2     |
| alert        | A monitor name, an error-tracker capture string, or a log line loaded in Step 2; a stack trace (file paths with line numbers or frames); or a service name from `## Observability` with an error rate, latency, or count |
| ticket       | A title followed by asks, acceptance criteria, or numbered items                                                                  |
| pasted text  | Quoted or forwarded prose attributed to someone else (a name, a channel, a date) rather than addressed to this workflow            |
| question     | Anything else                                                                                                                    |

### Step 4 - Retrieve

Walk `index.md`'s Need table to the cards, ledger, playbook, contracts, and register rows the input names, and search the curated docs by title, tags, headings, and body for the surfaces, entities, constants, and terms the input names, in every `## Audience` language as the layout's Languages rule searches. A frame is mapped through `_index/file-to-flow.json` by the longest path suffix that matches a key across repos; every flow the key lists is kept. A monitor, capture string, or log line maps to the cards whose Where to watch or How to see it carries it; a service metric maps to the cards whose Trace search names the service. A ticket item is retrieved by the surfaces, entities, and terms it names, matched against the inventories, the glossary, the cards' Story lines, and the curated `rules/`, `specs/`, `incidents/`, and `tech-debt/` docs. A bare name skips to Step 6.

### Step 5 - Fact-check and precedence

Every claim the answer makes cites one source: a card row (Trigger, hop `n`, a State changes, Side effects, Rules `R-n`, Edge branches, Failure modes, Where to watch, Contract, or Debt row), a ledger row, a chains block, a playbook row, a contract row, a register row, an inventory row, a glossary row, a curated doc's section, a `## Notes` line of a generated file, or, for pasted text, the paste itself.

- **Verified.** A generated row's `file:line` is read in the repo's checkout as it stands (its `HEAD`, which may be ahead of the card's `sources`): `verified` when the cited condition, write, or call is on that line, `moved` when the same code sits at another line of the file, `gone` when it is not in the file. A curated doc's `file:line` takes its ATLAS `## Citation drift` status when it has a row there, else it is checked as the layout's Verify citations pass checks it, against the checkout `HEAD`. A source with no `file:line` is `n/a`. A `gone` citation is not evidence: it becomes an Open unknowns line naming the card as stale for `task-domain-sync`, or the doc as stale.
- **Confidence per claim.** A ledger or card Rules row carries its `Confidence`, or the stronger one a `domain-rationale-chain` run for it returned. A curated doc section is `documented` when the doc is `active` and `inferred` when `draft`; a `deprecated` doc is cited only together with its `superseded_by` target, which carries the claim. A `## Notes` line, the paste itself, and a hop marked `(unverified)` or `(external - not in repos)`, is `inferred`. Any other generated row is `documented` unless its citation is `gone`, which makes it `unknown`.
- **Precedence.** When a card row and a doc state different things about the same case, apply `CLAUDE.md` `## Precedence`; a curated folder it does not rank (`adr/`, `incidents/`, `consumers/`, `tech-debt/`, `patterns/`) ranks below generated cards. A card row whose citation is `verified`, `moved`, or `n/a` answers, both texts are quoted, and a Drift line names the doc. A card whose citation is `gone` gives way to a doc that ranks above cards; against a doc ranked below cards, the claim is `unknown`. Two docs that disagree follow the `## Precedence` order, the lower one named in a Drift line. A doc silent on the case is not drift.
- **Why.** For a "why" whose ledger `Confidence` is below `documented`: Use skill: `domain-rationale-chain` for that rule; its block, without its ledger-row line, is shown under `## Why`, and nothing is written. Who to ask is that block's `Ask` value, else the rule's block in `ledger/chains.md`, used as given (a name, `none needed`, or an `unknown - ...` value); with neither, `unknown - no author recorded`.

Nothing is written in this step.

### Step 6 - Answer by shape

- **bare name**: Use skill: `domain-flow-explain` with the text, the KB root, and the Audience languages; the Shape line, then its output verbatim; no fact-check is applied to a lesson.
- **question**: the answer in prose, then evidence, confidence, and unknowns per the Output Format. When no source supports an answer, the Answer section is exactly `not found in docs`, followed by the three nearest artifact ids or doc paths and one line saying the topic can be checked under `repos/` and is not documented.
- **ticket**: one block per item: the flows touched, the state changes and side effects on those flows, the curated rules and specs naming the item's surfaces, the `debt/register.md` rows whose `Signal` starts `coupling` and whose files the flows share, the `contracts/` callers who would see a change (`consumers/` docs when `contracts/` does not exist), a size, and the unknowns. Size, the largest whose condition holds: `S` for one flow and no coupling row; `M` for two or three flows, or one coupling row; `L` for four or more flows, or two or more coupling rows; `L - new surface` when no flow matches. An item that contradicts a rule whose claim confidence is `documented` moves up one size (`L` stays `L`) and the reason names the rule. Unknowns are what the knowledge base could not settle for the item: a `gone` citation, a rule with `unknown` rationale, or a surface no card and no doc covers.
- **alert**: the flows the signal maps to; for a stack trace, every frame whose path matches a file under `repos/` read there: `verified` when the line calls or raises inside the function the frame names, `moved` when that call sits at another line of the function, `gone` when the function is not in the file; a frame outside `repos/` (a library or runtime) is not listed; each playbook row's first checks (the cards' Failure modes rows when `playbook/` does not exist), preceded by any card row the signal contradicts (an error the card says is rescued, a branch it says is unreachable), marked `signal disagrees`; the past incidents those rows name (without a playbook, the `incidents/` docs the card's `## Related` lists whose text names the failure or the signal); and runtime evidence. A tool is reachable when an MCP server for the `## Observability` `Tracing` or `Errors` tool is connected in this session; when one is, or tool output was pasted with the alert, Use skill: `domain-runtime-evidence` once per flow with the `## Observability` service the card's Trace search names, the trigger surface (the first backend hop when the trigger is a ui screen), the card's Edge branches, `Tracing`, `Errors`, and any tool output pasted with the alert as Paste, and show its `volume`, `error_rate`, `deploys`, and `monitors` blocks. The answer stops at the flows and first checks.
- **pasted text**: the answer as for a question, stating what the cited code holds today where the message differs from it; then a note proposal. The proposal is what `domain-kb-ingest` would decide for the message as `Text`, with `Citation` `Source: {name or channel, date}` from the paste, the KB root, and the Audience languages: its signal gate and decision tree name the curated kind and file. A message it rejects as `no folder fits` names instead the generated card or `capability.md` whose `## Notes` it belongs to; any other rejection is not saved. With `save`, Use skill: `domain-kb-ingest` with those inputs, or append the sentence to that `## Notes` (a `mark` under the layout); `index.md` `## Curated` picks up a new curated file at the next `task-domain-sync`.

### Step 7 - Language

The first `## Audience` `Language:` code is the language of every answer. When the list has a second code and the shape is `question`, `ticket`, or `pasted text`, the answer's prose is repeated in it under `## Answer ({code})`; evidence, confidence, and unknowns are not repeated, and a third code adds no block.

## Output Format

Question and pasted text:

```
- **Shape:** {question | pasted text}

## Answer

{prose, one to three paragraphs, every claim traceable to the Evidence table; or exactly `not found in docs`, then `Nearest: {id or path}, {id or path}, {id or path}` and `Not documented; the code under repos/ can be checked directly`}

## Evidence

| Claim | Source | Verified |
| ----- | ------ | -------- |
| {claim} | {<capability>/<flow> <section>{ R-n \| hop n \| D-n} \| ledger R-n \| chains R-n \| playbook row \| contracts/<caller> \| register D-n \| surfaces/<repo> row \| glossary term \| doc <path> <section> \| notes <path> \| paste <name, channel, date>}{ - file:line} | {verified \| moved \| gone \| n/a} |

## Why                                                 {only when the rationale chain ran}

{the domain-rationale-chain block, verbatim, without its ledger-row line}

## Confidence

- **Overall:** {documented | inferred | unknown} - {the weakest per-claim confidence among the claims the Answer rests on}
- {claim}: {confidence} - {why}
- **Drift:** {doc path} says {doc text}; {card row or doc path} ({verified | moved | n/a}) says {its text} - {the doc's owner corrects it | a superseding ADR replaces it}    {one per disagreement Step 5 found; the second form for an accepted ADR}

## Open unknowns

- {what could not be settled} - ask {name | none needed | unknown - ...}
- {card or doc} is stale at {file:line} - {run task-domain-sync | its owner updates it}
{or}
- none - every claim is verified

## Proposed note                                       {pasted text only}

- **Kind:** {rules/ | incidents/ | specs/services/ | specs/data-flow/ | tech-debt/ | adr/ | consumers/ | patterns/ | context/ | generated Notes | none}, one per piece ingest would write
- **File:** {curated path ingest names | generated file path | none - restatement of <path> | none - <ingest reason>}
- **Add:** {sentence} ({name or channel, date})
- **Saved:** {ingested - <ingest Signal check value> - <paths> | held - conflict with <path> | rejected - <ingest reason> | appended to Notes | no - say `save` to write}

{with `save` and an ingest call: its `## Signal check`, `## Files`, and `## Conflicts` blocks, verbatim, each heading demoted to `###`}

## Answer ({second code})                               {only when a second language is listed}

{prose}
```

Ticket:

```
- **Shape:** ticket

## Ticket: {title}

### {n}. {item}

- **Flows:** {<capability>/<flow>, ... | none - no card covers this surface}
- **Docs:** {rules/<file>.md, specs/services/<file>.md, ... | none - not found in docs}
- **Changes:** {state change or side effect - file:line (verified | moved | gone)}
- **Coupling:** {register rows | none - no coupling row shares these files}
- **Callers affected:** {contracts/<caller> or consumers/<name> | none}
- **Size:** {S | M | L | L - new surface} - {reason}
- **Unknowns:** {what to confirm} - ask {name | none needed | unknown - ...}

## Answer ({second code})                               {only when a second language is listed}

{one paragraph per item}
```

Alert:

```
- **Shape:** alert

## Alert: {signal as given}

- **Flows:** {<capability>/<flow>{ (stale | orphaned)}, ... - frame | monitor | capture string | log line | service metric}
- **Frames:** {file:line (verified | moved | gone), ...}            {stack trace only}
- **First checks:** {from the playbook rows or the cards' Failure modes, in order, each file:line they carry marked (verified | moved | gone); a contradicted card row first, ending `- signal disagrees`}
- **Past incidents:** {paths | none}
- **Runtime:** {volume, error_rate, deploys, monitors blocks | unavailable - no {tool, tool} MCP connected | unavailable - Tracing and Errors are none}
- **Next:** investigate from the flows and first checks above
```

`Flows` reads `none - {signal} maps to no card` when nothing maps, and every line but Frames then reads `none - no flow`. Every shape's block opens with the Shape line, then `- **Layers:** {generated only | curated only}` when only one layer exists. The stop lines Steps 2 and 3 name are emitted alone.

Bare name: `- **Shape:** bare name`, then the `domain-flow-explain` output verbatim.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: layout loaded; URL-only and `in_progress` stops checked first; both layers located, stopped only when neither exists, the single layer named; index, atlas with citation drift, audience (default `en`), observability, precedence, Notes, ledger columns, aliases, Where to watch lines loaded; curated folders walked; absent generated files noted; no repo file read
- [ ] Step 3: shape classified by the first matching row, `<capability>/<flow>` counted as a bare name, and written as the first line
- [ ] Step 4: retrieval walked the Need table and searched the curated docs in every Audience language; frames mapped by longest suffix; every mapped flow kept
- [ ] Step 5: every generated citation read at the checkout; curated citations taken from Citation drift or the layout's Verify check; `gone` excluded and the stale card or doc named; per-claim confidence set; precedence applied with unranked folders below cards, a Drift line per disagreement; rationale chain run for a below-documented why and shown without its ledger row; Ask carried as given
- [ ] Step 6: the shape's block emitted with every slot; `not found in docs` written exactly when nothing supports the answer; size taken as the largest condition that holds, the bump capped at `L`; alert frames under `repos/` marked, contradicted card rows first as `signal disagrees`, runtime fetched only from a connected tool or a paste, and the answer stopped at first checks; note proposal decided by ingest's gate, saved only on `save`, and the outcome stated with ingest's blocks
- [ ] Step 7: answers in the first listed language; second-language prose added only for the stated shapes and only for the second code

## Avoid

- Answering from memory of how such systems usually work instead of a cited source
- Citing a `file:line` without reading it in the repo first
- Resolving a card-versus-doc disagreement silently, in either direction
- Investigating an alert past naming the flows and first checks
- Writing any file other than a `domain-kb-ingest` call or a generated `## Notes` append on `save`
- Guessing who to ask when no chain block records one
