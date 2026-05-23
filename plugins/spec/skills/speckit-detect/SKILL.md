---
name: speckit-detect
description: Detect GitHub Spec Kit install and choose speckit-aware mode (delegate to /speckit-*) vs standalone mode (drive SDD via .specs/<slug>/).
metadata:
  category: spec
  tags: [spec, sdd, speckit, detection, mode-selection]
user-invocable: false
---

# Speckit Detection

> Composed by `task-spec-*` workflows. Run once per workflow run, after `behavioral-principles`. Read-only.

## Rules

- Evidence-based only: marker files or CLI presence. Never infer from project name or chat.
- Output mode + evidence so the consuming workflow can explain itself.
- If `.specify/` exists at all, prefer **speckit-installed** (Spec Kit owns artifacts).
- CLI on `$PATH` alone is not enough: project must also have `.specify/`.

## Decision Table

| `.specify/` | `.specs/` | Mode               | Note                                                      |
| ----------- | --------- | ------------------ | --------------------------------------------------------- |
| present     | -         | speckit-installed  | -                                                         |
| present     | present   | speckit-installed  | Flag duplication; existing `.specs/` not silently dropped |
| absent      | present   | standalone         | -                                                         |
| absent      | absent    | standalone         | New project; first write creates `.specs/`                |
| partial     | -         | standalone         | Recommend `speckit init` if user intended speckit mode    |

CLI check (informational, recorded in evidence):

```bash
command -v speckit >/dev/null 2>&1 && echo "speckit-cli-present"
```

## Output Format

```yaml
mode: speckit-installed | standalone
evidence:
  specify_dir_present: true | false
  specs_dir_present: true | false
  speckit_cli_on_path: true | false
  constitution_present: true | false   # .specify/memory/constitution.md
  feature_json_present: true | false   # .specify/feature.json (resolved feature directory)
  feature_json_path: <string or null>  # value of feature_directory if present (e.g., specs/003-user-auth)
  extensions_yml_present: true | false # .specify/extensions.yml (hook registration)
notes: |
  Required when both .specify/ and .specs/ exist, or when configuration is unusual.
next_action_hint: |
  speckit-installed -> delegate to /speckit-<command>; pre/post-process with our atomics.
                       Read the active feature directory from .specify/feature.json (if present)
                       rather than inferring it from the git branch name.
  standalone        -> use spec-artifact-paths to resolve .specs/<slug>/* and write artifacts.
```

## Edge Cases

- **Monorepo:** detect against the workflow's working directory; if sub-projects diverge, ask which scope applies.
- **Ambiguous `.specify/`** (empty or partial): treat as standalone, surface the ambiguity.

## Avoid

- State-changing commands during detection (`speckit init`, etc.).
- Picking a mode based on what the workflow wants vs. what the project shows.
- Caching across separate workflow runs (re-detect every run).
