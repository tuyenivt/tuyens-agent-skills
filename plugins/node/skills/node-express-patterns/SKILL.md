---
name: node-express-patterns
description: "Express patterns with TypeScript: router organization, middleware chain, error handling middleware, async handler wrapper, Zod validation, security headers, and request typing."
user-invocable: false
---

Cover:

1. ROUTER ORGANIZATION:
   - Separate router per resource: orders.router.ts, payments.router.ts
   - Router mounting: app.use('/api/v1/orders', ordersRouter)
   - Controller functions separate from router definition

2. MIDDLEWARE:
   - Order matters: helmet → cors → auth → validation → handler → error handler
   - Auth middleware: verify JWT, attach user to req
   - Async handler wrapper (catch async errors):

```typescript
const asyncHandler =
  (fn: RequestHandler): RequestHandler =>
  (req, res, next) =>
    Promise.resolve(fn(req, res, next)).catch(next);
```

3. VALIDATION WITH ZOD:

   Use Zod schemas for request validation — preferred over class-validator in Express because schemas are plain objects that compose naturally:

```typescript
import { z } from "zod";

const createProductSchema = z.object({
  body: z.object({
    name: z.string().min(1).max(255),
    price: z.number().positive(),
    category: z.string().min(1),
    stock: z.number().int().nonnegative(),
  }),
});

// Reusable validation middleware
const validate =
  (schema: z.ZodSchema) =>
  (req: Request, _res: Response, next: NextFunction) => {
    const result = schema.safeParse({ body: req.body, query: req.query, params: req.params });
    if (!result.success) {
      throw new AppError(400, result.error.issues.map((i) => i.message).join(", "));
    }
    next();
  };

// Usage in router
router.post("/", validate(createProductSchema), asyncHandler(controller.create));
```

4. ERROR HANDLING:

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

   - Unhandled rejection handler: process.on('unhandledRejection') to catch missed promises

5. TYPESCRIPT PATTERNS:
   - Typed request/response: Request<Params, ResBody, ReqBody, Query>
   - Extend Request interface for auth: declare module 'express' { interface Request { user?: User } }
   - Use Zod's `z.infer<typeof schema>` to derive types from validation schemas

6. SECURITY:
   - `helmet()` for security headers (first middleware)
   - `cors({ origin: allowedOrigins })` - never use `cors()` with no options in production (allows all origins)
   - Rate limiting with `express-rate-limit` on auth endpoints

7. GRACEFUL SHUTDOWN:

```typescript
const server = app.listen(port);

process.on("SIGTERM", () => {
  server.close(() => process.exit(0)); // finish in-flight requests, then exit
});
```

8. ANTI-PATTERNS:
   - Not catching async errors (unhandled promise rejection crashes the process)
   - Business logic in route handlers (extract to service layer)
   - Using `any` for request types (defeats TypeScript)
   - Missing error handling middleware (errors become unhandled rejections)
   - `cors()` with no origin restriction in production
