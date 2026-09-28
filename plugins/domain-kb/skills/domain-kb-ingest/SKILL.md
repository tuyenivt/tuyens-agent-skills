---
name: domain-kb-ingest
description: Classify a fact or document into the hand-written knowledge base: signal gate, decision tree, search before create, conflict flag, dedup, citations.
metadata:
  category: domain
  tags: [domain, knowledge-base, ingest, classify, hand-written, dedup, conflict]
user-invocable: false
---

# Domain KB Ingest

Places one input, a single fact or a whole document, into the hand-written layer `domain-kb-layout` defines: decides whether it is knowledge at all, which folder it belongs to, whether a file already covers it, and writes or updates exactly the files that result. It is the only writer of the hand-written layer; nothing reaches that layer by copy, script, or shell loop.

## When to Use

- `task-domain-sync import` for inline text, one file, or every file of a foreign knowledge base
- `task-domain-sync update` Distil pass, for each cited candidate fact from the commit window
- `task-domain-ask` with `save` on a pasted message that is a durable fact
- Standalone: one fact or one file named by the user

## Inputs

| Input     | Required | Notes                                                                                                                                       |
| --------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Text      | yes      | One fact in a sentence or paragraph, or a document body with or without frontmatter                                                         |
| Citation  | no       | `repos/<repo>/<path>:<line>`, a commit short SHA, a ticket id, or `Source: {who or channel, date}` for a fact that came from a person         |
| Hint      | no       | A target kind (`rule`, `incident`, `service`, `data-flow`, `tech-debt`, `adr`, `consumer`, `pattern`, `context`); a source folder name is a hint, never a decision |
| Mode      | no       | `fact` (default): the cross-folder split applies; `document`: the input is placed whole under its dominant kind and split candidates are only reported |
| KB root   | yes      | The hand-written folders, `_templates/`, and, when present, the generated layer for the restatement check                                    |
| Languages | no       | The `## Audience` `Language:` list; default `en`; every code is a search language                                                            |

## Rules

- **One call, one input, files written by this skill alone.** A document is ingested whole as `Text` in one call; a batch is one call per file. No script, shell loop, or bulk copy writes a hand-written file, and the caller reports this skill's `## Signal check` and `Kind` line for every file. A file whose only change is a path move is still ingested, not moved.
- **Signal gate, decided before any search.** Accept when the input adds a rule, threshold, or policy; a contract or data shape; a failure mode or incident fact; a decision with trade-offs; a corrected fact that contradicts a doc; a consumer's integration fact; or a debt item with a location. Reject a restatement of what a doc or card already holds (the answer names the covering path), commentary without a fact, implementation trivia (tests only, renames, formatting, dependency bumps with no behaviour change, log tweaks), and a status update. Downscope when only part is new and say what was dropped.
- **Decision tree, first match wins.** A rule, policy, threshold, or rollout gate -> `rules/`; something that went wrong in production -> `incidents/`; a per-service design, API, or data model -> `specs/services/`; a cross-service end-to-end flow -> `specs/data-flow/`; debt, a security risk, a dependency risk, or a compliance gap -> `tech-debt/`; an architectural decision with trade-offs -> `adr/`; an integrating party with no repo under `repos/` -> `consumers/`; a reusable convention -> `patterns/`; background or rationale for something the other folders hold -> `context/`; otherwise stop with `## Signal check` `Rejected: no folder fits - <what it looks like>` and ask. `context/` is never a catch-all. The `Hint` breaks a tie only; when the tree and the hint disagree the tree wins and the `Kind` line says `(hint overruled: <reason>)`.
- **Split across folders in `fact` mode.** An input spanning kinds is cut into one piece per kind, each placed by the tree, with reciprocal relative links under `## Related docs`; a rule is never embedded in a spec, and an incident's root cause that states a rule becomes a `rules/` file linked from the incident. In `document` mode the document is placed whole under its dominant kind (the kind of its title and first section) and every other kind it contains is listed under `Split candidates` for the caller to report.
- **Search before create.** Match candidates in the target folder, then across every hand-written folder, by filename, `tags`, title, headings, and body, in every listed language; the strongest match by shared surface strings, entity names, constants, and rule text wins. A match is updated: the new content goes into the section whose heading fits (`## Parameters` for a threshold, `## Exceptions` for an exception, `## Items` for a debt item, `## Timeline` for an incident event), `updated` is bumped to today, surrounding text is preserved, and a whole-document input that adds nothing beyond the match is rejected as a restatement. No match creates the file: copy the kind's `_templates/` file, fill `title`, `status: draft`, `created` and `updated` today, `tags` with the kind first, then the input's tags, fill the sections the input answers, and leave the rest with their template headings.
- **Conflict stops the write.** New content that contradicts a statement in the matched file, or in any file the search reached, stops with a `## Conflicts` entry naming the file, the existing text, and the new text; nothing is overwritten, and the conflicting piece is not written elsewhere either. A corrected fact the caller marks as a correction (`Citation` names the commit or the person who corrected it) is still a conflict: the user resolves it.
- **Citations travel verbatim.** A `repos/...:line`, commit, or ticket citation is written into the doc as given, in the section that holds the fact (`## Enforcement` `Where enforced:` for a rule, the item's `Location` for debt, the step's row for a flow). A fact with no citation and no human source is rejected as `unverifiable`; a fact from a person is written with `Source: {who or channel, date}` from the input.
- **Dedup after write.** When the fact now sits in two files, the second occurrence is replaced by a relative link to the first; `imported_from` is added only when the caller supplies it, verbatim.
- **Nothing invented.** Sections the input does not answer keep their template heading and no body; no owner, date, severity, or rationale is filled from what such docs usually say.

