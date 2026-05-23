---
name: spec-aware-preamble
description: Spec-aware preamble for stack workflows - detect .specs/<slug>/ artifacts, extract ACs/NFRs/scope, replace GATHER/DESIGN, surface conflicts.
metadata:
  category: spec
  tags: [spec, sdd, spec-aware, preamble, gather-design]
user-invocable: false
---

# Spec-Aware Preamble

> Composed by stack workflows (`task-*-new`, `task-code-test`, `task-code-review`, `task-pr-create`, `task-code-debug`). Runs after `behavioral-principles` and `stack-detect`, before the workflow's own GATHER.

## When to Use

A stack or task workflow is about to run GATHER/DESIGN and a `.specs/<slug>/` feature directory may exist. The preamble decides whether spec artifacts replace those phases and surfaces any chat-vs-spec conflicts before downstream steps run.

## Rules

- Detection is evidence-based: prefer `--spec <slug>`, otherwise derive a slug and match it against `.specs/`. Ask on ambiguity; never guess.
- Spec is source of truth: out-of-scope is a hard fence, NFRs are constraints, ACs are the test contract.
- Never edit `spec.md` / `plan.md` / `tasks.md` from a consuming workflow. Propose amendments to the user.
- Never silently override the spec when chat contradicts it. Surface every conflict using the schema below.
- If `spec.md` is in an **unresolved** state, stop and recommend `task-spec-clarify`. **Unresolved** means either:
  - `spec.md` contains any `[NEEDS CLARIFICATION]` marker, OR
  - `clarifications.md` has open questions (lines starting with `Q:` that have no following `A:` answer).
- If no spec is found, emit `mode: no-spec` and let the workflow run GATHER/DESIGN normally.

## Patterns

### 1. Resolve slug

Use `--spec <slug>` if provided. Otherwise delegate to `spec-artifact-paths` to derive a slug from the feature description. If two or more `.specs/` entries plausibly match, ask the user; do not pick.

### 2. Detect mode

Check artifact existence via `spec-artifact-paths`. Emit one mode:

| spec | plan | tasks | Mode        |
| ---- | ---- | ----- | ----------- |
| -    | -    | -     | `no-spec`   |
| y    | -    | -     | `spec-only` |
| y    | y    | -     | `spec+plan` |
| y    | y    | y     | `full-spec` |

If `tasks.md` exists without `plan.md`, downgrade to `spec-only` and record the anomaly in `notes`.

### 3. Check unresolved state

Before extracting, scan `spec.md` for `[NEEDS CLARIFICATION]` and `clarifications.md` for unanswered `Q:` lines. If found, halt: emit the mode plus `notes` describing the unresolved items and recommend `task-spec-clarify`. Do not extract further.

### 4. Extract

Pull the structured fields the consuming workflow will parse. For each present artifact:

- From `spec.md`: `acceptance_criteria` (verbatim AC list with ids), `nfrs` (`<category>: <target>` pairs), `out_of_scope` (verbatim bullets).
- From `plan.md`: `api_contract` (endpoint/contract summary), `data_model` (entities + key fields).
- From `tasks.md` (only when mode is `full-spec`): `next_task` = the first `[ ]` (unchecked) task line, formatted `T<NN>: <name>`.

### 5. Reconcile chat vs. spec

For each chat-provided requirement, classify against the extracted fields:

- **Aligned** (chat restates or narrows an AC / honors NFRs / stays in scope): proceed; no conflict entry.
- **Conflict**: append an entry to `conflicts` using the schema below. After classification, if `conflicts` is non-empty, stop and surface them. Do not proceed to the workflow's next phase.

Conflict decision tree (`kind` -> remedy):

| `kind`            | Trigger                                              | Recommended `remedy` |
| ----------------- | ---------------------------------------------------- | -------------------- |
| `out-of-scope`    | Chat asks for work listed under `out_of_scope`       | `clarify` or `amend` |
| `contradicts-ac`  | Chat contradicts an existing AC                      | `clarify`            |
| `violates-nfr`    | Chat would breach an NFR target                      | `amend` or `abort`   |

`clarify` -> recommend running `task-spec-clarify`. `amend` -> user must edit `spec.md` explicitly. `abort` -> drop the chat-proposed change.

## Output Format

```yaml
mode: no-spec | spec-only | spec+plan | full-spec
slug: <slug-or-null>
artifacts:
  spec_path: <path-or-null>
  plan_path: <path-or-null>
  tasks_path: <path-or-null>
loaded:                                # empty when mode == no-spec
  acceptance_criteria: [<AC-id: text>, ...]
  nfrs: [<category: target>, ...]
  out_of_scope: [...]
  api_contract: <summary-or-null>
  data_model: <summary-or-null>
  next_task: <T<NN>: name>             # only when mode == full-spec
conflicts:                             # empty when chat aligns with spec
  - kind: out-of-scope | contradicts-ac | violates-nfr
    chat: <quote or paraphrase of the chat item>
    spec_ref: <section + line/AC id from spec.md>
    remedy: clarify | amend | abort
notes: |
  Required when conflicts is non-empty, spec is unresolved, or state is degraded
  (orphan tasks.md, malformed spec, slug ambiguity resolved by user).
```

### Consuming workflow behavior

| Mode        | Behavior                                                                              |
| ----------- | ------------------------------------------------------------------------------------- |
| `no-spec`   | Run normal GATHER and DESIGN.                                                         |
| `spec-only` | Skip GATHER. Run DESIGN constrained to `acceptance_criteria` + `nfrs` + `out_of_scope`. |
| `spec+plan` | Skip GATHER and DESIGN. Use `plan.md` (via `api_contract` + `data_model`) as design. Go to IMPLEMENT. |
| `full-spec` | As `spec+plan`. For `task-spec-implement`, scope to `next_task` only.                 |

Non-empty `conflicts` halts the consuming workflow regardless of mode.

## Avoid

- Editing `spec.md`, `plan.md`, or `tasks.md` from a consuming workflow.
- Loading a different feature's slug because the chat description shared words with it.
- Running normal GATHER when a spec is loaded (the spec replaces it).
- Picking a side silently when chat contradicts the spec - always record a `conflicts` entry.
- Proceeding to extraction while `[NEEDS CLARIFICATION]` markers or open questions remain.
