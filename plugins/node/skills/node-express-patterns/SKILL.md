---
name: node-express-patterns
description: Express + TypeScript patterns: router structure, middleware ordering, async error handling, Zod validation, webhooks, graceful shutdown.
metadata:
  category: backend
  tags: [node, typescript, express, middleware, validation, patterns]
user-invocable: false
---

# Express Patterns

> Load `Use skill: stack-detect` first. It does not carry the Express major - read `dependencies.express` in `package.json`; that major decides the async-error and routing rules below and surfaces only in the block's `Express major version:` line.

## When to Use

- Building or extending Express + TypeScript applications
- Setting up middleware, validation, error handling, or webhooks
- Reviewing Express code for structural issues, or planning the Express 4 -> 5 upgrade

## Rules

- Middleware order: helmet -> cors -> request logger (`pino-http`) -> webhook routes (raw body) -> `express.json()` -> rate limiter -> auth at the router mount -> validation -> handler -> 404 fallback (`app.use((_req, res) => res.status(404).json({ error: "not_found" }))`, after every router) -> errorHandler (last)
- Express 4: wrap every async handler/middleware to forward rejections to `next`. Express 5 forwards them natively - there the wrapper is dead code, so strip `asyncHandler` from every example below
- Error middleware takes exactly 4 parameters (Express detects by arity), is registered after every router, and checks `res.headersSent` before writing - a failure mid-stream otherwise throws `ERR_HTTP_HEADERS_SENT`
- Never expose raw error details (message of an unknown error, stack) to clients in production
- No business logic in route handlers - delegate to services. A handler sends exactly one response: `return` after every `res.*` in a branch
- Two independent webhook rules: raw-body routes mount **before** `express.json()`, and signature-authenticated routes mount outside the JWT middleware's scope. Either applies alone - a bodyless signed-link GET needs the auth bypass without the raw parser
- Bind auth at the router mount (`app.use('/api/v1/orders', requireAuth, ordersRouter)`), never `app.use(requireAuth)` globally - global auth puts webhooks and health probes behind JWT
- Behind a proxy or ingress, set `trust proxy` to the exact number of proxy hops in front of the app (`1` for a single ALB or ingress), never `true` - unset, every client shares the proxy's IP and the limiter blocks everyone at once; `true` lets a client spoof `X-Forwarded-For` past it. express-rate-limit 7 and 8 report both at runtime (`ERR_ERL_UNEXPECTED_X_FORWARDED_FOR`, `ERR_ERL_PERMISSIVE_TRUST_PROXY`)

## Patterns

### Router Organization

One router per resource (`orders.router.ts`), controllers separate from routing, mounted with its auth at the mount point.

```typescript
const router = Router();
router.get("/:id", asyncHandler(orderController.getById));          // Express 4; drop asyncHandler on 5
router.post("/", validate(createOrderSchema), asyncHandler(orderController.create));
export default router;

// app.ts
app.use("/api/v1/orders", requireAuth, ordersRouter);
```

### Async Handler

Express 5 forwards rejected promises to error middleware natively. Express 4 does not: an unwrapped rejection becomes an unhandled rejection - the request hangs and, with no `unhandledRejection` listener, Node 15+ crashes the process.

```typescript
// Express 4 only
const asyncHandler =
  (fn: RequestHandler): RequestHandler =>
  (req, res, next) =>
    Promise.resolve(fn(req, res, next)).catch(next);
```

A synchronous `throw` is forwarded on both majors; only async code needs the wrapper on 4.

### Validation with Zod

