---
name: node-nestjs-overengineering-review
description: NestJS necessity review - class-validator duplicating Prisma/TypeORM/TS null, defensive DI guards, single-impl interfaces, request-scope misuse.
metadata:
  category: backend
  tags: [node, nestjs, typescript, code-review, redundancy, overengineering, necessity]
user-invocable: false
---

> Load `Use skill: stack-detect` first. Use only when the detected framework is NestJS; its `ORM` and `Database` pick the constraint vocabulary and duplicate-key code below, and surface only in the `**Engine:**` line above the categories.

## When to Use

- Reviewing a NestJS diff adding `class-validator` decorators, defensive `null` guards, service interfaces, module splits, or new abstractions
- Catching code that is correct, performant, and safe - but does not need to exist

## Rules

- Cite the constraint making the code redundant: FK, a NOT NULL column, unique index, Prisma `@unique` / non-`?` field, TS non-null type, another DTO decorator, `ValidationPipe`, or framework guarantee. A premature abstraction is redundant against a simpler construct that already does the job - name that construct.
- Intent - one predicate, shared with `node-express-overengineering-review`:
  - **`[Must]`** when the diff shows a measurable cost: an extra query per write, a wrong or masked status (a mis-mapped exception, a failure answered with a success status), a per-request allocation, or an abstraction whose every consumer is a passthrough. Common instances: manual unique-check before insert, a broad `catch` defeating the global filter, a single-impl service interface, `Scope.REQUEST` on a stateless provider, `BaseService<T>` with one child, a dead `orThrow` null check whose intended 404 answers 500.
  - **`[Recommend]`** otherwise - dead code that changes no status, a speculative config key, a stacked decorator - and whenever the constraint that makes the code redundant, or the read-site search, lies outside what you could read: state the assumed justification or the unchecked source and ask the author to confirm.
  - Partial justification exempts only the justified members: flag the unjustified ones alone.
- A construct outside the diff is in scope only when the diff adds a use of it; anchor to its declaration and name the new use.
- A redundancy with **visible** justification is not a finding. See `Avoid`.

## Patterns

### Category 1: Redundant validation vs DTO / ORM / DB

Stack: TS strict-null -> class-validator DTO -> ORM column -> DB. `ValidationPipe` enforces the DTO wherever it is bound (`app.useGlobalPipes`, an `APP_PIPE` provider, `@UsePipes`, a param pipe); `whitelist: true` additionally strips undecorated properties. Confirm the binding before calling a manual check redundant; DB is authoritative.

#### A decorator subsumed by another on the same field

TS types are erased - a field with no decorator is not validated at all. The redundancy is decorator-vs-decorator, never type-vs-decorator.

```ts
// Bad - @IsUUID() already rejects undefined, "" and non-strings
export class CreateOrderDto {
  @IsNotEmpty() @IsString() @IsUUID() customerId!: string;
}

// Good - the format decorator subsumes the presence and type checks
export class CreateOrderDto {
  @IsUUID() customerId!: string;
}
```

The subsuming format decorators include `@IsUUID()`, `@IsEmail()`, `@IsInt()`, `@IsDateString()`, `@IsEnum()` - each rejects `undefined` and `""`. Not redundant: `@IsNotEmpty()` next to `@IsString()` alone - `@IsString()` accepts `""`. Not redundant either: a decorator carrying a custom `message:` a client or test asserts on.

#### Manual presence check after a `@Body()` DTO

```ts
// Bad - ValidationPipe rejected missing/empty before this method ran
async create(@Body() dto: CreateOrderDto) {
  if (!dto.customerId) throw new BadRequestException('customerId required');
}
```

#### Manual existence or unique check before insert

`[Must]` - races and adds a SELECT per write; the constraint decides anyway.

```ts
// Bad
const existing = await this.prisma.user.findUnique({ where: { email: dto.email } });
if (existing) throw new ConflictException('email taken');
await this.prisma.user.create({ data: dto });

// Good - let the index decide; translate the driver error for the column that collided
try { return await this.prisma.user.create({ data: dto }); }
catch (e) {
  const t = e instanceof Prisma.PrismaClientKnownRequestError && e.code === 'P2002' ? e.meta?.target : undefined;
  // field names on PostgreSQL / SQLite, the index name string on MySQL
  if (Array.isArray(t) ? t.includes('email') : typeof t === 'string' && t.endsWith('_email_key')) {
    throw new ConflictException('email taken');
  }
  throw e;
}
```

