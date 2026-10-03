---
name: domain-kb-ingest
description: "Classify a fact or document into the curated knowledge base: signal gate, decision tree, search before create, conflict flag, dedup, citations."
metadata:
  category: domain
  tags: [domain, knowledge-base, ingest, classify, curated, dedup, conflict]
user-invocable: false
---

# Domain KB Ingest

> Load `Use skill: domain-kb-layout` first and read at least its Rules and these Patterns sections: Curated layer, Templates, Ids and references, and the Languages rule. It owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Places one input, a single fact or a whole document, into the curated layer `domain-kb-layout` defines: decides whether it is knowledge at all, which folder it belongs to, whether a file already covers it, and writes or updates exactly the files that result. It is the only writer of the curated layer besides a person; nothing reaches that layer by copy, script, or shell loop.

## When to Use

- `task-domain-sync import` for inline text, one file, or every file of a foreign knowledge base
- `task-domain-sync` Distil pass (`update`), for each cited candidate fact, or topic group of them, from the commit window
- `task-domain-ask` on a pasted message that is a durable fact: the gate and tree decide its note proposal, and `save` makes the call that writes
- Standalone: one fact or one file named by the user

## Inputs

| Input     | Required | Notes                                                                                                                                       |
| --------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Text      | yes      | One fact in a sentence or paragraph, or a document body with or without frontmatter                                                         |
| Citation  | no       | `repos/<repo>/<path>:<line>` (a commit short SHA or ticket id may follow in parentheses), a commit short SHA, a ticket id, or `Source: {who or channel, date}` for a fact that came from a person; several, each tied to the sentence it supports, when the text groups facts |
| Hint      | no       | A target kind (`rule`, `incident`, `service`, `data-flow`, `tech-debt`, `adr`, `consumer`, `pattern`, `context`); a source folder name is a hint, never a decision |
| Mode      | no       | `fact` (default): the cross-folder split applies; `document`: the input is placed whole under the kind of its title and first body section and split candidates are only reported |
| Imported from | no   | For an imported document, the `--in` path as the caller typed it joined with the file's path relative to it, or `inline` for text passed to `import` directly; written as `imported_from` on a file this call creates (`inline` is not written) |
| KB root   | yes      | The curated folders, `_templates/`, and, when present, the generated layer for the restatement check                                    |
| Languages | no       | The `## Audience` `Language:` list; default `en`; every code is a search language                                                            |

## Rules