```typescript
const createOrderSchema = z.object({
  body: z.object({
    customerId: z.uuid(),                     // Zod 4, RFC 9562 strict; z.guid() accepts any 8-4-4-4-12 hex, as Zod 3's z.string().uuid() did
    items: z.array(z.object({ productId: z.uuid(), quantity: z.number().int().positive() })).min(1),
  }),
  query: z.object({ limit: z.coerce.number().int().min(1).max(100).default(20) }),
  headers: z.object({ "x-tenant-id": z.uuid() }),
});

const validate = (schema: z.ZodType): RequestHandler => (req, _res, next) => {
  const r = schema.safeParse({ body: req.body, query: req.query, params: req.params, headers: req.headers });
  if (!r.success) {
    return next(new ValidationError(r.error.issues.map((i) => `${i.path.join(".")}: ${i.message}`).join(", ")));
  }
  req.valid = r.data;   // keep the parsed output - coercions and defaults exist only here
  next();
};
```

Parse `headers` and `query` in the same schema, and read `req.valid`, never `req.query`: coerced numbers and defaults live only on the parse result, and on Express 5 `req.query` is a getter that cannot be reassigned. Declare `req.valid` via the global-namespace augmentation used for `req.user`, and read it through a typed accessor so the parsed output stays checked: `const input = <S extends z.ZodType>(req: Request, _schema: S) => req.valid as z.infer<S>`.

### Error Handling

The `AppError` hierarchy (`ValidationError`, `NotFoundError`, ..., each `new X(message, cause?)`), its status mapping, ORM translation, and Sentry capture are owned by `node-exception-handling`; this skill wires its terminal middleware (`req.log` comes from `pino-http`).

```typescript
const errorHandler: ErrorRequestHandler = (err, req, res, next) => {
  if (res.headersSent) return next(err);       // mid-stream: Express's default handler destroys the socket
  if (err instanceof AppError) return void res.status(err.status).json({ error: err.code, message: err.message });
  // body-parser errors carry their own 4xx: malformed JSON 400, too large 413, bad charset 415
  if (typeof err.status === "number" && err.status < 500 && err.expose) {
    return void res.status(err.status).json({ error: err.type ?? "bad_request" });
  }
  req.log.error({ err }, "unhandled");
  res.status(500).json({ error: "internal" });  // no err.message, no stack
};
```

Register `process.on('unhandledRejection')` as a backstop that logs and then exits (or starts graceful shutdown) - a listener that only logs swallows Node's default crash and leaves the process running in an unknown state.

### Webhook Endpoints

External webhooks (Stripe, GitHub) need the raw body for signature validation, and are signature-authenticated, not JWT. Mount them before `express.json()` and outside the auth mount:

```typescript
app.post(
  "/api/v1/webhooks/stripe",
  express.raw({ type: "application/json" }),
  asyncHandler(async (req, res) => {
    let event: Stripe.Event;
    try {
      const sig = req.headers["stripe-signature"];
      if (typeof sig !== "string") return void res.status(400).send("missing signature");
      event = stripe.webhooks.constructEvent(req.body, sig, STRIPE_WEBHOOK_SECRET);
    } catch {
      return void res.status(400).send("invalid signature");   // not from Stripe; a real secret mismatch shows as failing deliveries
    }
    await paymentService.handleWebhookEvent(event);
    res.json({ received: true });
  }),
);

app.use(express.json());
app.use("/api/v1/orders", requireAuth, ordersRouter);
```

Signature schemes per provider (Stripe `t.payload`, Slack `v0:t:body`, Plaid's signed JWT, Twilio's URL + sorted params) and signed download links are `node-security-patterns`.

### TypeScript

- Typed handlers: `Request<Params, ResBody>` for params and the response; body and query are typed through `req.valid` (above)
- Extend `Request` via the global namespace. Augmenting `'express'` itself compiles but reaches only a `req` annotated as `express.Request`; the `core.Request` that inferred handler params use never sees it (TS2339 on `req.user`). The file holding `declare global` must be a module (an `import` or `export {}`):

```typescript
import type { User } from "./user";
declare global {
  namespace Express {
    interface Request { user?: User; valid?: unknown }
  }
}
```

### Security

