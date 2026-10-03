---
name: domain-flow-explain
description: "Render a flow card, capability, or rule from the domain knowledge base as a lesson: story, what happens, rules with reasons, surprises, symptoms."
metadata:
  category: domain
  tags: [domain, lesson, explain, flow-card, learning]
user-invocable: false
---

# Domain Flow Explain

> Load `Use skill: domain-kb-layout` first and read at least its Rules and these Patterns sections: Flow card, capability.md, ATLAS.md, Generated-file frontmatter, Curated layer, Templates, Stale marking, and the Ledger, playbook, contracts, debt, surfaces entry for `ledger/rules.md`. It owns every path, frontmatter key, section shape, and empty form this skill reads; the lesson shapes below are this skill's own.

Turns one knowledge-base artifact into a lesson a person can read once and explain back. It renders what the artifact holds; it never traces, searches, or infers beyond it.

## When to Use

- `task-domain-explain <name>` rendering a flow, capability, or rule
- `task-domain-ask` given a bare name instead of a question
- Standalone: a path, an id, or a bare flow name given by the user

## Inputs

| Input   | Required | Notes                                                                                                                                     |
| ------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Target  | yes      | A flow card path or `<capability>/<flow>`; a bare flow id or alias; a `capability.md` path or capability id; a rule id `R-<n>`             |
| KB root | yes      | `ATLAS.md`, `ledger/rules.md`, `capabilities/` (for bare-name resolution and the cards a capability lists), and the curated docs the target names: every `rules/` file a Rules row's `Doc` or a ledger row's `Doc` points at, every `doc:` and `consumer:` entry under the card's `## Related`, and the `superseded_by` target of any deprecated doc among them |
| Languages | no       | The `## Audience` `Language:` list from `CLAUDE.md`, `en` when absent; the first is the output language, and a bare name is matched against aliases in every listed language as written, never translated |

## Rules

- **Resolve the target first.** A `<capability>/<flow>` id is matched as written, its capability part also by that capability's aliases; a bare name or id is matched exactly, ignoring case, against every capability id and alias (the `capabilities/` directories, plus the capability names ATLAS `### Untraced` and `CLAUDE.md` `## Capabilities` list) and every flow id and alias at once. One match emits `resolved: <capability>` or `resolved: <capability>/<flow>` as the first line and the lesson follows; several, a capability and a flow included, emit `ambiguous: <id>, <id>` (capability ids and `<capability>/<flow>` ids) and nothing else; none emits `no match for <name> - see ATLAS.md` and nothing else. A path, an `R-<n>` id, or a `<capability>/<flow>` typed as written needs no resolution line; one typed through a capability alias gets it. A rule or debt id the card still writes as `R-new` or `D-new` is rendered as written. A missing source is reported in one line and nothing else is emitted: `no card for <name> - run task-domain-sync` for a flow, `no capability file for <name> - run task-domain-sync` for a capability, `no ledger row <id> - run task-domain-sync` for a rule. A standalone call opens with the layout's Sync line when `_index/sync-state.json` records a non-null `in_progress` (the Sync line precedes even an output emitted alone, and every `run task-domain-sync` remedy then reads `run task-domain-sync --resume`), and when it records no `sha` emits only `no completed sync yet - {command}:{pass} unfinished; when no sync is running, run task-domain-sync --resume` (a non-null `in_progress`) or `no knowledge base here - run task-domain-sync init`.
- **Render, never research.** Every statement comes from the target file, the cards a capability lists, the ledger, the curated docs the target links (`Doc` cells, `doc:` and `consumer:` entries), or ATLAS; a linked doc that does not exist renders as `doc missing: <path>` in the line the doc would have filled (the From the docs line, the Background or Who calls this line; a missing incident is one Background line, having no text to match a row), the Rules cell keeping the card's text, and nothing is searched for. A citation the source row carries (`file:line`, a path) is kept in the slot that has room for it: the parenthesis after a step, the end of a rule's `Why` cell, the `Where` column, the surprise line, the Monitor cell; a hop's `(unverified)` or `(external - not in repos)` marker travels with its step. A card whose `freshness` is `stale` renders `stale since {date}` in its Status line, the date being the first (oldest) `## Changed since` row's, and its `## Changed since` rows under Read next. A card whose `freshness` is `orphaned` renders `orphaned - frozen at {synced}` and, its body being frozen, emits only the header bullets, the Story, and Read next.
- **Plain words first.** Prose and numbered steps carry the lesson; tables condense, they do not introduce. The one-sentence summary is the card's Story verbatim, both sentences when it has two, even when it names a service; every other service and endpoint name sits in What happens. Text from a doc in another listed language is rendered in the output language; the Story is never translated.
- **Rules come from the card**, one lesson row per card row, keeping the card's `Id`; then one row per ledger rule whose `Flows` names the flow and that no card row holds (a `process`, `policy`, or `rollout gate` rule), with the ledger's `Id`, `Rule`, `Rationale`, `Confidence`, `Quirk`, and `Doc`, after the card rows in ledger order, which is their card order wherever this skill says card order. Both kinds of row follow the linked-docs rule.
- **Surprises are chosen by rule, in this order, three at most:** rules with `Quirk: yes`; rules with `Confidence: unknown`; failure modes whose `Detected by` reads a `none` or `unknown` form; edge branches with `Exercised in traces: no`; Debt rows whose class is `trace differs`. Fewer candidates yield fewer surprises, never padding.
- **Questions are derived, not invented.** At most five: rules first in card order, then failure modes, keeping at least one failure mode when the card has any; each restates its row as a stakeholder would ask it, and its answer cites the row.
- **Linked docs are rendered inline, in the section they belong to.** A Rules row whose `Doc` is a path takes the first sentence of the doc's `## Statement` as its `Rule` cell, and a `From the docs` line under the table carries the doc's `Does NOT apply to` (from `## Scope`) and `## Exceptions` in plain words (a section the doc leaves empty is skipped); when the Statement says more than the card's rule text, the line adds `card: <card rule text>` (card rows only). When the two contradict, the `Rule` cell keeps the card's text and the line reads `doc disagrees: <Statement> - drift`, since a card citation outranks the doc. A `draft` doc is rendered with `(draft)` after its path; a `deprecated` doc is rendered from its `superseded_by` target, the line ending `({target path}; supersedes {deprecated path})` (a missing target renders `doc missing: <target path>`). A `doc:` incident is the `Past incident` (its path) of every `When it breaks` row whose failure, symptom, or surface its text names, and one `Background` line when it names none. Any other `doc:` file not rendered above is one `Background` line: its title and the first sentence of its first section, or of `## Decision` for an ADR. A `consumer:` doc is one `Who calls this` line from its `## Who` and `## Sharp edges`. Each rendered line ends with the doc path. The reader never has to open the second folder to finish the lesson.
- **Only the target kind's sections are emitted.** The prose cap counts the free text the lesson writes, never steps, diagrams, tables, or doc lines: in a flow lesson the Story (both sentences), the surprises, and the questions, 400 words; in a capability lesson the Purpose, 250; in a rule lesson the `Rule` and `Why` bullets, 150.

