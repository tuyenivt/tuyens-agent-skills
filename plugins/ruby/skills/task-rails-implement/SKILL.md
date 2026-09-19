---
name: task-rails-implement
description: Implement a Rails feature end-to-end - migration, model, service, controller, serializer/views, Sidekiq, Pundit, RSpec.
agent: rails-engineer
metadata:
  category: backend
  tags: [ruby, rails, feature, implementation, workflow]
  type: workflow
user-invocable: true
---

## When to Use

- New Rails feature end-to-end (migration -> model -> service -> controller -> tests)
- New aggregate with REST API, persistence, authorization, tests
- Scaffolding a domain resource with production-ready patterns

Not for: single-file bug fixes, view-only edits (use `rails-view-templates`), migration-only changes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect` for Ruby/Rails version and DB (MySQL/PG). API-only vs server-rendered (`views/` beyond mailers, `ActionController::Base` vs `API`), serializer library and view engine (ERB/HAML/Slim) are not stack-detect fields (unless the project declares them under `## Tech Stack`, where they arrive in `Additional`) - read them here from the app itself. An app with both an API namespace and server-rendered views is both. Put the feature on the surface its consumer uses - a partner or SPA caller means the API namespace, an operator screen means the server-rendered controller, and both consumers mean both, with the mutation extracted to one service they share. Say which in the design - it is the `Surface:` line of the Step 4 design.

### Step 3 - Gather Requirements

Resolve (ask, or infer per the threshold below):
1. Feature description and primary use case
2. Main models (fields, types, relationships, constraints)
3. External integrations (payments, email, third parties)
4. Background jobs needed?
5. Authorization rules (admin / owner / public)
6. Status transitions

Anything the design assumes but the project does differently or lacks - a gem (Pundit, a serializer, advisory locks), a base class (`ApplicationMailer`), or a convention (this file's verb-named services against an app of noun-named ones; a project `Result` whose shape differs from `rails-service-objects`', used as is and extended additively) - is named at the design gate with the substitute you intend. Never silently skipped, never treated as blocking: the project's own conventions win over this workflow's defaults wherever the two differ - except a convention an atomic's Rules forbid (controller specs, truncation cleaning by default), where new code follows the atomic, shared config stays untouched, and the divergence is named at the gate - and a generated file's missing parent is generated with it.

Ask-vs-infer threshold: when the domain has one defensible conventional shape, infer it and confirm at the design gate - the gate is the round trip. Ask first only when a missing decision changes the schema or endpoints *and* has no conventional default (who approves what, novel entities, custom business rules). Edge cases:
- Referenced model doesn't exist - generate it with the feature when it has one conventional shape, naming the assumption at the gate; otherwise ask whether to generate or assume
- Partial input - ask for entity fields, relationships, operations before design

### Step 4 - Design (Approval Gate)

Use skill: `rails-activerecord-patterns` (associations, scopes, enums). Use skill: `rails-service-objects` (interface, transactions, Result).

Present:
- Surface: API namespace | server-rendered | both (Step 2)
- Entity model: fields, types, constraints, enum integer mapping
- Status transitions: allowed edges per stateful entity (from Step 3 item 6)
- Associations + `dependent:` options
- Service methods, transaction boundaries (claim-then-finalize when a contended resource - stock, seat, slot - is charged, with its stale-claim sweep job), Sidekiq dispatch points
- External integrations: each call placed before the transaction (gating) or after commit (deferrable) per Step 7, the inbound webhook endpoint (Step 8.5), the scheduler cadence (Step 7)
- Endpoints (method, URI, status, request/response shapes)
- Authorization rules per action
- Attachments, if any: Use skill: `rails-active-storage-patterns` here so it shapes the migration (Step 5), the model declarations (Step 6) and the upload surface - the form (Step 11) when server-rendered; API-only clients drive Rails' mounted `/rails/active_storage/direct_uploads` and submit the `signed_id` in the JSON body (Step 9)
- File tree (only files this feature touches - generated ones, and existing files it modifies, each marked)

