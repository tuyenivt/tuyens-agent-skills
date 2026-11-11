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

Depth (`standard` (default) | `deep`) and scope (`Core` | `+Perf` | `+Sec` | `+Obs` | `+Rel` | `Full`) follow `task-code-review`. Scope flags combine and are the exact scope: a flagged run spawns the lenses the user named and no other. Signals escalate only an unflagged invocation; pass `core-only` to suppress them.

**Auto-promote depth to `deep`** in Step 4, before any lens is spawned, when Blast Radius is Wide/Critical. Record in Summary. On round 2+ nothing is inherited; when the resolved depth falls below the checkpoint's (round 1 was user-flagged `deep`), note in Summary: `Depth narrowed vs round <prior.round> - re-run with deep to re-cover.`

**Auto-escalate scope on Rails signals** (unflagged invocations only):

- **+Sec**: file upload (Active Storage/Shrine/CarrierWave), Devise/Pundit/CanCanCan config, `params.permit` changes, raw SQL, secrets, Sidekiq taking user input, a new action with no authentication filter or one authorizing outside the app's policy layer (a hand-rolled role check)
- **+Perf**: `db/migrate/`, `add_index`, new `.where`/`.order`/scopes, new payload endpoints, loops hitting DB or HTTP
- **+Obs**: log/notifications/tracer config, a new external dependency, or a new service / ActiveJob / Sidekiq class whose diff adds no instrumentation (no structured log or event)
- **+Rel**: new Faraday/`Net::HTTP` client without timeout, `stoplight`/`retriable` config, job (Sidekiq or Active Job) without an idempotency guard, external call or `.perform_async` inside a transaction, unbounded `.all.each`, missing `after_commit` dispatch
- Two or more categories firing -> **Full** (all four lenses run, fired or not)
- With a scope flag passed, a category firing outside the flags escalates nothing - it becomes a `[Delegate]` Next Step (Step 4)

## Invocation

`/task-rails-review [<branch>|pr-<N>] [--base <branch>] [--req <path>] [+sec] [+perf] [+obs] [+rel] [full|core-only] [standard|deep]`

Defaults to current branch vs base; fails fast on trunk. Use `pr-<N>` for a local fetched ref. The workflow never modifies the working tree, and the review is static: it reads code and git objects, and runs the suite, boots the app or starts a service only when the invocation asks for it.

Pass `--req <path>` to name a requirement source (ticket export, PRD, spec) for Step 3.7; without it, `review-change-intent`'s own source ladder decides what counts as a source - the workflow adds nothing.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected from parent. Where the project's declared stack and its code disagree, record what the code does and note the divergence. If not Rails, redirect to `/task-code-review`. Versions: read Ruby / Rails from `.ruby-version` / `Gemfile.lock` (at the reviewed head - `git show <head_ref>:<path>` once Step 3 fixes a commit that is not checked out; `stack-detect` carries them only when the instruction file's stack section declares them, and a declared version the lockfile disagrees with is the divergence case above - the lockfile's value, divergence noted), else `unknown`, and the MySQL patch level from stack-detect's `Database` value, ops docs or the server, else `unknown`; read `config.load_defaults` from `config/application.rb` beside them - a version-gated default follows it, not the installed gem; `rails-migration-safety`'s INSTANT / functional-index / CHECK gates read that patch level.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the invocation's target argument, any `--base`, and `report_type: review`. Surface fail-fast messages verbatim and stop. The handle may include a `prior_checkpoint` block (the file at its `report_path` exists with valid frontmatter) or the scalar `legacy`. Decision logic is Step 3.5; for now, just hold onto it.

From the handle, fix `branch` = its `head_short_name` (never `HEAD`, never remote-prefixed - the atomic strips `origin/`). It names the review target everywhere below: the no-op message, the writer's `branch` field, and the report filename. `head_ref` passes through unchanged to the diff commands and to the writer.

Capture the current SHAs first - the Step 3.5 no-op gate needs only these:

- `current_head_sha = git rev-parse <head_ref>`
- `current_base_sha = git rev-parse <base_ref>`

Then, once Step 3.5 has not stopped the run, read **once** (skip when a parent passed pre-read artifacts):

- `git diff <base_ref>...<head_ref>`
- `git diff -M --name-status <base_ref>...<head_ref>`
- `git log <base_ref>..<head_ref>` (full messages - Step 3.7 reads criteria from commit bodies)

### Step 3.5 - Decide Round (re-review auto-detect)

**Every round analyzes the full `<base_ref>...<head_ref>` range read in Step 3.** Risk, blast radius, scope signals, depth promotion, and requirement fit are scored on the whole change on every round, so a small follow-up commit cannot under-score a large PR and a defect missed in round 1 stays reachable in round 2. Rounds differ only in that round 2+ reconciles against the prior report and may carry lens findings instead of re-running the lenses (Step 3.5d).

Skip if the handle has no `prior_checkpoint` -> `round = 1`, no fetch, no reconciliation. Continue to Step 4.

If `prior_checkpoint: legacy` (file present, frontmatter missing/invalid) -> `round = 1`. Note in Summary: `Prior report lacks checkpoint metadata - treated as round 1.` Continue to Step 4.

Otherwise (valid prior checkpoint present):

**Step 3.5a - Auto-fetch the head branch.** Only when a valid prior checkpoint exists, the handle's `head_is_remote` is false, and the upstream is not `base_ref`, refresh the local branch's remote-tracking ref for the reader's reference:

```bash
remote=$(git config "branch.<branch>.remote") && merge=$(git config "branch.<branch>.merge") && [ "$remote/${merge#refs/heads/}" != "<base_ref>" ] && git fetch "$remote" "${merge#refs/heads/}"
```

The upstream's branch half, not `<branch>`, names the remote ref (a `pr-42` branch tracking `origin/feature/x` fetches `feature/x`). No checkout, no merge. If either config key is unset (pr-ref with no upstream, detached HEAD, no remote configured), skip the fetch silently. If `git fetch` fails (offline, auth, deleted remote branch), continue silently - this is a convenience, not a gate. The fetch writes `FETCH_HEAD` and, only when `remote.<remote>.fetch` maps the branch, `refs/remotes/<remote>/<upstream branch>`; it never moves a local branch or `HEAD`, so `current_head_sha` does not change and is not re-resolved. With `head_is_remote` true the fetch is skipped: it would move `head_ref` itself out from under the captured SHA; the guard skips it likewise when `<remote>/<upstream branch>` is `base_ref` (a branch cut from `origin/main` tracks `main`), or the diff would be read against a moved base.

