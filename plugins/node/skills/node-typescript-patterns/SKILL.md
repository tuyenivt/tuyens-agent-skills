---
name: node-typescript-patterns
description: TypeScript strict-mode patterns for Node.js: no any, discriminated unions, type guards, generics, branded IDs, strict tsconfig.
metadata:
  category: backend
  tags: [node, typescript, types, generics, strict-mode, patterns]
user-invocable: false
---

# TypeScript Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing TypeScript in a Node.js project
- Replacing `any`, designing type-safe APIs, configuring strict tsconfig

## Rules

- `strict: true` plus `noUncheckedIndexedAccess`, `noImplicitReturns`, `exactOptionalPropertyTypes`. Fix the code, never weaken the config. On a legacy codebase turn flags on one at a time and hold the outstanding errors in a checked-in baseline whose counts may only fall - a per-file opt-out lets new code in an old file stay loose, a baseline does not.
- No `any`. Use `unknown` + type guards; assertions (`as T`) bypass checking.
- Domain IDs use branded types so `customerId` cannot flow into an `orderId` slot.
- Prefer `const` objects + union types over `enum` (exceptions: Prisma-generated enums and TypeORM `@Column({ type: "enum" })` definitions - use as-is).
- `@ts-ignore` / `@ts-expect-error` only with a comment justifying it.

## Patterns

### `unknown` + type guard instead of `any`

```typescript
function isOrder(x: unknown): x is Order {
  return typeof x === "object" && x !== null && "id" in x && "status" in x;
}

function parse<T>(data: string, guard: (x: unknown) => x is T): T {
  const parsed: unknown = JSON.parse(data);
  if (!guard(parsed)) throw new Error("Invalid shape");
  return parsed;
}
```

### Discriminated unions for Result types

```typescript
type Result<T> = { ok: true; data: T } | { ok: false; error: AppError };

if (r.ok) r.data;     // narrowed
else      r.error;    // narrowed
```

### Branded types for domain IDs

```typescript
type OrderId    = string & { readonly __brand: "OrderId" };
type CustomerId = string & { readonly __brand: "CustomerId" };

function findOrder(id: OrderId): Promise<Order | null> { ... }
findOrder(customerId); // compile error - cannot mix IDs
```

A brand needs exactly one construction point, or the `as` ban makes it unusable. Validate there and nowhere else:

```typescript
export const toOrderId = (v: string): OrderId => {
  if (!UUID_RE.test(v)) throw new ValidationError("orderId");
  return v as OrderId;                    // the one sanctioned assertion, inside the validator
};
```

Brand at the edges - controller input, repository mapper, third-party adapter - and the interior needs no assertions. Branding stops `CustomerId` reaching an `OrderId` slot; it does not stop `fromAccount`/`toAccount` swapping, which needs a named-parameter object.

### Exhaustiveness

```typescript
const assertNever = (x: never): never => { throw new Error(`unhandled: ${JSON.stringify(x)}`); };

switch (r.reason) {
  case "declined":  return ...;
  case "expired":   return ...;
  default:          return assertNever(r);   // adding a variant breaks the build here
}
```

`noImplicitReturns` plus `assertNever` is what makes a discriminated union safe to extend.

### Const object instead of enum

```typescript
const OrderStatus = {
  PENDING: "PENDING", CONFIRMED: "CONFIRMED", SHIPPED: "SHIPPED",
} as const;
type OrderStatus = (typeof OrderStatus)[keyof typeof OrderStatus];
```

### DTOs via utility types

`Pick`, `Omit`, `Partial`, `Required`, `Readonly`, `Record<K,V>`, `Extract`/`Exclude`.

```typescript
type CreateOrderDto = Pick<OrderFields, "customerId" | "items" | "shippingAddress">;
type UpdateOrderDto = Partial<Pick<OrderFields, "shippingAddress" | "status">>;
```

Under `exactOptionalPropertyTypes`, `Partial<T>` means "the key may be absent", not "the value may be `undefined`" - so `{ ...dto, status: undefined }` no longer type-checks. Omit the key instead, and model "clear this field" explicitly:

```typescript
const patch = { ...(status !== undefined && { status }) };      // omit, don't set undefined
type UpdateOrderDto = { shippingAddress?: string; note?: string | null };  // null = clear
```

For Prisma projects derive from the generated types rather than hand-rolling duplicates - but derive DTOs from the **row** type (`Prisma.OrderGetPayload<...>` / the model type), not from `OrderUpdateInput`, whose fields accept operation objects like `{ set: ... }` and would let a client post one.

### Generics with constraints

```typescript
interface Repository<T> {
  findById(id: string): Promise<T | null>;
  save(entity: T): Promise<T>;
}

function merge<T extends Record<string, unknown>>(base: T, patch: Partial<T>): T {
  return { ...base, ...patch };
}
```

### Type-safe event maps

```typescript
interface OrderEvents {
  "order.created":  { orderId: string; customerId: string };
  "order.shipped":  { orderId: string; trackingNumber: string };
}

function emit<E extends keyof OrderEvents>(event: E, payload: OrderEvents[E]): void { ... }

emit("order.shipped", { orderId: "1", trackingNumber: "ABC" }); // OK
emit("order.shipped", { orderId: "1" });                        // Error: missing trackingNumber
```

### Untyped third-party packages

Install `@types/<pkg>`. If none exists, write a narrow `types/<pkg>.d.ts` with `declare module` - type the surface you use, not `any`. The file must be reachable from tsconfig `include`/`typeRoots`, or the module silently falls back to `any`; and the file must have no top-level `import`/`export`, which would turn the declaration into a module augmentation that resolves to nothing. A hand-written declaration is an unverified claim, so validate the response at the adapter boundary rather than trusting it.

### `noUncheckedIndexedAccess`

`obj[key]` is `T | undefined`. Use optional chaining or an explicit guard before access.

## Output Format

When authoring, emit this block, then the actual type declarations and the tsconfig JSON below it - the table indexes the design, it is not the design. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit one finding per deviation. When planning a strict-mode migration, replace the Types table with the phased flag order and one representative fix per error class.

```
## TypeScript Design

### Types
| Type             | Kind                | Purpose                  | Constructed at |
|------------------|---------------------|--------------------------|----------------|
| OrderId          | branded type        | domain ID safety         | toOrderId()    |
| CreateOrderDto   | Pick<>              | request validation       | controller     |
| OrderResponseDto | class               | API response shape       | mapper         |
| Result<T>        | discriminated union | success/error handling   | service        |

### Generics
[Generic type parameters and their constraints]

### tsconfig Settings
[The JSON, plus what each strictness flag is buying]
```

## Avoid

- `any`, including via `as any` or untyped third-party modules
- `as T` assertions in place of type guards
- `enum` (except Prisma-generated and TypeORM enum columns)
- Loosening tsconfig to silence errors
- `@ts-ignore` / `@ts-expect-error` without justification
- Hand-rolled duplicates of Prisma-generated types
