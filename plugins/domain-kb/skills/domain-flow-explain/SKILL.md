---
name: domain-flow-explain
description: Render a flow card, capability, or rule from the domain knowledge base as a lesson: story, what happens, rules with reasons, surprises, symptoms.
metadata:
  category: domain
  tags: [domain, lesson, explain, flow-card, learning]
user-invocable: false
---

# Domain Flow Explain

Turns one knowledge-base artifact into a lesson a person can read once and explain back. It renders what the artifact holds; it never traces, searches, or infers beyond it.

## When to Use

- `task-domain-explain <name>` rendering a flow, capability, or rule
- `task-domain-ask` given a bare name instead of a question
- Standalone: a path, an id, or a bare flow name given by the user

## Inputs

| Input   | Required | Notes                                                                                                                                     |
| ------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Target  | yes      | A flow card path or `<capability>/<flow>`; a bare flow id or alias; a `capability.md` path or capability id; a rule id `R-<n>`             |
| KB root | yes      | `ATLAS.md`, `ledger/rules.md`, `capabilities/` (for bare-name resolution and the cards a capability lists), and the hand-written `rules/` doc a ledger row's `Doc` names |

## Rules

- **Resolve the target first.** A bare name is matched against capability ids and aliases, then flow ids and aliases across every capability; one match emits `resolved: <id>` as the first line and the lesson follows; several are listed as `ambiguous: <candidates>` and nothing else is emitted. A rule id the card still writes as `R-new` is rendered as `R-new`. A missing source is reported in one line and nothing else is emitted: `no card for <name> - trace it first` for a flow, `no capability file for <name> - sync first` for a capability, `no ledger row <id> - sync first` for a rule.
- **Render, never research.** Every statement comes from the target file, the ledger, the `rules/` doc a ledger row's `Doc` names, or ATLAS. A citation the source row carries (`file:line`, a path) is kept in the slot that has room for it: the parenthesis after a step, the `Where` column, the surprise line, the Monitor cell; a hop's `(unverified)` or `(external - not in repos)` marker travels with its step. A card whose `freshness` is `stale` renders `stale since {date}` in its Status line, the date being the first `## Changed since` row's, and its `## Changed since` rows under Read next. A card whose `freshness` is `orphaned` renders `orphaned - frozen at {synced}`.
- **Plain words first.** Prose and numbered steps carry the lesson; tables condense, they do not introduce. Service and endpoint names appear in What happens, never in the one-sentence summary, which is the card's Story verbatim, both sentences when it has two.
- **Rules come from the card**, one lesson row per card row, keeping the card's `Id`.
- **Surprises are chosen by rule, in this order, three at most:** rules with `Quirk: yes`; rules with `Confidence: unknown`; failure modes whose `Detected by` reads a `none` or `unknown` form; edge branches with `Exercised in traces: no`; Debt rows whose finding starts `trace differs`. Fewer candidates yield fewer surprises, never padding.
- **Questions are derived, not invented.** At most five: rules first in card order, then failure modes, keeping at least one failure mode when the card has any; each restates its row as a stakeholder would ask it, and its answer cites the row.
- **Only the target kind's sections are emitted.** The prose cap counts the Story, the surprises, and the questions only, never steps, diagram, or tables: 400 words for a flow lesson, 250 for a capability, 150 for a rule.

## Patterns

### Flow lesson

`What happens` is the hop list rewritten as plain-language steps, one per hop, each ending with its citation; branch sub-items become indented sub-steps. `What changes` condenses State changes to entity, from, to, the guard in plain words, and the citation. `The rules, and why` takes one row per card rule with the rationale in a sentence, and the word `quirk` in front of any row with `Quirk: yes`. `When it breaks` pairs each failure mode's `User sees` with its `First check`, and names the monitor or capture string from `Detected by`, or writes `no signal`. A Related entry that reads `flow to trace:` renders as `not yet traced: <kind>: <surface>`; a `doc:` or `consumer:` entry renders as its path under Read next.

Bad - a table with the card's cells copied:

```
| Refund window is 7 days after paid_at | repos/orders/app/services/refund_service.rb:6 | adr/0007 | documented | no |
```

Good - a sentence a person can repeat:

```
| R-1 | Refunds close 7 days after payment | Finance wanted a cut-off support can quote (ADR-0007, refund_service.rb:6) | documented |
```

### Capability lesson

Purpose, the services and their roles, the flows in ATLAS order each with its Story sentence (`not yet traced` when its card is absent), the top risks from `capability.md`, and Read next: the first flow of the capability, then the next capability on the ATLAS learning path or `none - last on the learning path`. A capability's Status is its frontmatter `freshness`.

### Rule lesson

The rule in a sentence, its kind, where it is enforced, why (with confidence), which flows it shapes, whether it is a quirk, and who touched it last. When the ledger row's `Doc` names a `rules/` file, the lesson also renders that doc's `## Statement`, `## Scope`, `## Parameters`, and `## Exceptions` in plain words, each cited by the doc path; when `Doc` is `none`, those four lines are absent.

## Output Format

Flow target:

```markdown
# Lesson: {Flow name}

- **Flow:** {capability}/{flow}
- **Priority:** {n}
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

## What will surprise you

1. {surprise - source section and row - file:line when the row has one}

## When it breaks

| You will hear | Look first | Monitor |
| ------------- | ---------- | ------- |

## See it yourself

- **Screens:** {from the card}
- **Job:** {from the card}
- **Log lines:** {from the card}
- **Tables to inspect:** {from the card}

## Questions you can now answer

- {question} - {answer} ({row cited})

## Read next

- {Read before flow from ATLAS (`not yet traced: <id>` when its card is absent), then Related entries, then Changed since rows on a stale card}
```

Capability target: `# Lesson: {Capability}`, `- **Status:** {current | orphaned}`, `**Purpose:**`, `## Services` (`| Service | Role |`), `## Flows in order` (numbered, each `{capability}/{flow} - {Story}`), `## Top risks` (numbered), `## Read next`.

Rule target: `# Lesson: {R-n}`, then bullets `**Rule:**`, `**Kind:**`, `**Enforced at:**`, `**Why:**` (ending `- {confidence}`), `**Shapes:**` (flows), `**Quirk:**` (`yes` or `no`), `**Last touched:**`, `**Doc:**` (path or `none`); then, only when `Doc` is a path, `**Statement:**`, `**Scope:**`, `**Parameters:**`, `**Exceptions:**`, each from the doc's section and ending `({doc path})`.

An empty section keeps its header and one line `none - {evidence from the source}`.

## Avoid

- Re-tracing or reading repo code to fill a gap the card left
- Restating a card table cell for cell instead of rewriting it as a sentence
- Ranking surprises by interest instead of the rule order
- Emitting the card itself, or the trace summary block, as part of the lesson