- `helmet()` first
- `cors({ origin: allowedOrigins })` - never bare `cors()` in production. Add `credentials: true` only for cookie or HTTP-auth sessions (the client sends `credentials: 'include'`); it is incompatible with `origin: '*'`. A bearer token in `Authorization` needs the header allowed, not credentials
- `express-rate-limit` on auth endpoints (see the `trust proxy` rule)

### Health and Shutdown

Liveness never touches dependencies. Readiness reports whether **this** instance can serve (pool initialised, warm-up done) - checking a shared dependency there marks every replica unready at once and turns a DB blip into a full outage. The drain delay exists because the orchestrator removes the instance from the load balancer asynchronously: Kubernetes drops a terminating pod from its endpoints as it starts terminating, and ECS deregisters the target and waits out the ALB deregistration delay **before** it sends `SIGTERM`. Failing readiness is defence in depth, not what triggers the drain.

```typescript
let ready = true;
app.get("/health", (_req, res) => res.json({ status: "ok" }));          // liveness - no I/O
app.get("/ready", (_req, res) => {                                       // readiness - local state only
  if (!ready || !dataSource.isInitialized) return void res.status(503).json({ status: "not-ready" });
  res.json({ status: "ready" });
});

const server = app.listen(port);
process.on("SIGTERM", async () => {
  ready = false;
  await new Promise((r) => setTimeout(r, 5_000));   // k8s: endpoint removal propagates; ECS: already deregistered
  const hard = setTimeout(() => { server.closeAllConnections(); process.exit(1); }, 20_000).unref();
  const workersClosed = Promise.allSettled(workers.map((w) => w.close()));   // BullMQ workers hosted here: stop fetching now, in-flight jobs finish; settled, so an early failure is no unhandled rejection
  server.close(async () => {
    await workersClosed;                                               // the longest job must fit inside the hard timer
    await Promise.all([...queues.map((q) => q.close()), dataSource.destroy()]);
    await redis.quit();                                                // the shared ioredis connection, after every queue
    clearTimeout(hard);
    process.exit(0);
  });
});
```

`server.close()` stops accepting and (Node 19+) closes idle keep-alive sockets; a busy keep-alive connection is bounded only by the hard timer. On ECS, point the ALB target group's health check at `/ready` (the container `healthCheck` restarts the task, so it points at `/health`). The grace period - Kubernetes `terminationGracePeriodSeconds` (default 30s) or ECS `stopTimeout` (Fargate: default 30s, max 120s; EC2: the agent's `ECS_CONTAINER_STOP_TIMEOUT`, default 30s) - must exceed the drain delay plus the hard timer (5 + 20 = 25 < 30), the longest in-flight job must fit inside the hard timer, and a `preStop` hook counts against the same budget.

### Express 4 -> 5 Upgrade

| Area | Express 5 behaviour | Codebase change | Guard test |
|------|---------------------|-----------------|------------|
| Async errors | rejected promises reach error middleware | delete `asyncHandler` / `express-async-errors` | a rejecting handler answers the error handler's status |
| Third-party middleware | packages whose peer range pins `express@4` fail `npm install` (ERESOLVE) or at load | `npm ls express` before the switch; replace or upgrade each | install on a clean tree |
| Route paths (path-to-regexp 8) | `*` must be named: `/*splat` (one or more segments) or `/{*splat}` (also the root); optional segments use braces (`/:file{.:ext}`); `:name?` and inline regex are gone | rewrite wildcard / optional routes | one request per rewritten route |
| `req.query` | read-only getter; default query parser is `simple` | stop assigning to it; read `req.valid` | a nested query key (`a[b]=1`) parses as the app expects |
| `req.body` | `undefined` (not `{}`) unless a parser parsed a body - no parser, no body, or a non-matching Content-Type | guard `req.body` before reading keys | a bodyless POST to a JSON route answers 400, not 500 |
| Removed APIs | `app.del`, `req.param()`, `res.sendfile`, `res.redirect(url, status)` (throws) | `app.delete`, `req.params` / `req.body` / `req.query` (here `req.valid`), `res.sendFile`, `res.redirect(status, url)` | grep finds none |
| `res.send(<number>)`, `res.json(obj, status)` | not removed: `res.send(n)` sends 200 with the number as the body, `res.json(obj, status)` ignores the status and sends 200 - nothing throws | grep for both; `res.sendStatus(n)`, `res.status(s).json(obj)` | the status asserted by the route's test |
| `app.listen` callback | receives an error argument when listening fails | handle it (log and exit) instead of a bare callback | a busy port exits non-zero |
| `res.status()` | integer 100-999 only | no string or out-of-range codes | grep finds none |
| `express.urlencoded` | `extended` defaults to `false` | set it explicitly | a form POST with a nested field parses |
| Runtime | Node 18+ | check `engines` | CI on the pinned Node |

