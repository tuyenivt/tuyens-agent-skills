---
name: node-typescript-patterns
description: TypeScript strict mode patterns for Node.js - proper typing with no `any`, discriminated unions for result types, type guards, utility types, generics, branded types for domain IDs, and strict tsconfig settings.
metadata:
  category: backend
  tags: [node, typescript, types, generics, strict-mode, patterns]
user-invocable: false
---

# TypeScript Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing TypeScript code in a Node.js project
- Enforcing strict typing, replacing `any` with proper types
- Designing type-safe APIs with generics, discriminated unions, or utility types
- Configuring tsconfig for maximum type safety

## Rules

- `strict: true` in tsconfig - never weaken strictness, fix the code instead
- No `any` anywhere - use `unknown` + type narrowing
- Prefer type guards over type assertions (`as T`)
- Use `const` objects or union types instead of `enum`

## Patterns

### Strict tsconfig

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitReturns": true,
    "exactOptionalPropertyTypes": true
  }
}
```

Key message: never weaken strictness to silence type errors - fix the code instead.

### No `any` - Use `unknown` + Type Narrowing

```typescript
// Type guard for runtime type checking
function isOrder(x: unknown): x is Order {
  return typeof x === "object" && x !== null && "id" in x && "status" in x;
}

// Generic function instead of any
function parse<T>(data: string, validator: (x: unknown) => x is T): T {
  const parsed: unknown = JSON.parse(data);
  if (!validator(parsed)) throw new Error("Invalid data shape");
  return parsed;
}
```

### Discriminated Unions (Result Types)

Use discriminated unions for operations that can succeed or fail with different data shapes:

```typescript
type Result<T> =
  | { success: true; data: T }
  | { success: false; error: AppError };

// TypeScript narrows the type after checking the discriminant
function handleResult(result: Result<Order>) {
  if (result.success) {
    console.log(result.data.id); // TypeScript knows data exists
  } else {
    console.error(result.error.message); // TypeScript knows error exists
  }
}
```

### Branded Types for Domain IDs

Prevent accidentally passing a `customerId` where an `orderId` is expected:

```typescript
type OrderId = string & { readonly __brand: 'OrderId' };
type CustomerId = string & { readonly __brand: 'CustomerId' };

function createOrderId(id: string): OrderId {
  return id as OrderId;
}

// Compile-time error: CustomerId is not assignable to OrderId
function findOrder(id: OrderId): Promise<Order | null> { ... }
```

### Utility Types for DTO Derivation

- `Partial<T>`, `Required<T>`, `Pick<T, K>`, `Omit<T, K>` for DTO derivation
- `Record<string, T>` for dictionaries
- `Readonly<T>` for immutable data
- `Extract`/`Exclude` for union manipulation

```typescript
// Derive DTOs from a base type
interface OrderFields {
  customerId: string;
  items: OrderItemDto[];
  shippingAddress: string;
  status: OrderStatus;
}

type CreateOrderDto = Pick<
  OrderFields,
  "customerId" | "items" | "shippingAddress"
>;
type UpdateOrderDto = Partial<Pick<OrderFields, "shippingAddress" | "status">>;
```

### Generics

```typescript
// Typed repository
interface Repository<T> {
  findById(id: string): Promise<T | null>;
  save(entity: T): Promise<T>;
}

// Paginated response
interface PaginatedResponse<T> {
  data: T[];
  meta: {
    page: number;
    pageSize: number;
    totalItems: number;
    totalPages: number;
  };
}

// Constrained generics
function merge<T extends Record<string, unknown>>(
  base: T,
  overrides: Partial<T>,
): T {
  return { ...base, ...overrides };
}
```

### Const Objects Over Enums

```typescript
// Prefer this (tree-shakeable, works with plain JS interop)
const OrderStatus = {
  PENDING: "PENDING",
  CONFIRMED: "CONFIRMED",
  SHIPPED: "SHIPPED",
  DELIVERED: "DELIVERED",
  CANCELLED: "CANCELLED",
} as const;

type OrderStatus = (typeof OrderStatus)[keyof typeof OrderStatus];

// Instead of: enum OrderStatus { PENDING, CONFIRMED, SHIPPED }
```

Note: Prisma generates its own enums. When using Prisma-generated enums, use them directly rather than re-declaring as const objects.

### Type-Safe Event Handling

```typescript
// Type-safe event map for webhook or domain events
interface OrderEvents {
  "order.created": { orderId: string; customerId: string };
  "order.shipped": { orderId: string; trackingNumber: string };
  "order.delivered": { orderId: string };
}

type OrderEventName = keyof OrderEvents;

function emit<E extends OrderEventName>(
  event: E,
  payload: OrderEvents[E],
): void {
  // ...
}

// TypeScript enforces correct payload shape per event
emit("order.shipped", { orderId: "123", trackingNumber: "ABC" }); // OK
emit("order.shipped", { orderId: "123" }); // Error: missing trackingNumber
```

## Edge Cases

- **Third-party libraries without types**: Install `@types/<package>` first. If no types exist, create a local `types/<package>.d.ts` with `declare module '<package>'` - type it as narrowly as possible, not `any`.
- **JSON.parse returns `any`**: Always assign to `unknown` first, then validate with a type guard before using.
- **Index signatures returning `undefined`**: With `noUncheckedIndexedAccess`, `obj[key]` is `T | undefined`. Use optional chaining or an explicit check before accessing.
- **Prisma-generated types**: Prisma generates its own types from the schema. Use `Prisma.OrderCreateInput` and similar generated types rather than hand-writing input types that duplicate the schema.

## Output Format

```
## TypeScript Design

### Types
| Type | Kind | Purpose |
|------|------|---------|
| OrderId | branded type | domain ID safety |
| CreateOrderDto | Pick<> | request validation |
| OrderResponseDto | class | API response shape |
| Result<T> | discriminated union | success/error handling |

### Generics
[Generic type parameters and their constraints]

### tsconfig Settings
[Key strictness settings and their purpose]
```

## Avoid

- `any` anywhere (use `unknown` or proper types)
- Type assertions (`as T`) instead of type guards (assertions bypass checking)
- `enum` (use const objects or union types in modern TypeScript - except Prisma-generated enums)
- Disabling strict checks to "fix" type errors
- `@ts-ignore` / `@ts-expect-error` without a comment explaining why it is necessary
- Duplicating Prisma-generated types by hand (use the generated types directly)