## Patterns

### Flow lesson

`What happens` is the hop list rewritten as plain-language steps, one per hop, each ending with its citation (none when the card's line has none); branch sub-items become indented sub-steps; for a schedule or message trigger with no entry hop, step 1 is the trigger with its Surface citation. `What changes` condenses State changes to entity, from, to, the guard in plain words, and the citation, then one row per Side effects row (`Entity` its kind and target, `From` and `To` empty, `Because` its `When`, `Where` its citation). `The rules, and why` takes one row per rule with the rationale in a sentence ending with its citation, and a `Rule` cell starting `quirk:` for a row with `Quirk: yes`. `When it breaks` pairs each failure mode's `User sees` with its `First check`, names the monitor or capture string from `Detected by`, or writes `no signal`, and fills `Past incident` per the linked-docs rule, else `none`. `Known debt` takes one line per card Debt row, its finding in plain words and its citation. `Background` holds one line per `doc:` entry the other sections did not render; `Who calls this` holds one line per `consumer:` entry. Under Read next, the ATLAS `Read before` flow comes first (a `none` adds no entry), a Related entry that reads `flow to trace:` renders as `not yet traced: <kind>: <surface>`, every `doc:` and `consumer:` path is repeated, `R-n` entries are not, and a `## Changed since` row renders `- changed {date}: {commit} - {files}`.

Bad - the card's row with its cells copied:

```
| R-1 | Refund window is 7 days after paid_at | code | repos/orders/app/services/refund_service.rb:6 | rules/refund-window.md | Finance wanted a cut-off support can quote (adr/0007-refund-window.md) | documented | no |
```

Good - the same row as a sentence a person can repeat, its `Rule` cell the first sentence of `rules/refund-window.md`'s Statement:

```
| R-1 | A paid order can be refunded for 7 days after payment | Finance wanted a cut-off support can quote (adr/0007-refund-window.md; repos/orders/app/services/refund_service.rb:6) | documented |

- **From the docs:** R-1: does not apply to orders in production or shipped orders; exceptions: supervisor override in production (rules/refund-window.md)
```

### Capability lesson

Purpose, the services and their roles, the flows in ATLAS order each with its Story, both sentences (`(orphaned)` after an orphaned one), then each ATLAS `### Untraced` trigger of the capability as `not yet traced: <kind>: <surface>`, the top risks from `capability.md`, and Read next: the first flow of the capability, then the next capability on the ATLAS learning path (the overview item is not a capability) or `none - last on the learning path`. Status is `orphaned - frozen at {synced}` for an orphaned capability, `stale ({n} of {m} flows)` when any listed card is stale, else `current`.

### Rule lesson

The rule in a sentence, its kind, where it is enforced, why (with confidence), which flows it shapes, whether it is a quirk, and who touched it last. When the ledger row's `Doc` names a `rules/` file, the lesson also renders that doc's `## Statement`, `## Scope`, `## Parameters`, and `## Exceptions` in plain words, each cited by the doc path; when `Doc` is `none`, those four lines are absent.

## Output Format

Flow target:

```markdown
resolved: {capability}/{flow}                          {only when a bare name or alias was resolved}

# Lesson: {Flow name}

- **Flow:** {capability}/{flow}
- **Priority:** {n | unranked}
- **Status:** {current | stale since {date} | orphaned - frozen at {synced}}

**In one sentence:** {Story, verbatim}

## What happens

1. {plain-language step} ({file:line}{ marker})
   - {branch step} ({file:line}{ marker})

{Mermaid sequenceDiagram copied from the card}

## What changes

| Entity | From | To | Because | Where |
| ------ | ---- | -- | ------- | ----- |

## The rules, and why

| Id | Rule | Why | Confidence |
| -- | ---- | --- | ---------- |

- **From the docs:** {R-n: does not apply to ...; exceptions: ...{; card: <card rule text> | ; doc disagrees: <Statement> - drift} ({doc path}{ (draft)})}    {one line per rule with a Doc; absent when none has one}

## What will surprise you

1. {surprise - source section and row}{ - file:line}

## When it breaks

| You will hear | Look first | Monitor | Past incident |
| ------------- | ---------- | ------- | ------------- |

## Known debt

- {D-n - finding in plain words ({file:line})}

## Background                                          {only when a doc: entry is left after the other sections}

- {title - first sentence of its first section, an ADR's ## Decision ({doc path})}

## Who calls this                                      {only when the card has a consumer: entry}

- {who - sharp edges in one sentence ({doc path})}

## See it yourself

- **Screens:** {from the card}
- **Job:** {from the card}
- **Log lines:** {from the card}
- **Tables to inspect:** {from the card}

## Questions you can now answer

- {question} - {answer} ({row cited})

## Read next

- {Read before flow from ATLAS, then Related entries, then Changed since rows on a stale card}
```

Capability target: the `resolved:` line when one was emitted, `# Lesson: {Capability}`, `- **Status:** {current | stale ({n} of {m} flows) | orphaned - frozen at {synced}}`, `**Purpose:**`, `## Services` (`| Service | Role |`), `## Flows in order` (numbered, each `{capability}/{flow} - {Story}{ (orphaned)}`, then one `- not yet traced: {kind}: {surface}` line per ATLAS `### Untraced` trigger of the capability), `## Top risks` (numbered), `## Read next`.

Rule target: `# Lesson: {R-n}`, then bullets `**Rule:**` (the ledger's `Rule` text), `**Kind:**`, `**Enforced at:**`, `**Why:**` (ending `- {confidence}`), `**Shapes:**` (flows), `**Quirk:**` (`yes` or `no`), `**Last touched:**`, `**Doc:**` (path or `none`); then, only when `Doc` is a path, `**Statement:**` (ending `; doc disagrees - drift` when it contradicts the ledger's `Rule`), `**Scope:**`, `**Parameters:**`, `**Exceptions:**`, each from the doc's section and ending `({doc path}{ (draft)})`, a section the doc leaves empty reading `none - not filled in the doc`; a missing doc makes `**Statement:**` read `doc missing: <path>` and the other three absent.

An empty section takes the layout's empty form (a table keeps its header and one `none - <evidence>` row; a list, numbered or not, reads `- none - <evidence>`); a section annotated `{only when ...}` is absent instead. `Priority` reads `unranked` for a card whose `priority` is `0`.

## Avoid

- Re-tracing or reading repo code to fill a gap the card left
- Searching the curated folders for a doc the card does not link
- Restating a card table cell for cell instead of rewriting it as a sentence
- Ranking surprises by interest instead of the rule order
- Emitting the card itself, or its frontmatter, as part of the lesson
