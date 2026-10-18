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

Not for: single-file bug fixes, view-only edits, migration-only changes.

## Workflow

### Step 1 - Behavioral Principles

Use skill: `behavioral-principles`.

### Step 2 - Stack Detect

Use skill: `stack-detect`. Where the project's declared stack and its code disagree, record what the code does and note the divergence. Versions: `stack-detect` carries them only when `## Tech Stack` declares them - otherwise read Ruby / Rails from `.ruby-version` / `Gemfile.lock` and the MySQL patch level from ops docs or the server, else `unknown`; `rails-migration-safety`'s INSTANT / functional-index / CHECK gates read that patch level. API-only vs server-rendered (`views/` beyond mailers, `ActionController::Base` vs `API`), serializer library and view engine (ERB/HAML/Slim) are not stack-detect fields (unless the project declares them under `## Tech Stack`, where they arrive in `Additional`) - read them here from the app itself. An app with both an API namespace and server-rendered views is both. Put the feature on the surface its consumer uses - a partner or SPA caller means the API namespace, an operator screen means the server-rendered controller, and both consumers mean both, with the mutation extracted to one service they share. Say which in the design - it is the `Surface:` line of the Step 4 design.

### Step 3 - Gather Requirements

Resolve (ask, or infer per the threshold below):
1. Feature description and primary use case
2. Main models (fields, types, relationships, constraints)
3. External integrations (payments, email, third parties)
4. Background jobs needed?
5. Authorization rules (admin / owner / public)
6. Status transitions

