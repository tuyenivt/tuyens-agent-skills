---
name: spec-aware-preamble
description: Spec-aware preamble for stack workflows - detect .specs/<slug>/ artifacts, extract ACs/NFRs/scope, replace GATHER/DESIGN, surface conflicts.
metadata:
  category: spec
  tags: [spec, sdd, spec-aware, preamble, gather-design]
user-invocable: false
---

# Spec-Aware Preamble

> Composed by stack workflows after `behavioral-principles` and `stack-detect`, before the workflow's own GATHER.

## When to Use

A stack workflow is about to run GATHER/DESIGN and a `.specs/<slug>/` directory may exist. The preamble decides whether spec artifacts replace those phases and surfaces chat-vs-spec conflicts.

## Rules

- Spec is source of truth: out-of-scope is a hard fence, NFRs are constraints, ACs are the test contract.
- Never edit `spec.md` / `plan.md` / `tasks.md`. Propose amendments to the user.
- Match chat-vs-spec semantically, not by substring (e.g., "let admins disable abusive uploads" overlaps an out_of_scope item "admin moderation of uploads").
- If `spec.md` is **unresolved**, halt and recommend `task-spec-clarify`. Unresolved means either:
  - `spec.md` contains any `[NEEDS CLARIFICATION]` marker, OR
  - `clarifications.md` has open questions (lines starting with `Q:` with no following `A:`).
- The output field is `spec_state` (not `mode`) to disambiguate from `speckit-detect`'s `mode`.

## Patterns

### 1. Resolve slug

Use `--spec <slug>` if provided. Otherwise pass the workflow's feature title (the canonical chat-supplied name, not the full prompt) to `spec-artifact-paths`. If two or more `.specs/` entries plausibly match, ask the user.

### 2. Detect state

| spec | plan | tasks | `spec_state`              |
| ---- | ---- | ----- | ------------------------- |
| -    | -    | -     | `no-spec`                 |
| y    | -    | -     | `spec-only`               |
| y    | y    | -     | `spec+plan`               |
| y    | y    | y     | `full-spec`               |
| y    | -    | y     | `spec-only` + `notes` (orphan tasks.md) |

### 3. Check unresolved state

Scan `spec.md` for `[NEEDS CLARIFICATION]` and `clarifications.md` for unanswered `Q:` lines. If found, halt: emit `spec_state` plus `notes` and recommend `task-spec-clarify`. `loaded` may be empty on halt.

### 4. Extract

- From `spec.md`: `acceptance_criteria` (AC list with ids), `nfrs` (`<category>: <target>`), `out_of_scope` (verbatim bullets).
- From `plan.md`: `api_contract`, `data_model`.
- From `tasks.md` (only when `full-spec`): `next_task` = first `[~]` (resume breadcrumb) else first `[ ]` whose deps are all `[x]`, formatted `T<NN>: <name>`.

### 5. Reconcile chat vs. spec

For each chat-provided requirement: if it restates/narrows an AC, honors NFRs, and stays in scope, it is **aligned** - proceed with no entry. Otherwise append one `conflicts` entry using the first matching row:

| `kind`            | Trigger                                                         | `remedy` |
| ----------------- | --------------------------------------------------------------- | -------- |
| `out-of-scope`    | Chat overlaps an `out_of_scope` item (semantic match)           | `amend` (default); `clarify` if overlap is ambiguous |
| `contradicts-ac`  | Chat contradicts an existing AC                                  | `clarify` |
| `violates-nfr`    | Chat would breach an NFR target                                  | `amend` if user accepts cost; `abort` otherwise |
| `orthogonal`      | Chat introduces a requirement the spec neither covers nor excludes | `clarify` |

If `conflicts` is non-empty, halt and surface. Quote both chat phrase and `spec_ref` text.

## Output Format

```yaml
spec_state: no-spec | spec-only | spec+plan | full-spec
slug: <slug-or-null>
artifacts:
  spec_path: <path-or-null>
  plan_path: <path-or-null>
  tasks_path: <path-or-null>
loaded:                                # empty when spec_state == no-spec OR halted at unresolved
  acceptance_criteria: [<AC-id: text>, ...]
  nfrs: [<category: target>, ...]
  out_of_scope: [...]
  api_contract: <summary-or-null>
  data_model: <summary-or-null>
  next_task: <T<NN>: name>             # only when spec_state == full-spec
conflicts:                             # empty when chat aligns with spec
  - kind: out-of-scope | contradicts-ac | violates-nfr | orthogonal
    chat: "<verbatim quote>"
    spec_ref: "<section + AC/line id + verbatim spec text>"
    remedy: clarify | amend | abort
notes: |
  Required when conflicts is non-empty, spec is unresolved, or state is degraded.
```

### Example conflict entry

```yaml
conflicts:
  - kind: out-of-scope
    chat: "let admins disable abusive uploads"
    spec_ref: "## Out of Scope, item 2: 'admin moderation of uploads'"
    remedy: amend
```

### Consuming workflow behavior

| `spec_state` | Behavior                                                                                   |
| ------------ | ------------------------------------------------------------------------------------------ |
| `no-spec`    | Run normal GATHER and DESIGN.                                                              |
| `spec-only`  | Skip GATHER. Run DESIGN constrained to `acceptance_criteria` + `nfrs` + `out_of_scope`.    |
| `spec+plan`  | Skip GATHER and DESIGN. Use `plan.md` as design. Go to IMPLEMENT.                          |
| `full-spec`  | As `spec+plan`. For `task-spec-implement`, scope to `next_task` only.                      |

Non-empty `conflicts` halts the workflow regardless of state.

## Avoid

- Loading a different feature's slug because the chat description shared words with it.
- Picking a side silently when chat contradicts the spec - always record a `conflicts` entry.
