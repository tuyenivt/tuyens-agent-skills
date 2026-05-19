---
name: task-adr-create
description: "Write or review an Architecture Decision Record (ADR): context, alternatives, trade-offs, consequences, review trigger; .md output."
metadata:
  category: workflow
  tags: [adr, architecture, decisions, trade-offs, documentation]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Architecture Decision Record (ADR) Creator

## Purpose

Capture significant architectural decisions as a durable, reviewable `.md` file with context, alternatives, trade-offs, consequences, and review trigger. This skill produces the document only - it does not implement the decision.

## When to Use

Write an ADR when the decision affects more than one module/service/team, would be hard or expensive to reverse, overrides an existing convention, or would prompt a future engineer to ask "why did they do it this way?".

Skip when: purely local to one module, follows an already-documented pattern, or is a style/formatting choice.

## Inputs

| Input                       | Required | Description                                                      |
| --------------------------- | -------- | ---------------------------------------------------------------- |
| Decision description        | Yes      | What was decided or is being considered                          |
| Context / problem statement | Yes      | Why a decision was needed - the forcing function                 |
| Alternatives considered     | Yes      | At least one alternative; ideally two or three                   |
| Status                      | No       | Proposed (default) | Accepted | Deprecated | Superseded          |
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

Ask before writing if any required input is missing:

- **No alternatives**: "What else did you consider? An ADR without alternatives documents an outcome, not a decision."
- **Vague context**: "What situation or constraint made this decision necessary right now?"
- **Decide vs justify**: Ask whether the decision is already implemented. If yes, prompt the author to revisit alternatives with fresh eyes; note in References that rationale was reconstructed post-implementation.
- **Status default**: `Proposed`. Set `Accepted` only on explicit author confirmation.

### Step 3 - Analyse Trade-Offs

Use skill: `stack-detect`

For 3+ alternatives, run `architecture-proposal-compare` to produce a criteria matrix (it becomes the Alternatives Considered evidence base), then `tradeoff-analysis` on the chosen option to deepen Consequences. For exactly 2 alternatives, skip the matrix and run `tradeoff-analysis` on each.

For every alternative (chosen and rejected), evaluate:
- What it provides; what it costs (complexity, coupling, latency, operational burden, team learning)
- Reversibility (Easy/Moderate/Hard) and what reversing requires
- Risk: assumptions that would make this choice wrong

Apply the same rigour to the chosen option - document its costs, not only its benefits.

### Step 4 - Write the ADR

Compose using the Output Format below. Conventions:

- **Filename**: `NNNN-kebab-case-title.md` (e.g., `0007-use-outbox-pattern-for-event-publishing.md`)
- **Title**: imperative under 72 chars ("Use X for Y", "Replace X with Y"); no "ADR:" prefix
- **Context**: situation/constraint that forced the decision, never the decision itself
- **Decision**: one present-tense statement with explicit scope
- **Consequences**: must include negatives or trade-offs; add migration notes when existing code changes
- **Review trigger**: specific observable condition (metric threshold, team size, EOL, incident type) - never "when needed"

### Step 5 - Output the File

Write the ADR to the target directory and state the full path. If the directory does not exist, provide the `mkdir` command.

## Review Mode

When reviewing a draft ADR authored by someone else (do not write a new file - produce a review):

Use skill: `architecture-review-lens` for severity taxonomy, completeness audit, internal-consistency check, assumptions audit, criteria scoring, questions for the author, and verdict.

Supply this ADR-specific factor list to the completeness audit:

| Factor                  | What "Present" Looks Like                                                            |
| ----------------------- | ------------------------------------------------------------------------------------ |
| Title                   | Imperative under 72 chars ("Use X for Y", "Replace X with Y"); no "ADR:" prefix      |
| Status                  | Proposed / Accepted / Deprecated / Superseded; not blank or "TBD"                    |
| Context                 | Situation, constraint, or forcing function; describes the problem, not the decision  |
| Decision                | One present-tense statement with explicit scope                                      |
| Alternatives considered | At least one rejected alternative with a specific "Why rejected" reason              |
| Costs of chosen option  | Chosen option lists what it costs, not only benefits                                 |
| Consequences            | Contains at least one negative or trade-off; concrete, not aspirational              |
| Reversibility           | Easy / Moderate / Hard, with what reversing would require                            |
| Migration notes         | When existing code changes, notes which teams/services need notification             |
| Review trigger          | Specific observable condition (metric threshold, team size, EOL); not "when needed"  |
| References              | Tickets, PRs, superseded ADRs; reconstructed-rationale flagged when post-hoc         |

Specific quality checks beyond the standard lens:

- **Decision masquerading as context**: Context section that pre-announces the decision is a Major finding
- **Decree, not decision**: Zero rejected alternatives is a Blocker (cannot proceed without them)
- **No costs on chosen option**: A Major finding; the artifact reads as advocacy, not analysis
- **Vague review trigger**: "Revisit periodically" or "when needed" is a Minor; promote to Major if reversibility is Hard

If the ADR proposes 3+ alternatives, also run `architecture-proposal-compare` to validate the criteria-based comparison the author should have produced.

Output header: `# ADR Review: ADR-NNNN {title}` and use the output structure defined in `architecture-review-lens`. Do not write a file; emit the review to chat.

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

## Rules

- At least one rejected alternative is required - if none provided, stop and ask
- Chosen option must list costs, not only benefits; Consequences must contain at least one negative or trade-off
- Default status is `Proposed`; only set `Accepted` on explicit author instruction
- Date is today in YYYY-MM-DD; omit empty sections (Migration Notes, Option 3, References)
- If the decision supersedes an existing ADR, update the superseded ADR's Status to `Superseded by ADR-NNNN` as a follow-up
- Respect any project-specific ADR format observed in existing ADRs over this template

## Self-Check

- [ ] Filename `NNNN-kebab-case.md`; date is today (YYYY-MM-DD)
- [ ] Context describes the forcing situation, not the decision
- [ ] Decision is one present-tense statement with explicit scope
- [ ] At least one rejected alternative with "Why rejected"; chosen option lists costs
- [ ] Consequences contains at least one negative or trade-off
- [ ] Review trigger is a specific observable condition
