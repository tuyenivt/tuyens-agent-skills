---
name: node-express-patterns
description: Express + TypeScript patterns: router structure, middleware ordering, async error handling, Zod validation, webhooks, graceful shutdown.
metadata:
  category: backend
  tags: [node, typescript, express, middleware, validation, patterns]
user-invocable: false
---

# Express Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or extending Express + TypeScript applications
- Setting up middleware, validation, error handling, or webhooks
- Reviewing Express code for structural or security issues

## Rules

- Middleware order: helmet -> cors -> webhook (raw) -> json -> auth -> validation -> handler -> errorHandler (last)
- Express 4: wrap every async handler/middleware to forward rejections to `next`. Express 5 does this natively - there the wrapper is dead code, so strip `asyncHandler` from every example below
- Error middleware must take exactly 4 parameters (Express detects by arity), and must check `res.headersSent` before writing - a failure mid-stream otherwise throws `ERR_HTTP_HEADERS_SENT`
- Never expose raw error details to clients in production
- No business logic in route handlers - delegate to services
- Two independent webhook rules: raw-body routes mount **before** `express.json()`, and signature-authenticated routes mount outside the JWT middleware's scope. Either applies alone - a bodyless signed-link GET needs the auth bypass without the raw parser
- Bind auth at the router mount (`app.use('/api/v1/orders', requireAuth, ordersRouter)`), never `app.use(requireAuth)` globally - global auth puts webhooks and health probes behind JWT
- Behind a proxy or ingress, `app.set('trust proxy', 1)` before `express-rate-limit`, or every client shares the proxy's IP and the limiter blocks everyone at once

## Patterns

### Router Organization

One router per resource (`orders.router.ts`), controllers separate from routing, mounted at `app.use('/api/v1/orders', ordersRouter)`.

```typescript
const router = Router();
router.get("/:id", asyncHandler(orderController.getById));
router.post("/", validate(createOrderSchema), asyncHandler(orderController.create));
export default router;
```

### Async Handler

Check the Express major version in `package.json` first. Express 5 forwards rejected promises to error middleware natively - no wrapper needed. Express 4 does not: an unwrapped rejection becomes an unhandled rejection and crashes the process.

```typescript
// Express 4 only
const asyncHandler =
  (fn: RequestHandler): RequestHandler =>
  (req, res, next) =>
    Promise.resolve(fn(req, res, next)).catch(next);
```

On Express 4, middleware returning promises must also be wrapped or chain `.catch(next)`.

### Validation with Zod

Zod schemas compose as plain objects; derive types with `z.infer<typeof schema>`.

```typescript
const createOrderSchema = z.object({
  body: z.object({
    customerId: z.string().uuid(),
    items: z.array(z.object({ productId: z.string().uuid(), quantity: z.number().int().positive() })).min(1),
  }),
  query: z.object({ limit: z.coerce.number().int().min(1).max(100).default(20) }),
  headers: z.object({ "x-tenant-id": z.string().uuid() }),
});

const validate = (schema: z.ZodSchema): RequestHandler => (req, _res, next) => {
  const r = schema.safeParse({ body: req.body, query: req.query, params: req.params, headers: req.headers });
  if (!r.success) return next(new AppError(400, r.error.issues.map(i => `${i.path.join(".")}: ${i.message}`).join(", ")));
  req.valid = r.data;   // keep the parsed output - coercions and defaults exist only here
  next();
};
```

Parse `headers` and `query` in the same schema, and read `req.valid`, never `req.query`: coerced numbers and defaults live only on the parse result, and on Express 5 `req.query` is a getter that throws on assignment. Declare `req.valid` via the same global-namespace augmentation used for `req.user`. Use `next(err)` rather than `throw` so the handler works unwrapped on Express 4.

### Error Handling

Minimal wiring form below. The full domain hierarchy (`code`, `retryable`, subclasses, ORM translation) is owned by `node-exception-handling` - adopt its `AppError` once domain errors grow beyond status + message; keep the field name `status` so both stay compatible.

```typescript
class AppError extends Error {
  constructor(public readonly status: number, message: string, public readonly isOperational = true) {
    super(message);
  }
}

const errorHandler: ErrorRequestHandler = (err, _req, res, next) => {
  if (res.headersSent) return next(err);      // mid-stream failure - Node must close the response
  if (err instanceof AppError) return void res.status(err.status).json({ error: err.message });
  console.error(err);
  res.status(500).json({ error: "Internal server error" });
};
```

