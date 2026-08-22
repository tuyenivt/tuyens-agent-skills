---
name: node-http-client-patterns
description: Node.js outbound HTTP - AbortSignal.timeout, Retry-After, idempotent retry, Idempotency-Key, BullMQ delegation, per-vendor wrapper, MSW.
metadata:
  category: backend
  tags: [node, typescript, http, fetch, axios, retry, abortsignal, msw, resilience]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Owns the Node bindings for outbound HTTP discipline. `ops-resiliency` owns the stack-agnostic contract - timeout and retry policy, retryable status codes, `Retry-After`, breakers, the per-dependency client wrapper, and the in-process-versus-queue retry-location decision. Load it first. The security workflow checks SSRF (`node-security-patterns`); the perf workflow checks event-loop blocking; this skill owns the `AbortSignal` / `fetch` / `axios` / BullMQ expression of those rules and the MSW test story. Workflows delegate here and flag deviations.

## When to Use

- Calling any third-party HTTP service (Stripe, SendGrid, internal microservices)
- Adding `fetch` / `axios` / `undici` / `got` in a service or processor
- Deciding in-process retry vs BullMQ retry for an outbound call
- Writing tests that hit the network (replace with MSW)

## Rules

- Every outbound call has an `AbortSignal.timeout(ms)` - Node's `fetch` applies no request deadline (undici's `headersTimeout` of ~300s is a backstop, not a timeout, and never bounds the body)
- One wrapper per vendor, but retry policy is per **call site**: the same vendor called from a sync handler and from a worker gets two named policy profiles on one client, not two clients
- Honor `Retry-After` on 429 / 503 - bounded; if it exceeds the in-process budget, delegate to BullMQ
- Retry only idempotent verbs (`GET`, `HEAD`, `PUT`, `DELETE`) automatically; POST retries require an `Idempotency-Key` header (or skip the retry)
- In-process retry budget is small (2-3 attempts, exponential with jitter, capped at a few seconds total) - longer waits go to BullMQ where the queue owns scheduling
- One client wrapper class per third party (`StripeClient`, `SendGridClient`) - configures base URL, auth, timeout, retry, error translation in one place; no scattered `fetch('https://api.x.com/...')` in business code
- Transport / 5xx / parsing errors translate to a domain `UpstreamError` (see `node-exception-handling`) at the wrapper boundary - never leak `fetch`'s `TypeError: fetch failed` to controllers
- HTTP client (`axios.create`, `undici.Agent`, `got.extend`) instantiated at module load, not per-request - connection pooling
- Tests use MSW (Mock Service Worker) to intercept HTTP at the network layer - never patch `global.fetch` or `axios.get` directly
- SSRF allowlist applies when URL is user-influenced (delegate to `node-security-patterns`)

## Patterns

### Timeout via `AbortSignal.timeout`

```typescript
// Bad - hangs forever on slow upstream
const res = await fetch(url);

// Good - 5s ceiling
const res = await fetch(url, { signal: AbortSignal.timeout(5_000) });

// Combine app-level cancel + timeout - GET/HEAD only
const res = await fetch(url, {
  signal: AbortSignal.any([req.signal, AbortSignal.timeout(5_000)]),
});
```

Never wire `req.signal` into a non-idempotent write. A client disconnect then aborts a request the server may already have accepted, turning a known outcome into an unknown one - which is exactly what produces duplicate charges on the retry.

`axios`: `timeout: 5_000`. `undici`: `bodyTimeout` + `headersTimeout`. `got`: `timeout: { request: 5_000 }`. Pick one library per project; don't mix - and pick it for the whole toolchain: MSW intercepts `fetch`/`axios`/`got` but not `undici.request`, and `got` is ESM-only, which a CJS NestJS build cannot import.

### Bounded Retry with Jitter, Honoring `Retry-After`

Retry on **thrown** errors as well as status codes: a timeout, DNS failure, or connection reset never produces a response, and a status-only loop silently never retries the most common failure. Wrap whichever library you chose so both paths reach one decision point.

