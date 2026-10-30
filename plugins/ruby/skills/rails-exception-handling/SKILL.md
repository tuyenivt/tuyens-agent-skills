---
name: rails-exception-handling
description: "Rails 8.1 exception strategy: rescue_from, domain vs framework errors, Result vs raise, Sidekiq retry propagation, boundary translation."
metadata:
  category: backend
  tags: [ruby, rails, exceptions, errors, rescue_from, sidekiq]
user-invocable: false
---

> Load `Use skill: stack-detect` first. API-only vs server-rendered and the reporter gem are not stack-detect fields - read `config.api_only` / the base controller class and the Gemfile.

## When to Use

- Defining the application-wide rescue strategy in `ApplicationController`
- Designing the domain error taxonomy for a feature or subsystem
- Choosing `Result` vs raise in service code
- Sidekiq job error handling (retry vs swallow)
- Translating third-party SDK errors at a boundary
- Reviewing bare `rescue`, `rescue Exception`, or logged-and-swallowed errors

## Rules

- One application-wide rescue ladder - `rescue_from` (a class method) declared in `ApplicationController`; controllers don't catch their own.
- App-level domain errors inherit from one base (`ApplicationError`) so they rescue as a group; a client-local boundary vocabulary (`BillingError`) is its own base per client, each subclass mapping onto one taxonomy category.
- Services: `Result` for expected failures (validation, not-found); policy denial is either - raise when the controller ladder catches it, `Result` when a service composes it; raise for programmer errors and unexpected state. A degraded optional read (a dashboard widget) is a nil or `Result` from the service under `Rails.error.handle`, never a controller rescue.
- Sidekiq: rescue domain errors that should not retry; let everything else propagate so Sidekiq retries.
- SDK errors translate at the boundary (`app/clients/`; a vendor wrapper under `app/services/` is still the client layer); business code rescues domain errors only, never `Faraday::Error` or `Stripe::StripeError`.
- Never `rescue Exception` - it swallows `SignalException`, `SystemExit` and `NoMemoryError`, which is how a job survives the shutdown signal meant to stop it. `rescue` on its own is `rescue StandardError`, so it catches none of those; its fault is being indiscriminate within `StandardError` and discarding the exception object. Use `rescue => e` and name the classes you actually handle.
- Every `rescue` re-raises, returns a typed Result, renders a documented response, or swallows with a stated reason and an explicit reporter call. Never log-and-continue silently.
- Error reporter (Sentry/Honeybadger/Bugsnag) fires once per error at the highest sensible boundary. Lower layers don't double-report.

## Patterns

### Application Rescue Ladder

```ruby
class ApplicationController < ActionController::API
  rescue_from ActionController::ParameterMissing,        with: :bad_request
  rescue_from ActiveRecord::RecordNotFound,              with: :not_found            # optional - rescue_responses already answers 404; keep only for the JSON envelope
  rescue_from ActiveRecord::RecordInvalid,               with: :unprocessable
  rescue_from Pundit::NotAuthorizedError,                with: :forbidden   # only gems actually present
  rescue_from ApplicationError::Unauthenticated,         with: :unauthorized         # 401 - no/!valid credential or signature
  rescue_from ApplicationError::NotFound,                with: :not_found
  rescue_from ApplicationError::ValidationFailed,        with: :unprocessable
  rescue_from ApplicationError::PolicyDenied,            with: :forbidden
  rescue_from ApplicationError::IdempotencyConflict,     with: :conflict             # 409
  rescue_from ApplicationError::ExternalUnavailable,     with: :service_unavailable  # 503 (502 if proxying the upstream's failure verbatim)
  rescue_from BillingError::Unavailable,                 with: :service_unavailable  # client-local vocabulary maps onto the same statuses;
  rescue_from BillingError::NotFound,                    with: :not_found            # BillingError::Unexpected stays unrescued - it is a bug
  rescue_from BillingError::Declined,                    with: :payment_required     # 402 - the status a Result :payment_declined code maps to

  private

  def bad_request(e)          = render_error(e, :bad_request)
  def unauthorized(e)         = render_error(e, :unauthorized)
  def conflict(e)             = render_error(e, :conflict)
  def not_found(e)            = render_error(e, :not_found)
  def forbidden(e)            = render_error(e, :forbidden)
  def payment_required(e)     = render_error(e, :payment_required)
  def service_unavailable(e)  = (Rails.error.report(e); render_error(e, :service_unavailable))   # a 503 is reported; needs config.rails.register_error_subscriber = true (Single-Source Reporting)
  def unprocessable(e)        = render json: { error: e.message, request_id: request.request_id,
                                               details: e.try(:record)&.errors || e.try(:details) },
                                       status: :unprocessable_content   # 8.1 maps it on every Rack it supports; :unprocessable_entity is the deprecated alias
  def render_error(e, status) = render json: { error: e.message, request_id: request.request_id }, status: status
end
```

