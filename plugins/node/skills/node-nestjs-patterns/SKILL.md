---
name: node-nestjs-patterns
description: NestJS patterns: modules, DI scopes, controllers, guards, interceptors, pipes, exception filters, class-validator, circular deps, webhooks.
metadata:
  category: backend
  tags: [node, typescript, nestjs, di, validation, patterns]
user-invocable: false
---

# NestJS Patterns

> Load `Use skill: stack-detect` first. Read the HTTP adapter from `@nestjs/platform-express` / `@nestjs/platform-fastify` in `package.json` (stack-detect does not carry it; unread, it is `unknown - package.json not read`). The examples below are Express-adapter; the adapter and the ORM surface only in the block's `**Stack:**` line.

## When to Use

- Building or reviewing NestJS modules, DI, controllers, guards, validation
- Webhook endpoints needing raw body + signature validation
- Diagnosing Nest DI errors, scope propagation, and bootstrap wiring

## Rules

- One module per bounded context; explicit imports/exports
- `@Injectable()` on every service/repository/guard/interceptor; prefer constructor injection
- Controllers orchestrate; services execute business logic. A handler that catches an error and **returns** a body answers with a success status (201 for POST) - let errors reach the filter
- Return DTOs - never raw Prisma/TypeORM entities. Map with an explicit allowlist mapper (a plain function or a `static from()`), never by stripping fields off the entity - a denylist re-leaks every column added later
- `ValidationPipe({ whitelist: true, transform: true })` globally; never `any` in DTOs. A global pipe cannot be overridden per route - `@UsePipes()` on a controller **adds** a pipe. A parameter whose metatype is `Object`, `Buffer`, `String`, `Number`, `Boolean`, `Array`, or `Date` (a `Record<string, string>` or bare-object type), an untyped parameter, and a custom param decorator (unless `validateCustomDecorators: true`) are skipped, so neither validation nor `whitelist` applies
- Authentication is global and fails closed: the JWT guard is an `APP_GUARD`, and a route opts out only through a `@Public()` decorator the guard reads via `Reflector`. Route-level `@UseGuards()` adds authorization (roles) on top; it never re-adds the JWT guard
- `main.ts` - and a standalone `createApplicationContext` worker - calls `app.enableShutdownHooks()`, or no `onModuleDestroy` / `beforeApplicationShutdown` hook (pool drain, BullMQ worker close) runs on `SIGTERM`

## Patterns

### Module Architecture

Export only what other modules need; `@Global()` only for truly cross-cutting providers (`PrismaModule`). Dynamic modules for configurable providers (`BullModule.registerQueue({ name })`); custom providers (`useClass` / `useFactory` / `useValue`) for DB and external clients.

### Bootstrap

```typescript
const app = await NestFactory.create<NestExpressApplication>(AppModule, { rawBody: true });
app.useBodyParser('json', { limit: '5mb' });        // on NestExpressApplication only; keeps rawBody
app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
app.enableShutdownHooks();
await app.listen(port);
```

Never `app.use(express.json())` in `main.ts`: at `init()` Nest sees a JSON parser already applied and skips its own, so the raw-body `verify` hook is never installed and `req.rawBody` stays `undefined`.

### Controllers

- `@Controller('api/v1/orders')`; HTTP verb decorators with `@Param/@Query/@Body`
- POST defaults to 201, every other verb to 200. `@HttpCode(204)` on a handler that returns no body (DELETE, a PATCH whose result the client already has); `@HttpCode(200)` on a non-creating POST. A response-shaping interceptor (`map(data => ({ data }))`) still wraps a `void` return - make it pass through when the value is `undefined`

```typescript
@Controller("api/v1/orders")
export class OrderController {
  constructor(private readonly orders: OrderService) {}

  @Post()
  create(@Body() dto: CreateOrderDto): Promise<OrderResponseDto> {   // global JWT guard applies
    return this.orders.create(dto);
  }

  @Patch(":id/approve")
  @Roles("staff") @UseGuards(RolesGuard)                              // authorization on top
  approve(@Param("id") id: string): Promise<OrderResponseDto> {
    return this.orders.approve(id);
  }
}
```

### Guards: Global Auth, Public Routes, Roles

