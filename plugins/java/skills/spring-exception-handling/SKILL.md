---
name: spring-exception-handling
description: Spring Boot @ControllerAdvice and ProblemDetail (RFC 7807) - domain exception hierarchy, HTTP status mapping, and error response consistency.
metadata:
  category: backend
  tags: [error-handling, rest, http, controller]
user-invocable: false
---

# Exception Handling

## When to Use

- Centralizing error handling across REST APIs
- Mapping business exceptions to appropriate HTTP status codes
- Ensuring consistent error response format

## Rules

- Use `@RestControllerAdvice` for centralized exception handling
- No try-catch in controller for business logic
- Map business exceptions to 4xx, system errors to 5xx
- Never expose stack traces to clients
- Use RFC 9457 `ProblemDetail` as the standard error response format (Spring Boot 3.x native support)
- Log system exceptions only, not expected business exceptions

## Domain Exception to HTTP Status Mapping

| Exception Class | HTTP Status | When to Use |
| --------------- | ----------- | ----------- |
| `ValidationException` | 400 Bad Request | Input validation failure |
| `AuthenticationException` | 401 Unauthorized | Missing or invalid credentials |
| `AccessDeniedException` | 403 Forbidden | Authenticated but not authorized |
| `NotFoundException` / `EntityNotFoundException` | 404 Not Found | Resource does not exist |
| `ConflictException` | 409 Conflict | State conflict (duplicate, optimistic lock) |
| `UnprocessableEntityException` | 422 Unprocessable Entity | Semantically invalid (valid format, invalid business state) |
| `RateLimitException` | 429 Too Many Requests | Rate limit exceeded |
| `RuntimeException` (unexpected) | 500 Internal Server Error | System failure - log with stack trace |

## Pattern

Bad - Scattered error handling:

```java
@RestController
public class UserController {
    @PostMapping("/users")
    public ResponseEntity<?> createUser(UserRequest req) {
        try {
            return ResponseEntity.ok(userService.create(req));
        } catch (Exception e) {
            return ResponseEntity.status(500).body("Error");
        }
    }
}
```

Good - Centralized exception handling with RFC 9457 ProblemDetail:

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    // Business exception: 400, no stack trace logged
    @ExceptionHandler(ValidationException.class)
    public ProblemDetail handleValidation(ValidationException ex, WebRequest request) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, ex.getMessage());
        pd.setTitle("Validation Failed");
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
    }

    // Domain not found: 404
    @ExceptionHandler(NotFoundException.class)
    public ProblemDetail handleNotFound(NotFoundException ex) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.getMessage());
        pd.setTitle("Resource Not Found");
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
    }

    // State conflict: 409
    @ExceptionHandler(ConflictException.class)
    public ProblemDetail handleConflict(ConflictException ex) {
        return ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, ex.getMessage());
    }

    // System exception: 500, log with stack trace
    @ExceptionHandler(Exception.class)
    public ProblemDetail handleUnexpected(Exception ex) {
        log.error("Unexpected error", ex); // stack trace logged server-side only
        ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR);
        pd.setDetail("An unexpected error occurred");
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
    }
}
```

Enable ProblemDetail in `application.yml`:

```yaml
spring:
  mvc:
    problemdetails:
      enabled: true
```

## Avoid

- Try-catch blocks in controllers
- Exposing implementation details or stack traces
- Using 200 status for error responses
- Custom error format when ProblemDetail (RFC 9457) is available - standard format enables client interoperability
- Logging expected business exceptions (404, 400) as ERROR - they are not system failures
