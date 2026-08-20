---
name: task-rails-review
description: Rails code review - Zeitwerk, callbacks, fat controllers, AR-in-API, services, scopes; spawns perf/security/observability/reliability subagents.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Rails Code Review

Rails-aware staff-level review. Runs correctness, architecture, and maintainability through a Rails lens; spawns perf/security/observability/reliability subagents in parallel when scope warrants. Stack-specific delegate of `task-code-review`.

## When to Use

Pre-merge Rails PR review, post-AI quality gate, architecture-drift detection. Not for feature design, incident triage, single-error debugging, or single-scope reviews (delegate directly).

## Depth and Scope

Depth (`standard` (default) | `deep`) and scope (`Core` | `+Perf` | `+Sec` | `+Obs` | `+Rel` | `Full`) mirror `task-code-review`. Pass `core-only` to suppress auto-escalation.

**Auto-promote depth to `deep`** after Step 4 when Blast Radius is Wide/Critical. Record in Summary. On round 2+ nothing is inherited; when the resolved depth falls below the checkpoint's (round 1 was user-flagged `deep`), note in Summary: `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

**Auto-escalate scope on Rails signals:**

- **+Sec**: file upload (Active Storage/Shrine/CarrierWave), Devise/Pundit/CanCanCan config, `params.permit` changes, raw SQL, secrets, Sidekiq taking user input
- **+Perf**: `db/migrate/`, `add_index`, new `.where`/`.order`/scopes, new payload endpoints, loops hitting DB or HTTP
- **+Obs**: new service, external dependency, ActiveJob/Sidekiq class, log/notifications config
- **+Rel**: new Faraday/`Net::HTTP` client without timeout, `stoplight`/`retriable` config, Sidekiq job without an idempotency guard, external call or `.perform_async` inside a transaction, unbounded `.all.each`, missing `after_commit` dispatch
- Two or more categories in the resolved union (user flags + firing signals) -> **Full** (scope enums are single-valued; a two-scope union has no representation)

## Invocation

`/task-rails-review [<branch>|pr-<N>] [--base <branch>] [--req <path>] [+sec|+perf|+obs|+rel|--full] [deep|core-only]`

Defaults to current branch vs base; fails fast on trunk. Use `pr-<N>` for a local fetched ref. The workflow never modifies the working tree.