`rescue_from` handlers are searched bottom-up: the **last-declared** handler whose class matches wins. So declare broad classes at the top, narrow ones at the bottom. Every domain error - app-level or client-local - gets a ladder entry and an HTTP status, except `Unexpected`-style bugs, which stay unrescued; include `request_id` so users can quote it in reports. Malformed JSON (`ActionDispatch::Http::Parameters::ParseError`) raises lazily on the first `params` read inside the action or a callback, so `rescue_from` catches it; `config.action_dispatch.rescue_responses` maps any ParseError that escapes unrescued to 400, whether a middleware raised it or an action with no matching `rescue_from` did; add the `rescue_from` only for the JSON envelope.

Server-rendered apps keep the identical ladder; handlers render an error template or `redirect_back` with a flash instead of JSON (`render "errors/not_found", status: :not_found`), and the `request_id` goes in the page footer rather than the payload.

The 4xx handlers above intentionally do NOT report to Sentry - they are expected outcomes. The unexpected-bug path (500) is reported once by Rails/Sentry middleware *after* controllers, so don't `rescue_from StandardError` to render a friendly 500 - it hides bugs from the middleware unless you report-then-re-render yourself; prefer leaving it unrescued.

### Domain Error Taxonomy

```ruby
# app/errors/application_error.rb
class ApplicationError < StandardError
  class Unauthenticated    < self; end
  class NotFound           < self; end
  class ValidationFailed   < self
    attr_reader :details
    def initialize(message, details: {}) = (@details = details; super(message))
  end
  class PolicyDenied        < self; end
  class ExternalUnavailable < self; end
  class IdempotencyConflict < self; end
end

# app/errors/billing_error.rb - client-local vocabulary (Boundary Translation)
class BillingError < StandardError
  class Declined < self; end
  class NotFound < self; end
  class Unavailable < self; end
  class Unexpected < self; end
end
```

Group by **how the caller responds**, not where the error originated. A vendor- or origin-named base that callers rescue (`PaymentError`/`StripeError`) is the wrong axis - callers care about "validation", "transient", "policy", "not found". A counterparty's business refusal (account frozen, limit exceeded) is `ValidationFailed`-shaped when the caller can change the input and `PolicyDenied`-shaped when it cannot.

### Result vs Raise

| Outcome                                | Mechanism          | Why                                                     |
| -------------------------------------- | ------------------ | ------------------------------------------------------- |
| User-input validation failure          | `Result`           | Caller renders; not exceptional                         |
| Not found by user-facing lookup        | `Result`           | Expected branch; caller chooses 404 vs default          |
| Pundit/policy denial                   | Either             | Raise if controller catches; Result if service composes |
| Programmer error (nil where forbidden) | Raise              | Bug - fail fast, surface in reporter                    |
| External service down                  | Raise (translated) | Job retry handles; caller cannot recover inline         |
| Expected DB constraint violation       | `Result`           | Convert `RecordNotUnique` from race to Result           |

```ruby
class FulfillOrder   # Result is the project's Result class (`rails-service-objects`)
  def initialize(order_id:) = @order = Order.find_by(id: order_id)

  def call
    return Result.failure(["order not found"], code: :not_found)       unless @order
    return Result.failure(["already shipped"], code: :already_shipped) if @order.shipped?

    BillingClient.new.capture!(@order.charge_id)   # raises BillingError::Declined
    @order.update!(status: :shipped)
    Result.success(@order)
  rescue BillingError::Declined => e
    Result.failure([e.message], code: :payment_declined)
  rescue BillingError::NotFound => e                      # a permanent 404 - a Result, or Sidekiq retries it five times
    Result.failure([e.message], code: :charge_not_found)
  end
end
```

