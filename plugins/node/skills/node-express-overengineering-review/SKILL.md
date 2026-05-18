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

- Reviewing an Express diff that adds Zod / class-validator schemas, defensive `null` guards, middleware factories, custom error classes, or new abstractions
- Catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Every finding cites the constraint making the code redundant: FK name, `@Column({ nullable: false })`, unique index, TypeORM non-`?` field, TS non-null type, Zod schema rule, validation middleware, or framework guarantee.
- Severity:
  - **Default `[Suggestion]`.** Cite the constraint, recommend the edit.
  - **`[High]`** when a measurable cost is present. Cite the cost in the `Cost:` field. Triggers:
    - Extra SELECT in a hot path
    - Broad `catch (e)` defeating the error-handling middleware
    - Middleware factory wrapping one inline call
    - Custom error class hierarchy with no consumer `instanceof` branching
    - Repository wrapper over TypeORM `Repository<T>` with no added behavior
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. See `Avoid` for the canonical exceptions.

## Patterns

### Category 1: Redundant validation vs TypeORM / DB / TS strict-null

Validation stack: **TS strict-null type -> Zod / class-validator schema (run via validation middleware) -> TypeORM `@Column` constraint -> DB schema**. The middleware returns 400 before the route handler runs. DB is authoritative.

#### Handler re-checking a schema rule

```ts
// Bad - the schema already rejected missing/empty/non-positive values
const CreateOrderSchema = z.object({ customerId: z.string().uuid(), total: z.number().positive() });

router.post('/orders', validate(CreateOrderSchema), async (req, res) => {
  const { customerId, total } = req.body;
  if (!customerId) return res.status(400).json({ error: 'customerId required' }); // dead
  if (total <= 0)  return res.status(400).json({ error: 'total must be positive' }); // dead
});

// Good - trust the schema; type the body via z.infer
router.post('/orders', validate(CreateOrderSchema), async (req, res) => {
  const { customerId, total } = req.body as z.infer<typeof CreateOrderSchema>;
});
```

#### Schema and column disagree on nullability

```ts
// Bad - schema accepts null; DB rejects on INSERT -> user gets 500 instead of 400
const CreateOrderSchema = z.object({ customerId: z.string().uuid().nullable() });
// @Column({ type: 'uuid', nullable: false }) customerId!: string;
```

Either drop `.nullable()` or make the column nullable. Pick one.

#### Manual unique-check before `repository.save`

`[High]` - races and adds a SELECT per write; the unique index decides anyway.

```ts
// Bad
const existing = await userRepo.findOneBy({ email: dto.email });
if (existing) return res.status(409).json({ error: 'email taken' });
await userRepo.save({ email: dto.email });

// Good - let the unique constraint raise; translate at the error middleware
try { return await userRepo.save({ email: dto.email }); }
catch (e) {
  if (e instanceof QueryFailedError && (e.driverError as any).code === '23505') {
    return res.status(409).json({ error: 'email taken' });
  }
  throw e;
}
```

### Category 2: Defensive code for impossible states

TS strict-null, validated request bodies, and `findOneOrFail` provide overlapping guarantees. Re-checking them is dead code.

#### `if (entity === null)` after `findOneOrFail`

```ts
// Bad - findOneOrFail throws EntityNotFoundError on missing
const order = await orderRepo.findOneOrFail({ where: { id } });
if (!order) return res.status(404).json({ error: 'not found' });
```

Pick one: use `findOneOrFail` and let it raise to the error middleware, or use `findOneBy` and handle the null branch.

#### Defensive checks on typed values

```ts
// Bad - status is `'pending' | 'confirmed' | 'shipped'`; always truthy
if (order.status) process(order.status);

// Bad - count is number; count=0 is falsy but valid
if (order.itemCount) process(order.itemCount);

// Bad - `as unknown as Order` bypasses TS, hiding real bugs
const order = result as unknown as Order;

// Good - explicit nullability checks for nullable values; trust the type otherwise
process(order.status);
if (order.itemCount > 0) process(order.itemCount);
```

`as` is legitimate at genuinely-untyped boundaries (third-party libs returning `unknown`, framework escape hatches with documented invariants). Flag when both sides are typed.

#### Blanket `catch (e)` defeating error-handling middleware

`[High]`. Express's terminal error middleware maps thrown errors to typed responses; a handler-level `try/catch` that converts everything to a generic 500 erases that mapping.

```ts
// Bad
router.post('/orders/:id/fulfill', async (req, res) => {
  try { res.json(await service.fulfill(req.params.id)); }
  catch (e) { res.status(500).json({ error: 'failed' }); }
});

// Good - name the failures; let the rest reach the error middleware
router.post('/orders/:id/fulfill', asyncHandler(async (req, res) => {
  try { res.json(await service.fulfill(req.params.id)); }
  catch (e) {
    if (e instanceof InsufficientStockError) throw new HttpError(409, e.message);
    if (e instanceof PaymentDeclinedError)   throw new HttpError(402, e.message);
    throw e;
  }
}));
```

