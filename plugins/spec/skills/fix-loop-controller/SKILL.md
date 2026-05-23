---
name: fix-loop-controller
description: Decide loop / escalate / proceed for orchestrated multi-agent SDD runs - classifies handoff envelopes, applies iteration caps, emits decision.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, fix-loop, control]
user-invocable: false
---

# Fix Loop Controller

> Composed by `task-spec-orchestrate` after every step that can fail (`test`, `review`, `fix`). Stateless: re-derives everything from `handoffs_dir` on each call. Reads envelopes (and optional evaluation sidecars) - never writes.

## When to Use

Invoked once per orchestration iteration to route the next step. Inputs: `handoffs_dir` (from `spec-artifact-paths`), `iteration_cap` (default 3).

## Rules

- All state derives from `handoffs_dir`. Filesystem is authoritative; never cache iteration count in workflow memory.
- `iteration_cap` clamps to `[1, 5]`; the hard cap of 5 is a safety, not a knob. Clamp adjustments are noted in `reason`.
- `fix_iterations` = count of envelopes with `step: fix`. Loop-routed dev re-runs are written as `step: fix` per `agent-handoff-contract`, so they count; raw `dev` envelopes do not.
- When latest is `step: review` and a parseable `<NN>-review-score.yaml` exists at the same ordinal, route via the **Evaluation Decision Table**. Otherwise use the **Standard Decision Table**. The envelope still feeds feedback synthesis even when the sidecar drives the decision.
- Every output carries a `reason`. No silent overrides: if `proceed-next`'s routed step would contradict `latest.next`, escalate instead.

## Patterns

### Procedure

1. Sort envelopes by ordinal. Empty -> `error.code: no-envelopes`. Duplicate ordinals -> `contract-violation`. Gap (e.g. 01, 02, 04) -> `ordinal-gap`. Frontmatter unparseable -> `envelope-parse`.
2. Identify latest envelope. Count `fix_iterations`.
3. Pick the table: sidecar present + parseable + latest is `step: review` -> Evaluation; else Standard. Sidecar parse error -> Standard, with `evaluation_sidecar` set to the filename and a note in `reason`.

### Standard Decision Table

| Latest `status`         | Other signals                     | Decision              | Routed step   |
| ----------------------- | --------------------------------- | --------------------- | ------------- |
| `complete`              | `next == "done"`, no amendments   | `proceed-done`        | -             |
| `complete`              | `next != "done"`, no amendments   | `proceed-next`        | `latest.next` |
| `complete`              | amendments non-empty              | `pause-for-amendment` | -             |
| `failed`                | `fix_iterations < cap`            | `loop`                | `dev`         |
| `failed`                | `fix_iterations >= cap`           | `escalate`            | -             |
| `blocked`               | -                                 | `escalate`            | -             |
| `needs-clarification`   | -                                 | `escalate`            | -             |
| (unknown status)        | -                                 | `error`               | -             |

### Evaluation Decision Table (sidecar present)

| `score.status` | Other signals                       | Decision              | Routed step |
| -------------- | ----------------------------------- | --------------------- | ----------- |
| `pass`         | no `proposed_amendments`            | `proceed-done`        | -           |
| `pass`         | amendments non-empty                | `pause-for-amendment` | -           |
| `needs-fix`    | `fix_iterations < cap`              | `loop`                | `dev`       |
| `needs-fix`    | `fix_iterations >= cap`             | `escalate`            | -           |
| `fail`         | -                                   | `escalate`            | -           |

`fail` surfaces `score.hard_fail_triggers` verbatim in `escalation.status`; the scorer (`eval-scorer`) owns the structural-vs-transient distinction.

### Step-Fix Edge

- Latest `step: fix`, `status: complete` -> route to `latest.next` (typically `test`); do not auto-loop because a fix happened.
- Latest `step: fix`, `status: failed` -> apply the `failed` row. The failed fix already counts in `fix_iterations`.

## Output Format

```yaml
decision: proceed-done | proceed-next | loop | pause-for-amendment | escalate | error
routed_step: architect | dev | test | review | fix | done   # omitted on escalate/error
reason: <one line - logged + shown to user>
fix_iterations: <int>
iteration_cap: <int after clamp>
latest_envelope: <filename>
evaluation_sidecar: <filename or null>     # filename even on parse error
signal_source: envelope | evaluation       # `envelope` when sidecar absent or parse-errored
feedback: <feedback packet, when decision == "loop">
amendments: <latest.proposed_amendments, when decision == "pause-for-amendment">
escalation: { status, blocking_questions, suggested_actions }   # when "escalate"
errors:                                                          # when "error"
  - { code: no-envelopes | contract-violation | ordinal-gap | envelope-parse | sidecar-parse,
      detail: <one line> }
```

`feedback` (loop only) - reference paths, do not paraphrase:

```yaml
feedback:
  source_envelope: <NN>-<step>-<agent>.md
  source_step: review | test | fix
  iteration: <fix_iterations + 1>
  blocker_count: <int>                              # score.blocking_issues.length when sidecar drove;
                                                    # else count of review-body blockers, or len(blocking_questions)
  highlights: [<one-line summary, max 5>]           # from score.blocking_issues when signal_source == evaluation
  full_findings_path: <relative path to envelope>
  evaluation_path: .specs/<slug>/evaluation.md      # only when signal_source == evaluation
  score_overall: <int>                              # only when signal_source == evaluation
  score_status: needs-fix                           # only when signal_source == evaluation
```

## Avoid

- Tracking iteration count outside the handoff directory.
- Emitting `proceed-next` with a `routed_step` that contradicts `latest.next` - that disagreement is `escalate`.
- Paraphrasing source envelopes into `feedback` - reference paths only.
- Treating a sidecar next to a non-review envelope as authoritative - ignore it.
- Counting raw `step: dev` envelopes toward `fix_iterations` - only `step: fix` envelopes count.
- Returning `decision` without `reason`.
