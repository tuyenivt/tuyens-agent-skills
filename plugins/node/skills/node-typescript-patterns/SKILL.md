---
name: node-typescript-patterns
description: TypeScript strict-mode patterns for Node.js: no any, discriminated unions, type guards, generics, branded IDs, strict tsconfig.
metadata:
  category: backend
  tags: [node, typescript, types, generics, strict-mode, patterns]
user-invocable: false
---

# TypeScript Patterns

> Load `Use skill: stack-detect` first. `ORM` picks the enum and derived-type guidance (Prisma / TypeORM; any other ORM takes the const-object-plus-union default) and `Framework` the DTO form (NestJS: validated classes); both surface only in the design block's `**Stack:**` line.

## When to Use

- Writing or reviewing TypeScript in a Node.js project
- Replacing `any`, designing type-safe APIs and domain types, configuring strict tsconfig
- Planning a strict-mode migration on a legacy codebase

## Rules

- `strict: true` plus `noUncheckedIndexedAccess`, `noImplicitReturns`, `exactOptionalPropertyTypes`. Fix the code, never weaken the config. On a legacy codebase turn flags on one at a time behind a checked-in baseline whose counts may only fall (Strict-mode migration below)
- No `any`. Use `unknown` + type guards; an assertion (`as T`) is tolerated only inside the one validating function that constructs a type - an `as` after an `includes` check included
- Domain IDs use branded types so `customerId` cannot flow into an `orderId` slot - in signatures, events, and repositories alike
- Prefer `const` objects + union types over `enum`. Prisma already generates const objects (`$Enums`) - import them, never redeclare; TypeORM's `enum:` column option accepts a const object; an existing TS `enum` in an entity may stay
- `@ts-ignore` / `@ts-expect-error` only with a comment justifying it
- Request DTOs that a framework validates at runtime are classes, not type aliases: a NestJS `@Body() dto: SomeAlias` has metatype `Object`, so `ValidationPipe` skips it and `whitelist` strips nothing

## Patterns

### `unknown` + type guard instead of `any`

```typescript
const isOrderStatus = (v: unknown): v is OrderStatus =>
  typeof v === "string" && Object.values<string>(OrderStatus).includes(v);

function isOrder(x: unknown): x is Order {
  return typeof x === "object" && x !== null
    && "id" in x && typeof x.id === "string"            // `in` narrowing (TS 4.9+) lets the guard check types
    && "status" in x && isOrderStatus(x.status);
}

function parse<T>(data: string, guard: (x: unknown) => x is T): T {
  const parsed: unknown = JSON.parse(data);
  if (!guard(parsed)) throw new Error("Invalid shape");
  return parsed;
}
```

A guard that only checks keys exist is an assertion with a guard's name; past a few fields, validate with a Zod schema and infer the type.

### Discriminated unions and state machines

```typescript
type Transfer =
  | { status: "pending";    id: TransferId }
  | { status: "authorized"; id: TransferId; authCode: string }
  | { status: "settled";    id: TransferId; settledAt: Date }
  | { status: "failed";     id: TransferId; reason: string }
  | { status: "reversed";   id: TransferId; reversedAt: Date };

const NEXT: { [S in Transfer["status"]]: readonly Transfer["status"][] } = {
  pending: ["authorized", "failed"],
  authorized: ["settled", "failed"],
  settled: ["reversed"],
  failed: [],
  reversed: [],
};
```

A `Result<T>` (`{ ok: true; data: T } | { ok: false; error: AppError }`, narrowed on `ok`) only where callers branch on several failure shapes carrying data (`node-exception-handling`); otherwise throw.

### Branded types for domain IDs and values

```typescript
type OrderId    = string & { readonly __brand: "OrderId" };
type CustomerId = string & { readonly __brand: "CustomerId" };

// One construction point per brand, and no assertion: a predicate narrows
const isOrderId = (v: string): v is OrderId => UUID_RE.test(v);
export const toOrderId = (v: string): OrderId => {
  if (!isOrderId(v)) throw new ValidationError("orderId");
  return v;
};

// A compound value is a branded readonly object; its constructor is the one sanctioned assertion
type Currency = "USD" | "EUR" | "JPY";
type Money = { readonly minor: bigint; readonly currency: Currency } & { readonly __brand: "Money" };
const money = (minor: bigint, currency: Currency): Money => ({ minor, currency }) as Money;   // minor units, never float
```

