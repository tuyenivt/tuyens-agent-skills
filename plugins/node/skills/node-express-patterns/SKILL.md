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
- Wrap every async handler/middleware to forward rejections to `next`
- Error middleware must take exactly 4 parameters (Express detects by arity)
- Never expose raw error details to clients in production
- No business logic in route handlers - delegate to services
- Webhook routes register before `express.json()` and bypass JWT auth

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

```typescript
const asyncHandler =
  (fn: RequestHandler): RequestHandler =>
  (req, res, next) =>
    Promise.resolve(fn(req, res, next)).catch(next);
```

Middleware returning promises must also be wrapped or chain `.catch(next)`.

### Validation with Zod

Zod schemas compose as plain objects; derive types with `z.infer<typeof schema>`.

```typescript
const createOrderSchema = z.object({
  body: z.object({
    customerId: z.string().uuid(),
    items: z.array(z.object({ productId: z.string().uuid(), quantity: z.number().int().positive() })).min(1),
  }),
});

const validate = (schema: z.ZodSchema): RequestHandler => (req, _res, next) => {
  const result = schema.safeParse({ body: req.body, query: req.query, params: req.params });
  if (!result.success) throw new AppError(400, result.error.issues.map(i => i.message).join(", "));
  next();
};
```

### Error Handling

```typescript
class AppError extends Error {
  constructor(public readonly statusCode: number, message: string, public readonly isOperational = true) {
    super(message);
  }
}

const errorHandler: ErrorRequestHandler = (err, _req, res, _next) => {
  if (err instanceof AppError) return void res.status(err.statusCode).json({ error: err.message });
  console.error(err);
  res.status(500).json({ error: "Internal server error" });
};
```

Domain-to-HTTP mapping:

| Domain Error         | HTTP |
| -------------------- | ---- |
| Validation failure   | 400  |
| Unauthorized         | 401  |
| Not found            | 404  |
| Conflict (duplicate) | 409  |
| Invalid transition   | 422  |
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
- Extend for auth: `declare module 'express' { interface Request { user?: User } }`

### Security

- `helmet()` first
- `cors({ origin: allowedOrigins })` - never bare `cors()` in production
- `express-rate-limit` on auth endpoints

### Health and Shutdown

```typescript
app.get("/health", (_req, res) => res.json({ status: "ok" }));
app.get("/ready", asyncHandler(async (_req, res) => {
  await dataSource.query("SELECT 1");
  res.json({ status: "ready" });
}));

const server = app.listen(port);
process.on("SIGTERM", () => server.close(() => process.exit(0)));
```

## Output Format

```
## Express Architecture

### Middleware Stack
| Order | Middleware | Purpose |
|-------|-----------|---------|
| 1 | helmet | security headers |
| 2 | cors | CORS |
| 3 | webhook routes | raw body for signature validation |
| 4 | express.json() | JSON body parsing |
| 5 | auth | JWT validation |
| 6 | routes | API handlers |
| 7 | errorHandler | centralized error handling |

### Router Structure
| Router | Mount Path | Endpoints |
|--------|-----------|-----------|

### Validation Schemas
[Zod schemas per endpoint]
```

## Avoid

- Unwrapped async handlers (rejections crash the process)
- Business logic in route handlers
- `any` for request types
- `cors()` with no origin in production
- `express.json()` before webhook routes (consumes raw body)
- Webhook routes behind JWT auth (use signature-based auth)
