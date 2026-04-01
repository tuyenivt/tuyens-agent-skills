---
name: node-nestjs-patterns
description: NestJS application patterns - module architecture, dependency injection, controllers, guards, interceptors, pipes, exception filters, validation with class-validator, DI scopes, circular dependency resolution, and webhook handling.
metadata:
  category: backend
  tags: [node, typescript, nestjs, di, validation, patterns]
user-invocable: false
---

# NestJS Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building or extending a NestJS application
- Setting up module structure, DI, guards, or validation
- Implementing webhook endpoints that need raw body reading and signature validation
- Reviewing NestJS code for architectural or DI issues

## Rules

- One module per bounded context - explicit imports/exports
- `@Injectable()` on every service, repository, guard, interceptor
- Constructor injection preferred; custom providers for advanced DI
- Return DTOs from controllers - never expose Prisma models or TypeORM entities
- No business logic in controllers - controllers orchestrate, services execute

## Patterns

### Module Architecture

- One module per bounded context: `OrdersModule`, `PaymentsModule`
- Explicit imports/exports: only export what other modules need
- Global modules (`@Global`) sparingly - only for truly cross-cutting services (e.g., `PrismaModule`)
- Dynamic modules for configurable providers (e.g., `BullModule.registerQueue({ name: ORDER_QUEUE })`)

### Dependency Injection

- `@Injectable()` on every service, repository, guard
- Constructor injection (default, preferred)
- Custom providers: `useClass`, `useFactory`, `useValue` for advanced DI
- Async providers for DB connections, external clients

```typescript
// Module with providers and exports
@Module({
  imports: [PrismaModule, BullModule.registerQueue({ name: ORDER_QUEUE })],
  providers: [OrderService, OrderProcessor],
  controllers: [OrderController],
  exports: [OrderService],
})
export class OrdersModule {}
```

### Controllers

- `@Controller('orders')` with route prefix
- HTTP decorators: `@Get()`, `@Post()`, `@Put()`, `@Patch()`, `@Delete()`
- `@Param()`, `@Query()`, `@Body()` for input extraction
- `@HttpCode(201)` for POST responses, `@HttpCode(204)` for DELETE
- Return DTOs, never return raw Prisma/entity objects

```typescript
@Controller("api/v1/orders")
export class OrderController {
  constructor(private readonly orderService: OrderService) {}

  @Get()
  findAll(
    @Query() query: ListOrdersDto,
  ): Promise<PaginatedResponse<OrderResponseDto>> {
    return this.orderService.findAll(query);
  }

  @Post()
  @HttpCode(201)
  create(@Body() dto: CreateOrderDto): Promise<OrderResponseDto> {
    return this.orderService.create(dto);
  }

  @Patch(":id")
  update(
    @Param("id") id: string,
    @Body() dto: UpdateOrderDto,
  ): Promise<OrderResponseDto> {
    return this.orderService.update(id, dto);
  }

  @Delete(":id")
  @HttpCode(204)
  remove(@Param("id") id: string): Promise<void> {
    return this.orderService.remove(id);
  }
}
```

### Guards, Interceptors, Pipes

- Guards for authentication/authorization: `@UseGuards(JwtAuthGuard)`
- Interceptors for response transformation, logging, caching
- Pipes for validation: `new ValidationPipe({ whitelist: true, transform: true })`
- Apply globally or per-controller/per-route
- Guard ordering matters: put auth guard before role guard: `@UseGuards(JwtAuthGuard, RolesGuard)`

### Exception Filters

- Built-in: `BadRequestException`, `NotFoundException`, `UnauthorizedException`, `ConflictException`
- Custom exception filter for consistent error format across the app
- `@Catch()` decorator on filter class

```typescript
@Catch()
export class AllExceptionsFilter implements ExceptionFilter {
  catch(exception: unknown, host: ArgumentsHost): void {
    const ctx = host.switchToHttp();
    const response = ctx.getResponse<Response>();

    if (exception instanceof HttpException) {
      response.status(exception.getStatus()).json({
        error: exception.message,
        statusCode: exception.getStatus(),
      });
      return;
    }
    response
      .status(500)
      .json({ error: "Internal server error", statusCode: 500 });
  }
}
```

