---
name: design-audience-calibration
description: "Calibrate a design doc to its reviewer: architecture and domain fluency axes set vocabulary, glossing, diagram density, and appendix policy."
metadata:
  category: architecture
  tags: [design, audience, reviewer, approval, communication]
user-invocable: false
---

# Design Audience Calibration

## When to Use

- A design deliverable must be approved by a named reviewer, and approval - not completeness - is the success condition.
- A reviewer profile is supplied, the reviewer sits outside the author's fluency band in either direction, or nothing is known about the reviewer (calibrate on the recorded default).

## Rules

- **Calibration moves depth, it does not remove it.** Every analysis the workflow would run still runs. Content the reader does not need in order to decide goes to the appendix - never out of the document.
- **Gloss once, where architecture fluency is Low.** Introduce a term with a one-clause plain meaning at first use, then use the term normally. Avoiding the term costs precision; repeating the gloss costs trust. At High architecture fluency use raw terms and gloss nothing. At Low/Low the gloss keeps the term and its consequence and drops the mechanism, which moves to the appendix - shorter, still named, never deleted.
- **Never condescend.** No "simply", "just", "obviously", "as you know", "basically". Never explain the reader's own domain back to them.
- **An unstated profile is not a skipped calibration.** Default to Architecture: Low / Domain: High, and record it as assumed so the author can correct it.
- **Mixed readers take the lower value on each axis** - an author who is also a reader excepted, per the note below. The body serves the least fluent reader; the appendix carries the union of what each more-fluent reader needs (mechanism depth and domain glossary can coexist). Taking each axis independently can land on a quadrant no single reader occupies - that is correct and intended: the document is calibrated for the union of their gaps, not for any one person.

## Patterns

### The two axes

| Axis | High | Low |
| --- | --- | --- |
| Architecture fluency | Reads boundaries, consistency models, and failure modes unaided; wants the trade-off, not the tutorial | Unfamiliar vocabulary, whether a strong engineer or a non-engineer - "eventual consistency", "idempotent", "backpressure" each cost a re-read |
| Domain fluency | Knows this system's entities, flows, and landmines cold; often longer tenure than the author | New to this system or business area; the change lands only after the current flow is established |

They are independent. The most common approver profile in a long-lived org is Low architecture / High domain: promoted from development, knows where the bodies are buried, never had to learn the vocabulary.

Infer from evidence when unstated - tenure and role history signal domain fluency in both directions (a long-tenure engineer infers High, an executive sponsor or a newcomer infers Low), the vocabulary in the reviewer's own writing signals architecture fluency - and record the signal rather than the guess.

The test is what the sentence asserts, not how it is phrased. Any direct claim about what the reader does or does not know is **stated**, whether framed as a negation ("she is not an architecture person"), a description ("non-technical", which speaks to the architecture axis only), or praise ("knows the refund flow better than anyone"). Facts about their history from which fluency must be deduced - tenure, role, team, what they have written - are a **signal** and yield inferred, even when the requester supplies them. A single briefing often contains both: take each axis's strongest claim.

An approver who is also the author is still a reader on both axes, but never the binding one while another reader exists; calibrate to the others and list the author by name under `Also answer`.

### Quadrants

| Architecture / Domain | Typical reader | Vocabulary | Diagrams in body | Body budget | Appendix carries |
| --- | --- | --- | --- | --- | --- |
| High / High | Peer architect on this system | Raw terms; no current-state recap | 1 | ~1 page | Mechanism detail and rejected alternatives, compactly - this reader asks rather than reads |
| Low / High | Long-tenure engineer or promoted lead who now signs off | Gloss once, anchored to a named domain object; never re-explain the domain | 2-3 | ~2 pages | Mechanism detail, NFR figures, rejected alternatives |
| High / Low | Platform, security, or external architect | Raw terms | 2, current state first | ~2 pages | Domain glossary |
| Low / Low | Manager, exec, or stakeholder new to this system | Term plus consequence, in outcome and risk language; no mechanism | 2, heavily labelled | ~1 page | Everything technical |

Both Low-domain rows gain a current-state section on top of the page figure, per the rule below.

A page is ~500 words of rendered body; a diagram or table counts as ~150 and both count against the body budget, though only diagrams carry a separate count. Budgets bound the body only - the appendix is unbounded. Wherever Domain fluency is Low the body gains a current-state section, which sits outside the page figure and is bounded only by what the reader needs to follow the change.

### What the reader is actually deciding