Example tree:

```
app/
  models/order.rb
  services/fulfill_order.rb
  controllers/api/v1/orders_controller.rb   # API
  serializers/order_serializer.rb           # API
  views/orders/{index,show,_form}.html.<ext> # server-rendered
  views/order_mailer/{confirmed}.html.<ext>  # if emails sent - API-only apps have these too
  components/order_card_component.rb        # server-rendered, reusable UI
  policies/order_policy.rb
  jobs/shipment_notification_job.rb         # if needed
  channels/order_channel.rb                 # if a custom ActionCable channel
  mailers/order_mailer.rb                   # if emails sent
  clients/shipment_api_client.rb            # if external API
  errors/application_error.rb               # domain error taxonomy (Step 12)
config/routes.rb                            # routes diff
config/schedule.yml                         # if cron-scheduled (sidekiq-cron; whenever uses schedule.rb)
lib/tasks/orders.rake                       # if a cron-invoked or backfill task
spec/{models,services,clients,policies,requests,jobs,mailers,components,channels,tasks,system}/...
spec/factories/orders.rb
db/migrate/<ts>_create_orders.rb
```

**Generate code only after user approves.** When the run cannot reach the user, present the design and stop there - state that the gate is unmet and what approval it needs. Never infer approval.

### Step 5 - Migrations

Use skill: `rails-migration-safety` (MySQL) or `rails-postgresql-migration-safety` (PG). One structural concern per migration (a new table plus its own indexes and constraints is one concern). Indexes on FKs and frequently-filtered columns; partial indexes for non-terminal status (PG; on MySQL a functional index, or a composite with the range/sort column); `null: false` + defaults where appropriate. Monetary values: integer cents columns (`amount_cents`) by default; `decimal` precision/scale only when matching an existing project convention; never float for money or percentages (integer percent / basis-point columns).

### Step 6 - Models

Use skill: `rails-activerecord-patterns`. Apply its rules: explicit `dependent:` on `has_many`/`has_one` (a bare `has_many :through` inherits it from its direct association), `enum` with integer mapping, chainable scopes, `counter_cache` where count queries appear, no `default_scope`.

File uploads: decided at the Step 4 design (`rails-active-storage-patterns` loaded there), including Active Storage's own tables in Step 5 when not yet installed; declare the attachments here.

### Step 7 - Services

Use skill: `rails-service-objects`. Use skill: `rails-transaction-patterns` for boundary discipline (`after_commit` dispatch, nested transactions). If Sidekiq needed: Use skill: `rails-sidekiq-patterns`. If a rake/backfill task is needed: Use skill: `rails-rake-task-patterns`. A mutation that is one AR write with no orchestration and fewer than three call sites takes no service - `rails-service-objects` forbids the hollow wrapper; the controller writes directly.

Canonical shape (no external calls in the flow):

```ruby
def call
  unless @order.processing? || @order.fulfilled?   # replay guard skips the work, not the dispatch
    ActiveRecord::Base.transaction do
      @order.update!(status: :processing, fulfilled_at: Time.current)
      decrement_inventory
    end
  end
  ShipmentNotificationJob.perform_async(@order.id)  # post-commit; re-sent on replay, the job is idempotent
  Result.success(@order.reload)
end
```

When externals enter the flow, `rails-service-objects`' ordering arbitrates. Discriminator, the atomic's one question - *if this call fails, is the local write still correct?* No means it gates (charging at checkout, a third-party inventory reservation) - call *before* the transaction with an idempotency key; yes means it is deferrable (notification, ERP sync, search indexing, retryable carrier booking) - post-commit Sidekiq job whose own service applies the same call-before-txn rule internally. Money movement gates either way: a charge **and a refund** both go before the transaction with an idempotency key - `rails-service-objects` lists refund among the calls whose failure makes the local write wrong. A deferred-external job owns its terminal failure: `sidekiq_retries_exhausted` flips the domain status to its failure state; reporting is the reporter gem's (sentry-sidekiq with `report_after_job_retries`), or `Rails.error.report` where none is wired (`rails-exception-handling`: nothing receives it without `config.rails.register_error_subscriber` or a subscriber) - name that terminal state in the Step 4 transitions.

