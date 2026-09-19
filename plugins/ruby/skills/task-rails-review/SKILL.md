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
- **+Obs**: log/notifications/tracer config, a new external dependency, or a new service / ActiveJob / Sidekiq class whose diff adds no instrumentation (no structured log or event)
- **+Rel**: new Faraday/`Net::HTTP` client without timeout, `stoplight`/`retriable` config, Sidekiq job without an idempotency guard, external call or `.perform_async` inside a transaction, unbounded `.all.each`, missing `after_commit` dispatch
- Two or more categories in the resolved union (user flags + firing signals) -> **Full** (this workflow's Summary `Scope:` line and its Step 10 writer mapping are both single-valued; `review-report-writer` would accept a space-joined subset, but nothing here emits one)

## Invocation

`/task-rails-review [<branch>|pr-<N>] [--base <branch>] [--req <path>] [+sec|+perf|+obs|+rel|full|core-only] [standard|deep]`

Defaults to current branch vs base; fails fast on trunk. Use `pr-<N>` for a local fetched ref. The workflow never modifies the working tree.

Pass `--req <path>` to name a requirement source (ticket export, PRD, spec) for Step 3.7; without it, `review-change-intent`'s own source ladder decides what counts as a source - the workflow adds nothing.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected from parent. If not Rails, redirect to `/task-code-review`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review`. Surface fail-fast messages verbatim and stop. The handle may include a `prior_checkpoint` block (the file at its `report_path` exists with valid frontmatter) or the scalar `legacy`. Decision logic is Step 3.5; for now, just hold onto it.

From the handle, fix `branch` = its `head_short_name` (never `HEAD`, never remote-prefixed - the atomic strips `origin/`). It names the review target everywhere below: the no-op message, the writer's `branch` field, and the report filename. `head_ref` passes through unchanged to the diff commands and to the writer.

Capture the current SHAs first - the Step 3.5 no-op gate needs only these:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

Then, once Step 3.5 has not stopped the run, read **once** (skip when a parent passed pre-read artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

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

No checkout, no merge. If `upstream` does not resolve (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. The fetch updates `refs/remotes/<remote>/<branch>` only - it never moves a local branch or `HEAD`, so `current_head_sha` does not change and is not re-resolved. Its value is leaving the tracking ref current for the reader, not for this run.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha` and `prior_checkpoint.base_sha == current_base_sha`, and the checkpoint's `scope` / `depth` cover the invocation's (covering = superset: `full` covers every scope, any scope covers `core-only`, `deep` covers `standard`; map the invocation's flags to the writer enum per Step 10 before comparing) | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` (`<sha_short>` = the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation's scope or depth is not covered | `round = prior.round + 1`. Note in Summary: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_checkpoint.head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round>.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round>.`           |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

Apply the first matching row's decision; when several rows match, emit every matching row's Summary note - except on the no-op row, which stops before a Summary exists: it prints its line and nothing else.

**Step 3.5c - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary: `Scope expanded round <N>: +<list>.`

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

**Scope on round 2+** resolves exactly as on round 1 (Step 4): the union of user flags and signals firing on the full range, with `core-only` suppressing the signals. Nothing is inherited from the checkpoint - a scope that escalated in round 1 escalates again on its own. When the resolved scope still falls below the checkpoint's (round 1 was user-flagged), note in Summary: `Scope narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover.`

### Step 3.7 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and the handle's `report_path` (as its `prior_report_path`) when round > 1.

Its `## Change Brief` block goes into the report verbatim, its `Requirement Source` and `Requirement Fit` lines into Summary, and its `### Requirement Findings` items join the assembled set in Step 9.3 - that section and the `### No Requirement Findings` marker are consumed, never rendered. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. Runs before the Step 4 risk snapshot - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

### Step 4 - Risk Snapshot

Use skills: `review-pr-risk`, `review-blast-radius`. State **Risk Level** and **Blast Radius** before line-level findings, each as the atomic's line value as emitted (a `(contract break: ...)` parenthetical or a two-state `<level> (unmitigated) -> <level> (with ...)` form stays whole; the promote and short-circuit tests read the unmitigated level unless the `Mitigation:` tag is `in-place:`). Only those two lines reach the report; the atomics' full blocks (`Signals:`, `Action:`, dimension lines, `Mitigation:`) inform the review and are not emitted.

**Resolve scope now:** union of user flags and signals firing on the Step 3 diff; `core-only` suppresses signal escalation. The Summary `Scope:` line carries the resolved value plus one annotation:

| Observed                              | Annotation                                         |
| ------------------------------------- | -------------------------------------------------- |
| No user flag, signals fired           | `auto-escalated from Core; signals: <list>`        |
| User flag, further categories fired   | `user-flagged; signals also firing: <list>`        |
| `core-only`, signals fired            | `core-only; suppressed signals: <list>`            |
| Otherwise                             | none                                               |

Every suppressed signal also emits a `[Delegate]` Next Step tagged `[+<Lens>]` naming the matching `/task-rails-review-*` command, whether or not the short-circuit below fires; a `[Delegate]` for a fix leaving the PR's scope is tagged `[scope: <owner>]` instead. A Step 5 carve-out finding on the same defect keeps its own `[Implement]` entry - the lens sweep and the point fix are separate steps, never merged.

**Low-risk short-circuit:** Risk: Low + Blast Radius: Narrow + change does not touch auth, middleware, API contracts, shared concerns, `app/services/`, or `lib/` -> skip Steps 6-8. Step 5 runs with its atomic skills; Step 9 follows its own scope rules; Steps 9.3-9.4 (and 9.5 on round 2+) and Step 10 run as usual. Note `Low-risk short-circuit: Steps 6-8 skipped` in Summary.

### Step 5 - Rails Correctness

Logical correctness, state-integrity, transaction boundaries, backward compat. Scope strictly to **Rails-specific correctness** - security idioms (strong params, authz, IDOR, mass assignment, AR-in-API leakage) belong to `task-rails-review-security`; an inbound `Idempotency-Key` gap is the API contract gate's (below, via `backend-api-guidelines`), never deferred. When +Sec IS in scope, core stays silent on the security idioms - the subagent owns them. When +Sec is not in scope, raise only the most severe as a `[Recommend]` ending "verify via `/task-rails-review-security`" - one finding for the whole deferred lens, not one per checklist family; the rest are not written; the lens owns them. Job idempotency guards, retries, timeouts, unbounded iteration, and pool/queue saturation follow the same pattern with +Rel: the reliability subagent owns them when +Rel is in scope; otherwise raise only the most severe as a `[Recommend]` + "verify via `/task-rails-review-reliability`". Dual-natured findings (a TOCTOU balance check is both a race and an authz-adjacent hole) are filed by core for the correctness dimension; the merge unifies.

Atomic skills - load with `Use skill:` each one whose area the PR touches:

- `rails-activerecord-patterns` (models, associations, scopes)
- `rails-service-objects` (new/extended service)
- `rails-sidekiq-patterns` (new/modified job)
- `rails-transaction-patterns` (transaction boundaries, nested transactions, callbacks, `after_commit` dispatch)
- `rails-concurrency-patterns` (`load_async`, threads, fibers, fan-out)
- `rails-actioncable-patterns` (channels, Turbo broadcasts)
- `rails-exception-handling` (rescue logic, new error classes, Sidekiq error flow)
- `rails-view-templates` (diffed `.erb`/`.haml`/`.slim` templates)

`deep` depth in core steps: consult every listed atomic skill (not only touched-area ones) and read each touched file in full plus the code the diff calls into before judging; an atomic with no matching surface in that reading is skipped, without a consulted-clean note - the review stays PR-shaped, never a repo sweep.

Checks:

- [ ] **Transactions / callbacks**: writes wrapped; no HTTP / `.perform_async` / `deliver_now` inside transactions or `after_save`/`after_create` - dispatch via `after_commit` (see `rails-transaction-patterns`)
- [ ] **`save!`** in services/transactions so failures surface
- [ ] **Error handling**: no bare `rescue` / `rescue Exception` / blanket `rescue StandardError` that logs-and-continues; `Pundit::NotAuthorizedError` and app-level `ApplicationError` centralized via `rescue_from` in `ApplicationController` (an uncaught `RecordNotFound` is already a 404 via `rescue_responses` - a per-action rescue of it is the finding, not its absence)
- [ ] **Bulk operations**: partial-failure path defined; transaction wraps one chunk, not whole run or single row
- [ ] **Concurrency**: no class-level mutable state, no `Time.zone=`; race-prone updates use row-level lock or `with_advisory_lock`

**Test coverage** (named finding, not buried): logic added without RSpec coverage -> `[Recommend]`; escalate to `[Must]` on critical paths: auth, authz, money/billing, multi-record transactions, state machines, data-mutating Sidekiq jobs, migrations changing column semantics.

**Test files are reviewed for coverage only.** For files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.

**Migration PRs** (`db/migrate/` change) - use skill: `ops-backward-compatibility`:

- [ ] Two-phase column rename/drop (add -> backfill -> cut over -> remove)
- [ ] `NOT NULL` on existing columns via the detected DB's safe path (PG: `add_check_constraint ... IS NOT NULL, validate: false` -> validate -> `change_column_null` -> drop the CHECK; MySQL: backfill, then `change_column_null` with `algorithm: :inplace`)
- [ ] `add_index` on large tables: PG `algorithm: :concurrently` + `disable_ddl_transaction!`; MySQL `algorithm: :inplace`
- [ ] PG: FKs added with `validate: false`, validated in a second migration. MySQL has no `NOT VALID` - with `foreign_key_checks=1` `ADD FOREIGN KEY` is ALGORITHM=COPY, and gh-ost refuses any FK-bearing table, so a large table goes through `pt-online-schema-change --alter-foreign-keys-method=rebuild_constraints` or a maintenance window (Use skill: `rails-migration-safety` or `rails-postgresql-migration-safety` per detected DB)
- [ ] Data migrations in rake tasks, not `db/migrate/`
- [ ] Rollback path documented

**API contract PRs** - run when the diff carries a contract-change signal: a removed / renamed / retyped serializer attribute, a changed rendered status code, a newly `permit`-ted required field or tightened validation, a new public route in a `/v1/`-versioned or external API namespace, a `render json:` on a raw AR model with no serializer, or an rswag / `openapi.yaml` edit. Use skills: `backend-api-guidelines`, `ops-backward-compatibility`:

- [ ] Breaking change (removed/renamed/retyped attribute, tightened validation, newly required param, changed status or error shape) carries a version bump or expand-contract plan; "no external callers" backed by a search; when consumption is unknown, treat a `/v1/`-versioned or spec-published surface as externally consumed
- [ ] Responses rendered through serializers, never a raw AR model; errors follow RFC 9457; collections paginated
- [ ] rswag / `openapi.yaml` matches the code - changed endpoints, schemas, status codes, and error shapes present and accurate
- [ ] Each finding names who breaks and how (for a leaked AR model: what it exposes and who couples to it). Severity maps to labels: High -> `[Must]` = unversioned breaking change to an externally consumed contract, or a raw AR model rendered on an externally consumed or versioned surface - a contract-shape finding this gate files itself (the Step 9.3 merge dedups with +Sec, per the dual-natured rule); Medium -> `[Recommend]` = internal breaking change with no coordinated-deploy note, inconsistent status/error envelope, unpaginated unbounded collection, rswag / `openapi.yaml` out of sync with the code; Low = naming drift with no consumer impact - below the reporting bar, write nothing, except an atomic-rated Low that names a consumer harm (a deprecated endpoint with no `Deprecation`/`Sunset` header), which publishes as `[Recommend]`. A raw AR model on an internal-only, unversioned surface follows the Step 5 security carve-out instead ([Recommend] + verify note when +Sec is absent; core silent when +Sec runs); one finding per `file:line` either way

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
- Use skill: `rails-overengineering-review` - validations duplicating DB constraints, defensive guards on impossible states, services/`Result`/base classes wrapping trivial logic; its findings join the set (Feedback Labels), its per-category `Considered, not flagged` footer lines go to `## Maintainability Notes`
- [ ] **Test verbosity**: setup > 30 lines per example; `let!` chains replaceable by a FactoryBot trait; matchers reimplemented when shoulda-matchers exist

### Step 8 - Maintainability

- [ ] **Naming**: classes are nouns; services describe an action (`FulfillOrder`); scopes are queries (`active`, `completed_after`)
- [ ] **Magic numbers/strings** extracted to constants or `Rails.application.config.x.*`
- [ ] **Credentials/URLs**: `Rails.application.credentials` or env config, never inline - filed here even when +Sec runs; Step 9.3 dedups
- [ ] **Method length**: > 15 lines reviewed; > 30 flagged unless `.call` orchestrating clearly named steps
- [ ] **Duplicated query logic**: same `.where(...).order(...)` in 3+ places extracted to a scope or query object
- [ ] **Logging hygiene**: correct levels; structured fields when `lograge`/`semantic_logger` is configured (depth owned by observability subagent)

Use skill: `backend-coding-standards` when new naming/structure patterns are introduced.

### Step 9 - Delegate Extra Scopes in Parallel

Skip if `core-only`. For each selected scope, spawn one independent subagent in parallel. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `rails-tech-lead` spawn:

| Scope | Skill                             | Subagent (`subagent_type`)     |
| ----- | --------------------------------- | ------------------------------ |
| +Perf | `task-rails-review-perf`          | `rails-performance-engineer`   |
| +Sec  | `task-rails-review-security`      | `rails-security-engineer`      |
| +Obs  | `task-rails-review-observability` | `rails-observability-engineer` |
| +Rel  | `task-rails-review-reliability`   | `rails-reliability-engineer`   |

`Full` = 4 subagents.

Each scope's skill in that table is loaded with `Use skill:` and returns its `## Findings`; the table names it rather than repeating the directive per row.

**Subagent prompt contract:** resolved `base_ref`/`head_ref` + pre-read diff and commit log; depth level; pre-confirmed stack (the full stack-detect output); the lens returns its `## Findings` - tier sections plus any `out of lens` lines - and no Summary, Next Steps, or report.

**Failure isolation:** if a subagent fails or times out, continue with remaining results; note `Scope incomplete: <scope>` under Summary.

**No-spawn fallback:** when the environment can't spawn subagents, run each selected scope's checks inline and sequentially using the same `task-rails-review-*` skills, label the findings per scope, and note `Scopes run inline` in Summary. Each lens applies its own atomic-load gates unchanged - an inline run consults the same atomics a spawned one would, and skips the ones its gates skip. Each inline scope produces its own skill's `## Findings` first, then Step 9.3 projects and merges it - do not synthesise straight into the merged shape, or the projection step has nothing to dedup against. Inline runs behave as subagent runs: their Steps 1-3 are pre-satisfied and their report writers are skipped - this workflow owns the report. Depth propagates to delegates (the security lens ignores the depth knob by its own contract - it always runs every check).

Scopes added by *firing signals* and by *user flag* alike review the full range; Step 3.5c records the expansion for the reconciliation table.

### Step 9.3 - Assemble the Finding Set

Runs once Step 9 has returned (with no lens in scope, on core's findings alone). Verify, reconcile, and the report all read this set, so build it in order:

1. **Project each lens's findings onto this report's shape.** Match tiers on the severity word, not the heading string - perf, observability, and reliability head tiers `High` / `Medium` / `Low` (`Impact` or `Severity`), security `Critical` / `High` / `Medium` / `Low`. A `Quick Wins` heading carries no severity word - treat its findings as `Low`. Every lens block carries a `Label:` line - use it; with none, Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`. Re-file each as `### [Label] file:line` (the `file:line` prefix of its Location line) with `Issue` (the lens's `Issue`, or observability's `Missing`), `Impact` (its `Impact`, security's `Attack scenario`, or reliability's `Failure Mode` and `Blast Radius` joined in one line), `Fix`, plus `System Risk` on a `[Must]`, written here from the Step 4 lines and the lens's stated exposure. Nothing downstream reads lens headings - `review-prior-findings-reconcile` sees only `## High-Impact Findings`.
2. **Merge.** Core (Steps 5-8), Step 3.7, and lens findings that make the same claim about the same defect collapse to one entry: strongest label wins (`Must` > `Recommend`), one `file:line`, and when two or more sources raised it, `raised by: <sources>` appended to the Issue line using the tokens `core`, `+Perf`, `+Sec`, `+Obs`, `+Rel` (Step 3.7 findings count as `core`). Distinct claims at one `file:line` stay separate entries - never re-anchor one to a neighbouring line to make room. The merged entry takes the prose of the source that states the mechanism most specifically, not the strongest label's source and not the first read. When sources disagree on a fact (one lens calls a timeout infinite, another says 60 s), pick neither: Step 9.4's evidence settles it. A Step 3.7 criterion finding and a defect finding on the same gap merge the same way, the Issue line naming the criterion.
3. **Non-finding lens lines.** A lens `out of lens` line is drafted here as a finding (label per Feedback Labels, Fix written here from the defect it names) before Step 9.4. Lenses return nothing else except reliability's `Failure-Mode and Blast-Radius Map` at `deep`, preserved verbatim as its own section after Next Steps, and security's `## Axes Skipped`, which is not rendered. `## Architecture Notes` carries `architecture-guardrail`'s summary (boundary impact, coupling change, drift) and `## Maintainability Notes` the Step 7 simplification and `Considered, not flagged` lines; the labelled findings those atomics raise join the set in item 2.
4. **Next Steps.** One entry per published finding, `[Implement]` when the fix is localized to the PR, `[Delegate]` with a `[scope: <owner>]` token when it leaves the PR's scope; Step 10 orders it.

### Step 9.4 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the Step 9.3 set, the diff already read, and `base_ref` / `head_ref`. One row per assembled entry - a merged entry is one row, so the tally counts each defect once, not once per source that raised it.

Runs before reconciliation so prior-round matching sees the corrected set. Publish only rows whose Verdict is not `Dropped`, carrying the skill's `Label` and `Annotation` columns; the annotation sits on the `### [Label] file:line` heading, each its own `_(...)_` group - the combined `_(pre-existing; newly reachable via ...)_` is written as `_(pre-existing)_ _(newly reachable via ...)_`, since `review-prior-findings-reconcile` matches `_(pre-existing)_` exactly and a merged group marks an untouched prior finding `Addressed`. Fill Summary's `Findings verified:` slot in the atomic's Summary form, `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`.

### Step 9.5 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the body of the file at the handle's `report_path` (frontmatter excluded), read here
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff --name-status <base_ref>...<head_ref>` from Step 3
- `head_sha`: `current_head_sha`
- `head_files`: the file list at `current_head_sha` (`git ls-tree -r --name-only <current_head_sha>`), when `name_status` contains any `D` entry - it disambiguates undetected moves; otherwise omit

The reconcile skill returns a Markdown table, a note line when one applies, and a tally line. Insert all of it under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` or `Needs re-check` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by label alongside this round's new findings (ties at the same label: carryover first). Do not emit a standalone "Carry-Over Open Items" section. A `Still open` row this round re-derived renders once in High-Impact Findings at this round's label, once as the reconciliation row (prior label verbatim), and once in Next Steps with the suffix at this round's label - never twice in the findings list. A `Still open` or `Needs re-check` row this round did not re-derive is still unresolved: publish it in `## High-Impact Findings` at its prior label with `_(carried from round <prior.round>)_` as its own group after the provenance groups, as well as in the reconciliation table and Next Steps. A prior label outside this workflow's vocabulary (`[Blocker]`, `[High]`, `[Suggestion]`, `[Question]`) stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried. A carried finding this round re-derived at a different label publishes at this round's label, the change noted in the reconciliation row's Notes. `review-prior-findings-reconcile` parses only that section, so a row kept out of it is invisible to round 3.

### Step 10 - Report

**Assessment** follows the open-label set: `Request Changes` when any `[Must]` is open - this round's published findings and round 2+ `Still open` / `Needs re-check` reconciliation rows count alike; `Discuss` when no `[Must]` is open but a `[Recommend]` rests on an assumption only the author can settle; `Approve` otherwise - `[Recommend]`s alone do not block.

Order findings and Next Steps by label (`[Must]` first), not by scope; carryovers per Step 9.5.

**Key Takeaways** are 2-4 bullets naming what the assembled set says about the change as a whole - a pattern across findings, a systemic risk, or a structural cause. Never a restatement of individual findings.

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `report_body` (the assembled report), `branch` (Step 3), `base_ref` and `head_ref` as the handle emitted them, plus `base_sha = current_base_sha`, `head_sha = current_head_sha`
- `mode: full` (the writer's only accepted value), `round` (from Step 3.5), `prior_head_sha = prior_checkpoint.head_sha` (omit on round 1), `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` (omitted when neither)
- `scope` (resolved in Step 4; frontmatter uses the writer's enum: `Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, `Full` -> `full`), `depth` (resolved/auto-promoted), `stack = ruby-rails`

Print confirmation line.

## Feedback Labels

Every finding carries exactly one label: `[Must]` (do not merge until this is fixed) or `[Recommend]` (fix, or push back with reasoning - cannot be silently acked). No other label is written; what earns neither is not written down. Findings arriving from an atomic with High/Medium/Low severity (`complexity-review`, `backend-api-guidelines`) map High -> `[Must]`, Medium/Low -> `[Recommend]`; a maintainability-only High (complexity, structure, naming) carries `[Recommend]`; `architecture-guardrail`'s own `[Must]` / `[Recommend]` stands; an `ops-backward-compatibility` breaking change with `Compatible: No` is `[Must]`. A finding this workflow raises directly takes `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Where `review-finding-verify` publishes a different `Label`, the published label governs - in Next Steps and Assessment too.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss - <open [Must] count, and on Discuss the assumption to settle>
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical   {the atomic's line as emitted - parenthetical or two-state form included}
- **Stack Detected:** Ruby <version> / Rails <version>
- **Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full   {plus the Step 4 annotation when one applies}
- **Depth:** standard | deep   {append `auto-promoted from standard; Blast Radius: <level>` if applicable}
- **Round:** <N>   {round 2+ only}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}
- **Requirement Source:** <path or origin> (Specified | Self-attested)   {this line and the next together, or both omitted when Step 3.7 resolved no source}
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable
- **Notes:** <every note line mandated by Depth and Scope, Steps 3.5/3.5c/4/9 - narrowing, expansion, short-circuit, incomplete or inline scopes - and the handle's `notes` (base fallback, approval gate)>   {omit when none}

## Change Brief

**Requested:** <what the change was asked to do, citing the source; `(inferred from commits)` when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <each choice the request did not imply, with its consequence, excluding choices already raised as findings; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability   {omit when Step 3.7 resolved no source}

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, or `-`> | <file:line or verification note, or `-`> |

## Prior Round Reconciliation   {round 2+ only}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

<the reconcile skill's note line, when it emitted one>

Reconciliation: <a> addressed, <s> still open, <o> obsolete, <r> needs re-check.

## High-Impact Findings

### [Must] file:line   {+ annotation groups per Steps 9.4 and 9.5}
- Issue: [Rails idiom named: callback abuse, fat controller, mid-transaction HTTP, gap-lock range scan, etc.] raised by: <sources, only when two or more>
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just a local bug]
- Fix: [concrete Rails change with code]

### [Recommend] file:line
- Issue:
- Impact:
- Fix:

## Architecture Notes
- Boundary impact / Coupling change / Drift detected / lens recommendations on boundaries, coupling, dependencies

## Maintainability Notes
- Over-engineering detected / Simplification opportunities / other lens recommendations

## Key Takeaways
- 2-4 bullets on systemic impact

## Next Steps

1. **[Implement]** [Must] file:line - one-line action
2. **[Implement]** [Recommend] OldFile.rb:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [+Sec] - run `/task-rails-review-security` (suppressed signal: <signal>)
4. **[Delegate]** [Recommend] [scope: platform] - one-line action for a fix leaving the PR's scope

## <Lens section title>   {each non-finding section a lens returned, verbatim - Step 9.3}
```

_Omit empty sections. Omit Next Steps entirely if no actionable findings._

## Self-Check

- [ ] Steps 1-3: behavioral rules, stack, diff resolved (or accepted from parent); `review-precondition-check` ran with `report_type: review` (or handle received); `branch` = `head_short_name`, current_head_sha, and current_base_sha fixed before the diff/log were read once
- [ ] Step 3.5 - round decided (1 / prior + 1 / no-op); auto-fetch attempted only when prior checkpoint exists; the full `<base_ref>...<head_ref>` range analyzed regardless of round; no-op path exits without writing the report
- [ ] Step 3.7 - `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; requirement lines in Summary, or all three requirement outputs omitted when no source resolved; its findings consumed into the set, section header not rendered
- [ ] Step 4: Risk and Blast Radius stated before findings, atomic blocks not emitted; depth auto-promoted on Wide/Critical; scope resolved with its Summary annotation; a `[Delegate]` Next Step per suppressed signal
- [ ] Step 5: Rails correctness only - security idioms deferred to the security subagent or the single most severe flagged for it; API contract checks ran when the diff carried a contract-change signal
- [ ] Step 6: architecture / layering / Zeitwerk / multi-tenant / multi-DB applied via `architecture-guardrail` (or skipped via low-risk short-circuit)
- [ ] Step 7: complexity + overengineering reviews run; test verbosity checked (or skipped via low-risk short-circuit)
- [ ] Step 8: maintainability checks applied (or skipped via low-risk short-circuit)
- [ ] Step 9: non-Core subagents ran in parallel with pre-resolved artifacts (or inline in sequence, noted); failed scopes noted
- [ ] Step 9.3 - lens findings projected to `### [Label] file:line`; same-claim findings merged with strongest label and `raised by:`; distinct claims kept apart; lens `out of lens` lines drafted as findings; reliability's Map preserved
- [ ] Step 9.4 - review-finding-verify ran on the assembled set; Dropped rows excluded; verdict labels and annotation groups applied; tally in Summary in the atomic's Summary form
- [ ] Step 9.5 - on round 2+, review-prior-findings-reconcile ran with `head_sha`; reconciliation table inserted; Still open / Needs re-check rows folded into Next Steps with (open since round <N>) suffix at the right label; legacy labels mapped
- [ ] Step 10: Assessment derived from the open-label set; findings and Next Steps ordered by label; report written via `review-report-writer` with every required input (report_type, report_body, branch, base_ref, head_ref, base_sha, head_sha, mode, round, prior_head_sha when round > 1, scope, depth, stack, pr_url when known)
- [ ] Every Must cites system risk; every finding has label + `file:line` + actionable Rails fix

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is `git fetch <remote> <branch>` in Step 3.5a, and only when a valid prior checkpoint exists.
- Auto-fetching on round 1 (no prior checkpoint) - keeps first-run behavior strictly read-only.
- Scoping round 2+ analysis to `<prior_checkpoint.head_sha>...<head_sha>` - risk, scope, depth, and requirement fit score the full `<base_ref>...<head_ref>` range on every round.
- Writing the report on no-op exit - the file must stay byte-identical. (Same head SHA with expanded scope/depth is not a no-op - Step 3.5b.)
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Duplicating perf / security / observability / reliability depth here - dedicated subagents own it
- Reviewing without reading the full diff and log first
- Applying generic backend conventions where a Rails idiom exists
- Nitpicking style
- Running extra-scope subagents sequentially or when `core-only` was passed