```typescript
const RETRYABLE_STATUS = new Set([408, 429, 500, 502, 503, 504]);
const RETRYABLE_CODE = new Set(['ECONNREFUSED', 'ECONNRESET', 'ENOTFOUND', 'EAI_AGAIN', 'ETIMEDOUT']);

type Policy = {
  attempts: number; baseMs: number; perAttemptMs: number; totalMs: number;
  // false for a POST with no idempotency key: only failures proven to precede acceptance may retry
  retryAfterSend: boolean;
};

async function callWithRetry<T>(call: (signal: AbortSignal) => Promise<T>, p: Policy): Promise<T> {
  const start = Date.now();
  for (let attempt = 1; ; attempt++) {
    try {
      return await call(AbortSignal.timeout(p.perAttemptMs));
    } catch (e) {
      // Node `fetch` never throws on status, so the wrapper must throw one itself:
      //   if (!res.ok) throw new HttpStatusError(res.status, res.headers);
      // and transport failures arrive as `TypeError: fetch failed` with the real code on `.cause`.
      const status = e instanceof HttpStatusError ? e.status : undefined;      // axios: e.response?.status
      const code = (e as { cause?: { code?: string } }).cause?.code ?? (e as { code?: string }).code;
      // Connect-phase failures are provably pre-acceptance; a 5xx or timeout after the body was
      // flushed is AMBIGUOUS - the server may have accepted it. Retrying that is what duplicates writes.
      const preAcceptance = code === 'ECONNREFUSED' || code === 'ENOTFOUND' || code === 'EAI_AGAIN';
      const retryable = (status ? RETRYABLE_STATUS.has(status) : RETRYABLE_CODE.has(code ?? ''))
        && (p.retryAfterSend || preAcceptance);
      if (!retryable || attempt === p.attempts) throw e;

      const retryAfter = parseRetryAfter(e instanceof HttpStatusError ? e.headers.get('retry-after') : null);  // ms; header is SECONDS or an HTTP-date
      const backoff = Math.min(p.baseMs * 2 ** (attempt - 1), 1_000);
      const wait = retryAfter ?? backoff * (0.5 + Math.random() * 0.5);     // jitter ours only, never undercut Retry-After
      // the budget must cover the wait AND the next attempt's timeout, or it overruns by a full timeout
      if (Date.now() - start + wait + p.perAttemptMs > p.totalMs) throw e;
      await new Promise((r) => setTimeout(r, wait));
    }
  }
}
```

Set `retryAfterSend: true` only for `GET`/`HEAD`/`PUT`/`DELETE`, or for a POST carrying an idempotency key. Two named policies, chosen at the call site: `interactive` (`{ attempts: 2, baseMs: 200, perAttemptMs: 3_000, totalMs: 8_000 }`, sized under the caller's own deadline) and `queued` (`{ attempts: 1, baseMs: 0, perAttemptMs: 10_000, totalMs: 10_000 }`, because the queue owns retry - and the queue's own `attempts` is subject to the same idempotency rule). If `Retry-After` exceeds the budget, throw and let the caller decide: surface a domain error, or enqueue a BullMQ job that retries with the queue's `attempts` + `backoff`.

### Idempotent vs Non-Idempotent Retries

```typescript
// Safe to retry automatically
GET /users/123          // idempotent
PUT /users/123          // idempotent (replaces full resource)
DELETE /users/123       // idempotent

// NOT safe to retry blindly - duplicate writes
POST /charges
POST /orders

// Make POST retry-safe with Idempotency-Key
await stripe.charges.create(
  { amount, currency: 'usd', source },
  { idempotencyKey: orderId },        // Stripe SDK header; server dedupes within 24h
);
```

Internal POST endpoints should accept an `Idempotency-Key` header and store the key + response for a TTL (Redis or an `idempotency_keys` table). Clients send the same key on retry.

When the vendor offers no idempotency key at all (Twilio, most SMS and push providers), the dedup has to be yours: claim before you call, and treat an ambiguous outcome as sent.

```typescript
// Claim first - SET NX makes the second caller a no-op even mid-flight
const key = `sms:${verificationId}`;
if (!(await redis.set(key, 'claimed', { NX: true, PX: 600_000 }))) return;   // already sent or in flight
try {
  await twilio.messages.create(...);
} catch (e) {
  if (isPreAcceptance(e)) await redis.del(key);   // provably not sent - free the key so a retry can send
  throw e;                                        // ambiguous: KEEP the claim, never re-send
}
```

A timeout or 5xx after the request body was flushed is **ambiguous**, not failed: "never sent" and "sent, response lost" are indistinguishable. Retrying an ambiguous non-idempotent write is what produces duplicates - reconcile with an idempotent `GET` first, or accept the loss.

### Delegating to BullMQ When Budget Blows

```typescript
// service
async sendInvoice(orderId: string): Promise<void> {
  try {
    await this.sendgrid.sendInvoice(orderId, { signal: AbortSignal.timeout(5_000) });
  } catch (e) {
    if (e instanceof UpstreamError) {
      // SendGrid down - queue takes over with exponential backoff over hours
      await this.queue.add('send-invoice', { orderId }, {
        attempts: 8,
        backoff: { type: 'exponential', delay: 30_000 },
        removeOnComplete: 1_000,
      });
      return;
    }
    throw e;
  }
}
```

Rule of thumb: **in-process retry seconds, BullMQ retry minutes-to-hours**. Sync request handlers can't sleep 5 minutes - the connection times out and the user retries the whole request.

Once the queue owns the retry, the job processor calls the vendor with in-process retries dropped to 0-1 (a retry-free wrapper variant) - otherwise 8 job attempts x 3 wrapper attempts is 24 upstream calls per failure, the multiplied budget `ops-resiliency` prohibits.

