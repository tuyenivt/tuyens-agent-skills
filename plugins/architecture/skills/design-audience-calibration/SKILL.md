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
- A reviewer profile is supplied, or the reviewer sits outside the author's fluency band in either direction.

## Rules

- **Calibration moves depth, it does not remove it.** Every analysis the workflow would run still runs. Content the reader does not need in order to decide goes to the appendix - never out of the document.
- **Gloss once.** Introduce a term with a one-clause plain meaning at first use, then use the term normally. Avoiding the term costs precision; repeating the gloss costs trust.
- **Never condescend.** No "simply", "just", "obviously", "as you know", "basically". Never explain the reader's own domain back to them.
- **An unstated profile is not a skipped calibration.** Default to Architecture: Low / Domain: High, and record it as assumed so the author can correct it.
- **Mixed readers take the lower value on each axis.** The body serves the least fluent reader; the appendix serves the most fluent one.

## Patterns

### The two axes

| Axis | High | Low |
| --- | --- | --- |
| Architecture fluency | Reads boundaries, consistency models, and failure modes unaided; wants the trade-off, not the tutorial | Strong engineer, unfamiliar vocabulary - "eventual consistency", "idempotent", "backpressure" each cost a re-read |
| Domain fluency | Knows this system's entities, flows, and landmines cold; often longer tenure than the author | New to this system or business area; the change lands only after the current flow is established |

They are independent. The most common approver profile in a long-lived org is Low architecture / High domain: promoted from development, knows where the bodies are buried, never had to learn the vocabulary.

Infer from evidence when unstated - tenure and role history signal domain fluency, the vocabulary in the reviewer's own writing signals architecture fluency - and record the signal rather than the guess. A named fluency ("she is not an architecture person") is stated; supplied evidence (tenure, role, the reviewer's writing) is a signal and yields inferred, even when the requester provides it.

### Quadrants

| Architecture / Domain | Typical reader | Vocabulary | Diagrams in body | Body budget | Appendix carries |
| --- | --- | --- | --- | --- | --- |
| High / High | Peer architect on this system | Raw terms; no current-state recap | 1 | ~1 page | Little - they will ask |
| Low / High | Long-tenure engineer or promoted lead who now signs off | Gloss once, anchored to a named domain object; never re-explain the domain | 2-3 | ~2 pages | Mechanism detail, NFR figures, rejected alternatives |
| High / Low | Platform, security, or external architect | Raw terms | 2, current state first | ~2 pages plus current state | Domain glossary |
| Low / Low | Manager, exec, or non-technical stakeholder | Outcome and risk language; no mechanism | 1, heavily labelled | ~1 page | Everything technical |

A page is ~500 words of rendered body; a diagram or table counts as ~150. Budgets bound the body only - the appendix is unbounded.

### What the reader is actually deciding

Write the ask to the quadrant's question, not to the author's.

| Quadrant | The reviewer is really asking |
| --- | --- |
| High / High | Is this the right design? |
| Low / High | Will this work in *our* system, and can we get back if it does not? |
| High / Low | Does this violate a platform, security, or compliance constraint? |
| Low / Low | What is the risk, what does it cost, and when does it land? |

### Translating for low architecture fluency

Anchor every abstraction in something the reader already names.

| Instead of | Write |
| --- | --- |
| Blast radius: Moderate | If this fails, checkout still works; confirmation emails are delayed up to 10 minutes |
| We use the outbox pattern | The "send confirmation" row is written in the same database transaction as the order, so a crash cannot lose it, and a background job sends it (the outbox pattern) |
| The read model is eventually consistent | The report can trail the orders table by up to 30 seconds |
| The endpoint is idempotent | Retrying with the same request ID creates one payment, not two (idempotent) |
| p99 latency under 200ms | 99 of every 100 requests finish under 0.2s; the slowest one may take longer |

Every row keeps the term and adds its meaning - that is glossing. Deleting the term is the failure on the other side: it reads simpler and says less.

### Translating for low domain fluency

Establish the current state before the change: name the entities, one sentence on today's flow, and who the actors are. A High-architecture reader with Low domain fluency needs no pattern explained and every entity introduced.

## Output Format

Internal contract. The calling workflow applies it and never emits this block; the document itself carries only a one-line attribution of who it was written for.

```
Audience calibration:
  Architecture fluency: {High | Low}
  Domain fluency: {High | Low}
  Source: per axis - {stated | inferred: <signal> | assumed default | mixed: lower bound across <readers>}
  Reader decides: {the quadrant question, one clause}
  Vocabulary: {raw | gloss-once | outcome-and-risk, no mechanism in body}
  Domain context: {assume known | establish current state first}
  Diagram budget: {N} in body, each placed before the prose that explains it
  Body budget: {target length, in pages}
  Appendix carries: {list}
```

Contract: every field is always present. Each axis records its own source; `assumed default` only when nothing was stated and no signal supported an inference. For mixed readers each axis records the lower bound and names the readers - the values describe the document's calibration, never an individual reader's fluency.

## Avoid

- Deleting analysis instead of relocating it - a shorter document that decided less is not calibrated, it is thinner
- Dropping a term to avoid glossing it, leaving a vaguer sentence than the original
- Condescension markers, or restating the reader's own domain back to them
- Treating an unstated profile as permission to write at the author's own level
- Calibrating structure when only prose needs calibrating - the caller's output contract owns section shape
