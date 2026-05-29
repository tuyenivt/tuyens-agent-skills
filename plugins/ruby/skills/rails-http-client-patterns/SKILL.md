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

Scoped to **Faraday + Retriable**. For `httpx` / `http.rb` / raw `Net::HTTP`, adapt the principles - the code shapes assume Faraday.

## Rules

- Every outbound call has explicit `open_timeout` and `timeout`
- Retry idempotent verbs (`GET HEAD PUT DELETE`) by default; `POST` only when `Idempotency-Key` is present
- Bounded in-process retry: ≤3 attempts, exponential backoff with jitter; longer waits live in Sidekiq
- Every external call goes through a client class - never `Faraday.get` from services / controllers
- Translate transport / HTTP errors into a domain taxonomy at the client boundary; callers rescue domain errors only
- Never log full URLs, request/response bodies, or `Authorization` headers
- No live HTTP in CI - stub at the boundary (WebMock or VCR)

## Patterns

### Client Class

```ruby
# app/clients/shipper_client.rb
class ShipperClient
  Error           = Class.new(StandardError)
  TransientError  = Class.new(Error)   # safe to retry
  PermanentError  = Class.new(Error)   # do not retry
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
      f.response :json, content_type: /\bjson$/
      f.response :raise_error
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
    when 408, 429 then RateLimitError.new("rate limited; retry-after=#{error.response_headers&.dig('retry-after')}")
    when 422      then ValidationError.new(error.response_body.to_s)
    else               PermanentError.new("rejected: #{error.response_status}")
    end
  end
end
```

```ruby
# Service consumes the client and rescues domain errors only
class FulfillOrder
  def call
    payload = ShipperClient.new.create_shipment(
      order_id: @order.id,
      idempotency_key: "fulfill-#{@order.id}-#{@order.fulfillment_attempt}"
    )
    Result.success(payload)
  rescue ShipperClient::PermanentError => e
    Result.failure(:shipper_rejected, e.message)
  rescue ShipperClient::TransientError
    raise  # let Sidekiq retry
  end
end
```

The TransientError vs PermanentError split is the contract: Sidekiq propagates transient; permanent becomes `Result.failure` -> 4xx in controllers. Rescuing `Faraday::Error` in a service couples business logic to the HTTP library.

### Timeouts

| Timeout        | Default  | Recommended | Notes                            |
| -------------- | -------- | ----------- | -------------------------------- |
| `open_timeout` | infinite | 1-2s        | TCP connect + TLS - slow connect signals dead host |
| `timeout`      | infinite | 3-10s       | Total request after connect      |

Web request path: external timeout < remaining request budget; stay under 5s and push longer work to Sidekiq. Sidekiq path: 10-30s is fine.

### Middleware Stack

Order matters - request middleware runs top-down, response bottom-up. Common mistakes:

- `:json` placed after the body is already a string -> double-encodes
- `:raise_error` before `:json` response middleware -> raised error has unparsed body
- `:logger` with `bodies: true` in production -> leaks tokens / PII

### Retry Strategy

Faraday's built-in `:retry` is idempotency-aware:

```ruby
retry_options = {
  max:                 2,
  interval:            0.5,
  interval_randomness: 0.5,
  backoff_factor:      2,
  methods:             %i[get head put delete],
  retry_statuses:      [408, 429, 500, 502, 503, 504],
  exceptions:          [Faraday::ConnectionFailed, Faraday::TimeoutError],
  retry_if:            ->(env, _exc) { env.request_headers["Idempotency-Key"].present? }
}

f.request :retry, retry_options
```

`retry_if` opts `POST` back in only when `Idempotency-Key` is present - the correct way to retry creates without duplicates. Stripe-style APIs require this header.

Reach for `retriable` only when retry must span beyond a single Faraday request (multi-step flow, non-Faraday call). Inside Sidekiq, prefer Sidekiq's retry - stacking layers compounds wait time unpredictably.