## Patterns

### Decision tree examples

Bad - a threshold filed as background, a whole document copied into a folder by name:

```
context/refund-rules.md: created - "Refunds close 7 days after payment"
rules/2026-08-31-refund-double-post.md: created - copied from old-kb/rules/
```

Good - the threshold is a rule; the document's content says incident, whatever its source folder said:

```
- Kind: rules/ (rule, threshold)
- rules/refund-window.md: updated - ## Parameters gained `Window | 7 | days | repos/orders/app/services/refund_service.rb:6 (commit 3f2a1c9)`
- Kind: incidents/ (hint overruled: the body is a timeline with a root cause)
- incidents/2026-08-31-refund-double-post.md: created - from _templates/incident.md
```

### Updating a section

The section is chosen by the template's headings, and content is appended inside it after the last existing line; a table gains a row, a list gains an item, prose gains a sentence. A section the template lacks is added before `## Related docs`. Frontmatter keys other than `updated` and `tags` are never changed on an update.

### Rejections

| Input                                                            | Signal check                                              |
| ---------------------------------------------------------------- | --------------------------------------------------------- |
| "Refunds close after 7 days" when `rules/refund-window.md` says so | `Rejected: restatement of rules/refund-window.md`          |
| "Looks fine to me, ship it"                                       | `Rejected: commentary without a fact`                      |
| "Renamed RefundSvc to RefundService"                              | `Rejected: implementation trivia`                          |
| "Refund cap is 500 now" with no citation and no source           | `Rejected: unverifiable - no citation and no source`       |
| "Refund cap is 500 (per ops, 2026-09-20); also we should rename the job" | `Downscoped: kept the cap; dropped the rename (trivia)` |

## Output Format

```
## Signal check

- {Accepted | Rejected | Downscoped}: {what was kept and, for downscoped, what was dropped, or the rejection reason}
- Kind: {rules/ | incidents/ | specs/services/ | specs/data-flow/ | tech-debt/ | adr/ | consumers/ | patterns/ | context/ | none}{ (hint overruled: <reason>)}
- Existing match: {path | none}
- Split candidates: {kind: <section or sentence>, ... | none}

## Files

- {path}: {created | updated} - {what changed}
{or}
- No files written. Reason: {rejected - <reason> | conflict}

## Conflicts

- {path}: {existing text} vs {new text}
{or}
- none

## Links added

- {from path} -> {to path} ({reciprocal | dedup})
{or}
- none
```

Every block is present on every call. `Kind` names the folder the tree chose, `none` on a rejection; in `fact` mode with a split, `## Files` carries one line per piece and `Kind` lists every folder used. The consuming workflow copies `## Signal check` and `## Files` into its own report row for the input.

## Avoid

- Copying a file into a folder because that is where its source kept it
- Creating a second file on a topic a search in another language would have found
- Filling a template section with what such a document usually says
- Resolving a contradiction by overwriting the older statement
- Writing a fact with no citation and no named source
