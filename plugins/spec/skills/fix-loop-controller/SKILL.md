---
name: fix-loop-controller
description: Decide whether an orchestrated multi-agent run should loop back to the dev step, escalate to the user, or proceed. Reads the handoff directory written by upstream agents, classifies the latest envelope, applies iteration caps, and emits a structured next-step decision. Composed by `task-spec-orchestrate`.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, fix-loop, control]
user-invocable: false
---

# Fix Loop Controller

> This atomic is composed by `task-spec-orchestrate` - do not invoke directly. It reads handoff envelopes following `agent-handoff-contract` and emits a routing decision; it never writes envelopes itself.

## When to Use

- Inside `task-spec-orchestrate` after every step that can fail or surface issues (`test`, `review`, `fix`)
- When orchestration needs to decide between: continue forward, loop back to `dev` with feedback, or stop and surface to user
- When iteration counts must be checked against the configured cap before another loop is permitted

**Not for:** Initial step routing (the orchestrator chooses the first step itself), single-agent skills, ad-hoc agent runs outside `task-spec-orchestrate`.

## Rules

- Decisions MUST be derivable from the handoff directory alone - no hidden state
- Iteration count is computed by counting `step: fix` envelopes in the directory; never tracked in a side channel
- Default iteration cap: **3 fix loops**; hard cap: **5**. The hard cap MUST NOT be exceeded regardless of caller flags
- A `status: blocked` or `status: needs-clarification` envelope ALWAYS routes to `escalate` - the controller never silently skips user-facing blockers
- A `status: failed` envelope routes to `loop` only if the iteration cap has not been reached; otherwise routes to `escalate`
- A `status: complete` envelope with non-empty `proposed_amendments` routes to `pause-for-amendment` - the user must accept, reject, or edit the amendment before the pipeline resumes
- The controller does not read code, run tests, or invoke agents - it only reads handoff frontmatter (and the evaluation sidecar, when present) and emits a decision
- **Signal priority:** when both an evaluation sidecar and a review envelope exist for the same ordinal, the sidecar wins. The review envelope's `status` becomes secondary - it is used only for feedback synthesis content, not for the decision. This is the post-#18 contract; before #18, only the envelope existed

## Inputs

| Input                | Source                                                                                                                                                                                                                                                                |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `handoffs_dir`       | Resolved via `Use skill: spec-artifact-paths` for the current slug                                                                                                                                                                                                    |
| `iteration_cap`      | Caller-supplied (default 3, hard cap 5). Values above 5 are clamped down with a warning                                                                                                                                                                               |
| `latest_envelope`    | The highest-ordinal file in `handoffs_dir`. Required - if missing, return `error: no-envelopes`                                                                                                                                                                       |
| `evaluation_sidecar` | Optional. When `task-spec-orchestrate` runs with `--with-evaluation`, it writes `<NN>-review-score.yaml` next to the matching review envelope. Controller reads this sidecar AFTER identifying the latest envelope and routes on `score.status` as the primary signal |

## Decision Procedure