Anything the design assumes but the project does differently or lacks - a gem (Pundit, a serializer, advisory locks), a base class (`ApplicationMailer`), or a convention (a project `Result` whose shape differs from `rails-service-objects`', used as is and extended additively; a Minitest suite) - is named at the design gate with the substitute you intend - as a `Divergences:` list under `## Design`, whether or not the gate is pre-approved. Never silently skipped, never treated as blocking: the project's own conventions win over this workflow's defaults wherever the two differ - except a convention an atomic's Rules forbid (controller specs, fixtures, noun-named services), where new code follows the atomic, shared config stays untouched, and the divergence is named at the gate - and a generated file's missing parent (`ApplicationController`-style base class, routes file, factory, `rails_helper` / test helper) is generated with it (a broken one is repaired, the repair listed under Files Generated); a collaborator the feature calls but does not own that is absent (a referenced job, an authentication mechanism, the inbound confirmation an asynchronous partner sends) is named at the gate, never scaffolded silently.

Ask-vs-infer threshold: when the domain has one defensible conventional shape, infer it and confirm at the design gate - the gate is the round trip. Ask first only when a missing decision changes the schema or endpoints *and* has no conventional default (who approves what, novel entities, custom business rules). Edge cases:
- Referenced model doesn't exist - generate it with the feature when it has one conventional shape, naming the assumption at the gate; otherwise ask whether to generate or assume
- No schema in evidence (`db/schema.rb` absent) - design the existing table from the model's code and name the assumption at the gate
- Partial input - ask for entity fields, relationships, operations before design

### Step 4 - Design (Approval Gate)

Use skill: `rails-activerecord-patterns` (associations, scopes, enums). Use skill: `rails-service-objects` (interface, transactions, Result).

Present:
- Stack: Ruby <v> / Rails <v> / MySQL <patch level or unknown> / <test framework> (Step 2)
- Surface: API namespace | server-rendered | both (Step 2)
- Entity model: fields, types, constraints, enum integer mapping
- Status transitions: allowed edges per stateful entity (from Step 3 item 6)
- Associations + `dependent:` options
- Service methods, transaction boundaries (claim-then-finalize when an external call - a charge, a reservation - sits between claiming a contended quantity and finalizing it, with its stale-claim sweep job; one transaction under `FOR UPDATE` otherwise), job dispatch points
- External integrations: each call placed before the transaction (gating) or after commit (deferrable) per Step 7, the inbound webhook endpoint (Step 8.5, under `app/controllers/webhooks/` outside the authenticated namespace), the scheduler cadence (Step 7)
- Endpoints (method, URI, status, request/response shapes)
- Authorization rules per action
- Attachments, if any: Use skill: `rails-active-storage-patterns` here so it shapes the migration (Step 5), the model declarations (Step 6) and the upload surface - the form (Step 11) when server-rendered keeps `direct_upload: true`, which resolves the `rails_direct_uploads` route by name (and silently renders a plain file field when none exists); every client drives an app subclass of `ActiveStorage::DirectUploadsController` that authenticates the caller (the engine controller inherits `ActionController::Base`, not `ApplicationController`, so it carries none of the app's filters), drawn by the app as `post "/rails/active_storage/direct_uploads" => "direct_uploads#create", as: :rails_direct_uploads` with `config.active_storage.draw_routes = false` (copy the engine's `config/routes.rb` into the app minus its `direct_uploads` line - the blob, representation and `/disk` routes and `direct` / `resolve` helpers that the Disk service in dev and test and `url_for(attachment)` need) - otherwise the engine's unauthenticated route stays open; API-only clients also skip forgery protection and submit the `signed_id` in the JSON body (Step 9)
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
config/schedule.yml                         # if cron-scheduled (sidekiq-cron; whenever uses schedule.rb; Solid Queue config/recurring.yml)
lib/tasks/orders.rake                       # if a cron-invoked or backfill task
spec/{models,services,clients,policies,requests,jobs,mailers,components,channels,tasks,system}/...
spec/factories/orders.rb
db/migrate/<ts>_create_orders.rb
```

**Generate code only after user approves.** When the run cannot reach the user, present the design and stop there - state that the gate is unmet and what approval it needs. Explicit approval written into the request itself meets the gate; never infer approval. The design is written from the atomics Steps 2-4 load; the atomics of Steps 5-13 load once the gate is met, so an unmet-gate design names the rules it will apply (signature verification, dedupe, scheduler) without loading them. A provider whose signing scheme the request does not state is named at the gate as an assumption (the default: HMAC-SHA256 over `"#{timestamp}.#{raw_body}"` in the signature header, the signed timestamp header rejected when older than ~5 minutes).

### Step 5 - Migrations

Use skill: `rails-migration-safety`. One structural change per migration (a new table with its indexes and constraints - inline in `create_table`, or an `add_index` on that new table in the same file - is one). A new lifecycle on an existing entity (a scheduled or cancellable variant of its rows) is columns on that table - a state value, the trigger date, a cancel timestamp - one migration each under the one-structural-change rule, not a new table; a new table only when the rows outlive, outnumber or are shared beyond the parent. Indexes on FKs and frequently-filtered columns; for a non-terminal-status filter, a composite with the range/sort column or a functional index (MySQL has no partial indexes); `null: false` + defaults where appropriate. Monetary values: integer cents columns (`amount_cents`) by default; `decimal` precision/scale only when matching an existing project convention; never float for money or percentages (integer percent / basis-point columns).

### Step 6 - Models

Use skill: `rails-activerecord-patterns`. Apply its rules: explicit `dependent:` on every owning `has_many`/`has_one` (a bare `has_many :through` is compliant when the direct `has_many` to the join model carries `dependent:`), `enum` with integer mapping on new columns (an existing string status column keeps its strings - a string-valued `enum` or plain scopes), chainable scopes, `counter_cache` where count queries appear, no `default_scope`.

File uploads: decided at the Step 4 design (`rails-active-storage-patterns` loaded there), including Active Storage's own tables in Step 5 when not yet installed; declare the attachments here.

### Step 7 - Services

Use skill: `rails-service-objects`. Use skill: `rails-transaction-patterns` for boundary discipline (`after_commit` dispatch, nested transactions). If a background job is needed: Use skill: `rails-sidekiq-patterns` - a Solid Queue app applies its idempotency, IDs-only and post-commit rules, retries through `retry_on` / `discard_on`, and puts terminal failure in the `retry_on` block. If a rake/backfill task is needed: Use skill: `rails-rake-task-patterns`. A mutation meeting neither limb of `rails-service-objects`' extraction bar takes no service - the atomic forbids the hollow wrapper; it stays in the model or controller (a single AR write: the controller calls it directly); a domain-state denial inside such a model method raises an `ApplicationError` subclass with a Step 12 ladder entry (`ValidationFailed` -> 422 for an invalid transition; a cap / stock conflict adds a `Conflict` subclass -> 409, since `rails-exception-handling`'s taxonomy maps only `IdempotencyConflict` to 409) - never a controller-local `rescue_from`.

Canonical shape: `rails-service-objects`' `FulfillOrder` - the replay guard and the full precondition checked after `lock!` inside `transaction(requires_new: true)`, and dispatch through `ActiveRecord.after_all_transactions_commit` (it waits for a caller's transaction and runs at once when none is open). A replay skips the work, not the dispatch, so every dispatched job - and any mail it sends - is idempotent on its own guard.

When externals enter the flow, `rails-service-objects`' ordering arbitrates. Discriminator, the atomic's one question - *if this call fails, is the local write still correct?* No means it gates (charging at checkout, a third-party inventory reservation) - call *before* the transaction with an idempotency key; yes means it is deferrable (notification, ERP sync, search indexing, retryable carrier booking) - post-commit job whose own service applies the same call-before-txn rule internally. Money movement gates either way: a charge **and a refund** both go before the transaction with an idempotency key - `rails-service-objects` lists refund among the calls whose failure makes the local write wrong. A deferred-external job owns its terminal failure: `sidekiq_retries_exhausted` (Active Job: the `retry_on` block) flips the domain status to its failure state - name that terminal state in the Step 4 transitions; reporting is the reporter gem's (sentry-sidekiq with `report_after_job_retries` on the Sidekiq adapter, sentry-rails' Active Job integration on other adapters); where none is wired, name the gap at the design gate - `Rails.error.report` alone reaches nobody without a subscriber (`rails-exception-handling`).

Cross-row invariants (per-user caps, quotas): enforce in the service under a row lock (Use skill: `rails-db-locking-patterns`), with a DB backstop where declaratively expressible (a CHECK on a parent-row counter column, `used_count <= cap` - MySQL CHECKs see one row; a unique or functional unique index for an at-most-one rule - not triggers) - a model validation alone races.

Domain-state denials (locked / archived / expired target): service `Result` failures, not Pundit policies - policies decide who may act, services decide whether current state allows it.

Mailers: generate under `app/mailers`; from a request or service dispatch with `deliver_later` post-commit, exactly like jobs - never inside the transaction; inside a job use `deliver_now` (the job is already the async boundary). Templates live in `app/views/<mailer_name>/` even in API-only apps - the Step 11 skip does not cover mailer views.

Time-based behavior (expiry, eligibility windows, retention): owned here. If the deadline is only checked at request time, a predicate on the timestamp (guard or scope) is the whole design - no scheduler. Add a cron-invoked rake task (`rails-rake-task-patterns`) or scheduled job only when something must happen at the deadline without a request (notify, purge, flip visible state); name the trigger in the design. A recurring task that executes due rows states its catch-up rule (every missed occurrence, or only the latest) and claims each row - `FOR UPDATE SKIP LOCKED`, or a status flip under the row lock per `rails-db-locking-patterns` - before any external call; the scheduled task enqueues one job per claimed row rather than calling the partner inside its own loop. Register the cadence in the scheduler the app already runs (`sidekiq-cron` schedule file, `whenever`'s `config/schedule.rb`, Solid Queue's `config/recurring.yml`; none present - cron-invoked rake task) and list that config file in Files Generated.

### Step 8 - External HTTP Clients

Skip if no external APIs. Otherwise: Use skill: `rails-http-client-patterns`. Reuse and extend an existing client for the same provider (its defects on the feature's call path go to Pre-existing Issues, fixed only when the feature cannot work without the fix, the fix listed under Files Generated); otherwise generate a dedicated `app/clients/<name>_client.rb` with explicit timeouts, JSON middleware + `:raise_error`, idempotency-aware retries (2-3 attempts - Faraday `max:` 1-2, since `max` counts retries; Sidekiq handles longer waits), a domain error taxonomy translated from Faraday/HTTP errors. Provider ships an official Ruby SDK (`stripe`, `aws-sdk-*`): the client class wraps the SDK instead of Faraday - configure timeouts/retries through the SDK (its global config in an initializer, listed under Files Generated) and translate its errors into the same domain taxonomy. Services rescue **domain** errors only; tests stub at the boundary (WebMock unit / VCR integration).

If the feature fans out across two or more external services on the same request or job, Use skill: `rails-concurrency-patterns` to pick the primitive (`Concurrent::Promises`, the `async` gem, or Sidekiq fan-out - `load_async` is not one, it only runs ActiveRecord queries on the async executor and cannot dispatch HTTP).

### Step 8.5 - Inbound Webhooks

Skip if the feature receives no provider callback. Otherwise the endpoint verifies the signature through the provider SDK where one exists, verifies against `request.raw_post` (cached and rewind-safe; a raw `request.body.read` must be rewound), rejects a signed timestamp older than ~5 minutes and is idempotent on the provider's event id (`webhook_events(provider, event_id)` unique index), answers 200 once the event row is stored and the job enqueued (a duplicate event id also answers 200 and re-enqueues the idempotent job unless the stored row's `processed_at`, set by the job when it finishes, is present - this overrides `rails-exception-handling`'s duplicate-as-no-op because the row insert and the enqueue are not atomic) - before doing slow work, never inline, and is excluded from the authenticated namespace with its own rationale. Use skill: `rails-security-patterns` for the verification rules, and Use skill: `rails-http-client-patterns` (Webhooks) for dedupe; out-of-order delivery takes `rails-sidekiq-patterns`' monotonic guard.

### Step 9 - Controllers

Strong params; pagination on list endpoints (match the project's paginator; none present - add `pagy`, named at the gate as an added gem); delegate business logic to services. Authentication: wire the app's existing mechanism (`before_action :authenticate_user!` or equivalent) on new controllers - scaffolding auth itself is out of scope; an app with none gets the gap named at the design gate. Domain error -> HTTP:

| Domain Error                          | HTTP |
| ------------------------------------- | ---- |
| Malformed or missing parameter        | 400  |
| Validation failure                    | 422  |
| RecordNotFound                        | 404  |
| Conflict (duplicate, quota / cap / stock exhausted) | 409 |
| Payment declined / requires action    | 402  |
| Payment processing (gateway not yet terminal) | 202 |
| Invalid state transition              | 422  |
| Upstream dependency down / timed out  | 503  |
| Unauthenticated                       | 401  |
| Forbidden                             | 403  |

A decline is 402 whether it arrives as a `Result` code or as `BillingError::Declined` through the Step 12 ladder.

**API versioning:** new APIs under `/api/v1/...`; for existing apps, match the convention.

**Idempotency keys** for non-GET write endpoints whose effect must not duplicate on retry (payments, orders, refunds). Mechanisms: row-creating endpoints forward the `Idempotency-Key` header backed by a unique index, deriving the key deterministically from intent - every input that makes a new attempt, `"checkout-#{user_id}-#{cart_id}-#{payment_method_id}"` - when the client sends none - a server-rendered form carries it as a hidden field; state transitions on existing rows are replay-safe via a status guard under row lock (no header needed - the existing row's status is the guard). An endpoint that does both (creates a row and transitions its parent) applies both: header-backed unique index on the new row, status guard on the parent. A create whose only effect is a row already guarded by a unique index needs no header - the index is the guard. See `rails-service-objects`.

### Step 10 - Serializers (API only)

Skip for server-rendered. One serializer per resource; never `render json: @model`. Library: match the project convention (`jbuilder` when `*.json.jbuilder` views exist - the tree and Response column then name the view - `alba`, `jsonapi-serializer`, `active_model_serializers`, `blueprinter`). No existing convention: use `alba`.

### Step 11 - Views (server-rendered only)

Skip for API-only. Use skill: `rails-view-templates`. **Match the existing engine** (ERB/HAML/Slim) - never introduce a new one. Generate only the files this feature needs (`index`/`show`/`new`/`edit`, `_form`, collection partial, ViewComponents, Turbo Frames keyed by `dom_id(record)`, Stimulus controllers, fragment caching for hot collections). Live in-place updates (`turbo_stream_from` + broadcasts): Use skill: `rails-actioncable-patterns` *here* for scope and broadcast hooks - don't defer it to Step 12. Intentional HTML via `sanitize` allowlist; never `.html_safe` on user input.

### Step 12 - Security + Exception Strategy

Use skill: `rails-security-patterns` (Pundit policies per resource; `verify_authorized` / `verify_policy_scoped` on the base class per its shape when every controller authorizes, else on the new controllers with the gap named at the design gate; strong params). Use skill: `rails-exception-handling` for the `ApplicationController#rescue_from` ladder and domain error taxonomy.

Public/token endpoints (shared links): the token *is* the capability - use Rails signed ids, `record.signed_id(expires_in:, purpose:)` and `Model.find_signed!(token, purpose:)`, so the token expires and is scoped to one purpose - it stays replayable until expiry, so a one-shot action also records its use (a `has_secure_token` column does neither); route by token outside the authenticated resource namespace, serve through a read-only serializer, and skip Pundit's enforcement inside the action with `skip_authorization` (`skip_policy_scope` instead on an `index` action, where the base calls `verify_policy_scoped`) - never `skip_after_action` on a callback the base class did not register (`rails-security-patterns`' base registers `verify_pundit_authorization`, not `verify_authorized`) - plus stated rationale.

