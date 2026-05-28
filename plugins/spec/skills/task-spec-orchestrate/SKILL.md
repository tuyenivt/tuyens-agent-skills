---
name: task-spec-orchestrate
description: Run multi-agent SDD pipeline (architect / dev / test / review with fix loop) over a feature; handoff envelopes on filesystem, resumable.
metadata:
  category: spec
  tags: [spec, sdd, orchestration, multi-agent, pipeline]
  type: workflow
user-invocable: true
---

# Spec - Orchestrate

## When to Use

When `spec.md`, `plan.md`, and `tasks.md` exist and the user wants the full multi-agent pipeline (vs. one-task-at-a-time `task-spec-implement`), or when resuming an interrupted run.

## Inputs

| Input               | Notes                                                                                  |
| ------------------- | -------------------------------------------------------------------------------------- |
| `<slug>`            | Required. Reads `.specs/<slug>/{spec,plan,tasks}.md`; writes to `.specs/<slug>/handoffs/`. |
| `--max-iterations`  | Fix-loop cap. Default 3, clamped to `[1, 5]`.                                          |
| `--skip-review`     | Pipeline ends after `test` succeeds.                                                   |
| `--start-from`      | `architect | dev | test | review`. Aborts if any earlier step has no envelope.        |
| `--with-evaluation` | After each `review` envelope (`status: complete`), run `task-spec-evaluate`; the score sidecar drives the fix-loop signal. Skip on `failed` review (no implementation to grade). |

Abort if any of the three artifacts is missing.

## Workflow

### STEP 1 - Behavioral Principles

Use skill: behavioral-principles

### STEP 2 - Stack Detection

Use skill: stack-detect

Capture stack name and `Stack Type` (backend / frontend / fullstack). Fullstack: abort and recommend two single-stack runs.

### STEP 3 - Resolve Paths

Use skill: spec-artifact-paths

Confirm the three artifacts exist; create `handoffs_dir` if missing.

### STEP 4 - Determine Resume Point

Use skill: fix-loop-controller

If the controller returns `error.code: no-envelopes`, treat as bootstrap: start at ordinal `01`, step `architect`. Otherwise route on the controller's `decision`. If `--start-from` is set and no envelope exists for an earlier step, abort.

### STEP 5 - Select Agent

Probe `plugins/<stack>/agents/` for the file matching the role. Use this resolver per step:

| Step      | Resolver                                                                       |
| --------- | ------------------------------------------------------------------------------ |
| architect | `<framework>-architect.md` if present, else `<stack>-architect.md`             |
| dev       | `<stack>-tech-lead.md`                                                         |
| test      | `<stack>-test-engineer.md`                                                     |
| review    | See Reviewer Variant below                                                     |

Where `<framework>` is the canonical framework name for the stack when distinct (e.g., java stack -> `spring`, ruby -> `rails`, php -> `laravel`). All other stacks use `<stack>` directly.

If the required agent file does not exist, abort with the missing path. Do not silently substitute.

#### Reviewer Variant

Choose by parsing spec.md:
- `<stack>-security-engineer` if spec frontmatter `tags:` includes `security`, OR `## Security` section is non-empty, OR ACs/NFRs mention auth/PII/secrets/payments.
- Else `<stack>-performance-engineer` if any NFR row sets a metric in `{p95, p99, throughput, rps, latency}`.
- Else `<stack>-tech-lead` as a generic reviewer (no `-reviewer` files exist in this repo).

On both matches, prefer security and record both triggers in Final Summary.

### STEP 6 - Invoke Agent

Assemble the prompt:

1. Absolute paths to `spec.md`, `plan.md`, `tasks.md`, and the most recent prior envelope.
2. The fix-loop `feedback` packet, when present.
3. **Assigned ordinal** `NN = max(existing ordinal in handoffs_dir) + 1` (`01` if empty). Agents must not recompute.
4. Pointer: agent ends its run by writing `<NN>-<step>-<agent>.md` per `agent-handoff-contract`.

Invoke via the Agent tool (`subagent_type` matches the agent file name without `.md`). Wait.

### STEP 7 - Verify Envelope

List `handoffs_dir`; confirm the new envelope at the expected ordinal exists. Missing -> abort with contract-violation. Re-read outputs from the envelope.

### STEP 7.5 - Evaluation Sidecar (when `--with-evaluation`)

When the just-written envelope has `step: review` AND `status: complete`, run `Use skill: task-spec-evaluate` and write its `score` block to `<handoffs_dir>/<NN>-review-score.yaml` (same ordinal as the review envelope; sidecar, declared in `agent-handoff-contract`). On evaluation failure, write the same filename with `status: error` and `reason: <...>`. Skip on `status: failed` review.

### STEP 8 - Loop

Return to STEP 4. Loop terminates on `proceed-done`, `escalate`, `pause-for-amendment`, or `error`.

### STEP 9 - Final Summary and tasks.md Sync

Read every envelope in order; emit Output Format below.

On `proceed-done`, flip `tasks.md` checkboxes from `[ ]`/`[~]` to `[x]` for every task ID appearing in any envelope's `satisfies:` list. Do not edit task text. This is the only legitimate orchestrator write outside chat.

## Output Format

```markdown
## Orchestration Summary

**Slug:** <feature-slug>
**Stack:** <detected stack> / <Stack Type>
**Pipeline status:** complete | escalated | paused-for-amendment | error
**Iterations used:** <fix-loop count> / <cap>

### Timeline

| Ordinal | Step      | Agent                       | Status   | Outputs (count) |
| ------- | --------- | --------------------------- | -------- | --------------- |
| 01      | architect | spring-architect            | complete | 0 (notes only)  |
| 02      | dev       | java-tech-lead              | complete | 7               |
| 03      | test      | java-test-engineer          | failed   | 0               |
| 04      | fix       | java-tech-lead              | complete | 2               |
| 05      | test      | java-test-engineer          | complete | 0               |
| 06      | review    | java-performance-engineer   | complete | 0               |

### Tasks Completed
- T01 - <name>
- T02 - <name>

### Surfaced Amendments
<aggregated `proposed_amendments` from envelopes; omit section if empty>

### Escalation
<source envelope, blocking questions, recommended action; only when status == escalated>

### Resume Instructions
<how to resume; only when status != complete>
```

## Self-Check

- [ ] STEP 1-2: behavioral-principles loaded; stack + `Stack Type` captured; fullstack aborted
- [ ] STEP 3: artifacts confirmed
- [ ] STEP 4: routed via `fix-loop-controller`; no in-memory iteration state
- [ ] STEP 5: agent file resolved per resolver; reviewer variant chosen by spec parse; abort if file missing
- [ ] STEP 6: ordinal assigned by orchestrator and passed to agent
- [ ] STEP 7: envelope verified; STEP 7.5 sidecar written when applicable
- [ ] STEP 9: summary derived from envelopes; `tasks.md` checkbox sync ran on `proceed-done`

## Avoid

- Inferring step success from chat output instead of the envelope.
- Persisting summary content into `.specs/<slug>/` (it is chat output).
- Auto-applying `proposed_amendments` (require human routing).
- Silently substituting an agent when the resolver does not match a file.
