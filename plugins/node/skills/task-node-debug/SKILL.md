---
name: task-node-debug
description: Debug Node.js / TypeScript errors: NestJS / Express, Prisma / TypeORM, tsc compile errors, Jest failures, BullMQ job failures.
agent: node-architect
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

> **Behavioral directive:** Load `Use skill: behavioral-principles` before executing this workflow. These rules govern every step that follows.

# Debug Node.js/TypeScript Error

## When to Use

- Stack traces, runtime errors, build failures, or test failures in NestJS / Express
- TypeScript compile errors, Prisma / TypeORM query errors, DI resolution failures
- BullMQ job failures, unhandled rejections, middleware ordering issues

Not for new features (use `task-node-implement`) or production incident triage (use `/task-oncall-start`).

## Workflow

### STEP 1 - INTAKE

Ask for: full stack trace, source file at the first application frame (skip `node_modules`), and expected behavior. For vague reports ("doesn't work"), ask which endpoint/command, expected vs actual, reproducibility, frequency.

**Common intake gaps:**

- **No trace, just behavior**: ask for exact error/output, triggering endpoint, recent changes.
- **Multiple errors**: the first is usually root; later ones cascade.
- **Intermittent**: suspect missing `await`, pool exhaustion, race conditions, transaction timeouts. Correlate with load.
- **Production-only**: diff env (pool size, timeouts, `NODE_ENV`), missing handlers, event loop blocking.
- **Third-party frame**: find the application frame that called in; inspect inputs passed.

**"No error, just wrong behavior"** (e.g., "field I sent is null in DB"): reframe as boundary loss. Trace the path and identify which boundary dropped the value before reading code:

`req.body` -> ValidationPipe (`whitelist: true` silently strips) / Zod `.strict()` -> DTO field declared? -> `class-transformer` `@Transform`/`@Type` mutation -> service whitelist (`data: { onlyTheseFields }` vs `data: dto`) -> Prisma `@map`/`@@map` or TypeORM `@Column({ name })` mismatch -> DB column.

Same shape for BullMQ: dispatch -> `afterCommit` -> Redis JSON serialization (class instances lose methods) -> processor `handle()` -> side effect.

### STEP 2 - CLASSIFY

Match the error, then load the listed atomic skill:

| Category | Signal | Likely cause | Skill |
|---|---|---|---|
| NestJS DI | `Nest can't resolve dependencies of X` | Missing `@Injectable()`, provider not in `providers[]`, circular dep | `node-nestjs-patterns` |
| NestJS DI | `Circular dependency detected` | Use `forwardRef()` as workaround; prefer extracting shared logic | `node-nestjs-patterns` |
| NestJS DI | `Cannot read properties of undefined (reading 'method')` in service | Provider not injected; missing `@Injectable()` or module import | `node-nestjs-patterns` |
| Prisma | `P2002` | Unique constraint violation; consider upsert or 409 | `node-prisma-patterns` |
| Prisma | `P2025` | Record not found; `findUniqueOrThrow` vs `findUnique` | `node-prisma-patterns` |
| Prisma | `P2003` | FK constraint; referenced record missing | `node-prisma-patterns` |
| Prisma | Interactive tx timeout | Default 5s; set `timeout` in `$transaction` options | `node-prisma-patterns` |
| TypeORM | `QueryFailedError` | Migration drift, column types | `node-typeorm-patterns` |
| TypeORM | `EntityNotFoundError` | `findOneOrFail` with no match | `node-typeorm-patterns` |
| TypeORM | QueryRunner leak | Missing `release()` in `finally` | `node-typeorm-patterns` |
| TS compile | `TS2322` / `TS2345` | Type mismatch (assignment / argument) | `node-typescript-patterns` |
| TS compile | `Cannot find module` | Wrong import path or missing install (`bun install`) | `node-typescript-patterns` |
| TS compile | `TS2339` | Property not on type; check narrowing | `node-typescript-patterns` |
| Runtime | `TypeError: Cannot read properties of undefined` | Null access; trace origin, optional chaining, async loading | - |
| Runtime | `ERR_UNHANDLED_REJECTION` | Missing `await` / `.catch()`; Express needs async wrapper | `node-express-patterns` |
| NestJS | `UnauthorizedException` | Token missing/expired, guard misconfigured | `node-nestjs-patterns` |
| NestJS | `BadRequestException` | DTO validation; check `class-validator` decorators | `node-nestjs-patterns` |
| BullMQ | Job stuck failed | Retry/backoff config, inspect `failedReason` | `node-bullmq-patterns` |
| BullMQ | Worker idle | Redis connectivity (`maxRetriesPerRequest: null`), processor not registered | `node-bullmq-patterns` |
| BullMQ | Job data missing | Passed entity instead of ID; JSON serialization drops methods | `node-bullmq-patterns` |
| BullMQ | Duplicate recurring jobs | Missing `jobId` on repeatable jobs | `node-bullmq-patterns` |
| Express | Error handler not firing | Error middleware needs 4 params (arity detection) | `node-express-patterns` |
| Express | Middleware order | `helmet` -> `cors` -> auth -> validation -> handler -> error handler | `node-express-patterns` |
| ESM | `ERR_REQUIRE_ESM` | CJS `require()` of an ESM-only package; switch to dynamic `import()` or move the importer to ESM | `node-typescript-patterns` |
| ESM | `ERR_MODULE_NOT_FOUND` | ESM relative import missing `.js` extension after TS compile; add the extension or set bundler resolver | `node-typescript-patterns` |
| ESM | `__dirname is not defined` | ESM has no `__dirname`/`__filename`; use `fileURLToPath(import.meta.url)` | `node-typescript-patterns` |
| ESM | Dual-package hazard | CJS + ESM build of the same package loaded twice; `instanceof` / singletons break - pin to one variant in `package.json` `exports` | `node-typescript-patterns` |

### STEP 3 - LOCATE

Read trace top-to-bottom, open the first application frame, and follow the data: DI chain for DI errors, query model/operation for Prisma, enqueue + processor for BullMQ.

### STEP 4 - ROOT CAUSE

Explain **why**, not just what. State confidence: **HIGH** (reproduced or obvious), **MEDIUM** (pattern match), **LOW** (multiple candidates).

```
ROOT CAUSE: [HIGH] P2002 at orders.service.ts:45 - createOrder inserts a
customer with an email that already exists; no pre-check, so the second
order from the same customer hits the unique index.
```

### STEP 5 - FIX

Provide before/after code. Minimal, addresses root cause not symptom.

### STEP 6 - PREVENTION

Add one guard so this class cannot recur:

- Test exercising the exact path (incl. error condition)
- Stricter TS type making the bug impossible at compile time
- Lint rule or `class-validator` decorator catching invalid input earlier
- BullMQ: idempotency check + retry config asserted in test
- Prisma unique constraint: upsert or explicit conflict handling

## Output Format

```markdown
## Error Classification

[Category]: [specific error type]

## Root Cause (confidence: HIGH/MEDIUM/LOW)

[Why the error occurs, referencing specific file:line]

## Fix

**Before:**
{code}

**After:**
{code}

## Prevention

[Test, TypeScript type constraint, or lint rule to prevent recurrence]
```

## Self-Check

- [ ] STEP 1: intake complete; trace, source file, expected behavior captured
- [ ] STEP 2: error classified against the table before reading code
- [ ] STEP 3: located in the first application frame, not a `node_modules` frame
- [ ] STEP 4: root cause references file:line; confidence stated
- [ ] STEP 5: minimal before/after fix; addresses root cause
- [ ] STEP 6: prevention guard added (test, type, lint, or idempotency)

## Avoid

- Proposing a fix before classifying (symptom-level fixes)
- `try/catch`, `@ts-ignore`, `as any`, or scattered null checks as band-aids
- `forwardRef()` for circular deps without considering service extraction
- `synchronize: true` or `prisma db push` to "fix" migration drift
- Swallowing BullMQ errors so jobs silently succeed instead of failing/retrying