Brand at the edges - controller input (`@Param("id", ParseUUIDPipe) id: string`, then `toOrderId(id)`; a missing pipe is `[Recommend]`, `[Must]` once the raw string reaches a query), repository mapper, third-party adapter - and the interior needs no assertions. An ORM column stays `string` on the entity (the ORM hydrates it unchecked; TypeORM returns `decimal` as a string - `node-typeorm-patterns`); the mapper brands it. Derive a DB enum's union from the const object the column is given (`type OrderStatus = (typeof OrderStatus)[keyof typeof OrderStatus]`) - one object, no drift. `JSON.stringify` throws on a `bigint`, so wire and event shapes carry `minor: string` (a `MoneyDto`), converted at the mapper. Branding does not stop `fromAccount` / `toAccount` swapping - that needs a named-parameter object.

### Exhaustiveness

```typescript
const assertNever = (x: never): never => { throw new Error(`unhandled: ${JSON.stringify(x)}`); };

switch (t.status) {
  case "pending":    return ...;
  case "authorized": return ...;
  case "settled":    return ...;
  case "failed":     return ...;
  case "reversed":   return ...;
  default:           return assertNever(t);   // adding a variant breaks the build here
}
```

`assertNever` in `default` is the guarantee. Without it a missing case surfaces only when the switch's value is returned (TS2366 with a return type excluding `undefined`, else TS7030 under `noImplicitReturns`); a switch run for side effects compiles silently.

### DTOs

Internal, already-validated shapes use utility types (`Pick`, `Omit`, `Partial`, `Record`). Runtime-validated request DTOs in NestJS are classes derived with `PickType` / `PartialType` / `OmitType` from `@nestjs/mapped-types` (or `@nestjs/swagger`), decorated with class-validator; required fields take `!` (definite assignment, populated by the pipe; ORM-hydrated entity columns are the other sanctioned use under `strictPropertyInitialization`) and optional fields `?`. A Zod schema is the alternative: `type Dto = z.infer<typeof schema>`, parsed at the controller.

Under `exactOptionalPropertyTypes`, `field?: T` means the key may be absent, not that the value may be `undefined`: `{ ...dto, status: undefined }` fails. Omit the key, and model "clear this field" explicitly:

```typescript
// PATCH: memo absent = unchanged, null = clear, string = set
export class UpdateTransferDto {
  @IsOptional() @IsString() memo?: string | null;          // class-validator: IsOptional admits null too
}

const patch = {
  ...(dto.memo !== undefined && { memo: dto.memo }),       // null passes through as "clear"
};
```

For Prisma, derive response and internal types from the **row** type (`Prisma.TransferGetPayload<...>`), never from `TransferUpdateInput`, whose fields accept operation objects (`{ set: ... }`) a client could post.

### Request principal

The verified JWT payload is `unknown` until guarded (`jose` and `jsonwebtoken` return a loose object); guard once, in the auth guard or middleware, and handlers read a typed principal.

```typescript
interface AccessClaims { sub: UserId; tenantId: TenantId; role: "staff" | "customer" }
const isAccessClaims = (p: unknown): p is AccessClaims =>                  // brands only through each brand's own predicate
  typeof p === "object" && p !== null && "sub" in p && typeof p.sub === "string" && isUserId(p.sub)
    && "tenantId" in p && typeof p.tenantId === "string" && isTenantId(p.tenantId)
    && "role" in p && (p.role === "staff" || p.role === "customer");

// Express: augment the global Express namespace so inferred handler params see it (node-express-patterns);
// with @types/passport, augment `interface User extends AccessClaims {}` instead - it already types Request.user
declare global { namespace Express { interface Request { user?: AccessClaims } } }

// NestJS: a param decorator, never `@Req() req: any`
export const CurrentUser = createParamDecorator((_data: unknown, ctx: ExecutionContext): AccessClaims => {
  const user = ctx.switchToHttp().getRequest<{ user?: AccessClaims }>().user;   // set by the guard; absent on a public route
  if (!user) throw new UnauthorizedException();
  return user;
});
```

### Generics with constraints

```typescript
interface Repository<T, Id> {
  findById(id: Id): Promise<T | null>;
  save(entity: T): Promise<T>;
}

// `object`, not Record<string, unknown>: interfaces and class instances have no index signature
function merge<T extends object>(base: T, patch: Partial<T>): T {
  return { ...base, ...patch };
}
```

### Type-safe event maps

```typescript
interface TransferEvents {
  "transfer.authorized": { transferId: TransferId; authCode: string };
  "transfer.settled":    { transferId: TransferId; amount: MoneyDto };   // wire shape: minor as string
}

function emit<E extends keyof TransferEvents>(event: E, payload: TransferEvents[E]): void { ... }

emit("transfer.settled", { transferId, amount });   // OK
emit("transfer.settled", { transferId });           // Error: missing amount
```

### Untyped third-party packages

