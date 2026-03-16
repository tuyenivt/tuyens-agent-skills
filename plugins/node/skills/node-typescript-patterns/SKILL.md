---
name: node-typescript-patterns
description: TypeScript strict mode patterns for Node.js - proper typing with no `any`, discriminated unions for result types, type guards, utility types, generics, and strict tsconfig settings.
metadata:
  category: backend
  tags: [node, typescript, types, generics, strict-mode, patterns]
user-invocable: false
---

# TypeScript Patterns

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

```typescript
type Result<T> =
  | { success: true; data: T }
  | { success: false; error: AppError };

// Usage - TypeScript narrows the type after checking discriminant
function handleResult(result: Result<Order>) {
  if (result.success) {
    console.log(result.data.id); // TypeScript knows data exists
  } else {
    console.error(result.error.message); // TypeScript knows error exists
  }
}
```

### Utility Types

- `Partial<T>`, `Required<T>`, `Pick<T, K>`, `Omit<T, K>` for DTO derivation
- `Record<string, T>` for dictionaries
- `Readonly<T>` for immutable data
- `Extract`/`Exclude` for union manipulation

### Generics

```typescript
// Typed repository
interface Repository<T> {
  findById(id: string): Promise<T | null>;
  save(entity: T): Promise<T>;
}

// Constrained generics
function merge<T extends Record<string, unknown>>(base: T, overrides: Partial<T>): T {
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
} as const;

type OrderStatus = (typeof OrderStatus)[keyof typeof OrderStatus];

// Instead of: enum OrderStatus { PENDING, CONFIRMED, SHIPPED }
```

## Edge Cases

- **Third-party libraries without types**: Install `@types/<package>` first. If no types exist, create a local `types/<package>.d.ts` with `declare module '<package>'` - type it as narrowly as possible, not `any`.
- **JSON.parse returns `any`**: Always assign to `unknown` first, then validate with a type guard before using.
- **Index signatures returning `undefined`**: With `noUncheckedIndexedAccess`, `obj[key]` is `T | undefined`. Use optional chaining or an explicit check before accessing.

## Avoid

- `any` anywhere (use `unknown` or proper types)
- Type assertions (`as T`) instead of type guards (assertions bypass checking)
- `enum` (use const objects or union types in modern TypeScript)
- Disabling strict checks to "fix" type errors
- `@ts-ignore` / `@ts-expect-error` without a comment explaining why it is necessary
