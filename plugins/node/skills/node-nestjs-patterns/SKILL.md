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
- `ValidationPipe({ whitelist: true, transform: true })` globally; never `any` in DTOs

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
- POST defaults to 201; add `@HttpCode(204)` on DELETE and `@HttpCode(200)` on non-creating POST actions

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
- Authenticate by signature, NOT JWT guard
- If global body parser runs first, `rawBody` is empty - bypass parsing on webhook routes

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

Scope propagates upward: a singleton injecting a `REQUEST` provider becomes `REQUEST`-scoped, silently degrading performance. Audit the chain on perf regressions.

### Circular Dependencies

Prefer extracting shared logic into a third service. `forwardRef()` is a workaround:

```typescript
constructor(@Inject(forwardRef(() => PaymentService)) private readonly payments: PaymentService) {}
```

Module-level error "Nest can't resolve dependencies of X" usually means the consuming module doesn't import the module that exports the dependency.

## Output Format

```
## NestJS Architecture

### Module Structure
| Module | Providers | Exports | Imports |
|--------|-----------|---------|---------|

### Controller Endpoints
| Method | Route | Guards | Pipe/Validation | Response DTO |
|--------|-------|--------|-----------------|--------------|

### DI Graph
[Provider dependency chain]
```

## Avoid

- Business logic in controllers; returning Prisma/entity objects; `any` in DTOs
- Circular module deps without `forwardRef()` (or without refactoring out a shared service)
- Injecting `REQUEST`-scoped providers into singletons unintentionally
- Global guards where per-route is more appropriate
- JWT guards on webhook endpoints (signature-based auth instead)
