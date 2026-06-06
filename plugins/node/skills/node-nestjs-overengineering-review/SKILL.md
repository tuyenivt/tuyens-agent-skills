---
name: node-nestjs-overengineering-review
description: NestJS necessity review - class-validator duplicating Prisma/TypeORM/TS null, defensive DI guards, single-impl interfaces, request-scope misuse.
metadata:
  category: backend
  tags: [node, nestjs, typescript, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first to determine the project stack. Use only when the detected framework is NestJS. For Express, use `node-express-overengineering-review`.

## When to Use

- Reviewing a NestJS diff adding `class-validator` decorators, defensive `null` guards, service interfaces, module splits, or new abstractions
- Catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Cite the constraint making the code redundant: FK, `@Column({ nullable: false })`, unique index, Prisma `@unique` / non-`?` field, TS non-null type, DTO decorator, `ValidationPipe` whitelist, or framework guarantee.
- Intent:
  - **`[Recommend]`** default. Cite the constraint, recommend the edit. Escalate to **`[Must]`** when a measurable cost is present (filled in `Cost:`): extra SELECT in a hot path, broad `catch (e)` defeating the global filter, single-impl service interface, `Scope.REQUEST` on a stateless provider.
  - **`[Question]`** when justification is plausible but not visible in the diff.
- A redundancy with **visible** justification is not a finding. See `Avoid`.

## Patterns

### Category 1: Redundant validation vs Prisma/TypeORM / DB / TS strict-null

Stack: TS strict-null -> class-validator DTO -> ORM column -> DB. `ValidationPipe({ whitelist: true })` enforces the DTO at the controller boundary; DB is authoritative.

#### `@IsNotEmpty()` / `@IsString()` on a non-optional string field

```ts
// Bad - type + ValidationPipe already reject missing/undefined
export class CreateOrderDto {
  @IsNotEmpty() @IsUUID() customerId!: string;
}

// Good - keep only constraints that go beyond the type
export class CreateOrderDto {
  @IsUUID() customerId!: string;
}
```

#### Manual presence check after a `@Body()` DTO

```ts
// Bad - ValidationPipe rejected missing/empty before this method ran
async create(@Body() dto: CreateOrderDto) {
  if (!dto.customerId) throw new BadRequestException('customerId required');
}
```

#### Manual unique-check before insert

`[Must]` - races and adds a SELECT per write; the unique index decides anyway.

```ts
// Bad
const existing = await this.prisma.user.findUnique({ where: { email: dto.email } });
if (existing) throw new ConflictException('email taken');
await this.prisma.user.create({ data: dto });

// Good - let the index decide; translate the driver error
try { return await this.prisma.user.create({ data: dto }); }
catch (e) {
  if (e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2002') {
    throw new ConflictException('email taken');
  }
  throw e;
}
```

TypeORM: catch `QueryFailedError` with `driverError.code === '23505'` (Postgres) or `'ER_DUP_ENTRY'` (MySQL).

### Category 2: Defensive code for impossible states

`ValidationPipe`, TS strict-null, Guards, and `findUniqueOrThrow` provide guarantees. Re-checking them is dead code.

#### `if (!entity)` after `findUniqueOrThrow` / `findOneOrFail`

```ts
// Bad - findUniqueOrThrow throws P2025 on missing
const order = await this.prisma.order.findUniqueOrThrow({ where: { id } });
if (!order) throw new NotFoundException();
```

Pick one: the `orThrow` variant, or `findUnique` with null-handling.

#### Null guard on a constructor-injected provider

```ts
// Bad - DI guarantees non-null without @Optional()
constructor(private readonly prisma: PrismaService) {
  if (!prisma) throw new Error('prisma missing');
}
```

Justified when: `@Optional()` is present.

#### `if (!req.user)` after `@UseGuards(JwtAuthGuard)`

```ts
// Bad - the guard halted unauthenticated requests upstream
@UseGuards(JwtAuthGuard)
async list(@Req() req: AuthenticatedRequest) {
  if (!req.user) throw new UnauthorizedException();
}
```

#### Blanket `catch (e)` defeating the global exception filter

`[Must]` - the default filter maps `HttpException` subclasses to typed responses; converting everything to generic 500 erases that mapping.

```ts
// Bad
try { return await this.service.fulfill(id); }
catch (e) { return { error: 'something went wrong' }; }

// Good - name the failures; let the rest reach the filter
try { return await this.service.fulfill(id); }
catch (e) {
  if (e instanceof InsufficientStockError) throw new ConflictException(e.message);
  if (e instanceof PaymentDeclinedError) throw new PaymentRequiredException(e.message);
  throw e;
}
```

#### `try { ... } catch (e) { throw e }` no-op rethrow

Delete it. Wrap only when `throw new Error('...', { cause: e })` adds context.

### Category 3: Premature abstraction

#### Single-implementation service interface

`[Must]` - every refactor touches two files for no behavioral reason. Nest mocks classes via `Test.createTestingModule(...).overrideProvider(...)`.

```ts
// Bad
export interface OrderService { fulfill(id: string): Promise<OrderResponse>; }
@Injectable() export class OrderServiceImpl implements OrderService { /* ... */ }
@Module({ providers: [{ provide: 'OrderService', useClass: OrderServiceImpl }],
  exports: ['OrderService'] })

// Good - inject the class directly
@Injectable() export class OrderService { /* ... */ }
@Module({ providers: [OrderService], exports: [OrderService] })
```

Justified when: a second implementer exists, or the module uses `useClass` / `useFactory` substitution beyond test overrides.

#### `BaseService<T>` / `BaseRepository<T>` for one or two children

Inline until 3+ services share genuine cross-cutting behavior.

#### `Scope.REQUEST` on a stateless provider

`[Must]` - allocates per request and propagates the scope to every transitive injector.

```ts
// Bad - no per-request state
@Injectable({ scope: Scope.REQUEST })
export class OrderService { /* stateless */ }

// Good - default singleton
@Injectable() export class OrderService { /* ... */ }
```

Justified when: per-request state (multi-tenant context, per-request transaction).

#### Custom `Result<T, E>` where exceptions or `T | null` suffice

```ts
// Bad
async findOrder(id: string): Promise<Result<Order, 'not_found'>> { /* ... */ }

// Good - absence is already in the type system
async findOrder(id: string): Promise<Order | null> {
  return this.prisma.order.findUnique({ where: { id } });
}
```

Justified when: callers branch on multiple distinct failure modes carrying data beyond a literal.

#### AutoMapper-style mapper between identical shapes

```ts
// Bad - mapper class for a 1:1 transformation
@Injectable() export class OrderMapper { toResponse(o: Order): OrderResponseDto { /* trivial */ } }

// Good - plain function
const toResponse = (o: Order): OrderResponseDto => ({ id: o.id, total: o.total });
```

#### Speculative `ConfigService` keys

Flag config keys declared in the Zod/Joi schema but never read via `ConfigService.get(...)`. Confirm zero read sites by repo-wide grep before flagging.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per finding:

```
### [Must | Recommend | Question] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}
- Code: {one-line citation, e.g., `@IsNotEmpty()` on non-optional `customerId: string`}
- Redundant because: {FK name | Prisma `@unique` | TypeORM `nullable: false` | TS strict-null | class-validator on DTO | framework guarantee}
- Cost: {extra SELECT per save | masked exception | speculative surface area | request-scope on stateless provider} _(required for `[Must]`; omit otherwise)_
- Recommendation: {concrete edit}
- Justified when: {one-line note if a legitimate reason might apply; otherwise omit}
```

For each of the three categories with no findings, state `No <category> findings.` so the consuming workflow knows the check ran.

## Avoid

- Flagging `@IsString()` / `@IsUUID()` / `@Min()` / `@Length()` - those go beyond the type
- Flagging class-validator decorators that own user-facing 400 error messages
- Flagging `@Optional()` providers, `Scope.REQUEST` on per-request state, or single-impl interfaces tied to `useClass` / `useFactory` substitution
- Recommending removal of `cause:` chain wrapping - that preserves the stack
- Confusing "duplicated" with "defense in depth" when multiple write paths exist (HTTP + BullMQ + cron)
