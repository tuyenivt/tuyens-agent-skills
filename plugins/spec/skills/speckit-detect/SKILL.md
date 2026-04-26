---
name: speckit-detect
description: Detect whether GitHub Spec Kit is installed in the current project and decide between speckit-aware mode (delegate to `/speckit.*` commands) and standalone mode (drive the SDD pipeline ourselves using the `.specs/<slug>/` artifact convention).
metadata:
  category: spec
  tags: [spec, sdd, speckit, detection, mode-selection]
user-invocable: false
---

# Speckit Detection

> This atomic is composed by `task-spec-*` workflows - do not invoke directly. Primary consumers: every workflow in the `spec` plugin.

## When to Use

- As the first detection step (after `behavioral-principles`) inside any `task-spec-*` workflow
- Before deciding whether the workflow should delegate to a `/speckit.*` command or write artifacts to `.specs/<slug>/` itself
- Once per workflow run; cache the result for the duration of the run

## Rules

- Detection MUST be evidence-based - check for marker files or CLI presence, do not infer from project name or chat context
- Output the chosen mode AND the evidence used, so consuming workflows can explain themselves
- If both signals are present, prefer **speckit-installed** mode (Spec Kit owns artifacts when present)
- If detection is ambiguous (e.g., partial `.specify/` directory), surface the ambiguity and ask the user; do not silently pick
- Never modify the project during detection - this is a read-only inspection

## Detection Procedure

### Step 1 - Marker file check (primary)

Look for these in the project root:

| Marker                            | Signal                                                                   |
| --------------------------------- | ------------------------------------------------------------------------ |
| `.specify/` directory exists      | Spec Kit project structure - **speckit-installed**                       |
| `.specify/memory/constitution.md` | Spec Kit constitution present - strengthens speckit-installed verdict    |
| `.specs/` directory exists        | This plugin's standalone artifact root - **standalone** (already in use) |
| Neither directory present         | Either mode is possible - default to **standalone**                      |

### Step 2 - CLI check (secondary)

Check whether `speckit` is available on `$PATH`:

```bash
command -v speckit >/dev/null 2>&1 && echo "speckit-cli-present"
```

A present CLI alone is NOT sufficient to choose speckit-installed mode - the project must also have `.specify/`. A user-global CLI install with no project structure means the user has Spec Kit available but has not initialized this project with it; standalone mode still applies until they run `speckit init` (or equivalent).

### Step 3 - Mode decision

| Evidence                                  | Mode                                                 |
| ----------------------------------------- | ---------------------------------------------------- |
| `.specify/` present (with or without CLI) | speckit-installed                                    |
| `.specs/` present, no `.specify/`         | standalone                                           |
| Neither present                           | standalone (new)                                     |
| Both present                              | speckit-installed; flag the duplication for the user |

## Output Format

Emit a structured result the calling workflow can parse:

```yaml
mode: speckit-installed | standalone
evidence:
  specify_dir_present: true | false
  specs_dir_present: true | false
  speckit_cli_on_path: true | false
  constitution_present: true | false
notes: |
  Free-form note. Required when both .specify/ and .specs/ exist (explain duplication),
  or when the user should be aware of an unusual configuration.
next_action_hint: |
  speckit-installed -> "delegate to /speckit.<command>; pre/post-process with our atomics"
  standalone        -> "use spec-artifact-paths to resolve .specs/<slug>/* and write artifacts ourselves"
```

## Handling Edge Cases

- **Neither directory, but user explicitly invoked a `task-spec-*` workflow:** standalone mode; the workflow itself (or `spec-artifact-paths`) will create `.specs/` on first write.
- **`.specify/` exists but is empty or partial:** treat as ambiguous - report `mode: standalone` with a note recommending `speckit init` if the user intended speckit-installed mode.
- **Monorepo with multiple sub-projects:** detection runs against the working directory the workflow is invoked from. If sub-projects have different states, surface this and ask which scope applies.
- **`.specs/` and `.specify/` both present:** the project may be migrating between modes. Choose speckit-installed (Spec Kit is the more opinionated owner) and note the existing `.specs/` content so it is not silently abandoned.

## Avoid

- Running `speckit init` or any other state-changing command during detection
- Picking a mode based on what the workflow "wants" rather than what the project shows
- Caching detection across separate workflow runs - re-detect every run, cheap and safe
- Assuming CLI presence implies project initialization
