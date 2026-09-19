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
- No outbound call inside an open `ActiveRecord::Base.transaction`. It pins a DB connection for the round trip (a slow upstream then exhausts the pool, not just the thread pool), and it inverts failure: the remote side has already acted when the local rollback undoes the row that recorded it. Call before the transaction (with an idempotency key - a crash between the call and the commit is `rails-service-objects`' reconciliation job), or after commit.
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
  AuthError       = Class.new(PermanentError)
  NotFoundError   = Class.new(PermanentError)
  ValidationError = Class.new(PermanentError)

  # Carries the header as data, not prose - sidekiq_retry_in reads exception.retry_after
  class RateLimitError < TransientError
    attr_reader :retry_after
    def initialize(message = nil, retry_after: nil)
      super(message)
      @retry_after = retry_after
    end
  end

  def initialize(token: ENV.fetch("SHIPPER_TOKEN"), connection: nil)
    @connection = connection || build_connection(token)
  end

  def create_shipment(order_id:, idempotency_key:)
    response = @connection.post("shipments") do |req|
      req.headers["Idempotency-Key"] = idempotency_key
      req.body = { order_id: order_id }
    end
    response.body
  rescue Faraday::ConnectionFailed, Faraday::TimeoutError, Faraday::SSLError => e
    raise TransientError, e.message
  rescue Faraday::ClientError => e
    raise translate(e)
  rescue Faraday::ServerError => e
    raise TransientError, e.message
  rescue Faraday::ParsingError => e
    raise PermanentError, e.message          # malformed body - retrying won't fix it
  rescue Faraday::Error => e
    raise PermanentError, e.message          # catch-all: nothing leaves untranslated
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
    # `[]` not `dig`: Faraday::Utils::Headers gets case-insensitivity from an overridden
    # #[], and Hash#dig is C-level so it bypasses that - nil on any adapter that
    # preserves the header's original casing.
    when 408, 429 then RateLimitError.new("rate limited",
                                          retry_after: retry_after_seconds(error.response_headers&.[]("retry-after")))
    when 422      then ValidationError.new(error.response_body.to_s)
    else               PermanentError.new("rejected: #{error.response_status}")
    end
  end

  # Retry-After is delay-seconds or an HTTP-date; "<date>".to_f is 0.0 and truthy, which
  # would re-fire the job immediately - anything unparseable becomes nil so the reader's fallback applies
  def retry_after_seconds(value)
    return nil if value.blank?
    Float(value, exception: false) || (Time.httpdate(value) - Time.now rescue nil)
  end
end
```

Expiring tokens (OAuth, 12h bearers): the client owns the refresh - cache the token in `Rails.cache` (TTL slightly under its lifetime, shared so every process and pod refreshes once, not once per worker), and on 401 refresh once and retry once before raising `AuthError`. A 401 is only *permanent* after a fresh token also failed.

One client serving both web and Sidekiq callers keeps the connection default at the web budget and overrides per call (`req.options.timeout = 15`) on job-path operations - don't build two clients.

Callers consume domain errors only:

```ruby
class FulfillOrder
  def call
    payload = ShipperClient.new.create_shipment(order_id: @order.id,
                                                idempotency_key: "fulfill-#{@order.id}-#{@order.fulfillment_attempt}")
    Result.success(payload)
  rescue ShipperClient::PermanentError => e
    Result.failure([e.message], code: :shipper_rejected)
  rescue ShipperClient::TransientError
    raise  # let Sidekiq retry
  end
end
```

Rescuing `Faraday::Error` in a service couples business logic to the transport. The Transient/Permanent split is the contract: Sidekiq retries transient; permanent becomes a 4xx via `Result.failure`. For full translation patterns, use skill: `rails-exception-handling`.

### Timeouts

| Timeout        | Default  | Recommended | Notes                                              |
| -------------- | -------- | ----------- | -------------------------------------------------- |
| `open_timeout` | 60s (net_http) | 1-2s  | TCP connect + TLS - slow connect signals dead host |
| `timeout`      | 60s (net_http) | 3-10s | Faraday resolves it as `read_timeout \|\| timeout`, so it bounds each socket read, **not** the whole call |

Faraday sets no timeout of its own; the adapter's default applies, and `net_http` (the default adapter) uses 60s for open, read and write. So "no timeout configured" means 60s per operation, not infinite - and because `timeout` is per-read, a response that drips bytes can outlive it many times over. A true wall-clock cap needs `rack-timeout` on the web path or an explicit deadline around the call.

Web request path: external timeout < remaining request budget; stay under 5s and push longer work to Sidekiq. Sidekiq path: 10-30s is fine *when nothing downstream is waiting* - but a client called from a bounded worker pool during a multi-minute brownout should keep the web-path tightness, because per-thread stall time is what exhausts the pool. Size it against the pool, then let the circuit breaker carry the rest.

### Middleware Order

Request middleware runs top-down, response bottom-up (last-registered response middleware runs first). Common breakages:

- Registering `:json` (response) before `:raise_error` -> `raise_error` runs first and the raised error carries an unparsed body. Register `:raise_error` above `:json`, as in the client above.
- Registering `:retry` *above* `:raise_error` -> `raise_error` converts the 5xx before `:retry` can see it, so every `retry_statuses` entry is dead. `:retry` must sit closer to the adapter than `:raise_error`. This is the ordering footgun that silently disables the retry config below.
- `:json` (request) skips `JSON.generate` for a `String` body but still sets `Content-Type: application/json` - so a pre-serialized string is sent as-is, and a non-JSON string is silently mislabelled. Pass hashes.
- `:logger` with `bodies: true` in production -> leaks tokens / PII.

### Retry Strategy

Retry lives in the separate `faraday-retry` gem since Faraday 2.0 (`gem "faraday-retry"` + `require "faraday/retry"`); without it `f.request :retry` raises `:retry is not registered`. Register it *below* `:raise_error` in the connection block so it sees raw statuses:

```ruby
f.response :raise_error
f.request :retry,
  max: 2, interval: 0.5, interval_randomness: 0.5, backoff_factor: 2,
  max_interval:   2,
  methods:        %i[get head put delete],
  retry_statuses: [408, 429, 500, 502, 503, 504],
  exceptions:     [Faraday::ConnectionFailed, Faraday::TimeoutError, Faraday::RetriableResponse],
  retry_if:       ->(env, _) { env.request_headers["Idempotency-Key"].present? }
```

`exceptions:` **replaces** the gem's default list rather than adding to it, and `Faraday::RetriableResponse` must stay in it: that is the class faraday-retry raises internally to signal a `retry_statuses` hit, and it converts it back to a response only in its own rescue. Omit it and a 429 or 503 escapes the middleware as `Faraday::RetriableResponse`, which the `ClientError`/`ServerError` rescues skip and the `Faraday::Error` catch-all turns into `PermanentError` - Sidekiq then stops retrying a retryable status.

`retry_if` opts `POST` back in only when `Idempotency-Key` is present - required for Stripe-style APIs.

Hard quotas (60/min per token) need proactive throttling before any retry logic: a Redis token bucket shared by every process (`rails-work-splitter-patterns`) or a low-concurrency queue. `Retry-After` on 429: faraday-retry sleeps the header value in-process, capped by `max_interval` (default `Float::MAX` - set it, or a Puma thread sleeps for minutes). Past the cap it stops retrying and returns the 429, which `:raise_error` and `translate` then turn into `RateLimitError` for Sidekiq to reschedule. Make the seconds machine-readable - `translate` parses the header into the error (`RateLimitError.new(retry_after: ...)`), and `sidekiq_retry_in` returns `exception.retry_after` plus jitter (`+ rand(10)`) so recovering jobs don't re-herd. The header is often absent, so the reader falls back rather than trusting it: `exception.retry_after || 60 * (count + 1)`, as `rails-sidekiq-patterns` does. Reactive 429 handling alone herds.

| Layer             | Count | Backoff       | When                                            |
| ----------------- | ----- | ------------- | ----------------------------------------------- |
| Faraday `:retry`  | 2-3   | <5s total     | Transient blips during one request              |
| Retriable wrapper | 2-3   | <30s total    | Non-Faraday clients / SDK calls on the web path: `Retriable.retriable(tries: 3, base_interval: 0.5, multiplier: 2, on: [Sdk::TimeoutError, Sdk::ServerError]) { sdk.call }` - `on:` names the SDK's own transient classes |
| Sidekiq retry     | 5-25  | minutes-hours | Anything that needs to wait out an outage       |
| Don't retry       | -     | -             | 4xx other than 408/429; POST without key        |

Stacking all three compounds wait time unpredictably. Inside a Sidekiq job, prefer Sidekiq's retry over wrapping in Retriable.

### Circuit Breaker

In-process retries during a sustained outage make the outage worse. Trip after N consecutive failures and short-circuit:

```ruby
require "stoplight"   # Stoplight 5.x keyword form; older releases chain .with_threshold(5).with_cool_off_time(60)

def create_shipment(order_id:, idempotency_key:)
  Stoplight("shipper.create_shipment", threshold: 5, cool_off_time: 60).run do
    @connection.post("shipments") { |req| ... }.body
  end
rescue Stoplight::Error::RedLight
  raise TransientError, "shipper circuit open"   # keep an open circuit inside the taxonomy
end
```

Without that rescue (or a fallback) an open circuit raises `Stoplight::Error::RedLight`, a class outside the taxonomy that callers rescuing `TransientError`/`PermanentError` will not catch. Stoplight counts every `StandardError`, so skip the permanent 4xx side (`skipped_errors:` in 5.x, `.with_error_handler` earlier) or five bad payloads open the circuit.

Use when synchronous on the request path (outages cascade into Puma worker exhaustion), volume >10 req/s sustained, upstream has documented SLOs, or a hard quota is shared with a batch consumer. Low-volume background work doesn't need one.

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
# Wire on the connection - `f.use :instrumentation` raises; the middleware is
# registered on Faraday::Request, not Faraday::Middleware:
f.request :instrumentation
```

`env.request_headers` holds the *outbound* headers, so `X-Request-Id` is nil unless the client sets it. Propagate it on the way out - `req.headers["X-Request-Id"] = Current.request_id` in the request block - or the field logs empty on every call.

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

In review or diagnosis mode, precede the blocks with numbered findings, each citing the violated rule or pattern and `file:line`; the consuming workflow owns the finding envelope, and invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. The block describes the corrected client. One block per client class; when methods differ in retry or breaker posture, `Retry:` and `Circuit breaker:` name the method. A vendor SDK client (Stripe) fills `Base URL:` and `Timeouts:` from the SDK's configuration and `n/a` where the SDK owns them. A call site that bypasses the client class (`Faraday.get` in a service, an SDK called from a service while the client exists) is a finding against Rule 5.

```
Client: {ClassName}

Base URL: {url}

Auth: {Bearer | API key header | OAuth (refresh: cached TTL + once-on-401) | credentials in query string - GAP | none - GAP unless the endpoint is documented public or on a trusted network (say which)}

Timeouts: open={Ns}, read={Ns} (+ per-call overrides for job-path ops); wall-clock cap: {rack-timeout | explicit deadline | none - a slow-drip response is unbounded}

Called inside a transaction: {No | Yes - BLOCKER, name the transaction}

Retry: {faraday | retriable | sidekiq only (job path, stated) | none | stacked - GAP | gem absent - GAP}, max={N}, backoff={strategy}, order={:retry below :raise_error | above - dead (GAP) | n/a}

Rate budget: {none | Redis token bucket shared across processes | low-concurrency queue | n/a - no hard quota}

Idempotency: {how POST/PATCH replay safety is achieved}

Error taxonomy: {domain error classes}

Circuit breaker: {none (justified) | Stoplight threshold/cool-off; skipped errors: permanent 4xx | all StandardError counted - GAP; open-circuit fallback per call site | gem absent - GAP}

Logging: {instrumentation subscriber - host, path, status, duration, request id; bodies off | bodies: true - GAP | none - GAP}

Tests: {WebMock unit | VCR cassettes | both - file paths | none or live HTTP - GAP | not in evidence}
```

## Avoid

- Stacking retry layers (Faraday + Retriable + Sidekiq) - wait times compound unpredictably
- Circuit breakers on every integration - reserve for high-volume request-path calls
- Rescuing `Faraday::Error` in services - couples business logic to the transport
- Retrying 4xx other than 408 / 429
- Full URLs in logs - query string tokens leak
