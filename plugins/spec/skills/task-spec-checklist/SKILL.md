---
name: task-spec-checklist
description: Generate a requirements-quality checklist for `spec.md` - "unit tests for English." Runs `spec-review` against the spec and produces a per-category pass/fail checklist (acceptance measurability, NFR coverage, conflict-freeness, ambiguity, out-of-scope clarity, story strength) the user can sign off on. Writes `checklist.md`. Speckit-aware - delegates to `/speckit.checklist` when Spec Kit is installed.
metadata:
  category: spec
  tags: [spec, sdd, checklist, quality, requirements]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Checklist

Produces structured **requirements-quality** checklists from `spec.md`. Where `task-spec-analyze` checks consistency _between_ artifacts, this workflow checks the **internal quality** of `spec.md` alone.

> **CRITICAL CONCEPT - "Unit Tests for English":** Checklist items test the **requirements themselves** (clarity, completeness, consistency, measurability, coverage), NOT whether the system works. This is the line that separates a checklist from a test plan.
>
> ❌ Wrong: "Verify the button clicks correctly" / "Test error handling works" / "Confirm the API returns 200"
> ✅ Right: "Are visual hierarchy requirements defined for all card types? [Completeness]" / "Is 'fast loading' quantified with specific timing thresholds? [Clarity, Spec §NFR-2]" / "Are hover state requirements consistent across all interactive elements? [Consistency]"
>
> Items must be in **question form**, end with a quality dimension in brackets, and (for ≥80% of items) cite a spec reference like `[Spec §FR-1]` or a marker like `[Gap]` / `[Ambiguity]` / `[Conflict]`.

Output is one or more themed checklist files under `.specs/<slug>/checklists/` (e.g., `requirements.md`, `ux.md`, `api.md`, `security.md`, `performance.md`). Each file has a verdict the user can sign off on (or hand to a reviewer) before running `task-spec-plan`.

## When to Use

- After `task-spec-specify` and ideally after `task-spec-clarify`, before `task-spec-plan`
- As a stakeholder-facing artifact: "this is what we agreed the requirements look like"
- When onboarding a new contributor to a feature - the checklist explains why the spec is structured the way it is
- When the spec has aged and the user wants a fresh quality pass independent of `task-spec-analyze`

**Not for:** Cross-artifact consistency (use `task-spec-analyze`), requirements elicitation (use `task-spec-specify`), resolving open questions (use `task-spec-clarify`), code review (use `task-code-review`).

## Inputs

- The feature slug (required) - workflow reads `.specs/<slug>/spec.md`
- Optional `--theme <name>` to emit a single themed checklist file (`ux`, `api`, `security`, `performance`, `accessibility`, ...). Filename = `.specs/<slug>/checklists/<theme>.md`. Default theme is `requirements` (the canonical six-category quality pass).
- Optional `--strict` to fail the checklist on any minor finding (default: pass on majors/minors, fail only on blockers)
- Optional `--non-interactive` to emit the checklist and exit without recommending next commands

