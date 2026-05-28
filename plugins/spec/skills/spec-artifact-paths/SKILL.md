---
name: spec-artifact-paths
description: Resolve .specs/<slug>/ artifact paths (spec, plan, tasks, analysis, evaluation, handoffs); derive slugs; surface existence. Read-only.
metadata:
  category: spec
  tags: [spec, sdd, artifacts, paths, filesystem]
user-invocable: false
---

# Spec Artifact Paths

Standalone-mode resolver for SDD artifacts. Invoked only when `speckit-detect` emits `mode: standalone`.

## When to Use

A spec workflow needs canonical paths for a feature's artifacts before reading or writing them.

## Rules

- Slug derivation is deterministic and idempotent.
- Read-only: the writer creates directories on first write.
- Workflows reference logical names (`spec`, `plan`, ...), never raw `.specs/` strings.
- Emit POSIX-style forward-slash paths (`C:/Users/...` on Windows); never mix separators.

## Slug Derivation

1. Lowercase the input.
2. Replace runs of non-`[a-z0-9]` with a single `-`.
3. Trim leading/trailing `-`.
4. If `length > 60`: let `i` = index of last `-` at or before position 60; if `i >= 20`, trim to `i`; else hard-cut at 60.
5. Empty result -> abort and ask the user for an explicit slug.

A pre-formed slug is accepted unchanged iff re-running the algorithm yields the same string. Slugs > 60 chars are always re-trimmed even when otherwise idempotent.

| Input                                       | Slug                              |
| ------------------------------------------- | --------------------------------- |
| `Add 2FA (TOTP) for staff accounts`         | `add-2fa-totp-for-staff-accounts` |
| `Re-architect billing -> events bus`        | `re-architect-billing-events-bus` |
| `Build Comprehensive Notification Center With Email SMS Push` (60+) | `build-comprehensive-notification-center-with-email` |
| `verylongsingletokenwithoutanyhyphensorbreaks` (no `-` before 20)  | `verylongsingletokenwithoutanybre` (hard-cut at 60 if >60; this 45-char input passes through) |

## Path Contract

`<root>` = nearest ancestor containing `.git/`; else nearest containing `CLAUDE.md`; else cwd (record fallback in `notes`). `constitution` is project-wide; everything else is per-feature.

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

`existence[name]` is `true` iff the file/directory exists.

## Output Format

```yaml
slug: <derived-slug>
root: <absolute-project-root>   # POSIX-style
paths:                # one entry per logical name
  spec: <root>/.specs/<slug>/spec.md
  ...
existence:            # one entry per logical name
  spec: true
  ...
notes: |              # optional; omit if empty
  Non-blocking observations (root fallback to cwd, unrecognized files under .specs/<slug>/).
```

## Edge Cases

- **Slug collision**: existing `.specs/<slug>/spec.md` has a top-level `#` heading whose slugified form differs from `<slug>`. Prompt `{reuse | rename | abort}`. `reuse` -> emit YAML for `<slug>`; `rename` -> re-derive; `abort` -> emit no YAML.
- **No project root marker**: use cwd; record fallback in `notes`.
- **Unrecognized files under `.specs/<slug>/`**: surface in `notes`.

## Avoid

- Hardcoding `.specs/` strings outside this skill.
- Falling back to a temp directory on any failure - propagate the OS error.
