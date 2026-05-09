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

- Centralizing error handling across REST APIs in Kotlin/Spring
- Mapping business exceptions to appropriate HTTP status codes
- Wrapping third-party API errors (Stripe, payment gateways) into domain exceptions
- Ensuring consistent error response format
- Designing sealed-class error hierarchies for exhaustive `when` handling

## Rules

- Use `@RestControllerAdvice` for centralized exception handling
- No try-catch in controller for business logic
- Map business exceptions to 4xx, system errors to 5xx
- Never expose stack traces to clients
- Use RFC 9457 `ProblemDetail` as the standard error response format (Spring Boot 3.x native support)
- Log system exceptions only, not expected business exceptions
- Use sealed classes for closed error hierarchies when modeling domain results; convert to exceptions at the controller boundary

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

Define a base exception that carries an error code and HTTP status. Make it `open` so subclasses can extend; the `kotlin("plugin.spring")` plugin only opens annotated classes, so domain exceptions need explicit `open`:

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
        HttpStatus.CONFLICT,
        "INSUFFICIENT_STOCK",
    )

class DuplicateEmailException(email: String) :
    DomainException("Email already registered: $email", HttpStatus.CONFLICT, "DUPLICATE_EMAIL")
```

### Sealed Result Hierarchy (Alternative)

For service layers that prefer to return results rather than throw, use sealed classes - the controller converts to HTTP at the boundary:

```kotlin
sealed interface OrderResult {
    data class Success(val order: Order) : OrderResult
    data class NotFound(val id: Long) : OrderResult
    data class InsufficientStock(val sku: String, val available: Int) : OrderResult
    data class Unauthorized(val reason: String) : OrderResult
}

@RestController
class OrderController(private val service: OrderService) {
    @GetMapping("/{id}")
    fun get(@PathVariable id: Long): ResponseEntity<*> = when (val result = service.findById(id)) {
        is OrderResult.Success -> ResponseEntity.ok(result.order.toResponse())
        is OrderResult.NotFound -> throw OrderNotFoundException(result.id)
        is OrderResult.InsufficientStock -> throw InsufficientStockException(result.sku, 0, result.available)
        is OrderResult.Unauthorized -> throw AccessDeniedException(result.reason)
    }
}
```

## Patterns

Bad - Scattered error handling:

```kotlin
@RestController
class UserController(private val userService: UserService) {
    @PostMapping("/users")
    fun createUser(@RequestBody req: UserRequest): ResponseEntity<*> = try {
        ResponseEntity.ok(userService.create(req))
    } catch (e: Exception) {
        ResponseEntity.status(500).body("Error")
    }
}
```

Good - Centralized exception handling with RFC 9457 ProblemDetail.

**Handler precedence:** Spring picks the most specific `@ExceptionHandler` - the one whose declared type is closest to the thrown exception in the type hierarchy. So `handleNotFound(NotFoundException)` wins over `handleDomainException(DomainException)` for a `NotFoundException`, and the catch-all `handleUnexpected(Exception)` only runs when nothing more specific matched. Keep the handlers ordered from most-specific to most-general for readability; the runtime ignores declaration order.

```kotlin
@RestControllerAdvice
class GlobalExceptionHandler {

    private val log = LoggerFactory.getLogger(javaClass)

    // Business exception: 400, no stack trace logged
    @ExceptionHandler(ValidationException::class)
    fun handleValidation(ex: ValidationException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, ex.message ?: "Invalid input").apply {
            title = "Validation Failed"
            setProperty("traceId", MDC.get("traceId"))
        }

