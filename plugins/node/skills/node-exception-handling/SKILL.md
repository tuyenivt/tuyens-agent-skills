---
name: node-exception-handling
description: Node.js exceptions - NestJS filters, Express middleware, AppError hierarchy, Result vs throw, BullMQ retry, ORM translation, Sentry capture-once.
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, errors, exceptions, bullmq, sentry]
user-invocable: false
---

> Load `Use skill: stack-detect` first. `Framework` picks the NestJS filter or the Express middleware (read the Express major from `package.json`), `ORM` and `Database` pick the driver error codes, and the detection surfaces only in the `Stack:` line below.

Single owner for the application-wide rescue contract. `node-nestjs-patterns` / `node-express-patterns` show framework wiring; this skill owns the domain-error hierarchy, retry propagation, ORM translation at the boundary, and Sentry capture discipline. Workflows (`task-node-implement`, `task-node-review-observability`) delegate here.

## When to Use

- Adding a new domain error or HTTP exception
- Wiring a NestJS exception filter or Express error middleware
- Deciding throw vs `Result<T, E>` for a service boundary
- BullMQ processor error handling - which errors retry, which don't
- Sentry / OpenTelemetry capture: making sure each error fires once

## Rules

- One global exception filter (NestJS `@Catch()`) or one terminal error middleware (Express) - never per-controller / per-route ad hoc. Express detects error middleware by **arity**: exactly four parameters, and registered after every router. Three parameters silently makes it an ordinary handler whose `res` is really `next`; registering it early makes it unreachable and orphans every `next(err)`
- Domain errors extend a typed `AppError`; HTTP translation lives at the boundary, not in services. Services throw typed errors and never re-catch one domain error to rewrap it as another
- Driver, ORM, and vendor-SDK errors (`P2002`, `P2025`, `QueryFailedError`, `StripeCardError`) are translated to domain errors once, at the adapter that owns the dependency (repository, vendor wrapper). Never leak Prisma / TypeORM / SDK types to controllers
- `Result<T, E>` only when the caller branches on several failure shapes that carry data (a card decline vs insufficient funds). Default to throw - it preserves the stack and lets the filter centralize the response shape
- BullMQ processors decide per error: resolve when a retry finds the work already done; stop without retry on a non-retryable `AppError` (`retryable === false`); let everything else throw so BullMQ applies `attempts` + `backoff`
- Sentry captures each error exactly once, at the **process's** outermost boundary: the global filter / middleware for HTTP, `worker.on('failed')` for a queue, the backstops for the rest. A standalone worker has no filter - wiring only the filter leaves every exhausted job dark. Don't `Sentry.captureException` in the service, then re-throw - the boundary doubles it
- Capture the **final** outcome, not each attempt: `attempts: 5` fires five `failed` events, so the outcome is final when `job.attemptsMade >= (job.opts.attempts ?? 1)` or the error is an `UnrecoverableError`. Capture it unless it maps to 4xx - errors that map to 4xx are logged, never captured
- No bare `catch (e) { console.log(e) }`, no `catch (e) { throw e }` no-op rethrow, no `catch (e) { /* ignore */ }`
- `process.on('unhandledRejection')` and `process.on('uncaughtException')` registered once as last-resort backstops that log, flush, and exit (let the orchestrator restart)

## Patterns

### AppError Hierarchy

```typescript
// One base, narrow subclasses, no parallel hierarchies per module.
// `super(message, { cause })` and `.cause` need tsconfig `lib` ES2022+ (target ES2022 includes it).
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly status: number,
    public readonly retryable: boolean = false,
    options?: { cause?: unknown },
  ) {
    super(message, options);
    this.name = this.constructor.name;
  }
}

export class ValidationError   extends AppError { constructor(m: string, c?: unknown) { super(m, 'validation',    400, false, { cause: c }); } }
export class UnauthorizedError extends AppError { constructor(m: string, c?: unknown) { super(m, 'unauthorized',  401, false, { cause: c }); } }
export class ForbiddenError    extends AppError { constructor(m: string, c?: unknown) { super(m, 'forbidden',     403, false, { cause: c }); } }
export class NotFoundError     extends AppError { constructor(m: string, c?: unknown) { super(m, 'not_found',     404, false, { cause: c }); } }
export class ConflictError     extends AppError { constructor(m: string, c?: unknown) { super(m, 'conflict',      409, false, { cause: c }); } }
export class InvalidStateError extends AppError { constructor(m: string, c?: unknown) { super(m, 'invalid_state', 422, false, { cause: c }); } }
export class UpstreamError     extends AppError { constructor(m: string, c?: unknown) { super(m, 'upstream',      503, true,  { cause: c }); } }
export class InternalError     extends AppError { constructor(m: string, c?: unknown) { super(m, 'internal',      500, false, { cause: c }); } }

// Worker-only sentinel: a retry found the work already done. Not an AppError, so it can never
// reach an HTTP response; the processor resolves on it.
export class AlreadySatisfiedError extends Error {}
```