1. List `handoffs_dir`, parse frontmatter for every file, sort by ordinal ascending.
2. If list is empty -> emit `error: no-envelopes`. Do not invent a default; the orchestrator has not run.
3. If two envelopes share the same ordinal -> emit `error: contract-violation` with the offending ordinals. Stop.
4. Identify the **latest envelope** (highest ordinal).
5. Count `fix_iterations = number of envelopes with step == "fix"`.
6. **Evaluation sidecar check (post-#18):** if the latest envelope has `step: review`, look for a sidecar `<NN>-review-score.yaml` at the same ordinal. If present and parseable, route via the **Evaluation Decision Table** below; the score is the primary signal. If the sidecar is missing, errored, or marks `status: error`, fall back to the standard envelope-based decision table (the pre-#18 behavior).
7. For all other cases (no review envelope, no sidecar, sidecar errored), apply the standard Decision Table below using the latest envelope's `status` and `next` fields.

## Decision Table

| Latest `status`         | Other signals                     | Decision              | Routed step                               | Reason                                                      |
| ----------------------- | --------------------------------- | --------------------- | ----------------------------------------- | ----------------------------------------------------------- |
| `complete`              | `next == "done"`, no amendments   | `proceed-done`        | (pipeline ends)                           | Pipeline finished cleanly                                   |
| `complete`              | `next != "done"`, no amendments   | `proceed-next`        | `latest.next`                             | Continue to the agent's nominated next step                 |
| `complete`              | `proposed_amendments` non-empty   | `pause-for-amendment` | (stop, ask user)                          | Spec/plan/tasks gap surfaced - user decides before resuming |
| `failed`                | `fix_iterations < iteration_cap`  | `loop`                | `dev` (then `test`/`review` per pipeline) | Failure within budget - send back with feedback             |
| `failed`                | `fix_iterations >= iteration_cap` | `escalate`            | (stop, ask user)                          | Fix loop exhausted - human decision needed                  |
| `blocked`               | any                               | `escalate`            | (stop, ask user)                          | External action required (env, infra, missing dependency)   |
| `needs-clarification`   | any                               | `escalate`            | (stop, ask user)                          | Blocking question(s) must be answered                       |
| any other / unparseable | -                                 | `error`               | -                                         | Surface envelope contents and stop                          |

`proceed-done` and `proceed-next` are different on purpose: `proceed-done` ends the orchestration; `proceed-next` continues it.

## Evaluation Decision Table (post-#18, when sidecar is present)

When the latest envelope is `step: review` AND a parseable `<NN>-review-score.yaml` sidecar exists at the matching ordinal, the controller routes on `score.status` from the sidecar **instead of** the envelope status. The review envelope's content still feeds feedback synthesis, but it does not drive the decision.

| `score.status` | Other signals                                | Decision              | Routed step      | Reason                                                                                                              |
| -------------- | -------------------------------------------- | --------------------- | ---------------- | ------------------------------------------------------------------------------------------------------------------- |
| `pass`         | review envelope has no `proposed_amendments` | `proceed-done`        | (pipeline ends)  | Spec satisfied; no amendments pending                                                                               |
| `pass`         | review envelope has `proposed_amendments`    | `pause-for-amendment` | (stop, ask user) | Score passes but amendments must be resolved before claiming done                                                   |
| `needs-fix`    | `fix_iterations < iteration_cap`             | `loop`                | `dev`            | Spec not yet satisfied - send back with `score.blocking_issues` as feedback                                         |
| `needs-fix`    | `fix_iterations >= iteration_cap`            | `escalate`            | (stop, ask user) | Iteration cap reached without reaching `pass` - human decision needed                                               |
| `fail`         | any                                          | `escalate`            | (stop, ask user) | Hard-fail signal (AC violation, drift, runner failure) - looping will not fix structural disagreement with the spec |

Hard-fail signals are surfaced verbatim from `score.hard_fail_triggers`. The controller does NOT loop on `fail` even when iterations remain - the scorer has already determined that the gap is structural, not a transient bug.

### Feedback synthesis with evaluation present

When the decision is `loop` driven by evaluation, the feedback packet uses `score.blocking_issues` as `highlights` (max 5) and references both the source review envelope and `evaluation.md`:

```yaml
feedback:
  source_envelope: <NN>-review-<agent>.md
  source_step: review
  evaluation_path: .specs/<slug>/evaluation.md
  iteration: <next fix iteration>
  blocker_count: <count from score.signals>
  highlights:
    - <one-line per score.blocking_issues entry, max 5>
  full_findings_path: <relative path to source envelope>
  score_overall: <int>
  score_status: needs-fix
```

The orchestrator passes this verbatim to the next `dev` agent's prompt.

## Feedback Synthesis (for `loop` decisions)

When the decision is `loop`, the controller synthesizes a **feedback packet** that the next `dev` step reads:

```yaml
feedback:
  source_envelope: 04-review-spring-security-reviewer.md
  source_step: review
  iteration: 2 # this will be the Nth fix loop
  blocker_count: 3
  highlights:
    - <one-line summary of each blocker, max 5>
  full_findings_path: <relative path to the source envelope>
```

The packet is emitted in the controller's output. The orchestrator includes it verbatim in the next `dev` agent's prompt. The controller does NOT modify the source envelope or write a new one.

## Output Format

The controller emits a YAML block:

```yaml
decision: proceed-done | proceed-next | loop | pause-for-amendment | escalate | error
routed_step: architect | dev | test | review | fix | done | (omitted on escalate/error)
reason: <one-line explanation - shown to user and logged>
fix_iterations: <integer>
iteration_cap: <integer used (post-clamp)>
latest_envelope: <filename>
evaluation_sidecar: <filename or null> # populated when sidecar drove the decision
signal_source: envelope | evaluation # which input drove the decision
feedback: <feedback packet, only when decision is "loop">
amendments: <copy of latest.proposed_amendments, only when decision is "pause-for-amendment">
escalation: <object with status, blocking_questions, suggested_actions; only when decision is "escalate">
errors: <list of strings, only when decision is "error">
```

This is parsed by `task-spec-orchestrate` to choose its next step. No prose output - the contract is the YAML.

## Handling Edge Cases

- **Caller passes `iteration_cap > 5`**: clamp to 5, set `iteration_cap` in output to 5, include a one-line note in `reason`.
- **Caller passes `iteration_cap < 1`**: clamp to 1; a single attempt with no loop is legal.
- **Latest envelope is `step: fix` and `status: complete`**: a fix step succeeded; route to whatever the fix envelope's `next` says (typically `test`). Do not auto-loop just because it was a fix.
- **Latest envelope is `step: fix` and `status: failed`**: this counts toward `fix_iterations` already (it was just written). Apply the failed-row of the decision table normally.
- **Out-of-order ordinals (gap, e.g., 01, 02, 04)**: emit `decision: error` with `errors: ["ordinal gap detected: missing 03"]`. Do not skip silently - something deleted or renamed an envelope.
- **`proposed_amendments` present but `status` is `failed`**: decision is `loop` (or `escalate` past cap). Amendments are recorded but not acted on; the user can review them when the loop terminates. Include `amendments_present: true` in `reason`.
- **`status: complete` with `next: done` AND `proposed_amendments` non-empty**: decision is `pause-for-amendment` (amendments win over `done` - never silently drop a surfaced gap).
- **Sidecar parse error**: treat as if no sidecar exists. Emit `signal_source: envelope` and add a `notes` line in `reason` so the orchestrator can warn the user. Do not stop - the envelope-based path is a valid fallback.
- **Sidecar present but envelope is not `step: review`**: ignore the sidecar. Sidecars are only meaningful next to review envelopes by contract.
- **Multiple sidecars at different ordinals**: use only the sidecar at the latest envelope's ordinal. Older sidecars are historical and never drive current decisions.

## Avoid

- Tracking iteration count anywhere other than the handoff directory - the filesystem is authoritative
- Emitting a `proceed-next` decision that contradicts `latest.next` - if you disagree with the agent's next, that's an `escalate` not a silent override
- Synthesizing feedback that paraphrases the source envelope - reference the path; do not duplicate content
- Increasing the cap beyond 5 under any caller flag - the hard cap is a contract safety, not a knob
- Returning a `decision` without a `reason` - downstream logging and user surfacing both depend on it

## Notes

- The controller is **stateless** between invocations. The orchestrator calls it after every step; each call re-derives state from disk.
- Pairing with `agent-handoff-contract`: the controller is the only consumer that interprets `status` semantics; agents themselves only declare status. This separates "what happened" (agent) from "what to do next" (controller).
- When the decision is `escalate`, the orchestrator surfaces the blocker to the user with the source envelope path; the user can amend, retry, or abandon. Resumption picks up from the next ordinal once a new envelope is written.
