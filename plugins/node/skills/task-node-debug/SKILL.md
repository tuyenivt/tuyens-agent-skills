---
name: task-node-debug
description: Debug Node.js/TypeScript application errors - NestJS and Express errors, Prisma and TypeORM issues, TypeScript compilation errors, Jest test failures, and BullMQ job failures. Paste a stack trace or describe the unexpected behavior.
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

- Debugging stack traces, runtime errors, build failures, or test failures in NestJS or Express applications
- Diagnosing TypeScript compilation errors, Prisma/TypeORM query errors, or DI resolution failures
- Investigating BullMQ job failures, unhandled rejections, or middleware ordering issues

Not for adding new features (use `task-node-new`) or production incident triage with blast radius assessment (use `task-incident-root-cause`).

## Edge Cases

- **No stack trace provided**: User describes behavior ("it crashes sometimes") without a trace. Ask for: (1) the exact error message or unexpected output, (2) which endpoint or command triggers it, (3) recent code changes. If they can reproduce, ask them to capture the full stack trace
- **Multiple errors in output**: Identify the root error (usually the first one) - later errors are often cascading failures from the same root cause
- **Intermittent errors**: If the error happens only on some requests, suspect: missing `await` on async operations, connection pool exhaustion, race conditions, or Prisma transaction timeouts under load. Ask about request volume and whether it correlates with load
- **Production-only errors**: Error doesn't reproduce locally. Check for: environment differences (connection pool size, timeouts, NODE_ENV), missing error handlers, or load-dependent issues (pool exhaustion, event loop blocking)
- **Third-party library error**: Stack trace originates in a dependency, not application code. Identify the application frame that called into the library and check the inputs passed

## Workflow

### STEP 1 - INTAKE

Ask for: full stack trace or error output, the source file where the error originates, and what the user expected to happen. If a stack trace is provided, identify the first application-code frame (skip node_modules frames) and read that file.

If the user provides only a partial error message or vague description ("it doesn't work"), ask clarifying questions: which command/endpoint was run, what the expected vs actual behavior is, whether the error is reproducible, and how frequently it occurs.

### STEP 2 - CLASSIFY

Match the error to one of these categories, then load the relevant atomic skill:

**NestJS DI / Module Errors**

- `Nest can't resolve dependencies of X` -> Missing `@Injectable()`, provider not in module `providers[]`, or circular dependency. Use skill: `node-nestjs-patterns`.
- `Circular dependency detected` -> Use `forwardRef()` as workaround, but prefer extracting shared logic to a third service.
- `Cannot read properties of undefined (reading 'method')` in a service -> provider not injected, missing `@Injectable()` or module import.

**Prisma Errors** (Use skill: `node-prisma-patterns`)

- `PrismaClientKnownRequestError (P2002)` -> Unique constraint violation. Duplicate value on unique field. Check which field's unique constraint is being violated and whether the caller should handle conflicts (upsert or 409).
- `PrismaClientKnownRequestError (P2025)` -> Record not found. ID does not exist or was deleted. Check if the query uses `findUniqueOrThrow` vs `findUnique`.
- `PrismaClientKnownRequestError (P2003)` -> Foreign key constraint failed. Referenced record doesn't exist.
- Interactive transaction timeout -> Default is 5 seconds. For long-running transactions, set `timeout` in `$transaction` options.

**TypeORM Errors** (Use skill: `node-typeorm-patterns`)

- `QueryFailedError` -> Check migration state, column types, and whether migrations are current.
- `EntityNotFoundError` -> Record not found with `findOneOrFail`.
- QueryRunner connection leak -> Missing `release()` in `finally` block.

**TypeScript Compilation Errors**

- `TS2322` / `TS2345` -> Type mismatch in assignment or argument. Use skill: `node-typescript-patterns`.
- `Cannot find module` -> Wrong import path or missing install; run `bun install`.
- `TS2339` -> Property does not exist on type. Check type definition and narrowing.

**Runtime / Async Errors**

- `TypeError: Cannot read properties of undefined` -> Null access. Trace variable origin, check optional chaining, verify async data loading.
- `ERR_UNHANDLED_REJECTION` -> Missing `await` or `.catch()` on async call. Use skill: `node-express-patterns` (Express) for async handler wrapper.
- `UnauthorizedException` (NestJS) -> Token missing/expired, guard misconfigured.
- `BadRequestException` (NestJS) -> DTO validation failed, check `class-validator` decorators.

**BullMQ Job Errors** (Use skill: `node-bullmq-patterns`)

- Job stuck in failed state -> Check retry/backoff config, examine `failedReason` on the job.
- Worker not processing -> Redis connectivity (`ioredis` with `maxRetriesPerRequest: null`), worker not registered, missing processor.
- Job data missing or undefined -> Passing entity instead of ID, check job data shape. BullMQ serializes via JSON - class instances lose methods.
- Duplicate recurring jobs on restart -> Missing `jobId` on repeatable jobs.

**Express-specific Errors** (Use skill: `node-express-patterns`)

- Error handler not catching errors -> Error middleware has fewer than 4 parameters (Express uses arity detection).
- Middleware ordering issues -> `helmet` -> `cors` -> auth -> validation -> handler -> error handler.

### STEP 3 - LOCATE

1. Read the stack trace top-to-bottom; find the first application-code frame (skip `node_modules`)
2. Open that source file and read the failing function
3. Trace the data path: where does the problematic value originate? Follow it through DI injection, async call chains, or middleware pipeline
4. For Prisma errors: check the query that triggered the error - which model and operation?
5. For DI errors: trace the dependency chain from the failing provider through module imports
6. For BullMQ: check both the enqueue site and the worker processor

### STEP 4 - ROOT CAUSE

Explain **why** the error occurs, not just what it is. State confidence: **HIGH** (reproduced or obvious from code), **MEDIUM** (likely based on pattern match), **LOW** (multiple possible causes).

```
ROOT CAUSE: [HIGH/MEDIUM/LOW confidence]
The P2002 unique constraint error occurs because OrdersService.createOrder at
orders.service.ts:45 creates a customer record with an email that already exists.
The service does not check for existing customers before creating - when the same
customer places a second order, Prisma attempts to INSERT a duplicate email value.
```

### STEP 5 - FIX

Provide before/after code. Fix must be minimal and address root cause, not symptoms.

### STEP 6 - PREVENTION

Add a guard so this class of error cannot recur:

- **Test** that exercises the exact code path (including the error condition)
- **Stricter TypeScript type** that makes the bug impossible at compile time
- **Lint rule** or `class-validator` decorator that catches invalid input earlier
- For BullMQ issues: add idempotency check and verify retry config in a test
- For Prisma unique constraint: consider upsert pattern or explicit conflict handling

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

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Framework constraints respected (NestJS DI, decorator patterns, Express middleware order)
- [ ] Prevention step included (Jest test, TypeScript type, or lint rule)
- [ ] For BullMQ errors: idempotency and retry strategy addressed
- [ ] For circular deps: structure resolved, not just `forwardRef` workaround

## Avoid

- Proposing a fix before classifying the error (skipping STEP 2 leads to symptom-level fixes)
- Adding try/catch to suppress errors instead of fixing the root cause
- Using `@ts-ignore` or `as any` to silence TypeScript errors
- Adding null checks everywhere as band-aids instead of fixing the data source
- Using `forwardRef()` for circular deps without considering service extraction
- Recommending `synchronize: true` or `prisma db push` to "fix" migration issues
- Swallowing BullMQ job errors (the job should fail and retry, not silently succeed)
