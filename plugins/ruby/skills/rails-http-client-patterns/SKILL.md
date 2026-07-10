---
name: rails-http-client-patterns
description: Rails HTTP clients with Faraday + Retriable: timeouts, idempotent retries, domain error taxonomy, circuit breakers, WebMock/VCR.
metadata:
  category: backend
  tags: [ruby, rails, faraday, retriable, http, integration]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building a client wrapper for a third-party API
- Adding retries / backoff to an existing integration
- Diagnosing flaky calls, timeout creep, retry storms
- Deciding what to retry, surface as permanent, or push to Sidekiq

Scoped to **Faraday 2+ / Retriable**. For `httpx` / `http.rb` / raw `Net::HTTP`, adapt the principles; code shapes assume Faraday.

## Rules

- Every outbound call has explicit `open_timeout` and `timeout`.
- Credentials travel in headers, never query strings - URLs land in logs, audit rows, and proxies.
- Retry idempotent verbs (`GET HEAD PUT DELETE`) by default; retry `POST` only when `Idempotency-Key` is present.
- Bounded in-process retry: <=3 attempts, exponential backoff with jitter. Long waits live in Sidekiq.
- Every external call goes through a client class - never `Faraday.get` from services or controllers.
- Translate transport / HTTP errors into a domain taxonomy at the client boundary. Callers rescue domain errors only.
- No live HTTP in CI - stub at the boundary (WebMock or VCR), not both per spec.

## Patterns

### Client Class

```ruby
# app/clients/shipper_client.rb
class ShipperClient
  Error           = Class.new(StandardError)
  TransientError  = Class.new(Error)        # safe to retry
  PermanentError  = Class.new(Error)        # do not retry
  RateLimitError  = Class.new(TransientError)
  AuthError       = Class.new(PermanentError)
  NotFoundError   = Class.new(PermanentError)
  ValidationError = Class.new(PermanentError)

  def initialize(token: ENV.fetch("SHIPPER_TOKEN"), connection: nil)
    @connection = connection || build_connection(token)
  end

  def create_shipment(order_id:, idempotency_key:)
    response = @connection.post("shipments") do |req|
      req.headers["Idempotency-Key"] = idempotency_key
      req.body = { order_id: order_id }
    end
    response.body
  rescue Faraday::ConnectionFailed, Faraday::TimeoutError => e
    raise TransientError, e.message
  rescue Faraday::ClientError => e
    raise translate(e)
  rescue Faraday::ServerError => e
    raise TransientError, e.message
  end

  private

  def build_connection(token)
    Faraday.new(url: "https://api.shipper.com/v1/") do |f|
      f.request  :json
      f.request  :authorization, "Bearer", token
      f.response :raise_error
      f.response :json, content_type: /\bjson$/
      f.response :logger, Rails.logger, headers: false, bodies: false
      f.options.open_timeout = 2
      f.options.timeout      = 5
      f.adapter Faraday.default_adapter
    end
  end

  def translate(error)
    case error.response_status
    when 401, 403 then AuthError.new("auth failed")
    when 404      then NotFoundError.new("not found")
    when 408, 429 then RateLimitError.new("retry-after=#{error.response_headers&.dig('retry-after')}")
    when 422      then ValidationError.new(error.response_body.to_s)
    else               PermanentError.new("rejected: #{error.response_status}")
    end
  end
end
```

Expiring tokens (OAuth, 12h bearers): the client owns the refresh - cache the token (TTL slightly under its lifetime), and on 401 refresh once and retry once before raising `AuthError`. A 401 is only *permanent* after a fresh token also failed.

One client serving both web and Sidekiq callers keeps the connection default at the web budget and overrides per call (`req.options.timeout = 15`) on job-path operations - don't build two clients.

Callers consume domain errors only:

```ruby
class FulfillOrder
  def call
    payload = ShipperClient.new.create_shipment(order_id: @order.id,
                                                idempotency_key: "fulfill-#{@order.id}-#{@order.fulfillment_attempt}")
    Result.success(payload)
  rescue ShipperClient::PermanentError => e
    Result.failure(:shipper_rejected, e.message)
  rescue ShipperClient::TransientError
    raise  # let Sidekiq retry
  end
end
```

Rescuing `Faraday::Error` in a service couples business logic to the transport. The Transient/Permanent split is the contract: Sidekiq retries transient; permanent becomes a 4xx via `Result.failure`. For full translation patterns, use skill: `rails-exception-handling`.

### Timeouts

| Timeout        | Default  | Recommended | Notes                                              |
| -------------- | -------- | ----------- | -------------------------------------------------- |
| `open_timeout` | infinite | 1-2s        | TCP connect + TLS - slow connect signals dead host |
| `timeout`      | infinite | 3-10s       | Total request after connect                        |

Web request path: external timeout < remaining request budget; stay under 5s and push longer work to Sidekiq. Sidekiq path: 10-30s is fine.

### Middleware Order

Request middleware runs top-down, response bottom-up (last-registered response middleware runs first). Common breakages:

- Registering `:json` (response) before `:raise_error` -> `raise_error` runs first and the raised error carries an unparsed body. Register `:raise_error` above `:json`, as in the client above.
- `:json` (request) skips `String` bodies - pass hashes; a pre-serialized string silently bypasses encoding and content-type.
- `:logger` with `bodies: true` in production -> leaks tokens / PII.

### Retry Strategy

Faraday's built-in `:retry` is idempotency-aware:

