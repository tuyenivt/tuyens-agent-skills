---
name: spec-artifact-paths
description: Resolve the canonical `.specs/<feature-slug>/` artifact paths (spec.md, clarifications.md, plan.md, tasks.md, analysis.md, evaluation.md, handoffs/) for a given feature. Slugify feature names, create directories on first write, and surface the path contract to consuming workflows.
metadata:
  category: spec
  tags: [spec, sdd, artifacts, paths, filesystem]
user-invocable: false
---

# Spec Artifact Paths

> This atomic is composed by `task-spec-*` workflows in standalone mode - do not invoke directly. In speckit-installed mode, Spec Kit owns paths and this skill is skipped.

## When to Use

- Inside any `task-spec-*` workflow (standalone mode) before reading or writing an SDD artifact
- When a workflow needs to deterministically know where `spec.md`, `plan.md`, `tasks.md`, etc. live for the current feature
- When orchestration or evaluation skills need handoff or evaluation paths under the same feature slug

## Rules

- Slug derivation MUST be deterministic for the same input - lowercase, hyphen-separated, alphanumeric only, max 60 characters
- Never overwrite an existing artifact silently - if an artifact exists, return its path AND signal `exists: true` so the caller can choose to amend, replace, or fail
- Create parent directories lazily on first write, never as a side effect of resolution
- Project-level `constitution.md` lives at `.specs/constitution.md` - it is NOT under any feature slug
- Feature-level files always live at `.specs/<slug>/<file>.md` - keep this contract stable across the plugin

## Slug Derivation

From a feature name string:

1. Lowercase
2. Replace any sequence of non-`[a-z0-9]` characters with a single `-`
3. Trim leading and trailing `-`
4. Truncate to 60 characters; if truncation cuts mid-word, trim back to the previous `-`
5. If the result is empty, fail and ask the user for an explicit slug

Examples:

| Input                                | Slug                              |
| ------------------------------------ | --------------------------------- |
| `User Profile Avatar Upload`         | `user-profile-avatar-upload`      |
| `Add 2FA (TOTP) for staff accounts`  | `add-2fa-totp-for-staff-accounts` |
| `Re-architect billing -> events bus` | `re-architect-billing-events-bus` |

## Path Contract

For project root `<root>` and feature slug `<slug>`:

| Logical Name     | Path                                     | Owner                                                       |
| ---------------- | ---------------------------------------- | ----------------------------------------------------------- |
| `constitution`   | `<root>/.specs/constitution.md`          | `task-spec-constitution`                                    |
| `spec`           | `<root>/.specs/<slug>/spec.md`           | `task-spec-specify` (writer), all (reader)                  |
| `clarifications` | `<root>/.specs/<slug>/clarifications.md` | `task-spec-clarify`                                         |
| `plan`           | `<root>/.specs/<slug>/plan.md`           | `task-spec-plan`                                            |
| `tasks`          | `<root>/.specs/<slug>/tasks.md`          | `task-spec-tasks` (writer), `task-spec-implement` (updater) |
| `analysis`       | `<root>/.specs/<slug>/analysis.md`       | `task-spec-analyze`                                         |
| `checklist`      | `<root>/.specs/<slug>/checklist.md`      | `task-spec-checklist`                                       |
| `handoffs_dir`   | `<root>/.specs/<slug>/handoffs/`         | `task-spec-orchestrate`                                     |
| `evaluation`     | `<root>/.specs/<slug>/evaluation.md`     | `task-spec-evaluate`                                        |

Workflows MUST use these logical names when referencing paths in their bodies, so a future move of the convention (e.g., to `docs/specs/`) is a single change here.

## Directory Creation

- On a **read** of an artifact, do NOT create directories. If the file does not exist, return `exists: false` and let the caller decide.
- On a **write**, create `<root>/.specs/` and `<root>/.specs/<slug>/` (and `handoffs/` for orchestration) with `mkdir -p` semantics if missing.
- The first writer of a feature is responsible for choosing the slug; every subsequent workflow uses the same slug as input.

## Output Format

When invoked with a feature input (name or existing slug), emit:

```yaml
slug: <derived-slug>
root: <project-root-absolute-path>
paths:
  constitution: <root>/.specs/constitution.md
  spec: <root>/.specs/<slug>/spec.md
  clarifications: <root>/.specs/<slug>/clarifications.md
  plan: <root>/.specs/<slug>/plan.md
  tasks: <root>/.specs/<slug>/tasks.md
  analysis: <root>/.specs/<slug>/analysis.md
  checklist: <root>/.specs/<slug>/checklist.md
  handoffs_dir: <root>/.specs/<slug>/handoffs/
  evaluation: <root>/.specs/<slug>/evaluation.md
existence:
  spec: true | false
  clarifications: true | false
  plan: true | false
  tasks: true | false
  analysis: true | false
  checklist: true | false
  evaluation: true | false
notes: |
  Free-form. Required when an existing slug collides with a different feature name input,
  or when the .specs/ root contains files outside the documented contract.
```

## Handling Edge Cases

- **Slug collision:** if `<root>/.specs/<slug>/` exists and the input feature name does not match the existing `spec.md`'s declared name, stop and ask the user whether to reuse, rename (new slug), or abort.
- **No project root:** if there is no detectable project root (no `.git/`, no `CLAUDE.md`), use the current working directory and note this in `notes`.
- **`.specs/` is a file, not a directory:** unrecoverable in this skill - surface to the user.
- **Read-only filesystem:** if directory creation fails on write, fail loudly with the OS error; do not fall back to a temp directory.

## Avoid

- Hardcoding `.specs/` paths in workflow skills - always go through this atomic so the convention is single-sourced
- Creating directories during a read-only resolution call
- Silently truncating or transforming user-supplied slugs - if the input is already a valid slug, pass it through unchanged
- Using forward-slash paths in code that may run on Windows shells without normalization (the contract uses forward slashes; the executing tool must adapt)
