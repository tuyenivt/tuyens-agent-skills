---
name: task-spec-constitution
description: Generate or update a project-level `.specs/constitution.md` capturing the durable engineering principles, coding-standards posture, governance rules, and review expectations that every feature in the repo must respect. Synthesizes existing standards skills (`backend-coding-standards`, `ops-engineering-governance`, `frontend-accessibility`, ...) and the repo's `CLAUDE.md` into one portable document. Speckit-aware - delegates to `/speckit.constitution` when Spec Kit is installed.
metadata:
  category: spec
  tags: [spec, sdd, constitution, governance, principles]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Spec - Constitution

Produces a project-wide `.specs/constitution.md` - the durable rulebook every feature, plan, and implementation in the repo is expected to honor. The constitution is **project-scoped, not feature-scoped**: one file per repo, not one per slug. Where `behavioral-principles` governs how Claude reasons, the constitution governs what the **project** demands of its code, contributors, and reviewers. Synthesizes content from the repo's `CLAUDE.md` plus any standards skills installed (`backend-coding-standards`, `ops-engineering-governance`, `frontend-accessibility`, etc.) into a single portable artifact.

## When to Use

- Bootstrapping SDD on an established repo: capture the rules already in force so feature specs can reference them rather than re-deriving them
- Onboarding a new contributor: the constitution explains "why we do things this way here" without spreading the answer across CLAUDE.md, READMEs, and tribal knowledge
- After a significant policy change (new compliance regime, new security baseline, new release process): re-run to amend the constitution
- Pre-handoff between teams or contributors: a portable rulebook the new owners can adopt

**Not for:** Per-feature requirements (use `task-spec-specify`), architecture for a feature (use `task-spec-plan`), runtime governance (those belong in CI / pre-commit hooks), or reasoning rules for Claude (those live in `behavioral-principles`).

## Inputs

- Optional `--scope <area>` to limit synthesis to a single area (`backend`, `frontend`, `ops`, `security`); default synthesizes every area covered by installed standards skills
- Optional `--from-claude-md-only` to ignore standards skills and produce a constitution from CLAUDE.md alone (useful when other plugins are not installed)
- Optional explicit constitution path override (otherwise resolved by `spec-artifact-paths` to `.specs/constitution.md`)

**Insufficient input handling:** If neither CLAUDE.md nor any standards skills are installed, ask the user for at least three durable rules (one each for code quality, ops, and review) before producing the constitution. Do not fabricate a constitution from nothing.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

Capture `mode`. Subsequent steps branch on it.

### STEP 3 - Resolve Artifact Paths

Use skill: spec-artifact-paths

Capture the `constitution` path (`.specs/constitution.md` at project root - NOT under any feature slug) and its existence flag. If `constitution.md` already exists, ask the user whether to **replace**, **amend** (preserve and add a revision section), or **abort** - default to amend. The constitution is meant to evolve, not be rewritten.

### STEP 4 - Branch on Mode

#### Mode: speckit-installed

1. Pre-process: locate Spec Kit's constitution path (typically `.specify/memory/constitution.md`). Note its existence and content.
2. Delegate by instructing the user to run `/speckit.constitution` (or invoke programmatically). Spec Kit owns its constitution path.
3. Post-process: read Spec Kit's output and surface any rules from CLAUDE.md or installed standards skills that Spec Kit's constitution did not capture. Present them as proposed additions; do not silently merge them.
4. Skip to STEP 9.

#### Mode: standalone

Continue to STEP 5.

### STEP 5 - Inventory Inputs

Build the source list before composing. Read:

- The repo's `CLAUDE.md` (if present) - especially "Tech Stack", "Behavioral Principles", "Post-Change Checklist", "Writing Conventions" sections
- `Use skill: behavioral-principles` - the universal reasoning rules
- Standards skills present in installed plugins:
  - `backend-coding-standards` (core)
  - `backend-api-guidelines` (core)
  - `ops-engineering-governance` (core)
  - `ops-release-safety`, `ops-observability`, `ops-resiliency` (core)
  - `frontend-accessibility` (core)
  - `architecture-guardrail` (core)
- Any per-stack standards atomics in installed stack plugins (e.g., `spring-jpa-performance`, `python-async-patterns`, `react-state-management`)

