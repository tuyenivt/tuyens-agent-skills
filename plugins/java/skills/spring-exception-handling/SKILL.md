---
name: spring-exception-handling
description: "Centralized REST error handling with @RestControllerAdvice and ProblemDetail (RFC 9457): domain exception hierarchy, HTTP mapping, vendor wrapping."
metadata:
  category: backend
  tags: [error-handling, rest, http, controller]
user-invocable: false
---

# Exception Handling

> Load `Use skill: stack-detect` first to confirm Spring Boot; then read the build file's starters yourself - stack-detect does not report them. MVC vs WebFlux decides the base class and several rows: WebFlux when `spring-boot-starter-webflux` is declared without `spring-boot-starter-webmvc` (or its deprecated name `spring-boot-starter-web`). The 401/403 rows apply when any Spring Security starter is present (`spring-boot-starter-security`, `-security-oauth2-resource-server`, `-security-oauth2-client`, or the deprecated `-oauth2-*` names). Written for Spring Framework 7 / Boot 4.

## When to Use

- Centralizing REST error handling; migrating a custom error envelope to `ProblemDetail`
- Mapping business and framework exceptions to HTTP status codes
- Wrapping third-party SDK errors at the integration boundary
- Reviewing existing error handling

## Rules

- Outside the security filter chain, `@RestControllerAdvice` is the only place that maps exceptions to HTTP; controllers and services throw, never catch for response shaping. Inside the chain, the `AuthenticationEntryPoint` and `AccessDeniedHandler` write the same envelope via the shared helper
- Business exceptions extend one `DomainException` base carrying `HttpStatus` and `errorCode`; one handler covers the hierarchy
- Response body is `ProblemDetail` (RFC 9457), produced by an advice that extends `ResponseEntityExceptionHandler`; also set `spring.mvc.problemdetails.enabled: true` (WebFlux: `spring.webflux.problemdetails.enabled`) as the fallback - it is inert while the advice exists
- Log unexpected failures (5xx) at `ERROR` with stack trace; expected transient upstream failures (503) and client errors (4xx, access denials included) at `WARN` or below; expected authentication failures at `DEBUG` or not at all. `Logged` records the level where the exception is finally logged (for security rows, the entry point / denied handler). Never leak stack traces, exception class names, or vendor/parser messages to clients
- Error codes are UPPER_SNAKE_CASE, prefixed by the domain noun (`ORDER_NOT_FOUND`, `PAYMENT_DECLINED`)
- Wrap vendor SDK exceptions at the integration boundary so callers depend only on domain types; the boundary authors the client-visible message
- Catching an exception only to log it and carry on hides a failure the caller needed - rethrow, translate, or record a failure state

## Exception to HTTP Mapping

| Exception                                                | Status |
| -------------------------------------------------------- | ------ |
| `MethodArgumentNotValidException`, `HandlerMethodValidationException`, `jakarta.validation.ConstraintViolationException`, `HttpMessageNotReadableException`, `MethodArgumentTypeMismatchException`, `MissingServletRequestParameterException`, `ServletRequestBindingException` | 400 |
| Webhook signature verification failure (domain)          | 400 - the provider must not keep retrying a forged payload |
| `AuthenticationException` (from the filter chain)        | 401    |
| `PaymentDeclinedException` (domain)                      | 402    |
| `AccessDeniedException` (filter chain or `@PreAuthorize`) | 403 (authenticated); 401 via the entry point (anonymous) |
| `DomainException` subtype built with `NOT_FOUND`; `NoResourceFoundException`, `NoHandlerFoundException` | 404 |
| `HttpRequestMethodNotSupportedException`                 | 405    |
| `HttpMediaTypeNotAcceptableException`                    | 406    |
| `DomainException` subtype built with `CONFLICT` (state conflict: duplicate key, stock, version); `OptimisticLockingFailureException` | 409 |
| `MaxUploadSizeExceededException`                         | 413    |
| `HttpMediaTypeNotSupportedException`                     | 415    |
| `DomainException` subtype built with `UNPROCESSABLE_ENTITY` (well-formed request violating a business rule regardless of current state) | 422 |
| `RateLimitedException` (domain - *our* throttle, not an upstream 429) | 429 |
| Unhandled `Exception`, unclassified `DataIntegrityViolationException` | 500 |
| Vendor-gateway wrapper (unclassified upstream failure, e.g. `PaymentGatewayException`) | 502 |
| `RetryableException` subtypes (transient upstream failure) | 503  |

