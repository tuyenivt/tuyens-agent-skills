---
name: node-http-client-patterns
description: Node.js outbound HTTP - AbortSignal.timeout, Retry-After, idempotent retry, Idempotency-Key, BullMQ delegation, per-vendor wrapper, MSW.
metadata:
  category: backend
  tags: [node, typescript, http, fetch, axios, retry, abortsignal, msw, resilience]
user-invocable: false
---

> Load `Use skill: stack-detect` first; the framework and the HTTP library in `package.json` pick the bindings below. The framework surfaces in the Resiliency Assessment's `**Stack:**` line, the HTTP library in each block's `Wrapper:` line.

Owns the Node bindings for outbound HTTP discipline. `ops-resiliency` owns the stack-agnostic contract - timeout and retry policy, retryable status codes, `Retry-After`, breakers, bulkheads, the per-dependency client wrapper, and the in-process-versus-queue retry-location decision. Load it first. The security workflow checks SSRF (`node-security-patterns`); the perf workflow checks event-loop blocking; this skill owns the `AbortSignal` / `fetch` / `axios` / BullMQ expression of those rules and the MSW test story.

## When to Use

- Calling any third-party HTTP service (Stripe, SendGrid, internal microservices)
- Adding `fetch` / `axios` / `undici` / `got` in a service or processor
- Deciding in-process retry vs BullMQ retry for an outbound call
- Writing tests that hit the network (replace with MSW)

## Rules

