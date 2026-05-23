---
name: spec-artifact-paths
description: Resolve canonical .specs/<slug>/ artifact paths (spec, plan, tasks, analysis, evaluation, handoffs); slugify names, create dirs on first write.
metadata:
  category: spec
  tags: [spec, sdd, artifacts, paths, filesystem]
user-invocable: false
---

# Spec Artifact Paths

> Composed by `task-spec-*` workflows in standalone mode. In speckit-installed mode, Spec Kit owns paths and this skill is skipped - the consuming workflow reads the active feature directory from `.specify/feature.json` (a JSON file with `{ "feature_directory": "specs/<NNN>-<short-name>" }` written by `/speckit-specify`); if absent, fall back to scanning `specs/` for the most-recently-modified feature directory or ask the user.

## Rules

- Slug is deterministic: lowercase, hyphen-separated, alphanumeric, max 60 chars.
- Resolution is read-only. Directories are created only by the *writer*, not by path resolution.
- Existing artifacts are surfaced via `exists: true`, never overwritten silently.
- Workflows reference logical names from the Path Contract; never hardcode `.specs/` strings.

## Slug Derivation

1. Lowercase.
2. Replace runs of non-`[a-z0-9]` with a single `-`.
3. Trim leading/trailing `-`.
4. Truncate to 60; if mid-word, trim back to previous `-`.
5. Empty result -> fail and ask the user for an explicit slug.

| Input                                | Slug                              |
| ------------------------------------ | --------------------------------- |
| `User Profile Avatar Upload`         | `user-profile-avatar-upload`      |
| `Add 2FA (TOTP) for staff accounts`  | `add-2fa-totp-for-staff-accounts` |
| `Re-architect billing -> events bus` | `re-architect-billing-events-bus` |

## Path Contract

`<root>` = project root. `<slug>` = derived slug. `constitution` is project-wide; everything else is per-feature.

| Logical Name     | Path                                     | Writer                   |
| ---------------- | ---------------------------------------- | ------------------------ |
| `constitution`   | `<root>/.specs/constitution.md`          | `task-spec-constitution` |
| `spec`           | `<root>/.specs/<slug>/spec.md`           | `task-spec-specify`      |
| `clarifications` | `<root>/.specs/<slug>/clarifications.md` | `task-spec-clarify`      |
| `plan`           | `<root>/.specs/<slug>/plan.md`           | `task-spec-plan`         |
| `tasks`          | `<root>/.specs/<slug>/tasks.md`          | `task-spec-tasks`        |
| `analysis`       | `<root>/.specs/<slug>/analysis.md`       | `task-spec-analyze`      |
| `checklists_dir` | `<root>/.specs/<slug>/checklists/`       | `task-spec-checklist`    |
| `handoffs_dir`   | `<root>/.specs/<slug>/handoffs/`         | `task-spec-orchestrate`  |
| `evaluation`     | `<root>/.specs/<slug>/evaluation.md`     | `task-spec-evaluate`     |

Future relocation of the convention (e.g., to `docs/specs/`) is a single change to this table.

## Output Format

```yaml
slug: <derived-slug>
root: <project-root-absolute-path>
paths:                # one entry per logical name in the contract
  spec: <root>/.specs/<slug>/spec.md
  ...
existence:            # one entry per logical name; true/false
  spec: true
  ...
notes: |
  Required when an existing slug's spec.md declares a different feature name,
  or when .specs/ contains files outside the documented contract.
```

## Edge Cases

- **Slug collision** (existing `spec.md` declares a different name): stop and ask reuse / rename / abort.
- **No detectable project root** (no `.git/`, no `CLAUDE.md`): use cwd and record it in `notes`.
- **User passes a pre-formed slug**: pass through unchanged if already valid.

## Avoid

- Hardcoding `.specs/` paths anywhere outside this skill.
- Creating directories during resolution.
- Falling back to a temp directory on write failure (fail loudly with the OS error).
