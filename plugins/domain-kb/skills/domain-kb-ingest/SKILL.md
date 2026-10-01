---
name: domain-kb-ingest
description: "Classify a fact or document into the curated knowledge base: signal gate, decision tree, search before create, conflict flag, dedup, citations."
metadata:
  category: domain
  tags: [domain, knowledge-base, ingest, classify, curated, dedup, conflict]
user-invocable: false
---

# Domain KB Ingest

> Load `Use skill: domain-kb-layout` first: it owns every path, frontmatter key, section shape, and empty form this skill reads or emits.

Places one input, a single fact or a whole document, into the curated layer `domain-kb-layout` defines: decides whether it is knowledge at all, which folder it belongs to, whether a file already covers it, and writes or updates exactly the files that result. It is the only writer of the curated layer; nothing reaches that layer by copy, script, or shell loop.

## When to Use

- `task-domain-sync import` for inline text, one file, or every file of a foreign knowledge base
- `task-domain-sync` Distil pass (`update`), for each cited candidate fact from the commit window
- `task-domain-ask` with `save` on a pasted message that is a durable fact
- Standalone: one fact or one file named by the user

## Inputs

| Input     | Required | Notes                                                                                                                                       |
| --------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Text      | yes      | One fact in a sentence or paragraph, or a document body with or without frontmatter                                                         |
| Citation  | no       | `repos/<repo>/<path>:<line>`, a commit short SHA, a ticket id, or `Source: {who or channel, date}` for a fact that came from a person         |
| Hint      | no       | A target kind (`rule`, `incident`, `service`, `data-flow`, `tech-debt`, `adr`, `consumer`, `pattern`, `context`); a source folder name is a hint, never a decision |
| Mode      | no       | `fact` (default): the cross-folder split applies; `document`: the input is placed whole under its dominant kind and split candidates are only reported |
| Imported from | no   | For an imported document, its source path as the caller resolved it; written as `imported_from` on a file this call creates |
| KB root   | yes      | The curated folders, `_templates/`, and, when present, the generated layer for the restatement check                                    |
| Languages | no       | The `## Audience` `Language:` list; default `en`; every code is a search language                                                            |

## Rules