Raise across boundaries you don't control, translate at the client, rescue domain errors in the service. A non-idempotent external call (a charge) never runs inside the DB transaction - the claim-then-finalize shape and its reconciliation live in `rails-service-objects`. A webhook receiver answers 2xx only after the event is durably recorded (`webhook_events` unique on `event_id`; a duplicate is a 2xx no-op); a rescue that returns 200 on a failed write cancels the sender's redelivery, so a transient failure raises (5xx).

### Sidekiq Retry Semantics

Sidekiq treats unhandled exceptions as "retry per the retry config". Honor the contract:

```ruby
class FulfillOrderJob
  include Sidekiq::Job
  sidekiq_options retry: 5, dead: true

  def perform(order_id)
    result = FulfillOrder.new(order_id: order_id).call
    return if result.success?

    case result.code
    when :not_found, :already_shipped, :charge_not_found
      # idempotent skip - do not retry
    when :payment_declined
      OrderMailer.payment_failed(order_id).deliver_later
      # business-level failure - do not retry
    else
      raise ApplicationError::ExternalUnavailable, result.errors.join(", ")  # typed - sidekiq_retry_in can match the class
    end
  end
end
```

An Active Job's `retry_on` / `discard_on` rescue the error before any middleware sees it, so a retried or discarded failure reaches no error tracker unless the declaration carries `report: true` (8.1) - then each retried attempt goes through `Rails.error`; the exhausted one is not reported by `report: true` - without a block it re-raises into the job middleware, with a block it is swallowed, so a `retry_on` block calls `Rails.error.report(error)` itself; sentry-rails' `config.rails.active_job_report_on_retry_error` is the same knob at gem level, so set one, not both; a `Sidekiq::Job`'s retries are captured by the tracker's Sidekiq middleware instead. `rescue => e; logger.error(...)` in a job prevents retry and hides incidents. So do unbounded `retry`/`sleep` loops inside service code - retry belongs to Sidekiq, bounded and observable. One retry channel per error class: the HTTP client's `:retry` (configured with `exceptions:` listing `Faraday::TimeoutError`, `Faraday::RetriableResponse` and `Faraday::ConnectionFailed` - the option replaces the defaults - and `retry_statuses: [502, 503, 504]`; by default it retries only timeouts, and only idempotent methods, so a POST such as `capture!` needs `methods:` or `retry_if`) absorbs connect and 5xx blips within one call, Sidekiq's retry waits out an outage - a job that also wraps the call in `Retriable` multiplies attempts (`rails-http-client-patterns`). "Mark failed only once retries are exhausted" is `sidekiq_retries_exhausted` (`retry_on ... do |job, error|` on Active Job - its block runs only once attempts are exhausted, and `after_discard` fires then; a `discard_on` block runs on the first raise), never a rescue in `perform`. Batch re-entry after a raise on partial failure (or a crash mid-batch) reprocesses the rows that already succeeded unless the job checkpoints (`rails-batch-processing-patterns`). If you swallow, document why and call the reporter explicitly. For per-item batch work, don't swallow per item silently: collect failures, report one aggregate `Rails.error.report` with counts and sample rows in context (not one report per item - 10k failing rows must not page 10k times), raise if everything failed (`ExternalUnavailable` when a retry can help, a plain error when the data is bad).

### Boundary Translation

The client owns the SDK exception vocabulary; service code never names Faraday or Stripe:

```ruby
class BillingClient
  # `connection` registers `f.response :raise_error` - without it Faraday 2 returns 4xx/5xx
  # responses instead of raising, and none of the rescues below ever fire
  def capture!(charge_id)
    connection.post("/charges/#{charge_id}/capture").body
  rescue Faraday::TimeoutError, Faraday::ConnectionFailed, Faraday::SSLError, Faraday::ServerError => e
    raise BillingError::Unavailable, e.message          # ServerError = 5xx, not a ClientError; TLS failures are transient too
  rescue Faraday::ParsingError => e
    raise BillingError::Unexpected, e.message           # a malformed body is a bug on one side - not a ClientError
  rescue Faraday::ClientError => e
    case e.response&.dig(:status)
    when 401, 403 then raise BillingError::Unavailable, dig_message(e)   # our credential - after the one refresh retry
    when 402      then raise BillingError::Declined,    dig_message(e)
    when 404      then raise BillingError::NotFound,    dig_message(e)
    when 408, 429 then raise BillingError::Unavailable, dig_message(e)   # transient, though Faraday files them under ClientError
    else               raise BillingError::Unexpected,  dig_message(e)
    end
  end

  private

  def connection = @connection ||= Faraday.new(url: ENV.fetch("BILLING_API_URL")) { |f| f.response :json; f.response :raise_error }

  def dig_message(e) = e.response&.dig(:body).to_s.presence || e.message
end
```