- **502 vs 503 at the integration boundary, on the cause.** Timeout, connection failure, upstream 429 and upstream 5xx are transient -> `RetryableException` -> 503. Everything else the vendor returns is unclassified -> gateway wrapper -> 502. An upstream 429 never becomes our 429 (the client is not throttled). An upstream 400 means our request was malformed - our bug, 502 plus an ERROR log. Classify by exception type or by the status code the SDK exposes, whichever it offers.
- **`DataIntegrityViolationException` is translated where the write happens.** Identify the constraint by name - the cause's `org.hibernate.exception.ConstraintViolationException.getConstraintName()` (JPA; match by suffix, MySQL/Oracle qualify it) or the SQLSTATE of an R2DBC cause; the name comes from the migration that created it. A constraint the client can act on (unique key) becomes a `CONFLICT` domain exception; everything else (FK to a missing parent, NOT NULL) stays 500 - it is our bug.
- **409 vs 422.** 409 when the request collides with current state that can change (duplicate, out of stock, stale version); 422 when it violates a rule no state change would satisfy.
- **Method validation (Framework 6.1+ / Boot 3.2+):** constraints on `@RequestParam`/`@PathVariable`/`@RequestHeader` parameters raise `HandlerMethodValidationException` - and once a handler has one, its `@Valid @RequestBody` errors raise it too. Override `handleHandlerMethodValidationException` so both shapes share one body. `ConstraintViolationException` reaches the advice only from `@Validated` beans (AOP method validation).
- **Security exceptions.** Filter-chain failures (bad or expired token, URL-level denial) never reach the advice - the entry point and denied handler render them. Method-security denials (`@PreAuthorize` throws `AuthorizationDeniedException`, Security 6.3+) and `AuthenticationCredentialsNotFoundException` do reach an `@ExceptionHandler`; rethrow them from the advice so `ExceptionTranslationFilter` picks 401 (anonymous) or 403 (authenticated) and writes the entry-point envelope. A catch-all `@ExceptionHandler(Exception.class)` without that rethrow turns every denial into a 500.
- **WebFlux.** Extend `org.springframework.web.reactive.result.method.annotation.ResponseEntityExceptionHandler`; every `WebRequest` parameter becomes `ServerWebExchange` and return types become `Mono<ResponseEntity<Object>>`; override `handleWebExchangeBindException` for body validation. Servlet rows swap for their reactive equivalents: `WebExchangeBindException` (400), `ServerWebInputException` / `MissingRequestValueException` (400), `MethodNotAllowedException` (405), `NotAcceptableStatusException` (406), `UnsupportedMediaTypeStatusException` (415), the reactive `NoResourceFoundException` (404); there is no multipart-size 413 row. `DataAccessException` rows stay - `DatabaseClient` translates R2DBC errors. Security: `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler`.

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

// Intermediate abstracts fix the status per family; callers branch on type, never on messages
public abstract class NotFoundException extends DomainException {
    protected NotFoundException(String msg, String code) { super(msg, NOT_FOUND, code); }
}
public abstract class RetryableException extends DomainException {
    protected RetryableException(String msg, Throwable cause, String code) { super(msg, cause, SERVICE_UNAVAILABLE, code); }
}

