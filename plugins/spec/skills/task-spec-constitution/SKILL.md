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

Produces a project-wide `.specs/constitution.md` - one rulebook per repo. Where `behavioral-principles` governs how Claude reasons, the constitution governs what the **project** demands of its code, contributors, and reviewers. Synthesizes from `CLAUDE.md` plus installed standards skills.

## When to Use

Bootstrapping SDD on an established repo, onboarding contributors, after a significant policy change, or pre-handoff. Not for per-feature requirements, feature architecture, runtime governance (CI/hooks), or Claude reasoning rules.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Detect Mode

Use skill: speckit-detect

### STEP 3 - Resolve Path

Use skill: spec-artifact-paths

Target is `.specs/constitution.md` at project root. If it exists, default to **amend**; offer replace/abort. Record `amend` vs `create` - STEP 7 branches on it.

### STEP 4 - Branch on Mode

**speckit-installed**: delegate to `/speckit-constitution`. Post-process by surfacing rules from CLAUDE.md or standards skills not captured upstream as **proposed additions**; never silently merge. Skip to STEP 9.

**standalone**: continue to STEP 5.

### STEP 5 - Inventory Inputs

Read:
- Repo `CLAUDE.md` (Tech Stack, Behavioral Principles, Post-Change Checklist, Writing Conventions).
- Every installed skill whose frontmatter `category` is one of `{standards, governance, ops, security, api, data}` OR whose name contains `coding-standards`, `api-guidelines`, `governance`, `accessibility`, `guardrail`, `db-*`, `ops-*`, `release-*`, `observability`.

Flags:
- `--scope {backend | frontend | ops | security}` filters which skills are read.
- `--from-claude-md-only` ignores skills entirely.

If neither CLAUDE.md nor any standards skill is present, stop and ask the user for at least three durable rules (one each from code quality, ops, review) before producing anything.

### STEP 6 - Synthesize

Each rule must be:
- A constraint (must / must not / measurable target), not a suggestion.
- Sourced: cite as `<source>#<anchor>, <YYYY-MM-DD>`. `<anchor>` is the slugified heading of the section the rule came from (e.g. `## Tech Stack` -> `tech-stack`). The date is the source file's last commit date (`git log -1 --format=%cs -- <path>`); if that returns empty (file not tracked in this repo, e.g. an installed skill), use today.
- Quoted verbatim from the source.

If CLAUDE.md and a standards skill state the same rule, cite both with ` | ` separator. If they conflict, stop and ask.

Canonical sections - omit any with no rules:

| Section                     | Purpose                                                                       |
| --------------------------- | ----------------------------------------------------------------------------- |
| **Identity**                | What this project is, who it serves, what it is not.                          |
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

Diff synthesized rules against the file; categorize each as `unchanged | changed | added | removed`.

- `changed`: place both versions under "Pending Reconciliation" within the section; ask the user.
- `removed`: move to **Archived** appendix with reason and date.
- Never reorder existing sections silently.

### STEP 8 - Write constitution.md

Initial creation: version `v1.0.0`; Sync Impact Report records `Version change: (none) -> v1.0.0`.

Amend version (semantic):
- **MAJOR**: principle removed/redefined or governance broken backward-incompatibly.
- **MINOR**: new principle/section, or materially expanded guidance.
- **PATCH**: clarification, wording, typo.

If the bump type is ambiguous, propose your reasoning and chosen bump in chat before finalizing.

### STEP 9 - Sync Impact Report and Propagation Scan

Prepend (or refresh) a Sync Impact Report as an HTML comment at the top of `constitution.md`. Propagation scan - surface findings only, never auto-edit. Skip any target that does not exist (first-time create usually has no `.specs/<slug>/` features yet):

| Target                                | Check                                                                          | Mode       |
| ------------------------------------- | ------------------------------------------------------------------------------ | ---------- |
| `.specs/<slug>/spec.md`               | AC/NFR contradicting a new/changed principle - flag for `task-spec-clarify`    | both       |
| `.specs/<slug>/plan.md`               | Architecture or tech-stack pin conflicting with new constitution               | both       |
| `CLAUDE.md`                           | Tech Stack or Behavioral Principles drift                                      | both       |
| `.specify/templates/*`                | Plan/spec/tasks template references that became stale                          | speckit    |

### STEP 10 - Summarize

Print: path, non-empty section count, total rule count, sources synthesized, mode, conflicts, version bump, propagation status, and next command:
- First-time: `task-spec-specify <feature>`.
- Pending reconciliations: resolve, then re-run.
- speckit mode with proposed additions: user merges manually.

## Output Format

```markdown
<!--
Sync Impact Report:
- Version change: <old or "(none)"> -> <new>
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
- "Language: Go 1.25+ (pinned)" _(CLAUDE.md#tech-stack, 2026-04-12)_

## Code Quality
- "Constructor injection only; no field @Autowired" _(CLAUDE.md#code-quality, 2026-04-12 | spring-coding-standards#di, 2026-03-01)_

## Out of Constitution
<Decisions deliberately left to feature-level.>

## Revisions
- <YYYY-MM-DD>: <change> (by `task-spec-constitution` | manual)

## Archived
(Rules removed in later amend passes; archived with reason + date, never deleted.)
```

## Self-Check

- [ ] STEP 1-3: behavioral-principles loaded; mode detected; path resolved at project root; amend vs create recorded
- [ ] STEP 4: speckit mode produced proposed additions only (no silent merges)
- [ ] STEP 5: inputs inventoried; missing-input case handled explicitly
- [ ] STEP 6: every rule has a dated source citation, quoted verbatim; conflicts surfaced
- [ ] STEP 7: amend mode - changed under "Pending Reconciliation", removed under "Archived"
- [ ] STEP 8: file written; initial version v1.0.0 or justified bump
- [ ] STEP 9: Sync Impact Report prepended; propagation findings surfaced
- [ ] STEP 10: summary lists counts, sources, conflicts, version, propagation, next command

## Avoid

- Fabricating rules without a source.
- Paraphrasing source rules instead of quoting them.
- Silently dropping a rule whose source was removed - archive it.
- Treating the constitution as feature-scoped.
- Capturing aspirational goals ("we should add tests") instead of rules in force.
- Including reasoning rules ("think before acting") - those belong in `behavioral-principles`.
