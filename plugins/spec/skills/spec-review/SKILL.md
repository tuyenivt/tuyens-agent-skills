---
name: spec-review
description: Audit spec.md for unmeasurable acceptance criteria, missing NFR coverage, conflicts, out-of-scope leakage; emit structured findings.
metadata:
  category: spec
  tags: [spec, sdd, review, requirements-quality, ambiguity]
user-invocable: false
---

# Spec Review

> Composed by `task-spec-clarify`, `task-spec-analyze`, `task-spec-checklist`.

## When to Use

Auditing `spec.md` for requirements quality before planning. Output is consumed by clarify/analyze/checklist workflows that route on `severity` and `category`.

## Rules

- Every finding cites `location` (heading or line range) and verbatim `excerpt`. Un-cited feedback is rejected.
- `severity` and `category` are required and assigned by the rubric below - no defaults, no inline overrides.
- Propose questions in `suggested_clarification`, never inline fixes or implementation choices.
- NFR exception: an explicit "not applicable, because X" satisfies that NFR category.

## Patterns

### Severity Rubric (hard rules)

| Severity | Trigger |
| -------- | ------- |
| `blocker` | Internal contradiction (ACs/NFRs that cannot simultaneously hold); a user story with zero ACs; stub spec (< 3 ACs or no NFRs section) |
| `major` | Unmeasurable AC; any NFR category from the checklist missing without "n-a-because-X"; out-of-scope leakage; weak story (missing role/want/value, or AC not traceable to any story) |
| `minor` | Vague language that doesn't change implementation; undefined-but-obvious term; cosmetic gap |

### NFR Coverage Checklist

Reviewer marks each as `covered`, `missing`, or `n-a-because-<reason>`:

- performance
- availability
- scalability
- security
- observability
- compliance (when domain implies regulatory scope)
- accessibility (when domain implies user-facing UI)

Any `missing` produces a `nfr-coverage` finding at `major`.

### Category Examples

**`acceptance-measurability`**
- Bad: "API responds quickly under load."
- Good: "p95 < 200ms at 500 RPS sustained 5 min."

**`conflict`**
- Bad: AC1 "All uploads are public." + NFR "All user data is private by default."
- Good: AC1 scoped to "avatar uploads"; NFR carves out "profile media is public-by-design."

**`out-of-scope`**
- Bad: Out-of-Scope lists "admin moderation"; Story 3 says "admin can ban a user."
- Good: Remove from Out-of-Scope or remove from Story 3 - cannot be both.

**`weak-story`**
- Bad: "User uploads avatar."
- Good: "As a registered user, I want to upload an avatar so my profile is recognisable."

### Status Decision

- `needs-rewrite` iff `blockers >= 1`.
- `needs-clarification` iff `blockers == 0` and `majors >= 1`.
- `pass` otherwise (minors do not change status).

### Edge Cases

- **`spec.md` missing**: one finding pointing at the absent file, `status: needs-rewrite`.
- **Stub spec**: emit one `blocker` of category `acceptance-measurability` or `nfr-coverage` as appropriate; do not nitpick.
- **Non-standard structure**: review what exists; flag missing standard sections via the rubric.
- **Duplicates**: consolidate into one finding with multiple `location` entries.

## Output Format

```yaml
spec_path: <root>/.specs/<slug>/spec.md
reviewed_at: <ISO-8601 UTC, e.g. 2026-05-23T14:30:00Z>
nfr_coverage:
  performance: covered | missing | n-a-because-<reason>
  availability: covered | missing | n-a-because-<reason>
  scalability: covered | missing | n-a-because-<reason>
  security: covered | missing | n-a-because-<reason>
  observability: covered | missing | n-a-because-<reason>
  compliance: covered | missing | n-a-because-<reason>
  accessibility: covered | missing | n-a-because-<reason>
findings:
  - id: F-001
    severity: blocker | major | minor
    category: acceptance-measurability | nfr-coverage | conflict | ambiguity | out-of-scope | weak-story
    location: "## Acceptance Criteria, item 3"   # or "lines 42-47"
    excerpt: "<short verbatim quote>"
    issue: |
      What is wrong and why it blocks/weakens the spec.
    suggested_clarification: |
      A question the user could answer to resolve this. Empty if a structural rewrite is needed.
summary:
  blockers: <n>
  majors: <n>
  minors: <n>
  status: pass | needs-clarification | needs-rewrite
```

## Avoid

- Reviewing prose style, grammar, or code (this skill reviews English).
- Proposing implementation choices (those belong in `plan.md`).
- Flagging optional NFRs (e.g., a11y for a CLI-only feature) without first checking the domain.
- Letting minors drive `status` away from `pass`.