Upgrade `@types/express` to 5 in the same change; middleware packages (helmet, cors, express-rate-limit) are major-agnostic.

## Output Format

When authoring, emit this block plus the wiring code it describes; a build over existing code is authoring plus review - findings for the existing defects the change touches, then the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings. After the findings, emit this block as the target state: every line and row shows the corrected value, and one the current code violates ends ` - GAP (was: <observed>)`; one whose evidence was not in the read set reads `unknown - <file> not read`, and an entry the code lacks (a router, an error mapping) is a row with the target value and ` - GAP (was: absent)`. Health and readiness routes mount before auth and get no Middleware Stack row. An upgrade plan is a review: findings, then the Upgrade table rows that apply (one per change) ordered as the steps to take, the Guard test column naming the test that guards each change before the switch, then the block with the version line `4 -> 5`. Defects another skill owns (authorization, mass assignment, open redirect, signature schemes: `node-security-patterns`) go on one closing `Out of scope:` line as `<file:line> <defect>`, separated by `; `.

```
## Express Architecture

Express major version: {4 | 5 | 4 -> 5}

trust proxy: {<hop count> (<the proxies in front>) | false (no proxy)}

### Middleware Stack
| Order | Middleware | Scope (app / router mount / route) | Purpose |
|-------|-----------|------------------------------------|---------|
| 1 | helmet | app | security headers |
| 2 | cors | app | origin: {allowlist}; credentials: {true \| false} |
| 3 | request logger (pino-http) | app | req.log for every later middleware and the errorHandler |
| 4 | webhook routes | app, before express.json | raw body and/or signature auth, outside JWT |
| 5 | express.json() | app | JSON body parsing |
| 6 | rate limiter | route (auth endpoints) | abuse control |
| 7 | auth | router mount | JWT validation |
| 8 | validation | route | Zod schema -> req.valid |
| 9 | routes | router | API handlers{, async-wrapped on 4} |
| 10 | 404 fallback | app, after every router | unknown route -> 404 |
| 11 | errorHandler | app, last | centralized error handling |

### Router Structure
| Router | Mount Path | Endpoints | Auth |
|--------|-----------|-----------|------|

### Validation Schemas
| Endpoint | body / query / params / headers | Failure status |
|----------|---------------------------------|----------------|

### Error Mapping
| Domain error | Status |
|--------------|--------|

Error handler: headersSent guard yes; body-parser 4xx passed through yes

unhandledRejection: {log + exit | log + graceful shutdown}

### Shutdown
Liveness: {path} - Readiness: {path, what it checks}

Drain: {readiness flip, drain delay, hard-stop timer, resources released}

Grace period: {terminationGracePeriodSeconds | stopTimeout | ECS_CONTAINER_STOP_TIMEOUT} = {n}s vs budget {preStop + drain delay + hard timer}s
```

## Avoid

- `any` for request types
- `cors()` with no origin in production
- `express-async-errors` - patches Express 4's router and fails to load on Express 5