- File uploads: `rails-active-storage-patterns` was loaded at the Step 4 design; apply its serving/security rules here
- Custom ActionCable channels / connection auth: Use skill: `rails-actioncable-patterns` here (when Step 11 did not already load it)

### Step 13 - Tests

Use skill: `rails-testing-patterns`. A Minitest suite (`test/`) is the project's convention: the same rows as Minitest tests under `test/` (request spec -> `test/integration`, job -> `test/jobs`, service / policy / client -> `test/services` / `test/policies` / `test/clients`), each in the atomic's per-file block, its `File:` slot holding the `test/` path in place of the slot's `spec/` forms (named under `Divergences:` at the gate), records built per its FactoryBot rule (adding `factory_bot_rails` to the test group, named at the gate; existing fixtures untouched). Minimum coverage - add rows the feature's behavior demands beyond this list:
- Model: associations, validations, scopes, enums
- Service: one example per `Result` outcome; side effects asserted
- Policy: every action, one example per distinct outcome, plus the `Scope`
- Request: happy + unauthorized + validation-error per action
- Job: idempotency + bounded retry (if applicable)
- Client: boundary-stubbed (WebMock) per outcome, incl. timeout/error -> domain-error translation (if external APIs)
- Mailer: per email action; enqueued via `deliver_later` from a request or service, delivered via `deliver_now` from a job (if emails sent). `rails-testing-patterns`' `Test Type` enum carries no Component value - emit ViewComponent specs in its per-file block shape with the type named plainly (Mailer and Channel use the enum's own values)
- Channel (custom ActionCable channel): subscription authorization + broadcast (if Step 12 generated one)
- Rake task: wiring spec (if Step 7 generated one)
- ViewComponent (server-rendered): `render_inline` per state
- Turbo Stream / broadcast (server-rendered live updates): response format + `have_broadcasted_to`
- System (server-rendered): critical user flows only, per `rails-testing-patterns`' speed ladder - not per CRUD action
- Factories: traits per status/state