```typescript
export const IS_PUBLIC = "isPublic";
export const Public = () => SetMetadata(IS_PUBLIC, true);
export const Roles = (...roles: string[]) => SetMetadata("roles", roles);

@Injectable()
export class JwtAuthGuard extends AuthGuard("jwt") {
  constructor(private readonly reflector: Reflector) { super(); }
  canActivate(ctx: ExecutionContext) {
    const isPublic = this.reflector.getAllAndOverride<boolean>(IS_PUBLIC, [ctx.getHandler(), ctx.getClass()]);
    return isPublic ? true : super.canActivate(ctx);
  }
}

@Injectable()
export class RolesGuard implements CanActivate {
  constructor(private readonly reflector: Reflector) {}
  canActivate(ctx: ExecutionContext): boolean {
    const roles = this.reflector.getAllAndOverride<string[]>("roles", [ctx.getHandler(), ctx.getClass()]);
    if (!roles?.length) return true;
    return roles.includes(ctx.switchToHttp().getRequest().user?.role);
  }
}

// app.module.ts
providers: [{ provide: APP_GUARD, useClass: JwtAuthGuard }]
```

A `@Public()` decorator the guard never reads is dead: the route stays behind JWT. An empty `@UseGuards()` opts out of nothing.

### Validation

DTO decorators (`@IsUUID`, `@IsInt`, `@IsEmail`, `@IsEnum`); nested objects and arrays need `@ValidateNested()` **and** `@Type(() => Child)` - without `@Type` the children stay plain objects and are never validated.

### Exception Filters

The domain hierarchy, the global filter, and capture discipline are `node-exception-handling`. A catch-all `@Catch()` filter here must keep two things Nest's default does: log unknown errors (extend `BaseExceptionFilter` and call `super.catch()` for them - register it as `{ provide: APP_FILTER, useClass }`, or pass `app.get(HttpAdapterHost).httpAdapter` to its constructor; with neither, `super.catch()` throws), and keep `ValidationPipe`'s field messages - build the body from `ex.getResponse()`, not `ex.message` (an array message collapses to "Bad Request Exception").

### Webhooks

- Enable `NestFactory.create(AppModule, { rawBody: true })`; read `req.rawBody` via `RawBodyRequest<Request>`
- Authenticate by signature, not JWT: mark the route `@Public()` so the global guard skips it
- Stripe and Slack sign the raw body - verify against `req.rawBody`. Twilio signs the full public URL plus the sorted **parsed** form params - type that handler's body `Record<string, string>` so the global `whitelist` does not strip fields first. The signing schemes themselves are `node-security-patterns`

```typescript
@Public()
@Post("webhooks/stripe")
@HttpCode(200)
handle(@Req() req: RawBodyRequest<Request>, @Headers("stripe-signature") sig: string) {
  let event: Stripe.Event;
  try {
    event = this.stripe.webhooks.constructEvent(req.rawBody!, sig, this.secret);
  } catch {
    throw new BadRequestException("invalid signature");   // not a 500
  }
  return this.payments.handleWebhookEvent(event);
}
```

### DI Scopes

| Scope               | Lifetime                         | Use When                                |
| ------------------- | -------------------------------- | --------------------------------------- |
| `DEFAULT`           | App lifetime (singleton)         | Stateless services (default)            |
| `REQUEST`           | Per HTTP request                 | Request-scoped state (e.g., current user) |
| `TRANSIENT`         | Per injection point              | Stateful helpers that must not be shared |

Scope propagates upward: a singleton injecting a `REQUEST` provider becomes `REQUEST`-scoped, and so does everything that injects *it*. Three symptoms, one cause:

- a "singleton" that got slow - it is rebuilt per request
- a `@Cron` / `@Interval` on a provider that became request-scoped is silently never registered (one warning line at boot)
- a BullMQ `@Processor` becomes request-scoped per job: `@nestjs/bullmq` resolves it per job with the `Job` as `REQUEST`, so boot succeeds, but a provider reading `req.user` / `req.headers` sees the `Job` - `tenantId` is `undefined`

The fix is to stop propagating scope, not to change the scope keyword. Carry per-request state in an `AsyncLocalStorage`-backed singleton; every provider goes back to `DEFAULT`, and a cron or worker supplies the context explicitly.

