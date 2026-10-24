---
name: domain-rationale-chain
description: "Reconstruct why a business rule exists: comment, test, spec, KB doc, ADR, commit, PR, ticket, incident chain with confidence and who to ask."
metadata:
  category: domain
  tags: [domain, rationale, business-rule, git-history, archaeology, confidence]
user-invocable: false
---

# Domain Rationale Chain

> Load `Use skill: domain-kb-layout` first and read at least its Rules and these Patterns sections: Curated layer, Templates (`business-rule.md`, `adr.md` `> Status:`), CLAUDE.md (`## Repos` `Branch`), Indexes (`sync-state.json` `branch`), and the Ledger, playbook, contracts, debt, surfaces entry for `ledger/`. It owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Walks every link of evidence for one business rule, from the enforcing line outward, and writes the strongest reason found as a ledger row with a confidence and a name to ask. It never guesses a reason and never lowers a confidence the card already earned.

## When to Use

- `task-domain-sync` Analyse pass, once per rule (file plus rule text) across every card's Rules rows, and its Link pass for each `rules/` doc no card row matched
- `task-domain-ask` answering "why does the system do X" when the ledger row's confidence is below `documented`
- Standalone: one enforcing `file:line` named by the user

## Inputs

| Input      | Required | Notes                                                                                                                                                       |
| ---------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Rule       | yes      | A card's Rules row: `Id`, text, `Kind`, `Enforced at` (`repos/<repo>/<file>:<line>`, or `process - <doc path>` for a non-code kind, the doc path being the `rules/` file itself, never its `Where enforced` text), `Doc`, `Rationale`, `Confidence`, `Quirk`, plus the card's `<capability>/<flow>`; a ledger row of kind `process`, `policy`, or `rollout gate` is walked the same way; standalone, only `Enforced at`: the text is the condition quoted from that line with every pipe escaped as `\|` (it replaces the matched ledger row's text, as a card's text does), and the id, `Kind`, `Doc`, and `Flows` are the ledger row's whose `Enforced at` is that site or the use line it resolves to (one row per rule text on that line); with no such row, `R-new`, `code`, the `rules/` file whose `Where enforced` cites the site (else `none`), and `none - not tied to a flow` |
| KB root    | no       | Curated `rules/`, `specs/`, `context/`, `adr/`, `incidents/`, and generated `ledger/rules.md`; absent, the `kb-doc`, `adr`, and `incident` links read `unavailable - no knowledge base` |
| PR access  | no       | `gh` installed and authenticated against the repo's remote; otherwise the `pr` link reads `unavailable - gh not installed`, `- gh not authenticated`, `- no remote`, `- remote not on GitHub`, or `- no default remote (run gh repo set-default)` |

## Rules

