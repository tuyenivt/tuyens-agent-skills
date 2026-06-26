---
name: speckit-detect
description: Detect GitHub Spec Kit install via .specify/ markers; pick speckit-installed (delegate /speckit-*) or standalone (.specs/<slug>/) mode.
metadata:
  category: spec
  tags: [spec, sdd, speckit, detection, mode-selection]
user-invocable: false
---

# Speckit Detection

Composed by `task-spec-*` workflows after `behavioral-principles`. Emits a mode plus structured evidence the workflow uses to delegate or self-drive.

## When to Use

Once per workflow run, before any artifact read or write.

## Rules

- Project root resolves via `spec-artifact-paths`' rule (nearest ancestor containing `.git/`, then `CLAUDE.md`, else cwd). Both skills must agree on root.
- `.specify/` is **well-formed** iff at least one of `memory/constitution.md`, `feature.json` (parseable JSON), `extensions.yml` (parseable YAML) exists and is non-empty. Well-formed -> `speckit-installed`. Else -> `standalone`.
- Evidence is marker files only. CLI on `$PATH` is never evidence.
- If `feature.json` points at a missing directory, stay `speckit-installed`, set `feature_json_path: null`, append a `notes` warning.
- Re-detect every run; never cache.
- `delegate_target` is the calling workflow's slash command (e.g., `task-spec-plan` -> `/speckit-plan`). Detection never infers it from chat content.

## Decision Table

| `.specify/`        | `.specs/` | Mode              | Note                                                     |
| ------------------ | --------- | ----------------- | -------------------------------------------------------- |
| well-formed        | absent    | speckit-installed | -                                                        |
| well-formed        | present   | speckit-installed | Warn in `notes`; existing `.specs/` not silently dropped |
| present, malformed | absent    | standalone        | Recommend `speckit init` if speckit mode was intended    |
| present, malformed | present   | standalone        | Warn in `notes`; treat malformed `.specify/` as noise    |
| absent             | present   | standalone        | -                                                        |
| absent             | absent    | standalone        | New project; first write creates `.specs/`               |

## Output Format

```yaml
mode: speckit-installed | standalone
evidence:
  specify_dir_present: true | false
  specify_well_formed: true | false
  specs_dir_present: true | false
  constitution_present: true | false    # .specify/memory/constitution.md
  feature_json_present: true | false    # .specify/feature.json
  feature_json_path: <string or null>   # path string when feature.json exists AND target dir exists; null otherwise
  extensions_yml_present: true | false  # .specify/extensions.yml
delegate_target: /speckit-<cmd> | null  # caller's slash command in speckit-installed mode; null in standalone
artifact_root: .specs/ | specs/         # standalone: .specs/ (slug appended by spec-artifact-paths); speckit: specs/ (NNN-name from feature.json)
notes: <free text>                      # optional; non-fatal warnings, one per line
```

Micro-example (dual-present case):

```yaml
mode: speckit-installed
evidence:
  specify_dir_present: true
  specify_well_formed: true
  specs_dir_present: true
  constitution_present: true
  feature_json_present: true
  feature_json_path: null
  extensions_yml_present: false
delegate_target: /speckit-plan
artifact_root: specs/
notes: |
  feature.json target dir missing.
  .specs/ also present; not modified.
```

## Avoid

- State-changing commands during detection (`speckit init`, file creation).
- Inferring mode from project name, branch, or chat content.