```typescript
import { AsyncLocalStorage } from "node:async_hooks";

@Injectable()
export class TenantContext {
  private readonly als = new AsyncLocalStorage<{ tenantId: string }>();
  run<T>(store: { tenantId: string }, fn: () => T): T { return this.als.run(store, fn); }
  get tenantId(): string {
    const id = this.als.getStore()?.tenantId;
    if (!id) throw new Error("TenantContext used outside a request, job, or cron run");
    return id;
  }
}

// HTTP: seed AFTER the JWT guard has set req.user - an interceptor, not middleware (middleware runs before guards)
@Injectable()
export class TenantInterceptor implements NestInterceptor {
  constructor(private readonly tenant: TenantContext) {}
  intercept(ctx: ExecutionContext, next: CallHandler): Observable<unknown> {
    const tenantId = ctx.switchToHttp().getRequest().user?.tenantId;
    if (!tenantId) return next.handle();                          // public route
    // the handler runs when the Observable is subscribed - run the subscription inside the store
    return new Observable((sub) => this.tenant.run({ tenantId }, () => next.handle().subscribe(sub)));
  }
}

// Worker: the producer puts tenantId in job data; the processor re-establishes the store
async process(job: Job<{ tenantId: string; month: string }>) {
  return this.tenant.run({ tenantId: job.data.tenantId }, () => this.reports.build(job.data.month));
}
// Cron: iterate tenants and run each inside tenant.run({ tenantId }, ...)
```

A genuinely request-scoped provider needed by a cron or hand-rolled worker is resolved per run: `const contextId = ContextIdFactory.create(); this.moduleRef.registerRequestByContextId(fakeRequest, contextId); const x = await this.moduleRef.resolve(X, contextId, { strict: false });`.

### Circular Dependencies and "Can't Resolve"

Prefer extracting shared logic into a third service. `forwardRef()` is a workaround with two separate uses: a **module** cycle needs `forwardRef(() => OtherModule)` in both modules' `imports`; a **provider** cycle needs `@Inject(forwardRef(() => Other))` on both constructors.

```typescript
// provider cycle - both sides
constructor(@Inject(forwardRef(() => PaymentService)) private readonly payments: PaymentService) {}
constructor(@Inject(forwardRef(() => OrderService)) private readonly orders: OrderService) {}
```

Diagnose "Nest can't resolve dependencies of X (A, ?)" from the name in "Please make sure that the argument <Name> at index [N]" - the `?` marks the failing index in every case:

| Argument name | Cause | Fix |
|---------------|-------|-----|
| a class name | the consuming module does not import the module that exports it, or the provider is not in its own module's `providers` | add the import/export or the provider |
| `Object` | injected by interface, type alias, or `import type` - the metatype erased | inject by token: `@Inject(TOKEN)` |
| `dependency` (with a forwardRef hint) | a circular file import left the class `undefined` at decoration time | break the file cycle, or `forwardRef` both sides |

"Nest cannot create the <Module> instance ... imports array is undefined" is the module-cycle case.

## Output Format

When authoring, emit this block plus the module, controller, and provider code it describes; a build over existing code is authoring plus review - findings for the existing defects the change touches, then the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings. After the findings, emit this block as the target state: every row shows the corrected value, and a row the current code violates ends ` - GAP (was: <observed>)`; a row whose evidence was not in the read set reads `unknown - <file> not read`.

```
## NestJS Architecture

**Stack:** {express | fastify | unknown} adapter, {Prisma | TypeORM | none}

### Bootstrap
| Setting | Value |
|---------|-------|
| rawBody | |
| Body parser | |
| Global pipes | |
| Global guards (APP_GUARD) | |
| Global filters | |
| Global interceptors | |
| enableShutdownHooks (main.ts) | |
| enableShutdownHooks (each standalone worker) | |

### Module Structure
| Module | Providers | Controllers | Exports | Imports | Cycle handling |
|--------|-----------|-------------|---------|---------|----------------|

### Controller Endpoints
| Method | Route | Status | Guards | Pipe/Validation | Response DTO (mapper) |
|--------|-------|--------|--------|-----------------|-----------------------|

### DI Graph and Scopes
| Provider | Scope | Injects | Scope it propagates to |
|----------|-------|---------|------------------------|
```

## Avoid

- Business logic in controllers; returning Prisma/entity objects; `any` in DTOs
- Circular module deps without `forwardRef()` on both sides (or without refactoring out a shared service)
- Injecting `REQUEST`-scoped providers into singletons unintentionally
- JWT guards on webhook endpoints (signature-based auth, `@Public()`)
