---
name: rails-http-client-patterns
description: Rails HTTP client patterns with Faraday/Retriable: timeouts, retry budgets, error taxonomy, circuit breaking, VCR/WebMock testing.
metadata:
  category: backend
  tags: [ruby, rails, faraday, retriable, http, integration]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building a client wrapper for a third-party API (payments, email, search, CRM, internal services)
- Adding retries and backoff to an existing HTTP integration
- Diagnosing flaky external calls, timeout creep, or retry-storm incidents
- Deciding what to retry, what to surface as a permanent error, and what to push to a Sidekiq retry
- Setting up VCR / WebMock fixtures for an external boundary

This skill is scoped to **Faraday + Retriable** specifically - the dominant pairing in modern Rails apps. Projects using `httpx`, `http.rb`, or raw `Net::HTTP` should adapt the principles (timeouts, idempotency-aware retries, error taxonomy) but the code shapes here assume Faraday.

## Rules

- Every outbound call has explicit `open_timeout` and `timeout`; never rely on defaults
- Only retry **idempotent** verbs (`GET`, `HEAD`, `PUT`, `DELETE`) by default; `POST` retries require an idempotency key or server-confirmed safety
- Retry budget is bounded - max 3 in-process attempts, exponential backoff with jitter; longer waits belong in Sidekiq
- Wrap every external call in a client class; controllers and services never call `Faraday.get` directly
- Translate transport / HTTP errors into a domain error taxonomy at the client boundary
- Never log full request/response bodies - they leak PII, tokens, and webhook secrets; log status, duration, request ID, and a redacted summary
- All tests stub the network at the boundary (VCR cassettes or `WebMock.stub_request`) - no live HTTP in CI

## Patterns

### Client Class Wrapper

Bad - service calls Faraday directly, mixes HTTP concerns with business logic:

```ruby
class CreateShipment
  def call(order)
    response = Faraday.post("https://api.shipper.com/shipments") do |req|
      req.headers["Authorization"] = "Bearer #{ENV['SHIPPER_TOKEN']}"
      req.body = { order_id: order.id }.to_json
    end
    Result.success(JSON.parse(response.body))
  end
end
```

Good - dedicated client encapsulates connection, auth, error mapping; service consumes a typed result:

```ruby
# app/clients/shipper_client.rb
class ShipperClient
  Error            = Class.new(StandardError)
  TransientError   = Class.new(Error) # safe to retry
  PermanentError   = Class.new(Error) # do not retry
  RateLimitError   = Class.new(TransientError)
  NotFoundError    = Class.new(PermanentError)

  def initialize(token: ENV.fetch("SHIPPER_TOKEN"), connection: nil)
    @connection = connection || build_connection(token)
  end

  def create_shipment(order_id:, idempotency_key:)
    response = @connection.post("shipments") do |req|
      req.headers["Idempotency-Key"] = idempotency_key
      req.body = { order_id: order_id }
    end
    response.body
  end

  private

  def build_connection(token)
    Faraday.new(url: "https://api.shipper.com/v1/") do |f|
      f.request  :json
      f.request  :authorization, "Bearer", token
      f.response :json, content_type: /\bjson$/
      f.response :raise_error          # raise on 4xx/5xx
      f.response :logger, Rails.logger, headers: false, bodies: false
      f.options.open_timeout = 2       # TCP connect
      f.options.timeout      = 5       # full request
      f.adapter Faraday.default_adapter
    end
  end
end
```

The service consumes the client and handles the typed error taxonomy:

```ruby
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
    raise # let Sidekiq retry
  end
end
```

### Timeouts

Two distinct timeouts; both must be set explicitly:

| Timeout        | Default  | Recommended | What It Bounds                       |
| -------------- | -------- | ----------- | ------------------------------------ |
| `open_timeout` | infinite | 1-2s        | TCP connect + TLS handshake          |
| `timeout`      | infinite | 3-10s       | Total request duration after connect |

Rules of thumb:

- **Web request path**: total external timeout < remaining request budget. If your Puma worker timeout is 15s and you've already spent 3s, an 8s external call is reckless. Stay under 5s, push longer work to Sidekiq.
- **Sidekiq job path**: can afford 10-30s; jobs survive slow upstreams better than web requests.
- **Connect timeout < total timeout**: a slow connect is almost always a dead host; fail fast (1-2s) and let retries handle it.

### Faraday Middleware Stack

Order matters - middleware runs top-down on request, bottom-up on response. A correct stack for a JSON API:

```ruby
Faraday.new(url: base_url) do |f|
  # --- Request middleware (top-down) ---
  f.request :json                                    # serializes hash body to JSON
  f.request :authorization, "Bearer", token          # adds auth header
  f.request :retry, retry_options                    # in-process retry (see below)

  # --- Response middleware (bottom-up) ---
  f.response :json, content_type: /\bjson$/          # parses JSON body
  f.response :raise_error                            # raises Faraday::ClientError / ServerError
  f.response :logger, Rails.logger,                  # logs after parse so we see status + duration
             headers: false, bodies: false           # never log bodies in production

  f.adapter Faraday.default_adapter                   # net_http unless project uses typhoeus/excon
end
```

