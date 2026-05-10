---
name: task-spec-checklist
description: Generate requirements-quality checklist for spec.md - measurability, NFR coverage, conflicts, ambiguity, out-of-scope clarity. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, checklist, quality, requirements]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Checklist

Produces structured **requirements-quality** checklists from `spec.md`. Where `task-spec-analyze` checks consistency *between* artifacts, this workflow checks the **internal quality** of `spec.md` alone. Output: themed file(s) under `.specs/<slug>/checklists/`, append-only, with a sign-offable verdict.

> **"Unit tests for English."** Items test the **requirements**, not the system.
>
> Wrong: "Verify the button clicks correctly" / "Test error handling works".
> Right: "Is 'fast loading' quantified with a specific timing threshold? [Clarity, Spec §NFR-2]".

## When to Use

After `task-spec-specify` (and ideally `task-spec-clarify`), before `task-spec-plan`. As a stakeholder sign-off artifact, contributor onboarding doc, or fresh quality pass when a spec ages. Not for: cross-artifact consistency (`task-spec-analyze`), elicitation (`task-spec-specify`), Q&A (`task-spec-clarify`), code review.

## Inputs

- `<slug>` (required). Aborts if `spec.md` missing or a stub.
- `--theme <name>`: `requirements` (default), `ux`, `api`, `security`, `performance`, `accessibility`, etc. Filename = `<theme>.md`.
- `--strict`: fail on any minor finding (default fails only on blockers).
- `--non-interactive`: skip next-command suggestion.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

Target file = `<checklists_dir>/<theme>.md`. If it exists, default to **amend** (preserve history); offer replace/abort.

### STEP 4 - Branch on Mode

**speckit-installed:** instruct the user to run `/speckit.checklist`. Post-process by re-running `spec-review` and appending uncovered items in a labeled "Marketplace Additions" section. No silent edits. Skip to STEP 8.

**standalone:** continue.

### STEP 5 - Run spec-review

Use skill: spec-review

Findings drive the checklist - audit logic is single-sourced. If `summary.status == needs-rewrite`, stop and recommend `task-spec-clarify` or `task-spec-specify` amend mode. Do not produce a checklist for a structurally broken spec.

### STEP 6 - Build the Checklist

Group findings by category. For categories with no findings, emit a passing question-form checkbox; for categories with findings, emit a failing checkbox plus finding details and remediation.

**Item-writing rules (non-negotiable):**

- **Question form only**: "Are X requirements defined for Y?", "Is `<vague term>` quantified?", "Can `<criterion>` be objectively measured?".
- End each item with a quality-dimension tag: `[Completeness]`, `[Clarity]`, `[Consistency]`, `[Measurability]`, `[Coverage]`, `[Edge Case]`, `[Ambiguity]`, `[Conflict]`, `[Assumption]`, `[Gap]`.
- ≥80% of items must cite a spec ref (`[Spec §FR-1]`) or a `[Gap]`-style marker.
- IDs: `CHK001`, `CHK002`, ..., monotonically increasing across amend sessions.
- **Forbidden item starts**: `Verify`, `Test`, `Confirm`, `Check that the system ...`. Those mark implementation tests.

For `--theme <name>`, narrow categories: `ux` (visual hierarchy / interaction states / a11y / fallback), `api` (errors / rate limits / auth / versioning), `security` (authn coverage / data protection / threat model), `performance` (quantified metrics / load / degradation).

**Default `requirements` theme categories:**

| Category                              | Passes when                                                                                  |
| ------------------------------------- | -------------------------------------------------------------------------------------------- |
| **Acceptance criteria measurability** | Every AC has a measurable threshold; no vague verbs                                          |
| **NFR coverage**                      | All applicable categories present with concrete targets, or explicitly waived                |
| **Conflict-freeness**                 | No two requirements contradict each other                                                    |
| **Ambiguity**                         | No undefined pronouns, jargon; domain terms defined inline or in glossary                    |
| **Out-of-scope clarity**              | Out-of-scope section is non-empty and explicit                                               |
| **Story strength**                    | Every story is "As a <role>, I want <capability>, so that <value>." with concrete role+value |

