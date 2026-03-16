---
name: node-nestjs-patterns
description: NestJS application patterns - module architecture, dependency injection, controllers, guards, interceptors, pipes, exception filters, validation with class-validator, DI scopes, and circular dependency resolution.
metadata:
  category: backend
  tags: [node, typescript, nestjs, di, validation, patterns]
user-invocable: false
---

# NestJS Patterns

## When to Use

- Building or extending a NestJS application
- Setting up module structure, DI, guards, or validation
- Reviewing NestJS code for architectural or DI issues

## Rules

- One module per bounded context - explicit imports/exports
- `@Injectable()` on every service, repository, guard, interceptor
- Constructor injection preferred; custom providers for advanced DI
- Return DTOs from controllers - never expose Prisma models or TypeORM entities

## Patterns

### Module Architecture

- One module per bounded context: `OrdersModule`, `PaymentsModule`
- Explicit imports/exports: only export what other modules need
- Global modules (`@Global`) sparingly - only for truly cross-cutting services
- Dynamic modules for configurable providers (e.g., `DatabaseModule.forRoot(config)`)

### Dependency Injection

- `@Injectable()` on every service, repository, guard
- Constructor injection (default, preferred)
- Custom providers: `useClass`, `useFactory`, `useValue` for advanced DI
- Async providers for DB connections, external clients

### Controllers

- `@Controller('orders')` with route prefix
- HTTP decorators: `@Get()`, `@Post()`, `@Put()`, `@Patch()`, `@Delete()`
- `@Param()`, `@Query()`, `@Body()` for input extraction
- `@HttpCode(201)` for POST responses
- Return DTOs, never return raw Prisma/entity objects

### Guards, Interceptors, Pipes

- Guards for authentication/authorization: `@UseGuards(JwtAuthGuard)`
- Interceptors for response transformation, logging, caching
- Pipes for validation: `new ValidationPipe({ whitelist: true, transform: true })`
- Apply globally or per-controller/per-route

### Exception Filters

- Built-in: `BadRequestException`, `NotFoundException`, `UnauthorizedException`
- Custom exception filter for consistent error format
- `@Catch()` decorator on filter class

### Validation

- `class-validator` decorators on DTOs: `@IsString()`, `@IsInt()`, `@Min()`, `@IsEmail()`
- `class-transformer` for type coercion
- `whitelist: true` strips unknown properties (security)
- Custom validators for complex business rules

### Dependency Injection Scopes

NestJS providers have three scopes controlling instance lifetime:

| Scope                 | Decorator              | Lifetime                         | Use When                                                     |
| --------------------- | ---------------------- | -------------------------------- | ------------------------------------------------------------ |
| `DEFAULT` (Singleton) | none / `Scope.DEFAULT` | One instance for app lifetime    | Stateless services (default)                                 |
| `REQUEST`             | `Scope.REQUEST`        | New instance per HTTP request    | Services that hold request-scoped state (e.g., current user) |
| `TRANSIENT`           | `Scope.TRANSIENT`      | New instance per injection point | Stateful helpers that must not be shared                     |

```typescript
import { Injectable, Scope } from "@nestjs/common";

// Singleton (default) - stateless services
@Injectable()
export class OrderService {}

// Request-scoped - inject REQUEST to access current request
@Injectable({ scope: Scope.REQUEST })
export class AuditService {
  constructor(@Inject(REQUEST) private readonly request: Request) {}
}

// Transient - new instance per injection
@Injectable({ scope: Scope.TRANSIENT })
export class UniqueIdGenerator {}
```

Note: REQUEST and TRANSIENT scopes propagate upward - a singleton that injects a REQUEST-scoped provider becomes REQUEST-scoped too.

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

@Injectable()
export class PaymentService {
  constructor(
    @Inject(forwardRef(() => OrderService))
    private readonly orderService: OrderService,
  ) {}
}
```

Prefer resolving circular deps by extracting shared logic into a third service. `forwardRef()` is a workaround, not a design goal.

## Edge Cases

- **Scope propagation confusion**: A singleton injecting a REQUEST-scoped provider silently becomes REQUEST-scoped. If performance degrades after adding a REQUEST-scoped dependency, check for unintended scope propagation up the injection chain.
- **Module not importing required provider**: Error "Nest can't resolve dependencies of X" - verify the module that declares X also imports the module that exports the dependency.
- **Guard ordering with multiple guards**: Guards execute in array order - put auth guard before role guard: `@UseGuards(JwtAuthGuard, RolesGuard)`.

## Avoid

- Business logic in controllers (use services)
- Circular module dependencies without `forwardRef()` (runtime error: "Nest cannot create the module instance")
- Injecting REQUEST-scoped providers into singletons without declaring `Scope.REQUEST` on the singleton (Nest will throw or use wrong scope)
- Using `any` in DTOs (defeats TypeScript purpose)
- Global guards when per-route is more appropriate
- Returning Prisma models directly from controllers
