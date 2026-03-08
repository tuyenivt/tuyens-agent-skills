---
name: task-adr-create
description: Write an Architecture Decision Record. Captures context, decision, alternatives considered, trade-offs, consequences, and a review trigger. Produces a ready-to-commit ADR file.
metadata:
  category: workflow
  tags: [adr, architecture, decisions, trade-offs, documentation]
  type: workflow
user-invocable: true
---

# Architecture Decision Record (ADR) Creator

## Purpose

Capture significant architectural decisions in a durable, reviewable format:

- **Context-first** - record the situation that forced the decision, not just the decision itself
- **Alternatives documented** - every accepted ADR must show what was rejected and why
- **Trade-off explicit** - state what is sacrificed, not just what is gained
- **Actionable consequences** - what changes, what teams need to know, what to watch for
- **Review trigger** - when to revisit this decision so it doesn't calcify into received wisdom

This skill produces a ready-to-commit `.md` file. It does not implement the decision.

## When to Use

- Before or after making a significant architectural choice that affects multiple teams or components
- When choosing between valid competing approaches (framework, pattern, protocol, data model)
- When overriding a previous ADR or changing an established pattern
- When a design decision will be hard to reverse and future engineers need context
- After an incident reveals a design assumption that should be made explicit

## What Qualifies as an ADR

**Write an ADR when:**

- The decision affects more than one module, service, or team
- The decision would be hard or expensive to reverse
- A future engineer would reasonably ask "why did they do it this way?"
- The decision overrides an existing convention or previous ADR

**Skip the ADR when:**

- The decision is purely local to one module with no cross-cutting impact
- It follows an established pattern already documented in the codebase
- It is a style or formatting choice with no architectural consequence

## Inputs

| Input                       | Required | Description                                                      |
| --------------------------- | -------- | ---------------------------------------------------------------- |
| Decision description        | Yes      | What was decided or is being considered                          |
| Context / problem statement | Yes      | Why a decision was needed - the forcing function                 |
| Alternatives considered     | Yes      | At least one alternative; ideally two or three                   |
| Status                      | No       | Proposed (default) \| Accepted \| Deprecated \| Superseded       |
| Supersedes ADR              | No       | ADR number/title if this replaces a previous decision            |
| Related tickets / PRs       | No       | Links to implementation context                                  |
| Target ADR directory        | No       | Default: `docs/adr/` - override if the project uses another path |

If alternatives are not provided, ask for them before proceeding. An ADR without considered alternatives is a decree, not a decision record.

## Workflow

### Step 1 - Locate Existing ADRs

Check for an existing ADR directory (`docs/adr/`, `doc/adr/`, `adr/`, `docs/decisions/`).

- If found: read the highest-numbered existing ADR to determine the next sequence number and observe any project-specific format conventions to follow.
- If not found: use number `0001` and create under `docs/adr/`.

Identify any existing ADR that this new decision supersedes or amends.

### Step 2 - Clarify Inputs

If any required input is missing, ask before writing:

- **No alternatives provided**: "What other approaches did you consider? An ADR without alternatives documents an outcome, not a decision."
- **Status unclear**: default to `Proposed` - the author or team lead marks it `Accepted` after review.
- **Context vague**: ask "What situation or constraint made this decision necessary right now?"

### Step 3 - Analyse Trade-Offs

Use skill: `tradeoff-analysis`

For each alternative (including the chosen option), evaluate:

- What it provides (capability, simplicity, performance, cost)
- What it costs (complexity, coupling, latency, operational burden, team learning)
- Reversibility: Easy / Moderate / Hard - and specifically what reversing it would require
- Risk: what conditions or assumptions would make this choice wrong

The chosen option must have the same rigour applied as the rejected ones - document its costs, not just its benefits.

### Step 4 - Write the ADR

Compose the ADR following the Output Format below.

**Filename convention:** `NNNN-kebab-case-title.md` where `NNNN` is the zero-padded sequence number.

Example: `0007-use-outbox-pattern-for-event-publishing.md`

