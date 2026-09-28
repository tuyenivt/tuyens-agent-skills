---
name: domain-rationale-chain
description: Reconstruct why a business rule exists: comment, test, spec, KB doc, ADR, commit, PR, ticket, incident chain with confidence and who to ask.
metadata:
  category: domain
  tags: [domain, rationale, business-rule, git-history, archaeology, confidence]
user-invocable: false
---

# Domain Rationale Chain

Walks every link of evidence for one business rule, from the enforcing line outward, and writes the strongest reason found as a ledger row with a confidence and a name to ask. It never guesses a reason and never lowers a confidence the card already earned.

## When to Use

- `task-domain-sync` Analyse pass, once per enforcement site across every card's Rules rows
- `task-domain-ask` answering "why does the system do X" when the ledger row's confidence is below `documented`
- Standalone: one enforcing `file:line` named by the user

## Inputs

| Input      | Required | Notes                                                                                                                                                       |
| ---------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rule       | yes      | A card's Rules row: `Id`, text, `Kind`, `Enforced at` (`repos/<repo>/<file>:<line>`, or `process - <doc path>` for a non-code kind), `Doc`, `Rationale`, `Confidence`, `Quirk`, plus the card's `<capability>/<flow>`; a ledger row of kind `process`, `policy`, or `rollout gate` is walked the same way; standalone, only `Enforced at`, the text becomes the condition quoted from that line with every pipe escaped as `\|`, and the flow `unknown - standalone` |
| KB root    | no       | Curated `rules/`, `specs/`, `context/`, `adr/`, `incidents/`, and generated `ledger/rules.md`; absent, the `kb-doc`, `adr`, and `incident` links read `unavailable - no knowledge base` |
| PR access  | no       | `gh` authenticated; absent or failing, the `pr` link reads `unavailable - <reason>`                                                                          |

## Rules

- **Every link is walked and recorded**; the reason is the strongest link, not the first. A link searched with nothing found reads `none`; a link that could not be searched reads `unavailable - <reason>`.
- **Confidence is earned by a stated reason.** `documented` when a link states why in words: a comment, a test whose name or description states it, a spec, a curated KB doc (`rules/`, `specs/`, `context/`), an ADR, a commit or PR message. `inferred` when no link states it but the reason follows from named evidence: an incident naming the rule whose cause explains it, a constant equal to a limit a document in scope names, or the code shape the card's trace already read as `inferred`. `unknown` otherwise. A ticket id, a requester's name, or "per ops" is a pointer, never a reason. When the walk finds less than the card holds, the card's `Rationale` and `Confidence` are kept and `Ask` follows them. A link found that states no reason keeps its text with `(no reason stated)`, never `none`.
- **Quirk is `yes`** when the result is `unknown`, when the stated reason contradicts current code or a document in scope, when the rule hardcodes a business constant with no named source, or when the enforcing line sits under a `TODO`, `FIXME`, `HACK`, `workaround`, or `legacy` marker. Quirk and Last touched come from the fresh walk always.
- **The enforcing line is where the condition is evaluated**, never where a constant is declared; a row that cites a declaration is walked at the first use of the constant in the same file, the block's `Enforced at` shows that use line and adds `declared at {line}`, while the ledger row and the card mark keep the card's own `Enforced at`. A range (`file:6-7`) is walked as `-L 6,7`. **Last touched** is the author and date of the newest commit in that history; the introducing commit is the oldest one in which the condition exists. When `git rev-parse --is-shallow-repository` is `true` and the history ends at the graft, `commit` reads `unavailable - shallow clone` and `Ask` reads `unknown - shallow clone`. Ticket ids are scanned across the whole line history. **Ask** is the introducing author when the result is not `documented`, `none needed` when it is.
- **A non-code rule has no line history.** For `Kind` `process`, `policy`, or `rollout gate` the walk covers `kb-doc`, `adr`, `ticket`, and `incident` only; `comment`, `test`, `spec`, `commit`, and `pr` read `n/a - process rule`, `Last touched` reads `n/a - process rule`, and `Ask` is the owner the doc names (an `Approved by` cell, an `Owner` line, or a `Source:` name), else `unknown - no owner recorded`.
- **One row per rule.** A rule's identity is its file plus rule text; in a batch, rows from different cards with the same identity merge into one block whose flows are the union, and two rules on one line stay two blocks. An existing ledger row matched by file plus text, then by text alone, keeps its `Id` and takes the card's current rule text; its `Rationale` and `Confidence` change only to a stronger result. New ids are assigned in card row order after every match.
- **Commands run inside the repo**: `git -C repos/<repo> log -L <line>,<line>:<repo-relative file> --format='%H %cs %an%n%s%n%b'` gives the line's history (oldest last); `gh pr list --state merged --search <sha> --json number,title,body` runs with `repos/<repo>` as the working directory so `gh` resolves the remote. Read-only throughout.

