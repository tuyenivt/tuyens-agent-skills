---
name: node-express-patterns
description: Express application patterns with TypeScript - router organization, middleware chain ordering, async error handling, Zod validation, central error middleware, webhook handling, security headers, health endpoints, and graceful shutdown.
metadata:
  category: backend
  tags: [node, typescript, express, middleware, validation, patterns]
user-invocable: false
---

# Express Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or extending an Express application with TypeScript
- Setting up middleware chain, validation, or error handling in Express
- Implementing webhook endpoints that need raw body reading and signature validation
- Reviewing Express code for structural or security issues

## Rules

- Middleware order matters: helmet -> cors -> auth -> validation -> handler -> error handler
- All async route handlers must be wrapped to catch rejected promises
- Central error middleware must have exactly 4 parameters (Express uses arity detection)
- Never expose raw error details to clients in production
- No business logic in route handlers - extract to service layer

## Patterns

### Router Organization

- Separate router per resource: `orders.router.ts`, `payments.router.ts`
- Router mounting: `app.use('/api/v1/orders', ordersRouter)`
- Controller functions separate from router definition

```typescript
// routes/orders.router.ts
const router = Router();

router.get("/", asyncHandler(orderController.list));
router.get("/:id", asyncHandler(orderController.getById));
router.post(
  "/",
  validate(createOrderSchema),
  asyncHandler(orderController.create),
);
router.patch(
  "/:id",
  validate(updateOrderSchema),
  asyncHandler(orderController.update),
);
router.delete("/:id", asyncHandler(orderController.remove));

export default router;
```

### Async Handler Wrapper

Every async route handler must be wrapped to forward rejected promises to the error middleware. Without this, unhandled rejections crash the process:

```typescript
const asyncHandler =
  (fn: RequestHandler): RequestHandler =>
  (req, res, next) =>
    Promise.resolve(fn(req, res, next)).catch(next);
```

### Validation with Zod

Use Zod schemas for request validation - preferred over class-validator in Express because schemas are plain objects that compose naturally:

```typescript
import { z } from "zod";

const createOrderSchema = z.object({
  body: z.object({
    customerId: z.string().uuid(),
    items: z
      .array(
        z.object({
          productId: z.string().uuid(),
          quantity: z.number().int().positive(),
        }),
      )
      .min(1),
    shippingAddress: z.string().min(1).max(500),
  }),
});

// Reusable validation middleware
const validate =
  (schema: z.ZodSchema) =>
  (req: Request, _res: Response, next: NextFunction) => {
    const result = schema.safeParse({
      body: req.body,
      query: req.query,
      params: req.params,
    });
    if (!result.success) {
      throw new AppError(
        400,
        result.error.issues.map((i) => i.message).join(", "),
      );
    }
    next();
  };

// Usage in router
router.post("/", validate(createOrderSchema), asyncHandler(controller.create));
```

### Error Handling

Central error middleware must have exactly 4 parameters (Express uses arity to detect error handlers):

```typescript
class AppError extends Error {
  constructor(
    public readonly statusCode: number,
    message: string,
    public readonly isOperational = true,
  ) {
    super(message);
  }
}

// Error handler - register LAST, after all routes
const errorHandler: ErrorRequestHandler = (err, _req, res, _next) => {
  if (err instanceof AppError) {
    res.status(err.statusCode).json({ error: err.message });
    return;
  }
  // Unexpected errors - log full details, return generic message
  console.error(err);
  res.status(500).json({ error: "Internal server error" });
};
```

Map domain errors to HTTP status codes consistently:

| Domain Error         | HTTP Status |
| -------------------- | ----------- |
| Validation failure   | 400         |
| Not found            | 404         |
| Conflict (duplicate) | 409         |
| Unauthorized         | 401         |
| Invalid transition   | 422         |
| External timeout     | 503         |

Unhandled rejection handler: `process.on('unhandledRejection')` to catch missed promises.

### Webhook Endpoints

Webhook endpoints from external services (Stripe, GitHub) require reading the raw body for signature validation. Express's `json()` middleware consumes the body, so webhook routes need special handling:

```typescript
// Register webhook route BEFORE json() middleware, or use express.raw()
app.post(
  "/api/v1/webhooks/stripe",
  express.raw({ type: "application/json" }),
  asyncHandler(async (req: Request, res: Response) => {
    const sig = req.headers["stripe-signature"] as string;
    const event = stripe.webhooks.constructEvent(
      req.body,
      sig,
      STRIPE_WEBHOOK_SECRET,
    );
    await paymentService.handleWebhookEvent(event);
    res.json({ received: true });
  }),
);

// THEN register json() for all other routes
app.use(express.json());
app.use("/api/v1/orders", ordersRouter);
```

Webhook endpoints should NOT be behind JWT auth middleware - they use their own signature-based authentication.

### TypeScript Patterns

- Typed request/response: `Request<Params, ResBody, ReqBody, Query>`
- Extend Request interface for auth: `declare module 'express' { interface Request { user?: User } }`
- Use Zod's `z.infer<typeof schema>` to derive types from validation schemas

### Security

- `helmet()` for security headers (first middleware)
- `cors({ origin: allowedOrigins })` - never use `cors()` with no options in production (allows all origins)
- Rate limiting with `express-rate-limit` on auth endpoints

### Health and Readiness Endpoints

```typescript
app.get("/health", (_req, res) => res.json({ status: "ok" }));
app.get(
  "/ready",
  asyncHandler(async (_req, res) => {
    await dataSource.query("SELECT 1");
    res.json({ status: "ready" });
  }),
);
```

### Graceful Shutdown

```typescript
const server = app.listen(port);

process.on("SIGTERM", () => {
  server.close(() => process.exit(0)); // finish in-flight requests, then exit
});
```

## Edge Cases

- **Webhook body already parsed**: If `express.json()` runs before the webhook route, the raw body is consumed and signature validation fails. Register webhook routes before `express.json()` or use `express.raw()` on the specific route.
- **Error handler not invoked**: If the error middleware has fewer than 4 parameters, Express treats it as a regular middleware and skips it. Always include all 4 parameters, even if unused (prefix with `_`).
- **Async errors in middleware**: Middleware that returns promises must also be wrapped with `asyncHandler` or have explicit `.catch(next)`.

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

- Not catching async errors (unhandled promise rejection crashes the process)
- Business logic in route handlers (extract to service layer)
- Using `any` for request types (defeats TypeScript)
- Missing error handling middleware (errors become unhandled rejections)
- `cors()` with no origin restriction in production
- Error handler with fewer than 4 parameters (Express will not recognize it as an error handler)
- `express.json()` before webhook routes (consumes raw body, breaks signature validation)
- Putting webhook routes behind JWT auth middleware (they use signature-based auth)
