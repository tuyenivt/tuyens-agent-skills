---
name: task-rails-review
description: Rails code review: Zeitwerk, callbacks, fat controllers, AR-in-API, services, scope sprawl; spawns perf/security/observability subagents.
agent: rails-tech-lead
metadata:
  category: backend
  tags: [ruby, rails, code-review, pull-request, staff-review, multi-scope, workflow]
  type: workflow
user-invocable: true
---

# Rails Code Review

Rails-aware staff-level review umbrella. Runs Phases A-E with Rails-specific correctness, architecture, AI-quality, and maintainability checks. Coordinates Rails perf / security / observability subagents in parallel for extra scopes. Stack-specific delegate of `task-code-review`; runs standalone with full PR/branch resolution.

## When to Use

- Pre-merge Rails PR review, post-AI-generation quality gate, architecture-drift detection

**Not for:** feature design (`task-rails-implement`), incident triage (`/task-oncall-start`), single-error debugging (`task-rails-debug`), new-system design (`task-design-architecture`), or single-scope reviews (delegate directly to `task-rails-review-{perf,security,observability}`).

## Depth and Scope

Depth (`quick` | `standard` | `deep`, default `standard`) and scope (`Core` | `+Perf` | `+Security` | `+Observability` | `Full`) mirror `task-code-review`.

**Auto-promote depth to `deep`** after Phase A when Blast Radius is Wide/Critical and the user did not pass `quick`. Record in Summary.

**Auto-escalate scope (Rails-tuned signals):**

- **+Security**: Active Storage / Shrine / CarrierWave, Devise config, Pundit/CanCanCan policies, `params.permit` changes, raw SQL / `find_by_sql`, secrets, Sidekiq jobs taking user input
- **+Perf**: new `db/migrate/`, `add_index`, new scopes / `.where` / `.order`, new payload endpoints, loops hitting DB or HTTP
- **+Observability**: new service object, external dependency, `ActiveJob`/`Sidekiq` job class, log config changes, new `ActiveSupport::Notifications`
- Two or more signal categories → promote to **Full**

Pass `core-only` to suppress auto-escalation.

## Invocation

| Form | Behavior |
| --- | --- |
| `/task-rails-review` | Current branch vs base; fails fast on trunk |
| `/task-rails-review <branch>` | 3-dot diff vs base |
| `/task-rails-review pr-<N>` | Local ref `pr-<N>` (user fetches first) |

Flags compose: `/task-rails-review pr-50273 --base phase-01 +security deep`. Pass `--base <branch>` when the PR's true base is non-trunk. The workflow never modifies the working tree.

## Workflow

### Step 1 - Load Behavioral Rules

Use skill: `behavioral-principles`. If `--spec <slug>` was passed or `.specs/<slug>/spec.md` exists, also use skill: `spec-aware-preamble`; cross-check the diff against `spec.md` / `plan.md` - out-of-scope changes are blockers, missing AC coverage is a gap, never edit spec artifacts.

### Step 2 - Confirm Stack

Use skill: `stack-detect`. Accept pre-detected stack from a parent dispatcher. If not Rails, redirect to `/task-code-review`.

### Step 3 - Resolve the Diff

Use skill: `review-precondition-check` with the user's argument and any `--base`. Surface fail-fast messages verbatim and stop. On approval, read the diff and log **once**:

- `git diff <base_ref>...<head_ref>`
- `git diff --name-status <base_ref>...<head_ref>`
- `git log --oneline <base_ref>..<head_ref>`

All phases reuse these artifacts. Skip this step entirely when a parent dispatcher passed the precondition handle plus pre-read diff and log.

### Phase A - PR Risk Snapshot

- Use skill: `review-pr-risk`
- Use skill: `review-blast-radius`
- State Risk Level and Blast Radius before any line-level findings

**Low-risk short-circuit:** if Risk: Low and Blast Radius: Narrow **and** the change does not touch auth, middleware, API contracts, shared concerns, `app/services/`, or `lib/`, skip Phases C-D and produce Phase B findings only.

### Phase B - Rails Correctness and Safety

Logical correctness, error handling, state-integrity edge cases, backward compatibility, transaction boundaries - through a Rails lens.

**Test coverage finding (named, not buried in Key Takeaways):** logic added without RSpec coverage is at minimum `[Suggestion]`. Escalate to `[High]` on critical paths: auth (Devise/JWT/custom), authorization (Pundit/CanCanCan, ownership scoping), money/billing, multi-record transactions, state machines, data-mutating Sidekiq jobs, migrations changing column semantics.

**Rails diff-scan checks** (depth lives in the linked atomic skills):