### Step 14 - Validate

Run `bundle exec rspec` (a Minitest suite: `bin/rails test:all` - `bin/rails test` alone skips `test/system`) and `bundle exec rubocop`. Fix failures before presenting output. If the environment can't execute them, say so explicitly, list the commands for the user to run, and report spec counts as "written, not executed" - never claim passes.

## Output Format

`## Design` opens every deliverable: the Step 4 `Present:` list, filled, with the endpoints under the `## Endpoints` heading that follows it rather than repeated inside the list. When the gate is unmet, `## Blocked At` comes next, naming the gate, the approval it needs, and each question the run could not ask; the built sections below it, except `## Pre-existing Issues`, are omitted entirely. When the gate is met, `## Blocked At` is omitted and the built sections follow; `## Files Generated` carries each generated or modified file's path followed by its content in a fenced block (a modified file over ~60 lines: the changed hunks with context), grouped by layer. Every atomic's output block informs the code and is not emitted, with two exceptions the template carries: `rails-testing-patterns`' per-file blocks under `## Tests`, and each migration's `Safety:` value under `## Migrations`. Server-rendered endpoints fill the Response column with the view rendered (200) or the redirect target (302; 303 after a Turbo `DELETE`); a failed form re-renders with 422. When Step 14 could not execute, `## Tests` reads `[N] specs written, not executed`.