TypeORM: catch `QueryFailedError` with `driverError.code === '23505'` (PostgreSQL), `'ER_DUP_ENTRY'` (MySQL), `'SQLITE_CONSTRAINT_UNIQUE'` (`better-sqlite3`), or `'SQLITE_CONSTRAINT'` plus a `UNIQUE constraint failed` message (`sqlite3`, TypeORM `type: 'sqlite'`); with `Database: unknown`, the finding names the engine it assumed. The same shape applies to a parent-exists SELECT before an insert: the FK decides - translate Prisma `P2003` (scalar `customerId: id`) or `P2025` (nested `connect`), `23503`, `ER_NO_REFERENCED_ROW_2`, or `SQLITE_CONSTRAINT_FOREIGNKEY` instead. Justified when: Prisma `relationMode = "prisma"` - there is no database FK, and the SELECT is load-bearing.

### Category 2: Defensive code for impossible states

`ValidationPipe`, TS strict-null, Guards, and `findUniqueOrThrow` provide guarantees. Re-checking them is dead code.

#### `if (!entity)` after `findUniqueOrThrow` / `findOneOrFail`

```ts
// Bad - findUniqueOrThrow throws P2025 on missing; the NotFoundException never runs
const order = await this.prisma.order.findUniqueOrThrow({ where: { id } });
if (!order) throw new NotFoundException();
```

`P2025` (TypeORM: `EntityNotFoundError`) is not an `HttpException`, so without a filter mapping it the missing row answers 500 - `[Must]`, Cost `wrong or masked status`, Redundant because `superseded by findUniqueOrThrow`. Fix: `findUnique` + `throw new NotFoundException()`; keep the `orThrow` variant only when an exception filter maps it to 404, and cite that filter.

#### Null guard on a constructor-injected provider

```ts
// Bad - DI guarantees non-null for a class provider without @Optional()
constructor(private readonly prisma: PrismaService) {
  if (!prisma) throw new Error('prisma missing');
}
```

Justified when: `@Optional()` is present, or the token is bound by a `useFactory` / `useValue` that can yield `null` or `undefined`.

#### `if (!req.user)` after `@UseGuards(JwtAuthGuard)`

```ts
// Bad - the guard halted unauthenticated requests upstream
@UseGuards(JwtAuthGuard)
async list(@Req() req: AuthenticatedRequest) {
  if (!req.user) throw new UnauthorizedException();
}
```

Justified when: the guard overrides `handleRequest` or `canActivate` to let anonymous requests through (optional auth) - read the guard class before flagging.

#### Blanket `catch (e)` defeating the global exception filter

`[Must]`, Cost `wrong or masked status`, Redundant because `superseded by the global exception filter` - the filter maps `HttpException` subclasses to typed responses. Returning a value from a handler sends a **success** status (201 for POST, 200 otherwise), so a catch that returns an error body reports every failure as success.

```ts
// Bad - every failure answers 201 { error }
try { return await this.service.fulfill(id); }
catch (e) { return { error: 'something went wrong' }; }

// Good - name the failures; let the rest reach the filter
try { return await this.service.fulfill(id); }
catch (e) {
  if (e instanceof InsufficientStockError) throw new ConflictException(e.message);
  if (e instanceof PaymentDeclinedError) throw new UnprocessableEntityException(e.message);
  throw e;
}
```

#### `try { ... } catch (e) { throw e }` no-op rethrow

Delete it (Redundant because `superseded by default propagation`). Wrap only when the wrap adds context, and with a plain `new Error('<context>', { cause: e })` (tsconfig `lib` ES2022+): Nest's default filter logs non-`HttpException` errors, while an `HttpException` wrapper is answered without logging and turns a service's 404/409 into 500.

### Category 3: Premature abstraction

#### Single-implementation service interface

`[Must]`, Cost `abstraction whose every consumer is a passthrough` - every consumer passes through a token to reach the one class; every refactor touches two files. Nest mocks classes via `Test.createTestingModule(...).overrideProvider(...)`.

```ts
// Bad
export interface OrderService { fulfill(id: string): Promise<OrderResponse>; }
@Injectable() export class OrderServiceImpl implements OrderService { /* ... */ }
@Module({ providers: [{ provide: 'OrderService', useClass: OrderServiceImpl }], exports: ['OrderService'] })
export class OrdersModule {}

// Good - inject the class directly
@Injectable() export class OrderService { /* ... */ }
@Module({ providers: [OrderService], exports: [OrderService] })
export class OrdersModule {}
```

Justified when: a second implementer exists, or a `useFactory` / `useClass` binding selects among implementations at runtime. A token bound to exactly one class is indirection, not substitution.

#### `BaseService<T>` / `BaseRepository<T>` for one or two children

One child: `[Must]` (the base is a passthrough). Two children: `[Recommend]`. Inline until 3+ services share genuine cross-cutting behavior.

#### `Scope.REQUEST` on a stateless provider

