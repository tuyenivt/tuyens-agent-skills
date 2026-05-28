---
name: fix-loop-controller
description: Decide loop / escalate / proceed for orchestrated multi-agent SDD runs - classifies handoff envelopes, applies iteration caps, emits decision.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, fix-loop, control]
user-invocable: false
---

# Fix Loop Controller

> Composed by `task-spec-orchestrate` after every step that can fail. Stateless: re-derives everything from `handoffs_dir` on each call. Reads envelopes (and optional evaluation sidecars); never writes.

## When to Use

Once per orchestration iteration to route the next step. Inputs: `handoffs_dir` (from `spec-artifact-paths`), `iteration_cap` (default 3, clamped to `[1, 5]`).

## Rules

- All state lives in `handoffs_dir`. Never cache iteration count.
- `fix_iterations` = count of envelopes with `step: fix` (per `agent-handoff-contract`).
- A sidecar is **parseable** only if `score.status` and `score.blocking_issues` are present. Missing required fields -> append `errors[]: sidecar-parse`, fall through to Standard; `decision` is not `error` unless the envelope itself is unparseable.
- Sidecar drives the Evaluation table only when latest is `step: review` AND sidecar parseable.
- Every output carries a `reason`.

## Procedure

1. Sort envelopes by ordinal. Empty -> `error.code: no-envelopes`. Duplicate ordinals -> `contract-violation`. Gap (01, 02, 04) -> `ordinal-gap`. Frontmatter unparseable -> `envelope-parse`.
2. Identify latest envelope; count `fix_iterations`.
3. Pick table: parseable sidecar + latest is `step: review` -> Evaluation; else Standard.

## Standard Decision Table

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

## Evaluation Decision Table (sidecar present)

| `score.status` | Other signals                       | Decision              | Routed step |
| -------------- | ----------------------------------- | --------------------- | ----------- |
| `pass`         | no `proposed_amendments`            | `proceed-done`        | -           |
| `pass`         | amendments non-empty                | `pause-for-amendment` | -           |
| `needs-fix`    | `fix_iterations < cap`              | `loop`                | `dev`       |
| `needs-fix`    | `fix_iterations >= cap`             | `escalate`            | -           |
| `fail`         | -                                   | `escalate`            | -           |

On `fail`, copy `score.hard_fail_triggers` verbatim into `escalation.status`.

## Step-Fix Edge

- Latest `step: fix`, `status: complete` -> route to `latest.next` (typically `test`). Do not auto-loop because a fix happened.
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
signal_source: envelope | evaluation       # envelope when sidecar absent or parse-errored
feedback: <feedback packet, when decision == "loop">
amendments: <latest.proposed_amendments, when decision == "pause-for-amendment">
escalation: { status, blocking_questions, suggested_actions }   # when "escalate"
errors:                                                          # when "error" OR sidecar-parse fallback
  - { code: no-envelopes | contract-violation | ordinal-gap | envelope-parse | sidecar-parse,
      detail: <one line> }
```

`feedback` (loop only):

```yaml
feedback:
  source_envelope: <NN>-<step>-<agent>.md
  source_step: review | test | fix
  iteration: <fix_iterations + 1>           # the upcoming fix index
  blocker_count: <int>                      # score.blocking_issues.length when sidecar drove;
                                            # else len(latest.blocking_questions)
  highlights: [<one-line summary, max 5>]   # from score.blocking_issues when signal_source == evaluation
  full_findings_path: <relative path to envelope>
  evaluation_path: .specs/<slug>/evaluation.md      # only when signal_source == evaluation
  score_overall: <int>                              # only when signal_source == evaluation
  score_status: needs-fix                           # only when signal_source == evaluation
```

### Worked example

Envelopes `[01-architect, 02-dev:complete, 03-test:failed, 04-fix:complete, 05-test:failed]`, `iteration_cap=3`. `fix_iterations=1`, latest=`05-test` (failed). `1<3` -> `loop`, `routed_step=dev`, `feedback.iteration=2`, `source_envelope=05-test-*.md`, `signal_source=envelope`.

## Avoid

- Tracking iteration count outside `handoffs_dir`.
- Paraphrasing source envelopes into `feedback` - reference paths only.
- Treating a sidecar next to a non-review envelope as authoritative - ignore it.
- Returning `decision` without `reason`.