`retryable` lets BullMQ processors decide retry-vs-stop without sniffing the message. `{ cause }` chains the original error.

### Domain-to-HTTP Mapping

| Domain               | HTTP | Retryable | Notes                                    |
| -------------------- | ---- | --------- | ---------------------------------------- |
| ValidationError      | 400  | no        | Bad input - never auto-retry             |
| UnauthorizedError    | 401  | no        |                                          |
| ForbiddenError       | 403  | no        |                                          |
| NotFoundError        | 404  | no        |                                          |
| ConflictError        | 409  | no        | Duplicate / idempotency collision        |
| InvalidStateError    | 422  | no        | State machine rejection                  |
| UpstreamError        | 503  | yes       | Third-party 5xx / timeout / rate limit   |
| InternalError        | 500  | no        | Wrap a known-deterministic bug (`TypeError`, `RangeError`) so it stops instead of retrying |
| Unknown (`Error`)    | 500  | yes, bounded by `attempts` | An untyped error in a processor throws and burns every configured attempt; a transient untyped failure (`ECONNRESET`, a pool timeout) is what those attempts are for |

In a worker the HTTP column is unused; `retryable` is the only column that decides anything.

### NestJS Global Filter

```typescript
import type { Request, Response } from 'express';
import { InjectPinoLogger, PinoLogger } from 'nestjs-pino';   // PinoLogger takes (obj, msg); nestjs-pino's Logger is Nest-shaped (msg, context)

@Catch()
export class AppExceptionFilter implements ExceptionFilter {
  constructor(@InjectPinoLogger(AppExceptionFilter.name) private readonly logger: PinoLogger) {}

  catch(ex: unknown, host: ArgumentsHost): void {
    if (host.getType() !== 'http') throw ex;     // GraphQL / RPC contexts have their own handling
    const res = host.switchToHttp().getResponse<Response>();
    const req = host.switchToHttp().getRequest<Request>();

    const status = ex instanceof AppError ? ex.status
      : ex instanceof HttpException ? ex.getStatus() : 500;

    if (status >= 500) {
      this.logger.error({ err: ex, path: req.url }, 'unhandled');   // pino serializes `err` incl. its cause chain
      Sentry.captureException(ex);                                    // this transport's single capture site
    } else {
      this.logger.warn({ err: ex, path: req.url }, 'client error');
    }

    if (ex instanceof AppError) return void res.status(status).json({ error: ex.code, message: ex.message });
    if (ex instanceof HttpException) {                               // built-ins, incl. ValidationPipe's message array
      const body = ex.getResponse();
      const message = typeof body === 'string' ? body : (body as { message?: unknown }).message;
      return void res.status(status).json({ error: `http_${status}`, message });   // same envelope as AppError
    }
    res.status(500).json({ error: 'internal' });
  }
}

// app.module.ts
{ provide: APP_FILTER, useClass: AppExceptionFilter }
```

### Express Terminal Middleware

```typescript
// Registered LAST, after all routes
const errorHandler: ErrorRequestHandler = (err, req, res, next) => {
  if (res.headersSent) return next(err);           // mid-stream failure: let Node close the response
  // body-parser and other http-errors carry their own 4xx (malformed JSON 400, too large 413)
  const status = err instanceof AppError ? err.status
    : Number.isInteger(err?.status) && err.status >= 400 && err.status < 500 ? err.status : 500;
  if (status >= 500) {
    req.log.error({ err }, 'unhandled');
    Sentry.captureException(err);
  } else {
    req.log.warn({ err }, 'client error');
  }
  if (err instanceof AppError) return void res.status(status).json({ error: err.code, message: err.message });
  res.status(status).json({ error: status === 500 ? 'internal' : `http_${status}` });
};

app.use(errorHandler);
```

Async errors reach it natively on Express 5. On Express 4 only, wrap every async handler - `(fn) => (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next)`. Prefer the wrapper over `express-async-errors`: the package patches Express 4's internal router and fails to load on Express 5 (`express/lib/router/layer` is gone), so it blocks the upgrade.

