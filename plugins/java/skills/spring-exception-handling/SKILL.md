---
name: spring-exception-handling
description: "Centralized REST error handling with @RestControllerAdvice and ProblemDetail (RFC 9457): domain exception hierarchy, HTTP mapping, vendor wrapping."
metadata:
  category: backend
  tags: [error-handling, rest, http, controller]
user-invocable: false
---

# Exception Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Centralizing REST error handling
- Mapping business exceptions to HTTP status codes
- Wrapping third-party SDK errors at the integration boundary

## Rules

- `@RestControllerAdvice` is the only place that maps exceptions to HTTP; controllers and services throw, never catch for response shaping
- Business exceptions extend one `DomainException` base carrying `HttpStatus` and `errorCode`; one handler covers the hierarchy
- Response body is `ProblemDetail` (RFC 9457); enable via `spring.mvc.problemdetails.enabled: true`
- Log unexpected failures at `ERROR` with stack trace, expected business errors at `WARN` or below, and never leak stack traces to clients
- Wrap vendor SDK exceptions at the integration boundary so callers depend only on domain types

## Exception to HTTP Mapping

| Exception                                                | Status |
| -------------------------------------------------------- | ------ |
| `MethodArgumentNotValidException`, `ConstraintViolationException`, `HttpMessageNotReadableException`, `MethodArgumentTypeMismatchException` | 400 |
| `AuthenticationException`                                | 401    |
| `AccessDeniedException`                                  | 403    |
| `NotFoundException` (domain)                             | 404    |
| `HttpRequestMethodNotSupportedException`                 | 405    |
| `ConflictException`, `DataIntegrityViolationException`, `OptimisticLockingFailureException` | 409 |
| `HttpMediaTypeNotSupportedException`                     | 415    |
| `MaxUploadSizeExceededException`                         | 413    |
| `UnprocessableEntityException` (domain)                  | 422    |
| `RateLimitedException` (domain)                          | 429    |
| Unhandled `Exception`                                    | 500    |

Spring 6.2+: extend `ResponseEntityExceptionHandler` to convert framework defaults to `ProblemDetail`, or throw `ErrorResponseException` directly for one-off cases.

## Patterns

### Domain exception hierarchy

```java
public abstract class DomainException extends RuntimeException {
    private final HttpStatus status;
    private final String errorCode;

    protected DomainException(String msg, HttpStatus status, String errorCode) {
        super(msg); this.status = status; this.errorCode = errorCode;
    }
    public HttpStatus getStatus() { return status; }
    public String getErrorCode() { return errorCode; }
}

public final class OrderNotFoundException extends DomainException {
    public OrderNotFoundException(Long id) {
        super("Order not found: " + id, NOT_FOUND, "ORDER_NOT_FOUND");
    }
}
```

Mark retryable failures with a sibling abstract (`RetryableException extends DomainException`) so callers can branch without string-matching messages.

### Global handler

```java
@RestControllerAdvice
public class GlobalExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(DomainException.class)
    ProblemDetail handleDomain(DomainException ex) {
        log.warn("{}: {}", ex.getErrorCode(), ex.getMessage());
        return problem(ex.getStatus(), ex.getErrorCode(), ex.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail handleValidation(MethodArgumentNotValidException ex) {
        var pd = problem(BAD_REQUEST, "VALIDATION_FAILED", "Request validation failed");
        pd.setProperty("fieldErrors", ex.getBindingResult().getFieldErrors().stream()
            .collect(toMap(FieldError::getField, FieldError::getDefaultMessage, (a, b) -> a)));
        return pd;
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail handleUnexpected(Exception ex) {
        log.error("Unexpected error", ex);
        return problem(INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "An unexpected error occurred");
    }

    private static ProblemDetail problem(HttpStatus status, String code, String detail) {
        var pd = ProblemDetail.forStatusAndDetail(status, detail);
        pd.setTitle(code);
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
    }
}
```

The `DomainException` handler covers every subclass via Spring's most-specific-type resolution; no per-subclass handler needed.

### Wrapping vendor SDK errors

Classify at the boundary; callers see domain types only.

```java
@Component
class StripePaymentGateway implements PaymentGateway {
    public PaymentResult charge(PaymentRequest req) {
        try {
            return PaymentResult.success(stripeClient.createCharge(req).getId());
        } catch (CardException e) {
            throw new PaymentDeclinedException(req.orderId(), e.getDeclineCode());
        } catch (com.stripe.exception.RateLimitException e) {
            throw new PaymentRetryableException(req.orderId(), e);
        } catch (StripeException e) {
            throw new PaymentGatewayException(req.orderId(), e);
        }
    }
}
```

## Output Format

```
Exception: {fully-qualified class}
HTTP Status: {code and reason}
Error Code: {domain code}
Logged: {ERROR | WARN | INFO | none}
Response Detail: {client-visible message}
```

## Avoid

- Try/catch in controllers for response shaping
- Custom error envelopes when `ProblemDetail` is available
- Logging expected business exceptions (404, 400, 409) at `ERROR`
- Leaking vendor exception types past the integration boundary
- Per-subclass handlers when the `DomainException` base handler suffices