```ruby
f.request :retry,
  max: 2, interval: 0.5, interval_randomness: 0.5, backoff_factor: 2,
  methods:        %i[get head put delete],
  retry_statuses: [408, 429, 500, 502, 503, 504],
  exceptions:     [Faraday::ConnectionFailed, Faraday::TimeoutError],
  retry_if:       ->(env, _) { env.request_headers["Idempotency-Key"].present? }
```

`retry_if` opts `POST` back in only when `Idempotency-Key` is present - required for Stripe-style APIs.

`Retry-After` on 429: faraday-retry honors the header when the wait fits the in-process budget; longer waits re-raise as `RateLimitError` and Sidekiq reschedules. Make the seconds machine-readable - `translate` parses the header into the error (`RateLimitError.new(retry_after: ...)`), and `sidekiq_retry_in` returns `exception.retry_after` plus jitter (`+ rand(10)`) so recovering jobs don't re-herd. Hard quotas (60/min per token) need proactive throttling - a token bucket or low-concurrency queue (see `rails-work-splitter-patterns`) - reactive 429 handling alone herds.

| Layer             | Count | Backoff       | When                                            |
| ----------------- | ----- | ------------- | ----------------------------------------------- |
| Faraday `:retry`  | 2-3   | <5s total     | Transient blips during one request              |
| Retriable wrapper | 2-3   | <30s total    | Cross-call retry in a Sidekiq job; non-Faraday  |
| Sidekiq retry     | 5-25  | minutes-hours | Anything that needs to wait out an outage       |
| Don't retry       | -     | -             | 4xx other than 408/429; POST without key        |

Stacking all three compounds wait time unpredictably. Inside a Sidekiq job, prefer Sidekiq's retry over wrapping in Retriable.

### Circuit Breaker

In-process retries during a sustained outage make the outage worse. Trip after N consecutive failures and short-circuit:

```ruby
require "stoplight"

def create_shipment(order_id:, idempotency_key:)
  Stoplight("shipper.create_shipment") do
    @connection.post("shipments") { |req| ... }.body
  end.with_threshold(5).with_cool_off_time(60).run
end
```

Use when synchronous on the request path (outages cascade into Puma worker exhaustion), volume >10 req/s sustained, or upstream has documented SLOs. Low-volume background work doesn't need one.

Two decisions the breaker forces on the caller:

- **Open-circuit fallback** - decide fail-open vs fail-closed per call site: serve a cached/last-known value (rate quotes, display data), defer to Sidekiq (notifications), or fail the operation (anything moving money - never default to `0.0`-style sentinel values).
- **Recovery herd** - when the breaker closes after an outage, queued Sidekiq retries plus live traffic fire at once and re-trip the partner's rate limit. Stagger re-entry: jittered `sidekiq_retry_in`, and keep the breaker's threshold low enough to re-open fast if recovery is partial.

### Logging

Boundary calls are the line you grep during incidents. Capture method, host, path (not full URL - tokens hide in query strings), status, duration, request ID:

```ruby
ActiveSupport::Notifications.subscribe("request.faraday") do |_, start, finish, _, env|
  Rails.logger.info(event: "http_client", host: env[:url].host, path: env[:url].path,
                    method: env[:method], status: env[:status],
                    duration_ms: ((finish - start) * 1000).round,
                    request_id: env.request_headers["X-Request-Id"])
end
# Wire on the connection:
f.use :instrumentation
```

### Webhooks (inbound)

Verify signature **before** parsing the body. Persist `webhook_events(provider, event_id)` with a unique index for replay protection. Respond 200 quickly; dispatch work to Sidekiq. For signature verification, use skill: `rails-security-patterns`.

### Testing

WebMock for client unit specs; VCR for service / request specs. One per spec - mixing cassettes and ad-hoc stubs is confusing.

```ruby
# WebMock - client unit
RSpec.describe ShipperClient do
  it "raises RateLimitError on 429" do
    stub_request(:post, /shipper.com/).to_return(status: 429)
    expect { described_class.new.create_shipment(order_id: 7, idempotency_key: "k") }
      .to raise_error(ShipperClient::RateLimitError)
  end
end

# VCR - service-level
VCR.configure do |c|
  c.filter_sensitive_data("<SHIPPER_TOKEN>") { ENV["SHIPPER_TOKEN"] }
  c.filter_sensitive_data("<IDEMPOTENCY_KEY>") { |i| i.request.headers["Idempotency-Key"]&.first }
end
```

## Output Format

In review mode, precede the block with numbered findings citing the violated rule; the block describes the corrected client.

```
Client: {ClassName}
Base URL: {url}
Auth: {Bearer | API key header | OAuth (refresh: cached TTL + once-on-401)}
Timeouts: open={Ns}, total={Ns} (+ per-call overrides for job-path ops)
Retry: {faraday | retriable | none}, max={N}, backoff={strategy}
Idempotency: {how POST/PATCH replay safety is achieved}
Error taxonomy: {domain error classes}
Circuit breaker: {none (justified) | Stoplight threshold/cool-off; open-circuit fallback per call site}
Tests: {WebMock unit | VCR cassettes - file paths}
```

## Avoid

- Stacking retry layers (Faraday + Retriable + Sidekiq) - wait times compound unpredictably
- Circuit breakers on every integration - reserve for high-volume request-path calls
- Rescuing `Faraday::Error` in services - couples business logic to the transport
- Retrying 4xx other than 408 / 429
- Full URLs in logs - query string tokens leak