**Composite verdict:**
- **pass**: every category passes (or only `--strict`-excluded minors).
- **conditional pass**: blockers resolved, majors remain - reviewer must sign off.
- **fail**: any blocker.

### STEP 7 - Write Themed File

Append-only. New `## Session <timestamp>` block; preserve prior sessions.

### STEP 8 - Summarize

Print path, per-category pass/fail, composite verdict, next command:
- `pass` -> `task-spec-plan <slug>`.
- `conditional pass` -> reviewer sign-off, then `task-spec-plan`; otherwise `task-spec-clarify`.
- `fail` -> `task-spec-clarify <slug>`, then re-run.

`--non-interactive` skips the next-command suggestion.

## Output Format

```markdown
# Requirements Checklist - <Feature Name>

- **Slug:** <slug>
- **Last reviewed:** <YYYY-MM-DD HH:MM>

## Session <YYYY-MM-DD HH:MM>

- **Verdict:** pass | conditional pass | fail
- **Reviewer:** (name or self-review)

### Acceptance Criteria Measurability
- [x] CHK001 - Are acceptance criteria thresholds quantified with specific numbers? [Measurability, Spec §AC1-AC5]
- [ ] CHK002 - Is "fast" in AC4 quantified with a specific latency target? [Clarity, Ambiguity, Spec §AC4]
  - Finding F-003 (major): "AC4: response should be fast" - no threshold. Remediation: `task-spec-clarify`.

### NFR Coverage
- [x] CHK003 - Are performance targets defined for all critical paths? [Completeness, Spec §NFR-1]
- [ ] CHK005 - Does the spec name a specific compliance standard for the PII it handles? [Gap, Coverage]
  - Finding F-007 (major): no compliance standard named despite PII. Remediation: `task-spec-clarify`.

### Conflict-Freeness
- [x] CHK007 - Are requirements free of internal contradictions across sections? [Consistency]

### Ambiguity
- [ ] CHK009 - Is the referent of "they" in AC2/AC3 explicitly disambiguated? [Ambiguity, Spec §AC2-§AC3]

### Out-of-Scope Clarity
- [x] CHK010 - Is the out-of-scope section non-empty and explicit? [Completeness, Spec §Out-of-Scope]

### Story Strength
- [x] CHK011 - Does every story use "As a / I want / so that" with concrete role + value? [Completeness, Spec §User-Stories]

### Marketplace Additions
(Empty in standalone mode. In speckit mode, lists items this plugin's `spec-review` flagged that Spec Kit's checklist missed.)

### Summary
- Categories passing: <n> / 6
- Findings: blockers=<n> majors=<n> minors=<n>
- Verdict: <pass | conditional pass | fail>
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` first
- [ ] Resolved paths via `spec-artifact-paths`
- [ ] Aborted on missing/stub `spec.md`
- [ ] In speckit mode, additions appended in a labeled section (no silent edits)
- [ ] Used `spec-review` as findings source (not ad-hoc invention)
- [ ] Stopped on `needs-rewrite` rather than producing misleading output
- [ ] Every item is in question form, ends with `[Quality Dimension]`, and ≥80% cite a spec ref or `[Gap]`
- [ ] No item starts with `Verify`/`Test`/`Confirm`/`Check that the system ...`
- [ ] IDs increment monotonically across amend sessions
- [ ] All six canonical categories represented for default `requirements` theme
- [ ] Failing categories cite finding ID, severity, remediation
- [ ] File is append-only

## Avoid

- Inventing items not grounded in `spec-review` findings.
- Treating "no findings" as suspicious - a clean spec is valid.
- Editing `spec.md` (route via `task-spec-clarify`).
- Producing a checklist for a stub or broken spec.
- Conflating with `task-spec-analyze` - this checks within `spec.md`; analyze checks across artifacts.