### Per-Vendor Client Wrapper

```typescript
// One file owns Stripe; everywhere else injects this
@Injectable()
export class StripeClient {
  private readonly http: Got;

  constructor(config: ConfigService) {
    this.http = got.extend({
      prefixUrl: 'https://api.stripe.com/v1',
      headers: { authorization: `Bearer ${config.getOrThrow('STRIPE_SECRET')}` },
      timeout: { request: 5_000 },
      retry: { limit: 0 },          // we own retry policy, not got's
    });
  }

  async createCharge(input: ChargeInput, idempotencyKey: string): Promise<Charge> {
    try {
      return await callWithRetry(() => this.http.post('charges', {
        form: input,
        headers: { 'idempotency-key': idempotencyKey },
      }).json<Charge>());
    } catch (e) {
      if (e instanceof HTTPError) {
        if (e.response.statusCode === 402) throw new ValidationError('card declined', e);
        if (e.response.statusCode < 500)                              // 401/403/422: config or contract bug
          throw new InvalidStateError(`stripe rejected: ${e.response.statusCode}`, e);  // non-retryable
      }
      throw new UpstreamError('stripe unreachable', e);               // 5xx/transport -> retry queue candidate
    }
  }
}
```

One translation point per vendor: HTTP status -> domain error. Controllers see `ValidationError` / `UpstreamError`, never `got`'s `HTTPError`.

### Module-Level Clients, Not Per-Request

```typescript
// Bad - new connection pool every request
@Get()
list() {
  const client = got.extend({ prefixUrl: '...' });    // fresh pool, no reuse
  return client('users').json();
}

// Good - client constructed once, injected
constructor(private readonly users: UsersClient) {}
```

`axios.create()`, `undici.Agent`, `got.extend` all hold connection pools. Per-request instantiation defeats keep-alive and surges TCP / TLS handshakes.

### Testing with MSW

```typescript
// test/setup.ts
import { setupServer } from 'msw/node';
import { http, HttpResponse } from 'msw';

export const server = setupServer(
  http.post('https://api.stripe.com/v1/charges', () =>
    HttpResponse.json({ id: 'ch_test', status: 'succeeded' })),
);

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// per-test override for the 503 path
server.use(http.post('https://api.stripe.com/v1/charges', () => new HttpResponse(null, { status: 503 })));
```

`onUnhandledRequest: 'error'` catches accidental real network calls. Don't mock `global.fetch` / `axios.get` - MSW intercepts at the network layer and exercises the real client wrapper, retry, and error-translation code.

## Output Format

Emit one block per **vendor call site** - a vendor called from both a handler and a processor gets two blocks, since the policy differs. When reviewing, also emit `ops-resiliency`'s Resiliency Assessment envelope with a Node binding in every Recommendation; the block below describes current state, and the envelope carries the finding, severity, and fix.

```
Vendor: {Stripe | SendGrid | internal-service-X | ...}
Call Site: {sync handler file:line | BullMQ processor file:line}
Wrapper: {file:line of the client class, or "scattered - needs consolidation"}
Timeout: {per-attempt ms and total budget ms - or MISSING}
Retry Policy: {none | in-process N attempts, expo+jitter, cap M ms | delegated to BullMQ | UNBOUNDED (defect) | multiplied: N wrapper x M job attempts (defect)}
Idempotency: {GET/PUT/DELETE only | Idempotency-Key on POST | app-owned claim key | NONE on a retried POST (defect) | N/A}
Breaker: {open-after / half-open policy, and what it counts | none}
Error Translation: {what HTTP statuses -> what domain errors | none - vendor error leaks (defect)}
Tests: {MSW handler at path/to/setup.ts | missing | mocks global.fetch (defect)}
```

## Avoid

- `fetch(url)` without `AbortSignal.timeout(...)` - Node's `fetch` has no default timeout
- Retrying POST without an `Idempotency-Key` - duplicate writes
- Unbounded in-process retry loops (sync handlers must respond in seconds, not minutes)
- Letting `got`/`axios` retry interleave with your own retry layer - pick one. `axiosRetry(client, opts)` configures by side effect and returns `void`, so passing it to `interceptors.response.use(...)` silently wires nothing
- Retrying only on status codes - timeouts and connection errors throw and never reach a status check
- Piping `req.signal` into a POST/PATCH - a client disconnect makes the write's outcome unknown
- Per-request client instantiation (`got.extend` / `axios.create` in the handler body)
- Leaking `HTTPError` / `AxiosError` / `TypeError: fetch failed` past the vendor wrapper
- Mocking `global.fetch` or `axios.get` in tests - use MSW, exercise the real wrapper
- Treating `Retry-After: 600` as if it were milliseconds (it's seconds, or an HTTP-date)
- Retrying 4xx responses (except 408 / 429)
- One mega-`HttpClient` class for all vendors - one wrapper per vendor, each with its own error map