Write the ask to the quadrant's question, not to the author's.

| Quadrant | The reviewer is really asking |
| --- | --- |
| High / High | Is this the right design? |
| Low / High | Will this work in *our* system, and can we get back if it does not? |
| High / Low | Does this violate a platform, security, or compliance constraint? |
| Low / Low | What is the risk, what does it cost, and when does it land? |

### Translating for low architecture fluency

Anchor every abstraction in something the reader already names - a named entity, flow, or number from this system, not a generic one. These glosses are written for Low architecture / High domain readers. At Low/Low, keep the term and its consequence and send the mechanism to the appendix: "the report can trail the orders table (the read model is eventually consistent)" rather than dropping either half.

| Instead of | Write |
| --- | --- |
| Blast radius: Moderate | If this fails, checkout still works and confirmation emails are delayed up to 10 minutes - a moderate blast radius |
| We use the outbox pattern | The "send confirmation" row is written in the same database transaction as the order, so a crash cannot lose it, and a background job sends it (the outbox pattern) |
| The read model is eventually consistent | The report catches up with the orders table rather than matching it instantly, normally within 30 seconds (the read model is eventually consistent) |
| The endpoint is idempotent | Retrying with the same request ID creates one payment, not two (idempotent) |
| p99 latency under 200ms | 99 of every 100 checkouts finish under 0.2s and the slowest may take longer - that is p99 latency under 200ms |

Every row keeps the term and adds its meaning - that is glossing. Deleting the term is the failure on the other side: it reads simpler and says less. Note the third row keeps "eventually consistent" and gives a normal-case figure without promising a ceiling, because eventual consistency guarantees convergence and not a bound; write a bound only where the system actually enforces one.

### Translating for low domain fluency

Establish the current state before the change: name the entities, one sentence on today's flow, and who the actors are. A High-architecture reader with Low domain fluency needs no pattern explained and every entity introduced.

## Output Format

Internal contract. The calling workflow applies it and never emits this block; the only thing that reaches the document is the `Attribution line`.

```
Audience calibration:
  Architecture fluency: {High | Low}
  Domain fluency: {High | Low}
  Source - architecture: {stated: <phrase> | inferred: <signal> | assumed default} for the binding reader{, per reader: <name> <value> (<source>); ...}{, lower bound across <readers>}
  Source - domain: {stated: <phrase> | inferred: <signal> | assumed default} for the binding reader{, per reader: <name> <value> (<source>); ...}{, lower bound across <readers>}
  Reader decides: {the calibrated quadrant's question, verbatim from the table}
  Also answer: {<name>: <that reader's quadrant question, verbatim>, one line per reader whose quadrant differs and always one for an author-reader | "n/a - every reader sits in the calibrated quadrant", for two or more readers | "n/a - single reader"}
  Vocabulary: {raw | gloss-once | outcome-and-risk}
  Domain context: {assume known | establish current state first}
  Diagram budget: {N} in body{, current state first}{, heavily labelled}
  Body budget: ~{N} page{s} of body{, plus a current-state section}
  Appendix carries: {enumerated list; the union across readers when they differ}
  Attribution line: {one sentence naming the fluency the document assumes on each axis, and saying the profile was assumed where it was}
```

Contract: every field is always present. An author who is the sole reader binds, and the author-reader line in `Also answer` wins over either n/a value. Each axis records its own source on its own line; `assumed default` only when nothing was stated and no signal supported an inference. For mixed readers the axis carries the lower bound, and provenance lists each reader's own value so a split (one stated, one defaulted) stays visible - the axis values themselves never describe an individual reader's fluency. `Reader decides` is the calibrated document's question; `Also answer` carries the others'. `Diagram budget` takes a single number: where the quadrant gives a range, the top when the change alters how two or more independently deployed components talk to each other and the bottom when it changes behaviour inside one; a single-value quadrant takes that value. A datastore the change only reads or writes is not a second component. Diagrams go before the prose that explains them. The current-state section's own diagram counts against the diagram budget; its ~150-word charge follows its words, outside the page figure.

## Avoid

- Deleting analysis instead of relocating it - a shorter document that decided less is not calibrated, it is thinner
- Dropping a term to avoid glossing it, leaving a vaguer sentence than the original
- Condescension markers, or restating the reader's own domain back to them
- Treating an unstated profile as permission to write at the author's own level
- Reordering or renaming the caller's sections - this skill sets depth, vocabulary, diagram count, and what moves to the appendix; the caller's output contract owns the section list
