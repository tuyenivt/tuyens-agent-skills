---
name: node-http-client-patterns
description: Node.js outbound HTTP - AbortSignal.timeout, Retry-After, idempotent retry, Idempotency-Key, BullMQ delegation, per-vendor wrapper, MSW.
metadata:
  category: backend
  tags: [node, typescript, http, fetch, axios, retry, abortsignal, msw, resilience]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Single owner for outbound HTTP discipline. The security workflow checks SSRF (`node-security-patterns`); the perf workflow checks event-loop blocking; this skill owns timeout / retry / idempotency / wrapper structure. Workflows delegate here and flag deviations.

## When to Use

- Calling any third-party HTTP service (Stripe, SendGrid, internal microservices)
- Adding `fetch` / `axios` / `undici` / `got` in a service or processor
- Deciding in-process retry vs BullMQ retry for an outbound call
- Writing tests that hit the network (replace with MSW)

## Rules

- Every outbound call has an `AbortSignal.timeout(ms)` - no infinite hangs (Node `fetch` does not time out by default)
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

// Combine app-level cancel + timeout
const res = await fetch(url, {
  signal: AbortSignal.any([req.signal, AbortSignal.timeout(5_000)]),
});
```

`axios`: `timeout: 5_000`. `undici`: `bodyTimeout` + `headersTimeout`. `got`: `timeout: { request: 5_000 }`. Pick one library per project; don't mix.

### Bounded Retry with Jitter, Honoring `Retry-After`

```typescript
const RETRYABLE = new Set([408, 429, 500, 502, 503, 504]);
const MAX_ATTEMPTS = 3;
const BASE_MS = 200;
const MAX_TOTAL_MS = 3_000;          // in-process ceiling - past this, hand to BullMQ

async function callWithRetry(req: () => Promise<Response>): Promise<Response> {
  let start = Date.now();
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const res = await req();
    if (res.ok || !RETRYABLE.has(res.status)) return res;
    if (attempt === MAX_ATTEMPTS) return res;

    const retryAfter = parseRetryAfter(res.headers.get('retry-after'));
    const backoff = retryAfter ?? Math.min(BASE_MS * 2 ** (attempt - 1), 1_000);
    const jitter = backoff * (0.5 + Math.random() * 0.5);
    if (Date.now() - start + jitter > MAX_TOTAL_MS) return res;     // budget blown
    await new Promise(r => setTimeout(r, jitter));
  }
  throw new Error('unreachable');
}
```

If `Retry-After` exceeds the budget, return the failed response and let the caller decide: surface to the user (4xx domain error) or enqueue a BullMQ job that retries with the queue's `attempts` + `backoff`.

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

Internal POST endpoints should accept an `Idempotency-Key` header and store the key + response for a TTL (Redis or a `idempotency_keys` table). Clients send the same key on retry.

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
      if (e instanceof HTTPError && e.response.statusCode === 402) {
        throw new ValidationError('card declined', e);                // 4xx -> domain
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

```
Vendor: {Stripe | SendGrid | internal-service-X | ...}
Wrapper: {file:line of the client class, or "scattered - needs consolidation"}
Timeout: {ms via AbortSignal.timeout / axios.timeout / got.timeout - or MISSING}
Retry Policy: {none | in-process N attempts, expo+jitter, cap M ms | delegated to BullMQ}
Idempotency: {GET/PUT/DELETE only | Idempotency-Key on POST | N/A}
Error Translation: {what HTTP statuses -> what domain errors}
Tests: {MSW handler at path/to/setup.ts | missing | mocks global.fetch (bad)}
```

## Avoid

- `fetch(url)` without `AbortSignal.timeout(...)` - Node's `fetch` has no default timeout
- Retrying POST without an `Idempotency-Key` - duplicate writes
- Unbounded in-process retry loops (sync handlers must respond in seconds, not minutes)
- Letting `got`/`axios` retry interleave with your own retry layer - pick one
- Per-request client instantiation (`got.extend` / `axios.create` in the handler body)
- Leaking `HTTPError` / `AxiosError` / `TypeError: fetch failed` past the vendor wrapper
- Mocking `global.fetch` or `axios.get` in tests - use MSW, exercise the real wrapper
- Treating `Retry-After: 600` as if it were milliseconds (it's seconds, or an HTTP-date)
- Retrying 4xx responses (except 408 / 429)
- One mega-`HttpClient` class for all vendors - one wrapper per vendor, each with its own error map
