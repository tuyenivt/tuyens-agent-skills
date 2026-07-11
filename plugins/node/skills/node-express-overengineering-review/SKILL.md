---
name: node-express-overengineering-review
description: Express necessity review - Zod/TypeORM/DB duplication, defensive null on typed values, middleware-of-one, Repository wrappers, custom errors.
metadata:
  category: backend
  tags: [node, express, typescript, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Use only when the detected framework is Express. For NestJS, use `node-nestjs-overengineering-review`.

## When to Use

Reviewing Express diffs that add Zod / class-validator schemas, null guards, middleware factories, custom errors, or new abstractions that are correct but do not need to exist.

## Rules

- Cite the constraint making the code redundant: FK, `@Column({ nullable: false })`, unique index, TypeORM non-`?` field, TS non-null type, Zod rule, validation middleware, or framework guarantee.
- Intent:
  - **`[Recommend]`** default. Escalate to **`[Must]`** with `Cost:` field for: extra SELECT in hot path, blanket `catch` defeating error middleware, no-arg middleware factory, custom error hierarchy with no `instanceof` branching, Repository wrapper of passthroughs.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- Redundancy with **visible** justification is not a finding. See `Avoid`.

## Patterns

### Category 1: Redundant validation vs TypeORM / DB / TS strict-null

Stack: TS strict-null -> Zod / class-validator (via middleware, 400 before handler) -> TypeORM `@Column` -> DB (authoritative).

#### Handler re-checking a schema rule

```ts
// Bad - schema already rejected these
router.post('/orders', validate(CreateOrderSchema), async (req, res) => {
  if (!req.body.customerId) return res.status(400).json(...); // dead
  if (req.body.total <= 0)  return res.status(400).json(...); // dead
});
// Good - type via z.infer and trust the schema
const body = req.body as z.infer<typeof CreateOrderSchema>;
```

#### Schema and column disagree on nullability

```ts
// Bad - schema accepts null; DB rejects on INSERT -> 500 instead of 400
z.object({ customerId: z.string().uuid().nullable() });
// @Column({ nullable: false }) customerId!: string;
```

Drop `.nullable()` or make the column nullable. Pick one.

#### Manual unique-check before `repository.save`

`[Must]` - races and adds a SELECT per write; the unique index decides anyway.

```ts
// Bad
if (await userRepo.findOneBy({ email })) return res.status(409).json(...);
await userRepo.save({ email });

// Good - let the constraint raise; translate in error middleware
try { return await userRepo.save({ email }); }
catch (e) {
  if (e instanceof QueryFailedError && (e.driverError as { code?: string }).code === '23505') {
    return res.status(409).json({ error: 'email taken' });
  }
  throw e;
}
```

### Category 2: Defensive code for impossible states

#### `if (entity === null)` after `findOneOrFail`

```ts
// Bad - findOneOrFail throws on missing
const order = await orderRepo.findOneOrFail({ where: { id } });
if (!order) return res.status(404).json(...); // unreachable
```

Use `findOneOrFail` and let it raise, or `findOneBy` and handle null. Not both.

#### Defensive checks on typed values

```ts
if (order.status) process(...);        // Bad - union type, always truthy
if (order.itemCount) process(...);     // Bad - 0 is valid but falsy
const o = result as unknown as Order;  // Bad - bypasses TS
```

`as` is legitimate at untyped boundaries (third-party `unknown`, framework escapes). Flag when both sides are typed.

#### Blanket `catch (e)` defeating error-handling middleware

`[Must]`. The terminal error middleware maps thrown errors to typed responses; handler-level `try/catch -> 500` erases that mapping.

```ts
// Bad
catch (e) { res.status(500).json({ error: 'failed' }); }

// Good - name the failures; rethrow the rest
catch (e) {
  if (e instanceof InsufficientStockError) throw new AppError(409, e.message);
  if (e instanceof PaymentDeclinedError)   throw new AppError(402, e.message);
  throw e;
}
```

Mapping branches followed by `throw e` is not the no-op rethrow.

#### `try { ... } catch (e) { throw e }` no-op rethrow

Delete it. Wrap with `throw new Error('wrap', { cause: e })` only when the wrap adds context.

### Category 3: Premature abstraction

#### Middleware factory wrapping a one-line operation

`[Must]` when the factory takes no parameters.

```ts
// Bad - no-arg factory
export const requireAdmin = () => (req, res, next) => {...};
router.delete('/x', requireAdmin(), handler);

// Good - export the middleware itself
export const requireAdmin = (req, res, next) => {...};
router.delete('/x', requireAdmin, handler);
```

Justified when parameters vary across mount points (`requireRole('admin')`, `rateLimit({ window: '1m' })`).

#### Repository pattern on top of TypeORM

`[Must]` when the wrapper only passes through. `Repository<T>` is already the repository.

```ts
// Bad - passthroughs over Repository<Order>
class OrderRepository { findById(id) { return this.repo.findOneBy({ id }); } }
// Good
const orderRepo = AppDataSource.getRepository(Order);
```

Justified when it encapsulates multi-table joins, swaps a non-TypeORM source, or provides a test seam `Repository<T>` cannot satisfy.

#### Custom error hierarchy with no consumer branching

```ts
// Bad - DomainError -> NotFoundError -> OrderNotFoundError; no `instanceof` branching
class OrderNotFoundError extends NotFoundError {}
// Good
throw new AppError(404, `order ${id} not found`);
```

Justified when middleware or callers branch on `instanceof` to produce different status codes / payloads.

#### Custom `Result<T, E>` where exceptions or `T | null` suffice

```ts
// Bad
Promise<{ ok: true; order: Order } | { ok: false; error: 'not_found' }>
// Good
Promise<Order | null>
```

Keep `Result<T, E>` only when callers branch on multiple failure modes carrying data beyond a literal.

#### Service class wrapping a single repository call

```ts
// Bad
class OrderService { findById(id) { return this.repo.findOneBy({ id }); } }
// Good
const findOrderById = (id) => AppDataSource.getRepository(Order).findOneBy({ id });
```

Justified for multi-step orchestration, cross-entity writes, or external I/O.

#### Speculative config keys

Flag schema-validated config keys with zero read sites. Confirm with a repo-wide grep first.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Must | Recommend | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `if (!order)` after `findOneOrFail`}
- Redundant because: {FK name | TypeORM `nullable: false` | unique index | TS strict-null | Zod schema rule | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | middleware factory of one | repository wrapper passthrough} _(required for `[Must]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each category with no findings, state `No <category> findings.` so the workflow knows the check ran.

## Avoid

- Flagging Zod schemas on bodies consumed by validation middleware - that layer owns user-facing messages
- Flagging `.min(1)` / `.email()` / `.regex(...)` - those go beyond the type
- Recommending `findOneOrFail` -> `findOneBy` + null check - the `orThrow` variant is idiomatic
- Flagging a Repository wrapper before checking for multi-table queries or non-TypeORM sources
- Flagging custom errors before checking whether middleware branches on `instanceof`
- Recommending removal of `asyncHandler` / `AppError` - idiomatic for surfacing async errors
- Confusing duplication with defense in depth when multiple write paths exist (HTTP + BullMQ + cron)