Swapping Faraday for HTTPX or Stripe for Adyen does not ripple. A client-local namespace (`BillingError::Declined`) is boundary vocabulary named for the *capability*, not the vendor; each class still maps onto one caller-response category from the taxonomy. SDKs that raise one class for everything: branch on the error's `code`/`status` attribute the same way this example branches on HTTP status. Stripe's classes map the same way: `Stripe::CardError` -> `Declined`; `APIError`, `RateLimitError`, `APIConnectionError`, `AuthenticationError`, `PermissionError` -> `Unavailable`; `InvalidRequestError` -> `NotFound` when `code == "resource_missing"`; everything else (any other `InvalidRequestError`, `IdempotencyError`) -> `Unexpected`. A `Net::HTTP` client translates `Net::OpenTimeout`, `Net::ReadTimeout`, `SocketError`, `Errno::ECONNREFUSED` and `OpenSSL::SSL::SSLError` to `Unavailable`, and branches on `response.code` for the rest (it raises on status only through `response.value`). A 401/403 from the partner on our own credential is `Unavailable`-shaped after one refresh - an ops failure, never a caller fault. Auth-expiry belongs to the client too - refresh and retry once inside the client, then translate to `Unavailable` if it still fails. For client structure, see `rails-http-client-patterns`.

### Single-Source Reporting

Modern reporter gems self-wire, but through two independent mechanisms - conflating them is how swallowed errors go missing. sentry-rails installs the `Sentry::Rails::CaptureExceptions` Rack middleware, which catches unhandled controller errors; *separately* it registers a `Rails.error` subscriber, gated on `config.rails.register_error_subscriber`. Verify that flag is on before relying on `Rails.error.report` below, or intentional swallows reach nobody. sentry-sidekiq captures job errors, and its `report_after_job_retries` setting decides every-retry vs retries-exhausted - that setting, not the rescue, is the knob for an alert flood from a job that eventually succeeds. Adding manual `Rails.error.subscribe(...)` or `Sentry.capture_exception` on top is the usual *cause* of duplicate alerts, not the fix.

- Default: zero manual capture calls. The middleware reports unhandled errors once at the terminal boundary (controller, job, rake).
- Manual capture is for errors you intentionally swallow: `Rails.error.handle(context: {...}) { ... }` (reports and suppresses) or `Rails.error.report(e)` - only at the layer that decided to swallow.
- Lower layers never call the reporter; `rescue_from`-handled 4xx domain errors are not reported at all.

## Output Format

