---
name: node-nestjs-patterns
description: NestJS patterns: modules, DI scopes, controllers, guards, interceptors, pipes, exception filters, class-validator, circular deps, webhooks.
metadata:
  category: backend
  tags: [node, typescript, nestjs, di, validation, patterns]
user-invocable: false
---

# NestJS Patterns

> Load `Use skill: stack-detect` first. Read the HTTP adapter from `@nestjs/platform-express` / `@nestjs/platform-fastify` and BullMQ from `@nestjs/bullmq` or `bullmq` in `package.json` (stack-detect has no field for either - an `Additional` key such as `Queue: BullMQ` counts; unread, the adapter is `unknown - package.json not read` and the suffix is omitted). The examples below are Express-adapter; the adapter, the ORM, and the `, BullMQ` suffix surface only in the block's `**Stack:**` line.

## When to Use

- Building or reviewing NestJS modules, DI, controllers, guards, validation
- Webhook endpoints needing raw body + signature validation
- Diagnosing Nest DI errors, scope propagation, and bootstrap wiring

## Rules

- One module per bounded context; explicit imports/exports
- `@Injectable()` on every service/repository/guard/interceptor; prefer constructor injection
- Controllers orchestrate; services execute business logic. A handler that catches an error and **returns** a body answers with a success status (201 for POST) - let errors reach the filter
- Return DTOs - never raw Prisma/TypeORM entities. Map with an explicit allowlist mapper (a plain function or a `static from()`), never by stripping fields off the entity - a denylist re-leaks every column added later
- `ValidationPipe({ whitelist: true, transform: true })` globally; never `any` in DTOs. A global pipe is not overridden per route - `@UsePipes()` **adds** a pipe. A parameter whose metatype is `Object` / `Buffer` / `String` / `Number` / `Boolean` / `Array` / `Date` (a `Record<string, string>` or bare-object type), an untyped parameter, and a custom param decorator (unless `validateCustomDecorators: true`) are skipped - neither validation nor `whitelist` applies
- Authentication is global and fails closed: the JWT guard is an `APP_GUARD`, and a route opts out only through a `@Public()` decorator the guard reads via `Reflector`. Route-level `@UseGuards()` adds authorization (roles) on top; it never re-adds the JWT guard
- `main.ts` - and a standalone `createApplicationContext` worker - calls `app.enableShutdownHooks()`, or no `onModuleDestroy` / `beforeApplicationShutdown` / `onApplicationShutdown` hook (pool drain, BullMQ worker close) runs on `SIGTERM`

## Patterns

### Module Architecture

Export only what other modules need; `@Global()` only for truly cross-cutting providers (`PrismaModule`). A provider another module needs is exported by its owner and reached through `imports` - never listed in both modules' `providers`, which builds two instances (two caches, two pools); the same holds for `BullModule.registerQueue({ name })`, registered once and imported. Dynamic modules for configurable providers; custom providers (`useClass` / `useFactory` / `useValue`) for DB and external clients.

### Bootstrap

```typescript
const app = await NestFactory.create<NestExpressApplication>(AppModule, { rawBody: true });
app.useBodyParser('json', { limit: '5mb' });        // on NestExpressApplication only; keeps rawBody
app.useGlobalPipes(new ValidationPipe({ whitelist: true, transform: true }));
app.enableShutdownHooks();
await app.listen(port);
```

Never `app.use(express.json())` in `main.ts`: at `init()` Nest sees a JSON parser already applied and skips its own, so the raw-body `verify` hook is never installed and `req.rawBody` stays `undefined`. `app.useGlobalGuards(new X())` / `useGlobalFilters` / `useGlobalInterceptors` take instances with no constructor injection - every dependency (`app.get(Reflector)`, `app.get(HttpAdapterHost).httpAdapter`) is passed by hand - so global guards and interceptors register through the `APP_*` tokens.

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

// app.module.ts - global guard, and a global interceptor the same way (APP_INTERCEPTOR / APP_FILTER / APP_PIPE)
providers: [{ provide: APP_GUARD, useClass: JwtAuthGuard }, { provide: APP_INTERCEPTOR, useClass: TenantInterceptor }]
```

A `@Public()` decorator the guard never reads is dead: the route stays behind JWT. An empty `@UseGuards()` opts out of nothing. The moment `APP_GUARD` lands, every route without `@Public()` is behind JWT - audit webhooks and health routes before the change ships, and drop controller-level `@UseGuards(JwtAuthGuard)` (a GAP row). Type the principal once (`src/common/auth/`, beside `Public` and `Roles`) - `interface AuthenticatedRequest extends Request { user: JwtPayload }` - and read it with `@Req() req: AuthenticatedRequest` or a `@CurrentUser()` param decorator; `req.user` on the bare Express `Request` does not compile without `@types/passport` and is `Express.User | undefined` with it, and `ctx.switchToHttp().getRequest()` is `any`.

### Validation

DTO decorators (`@IsUUID`, `@IsInt`, `@IsEmail`, `@IsEnum`); nested objects and arrays need `@ValidateNested()` **and** `@Type(() => Child)` - without `@Type` the children stay plain objects and are never validated.

### Exception Filters

The domain hierarchy, the global filter, and capture discipline are `node-exception-handling`. A catch-all `@Catch()` filter keeps two things Nest's default does: log unknown errors (extend `BaseExceptionFilter` and call `super.catch()` for them - register it as `{ provide: APP_FILTER, useClass }`, or pass `app.get(HttpAdapterHost).httpAdapter` to its constructor; with neither, `super.catch()` throws), and keep `ValidationPipe`'s field messages - build the body from `ex.getResponse()`, not `ex.message` (an array message collapses to "Bad Request Exception").

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
- a `@Cron` / `@Interval` on a provider that became request-scoped is never registered - one warning line at boot, nothing at run time
- a BullMQ `@Processor` becomes request-scoped per job: `@nestjs/bullmq` resolves it per job with the `Job` as `REQUEST`, so boot succeeds, but a provider reading `req.user` / `req.headers` sees the `Job` - `tenantId` is `undefined`

The fix is to stop propagating scope, not to change the scope keyword. Carry per-request state in an `AsyncLocalStorage`-backed singleton; every provider goes back to `DEFAULT`, and a cron or worker supplies the context explicitly. A database client dragged into `REQUEST` is `node-connection-pool-sizing`'s pool finding.

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
    // next.handle() binds the async context when it is CALLED (AsyncResource.bind); the handler runs on subscribe - so call it inside the store, not just subscribe
    return new Observable((sub) => this.tenant.run({ tenantId }, () => next.handle().subscribe(sub)));
  }
}

// Worker: the producer puts tenantId in job data; the processor re-establishes the store
async process(job: Job<{ tenantId: string; month: string }>) {
  return this.tenant.run({ tenantId: job.data.tenantId }, () => this.reports.build(job.data.month));
}
// Cron: iterate tenants and run each inside tenant.run({ tenantId }, ...)
```

