---
name: node-code-explain
description: Node.js / NestJS / Express signals for code explanation: event loop, async semantics, DI, middleware chain, TypeScript runtime behavior.
metadata:
  category: backend
  tags: [explanation, code-understanding, node, nestjs, express, typescript]
user-invocable: false
---

# Node Code Explain (atomic)

> Load `Use skill: stack-detect` first to determine the project stack. This atomic is composed by `task-code-explain` when the detected stack is Node.js / TypeScript (NestJS primary, Express secondary).

## When to Use

- A workflow needs Node-specific signals: event loop behavior, NestJS module graph and DI, Express middleware order, error propagation across async, TypeScript-vs-runtime distinctions.
- Target uses `async`/`await`, Promises, NestJS decorators, Express middleware, or TypeScript types.

## Rules

- Distinguish what TypeScript types tell you from what runs at runtime - types are erased after compilation; only runtime behavior matters for "what does this do".
- Identify whether the code is on the event loop main thread or in a worker thread - blocking the loop stalls the entire process.
- For NestJS: identify the module the provider is in, and which modules import/export it - DI scope is module-level.
- For Express: list middleware in order before describing the route handler. Each middleware can short-circuit by sending a response.
- Surface error propagation across async: `throw` inside `async` becomes a rejected Promise; unhandled rejections crash the process in newer Node.

## Patterns

### Event Loop and Async

| Construct                     | Behavior                                                                              | What to flag                                                                                                                                       |
| ----------------------------- | ------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `async function`              | Returns a Promise; `await` suspends inside                                            | Forgetting `await` returns the unresolved Promise; common with mocks                                                                                |
| `Promise.all([...])`          | Concurrent; rejects on first failure                                                  | All work continues even after rejection (no cancellation in JS); use `Promise.allSettled` if all results needed                                    |
| `Promise.race([...])`         | Settles with the first to settle (resolve or reject)                                  | Other Promises continue running; use for timeouts but combine with `AbortController` for proper cancellation                                       |
| `setImmediate(fn)`            | Runs after current poll phase                                                         | Different from `setTimeout(fn, 0)` (which is at least 1ms)                                                                                          |
| `process.nextTick(fn)`        | Runs before any other I/O at end of current op                                        | Recursive nextTick can starve I/O                                                                                                                  |
| Sync I/O (`readFileSync`)     | Blocks the event loop                                                                 | Acceptable at startup; never in request path                                                                                                        |
| CPU-bound work in main thread | Blocks event loop                                                                     | Move to `worker_threads` or external service                                                                                                       |
| `worker_threads`              | Separate V8 instance; message-passing via `parent.postMessage`                        | No shared memory by default (use `SharedArrayBuffer`); each worker has its own event loop                                                          |

**Unhandled rejection:** in Node 15+, default behavior is to crash the process. `process.on('unhandledRejection', ...)` exists but is not a substitute for actually awaiting Promises.

### NestJS Module Graph and DI

- `@Module({ imports, controllers, providers, exports })`: providers are scoped to the module unless re-exported.
- Provider scope: `DEFAULT` (singleton, shared across the app), `REQUEST` (new instance per request, can inject `REQUEST`), `TRANSIENT` (new instance per consumer).
- Circular dependencies between modules: use `forwardRef(() => OtherModule)`.
- `@Global()` makes a module's exports globally available without re-import.
- `OnModuleInit` / `OnApplicationBootstrap` lifecycle hooks: run once at startup; `OnModuleDestroy` / `OnApplicationShutdown` on shutdown (only if `app.enableShutdownHooks()` is called).

### NestJS Request Pipeline

```
Middleware -> Guards -> Interceptors (before) -> Pipes -> Handler -> Interceptors (after) -> Filters (errors)
```

- **Middleware**: same as Express middleware; runs first.
- **Guards** (`@UseGuards`): authorization; throwing `ForbiddenException` short-circuits.
- **Interceptors** (`@UseInterceptors`): wrap the handler; can transform request/response, run before/after.
- **Pipes** (`@UsePipes`, `@Body() body: Dto`): validation and transformation. `class-validator` decorators on the DTO drive validation when `ValidationPipe` is enabled.
- **Filters** (`@UseFilters`): catch exceptions; convert to HTTP responses.

Order matters - guards run before pipes, so guards see un-validated input.

### Express Middleware

- Mounted via `app.use(fn)`, `router.use(fn)`, or per-route `app.get(path, mw, handler)`.
- Order is the order of `app.use` calls in `app.js` / `server.js`. Express does not have a declarative middleware list.
- Async middleware errors: `next(err)` propagates to error-handling middleware (4-arg signature `(err, req, res, next)`). In modern Express, throwing inside an async middleware is auto-caught.
- `req`, `res` are mutated by middleware (e.g., `req.user` set by auth middleware) - the chain shares state.

### Error Propagation Across Async

