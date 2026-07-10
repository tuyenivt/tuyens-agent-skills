---
name: rails-exception-handling
description: "Rails 7.2 exception strategy: rescue_from, domain vs framework errors, Result vs raise, Sidekiq retry propagation, boundary translation."
metadata:
  category: backend
  tags: [ruby, rails, exceptions, errors, rescue_from, sidekiq]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack (API-only vs server-rendered, error reporter gem).

## When to Use

- Defining the application-wide rescue strategy in `ApplicationController`
- Designing the domain error taxonomy for a feature or subsystem
- Choosing `Result` vs raise in service code
- Sidekiq job error handling (retry vs swallow)
- Translating third-party SDK errors at a boundary
- Reviewing bare `rescue`, `rescue Exception`, or logged-and-swallowed errors

## Rules

- One application-wide rescue ladder in `ApplicationController#rescue_from`; controllers don't catch their own.
- Domain errors inherit from one app-level base (`ApplicationError`) so they rescue as a group.
- Services: `Result` for expected failures (validation, not-found, policy denial); raise for programmer errors and unexpected state.
- Sidekiq: rescue domain errors that should not retry; let everything else propagate so Sidekiq retries.
- SDK errors translate at the boundary (`app/clients/`); business code rescues domain errors only, never `Faraday::Error` or `Stripe::Error`.
- Never bare `rescue` or `rescue Exception` (swallows `SignalException`, `SystemExit`, `NoMemoryError`). Use `rescue => e` to catch `StandardError`.
- Every `rescue` re-raises, returns a typed Result, or renders a documented response. Never log-and-continue silently.
- Error reporter (Sentry/Honeybadger/Bugsnag) fires once per error at the highest sensible boundary. Lower layers don't double-report.

## Patterns

### Application Rescue Ladder

```ruby
class ApplicationController < ActionController::API
  rescue_from ActionController::ParameterMissing,        with: :bad_request
  rescue_from ActiveRecord::RecordNotFound,              with: :not_found
  rescue_from ActiveRecord::RecordInvalid,               with: :unprocessable
  rescue_from Pundit::NotAuthorizedError,                with: :forbidden   # only gems actually present
  rescue_from ApplicationError::NotFound,                with: :not_found
  rescue_from ApplicationError::ValidationFailed,        with: :unprocessable
  rescue_from ApplicationError::PolicyDenied,            with: :forbidden
  rescue_from ApplicationError::IdempotencyConflict,     with: :conflict             # 409
  rescue_from ApplicationError::ExternalUnavailable,     with: :service_unavailable  # 503 (502 if proxying the upstream's failure verbatim)

  private

  def bad_request(e)          = render_error(e, :bad_request)
  def not_found(e)            = render_error(e, :not_found)
  def forbidden(e)            = render_error(e, :forbidden)
  def service_unavailable(e)  = render_error(e, :service_unavailable)
  def unprocessable(e)        = render json: { error: e.message, request_id: request.request_id,
                                               details: e.try(:record)&.errors }, status: :unprocessable_entity
  def render_error(e, status) = render json: { error: e.message, request_id: request.request_id }, status: status
end
```

`rescue_from` handlers are searched bottom-up: the **last-declared** handler whose class matches wins. So declare broad classes at the top, narrow ones at the bottom. Every domain error in the taxonomy gets a ladder entry and an HTTP status; include `request_id` so users can quote it in reports. Malformed JSON (`ActionDispatch::Http::Parameters::ParseError`) raises before controllers - handle via `config.action_dispatch.rescue_responses` or middleware, not `rescue_from`.

The 4xx handlers above intentionally do NOT report to Sentry - they are expected outcomes. The unexpected-bug path (500) is reported once by Rails/Sentry middleware *after* controllers, so don't `rescue_from StandardError` to render a friendly 500 - it hides bugs from the middleware unless you report-then-re-render yourself; prefer leaving it unrescued.

### Domain Error Taxonomy

```ruby
# app/errors/application_error.rb
class ApplicationError < StandardError
  class NotFound           < self; end
  class ValidationFailed   < self
    attr_reader :details
    def initialize(message, details: {}) = (@details = details; super(message))
  end
  class PolicyDenied        < self; end
  class ExternalUnavailable < self; end
  class IdempotencyConflict < self; end
end
```

Group by **how the caller responds**, not where the error originated. `BillingError`/`PaymentError`/`StripeError` is the wrong axis - callers care about "validation", "transient", "policy", "not found".

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
class FulfillOrder
  def call
    return Result.failure(:not_found)       unless @order
    return Result.failure(:already_shipped) if @order.shipped?

    Billing::Client.capture!(@order.charge_id)   # raises BillingError::Declined
    @order.update!(status: :shipped)
    Result.success(@order)
  rescue BillingError::Declined => e
    Result.failure(:payment_declined, e.message)
  end
