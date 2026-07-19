---
name: node-exception-handling
description: Node.js exceptions - NestJS filters, Express middleware, AppError hierarchy, Result vs throw, BullMQ retry, ORM translation, Sentry capture-once.
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, errors, exceptions, bullmq, sentry]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack.

Single owner for the application-wide rescue contract. `node-nestjs-patterns` / `node-express-patterns` show framework wiring; this skill owns the domain-error hierarchy, retry propagation, ORM translation at the boundary, and Sentry capture discipline. Workflows (`task-node-implement`, `task-node-review-observability`) delegate here.

## When to Use

- Adding a new domain error or HTTP exception
- Wiring a NestJS exception filter or Express error middleware
- Deciding throw vs `Result<T, E>` for a service boundary
- BullMQ processor error handling - which errors retry, which don't
- Sentry / OpenTelemetry capture: making sure each error fires once

## Rules

- One global exception filter (NestJS `@Catch()`) or one terminal error middleware (Express) - never per-controller / per-route ad hoc
- Domain errors extend a typed `AppError` / `DomainError` base; HTTP translation lives at the boundary, not in services
- Services `throw` typed exceptions; controllers / handlers translate to HTTP via the global filter / middleware (don't catch-and-rewrap inside the service layer)
- `Result<T, E>` only when the caller routinely branches on the failure (Stripe charge, idempotency conflict resolution). Default to throw - it preserves stack and lets the filter centralize the response shape
- BullMQ processors rescue **and stop** on non-retryable domain errors (`ValidationError`, `NotFoundError`, `ConflictError`); let everything else throw so BullMQ applies `attempts` + `backoff`
- ORM errors (`P2002`, `P2025`, `QueryFailedError`) translate to domain errors at the repository / service boundary - never leak Prisma / TypeORM types to controllers
- Sentry captures each error exactly once - at the global filter / middleware. Don't `Sentry.captureException` in the service, then re-throw - the filter doubles it
- No bare `catch (e) { console.log(e) }`, no `catch (e) { throw e }` no-op rethrow, no `catch (e) { /* ignore */ }`
- `process.on('unhandledRejection')` and `process.on('uncaughtException')` registered once as last-resort backstops that log and exit (let the orchestrator restart)

## Patterns

### AppError Hierarchy

```typescript
// One base, narrow subclasses, no parallel hierarchies per module
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
```

`retryable` lets BullMQ processors decide retry-vs-stop without sniffing the message. `{ cause }` chains the original error - the filter logs the chain.

### Domain-to-HTTP Mapping

| Domain               | HTTP | Retryable | Notes                                    |
| -------------------- | ---- | --------- | ---------------------------------------- |
| ValidationError      | 400  | no        | Bad input - never auto-retry             |
| Unauthorized         | 401  | no        |                                          |
| Forbidden            | 403  | no        |                                          |
| NotFoundError        | 404  | no        |                                          |
| ConflictError        | 409  | no        | Duplicate / idempotency collision        |
| InvalidStateError    | 422  | no        | State machine rejection                  |
| UpstreamError        | 503  | yes       | Third-party 5xx / timeout                |
| Unknown (`Error`)    | 500  | yes       | Last-resort - log + alert                |

### NestJS Global Filter

```typescript
@Catch()
export class AppExceptionFilter implements ExceptionFilter {
  constructor(private readonly logger: Logger) {}

  catch(ex: unknown, host: ArgumentsHost): void {
    const res = host.switchToHttp().getResponse<Response>();
    const req = host.switchToHttp().getRequest<Request>();

    if (ex instanceof AppError) {
      this.logger.warn({ code: ex.code, path: req.url, cause: ex.cause }, ex.message);
      res.status(ex.status).json({ error: ex.code, message: ex.message });
      return;
    }
    if (ex instanceof HttpException) {                       // built-in Nest exceptions
      const r = ex.getResponse();
      res.status(ex.getStatus()).json(typeof r === 'string' ? { message: r } : r);
      return;
    }
    this.logger.error({ err: ex, path: req.url }, 'unhandled');
    res.status(500).json({ error: 'internal' });
  }
}

// app.module.ts
{ provide: APP_FILTER, useClass: AppExceptionFilter }
```

The filter is the single Sentry / OTel capture site - inject the SDK and call it here, nowhere else.

### Express Terminal Middleware

```typescript
// Registered LAST, after all routes
const errorHandler: ErrorRequestHandler = (err, req, res, _next) => {
  if (err instanceof AppError) {
    req.log.warn({ code: err.code, cause: err.cause }, err.message);
    return res.status(err.status).json({ error: err.code, message: err.message });
  }
  req.log.error({ err }, 'unhandled');
  res.status(500).json({ error: 'internal' });
};

app.use(errorHandler);

// Async routes wrapped so rejections reach the middleware
const asyncHandler = (fn: RequestHandler): RequestHandler =>
  (req, res, next) => Promise.resolve(fn(req, res, next)).catch(next);
```

`express-async-errors` works too; pick one mechanism and apply it consistently.

### ORM Error Translation at the Boundary

```typescript
// Prisma - at the repository / service boundary
try {
  return await this.prisma.user.create({ data });
} catch (e) {
  if (e instanceof Prisma.PrismaClientKnownRequestError) {
    if (e.code === 'P2002') throw new ConflictError('email already registered', e);
    if (e.code === 'P2025') throw new NotFoundError('user not found', e);
  }
  throw e;     // unknown - let the global filter handle it
}

// TypeORM
try {
  return await this.repo.save(entity);
} catch (e) {
  if (e instanceof QueryFailedError && (e.driverError as { code?: string }).code === '23505') {
    throw new ConflictError('unique violation', e);
  }
  throw e;
}
```

Never let `Prisma.PrismaClientKnownRequestError` or `QueryFailedError` reach the controller - they leak schema details and bypass the domain error contract.

### Result vs Throw

Default to throw. Use `Result<T, E>` only when the caller routinely branches on the failure shape:

```typescript
// Justified - Stripe charge has a structured non-exceptional failure mode
type ChargeResult =
  | { ok: true; chargeId: string }
  | { ok: false; reason: 'declined' | 'insufficient_funds'; raw: Stripe.Error };

async charge(...): Promise<ChargeResult> { ... }

// caller
const r = await this.payments.charge(...);
if (!r.ok && r.reason === 'declined') { /* user-facing flow */ }
if (!r.ok && r.reason === 'insufficient_funds') { /* different flow */ }
```

If the caller's reaction to every failure variant is "log and bubble up", that's a throw, not a Result.

### BullMQ Retry Propagation

```typescript
@Processor(ORDER_QUEUE)
export class OrderProcessor extends WorkerHost {
  async process(job: Job<{ orderId: string }>): Promise<void> {
    try {
      await this.orders.fulfill(job.data.orderId);
    } catch (e) {
      if (e instanceof AppError && !e.retryable) {
        // Domain rejection - retry won't help. Mark and stop.
        await this.orders.markFailed(job.data.orderId, e.code);
        return;                                    // resolve = no retry
      }
      throw e;                                     // BullMQ applies attempts + backoff
    }
  }
}
```

`attempts` and `backoff` configured on the queue (see `node-bullmq-patterns`). The processor's only job is deciding which errors are domain-final (resolve) vs transient (throw).

### Sentry Capture-Once

```typescript
// Bad - double capture
try { await this.orders.fulfill(id); }
catch (e) {
  Sentry.captureException(e);     // first capture
  throw e;                         // global filter captures again
}

// Good - capture only at the global boundary (filter / middleware / unhandledRejection)
```

If a service needs structured logging on an intermediate failure, use the logger (`pino` / `winston`) - not the error tracker. Sentry is for unhandled exceptions, not breadcrumbs.

### Last-Resort Backstops

```typescript
process.on('unhandledRejection', (reason) => { logger.fatal({ reason }, 'unhandledRejection'); process.exit(1); });
process.on('uncaughtException',  (err)    => { logger.fatal({ err },    'uncaughtException');  process.exit(1); });
```

Crash and let the orchestrator (PM2, k8s, systemd) restart. Don't try to keep running after these fire - state is undefined.

## Output Format

```
Layer: {NestJS Filter | Express Middleware | Repository Boundary | BullMQ Processor | Backstop}
Error Type: {AppError subclass | HttpException | Prisma P-code | QueryFailedError | unknown}
Translation: {what was applied}
Capture: {logger.warn | logger.error | Sentry once at filter | none}
Retry Behavior: {domain-final / transient with attempts+backoff / one-shot}
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
