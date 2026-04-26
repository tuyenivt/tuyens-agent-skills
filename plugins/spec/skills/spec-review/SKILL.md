---
name: spec-review
description: Audit a `spec.md` document for requirements-quality issues - unmeasurable acceptance criteria, missing NFR coverage, conflicting requirements, ambiguous pronouns or undefined terms, and out-of-scope leakage. Produces a structured findings report consumable by `task-spec-clarify`, `task-spec-analyze`, and `task-spec-checklist`.
metadata:
  category: spec
  tags: [spec, sdd, review, requirements-quality, ambiguity]
user-invocable: false
---

# Spec Review

> This atomic is composed by spec workflows - do not invoke directly. Primary consumers: `task-spec-clarify`, `task-spec-analyze`, `task-spec-checklist`.

## When to Use

- After `spec.md` is drafted (by `task-spec-specify`) and before planning begins
- During `task-spec-clarify` to surface a structured ambiguity list for the user
- During `task-spec-analyze` as one input to cross-artifact consistency checks
- As the body of `task-spec-checklist` when generating a "unit tests for English" report

## Rules

- Every finding MUST cite a specific line range or section heading from `spec.md` - vague feedback is rejected
- Findings MUST be classified by severity (`blocker | major | minor`) and category - consuming workflows route on these fields
- Do not propose fixes inline; propose them as separate `suggested_clarification` entries the user can accept or reject
- Conflicting requirements MUST be flagged as `blocker` - they cannot be silently resolved
- A spec with zero findings is a valid outcome; do not invent issues to fill space
- This skill reviews **English**, not code. Do not flag implementation choices unless the spec leaks them as requirements

## Review Categories

### 1. Acceptance criteria measurability

Every acceptance criterion must be falsifiable by a test. Flag:

- Vague verbs without thresholds: "should be fast", "must scale well", "user-friendly"
- Missing units: "respond quickly" (quickly = ?), "support many users" (many = ?)
- Subjective qualifiers without measurement: "intuitive", "modern-looking"

**Bad:** "The API should respond quickly under load."
**Good:** "p95 latency < 200ms under sustained 500 RPS for 5 minutes."

### 2. NFR coverage

Cross-check `spec.md`'s NFR section (or absence) against the categories required by `nfr-specification`:

| Category      | Required if...                                                       |
| ------------- | -------------------------------------------------------------------- |
| Performance   | Always - flag missing latency/throughput targets                     |
| Availability  | Always - flag missing uptime/RTO/RPO                                 |
| Scalability   | Always - flag missing current and projected scale                    |
| Security      | Always - flag missing authn/authz, data classification, threat model |
| Compliance    | If domain implies it (payments, health, PII) - flag missing standard |
| Observability | Always - flag missing logs/metrics/traces requirements               |
| Accessibility | If user-facing UI - flag missing WCAG level                          |

A missing category is a `major` finding; an explicitly-stated "not applicable, because X" is acceptable.

### 3. Conflicting requirements

Two or more requirements that cannot simultaneously hold. Examples:

- "Must support 10K concurrent users" + "Single-node deployment with no replication"
- "All data encrypted at rest with customer-managed keys" + "Sub-100ms p99 read latency on cold cache"

Always `blocker`.

### 4. Ambiguous pronouns and undefined terms

- Pronouns whose antecedent is unclear ("it", "they", "this") more than one sentence away from a clear referent
- Domain terms used without definition on first occurrence ("the audit pipeline", "primary entitlement")
- Acronyms not expanded on first use

`minor` unless the ambiguity changes the implementation, in which case `major`.

### 5. Out-of-scope leakage

The spec lists something in "Acceptance Criteria" or "Stories" that contradicts its own "Out of Scope" section. Always `major`.

### 6. Missing or weak user stories

- Stories without an explicit user role, motivation, and value statement
- Stories without acceptance criteria
- Acceptance criteria not traceable to any story

`major` for missing acceptance criteria; `minor` for cosmetic story-format issues.

## Output Format

```yaml
spec_path: <root>/.specs/<slug>/spec.md
findings:
  - id: F-001
    severity: blocker | major | minor
    category: acceptance-measurability | nfr-coverage | conflict | ambiguity | out-of-scope | weak-story
    location: "## Acceptance Criteria, item 3" | "lines 42-47"
    excerpt: "<short verbatim quote>"
    issue: |
      One-paragraph explanation of what is wrong and why it blocks/weakens the spec.
    suggested_clarification: |
      A question the user could answer to resolve this. Empty if the user must restructure the spec.
summary:
  blockers: <count>
  majors: <count>
  minors: <count>
  status: pass | needs-clarification | needs-rewrite
```

`status` decision:

- `pass` - zero blockers, zero majors
- `needs-clarification` - zero blockers, any majors or minors
- `needs-rewrite` - one or more blockers

## Handling Edge Cases

- **`spec.md` missing entirely:** return `status: needs-rewrite` with a single finding pointing to the absent file. Do NOT fabricate review output.
- **`spec.md` is a stub (under 20 lines, no sections):** treat as `needs-rewrite`; do not nitpick a placeholder.
- **Spec uses a non-standard structure:** review what is there; flag missing standard sections as `major` findings rather than failing.
- **Duplicate or near-duplicate findings:** consolidate into one entry with multiple `location` references.

## Avoid

- Reviewing prose style or grammar - that is not the purpose of this skill
- Proposing implementation choices ("you should use Postgres") - belongs in `plan.md`, not spec review
- Flagging absence of sections that are genuinely optional for the project (e.g., accessibility for a CLI-only feature) - read the spec's domain hints first
- Generating findings without `location` and `excerpt` - the consumer cannot act on un-cited feedback
