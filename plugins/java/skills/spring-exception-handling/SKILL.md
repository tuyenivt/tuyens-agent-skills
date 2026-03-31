---
name: spring-exception-handling
description: Spring Boot @RestControllerAdvice and ProblemDetail (RFC 9457) - domain exception hierarchy, HTTP status mapping, DataIntegrityViolationException handling, and error response consistency.
metadata:
  category: backend
  tags: [error-handling, rest, http, controller]
user-invocable: false
---

# Exception Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Centralizing error handling across REST APIs
- Mapping business exceptions to appropriate HTTP status codes
- Wrapping third-party API errors (Stripe, payment gateways) into domain exceptions
- Ensuring consistent error response format

## Rules

- Use `@RestControllerAdvice` for centralized exception handling
- No try-catch in controller for business logic
- Map business exceptions to 4xx, system errors to 5xx
- Never expose stack traces to clients
- Use RFC 9457 `ProblemDetail` as the standard error response format (Spring Boot 3.x native support)
- Log system exceptions only, not expected business exceptions

## Domain Exception to HTTP Status Mapping

| Exception Class                                 | HTTP Status               | When to Use                                                 |
| ----------------------------------------------- | ------------------------- | ----------------------------------------------------------- |
| `ValidationException`                           | 400 Bad Request           | Input validation failure                                    |
| `AuthenticationException`                       | 401 Unauthorized          | Missing or invalid credentials                              |
| `AccessDeniedException`                         | 403 Forbidden             | Authenticated but not authorized                            |
| `NotFoundException` / `EntityNotFoundException` | 404 Not Found             | Resource does not exist                                     |
| `ConflictException`                             | 409 Conflict              | State conflict (duplicate, optimistic lock)                 |
| `UnprocessableEntityException`                  | 422 Unprocessable Entity  | Semantically invalid (valid format, invalid business state) |
| `RateLimitException`                            | 429 Too Many Requests     | Rate limit exceeded                                         |
| `RuntimeException` (unexpected)                 | 500 Internal Server Error | System failure - log with stack trace                       |

## Domain Exception Hierarchy

Define a base exception that carries an error code and HTTP status, then extend it for each domain case. This lets the global handler map any domain exception with a single `@ExceptionHandler`:

```java
// Base class - all domain exceptions extend this
public abstract class DomainException extends RuntimeException {
    private final HttpStatus status;
    private final String errorCode;

    protected DomainException(String message, HttpStatus status, String errorCode) {
        super(message);
        this.status = status;
        this.errorCode = errorCode;
    }

    public HttpStatus getStatus() { return status; }
    public String getErrorCode() { return errorCode; }
}

// Concrete domain exceptions
public class OrderNotFoundException extends DomainException {
    public OrderNotFoundException(Long id) {
        super("Order not found: " + id, HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND");
    }
}

public class InsufficientStockException extends DomainException {
    public InsufficientStockException(String sku, int requested, int available) {
        super("Insufficient stock for %s: requested %d, available %d".formatted(sku, requested, available),
              HttpStatus.CONFLICT, "INSUFFICIENT_STOCK");
    }
}

public class DuplicateEmailException extends DomainException {
    public DuplicateEmailException(String email) {
        super("Email already registered: " + email, HttpStatus.CONFLICT, "DUPLICATE_EMAIL");
    }
}
```

## Patterns

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

    // Generic domain exception handler - catches all DomainException subclasses
    @ExceptionHandler(DomainException.class)
    public ProblemDetail handleDomainException(DomainException ex) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(ex.getStatus(), ex.getMessage());
        pd.setTitle(ex.getErrorCode());
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
    }

    // Bean validation errors: 400, with per-field details
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail handleValidationErrors(MethodArgumentNotValidException ex) {
        ProblemDetail pd = ProblemDetail.forStatus(HttpStatus.BAD_REQUEST);
        pd.setTitle("Validation Failed");
        pd.setProperty("traceId", MDC.get("traceId"));
        Map<String, String> fieldErrors = ex.getBindingResult().getFieldErrors().stream()
            .collect(Collectors.toMap(
                FieldError::getField,
                fe -> fe.getDefaultMessage() != null ? fe.getDefaultMessage() : "invalid",
                (a, b) -> a // keep first if duplicate field
            ));
        pd.setProperty("fieldErrors", fieldErrors);
        return pd;
    }

    // Database constraint violation: 409 (e.g., unique constraint on email, SKU)
    @ExceptionHandler(DataIntegrityViolationException.class)
    public ProblemDetail handleDataIntegrity(DataIntegrityViolationException ex) {
        log.warn("Data integrity violation: {}", ex.getMostSpecificCause().getMessage());
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT,
            "A record with the given value already exists");
        pd.setTitle("Conflict");
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
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

### Wrapping External API Errors

Third-party APIs (Stripe, payment gateways, etc.) return their own exception types. Wrap them into domain exceptions at the integration boundary so callers never depend on the external library:

```java
// Bad: leaking Stripe exception into service layer
@Service
public class PaymentService {
    public PaymentResult charge(PaymentRequest req) {
        try {
            return stripeClient.charge(req);
        } catch (StripeException e) {
            throw e; // caller must import com.stripe.exception
        }
    }
}

// Good: classify and wrap at the boundary
@Component
@RequiredArgsConstructor
public class StripePaymentGateway implements PaymentGateway {

    public PaymentResult charge(PaymentRequest req) {
        try {
            var charge = stripeClient.createCharge(req.amount(), req.currency());
            return PaymentResult.success(charge.getId());
        } catch (CardException e) {
            throw new PaymentDeclinedException(req.orderId(), e.getDeclineCode());
        } catch (RateLimitException e) {
            throw new PaymentRetryableException(req.orderId(), "Rate limited", e);
        } catch (StripeException e) {
            throw new PaymentGatewayException(req.orderId(), e.getMessage(), e);
        }
    }
}
```

### Retryable vs Permanent Error Classification

When calling external services, callers need to know whether to retry. Use a marker interface or base class:

```java
public class RetryableException extends DomainException {
    protected RetryableException(String message, HttpStatus status, String errorCode) {
        super(message, status, errorCode);
    }
    public boolean isRetryable() { return true; }
}

public class PaymentRetryableException extends RetryableException {
    public PaymentRetryableException(Long orderId, String reason, Throwable cause) {
        super("Payment temporarily failed for order %d: %s".formatted(orderId, reason),
              HttpStatus.SERVICE_UNAVAILABLE, "PAYMENT_RETRYABLE");
        initCause(cause);
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

## Output Format

When applying exception handling patterns, document the mapping:

```
Exception: {exception class}
HTTP Status: {status code and name}
Error Code: {domain error code}
Logged: {yes (ERROR) | yes (WARN) | no}
Response Detail: {what the client sees}
```

## Avoid

- Try-catch blocks in controllers
- Exposing implementation details or stack traces
- Using 200 status for error responses
- Custom error format when ProblemDetail (RFC 9457) is available - standard format enables client interoperability
- Logging expected business exceptions (404, 400) as ERROR - they are not system failures
