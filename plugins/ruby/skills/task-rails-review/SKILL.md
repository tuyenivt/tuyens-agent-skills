---
name: task-rails-review
description: Rails code review - Zeitwerk, callbacks, fat controllers, AR-in-API, services, scopes; spawns perf/security/observability subagents.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Rails Code Review

Rails-aware staff-level review. Runs correctness, architecture, and maintainability through a Rails lens; spawns perf/security/observability subagents in parallel when scope warrants. Stack-specific delegate of `task-code-review`.

## When to Use

Pre-merge Rails PR review, post-AI quality gate, architecture-drift detection. Not for feature design, incident triage, single-error debugging, or single-scope reviews (delegate directly).

## Depth and Scope

Depth (`quick` | `standard` | `deep`, default `standard`) and scope (`Core` | `+Perf` | `+Security` | `+Observability` | `Full`) mirror `task-code-review`. Pass `core-only` to suppress auto-escalation.

**Auto-promote depth to `deep`** after Step 4 when Blast Radius is Wide/Critical and user did not pass `quick`. Record in Summary.

**Auto-escalate scope on Rails signals:**

- **+Security**: file upload (Active Storage/Shrine/CarrierWave), Devise/Pundit/CanCanCan config, `params.permit` changes, raw SQL, secrets, Sidekiq taking user input
- **+Perf**: `db/migrate/`, `add_index`, new `.where`/`.order`/scopes, new payload endpoints, loops hitting DB or HTTP
- **+Observability**: new service, external dependency, ActiveJob/Sidekiq class, log/notifications config
- Two or more categories -> **Full**

## Invocation

`/task-rails-review [<branch>|pr-<N>] [--base <branch>] [+security|+perf|+observability|--full] [quick|deep|core-only]`

Defaults to current branch vs base; fails fast on trunk. Use `pr-<N>` for a local fetched ref. The workflow never modifies the working tree.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`. If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, also use skill: `spec-aware-preamble`; out-of-scope diff = blocker, missing AC coverage = gap.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected from parent. If not Rails, redirect to `/task-code-review`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check`. Surface fail-fast messages verbatim and stop. The handle may include a `prior_checkpoint` block (a prior `review-<branch>.md` exists). Decision logic is Step 3.5; for now, just hold onto it.

