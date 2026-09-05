---
name: design-reference-pattern
description: Extract a design-doc house pattern from a company template or an approved prior design - section skeleton, depth, diagram and metadata conventions.
metadata:
  category: architecture
  tags: [design, template, house-style, documentation, approval]
user-invocable: false
---

# Design Reference Pattern

## When to Use

- A design workflow has a company template, an approved prior design, or both, and the deliverable must look like the ones the organization already approves.
- No reference exists - this skill still runs and returns the built-in fallback, so callers keep one code path.

## Rules

- **A reference supplies shape, not substance.** Never carry a fact, entity name, decision, number, or diagram element from a filled reference into the new document. Contamination is this skill's primary failure mode.
- **House structure wins on shape; required substance is never dropped.** Content the workflow requires that has no house section goes in the nearest fitting one, or in a clearly named section appended at the end - with one line saying why it was added.
- **Never invent a house pattern.** No usable reference means the built-in template and `Source: built-in`; a reference that was supplied but rejected is still named under `Rejected`, so the caller can see it was considered. A pattern guessed from one heading is `Confidence: Low`, stated as such.
- **Read narrowly.** Only the supplied references and, at most, one instruction file's pointer section. Do not scan the project for more documents.

## Patterns

### Step 1 - Locate the reference

Precedence for the REFERENCE DOCUMENTS:

1. A path or pasted document in the request.
2. `Template:` and `Reference:` in a `## Design Docs` section (see below).
3. Nothing - built-in template.

A request-supplied reference wins its own kind: a pasted template supersedes a `Template:` pointer, and the superseded one is named under `Rejected`. It does not discard a reference of the other kind, so a pasted template and a `Reference:` approved design are both used.

Read `## Design Docs` whenever one exists, even when a request-supplied reference already won - it carries metadata no reference document supplies. Look in `./CLAUDE.md`, `.claude/CLAUDE.md`, `./AGENTS.md`, or `./GEMINI.md` (first file carrying one), as key-value lines. `Template:` and `Reference:` are classified by Step 2, not by key name, so a `Template:` pointing at a filled doc is an approved design. `Approver:` fills `Reviewer`, `Tool:` fills the diagram tool, and any other key goes to `Other keys`. Where a key contradicts what the references show, keep the references' value and record the clash in `Divergence`.

### Step 2 - Classify what was supplied

Extraction differs by kind. Classify before extracting.

| Kind | Signals | Extract | Never extract |
| --- | --- | --- | --- |
| Blank template | Placeholders, empty sections, author instructions, `<fill in>` | Section skeleton and order verbatim, metadata slots, any stated length or format rule | - |
| Approved prior design | Real content about a real system, sign-off names, a version history | Skeleton, per-section depth, diagram types actually used, tone, terminology, what approved docs omit | Every fact, entity, decision, number, and diagram element in it |
| Not a design doc | It is a PRD, ticket, runbook, or postmortem | Nothing | - |

For "not a design doc": name which artifact it looks like in `Rejected` and set it aside; fall back to the built-in template only when no valid reference remains. A fragment matching no kind's signals classifies as the nearest kind and caps `Confidence` at Low. Either way, continue - do not stop the workflow.

Several references: the most recent approved design wins on depth and tone, a blank template wins on skeleton and metadata slots. Record any divergence in `Divergence`.

### The built-in template

Used when no valid reference remains. Skeleton: Context and Problem; Goals and Non-Goals; Current State; Proposed Design; Alternatives Considered; Risks and Rollback; Operational Impact; Open Questions. Metadata slots: author, status, reviewers. Depth: prose for Context and Proposed Design, bullets elsewhere. Diagrams: Mermaid, one current state and one target. Tone: first-person plural. `Omits: none`, since it withholds nothing by convention - but eight headings will not fit every caller's list, so an item with no findable home is still appended.

### Step 3 - Extract the pattern

Pull only these:

- **Section skeleton** - headings verbatim, in order, including ones the workflow would not have produced. Where the reference is a fragment whose numbering implies sections you cannot see, record the gap in the skeleton as `<unseen>` at that position rather than renumbering.
- **Metadata slots** - the doc's identifying fields: doc ID, author, status, reviewer list, linked epic or ticket, and a version history. A metadata block rendered as a heading (`## Version History`) is a metadata slot, not a skeleton section.
- **Depth convention** - bullets or prose, and roughly how much each section carries.
- **Diagram convention** - the tool (Mermaid, PlantUML, draw.io export, screenshots), which diagram types appear, or that none do.
- **Terminology** - the house's naming conventions for systems, environments, teams, and roles ("squads", "PROD", capitalization style) - never a reference system's own proper noun.
- **Tone** - first-person plural, impersonal, or passive.
- **Omits** - content approved docs never carry. Where the skeleton has a heading the approved designs leave empty, the heading wins for placement and `Omits` records that the house rarely fills it; `Omits` diverts an item only when no heading exists for it at all.

A house pattern that omits a section the workflow requires is a placement instruction, not a licence to skip the analysis.

### Step 4 - Map required content to house sections

The caller supplies its required-content list, and states whether its deliverable carries an appendix; absent that, assume it does not. Map every item to a house section before writing a word of the document. Place an item in a house section only when that heading would let a reader find it; a loose thematic fit misleads more than it helps. Items with no such section resolve as `appended as <name>`; items on the house pattern's Omits list resolve as `appendix` when the deliverable carries one, else `appended as <name>`. Nothing resolves as dropped.

Items a single reader would look for in one place go in one appended section - a data migration plan and a rollback plan are both "how we get there and back"; a security sign-off is not. Unrelated items get their own. Name an appended section for what it holds, and never reuse a house heading that already exists elsewhere in the skeleton. Each appended section carries its reason in the mapping row.

## Output Format

Internal contract. The calling workflow applies it and never emits this block. Three things reach the document: the skeleton, the `Attribution` line, and one line under each appended section saying why it was added - the mapping table's `Reason` is where that line is drafted.

```
House pattern:
  Source: {one line per reference used - "template: <path or pasted>" | "approved design: <path or pasted>" | the single line "built-in"}
  Rejected: {one line per supplied reference not used - <path or paste> followed by the artifact it looks like, or "superseded by <which>" | "none"}
  Confidence: {High | Medium | Low}
  Section skeleton: {ordered headings verbatim, with "<unseen>" where a fragment's numbering implies a section you cannot see | built-in (see The built-in template)}
  Metadata slots: {slot names the pattern carries, e.g. doc ID, author, status, reviewers | none}
  Reviewer: {the Approver value, whether or not the pattern has a slot for it | none supplied}
  Depth convention: {per-section note | built-in}
  Diagram convention: {tool and types | tool only, no diagrams observed | none observed}
  Terminology: {house terms | none observed}
  Tone: {first-person plural | impersonal | passive | none observed}
  Omits: {content the house pattern has no heading for | none}
  Divergence: {one line per disagreement between references or against a Design Docs key | none}
  Other keys: {unrecognized Design Docs keys, verbatim | none}
  Attribution: {one sentence naming every reference followed, or "built-in template"}
```

```
Content mapping:
| Required content | House section | Placement | Reason |
| --- | --- | --- | --- |
| <caller's item> | <house heading, or "-" when not placed> | {placed | appended as <name> | appendix} | {"-" when placed | why otherwise} |
```

Contract: every required-content item the caller supplied appears as a row, and `Attribution` is assembled from `Source` once Step 4 completes. Metadata slots names the slots, never their values - the sole value carried out of a reference is `Approver`, which has its own field, because everything else in a filled reference is contaminating content.

`Confidence` is decided on the best evidence available, then capped:

- `High` - a blank template plus at least one complete approved design.
- `Medium` - one complete reference of either kind, or several of the same kind.
- `Low` - every reference is partial, a skeleton was inferred from fewer than three headings, a fragment was classified as its nearest kind, or the built-in fallback was used.

A partial reference alongside a complete one does not force Low; it caps the aspects it contributes, so note that in `Divergence`.

## Avoid

- Copying content, examples, or diagram elements out of a filled reference
- Adding sections the house pattern does not have "for completeness" - map them or append them with a stated reason
- Dropping required substance because the template has no slot for it
- Reporting a confident pattern from a partial paste
- Reproducing a reference's defects (a missing rollback section, an unowned risk) as if they were house style
