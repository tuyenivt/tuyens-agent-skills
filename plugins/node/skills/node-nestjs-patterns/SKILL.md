---
name: node-nestjs-patterns
description: "NestJS patterns: modules, DI, controllers, guards, interceptors, pipes, exception filters, validation, and Swagger/OpenAPI. TypeScript strict mode."
user-invocable: false
---

Cover:

1. MODULE ARCHITECTURE:
   - One module per bounded context: OrdersModule, PaymentsModule
   - Explicit imports/exports: only export what other modules need
   - Global modules (@Global) sparingly — only for truly cross-cutting services
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

7. ANTI-PATTERNS:
   - ❌ Business logic in controllers (use services)
   - ❌ Circular module dependencies (refactor to shared module)
   - ❌ Using `any` in DTOs (defeats TypeScript purpose)
   - ❌ Global guards when per-route is more appropriate
   - ❌ Returning Prisma models directly from controllers
