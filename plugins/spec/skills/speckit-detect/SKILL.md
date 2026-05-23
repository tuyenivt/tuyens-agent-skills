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

Once per workflow run, before any artifact read or write. Never user-invoked.

## Rules

- Detect against the repo root: `git rev-parse --show-toplevel` if available, else cwd. Do not walk up.
- `.specify/` is **well-formed** iff it contains at least one of `memory/constitution.md`, `feature.json`, `extensions.yml`. Well-formed -> `speckit-installed`. Otherwise -> `standalone`.
- Evidence is marker files only. CLI on `$PATH` is not evidence and is not recorded.
- If `.specify/feature.json` points at a missing directory, stay `speckit-installed`, warn via `notes`, and leave `feature_json_path` null.
- Re-detect every run; never cache.

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
  feature_json_path: <string or null>   # only if file exists AND target dir exists
  extensions_yml_present: true | false  # .specify/extensions.yml
delegate_target: /speckit-<cmd> | null  # set in speckit-installed mode, null otherwise
artifact_root: .specs/<slug> | specs/<NNN>-<name>
notes: <free text>                      # optional; non-fatal warnings only
```

Micro-example (dual-present case):

```yaml
mode: speckit-installed
evidence:
  specify_well_formed: true
  feature_json_path: specs/003-user-auth
delegate_target: /speckit-plan
notes: Both .specify/ and .specs/ present; existing .specs/ left untouched.
```

## Avoid

- State-changing commands during detection (`speckit init`, file creation).
- Inferring mode from project name, branch, or chat content.
- Recording CLI-on-PATH or any signal the decision table does not consume.
