---
name: node-nestjs-patterns
description: NestJS patterns: modules, DI scopes, controllers, guards, interceptors, pipes, exception filters, class-validator, circular deps, webhooks.
metadata:
  category: backend
  tags: [node, typescript, nestjs, di, validation, patterns]
user-invocable: false
---

# NestJS Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or reviewing NestJS modules, DI, controllers, guards, validation
- Webhook endpoints needing raw body + signature validation

## Rules

- One module per bounded context; explicit imports/exports
- `@Injectable()` on every service/repository/guard/interceptor; prefer constructor injection
- Controllers orchestrate; services execute business logic
- Return DTOs - never raw Prisma/TypeORM entities
- `ValidationPipe({ whitelist: true, transform: true })` globally; never `any` in DTOs. A global pipe cannot be overridden per route - `@UsePipes()` on a controller **adds** a pipe, it does not replace the global one. Escape by shape, not config: a handler parameter typed `Buffer`, `Record<string, string>`, or a bare `Object` has no metatype to validate, so the pipe skips it
- Global guards (`APP_GUARD`) run before route-level guards, so a route cannot opt out by omission. Put the exemption inside the guard - a `@Public()` decorator read via `Reflector` - and fail closed by default
- Map entities to DTOs with an explicit allowlist mapper (a plain function or a `static from()`), never by stripping fields off the entity - a denylist re-leaks every column added later

## Patterns

### Module Architecture

- Export only what other modules need; `@Global()` only for truly cross-cutting (e.g., `PrismaModule`)
- Dynamic modules for configurable providers: `BullModule.registerQueue({ name: ORDER_QUEUE })`
- Custom providers (`useClass` / `useFactory` / `useValue`) and async providers for DB/external clients

```typescript
@Module({
  imports: [PrismaModule, BullModule.registerQueue({ name: ORDER_QUEUE })],
  providers: [OrderService],
  controllers: [OrderController],
  exports: [OrderService],
})
export class OrdersModule {}
```

### Controllers

- `@Controller('api/v1/orders')`; HTTP verb decorators with `@Param/@Query/@Body`
- POST defaults to 201, every other verb to 200. `@HttpCode(204)` on any handler that returns no body (DELETE, and a PATCH whose result the client already has); `@HttpCode(200)` on a non-creating POST. A 204 handler must return `void` - a response-shaping interceptor still runs and will otherwise emit a body Nest cannot send
- Built-in exceptions: `BadRequestException`, `UnauthorizedException`, `ForbiddenException`, `NotFoundException`, `ConflictException`, `UnprocessableEntityException`

```typescript
@Controller("api/v1/orders")
export class OrderController {
  constructor(private readonly orders: OrderService) {}

  @Post()
  @UseGuards(JwtAuthGuard)
  create(@Body() dto: CreateOrderDto): Promise<OrderResponseDto> {
    return this.orders.create(dto);
  }
}
```

### Guards, Interceptors, Pipes

- Guards: authn/authz. Order matters - auth before role: `@UseGuards(JwtAuthGuard, RolesGuard)`
- Interceptors: response transform, logging, caching
- Pipes: validation/coercion via `class-validator` + `class-transformer`

### Validation

- DTO decorators: `@IsString`, `@IsInt`, `@IsEmail`, `@IsEnum`, `@ValidateNested({ each: true })` + `@Type(() => Child)`
- `whitelist: true` strips unknown props (security); custom validators for business rules

```typescript
export class CreateOrderDto {
  @IsString() customerId: string;

  @IsArray() @ValidateNested({ each: true }) @Type(() => OrderItemDto)
  items: OrderItemDto[];

  @IsEnum(OrderStatus) @IsOptional() status?: OrderStatus;
}
```

### Exception Filters

- Built-ins: `BadRequestException`, `NotFoundException`, `UnauthorizedException`, `ConflictException`
- `@Catch()` filter for consistent error envelope

```typescript
@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  catch(ex: unknown, host: ArgumentsHost): void {
    const res = host.switchToHttp().getResponse<Response>();
    const http = ex instanceof HttpException ? ex : null;
    res.status(http?.getStatus() ?? 500).json({
      error: http?.message ?? "Internal server error",
      statusCode: http?.getStatus() ?? 500,
    });
  }
}
```

