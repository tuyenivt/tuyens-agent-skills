---
name: spec-aware-preamble
description: Spec-aware mode preamble for stack workflows. Detects whether the current feature has artifacts under `.specs/<slug>/` (spec.md, plan.md, tasks.md) and, if so, loads them in place of the workflow's own GATHER/DESIGN phases. Single-source contract so every consuming workflow behaves identically.
metadata:
  category: spec
  tags: [spec, sdd, spec-aware, preamble, gather-design]
user-invocable: false
---

# Spec-Aware Preamble

> This atomic is composed by stack-specific `task-*-new` workflows and other spec-aware workflows (`task-code-test`, `task-code-review`, `task-pr-create`, `task-code-debug`) - do not invoke directly.

## When to Use

- As the very first content step inside a workflow that may consume SDD artifacts
- After `behavioral-principles` and `stack-detect`, before the workflow's own GATHER step
- Whenever a workflow accepts an explicit `--spec <slug>` flag OR runs in a project that may have `.specs/` artifacts for the current feature

## Rules

- Detection MUST be evidence-based: explicit `--spec <slug>` argument first, otherwise look for `.specs/<slug>/spec.md` matching a slug derived from the feature description
- Never silently skip GATHER/DESIGN if no spec is found - run the workflow as it normally would
- Never silently override the spec - if the user's chat input contradicts `spec.md`, stop and surface the conflict (do not pick a side)
- Never edit `spec.md`, `plan.md`, or `tasks.md` from the consuming workflow - propose amendments to the user instead
- A spec is the source of truth: out-of-scope items are hard fences, NFRs are constraints, acceptance criteria are the test contract

## Inputs

| Input             | How obtained                                                             |
| ----------------- | ------------------------------------------------------------------------ |
| `--spec <slug>`   | Explicit user-supplied flag                                              |
| Feature name/desc | The workflow's normal input - used to derive a candidate slug if no flag |
| Project state     | Existence of `.specs/<slug>/{spec,plan,tasks}.md`                        |

## Detection Procedure

### Step 1 - Resolve candidate slug

If the user passed `--spec <slug>`, use that slug verbatim.

Otherwise, derive a candidate slug from the feature description using `Use skill: spec-artifact-paths` (slug derivation rules). Treat the derivation as a guess - confirm with the user if multiple slugs under `.specs/` plausibly match.

### Step 2 - Check artifact existence

Use skill: spec-artifact-paths

Capture `existence` flags for `spec`, `plan`, `tasks`.

| Artifact state                             | Mode                       |
| ------------------------------------------ | -------------------------- |
| `spec` missing                             | **no-spec** - run normally |
| `spec` present, `plan` missing             | **spec-only**              |
| `spec` and `plan` present, `tasks` missing | **spec+plan**              |
| `spec`, `plan`, and `tasks` all present    | **full-spec**              |

### Step 3 - Load artifacts (if any)

For every artifact present, read it end-to-end and extract:

- **From `spec.md`:** problem, target users, user stories, acceptance criteria, NFRs, out-of-scope items, open questions still tagged blocker/major
- **From `plan.md`:** architecture overview, data model, API contract, NFR mapping, alternatives considered, risks
- **From `tasks.md`:** task list with IDs, dependencies, status markers; identify the next `[ ]` task if the consuming workflow is `task-spec-implement`

If `spec.md` has unresolved blocker findings, stop and recommend `task-spec-clarify` before continuing - do not implement against a spec that is structurally incomplete.

### Step 4 - Reconcile with user input

If the user provided a feature description in chat alongside `--spec <slug>`, compare it to `spec.md`:

- **Aligned:** proceed with the spec as source of truth; the chat input is a hint for which slice of the spec to focus on (e.g., "implement the avatar resize task")
- **Contradicts spec:** stop. Surface the contradiction. Ask the user whether to (a) treat chat as a proposed amendment to `spec.md`, (b) ignore chat and proceed with spec, or (c) abort
- **Out of scope per spec:** stop. The spec excludes the requested change. Recommend `task-spec-clarify` or amending out-of-scope explicitly

## Output Format

Emit a structured result the calling workflow can branch on:

```yaml
mode: no-spec | spec-only | spec+plan | full-spec
slug: <resolved-slug-or-null>
artifacts:
  spec_path: <path-or-null>
  plan_path: <path-or-null>
  tasks_path: <path-or-null>
loaded:
  acceptance_criteria: [<AC1, AC2, ...>]   # empty when mode == no-spec
  nfrs: [<category: target>, ...]
  out_of_scope: [<item>, ...]
  api_contract: <summary-or-null>
  data_model: <summary-or-null>
  next_task: <T<NN>: name | null>          # only when mode == full-spec
conflicts: []                              # populated if chat input contradicts spec
notes: |
  Free-form. Required when conflicts is non-empty or when the user must be informed
  of a degraded/partial state (e.g., spec exists but is empty).
```

## Consuming Workflow Contract

A consuming workflow (e.g., `task-spring-new`, `task-react-new`, `task-feature-implement`) branches on `mode`:

| Mode        | Behavior                                                                                                                                                       |
| ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `no-spec`   | Run the workflow's normal GATHER and DESIGN phases. Behave as if this preamble did not exist.                                                                  |
| `spec-only` | Use `spec.md` to skip GATHER. Run DESIGN as normal, but constrain it to acceptance criteria + NFRs.                                                            |
| `spec+plan` | Skip GATHER and DESIGN. Use `plan.md` directly as the design. Move to IMPLEMENT.                                                                               |
| `full-spec` | Skip GATHER and DESIGN. Use `plan.md` as design. If consuming workflow is task-spec-implement, pick `next_task` from `tasks.md` and implement only that scope. |

Out-of-scope items from `spec.md` are **hard fences** in every non-`no-spec` mode - the workflow must refuse to introduce them and surface the conflict if asked.

## Handling Edge Cases

- **Slug ambiguity:** multiple slugs under `.specs/` plausibly match the feature description - ask the user which one. Do not pick.
- **Feature description with no obvious slug:** treat as `no-spec` mode and proceed normally.
- **Spec exists but empty/malformed:** treat as `no-spec` mode and recommend re-running `task-spec-specify`.
- **`tasks.md` exists but `plan.md` was deleted:** treat as `spec-only` mode (cannot trust orphan tasks). Surface to user.
- **Multiple in-progress task markers (`[~]` or `[x]`) in `tasks.md`:** acceptable - `task-spec-implement` resumes from the first `[ ]`. Other consuming workflows should ignore status entirely.

## Avoid

- Editing `spec.md`, `plan.md`, or `tasks.md` from a consuming workflow - amendments are proposals, not changes
- Silently treating chat input as overriding the spec when they contradict
- Picking a slug when ambiguous - always ask
- Loading artifacts from a different feature's slug because the chat description happened to mention overlapping words
- Running the consuming workflow's normal GATHER when a spec is loaded - the spec replaces it