Install `@types/<pkg>`; if none exists, write a narrow `types/<pkg>.d.ts` with `declare module "<pkg>"` under a directory in tsconfig `include` - type the surface you use, not `any` (under `strict` a missing declaration is a loud TS7016). No top-level `import` / `export` in that file: it turns `declare module` into an augmentation that never applies - TS2665 in the `.d.ts` without `skipLibCheck`, otherwise only the TS7016 at the import; put imports **inside** the block. A hand-written declaration is an unverified claim - validate at the adapter boundary.

### `noUncheckedIndexedAccess`

Index-signature reads (`Record<string, T>`) and array elements are `T | undefined`; declared properties, finite-key records, and in-range tuple positions are not. `k in m` and a length check do not narrow the read - bind the value and check it (`const v = m[k]; if (v === undefined) ...`), or iterate with `for...of` / `entries()`.

### Strict-mode migration

```bash
# baseline for the flag under migration: error count per file and code, checked in; CI regenerates it and fails on any difference (`diff -q`), so a fix commits the lowered baseline with it
# -p the config CI type-checks (a tsconfig.build.json that excludes tests is a second baseline); --pretty false, or a "pretty": true config yields zero lines
npx tsc --noEmit --pretty false --strictNullChecks 2>&1 | grep -oE "^[^(]+\([0-9]+,[0-9]+\): error TS[0-9]+" \
  | sed -E 's/\([0-9]+,[0-9]+\)//' | sort | uniq -c > ts-baseline-strictNullChecks.txt
```

Order the flags from mechanical to invasive, one per release: `alwaysStrict`, `noImplicitAny`, `noImplicitThis`, `strictBindCallApply`, `strictFunctionTypes`, `strictBuiltinIteratorReturn` (TS 5.6+), `useUnknownInCatchVariables`, `strictNullChecks` (the large one - split it by directory), `strictPropertyInitialization`, then `noImplicitReturns`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`. A flag already on is listed as done, no baseline. One baseline file per flag; the CLI flag overrides an explicit `false` in the legacy tsconfig. Once every member flag is on, replace them with `strict: true`. On TypeScript 6+ `strict` defaults to `true` and `alwaysStrict: false` is deprecated (removed in 7): a legacy tsconfig sets `"strict": false` explicitly before upgrading, and the ladder starts at `noImplicitAny`. Alongside the ladder: `target` ES2022 and `lib` from the Node major (`.node-version`): ES2023 on Node 20, ES2024 on Node 22 - the `@tsconfig/node<major>` bases, `module` `node16` / `nodenext` for a Node package, and `useDefineForClassFields` (default on from `target` ES2022) gives every declared-but-unassigned field an own `undefined` property (`Object.keys(dto)` lists it) - `false` where decorator-based classes or `hasOwn` checks care.

## Output Format

When authoring, emit the block below, then the type declarations and the tsconfig JSON - the table indexes the design. A build over existing code is authoring plus review - findings for the existing defects the change touches, then the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole (an `any` that hides a wrong shape at runtime - worst when it lets `undefined` reach a Prisma `where`, which drops that filter - or a DTO that skips validation), `[Recommend]` otherwise. After the findings, emit this block as the target state: the Types table lists the types the change adds or touches (a review: the types the findings name), every row shows the corrected value, a row the current code violates ends ` - GAP (was: <observed>)` in its last cell, and the tsconfig slot carries the full `compilerOptions` when authoring and only the keys that change (a flag turned on, a redundant key removed) when reviewing - a required flag that is off is one finding at the tsconfig, not one per site, and its line in the slot's explanation ends ` - GAP (was: <observed>)`. A defect outside this skill's lens (a hardcoded secret) goes on one `Out of scope: <defect> - <owning skill>` line after the findings, before the block. When planning a strict-mode migration, emit no findings (the baseline is the defect list): replace the Types table with the phased flag order, the baseline, and one representative fix per error class (class = TS error code); keep the Stack line and the other sections (Generics `none in scope`).

```
## TypeScript Design

**Stack:** {Prisma | TypeORM | <other ORM name> | none} + {NestJS | Express | other}

### Types
| Type             | Kind                          | Purpose                  | Constructed at |
|------------------|-------------------------------|--------------------------|----------------|
| OrderId          | branded type                  | domain ID safety         | toOrderId()    |
| CreateOrderDto   | class (PickType) or z.infer   | request validation       | controller     |
| OrderResponseDto | class or type                 | API response shape       | mapper         |
| Transfer         | discriminated union           | state machine            | service        |

### Generics
{generic type parameters and their constraints | none in scope}

### tsconfig Settings
{the compilerOptions JSON, and what each strictness flag is buying}
```

## Avoid

- Hand-rolled duplicates of Prisma-generated types