    // Domain not found: 404
    @ExceptionHandler(NotFoundException::class)
    fun handleNotFound(ex: NotFoundException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(HttpStatus.NOT_FOUND, ex.message ?: "Not found").apply {
            title = "Resource Not Found"
            setProperty("traceId", MDC.get("traceId"))
        }

    // Generic domain exception handler - catches all DomainException subclasses
    @ExceptionHandler(DomainException::class)
    fun handleDomainException(ex: DomainException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(ex.status, ex.message ?: "Error").apply {
            title = ex.errorCode
            setProperty("traceId", MDC.get("traceId"))
        }

    // Bean validation errors: 400, with per-field details
    @ExceptionHandler(MethodArgumentNotValidException::class)
    fun handleValidationErrors(ex: MethodArgumentNotValidException): ProblemDetail =
        ProblemDetail.forStatus(HttpStatus.BAD_REQUEST).apply {
            title = "Validation Failed"
            setProperty("traceId", MDC.get("traceId"))
            setProperty(
                "fieldErrors",
                ex.bindingResult.fieldErrors.associate { it.field to (it.defaultMessage ?: "invalid") },
            )
        }

    // Database constraint violation: 409 (e.g., unique constraint on email, SKU)
    @ExceptionHandler(DataIntegrityViolationException::class)
    fun handleDataIntegrity(ex: DataIntegrityViolationException): ProblemDetail {
        log.warn("Data integrity violation: {}", ex.mostSpecificCause.message)
        return ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, "A record with the given value already exists").apply {
            title = "Conflict"
            setProperty("traceId", MDC.get("traceId"))
        }
    }

    // Optimistic lock conflict: 409 with retry hint
    // Both Spring's OptimisticLockingFailureException and JPA's ObjectOptimisticLockingFailureException land here.
    @ExceptionHandler(OptimisticLockingFailureException::class)
    fun handleOptimisticLock(ex: OptimisticLockingFailureException): ProblemDetail {
        log.warn("Optimistic lock conflict: {}", ex.message)
        return ProblemDetail.forStatusAndDetail(HttpStatus.CONFLICT, "The resource was modified concurrently. Reload and retry.").apply {
            title = "Concurrent Modification"
            setProperty("traceId", MDC.get("traceId"))
            setProperty("retryable", true)
        }
    }

    // Malformed JSON / type mismatch on @RequestBody: 400, not 500
    @ExceptionHandler(HttpMessageNotReadableException::class)
    fun handleUnreadable(ex: HttpMessageNotReadableException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, "Request body is missing or malformed").apply {
            title = "Bad Request"
            setProperty("traceId", MDC.get("traceId"))
        }

    // Path / query parameter bean validation (Spring 6 / Boot 3) - separate from @RequestBody validation above
    @ExceptionHandler(HandlerMethodValidationException::class)
    fun handleParamValidation(ex: HandlerMethodValidationException): ProblemDetail =
        ProblemDetail.forStatusAndDetail(HttpStatus.BAD_REQUEST, "Invalid request parameters").apply {
            title = "Validation Failed"
            setProperty("traceId", MDC.get("traceId"))
            setProperty(
                "paramErrors",
                ex.allValidationResults.flatMap { r ->
                    r.resolvableErrors.map { e -> r.methodParameter.parameterName to (e.defaultMessage ?: "invalid") }
                }.toMap(),
            )
        }

    // System exception: 500, log with stack trace
    @ExceptionHandler(Exception::class)
    fun handleUnexpected(ex: Exception): ProblemDetail {
        log.error("Unexpected error", ex)
        return ProblemDetail.forStatus(HttpStatus.INTERNAL_SERVER_ERROR).apply {
            detail = "An unexpected error occurred"
            setProperty("traceId", MDC.get("traceId"))
        }
    }
}
```

### Wrapping External API Errors

Third-party APIs (Stripe, payment gateways, etc.) return their own exception types. Wrap them into domain exceptions at the integration boundary so callers never depend on the external library:

```kotlin
// Bad: leaking Stripe exception into service layer
@Service
class PaymentService(private val stripeClient: StripeClient) {
    fun charge(req: PaymentRequest): PaymentResult = stripeClient.charge(req) // caller must import com.stripe.exception
}

// Good: classify and wrap at the boundary
@Component
class StripePaymentGateway(private val stripeClient: StripeClient) : PaymentGateway {

    override fun charge(req: PaymentRequest): PaymentResult = try {
        val charge = stripeClient.createCharge(req.amount, req.currency)
        PaymentResult.success(charge.id)
    } catch (e: CardException) {
        throw PaymentDeclinedException(req.orderId, e.declineCode)
    } catch (e: StripeRateLimitException) {
        throw PaymentRetryableException(req.orderId, "Rate limited", e)
    } catch (e: StripeException) {
        throw PaymentGatewayException(req.orderId, e.message ?: "Stripe failure", e)
    }
}
```

### Retryable vs Permanent Error Classification

When calling external services, callers need to know whether to retry. Use a marker `open class` (Kotlin requires explicit `open`):

```kotlin
open class RetryableException(
    message: String,
    status: HttpStatus,
    errorCode: String,
) : DomainException(message, status, errorCode) {
    open val isRetryable: Boolean = true
}

class PaymentRetryableException(orderId: Long, reason: String, cause: Throwable) :
    RetryableException(
        "Payment temporarily failed for order $orderId: $reason",
        HttpStatus.SERVICE_UNAVAILABLE,
        "PAYMENT_RETRYABLE",
    ) {
    init { initCause(cause) }
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
- `runCatching { }.getOrThrow()` chains that discard the original exception type - preserve the cause