**Title rules:**

- Imperative phrase describing the decision: "Use X for Y", "Replace X with Y", "Adopt X pattern"
- Under 72 characters
- No "ADR:" prefix in the title itself (the filename and H1 carry the number)

**Context rules:**

- Describe the situation, constraint, or failure that made a decision necessary
- Include relevant scale, team, or operational context
- Do not describe the decision itself here - that belongs in the Decision section

**Decision rules:**

- One clear statement of what was decided
- Present tense: "We will use X" or "X is adopted as the standard for Y"
- Reference the relevant module, layer, or service scope

**Consequences rules:**

- Split into Positive and Negative (or Neutral) - never list only positives
- Include operational consequences (what teams need to monitor, change, or learn)
- Include migration notes if existing code needs to change

**Review trigger rules:**

- State a specific, observable condition - not "when the team feels it's time"
- Examples: a metric threshold, a team size, a dependency version EOL, an incident type

### Step 5 - Output the File

Write the ADR to the target directory. State the full file path at the top of your response.

If the target directory does not exist, note that it needs to be created and provide the `mkdir` command.

## Output Format

File: `docs/adr/NNNN-kebab-case-title.md`

```markdown
# ADR-NNNN: [Imperative title - under 72 chars]

## Status

[Proposed | Accepted | Deprecated | Superseded by ADR-NNNN]

## Date

[YYYY-MM-DD]

## Context

[Describe the situation, constraint, problem, or incident that required a decision.
What is changing, what is breaking, what scale or team need is driving this?
Do NOT describe the decision here.]

## Decision

[One clear statement of what was decided and its scope.]

## Alternatives Considered

### Option 1: [Name of chosen option]

- **What it provides:** [capability, simplicity, operational benefit]
- **What it costs:** [complexity, coupling, latency, team burden]
- **Reversibility:** [Easy / Moderate / Hard] - [what reversing would require]
- **Risk:** [what conditions would make this choice wrong]

### Option 2: [Name of rejected option]

- **What it provides:** [...]
- **What it costs:** [...]
- **Why rejected:** [specific reason this was not chosen over Option 1]
- **Reversibility:** [...]

### Option 3: [Name of rejected option] _(if applicable)_

- **What it provides:** [...]
- **Why rejected:** [...]

## Consequences

### Positive

- [Concrete benefit 1]
- [Concrete benefit 2]

### Negative / Trade-offs

- [Concrete cost or constraint 1]
- [Concrete cost or constraint 2]

### Migration Notes _(if applicable)_

- [What existing code or infrastructure needs to change]
- [Teams or services that need to be notified]

## Review Trigger

Revisit this decision if:

- [Specific observable condition - e.g., "p99 latency on the event broker exceeds 500ms"]
- [Specific condition - e.g., "team grows beyond 10 engineers and module ownership becomes unclear"]
- [Specific condition - e.g., "the chosen library reaches end-of-life or drops maintained support"]

## References

- [Ticket / PR / incident link]
- [Supersedes ADR-NNNN: title] _(if applicable)_
- [Related ADR-NNNN: title] _(if applicable)_
```

### Output Constraints

- File must include a zero-padded 4-digit sequence number (`0001`, `0012`, `0123`)
- Every ADR must have at least one rejected alternative - stop and ask if none provided
- Consequences section must include at least one negative or trade-off item
- Review trigger must be a specific, observable condition - never "when needed"
- Date must be today's date in YYYY-MM-DD format
- Omit Migration Notes and Option 3 if not applicable - do not leave empty sections
- References section omitted if no links were provided

## Rules

- Never write an ADR with only one option evaluated - it is not a decision record
- Default status is `Proposed` - do not mark `Accepted` without explicit author instruction
- Do not implement the decision - produce the document only
- If the decision supersedes an existing ADR, update the superseded ADR's Status line to `Superseded by ADR-NNNN` and note this as a follow-up action
- Respect any project-specific ADR format observed in existing ADRs over this template