### ORM Error Translation at the Boundary

```typescript
// Prisma - repository boundary
try {
  return await this.prisma.user.create({ data });
} catch (e) {
  if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2002') {
    const t = e.meta?.target;                        // field names on PostgreSQL, the index name string on MySQL
    throw new ConflictError(`duplicate ${Array.isArray(t) ? t.join(',') : String(t ?? '')}`, e);
  }
  throw e;     // unknown - let the global filter handle it
}
// P2025 comes from findUniqueOrThrow / findFirstOrThrow, update / delete (record not found), and create with
// a nested connect to a missing related record - translate it on those calls: NotFoundError('order not found', e)

// TypeORM - the code is the engine's
try {
  return await this.repo.save(entity);
} catch (e) {
  const code = e instanceof QueryFailedError ? (e.driverError as { code?: string }).code : undefined;
  if (code === '23505' || code === 'ER_DUP_ENTRY') throw new ConflictError('unique violation', e);
  if (code === '23503' || code === 'ER_NO_REFERENCED_ROW_2') throw new ValidationError('referenced row does not exist', e);
  throw e;
}
```

| Violation   | PostgreSQL (`pg`) | MySQL (`mysql2`)          | Prisma  |
|-------------|-------------------|---------------------------|---------|
| Unique      | `23505`           | `ER_DUP_ENTRY` (1062)     | `P2002` |
| Foreign key | `23503`           | `ER_NO_REFERENCED_ROW_2` (1452) | `P2003` |

Never let `Prisma.PrismaClientKnownRequestError` or `QueryFailedError` reach the controller - they leak schema details and bypass the domain error contract.

### Vendor SDK Errors

Translate at the vendor wrapper, same as ORM errors. Stripe as the example:

| stripe-node error | Domain | Why |
|-------------------|--------|-----|
| `StripeCardError` | `ValidationError` (or a `Result` variant, below) | the card's problem - no retry fixes it |
| `StripeRateLimitError`, `StripeConnectionError`, `StripeAPIError` | `UpstreamError` | transient |
| `StripeInvalidRequestError` code `idempotency_key_in_use` | `UpstreamError` | a concurrent request with the same key is still in flight - retry after backoff |
| `StripeIdempotencyError` | `InternalError` | the same key reused with different parameters - a bug, not a retry |
| `StripeInvalidRequestError` (other) | `InternalError` | our request is wrong - a bug, not a retry |
| `StripeAuthenticationError` / `StripePermissionError` | `InternalError` | our key or config is wrong - page, don't blame the client |

### Result vs Throw

Default to throw. Use `Result<T, E>` only when the caller branches on several failure shapes that carry data:

```typescript
type ChargeResult =
  | { ok: true; chargeId: string }
  | { ok: false; reason: 'declined'; declineCode: string; raw: Stripe.errors.StripeCardError };

const r = await this.payments.charge(...);
if (!r.ok) return this.askForAnotherCard(r.declineCode);   // user-facing flow keyed on the decline
```

A queue processor whose every failure means "retry or stop" throws - its caller is BullMQ, which only understands throw vs resolve.

### BullMQ Retry Propagation

```typescript
@Processor(ORDER_QUEUE)
export class OrderProcessor extends WorkerHost {
  constructor(
    private readonly orders: OrdersService,
    @InjectPinoLogger(OrderProcessor.name) private readonly logger: PinoLogger,
  ) {
    super();
  }

  async process(job: Job<{ orderId: string }>): Promise<void> {
    try {
      await this.orders.fulfill(job.data.orderId);
    } catch (e) {
      if (e instanceof AlreadySatisfiedError) return;          // duplicate delivery - the work is done
      if (e instanceof AppError && !e.retryable) {
        // Retry won't help. Record it only if nothing newer won (at-least-once).
        await this.orders.markFailedIfPending(job.data.orderId, e.code);   // UPDATE ... WHERE status = 'PENDING'
        if (e.status < 500) this.logger.warn({ err: e, jobId: job.id }, 'domain rejection');
        // UnrecoverableError takes only a message - attach the cause so onFailed can classify it
        throw Object.assign(new UnrecoverableError(e.message), { cause: e });   // failed, no retry, visible
      }
      throw e;                                                 // BullMQ applies attempts + backoff
    }
  }

  @OnWorkerEvent('failed')                                     // the worker's capture site - no filter here
  onFailed(job: Job | undefined, err: Error): void {
    const final = !job || err.name === 'UnrecoverableError' || job.attemptsMade >= (job.opts.attempts ?? 1);
    const source = err.cause instanceof AppError ? err.cause : err;
    const clientError = source instanceof AppError && source.status < 500;
    if (final && !clientError) Sentry.captureException(source, { extra: { jobId: job?.id } });
  }
}
```