Common mistakes:

- `:json` request middleware after the body is already a string - it double-encodes
- `:raise_error` before `:json` response middleware - the raised error has unparsed body
- `:logger` with `bodies: true` in production - leaks tokens and PII

### Retry Strategy

Retries are a **distributed-systems concern, not a convenience.** A naive retry loop turns a brief upstream blip into a thundering herd that prevents recovery. Apply with care.

**Use Faraday's built-in `:retry` middleware for in-process retries** - it ships with idempotency awareness, exponential backoff, and jitter:

```ruby
retry_options = {
  max:                 2,                                  # 2 retries = 3 total attempts
  interval:            0.5,                                # base delay (seconds)
  interval_randomness: 0.5,                                # ±50% jitter
  backoff_factor:      2,                                  # exponential: 0.5s, 1s, 2s
  methods:             %i[get head put delete],            # idempotent only by default
  retry_statuses:      [408, 429, 500, 502, 503, 504],
  exceptions:          [Faraday::ConnectionFailed, Faraday::TimeoutError],
  retry_if:            ->(env, _exc) { env.request_headers["Idempotency-Key"].present? }
}

f.request :retry, retry_options
```

The `retry_if` callback opts `POST` back in **only** when an `Idempotency-Key` is present - this is the correct way to retry creates without risking duplicates. Stripe-style APIs require this header for exactly this reason.

**Use `retriable` for retries that span beyond a single Faraday request** - e.g., a multi-step flow where you retry the whole transaction, or a non-Faraday call:

```ruby
require "retriable"

Retriable.retriable(
  on: [ShipperClient::TransientError, Faraday::TimeoutError],
  tries: 3,
  base_interval: 0.5,
  multiplier: 2.0,
  rand_factor: 0.5
) do
  ShipperClient.new.create_shipment(...)
end
```

Use Retriable sparingly inside web requests - it can blow your request budget. Inside Sidekiq jobs it's fine, but consider: if the work is in a job, **let Sidekiq do the retry** instead. Two retry layers (Retriable inside, Sidekiq outside) compound and produce surprise wait times.

**Retry decision matrix:**

| Layer                   | Retry Count | Backoff       | When to Use                                                            |
| ----------------------- | ----------- | ------------- | ---------------------------------------------------------------------- |
| Faraday `:retry`        | 2-3         | <5s total     | Transient network blips during a single request                        |
| Retriable wrapper       | 2-3         | <30s total    | Cross-call retry inside a Sidekiq job; non-Faraday client              |
| Sidekiq job retry       | 5-25        | minutes-hours | Anything that genuinely needs to wait out an outage                    |
| Don't retry             | -           | -             | 4xx other than 408/429; permanent errors; non-idempotent without a key |

### Error Taxonomy

The client must translate the wire-level zoo (`Faraday::ConnectionFailed`, `Faraday::TimeoutError`, `Faraday::ClientError`, `Faraday::ServerError`) into a small domain taxonomy. Callers should never `rescue Faraday::Error` - that couples every service to the HTTP library.

```ruby
class ShipperClient
  Error          = Class.new(StandardError)
  TransientError = Class.new(Error)   # caller may retry (network, 5xx, 429, 408)
  PermanentError = Class.new(Error)   # caller must not retry (4xx other than 408/429)
  RateLimitError = Class.new(TransientError)  # carries Retry-After
  AuthError      = Class.new(PermanentError)  # 401/403 - check credentials
  NotFoundError  = Class.new(PermanentError)
  ValidationError = Class.new(PermanentError) # 422 - bad input

  def create_shipment(...)
    response = @connection.post("shipments") { |req| ... }
    response.body
  rescue Faraday::ConnectionFailed, Faraday::TimeoutError => e
    raise TransientError, e.message
  rescue Faraday::ClientError => e
    raise translate_client_error(e)
  rescue Faraday::ServerError => e
    raise TransientError, e.message
  end

  private

  def translate_client_error(error)
    case error.response_status
    when 401, 403 then AuthError.new("shipper auth failed")
    when 404      then NotFoundError.new("shipment not found")
    when 408, 429 then RateLimitError.new("rate limited; retry-after=#{error.response_headers&.dig('retry-after')}")
    when 422      then ValidationError.new(error.response_body.to_s)
    else               PermanentError.new("shipper rejected: #{error.response_status}")
    end
  end
end
```

The dividing line is **TransientError vs PermanentError**. Sidekiq retries propagate transient errors; permanent errors should be caught and converted to a `Result.failure` that the controller maps to a 4xx.

### Circuit Breaker Posture

For high-volume integrations, in-process retries during a sustained outage make the outage worse. A circuit breaker (e.g., `stoplight`, `circuitbox`) trips after N consecutive failures and short-circuits subsequent calls for a cooldown:

```ruby
require "stoplight"

def create_shipment(order_id:, idempotency_key:)
  Stoplight("shipper.create_shipment") do
    @connection.post("shipments") { |req| ... }.body
  end.with_threshold(5).with_cool_off_time(60).run
end
```

Apply circuit breakers selectively - they add operational complexity (alerts, dashboards, manual reset). Reach for one when:

- The integration is **synchronous on the request path** and an outage cascades into Puma worker exhaustion
- Call volume is high enough that retry storms are a real risk (>10 req/s sustained)
- The upstream has documented availability SLOs you're already monitoring

For low-volume background work, Sidekiq's retry + dead set is sufficient.

### Logging and Observability

The boundary call is the highest-value log line in the system - it's the one you'll grep during an incident. Capture:

- Method, host, path (not full URL with query string - tokens leak)
- Status code
- Duration (Faraday's `:logger` doesn't include this; add a custom middleware or use `:instrumentation`)
- Request ID (forward `X-Request-Id` from the inbound request for trace correlation)
- Outcome (`success` / `transient_error` / `permanent_error`)

```ruby
# config/initializers/faraday_instrumentation.rb
ActiveSupport::Notifications.subscribe("request.faraday") do |name, start, finish, _id, env|
  duration_ms = ((finish - start) * 1000).round
  Rails.logger.info(
    event: "http_client",
    host: env[:url].host,
    path: env[:url].path,
    method: env[:method],
    status: env[:status],
    duration_ms: duration_ms,
    request_id: env.request_headers["X-Request-Id"]
  )
end

# In the connection:
f.use :instrumentation
```

**Never** log:

- Full URL (query strings carry tokens)
- Request bodies (often contain PII or secrets)
- Response bodies (same; also large)
- `Authorization` headers

### Webhook Handling (inbound)

Inbound webhooks share the retry/idempotency story: verify signature **before** parsing the body, persist `webhook_events(provider, event_id)` with a unique index for replay protection, respond `200` quickly and dispatch real work to a Sidekiq job. See `rails-security-patterns` for signature verification.

### Testing

The contract is: **no live HTTP in CI, ever.** Two boundary-stubbing tools:

**WebMock** for unit-level client tests where you control the exact request shape:

```ruby
RSpec.describe ShipperClient do
  describe "#create_shipment" do
    it "returns the parsed response on 201" do
      stub_request(:post, "https://api.shipper.com/v1/shipments")
        .with(headers: { "Idempotency-Key" => "key-1" })
        .to_return(status: 201, body: { id: "shp_123" }.to_json,
                   headers: { "Content-Type" => "application/json" })

      result = described_class.new.create_shipment(order_id: 7, idempotency_key: "key-1")
      expect(result).to eq("id" => "shp_123")
    end

    it "raises RateLimitError on 429" do
      stub_request(:post, /shipper.com/).to_return(status: 429)
      expect {
        described_class.new.create_shipment(order_id: 7, idempotency_key: "key-1")
      }.to raise_error(ShipperClient::RateLimitError)
    end
  end
end
```

**VCR** for integration-level tests where you record one real interaction and replay it:

```ruby
RSpec.describe FulfillOrder, vcr: { cassette_name: "fulfill_order/success" } do
  it "fulfills the order" do
    result = described_class.new(order: order).call
    expect(result).to be_success
  end
end
```

Configure VCR to filter sensitive data:

```ruby
VCR.configure do |c|
  c.filter_sensitive_data("<SHIPPER_TOKEN>") { ENV["SHIPPER_TOKEN"] }
  c.filter_sensitive_data("<IDEMPOTENCY_KEY>") do |interaction|
    interaction.request.headers["Idempotency-Key"]&.first
  end
end
```

Use one or the other per spec, not both - cassettes plus stubs interact in confusing ways. Default to WebMock for client specs and VCR for happy-path service/request specs that exercise the full integration.

## Output Format

When generating an HTTP client, document:

```
Client: {ClassName}
Base URL: {url}
Auth: {Bearer token / API key header / OAuth}
Timeouts: open={Ns}, total={Ns}
Retry: {layer (faraday/retriable/none)}, max={N}, backoff={strategy}
Idempotency: {how POST/PATCH replay safety is achieved}
Error taxonomy: {list of domain error classes mapped from HTTP statuses}
Tests: {WebMock unit specs / VCR cassettes - file paths}
```

## Avoid

- Calling `Faraday.get` / `Faraday.post` directly from services or controllers - always go through a client class
- Default (infinite) timeouts - every connection must set `open_timeout` and `timeout`
- Retrying `POST` without an `Idempotency-Key` - duplicates in the upstream system
- Stacking retry layers (Faraday retry inside Retriable inside Sidekiq) - waits compound surprisingly
- Logging full URLs, request bodies, response bodies, or `Authorization` headers
- Catching `Faraday::Error` in services - couples business logic to the HTTP library; rescue domain errors
- Live HTTP in tests - stub at the boundary with WebMock or VCR
- Retrying 4xx other than `408` and `429` - the upstream said no, retrying won't change its mind
- A circuit breaker on every integration - reserve for high-volume synchronous request-path calls
