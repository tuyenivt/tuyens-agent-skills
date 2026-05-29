---
name: kotlin-spring-exception-handling
description: Kotlin / Spring exception handling: @RestControllerAdvice, ProblemDetail (RFC 9457), sealed domain exceptions, HTTP status mapping, consistent errors.
metadata:
  category: backend
  tags: [kotlin, error-handling, rest, http, controller, sealed-class]
user-invocable: false
---

# Kotlin Exception Handling

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Centralizing error handling in Kotlin / Spring REST APIs
- Mapping domain exceptions to HTTP status codes
- Wrapping third-party API errors into domain types
- Designing sealed-class result hierarchies

## Rules

- `@RestControllerAdvice` for centralized handling. No try/catch in controllers for business logic.
- `ProblemDetail` (RFC 9457) as the response format. Spring Boot 3.x has native support.
- Business exceptions: 4xx, no stack trace logged. System exceptions: 5xx, log with stack trace.
- Never expose stack traces or internal details to clients.
- Domain exceptions: `open` base class (kotlin-spring plugin only opens annotated classes).
- Wrap third-party exceptions at the integration boundary. Callers should not import Stripe/AWS/etc. types.
- Sealed-class results when callers programmatically branch on multiple failure modes; otherwise throw.

## Domain exception → HTTP status

| Exception                                       | HTTP                      | When                                                  |
| ----------------------------------------------- | ------------------------- | ----------------------------------------------------- |
| `ValidationException`                           | 400 Bad Request           | Input validation failure                              |
| `AuthenticationException`                       | 401 Unauthorized          | Missing / invalid credentials                         |
| `AccessDeniedException`                         | 403 Forbidden             | Authenticated, not authorized                         |
| `NotFoundException` / `EntityNotFoundException` | 404 Not Found             | Resource does not exist                               |
| `ConflictException`                             | 409 Conflict              | Duplicate / optimistic lock                           |
| `UnprocessableEntityException`                  | 422 Unprocessable Entity  | Valid format, invalid business state                  |
| `RateLimitException`                            | 429 Too Many Requests     | Rate limit exceeded                                   |
| Unexpected `RuntimeException`                   | 500 Internal Server Error | System failure - log with stack trace                 |

## Patterns

### Domain exception hierarchy

```kotlin
abstract class DomainException(
    message: String,
    val status: HttpStatus,
    val errorCode: String,
) : RuntimeException(message)

class OrderNotFoundException(id: Long) :
    DomainException("Order not found: $id", HttpStatus.NOT_FOUND, "ORDER_NOT_FOUND")

class InsufficientStockException(sku: String, requested: Int, available: Int) :
    DomainException(
        "Insufficient stock for $sku: requested $requested, available $available",
        HttpStatus.CONFLICT, "INSUFFICIENT_STOCK",
    )
```

### Sealed result hierarchy (alternative)

When callers branch on multiple distinct failures, return a sealed type and convert at the controller boundary:

```kotlin
sealed interface OrderResult {
    data class Success(val order: Order) : OrderResult
    data class NotFound(val id: Long) : OrderResult
    data class InsufficientStock(val sku: String, val available: Int) : OrderResult
}

@GetMapping("/{id}")
fun get(@PathVariable id: Long): ResponseEntity<*> = when (val r = service.findById(id)) {
    is OrderResult.Success -> ResponseEntity.ok(r.order.toResponse())
    is OrderResult.NotFound -> throw OrderNotFoundException(r.id)
    is OrderResult.InsufficientStock -> throw InsufficientStockException(r.sku, 0, r.available)
}
```

### `@RestControllerAdvice`

Spring picks the most specific `@ExceptionHandler` by exception-type hierarchy - declaration order doesn't matter, but order most-specific to most-general for readability.

