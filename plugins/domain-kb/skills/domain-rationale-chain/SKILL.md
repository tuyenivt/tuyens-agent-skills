---
name: domain-rationale-chain
description: "Reconstruct why a business rule exists: comment, test, spec, KB doc, ADR, commit, PR, ticket, incident chain with confidence and who to ask."
metadata:
  category: domain
  tags: [domain, rationale, business-rule, git-history, archaeology, confidence]
user-invocable: false
---

# Domain Rationale Chain

> Load `Use skill: domain-kb-layout` first: it owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Walks every link of evidence for one business rule, from the enforcing line outward, and writes the strongest reason found as a ledger row with a confidence and a name to ask. It never guesses a reason and never lowers a confidence the card already earned.

## When to Use

- `task-domain-sync` Analyse pass, once per enforcement site across every card's Rules rows
- `task-domain-ask` answering "why does the system do X" when the ledger row's confidence is below `documented`
- Standalone: one enforcing `file:line` named by the user

## Inputs

| Input      | Required | Notes                                                                                                                                                       |
| ---------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rule       | yes      | A card's Rules row: `Id`, text, `Kind`, `Enforced at` (`repos/<repo>/<file>:<line>`, or `process - <doc path>` for a non-code kind), `Doc`, `Rationale`, `Confidence`, `Quirk`, plus the card's `<capability>/<flow>`; a ledger row of kind `process`, `policy`, or `rollout gate` is walked the same way; standalone, only `Enforced at`: the text is the condition quoted from that line with every pipe escaped as `\|`, and the id, `Kind`, `Doc`, and `Flows` are the ledger row's whose `Enforced at` is that site or the use line it resolves to (one row per rule text on that line); with no such row, `R-new`, `code`, the `rules/` file whose `Where enforced` cites the site (else `none`), and `none - not tied to a flow` |
| KB root    | no       | Curated `rules/`, `specs/`, `context/`, `adr/`, `incidents/`, and generated `ledger/rules.md`; absent, the `kb-doc`, `adr`, and `incident` links read `unavailable - no knowledge base` |
| PR access  | no       | `gh` installed and authenticated against the repo's remote; otherwise the `pr` link reads `unavailable - gh not installed`, `- gh not authenticated`, `- no remote`, or `- remote not on GitHub` |

## Rules

- **Every link is walked and recorded**; the reason is the strongest link, not the first, and among links that state one the layout's precedence decides: a `rules/` doc, then an `accepted` ADR, a spec, a comment or test, a commit or PR, and a `context/` pack last. A link searched with nothing found reads `none`; a link that could not be searched reads `unavailable - <reason>`; a link that does not apply reads its `n/a - ...` form.
- **Confidence is earned by a stated reason.** `documented` when a link states why in words: a comment, a test whose name or description states it, a spec, a curated KB doc (`rules/`, `specs/`, `context/`), an ADR, a commit or PR message. `inferred` when no link states it but the reason follows from named evidence: an incident naming the rule whose cause explains it, a constant equal to a limit a document in scope names, or the code shape the card's trace already read as `inferred`. `unknown` otherwise. A ticket id, a requester's name, or "per ops" is a pointer, never a reason. When the walk finds less than the input holds (the strongest of the merged card rows and the matched ledger row), that `Rationale` and `Confidence` are kept verbatim (pointers the walk found go to the chain, not to the `Rationale`) and `Ask` follows them. A link found that states no reason keeps its text with `(no reason stated)`, never `none`.
- **Quirk is `yes`** when the row's resulting `Confidence` is `unknown`, when the stated reason contradicts current code or a document in scope, when the rule hardcodes a business constant with no named source (a person named as `Source:` is a named source), or when the enforcing line sits under a `TODO`, `FIXME`, `HACK`, `workaround`, or `legacy` marker. Quirk and Last touched come from the fresh walk always.
- **The enforcing line is where the condition is evaluated**, never where a constant is declared; a row that cites a declaration is walked at the first use of the constant in the same file (in the file the card's hop cites when the constant is used elsewhere, else at the declaration), the block's `Enforced at` shows that use line and adds `declared at {line}`, while the ledger row and the card mark keep the input row's own `Enforced at` (standalone, the matched ledger row's, else the input site); a test link cites the line that names the test. When several lines evaluate the constant, the first is walked and cited. A range (`file:6-7`) is walked as `-L 6,7:<file>`. A line that no longer exists at the tip (a stale card) makes `commit` read `unavailable - line moved, re-trace the card`. **Last touched** is the author and date of the newest commit in that history; the introducing commit is the oldest one whose version of the line already holds the condition, so a later edit to the line never counts as its introduction. When `git -C repos/<repo> rev-parse --is-shallow-repository` prints `true` and the oldest commit the history returns has no parent in the clone (`git -C repos/<repo> rev-list --parents -n 1 <sha>` prints the sha alone), the history ends at the graft: `commit` reads `unavailable - shallow clone` and `pr` reads `n/a - no commit`. Ticket ids are scanned across the whole line history, and for a non-code rule across the whole doc; a `(#n)` subject suffix or `Merge pull request #n` is the PR, never a ticket. **Ask** is `none needed` when the result is `documented`; otherwise the introducing author, `unknown - shallow clone` behind a graft, `unknown - no history` when `commit` is `none`.
- **A non-code rule has no line history.** For `Kind` `process`, `policy`, or `rollout gate` the walk covers `kb-doc`, `adr`, `ticket`, and `incident` only; `comment`, `test`, `spec`, `commit`, and `pr` read `n/a - process rule`, `Last touched` reads `n/a - process rule`, and `Ask`, when the result is not `documented`, is the owner the doc's text names (an `Owner:` or `Source:` line; an exception's approver is not the owner), else `unknown - no owner recorded`.
- **One row per rule.** A rule's identity is its file plus rule text; in a batch, rows from different cards with the same identity merge into one block whose flows are the union, and two rules on one line stay two blocks. An existing ledger row matched by file plus text, then by text alone, keeps its `Id` and takes the card's current rule text; its `Rationale` and `Confidence` change only to a stronger result. A rule no row matches is emitted as `R-new`, in card row order, and the consuming workflow numbers it.
- **Commands run inside the repo**: `git -C repos/<repo> log -L <line>,<line>:<repo-relative file> --format='%x00%H %as %an%n%s%n%b'` gives the line's history, newest first, each commit starting at a NUL byte and its patch following its message (`%as` is the author date); `gh pr list --state merged --search <sha> --json number,title,body,baseRefName` runs with `repos/<repo>` as the working directory so `gh` resolves the remote, and when it returns nothing (a rebase or squash merge rewrote the sha), `gh api repos/{owner}/{repo}/commits/<sha>/pulls` from the same directory, reading `number`, `title`, `body`, `base.ref`, and `merged_at`; of several PRs, the one merged (`merged_at` set) into the tracked branch wins. `pr` reads `n/a - no commit` when `commit` is `none` or `unavailable`. Read-only throughout.

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

