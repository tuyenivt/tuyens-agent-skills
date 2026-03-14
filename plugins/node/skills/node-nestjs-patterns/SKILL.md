---
name: node-nestjs-patterns
description: "NestJS patterns: modules, DI, controllers, guards, interceptors, pipes, exception filters, validation, and Swagger/OpenAPI. TypeScript strict mode."
user-invocable: false
---

Cover:

1. MODULE ARCHITECTURE:
   - One module per bounded context: OrdersModule, PaymentsModule
   - Explicit imports/exports: only export what other modules need
   - Global modules (@Global) sparingly - only for truly cross-cutting services
   - Dynamic modules for configurable providers (e.g., DatabaseModule.forRoot(config))

2. DEPENDENCY INJECTION:
   - @Injectable() on every service, repository, guard, etc.
   - Constructor injection (default, preferred)
   - Custom providers: useClass, useFactory, useValue for advanced DI
   - Async providers for DB connections, external clients

3. CONTROLLERS:
   - @Controller('orders') with route prefix
   - HTTP decorators: @Get(), @Post(), @Put(), @Patch(), @Delete()
   - @Param(), @Query(), @Body() for input extraction
   - @HttpCode(201) for POST responses
   - Return DTOs, never return raw Prisma/entity objects

4. GUARDS, INTERCEPTORS, PIPES:
   - Guards for authentication/authorization: @UseGuards(JwtAuthGuard)
   - Interceptors for response transformation, logging, caching
   - Pipes for validation: new ValidationPipe({ whitelist: true, transform: true })
   - Apply globally or per-controller/per-route

5. EXCEPTION FILTERS:
   - Built-in: BadRequestException, NotFoundException, UnauthorizedException
   - Custom exception filter for consistent error format
   - @Catch() decorator on filter class

6. VALIDATION:
   - class-validator decorators on DTOs: @IsString(), @IsInt(), @Min(), @IsEmail()
   - class-transformer for type coercion
   - Whitelist: true strips unknown properties (security)
   - Custom validators for complex business rules

7. DEPENDENCY INJECTION SCOPES:

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

8. CIRCULAR DEPENDENCY RESOLUTION:

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

9. ANTI-PATTERNS:
   - ❌ Business logic in controllers (use services)
   - ❌ Circular module dependencies without `forwardRef()` (runtime error: "Nest cannot create the module instance")
   - ❌ Injecting REQUEST-scoped providers into singletons without declaring `Scope.REQUEST` on the singleton (Nest will throw or use wrong scope)
   - ❌ Using `any` in DTOs (defeats TypeScript purpose)
   - ❌ Global guards when per-route is more appropriate
   - ❌ Returning Prisma models directly from controllers
