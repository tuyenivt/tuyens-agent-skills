---
name: task-node-debug
description: "Debug Node.js/TypeScript errors. Paste a stack trace, test failure, or describe unexpected behavior. Handles NestJS and Express errors, Prisma and TypeORM issues, and TypeScript compilation errors."
agent: node-architect
---

STEP 1 — INTAKE: stack trace, Jest failure, build error, runtime error

STEP 2 — CLASSIFY:

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

STEP 3 — LOCATE: read stack trace, open source, trace call chain

STEP 4 — ROOT CAUSE: WHY. Confidence level.

STEP 5 — FIX: before/after, minimal change

STEP 6 — PREVENTION: Jest test, stricter types, lint rule

OUTPUT: root cause → location → fix → prevention