A `@Processor` host also needs `enableShutdownHooks()`: `@nestjs/bullmq` closes its Workers from `onApplicationShutdown`, so without it `SIGTERM` kills in-flight jobs. Scheduling (`upsertJobScheduler`, repeatables) is wiring, done once in `onModuleInit` of the producer's module, never inside `process()`. A genuinely request-scoped provider needed by a cron or hand-rolled worker is resolved per run: `const contextId = ContextIdFactory.create(); this.moduleRef.registerRequestByContextId(fakeRequest, contextId); const x = await this.moduleRef.resolve(X, contextId, { strict: false });`.

### Circular Dependencies and "Can't Resolve"

Prefer extracting shared logic into a third service. `forwardRef()` is a workaround with two separate uses: a **module** cycle needs `forwardRef(() => OtherModule)` in both modules' `imports`; a **provider** cycle needs `@Inject(forwardRef(() => Other))` on both constructors.

```typescript
// provider cycle - both sides
constructor(@Inject(forwardRef(() => PaymentService)) private readonly payments: PaymentService) {}
constructor(@Inject(forwardRef(() => OrderService)) private readonly orders: OrderService) {}
```

Diagnose "Nest can't resolve dependencies of X (A, ?)" from the `?` position and the exception class. A named argument reads "the argument <Name> at index [N] is available in the <Module> module" (11.1.16+; "<Module> context" before); from 11.1.7 an erased metatype and an undefined dependency print the same unnamed text ("available in the current module" - "current context" with the word `dependency` before 11.1.16 - then "appears to be undefined at runtime"), so only the exception class tells them apart:

| Message | Cause | Fix |
|---------|-------|-----|
| a class name at index [N] | the consuming module does not import the module that exports it, or the provider is not in its own module's `providers` | add the import/export or the provider |
| `UnknownDependenciesException` with an unnamed argument (11.1.16+), `dependency` (11.1.7-11.1.15), or `Object` (11.0-11.1.6) | injected by interface, type alias, or `import type` - the metatype erased | inject by token: `@Inject(TOKEN)` |
| `UndefinedDependencyException`, preceded at the default log level by the `InjectorLogger` line "Nest encountered an undefined dependency. This may be due to a circular import or a missing dependency declaration." | a circular file import left the class `undefined` at decoration time | break the file cycle, or `forwardRef` both sides |

"Nest cannot create the <Module> instance ... imports array is undefined" is the module-cycle case.

## Output Format

When authoring, emit this block plus the module, controller, and provider code it describes; a build over existing code is authoring plus review - findings for the existing defects the change touches, then the block; a defect elsewhere in the read set goes on one `Out of scope:` line naming the owning skill, after the findings and before the block. When reviewing or diagnosing, the consuming workflow owns the finding envelope; invoked standalone, each finding is a `### [Must] file:line` or `### [Recommend] file:line` heading (`pasted:<construct>` when the input names no file) followed by `Issue:` and `Fix:` lines, `[Must]` first - `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise. A diagnosis opens with one `Symptom: <as reported> -> <each cause at file:line>` line per reported symptom, and a question the request asks outright gets one `Ruling:` line; both precede the findings. After the findings, emit this block as the target state: every row shows the corrected value, and a row the current code violates ends ` - GAP (was: <observed>)`; a row whose evidence was not in the read set reads `unknown - <file> not read`, and a cell that does not apply reads `n/a`. Module Structure lists the modules the change touches plus every module they import or export to - a module or provider the change adds is a row with no GAP, anchored as `<file> (new)`; a provider the change removes keeps its DI Graph and Scopes row with `removed - <reason>` in the Scope cell. A row for a required construct the current code lacks (a Bootstrap setting, a global guard, a shutdown hook) reads ` - GAP (was: absent)`. The standalone-worker row covers any entrypoint that calls `createApplicationContext` - a second `main.ts`, or the same file behind an env flag.

```
## NestJS Architecture

**Stack:** {express | fastify | unknown - package.json not read} adapter, {Prisma | TypeORM | <other ORM> | none}{, BullMQ}

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

- Injecting `REQUEST`-scoped providers into singletons unintentionally