- **One call, one input, files written by this skill alone.** A document is ingested whole as `Text` in one call; a batch is one call per file, and no call reads another call's result. No script, shell loop, or bulk copy writes a curated file, and the caller reports this skill's `## Signal check`, `## Files`, and `## Conflicts` for every file. A file whose only change is a path move is still ingested, not moved.
- **Signal gate, decided before any write.** Accept when the input adds a rule, threshold, or policy; a contract or data shape; a failure mode, a risk, or an incident fact; a decision with trade-offs; a corrected fact that contradicts a doc; a consumer's integration fact; or a debt item. Reject a restatement of what a curated doc already holds, or what a flow card already holds when the input carries nothing a person vouches for (an imported document is vouched for by its authors) (the search below finds the covering path, cards included for this test only, and the answer names it), commentary without a fact, implementation trivia (tests only, renames, formatting, dependency bumps with no behaviour change, log tweaks), and a status update. Downscope when only part is new, routing the new part (a name, a date, a reason the KB lacks) to the file that holds the rest, and say what was dropped.
- **Decision tree, first match wins.** Something that went wrong in production -> `incidents/`; debt or a risk (security, dependency, compliance, or a failure mode nothing handles) -> `tech-debt/`; an architectural decision with trade-offs -> `adr/`; a rule, policy, threshold, or rollout gate -> `rules/`; an integrating party with no repo under `repos/`, its contract with us included -> `consumers/`; a cross-service end-to-end flow -> `specs/data-flow/`; a per-service design, API, or data model -> `specs/services/`; a convention for implementing or reviewing code in these repos -> `patterns/`; background or rationale for something the other folders hold -> `context/`; otherwise `Rejected: no folder fits - <what it looks like>`, and a standalone call asks the user. `context/` is never a catch-all. The tree decides in both modes; the `Hint` decides only an input that names no kind of its own (a bare table, a list of values). When the tree and the hint disagree, the `Kind` line says `(hint overruled: <reason>)`.
- **Split across folders in `fact` mode.** An input spanning kinds is cut into one piece per kind, each placed by the tree, with reciprocal relative links under `## Related docs`; a rule is never embedded in a spec, and an incident's root cause that states a rule becomes a `rules/` file linked from the incident. In `document` mode the document is placed whole under the tree's answer for its title and first section, and every other kind it contains is listed under `Split candidates` for the caller to report, on a rejection too.
- **Search before create.** Search every curated folder by filename, `tags`, title, headings, and body, in every listed language (the layout's Languages rule). A match is a file in the tree's folder sharing a surface string, constant, or rule text with the input, or the same entity and topic tag (an entity name alone is not enough); most shared wins, then the latest `updated`. Hits in other folders get links and the conflict check, never the write. A `deprecated` match hands the write to its `superseded_by` target; an `accepted` ADR is never updated, and new content for it is `Held: accepted ADR - <path>`. A match is updated: the new content goes into the section whose heading fits (`## Parameters` for a threshold, `## Exceptions` for an exception, `## Items` for a debt item as a new `### {Severity} - {Title}` block, `Unknown` without a severity, `## Timeline` for an incident event), `updated` is bumped to today, surrounding text is preserved, and a whole-document input that adds nothing beyond the match is a restatement.
- **Create from the template.** No match creates the file at the layout's path (an undated incident is `undated-<slug>.md`; an ADR takes the next free `NNNN`) from the kind's `_templates/` file (written from the layout's skeleton when missing): the H1, `title`, `status: draft`, `created` and `updated` today, `tags` with the kind word of the folder written (`rule`, `incident`, `service`, `data-flow`, `tech-debt`, `adr`, `consumer`, `pattern`, `context`) first, then the input's tags, `imported_from` when supplied, and the sections the input answers. A document's own frontmatter `title`, `created`, and `status` (mapped to the curated enum) are kept; a value neither gives (an incident's `severity`, a timeline `{tz}`) reads `unknown`, and an ADR's `> Status:` reads `proposed`.
- **Conflict holds the write.** New content that contradicts a statement in the matched file, or in another curated file stating the same rule, threshold, or contract, is held: a `## Conflicts` entry names the file, the existing text, and the new text, nothing is overwritten, and the held content is not written elsewhere. In `fact` mode only the conflicting piece is held and the other pieces are written; in `document` mode the whole document is held. A corrected fact the caller marks as a correction (`Citation` names the commit or the person who corrected it) is still a conflict: the user resolves it. A new value with a stated future effective date is not a contradiction: it is written beside the current one with `from <date>` (a Parameters row of its own, or a sentence), the current value untouched.
- **Citations travel verbatim.** A `repos/...:line`, commit, or ticket citation is written into the doc as given, in the place that holds the fact: a rule's enforcement site in `## Enforcement` `Where enforced:` with its commit or ticket after it in parentheses, a threshold in its `## Parameters` row's `Notes`, a debt item in its `Location` (the service or component when the input names no line), a flow step at the end of its `Action` cell. A fact from a person is written with `Source: {who or channel, date}` at the end of the sentence or row that holds it. A single fact with no citation and no human source is rejected as `unverifiable`; an imported document is its own source, and its uncited facts are written as they stand.
- **Dedup after write.** When the same statement now sits in two curated files, the file the tree places it in keeps it, and the other file's sentence is replaced by a link to that file; an incident or an ADR is a record of its time and keeps its sentence, gaining a link under `## Related docs` instead, and a copy that adds provenance (a name, a date) is not a duplicate. Links inside curated docs are relative Markdown links (`[rules/refund-window.md](../rules/refund-window.md)`), resolvable from the file that holds them. Every other file this call edits is a `## Files` line `updated - link` and bumps its `updated`; on an update, `imported_from` is not added and the section notes `(imported from <path>)` instead.
- **Nothing invented.** Sections the input does not answer keep their template heading and no body; no owner, date, severity, or rationale is filled from what such docs usually say.

## Patterns

### Decision tree examples

Bad - a threshold filed as background, a whole document copied into a folder by name:

```
context/refund-rules.md: created - "Refunds close 7 days after payment"
rules/2026-08-31-refund-double-post.md: created - copied from old-kb/rules/
```

Good - two calls: the threshold is a rule; the document's content says incident, whatever its source folder said:

```
- Kind: rules/
- rules/refund-window.md: updated - ## Parameters gained `Window | 7 | days | repos/orders/app/services/refund_service.rb:6 (commit 3f2a1c9)`

- Kind: incidents/ (hint overruled: the body is a timeline with a root cause)
- incidents/2026-08-31-refund-double-post.md: created - from _templates/incident.md
```

### Updating a section

The section is chosen by the template's headings, and content is appended inside it; a table gains a row directly after its last row, a list gains an item after its last item, prose gains a sentence at the section's end. A section the template lacks is added before `## Related docs`. Frontmatter keys other than `updated` and `tags` are never changed on an update.

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

- {Accepted | Rejected | Downscoped | Held}: {what was kept and, for downscoped, what was dropped; the rejection reason; or, for held, `conflict with <path>`}
- Kind: {folder, folder | none}{ (hint overruled: <reason>)}
- Existing match: {path, path | none}
- Split candidates: {kind: <section or sentence>, ... | none}

## Files

- {path}: {created | updated} - {what changed}
- held: {piece} - conflict with {path}
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

Every block is present on every call. `Kind` names each folder written or held in (from the layout's curated table), `none` on a rejection; in `fact` mode with a split, `Kind` and `Existing match` list one entry per piece in the same order, and `## Files` carries one line per piece written and one `held:` line per piece held. `Held` is the Signal check value when nothing is written because of a conflict, and `## Files` then carries only `held:` lines; `Downscoped` when part of the input was dropped as no signal; `Accepted` otherwise. `No files written` appears only on a rejection. The consuming workflow copies `## Signal check`, `## Files`, and `## Conflicts` into its own report row for the input.

## Avoid

- Copying a file into a folder because that is where its source kept it
- Creating a second file on a topic a search in another language would have found
- Filling a template section with what such a document usually says
- Resolving a contradiction by overwriting the older statement
- Writing a single fact with no citation and no named source
