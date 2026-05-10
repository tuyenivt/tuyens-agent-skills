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

## Rules

- All state derives from `handoffs_dir` - filesystem is authoritative.
- `fix_iterations` = count of `step: fix` envelopes. Default cap 3, hard cap 5 (clamped, never exceeded).
- `blocked` and `needs-clarification` ALWAYS escalate.
- `proceed-done` (ends pipeline) and `proceed-next` (continues) are distinct decisions.
- `proposed_amendments` non-empty -> `pause-for-amendment`, even if `next: done`. Never silently drop a surfaced gap.
- **Sidecar wins** when `<NN>-review-score.yaml` exists next to the latest review envelope. The envelope's content still feeds feedback synthesis but no longer drives the decision. Hard fails (`fail`) never loop, even with iterations remaining.

## Inputs

`handoffs_dir` (from `spec-artifact-paths`), `iteration_cap` (default 3, max 5).

## Procedure

1. Sort envelopes by ordinal. Empty -> `error: no-envelopes`. Duplicate ordinals -> `error: contract-violation`. Gap (e.g. 01, 02, 04) -> `error: ordinal-gap`.
2. Identify latest envelope. Count `fix_iterations`.
3. If latest is `step: review` and a parseable `<NN>-review-score.yaml` exists at the same ordinal, route via the **Evaluation Decision Table**. On parse error or missing sidecar, fall back to the **Standard Decision Table**.

## Standard Decision Table

| Latest `status`         | Other signals                     | Decision              | Routed step  |
| ----------------------- | --------------------------------- | --------------------- | ------------ |
| `complete`              | `next == "done"`, no amendments   | `proceed-done`        | -            |
| `complete`              | `next != "done"`, no amendments   | `proceed-next`        | `latest.next` |
| `complete`              | amendments non-empty              | `pause-for-amendment` | -            |
| `failed`                | `fix_iterations < cap`            | `loop`                | `dev`        |
| `failed`                | `fix_iterations >= cap`           | `escalate`            | -            |
| `blocked`               | -                                 | `escalate`            | -            |
| `needs-clarification`   | -                                 | `escalate`            | -            |
| (other / unparseable)   | -                                 | `error`               | -            |

## Evaluation Decision Table (sidecar present)

| `score.status` | Other signals                       | Decision              | Routed step |
| -------------- | ----------------------------------- | --------------------- | ----------- |
| `pass`         | no `proposed_amendments`            | `proceed-done`        | -           |
| `pass`         | amendments non-empty                | `pause-for-amendment` | -           |
| `needs-fix`    | `fix_iterations < cap`              | `loop`                | `dev`       |
| `needs-fix`    | `fix_iterations >= cap`             | `escalate`            | -           |
| `fail`         | -                                   | `escalate`            | -           |

`fail` does not loop - the scorer has determined the gap is structural, not a transient bug. Hard-fail triggers are surfaced verbatim from `score.hard_fail_triggers`.

## Output Format

```yaml
decision: proceed-done | proceed-next | loop | pause-for-amendment | escalate | error
routed_step: architect | dev | test | review | fix | done   # omitted on escalate/error
reason: <one line - logged + shown to user>
fix_iterations: <int>
iteration_cap: <int after clamp>
latest_envelope: <filename>
evaluation_sidecar: <filename or null>
signal_source: envelope | evaluation
feedback: <feedback packet, when decision == "loop">
amendments: <latest.proposed_amendments, when decision == "pause-for-amendment">
escalation: { status, blocking_questions, suggested_actions }   # when "escalate"
errors: [...]                                                   # when "error"
```

`feedback` (loop only) - reference the envelope, do not duplicate its content:

```yaml
feedback:
  source_envelope: <NN>-<step>-<agent>.md
  source_step: review | test | fix
  iteration: <next iteration index>
  blocker_count: <int>
  highlights: [<one-line summary, max 5>]   # from score.blocking_issues when sidecar drove the decision
  full_findings_path: <relative path>
  evaluation_path: .specs/<slug>/evaluation.md   # only when signal_source == evaluation
  score_overall: <int>                            # only when signal_source == evaluation
  score_status: needs-fix                         # only when signal_source == evaluation
```

## Edge Cases

- **`iteration_cap` > 5**: clamp to 5, note in `reason`. **`< 1`**: clamp to 1.
- **Latest is `step: fix`, `status: complete`**: route to `fix.next` (typically `test`). Do not auto-loop because it was a fix.
- **Latest is `step: fix`, `status: failed`**: this fix already counts in `fix_iterations`. Apply the failed-row normally.
- **Sidecar parse error**: fall back to envelope path; note it in `reason`.
- **Sidecar at non-review envelope**: ignore - sidecars are only meaningful next to review envelopes.
- **Multiple sidecars across ordinals**: only the one at the latest envelope's ordinal counts.

## Avoid

- Tracking iteration count outside the handoff directory.
- Emitting `proceed-next` that contradicts `latest.next` (disagreement is `escalate`, not silent override).
- Paraphrasing source envelopes into feedback - reference paths only.
- Raising the hard cap under any flag (it is a safety, not a knob).
- Returning `decision` without `reason`.