One block per rule (two rules on one line are two blocks):

```
- **Rule:** {R-n | R-new} - {rule text}
- **Kind:** {code | process | policy | rollout gate}
- **Enforced at:** {repos/<repo>/<file>:<line>{ (declared at <line>)} | process - <doc path>}
- **Doc:** {rules/<file>.md | none}
- **Flows:** {<capability>/<flow>, ... | none - not tied to a flow}
- **Chain:**
  1. comment - {text{ (no reason stated)} | none | n/a - process rule}
  2. test - {name - file:line{ (no reason stated)} | none | n/a - process rule}
  3. spec - {path - text{ (no reason stated)} | none | n/a - process rule}
  4. kb-doc - {path - text{ (no reason stated)} | none | unavailable - <reason>}
  5. adr - {path | none | unavailable - <reason>}
  6. commit - {sha date author - message | none | unavailable - <reason> | n/a - process rule}
  7. pr - {#n title - body excerpt | none | unavailable - <reason> | n/a - no commit | n/a - process rule}
  8. ticket - {id, id | none}
  9. incident - {path | none | unavailable - <reason>}
- **Rationale:** {one sentence | the kept input text | `unknown; <what the pointers say>`}
- **Confidence:** {documented | inferred | unknown}
- **Quirk:** {yes - <reason> | no}
- **Last touched:** {{author} {date} ({sha}) | n/a - process rule}
- **Ask:** {author | doc owner | none needed | unknown - no owner recorded | unknown - shallow clone | unknown - no history}
```

Then the ledger rows in `ledger/rules.md` shape, one per block:

```
| {Id} | {rule text} | {Kind} | {flows} | {Enforced at} | {Doc} | {Rationale} | {Confidence} | {yes \| no} | {author date \| n/a - process rule} |
```

`Doc` is the input row's value, `none` when the input had none; the consuming workflow's Link pass fills it. Every `|` inside a cell is escaped `\|`, `Rationale` included. The consuming workflow writes the rows into `ledger/rules.md`, the blocks into `ledger/chains.md` under `## {Id}` headings, and marks each card's Rules row with the new `Id`, `Rationale`, `Confidence`, and `Quirk`.

## Avoid

- Stopping the walk at the first link found instead of recording every link
- Fetching a ticket, or treating its title as the reason
- Writing `inferred` for a reason that is merely plausible rather than named by a link
- Lowering a confidence the card or ledger already holds
