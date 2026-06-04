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
  rescue_from ActiveRecord::RecordNotFound,       with: :not_found
  rescue_from ActiveRecord::RecordInvalid,        with: :unprocessable
  rescue_from Pundit::NotAuthorizedError,         with: :forbidden
  rescue_from ApplicationError::NotFound,         with: :not_found
  rescue_from ApplicationError::ValidationFailed, with: :unprocessable
  rescue_from ApplicationError::PolicyDenied,     with: :forbidden

  private

  def not_found(e)     = render json: { error: e.message }, status: :not_found
  def forbidden(e)     = render json: { error: e.message }, status: :forbidden
  def unprocessable(e) = render json: { error: e.message, details: e.try(:record)&.errors },
                                status: :unprocessable_entity
end
```

Rails matches the **first** `rescue_from` whose class matches - narrow classes first, broad last. Don't `rescue_from StandardError` unless you also re-raise after reporting.

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
      raise result.error_message   # transient or unknown - let Sidekiq retry
    end
  end
end
```

`rescue => e; logger.error(...)` in a job prevents retry and hides incidents. If you swallow, document why and call the reporter explicitly.

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

Swapping Faraday for HTTPX or Stripe for Adyen does not ripple. For client structure, use skill: `rails-http-client-patterns`.

### Single-Source Reporting

```ruby
# config/initializers/error_reporting.rb
Rails.error.subscribe(Sentry::Rails::ErrorSubscriber.new)
```

Rails 7.0+ `Rails.error` is the unified hook. Call `Rails.error.handle(context: {...}) { ... }` at the boundary where the error becomes terminal (controller, job, rake). Lower layers don't call `Sentry.capture_exception` directly.

## Output Format

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
- Multiple `Sentry.capture_exception` calls in one error path - alert spam, harder to debug
- Bare `rescue => e; logger.error(...)` in a Sidekiq job - silently kills retry