On approval, read **once** (skip when a parent passed pre-read artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

Also capture the current SHAs for the report's checkpoint frontmatter:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

### Step 3.5 - Decide Mode (re-review auto-detect)

Skip if the handle has no `prior_checkpoint` -> `mode = full`, `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `mode = full`, `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

Otherwise (valid prior checkpoint present):

**Step 3.5a - Auto-fetch the head branch.** Only when a valid prior checkpoint exists, refresh the local tracking ref so a script can re-run the same command without manually fetching:

```bash
upstream=$(git rev-parse --abbrev-ref --symbolic-full-name "<head_ref>@{u}" 2>/dev/null)
```

If `upstream` resolves to `<remote>/<branch>` form, split and run:

```bash
git fetch <remote> <branch>
```

No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. After a successful fetch, re-resolve `current_head_sha = git rev-parse <head_ref>`.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`                        | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` and stop. Do not call `review-report-writer`. |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `mode = full`, `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten; full re-review.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round> - full re-review.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `mode = full`, `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round> - full re-review.`           |
| None of the above                                                       | `mode = incremental`, `round = prior.round + 1`, `incremental_range = <prior_head_sha>...<current_head_sha>`.                       |

**Step 3.5c - Incremental: re-read the diff scoped to the new range.**

If `mode = incremental`, replace the diff read from Step 3 with:

- `git diff <prior_head_sha>...<current_head_sha>`
- `git diff --name-status <prior_head_sha>...<current_head_sha>`
- `git log --oneline <prior_head_sha>..<current_head_sha>`

The full-range diff from Step 3 is discarded; all Phase / Step analysis operates on the incremental range only.

**Step 3.5d - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list> - new scopes reviewed in full; previously-reviewed scopes reviewed incrementally.` The reconciliation table only covers findings whose scope was active in the prior round.

### Step 4 - Risk Snapshot

Use skills: `review-pr-risk`, `review-blast-radius`. State **Risk Level** and **Blast Radius** before line-level findings.

**Low-risk short-circuit:** Risk: Low + Blast Radius: Narrow + change does not touch auth, middleware, API contracts, shared concerns, `app/services/`, or `lib/` -> skip Steps 6-8, produce Step 5 only.

### Step 5 - Rails Correctness

Logical correctness, state-integrity, transaction boundaries, backward compat. Scope strictly to **Rails-specific correctness** - security idioms (strong params, authz, IDOR, mass assignment, AR-in-API leakage, idempotency keys) belong to `task-rails-review-security` and must not be duplicated here. When +Security is not in scope, raise the most severe as a `[High]` and note "verify via `/task-rails-review-security`".

Atomic skills (consult when PR touches the area):

- `rails-activerecord-patterns` (models, associations, scopes)
- `rails-service-objects` (new/extended service)
- `rails-sidekiq-patterns` (new/modified job)
- `rails-transaction-patterns` (transaction boundaries, nested transactions, callbacks, `after_commit` dispatch)
- `rails-concurrency-patterns` (`load_async`, threads, fibers, fan-out)
- `rails-actioncable-patterns` (channels, Turbo broadcasts)
- `rails-exception-handling` (rescue logic, new error classes, Sidekiq error flow)

Checks:

- [ ] **Transactions / callbacks**: writes wrapped; no HTTP / `.perform_async` / `deliver_now` inside transactions or `after_save`/`after_create` - dispatch via `after_commit` (see `rails-transaction-patterns`)
- [ ] **`save!`** in services/transactions so failures surface
- [ ] **Error handling**: no bare `rescue` / `rescue Exception` / blanket `rescue StandardError` that logs-and-continues; `RecordNotFound`, `Pundit::NotAuthorizedError`, app-level `ApplicationError` centralized via `rescue_from` in `ApplicationController`
- [ ] **Bulk operations**: partial-failure path defined; transaction wraps one chunk, not whole run or single row
- [ ] **Concurrency**: no class-level mutable state, no `Time.zone=`; race-prone updates use row-level lock or `with_advisory_lock`

**Test coverage** (named finding, not buried): logic added without RSpec coverage is `[Suggestion]`. Escalate to `[High]` on critical paths: auth, authz, money/billing, multi-record transactions, state machines, data-mutating Sidekiq jobs, migrations changing column semantics.

**Migration PRs** (`db/migrate/` change) - use skill: `ops-backward-compatibility`:

- [ ] Two-phase column rename/drop (add -> backfill -> cut over -> remove)
- [ ] `NOT NULL` on existing columns via two-step (nullable -> backfill -> set NOT NULL)
- [ ] `add_index` on large tables: PG `algorithm: :concurrently` + `disable_ddl_transaction!`; MySQL `algorithm: :inplace`
- [ ] FKs added with `validate: false`, validated separately
- [ ] Data migrations in rake tasks, not `db/migrate/`
- [ ] Rollback path documented

### Step 6 - Architecture

Use skill: `architecture-guardrail`.

- [ ] **Layering**: presentation -> service/domain -> data. No business logic in controllers; no `Net::HTTP` in models; no view rendering in services
- [ ] **Service discipline**: controller actions > 5 orchestration lines extracted; services expose `.call` returning `Result`; consistent interface across the app
- [ ] **Concern hygiene**: `app/**/concerns/*.rb` role-based (`Sluggable`, `SoftDeletable`), not grab-bags
- [ ] **Zeitwerk**: file paths match constant names; no `require_relative` inside `app/`
- [ ] **Namespace / engine boundaries**: cross-namespace access via service objects, not direct model reach-in
- [ ] **Multi-tenant isolation**: enforced at the model layer (`acts_as_tenant`, `default_scope`, query objects), not controller-only
- [ ] **Multi-database**: `connects_to` declared on models; cross-DB joins flagged

For multi-service PRs, also use skill: `ops-backward-compatibility` for API contract compatibility and deployment order.

### Step 7 - Code Hygiene

- Use skill: `complexity-review` - cyclomatic/cognitive complexity; redundant mapping layers (`User -> Decorator -> Presenter -> Serializer`)
- Use skill: `rails-overengineering-review` - validations duplicating DB constraints, defensive guards on impossible states, services/`Result`/base classes wrapping trivial logic
- [ ] **Test verbosity**: setup > 30 lines per example; `let!` chains replaceable by a FactoryBot trait; matchers reimplemented when shoulda-matchers exist

### Step 8 - Maintainability

- [ ] **Naming**: classes are nouns; services describe an action (`FulfillOrder`); scopes are queries (`active`, `completed_after`)
- [ ] **Magic numbers/strings** extracted to constants or `Rails.application.config.x.*`
- [ ] **Credentials/URLs**: `Rails.application.credentials` or env config, never inline
- [ ] **Method length**: > 15 lines reviewed; > 30 flagged unless `.call` orchestrating clearly named steps
- [ ] **Duplicated query logic**: same `.where(...).order(...)` in 3+ places extracted to a scope or query object
- [ ] **Logging hygiene**: correct levels; structured fields when `lograge`/`semantic_logger` is configured (depth owned by observability subagent)

Load `backend-coding-standards` when new naming/structure patterns introduced.

### Step 9 - Delegate Extra Scopes in Parallel

Skip if `core-only`. For each selected scope, spawn one independent subagent in parallel running the matching `task-rails-review-*`. `Full` = 3 subagents.

**Subagent prompt contract:** resolved `base_ref`/`head_ref` + pre-read diff and commit log; depth level; pre-confirmed stack; return findings in its own skill's Output Format.

**Failure isolation:** if a subagent fails or times out, continue with remaining results; note `Scope incomplete: <scope>` under Summary.

### Step 9.5 - Reconcile Prior Findings (incremental mode only)

Skip if `mode = full`. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `incremental_diff`: from Step 3.5c
- `name_status`: from Step 3.5c

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

### Step 10 - Synthesize and Report

Merge subagent findings:
- Deduplicate cross-cutting findings; one entry citing all scopes that raised it
- Highest severity wins on conflict (`Blocker > High > Suggestion > Question`)
- Preserve `file:line` citations; order by severity, not scope
- Merge Next Steps into one prioritized list; preserve `[Implement]`/`[Delegate]` tags

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode` (from Step 3.5), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4), `depth` (resolved/auto-promoted), `stack = ruby-rails`

Print confirmation line.

## Feedback Labels

`[Blocker]` (must fix before merge) | `[High]` (significant impact) | `[Suggestion]` (non-blocking) | `[Question]` (clarification)

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(append `auto-escalated from Core; signals: <list>` if applicable)_
**Depth:** quick | standard | deep _(append `auto-promoted from standard; Blast Radius: <level>` if applicable)_
**Round:** <N>                                _(include from round 2 onward)_
**Mode:** incremental (since <prior_head_sha_short>) | full _(include from round 2 onward)_
**Diff Range:** <range_short> (<N> commits, <M> files) _(incremental rounds only)_

## Prior Round Reconciliation _(incremental rounds only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## Findings

Each entry, ordered Blocker > High > Suggestion > Question:

### [Label] file:line

- Issue: [Rails idiom named: callback abuse, fat controller, AR-in-API, missing authorize, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level] _(required for Blocker; optional otherwise)_
- Fix: [concrete Rails change with code]

## Architecture Notes
- Boundary impact / Coupling change / Drift detected

## Maintainability Notes
- Over-engineering detected / Simplification opportunities

## Key Takeaways
- 2-4 bullets on systemic impact

## Next Steps

On incremental rounds, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by severity alongside new findings. Prioritized; each `[Implement]` or `[Delegate]`; order Blocker > High > Suggestion.

1. **[Implement]** [Blocker] file:line - one-line action
2. **[Implement]** [High] OldFile.rb:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [High] [scope] - one-line action
```

_Omit empty sections. Omit Next Steps entirely if no actionable findings._

## Self-Check

- [ ] Steps 1-3: behavioral rules, stack, diff resolved (or accepted from parent); diff/log read once; `review-precondition-check` ran (or handle received); current_head_sha and current_base_sha captured
- [ ] Step 3.5 - mode decided (full / incremental / no-op); auto-fetch attempted only when prior checkpoint exists; incremental range re-read when mode flipped to incremental; no-op path exits without writing the report
- [ ] Step 4: Risk and Blast Radius stated before findings; depth auto-promoted on Wide/Critical
- [ ] Step 5: Rails correctness only - security idioms deferred to the security subagent or flagged for it
- [ ] Step 6: architecture / layering / Zeitwerk / multi-tenant / multi-DB applied via `architecture-guardrail`
- [ ] Step 7: complexity + overengineering reviews run; test verbosity checked
- [ ] Step 8: maintainability checks applied
- [ ] Step 9: non-Core subagents ran in parallel with pre-resolved artifacts; failed scopes noted
- [ ] Step 9.5 - on incremental rounds, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Step 10: findings merged with dedup + highest-severity-wins; report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack)
- [ ] Every Blocker states a system risk; every finding has label + `file:line` + actionable Rails fix
- [ ] If `--spec` was passed, every finding traces to AC/NFR/task or is flagged out-of-scope

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Running incremental analysis against the full-range diff (must re-read scoped to `<prior_head_sha>...<head_sha>`).
- Writing the report on no-op exit (prior `head_sha == current head_sha`) - the file must stay byte-identical.
- Reconciling against prior Suggestions or Architecture/Maintainability notes - only `## High-Impact Findings` rows.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Duplicating perf / security / observability depth here - dedicated subagents own it
- Reviewing without reading the full diff and log first
- Applying generic backend conventions where a Rails idiom exists
- Nitpicking style; no `[Nitpick]` / `[Praise]` labels
- Appending raw subagent reports instead of merging into one severity-ordered list
- Running extra-scope subagents sequentially or when `core-only` was passed
