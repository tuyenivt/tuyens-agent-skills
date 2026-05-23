---
name: task-spec-constitution
description: Generate or update project-level `.specs/constitution.md` with engineering principles, standards, governance, review rules. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, constitution, governance, principles]
  type: workflow
user-invocable: true
---

# Spec - Constitution

Produces a project-wide `.specs/constitution.md` - one rulebook per repo, not per feature. Where `behavioral-principles` governs how Claude reasons, the constitution governs what the **project** demands of its code, contributors, and reviewers. Synthesizes from `CLAUDE.md` plus installed standards skills.

## When to Use

Bootstrapping SDD on an established repo, onboarding contributors, after a significant policy change (compliance, security baseline, release process), or pre-handoff. Not for: per-feature requirements (`task-spec-specify`), feature architecture (`task-spec-plan`), runtime governance (CI/hooks), or Claude reasoning rules (`behavioral-principles`).

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Path

Use skill: spec-artifact-paths

Target is `.specs/constitution.md` at project root (NOT under a feature slug). If it exists, default to **amend**; offer replace/abort. Record `amend` vs `create` - STEP 7 branches on it.

### STEP 4 - Branch on Mode

**speckit-installed:** delegate to `/speckit-constitution` (its registered hooks fire normally). Post-process by surfacing rules from CLAUDE.md or standards skills not captured upstream as **proposed additions**; never silently merge. Skip to STEP 9.

**standalone:** continue.

### STEP 5 - Inventory Inputs

Read:
- Repo `CLAUDE.md` - especially Tech Stack, Behavioral Principles, Post-Change Checklist, Writing Conventions.
- Every installed standards/governance skill (names containing `coding-standards`, `api-guidelines`, `governance`, `accessibility`, `guardrail`, `db-*`, `ops-*`, `release-*`, `observability`).

Flags:
- `--scope {backend | frontend | ops | security}` filters which skills are read.
- `--from-claude-md-only` ignores skills entirely.

If neither CLAUDE.md nor any standards skill is present, stop and ask the user for at least three durable rules (one each from code quality, ops, review) before producing anything. Do not fabricate.

### STEP 6 - Synthesize

Each rule must be:
- A constraint (must / must not / measurable target), not a suggestion.
- Sourced - cite the CLAUDE.md section, skill name, or user input, with the date the source was last touched.
- Quoted from the source, not paraphrased. Drift accumulates with each restatement.

If sources disagree, stop and ask. Never silently pick a side.

Canonical sections - omit any with no rules:

| Section                     | Purpose                                                                       |
| --------------------------- | ----------------------------------------------------------------------------- |
| **Identity**                | What this project is, who it serves, what it deliberately is not.             |
| **Tech Stack Commitments**  | Languages, runtimes, frameworks, databases. Pin where stability matters.      |
| **Code Quality**            | Style, layering, DI conventions, immutability defaults, lint baselines.       |
| **API and Contract Rules**  | REST/RPC conventions, versioning, deprecation, error model.                   |
| **Data and Persistence**    | Migration policy, index requirements, retention, encryption.                  |
| **Security and Compliance** | Authn/authz baseline, secret-handling, regulatory regimes.                    |
| **Operability**             | Observability minimums, SLO discipline, runbooks, feature-flag policy.        |
| **Release and Rollback**    | Deploy posture, rollback contract, backward-compatibility window.             |
| **Review and Governance**   | What changes require ADRs, review depth, blast-radius gates, sign-off matrix. |
| **Out of Constitution**     | Decisions deliberately left to feature-level.                                 |

### STEP 7 - Reconcile (amend mode only)

Only when STEP 3 found an existing file. Diff synthesized rules against the file; categorize each as `unchanged | changed | added | removed`.

- `changed`: place both versions under "Pending Reconciliation" within the section; ask the user. Never silently overwrite.
- `removed`: move to **Archived** appendix with reason and date. Never delete.
- Never reorder existing sections silently.

### STEP 8 - Write constitution.md

Write the file at the path from STEP 3 using the Output Format template.

Version (semantic):
- **MAJOR:** principle removed/redefined or governance broken backward-incompatibly.
- **MINOR:** new principle/section, or materially expanded guidance.
- **PATCH:** clarification, wording, typo.

If the bump type is ambiguous, propose your reasoning and chosen bump in chat before finalizing.

### STEP 9 - Sync Impact Report and Propagation Scan

Prepend (or refresh) a Sync Impact Report as an HTML comment at the top of `constitution.md`: version change `<old> -> <new>`, modified principles, added/removed sections, propagation results, deferred TODOs (`TODO(<FIELD>): <reason>`).

