---
name: spec-review
description: Audit spec.md for requirements-quality - unmeasurable AC, missing NFR coverage, conflicts, ambiguity, out-of-scope leakage; structured findings.
metadata:
  category: spec
  tags: [spec, sdd, review, requirements-quality, ambiguity]
user-invocable: false
---

# Spec Review

> Composed by `task-spec-clarify`, `task-spec-analyze`, `task-spec-checklist`. Reviews **English**, not code.

## Rules

- Every finding cites `location` (heading or line range) and `excerpt`. Un-cited feedback is rejected.
- Severity (`blocker | major | minor`) and `category` are required - consumers route on them.
- Propose questions in `suggested_clarification`, not inline fixes.
- Conflicts are always `blocker`. Out-of-scope leakage is always `major`.
- Zero findings is a valid outcome - do not invent issues.

## Review Categories

| Category                     | What to flag                                                                                          | Default severity |
| ---------------------------- | ----------------------------------------------------------------------------------------------------- | ---------------- |
| `acceptance-measurability`   | Vague verbs / missing units / subjective qualifiers ("fast", "many", "intuitive")                     | major            |
| `nfr-coverage`               | Missing performance, availability, scalability, security, observability; compliance/a11y when implied | major            |
| `conflict`                   | Requirements that cannot simultaneously hold                                                          | blocker          |
| `ambiguity`                  | Unclear pronouns, undefined domain terms, unexpanded acronyms                                         | minor (major if it changes implementation) |
| `out-of-scope`               | Item appears both in Out-of-Scope and in ACs/Stories                                                  | major            |
| `weak-story`                 | Story missing role/motivation/value, or AC not traceable to any story                                 | major (minor if cosmetic) |

NFR exception: an explicit "not applicable, because X" is acceptable and not flagged.

**AC measurability example.**
Bad: "The API should respond quickly under load."
Good: "p95 latency < 200ms under sustained 500 RPS for 5 minutes."

## Output Format

```yaml
spec_path: <root>/.specs/<slug>/spec.md
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

`status`: `needs-rewrite` if any blockers; else `needs-clarification` if any majors/minors; else `pass`.

## Edge Cases

- **`spec.md` missing**: return `needs-rewrite` with a single finding pointing to the absent file. Do not fabricate.
- **Stub spec** (<20 lines, no sections): `needs-rewrite`; do not nitpick a placeholder.
- **Non-standard structure**: review what's there; flag missing standard sections rather than failing.
- **Duplicate findings**: consolidate into one entry with multiple `location` references.

## Avoid

- Reviewing prose style or grammar.
- Proposing implementation choices (those belong in `plan.md`).
- Flagging optional sections (e.g., a11y for a CLI-only feature) - read the domain first.