Domain-to-HTTP mapping:

| Domain Error         | HTTP |
| -------------------- | ---- |
| Validation failure   | 400  |
| Unauthorized         | 401  |
| Forbidden / tenant mismatch | 403 |
| Not found            | 404  |
| Conflict (duplicate) | 409  |
| Invalid transition   | 422  |
| Rate limited         | 429  |
| External timeout     | 503  |

Also register `process.on('unhandledRejection')` as a last-resort backstop.

### Webhook Endpoints

External webhooks (Stripe, GitHub) need the raw body for signature validation. Mount the raw-body route before `express.json()`:

```typescript
app.post(
  "/api/v1/webhooks/stripe",
  express.raw({ type: "application/json" }),
  asyncHandler(async (req, res) => {
    const event = stripe.webhooks.constructEvent(
      req.body,
      req.headers["stripe-signature"] as string,
      STRIPE_WEBHOOK_SECRET,
    );
    await paymentService.handleWebhookEvent(event);
    res.json({ received: true });
  }),
);

app.use(express.json());
app.use("/api/v1/orders", ordersRouter);
```

### TypeScript

- Typed handlers: `Request<Params, ResBody, ReqBody, Query>`
- Extend for auth via the global namespace (module augmentation of `'express'` fails silently - `Request` lives in `express-serve-static-core`):

```typescript
declare global {
  namespace Express {
    interface Request { user?: User }
  }
}
```

### Security

- `helmet()` first
- `cors({ origin: allowedOrigins, credentials: true })` - never bare `cors()` in production; `credentials` is required for cookie or `Authorization` cross-origin calls, and is incompatible with `origin: '*'`
- `express-rate-limit` on auth endpoints (see the `trust proxy` rule)

### Health and Shutdown

Liveness must not touch dependencies; readiness must, and must flip to failing *before* the server stops accepting, so the load balancer drains first.

```typescript
let ready = true;
app.get("/health", (_req, res) => res.json({ status: "ok" }));          // liveness - no I/O
app.get("/ready", async (_req, res) => {                                 // readiness
  if (!ready) return void res.status(503).json({ status: "draining" });
  await dataSource.query("SELECT 1");
  res.json({ status: "ready" });
});

const server = app.listen(port);
process.on("SIGTERM", async () => {
  ready = false;                                    // fail readiness first
  await new Promise((r) => setTimeout(r, 5_000));   // let the LB observe it
  const hard = setTimeout(() => process.exit(1), 25_000).unref();   // bounded drain
  server.closeIdleConnections?.();                  // keep-alive sockets never close on their own
  server.close(async () => { clearTimeout(hard); await dataSource.destroy(); process.exit(0); });
});
```

`terminationGracePeriodSeconds` must exceed the readiness delay plus the hard-stop timer.

## Output Format

When authoring, emit this block plus the wiring code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it.

```
## Express Architecture

Express major version: {4 | 5} - determines whether asyncHandler is required

### Middleware Stack
| Order | Middleware | Scope (app / router) | Purpose |
|-------|-----------|----------------------|---------|
| 1 | helmet | app | security headers |
| 2 | cors | app | CORS |
| 3 | webhook routes | router | raw body and/or signature auth, outside JWT |
| 4 | express.json() | app | JSON body parsing |
| 5 | auth | router mount | JWT validation |
| 6 | routes | router | API handlers |
| 7 | errorHandler | app, last | centralized error handling |

### Router Structure
| Router | Mount Path | Endpoints | Auth |
|--------|-----------|-----------|------|

### Validation Schemas
| Endpoint | body / query / params / headers | Failure status |
|----------|---------------------------------|----------------|

### Error Mapping
| Domain error | Status |
|--------------|--------|

### Shutdown
[readiness flip, drain delay, hard-stop timer, resources released]
```

## Avoid

- Unwrapped async handlers on Express 4 (rejections crash the process)
- Business logic in route handlers
- `any` for request types
- `cors()` with no origin in production
- `express.json()` before webhook routes (consumes raw body)
- Webhook routes behind JWT auth (use signature-based auth)
