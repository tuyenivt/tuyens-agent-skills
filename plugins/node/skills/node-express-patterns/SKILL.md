---
name: node-express-patterns
description: "Express patterns with TypeScript: router organization, middleware chain, error handling middleware, async handler wrapper, TypeORM integration, and request validation."
user-invocable: false
---

Cover:

1. ROUTER ORGANIZATION:
   - Separate router per resource: orders.router.ts, payments.router.ts
   - Router mounting: app.use('/api/v1/orders', ordersRouter)
   - Controller functions separate from router definition

2. MIDDLEWARE:
   - Order matters: cors → auth → validation → handler → error handler
   - Auth middleware: verify JWT, attach user to req
   - Validation middleware: zod or joi schema validation
   - Async handler wrapper (catch async errors):

```typescript
const asyncHandler =
  (fn: RequestHandler): RequestHandler =>
  (req, res, next) =>
    Promise.resolve(fn(req, res, next)).catch(next);
```

3. ERROR HANDLING:
   - Central error middleware (must have 4 params: err, req, res, next)
   - Custom AppError class with statusCode and isOperational flag
   - Never expose stack traces in production
   - Unhandled rejection handler: process.on('unhandledRejection')

4. TYPESCRIPT PATTERNS:
   - Typed request/response: Request<Params, ResBody, ReqBody, Query>
   - Extend Request interface for auth: declare module 'express' { interface Request { user?: User } }
   - Zod schemas for request validation (preferred over class-validator in Express)

5. ANTI-PATTERNS:
   - ❌ Not catching async errors (unhandled promise rejection)
   - ❌ Business logic in route handlers
   - ❌ Using `any` for request types
   - ❌ Missing error handling middleware