If `--scope <area>` was set, filter the source list. If `--from-claude-md-only`, restrict to CLAUDE.md.

### STEP 6 - Synthesize

Group durable rules under canonical sections. Each rule must be:

- **Stated as a constraint** (a "must / must not" or measurable target), not a suggestion
- **Sourced** - cite which input (CLAUDE.md section, skill name, or user-supplied input) the rule came from, so future readers can trace it
- **Non-redundant with `behavioral-principles`** - the constitution is project-specific; rules that apply to every Claude Code project belong in `behavioral-principles`

Canonical sections (omit any that have no rules):

| Section                     | Purpose                                                                                                                  |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Identity**                | What this project is, who it serves, what it deliberately is not. Anchors every other rule.                              |
| **Tech Stack Commitments**  | Languages, runtimes, primary frameworks, databases. Pinned where stability matters; flexible where it does not.          |
| **Code Quality**            | Style, layering, dependency injection style, immutability defaults, linting baselines.                                   |
| **API and Contract Rules**  | REST/RPC conventions, versioning policy, deprecation rules, request/response shapes.                                     |
| **Data and Persistence**    | Migration policy (expand/contract), index requirements, retention rules, encryption expectations.                        |
| **Security and Compliance** | Authn/authz baseline, secret-handling rules, regulatory standards (PCI, HIPAA, SOC 2, GDPR, ...) the project must honor. |
| **Operability**             | Observability minimums (logs, metrics, traces), SLO discipline, runbook requirements, feature-flag policy.               |
| **Release and Rollback**    | Deployment posture (blue/green, canary, rolling), rollback contract, backward-compatibility window.                      |
| **Review and Governance**   | What changes require ADRs, review depth thresholds, blast-radius gates, who signs off on what.                           |
| **Out of Constitution**     | Rules deliberately NOT codified - left to feature-level decision. Surfaces what is intentionally flexible.               |

Rules during synthesis:

- **Surface conflicts.** If CLAUDE.md says one thing and a standards skill says another, stop and ask the user to reconcile. Do not silently pick a side.
- **Quote, do not paraphrase.** When CLAUDE.md or a skill states a rule precisely, preserve the wording. Paraphrasing introduces drift.
- **Date-stamp the source.** Each rule's citation includes the source name and the date this synthesis was run, so future readers can tell whether the citation is still accurate.
- **No rule without a source.** A rule with no citation is either fabricated or tribal knowledge the user must endorse explicitly. Surface it as a candidate, do not include it silently.

### STEP 7 - Reconcile with Existing Constitution

If `constitution.md` already exists and the user chose **amend**:

- Diff the synthesized rules against the existing file. Categorize each as `unchanged`, `changed` (different wording or threshold), `added` (new rule from a new source), or `removed` (old rule whose source no longer exists).
- Preserve the existing structure - never reorder sections silently.
- For `changed` rules, append both versions in a "Pending Reconciliation" subsection within the relevant canonical section, and ask the user which to keep. Do not silently overwrite.
- For `removed` rules, do not delete - move to an "Archived" appendix with the reason and date.

### STEP 8 - Write constitution.md

Write to the resolved path using the template in **Output Format** below. In amend mode, preserve prior text and append a dated revision section; never delete prior content (especially Archived appendix entries).

### STEP 9 - Summarize

Print a short summary to chat:

- Path written
- Sections populated and rule counts per section
- Sources synthesized (CLAUDE.md, list of standards skills consulted)
- Mode used (speckit-installed or standalone)
- Conflicts surfaced (if any)
- Suggested next command:
  - First-time creation -> `task-spec-specify <feature>` (the constitution is now live for new features)
  - Amend with pending reconciliations -> resolve those, then re-run `task-spec-constitution` in amend mode
  - Speckit-installed with proposed additions -> the user merges them into Spec Kit's constitution manually

## Output Format

