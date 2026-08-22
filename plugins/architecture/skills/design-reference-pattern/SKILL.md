---
name: design-reference-pattern
description: Extract a design-doc house pattern from a company template or an approved prior design - section skeleton, depth, diagram and approval conventions.
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
- **Never invent a house pattern.** No reference means the built-in template and `Source: built-in`. A pattern guessed from one heading is `Confidence: Low`, stated as such.
- **Read narrowly.** Only the supplied references and, at most, one instruction file's pointer section. Do not scan the project for more documents.

## Patterns

### Step 1 - Locate the reference

Precedence, first hit wins:

1. A path or pasted document in the request.
2. A `## Design Docs` section in `./CLAUDE.md`, `.claude/CLAUDE.md`, `./AGENTS.md`, or `./GEMINI.md` (first file carrying one), parsed as key-value lines: `Template:`, `Reference:`, `Approver:`, `Tool:`. `Approver:` fills the reviewer metadata slot; `Tool:` sets the diagram convention's tool when the references themselves show none; any other key is reported under `Other keys` for the caller.
3. Nothing - built-in template.

### Step 2 - Classify what was supplied

Extraction differs by kind. Classify before extracting.

| Kind | Signals | Extract | Never extract |
| --- | --- | --- | --- |
| Blank template | Placeholders, empty sections, author instructions, `<fill in>` | Section skeleton and order verbatim, metadata slots, any stated length or format rule | - |
| Approved prior design | Real content about a real system, sign-off names, a version history | Skeleton, per-section depth, diagram types actually used, tone, terminology, what approved docs omit | Every fact, entity, decision, number, and diagram element in it |
| Not a design doc | It is a PRD, ticket, runbook, or postmortem | Nothing | - |

For "not a design doc": say which artifact it looks like and set it aside; fall back to the built-in template only when no valid reference remains. Either way, continue - do not stop the workflow.

Several references: the most recent approved design wins on depth and tone, a blank template wins on skeleton and metadata slots. Note any divergence in one line.

### Step 3 - Extract the pattern

Pull only these:

- **Section skeleton** - headings verbatim, in order, including ones the workflow would not have produced.
- **Metadata slots** - doc ID, author, status, version history, reviewer list, linked epic or ticket.
- **Depth convention** - bullets or prose, and roughly how much each section carries.
- **Diagram convention** - the tool (Mermaid, PlantUML, draw.io export, screenshots), which diagram types appear, or that none do.
- **Terminology** - the house's naming conventions for systems, environments, teams, and roles ("squads", "PROD", capitalization style) - never a reference system's own proper noun.
- **Tone** - first-person plural, impersonal, or passive.
- **Omissions** - content approved docs never carry. Do not add it to the body; the appendix takes it when the workflow requires it.

A house pattern that omits a section the workflow requires is a placement instruction, not a licence to skip the analysis.

### Step 4 - Map required content to house sections

The caller supplies its required-content list. Map every item to a house section before writing a word of the document. Place an item in a house section only when that heading would let a reader find it; a loose thematic fit misleads more than it helps. Items with no such section resolve as `appended as <name>`; items on the house pattern's Omits list resolve as `appendix` when the caller's deliverable carries one, else `appended as <name>`. Nothing resolves as dropped.

## Output Format

Internal contract. The calling workflow applies it and never emits this block; the document itself follows the skeleton and, when a reference was used, names it on the format line.

```
House pattern:
  Source: {template: <path or pasted> | approved design: <path or pasted> | both | built-in}
  Confidence: {High | Medium | Low}
  Section skeleton: {ordered headings verbatim | built-in}
  Metadata slots: {list | none}
  Depth convention: {per-section note | built-in}
  Diagram convention: {tool and types | none observed}
  Terminology: {house terms | none observed}
  Tone: {first-person plural | impersonal | passive}
  Omits: {content the house pattern never carries | none}
  Other keys: {unrecognized Design Docs keys, verbatim | none}
```

```
Content mapping:
| Required content | House section | Placement |
| --- | --- | --- |
| <caller's item> | <house heading> | {placed | appended as <name> | appendix} |
```

Contract: every required-content item the caller supplied appears as a row. `Confidence` is `Low` for a single partial reference or a skeleton inferred from fewer than three headings, `Medium` for one complete reference, `High` for a blank template plus at least one approved design.

## Avoid

- Copying content, examples, or diagram elements out of a filled reference
- Adding sections the house pattern does not have "for completeness" - map them or append them with a stated reason
- Dropping required substance because the template has no slot for it
- Reporting a confident pattern from a partial paste
- Reproducing a reference's defects (a missing rollback section, an unowned risk) as if they were house style
