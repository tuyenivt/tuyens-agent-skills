---
name: node-typescript-patterns
description: "TypeScript strict mode patterns for Node.js: proper typing, generics, discriminated unions, type guards, utility types, no 'any', and strict tsconfig settings."
user-invocable: false
---

Cover:

1. STRICT TSCONFIG:
   - strict: true (enables all strict checks)
   - noUncheckedIndexedAccess: true
   - noImplicitReturns: true
   - exactOptionalPropertyTypes: true
   - Key message: never weaken strictness, fix the code instead

2. NO `ANY`:
   - Use unknown + type narrowing instead of any
   - Type guards: function isOrder(x: unknown): x is Order
   - Generic functions over any: function parse<T>(data: string): T

3. DISCRIMINATED UNIONS (for result types):

```typescript
type Result<T> =
  | { success: true; data: T }
  | { success: false; error: AppError };
```

4. UTILITY TYPES:
   - Partial<T>, Required<T>, Pick<T, K>, Omit<T, K>
   - Record<string, T> for dictionaries
   - Readonly<T> for immutable data
   - Extract/Exclude for union manipulation

5. GENERICS:
   - Repository<T> for typed data access
   - Service<TCreate, TUpdate, TResponse> for typed service layer
   - Constrained generics: <T extends BaseEntity>

6. ANTI-PATTERNS:
   - ❌ `any` anywhere (use unknown or proper types)
   - ❌ Type assertions (as T) instead of type guards
   - ❌ Enums (use const objects or union types in modern TS)
   - ❌ Disabling strict checks to "fix" type errors