### Validation

- `class-validator` decorators on DTOs: `@IsString()`, `@IsInt()`, `@Min()`, `@IsEmail()`, `@IsEnum()`
- `class-transformer` for type coercion
- `whitelist: true` strips unknown properties (security)
- Custom validators for complex business rules

```typescript
export class CreateOrderDto {
  @IsString()
  customerId: string;

  @IsArray()
  @ValidateNested({ each: true })
  @Type(() => OrderItemDto)
  items: OrderItemDto[];

  @IsEnum(OrderStatus)
  @IsOptional()
  status?: OrderStatus;
}
```

### Webhook Endpoints

Webhook endpoints from external services (Stripe, GitHub) require reading the raw body for signature validation. Enable raw body in NestJS bootstrap and use `@Req()` to access it:

```typescript
// main.ts - enable raw body
const app = await NestFactory.create(AppModule, { rawBody: true });

// Controller - webhook with raw body access
@Post('webhooks/stripe')
async handleStripeWebhook(
  @Req() req: RawBodyRequest<Request>,
  @Headers('stripe-signature') signature: string,
): Promise<{ received: boolean }> {
  const event = this.stripe.webhooks.constructEvent(
    req.rawBody!,
    signature,
    this.configService.get('STRIPE_WEBHOOK_SECRET'),
  );
  await this.paymentService.handleWebhookEvent(event);
  return { received: true };
}
```

Webhook endpoints should NOT be behind JWT auth guards - they use signature-based authentication.

### Dependency Injection Scopes

NestJS providers have three scopes controlling instance lifetime:

| Scope                 | Decorator              | Lifetime                         | Use When                                                     |
| --------------------- | ---------------------- | -------------------------------- | ------------------------------------------------------------ |
| `DEFAULT` (Singleton) | none / `Scope.DEFAULT` | One instance for app lifetime    | Stateless services (default)                                 |
| `REQUEST`             | `Scope.REQUEST`        | New instance per HTTP request    | Services that hold request-scoped state (e.g., current user) |
| `TRANSIENT`           | `Scope.TRANSIENT`      | New instance per injection point | Stateful helpers that must not be shared                     |

Note: REQUEST and TRANSIENT scopes propagate upward - a singleton that injects a REQUEST-scoped provider becomes REQUEST-scoped too. This can silently degrade performance.

### Circular Dependency Resolution

When two providers depend on each other, use `forwardRef()` to break the cycle:

```typescript
@Injectable()
export class OrderService {
  constructor(
    @Inject(forwardRef(() => PaymentService))
    private readonly paymentService: PaymentService,
  ) {}
}
```

Prefer resolving circular deps by extracting shared logic into a third service. `forwardRef()` is a workaround, not a design goal.

## Edge Cases

- **Scope propagation confusion**: A singleton injecting a REQUEST-scoped provider silently becomes REQUEST-scoped. If performance degrades after adding a REQUEST-scoped dependency, check for unintended scope propagation up the injection chain.
- **Module not importing required provider**: Error "Nest can't resolve dependencies of X" - verify the module that declares X also imports the module that exports the dependency.
- **Guard ordering with multiple guards**: Guards execute in array order - put auth guard before role guard: `@UseGuards(JwtAuthGuard, RolesGuard)`.
- **Webhook body already consumed**: If a global body-parsing middleware runs before the webhook route, `rawBody` may be unavailable. Ensure webhook routes either bypass body parsing or use NestJS's built-in `rawBody` option.

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

- Business logic in controllers (use services)
- Circular module dependencies without `forwardRef()` (runtime error: "Nest cannot create the module instance")
- Injecting REQUEST-scoped providers into singletons without declaring `Scope.REQUEST` on the singleton
- Using `any` in DTOs (defeats TypeScript purpose)
- Global guards when per-route is more appropriate
- Returning Prisma models directly from controllers (use response DTOs)
- Putting webhook endpoints behind JWT auth guards (they use signature-based auth)