`constitution.md` template (standalone mode; speckit-installed mode defers to Spec Kit's template, with proposed additions printed to chat for manual merge):

```markdown
# Project Constitution

- **Last updated:** <YYYY-MM-DD>
- **Sources synthesized:** CLAUDE.md, behavioral-principles, backend-coding-standards, ops-engineering-governance, frontend-accessibility (or list per project)
- **Scope:** all | backend | frontend | ops | security

## Identity

<One paragraph: what this project is, who it serves, what it is not. Anchors every rule below.>

## Tech Stack Commitments

- **Language:** <e.g., Java 21+, pinned> _(source: CLAUDE.md#tech-stack)_
- **Framework:** <e.g., Spring Boot 3.5+> _(source: CLAUDE.md#tech-stack)_
- **Database:** <e.g., PostgreSQL 15+> _(source: CLAUDE.md#tech-stack)_

## Code Quality

- Constructor injection only - no field `@Autowired` _(source: backend-coding-standards#di)_
- Records for all DTOs (Java 21+); classes for JPA entities _(source: backend-coding-standards#dto)_
- ...

## API and Contract Rules

- All public endpoints versioned under `/api/v1/...` _(source: backend-api-guidelines#versioning)_
- Breaking changes ship behind a deprecation window of <N> releases _(source: ops-engineering-governance#deprecation)_

## Data and Persistence

- Schema changes follow expand-then-contract; never destructive in a single deploy _(source: backend-db-migration)_
- Every FK column is indexed _(source: backend-db-indexing)_

## Security and Compliance

- Compliance regimes honored: <list, e.g., PCI-DSS, GDPR> _(source: <CLAUDE.md or user-confirmed>)_
- Secrets never in source; injected via <vault / env / KMS> _(source: ops-engineering-governance#secrets)_

## Operability

- Every endpoint emits structured logs with trace IDs _(source: ops-observability)_
- Critical paths have SLOs with measurement method _(source: nfr-specification#slo)_

## Release and Rollback

- Default deploy strategy: <e.g., rolling, canary 5% -> 50% -> 100%> _(source: ops-release-safety)_
- Rollback target: <e.g., 5 minutes> _(source: ops-release-safety)_

## Review and Governance

- ADRs required for: data-model changes, new external dependencies, security-boundary changes _(source: ops-engineering-governance#adrs)_
- Code review depth thresholds align with `task-code-review`'s standard depth _(source: task-code-review)_

## Out of Constitution

<Explicit list of decisions deliberately left to feature-level - prevents the constitution from over-constraining future work.>

## Revisions

(Empty on first write. Amend mode appends dated entries.)

- <YYYY-MM-DD>: <summary of change> (by `task-spec-constitution` | manual)

## Archived

(Empty on first write. Houses rules removed in later amend passes, with reason and date - never deleted.)
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` before any other work
- [ ] Resolved artifact path through `spec-artifact-paths` (`.specs/constitution.md` at project root, NOT under any feature slug)
- [ ] In speckit-installed mode, did not silently merge into Spec Kit's constitution - additions surfaced for manual review
- [ ] Inventoried inputs explicitly (CLAUDE.md, behavioral-principles, every installed standards skill in scope)
- [ ] Every rule has a source citation; no rule fabricated without user endorsement
- [ ] Conflicts between sources surfaced rather than silently resolved
- [ ] In amend mode: changed rules placed in "Pending Reconciliation" for user decision; removed rules moved to "Archived", never deleted
- [ ] No content duplicated from `behavioral-principles` (constitution is project-specific)
- [ ] Sections with no rules omitted (empty sections add noise)
- [ ] Final summary printed with sections, rule counts, sources, conflicts, and next-command suggestion

## Avoid

- Producing a constitution from thin air - if no sources exist, ask the user for explicit rules first
- Paraphrasing source rules - drift accumulates with each restatement
- Overwriting an existing constitution without amend/replace/abort offer
- Silently dropping a rule whose source has been removed - archive it with a reason
- Including reasoning rules ("think before acting") - those belong in `behavioral-principles`
- Treating the constitution as feature-scoped - it is one file per repo, period
- Listing aspirational rules ("we should add tests") - the constitution captures rules already in force, not goals

## Notes

- The constitution is the contract every `task-spec-specify` and `task-spec-plan` is expected to respect. A spec that proposes an out-of-constitution choice should be rejected at the checklist or analyze stage.
- Rules deliberately omitted (the "Out of Constitution" section) are as informative as rules included - they tell future contributors what flexibility is intentional.
- For monorepos with multiple sub-projects whose rules diverge, consider one constitution per sub-project rather than one umbrella file - surface this to the user during STEP 5 if the inputs disagree by area.