- [ ] **Transaction boundaries**: writes wrapped; no HTTP / `.perform_async` inside - use `after_commit` (see `rails-activerecord-patterns`, `rails-sidekiq-patterns`)
- [ ] **Callback discipline**: cross-aggregate work and Sidekiq dispatch via `after_commit`, not `after_save`/`after_create`
- [ ] **`save!` in services / transactions** so failures surface
- [ ] **Strong params** with explicit `permit(...)`; no `permit!` / `to_unsafe_h` (see `rails-security-patterns`)
- [ ] **N+1 / unbounded queries**: preload in controllers and serializers; `find_each` over `.all.each`
- [ ] **AR-in-API**: no `render json: @model` - serializer required. Flag sensitive fields in serializer `attributes` (`password_digest`, `*_secret`, `api_key`, `is_admin`, internal/audit columns) per `rails-security-patterns`. Bare `render json: @model` is `[High]`.
- [ ] **Idempotency-Key on unsafe writes**: HTTP-layer `Idempotency-Key` (client-server retries) is distinct from Sidekiq `unique_for:` (worker-side). Missing on new `payments`, `orders#create`, `refunds`, `subscriptions#create`, or inbound webhooks is `[High]`. See `backend-idempotency`.
- [ ] **Authorization on every action**: `authorize @resource` / `load_and_authorize_resource`; explicit `skip_authorization` with rationale
- [ ] **Error handling**: no blanket `rescue StandardError`; `rescue_from` in `ApplicationController` for `RecordNotFound`, `Pundit::NotAuthorizedError`
- [ ] **Bulk operations**: partial-failure path defined; idempotent retry; transaction size between "wraps I/O" and "one per row"

**Migration PRs** (any change in `db/migrate/`):

- [ ] Two-phase column rename/drop (add → backfill → cut over → remove)
- [ ] `NOT NULL` on existing columns via two-step (nullable → backfill → set NOT NULL)
- [ ] `add_index` on large tables uses `algorithm: :concurrently` + `disable_ddl_transaction!`
- [ ] FKs added with `validate: false`, then validated separately
- [ ] Data migrations live in Rake tasks, not `db/migrate/`
- [ ] Rollback path documented
- Use skill: `ops-backward-compatibility`

**Concurrency safety:**

- [ ] No class-level mutable state (`@@var`, `class << self` with state); no thread-unsafe globals (`Time.zone=`)
- [ ] `with_advisory_lock` or row-level locking for race-prone updates (counters, balances, state transitions)

Atomic skills: `rails-activerecord-patterns`, `rails-service-objects` (only if PR adds/extends a service), `rails-sidekiq-patterns` (only if PR adds/modifies a job).

### Phase C - Rails Architecture Guardrails

Use skill: `architecture-guardrail`.

- [ ] **Layering**: presentation → service/domain → data. No business logic in controllers; no `Net::HTTP` in models; no view rendering in services
- [ ] **Service-object discipline**: controller actions > 5 orchestration lines extracted; services expose `.call` returning `Result` (or Dry-Monads); no mixed `.call` / `.execute` / `.run` interfaces
- [ ] **Concern hygiene**: `app/**/concerns/*.rb` are role-based (`Sluggable`, `SoftDeletable`), not grab-bags
- [ ] **Zeitwerk**: file paths match constant names; no `require_relative` inside `app/`; no `eager_load!` workarounds
- [ ] **Namespace / engine boundaries**: cross-namespace access via service objects, not direct `Billing::Invoice.find` calls
- [ ] **Multi-tenant isolation**: enforced at the model layer (`acts_as_tenant`, `default_scope`, query objects), not only in controllers
- [ ] **Multi-database**: `connects_to` declared on models; cross-DB joins flagged

For multi-service PRs, check API contract compatibility and deployment order; use skill: `ops-backward-compatibility`.

### Phase D - AI-Generated Code Quality

Use skill: `complexity-review` (covers cyclomatic/cognitive complexity and redundant mapping layers like `User → UserDecorator → UserPresenter → UserSerializer`).
Use skill: `rails-overengineering-review` for: validations duplicating DB constraints, defensive guards on impossible states, services / `Result` / base classes wrapping trivial logic.

Additional Rails AI smell not covered by the above:

- [ ] **Test verbosity**: setup > 30 lines per example; `let!` chains replaceable by a FactoryBot trait; matchers reimplemented when shoulda-matchers exist

### Phase E - Rails Maintainability

- [ ] **Naming**: classes are nouns; services describe an action (`FulfillOrder`); scopes are queries (`active`, `completed_after`); no abbreviations outside the project glossary
- [ ] **Magic numbers / strings**: extracted to constants or `Rails.application.config.x.*`
- [ ] **Credentials / URLs**: `Rails.application.credentials` or env config, never inline
- [ ] **Method length**: > 15 lines reviewed; > 30 lines flagged unless it's a service `.call` orchestrating clearly named steps
- [ ] **Duplicated query logic**: same `.where(...).order(...)` in 3+ places extracted to a scope or query object
- [ ] **Logging hygiene**: correct levels; structured fields when `lograge` / `semantic_logger` is configured

Load conditionally: `backend-coding-standards` when the diff introduces new naming/structure patterns; `ops-observability` when the diff touches logging or metrics (depth is owned by `task-rails-review-observability`).

### Step 4 - Delegate Extra Scopes in Parallel