Mapping branches followed by `throw e` is **not** the no-op rethrow - the no-op case is catch-then-immediately-rethrow with no branching.

#### `try { ... } catch (e) { throw e }` no-op rethrow

Delete it. Wrap with `throw new Error('wrap', { cause: e })` only when the wrapping adds context.

### Category 3: Premature abstraction

#### Middleware factory wrapping a one-line operation

`[High]` when the factory takes no parameters.

```ts
// Bad - no-arg factory returns a one-line middleware
export const requireAdmin = () => (req, res, next) => {
  if (req.user?.role !== 'admin') return res.status(403).json({ error: 'forbidden' });
  next();
};
router.delete('/orders/:id', requireAdmin(), deleteOrder);

// Good - export the middleware itself
export const requireAdmin = (req, res, next) => {
  if (req.user?.role !== 'admin') return res.status(403).json({ error: 'forbidden' });
  next();
};
router.delete('/orders/:id', requireAdmin, deleteOrder);
```

Justified when: the factory accepts parameters that vary across mount points (`requireRole('admin')`, `rateLimit({ window: '1m' })`).

#### Repository pattern on top of TypeORM

`[High]` when the wrapper adds no behavior beyond passthroughs. TypeORM's `Repository<T>` is already the repository.

```ts
// Bad
export class OrderRepository {
  constructor(private readonly typeOrmRepo: Repository<Order>) {}
  findById(id: string) { return this.typeOrmRepo.findOneBy({ id }); }
  save(order: Order)   { return this.typeOrmRepo.save(order); }
}

// Good - inject TypeORM's Repository directly
const orderRepo = AppDataSource.getRepository(Order);
```

Justified when: encapsulates multi-table joins, swaps a non-TypeORM source-of-truth, or provides a test seam `Repository<T>` cannot satisfy.

#### Custom error hierarchy with no consumer branching

```ts
// Bad - DomainError -> NotFoundError -> OrderNotFoundError; middleware doesn't branch on subclass
class OrderNotFoundError extends NotFoundError { /* ... */ }
throw new OrderNotFoundError(orderId);
if (err instanceof DomainError) res.status(500).json({ error: err.message });  // no branching

// Good - one HttpError with a status code
throw new HttpError(404, `order ${orderId} not found`);
```

Justified when: the error middleware or callers branch on `instanceof` to produce different status codes / payloads.

#### Custom `Result<T, E>` where exceptions or `T | null` suffice

```ts
// Bad
async function findOrder(id: string): Promise<{ ok: true; order: Order } | { ok: false; error: 'not_found' }> { /* ... */ }

// Good - the type system already encodes absence
async function findOrder(id: string): Promise<Order | null> { return orderRepo.findOneBy({ id }); }
```

Keep `Result<T, E>` only when callers branch on multiple distinct failure modes carrying data beyond a literal.

#### Service class wrapping a single repository call

```ts
// Bad
export class OrderService {
  constructor(private readonly repo: Repository<Order>) {}
  async findById(id: string) { return this.repo.findOneBy({ id }); }
}

// Good - module-level function, or call the repository directly from the handler
export const findOrderById = (id: string) => AppDataSource.getRepository(Order).findOneBy({ id });
```

Justified when: multi-step orchestration, cross-entity writes, or external I/O.

#### Speculative config keys

Flag schema-validated config keys with zero read sites. Confirm with a repo-wide grep before flagging.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Suggestion | High | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `if (!order)` after `findOneOrFail`}
- Redundant because: {FK name | TypeORM `nullable: false` | unique index | TS strict-null | Zod schema rule | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | middleware factory of one | repository wrapper passthrough} _(required for `[High]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging Zod schemas on request bodies consumed by validation middleware - that layer owns user-facing error messages
- Flagging `.min(1)` / `.email()` / `.regex(...)` constraints - those go beyond the type
- Recommending removal of `findOneOrFail` in favor of `findOneBy` + manual null check - the `orThrow` variant is the idiomatic way to let the error middleware handle 404
- Flagging a Repository wrapper before checking whether it encapsulates multi-table queries or a non-TypeORM source-of-truth
- Flagging custom error hierarchies before checking whether the error middleware branches on `instanceof`
- Recommending removal of `asyncHandler` / `HttpError` pairs - that's the idiomatic way to surface async errors to Express's error middleware
- Confusing "duplicated" with "defense in depth" when multiple write paths exist (HTTP + BullMQ consumer + cron)