**Step 3.5b - Compare checkpoints.**

| Condition                                                              | Decision                                                                                                                            |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `prior_checkpoint.head_sha == current_head_sha`, `prior_checkpoint.base_ref == base_ref` and `prior_checkpoint.base_sha == current_base_sha`, and the checkpoint's `scope` / `depth` cover the invocation's (covering = superset: `full` covers every scope, a flag set covers each subset of it, any scope covers `core-only`, `deep` covers `standard`; a `core-only` checkpoint covers an unflagged invocation - an unflagged run with no firing signal writes `core-only` too, so re-covering suppressed signals takes the lens flags; map the invocation's flags to the writer enum per Step 10 before comparing) | **No-op.** Print `No new commits on <branch> since prior review at <sha_short>. Prior report unchanged.` (`<sha_short>` = the first 7 chars of `current_head_sha`) and stop. Do not call `review-report-writer`. |
| `prior_checkpoint.head_sha == current_head_sha`, but the invocation's scope or depth is not covered | `round = prior.round + 1`. Note in Summary: `Same head as round <prior.round>; re-review for expanded <scope\|depth>.` |
| `git merge-base --is-ancestor <prior_checkpoint.head_sha> <current_head_sha>` fails (prior SHA unreachable) | `round = prior.round + 1`. Note in Summary: `Prior checkpoint unreachable - history rewritten.`      |
| `prior_checkpoint.base_sha != current_base_sha`                        | `round = prior.round + 1`. Note in Summary: `Base branch advanced since round <prior.round>.`       |
| `prior_checkpoint.base_ref != base_ref`                                | `round = prior.round + 1`. Note in Summary: `Base ref changed since round <prior.round>.`           |
| None of the above                                                       | `round = prior.round + 1`.                                                                          |

Apply the first matching row's decision; when several rows match, emit every matching row's Summary note - except on the no-op row, which stops before a Summary exists: it prints its line and nothing else.

**Step 3.5c - Scope expansion handling.**

If the user's invocation expanded scope vs. the prior round (e.g., round 1 was `core-only`, round 2 is `full`), the newly-added scopes have no prior findings to reconcile. Record in Summary, once Step 4 has resolved this round's scope: `Scope expanded round <N>: +<list>.`

The reconciliation table (when emitted) only covers findings whose scope was active in the prior round.

**Scope on round 2+** resolves exactly as on round 1 (Step 4): the user's flags when any were passed, else the signals firing on the full range, with `core-only` suppressing them. Nothing is inherited from the checkpoint - a scope that escalated in round 1 escalates again on its own. When the resolved scope still falls below the checkpoint's (round 1 carried flags this round lacks, or this round's flags or `core-only` left out a lens round 1 ran), note in Summary: `Scope narrowed vs round <prior.round>: <list> - re-run with <flags> to re-cover.`

**Step 3.5d - Lens re-run gate.** Core Steps 5-8 re-read the full range every round; the lenses re-run only when the commits since the prior round could change what they found. Decide it at the end of Step 4, where the lenses would spawn: run `git diff --name-only <prior_checkpoint.head_sha> <current_head_sha>`. The lenses are carried, not spawned, when all of these hold: the command exits 0; every path it lists (an empty list included) is documentation (`*.md`, `docs/`) or a spec / test file that is not a fixture, factory or cassette; the resolved scope and depth are covered by the checkpoint's; and the prior Summary carries no `Scope incomplete` note. A carried lens's prior findings reach this report through Step 9.5 as rows this round did not re-derive. Note in Summary: `Lenses carried from round <prior.round>: commits since touch no runtime file.` Any other outcome (a non-zero exit, one runtime path, a newly added lens, a deeper depth) runs Step 9 in full.

### Step 3.7 - Change Intent

Use skill: `review-change-intent` with the `<base_ref>...<head_ref>` diff and log, the `--req <path>` file when passed, and the handle's `report_path` (as its `prior_report_path`) when round > 1.

Its `## Change Brief` block goes into the report verbatim, its `## Requirement Traceability` table renders as that section when a source resolved, its `Requirement Source` and `Requirement Fit` lines go into Summary, and its `### Requirement Findings` items join the assembled set in Step 9.3 - that section and the `### No Requirement Findings` marker are consumed, never rendered. With no requirement source the Brief still renders, and the traceability block and its two Summary lines are omitted. Runs before the Step 4 risk snapshot - acceptance criteria decide what counts as a defect downstream - and the low-risk short-circuit never skips it.

### Step 4 - Risk Snapshot

Use skills: `review-pr-risk`, `review-blast-radius`. State **Risk Level** and **Blast Radius** before line-level findings, each as the atomic's line value as emitted (a `(contract break: ...)` parenthetical or a two-state `<level> (unmitigated) -> <level> (with ...)` form stays whole; the promote and short-circuit tests read the unmitigated level unless the `Mitigation:` tag is `in-place:`). Only those two lines reach the report; the atomics' full blocks (`Signals:`, `Action:`, dimension lines, `Mitigation:`) inform the review and are not emitted.

**Resolve scope now:** the user's scope flags, exactly, when any were passed (`full` = all four lenses); with none, the signals firing on the Step 3 diff (two or more categories -> `Full`); `core-only` suppresses signal escalation. The Summary `Scope:` line carries the resolved value plus one annotation:

| Observed                              | Annotation                                         |
| ------------------------------------- | -------------------------------------------------- |
| No user flag, signals fired           | `auto-escalated from Core; signals: <list>`        |
| User flag, further categories fired   | `user-flagged; signals not escalated: <list>` (the categories beyond the flagged ones) |
| `core-only`, signals fired            | `core-only; suppressed signals: <list>`            |
| Otherwise                             | none                                               |

Every signal firing for a lens outside the resolved scope - suppressed by `core-only` or left out by the user's flags - also emits a `[Delegate]` Next Step tagged `[+<Lens>]` naming the matching `/task-rails-review-*` command, whether or not the short-circuit below fires; a `[Delegate]` for a fix leaving the PR's scope is tagged `[scope: <owner>]` instead. A Step 5 carve-out finding on the same defect keeps its own `[Implement]` entry - the lens sweep and the point fix are separate steps, never merged.

**Low-risk short-circuit:** Risk: Low + Blast Radius: Narrow + change does not touch auth, middleware, API contracts, shared concerns, `app/services/`, or `lib/` -> skip Steps 6-8. Step 5 runs with its atomic skills; Step 9 follows its own scope rules; Steps 9.3-9.4 (and 9.5 on round 2+) and Step 10 run as usual. Note `Low-risk short-circuit: Steps 6-8 skipped` in Summary.

**Spawn the Step 9 lenses now.** Risk, depth (after auto-promotion) and scope are final here, so launch each lens Step 9 selects before starting Step 5 and run Steps 5-8 while they work; Step 9.3 waits for every one of them.

### Step 5 - Rails Correctness

Logical correctness, state-integrity, transaction boundaries, backward compat. Scope strictly to **Rails-specific correctness** - security idioms (authentication wiring, strong params, authz, IDOR, mass assignment, AR-in-API leakage) belong to `task-rails-review-security`; an inbound `Idempotency-Key` gap is the API contract gate's (below, via `backend-api-guidelines`), never deferred. When +Sec IS in scope, core stays silent on the security idioms - the subagent owns them. When +Sec is not in scope, raise only the most severe as one finding ending "verify via `/task-rails-review-security`", labelled per Feedback Labels (an exploitable hole on a changed path is `[Must]`) - one finding for the whole deferred lens, not one per checklist family; the rest are not written; the lens owns them. Job idempotency guards, retries, timeouts, unbounded iteration, and pool/queue saturation follow the same pattern with +Rel: the reliability subagent owns them when +Rel is in scope; otherwise raise only the most severe as one finding + "verify via `/task-rails-review-reliability`", labelled per Feedback Labels. Dual-natured findings (a TOCTOU balance check is both a race and an authz-adjacent hole) are filed by core for the correctness dimension; the merge unifies.

Atomic skills - load with `Use skill:` each one whose area the PR touches:

- `rails-activerecord-patterns` (models, associations, scopes)
- `rails-service-objects` (new/extended service)
- `rails-sidekiq-patterns` (new/modified job)
- `rails-transaction-patterns` (transaction boundaries, nested transactions, callbacks, `after_commit` dispatch)
- `rails-concurrency-patterns` (`load_async`, threads, fibers, fan-out)
- `rails-actioncable-patterns` (channels, Turbo broadcasts)
- `rails-exception-handling` (rescue logic, new error classes, Sidekiq error flow)
- `rails-view-templates` (diffed `.erb`/`.haml`/`.slim` templates)

`deep` depth in core steps: read every atomic skill listed above (not only touched-area ones; each lens keeps its own load gates) and each touched file in full plus the code the diff calls into before judging; apply each atomic where that reading finds its surface, and drop one with none silently, without a consulted-clean note - the review stays PR-shaped, never a repo sweep.

Checks:

- [ ] **Transactions / callbacks**: writes wrapped; no HTTP / `.perform_async` / `deliver_now` inside transactions or `after_save`/`after_create` - dispatch via `after_commit` (see `rails-transaction-patterns`). An Active Job `perform_later` / `deliver_later` deferred to commit by `enqueue_after_transaction_commit`, Sidekiq `perform_async` under `Sidekiq.transactional_push!`, or any enqueue on Solid Queue with no production `config.solid_queue.connects_to` (the job row commits with the caller's transaction), is not a finding - read the setting per `rails-transaction-patterns`; when it is not in evidence, file the finding and name the setting to check in its Fix. Sidekiq's bulk forms are findings whatever the setting - `push_bulk` / `perform_bulk` and a push inside a `Sidekiq::Batch` enqueue immediately; off that Solid Queue setup `ActiveJob.perform_all_later` enqueues immediately below Rails 8.1.2, and from 8.1.2 defers only the jobs whose class sets `enqueue_after_transaction_commit = true`.
- [ ] **`save!`** in services/transactions so failures surface
- [ ] **Error handling**: no bare `rescue` / `rescue Exception` / blanket `rescue StandardError` that logs-and-continues; `Pundit::NotAuthorizedError` and app-level `ApplicationError` centralized via `rescue_from` in `ApplicationController` (an uncaught `RecordNotFound` is already a 404 via `rescue_responses` - a per-action rescue of it is the finding, not its absence)
- [ ] **Bulk operations**: partial-failure path defined; transaction wraps one chunk, not whole run or single row
- [ ] **Concurrency**: no class-level mutable state; a per-request zone set with `Time.use_zone` in an `around_action`, not a bare `Time.zone=` that leaks into the thread's next request; race-prone updates use row-level lock or `with_advisory_lock`

**Test coverage** (named finding, not buried): logic added without spec or Minitest coverage -> `[Recommend]`; escalate to `[Must]` on critical paths: auth, authz, money/billing, multi-record transactions, state machines, data-mutating Sidekiq jobs, migrations changing column semantics.

**Test files are reviewed for coverage and committed secrets only.** A live credential or real personal data in a diffed fixture, factory or cassette is a `[Must]` at its own `file:line`. Otherwise, for files that are themselves tests, the only finding to raise is a coverage gap: production logic in the diff that no test exercises. Anchor that finding to the untested production `file:line` and state the case to cover, not the test file. Do not review test code for style, structure, duplication, naming, or performance - a passing test with awkward setup is not a finding.

**Migration PRs** (`db/migrate/` change) - Use skill: `rails-migration-safety`, `ops-backward-compatibility`:

- [ ] Two-phase column rename/drop (add -> backfill -> cut over -> remove)
- [ ] `NOT NULL` on existing columns via the safe path (backfill, then `change_column_null` - an INPLACE rebuild; >100M rows through gh-ost / pt-online-schema-change)
- [ ] `add_index`: `algorithm: :inplace` - online with concurrent DML for a B-tree secondary index (Rails emits no LOCK clause; an exact `LOCK=NONE` needs `execute`; a FULLTEXT or SPATIAL index add blocks writes, and a table's first FULLTEXT also rebuilds it); never `algorithm: :concurrently`, which the MySQL adapter rejects. Past ~100M rows any index build goes through gh-ost, or pt-online-schema-change when the table is an FK child or parent - gh-ost refuses both
- [ ] Foreign keys on existing tables: MySQL has no `NOT VALID` - with `foreign_key_checks=1` `ADD FOREIGN KEY` is ALGORITHM=COPY, and gh-ost refuses any FK-bearing table, so a large table goes through `pt-online-schema-change --alter "ADD FOREIGN KEY ..."` (adding `--alter-foreign-keys-method=rebuild_constraints` when other tables reference it) or a maintenance window
- [ ] Data migrations in rake tasks, not `db/migrate/`
- [ ] Rollback path documented

**API contract PRs** - run when the diff carries a contract-change signal: a removed / renamed / retyped serializer attribute, a changed rendered status code, a newly `permit`-ted required field or tightened validation, a new public route in a `/v1/`-versioned or external API namespace, a new non-GET write route whose effect duplicates on retry with no `Idempotency-Key` support, a `render json:` on a raw AR model with no serializer, or an rswag / `openapi.yaml` edit. Use skills: `backend-api-guidelines`, `ops-backward-compatibility`:

- [ ] Breaking change (removed/renamed/retyped attribute, tightened validation, newly required param, changed status or error shape) carries a version bump or expand-contract plan; "no external callers" backed by a search; when consumption is unknown, treat a `/v1/`-versioned or spec-published surface as externally consumed and an unversioned, unpublished `/api/` namespace as internal unless the request or commits say otherwise; a repo-wide convention of rendering raw models does not lower the tier
- [ ] Responses rendered through serializers, never a raw AR model; errors follow RFC 9457; collections paginated
- [ ] rswag / `openapi.yaml` matches the code - changed endpoints, schemas, status codes, and error shapes present and accurate
- [ ] Each finding names who breaks and how (for a leaked AR model: what it exposes and who couples to it). These tiers replace `backend-api-guidelines`' own: High -> `[Must]` = unversioned breaking change to an externally consumed contract, a raw AR model rendered on an externally consumed or versioned surface, a write endpoint whose effect duplicates on retry with no `Idempotency-Key` support, or missing input validation on an external surface - a contract-shape finding this gate files itself (the Step 9.3 merge dedups with +Sec, per the dual-natured rule); Medium -> `[Recommend]` = internal breaking change with no coordinated-deploy note, missing input validation on an internal-only surface (this gate's finding, not the carve-out's), inconsistent status/error envelope, unpaginated unbounded collection, rswag / `openapi.yaml` out of sync with the code; Low = naming drift with no consumer impact - below the reporting bar, write nothing, except an atomic-rated Low that names a consumer harm (a deprecated endpoint with no `Deprecation`/`Sunset` header), which publishes as `[Recommend]`. A raw AR model on an internal-only, unversioned surface follows the Step 5 security carve-out instead (the single deferred finding + verify note when +Sec is absent; core silent when +Sec runs); one finding per `file:line` either way. An atomic-rated High or Medium this list does not name keeps its atomic tier (High -> `[Must]`, Medium -> `[Recommend]`); one that is a security idiom (an error body leaking stack traces or internal IDs) follows the Step 5 security carve-out

### Step 6 - Architecture

Use skill: `architecture-guardrail`.

- [ ] **Layering**: presentation -> service/domain -> data. No business logic in controllers; no `Net::HTTP` in models; no view rendering in services
- [ ] **Service discipline**: extraction follows `rails-service-objects`' bar (2+ models or an external API plus a transaction boundary, or 3+ call sites - never line count); services follow its shape (instance `#call`; `Result` where the caller branches on an expected failure) - a service below that bar is Step 7's finding, not a missing one here, unless the project's CLAUDE.md mandates services for writes, where `architecture-guardrail` files the missing one as a documented-rule violation and Step 7 files none
- [ ] **Concern hygiene**: `app/**/concerns/*.rb` role-based (`Sluggable`, `SoftDeletable`), not grab-bags
- [ ] **Zeitwerk**: file paths match constant names; no `require_relative` inside `app/`
- [ ] **Namespace / engine boundaries**: cross-namespace access via service objects, not direct model reach-in
- [ ] **Multi-tenant isolation**: enforced at the model layer (`acts_as_tenant`, `default_scope`, query objects), not controller-only
- [ ] **Multi-database**: `connects_to` declared on an abstract base class (it raises on a concrete model) that the models inherit; a model bypassing that base, and cross-DB joins, flagged

For multi-service PRs, also Use skill: `ops-backward-compatibility` for API contract compatibility and deployment order.

### Step 7 - Code Hygiene

- Use skill: `complexity-review` - cyclomatic/cognitive complexity, method length, nesting
- Use skill: `rails-overengineering-review` - validations duplicating DB constraints, defensive guards on impossible states, services/`Result`/base classes wrapping trivial logic, redundant indirection (`User -> Decorator -> Presenter -> Serializer`); its findings join the set (Feedback Labels), except a Category 3 service finding when the project's CLAUDE.md mandates services for writes (Step 6); its per-category `Considered, not flagged` footer lines go to `## Maintainability Notes`

### Step 8 - Maintainability

- [ ] **Naming**: classes are nouns; services describe an action (`FulfillOrder`); scopes are queries (`active`, `completed_after`)
- [ ] **Magic numbers/strings** extracted to constants or `Rails.application.config.x.*`
- [ ] **Credentials/URLs**: `Rails.application.credentials` or env config, never inline - filed here even when +Sec runs; Step 9.3 dedups
- [ ] **Method length**: `complexity-review`'s thresholds (Step 7) govern, not re-flagged here; a `.call` orchestrating clearly named steps lowers that finding's severity (this workflow's exemption, applied when the row is filed)
- [ ] **Duplicated query logic**: same `.where(...).order(...)` in 3+ places extracted to a scope or query object
- [ ] **Logging hygiene**: correct levels; structured fields when `lograge`/`semantic_logger` is configured (depth owned by observability subagent)

Use skill: `backend-coding-standards` when new naming/structure patterns are introduced.

### Step 9 - Delegate Extra Scopes in Parallel

Skip when the resolved scope is `Core` (`core-only` suppresses signals; a user flag beside it still runs its lens) or Step 3.5d carried the lenses. The spawn happens at the end of Step 4; this step is the lenses' contract and where their results are collected. A selected lens is spawned only when the diff holds something it reads: when name-status lists no Ruby, template, `config/`, `db/` or Gemfile path (a docs-only, frontend-only or CI-only diff), a lens runs only for an area a changed document makes claims about (a design doc proposing a retry policy runs +Rel), and Step 5 checks those claims against the code at `head_ref`. Each lens left out is a Summary note, `Lens not run: <scope> - no surface in the diff`; the resolved scope is unchanged. For each selected scope, spawn one independent subagent in parallel. Use the **declared subagent for that scope** (`subagent_type` below) - do not infer the agent from the scope name; an observability review is not a `rails-tech-lead` spawn:

| Scope | Skill                             | Subagent (`subagent_type`)     |
| ----- | --------------------------------- | ------------------------------ |
| +Perf | `task-rails-review-perf`          | `rails-performance-engineer`   |
| +Sec  | `task-rails-review-security`      | `rails-security-engineer`      |
| +Obs  | `task-rails-review-observability` | `rails-observability-engineer` |
| +Rel  | `task-rails-review-reliability`   | `rails-reliability-engineer`   |

`Full` = 4 subagents, fired or not.

Each scope's skill in that table is loaded with `Use skill:` and returns its `## Findings`; the table names it rather than repeating the directive per row.

**Subagent prompt contract:** resolved `base_ref`/`head_ref` + pre-read diff and commit log (a diff too large to inline goes in a scratch file outside the repository, never in the working tree); the resolved depth, after Step 4's auto-promotion; pre-confirmed stack (the full stack-detect output); Step 3.7's `## Change Brief` and, when a source resolved, its criteria - a lens finding that contradicts a criterion or a recorded author decision names it in its Issue line; each spawned lens runs its own Step 1 (`behavioral-principles`), or the spawning prompt inlines the whole Rules section and the disclosure block where the subagent cannot load it; the lens returns a `Loaded:` line naming the atomic skills it loaded, then its `## Findings` - tier sections plus any `out of lens` lines, with reliability's Failure-Mode and Blast-Radius Map after them at `deep` and security's `## Axes Skipped` - and no Summary, Next Steps, or report. A hand-back with no `Loaded:` line, or one reading `none` where the diff holds that lens's surface, is a Summary note: `Lens atomics not loaded: <scope>`.

**Failure isolation:** if a subagent fails or times out, continue with remaining results; note `Scope incomplete: <scope>` under Summary.

**No-spawn fallback:** when the environment can't spawn subagents, run each selected scope's checks inline and sequentially using the same `task-rails-review-*` skills, label the findings per scope, and note `Scopes run inline` in Summary. Each lens applies its own atomic-load gates unchanged - an inline run consults the same atomics a spawned one would, and skips the ones its gates skip. Each inline scope produces its own skill's `## Findings` first, then Step 9.3 projects and merges it - do not synthesise straight into the merged shape, or the projection step has nothing to dedup against. That per-lens `## Findings` is working material, not a report section; the lens's own verify, reconcile and writer steps do not run - Step 9.4 verifies and Step 9.5 reconciles the merged set once. Inline runs behave as subagent runs: their stack detection and diff resolution are pre-satisfied - each lens still makes its Step 2 recordings (auth / authz flavors; logger, tracing, error tracker; DB and versions; background runtime) from the artifacts - and their report writers are skipped; this workflow owns the report. Depth propagates to delegates (the security lens ignores the depth knob by its own contract - it always runs every check).

Scopes added by *firing signals* and by *user flag* alike review the full range; Step 3.5c records the expansion for the reconciliation table.

### Step 9.3 - Assemble the Finding Set

Runs once Step 9 has returned (with no lens in scope, on core's findings alone). Verify, reconcile, and the report all read this set, so build it in order:

1. **Project each lens's findings onto this report's shape.** Match tiers on the severity word, not the heading string - perf, observability, and reliability head tiers `High` / `Medium` / `Low` (`Impact` or `Severity`), security `Critical` / `High` / `Medium` / `Low`. A `Quick Wins` heading carries no severity word - treat its findings as `Low`. Every lens block carries a `Label:` line - use it; with none, Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`. Re-file each as `### [Label] file:line` (the `file:line` prefix of its Location line; a Location with none takes: `Controller#a, #b` -> the controller file at the first named action's line; a route -> `config/routes.rb` at the route's line; a file named without a line -> the line of the construct named; an absent file -> `<path>:1`; a bare class name -> its defining file at the class line; `a:line -> b:line` -> the left-hand `file:line`, the right side named in Issue; a module or edge anchor -> the first file of the module or edge at the violating line, the module or edge named in Issue) with `Issue` (the lens's `Issue`, or observability's `Missing`), `Impact` (its `Impact`, security's `Attack scenario`, or reliability's `Failure Mode` and `Blast Radius` joined in one line), `Fix`, plus `System Risk` on a `[Must]`, written here from the Step 4 lines and the lens's stated exposure. Nothing downstream reads lens headings - `review-prior-findings-reconcile` sees only `## High-Impact Findings`. Core, Step 3.7, and atomic-shaped findings (`- [Label] file:line - claim`, Category / Cost / Recommendation, Signal / Simplification, Issue / Impact / Drift, table rows) take the same shape: the claim -> `Issue`, its cost or impact -> `Impact`, its recommendation -> `Fix`, each drafted here when the source carries none. A `GAP`- or `BLOCKER`-marked block field with no numbered finding, a `rails-migration-safety` `Safety: Blocked | Maintenance Window | Reject`, and a `rails-view-templates` review block (Critical / High -> `[Must]`, Medium / Low -> `[Recommend]`) are each drafted as a finding; the atomics' own blocks are not emitted, and an overengineering sibling pointer to `rails-security-patterns` follows the Step 5 security carve-out.
2. **Merge.** Core (Steps 5-8), Step 3.7, and lens findings that make the same claim about the same defect collapse to one entry: strongest label wins (`Must` > `Recommend`), one `file:line`, and when two or more sources raised it, `raised by: <sources>` appended to the Issue line using the tokens `core`, `+Perf`, `+Sec`, `+Obs`, `+Rel`, each once (Step 3.7, atomic and Step 5-8 findings all count as `core`). Distinct claims at one `file:line` stay separate entries - never re-anchor one to a neighbouring line to make room. The merged entry takes the prose of the source that states the mechanism most specifically, not the strongest label's source and not the first read. When sources disagree on a fact (one lens calls a timeout infinite, another says 60 s), pick neither: Step 9.4's evidence settles it. A Step 3.7 criterion finding and a defect finding on the same gap merge the same way, the Issue line naming the criterion. A finding that contradicts a criterion or a recorded author decision - the code does what was specified, and the finding disputes the specification - is `[Must]` only when the specified behaviour is itself a security hole or loses data, `[Recommend]` otherwise, with its Fix phrased as the question for the requirement's owner.
3. **Non-finding lens lines.** A lens `out of lens` line is drafted here as a finding (label per Feedback Labels, Fix written here from the defect it names) before Step 9.4. Lenses return nothing else except reliability's `Failure-Mode and Blast-Radius Map` at `deep`, preserved verbatim as its own section after Next Steps, and security's `## Axes Skipped`, which is not rendered. `## Architecture Notes` carries the `Drift:` lines of `architecture-guardrail`'s violations (omitted on its `No Violations Found`) and `## Maintainability Notes` the `Considered, not flagged` lines; `complexity-review`'s rows (a row's `Simplification:` is its Fix) and `rails-overengineering-review`'s labelled findings join the set in item 2.
4. **Next Steps** - built in Step 10, once Steps 9.4 and 9.5 have settled the published set. One entry per finding published in `## High-Impact Findings` (two findings at one `file:line` are two entries; a `## Pre-existing Risks` line takes none), `[Implement]` when the fix is localized to the PR, `[Delegate]` with a `[scope: <owner>]` token when it leaves the PR's scope; Step 10 orders it. `[scope: <owner>]` names who owns the work - platform, schema, dependencies, infra, load-test, a team - never a lens.

### Step 9.4 - Verify Findings (second pass)

Use skill: `review-finding-verify` with the Step 9.3 set, the diff already read, and `base_ref` / `head_ref`. One row per assembled entry - a merged entry is one row, so the tally counts each defect once, not once per source that raised it. A row that holds only if a gem or Rails behaves a certain way (a default timeout, a retry rule, a version-gated default the app's own files do not set, whether or not a lens states it) is settled with Use skill: `rails-gem-source-evidence` before verify rules on it, its block attached to the finding's claim in `findings`, the locked version read from `Gemfile.lock` at `head_ref` (an installed gem at another version is a failed probe). Gem source that atomic read counts as in-tree code for verify, not the out-of-tree package of its `Unverified` rule, and a part it left unread is a construct verify could not read; verify rules from there by its own steps, and a row left `Unverified` by an unread part publishes with the atomic's `_(unverified: gem source not read - <reason>)_` group.

Runs before reconciliation so prior-round matching sees the corrected set. A row whose Verdict is plain `Pre-existing` - the PR neither wrote the defect nor changed how it is reached - publishes as one line under `## Pre-existing Risks`, never in `## High-Impact Findings`: it is context for the author, carries no label, and never moves the Assessment. Every other row whose Verdict is not `Dropped` publishes in `## High-Impact Findings`, carrying the skill's `Label` and `Annotation` columns; the annotation sits on the `### [Label] file:line` heading, each its own `_(...)_` group - the combined `_(pre-existing; newly reachable via ...)_` is written as `_(pre-existing)_ _(newly reachable via ...)_`, since `review-prior-findings-reconcile` matches `_(pre-existing)_` exactly and a merged group marks an untouched prior finding `Addressed`. A finding anchored in an existing file the diff does not touch carries `_(pre-existing)_`, written first, before any `_(unverified: ...)_` or `_(mechanism: ...)_` group, even when verify attached no such group (an `Unverified` row carries both groups; an anchor on a path absent at `head_ref`, whatever its source, gets no added group) - without it, reconcile cannot tell a pre-existing finding on an untouched file from one the PR reverted, and an `Addressed` row on it reads `reverted to base state` instead of `fixed on the base branch`. The verify table itself is working material, never a report section - only its labels, annotations and tally reach the report. A Step 3.7 requirement finding in an untouched file carries the group too, although verify's own Annotation for it is `-`. Fill Summary's `Findings verified:` slot in the atomic's Summary form, `<N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}`.

### Step 9.5 - Reconcile Prior Findings (round 2+ only)

Skip on round 1. Otherwise Use skill: `review-prior-findings-reconcile` with:

- `prior_report`: the body of the file at the handle's `report_path` (frontmatter excluded), read here
- `diff`: the full-range diff from Step 3
- `name_status`: the full-range `git diff -M --name-status <base_ref>...<head_ref>` from Step 3
- `head_sha`: `current_head_sha`
- `base_ref`: the handle's `base_ref` - reconcile derives the merge base from it
- `head_files`: the file list at `current_head_sha` (`git ls-tree -r --name-only <current_head_sha>`) - reconcile probes it for a prior path that `name_status` does not list

The reconcile skill returns a Markdown table, its note lines when any apply, and a tally line. Insert all of it under `## Prior Round Reconciliation` in the report (see Output Format).

Fold any `Still open` or `Needs re-check` rows into `## Next Steps` as `(open since round <prior.round>)`-suffixed entries, ordered by label alongside this round's new findings (ties at the same label: carryover first). Do not emit a standalone "Carry-Over Open Items" section. A `Still open` row this round re-derived renders once in High-Impact Findings at this round's label, once as the reconciliation row (prior label verbatim), and once in Next Steps with the suffix at this round's label - never twice in the findings list. A `Still open` or `Needs re-check` row this round did not re-derive is still unresolved: publish it in `## High-Impact Findings` at its prior label with `_(carried from round <prior.round>)_` as its own group after the provenance groups, as well as in the reconciliation table and Next Steps. A prior row joining two smells with one fixed is `Still open`, its Notes naming the fixed half; a carried finding cites its current `file:line` when the site moved (the table row keeps the prior one verbatim). A prior label outside this workflow's vocabulary (`[Blocker]`, `[High]`, `[Suggestion]`, `[Question]`) stays verbatim in the table and maps before publication: `[Blocker]`, `[High]`, `[Critical]` -> `[Must]`; anything else -> `[Recommend]`; `[Praise]` rows are never carried. A carried finding this round re-derived at a different label publishes at this round's label, the change noted in the reconciliation row's Notes. A prior row that verify rules plain `Pre-existing` this round keeps its reconciliation row and is listed under `## Pre-existing Risks` instead of being carried - it takes no Next Steps entry and does not count as open. A row this round did not re-derive never moves there, whatever groups its heading carries. `review-prior-findings-reconcile` parses only that section, so a row kept out of it is invisible to round 3.

### Step 10 - Report

**Assessment** follows the open-label set: `Request Changes` when any `[Must]` is open - this round's published findings and round 2+ `Still open` / `Needs re-check` reconciliation rows count alike - a finding in both once, a row Step 9.5 listed under `## Pre-existing Risks` not at all; `Discuss` when no `[Must]` is open and one named `[Recommend]` becomes `[Must]` or is withdrawn depending on a fact only the author or the requirement's owner holds - the Assessment line states that question and the finding it decides; `Approve` otherwise - `[Recommend]`s alone do not block, and `## Pre-existing Risks` lines never count.

Order findings and Next Steps by label (`[Must]` first), not by scope; at one label, carryovers first (Step 9.5), then `[Implement]`, then `[Delegate]`.

**Key Takeaways** are 2-4 bullets naming what the assembled set says about the change as a whole - a pattern across findings, a systemic risk, or a structural cause. Never a restatement of individual findings.

Use skill: `review-report-writer` with `report_type: review` and these checkpoint fields:

- `report_body` (the assembled report), `branch` (Step 3), `base_ref` and `head_ref` as the handle emitted them, plus `base_sha = current_base_sha`, `head_sha = current_head_sha`
- `mode: full` (the writer's only accepted value), `round` (from Step 3.5), `prior_head_sha = prior_checkpoint.head_sha` (omit on round 1), `pr_url` when the request carried a PR/MR URL, else copied from `prior_checkpoint.pr_url` (omitted when neither)
- `scope` (resolved in Step 4; frontmatter uses the writer's grammar: `Core` -> `core-only`, `+Sec` -> `+sec`, `+Perf` -> `+perf`, `+Obs` -> `+obs`, `+Rel` -> `+rel`, a flagged subset -> its flags space-joined in the order `+perf +sec +obs +rel`, `Full` or all four flags -> `full`), `depth` (resolved/auto-promoted), `stack = ruby-rails` (this plugin's fixed identifier - `stack-detect` emits none)

Emit the report body in chat, then the writer's confirmation line.

## Feedback Labels

Every finding carries exactly one label: `[Must]` (do not merge until this is fixed) or `[Recommend]` (fix, or push back with reasoning - cannot be silently acked). No other label is written; what earns neither is not written down. `complexity-review`'s rows carry `[Recommend]` at every severity, except a row whose `Error-handling complexity` Signal group is a broad catch that swallows errors on a request path, which takes `[Must]`; `rails-overengineering-review`'s own `[Must]` / `[Recommend]` stands (its Rules' escalation list); `backend-api-guidelines` findings take the Step 5 gate's tiers; `architecture-guardrail`'s own `[Must]` / `[Recommend]` stands; an `ops-backward-compatibility` breaking change with `Compatible: No` or `No (unverified)` is `[Must]`, except an internal API break, which takes the Step 5 gate's `[Recommend]`. A finding this workflow raises directly takes `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Where `review-finding-verify` publishes a different `Label`, the published label governs - in Next Steps and Assessment too.

## Output Format

The fence below delimits the template for display only - it is not part of the report. Emit `report_body` as raw Markdown so headings, tables, and lists render; never wrap the whole report in a code fence.

```markdown
## Summary

- **Assessment:** Approve | Request Changes | Discuss - <open [Must] count, and on Discuss the one question and the finding it decides>
- **Risk Level:** Low | Medium | High | Critical
- **Blast Radius:** Narrow | Moderate | Wide | Critical   {the atomic's line as emitted - parenthetical or two-state form included}
- **Stack Detected:** Ruby <version> / Rails <version>
- **Scope:** Core | +Sec | +Perf | +Obs | +Rel | Full   {a flagged subset lists its flags, `+Perf +Sec +Rel`; plus the Step 4 annotation when one applies}
- **Depth:** standard | deep   {append `auto-promoted from standard; Blast Radius: <level>` if applicable}
- **Round:** <N>   {round 2+ only}
- **Findings verified:** <N> confirmed, <M> reattributed, <U> unverified, <K> dropped{ (<F> false positive, <R> resolved by diff)}
- **Requirement Source:** <`review-change-intent`'s line value as emitted: each source with its authority, two joined by ` + `>   {this line and the next together, or both omitted when Step 3.7 resolved no source}
- **Requirement Fit:** <n> met, <n> partial, <n> unmet, <n> deferred, <n> untraceable
- **Notes:** <every note line mandated by Depth and Scope, Steps 2/3.5/3.5c/3.5d/4/9 - declared-vs-code divergence, narrowing, expansion, carried lenses, short-circuit, incomplete or inline scopes, lenses not run, lens atomics not loaded - and every entry of the handle's `notes` (base fallback, approval gate, tag collision, pr-ref base reminder, legacy checkpoint)>   {omit when none}

## Change Brief

**Requested:** <what the change was asked to do, citing the source; the brief's own `(inferred from ...)` marker when no source resolved>

**Delivered:** <the mechanism implemented and where>

**Author decisions:** <the Change Brief's line, verbatim (Step 3.7): one bullet per choice the request did not imply and that is not unrequested scope, with its consequence; `None observed` when nothing remains>

**Watch points:** <what to confirm by hand before reading findings; `None` when there are none>

## Requirement Traceability   {omit when Step 3.7 resolved no source}

| Criterion | Status | Implementation | Proof |
| --------- | ------ | -------------- | ----- |
| <id or quoted outcome> | Met \| Partial \| Unmet \| Deferred \| Untraceable | <file:line, `file:line (pre-existing)`, or `-`> | <file:line or verification note, optionally `(pre-existing)`, or `-`> |

## Prior Round Reconciliation   {round 2+ only}

| Round <N-1> Finding | file:line | Status | Notes |
| ------------------- | --------- | ------ | ----- |
| ...                 | ...       | ...    | ...   |

<the reconcile skill's note lines, when it emitted any>

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

## Pre-existing Risks   {when verify ruled at least one row plain `Pre-existing` - Step 9.4}

Not introduced or made newly reachable by this change; context only, not part of the Assessment.

- file:line - <the defect in one clause> - <the fix in one clause> raised by: <sources, only when two or more>

## Architecture Notes
- Drift detected - one line per `architecture-guardrail` violation's `Drift:`

## Maintainability Notes
- `rails-overengineering-review`'s per-category `Considered, not flagged` lines (Step 7)

## Key Takeaways
- 2-4 bullets on systemic impact

## Next Steps

1. **[Implement]** [Must] file:line - one-line action
2. **[Implement]** [Recommend] OldFile.rb:88 - N+1 in listAll (open since round 1)
3. **[Delegate]** [Recommend] [+Sec] - run `/task-rails-review-security` (suppressed signal: <signal>)
4. **[Delegate]** [Recommend] [scope: platform] - one-line action for a fix leaving the PR's scope

## Failure-Mode and Blast-Radius Map   {reliability's, at deep, verbatim - Step 9.3}
```

_Omit empty sections. Omit Next Steps only when there are no High-Impact findings, no carryovers, and no suppressed-signal delegates._

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Steps 2-3: stack, diff resolved (or accepted from parent); `review-precondition-check` ran with `report_type: review` (or handle received); `branch` = `head_short_name`, current_head_sha, and current_base_sha fixed before the diff/log were read once
- [ ] Step 3.5 - round decided (1 / prior + 1 / no-op); auto-fetch attempted only when a valid prior checkpoint exists, `head_is_remote` is false, and the upstream is not `base_ref`; the full `<base_ref>...<head_ref>` range analyzed regardless of round; lenses carried only when Step 3.5d's every condition held, noted in Summary; no-op path exits without writing the report
- [ ] Step 3.7 - `review-change-intent` ran on the cumulative diff; Change Brief carried into the report; requirement lines in Summary, or all three requirement outputs omitted when no source resolved; its findings consumed into the set, section header not rendered
- [ ] Step 4: subagent loaded behavioral-principles, or the whole Rules section and the disclosure block inlined in the spawning prompt; Risk and Blast Radius stated before findings, atomic blocks not emitted; depth auto-promoted on Wide/Critical; scope resolved - the user's flags exactly, or signals when unflagged - with its Summary annotation; a `[Delegate]` Next Step per signal outside the resolved scope; lenses spawned here, before Step 5
- [ ] Step 5: touched-area atomics loaded; Rails correctness only - security idioms deferred to the security subagent or the single most severe flagged for it; test-coverage gap filed as a named finding; `rails-migration-safety` and `ops-backward-compatibility` applied on a `db/migrate/` change; API contract checks ran when the diff carried a contract-change signal
- [ ] Step 6: architecture / layering / Zeitwerk / multi-tenant / multi-DB applied via `architecture-guardrail` (or skipped via low-risk short-circuit)
- [ ] Step 7: complexity + overengineering reviews run (or skipped via low-risk short-circuit)
- [ ] Step 8: maintainability checks applied (or skipped via low-risk short-circuit)
- [ ] Step 9: non-Core subagents ran in parallel with core Steps 5-8 on pre-resolved artifacts, the final depth and the Change Brief (or inline in sequence, noted; or carried per Step 3.5d); a lens with no surface in the diff not run, noted; every lens returned before Step 9.3, its `Loaded:` line checked; failed scopes noted
- [ ] Step 9.3 - lens findings projected to `### [Label] file:line`; same-claim findings merged with strongest label and `raised by:`; distinct claims kept apart; core / Step 3.7 / atomic findings drafted in the same shape; lens `out of lens` lines drafted as findings; reliability's Map preserved; Notes sections filled from their named sources
- [ ] Step 9.4 - review-finding-verify ran on the assembled set; gem- and framework-behaviour claims settled via `rails-gem-source-evidence`; Dropped rows excluded; plain `Pre-existing` rows listed under Pre-existing Risks, not High-Impact Findings; verdict labels and annotation groups applied; tally in Summary in the atomic's Summary form
- [ ] Step 9.5 - on round 2+, review-prior-findings-reconcile ran with `head_sha` and `base_ref`; reconciliation table inserted; Still open / Needs re-check rows folded into Next Steps with (open since round <N>) suffix at the right label; prior rows verify ruled plain `Pre-existing` this round listed under Pre-existing Risks, not carried; legacy labels mapped
- [ ] Step 10: Assessment derived from the open-label set, `Discuss` only with its one deciding question stated; one Next Steps entry per published finding; findings and Next Steps ordered by label; 2-4 systemic Key Takeaways, none restating a finding; report written via `review-report-writer` with every required input (report_type, report_body, branch, base_ref, head_ref, base_sha, head_sha, mode, round, prior_head_sha when round > 1, scope, depth, stack, pr_url when known)
- [ ] Every Must cites system risk; every finding has label + `file:line` + actionable Rails fix

## Avoid

- State-changing git from this workflow (checkout/merge/pull/rebase). The one allowed exception is Step 3.5a's `git fetch <remote> <upstream branch>`, and only when a valid prior checkpoint exists, `head_is_remote` is false, and the upstream is not `base_ref`.
- Reconciling against prior Architecture/Maintainability notes - only `## High-Impact Findings` rows count (regardless of whether they used legacy `[Suggestion]` or current `[Recommend]`).
- Duplicating perf / security / observability / reliability depth here - dedicated subagents own it
- Reviewing without reading the full diff and log first
- Writing a `Findings verified:` tally, a `Requirement Fit` line or a reconciliation table that its skill did not produce in this run
- Ending the turn or assembling the finding set while a spawned lens is still running
- Running the test suite, booting the app or starting containers when the invocation did not ask for it
- Applying generic backend conventions where a Rails idiom exists
- Nitpicking style
