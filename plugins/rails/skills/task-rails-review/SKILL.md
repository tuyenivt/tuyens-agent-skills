---
name: task-rails-review
description: Rails-specific staff-level code review umbrella - Phases A-E (risk, correctness, architecture, AI quality, maintainability) with Rails idioms (Zeitwerk, callback abuse, fat controllers, AR-in-API, service-object boundaries, scope sprawl). Spawns Rails-specific perf/security/observability subagents for extra scopes. Stack-specific override of task-code-review for Ruby/Rails. Runs standalone with full PR/branch resolution.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.
>
> **Spec-aware mode:** If the user passed `--spec <slug>` or `.specs/<slug>/spec.md` exists for the diff under review, load `Use skill: spec-aware-preamble` (from the `spec` plugin) immediately after `behavioral-principles`. When a spec is loaded, cross-check the diff against `spec.md` and `plan.md`: every changed surface must trace to an acceptance criterion, NFR, or task; flag changes that touch out-of-scope items as **blockers**, not suggestions; flag missing coverage of in-scope acceptance criteria as gaps. Never edit `spec.md`, `plan.md`, or `tasks.md` from this workflow.

# Rails Code Review

## Purpose

Rails-aware staff-level code review umbrella. Replaces the generic Phase A-E flow with Rails-specific correctness, architecture, AI-quality, and maintainability checks (Zeitwerk hygiene, callback abuse, fat controllers, ActiveRecord exposure in API, service-object boundaries, scope sprawl). Coordinates Rails-specific perf / security / observability subagents in parallel for extra scopes.

This workflow is the stack-specific delegate of `task-code-review` for Ruby/Rails. The core workflow's contract (depth levels, scope auto-escalation, low-risk short-circuit, output format) is preserved so callers see a stable shape. **Runs standalone** with full PR/branch resolution - the core dispatcher is optional, not required.

## When to Use

- Reviewing a Rails PR before merge
- Post-AI-generation quality gate on a Rails change set
- Architecture drift detection in a Rails codebase
- Pre-merge risk assessment on a Rails branch

**Not for:**

- Pre-implementation feature design (use `task-rails-new`)
- Active production incident triage (use `/task-oncall-start`)
- Single-error debugging (use `task-rails-debug`)
- Architecture/design review of a new Rails system (use `task-design-architecture`)
- Single-scope reviews when only one concern matters - delegate directly to `task-rails-review-perf`, `task-rails-review-security`, or `task-rails-review-observability`

## Depth Levels

Mirrors `task-code-review`:

| Depth      | When to Use                                                               | What Runs                                                    |
| ---------- | ------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `quick`    | "Is this safe to merge?" - fast risk snapshot for time-constrained review | Risk snapshot + top 3 findings only (Phases A and B summary) |
| `standard` | Default - full Rails staff-level review                                   | Phases A-E                                                   |
| `deep`     | Architectural PRs, post-incident change review, or Principal sign-off     | Phases A-E + historical pattern matching + cross-PR context  |

Default: `standard`.

**Auto-promote to `deep`:** After Phase A computes blast radius, if `Blast Radius` is `Wide` or `Critical` and the user did not explicitly pass `quick`, promote depth from `standard` to `deep` automatically. Surface this in Summary as `Depth auto-promoted: standard -> deep (Blast Radius: <level>)`.

## Scope

| Scope           | What runs                                                                  |
| --------------- | -------------------------------------------------------------------------- |
| Core            | Phases A-E only (Rails-flavored)                                           |
| + Perf          | Core + parallel subagent: `task-rails-review-perf`                         |
| + Security      | Core + parallel subagent: `task-rails-review-security`                     |
| + Observability | Core + parallel subagent: `task-rails-review-observability`                |
| Full            | Core + Performance + Security + Observability (3 parallel Rails subagents) |

Default: **Core with auto-escalation** (same signal rules as `task-code-review`). Pass `core-only` to suppress.

**Scope auto-escalation signals (Rails-tuned):**