- Every outbound call has a total deadline: `AbortSignal.timeout(ms)` on `fetch`. Node's `fetch` has no total-request deadline - undici's defaults are idle timers (`headersTimeout` and `bodyTimeout` 300s, connect 10s), and a body trickled one chunk at a time never trips them
- One wrapper per vendor, but retry policy is per **call site**: the same vendor called from a sync handler and from a worker gets two named policy profiles on one client, not two clients
- Honor `Retry-After` on 429 / 503 - bounded; if it exceeds the in-process budget, delegate to BullMQ
- Retry automatically only idempotent verbs (`GET`, `HEAD`, `PUT`, `DELETE`) and a `POST` carrying an idempotency key; any other `POST` retries only failures proven to precede acceptance
- In-process retry budget is small (2-3 attempts, exponential with jitter, capped under the caller's own deadline) - longer waits go to BullMQ where the queue owns scheduling, and the processor then calls with 1 attempt
- One client wrapper per third party (`StripeClient`, `ShipFastClient`) - base URL, auth, timeout, retry, breaker, error translation in one place; no scattered `fetch('https://api.x.com/...')` in business code
- Non-2xx, transport, and parsing failures translate to a domain `UpstreamError` / `ValidationError` / `InternalError` (see `node-exception-handling`) at the wrapper boundary - `fetch` never throws on a status, so the wrapper checks `res.ok` itself, and `TypeError: fetch failed` never leaks to controllers
- The connection pool lives in the **agent**: build one `undici.Agent` / `http.Agent` (or rely on the global agent, keep-alive since Node 19) at module load, never per request. `axios.create` / `got.extend` only merge config - construct them once for the interceptors and hooks, not for pooling
- Tests use MSW to intercept HTTP at the network layer - never patch `global.fetch` or `axios.get` directly
- A user-influenced URL (a customer webhook endpoint, a "send test" button) goes through the SSRF guard in `node-security-patterns`, not a vendor wrapper

## Patterns

### Timeouts

```typescript
// Bad - hangs until undici's 300s idle timers, or forever on a trickled body
const res = await fetch(url);

// Good - 5s total deadline
const res = await fetch(url, { signal: AbortSignal.timeout(5_000) });
```

`axios` (Node http adapter): `timeout` is a socket-idle timer, the same class as undici's - pass `signal: AbortSignal.timeout(ms)` for a hard deadline. `undici.request`: `signal: AbortSignal.timeout(ms)`, with `headersTimeout` / `bodyTimeout` as idle backstops. `got`: `timeout: { request: ms }`. An SDK with no `signal` option (Twilio, most vendor SDKs) takes its own `timeout` client option. Pick one library per project and pick it for the toolchain: MSW intercepts `fetch` / `axios` / `got` but not `undici.request`, and `got` is ESM-only - a CommonJS build loads it only through `await import()` or Node 20.19+ / 22.12+ `require(esm)`.

Express and NestJS requests have no `signal`. To cancel a GET when the client disconnects, build one: `const ac = new AbortController(); res.on('close', () => { if (!res.writableFinished) ac.abort(); })`, then `AbortSignal.any([ac.signal, AbortSignal.timeout(5_000)])` (Node 20.3+), or pass `ac.signal` as `callWithRetry`'s `outer` signal. Never wire it into a non-idempotent write - a disconnect then aborts a request the server may already have accepted, turning a known outcome into an unknown one.

### Bounded Retry with Jitter, Honoring `Retry-After`

Retry on **thrown** errors as well as statuses: a timeout, DNS failure, or connection reset never produces a response, and a status-only loop never retries the most common failure. The helper owns the one decision point; every wrapper call goes through it.

```typescript
export class HttpStatusError extends Error {
  constructor(readonly status: number, readonly headers: Headers) { super(`HTTP ${status}`); }
}

const RETRYABLE_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);   // + 409 carrying Retry-After
const PRE_ACCEPTANCE = new Set(['ECONNREFUSED', 'ENOTFOUND', 'EAI_AGAIN', 'UND_ERR_CONNECT_TIMEOUT']);
const TRANSPORT = new Set([...PRE_ACCEPTANCE, 'ECONNRESET', 'ETIMEDOUT', 'UND_ERR_SOCKET', 'UND_ERR_HEADERS_TIMEOUT']);

export type Profile = { attempts: number; baseMs: number; perAttemptMs: number; totalMs: number };
// retryAfterSend: true only for GET/HEAD/PUT/DELETE, or a POST carrying an idempotency key
export type Policy = Profile & { retryAfterSend: boolean };

// Seconds or an HTTP-date; null when absent or invalid; a past date clamps to 0
export function parseRetryAfter(h: string | null): number | null {
  if (!h) return null;
  const secs = Number(h);
  if (Number.isFinite(secs)) return Math.max(0, secs * 1_000);
  const at = Date.parse(h);
  return Number.isNaN(at) ? null : Math.max(0, at - Date.now());
}

export function classify(e: unknown): { status?: number; preAcceptance: boolean; retryable: boolean } {
  const status = e instanceof HttpStatusError ? e.status : undefined;
  if (status !== undefined) {
    const retryAfter409 = status === 409 && e instanceof HttpStatusError && e.headers.has('retry-after');
    // 408 / 425 / 429 are refusals - the request was not processed; a 5xx stays ambiguous
    return { status, preAcceptance: [408, 425, 429].includes(status), retryable: RETRYABLE_STATUS.has(status) || retryAfter409 };
  }
  // our own AbortSignal.timeout rejects with a DOMException named TimeoutError - no .cause, numeric .code
  if ((e as Error)?.name === 'TimeoutError') return { preAcceptance: false, retryable: true };
  // fetch transport failures arrive as TypeError('fetch failed') with the real code on .cause
  const code = (e as { cause?: { code?: string } } | undefined)?.cause?.code ?? (e as { code?: string } | undefined)?.code ?? '';
  return { preAcceptance: PRE_ACCEPTANCE.has(code), retryable: TRANSPORT.has(code) };
}

export async function callWithRetry<T>(
  call: (signal: AbortSignal) => Promise<T>, p: Policy, outer?: AbortSignal,   // outer: e.g. client disconnect
): Promise<T> {
  const start = Date.now();
  for (let attempt = 1; ; attempt++) {
    try {
      const attemptSignal = AbortSignal.timeout(p.perAttemptMs);
      return await call(outer ? AbortSignal.any([outer, attemptSignal]) : attemptSignal);
    } catch (e) {
      const c = classify(e);
      // a timeout or 5xx after the body was flushed is AMBIGUOUS - the server may have accepted it
      if (!c.retryable || !(p.retryAfterSend || c.preAcceptance) || attempt >= p.attempts) throw e;
      const retryAfter = parseRetryAfter(e instanceof HttpStatusError ? e.headers.get('retry-after') : null);
      const backoff = Math.min(p.baseMs * 2 ** (attempt - 1), 1_000) * (0.5 + Math.random() * 0.5);
      const wait = retryAfter ?? backoff;                       // never undercut Retry-After
      // the budget must cover the wait AND the next attempt's timeout, or it overruns by a full timeout
      if (Date.now() - start + wait + p.perAttemptMs > p.totalMs || outer?.aborted) throw e;
      await new Promise((r) => setTimeout(r, wait));
    }
  }
}

// Two named profiles, chosen at the call site
export const interactive: Profile = { attempts: 2, baseMs: 200, perAttemptMs: 3_000, totalMs: 8_000 };
export const queued: Profile = { attempts: 1, baseMs: 0, perAttemptMs: 10_000, totalMs: 10_000 };
```

The helper is `fetch`-shaped. For axios, map an `AxiosError` with `response` to its `status` / headers, and `ERR_CANCELED` / `ECONNABORTED` to a timeout, before classifying. Size `interactive` under the caller's deadline: `attempts x perAttemptMs + waits <= caller deadline - the caller's own work`. An 800 ms request budget with ~200 ms of its own work leaves ~600 ms: `{ attempts: 2, perAttemptMs: 250, baseMs: 50, totalMs: 600 }`, or one attempt when even that does not fit. `queued` makes one attempt because the queue owns retry - and the queue's own `attempts` is subject to the same idempotency rule. If `Retry-After` exceeds the budget, throw and let the caller decide: surface a domain error, or enqueue a BullMQ job that retries with the queue's `attempts` + `backoff`.

A `Retry-After` from a **per-key** upstream (a per-store or per-tenant API) throttles that key only: in a worker, defer that job (`job.moveToDelayed`), never pause the whole queue - see `node-bullmq-patterns`.

### Idempotent vs Non-Idempotent Retries

A `POST` becomes retry-safe with an idempotency key the vendor honours. Key it on the **attempt**, not the business object, whenever the payload for that object can change: a same-parameter retry replays the cached result (a decline stays a decline), and a retry with a new card under the same key is rejected as a parameter mismatch.

```typescript
// Stripe: the SDK retries on its own (maxNetworkRetries) with an auto-generated key - set it
// explicitly and put no second retry layer around the SDK
const stripe = new Stripe(key, { maxNetworkRetries: 2, timeout: 5_000 });
await stripe.paymentIntents.create(
  { amount, currency: 'usd', customer, payment_method, confirm: true,
    automatic_payment_methods: { enabled: true, allow_redirects: 'never' } },   // server-side confirm, no return_url
  { idempotencyKey: `pi-${orderId}-${attemptId}` },
);
```

Internal POST endpoints accept an `Idempotency-Key` header and store key + response for a TTL (Redis or an `idempotency_keys` table). Clients send the same key on retry.

When the vendor offers no idempotency key at all (Twilio, most SMS and push providers), the dedup is yours: claim before you call, mark it sent after, and treat an ambiguous outcome as sent.

```typescript
// ioredis (the client BullMQ already requires); node-redis takes { NX: true, PX: ms }
const key = `sms-${verificationId}`;
const HORIZON_MS = 2 * 3_600_000;        // longer than every retry path: queue backoff + a stalled-job window
if ((await redis.set(key, 'claimed', 'PX', HORIZON_MS, 'NX')) !== 'OK') return;   // sent or in flight
try {
  await twilio.messages.create(...);     // only the vendor call is classified
} catch (e) {
  if (classify(e).preAcceptance) await redis.del(key).catch(() => {});   // provably not sent - free the key
  throw e;                                // ambiguous: KEEP the claim, never re-send within the window
}
await redis.set(key, 'sent', 'PX', HORIZON_MS);   // a failed write leaves 'claimed' in place - still safe
```

A timeout or 5xx after the request body was flushed is **ambiguous**, not failed: "never sent" and "sent, response lost" are indistinguishable. Reconcile with an idempotent `GET` first, or accept the loss.

### Delegating to BullMQ When the Budget Blows

```typescript
async sendInvoice(orderId: string): Promise<void> {
  try {
    await this.sendgrid.sendInvoice(orderId, interactive);
  } catch (e) {
    // SendGrid mail send is a POST with no idempotency key: queue only failures that provably
    // never reached SendGrid; an ambiguous failure goes through the claim key above instead
    if (e instanceof UpstreamError && classify(e.cause).preAcceptance) {
      await this.queue.add('send-invoice', { orderId }, {
        jobId: `send-invoice-${orderId}`,                // a second caller enqueues nothing
        attempts: 8,
        backoff: { type: 'exponential', delay: 30_000, jitter: 0.5 },
        removeOnComplete: { age: 86_400 },
        removeOnFail: { age: 7 * 86_400 },               // a kept failed job would block every later resend
      });
      return;
    }
    throw e;
  }
}
```

BullMQ's exponential backoff is `delay x 2^(attemptsMade - 1)`: 8 attempts at 30s wait 30s + 60s + ... + 1920s, about 63 minutes in total. Recent BullMQ 5 releases take `jitter` (0-1) on the built-in backoff; on older ones register a custom `settings.backoffStrategy` on the Worker.

Rule of thumb: **in-process retry seconds, BullMQ retry minutes-to-hours**. Once the queue owns the retry, the processor calls the vendor with the `queued` profile (1 attempt) - otherwise 8 job attempts x 2 `interactive` attempts is 16 upstream calls per failure, the multiplied budget `ops-resiliency` prohibits.

### Per-Vendor Client Wrapper

```typescript
// One file owns the carrier; everywhere else injects this
@Injectable()
export class ShipFastClient {
  private readonly breaker = circuitBreaker(handleWhen((e) => e instanceof UpstreamError), {
    halfOpenAfter: 30_000, breaker: new ConsecutiveBreaker(5),        // cockatiel
  });
  private readonly bulkhead = bulkhead(20, 50);                         // max 20 in flight, 50 queued

  constructor(private readonly config: ConfigService, private readonly logger: PinoLogger) {
    this.breaker.onBreak(() => this.logger.warn('shipfast breaker open'));      // breaker monitoring
    this.breaker.onReset(() => this.logger.info('shipfast breaker closed'));
  }

  async createShipment(attemptKey: string, input: ShipmentInput, profile: Profile): Promise<Shipment> {
    try {
      return await this.bulkhead.execute(() => this.breaker.execute(() => this.send(attemptKey, input, profile)));
    } catch (e) {
      // breaker open / bulkhead full are raised outside send() - translate them here too
      if (e instanceof BrokenCircuitError || e instanceof BulkheadRejectedError) {
        this.logger.warn({ err: e }, 'shipfast rejected locally');
        throw new UpstreamError('shipfast unavailable', e);
      }
      throw e;
    }
  }

  private async send(attemptKey: string, input: ShipmentInput, profile: Profile): Promise<Shipment> {
    try {
      return await callWithRetry(async (signal) => {
        const res = await fetch(`${this.config.getOrThrow('SHIPFAST_BASE_URL')}/shipments`, {
          method: 'POST', signal,
          headers: {
            authorization: `Bearer ${this.config.getOrThrow('SHIPFAST_API_KEY')}`,
            'content-type': 'application/json',
            'idempotency-key': attemptKey,                             // caller-supplied: shipment-<orderId>-<attempt>
          },
          body: JSON.stringify(input),
        });
        if (!res.ok) {
          await res.body?.cancel();                                  // an unread body holds the connection
          throw new HttpStatusError(res.status, res.headers);
        }
        return (await res.json()) as Shipment;
      }, { ...profile, retryAfterSend: true });
    } catch (e) {
      const { status, retryable } = classify(e);
      if (status === 400 || status === 422) throw new ValidationError('shipfast rejected the shipment', e);
      if (status === 401 || status === 403) throw new InternalError('shipfast credentials or config', e);  // our fault - page
      if (retryable || status === undefined) throw new UpstreamError('shipfast unavailable', e);            // 408/425/429/5xx/transport
      throw new InternalError(`shipfast responded ${status}`, e);
    }
  }
}
```

One translation point per vendor: HTTP status -> domain error. Controllers see `ValidationError` / `UpstreamError` / `InternalError`, never an `HttpStatusError`, `AxiosError`, or `TypeError: fetch failed`. The breaker counts only `UpstreamError` (a 4xx is the caller's problem, not the vendor's health). A caller that has a fallback (a cached rate, a default estimate) catches `UpstreamError` and logs the original failure at WARN; which fallback is acceptable - fail open, fail closed, send to review - is a product decision the call site states. Give each caller class its own bulkhead when their latency classes differ (a checkout handler and a nightly job).

### Module-Level Clients, Not Per-Request

```typescript
// Bad - a new Agent (and connection pool) per request
@Get()
list() {
  return fetch(url, { dispatcher: new Agent({ keepAliveTimeout: 10_000 }) });
}

// Good - the agent and the client are built once and injected
constructor(private readonly users: UsersClient) {}
```

A per-request `undici.Agent`, `http.Agent`, or an `agent:` option built per request defeats keep-alive and surges TCP / TLS handshakes.

### Testing with MSW

```typescript
// test/setup.ts
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

export const server = setupServer(
  http.post('https://api.shipfast.example/v2/shipments', () => HttpResponse.json({ shipmentId: 's_1' })),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

```typescript
// shipfast.client.spec.ts - a per-test override lives inside the test; resetHandlers removes it after
it('translates a 503 into UpstreamError', async () => {
  server.use(http.post('https://api.shipfast.example/v2/shipments', () => new HttpResponse(null, { status: 503 })));
  await expect(client.createShipment('o1', input, interactive)).rejects.toBeInstanceOf(UpstreamError);
});
```

`onUnhandledRequest: 'error'` catches accidental real network calls. MSW asserts on the request as actually sent (URL, headers, body) and survives a library change; a `global.fetch` stub skips the transport and breaks when the client library changes.

## Output Format

When authoring, emit the blocks plus the client code they describe; a build over existing code is authoring plus review (the envelope below carries the existing defects). Emit one block per **vendor call site** - a vendor called from both a handler and a processor gets two blocks, since the policy differs; a user-supplied URL is its own block with `Vendor: user-supplied URL`. When reviewing or diagnosing, also emit `ops-resiliency`'s Resiliency Assessment envelope with a Node binding in every Recommendation: the blocks describe current state, the envelope carries the finding, severity, and fix. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the blocks, and a fix order goes in the envelope as its Gaps' severity order.

```
Vendor: {Stripe | SendGrid | internal-service-X | user-supplied URL (SSRF - node-security-patterns) | ...}

Call Site: {sync handler file:line | BullMQ processor file:line}

Wrapper: {file:line of the client class and its HTTP library, or "scattered - needs consolidation"}

Timeout: {per-attempt ms and total budget ms | idle timers only (defect) | MISSING}

Retry Policy: {none | in-process N attempts, expo+jitter, cap M ms | SDK-owned: <option> N | delegated to BullMQ: job attempts N, backoff <shape> | UNBOUNDED (defect) | multiplied: N wrapper x M job attempts (defect)}; Retry-After {honored | ignored (defect) | n/a}

Idempotency: {GET/HEAD/PUT/DELETE only | Idempotency-Key on POST | app-owned claim key | POST without key, pre-acceptance retry only | NONE on a retried POST (defect) | N/A}

Connection Pool: {module-level agent | global dispatcher | per-request agent or client (defect)}

Breaker / Bulkhead: {breaker thresholds and what it counts; bulkhead limit | none}

Error Translation: {what HTTP statuses -> what domain errors | status unchecked - res.json() on any status (defect) | none - vendor error leaks (defect)}

Tests: {MSW handler at path/to/setup.ts | missing | mocks global.fetch (defect)}
```

## Avoid

- `fetch(url)` without `AbortSignal.timeout(...)` - undici's idle timers are not a deadline
- Retrying POST without an `Idempotency-Key` - duplicate writes
- Unbounded in-process retry loops (sync handlers must respond in seconds, not minutes)
- Letting an SDK's or library's own retry interleave with yours - pick one. `axiosRetry(client, opts)` registers its interceptors itself and returns their ids; wrapping it in `interceptors.response.use(...)` only adds a dead no-op interceptor, and calling it on the global `axios` wires nothing on your `client`
- Retrying only on status codes - timeouts and connection errors throw and never reach a status check
- Piping a client-disconnect signal into a POST/PATCH - a disconnect makes the write's outcome unknown
- Treating `Retry-After: 600` as if it were milliseconds (it's seconds, or an HTTP-date)
- Retrying 4xx responses other than 408 / 425 / 429 and a 409 carrying `Retry-After`
- One mega-`HttpClient` class for all vendors - one wrapper per vendor, each with its own error map