Cross-row invariants (per-user caps, quotas): enforce in the service under a row lock (Use skill: `rails-db-locking-patterns`), with a DB backstop where declaratively expressible (constraint, unique/partial index - not triggers) - a model validation alone races.

Domain-state denials (locked / archived / expired target): service `Result` failures, not Pundit policies - policies decide who may act, services decide whether current state allows it.

Mailers: generate under `app/mailers`; from a request or service dispatch with `deliver_later` post-commit, exactly like Sidekiq jobs - never inside the transaction; inside a Sidekiq job use `deliver_now` (the job is already the async boundary). Templates live in `app/views/<mailer_name>/` even in API-only apps - the Step 11 skip does not cover mailer views.

Time-based behavior (expiry, eligibility windows, retention): owned here. If the deadline is only checked at request time, a predicate on the timestamp (guard or scope) is the whole design - no scheduler. Add a cron-invoked rake task (`rails-rake-task-patterns`) or scheduled job only when something must happen at the deadline without a request (notify, purge, flip visible state); name the trigger in the design. Register the cadence in the scheduler the app already runs (`sidekiq-cron` schedule file, `whenever`'s `config/schedule.rb`; none present - cron-invoked rake task) and list that config file in Files Generated.

### Step 8 - External HTTP Clients

Skip if no external APIs. Otherwise: Use skill: `rails-http-client-patterns`. Generate a dedicated `app/clients/<name>_client.rb` with explicit timeouts, JSON middleware + `:raise_error`, idempotency-aware retries (cap 2-3; Sidekiq handles longer waits), a domain error taxonomy translated from Faraday/HTTP errors. Provider ships an official Ruby SDK (`stripe`, `aws-sdk-*`): the client class wraps the SDK instead of Faraday - configure timeouts/retries through the SDK and translate its errors into the same domain taxonomy. Services rescue **domain** errors only; tests stub at the boundary (WebMock unit / VCR integration).

If the feature fans out across two or more external services on the same request or job, Use skill: `rails-concurrency-patterns` to pick the primitive (`Concurrent::Promises`, the `async` gem, or Sidekiq fan-out - `load_async` is not one, it only runs ActiveRecord queries on the async executor and cannot dispatch HTTP).

### Step 8.5 - Inbound Webhooks

Skip if the feature receives no provider callback. Otherwise the endpoint verifies the signature through the provider SDK where one exists, verifies against `request.raw_post` (it caches and rewinds, so `params` still parses; `request.body` read without rewinding empties both), rejects a signed timestamp older than ~5 minutes and is idempotent on the provider's event id (unique index), responds before doing slow work (enqueue, don't process inline), and is excluded from the authenticated namespace with its own rationale. Use skill: `rails-security-patterns` for the verification rules.

### Step 9 - Controllers

