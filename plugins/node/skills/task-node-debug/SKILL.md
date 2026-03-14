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

STEP 1 - INTAKE: stack trace, Jest failure, build error, runtime error

STEP 2 - CLASSIFY:

- DI / Injection errors (NestJS): `Cannot read properties of undefined (reading 'method')` in a service → missing `@Injectable()`, provider not listed in module `providers[]`, or circular dependency. Check constructor injection and module metadata. Prevention: NestJS integration test that bootstraps the full module and calls `app.get(YourService)`.
- TypeError: Cannot read properties of undefined → null/undefined access
- PrismaClientKnownRequestError (P2002) → unique constraint violation
- PrismaClientKnownRequestError (P2025) → record not found
- QueryFailedError (TypeORM) → SQL error, check migration state
- UnauthorizedException (NestJS) → auth guard failed
- BadRequestException (NestJS) → validation pipe rejected input
- TS2322 / TS2345 → TypeScript type mismatch, check types
- Cannot find module → missing dependency, wrong import path; run `bun install`
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

## Self-Check

- [ ] Error classified before any code is read or fix proposed
- [ ] Root cause references the specific source file and line; confidence level stated
- [ ] Concrete before/after fix provided; fix is minimal, addresses root cause not symptom
- [ ] Framework constraints respected (NestJS DI, decorator patterns, Express middleware order)
- [ ] Prevention step included (Jest test, TypeScript type, or lint rule)
- [ ] For circular deps: structure resolved, not just `forwardRef`; for BullMQ: idempotency and retry addressed

> Run `/task-skill-feedback` if output needed significant correction.
