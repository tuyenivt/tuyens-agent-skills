---
name: task-domain-ask
description: Answer from both layers of the domain knowledge base, fact-checked against the repos: question, ticket, alert or stack trace, pasted message.
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

**Not for:** reading the atlas (`task-domain-explain`); building the knowledge base (`task-domain-sync`); turning a ticket into an implementation plan (`task-domain-solve`); driving a live incident to a root cause, which is the on-call workflow's job after this one has named the flow.

## Inputs

| Input | Required | Notes                                                                                                                          |
| ----- | -------- | ------------------------------------------------------------------------------------------------------------------------------ |
| Text or `--in <file>` | yes | The question, ticket text, alert, trace, message, or name, inline or read from the file; a bare tracker URL is not fetched, the workflow asks for the ticket text and stops |
| Save  | no       | The word `save` after a pasted message: a durable fact is routed into the curated layer, anything else is appended to the named generated file's `## Notes` |

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Locate and load the index

The root is the working directory. The generated layer exists when `_index/sync-state.json` records a `sha`; the curated layer exists when any of `rules/`, `specs/`, `incidents/`, `context/`, `tech-debt/`, `adr/`, `consumers/`, `patterns/` holds a Markdown file. When neither exists, emit `no knowledge base here - run task-domain-sync init or import` and stop; when only one exists, say which and continue with it. From the generated layer read `index.md`, `ATLAS.md`, `CLAUDE.md` `## Audience`, `## Observability`, and `## Precedence`, the `Id` and `Doc` columns of `ledger/rules.md`, the frontmatter `id` and `aliases` of every card and `capability.md`, and every card's `## Where to watch` Monitors and Error tracker lines and `## How to see it` Log lines. From the curated layer read `index.md` `## Curated`, or walk the folders when it is absent, for every doc's path, title, status, and tags. A text that is only a tracker URL gets `paste the ticket text - URLs are not fetched` and the workflow stops. Nothing under `repos/` is read yet.

### Step 3 - Classify the input

Take the first matching row; the shape is written as the first line of the answer.

| Shape        | Signals                                                                                                                          |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| bare name    | The whole text matches a capability or flow id or alias, or a ledger `Id`, loaded in Step 2                                       |
| alert        | A monitor name, an error-tracker capture string, or a log line loaded in Step 2; a stack trace (file paths with line numbers or frames); or a service name from `## Observability` with an error rate, latency, or count |
| ticket       | A title followed by asks, acceptance criteria, or numbered items                                                                  |
| pasted text  | Quoted or forwarded prose attributed to someone else (a name, a channel, a date) rather than addressed to this workflow            |
| question     | Anything else                                                                                                                    |

### Step 4 - Retrieve

Walk `index.md`'s Need table to the cards, ledger, playbook, contracts, and register rows the input names, and search the curated docs by title, tags, headings, and body for the surfaces, entities, constants, and terms the input names, in every `## Audience` language. A frame is mapped through `_index/file-to-flow.json` by the longest path suffix that matches a key across repos; every flow the key lists is kept. A monitor, capture string, or log line maps to the cards whose Where to watch or How to see it carries it; a service metric maps to the cards whose Trace search names the service. A ticket item is retrieved by the surfaces, entities, and terms it names, matched against the inventories, the glossary, the cards' Story lines, and the curated `rules/`, `specs/`, `incidents/`, and `tech-debt/` docs. A bare name skips to Step 6.

### Step 5 - Fact-check and precedence

Every claim the answer will make cites one row or one doc section: a card row (Trigger, hop `n`, a State changes, Side effects, Rules `R-n`, Edge branches, Failure modes, Where to watch, Contract, or Debt row), a ledger row, a chains block, a playbook row, a contract row, a register row, an inventory row, a glossary row, or a curated doc's section. For each cited `file:line`, on either layer, read that line in the repo: `verified` when the cited condition, write, or call is still there, `moved` when the same code sits at another line in the file, `gone` when it is not in the file; a row or section with no `file:line` is `n/a`. A `gone` citation is not used as evidence; the answer says the card is stale there and names the flow for `task-domain-sync`, or names the doc for `task-domain-sync import`. A curated claim with no citation takes Confidence `documented` when its doc's `status` is `active` and `inferred` when `draft`; a `deprecated` doc is cited only together with its `superseded_by` target. When a card row and a doc disagree, apply `CLAUDE.md` `## Precedence`: with the card's citation `verified`, answer with the code, quote both, and add the Drift line; otherwise the doc wins in its layer order and the card is named as stale. Nothing is written. For a "why" whose ledger confidence is below `documented`: Use skill: `domain-rationale-chain` for that rule; its block is shown under `## Why` and nothing is written. Who to ask comes from that block's `Ask` line, the rule's block in `ledger/chains.md`, or the doc's owner line: an author's name is used as given, `none needed` means the reason is documented and no one need be asked, and any other value or no block reads `unknown - no author recorded`.

### Step 6 - Answer by shape