Propagation scan - surface findings only, never auto-edit. Each row marked `updated` or `pending` with the file path:

| Target                                | Check                                                                          | Mode       |
| ------------------------------------- | ------------------------------------------------------------------------------ | ---------- |
| `.specs/<slug>/spec.md`               | AC/NFR contradicting a new/changed principle - flag for `task-spec-clarify`    | both       |
| `.specs/<slug>/plan.md`               | Architecture or tech-stack pin conflicting with new constitution               | both       |
| `CLAUDE.md`                           | Tech Stack or Behavioral Principles drift                                      | both       |
| `.specify/templates/*`                | Plan/spec/tasks template references that became stale                          | speckit    |

### STEP 10 - Summarize

Print: path, section + rule counts, sources synthesized, mode, conflicts, version bump, propagation status, and next command:
- First-time: `task-spec-specify <feature>`.
- Pending reconciliations: resolve, then re-run.
- speckit mode with proposed additions: user merges manually.

## Output Format

```markdown
<!--
Sync Impact Report (template - replace all <placeholders>):
- Version change: <old> -> <new>
- Modified principles: <list, with renames>
- Added sections: <list>
- Removed sections: <list>
- Downstream propagation:
  - .specs/<slug>/spec.md       <updated | pending> (<reason>)
  - CLAUDE.md                   <updated | pending> (<reason>)
  - .specify/templates/plan-template.md  <updated | pending> (<reason>)  # speckit only
- Deferred TODOs: TODO(<FIELD>): <reason>
-->

# Project Constitution

- **Constitution Version:** v<MAJOR.MINOR.PATCH>
- **Ratification date:** <YYYY-MM-DD or TODO(RATIFICATION_DATE)>
- **Last amended:** <YYYY-MM-DD>
- **Sources synthesized:** <comma-separated list, each with last-touched date>
- **Scope:** <all | backend | frontend | ops | security>

## Identity
<One paragraph: what this project is, who it serves, what it is not.>

## Tech Stack Commitments
- **Language:** Java 21+ (pinned)  _(CLAUDE.md#tech-stack, 2026-04-12)_
- **Framework:** Spring Boot 3.5+  _(CLAUDE.md#tech-stack, 2026-04-12)_
- **Database:** PostgreSQL 17+     _(CLAUDE.md#tech-stack, 2026-04-12)_

## Code Quality
- Constructor injection only; no field `@Autowired`   _(backend-coding-standards#di, 2026-03-01)_

## API and Contract Rules
- Public endpoints versioned `/api/v1/...`            _(backend-api-guidelines#versioning, 2026-02-18)_

## Data and Persistence
- Schema changes follow expand-then-contract          _(backend-db-migration, 2026-01-30)_

## Security and Compliance
- Compliance regimes: <PCI-DSS, GDPR>                 _(CLAUDE.md or user-confirmed, <date>)_

## Operability
- Every endpoint emits structured logs with trace IDs _(ops-observability, 2026-03-22)_

## Release and Rollback
- Default deploy: rolling / canary 5% -> 50% -> 100%  _(ops-release-safety, 2026-04-02)_
- Rollback target: 5 minutes                          _(ops-release-safety, 2026-04-02)_

## Review and Governance
- ADRs required for: data-model changes, new external dependencies, security-boundary changes  _(ops-engineering-governance#adrs, 2026-03-15)_

## Out of Constitution
<Decisions deliberately left to feature-level.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-constitution` | manual)

## Archived
(Rules removed in later amend passes; archived with reason + date, never deleted.)
```

## Self-Check

- [ ] STEP 1-3 ran; path resolved at project root; amend vs create recorded
- [ ] STEP 4: speckit mode produced proposed additions only (no silent merges)
- [ ] STEP 5: inputs inventoried; missing-input case handled explicitly
- [ ] STEP 6: every rule has a dated source citation, quoted not paraphrased; conflicts surfaced
- [ ] STEP 7: amend mode only - changed rules under "Pending Reconciliation", removed rules under "Archived"
- [ ] STEP 8: file written; version bump justified when ambiguous
- [ ] STEP 9: Sync Impact Report prepended; propagation findings surfaced, never auto-edited
- [ ] STEP 10: summary lists counts, sources, conflicts, version, propagation, next command

## Avoid

- Fabricating rules without a source.
- Paraphrasing source rules instead of quoting them.
- Silently dropping a rule whose source was removed - archive it.
- Treating the constitution as feature-scoped (one file per repo, at project root).
- Capturing aspirational goals ("we should add tests") instead of rules in force.
- Including reasoning rules ("think before acting") - those belong in `behavioral-principles`.