One block per layer per file (a feature spanning client + service + job emits three; two jobs under review are two job blocks); one controller block per base class when `ActionController::Base` and `ActionController::API` carry separate ladders, one block for the shared concern when they do not. Fields that don't apply to a layer take `N/A`. A layer the reviewed path calls but the read set does not include gets no block: one numbered finding names the file as `not in evidence`. In review or diagnosis mode, numbered findings precede the blocks, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. Every block field holds the corrected value, except a field the reviewed code violates: it holds `<observed> - GAP -> <corrected>` (`none - GAP -> <corrected>` when the code has nothing there), and when the enum value that matches already carries a `GAP`, `FIX` or `BLOCKER` marker in any spelling (` - GAP`, `(GAP)`, `(FIX)`, `(BLOCKER)`, a trailing parenthetical included), that value is the observed half and ` -> <corrected>` follows it. The marker applies to every field, whether or not its enum lists a `GAP` value; a field whose value is several named or `+`-joined parts marks only the violated part. A violation that belongs to no block - process or deploy config, a schema defect, a sibling skill's concern, a bug seen in passing - is a numbered finding with no block, naming the file and, for a sibling's concern, the owning skill. A violation whose block unit the code lacks (no client class, no transaction, no channel class) gets a block for the unit the fix introduces, its name suffixed `(proposed)`. When the request's premise or a document contradicts the code or schema, the code wins: say so in a finding and proceed on what the code shows. A request to add code, or to change code the request does not ask you to judge, is build mode: every block field holds the corrected value and no GAP marker (an enum value's own marker is dropped), and a pre-existing violation the change touches is still a numbered finding. A request that names existing code to assess, even when it also asks for the fix, is review mode.

The job backend comes from the Gemfile (`sidekiq` or `solid_queue`), not from stack-detect. An Active Job class (`ApplicationJob`, any backend) retries through `retry_on` / `discard_on` and enqueues with `perform_later`; a `Sidekiq::Job` retries through `sidekiq_options retry:` + `sidekiq_retry_in` and enqueues with `perform_async`. A slot named for Sidekiq (`Sidekiq retry`, `sidekiq only`) takes the channel of whichever backend runs the job. A `rescue` inside `perform` for a class the retry channel owns wins and silently disables that retry - one channel per class. A worker killed mid-job (OOM, SIGKILL) raises nothing any rescue sees: Solid Queue fails the job with `SolidQueue::Processes::ProcessExitError`, `ProcessPrunedError` or `ProcessMissingError` and recovery is `rails-solid-stack-patterns`' subscriber; OSS Sidekiq loses it (Pro `super_fetch` recovers it).

```
Layer: <controller | service | job | client | rake | middleware / config (rescue_responses, reporter initializer)>

Rescue strategy: <rescue_from ladder (controller) | Result on expected | Result on expected + bounded local retry (2-3, Deadlocked only, idempotent work) | raise on unexpected | boundary translation (client: catch vendor, raise domain) | per-item isolation (batch: collect failures, raise only if all failed) | webhook receiver: 2xx after durable record, 5xx on transient failure | webhook receiver returning 2xx on failure - GAP | none - unhandled (GAP) | degraded optional read: nil / Result under Rails.error.handle | swallow into false / nil without a reporter call (GAP) | N/A - config layer | rescue Exception / Interrupt - swallows signals and Sidekiq::Shutdown (GAP) | mixed (justified - say which path takes which) | mixed - unjustified (GAP)>

Domain errors: <ApplicationError::X | client-local boundary vocabulary (BillingError::Declined) | framework only | none yet - the taxonomy this block introduces>

SDK translation: <at boundary | at boundary but undifferentiated - one class for timeout, 4xx and 5xx (FIX) | leaked into service (FIX) | leaked into a controller or job (FIX) | N/A - the layer makes no SDK call>

rescue_from coverage: <listed classes; missing: ...>

Sidekiq retry: <propagate | propagate via retry_on / discard_on (Active Job, any backend) | swallow with reason | per-item: swallow partial failures, propagate when all failed | bounded local retry then propagate (ActiveRecord::Deadlocked only, idempotent work) | per kind: <transient classes> propagate, <permanent classes> discarded | N/A - not a job layer>

Reporter call: <Rails.error / reporter notifier at <layer> | retry_on / discard_on report: true (Active Job, 8.1) | none (auto middleware reports) | none - rescue_from-handled 4xx (intended) | swallowed before the middleware saw it (FIX) | Rails.error.report with register_error_subscriber off - reaches nobody (FIX) | hand-written Rails.error.subscribe or capture beside the gem's own wiring - double-reported (FIX) | integration gem absent - under-reported (FIX) | every-retry, should be retries-exhausted (FIX)>
```

An app with both `ActionController::Base` and `ActionController::API` bases keeps one ladder in a concern included by both; handlers branch on `request.format` (the API base has no view renderer, so its branch renders JSON only). `ExternalUnavailable` (503) reports like a 5xx, not like the 4xx handlers - the no-report rule covers client-fault statuses only. A transient `ActiveRecord::Deadlocked` inside a job may take a bounded local retry (2-3, backed off) *when the work is idempotent*; otherwise let it propagate and let Sidekiq own the retry - never both.

## Avoid

- `rescue_from StandardError` rendering a friendly 500 - it hides every bug and suppresses the middleware that would have reported it. Leave 500s unrescued
- Manual `Sentry.capture_exception` / `Rails.error.subscribe` alongside auto-wired reporter gems - duplicate alerts
- Unbounded `retry` or `sleep`-and-retry inside rescue blocks - infinite loops that hold a worker thread
