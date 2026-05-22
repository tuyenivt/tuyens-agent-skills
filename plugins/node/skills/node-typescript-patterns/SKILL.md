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

- `strict: true` plus `noUncheckedIndexedAccess`, `noImplicitReturns`, `exactOptionalPropertyTypes`. Fix the code, never weaken the config.
- No `any`. Use `unknown` + type guards; assertions (`as T`) bypass checking.
- Domain IDs use branded types so `customerId` cannot flow into an `orderId` slot.
- Prefer `const` objects + union types over `enum` (exception: Prisma-generated enums - use as-is).
- `@ts-ignore` / `@ts-expect-error` only with a comment justifying it.

## Patterns

### `unknown` + type guard instead of `any`

```typescript
function isOrder(x: unknown): x is Order {
  return typeof x === "object" && x !== null && "id" in x && "status" in x;
}

function parse<T>(data: string, guard: (x: unknown) => x is T): T {
  const parsed: unknown = JSON.parse(data); // JSON.parse returns any - assign to unknown first
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

For Prisma projects use the generated `Prisma.OrderCreateInput` etc. - do not hand-roll duplicates.

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

Install `@types/<pkg>`. If none exists, write a narrow `types/<pkg>.d.ts` with `declare module` - type the surface you use, not `any`.

### `noUncheckedIndexedAccess`

`obj[key]` is `T | undefined`. Use optional chaining or an explicit guard before access.

## Output Format

```
## TypeScript Design

### Types
| Type             | Kind                | Purpose                  |
|------------------|---------------------|--------------------------|
| OrderId          | branded type        | domain ID safety         |
| CreateOrderDto   | Pick<>              | request validation       |
| OrderResponseDto | class               | API response shape       |
| Result<T>        | discriminated union | success/error handling   |

### Generics
[Generic type parameters and their constraints]

### tsconfig Settings
[Key strictness settings and their purpose]
```

## Avoid

- `any`, including via `as any` or untyped third-party modules
- `as T` assertions in place of type guards
- `enum` (except Prisma-generated)
- Loosening tsconfig to silence errors
- `@ts-ignore` / `@ts-expect-error` without justification
- Hand-rolled duplicates of Prisma-generated types