| Layer             | Count  | Backoff       | When                                                |
| ----------------- | ------ | ------------- | --------------------------------------------------- |
| Faraday `:retry`  | 2-3    | <5s total     | Transient network blips during one request          |
| Retriable wrapper | 2-3    | <30s total    | Cross-call retry in a Sidekiq job; non-Faraday call |
| Sidekiq retry     | 5-25   | minutes-hours | Anything that needs to wait out an outage           |
| Don't retry       | -      | -             | 4xx other than 408/429; non-idempotent POST without a key |

### Circuit Breaker

In-process retries during a sustained outage make the outage worse. Trip after N consecutive failures and short-circuit for a cooldown:

```ruby
require "stoplight"

def create_shipment(order_id:, idempotency_key:)
  Stoplight("shipper.create_shipment") do
    @connection.post("shipments") { |req| ... }.body
  end.with_threshold(5).with_cool_off_time(60).run
end
```

Reach for one when synchronous on the request path (outages cascade into Puma worker exhaustion), volume >10 req/s sustained, or upstream has documented SLOs. Low-volume background work doesn't need it - Sidekiq's retry + dead set is sufficient.

### Logging

The boundary call is the line you grep during an incident. Capture method, host, path (not full URL - tokens hide in query strings), status, duration, request ID:

```ruby
ActiveSupport::Notifications.subscribe("request.faraday") do |_, start, finish, _, env|
  Rails.logger.info(
    event: "http_client", host: env[:url].host, path: env[:url].path,
    method: env[:method], status: env[:status],
    duration_ms: ((finish - start) * 1000).round,
    request_id: env.request_headers["X-Request-Id"]
  )
end

# Wire it on the connection:
f.use :instrumentation
```

### Webhooks (inbound)

Verify signature **before** parsing the body. Persist `webhook_events(provider, event_id)` with a unique index for replay protection. Respond 200 quickly; dispatch work to Sidekiq. See `rails-security-patterns` for signature verification.

### Testing

```ruby
# WebMock - client unit
RSpec.describe ShipperClient do
  it "returns parsed response on 201" do
    stub_request(:post, "https://api.shipper.com/v1/shipments")
      .with(headers: { "Idempotency-Key" => "key-1" })
      .to_return(status: 201, body: { id: "shp_123" }.to_json,
                 headers: { "Content-Type" => "application/json" })
    expect(described_class.new.create_shipment(order_id: 7, idempotency_key: "key-1"))
      .to eq("id" => "shp_123")
  end

  it "raises RateLimitError on 429" do
    stub_request(:post, /shipper.com/).to_return(status: 429)
    expect { described_class.new.create_shipment(order_id: 7, idempotency_key: "key-1") }
      .to raise_error(ShipperClient::RateLimitError)
  end
end

# VCR - service-level
RSpec.describe FulfillOrder, vcr: { cassette_name: "fulfill_order/success" } do
  it "fulfills the order" do
    expect(described_class.new(order: order).call).to be_success
  end
end

VCR.configure do |c|
  c.filter_sensitive_data("<SHIPPER_TOKEN>") { ENV["SHIPPER_TOKEN"] }
  c.filter_sensitive_data("<IDEMPOTENCY_KEY>") { |i| i.request.headers["Idempotency-Key"]&.first }
end
```

WebMock for client unit specs; VCR for service / request specs that exercise the integration. One per spec - cassettes + ad-hoc stubs interact confusingly.

## Output Format

```
Client: {ClassName}
Base URL: {url}
Auth: {Bearer | API key header | OAuth}
Timeouts: open={Ns}, total={Ns}
Retry: {faraday | retriable | none}, max={N}, backoff={strategy}
Idempotency: {how POST/PATCH replay safety is achieved}
Error taxonomy: {domain error classes}
Tests: {WebMock unit specs | VCR cassettes - file paths}
```

## Avoid

- Stacking retry layers (Faraday + Retriable + Sidekiq) - wait times compound unpredictably
- Circuit breakers on every integration - reserve for high-volume request-path calls
- Rescuing `Faraday::Error` in services - couples business logic to the transport
- Retrying 4xx other than 408 / 429
- Full URLs in logs - query string tokens leak
