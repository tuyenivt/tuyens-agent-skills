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

- `strict: true` plus `noUncheckedIndexedAccess`, `noImplicitReturns`, `exactOptionalPropertyTypes`. Fix the code, never weaken the config. On a legacy codebase turn flags on one at a time and hold the outstanding errors in a checked-in baseline whose counts may only fall - a per-file opt-out lets new code in an old file stay loose, a baseline does not
- No `any`. Use `unknown` + type guards; an assertion (`as T`) is tolerated only inside the one validating function that constructs a type
- Domain IDs use branded types so `customerId` cannot flow into an `orderId` slot - in signatures, events, and repositories alike
- Prefer `const` objects + union types over `enum`. Prisma already generates const objects (`$Enums`) - import them, never redeclare; TypeORM's `enum:` column option accepts a const object; an existing TS `enum` in an entity may stay
- `@ts-ignore` / `@ts-expect-error` only with a comment justifying it
- Request DTOs that a framework validates at runtime are classes, not type aliases: a NestJS `@Body() dto: SomeAlias` has metatype `Object`, so `ValidationPipe` skips it and `whitelist` strips nothing

## Patterns

### `unknown` + type guard instead of `any`

```typescript
const isOrderStatus = (v: unknown): v is OrderStatus =>
  typeof v === "string" && (Object.values(OrderStatus) as string[]).includes(v);

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

A guard that checks only that keys exist is an unchecked assertion with a guard's name. For anything past a few fields, validate with a schema (Zod) and infer the type from it.

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

A `Result<T>` is the same shape: `{ ok: true; data: T } | { ok: false; error: AppError }`, narrowed on `ok`.

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

Brand at the edges - controller input, repository mapper, third-party adapter - and the interior needs no assertions. `JSON.stringify` throws on a `bigint`, so wire and event shapes carry `minor: string` (a `MoneyDto`), converted at the mapper. Branding stops `CustomerId` reaching an `OrderId` slot; it does not stop `fromAccount` / `toAccount` swapping, which needs a named-parameter object.

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

`assertNever` in `default` is the guarantee. Without it, a missing case is caught by TS2366 (annotated return type excluding `undefined`) or TS7030 (`noImplicitReturns`) only when the switch's value is returned; a switch run for side effects, or returning into a `| undefined` type, compiles silently.

### DTOs

Internal, already-validated shapes use utility types (`Pick`, `Omit`, `Partial`, `Required`, `Readonly`, `Record`). Runtime-validated request DTOs in NestJS are classes derived with `PickType` / `PartialType` / `OmitType` from `@nestjs/mapped-types` (or `@nestjs/swagger`), decorated with class-validator; their fields take `!` (definite assignment - populated by the pipe; TypeORM entity columns, hydrated by the ORM, are the other sanctioned use under `strictPropertyInitialization`). A Zod schema is the alternative: `type Dto = z.infer<typeof schema>`, parsed at the controller.

Under `exactOptionalPropertyTypes`, `field?: T` means "the key may be absent", not "the value may be `undefined`" - so `{ ...dto, status: undefined }` does not type-check. Omit the key instead, and model "clear this field" explicitly:

```typescript
// PATCH: memo absent = unchanged, null = clear, string = set
export class UpdateTransferDto {
  @IsOptional() @IsString() memo?: string | null;          // class-validator: IsOptional admits null too
}

const patch = {
  ...(dto.memo !== undefined && { memo: dto.memo }),       // null passes through as "clear"
};
```

For Prisma, derive response and internal types from the **row** type (`Prisma.TransferGetPayload<...>` / the model type), not from `TransferUpdateInput`, whose fields accept operation objects like `{ set: ... }` a client could post.

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

Install `@types/<pkg>`. If none exists, write a narrow `types/<pkg>.d.ts` with `declare module "<pkg>"` - type the surface you use, not `any`. Put it under a directory in tsconfig `include`. Under `strict` a missing declaration is a loud TS7016, not a silent `any`. The file has no top-level `import` / `export` - that turns `declare module` into an augmentation of a module that has no types, which fails (TS2664 / TS2665); put any imports **inside** the `declare module` block. A hand-written declaration is an unverified claim, so validate the response at the adapter boundary.

### `noUncheckedIndexedAccess`

Index-signature reads (`Record<string, T>`, `{ [k: string]: T }`) and array elements are `T | undefined`; declared properties, finite-key records, and in-range tuple positions are not. `k in m` and a length check do not narrow the read - bind the value and check it (`const v = m[k]; if (v === undefined) ...`), or iterate with `for...of` / `entries()`.

### Strict-mode migration

```bash
# baseline for the flag under migration: error count per file and code, checked in; CI fails when any count rises
npx tsc --noEmit --strictNullChecks 2>&1 | grep -oE "^[^(]+\([0-9]+,[0-9]+\): error TS[0-9]+" \
  | sed -E 's/\([0-9]+,[0-9]+\)//' | sort | uniq -c > ts-baseline-strictNullChecks.txt
```

Order the flags from mechanical to invasive, one per release: `alwaysStrict`, `noImplicitAny`, `noImplicitThis`, `strictBindCallApply`, `strictFunctionTypes`, `strictBuiltinIteratorReturn` (TS 5.6+), `useUnknownInCatchVariables`, `strictNullChecks` (the large one - split it by directory), `strictPropertyInitialization`, then `noImplicitReturns`, `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`. One baseline file per flag; the CLI flag overrides an explicit `false` in the legacy tsconfig. Tools like `betterer` automate the ratchet.

## Output Format

When authoring, emit the block below, then the actual type declarations and the tsconfig JSON - the table indexes the design, it is not the design. A build over existing code is authoring plus review - findings for the existing defects the change touches, then the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole (an `any` that hides a wrong shape at runtime - worst when it lets `undefined` reach a Prisma `where`, which drops that filter - or a DTO that skips validation), `[Recommend]` otherwise. After the findings, emit this block as the target state: every row shows the corrected value, and a row the current code violates ends ` - GAP (was: <observed>)`. When planning a strict-mode migration, emit no findings (the baseline is the defect list): replace the Types table with the phased flag order, the baseline, and one representative fix per error class; keep the other sections.

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

- `any`, including via `as any` or untyped third-party modules
- `as T` assertions in place of type guards
- `enum` for new code (import Prisma's `$Enums`; pass TypeORM a const object)
- Loosening tsconfig to silence errors
- `@ts-ignore` / `@ts-expect-error` without justification
- Hand-rolled duplicates of Prisma-generated types
