---
name: task-spec-constitution
description: Generate or update project-level `.specs/constitution.md` with engineering principles, coding standards, governance, review rules. Speckit-aware.
metadata:
  category: spec
  tags: [spec, sdd, constitution, governance, principles]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow.

# Spec - Constitution

Produces a project-wide `.specs/constitution.md` - one rulebook per repo, not per feature. Where `behavioral-principles` governs how Claude reasons, the constitution governs what the **project** demands of its code, contributors, and reviewers. Synthesizes from `CLAUDE.md` plus installed standards skills.

## When to Use

Bootstrapping SDD on an established repo, onboarding new contributors, after a significant policy change (compliance, security baseline, release process), or pre-handoff. Not for: per-feature requirements (`task-spec-specify`), feature architecture (`task-spec-plan`), runtime governance (CI/hooks), or Claude reasoning rules (`behavioral-principles`).

## Inputs

- `--scope <area>`: limit to `backend | frontend | ops | security`. Default covers all installed standards skills.
- `--from-claude-md-only`: ignore standards skills, use CLAUDE.md alone.
- Optional explicit constitution path override.

If neither CLAUDE.md nor standards skills are present, ask the user for at least three durable rules (one each: code quality, ops, review) before producing anything. Do not fabricate.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Path

Use skill: spec-artifact-paths

Path is `.specs/constitution.md` (project root, NOT under a feature slug). If it exists, default to **amend**; offer replace/abort.

### STEP 4 - Branch on Mode

**speckit-installed:** locate Spec Kit's path (typically `.specify/memory/constitution.md`). Instruct user to run `/speckit-constitution` (any `before_constitution` / `after_constitution` hooks registered in `.specify/extensions.yml` will fire as part of that call - do not bypass them). Post-process by surfacing rules from CLAUDE.md or standards skills not captured by Spec Kit; present as proposed additions, do not silently merge. Skip to STEP 9.

**standalone:** continue.

### STEP 5 - Inventory Inputs

Read:
- Repo `CLAUDE.md` (especially Tech Stack, Behavioral Principles, Post-Change Checklist, Writing Conventions).
- `behavioral-principles` (universal reasoning - **do not duplicate** into the constitution).
- Every installed standards skill in scope: `backend-coding-standards`, `backend-api-guidelines`, `ops-*`, `frontend-accessibility`, `architecture-guardrail`, plus per-stack standards atomics.

`--scope` filters; `--from-claude-md-only` restricts to CLAUDE.md.

### STEP 6 - Synthesize

Each rule must be:
- Stated as a constraint (must / must not / measurable target), not a suggestion.
- Sourced (cite CLAUDE.md section, skill name, or user input - so future readers can trace it).
- Not duplicating `behavioral-principles` content.

Canonical sections (omit any with no rules):

| Section                     | Purpose                                                                                                |
| --------------------------- | ------------------------------------------------------------------------------------------------------ |
| **Identity**                | What this project is, who it serves, what it deliberately is not. Anchors every other rule.           |
| **Tech Stack Commitments**  | Languages, runtimes, frameworks, databases. Pinned where stability matters.                            |
| **Code Quality**            | Style, layering, DI conventions, immutability defaults, lint baselines.                                |
| **API and Contract Rules**  | REST/RPC conventions, versioning, deprecation, error model.                                            |
| **Data and Persistence**    | Migration policy, index requirements, retention, encryption.                                           |
| **Security and Compliance** | Authn/authz baseline, secret-handling, regulatory regimes (PCI/HIPAA/SOC2/GDPR).                       |
| **Operability**             | Observability minimums, SLO discipline, runbooks, feature-flag policy.                                 |
| **Release and Rollback**    | Deploy posture, rollback contract, backward-compatibility window.                                      |
| **Review and Governance**   | What changes require ADRs, review depth thresholds, blast-radius gates, sign-off matrix.               |
| **Out of Constitution**     | Decisions deliberately left to feature-level - surfaces what is intentionally flexible.                |

Synthesis rules:
- **Surface conflicts.** If sources disagree, stop and ask - never silently pick a side.
- **Quote, do not paraphrase.** Drift accumulates with each restatement.
- **Date-stamp the source citation.**
- **No rule without a source.** Surface uncited candidates for explicit user endorsement.

### STEP 7 - Reconcile (amend mode)

Diff synthesized rules against existing file. Categorize each as `unchanged | changed | added | removed`.

- `changed` rules: place both versions under "Pending Reconciliation" within the section; ask the user. Never silently overwrite.
- `removed` rules: move to **Archived** appendix with reason and date. Never delete.
- Never reorder existing sections silently.

### STEP 8 - Write constitution.md

**Constitution Version (semantic):**
- **MAJOR:** principle removed/redefined or governance broken backward-incompatibly.
- **MINOR:** new principle/section, or materially expanded guidance.
- **PATCH:** clarification, wording, typo.

If the bump type is ambiguous, propose your reasoning and chosen bump in chat before finalizing.

### STEP 9 - Sync Impact Report and Propagation Scan

Prepend (or refresh) a Sync Impact Report as an HTML comment at the top of `constitution.md`:
- Version change `<old> -> <new>`
- Modified principles (with renames)
- Added / removed sections
- Downstream propagation results (per table below)
- Deferred TODOs (`TODO(<FIELD>): <reason>`)