`[Must]`, Cost `per-request allocation` - allocates per request and propagates the scope to every transitive injector.

```ts
// Bad - no per-request state
@Injectable({ scope: Scope.REQUEST })
export class OrderService { /* stateless */ }

// Good - default singleton
@Injectable() export class OrderService { /* ... */ }
```

Check the provider's dependencies first: a provider that injects `REQUEST` or any request-scoped provider stays request-scoped after the explicit scope is deleted, so the finding belongs to that dependency. Justified when: per-request state (multi-tenant context, per-request transaction).

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

#### `@Injectable()` mapper with no injected dependencies

The target is the DI wrapper, not the mapping. A class with an empty constructor that only reshapes its argument is a function; keep it a class once it injects anything (a config, a formatter, a repository).

```ts
// Bad - injectable with no dependencies, field-for-field copy
@Injectable() export class OrderMapper { toResponse(o: Order): OrderResponseDto { /* trivial */ } }

// Good - plain function
const toResponse = (o: Order): OrderResponseDto => ({ id: o.id, total: o.total });
```

#### Speculative config keys and unused providers

Flag config keys declared in the Zod/Joi schema with zero read sites, and providers registered in a module that nothing injects - unless Nest discovers them without injection (`@Cron` / `@Interval`, `@OnEvent`, `@Processor`, `@Resolver`, `@WebSocketGateway`, an `APP_GUARD` / `APP_PIPE` / `APP_FILTER` / `APP_INTERCEPTOR` token, or work in `onModuleInit` / `onApplicationBootstrap`). Grep the name across `ConfigService.get` / `getOrThrow`, `registerAs` factories and their `ConfigType` property access, and direct environment reads. A Joi `.required()` key nothing reads still fails boot wherever it is missing - say so. When the grep cannot run (a restricted read set, a diff with no repo), the finding is `[Recommend]` and says the read sites were not searched - the same holds for "only implementer" and "only child" claims, and for a `ValidationPipe` binding you could not read.

## Output Format

Findings contribute to the consuming workflow's unified output. One block per redundant construct: repeated occurrences of the same construct in one class are one block listing every site in `Code:`; two adjacent constructs are one block each; a construct matching two patterns is one block under the pattern with the higher intent; a construct spanning files (interface + module binding) anchors to its declaration and names the other files in `Code:` as `(also <file:line>)`. When the diff carries no line numbers, anchor as `file:<enclosing class, method, or export>`; pasted code with no file name anchors as `pasted:<construct>`.

```
### [Must | Recommend] file:line

- Category: {Redundant Validation | Defensive Impossibility | Premature Abstraction}

- Code: {one-line citation, e.g., `@IsNotEmpty()` stacked on `@IsUUID()` on `customerId`}

- Redundant because: {FK name | unique index <name> (`@unique`, `@@unique`, `@Column({ unique })`, `@Index({ unique })`) | NOT NULL column (incl. a Prisma non-`?` field) | TS strict-null | another decorator on the field | `ValidationPipe` binding | framework guarantee | zero read sites | superseded by <the simpler construct that already does this>}

- Cost: {extra query per write | wrong or masked status | per-request allocation | abstraction whose every consumer is a passthrough} {only for [Must]}

- Recommendation: {concrete edit}

- Justified when: {the legitimate reason that might apply} {only when one might}
```

The output opens with `**Engine:** {ORM} / {Database}` (`unknown` when undetected), then one `##` heading per category, in the order Redundant Validation, Defensive Impossibility, Premature Abstraction. Within a category: `[Must]` blocks, then `[Recommend]` blocks, then one `Cleared:` line listing every construct examined and not flagged with its reason. A category with no findings is `No <category> findings.` followed by its `Cleared:` line - silence is indistinguishable from a skipped check. After the last category, one `Out of scope:` line names defects seen in passing that are not redundancy (an N+1, `Float` money, a wrong return type), or `none`.

When stack-detect's `Framework` is not NestJS, the whole output is one line and nothing else: `Framework: Express - run node-express-overengineering-review` for Express, `Framework: <name> - not a NestJS project; no review` for anything else.

## Avoid

- Flagging a format decorator (`@IsUUID()`, `@Min()`, `@Length()`) as redundant against the TS type - only a decorator subsumed by another decorator is a finding
- Flagging `@Optional()` providers, `Scope.REQUEST` on per-request state, or interfaces with a second implementer or a runtime-selecting binding
- Recommending removal of `cause:` chain wrapping - it keeps the inner error for a logger that serializes `cause` (pino's `err` serializer); `Error.stack` alone does not include it
- Confusing "duplicated" with "defense in depth" when multiple write paths exist (HTTP + BullMQ + cron)
