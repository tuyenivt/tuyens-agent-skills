---
name: spec-artifact-paths
description: Resolve .specs/<slug>/ artifact paths (spec, plan, tasks, analysis, evaluation, handoffs); derive slugs; surface existence. Read-only.
metadata:
  category: spec
  tags: [spec, sdd, artifacts, paths, filesystem]
user-invocable: false
---

# Spec Artifact Paths

Standalone-mode resolver for SDD artifacts. The consuming workflow has already chosen standalone mode via `speckit-detect`; in speckit-installed mode this skill is skipped.

## When to Use

A spec workflow needs canonical paths for a feature's artifacts before reading or writing them.

## Rules

- Slug derivation is deterministic and idempotent.
- Resolution is read-only - never creates directories or files; the writer creates the directory tree on first write.
- Collisions abort. Non-blocking observations go in `notes`.
- Workflows reference logical names (`spec`, `plan`, ...) from the Path Contract, never raw `.specs/` strings.

## Slug Derivation

1. Lowercase the input.
2. Replace runs of non-`[a-z0-9]` with a single `-`.
3. Trim leading/trailing `-`.
4. If length > 60, trim back to the last `-` at or before position 60; if that would leave < 20 chars, hard-cut at 60 instead.
5. Empty result -> abort and ask the user for an explicit slug.

A pre-formed slug is accepted unchanged iff re-running the algorithm on it yields the same string.

| Input                                       | Slug                              |
| ------------------------------------------- | --------------------------------- |
| `User Profile Avatar Upload`                | `user-profile-avatar-upload`      |
| `Add 2FA (TOTP) for staff accounts`         | `add-2fa-totp-for-staff-accounts` |
| `Re-architect billing -> events bus`        | `re-architect-billing-events-bus` |
| `supercalifragilisticexpialidocious-feature-name-extended` (>60) | `supercalifragilisticexpialidocious-feature-name` (trim to last `-` <= 60) |

## Path Contract

`<root>` = project root (nearest ancestor containing `.git/` or `CLAUDE.md`; else cwd, recorded in `notes`). `constitution` is project-wide; everything else is per-feature.

| Logical Name     | Path                                     |
| ---------------- | ---------------------------------------- |
| `constitution`   | `<root>/.specs/constitution.md`          |
| `spec`           | `<root>/.specs/<slug>/spec.md`           |
| `clarifications` | `<root>/.specs/<slug>/clarifications.md` |
| `plan`           | `<root>/.specs/<slug>/plan.md`           |
| `tasks`          | `<root>/.specs/<slug>/tasks.md`          |
| `analysis`       | `<root>/.specs/<slug>/analysis.md`       |
| `checklists_dir` | `<root>/.specs/<slug>/checklists/`       |
| `handoffs_dir`   | `<root>/.specs/<slug>/handoffs/`         |
| `evaluation`     | `<root>/.specs/<slug>/evaluation.md`     |

Existence semantics: file entries are `true` iff the file exists; directory entries are `true` iff the directory exists (contents irrelevant).

## Output Format

```yaml
slug: <derived-slug>
root: <absolute-project-root>
paths:                # one entry per logical name
  spec: <root>/.specs/<slug>/spec.md
  ...
existence:            # one entry per logical name; true | false
  spec: true
  ...
notes: |              # optional; omit if empty
  Non-blocking observations only (e.g., root fallback to cwd,
  unrecognized files under .specs/<slug>/).
```

## Edge Cases

- **Slug collision** (existing `spec.md` declares a different feature name): abort with `reuse / rename / abort` prompt; emit no YAML.
- **No project root marker**: use cwd as `<root>` and record the fallback in `notes`.
- **Files under `.specs/<slug>/` outside the contract**: surface in `notes`; do not fail.

## Avoid

- Hardcoding `.specs/` strings outside this skill.
- Falling back to a temp directory on any failure - propagate the OS error.
