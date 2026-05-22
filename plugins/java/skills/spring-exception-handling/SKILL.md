---
name: spring-exception-handling
description: "Centralized error handling with @RestControllerAdvice and ProblemDetail (RFC 9457): exception hierarchy, HTTP mapping, external API wrapping."
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
- Wrapping third-party API errors at the integration boundary

## Rules

- `@RestControllerAdvice` is the only place that maps exceptions to HTTP - no try/catch in controllers for business logic
- Business exceptions extend a single `DomainException` base carrying `HttpStatus` and `errorCode`
- Response body uses `ProblemDetail` (RFC 9457) - never custom error envelopes
- Never expose stack traces to clients; log them server-side at `ERROR` only for unexpected failures (`WARN` or below for expected business errors)
- Spring resolves `@ExceptionHandler` by most-specific type - a `DomainException` handler covers all subclasses

## Domain Exception → HTTP Mapping

| Exception                                       | Status  | When                            |
| ----------------------------------------------- | ------- | ------------------------------- |
| `ValidationException` / `MethodArgumentNotValidException` | 400 | Input validation failure        |
| `AuthenticationException`                       | 401     | Missing/invalid credentials     |
| `AccessDeniedException`                         | 403     | Authn ok, authz failed          |
| `NotFoundException` / `EntityNotFoundException` | 404     | Resource missing                |
| `ConflictException` / `DataIntegrityViolationException` | 409 | Unique / optimistic-lock conflict |
| `UnprocessableEntityException`                  | 422     | Valid format, invalid business state |
| `RateLimitException`                            | 429     | Rate limited                    |
| Unhandled `RuntimeException`                    | 500     | System failure - log stack trace |

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

public class OrderNotFoundException extends DomainException {
    public OrderNotFoundException(Long id) {
        super("Order not found: " + id, NOT_FOUND, "ORDER_NOT_FOUND");
    }
}

public class InsufficientStockException extends DomainException {
    public InsufficientStockException(String sku, int requested, int available) {
        super("Insufficient stock for %s: requested %d, available %d".formatted(sku, requested, available),
              CONFLICT, "INSUFFICIENT_STOCK");
    }
}
```

### Global handler with ProblemDetail

```java
@Slf4j @RestControllerAdvice
public class GlobalExceptionHandler {

    // Catches every DomainException subclass via type hierarchy
    @ExceptionHandler(DomainException.class)
    public ProblemDetail handleDomain(DomainException ex) {
        ProblemDetail pd = ProblemDetail.forStatusAndDetail(ex.getStatus(), ex.getMessage());
        pd.setTitle(ex.getErrorCode());
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ProblemDetail handleValidation(MethodArgumentNotValidException ex) {
        ProblemDetail pd = ProblemDetail.forStatus(BAD_REQUEST);
        pd.setTitle("Validation Failed");
        pd.setProperty("fieldErrors", ex.getBindingResult().getFieldErrors().stream()
            .collect(toMap(FieldError::getField,
                fe -> fe.getDefaultMessage() != null ? fe.getDefaultMessage() : "invalid",
                (a, b) -> a)));
        pd.setProperty("traceId", MDC.get("traceId"));
        return pd;
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ProblemDetail handleDataIntegrity(DataIntegrityViolationException ex) {
        log.warn("Data integrity violation: {}", ex.getMostSpecificCause().getMessage());
        return problem(CONFLICT, "Conflict", "A record with the given value already exists");
    }

    @ExceptionHandler(Exception.class)
    public ProblemDetail handleUnexpected(Exception ex) {
        log.error("Unexpected error", ex);
        return problem(INTERNAL_SERVER_ERROR, null, "An unexpected error occurred");
    }
}
```

Other framework exceptions worth explicit handlers (or extend `ResponseEntityExceptionHandler` to convert defaults to `ProblemDetail`): `HttpMessageNotReadableException` (400), `MethodArgumentTypeMismatchException` (400), `ConstraintViolationException` (400), `HttpRequestMethodNotSupportedException` (405), `HttpMediaTypeNotSupportedException` (415), `MaxUploadSizeExceededException` (413).

### Wrapping external API errors

Classify and wrap at the integration boundary so callers never depend on the vendor SDK.

```java
@Component @RequiredArgsConstructor
public class StripePaymentGateway implements PaymentGateway {
    public PaymentResult charge(PaymentRequest req) {
        try {
            return PaymentResult.success(stripeClient.createCharge(req.amount(), req.currency()).getId());
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

For retry-vs-permanent classification, mark retryable exceptions via a marker class (`RetryableException extends DomainException`).

Enable ProblemDetail conversion site-wide:

```yaml
spring.mvc.problemdetails.enabled: true
```

## Output Format

```
Exception: {class}
HTTP Status: {code and name}
Error Code: {domain code}
Logged: {ERROR | WARN | none}
Response Detail: {client-visible message}
```

## Avoid

- Try/catch in controllers
- Custom error envelopes when `ProblemDetail` is available
- Logging expected business exceptions (404, 400) as `ERROR`
- Leaking vendor exception types past the integration boundary