- **One call, one input, files written by this skill alone.** A document is ingested whole as `Text` in one call; a batch is one call per file, each seeing the files earlier calls wrote and none reading another call's report. No script, shell loop, or bulk copy writes a curated file, and the caller reports this skill's `## Signal check`, `## Files`, and `## Conflicts` for every file. A file whose only change is a path move is still ingested, not moved.
- **Signal gate, decided before any write.** Accept when the input adds a rule, threshold, or policy; a contract or data shape; a failure mode, a risk, or an incident fact; a decision with trade-offs; a corrected fact that contradicts a doc; a consumer's integration fact; a debt item; a cross-service flow or a service's design as people describe it; a convention for these repos; or background for something another folder holds. Reject a restatement: an input adding nothing to what a doc in the tree's folder already holds (a doc in another folder holding it is dedup, below), or, when no doc in the tree's folder states the same rule, threshold, or contract (one stating a different value is a conflict, below), to what a flow card already holds unless a person or channel is named as its source or it is an imported document (the search below finds the covering path, cards included for this test only, and the answer names it); commentary without a fact, implementation trivia (tests only, renames, formatting, dependency bumps with no behaviour change, log tweaks), and a status update. Downscope when only part is new, routing the new part (a name, a date, a reason the KB lacks) to the file that holds the rest, and say what was dropped. An input that fails several gate tests takes the first reason in this list's order.
- **Decision tree, first match wins.** Something that went wrong in production -> `incidents/`; debt or a risk (security, dependency, compliance, or a failure mode nothing handles) -> `tech-debt/`; an architectural decision with trade-offs -> `adr/`; a rule, policy, threshold, or rollout gate -> `rules/`; an integrating party with no repo under `repos/`, its contract with us included -> `consumers/`; a cross-service end-to-end flow -> `specs/data-flow/`; a per-service design, API, or data model -> `specs/services/`; a convention for implementing or reviewing code in these repos -> `patterns/`; background or rationale for something the other folders hold -> `context/`; otherwise `Rejected: no folder fits - <what it looks like>`, and a standalone call asks the user. `context/` is never a catch-all. The tree decides in both modes; the `Hint` decides only an input that names no kind of its own (a bare table, a list of values). When the tree and the hint disagree, the `Kind` line says `(hint overruled: <reason>)`.
- **Split across folders in `fact` mode.** An input spanning kinds is cut into one piece per kind, each placed by the tree, with reciprocal relative links under `## Related docs`; a rule is never embedded in a spec, and an incident's root cause that states a rule becomes a `rules/` file linked from the incident. In `document` mode the document is placed whole under the tree's answer for its title and first section, and every other kind it contains is listed under `Split candidates` for the caller to report, on a rejection too.
- **Search before create.** Search every curated folder by filename, `tags`, title, headings, and body, in every listed language (the layout's Languages rule). A match is a file in the tree's folder sharing a surface string, constant, or rule text with the input, or the same entity and topic tag (an entity name alone is not enough); most shared wins, then the latest `updated`. Hits in other folders get links (from the written file to the hit) and the conflict check, never the write; a `tech-debt/` item matches only the file of its own service or area. A `deprecated` match hands the write to its `superseded_by` target when that is a root-relative path to an existing doc, else the input counts as unmatched; an `accepted` ADR receives only a `## Related docs` link and the supersede transition below, an input stating a decision that replaces it is created as a new ADR (the Create rule, `supersedes` set), and any other new content for it is `Held: accepted ADR - <path>`. A match is updated: the new content goes into the section whose heading fits (`## Parameters` for a threshold, `## Exceptions` for an exception, `## Items` for a debt item as a new `### {Severity} - {Title}` block, `Unknown` without a severity, `## Timeline` for an incident event), `updated` is bumped to today, surrounding text is preserved, and a whole-document input that adds nothing beyond the match is a restatement.
- **Create from the template.** No match creates the file at the layout's path (an undated incident is `undated-<slug>.md`; an ADR takes the next free `NNNN`) from the kind's `_templates/` file (the layout's skeleton, used in memory and not written, when the file is missing): the H1, `title`, `status: draft`, `created` and `updated` today, `tags` with the kind word of the folder written (`rule`, `incident`, `service`, `data-flow`, `tech-debt`, `adr`, `consumer`, `pattern`, `context`) first, then the input's tags, `imported_from` when supplied, and the sections the input answers. A document's own frontmatter `title` (else its H1, else its file name), `created`, and `status` are kept, `status` mapped onto the curated enum (`draft`, `active`, `deprecated` as they are; `accepted`, `approved`, `final`, `published`, `current` read `active`; `proposed`, `wip`, `review`, `in progress` read `draft`; `obsolete`, `superseded`, `superseded by ...`, `rejected`, `archived`, `retired` read `deprecated`, with `superseded_by` the replacement the document names, else `unknown - not named in source`); a value neither gives (an incident's `severity`, a timeline `{tz}`) reads `unknown`, and an ADR's `> Status:` is the one its body or frontmatter `status` states, mapped the same way onto `accepted` (`accepted`, `approved`, `final`), `superseded` (`superseded`, `superseded by ...`, `deprecated`, `rejected`), else `proposed`. An ADR whose input names the decision it replaces sets `supersedes`, and the old ADR's `> Status:` becomes `superseded`, its `status` `deprecated`, its `superseded_by` the new path. A single fact's `title` is its subject noun phrase (`Refund pending reminder`), its topic tags the entities and surfaces it names.
- **Conflict holds the write.** New content that contradicts a statement in the matched file, or in another curated `rules/`, `specs/`, `consumers/`, `patterns/`, or `tech-debt/` file stating the same rule, threshold, or contract, is held (an incident or ADR is a record of its time and never a conflict source; a different severity, owner, or date on the same item is provenance, not a contradiction): a `## Conflicts` entry names the file, the existing text, and the new text, nothing is overwritten, and the held content is not written elsewhere. In `fact` mode only the conflicting piece is held and the other pieces are written; in `document` mode the whole document is held. A corrected fact the caller marks as a correction (`Citation` names the commit or the person who corrected it) is still a conflict: the user resolves it. A new value with a stated future effective date is not a contradiction: it is written beside the current one with `from <date>` (a Parameters row of its own, or a sentence), the current value untouched.
- **Citations travel verbatim.** A `repos/...:line`, commit, or ticket citation is written into the doc as given, in the place that holds the fact: a rule's enforcement site in `## Enforcement` `Where enforced:` bare (the Link pass matches it as `file:line`), its commit or ticket in the `## Parameters` row's `Notes` or, with no row, in `## Operational notes`, a threshold in its `## Parameters` row's `Notes`, a debt item in its `Location` (the service or component when the input names no line), a flow step at the end of its `Action` cell. A fact from a person is written with `Source: {who or channel, date}` at the end of the sentence or row that holds it. A single fact with no citation and no human source is rejected as `unverifiable`; an imported document, inline text or a file passed by `import` included, is its own source, and its uncited facts are written as they stand.
- **Dedup after write.** When the same statement now sits in two curated files, the file the tree places it in keeps it, and the other file's sentence is replaced by a link to that file; an incident or an ADR is a record of its time and keeps its sentence, gaining a link under `## Related docs` instead, and a copy that adds provenance (a name, a date) is not a duplicate. Links inside curated docs are relative Markdown links (`[rules/refund-window.md](../rules/refund-window.md)` from `incidents/`, `../../rules/...` from a `specs/` subfolder), resolvable from the file that holds them. Every other file this call edits is a `## Files` line `updated - link` (`updated - superseded` for the old ADR of a supersede transition) and bumps its `updated`; on an update, `imported_from` is not added and the section notes `(imported from <path>)` instead.
- **Nothing invented.** Sections the input does not answer keep their template heading and no body; no owner, date, severity, or rationale is filled from what such docs usually say.

## Patterns

### Decision tree examples

Bad - a threshold filed as background, a whole document copied into a folder by name:

```
context/refund-rules.md: created - "Refunds close 7 days after payment"
rules/2026-08-31-refund-double-post.md: created - copied from old-kb/rules/
```

Good - two calls: the threshold is a rule (the file did not yet hold the value); the document's content says incident, whatever its source folder said:

```
- Kind: rules/
- rules/refund-window.md: updated - ## Parameters gained `Window | 7 | days | repos/orders/app/services/refund_service.rb:6 (commit 3f2a1c9)`

- Kind: incidents/ (hint overruled: the title and first section are a dated timeline)
- incidents/2026-08-31-refund-double-post.md: created - from _templates/incident.md
```

### Updating a section

The section is chosen by the template's headings, and content is appended inside it; a table gains a row directly after its last row, a list gains an item after its last item, prose gains a sentence at the section's end. A table section with no rows yet gains its header row with the first row. A section the template lacks is added before `## Related docs`. Frontmatter keys other than `updated` and `tags` (which gains the input's topic tags it lacks) are never changed on an update, the supersede transition excepted.

### Rejections

| Input                                                            | Signal check                                              |
| ---------------------------------------------------------------- | --------------------------------------------------------- |
| "Refunds close after 7 days" when `rules/refund-window.md` says so | `Rejected: restatement of rules/refund-window.md`          |
| "Looks fine to me, ship it"                                       | `Rejected: commentary without a fact`                      |
| "Renamed RefundSvc to RefundService"                              | `Rejected: implementation trivia`                          |
| "Refund cap is 500 now" with no citation and no source           | `Rejected: unverifiable - no citation and no source`       |
| "Refund cap is 500 (per ops, 2026-09-20); also we should rename the job" | `Downscoped: kept the cap; dropped the rename (commentary)` |

## Output Format

```
## Signal check

- {Accepted | Rejected | Downscoped | Held}: {what was kept and, for downscoped, what was dropped; the rejection reason; or, for held, `conflict with <path>` or `accepted ADR - <path>`}
- Kind: {folder, folder | none}{ (hint overruled: <reason>)}
- Existing match: {path, path | none}
- Split candidates: {kind: <section or sentence>, ... | none}

## Files

- {path}: {created | updated} - {what changed}
- held: {piece} - {conflict with {path} | accepted ADR - {path}}
{or}
- No files written. Reason: rejected - {reason}

## Conflicts

- {path}: {existing text} vs {new text}
{or}
- none

## Links added

- {from path} -> {to path} ({reciprocal | dedup | related})
{or}
- none
```

Every block is present on every call. `Split candidates` names kinds by the folder's kind word and reads `none` in `fact` mode. `Kind` names each folder written or held in (from the layout's curated table), `none` on a rejection; in `fact` mode with a split, `Kind` and `Existing match` list one entry per piece in the same order, and `## Files` carries one line per piece written and one `held:` line per piece held. `Held` is the Signal check value when nothing is written because of a conflict or an accepted ADR, and `## Files` then carries only `held:` lines; `Downscoped` when part of the input was dropped as no signal; `Accepted` otherwise. `No files written` appears only on a rejection. A `## Conflicts` entry quotes the sentence or table row that states the existing value. The consuming workflow copies `## Signal check`, `## Files`, and `## Conflicts` into its own report row for the input.

## Avoid

- Copying a file into a folder because that is where its source kept it
- Creating a second file on a topic a search in another language would have found
- Filling a template section with what such a document usually says