Pass `--req <path>` to name a requirement source (ticket export, PRD, spec) for Step 3.7; without it, Step 3.7 uses whatever requirement is already in context.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`.

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

### Step 3.5 - Decide Round (re-review auto-detect)

**Every round analyzes the full `<base_ref>...<head_ref>` range read in Step 3.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change on every round, so a small follow-up commit cannot under-score a large PR and a defect missed in round 1 stays reachable in round 2. Rounds differ only in that round 2+ reconciles against the prior report.

Skip if the handle has no `prior_checkpoint` -> `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

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
| `prior_checkpoint.head_sha == current_head_sha`, and the invocation adds no scope or depth beyond the prior checkpoint | **No-op.** Print `No new commits on <head_ref_short> since prior review at <sha_short>. Prior report unchanged.` (where `<head_ref_short>` is the short name of `head_ref` - the review target, not the user's current branch - and `<sha_short>` is the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation expands scope or depth beyond it | `round = prior.round + 1`. Note in Summary: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round>.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round>.`           |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

**Step 3.5c - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list>.`

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

**Scope precedence on round 2+:** user flag > firing signals. Signals are scored on the full range every round, so a scope that escalated in round 1 escalates again on its own - nothing is inherited from the prior checkpoint. When the resolved scope still falls below the checkpoint's (round 1 was user-flagged), note in Summary: `Scope narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover.`

### Step 3.7 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and `prior_checkpoint.report_path` when round > 1.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its findings join the assembled set verified in Step 9.4. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. Runs before the Step 4 risk snapshot - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

### Step 4 - Risk Snapshot

Use skills: `review-pr-risk`, `review-blast-radius`. State **Risk Level** and **Blast Radius** before line-level findings.

**Resolve scope now** (round 1): union of user flags and signals firing on the Step 3 diff; `core-only` suppresses signal escalation. Record firing signals in Summary. (Round 2+ precedence: Step 3.5c.)

**Low-risk short-circuit:** Risk: Low + Blast Radius: Narrow + change does not touch auth, middleware, API contracts, shared concerns, `app/services/`, or `lib/` -> skip Steps 6-8, produce Step 5 only (with its atomic skills); Step 9 still follows its own scope rules; Step 10 still writes the report (Summary + the Step 3.7 outputs (Change Brief, traceability, requirement findings) + Step 5 findings). Note `Low-risk short-circuit: Steps 6-8 skipped` in Summary. When `core-only` suppressed a firing escalation signal, record the suppressed signal in Summary and emit a `[Delegate]` Next Step naming the matching `/task-rails-review-*` command.

### Step 5 - Rails Correctness

Logical correctness, state-integrity, transaction boundaries, backward compat. Scope strictly to **Rails-specific correctness** - security idioms (strong params, authz, IDOR, mass assignment, AR-in-API leakage, idempotency keys) belong to `task-rails-review-security`. When +Sec IS in scope, core stays silent on them - the subagent owns them and Step 10 dedups. When +Sec is not in scope, raise the most severe as a `[Recommend]` and note "verify via `/task-rails-review-security`". Dual-natured findings (a TOCTOU balance check is both a race and an authz-adjacent hole) are filed by core for the correctness dimension; the merge unifies.

Atomic skills (consult when PR touches the area):

- `rails-activerecord-patterns` (models, associations, scopes)
- `rails-service-objects` (new/extended service)
- `rails-sidekiq-patterns` (new/modified job)
- `rails-transaction-patterns` (transaction boundaries, nested transactions, callbacks, `after_commit` dispatch)
- `rails-concurrency-patterns` (`load_async`, threads, fibers, fan-out)
- `rails-actioncable-patterns` (channels, Turbo broadcasts)
- `rails-exception-handling` (rescue logic, new error classes, Sidekiq error flow)
- `rails-view-templates` (diffed `.erb`/`.haml`/`.slim` templates)

`deep` depth in core steps: consult every listed atomic skill (not only touched-area ones) and read the surrounding code beyond the diff hunks before judging.

Checks:

- [ ] **Transactions / callbacks**: writes wrapped; no HTTP / `.perform_async` / `deliver_now` inside transactions or `after_save`/`after_create` - dispatch via `after_commit` (see `rails-transaction-patterns`)
- [ ] **`save!`** in services/transactions so failures surface
- [ ] **Error handling**: no bare `rescue` / `rescue Exception` / blanket `rescue StandardError` that logs-and-continues; `RecordNotFound`, `Pundit::NotAuthorizedError`, app-level `ApplicationError` centralized via `rescue_from` in `ApplicationController`
- [ ] **Bulk operations**: partial-failure path defined; transaction wraps one chunk, not whole run or single row
- [ ] **Concurrency**: no class-level mutable state, no `Time.zone=`; race-prone updates use row-level lock or `with_advisory_lock`

**Test coverage** (named finding, not buried): logic added without RSpec coverage -> `[Recommend]`; escalate to `[Must]` on critical paths: auth, authz, money/billing, multi-record transactions, state machines, data-mutating Sidekiq jobs, migrations changing column semantics.

**Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.

**Migration PRs** (`db/migrate/` change) - use skill: `ops-backward-compatibility`:

- [ ] Two-phase column rename/drop (add -> backfill -> cut over -> remove)
- [ ] `NOT NULL` on existing columns via two-step (nullable -> backfill -> set NOT NULL)
- [ ] `add_index` on large tables: PG `algorithm: :concurrently` + `disable_ddl_transaction!`; MySQL `algorithm: :inplace`
- [ ] FKs added with `validate: false`, validated separately
- [ ] Data migrations in rake tasks, not `db/migrate/`
- [ ] Rollback path documented

**API contract PRs** - run when the diff carries a contract-change signal: a removed / renamed / retyped serializer attribute, a changed rendered status code, a newly `permit`-ted required field or tightened validation, a new public route in a `/v1/`-versioned or external API namespace, a `render json:` on a raw AR model with no serializer, or an rswag / `openapi.yaml` edit. Use skills `backend-api-guidelines`, `ops-backward-compatibility`:

- [ ] Breaking change (removed/renamed/retyped attribute, tightened validation, newly required param, changed status or error shape) carries a version bump or expand-contract plan; "no external callers" backed by a search; when consumption is unknown, treat a `/v1/`-versioned or spec-published surface as externally consumed
- [ ] Responses rendered through serializers, never a raw AR model; errors follow RFC 9457; collections paginated
- [ ] rswag / `openapi.yaml` matches the code - changed endpoints, schemas, status codes, and error shapes present and accurate
- [ ] Each finding names who breaks and how (for a leaked AR model: what it exposes and who couples to it). Severity maps to labels: High -> `[Must]` = unversioned breaking change to an externally consumed contract, or a raw AR model rendered on an externally consumed / versioned surface - a contract-shape finding this gate files itself (the Step 10 merge dedups with +Sec, per the dual-natured rule); Medium -> `[Recommend]` = internal breaking change with no coordinated-deploy note, inconsistent status/error envelope, unpaginated unbounded collection, rswag / `openapi.yaml` out of sync with the code; Low = naming drift with no consumer impact - below the reporting bar, write nothing. A raw AR model on an internal-only surface follows the Step 5 security carve-out instead ([Recommend] + verify note when +Sec is absent; core silent when +Sec runs); one finding per `file:line` either way

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

Skip if `core-only`. For each selected scope, spawn one independent subagent in parallel. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `rails-tech-lead` spawn:

| Scope | Skill                             | Subagent (`subagent_type`)     |
| ----- | --------------------------------- | ------------------------------ |
| +Perf | `task-rails-review-perf`          | `rails-performance-engineer`   |
| +Sec  | `task-rails-review-security`      | `rails-security-engineer`      |
| +Obs  | `task-rails-review-observability` | `rails-observability-engineer` |
| +Rel  | `task-rails-review-reliability`   | `rails-reliability-engineer`   |

`Full` = 4 subagents.

**Subagent prompt contract:** resolved `base_ref`/`head_ref` + pre-read diff and commit log; depth level; pre-confirmed stack; return findings in its own skill's Output Format.

**Failure isolation:** if a subagent fails or times out, continue with remaining results; note `Scope incomplete: <scope>` under Summary.

**No-spawn fallback:** when the environment can't spawn subagents, run each selected scope's checks inline and sequentially using the same `task-rails-review-*` skills, label the findings per scope, and note `Scopes run inline` in Summary. Inline runs behave as subagent runs: their Steps 1-3 are pre-satisfied and their report writers are skipped - this workflow owns the report. Depth propagates to delegates (security always runs full depth regardless).

Scopes added by *firing signals* and by *user flag* alike review the full range; Step 3.5c records the expansion for the reconciliation table.

### Step 9.4 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the assembled findings (including any merged back from subagents), the diff already read, and `base_ref` / `head_ref`.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` column. Carry its tally into Summary as `Findings verified: <N> confirmed, <M> reattributed, <K> dropped`.

### Step 9.5 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the loaded body of `review-<branch>.md` (frontmatter excluded)
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff --name-status <base_ref>...<head_ref>` from Step 3
- `head_files`: the file list at `current_head_sha` (`git ls-tree -r --name-only <head_ref>`), when the reconcile skill requests it

The reconcile skill returns a Markdown table and a tally line. Insert the table under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by severity alongside this round's new findings. Do not emit a standalone "Carry-Over Open Items" section.

### Step 10 - Synthesize and Report

Merge subagent findings:
- Deduplicate cross-cutting findings; one entry citing all scopes that raised it
- **Strongest intent wins** when labels differ across subagent reports for the same finding: `Must` > `Recommend`
- Preserve `file:line` citations; order by intent, not scope
- Merge Next Steps into one prioritized list; preserve `[Implement]`/`[Delegate]` tags
- Preserve deep-only sections returned by subagents (e.g., reliability's `Failure-Mode and Blast-Radius Map`) as their own section after Next Steps - they are not findings; the merge must not drop them

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `branch`, `base_ref`, `base_sha = current_base_sha`, `head_ref`, `head_sha = current_head_sha`
- `mode: full` (the writer's only accepted value), `round` (from Step 3.5), `prior_head_sha` (omit on round 1)
- `scope` (resolved in Step 4; frontmatter uses the writer's enum - `Core` maps to `core-only`, `+Rel` to `+rel`), `depth` (resolved/auto-promoted), `stack = ruby-rails`

Print confirmation line.

## Feedback Labels

| Label        | Meaning                                                                  |
| ------------ | ------------------------------------------------------------------------ |
| [Must]       | Do not merge until this is fixed.                                        |
| [Recommend]  | Fix, or push back with reasoning. Cannot be silently acked.              |

No `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` - if it isn't `[Must]` or `[Recommend]`, don't write it down.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
_(Request Changes = any [Must]; Discuss = no [Must] but an unresolved assumption in a [Recommend] gates the verdict; Approve = neither - [Recommend]s alone don't block.)_
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide | Critical
**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full _(append `auto-escalated from Core; signals: <list>` if applicable)_
**Depth:** standard | deep _(append `auto-promoted from standard; Blast Radius: <level>` if applicable)_
**Round:** <N>                                _(include from round 2 onward)_
**Findings verified:** <N> confirmed, <M> reattributed, <K> dropped
**Requirement Source:** <path or origin> (Specified | Self-attested) _(this line and the next are emitted together, or both omitted when Step 3.7 resolved no source)_
**Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when no source resolved>
**Delivered:** <the mechanism implemented and where>
**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>
**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability _(omit when Step 3.7 resolved no source)_

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, or `-`> | <file:line or verification note, or `-`> |

## Prior Round Reconciliation _(round 2+ only; omit otherwise)_

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line
- Issue: [Rails idiom named: callback abuse, fat controller, mid-transaction HTTP, gap-lock range scan, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Rails change with code]

### [Recommend] file:line
- Issue:
- Impact:
- Fix:

## Architecture Notes
- Boundary impact / Coupling change / Drift detected

## Maintainability Notes
- Over-engineering detected / Simplification opportunities

## Key Takeaways
- 2-4 bullets on systemic impact

## Next Steps

On round 2+, prior-round Still open items are folded in with (open since round <N>) suffix and ordered by intent alongside new findings. Prioritized; each `[Implement]` or `[Delegate]`; order Must > Recommend.

1. **[Implement]** [Must] file:line - one-line action
2. **[Implement]** [Recommend] OldFile.rb:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [scope] - one-line action
```

_Omit empty sections. Omit Next Steps entirely if no actionable findings._

## Self-Check

- [ ] Steps 1-3: behavioral rules, stack, diff resolved (or accepted from parent); diff/log read once; `review-precondition-check` ran (or handle received); current_head_sha and current_base_sha captured
- [ ] Step 3.5 - round decided (1 / prior + 1 / no-op); auto-fetch attempted only when prior checkpoint exists; the full `<base_ref>...<head_ref>` range analyzed regardless of round; no-op path exits without writing the report
- [ ] Step 3.7 - `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; requirement lines in Summary, or all three requirement outputs omitted when no source resolved; its findings verified with the rest
- [ ] Step 4: Risk and Blast Radius stated before findings; depth auto-promoted on Wide/Critical
- [ ] Step 5: Rails correctness only - security idioms deferred to the security subagent or flagged for it; API contract checks ran when a route, serializer, permitted param, or rswag/openapi spec changed
- [ ] Step 6: architecture / layering / Zeitwerk / multi-tenant / multi-DB applied via `architecture-guardrail`
- [ ] Step 7: complexity + overengineering reviews run; test verbosity checked
- [ ] Step 8: maintainability checks applied
- [ ] Step 9: non-Core subagents ran in parallel with pre-resolved artifacts; failed scopes noted
- [ ] Step 9.4 - review-finding-verify ran on all assembled findings; Dropped rows excluded; verdict labels applied; tally in Summary
- [ ] Step 9.5 - on round 2+, review-prior-findings-reconcile ran; reconciliation table inserted; Still open rows folded into Next Steps with (open since round <N>) suffix
- [ ] Step 10: findings merged with dedup + strongest-intent-wins; report written via `review-report-writer` with full checkpoint fields (mode, round, prior_head_sha when round > 1, head_sha, base_sha, scope, depth, stack)
- [ ] Every Must cites system risk; every finding has label + `file:line` + actionable Rails fix

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Scoping round 2+ analysis to `<prior_head_sha>...<head_sha>` - risk, scope, depth, and requirement fit score the full `<base_ref>...<head_ref>` range on every round.
- Writing the report on no-op exit - the file must stay byte-identical. (Same head SHA with expanded scope/depth is not a no-op - Step 3.5b.)
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Emitting `[Question]`, `[Suggestion]`, `[Consider]`, `[Nit]`, `[Nitpick]`, or `[Praise]` labels - if it isn't `[Must]` or `[Recommend]`, don't write it down.
- Emitting a "Carry-Over Open Items" section - fold into Next Steps instead.
- Duplicating perf / security / observability / reliability depth here - dedicated subagents own it
- Reviewing without reading the full diff and log first
- Applying generic backend conventions where a Rails idiom exists
- Nitpicking style
- Appending raw subagent reports instead of merging into one intent-ordered list
- Running extra-scope subagents sequentially or when `core-only` was passed
