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

Auditing `spec.md` for requirements quality before planning. Output routes on `severity` and `category`.

## Rules

- Every finding cites `location` (list of headings/line-ranges) and verbatim `excerpt`. No citation -> reject.
- `severity` and `category` follow the rubric; no defaults, no inline overrides.
- One finding per defect. When two rules could both apply to one span, classify by the **first matching row** of the Category Precedence table - never emit two findings for one span. When the same defect appears at multiple sites (e.g., a scope leak in both a story and an AC), emit one finding listing every site in `location`.
- `suggested_clarification` proposes a question, never an implementation choice.
- `id` is `F-NNN` in document order of `location[0]`. Stable across re-runs while `spec.md` is unchanged.
- `spec_path` is the actual path of the reviewed file, not a template placeholder.
- NFR exception: an explicit `n-a-because-<reason>` satisfies that category.

## Patterns

### Category Precedence

When several rules fit one span, the first matching row wins. Emit exactly one finding.

| Order | Condition | `category` | `severity` |
| ----- | --------- | ---------- | ---------- |
| 1 | Two ACs/NFRs cannot simultaneously hold, or an AC contradicts itself or the feature premise | `conflict` | `blocker` |
| 2 | A story or AC restates something the Out-of-Scope list excludes (semantic match) | `out-of-scope` | `major` |
| 3 | Vague/unmeasurable language inside an AC or NFR target | `acceptance-measurability` | `major` |
| 4 | Story missing role/want/value, or AC traceable to no story | `weak-story` | `major` |
| 5 | Vague language outside ACs/NFRs, undefined-but-obvious term, cosmetic gap | `ambiguity` | `minor` |

A degenerate story (e.g., "User checks out.") matches row 4 (`weak-story`, `major`), not the zero-AC blocker trigger - that trigger is for a fleshed-out story whose behavior no AC covers.

### Severity Rubric

| Severity | Trigger |
| -------- | ------- |
| `blocker` | Internal contradiction (row 1); fleshed-out user story with zero ACs; stub spec (< 3 ACs or no NFRs section) |
| `major` | Unmeasurable AC; missing NFR category without `n-a-because-X`; out-of-scope leakage; weak story |
| `minor` | Vague language outside ACs/NFRs; undefined-but-obvious term; cosmetic gap |

### NFR Coverage Checklist

Each marked `covered`, `missing`, or `n-a-because-<reason>`. Emit one `nfr-coverage` finding per `missing` category (not aggregated).

- performance, availability, scalability, security, observability
- compliance: applies when spec mentions PII, payments, health, audit, or names a regulation; else default `n-a-because-no-regulated-data`.
- accessibility: applies when spec mentions UI, forms, visual or interaction surface; else default `n-a-because-non-ui-feature`.

### Category Examples

**`acceptance-measurability`** - Bad: "API responds quickly under load." Good: "p95 < 200ms at 500 RPS sustained 5 min."

**`conflict`** - Bad: NFR "All user data is private by default" + AC "All checkout sessions broadcast to a public stream." Good: AC scoped to "anonymized session telemetry"; NFR carves out "telemetry events are public-by-design."

**`out-of-scope`** - Bad: Out-of-Scope lists "partial refunds"; Story 3 says "user requests partial refund." Good: remove from one side.

**`weak-story`** - Bad: "User checks out." Good: "As a returning customer, I want one-click checkout so I complete purchase in <30s."

### Status Decision

- `needs-rewrite` iff blockers >= 1.
- `needs-clarification` iff blockers == 0 and majors >= 1.
- `pass` otherwise.

### Degraded Input

- **`spec.md` missing**: emit one finding pointing at the absent file; `status: needs-rewrite`.
- **Stub spec** (< 3 ACs or no NFRs section): emit one `blocker` (`acceptance-measurability` or `nfr-coverage`); do not nitpick beyond it.

## Output Format

```yaml
spec_path: <actual path of the reviewed spec.md>
reviewed_at: <ISO-8601 UTC>
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
    location: ["## Acceptance Criteria, item 3"]   # list; length 1 for single-site findings
    excerpt: "<short verbatim quote>"
    issue: |
      What is wrong and why it blocks/weakens the spec.
    suggested_clarification: |
      A question the user could answer. Empty if a structural rewrite is needed.
summary:
  blockers: <n>
  majors: <n>
  minors: <n>
  status: pass | needs-clarification | needs-rewrite
```

## Avoid

- Reviewing prose style, grammar, or code (this skill reviews English).
- Flagging optional NFRs (a11y for a CLI-only feature) without first checking the domain.