Strong params; pagination on list endpoints (match the project's paginator; none - `pagy`); delegate business logic to services. Authentication: wire the app's existing mechanism (`before_action :authenticate_user!` or equivalent) on new controllers - scaffolding auth itself is out of scope. Domain error -> HTTP:

| Domain Error                          | HTTP |
| ------------------------------------- | ---- |
| Malformed or missing parameter        | 400  |
| Validation failure                    | 422  |
| RecordNotFound                        | 404  |
| Conflict (duplicate, quota / cap / stock exhausted) | 409 |
| Payment declined / requires action    | 402  |
| Invalid state transition              | 422  |
| Upstream dependency down / timed out  | 503  |
| Unauthenticated                       | 401  |
| Forbidden                             | 403  |

**API versioning:** new APIs under `/api/v1/...`; for existing apps, match the convention.

**Idempotency keys** for non-GET write endpoints whose effect must not duplicate on retry (payments, orders, refunds). Mechanisms: row-creating endpoints forward the `Idempotency-Key` header backed by a unique index, deriving the key deterministically from intent (`"checkout-#{user_id}-#{cart_id}"`) when the client sends none - a server-rendered form carries it as a hidden field; state transitions on existing rows are replay-safe via a status guard under row lock (no header needed - the existing row's status is the guard). An endpoint that does both (creates a row and transitions its parent) applies both: header-backed unique index on the new row, status guard on the parent. A create whose only effect is a row already guarded by a unique index needs no header - the index is the guard. See `rails-service-objects`.

### Step 10 - Serializers (API only)

Skip for server-rendered. One serializer per resource; never `render json: @model`. Library: match the project convention (`alba`, `jsonapi-serializer`, `active_model_serializers`, `blueprinter`). No existing convention (Rails ships none): use `alba`.

### Step 11 - Views (server-rendered only)

Skip for API-only. Use skill: `rails-view-templates`. **Match the existing engine** (ERB/HAML/Slim) - never introduce a new one. Generate only the files this feature needs (`index`/`show`/`new`/`edit`, `_form`, collection partial, ViewComponents, Turbo Frames keyed by `dom_id(record)`, Stimulus controllers, fragment caching for hot collections). Live in-place updates (`turbo_stream_from` + broadcasts): Use skill: `rails-actioncable-patterns` *here* for scope and broadcast hooks - don't defer it to Step 12. Intentional HTML via `sanitize` allowlist; never `.html_safe` on user input.

### Step 12 - Security + Exception Strategy

Use skill: `rails-security-patterns` (Pundit policies per resource; `verify_authorized` / `verify_policy_scoped` on the base class per its shape when every controller authorizes, else on the new controllers with the gap named at the design gate; strong params). Use skill: `rails-exception-handling` for the `ApplicationController#rescue_from` ladder and domain error taxonomy.

Public/token endpoints (shared links): the token *is* the capability - use Rails signed ids, `record.signed_id(expires_in:, purpose:)` and `Model.find_signed!(token, purpose:)`, so the token expires and is scoped to one purpose - it stays replayable until expiry, so a one-shot action also records its use (a `has_secure_token` column does neither); route by token outside the authenticated resource namespace, serve through a read-only serializer, and skip Pundit with an explicit `skip_after_action :verify_authorized` (and `:verify_policy_scoped` on a collection) + stated rationale.

- File uploads: `rails-active-storage-patterns` was loaded at the Step 4 design; apply its serving/security rules here
- Custom ActionCable channels / connection auth: Use skill: `rails-actioncable-patterns` here (Step 11 loaded it for Turbo broadcast scoping on server-rendered runs; API-only runs load it here)

### Step 13 - Tests

Use skill: `rails-testing-patterns`. Minimum coverage - add rows the feature's behavior demands beyond this list:
- Model: associations, validations, scopes, enums
- Service: one example per `Result` outcome; side effects asserted
- Policy: every action, one example per distinct outcome, plus the `Scope`
- Request: happy + unauthorized + validation-error per action
- Job: idempotency + bounded retry (if applicable)
- Client: boundary-stubbed (WebMock) per outcome, incl. timeout/error -> domain-error translation (if external APIs)
- Mailer: per email action; enqueued via `deliver_later` from a request or service, delivered via `deliver_now` from a job (if emails sent). `rails-testing-patterns`' `Test Type` enum carries no Mailer, Component or Channel value - emit these in its per-file block shape with the type named plainly
- Channel (custom ActionCable channel): subscription authorization + broadcast (if Step 12 generated one)
- Rake task: wiring spec (if Step 7 generated one)
- ViewComponent (server-rendered): `render_inline` per state
- Turbo Stream / broadcast (server-rendered live updates): response format + `have_broadcasted_to`
- System (server-rendered): critical user flows only, per `rails-testing-patterns`' speed ladder - not per CRUD action
- Factories: traits per status/state

### Step 14 - Validate

Run `bundle exec rspec` and `bundle exec rubocop`. Fix failures before presenting output. If the environment can't execute them, say so explicitly, list the commands for the user to run, and report spec counts as "written, not executed" - never claim passes.

## Output Format

When the Step 4 gate is unmet, the deliverable is the design itself - the `Present:` list, filled - under `## Proposed Design`, followed by `## Blocked At` naming the gate, the approval it needs, and each question the run could not ask. The blocks below describe what was built and are omitted entirely; do not restate the design in them. Every atomic's output block informs the code and is not emitted, with two exceptions the template carries: `rails-testing-patterns`' per-file blocks under `## Tests`, and each migration's `Safety:` value under `## Migrations`. Server-rendered endpoints fill the Response column with the view rendered or the redirect target and Status 302/422. When Step 14 could not execute, `## Tests` reads `[N] specs written, not executed`.

```markdown
## Proposed Design   {gate unmet: the Step 4 Present list, filled; the sections below are then omitted}

## Blocked At   {gate unmet: the gate, the approval it needs, each question the run could not ask}

## Files Generated
{grouped by layer: migrations, models, services, controllers, serializers/views (incl. Stimulus controllers, helpers, locales), policies, jobs, mailers, clients, errors, channels, rake tasks, view components, routes, scheduler config, tests}

## Endpoints
| Method | Path                       | Request      | Response                   | Status |
| ------ | -------------------------- | ------------ | -------------------------- | ------ |
| POST   | /api/v1/orders             | OrderParams  | OrderSerializer            | 201    |
| POST   | /api/v1/orders/:id/fulfill | -            | OrderSerializer            | 200    |

## Sidekiq Jobs   {when at least one job}
| Job                     | Queue   | Trigger               | Retry |
| ----------------------- | ------- | --------------------- | ----- |
| ShipmentNotificationJob | mailers | After order fulfilled | 5     |

## Tests
{one `rails-testing-patterns` per-file block per spec, factory and support file}

{N} specs passing | {N} specs written, not executed

## Migrations
{file name; tables, indexes, constraints; the migration atomic's `Safety:` value, and any `Blocked` out-of-band step named}
```

## Self-Check

- [ ] Step 1: behavioral-principles loaded
- [ ] Step 2: stack confirmed (API-only vs server-rendered, view engine, serializer lib)
- [ ] Step 3: requirements gathered
- [ ] Step 4: design approved before generating code
- [ ] Step 5: migration-safety skill consulted; one concern per migration; indexes on FKs/filters
- [ ] Step 6: `rails-activerecord-patterns` applied to models
- [ ] Step 7: services return `Result`; transactions and post-commit dispatch via `rails-transaction-patterns`
- [ ] Step 8: external APIs go through a dedicated client with timeouts and domain taxonomy; multi-service fan-out picked its primitive via `rails-concurrency-patterns`
- [ ] Step 8.5: inbound webhooks verify the signature and timestamp freshness, read the body once via `raw_post`, dedup on the provider event id, and enqueue rather than process inline (or no callback in this feature)
- [ ] Step 9: strong params, pagination, domain-to-HTTP mapping, idempotency keys on writes
- [ ] Step 10: serializer per resource (or skipped for server-rendered)
- [ ] Step 11: views in existing engine via `rails-view-templates` (or skipped for API)
- [ ] Step 12: Pundit policies + `rescue_from` ladder; Active Storage serving rules and custom ActionCable channels when applicable
- [ ] Step 13: model + service + policy (with Scope) + request + job + mailer + client + component + channel + rake + broadcast + system specs as applicable; factory traits
- [ ] Step 14: `rspec` and `rubocop` pass (or reported "written, not executed" when the environment can't run them)

## Avoid

- Generating code before design approval
- `.perform_async` / external API calls / mailers inside a DB transaction (dispatch post-commit: sequential code after the outermost transaction block, `ActiveRecord.after_all_transactions_commit` inside a caller's transaction, or `after_commit`)
- `render json: @model` without a serializer
- Business logic in controllers or model callbacks
- Introducing a new view engine when one already exists