- **bare name**: Use skill: `domain-flow-explain` and emit its lesson verbatim; no fact-check is applied to a lesson.
- **question**: the answer in prose, then evidence, confidence, and unknowns per the Output Format. When no row and no doc supports an answer, the Answer section is exactly `not found in docs`, followed by the three nearest artifact ids or doc paths and one line saying the topic can be checked under `repos/` and is not documented.
- **ticket**: one block per item: the flows touched, the state changes and side effects on those flows, the curated rules and specs naming the item's surfaces, the `debt/register.md` rows whose `Signal` starts `coupling` and whose files the flows share, the `contracts/` callers who would see a change, a size signal, and the unknowns: `S` for one flow and no coupling row, `M` for two or three flows or one coupling row, `L` for more, `L - new surface` when no flow matches; an item that contradicts a rule with `Confidence: documented` moves up one size and the reason names the rule; each with the reason. Unknowns are what the knowledge base could not settle for the item: a `gone` citation, a rule with `unknown` rationale, or a surface no card and no doc covers.
- **alert**: the flows the signal maps to, each playbook row's first checks (the cards' Failure modes rows serve when `playbook/` does not exist yet), the incidents those rows name, and, when `## Observability` names a reachable tool, Use skill: `domain-runtime-evidence` for each flow's trigger surface (the first backend hop when the trigger is a ui screen) and show its `volume`, `error_rate`, `deploys`, and `monitors` blocks. Hand the flows to the on-call workflow; this step does not investigate further.
- **pasted text**: the answer as for a question, then a note proposal. When the message passes the `domain-kb-ingest` signal gate (a rule, threshold, contract, failure mode, decision, correction, consumer fact, or located debt item) the proposal names the curated kind and, with `save`, Use skill: `domain-kb-ingest` with the message as `Text` and `Source: {name or channel, date}` from the paste; otherwise the proposal names the generated card or `capability.md` whose `## Notes` the message belongs to and, with `save`, appends the sentence (a `mark` under the layout). The answer says which happened.

### Step 7 - Language

When `## Audience` `Language:` lists a second code and the shape is `question`, `ticket`, or `pasted text`, add the answer's prose in that language under `## {Language} answer`. Evidence, confidence, and unknowns stay English; a third listed code adds no block.

## Output Format

Question and pasted text:

```
- **Shape:** {question | pasted text}

## Answer

{prose, one to three paragraphs, every claim traceable to the Evidence table; or exactly `not found in docs`, then `Nearest: {id or path}, {id or path}, {id or path}` and `Not documented; the code under repos/ can be checked directly`}

## Evidence

| Claim | Source | Verified |
| ----- | ------ | -------- |
| {claim} | {<capability>/<flow> <section>{ R-n \| hop n \| D-n} \| ledger R-n \| chains R-n \| playbook row \| contracts/<caller> \| register D-n \| surfaces/<repo> row \| glossary term \| doc <path> <section>}{ - file:line} | {verified \| moved \| gone \| n/a} |

## Why                                                 {only when the rationale chain ran}

{the domain-rationale-chain block, verbatim}

## Confidence

- **Overall:** {documented | inferred | unknown} - the weakest confidence among the rule claims the answer rests on; a row with no Confidence counts as `documented` when its citation is `verified` and `unknown` otherwise; a doc section counts by its `status` as Step 5 states
- {claim needing it}: {confidence} - {why}
- **Drift:** {doc path} disagrees with {card row} - run task-domain-sync import to reconcile    {only when a verified card contradicts a doc}

## Open unknowns

- {what could not be settled} - ask {name | unknown - no author recorded}

## Proposed note                                       {pasted text only}

- **Kind:** {rules/ | incidents/ | specs/services/ | specs/data-flow/ | tech-debt/ | adr/ | consumers/ | patterns/ | context/ | generated Notes}
- **File:** {curated target path from ingest | generated file path}
- **Add:** {sentence} ({name or channel, date})
- **Saved:** {yes - ingested to {path} | yes - appended to Notes | no - say `save` to write}

## {Language} answer                                  {only when a second language is listed}

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
- **Coupling:** {register rows, or none - no coupling row shares these files}
- **Callers affected:** {contracts, or none}
- **Size:** {S | M | L | L - new surface} - {reason}
- **Unknowns:** {what to confirm} - ask {name | unknown - no author recorded}

## {Language} answer                                  {only when a second language is listed}

{one paragraph per item}
```

Alert:

```
- **Shape:** alert

## Alert: {signal as given}

- **Flows:** {<capability>/<flow>, ...} - {frame | monitor | capture string | log string | service metric}
- **First checks:** {from the playbook rows, in order, each file:line marked (verified | moved | gone)}
- **Past incidents:** {paths, or none}
- **Runtime:** {volume, error_rate, deploys, monitors blocks | unavailable - <reason>}
- **Hand-off:** the on-call workflow, with the flows and first checks above
```

Bare name: `- **Shape:** bare name`, then the `domain-flow-explain` lesson verbatim.

## Self-Check

- [ ] Step 1: `behavioral-principles` loaded
- [ ] Step 2: both layers located; stopped only when neither exists; index, atlas, audience, observability, precedence, aliases, Where to watch lines, and the curated list loaded; no repo file read
- [ ] Step 3: shape classified by the first matching row and written as the first line
- [ ] Step 4: retrieval walked the Need table and searched the curated docs in every Audience language; frames mapped by longest suffix; every mapped flow kept
- [ ] Step 5: every cited line on either layer read and marked; `gone` excluded and the stale flow or doc named; doc confidence taken from `status`; precedence applied and the Drift line added when a verified card contradicts a doc; rationale chain run for a below-documented why and shown, not written
- [ ] Step 6: the shape's block emitted with every slot; `not found in docs` written exactly when nothing supports the answer; size rule applied; alert handed off, not investigated; note proposal attributed, routed through ingest when it is a durable fact, saved only on `save`, and the outcome stated
- [ ] Step 7: second-language prose added only for the stated shapes and only for the second listed code

## Avoid

- Answering from memory of how such systems usually work instead of a cited row or doc section
- Citing a `file:line` without reading it in the repo first
- Resolving a card-versus-doc disagreement silently, in either direction
- Investigating an alert past naming the flows and first checks
- Writing any file other than a `domain-kb-ingest` call or a generated `## Notes` append on `save`
- Guessing who to ask when no chain block or doc records an author
