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
- Choosing between `Result` objects and raised exceptions in service code
- Sidekiq job error handling (retry vs swallow)
- Translating third-party SDK errors at a boundary
- Reviewing for bare `rescue`, `rescue Exception`, or logged-and-swallowed errors

## Rules

- One application-wide rescue ladder lives in `ApplicationController#rescue_from`; controllers don't catch their own.
- Domain errors inherit from a single app-level base (`ApplicationError` or `AppName::Error`) so they can be rescued as a group.
- Service objects: return `Result` for expected failures (validation, not-found, policy denial); raise for programmer errors and unexpected state.
- Sidekiq jobs: rescue domain errors that should not retry; let everything else propagate so Sidekiq's retry kicks in.
- External SDK errors get translated at the boundary (`app/clients/`) - business logic rescues domain errors, never `Faraday::Error` or `Stripe::Error`.
- No bare `rescue` or `rescue Exception` - both swallow `SignalException`, `SystemExit`, `NoMemoryError`. `rescue => e` catches `StandardError`, which is what you mean.
- Every `rescue` either re-raises, returns a typed Result, or renders a documented response - never logs and continues silently.
- The error reporter (Sentry/Honeybadger/Bugsnag) is invoked once per error, at the highest sensible boundary (controller, job, rake). Lower layers do not double-report.

## Patterns

### Application Rescue Ladder

```ruby
class ApplicationController < ActionController::API
  rescue_from ActiveRecord::RecordNotFound,     with: :not_found
  rescue_from ActiveRecord::RecordInvalid,      with: :unprocessable
  rescue_from Pundit::NotAuthorizedError,       with: :forbidden
  rescue_from ApplicationError::NotFound,       with: :not_found
  rescue_from ApplicationError::ValidationFailed, with: :unprocessable
  rescue_from ApplicationError::PolicyDenied,   with: :forbidden

  private

  def not_found(e)      = render json: { error: e.message }, status: :not_found
  def forbidden(e)      = render json: { error: e.message }, status: :forbidden
  def unprocessable(e)  = render json: { error: e.message, details: e.try(:record)&.errors }, status: :unprocessable_entity
end
```

Order matters - Rails matches the **first** `rescue_from` whose class matches. Put narrow classes first, broad classes (`StandardError`) last. Don't `rescue_from StandardError` unless you also re-raise after reporting.

### Domain Error Taxonomy

```ruby
# app/errors/application_error.rb
class ApplicationError < StandardError
  class NotFound          < self; end
  class ValidationFailed  < self
    attr_reader :details
    def initialize(message, details: {}) = (@details = details; super(message))
  end
  class PolicyDenied      < self; end
  class ExternalUnavailable < self; end
  class IdempotencyConflict < self; end
end
```

Group by **how the caller responds**, not by where the error originated. `BillingError`, `PaymentError`, `StripeError` is the wrong axis - the caller cares about "validation", "transient", "policy", "not found".

### Result vs Raise

| Outcome                                | Mechanism | Why                                            |
| -------------------------------------- | --------- | ---------------------------------------------- |
| User-input validation failure          | `Result`  | Caller renders the error; not exceptional      |
| Not found by a user-facing lookup      | `Result`  | Expected branch; caller chooses 404 vs default |
| Pundit/policy denial                   | Either    | Raise if controller catches; Result if service composes |
| Programmer error (nil where none allowed) | Raise   | Bug - fail fast, surface in error reporter     |
| External service down                  | Raise (translated) | Job retry / boundary handles; caller cannot recover inline |
| DB constraint violation we expected    | `Result`  | Race outcome - convert `RecordNotUnique` to Result |

```ruby
class FulfillOrder
  def call
    return Result.failure(:not_found) unless @order
    return Result.failure(:already_shipped) if @order.shipped?

    Billing::Client.capture!(@order.charge_id)  # raises BillingError::Declined (translated)
    @order.update!(status: :shipped)
    Result.success(@order)
  rescue BillingError::Declined => e
    Result.failure(:payment_declined, e.message)
  end
end
```

Raise across the boundary you don't control (Stripe), translate at the client, rescue domain errors in the service.

### Sidekiq Retry Semantics

Sidekiq treats an unhandled exception as "retry per the retry config". This is the contract - don't fight it:

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
      raise result.error_message    # transient or unknown - let Sidekiq retry
    end
  end
end
```

Bare `rescue => e; logger.error(...)` prevents retry and hides incidents. If you swallow, document why in the catch and call the reporter explicitly.

### Boundary Translation

The HTTP client owns the SDK exception vocabulary:

```ruby
class BillingClient
  def capture!(charge_id)
    response = connection.post("/charges/#{charge_id}/capture")
    response.body
  rescue Faraday::TimeoutError, Faraday::ConnectionFailed => e
    raise BillingError::Unavailable, e.message
  rescue Faraday::ClientError => e
    case e.response&.dig(:status)
    when 402 then raise BillingError::Declined, dig_message(e)
    when 404 then raise BillingError::NotFound,  dig_message(e)
    else          raise BillingError::Unexpected, dig_message(e)
    end
  end
end
```

Service code now rescues `BillingError::*` - swapping Faraday for HTTPX, or Stripe for Adyen, does not ripple.

### Error Reporting Single Source

```ruby
# config/initializers/error_reporting.rb
Rails.error.subscribe(Sentry::Rails::ErrorSubscriber.new)
```

Rails 7.0+'s `Rails.error` is the unified hook. Use `Rails.error.handle(context: {...}) { ... }` at the boundary where the error becomes terminal (controller, job, rake). Lower layers do not call `Sentry.capture_exception` directly - leads to double-reporting and noisy alerts.

## Output Format

When designing or reviewing exception handling:

```
Layer: <controller | service | job | client | rake>
Rescue strategy: <Result on expected | raise on unexpected | mixed (justified)>
Domain errors: <ApplicationError::X | none - using framework errors only>
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
- Treating a `Result.failure` as if it were a successful call - always branch on `.success?`
- Bare `rescue => e; logger.error(...)` in a Sidekiq job - silently kills retry, masks incidents
