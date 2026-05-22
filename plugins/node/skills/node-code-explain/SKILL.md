---
name: node-code-explain
description: Node.js / NestJS / Express signals for code explanation: event loop, async semantics, DI, middleware chain, TypeScript runtime behavior.
metadata:
  category: backend
  tags: [explanation, code-understanding, node, nestjs, express, typescript]
user-invocable: false
---

# Node Code Explain (atomic)

> Load `Use skill: stack-detect` first. Composed by `task-code-explain` for Node.js / TypeScript.

## When to Use

Workflow needs Node-specific signals: event loop, NestJS DI/module graph, Express middleware order, error propagation across async, TypeScript-vs-runtime.

## Rules

- TS types are erased; only runtime behavior matters for "what does this do". `instanceof` works on classes only.
- Identify event-loop main thread vs worker thread - blocking the loop stalls the process.
- NestJS: identify provider scope and the module it lives in - DI is module-level.
- Express: list middleware in order before the handler; each can short-circuit.
- Unawaited Promises become unhandled rejections - crash in Node 15+.

## Patterns

### Event Loop and Async

| Construct                | Behavior                                          | Flag                                              |
| ------------------------ | ------------------------------------------------- | ------------------------------------------------- |
| `async function`         | Returns Promise; `await` suspends                 | Missing `await` returns unresolved Promise        |
| `Promise.all`            | Concurrent; rejects on first failure              | Other work continues; use `allSettled` if needed  |
| `Promise.race`           | Settles with first to settle                      | Losers keep running; pair with `AbortController`  |
| `setImmediate` / `nextTick` / `setTimeout(0)` | Distinct queues       | Recursive `nextTick` starves I/O                  |
| Sync I/O (`readFileSync`)| Blocks event loop                                 | OK at startup; never in request path              |
| CPU-bound work           | Blocks event loop                                 | Move to `worker_threads` or external service      |

### NestJS Request Pipeline

`Middleware -> Guards -> Interceptors(before) -> Pipes -> Handler -> Interceptors(after) -> Filters`

- Guards run before pipes - they see un-validated input.
- Pipes (`ValidationPipe`) drive `class-validator` on the DTO.
- Filters convert exceptions to HTTP responses.

### NestJS DI Scopes

| Scope     | Lifetime                          | Caveat                                                      |
| --------- | --------------------------------- | ----------------------------------------------------------- |
| DEFAULT   | Singleton                         | -                                                           |
| REQUEST   | One instance per request          | Propagates upward - singletons that inject it become REQUEST |
| TRANSIENT | One instance per injection point  | New instance every consumer                                 |

Circular deps: `forwardRef(() => Other)`. `@Global()` exports without re-import. Lifecycle: `OnModuleInit` runs once; `OnApplicationShutdown` needs `app.enableShutdownHooks()`.

### Express Middleware

- Order is the order of `app.use` / `router.use` calls.
- Async middleware: `next(err)` propagates; modern Express auto-catches throws inside async.
- `req` / `res` are mutated through the chain (e.g., `req.user` from auth).
- Error middleware needs exactly 4 args; Express uses arity detection.

### Error Propagation

- `throw` in `async` -> rejected Promise; caller must `await` to observe.
- Errors in `emitter.on('event', async () => ...)` are silent unless wired.
- `setTimeout(async () => { throw })` becomes unhandled rejection - process crash.
- `process.on('unhandledRejection')` and `'uncaughtException'` are for logging, not control flow.

### TypeScript at Runtime

- Types erased: `interface User` does not exist at runtime; `instanceof` only on classes.
- Type guards (`x is User`) are runtime functions.
- Decorators emit runtime code (`experimentalDecorators`) - NestJS depends on this.
- `as` is compile-time only - does not validate.
- `unknown` requires narrowing; `any` opts out entirely.

### ORM Semantics

- **Prisma**: explicit `include`/`select`; no lazy loading. `$transaction(fn)` interactive, `$transaction([...])` batch.
- **TypeORM**: `eager: true` loads always; `lazy: true` returns Promises. `dataSource.transaction(fn)` or `QueryRunner`.
- **Sequelize**: `findAll({ include })`; hooks (`beforeCreate`).
- **Mongoose**: `populate()` is a separate query, not a join.

### Module System

`"type": "module"` -> ESM (`import`/`export`, top-level `await`); else CJS (`require`). ESM can `import` CJS via default; CJS cannot `require` ESM synchronously. ESM has no `__dirname` - use `import.meta.url`.

### Streams

`pipe()` handles backpressure; manual loops don't. Unconsumed Readable stays paused - common "request hangs" cause.

### Logging / Tracing

`pino` / `winston` for structured logs; avoid `console.log` in prod. `AsyncLocalStorage` propagates context across `await` (request IDs). OpenTelemetry auto-instruments most libs.

## Output Format

Inject into `task-code-explain`:

- **Flow Context**: async or not; NestJS full pipeline or Express middleware order; DI scope; ORM transaction boundary.
- **Non-Obvious Behavior**: missing `await`, `Promise.all` losers continuing, sync I/O on loop, unhandled rejection, TS type erasure, ESM/CJS boundary, ORM lazy/eager.
- **Key Invariants**: Promises must be awaited; NestJS scope propagation; Express middleware order; `AsyncLocalStorage` across `await` only.
- **Change Impact**: making a function `async` ripples to every caller; new guard applies to every handler in the controller; TypeORM `eager: true` toggles a perf cliff; Sequelize hook fires on every save.

## Avoid

- Treating TS types as runtime guarantees
- `Promise.race` for timeouts without `AbortController`
- Conflating NestJS pipeline with Express middleware
- Confusing `nextTick` / `setImmediate` / `setTimeout(0)`
- Uniform ORM descriptions (transaction and lazy-load semantics differ sharply)
