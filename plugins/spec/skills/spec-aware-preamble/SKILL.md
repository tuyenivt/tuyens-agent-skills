---
name: spec-aware-preamble
description: Spec-aware preamble for stack workflows - detects .specs/<slug>/ artifacts and loads spec.md / plan.md / tasks.md in place of GATHER/DESIGN phases.
metadata:
  category: spec
  tags: [spec, sdd, spec-aware, preamble, gather-design]
user-invocable: false
---

# Spec-Aware Preamble

> Composed by stack workflows (`task-*-new`, `task-code-test`, `task-code-review`, `task-pr-create`, `task-code-debug`). Runs after `behavioral-principles` and `stack-detect`, before the workflow's own GATHER.

## Rules

- Detection is evidence-based: `--spec <slug>` first, otherwise a slug derived from the feature description matched against `.specs/`.
- The spec is source of truth: out-of-scope is a hard fence, NFRs are constraints, ACs are the test contract.
- Never edit `spec.md`/`plan.md`/`tasks.md` from a consuming workflow - propose amendments to the user.
- Never silently override the spec or pick a side when chat contradicts it - surface the conflict.
- If no spec is found, run the workflow normally (do not skip GATHER/DESIGN).

## Procedure

1. **Resolve slug.** Use `--spec <slug>` if given; otherwise derive via `Use skill: spec-artifact-paths`. Ask if multiple `.specs/` slugs plausibly match.
2. **Check existence** via `spec-artifact-paths`. Choose mode:

   | spec | plan | tasks | Mode        |
   | ---- | ---- | ----- | ----------- |
   | -    | -    | -     | `no-spec`   |
   | y    | -    | -     | `spec-only` |
   | y    | y    | -     | `spec+plan` |
   | y    | y    | y     | `full-spec` |

3. **Load present artifacts.** If `spec.md` has unresolved blocker findings, stop and recommend `task-spec-clarify`.
4. **Reconcile chat input vs. spec:**
   - **Aligned** (chat narrows scope): proceed.
   - **Contradicts**: stop, ask amend / ignore-chat / abort.
   - **Out of scope per spec**: stop, recommend `task-spec-clarify` or explicit amendment.

## Output Format

```yaml
mode: no-spec | spec-only | spec+plan | full-spec
slug: <slug-or-null>
artifacts:
  spec_path: <path-or-null>
  plan_path: <path-or-null>
  tasks_path: <path-or-null>
loaded:                                # empty when mode == no-spec
  acceptance_criteria: [...]
  nfrs: [<category: target>, ...]
  out_of_scope: [...]
  api_contract: <summary-or-null>
  data_model: <summary-or-null>
  next_task: <T<NN>: name>             # only when mode == full-spec
conflicts: []                          # populated when chat contradicts spec
notes: |
  Required when conflicts is non-empty or state is degraded (spec empty, orphan tasks, etc.).
```

## Consuming Workflow Contract

| Mode        | Behavior                                                                                              |
| ----------- | ----------------------------------------------------------------------------------------------------- |
| `no-spec`   | Run normal GATHER and DESIGN.                                                                         |
| `spec-only` | Skip GATHER. Run DESIGN constrained to ACs + NFRs.                                                    |
| `spec+plan` | Skip GATHER and DESIGN. Use `plan.md` as design. Go to IMPLEMENT.                                     |
| `full-spec` | As `spec+plan`. For `task-spec-implement`, scope to `next_task` only.                                 |

Out-of-scope items are hard fences in every non-`no-spec` mode.

## Edge Cases

- **Slug ambiguity**: ask. Do not pick.
- **Spec empty/malformed**: treat as `no-spec`; recommend re-running `task-spec-specify`.
- **`tasks.md` orphaned** (no `plan.md`): downgrade to `spec-only` and surface.
- **Multiple in-progress markers in `tasks.md`**: `task-spec-implement` resumes at first `[ ]`; other workflows ignore status.

## Avoid

- Editing artifacts from a consuming workflow.
- Loading a different feature's slug because chat description shared words.
- Running normal GATHER when a spec is loaded (the spec replaces it).