```markdown
## Design   {the Step 4 Present list, filled - every run}

## Endpoints   {every run}
| Method | Path                       | Request      | Response                   | Status |
| ------ | -------------------------- | ------------ | -------------------------- | ------ |
| POST   | /api/v1/orders             | OrderParams  | OrderSerializer            | 201    |
| POST   | /api/v1/orders/:id/fulfill | -            | OrderSerializer            | 200    |

## Blocked At   {gate unmet only: the gate, the approval it needs, each question the run could not ask; the sections below, except Pre-existing Issues, are then omitted}

## Pre-existing Issues   {when code the feature touches or depends on - not the repo at large - carries a defect the feature does not fix: `file:line` - the defect - why left}

## Files Generated
{grouped by layer: migrations, models, services, controllers, serializers/views (incl. Stimulus controllers, helpers, locales), policies, jobs, mailers, clients, errors, channels, rake tasks, view components, routes, scheduler config, tests; each path followed by the file's content in a fenced block}

## Background Jobs   {when at least one job; Retry = retries after the first run: `sidekiq_options retry:`, or `retry_on` attempts minus 1 - an Active Job class on the Sidekiq adapter also gets Sidekiq's own channel - its `sidekiq_options retry:` value, 25 when unset, none under `retry: 0` / `retry: false` - stated beside it; a `retry_on` block swallows only the classes it names}
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
- [ ] Step 2: stack confirmed (versions incl. MySQL patch level or `unknown`; API-only vs server-rendered, view engine, serializer lib)
- [ ] Step 3: requirements gathered
- [ ] Step 4: design approved before generating code
- [ ] Step 5: migration-safety skill consulted; one structural change per migration; indexes on FKs/filters
- [ ] Step 6: `rails-activerecord-patterns` applied to models
- [ ] Step 7: services return `Result`; transactions and post-commit dispatch via `rails-transaction-patterns`
- [ ] Step 8: external APIs go through a dedicated client with timeouts and domain taxonomy; multi-service fan-out picked its primitive via `rails-concurrency-patterns`
- [ ] Step 8.5: inbound webhooks verify the signature and timestamp freshness, read the body via `raw_post`, dedup on `(provider, event_id)` per `rails-http-client-patterns`, and enqueue rather than process inline (or no callback in this feature)
- [ ] Step 9: strong params, pagination, domain-to-HTTP mapping, idempotency per Step 9 (a key on duplicate-sensitive creates, a status guard under row lock on transitions)
- [ ] Step 10: serializer per resource (or skipped for server-rendered)
- [ ] Step 11: views in existing engine via `rails-view-templates` (or skipped for API)
- [ ] Step 12: Pundit policies + `rescue_from` ladder; Active Storage serving rules and custom ActionCable channels when applicable
- [ ] Step 13: model + service + policy (with Scope) + request + job + mailer + client + component + channel + rake + broadcast + system specs as applicable; factory traits
- [ ] Step 14: `rspec` (or `bin/rails test:all`) and `rubocop` pass (or reported "written, not executed" when the environment can't run them)

## Avoid

- Generating code before design approval
- `.perform_async` / an undeferred `perform_later` / external API calls / mailers inside a DB transaction (dispatch post-commit: `ActiveRecord.after_all_transactions_commit` from a service, sequential code after the transaction in a controller or job that owns it, or `after_commit`)
- `render json: @model` without a serializer
- Business logic in controllers or model callbacks
- Introducing a new view engine when one already exists