Propagation scan (surface findings only - never auto-edit):

| Target                                          | Check                                                                          |
| ----------------------------------------------- | ------------------------------------------------------------------------------ |
| `.specs/<slug>/spec.md`                         | AC/NFR contradicting a new/changed principle - flag for `task-spec-clarify`    |
| `.specs/<slug>/plan.md`                         | Architecture or tech-stack pin conflicting with new constitution               |
| `CLAUDE.md`                                     | Tech Stack or Behavioral Principles drift from new constitution                |
| `.specify/templates/*` (speckit mode)           | Plan/spec/tasks template references that became stale                          |

Each result marked `updated` or `pending` with the file path. The user (not this workflow) edits the affected artifacts.

### STEP 10 - Summarize

Print path, sections + rule counts, sources synthesized, mode, conflicts, version bump, propagation status, next command:
- First-time: `task-spec-specify <feature>` (constitution is now live).
- Pending reconciliations: resolve, then re-run in amend mode.
- speckit mode with proposed additions: user merges manually.

## Output Format

```markdown
<!--
Sync Impact Report:
- Version change: v0.1.0 -> v0.2.0
- Modified principles: <list, with renames>
- Added sections: <list>
- Removed sections: <list>
- Downstream propagation:
  - .specs/<slug>/spec.md       pending (AC4 may conflict with new compliance principle)
  - CLAUDE.md                    updated (Tech Stack synced)
  - .specify/templates/plan-template.md  pending (Constitution Check block stale)
- Deferred TODOs: TODO(RATIFICATION_DATE): unknown adoption date
-->

# Project Constitution

- **Constitution Version:** v0.2.0
- **Ratification date:** <YYYY-MM-DD or TODO>
- **Last amended:** <YYYY-MM-DD>
- **Sources synthesized:** CLAUDE.md, behavioral-principles, backend-coding-standards, ops-engineering-governance, frontend-accessibility
- **Scope:** all | backend | frontend | ops | security

## Identity
<One paragraph: what this project is, who it serves, what it is not.>

## Tech Stack Commitments
- **Language:** Java 21+ (pinned)         _(source: CLAUDE.md#tech-stack)_
- **Framework:** Spring Boot 3.5+         _(source: CLAUDE.md#tech-stack)_
- **Database:** PostgreSQL 17+            _(source: CLAUDE.md#tech-stack)_

## Code Quality
- Constructor injection only; no field `@Autowired`   _(source: backend-coding-standards#di)_
- Records for DTOs; classes for JPA entities          _(source: backend-coding-standards#dto)_

## API and Contract Rules
- Public endpoints versioned `/api/v1/...`            _(source: backend-api-guidelines#versioning)_
- Breaking changes via deprecation window of N releases _(source: ops-engineering-governance#deprecation)_

## Data and Persistence
- Schema changes follow expand-then-contract          _(source: backend-db-migration)_
- Every FK column is indexed                          _(source: backend-db-indexing)_

## Security and Compliance
- Compliance regimes: <PCI-DSS, GDPR>                 _(source: <CLAUDE.md or user-confirmed>)_
- Secrets injected via <vault / env / KMS>            _(source: ops-engineering-governance#secrets)_

## Operability
- Every endpoint emits structured logs with trace IDs _(source: ops-observability)_
- Critical paths have SLOs with measurement method    _(source: nfr-specification#slo)_

## Release and Rollback
- Default deploy: rolling / canary 5% -> 50% -> 100%  _(source: ops-release-safety)_
- Rollback target: 5 minutes                          _(source: ops-release-safety)_

## Review and Governance
- ADRs required for: data-model changes, new external dependencies, security-boundary changes  _(source: ops-engineering-governance#adrs)_
- Code review depth aligns with `task-code-review`    _(source: task-code-review)_

## Out of Constitution
<Decisions deliberately left to feature-level.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-constitution` | manual)

## Archived
(Houses rules removed in later amend passes; never deleted, only archived with reason + date.)
```

## Self-Check

- [ ] Loaded `behavioral-principles` and `speckit-detect` first
- [ ] Path resolved at project root (NOT under a feature slug)
- [ ] In speckit mode, additions surfaced for manual merge (no silent edits)
- [ ] Inputs inventoried explicitly (CLAUDE.md + every standards skill in scope)
- [ ] Every rule has a source citation; no fabrication
- [ ] Conflicts surfaced, not silently resolved
- [ ] Amend mode: changed rules in "Pending Reconciliation"; removed rules in "Archived"; never deleted
- [ ] No content duplicated from `behavioral-principles`
- [ ] Empty sections omitted
- [ ] Version bumped per MAJOR/MINOR/PATCH semantics (ambiguous bumps justified in chat)
- [ ] Sync Impact Report and propagation scan completed (findings surfaced, not auto-edited)
- [ ] Summary includes counts, sources, conflicts, version, propagation status, next command

## Avoid

- Producing a constitution from thin air.
- Paraphrasing source rules.
- Overwriting without amend/replace/abort offer.
- Silently dropping a rule whose source was removed - archive it.
- Including reasoning rules ("think before acting") - those belong in `behavioral-principles`.
- Treating the constitution as feature-scoped (one file per repo).
- Listing aspirational rules ("we should add tests") - capture rules in force, not goals.
