---
name: spring-exception-handling
description: Centralized exception handling with proper HTTP mapping
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
- Use standard error format: code, message, traceId
- Log system exceptions only, not expected business exceptions

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

Good - Centralized exception handling:

```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    @ExceptionHandler(ValidationException.class)
    public ResponseEntity<ErrorResponse> handleValidation(ValidationException e) {
        return ResponseEntity.status(400).body(
            new ErrorResponse("VALIDATION_ERROR", e.getMessage(), traceId)
        );
    }
}
```

## Avoid

- Try-catch blocks in controllers
- Exposing implementation details or stack traces
- Using 200 status for error responses