public final class OrderNotFoundException extends NotFoundException {
    public OrderNotFoundException(Long id) { super("Order not found: " + id, "ORDER_NOT_FOUND"); }
}
```

### Global handler (MVC)

Extend `ResponseEntityExceptionHandler`: a standalone advice with a bare `@ExceptionHandler(Exception.class)` intercepts framework exceptions (405, 415, `NoResourceFoundException`, ...) before Spring's default handling and collapses them to 500.

```java
@RestControllerAdvice
public class GlobalExceptionHandler extends ResponseEntityExceptionHandler {
    private static final Logger log = LoggerFactory.getLogger(GlobalExceptionHandler.class);

    @ExceptionHandler(DomainException.class)
    ProblemDetail handleDomain(DomainException ex) {
        if (ex.getStatus().is5xxServerError() && !(ex instanceof RetryableException)) log.error("{}", ex.getErrorCode(), ex);
        else log.warn("{}: {}", ex.getErrorCode(), ex.getMessage());
        return ProblemDetails.of(ex.getStatus(), ex.getErrorCode(), ex.getMessage());
    }

    @ExceptionHandler(OptimisticLockingFailureException.class)
    ProblemDetail handleStale(OptimisticLockingFailureException ex) {
        log.warn("Concurrent modification", ex);
        return ProblemDetails.of(CONFLICT, "CONCURRENT_MODIFICATION", "The resource was modified concurrently; reload and retry");
    }

    // Let the security filter chain decide 401 vs 403 and write its envelope
    @ExceptionHandler({AccessDeniedException.class, AuthenticationException.class})
    void rethrowSecurity(RuntimeException ex) { throw ex; }

    // ResponseEntityExceptionHandler already claims these - override, never re-declare
    // (a duplicate @ExceptionHandler fails startup with an ambiguous mapping)
    @Override
    protected ResponseEntity<Object> handleMethodArgumentNotValid(MethodArgumentNotValidException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        var fieldErrors = new LinkedHashMap<String, String>();
        ex.getBindingResult().getFieldErrors().forEach(fe ->
            fieldErrors.putIfAbsent(fe.getField(), Objects.requireNonNullElse(fe.getDefaultMessage(), "invalid")));
        var pd = ProblemDetails.of(BAD_REQUEST, "VALIDATION_FAILED", "Request validation failed");
        pd.setProperty("fieldErrors", fieldErrors);
        return ResponseEntity.badRequest().body(pd);
    }

    @Override   // parameter constraints, and body errors on a handler that has any
    protected ResponseEntity<Object> handleHandlerMethodValidationException(HandlerMethodValidationException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        var fieldErrors = new LinkedHashMap<String, String>();
        ex.getParameterValidationResults().forEach(r -> r.getResolvableErrors().forEach(e ->
            fieldErrors.putIfAbsent(r.getMethodParameter().getParameterName(), Objects.requireNonNullElse(e.getDefaultMessage(), "invalid"))));
        var pd = ProblemDetails.of(BAD_REQUEST, "VALIDATION_FAILED", "Request validation failed");
        pd.setProperty("fieldErrors", fieldErrors);
        return ResponseEntity.badRequest().body(pd);
    }

    @Override   // never echo the parser message - it names internal types
    protected ResponseEntity<Object> handleHttpMessageNotReadable(HttpMessageNotReadableException ex,
            HttpHeaders headers, HttpStatusCode status, WebRequest request) {
        return ResponseEntity.badRequest().body(ProblemDetails.of(BAD_REQUEST, "MALFORMED_REQUEST", "Request body is malformed"));
    }

    // @Validated beans (AOP method validation) - not covered by ResponseEntityExceptionHandler
    @ExceptionHandler(jakarta.validation.ConstraintViolationException.class)
    ProblemDetail handleConstraint(jakarta.validation.ConstraintViolationException ex) {
        var fieldErrors = new LinkedHashMap<String, String>();
        ex.getConstraintViolations().forEach(v -> {
            String path = v.getPropertyPath().toString();
            fieldErrors.putIfAbsent(path.substring(path.lastIndexOf('.') + 1), v.getMessage());
        });
        var pd = ProblemDetails.of(BAD_REQUEST, "VALIDATION_FAILED", "Request validation failed");
        pd.setProperty("fieldErrors", fieldErrors);
        return pd;
    }

