---
name: task-node-debug
description: Debug Node.js/TypeScript application errors - NestJS and Express errors, Prisma and TypeORM issues, TypeScript compilation errors, and Jest test failures. Paste a stack trace or describe the unexpected behavior. Not for production incident analysis with blast radius assessment (use task-incident-root-cause for that).
agent: node-architect
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

# Debug Node.js/TypeScript Error

## When to Use

- Debugging stack traces, runtime errors, build failures, or test failures in NestJS or Express applications
- Diagnosing TypeScript compilation errors, Prisma/TypeORM query errors, or DI resolution failures
- Investigating BullMQ job failures, unhandled rejections, or middleware ordering issues

## Rules

- Classify the error before reading any source code or proposing a fix
- Always state confidence level (high/medium/low) with root cause
- Provide minimal before/after fix - address root cause, not symptoms
- Include a prevention step (test, type constraint, or lint rule) with every fix

## Edge Cases

- **No stack trace provided**: Ask the user to reproduce the error and capture the full stack trace. If they describe behavior only, ask for: (1) the exact error message or unexpected output, (2) which endpoint or command triggers it, (3) recent code changes.
- **Multiple errors in output**: Identify the root error (usually the first one) - later errors are often cascading failures.
- **Intermittent errors**: Ask about concurrency, connection pool exhaustion, or race conditions. Check for missing `await` on async operations.

## Implementation

STEP 1 - INTAKE: Collect the error - stack trace, Jest failure output, build error, or runtime error description. If the user provides only a description without an error message, ask for the exact error output before proceeding.

STEP 2 - CLASSIFY the error into one of these categories:

| Error Pattern                                                       | Category          | First Check                                                                 |
| ------------------------------------------------------------------- | ----------------- | --------------------------------------------------------------------------- |
| `Cannot read properties of undefined (reading 'method')` in service | NestJS DI         | Missing `@Injectable()`, provider not in module `providers[]`, circular dep |
| `TypeError: Cannot read properties of undefined`                    | Null access       | Trace variable origin, check optional chaining                              |
| `PrismaClientKnownRequestError (P2002)`                             | Unique constraint | Duplicate value on unique field                                             |
| `PrismaClientKnownRequestError (P2025)`                             | Record not found  | ID does not exist or was deleted                                            |
| `QueryFailedError` (TypeORM)                                        | SQL error         | Check migration state, column types                                         |
| `UnauthorizedException` (NestJS)                                    | Auth guard        | Token missing/expired, guard misconfigured                                  |
| `BadRequestException` (NestJS)                                      | Validation        | DTO validation failed, check decorators                                     |
| `TS2322` / `TS2345`                                                 | Type mismatch     | Incompatible types in assignment or argument                                |
| `Cannot find module`                                                | Missing dep       | Wrong import path or missing install; run `bun install`                     |
| `Circular dependency detected` (NestJS)                             | Circular DI       | Use `forwardRef()` or extract shared logic to third service                 |
| `ERR_UNHANDLED_REJECTION`                                           | Unhandled promise | Missing `await` or `.catch()` on async call                                 |
| BullMQ job stuck in failed state                                    | Job failure       | Load `node-bullmq-patterns`, check retry/backoff config                     |
| BullMQ worker not processing                                        | Worker issue      | Redis connectivity, worker not registered, missing processor                |
| Job data missing or undefined                                       | Serialization     | Passing entity instead of ID, check job data shape                          |

STEP 3 - LOCATE: Read the stack trace top-to-bottom. Open the referenced source files. Trace the call chain from the error point back to the trigger.

STEP 4 - ROOT CAUSE: State WHY the error occurs (not just what). Include confidence level (high/medium/low) and reasoning.

STEP 5 - FIX: Provide concrete before/after code. Fix must be minimal and address the root cause.

STEP 6 - PREVENTION: Add a Jest test that would catch this error, a stricter TypeScript type, or a lint rule.

## Output

```markdown
## Root Cause

{confidence: high/medium/low} - {explanation of WHY the error occurs}

## Location

`{file}:{line}` - {description of the problematic code}

## Fix

**Before:**
{code}

**After:**
{code}

## Prevention

{test, type constraint, or lint rule to prevent recurrence}
```

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Framework constraints respected (NestJS DI, decorator patterns, Express middleware order)
- [ ] Prevention step included (Jest test, TypeScript type, or lint rule)
- [ ] For circular deps: structure resolved, not just `forwardRef`; for BullMQ: idempotency and retry addressed