`attempts` and `backoff` are configured on the queue (see `node-bullmq-patterns`). Throwing `UnrecoverableError` for a non-retryable error keeps the job in the failed set (visible, countable) without retrying; resolving instead would count it as completed. A 4xx-class rejection is logged, not captured; a non-retryable 5xx (`InternalError`, a vendor auth failure) is captured, the same as the HTTP filter does. The guarded `markFailedIfPending` is what stops a late failing attempt from overwriting a state a concurrent success already wrote.

### Sentry Capture-Once

```typescript
// Bad - double capture
try { await this.orders.fulfill(id); }
catch (e) {
  Sentry.captureException(e);     // first capture
  throw e;                         // global filter captures again
}

// Good - capture only at the process boundary (filter / middleware / worker 'failed' / backstop)
```

For context on an intermediate failure, log it or add `Sentry.addBreadcrumb` - never `captureException` from inside the call path. `span.recordException(err)` + `span.setStatus({ code: SpanStatusCode.ERROR })` on the active span is trace annotation, allowed at the failing layer; it does not count against capture-once. `@sentry/node` 8 must initialise before anything it instruments: `Sentry.init` in its own `instrument.ts`, imported (or `--import`ed) first.

### Last-Resort Backstops

```typescript
// @sentry/node 8's default onUncaughtException / onUnhandledRejection integrations already capture
// both events - the backstop only logs, flushes, and exits
const fatal = (err: unknown, kind: string) => {
  logger.fatal({ err }, kind);
  void Sentry.close(2_000).finally(() => process.exit(1));   // flush first, or the event dies with the process
};
process.on('unhandledRejection', (reason) => fatal(reason, 'unhandledRejection'));
process.on('uncaughtException',  (err)    => fatal(err,    'uncaughtException'));
```

Crash and let the orchestrator (PM2, k8s, systemd) restart. Don't try to keep running after these fire - state is undefined.

## Output Format

Every mode opens with the `Stack:` line. When authoring, emit one block per layer touched; a design request over existing code is both - the findings for what exists, then the authoring blocks for the layer that replaces it. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise - and then its block, with `Translation` and `Capture` describing the current behaviour. A defect spanning two files that act as one boundary (a service and its vendor client) anchors to the file where the translation should live and names the other in `Issue:`. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright (throw or `Result`?) gets one `Ruling:` line; both precede the findings.

```
**Stack:** {NestJS | Express 4 | Express 5 | standalone worker} + {Prisma | TypeORM (<engine>) | <driver> (no ORM) | none}

Layer: {NestJS Filter | Express Middleware | Route Handler | Service | Repository Boundary | Vendor SDK Boundary | BullMQ Processor | Worker Event Handler | Bootstrap | Backstop}

Error Type: {AppError subclass | generic untyped `Error` | HttpException | Prisma P-code | QueryFailedError | vendor SDK error | worker sentinel (AlreadySatisfiedError \| UnrecoverableError) | Result variant (returned, not thrown) | none - wiring defect | unknown}

Translation: {source error -> domain error, or "none - leaks as-is"}

Capture: {logger.warn | logger.error | logger.fatal | Sentry | OTel span.recordException | console.* (defect) | none} - list every one that applies

Retry Behavior: {idempotent success (resolve) | terminal, no retry (UnrecoverableError) | transient (throw; attempts + backoff apply) | one-shot (no retry configured on this path)}
```

## Avoid

- Per-controller / per-route try/catch that duplicates the global filter
- Catching to log + rethrow at intermediate layers (doubles Sentry / log volume)
- Leaking `Prisma.PrismaClientKnownRequestError` / `QueryFailedError` past the repository boundary
- `Result<T, E>` everywhere - default to throw; `Result` only for branched failure shapes
- BullMQ processors that retry validation / not-found errors (wastes attempts, hides bugs)
- Sniffing `error.message` strings instead of typed subclasses or error codes
- `catch (e) { throw e }` no-op rethrow - add `{ cause: e }` context or delete
- Trying to recover after `uncaughtException` - exit and let the orchestrator restart
