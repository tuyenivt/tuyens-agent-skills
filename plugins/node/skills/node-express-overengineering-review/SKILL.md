---
name: node-express-overengineering-review
description: Express necessity review - Zod/TypeORM/DB duplication, defensive null on typed values, middleware-of-one, Repository wrappers, custom errors.
metadata:
  category: backend
  tags: [node, express, typescript, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Use only when the detected framework is Express; its `ORM` and `Database` pick the constraint vocabulary and duplicate-key code below, and surface only in the `**Engine:**` line above the categories. Read the Express major from `package.json` (else the instruction file's `## Tech Stack`): it decides whether an async wrapper is redundant.

## When to Use

Reviewing Express diffs that add Zod / class-validator schemas, null guards, middleware factories, custom errors, or new abstractions that are correct but do not need to exist.

## Rules

- Cite the constraint making the code redundant: FK, a NOT NULL column (`@Column()` without `nullable: true`, a Prisma non-`?` field), unique index, TS non-null type, Zod rule, validation middleware, or framework guarantee. A premature abstraction is redundant against a simpler construct that already does the job - name that construct.
- Intent - one predicate, shared with `node-nestjs-overengineering-review`:
  - **`[Must]`** when the diff shows a measurable cost: an extra query per write, a wrong or masked status (a mis-mapped exception, a failure answered with a success status), a per-request allocation, or an abstraction whose every consumer is a passthrough. Common instances: manual unique-check before `save`, blanket `catch` answering 500 or 2xx, unbranched custom error hierarchy, Repository wrapper of passthroughs, a no-arg middleware factory every mount point calls only to get the middleware, schema/column nullability mismatch (turns a 400 into a 500).
  - **`[Recommend]`** otherwise - dead code that changes no status, a speculative config key, a redundant schema rule - and whenever the constraint that makes the code redundant, or the read-site search, lies outside what you could read: state the assumed justification or the unchecked source and ask the author to confirm.
  - Partial justification exempts only the justified members: if `requireRole(role)` is justified and `requireAdmin()` is not, flag `requireAdmin()` alone.
- A construct outside the diff is in scope only when the diff adds a use of it; anchor to its declaration and name the new use.
- Redundancy with **visible** justification is not a finding. See `Avoid`.

## Patterns

### Category 1: Redundant validation vs Zod / DB / TS strict-null

Stack: TS strict-null -> Zod / class-validator (via middleware, 400 before handler) -> ORM column -> DB (authoritative).

#### Handler re-checking a schema rule

```ts
const CreateOrderSchema = z.object({ customerId: z.string().uuid(), total: z.number().positive() });

// Bad - the schema already rejected these (dead only because .uuid() rejects "" and .positive() rejects <= 0)
router.post('/orders', validate(CreateOrderSchema), async (req, res) => {
  if (!req.body.customerId) return res.status(400).json(...);
  if (req.body.total <= 0)  return res.status(400).json(...);
});
// Good - type via z.infer and trust the schema (sound when `validate` writes the parsed output back)
const body = req.body as z.infer<typeof CreateOrderSchema>;
```

#### Schema and column disagree on nullability

```ts
// Bad - schema accepts null; DB rejects on INSERT -> 500 instead of 400
z.object({ customerId: z.string().uuid().nullable() });
// @Column() customerId!: string;      (NOT NULL: no nullable: true)
```

Drop `.nullable()` or make the column nullable. Pick one.

#### Manual unique-check before save

`[Must]` - races and adds a SELECT per write; the unique index decides anyway.

```ts
// Bad
if (await userRepo.findOneBy({ email })) return res.status(409).json(...);
await userRepo.save({ email });

// Good - let the constraint raise, translate at the call site, rethrow the rest
try {
  const user = await userRepo.save({ email });
  return res.status(201).json(user);
} catch (e) {
  const code = e instanceof QueryFailedError ? (e.driverError as { code?: string }).code : undefined;
  // PostgreSQL | MySQL | better-sqlite3 (sqlite3 reports SQLITE_CONSTRAINT + 'UNIQUE constraint failed')
  if (code === '23505' || code === 'ER_DUP_ENTRY' || code === 'SQLITE_CONSTRAINT_UNIQUE') return res.status(409).json({ error: 'email taken' });
  throw e;                              // bare Express 4 async handler: return next(e) instead
}
```

Prisma: `findUnique` + 409 before `create` is the same finding; translate `P2002` instead. With `Database: unknown`, the finding names the engine it assumed.

### Category 2: Defensive code for impossible states

#### Null check after an `OrFail` / `OrThrow` lookup

```ts
// Bad - findOneOrFail throws EntityNotFoundError on missing; the 404 below never runs
const order = await orderRepo.findOneOrFail({ where: { id } });
if (!order) return res.status(404).json(...);
```

The unreachable 404 shows the intent: a missing row now answers 500 on Express 5 or an async-wrapped route - `EntityNotFoundError` (Prisma `findUniqueOrThrow`: `P2025`) reaches the error middleware unmapped - and crashes or hangs on a bare Express 4 async handler. `[Must]`, Cost `wrong or masked status`, Redundant because `superseded by findOneOrFail`. Fix: `findOneBy` + the null check, or keep `findOneOrFail` and map `EntityNotFoundError` to 404 in the error middleware (confirm it does). A dead check whose intended status is already produced is `[Recommend]`.

#### Defensive checks on typed values

```ts
if (order.status) process(...);        // Bad - string-literal union with no '' member: always truthy
const o = result as unknown as Order;  // Bad - bypasses TS when both sides are typed
```

`as` is legitimate at untyped boundaries (third-party `unknown`, framework escapes). A truthiness guard on a numeric enum or a count (`if (order.itemCount)`) is not redundant - `0` is falsy, so it silently skips a valid value; report it in the `Out of scope:` line.

#### Blanket `catch (e)` defeating error-handling middleware

`[Must]`, Cost `wrong or masked status`, Redundant because `superseded by the terminal error middleware`. The middleware maps thrown errors to typed responses; handler-level `try/catch -> 500` (or `-> 200 { error }`) erases that mapping.

```ts
// Bad
catch (e) { res.status(500).json({ error: 'failed' }); }

// Good - name the failures; forward the rest
catch (e) {
  if (e instanceof InsufficientStockError) return next(new AppError(409, e.message));
  if (e instanceof PaymentDeclinedError)   return next(new AppError(402, e.message));
  return next(e);
}
```

On Express 5 (or an async-wrapped route on 4) `throw` works as well as `next(err)`; on a bare Express 4 async handler the rejection is unhandled - on Node 15+ the process crashes (`--unhandled-rejections=throw`), or the request hangs when an `unhandledRejection` listener swallows it. Mapping branches followed by forwarding the rest is not the no-op rethrow.

#### `try { ... } catch (e) { throw e }` no-op rethrow

Delete it (Redundant because `superseded by default propagation`). Wrap with `throw new Error('wrap', { cause: e })` (needs tsconfig `lib` ES2022+) only when the wrap adds context.

### Category 3: Premature abstraction

#### Middleware factory wrapping a one-line operation

`[Must]` when the factory takes no parameters - Cost `abstraction whose every consumer is a passthrough`: every mount point calls it only to get the middleware. A factory called **inside** the handler on every request is Cost `per-request allocation` - `(req, res, next) => rateLimit({ windowMs: 60_000, limit: 5 })(req, res, next)` also builds a fresh limiter store per request, so it never limits.

```ts
// Bad - no-arg factory
export const requireAdmin = (): RequestHandler => (req, res, next) => {...};
router.delete('/x', requireAdmin(), handler);

// Good - export the middleware itself
export const requireAdmin: RequestHandler = (req, res, next) => {...};
router.delete('/x', requireAdmin, handler);
```

Justified when parameters vary across mount points (`requireRole('admin')`, `rateLimit({ windowMs: 60_000, limit: 100 })`).

#### Repository wrapper over the ORM

`[Must]` when the wrapper only passes through. `Repository<T>` (or the Prisma delegate) is already the repository.

```ts
// Bad - passthroughs over Repository<Order>
class OrderRepository {
  constructor(private readonly repo: Repository<Order>) {}
  findById(id: string) { return this.repo.findOneBy({ id }); }
}
// Good
const orderRepo = AppDataSource.getRepository(Order);
```

Justified when it encapsulates multi-table joins, swaps a non-ORM source, or provides a test seam the ORM cannot satisfy.

#### Custom error hierarchy with no consumer branching

`[Must]` when nothing branches on the subclasses - Cost `abstraction whose every consumer is a passthrough`.

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

`[Must]` when every method is a single-call passthrough - the same Cost as the Repository wrapper; a service stacked on a Repository wrapper is two findings.

```ts
// Bad
class AccountService {
  constructor(private readonly repo = new AccountRepository()) {}
  getAccount(id: string) { return this.repo.findById(id); }
}
// Good - call the repository at the use site
const account = await accountRepo.findOneBy({ id });
```

Justified for multi-step orchestration, cross-entity writes, or external I/O.

#### Async wrapper on Express 5

On Express 5 a hand-rolled `asyncHandler` is redundant - Express forwards rejected promises natively (`[Recommend]`, Redundant because `framework guarantee`). `express-async-errors` on Express 5 is not redundant but broken - it requires `express/lib/router/layer`, which 5 removed, so boot fails; put it on the `Out of scope:` line. On Express 4 either one is load-bearing; never flag it there.

#### Speculative config keys and unused members

Flag schema-validated config keys, request-schema fields, and injected fields with zero read sites (Category 3). Confirm with a repo-wide grep of the key or field name; when the grep cannot run (a restricted read set, a diff with no repo), the finding is `[Recommend]` and says the read sites were not searched.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per redundant construct: repeated occurrences of the same construct in one file are one block listing every site in `Code:`; two adjacent constructs (a wrapper and the service wrapping it) are one block each, and the same pattern in two files is two blocks; a construct matching two patterns is one block under the pattern with the higher intent; a construct spanning files anchors to its declaration and names the other files in `Code:` as `(also <file:line>)`. When the diff carries no line numbers, anchor as `file:<enclosing function or export>`; pasted code with no file name anchors as `pasted:<construct>`.

```
### [Must | Recommend] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}

- Code: {one-line citation, e.g., `if (!order)` after `findOneOrFail`}

- Redundant because: {FK name | NOT NULL column | unique index | TS strict-null | schema rule (Zod / class-validator) | validation middleware | framework guarantee | zero read sites | superseded by <the simpler construct that already does this>}

- Cost: {extra query per write | wrong or masked status | per-request allocation | abstraction whose every consumer is a passthrough} {only for [Must]}

- Recommendation: {concrete edit}

- Justified when: {the legitimate reason that might apply} {only when one might}
```

The output opens with `**Engine:** {ORM} / {Database}` (`unknown` when undetected), then one `##` heading per category, in the order Redundant Validation, Defensive Impossibility, Premature Abstraction. Within a category: `[Must]` blocks, then `[Recommend]` blocks, then one `Cleared:` line listing every construct examined and not flagged with its reason. A category with no findings is `No <category> findings.` followed by its `Cleared:` line - silence is indistinguishable from a skipped check. After the last category, one `Out of scope:` line names defects seen in passing that are not redundancy (a falsy-zero guard, a query bug, mass assignment), each as `<file:line> <defect>` separated by `; `, or `none`.

When stack-detect's `Framework` is not Express (a NestJS project also lists `express` - `@nestjs/core` decides), the whole output is one line and nothing else: `Framework: NestJS - run node-nestjs-overengineering-review` for NestJS, `Framework: <name> - not an Express project; no review` for anything else.

## Avoid

- Flagging Zod schemas on bodies consumed by validation middleware - that layer owns user-facing messages
- Flagging `.min(1)` / `.email()` / `.regex(...)` - those go beyond the type
- Flagging a Repository wrapper before checking for multi-table queries or non-ORM sources
- Flagging custom errors before checking whether middleware branches on `instanceof`
- Flagging an async wrapper on Express 4 - there it is what surfaces async errors
- Confusing duplication with defense in depth when multiple write paths exist (HTTP + BullMQ + cron)
