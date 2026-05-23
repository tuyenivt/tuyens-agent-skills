---
name: task-spec-checklist
description: Generate themed requirements-quality checklist from spec.md - measurability, NFR coverage, conflicts, ambiguity, scope. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, checklist, quality, requirements]
  type: workflow
user-invocable: true
---

# Spec - Checklist

Generate a themed requirements-quality checklist for `spec.md`. Output is an append-only file under `.specs/<slug>/checklists/<theme>.md`.

## When to Use

After `task-spec-specify` (and ideally `task-spec-clarify`), before `task-spec-plan`. Also for stakeholder sign-off, contributor onboarding, or a fresh quality pass on an aged spec.

Not for: cross-artifact consistency (`task-spec-analyze` covers spec <-> plan <-> tasks), requirements elicitation (`task-spec-specify`), Q&A (`task-spec-clarify`), or code review. This skill inspects the internal quality of `spec.md` only.

## Arguments

- `<slug>` (required).
- `--theme <name>` - one of `requirements` (default), `ux`, `api`, `security`, `performance`, `accessibility`. Filename = `<theme>.md`.
- `--strict` - any finding (including minors) downgrades verdict to `fail`.
- `--non-interactive` - skip next-command suggestion.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

Target = `<checklists_dir>/<theme>.md`. If `spec.md` is missing or a stub, abort with a one-line recommendation to run `task-spec-specify`.

### STEP 4 - Branch on Mode

- **speckit-installed:** instruct the user to run `/speckit-checklist`. `before_checklist`/`after_checklist` hooks in `.specify/extensions.yml` fire as part of that call - do not bypass them. After it runs, post-process by re-running `spec-review` and appending uncovered items in a labeled `### Marketplace Additions` section of the speckit-produced file. Skip to STEP 8.
- **standalone:** continue.

### STEP 5 - Audit the Spec

Use skill: spec-review

If `summary.status == needs-rewrite`, abort: print blockers + recommendation (`task-spec-clarify` or `task-spec-specify` amend). Do not write a checklist - a broken spec cannot be meaningfully checklisted.

### STEP 6 - Build the Checklist

Categories for `--theme requirements` (six canonical; emit all):

| Category                          | Passes when                                                                       |
| --------------------------------- | --------------------------------------------------------------------------------- |
| Acceptance criteria measurability | Every AC has a measurable threshold; no vague verbs                               |
| NFR coverage                      | Every applicable category present with concrete targets, or explicitly waived     |
| Conflict-freeness                 | No two requirements contradict                                                    |
| Ambiguity                         | No undefined pronouns/jargon; domain terms defined inline or in glossary          |
| Out-of-scope clarity              | Out-of-Scope section non-empty and explicit                                       |
| Story strength                    | Every story uses "As a <role>, I want <capability>, so that <value>." with both   |

Categories for other themes - filter `spec-review` findings by domain keyword, then emit one category per finding cluster:

- `ux`: visual hierarchy, interaction states, fallback states, a11y basics
- `api`: error contracts, rate limits, auth, versioning
- `security`: authn coverage, data protection, threat model
- `performance`: quantified metrics, load profile, degradation
- `accessibility`: WCAG conformance level, keyboard, contrast, screen reader

For each category: emit one passing item if no findings, one failing item per cluster otherwise. Each failing item lists the finding ID, severity, and remediation pointer.

### Item Rules

- Question form. "Are X defined?", "Is `<vague term>` quantified?", "Can `<criterion>` be objectively measured?"
- End with a dimension tag: `[Completeness]`, `[Clarity]`, `[Consistency]`, `[Measurability]`, `[Coverage]`, `[Edge Case]`, `[Ambiguity]`, `[Conflict]`, `[Assumption]`, `[Gap]`.
- Cite a spec ref (`[Spec §FR-1]`) or a `[Gap]` marker. No uncited items.
- IDs: `CHK001`, `CHK002`, ..., monotonic across amend sessions.
- Never start with `Verify`/`Test`/`Confirm`/`Check that the system ...` - those are implementation tests, not requirements tests.