Skip if scope is Core-only. For each selected scope, spawn an independent subagent **in parallel** with the main thread.

| Scope | Subagents |
| --- | --- |
| +Perf / +Security / +Observability | 1 subagent running the matching `task-rails-review-*` |
| Full | 3 subagents in parallel |

**Subagent prompt contract:**

- Resolved `base_ref` / `head_ref` plus the already-read diff and commit log (no re-running `review-precondition-check` or `git diff`)
- Depth level
- Pre-confirmed stack (so the subagent skips its own `stack-detect`)
- Instruction to return findings using its own skill's Output Format

**Failure isolation:** if a subagent fails or times out, continue with remaining results; note `Scope incomplete: <scope>` under Summary.

### Step 5 - Synthesize

Merge subagent findings into the single Output Format below:

- Deduplicate cross-cutting findings; one entry citing all scopes that raised it
- On differing labels, highest severity wins (`Blocker > High > Suggestion > Question`)
- Preserve `file:line` citations
- Order findings by severity, not by scope
- Merge Next Steps into one prioritized list; preserve `[Implement]` / `[Delegate]` tags

### Step 6 - Write Report

Use skill: `review-report-writer` with `report_type: review`. Print the confirmation line.

## Feedback Labels

| Label | Meaning |
| --- | --- |
| [Blocker] | Must fix before merge - correctness or risk |
| [High] | Should fix - significant impact or smell |
| [Suggestion] | Would improve - non-blocking |
| [Question] | Need clarity from author |

## Output Format

```markdown
## Summary

**Assessment:** Approve | Request Changes | Discuss
**Risk Level:** Low | Medium | High | Critical
**Blast Radius:** Narrow | Moderate | Wide
**Stack Detected:** Ruby <version> / Rails <version>
**Scope:** Core | +Security | +Perf | +Observability | Full _(append `auto-escalated from Core; signals: <list>` if applicable)_
**Depth:** quick | standard | deep _(append `auto-promoted from standard; Blast Radius: <level>` if applicable)_

## Findings

Each entry, ordered Blocker > High > Suggestion > Question:

### [Label] file:line

- Issue: [Rails idiom named: callback abuse, fat controller, AR-in-API, missing authorize, etc.]
- Impact: [user-visible or operational consequence]
- System Risk: [why this is system-level, not just local] _(required for Blocker; optional otherwise)_
- Fix: [concrete Rails change with code]

## Architecture Notes
- Boundary impact / Coupling change / Drift detected

## Maintainability Notes
- Over-engineering detected / Simplification opportunities

## Key Takeaways
- 2-4 bullets on systemic impact

## Next Steps

Prioritized; each item `[Implement]` or `[Delegate]`; order Blocker > High > Suggestion.

1. **[Implement]** [Blocker] file:line - one-line action
2. **[Delegate]** [High] [scope] - one-line action
```

_Omit empty sections. Omit Next Steps entirely if no actionable findings._

## Self-Check

- [ ] `behavioral-principles` loaded first; `spec-aware-preamble` loaded when applicable
- [ ] Stack confirmed (or accepted from parent)
- [ ] `review-precondition-check` ran (or its handle was received); diff and log read once and reused
- [ ] Scope auto-escalation evaluated; depth auto-promoted on Wide/Critical Blast Radius; both recorded in Summary
- [ ] Risk Level and Blast Radius stated before line-level findings
- [ ] Phase B Rails checks applied (callbacks, transactions, strong params, AR-in-API, authorize, error specificity)
- [ ] Phase C architecture checks applied (layering, services, Zeitwerk, multi-tenant, concerns)
- [ ] Phase D applied via `complexity-review` and `rails-overengineering-review`
- [ ] Phase E maintainability checks applied
- [ ] Missing tests raised as a named finding
- [ ] Every Blocker states a system risk; every finding has a label, `file:line`, and an actionable Rails fix
- [ ] If `--spec` was passed, every finding traces to AC/NFR/task or is flagged out-of-scope
- [ ] Non-Core subagents ran in parallel with the pre-resolved diff/log; failed scopes noted as `Scope incomplete`
- [ ] Findings merged with deduplication and highest-severity-wins; raw subagent reports not appended
- [ ] Next Steps produced (or omitted only when no actionable findings)
- [ ] Report written via `review-report-writer`; confirmation line printed

## Avoid

- Running `git fetch`, `git checkout`, or any state-changing git command - the user runs these
- Reviewing without reading the full diff and log first
- Applying generic backend conventions where a Rails idiom exists ("extract to a service object", not "extract to a helper class")
- Nitpicking style without a project standard; no `[Nitpick]` / `[Praise]` labels
- Vague feedback without a concrete Rails fix
- Blocking on personal preference rather than correctness, risk, or maintainability
- Running extra-scope subagents when the user passed `core-only`
- Duplicating perf / security / observability depth here when the dedicated subagent owns it
- Running multiple extra scopes sequentially when they can run in parallel
- Appending raw subagent reports instead of merging into one severity-ordered list