- File uploads (Active Storage, Shrine, CarrierWave), `devise` config, Pundit/CanCanCan policy changes, `params.permit` lists, raw SQL or `find_by_sql`, secrets/credentials, Sidekiq jobs with user input → auto-add **+Security**
- New `db/migrate/`, `add_index`, new ActiveRecord scopes, new `.where` / `.order` patterns, new endpoints with payloads, loops over collections that hit DB or HTTP → auto-add **+Perf**
- New service object, new external dependency, new `ActiveJob`/`Sidekiq` job class, change to `lograge` / `semantic_logger` / `Rails.logger` config, new `ActiveSupport::Notifications` instrument calls → auto-add **+Observability**
- Two or more signal categories present → promote to **Full**

## Invocation

The slash command accepts an optional argument identifying the diff to review:

| Invocation                    | Meaning                                                                                                                                                                               |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/task-rails-review`          | Review current branch vs its base - fails fast if on a trunk branch (`main`/`master`/`develop`); commit or switch to a feature branch first                                           |
| `/task-rails-review <branch>` | Review `<branch>` vs its base (3-dot diff) - cross-review a teammate's branch checked out locally, or self-review a named branch from any session                                     |
| `/task-rails-review pr-<N>`   | Review a PR head fetched into local branch `pr-<N>` - run `git fetch origin pull/<N>/head:pr-<N>` first (user runs it; see `review-precondition-check` for GitLab/Bitbucket variants) |

**No checkout required.** Stay on your current branch; the workflow reads git history via ref-qualified diffs and never modifies your working tree.

**Explicit base override.** When the PR was opened against a non-trunk base branch, pass `--base <branch>` so the diff is computed against the true base.

Examples:

- `/task-rails-review pr-123 --base phase-01` - PR opened against feature branch `phase-01`
- `/task-rails-review feature/x --base develop` - branch off `develop` rather than `main`

Scope and depth flags compose: `/task-rails-review pr-50273 --base phase-01 +security deep`.

## Workflow

### Step 1 - Confirm Stack

Use skill: `stack-detect` to confirm Ruby / Rails. If invoked as a delegate of `task-code-review` (parent already detected Rails), accept the pre-detected stack and skip re-detection. If the detected stack is not Rails, stop and tell the user to invoke `/task-code-review` instead.

### Step 2 - Resolve the Diff Under Review

Use skill: `review-precondition-check` with the user's argument (or no argument to default to the current branch). Forward `--base <branch>` if the user passed it.

If the precondition check stops with a fail-fast message (dirty tree, trunk branch, missing PR ref, or denied head-vs-current confirmation), surface the message verbatim and stop. Do not run any state-changing git command from this workflow.

Once approved, read the diff and commit log directly using the returned refs:

- Diff: `git diff <base_ref>...<head_ref>`
- Files changed: `git diff --name-status <base_ref>...<head_ref>`
- Commit log: `git log --oneline <base_ref>..<head_ref>`

All subsequent phases operate on this read-once diff and log; do not re-derive them.

**Skip this entire step** when invoked as a subagent of `task-code-review` and the parent passed the precondition handle plus pre-read diff and commit log. Reuse the parent's artifacts.

### Phase A - PR Risk Snapshot (run first)

- Use skill: `review-pr-risk` to evaluate cross-cutting risk signals
- Use skill: `review-blast-radius` to assess failure propagation scope
- Output risk level and blast radius before proceeding to findings

**Low-risk short-circuit:** If Phase A yields Risk Level: Low and Blast Radius: Narrow, **and** the change does not touch architecture-relevant files (auth, middleware, API contracts, shared concerns, `app/services/`, `lib/`), skip Phases C-D and produce a streamlined output with Phase B findings only.

### Phase B - Rails Correctness and Safety

Logical correctness, error handling completeness, edge cases affecting state integrity, backward compatibility, transaction boundary correctness - through a Rails lens.

**Test coverage finding:** If the PR adds or modifies logic without corresponding RSpec coverage, raise this as an explicit finding. At minimum a [Suggestion]; escalate to [High] if the change is in a critical path (Devise/JWT auth, Pundit policies, payment, data integrity, Sidekiq jobs that mutate data). Do not bury this in Key Takeaways.

**Rails-specific correctness checks:**

- [ ] **Transaction boundaries**: writes wrapped in `ActiveRecord::Base.transaction`; no HTTP calls or `.perform_async` _inside_ the transaction (use `after_commit` or `transaction.after_commit { ... }`)
- [ ] **Callback discipline**: `after_create` / `after_save` callbacks not used for cross-aggregate orchestration (extract to a service object); no `after_*` callback enqueuing Sidekiq jobs without `after_commit`
- [ ] **`save` vs `save!`**: `save!` used inside transactions and in service objects (so failures surface); `save` only when caller checks the return value
- [ ] **Strong params**: every `create` / `update` action uses `params.require(:model).permit(...)`; no `params.permit!` or `params.to_unsafe_h` in production paths
- [ ] **N+1 query patterns**: any `.each` over an association in controllers/views/serializers preloads via `includes` / `preload` / `eager_load` (delegate to `task-rails-review-perf` for depth)
- [ ] **Unbounded queries**: no `Model.all` followed by `.each`; use `find_each` or pagination; serializer not iterating an unbounded collection
- [ ] **AR entities exposed in API**: controllers do not `render json: @model` directly; responses go through a serializer (ActiveModel::Serializer, JSONAPI::Serializer, Blueprinter, Jbuilder) - models do not leak internal fields like `created_at_db_default` or password digests
- [ ] **Authorization on every action**: every controller action calls `authorize @resource` (Pundit) or `load_and_authorize_resource` (CanCanCan), or has explicit `skip_authorization` with rationale (delegate to `task-rails-review-security` for depth)
- [ ] **Error handling**: no blanket `rescue StandardError` or `rescue => e`; rescue specific exception classes; `rescue_from` in `ApplicationController` handles `ActiveRecord::RecordNotFound`, `Pundit::NotAuthorizedError`, etc. with appropriate status codes
- [ ] **Backward compatibility on migrations**: see Phase C migration checks
- [ ] **Bulk operations**: partial-failure handling defined; idempotency for retryable bulk; transaction boundaries appropriate (not one giant transaction wrapping I/O, not one per row)

**Migration PRs (any change in `db/migrate/`):**

- [ ] Two-phase deploys for column rename / drop (add new → backfill → cut over → remove old)
- [ ] `NOT NULL` on existing columns added via two-step (add nullable → backfill → set NOT NULL with `validate_check_constraint` or strong_migrations helper)
- [ ] `add_index` on large tables uses `algorithm: :concurrently` and `disable_ddl_transaction!`
- [ ] Foreign keys added with `validate: false`, then validated separately
- [ ] Data migrations are not in `db/migrate/` (use a Rake task or one-off script)
- [ ] Rollback path documented or verified
- Use skill: `ops-backward-compatibility` to assess client/session/in-flight-request impact

**Concurrency safety:**

- [ ] Class-level mutable state (`@@variable`, `class << self` with state) avoided
- [ ] Thread-unsafe libraries not used in shared code (e.g., `Time.zone=` mutating global state)
- [ ] `with_advisory_lock` or row-level locking used for race-prone updates (counters, balance changes, state transitions)

Use skill: `rails-activerecord-patterns` for canonical AR correctness patterns.
Use skill: `rails-service-objects` for service-object boundaries when this PR introduces or extends a service.
Use skill: `rails-sidekiq-patterns` for any new or modified job.

### Phase C - Rails Architecture Guardrails

Use skill: `architecture-guardrail` to detect layer violations, new coupling, circular dependency risk, bypassing abstractions, boundary erosion.

**Rails-specific architecture checks:**

- [ ] **Layering**: presentation (controllers, mailers, views) → service / domain → data (models). No business logic in controllers; no `Net::HTTP` calls in models; no view rendering inside services
- [ ] **Service-object discipline**: any controller action with > 5 lines of orchestration extracted to a service object; service objects expose `.call` returning a `Result` (or `Success` / `Failure` Dry-Monads); no mixing of `.call` and `.execute` / `.run` interfaces in the same codebase
- [ ] **Concern soup**: `app/models/concerns/*.rb` and `app/controllers/concerns/*.rb` files are _role-based_ (e.g., `Sluggable`, `SoftDeletable`), not dumping grounds for unrelated methods
- [ ] **Zeitwerk hygiene**: file paths match constant names exactly (`app/services/order_fulfillment.rb` → `OrderFulfillment`); no `require_relative` inside `app/`; no `eager_load!` workarounds for autoload failures
- [ ] **Engine / namespace boundaries**: if the app uses Rails engines or namespaced models (e.g., `Billing::Invoice`), cross-namespace direct AR access is via service objects, not direct `Billing::Invoice.find` calls in unrelated namespaces
- [ ] **Multi-tenant isolation**: tenant scoping enforced at the model layer (`acts_as_tenant`, `default_scope`, or query objects), not at the controller layer alone
- [ ] **Database boundaries**: in apps with multiple databases (`connects_to`), models declare their connection; cross-database joins flagged

**Multi-service PRs (when change spans 2+ services or this Rails app + a separate service):**

- API contract compatibility checked
- Deployment order documented or independent
- Use skill: `ops-backward-compatibility` for any changed inter-service contract

### Phase D - AI-Generated Code Quality Control

Use skill: `complexity-review` to detect verbosity, over-engineering, and simplification opportunities.

**Rails-specific AI smells:**

- [ ] **Pattern inflation**: a service object created where a 3-line controller method would do; a `Result` object returned where `true` / `false` is sufficient; a class created where a module method would suffice
- [ ] **Over-abstraction**: `BaseService` / `ApplicationService` parent class with `Template Method` pattern when the codebase has 2 services; premature inheritance hierarchies; "factory" classes for objects that have one constructor path
- [ ] **Speculative configurability**: methods accepting `**options` hashes with documented but unused keys; `config.x.feature_flag` for features that have no off path
- [ ] **Redundant mapping layers**: `User → UserDecorator → UserPresenter → UserSerializer` when one serializer would suffice
- [ ] **Test verbosity**: setup blocks > 30 lines for a single example; `let!` chains that could be a single FactoryBot trait; matchers reimplemented when shoulda-matchers exists
- [ ] **Comment cruft**: comments restating method names; `# end of method foo` markers; YARD docs on private helper methods

### Phase E - Rails Maintainability and Clarity

Naming that obscures intent, mixed responsibilities, large unreviewable chunks, hardcoded values that should be config or constants.

**Rails-specific maintainability checks:**

- [ ] **Naming conventions**: classes are nouns (`OrderFulfillment`), service objects describe an action (`OrderFulfiller`, `FulfillOrder`); scopes are queries (`active`, `completed_after`); no abbreviations not already in the project glossary
- [ ] **Magic numbers / strings**: extracted to constants (`STATUSES`, `LIMITS`) or `Rails.application.config.x.feature.foo`
- [ ] **Hardcoded URLs / credentials**: in `Rails.application.credentials` or environment-specific config, never inline
- [ ] **Method length**: methods > 15 lines reviewed for extraction; methods > 30 lines flagged unless they are a service object's `.call` orchestrating clearly named steps
- [ ] **Duplicated query logic**: same `.where(...).order(...)` pattern in 3+ places extracted to a scope or query object
- [ ] **Logging hygiene**: `Rails.logger.info` / `.warn` / `.error` used at the right level; structured logging fields (`tags: [...]`) when `lograge` or `semantic_logger` is configured (delegate to `task-rails-review-observability` for depth)

Use skill: `backend-coding-standards` for cross-language naming and structure conventions.
Use skill: `ops-observability` for cross-cutting logging/metrics presence (the `task-rails-review-observability` subagent owns the depth review).

### Step 3 - Delegate Extra Scopes in Parallel (if scope includes)

If scope is **Core only**, skip this step.

For any selected extra scope, spawn an independent subagent **in parallel** with the main thread (which continues running Phases A-E for Core). Subagents run concurrently with each other and with Core, not sequentially.

| Scope                | Subagents spawned                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Core + Perf          | 1 subagent running `task-rails-review-perf`                                                                               |
| Core + Security      | 1 subagent running `task-rails-review-security`                                                                           |
| Core + Observability | 1 subagent running `task-rails-review-observability`                                                                      |
| Full                 | 3 subagents running `task-rails-review-perf`, `task-rails-review-security`, `task-rails-review-observability` in parallel |

**Subagent prompt contract.** Each subagent prompt must include:

- The resolved review target from Step 2 (`base_ref`, `head_ref`) plus the already-read diff and commit log, so the subagent does not re-run `review-precondition-check` and does not re-issue `git diff`
- The depth level (`quick` | `standard` | `deep`)
- The pre-confirmed stack (Ruby / Rails) so the subagent skips its own `stack-detect`
- Instruction to return findings using its own skill's Output Format

**Failure isolation.** If a subagent fails or times out, continue with the remaining results. Note the missing scope in the synthesized output rather than blocking the whole review.

### Step 4 - Synthesize (only if Step 3 ran)

Merge subagent findings into the single Output Format below. Do not append raw subagent reports.

- **Deduplicate cross-cutting findings.** The same issue may surface in multiple scopes (e.g., a synchronous external call in a hot path can be flagged by both Core/Phase B and Perf). Keep one entry, citing all scopes that raised it.
- **Severity wins.** When the same finding has different labels across scopes, use the highest severity (`Blocker` > `High` > `Suggestion` > `Question`).
- **Preserve `file:line` citations** from the originating subagent.
- **Order findings by severity, not by scope.** Produce one merged Findings list.
- **Note missing scopes.** If any subagent failed, add `Scope incomplete: <scope> review did not complete` under Summary.
- **Merge Next Steps.** Combine Core Next Steps with each subagent's Next Steps into one prioritized list under `## Next Steps`. Preserve `[Implement]` / `[Delegate]` tags; deduplicate items mapping to the same fix; re-sort by severity (Blocker/Critical > High > Medium/Suggestion > Low).

## Feedback Labels

| Label        | Meaning                                     | Required |
| ------------ | ------------------------------------------- | -------- |
| [Blocker]    | Must fix before merge - correctness or risk | Yes      |
| [High]       | Should fix - significant impact or smell    | Strong   |
| [Suggestion] | Would improve - non-blocking                | No       |
| [Question]   | Need clarity from author                    | Clarify  |

No `[Nitpick]` or `[Praise]` labels.

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(if auto-escalated, append: `auto-escalated from Core; signals: <list>`)_
**Depth:** quick | standard | deep _(if auto-promoted, append: `auto-promoted from standard; Blast Radius: <level>`)_

## High-Impact Findings

### [Blocker] file:line

- Issue: [what is wrong - name the Rails idiom: callback abuse, fat controller, AR-in-API, missing Pundit authorize, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is a system-level concern, not just a local bug]
- Fix: [concrete Rails change with code example]

### [High] file:line

- Issue:
- Impact:
- Fix:

### [Suggestion] file:line

- Improvement:

## Architecture Notes

- Boundary impact:
- Coupling change:
- Drift detected:

## Maintainability Notes

- Over-engineering detected:
- Simplification opportunities:

## Key Takeaways

- 2-4 concise bullets summarizing systemic impact and what to address before merge.

## Next Steps

Prioritized action list. Each item tagged `[Implement]` or `[Delegate]`. Order: Blockers > High > Suggestions.

1. **[Implement]** [Blocker] file:line - [one-line action, e.g., "Move `OrderMailer.deliver_later` outside the transaction in OrdersController#create"]
2. **[Delegate]** [High] [scope: cross-service] - [one-line action]
3. **[Implement]** [Suggestion] file:line - [one-line action]

_Omit this section if there are no actionable findings._
```

**Omit empty sections.** If there are no Blockers, do not include a Blocker heading.

## Rules

- Review the whole change as a system impact, not file-by-file in isolation
- Lead with risk assessment before line-level findings
- Apply Rails conventions, not generic backend conventions
- Provide actionable feedback with Rails code examples
- Never comment on trivial formatting or style where no project standard exists
- Default to Core scope; auto-escalate on signals; honor `core-only` flag
- Delegate perf / security / observability depth to the appropriate Rails subagent rather than duplicating the check here

## Self-Check

- [ ] Stack confirmed as Rails (or accepted from parent dispatcher)
- [ ] `review-precondition-check` ran (or its handle was received from a parent dispatcher); `base_ref` / `base_source` / `head_ref` / `current_branch` / `head_matches_current` captured. If user passed `--base`, `base_source: explicit-override` recorded
- [ ] Diff and commit log were read once via `git diff <base>...<head>` and `git log <base>..<head>` and reused by all phases (and shared with subagents) - no re-issuing of git commands mid-review
- [ ] For `pr-ref` mode, the user-run fetch command was surfaced and the local ref existed before review continued
- [ ] When `head_matches_current` was false, explicit user approval was obtained before any review phase ran
- [ ] Scope auto-escalation evaluated after Step 2; promotion (or `core-only` suppression) recorded in Summary
- [ ] Depth auto-promoted to `deep` when Blast Radius is Wide/Critical and user did not pass `quick`; promotion recorded in Summary
- [ ] Risk level and blast radius stated before any line-level findings
- [ ] Phase B Rails correctness checks applied: callbacks, transaction boundaries, strong params, AR-in-API, Pundit on every action, error rescue specificity
- [ ] Phase C Rails architecture checks applied: layering, service-object discipline, Zeitwerk, multi-tenant isolation, concern soup
- [ ] Phase D AI-quality checks applied: pattern inflation, over-abstraction, speculative configurability, test verbosity
- [ ] Phase E Rails maintainability checks applied: naming, magic numbers, method length, duplicated query logic
- [ ] Missing tests raised as an explicit named finding (not buried in Key Takeaways)
- [ ] Every Blocker states a system risk, not just a code observation
- [ ] Every finding has a label, location (file:line), and actionable Rails fix
- [ ] If `--spec` was passed, every finding traces to an AC/NFR/task or is flagged as out-of-scope blocker
- [ ] For non-Core scopes, Rails-specific subagents (`task-rails-review-perf`, `-security`, `-observability`) ran in parallel and received the pre-resolved diff/log handle
- [ ] Subagent findings merged into the single Output Format with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Any failed/missing subagent scope noted under Summary as `Scope incomplete: <scope>`
- [ ] Next Steps section produced with each item tagged `[Implement]` or `[Delegate]` and ordered Blocker > High > Suggestion (omitted only when no actionable findings exist)

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command from this workflow - the user must run these so they can protect uncommitted work
- Reviewing without reading the full diff and commit log first
- Applying generic backend conventions when a Rails idiom exists (say "extract to a service object", not "extract to a helper class")
- Nitpicking style where no project standard exists; no `[Nitpick]` or `[Praise]` labels
- Providing vague feedback without a concrete Rails fix ("this could be better")
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running perf / security / observability sub-workflows when user passed `core-only`
- Treating auto-escalation signals as advisory; the default is to promote and let the user opt out via `core-only`
- Duplicating perf / security / observability depth checks here when the dedicated Rails subagent owns them - flag and delegate
- Running multiple extra scopes sequentially when they could spawn in parallel
- Appending raw subagent reports section-by-section instead of merging into one severity-ordered Findings list