## Patterns

### Reading the links

| Link     | Where                                                                                    | States a reason when                                                   |
| -------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| comment  | The enforcing line, the lines above it, the constant's declaration                        | It says why, not what (`gateway bills per call` yes; `see PF-412` no)   |
| test     | Tests whose name or description names the rule or its constant                            | The name or description states the reason                              |
| spec     | `docs/`, `README`, OpenAPI descriptions, in-repo design notes                              | The text explains the rule                                             |
| kb-doc   | Curated `rules/`, `specs/`, `context/` files naming the rule, its surface, or its constant, searched in every Audience language | Its `## Rationale`, a Statement, or the surrounding prose states why; the path is the source |
| adr      | KB `adr/` files naming the rule, its surface, or its constant                              | The decision section states it                                         |
| commit   | The introducing commit from the line history                                               | The message states why                                                 |
| pr       | The PR whose merge introduced that commit                                                  | Title or body states why                                               |
| ticket   | An id pattern (`PF-412`, `#1234`, a tracker URL) in any link above                          | Never; recorded as the pointer to ask about                            |
| incident | KB `incidents/` files naming the rule, surface, or constant; a related but distinct incident is `none` | Its cause or decision explains the rule, which makes the result `inferred` |

Bad - a pointer promoted to a reason:

```
- **Rationale:** PF-412
- **Confidence:** documented
```

Good - the pointer kept, the gap named:

```
- **Rationale:** unknown; the comment cites PF-412 and states no reason
- **Confidence:** unknown
- **Ask:** Hiro Tanaka
```

## Output Format

One block per enforcement site:

```
- **Rule:** {R-n | R-new} - {rule text}
- **Kind:** {code | process | policy | rollout gate}
- **Enforced at:** {repos/<repo>/<file>:<line>{ (declared at <line>)} | process - <doc path>}
- **Doc:** {rules/<file>.md | none}
- **Flows:** {<capability>/<flow>, ... | none - not tied to a flow}
- **Chain:**
  1. comment - {text | none | n/a - process rule}
  2. test - {name - file:line | none | n/a - process rule}
  3. spec - {path - text | none | n/a - process rule}
  4. kb-doc - {path - text | none | unavailable - <reason>}
  5. adr - {path | none | unavailable - <reason>}
  6. commit - {sha date author - message | none | unavailable - <reason> | n/a - process rule}
  7. pr - {#n title - body excerpt | none | unavailable - <reason> | n/a - process rule}
  8. ticket - {id | none}
  9. incident - {path | none | unavailable - <reason>}
- **Rationale:** {one sentence, or `unknown; <what the pointers say>`}
- **Confidence:** {documented | inferred | unknown}
- **Quirk:** {yes - <reason> | no}
- **Last touched:** {author} {date} ({sha}) | n/a - process rule
- **Ask:** {author | none needed | unknown - no owner recorded}
```

Then the ledger rows in `ledger/rules.md` shape, one per block:

```
| {Id} | {rule text} | {Kind} | {flows} | {Enforced at} | {Doc} | {Rationale} | {Confidence} | {yes \| no} | {author date \| n/a - process rule} |
```

`Doc` is the input row's value, `none` when the input had none; the consuming workflow's Link pass fills it. The consuming workflow writes the rows into `ledger/rules.md`, the blocks into `ledger/chains.md` under `## {Id}` headings, and marks each card's Rules row with the new `Id`, `Rationale`, `Confidence`, and `Quirk`.

## Avoid

- Stopping the walk at the first link found instead of recording every link
- Fetching a ticket, or treating its title as the reason
- Writing `inferred` for a reason that is merely plausible rather than named by a link
- Lowering a confidence the card or ledger already holds