    @ExceptionHandler(Exception.class)
    ProblemDetail handleUnexpected(Exception ex) {
        log.error("Unexpected error", ex);
        return ProblemDetails.of(INTERNAL_SERVER_ERROR, "INTERNAL_ERROR", "An unexpected error occurred");
    }

    // Framework exceptions the superclass renders arrive without `code`; add code and traceId, keeping
    // their `type: about:blank` (its title is the reason phrase, so type and title stay consistent)
    @Override
    protected ResponseEntity<Object> createResponseEntity(Object body, HttpHeaders headers,
            HttpStatusCode status, WebRequest request) {
        if (body instanceof ProblemDetail pd && (pd.getProperties() == null || !pd.getProperties().containsKey(ProblemDetails.CODE))) {
            pd.setProperty(ProblemDetails.CODE, status.is5xxServerError() ? "INTERNAL_ERROR" : "REQUEST_REJECTED");
            pd.setProperty("traceId", MDC.get("traceId"));
        }
        return super.createResponseEntity(body, headers, status, request);
    }
}
```

The shared helper lives outside the advice so the security handlers (another package) emit the identical envelope:

```java
public final class ProblemDetails {
    public static final String CODE = "code";   // "errorCode" when preserving a legacy envelope
    private static final String TYPE_BASE = "https://api.example.com/problems/";   // a URI namespace your team owns

    public static ProblemDetail of(HttpStatusCode status, String code, String detail) {
        return decorate(ProblemDetail.forStatusAndDetail(status, detail), code);
    }

    public static ProblemDetail decorate(ProblemDetail pd, String code) {
        pd.setType(URI.create(TYPE_BASE + code.toLowerCase(Locale.ROOT).replace('_', '-')));   // RFC 9457 machine id
        pd.setTitle(HttpStatus.valueOf(pd.getStatus()).getReasonPhrase());                       // human summary
        pd.setProperty(CODE, code);                                                              // machine code for clients
        pd.setProperty("traceId", MDC.get("traceId"));  // MVC. WebFlux: MDC is thread-local - use the exchange/Tracer
        return pd;
    }
}

@Component @RequiredArgsConstructor
class ProblemAuthenticationEntryPoint implements AuthenticationEntryPoint {
    private final JsonMapper mapper;   // Boot's bean carries the ProblemDetail mixin (properties become top-level
                                       // fields); a new JsonMapper() nests them under "properties". Boot 3.x: ObjectMapper