- `throw` inside `async`: the returned Promise rejects. Caller must `await` to observe.
- `try/catch` around an `await` catches the rejection.
- Errors in event handlers (`emitter.on('event', async () => { throw ... })`) are silent unless EventEmitter has its own error handling.
- `setTimeout(async () => { throw ... }, 0)`: the throw becomes an unhandled rejection in the next tick - process crash.
- `process.on('uncaughtException')` for sync throws; `process.on('unhandledRejection')` for Promise rejections; do not use these for normal control flow.

### TypeScript at Runtime

- Types are erased; `interface User { id: string }` does not exist at runtime. `instanceof` only works on classes.
- Type guards (`function isUser(x): x is User`) are runtime functions even though they help the type checker.
- Decorators (legacy or stage-3) DO emit runtime code if `experimentalDecorators` is on. NestJS depends on this.
- `as` casts are compile-time only - they do not validate the value.
- `unknown` vs `any`: `unknown` requires narrowing before use; `any` opts out of type checking entirely.

### TypeORM / Prisma / Sequelize / Mongoose

- **TypeORM:** entity relations with `@OneToMany` etc.; `eager: true` loads on every fetch; `lazy: true` returns Promises for relations. Repositories are obtained from the DataSource; transactions via `dataSource.transaction()` or `@Transaction()` decorator.
- **Prisma:** generated client; `prisma.user.findMany({ include: { posts: true } })`. Transactions via `prisma.$transaction([...])` (interactive) or array form (batch). No lazy loading - explicit `include` always.
- **Sequelize:** `findAll({ include: [...] })`; hooks (`beforeCreate`, etc.) similar to AR; transactions via `sequelize.transaction()`.
- **Mongoose:** schema-driven; middleware (`pre('save')`, etc.) and virtuals; `populate()` for refs (separate query, not join).

### Module System (CommonJS vs ESM)

- `package.json` `"type": "module"` -> ESM (`import`/`export`); otherwise CommonJS (`require`/`module.exports`).
- ESM is async by default; top-level `await` is allowed.
- Mixing CJS and ESM: ESM can `import` CJS but uses default import for the entire module.exports; CJS cannot `require` ESM synchronously.
- `__dirname` and `__filename` do not exist in ESM; use `import.meta.url` + `fileURLToPath`.

### Streams and Backpressure

- Readable streams have `data` events; writable streams have `drain` events for backpressure.
- `pipe()` handles backpressure automatically; manually piping with `for await (const chunk of readable)` writing to writable does not.
- Failing to consume a readable stream leaves it paused; common cause of "request hangs".

### Logging and Tracing

- `pino` and `winston` are common structured loggers. Avoid `console.log` in production paths.
- `AsyncLocalStorage` (Node 12.17+) propagates context across `await` (similar to thread-local in Java); used for request IDs and trace IDs.
- OpenTelemetry SDK auto-instruments most popular libs; manual spans via `tracer.startSpan`.

## Output Format

This atomic produces signals consumed by `task-code-explain`. Inject the following:

**Into "Flow Context":**

- Whether `def` is `async`; if NestJS, full pipeline (Middleware -> Guards -> Interceptors -> Pipes -> Handler -> Filters)
- For Express: middleware order leading to the route
- DI scope for NestJS providers (singleton / request / transient)
- ORM transaction boundary

**Into "Non-Obvious Behavior":**

- Missing `await` returning unresolved Promises
- `Promise.all` continuing other work after rejection
- Sync I/O on the event loop
- Unhandled rejection crashing the process
- TypeScript types being erased - `instanceof` only on classes
- ESM/CJS boundary issues (`__dirname`, top-level await, default import shape)
- ORM-specific lazy/eager loading

**Into "Key Invariants":**

- Promises must be awaited or handled or they become unhandled rejections
- NestJS provider scope determines lifetime; mismatched scope chains cause runtime DI errors
- Express middleware order is the order of `app.use` calls
- `AsyncLocalStorage` carries context only across `await`, not across `setTimeout` without explicit binding

**Into "Change Impact Preview":**

- Switching a function to `async`: every caller must now `await`; sync callers see Promise objects instead of values
- Adding a NestJS guard: applies to every handler in the controller; can short-circuit before pipes validate input
- Changing a TypeORM relation from `eager: false` to `true`: every query loads the relation - perf cliff
- Adding a Sequelize hook: fires on every `save`/`create` anywhere in the codebase
- Switching from CJS to ESM: `__dirname` breaks; sync `require` of ESM modules fails

## Avoid

- Treating TypeScript types as runtime guarantees - they are erased
- Recommending `Promise.race` for timeouts without `AbortController` - the work continues
- Saying "NestJS is just Express" - the request pipeline is structured and order is rigid
- Confusing `process.nextTick` and `setImmediate` and `setTimeout(0)` - all three behave differently
- Describing Sequelize/TypeORM/Prisma uniformly - they have very different transaction and lazy-load semantics
- Recommending `console.log` in handlers - production needs structured logging
