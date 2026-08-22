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
| `PaymentDeclinedException` (domain)                      | 402    |
| `HttpMediaTypeNotSupportedException`                     | 415    |
| `MaxUploadSizeExceededException`                         | 413    |
| `UnprocessableEntityException` (domain)                  | 422    |
| `RateLimitedException` (domain - *our* throttle, not an upstream 429) | 429 |
| Unhandled `Exception`                                    | 500    |
| `RetryableException` subtypes (transient upstream failure) | 503  |
| Vendor-gateway wrapper (unclassified upstream failure, e.g. `PaymentGatewayException`) | 502 |

Split 502 from 503 at the integration boundary, on the cause: timeout, connection failure, upstream 429 or upstream 5xx are transient -> `RetryableException` -> 503; everything else the vendor throws is unclassified -> gateway wrapper -> 502. An upstream 429 never becomes our 429 - that would tell the client it is throttled when it is not. Likewise `DataIntegrityViolationException` is 409 only for a constraint the client can act on (unique key); identify the constraint at the boundary and let the rest fall to 500.

Spring 6+: the advice extends `ResponseEntityExceptionHandler` (see Global handler) so framework exceptions keep their table statuses as `ProblemDetail`. Once that advice exists `spring.mvc.problemdetails.enabled` is inert - Boot's `ProblemDetailsExceptionHandler` is `@ConditionalOnMissingBean(ResponseEntityExceptionHandler.class)` and backs off. Set it anyway (WebFlux: `spring.webflux.problemdetails.enabled`) so removing the advice degrades to `ProblemDetail` rather than Boot's default error map. One-off cases can throw `ErrorResponseException` directly.

The 401/403 rows are special: exceptions thrown in the security filter chain (failed authentication, filter-level authorization) never reach the advice - wire `AuthenticationEntryPoint` / `AccessDeniedHandler` in the security config for those (WebFlux: `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler`). Only method-security denials (`@PreAuthorize`) surface as `AccessDeniedException` to an `@ExceptionHandler`.

WebFlux differences: extend the reactive `ResponseEntityExceptionHandler` (`org.springframework.web.reactive.result.method.annotation`), override `handleWebExchangeBindException` in place of `handleMethodArgumentNotValid`, return `Mono<ResponseEntity<Object>>`, and drop the JDBC rows - R2DBC failures arrive already translated as `DataAccessException`, never `SQLException`.

## Patterns

### Domain exception hierarchy

```java
public abstract class DomainException extends RuntimeException {
    private final HttpStatus status;
    private final String errorCode;

    protected DomainException(String msg, HttpStatus status, String errorCode) {
        super(msg); this.status = status; this.errorCode = errorCode;
    }
    protected DomainException(String msg, Throwable cause, HttpStatus status, String errorCode) {
        super(msg, cause); this.status = status; this.errorCode = errorCode;
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

Extend `ResponseEntityExceptionHandler`: a standalone advice with a bare `@ExceptionHandler(Exception.class)` intercepts framework exceptions (405, 415, `NoResourceFoundException`, ...) before Spring's default handling and collapses them to 500, contradicting the mapping table.

```java
@RestControllerAdvice
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(DomainException.class)
    ProblemDetail handleDomain(DomainException ex) {
        if (ex.getStatus().is5xxServerError()) log.error("{}", ex.getErrorCode(), ex);  // wrapped upstream failures are unexpected
        else log.warn("{}: {}", ex.getErrorCode(), ex.getMessage());
        return problem(ex.getStatus(), ex.getErrorCode(), ex.getMessage());
    }

    // ResponseEntityExceptionHandler already claims MethodArgumentNotValidException -
    // override it; re-declaring it via @ExceptionHandler fails startup (ambiguous mapping)
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        var pd = problem(BAD_REQUEST, "VALIDATION_FAILED", "Request validation failed");
        pd.setProperty("fieldErrors", ex.getBindingResult().getFieldErrors().stream()
            .collect(toMap(FieldError::getField, FieldError::getDefaultMessage, (a, b) -> a)));
        return ResponseEntity.badRequest().body(pd);
    }

    // param/path-variable validation - not covered by ResponseEntityExceptionHandler
    @ExceptionHandler(ConstraintViolationException.class)
    ProblemDetail handleConstraint(ConstraintViolationException ex) {
        return problem(BAD_REQUEST, "VALIDATION_FAILED", ex.getMessage());
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail handleUnexpected(Exception ex) {
        log.error("Unexpected error", ex);
        return problem(INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "An unexpected error occurred");
    }

    // Framework exceptions the superclass renders arrive without `code`, so clients that
    // parse it see two envelope shapes. Decorate every body on the way out.
    @Override
    protected ResponseEntity<Object> createResponseEntity(Object body, HttpHeaders headers,
            HttpStatusCode status, WebRequest request) {
        if (body instanceof ProblemDetail pd && (pd.getProperties() == null || !pd.getProperties().containsKey("code"))) {
            decorate(pd, status.is5xxServerError() ? "INTERNAL_ERROR" : "REQUEST_REJECTED");
        }
        return super.createResponseEntity(body, headers, status, request);
    }

    static ProblemDetail problem(HttpStatus status, String code, String detail) {
        return decorate(ProblemDetail.forStatusAndDetail(status, detail), code);
    }

    // Package-private, not inlined into the advice: the security entry point writes bodies
    // from inside the filter chain and must emit the identical envelope.
    static ProblemDetail decorate(ProblemDetail pd, String code) {
        pd.setType(URI.create("urn:problem:" + code.toLowerCase().replace('_', '-')));  // RFC 9457 machine id
        pd.setTitle(HttpStatus.valueOf(pd.getStatus()).getReasonPhrase());               // human-readable summary
        pd.setProperty("code", code);                                                    // machine code for clients
        pd.setProperty("traceId", MDC.get("traceId"));  // MVC: MDC filter or Micrometer Tracing. On WebFlux MDC is
        return pd;                                      // thread-local and unreliable - use the exchange id or Tracer.
    }
}
```

The `DomainException` handler covers every subclass via Spring's most-specific-type resolution; no per-subclass handler needed.

Replacing a custom envelope on a live API: `ProblemDetail` extension properties serialize as top-level fields, so a `code`/`message` contract survives by adding those properties. The breaking change is the `Content-Type` flip to `application/problem+json` - confirm each consumer before shipping.

### Wrapping vendor SDK errors

Classify at the boundary; callers see domain types only. Author the wrapper's message at the boundary - never pass the vendor exception's `getMessage()` through as the domain message (it becomes client-visible `ProblemDetail.detail`); keep the vendor exception as `cause` for logs.

```java
@Component
class StripePaymentGateway implements PaymentGateway {
    public PaymentResult charge(PaymentRequest req) {
        try {
            return PaymentResult.success(stripeClient.createCharge(req).getId());
        } catch (CardException e) {                                       // subtype - must precede StripeException
            throw new PaymentDeclinedException(req.orderId(), e.getDeclineCode(), e);   // cause: logs only
        } catch (com.stripe.exception.RateLimitException e) {
            throw new PaymentRetryableException(req.orderId(), e);
        } catch (StripeException e) {
            throw new PaymentGatewayException(req.orderId(), e);
        }
    }
}
```

## Output Format

One block per exception type that reaches the web layer; vendor exceptions wrapped at the boundary are covered by their wrapping domain type's block:

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