    @Override
    public void commence(HttpServletRequest req, HttpServletResponse res, AuthenticationException ex) throws IOException {
        res.setStatus(401);
        res.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer");   // required on 401; session apps: the scheme they use
        res.setContentType(MediaType.APPLICATION_PROBLEM_JSON_VALUE);
        var pd = ProblemDetails.of(UNAUTHORIZED, "UNAUTHENTICATED", "Authentication required");
        pd.setInstance(URI.create(req.getRequestURI()));        // advice-rendered bodies carry it too
        mapper.writeValue(res.getOutputStream(), pd);
    }
}
// API-only app: .exceptionHandling(e -> e.authenticationEntryPoint(entryPoint).accessDeniedHandler(deniedHandler)),
// and for a JWT resource server also .oauth2ResourceServer(o -> o.authenticationEntryPoint(entryPoint)).
// Form-login app serving an SPA: scope it so pages keep the login redirect -
//   e.defaultAuthenticationEntryPointFor(entryPoint, PathPatternRequestMatcher.withDefaults().matcher("/api/**"))
//   (Security 6.5+; AntPathRequestMatcher.antMatcher("/api/**") before 6.5).
// The AccessDeniedHandler is the same shape with 403 / "FORBIDDEN", logged at WARN.
```

### Replacing a live envelope

`ProblemDetail` extension properties serialize as top-level fields, so an existing `{errorCode, message}` contract survives by setting properties with those exact names (`ProblemDetails.CODE = "errorCode"`, a `message` property mirroring `detail`) - old clients keep parsing, new clients read RFC 9457 fields. The `Content-Type` flip to `application/problem+json` is the breaking part for clients that check it: `Envelope: additive` only once every consumer is confirmed to accept it, `breaking` otherwise.

### Wrapping vendor SDK errors

Classify at the boundary; callers see domain types only. Author the wrapper's message at the boundary - never pass the vendor's `getMessage()` through as `detail`; keep the vendor exception as `cause` for logs. Decline reasons reach clients through an allowlist (`insufficient_funds`, `expired_card`, `incorrect_cvc`, ...); every other vendor reason becomes a generic decline. A 503 for a non-idempotent vendor call (payment create) is safe only when the call carries a stable idempotency key - the timed-out request may have succeeded.

```java
@Component @RequiredArgsConstructor
class StripePaymentGateway implements PaymentGateway {
    private final StripeClient stripe;

    public PaymentResult charge(PaymentRequest req) {
        try {
            var opts = RequestOptions.builder().setIdempotencyKey("order-" + req.orderId()).build();
            return PaymentResult.success(stripe.paymentIntents().create(toParams(req), opts).getId());
        } catch (CardException e) {                                   // decline - subtypes before StripeException
            throw new PaymentDeclinedException(req.orderId(), publicDeclineCode(e.getDeclineCode()), e);
        } catch (RateLimitException | ApiConnectionException e) {     // upstream 429, network failure, timeout
            throw new PaymentRetryableException(req.orderId(), e);
        } catch (ApiException e) {                                    // Stripe-side error
            if (e.getStatusCode() == null || e.getStatusCode() >= 500) throw new PaymentRetryableException(req.orderId(), e);
            throw new PaymentGatewayException(req.orderId(), e);
        } catch (StripeException e) {                                 // everything else: unclassified
            throw new PaymentGatewayException(req.orderId(), e);
        }
    }
}
```

## Output Format

In every mode, emit the `**Stack:**` line once, then one block per exception type that reaches the web layer or the security handlers in the target design - including types today's code never lets reach it; vendor exceptions wrapped at the boundary are covered by their wrapping domain type's block. When reviewing, the consuming workflow owns the finding envelope; invoked standalone, list findings first - `### [Must|Recommend] file:line` (pasted input: `Class.method`), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when an error leaks internals, lands in the wrong status class (4xx vs 5xx), or is swallowed, `[Recommend]` otherwise (a wrong code within the right class included) - then the blocks as the target state, carrying the current value as `was: ...` in each slot that changes. A finding that is not a mapping (a swallowed exception) has no block.

```
**Stack:** {Spring MVC | WebFlux}{ + Spring Security}
```

```
Exception: {fully-qualified class | AuthenticationEntryPoint - <trigger> | AccessDeniedHandler - <trigger>}

HTTP Status: {code and reason}

Error Code: {domain code}

Logged: {ERROR | WARN | INFO | DEBUG | none}

Response Detail: {client-visible message}
```

When the change replaces an existing error envelope, close with one line: `Envelope: {unchanged | additive - <legacy fields kept> | breaking - <what clients must change>}`.

## Avoid

- Try/catch in controllers for response shaping
- Custom error envelopes when `ProblemDetail` is available
- Logging expected client errors (400, 404, 409) at `ERROR`
- Leaking vendor exception types or messages past the integration boundary
- A catch-all `@ExceptionHandler(Exception.class)` that also swallows security exceptions
- Per-subclass handlers when the `DomainException` base handler suffices