- **Every link is walked and recorded**; the reason is the strongest link, not the first, and among links that state one this order decides: a `rules/` doc, then an `accepted` ADR, a curated `specs/` doc or an in-repo spec, a comment or test, a commit or PR, and a `context/` pack last (a `proposed` or `superseded` ADR, and a `draft` doc, rank with `context/`; a `deprecated` doc is read through its `superseded_by` target); `Confidence` is the winning link's, and an incident, which explains without stating, gives the `inferred` result only when no link states a reason. A link searched with nothing found reads `none`; a link that could not be searched reads `unavailable - <reason>`; a link that does not apply reads its `n/a - ...` form.
- **Confidence is earned by a stated reason.** `documented` when a link states why in words: a comment, a test whose name or description states it, a spec, a curated KB doc (`rules/`, `specs/`, `context/`), an ADR, a commit or PR message. `inferred` when no link states it but the reason follows from named evidence: an incident naming the rule whose cause explains it, a constant equal to a limit a document in scope names, or the code shape the card's trace already read as `inferred`. `unknown` otherwise. A ticket id, a requester's name, "per ops", or a reason the doc itself marks unconfirmed (an open question, "nobody remembers why") is a pointer, never a reason. When the walk finds no more than the input holds (the strongest of the merged card rows and the matched ledger row; the source the input cites, found again with fuller wording, is not more), that `Rationale` and `Confidence` are kept verbatim (pointers the walk found go to the chain, not to the `Rationale`) and `Ask` follows them. A link found that states no reason keeps its text with `(no reason stated)`, never `none`; several hits of one link kind share its line, joined with `; `, the one stating the reason first, then the rest by path ascending, then line ascending (several stating one: in the strongest-link order above, then path ascending; the first is the link's entry in that order).
- **Quirk is `yes`** when the row's resulting `Confidence` is `unknown`, when the stated reason contradicts current code or a document in scope, when the rule hardcodes a business constant whose reason no link states (the result is not `documented`), or when the enforcing line sits under a `TODO`, `FIXME`, `HACK`, `workaround`, or `legacy` marker. Quirk and Last touched come from the fresh walk always.
- **The enforcing line is where the condition is evaluated**, never where a constant is declared; a row that cites a declaration is walked at the first use of the constant in the same file (in the file the card's hop cites when the constant is used elsewhere, else at the declaration), the block's `Enforced at` shows that use line and adds `(declared at {line})`, `(declared at repos/<repo>/<file>:{line})` when the declaration is in another file, while the ledger row and the card mark keep the input row's own `Enforced at` (standalone, the matched ledger row's, else the input site); a test link cites the line that names the test. When several lines evaluate the constant, the first is walked and cited. A range (`file:6-7`) is walked as `-L 6,7:<file>` and emitted as written. A line that no longer exists at the tip (a file absent from `HEAD`, where `git log -L` fails with `fatal: There is no path <file> in the commit`, or a line past the file's end, `fatal: file <file> has only <n> lines`, included; any other git failure makes `commit` and `Last touched` read `unavailable - <git's fatal message>`), or no longer holds the rule's check (a stale card), makes `commit` read `unavailable - line moved, re-trace the card`, `pr` `n/a - no commit`, `Last touched` `unavailable - line moved`, and, when the Ask rule below would name the introducing author, `Ask` `unknown - line moved`. **Last touched** is the author and date of the newest commit in that history, or in the history of the declaration line of a constant the condition reads from the same file when that commit is newer (a changed limit is a touch); the introducing commit is the oldest one whose version of the line already holds the check (its shape, whatever the constant's value then), so a later edit to the line or its limit never counts as its introduction. When `git -C repos/<repo> rev-parse --is-shallow-repository` prints `true` and the oldest commit the history returns has no parent in the clone (`git -C repos/<repo> rev-list --parents -n 1 <sha>` prints the sha alone and the sha is listed in the file `git -C repos/<repo> rev-parse --git-path shallow` names, relative to `repos/<repo>` for a clone and absolute for a submodule; a genuine root commit is not a graft), the history ends at the graft: when that graft commit is the one whose version first holds the check, `commit` reads `unavailable - shallow clone`, `pr` reads `n/a - no commit`, and `Last touched` reads `unavailable - shallow clone` unless a later commit in the clone changed the line or the declaration line it also reads; a later commit that introduced the check is walked as usual. Ticket ids are scanned across every commit of the line history whose patch changes the enforcing line, and for a non-code rule across the whole doc; a `(#n)` subject suffix or `Merge pull request #n` is the PR, never a ticket. **Ask** is `none needed` when the result is `documented`; otherwise the person a `Source:` sentence in a kb-doc link or a `## Notes` line of a generated file names for the rule (a channel-only source names nobody), else the introducing author, `unknown - shallow clone` behind a graft, `unknown - no history` when `commit` reads any other `unavailable - <reason>`.
- **A non-code rule has no line history.** For `Kind` `process`, `policy`, or `rollout gate` the walk covers `kb-doc`, `adr`, `ticket`, and `incident` only; `comment`, `test`, `spec`, `commit`, and `pr` read `n/a - process rule`, `Last touched` reads `n/a - process rule`, and `Ask`, when the result is not `documented`, is the owner the doc's text names (an `Owner:` bullet or a `Source:` sentence anywhere in the doc, Operational notes included; an exception's approver is not the owner), else `unknown - no owner recorded`.
- **One row per rule.** A rule's identity is its file plus rule text; in a batch, rows from different cards with the same identity merge into one block whose flows are the union, and two rules on one line stay two blocks. An existing ledger row matched by file plus text, then, for the rows that key left unmatched, by text alone (ignoring case, whitespace, and numerals, so a changed limit keeps the row; each ledger row is claimed once, by the first card row in card order), keeps its `Id` and takes the card's current rule text; its `Rationale` and `Confidence` change only to a stronger result: a higher `Confidence`, or the same `Confidence` from a link earlier in the strongest-link order than the source the input `Rationale` cites in parentheses (an input citing none is kept), whose reason then becomes the `Rationale`. A Link-pass row (a `rules/` doc no card row matched) keeps its id by the layout's key instead: the ledger row with the same `Doc` path, then the same rule text; its rule text is the first sentence of the doc's `## Statement`. A rule no row matches is emitted as `R-new`, in card row order, and the consuming workflow numbers it.
- **Commands run inside the repo**: `git -C repos/<repo> log -L <line>,<line>:<repo-relative file> --format='%x00%H %as %an%n%s%n%b'` gives the line's history, newest first, each commit starting at a NUL byte and its patch following its message (`%as` is the author date); `gh pr list --state merged --search <sha> --json number,title,body,baseRefName` runs with `repos/<repo>` as the working directory so `gh` resolves the remote, and when it returns nothing (a rebase or squash merge rewrote the sha) or no PR it lists was merged into the tracked branch, `gh api repos/{owner}/{repo}/commits/<sha>/pulls` from the same directory, reading `number`, `title`, `body`, `base.ref`, and `merged_at`; of several PRs, the one merged (`merged_at` set) into the tracked branch wins; for a commit off the default branch the endpoint also returns open PRs, and an open PR (`merged_at` null) is never cited; a PR neither command returns reads `none`. The tracked branch is the repo's `branch` in `_index/sync-state.json`; standalone with none, the `CLAUDE.md` `## Repos` `Branch` cell, else `origin/HEAD`'s target; a `.` value means the root's current branch, a `HEAD` value, or an `origin/HEAD` with no target, means no tracked branch, and any merged PR qualifies (of several, the earliest `merged_at`), and names compare bare (`origin/` stripped) against `baseRefName` and `base.ref`. `pr` reads `n/a - no commit` when `commit` is `unavailable`. Read-only throughout.

## Patterns

### Reading the links

| Link     | Where                                                                                    | States a reason when                                                   |
| -------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------- |
| comment  | The enforcing line, the comment block directly above it (ended by the first code line), the constant's declaration | It says why, not what (`gateway bills per call` yes; `see PF-412` no)   |
| test     | Tests whose name or description names the rule or its constant                            | The name or description states the reason                              |
| spec     | `docs/`, `README`, OpenAPI descriptions, in-repo design notes                              | The text explains the rule                                             |
| kb-doc   | Curated `rules/`, `specs/`, `context/` files naming the rule, its surface, or its constant, searched in every Audience language; a `## Notes` line of a generated file naming it is a pointer to a person, never a reason, written `{path} ## Notes - {text} (no reason stated)` | Its `## Rationale`, a Statement, or the surrounding prose states why; the path is the source |
| adr      | KB `adr/` files naming the rule, its surface, or its constant                              | Its `## Context` or `## Decision` states why                            |
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
- **Enforced at:** {repos/<repo>/<file>:<line | a-b>{ (declared at {repos/<repo>/<file>:}line)} | process - <doc path>}
- **Doc:** {rules/<file>.md | none}
- **Flows:** {<capability>/<flow>, ... | none - not tied to a flow}
- **Chain:**
  1. comment - {text{ (no reason stated)} | none | n/a - process rule}
  2. test - {name - file:line{ (no reason stated)} | none | n/a - process rule}
  3. spec - {path - text{ (no reason stated)} | none | n/a - process rule}
  4. kb-doc - {path - text{ (no reason stated)} | none | unavailable - <reason>}
  5. adr - {path - text{ (no reason stated)} | none | unavailable - <reason>}
  6. commit - {short sha date author - message{ (no reason stated)} | unavailable - shallow clone | unavailable - line moved, re-trace the card | unavailable - <reason> | n/a - process rule}
  7. pr - {#n title - body excerpt{ (no reason stated)} | none | unavailable - <reason> | n/a - no commit | n/a - process rule}
  8. ticket - {id; id | none}
  9. incident - {path - text{ (no reason stated)} | none | unavailable - <reason>}
- **Rationale:** {one sentence ({the winning link's source: a path, `file:line`, short sha, or #n}) | the kept input text | `unknown; <what the pointers say>`}
- **Confidence:** {documented | inferred | unknown}
- **Quirk:** {yes - <reason> | no}
- **Last touched:** {{author} {date} ({short sha}) | unavailable - shallow clone | unavailable - line moved | unavailable - <reason> | n/a - process rule}
- **Ask:** {named source or author | doc owner | none needed | unknown - no owner recorded | unknown - shallow clone | unknown - line moved | unknown - no history}
```

Then the ledger rows in `ledger/rules.md` shape, one per block, with no header row:

```
| {Id} | {rule text} | {Kind} | {flows} | {Enforced at} | {Doc} | {Rationale} | {Confidence} | {yes \| no} | {author date \| unavailable - shallow clone \| unavailable - line moved \| unavailable - <reason> \| n/a - process rule} |
```

An incident that explains the rule is written without `(no reason stated)`. `Doc` is the input row's value, `none` when the input had none; the consuming workflow's Link pass fills it. Every `|` inside a cell is escaped `\|`, `Rationale` included. The consuming workflow writes the rows into `ledger/rules.md`, the blocks into `ledger/chains.md` under `## {Id}` headings, and marks each card's Rules row with the new `Id`, `Rationale`, `Confidence`, and `Quirk`.

## Avoid

- Fetching a ticket, or treating its title as the reason
- Lowering a confidence the card or ledger already holds