end
```

Raise across boundaries you don't control, translate at the client, rescue domain errors in the service. For service-object structure, use skill: `rails-service-objects`.

### Sidekiq Retry Semantics

Sidekiq treats unhandled exceptions as "retry per the retry config". Honor the contract:

```ruby
class FulfillOrderJob
  include Sidekiq::Job
  sidekiq_options retry: 5, dead: true

  def perform(order_id)
    result = FulfillOrder.new(order_id: order_id).call
    return if result.success?

    case result.error_code
    when :not_found, :already_shipped
      # idempotent skip - do not retry
    when :payment_declined
      OrderMailer.payment_failed(order_id).deliver_later
      # business-level failure - do not retry
    else
      raise ApplicationError::ExternalUnavailable, result.error_message  # typed - sidekiq_retry_in can match the class
    end
  end
end
```

`rescue => e; logger.error(...)` in a job prevents retry and hides incidents. So do unbounded `retry`/`sleep` loops inside service code - retry belongs to Sidekiq, bounded and observable. If you swallow, document why and call the reporter explicitly. For per-item batch work, don't swallow per item silently: collect failures, report the batch summary, raise if everything failed.

### Boundary Translation

The client owns the SDK exception vocabulary; service code never names Faraday or Stripe:

```ruby
class BillingClient
  def capture!(charge_id)
    connection.post("/charges/#{charge_id}/capture").body
  rescue Faraday::TimeoutError, Faraday::ConnectionFailed => e
    raise BillingError::Unavailable, e.message
  rescue Faraday::ClientError => e
    case e.response&.dig(:status)
    when 402 then raise BillingError::Declined,  dig_message(e)
    when 404 then raise BillingError::NotFound,  dig_message(e)
    else          raise BillingError::Unexpected, dig_message(e)
    end
  end
end
```

Swapping Faraday for HTTPX or Stripe for Adyen does not ripple. A client-local namespace (`BillingError::Declined`) is fine - it is boundary vocabulary, named for the *capability*, not the vendor or SDK; each class still maps onto one caller-response category from the taxonomy. SDKs that raise one class for everything: branch on the error's `code`/`status` attribute the same way this example branches on HTTP status. Auth-expiry belongs to the client too - refresh and retry once inside the client, then translate to `Unavailable` if it still fails. For client structure, use skill: `rails-http-client-patterns`.

### Single-Source Reporting

Modern reporter gems self-wire: sentry-rails subscribes to `Rails.error` and captures unhandled controller errors; sentry-sidekiq captures job errors (configurable: every retry vs. retries-exhausted). Adding manual `Rails.error.subscribe(...)` or `Sentry.capture_exception` on top of that is the usual *cause* of duplicate alerts, not the fix.

- Default: zero manual capture calls. The middleware reports unhandled errors once at the terminal boundary (controller, job, rake).
- Manual capture is for errors you intentionally swallow: `Rails.error.handle(context: {...}) { ... }` (reports and suppresses) or `Rails.error.report(e)` - only at the layer that decided to swallow.
- Lower layers never call the reporter; `rescue_from`-handled 4xx domain errors are not reported at all.

## Output Format

One block per layer touched (a feature spanning client + service + job emits three). Fields that don't apply to a layer take `N/A`. In review mode, blocks describe the post-fix state, preceded by findings:

```
Layer: <controller | service | job | client | rake>
Rescue strategy: <Result on expected | raise on unexpected | mixed (justified)>
Domain errors: <ApplicationError::X | framework only>
SDK translation: <at boundary | leaked into service (FIX) | N/A>
rescue_from coverage: <listed classes | missing: ...>
Sidekiq retry: <propagate | swallow with reason | N/A>
Reporter call: <Rails.error / Sentry at <layer> | none | double-reported (FIX)>
```

## Avoid

- `rescue Exception` or bare `rescue` - swallows signals and shutdown errors
- Rescuing SDK errors in service code (`rescue Stripe::CardError`) - leaks vendor vocabulary upward
- Logging an error and continuing - either re-raise, return Result, or render a typed response
- `rescue_from StandardError` without re-raising after reporting - hides every bug
- Manual `Sentry.capture_exception` / `Rails.error.subscribe` alongside auto-wired reporter gems - duplicate alerts
- Unbounded `retry` or `sleep`-and-retry inside rescue blocks - infinite loops that hold a worker thread
- Bare `rescue => e; logger.error(...)` in a Sidekiq job - silently kills retry