```kotlin
@RestControllerAdvice
class GlobalExceptionHandler {
    private val log = LoggerFactory.getLogger(javaClass)

    @ExceptionHandler(NotFoundException::class)
    fun handleNotFound(ex: NotFoundException): ProblemDetail =
        problem(HttpStatus.NOT_FOUND, "Resource Not Found", ex.message ?: "Not found")

    @ExceptionHandler(DomainException::class)
    fun handleDomain(ex: DomainException): ProblemDetail =
        problem(ex.status, ex.errorCode, ex.message ?: "Error")

    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleBeanValidation(ex: MethodArgumentNotValidException): ProblemDetail =
        problem(HttpStatus.BAD_REQUEST, "Validation Failed", "Invalid request body").apply {
            setProperty("fieldErrors",
                ex.bindingResult.fieldErrors.associate { it.field to (it.defaultMessage ?: "invalid") })
        }

    @ExceptionHandler(HandlerMethodValidationException::class)        // Spring 6 path/query validation
    fun handleParamValidation(ex: HandlerMethodValidationException): ProblemDetail =
        problem(HttpStatus.BAD_REQUEST, "Validation Failed", "Invalid request parameters")

    @ExceptionHandler(DataIntegrityViolationException::class)
    fun handleDataIntegrity(ex: DataIntegrityViolationException): ProblemDetail {
        log.warn("integrity violation: {}", ex.mostSpecificCause.message)
        return problem(HttpStatus.CONFLICT, "Conflict", "A record with this value already exists")
    }

    @ExceptionHandler(OptimisticLockingFailureException::class)       // includes ObjectOptimisticLockingFailureException
    fun handleOptimisticLock(ex: OptimisticLockingFailureException): ProblemDetail {
        log.warn("optimistic lock: {}", ex.message)
        return problem(HttpStatus.CONFLICT, "Concurrent Modification",
            "The resource was modified concurrently. Reload and retry.")
            .apply { setProperty("retryable", true) }
    }

    @ExceptionHandler(HttpMessageNotReadableException::class)
    fun handleUnreadable(ex: HttpMessageNotReadableException): ProblemDetail =
        problem(HttpStatus.BAD_REQUEST, "Bad Request", "Request body is missing or malformed")

    @ExceptionHandler(Exception::class)
    fun handleUnexpected(ex: Exception): ProblemDetail {
        log.error("unexpected error", ex)
        return problem(HttpStatus.INTERNAL_SERVER_ERROR, "Server Error", "An unexpected error occurred")
    }

    private fun problem(status: HttpStatus, title: String, detail: String): ProblemDetail =
        ProblemDetail.forStatusAndDetail(status, detail).apply {
            this.title = title
            setProperty("traceId", MDC.get("traceId"))
        }
}
```

### Wrap third-party errors at the boundary

```kotlin
@Component
class StripePaymentGateway(private val stripe: StripeClient) : PaymentGateway {
    override fun charge(req: PaymentRequest): PaymentResult = try {
        PaymentResult.success(stripe.createCharge(req.amount, req.currency).id)
    } catch (e: CardException) {
        throw PaymentDeclinedException(req.orderId, e.declineCode)
    } catch (e: StripeRateLimitException) {
        throw PaymentRetryableException(req.orderId, "Rate limited", e)
    } catch (e: StripeException) {
        throw PaymentGatewayException(req.orderId, e.message ?: "Stripe failure", e)
    }
}
```

### Retryable vs permanent

Mark transient failures with `HttpStatus.SERVICE_UNAVAILABLE` + a retryable error code; set `retryable=true` property on `ProblemDetail` so clients can backoff vs give up.

Enable globally: `spring.mvc.problemdetails.enabled: true`.

## Output Format

```
Exception: {class}
HTTP Status: {code and name}
Error Code: {domain code}
Logged: {yes (ERROR) | yes (WARN) | no}
Response Detail: {client-visible}
```

## Avoid

- Try/catch in controllers
- Exposing stack traces or internal details
- 200 status with error payloads
- Custom error format when ProblemDetail covers it
- Logging expected business exceptions (404, 400) as ERROR
- `runCatching { }.getOrThrow()` chains that drop the original cause