### Webhooks

- Enable `NestFactory.create(AppModule, { rawBody: true })`; access via `RawBodyRequest<Request>`
- Authenticate by signature, NOT JWT guard - and because the JWT guard is usually global, that means a `@Public()` exemption read inside the guard
- If a custom body parser is registered ahead of Nest's, `rawBody` is empty - do not `app.use(express.json())` before bootstrap
- A form-encoded provider (Twilio, Slack) signs the parsed-and-sorted params or the raw form body, not JSON. Type that handler's body `Record<string, string>` so the global `whitelist` does not strip fields before the signature is computed

```typescript
@Post("webhooks/stripe")
handle(@Req() req: RawBodyRequest<Request>, @Headers("stripe-signature") sig: string) {
  const event = this.stripe.webhooks.constructEvent(req.rawBody!, sig, this.secret);
  return this.payments.handleWebhookEvent(event);
}
```

### DI Scopes

| Scope               | Lifetime                         | Use When                                |
| ------------------- | -------------------------------- | --------------------------------------- |
| `DEFAULT`           | App lifetime (singleton)         | Stateless services (default)            |
| `REQUEST`           | Per HTTP request                 | Request-scoped state (e.g., current user) |
| `TRANSIENT`         | Per injection point              | Stateful helpers that must not be shared |

Scope propagates upward: a singleton injecting a `REQUEST` provider becomes `REQUEST`-scoped, and so does everything that injects *it*. Two symptoms, one cause - a "singleton" that got slow, and a `@Cron` job or BullMQ processor that throws at startup because request scope is **unreachable** outside a request.

The fix is to stop propagating scope, not to change the scope keyword. Carry per-request state out of band in an `AsyncLocalStorage`-backed singleton seeded by middleware; every provider goes back to `DEFAULT`, and a cron or worker supplies the context explicitly.

```typescript
@Injectable()
export class TenantContext {
  private readonly als = new AsyncLocalStorage<{ tenantId: string }>();
  run<T>(store: { tenantId: string }, fn: () => T): T { return this.als.run(store, fn); }
  get tenantId(): string { return this.als.getStore()?.tenantId ?? throwMissingContext(); }
}
```

Where a genuinely request-scoped provider must be reached from a worker, resolve it per job with `ModuleRef` + `ContextIdFactory`, not by injecting it.

### Circular Dependencies

Prefer extracting shared logic into a third service. `forwardRef()` is a workaround, and a module cycle needs it in **both** places - the constructor form alone does not resolve it:

```typescript
// both modules
@Module({ imports: [forwardRef(() => PaymentsModule)] })
// and the injection site
constructor(@Inject(forwardRef(() => PaymentService)) private readonly payments: PaymentService) {}
```

"Nest can't resolve dependencies of X" has two distinct causes: the consuming module does not import the module that **exports** the dependency (add the import/export), or the two modules form a cycle (adding a plain import makes it worse - break the cycle or `forwardRef` both sides).

## Output Format

When authoring, emit this block plus the module, controller, and provider code it describes. When reviewing, the consuming workflow owns the finding envelope (label, severity, `file:line`; invoked standalone, order `[Must]` first and label each finding `[Must]` when it risks incorrect behaviour, data loss, or a security hole, `[Recommend]` otherwise); emit this block as the target state and one finding per deviation from it.

```
## NestJS Architecture

### Bootstrap
[Global pipes, global guards/filters/interceptors, rawBody, and anything registered before NestFactory]

### Module Structure
| Module | Providers | Controllers | Exports | Imports | Cycle handling |
|--------|-----------|-------------|---------|---------|----------------|

### Controller Endpoints
| Method | Route | Status | Guards | Pipe/Validation | Response DTO |
|--------|-------|--------|--------|-----------------|--------------|

### DI Graph and Scopes
| Provider | Scope | Injects | Scope it propagates to |
|----------|-------|---------|------------------------|
```

## Avoid

- Business logic in controllers; returning Prisma/entity objects; `any` in DTOs
- Circular module deps without `forwardRef()` (or without refactoring out a shared service)
- Injecting `REQUEST`-scoped providers into singletons unintentionally
- Global guards where per-route is more appropriate
- JWT guards on webhook endpoints (signature-based auth instead)