**Insufficient input handling:** If `spec.md` is missing, abort and recommend `task-spec-specify`. If `spec.md` is a stub (per `spec-review`'s handling), do not produce a checklist - recommend filling out the spec first.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

Capture `mode`. Subsequent steps branch on it.

### STEP 3 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Capture `spec` and `checklist` paths plus existence flags. If `spec.md` does not exist, abort with a clear message recommending `task-spec-specify`. If `checklist.md` already exists, ask the user whether to **replace**, **amend** (preserve history with a new session), or **abort** - default to amend.

### STEP 4 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: nothing - speckit owns checklist generation.
2. Delegate by instructing the user to run `/speckit.checklist` (or invoke programmatically).
3. Post-process: re-run `Use skill: spec-review` over the spec and append any items Spec Kit's checklist did not cover (e.g., NFR-coverage gaps the marketplace cares about) in a clearly labeled "Marketplace additions" section. Do not silently edit Spec Kit's output.
4. Skip to STEP 8.

#### Mode: standalone

Continue to STEP 5.

### STEP 5 - Run spec-review

Use skill: spec-review

Capture the findings list and `summary.status`. The checklist is the findings reorganized as a sign-offable artifact - the underlying audit logic lives in `spec-review`, not here.

If `summary.status == needs-rewrite` (any blocker), stop and recommend the user run `task-spec-clarify` or re-run `task-spec-specify` in amend mode. Do not produce a checklist for a structurally broken spec.

### STEP 6 - Build the Checklist

Group findings by category and turn each into a **question-form** checklist item that tests the requirements themselves, not the implementation. For categories with **no findings**, emit a passing question-form checkbox; for categories with findings, emit a failing question-form checkbox plus the finding details and remediation pointer.

**Item-writing rules (non-negotiable):**

- Question form only: "Are X requirements defined for Y?", "Is `<vague term>` quantified?", "Can `<criterion>` be objectively measured?", "Does the spec define `<missing aspect>`?"
- End each item with a bracketed quality dimension: `[Completeness]`, `[Clarity]`, `[Consistency]`, `[Measurability]`, `[Coverage]`, `[Edge Case]`, `[Ambiguity]`, `[Conflict]`, `[Assumption]`, `[Gap]`
- ≥80% of items must include a spec reference like `[Spec §FR-1]` or a `[Gap]` marker if the requirement is missing
- Numbered IDs `CHK001`, `CHK002`, ... incrementing across the file. In amend mode, continue from the highest existing ID rather than restarting.
- Forbidden verbs at item start: `Verify`, `Test`, `Confirm`, `Check that the system <does something>`. These mark implementation tests, not requirement tests.

For `--theme <name>`, narrow the categories to that theme (e.g., `ux` → visual hierarchy / interaction states / accessibility / fallback states; `api` → error formats / rate limits / auth consistency / versioning; `security` → authn coverage / data protection / threat model; `performance` → quantified metrics / load conditions / degradation).

**Categories and pass criteria:**

| Category                              | Passes when                                                                                      |
| ------------------------------------- | ------------------------------------------------------------------------------------------------ |
| **Acceptance criteria measurability** | Every AC has a measurable threshold; no vague verbs                                              |
| **NFR coverage**                      | All applicable NFR categories present with concrete targets, or explicitly waived with reason    |
| **Conflict-freeness**                 | No two requirements contradict each other (offline + real-time, etc.)                            |
| **Ambiguity**                         | No undefined pronouns, jargon, or terms; domain words have a glossary or inline definition       |
| **Out-of-scope clarity**              | Out-of-scope section is non-empty and lists explicit non-goals                                   |
| **Story strength**                    | Every story is "As a <role>, I want <capability>, so that <value>." with a concrete role + value |

**Composite pass criteria:**

- **Pass:** every category passes (no findings, or only `--strict`-excluded minors)
- **Conditional pass:** all blockers resolved, but majors remain - reviewer must sign off knowing the gaps
- **Fail:** any blocker present (treat as a hard stop)

### STEP 7 - Write checklist.md

Write to the resolved path using the template in **Output Format** below. In amend mode, append a new `## Session <timestamp>` block; never delete prior sessions.

### STEP 8 - Summarize

Print a short summary to chat:

- Path written
- Pass/fail per category (all six)
- Composite verdict: pass | conditional pass | fail
- Suggested next command:
  - `pass` -> `task-spec-plan <slug>`
  - `conditional pass` -> proceed to `task-spec-plan` only if a reviewer signs off; otherwise `task-spec-clarify`
  - `fail` -> `task-spec-clarify <slug>` then re-run `task-spec-checklist`

In `--non-interactive` mode, skip the next-command suggestion.

## Output Format

`checklist.md` template (standalone mode; speckit-installed mode defers to Spec Kit's template, with marketplace additions appended):

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

- [x] CHK003 - Are performance targets (latency, throughput) defined for all critical paths? [Completeness, Spec §NFR-1]
- [x] CHK004 - Is the availability target specified with a measurable SLO? [Measurability, Spec §NFR-2]
- [ ] CHK005 - Does the spec name a specific compliance standard for the PII it handles? [Gap, Coverage]
  - Finding F-007 (major): no compliance standard named despite PII handling. Remediation: `task-spec-clarify`.
- [x] CHK006 - Are observability requirements specified for failure modes? [Coverage, Spec §NFR-4]

### Conflict-Freeness

- [x] CHK007 - Are requirements free of internal contradictions across sections? [Consistency]

### Ambiguity

- [x] CHK008 - Are domain terms defined or self-evident in context? [Clarity]
- [ ] CHK009 - Is the referent of "they" in AC2/AC3 explicitly disambiguated? [Ambiguity, Spec §AC2-§AC3]
  - Finding F-011 (minor): "they receive a notification" - "they" ambiguous between AC2 and AC3 actors.

### Out-of-Scope Clarity

- [x] CHK010 - Is the out-of-scope section non-empty and explicit about non-goals? [Completeness, Spec §Out-of-Scope]

### Story Strength

- [x] CHK011 - Does every story follow "As a / I want / so that" structure with a concrete role and value? [Completeness, Spec §User-Stories]

### Marketplace Additions

(Empty in standalone mode. In speckit-installed mode, lists items this plugin's `spec-review` flagged that Spec Kit's checklist did not cover.)

### Summary

- Categories passing: <n> / 6
- Findings: blockers=<n> majors=<n> minors=<n>
- Verdict: <pass | conditional pass | fail>
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` before any other work
- [ ] Resolved artifact paths through `spec-artifact-paths` (no hardcoded `.specs/` strings)
- [ ] Aborted cleanly if `spec.md` was missing or stub-only
- [ ] In speckit-installed mode, did not silently edit Spec Kit's output - additions appended in a labeled section
- [ ] Used `spec-review` as the source of findings - did not invent ad-hoc quality checks
- [ ] Stopped on `needs-rewrite` (blocker present) rather than producing a misleading checklist
- [ ] Every checklist item is in question form, ends with a `[Quality Dimension]` tag, and (≥80%) cites a spec section or `[Gap]`-style marker
- [ ] No item starts with forbidden verbs (`Verify`, `Test`, `Confirm`, `Check that the system ...`) - those mark implementation tests, not requirement tests
- [ ] Item IDs (`CHK001`...) increment continuously across amend sessions, never restart
- [ ] Default theme writes `requirements.md`; `--theme <name>` writes `<theme>.md` under `.specs/<slug>/checklists/`
- [ ] Every one of the six categories has a checkbox row (pass or fail) for the default `requirements` theme
- [ ] Failing categories cite the specific finding ID, severity, and remediation workflow
- [ ] `checklist.md` is append-only - prior sessions preserved
- [ ] Final summary printed with per-category pass/fail, composite verdict, and next-command suggestion

## Avoid

- Inventing checklist items not grounded in `spec-review` findings - the audit logic is single-sourced
- Treating "no findings" as suspicious - a clean spec is a valid outcome
- Editing `spec.md` from this workflow - findings route to `task-spec-clarify` for fixes
- Producing a checklist for a stub or structurally broken spec - that is misleading
- Discarding prior checklist sessions - the audit trail is the point
- Conflating this workflow with `task-spec-analyze` - one checks within `spec.md`, the other checks across `spec.md` + `plan.md` + `tasks.md`

## Notes

- The checklist is a stakeholder artifact: it is more important that it is accurate than that it is exhaustive. Six categories is enough.
- A `conditional pass` verdict is the most common outcome on a first pass - majors often surface real questions that take judgement to resolve.
- For features that explicitly waive a category (e.g., a CLI-only feature waiving accessibility), record the waiver and reason in the spec, then re-run the checklist - the waiver is not a failure.
