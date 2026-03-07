---
name: task-node-debug
description: "Debug Node.js/TypeScript errors. Paste a stack trace, test failure, or describe unexpected behavior. Handles NestJS and Express errors, Prisma and TypeORM issues, and TypeScript compilation errors."
agent: node-architect
metadata:
  category: backend
  tags: [node, typescript, nestjs, express, debug, troubleshooting, workflow]
  type: workflow
user-invocable: true
---

STEP 1 - INTAKE: stack trace, Jest failure, build error, runtime error

STEP 2 - CLASSIFY:

- TypeError: Cannot read properties of undefined → null/undefined access
- PrismaClientKnownRequestError (P2002) → unique constraint violation
- PrismaClientKnownRequestError (P2025) → record not found
- QueryFailedError (TypeORM) → SQL error, check migration state
- UnauthorizedException (NestJS) → auth guard failed
- BadRequestException (NestJS) → validation pipe rejected input
- TS2322 / TS2345 → TypeScript type mismatch, check types
- Cannot find module → missing dependency, wrong import path
- Circular dependency detected (NestJS) → forwardRef or refactor modules
- ERR_UNHANDLED_REJECTION → unhandled promise rejection, add catch
- BullMQ job stuck in failed state → load node-bullmq-patterns, check retry/backoff config
- BullMQ worker not processing → Redis connectivity, worker not registered, missing processor
- Job data missing or undefined → passing entity instead of ID, check serialization

STEP 3 - LOCATE: read stack trace, open source, trace call chain

STEP 4 - ROOT CAUSE: WHY. Confidence level.

STEP 5 - FIX: before/after, minimal change

STEP 6 - PREVENTION: Jest test, stricter types, lint rule

OUTPUT: root cause → location → fix → prevention

## Success Criteria

A well-executed debug session passes all of these. Use as a self-check before presenting the fix.

### Completeness

- [ ] Error is classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line
- [ ] A concrete before/after code fix is provided - no vague suggestions
- [ ] A prevention step is included (Jest test, TypeScript type, or lint rule)

### Correctness

- [ ] The fix addresses the root cause, not the symptom
- [ ] Confidence level is stated - LOW confidence lists what additional info would help
- [ ] The fix is minimal - no unrelated refactoring
- [ ] Framework constraints respected (NestJS DI, decorator patterns, Express middleware order)

### Staff-Level Signal

- [ ] The "why" is explained - a developer understands how to avoid this class of bug
- [ ] For circular dependency errors, the fix resolves the structure - not just applies `forwardRef`
- [ ] For BullMQ issues, job idempotency and retry config are addressed alongside the immediate fix

## After This Skill

If the output needed significant adjustment - root cause was wrong, TypeScript types were incorrectly diagnosed, or NestJS DI constraints were missed - run `/task-skill-feedback` to log what changed and why.