Bad: `- [ ] Verify the upload button works.` (implementation test)
Good: `- [ ] Is "fast" in AC4 quantified with a specific latency target? [Clarity, Spec §AC4]` (requirement test)

### Verdict

Mirror `spec-review` status:

| Spec-review status   | Checklist verdict   |
| -------------------- | ------------------- |
| `pass`               | `pass`              |
| `needs-clarification`| `conditional pass`  |
| `needs-rewrite`      | (aborted at STEP 5) |

`--strict` overrides: any minor present -> `fail`.

### STEP 7 - Write Themed File

Append-only. Prepend a new `## Session <YYYY-MM-DD HH:MM>` block under the existing header. Preserve prior sessions verbatim.

### STEP 8 - Summarize

Print path, per-category pass/fail, verdict, and (unless `--non-interactive`) the next command:

- `pass` -> `task-spec-plan <slug>`
- `conditional pass` -> reviewer sign-off, then `task-spec-plan`; or `task-spec-clarify` to lift to `pass`
- `fail` (`--strict` only) -> `task-spec-clarify <slug>`, then re-run

## Output Format

```markdown
# Requirements Checklist - <Feature Name>

- **Slug:** <slug>
- **Last reviewed:** <YYYY-MM-DD HH:MM>

## Session <YYYY-MM-DD HH:MM>

- **Verdict:** conditional pass
- **Reviewer:** (name or self-review)

### Acceptance Criteria Measurability
- [ ] CHK001 - Is "fast" in AC4 quantified with a specific latency target? [Measurability, Spec §AC4]
  - Finding F-002 (major). Remediation: `task-spec-clarify`.

### NFR Coverage
- [ ] CHK002 - Does the spec name a specific compliance standard for the PII it handles? [Coverage, Gap]
  - Finding F-004 (major). Remediation: `task-spec-clarify`.

### Conflict-Freeness
- [x] CHK003 - Are requirements free of internal contradictions? [Consistency, Spec §all]

### Ambiguity
- [ ] CHK004 - Is the referent of "they" in AC2/AC3 explicitly disambiguated? [Ambiguity, Spec §AC2-AC3]
  - Finding F-003 (major). Remediation: `task-spec-clarify`.

### Out-of-Scope Clarity
- [x] CHK005 - Is the Out-of-Scope section non-empty and explicit? [Completeness, Spec §Out-of-Scope]

### Story Strength
- [x] CHK006 - Does every story use "As a / I want / so that" with concrete role + value? [Completeness, Spec §User-Stories]

### Summary
- Categories passing: 3 / 6
- Findings: blockers=0 majors=3 minors=0
- Verdict: conditional pass
```

In speckit mode, the file is the one Spec Kit produced; append only the `### Marketplace Additions` block listing items this plugin flagged that Spec Kit's checklist missed.

## Self-Check

- [ ] STEP 1: loaded `behavioral-principles`
- [ ] STEP 2: ran `speckit-detect` and branched correctly
- [ ] STEP 3: resolved paths; aborted on missing/stub `spec.md`
- [ ] STEP 4: in speckit mode, only appended a labeled `Marketplace Additions` block - no silent edits
- [ ] STEP 5: ran `spec-review`; aborted on `needs-rewrite`
- [ ] STEP 6: every item is question form, cites a spec ref or `[Gap]`, ends with a dimension tag, has a monotonic `CHK###` ID
- [ ] STEP 7: file is append-only with a fresh `## Session` block
- [ ] STEP 8: printed verdict and next-command (unless `--non-interactive`)

## Avoid

- Inventing items not grounded in `spec-review` findings.
- Producing a checklist for a `needs-rewrite` spec.
- Editing `spec.md` directly - route fixes through `task-spec-clarify`.
- Treating "no findings" as suspicious - a clean spec passes.
