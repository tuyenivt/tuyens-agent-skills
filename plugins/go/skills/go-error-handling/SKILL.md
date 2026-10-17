---
name: go-error-handling
description: "Go errors: explicit returns, %w wrapping, sentinels, custom types, errors.Is/As, Gin error middleware, retryable classification."
metadata:
  category: backend
  tags: [go, error-handling, sentinel-errors, gin, middleware]
user-invocable: false
---

# Go Error Handling

> Load `Use skill: stack-detect` first. This skill reads `Database`; the Go version is the `go` directive in `go.mod` (a `## Tech Stack` `Language:` line may carry a version; the directive wins when they differ). The driver-error example is PostgreSQL on pgx v5 (`github.com/jackc/pgx/v5/pgconn`); on MySQL match `*mysql.MySQLError` and its `Number` (1062 duplicate key, 1452 FK); on `unknown`, keep the PostgreSQL form. Baseline: Go 1.25+ (`log/slog`, multi-`%w`, `errors.Join`), Gin v1.10+, GORM v1.25+ with a dialector implementing `gorm.ErrorTranslator` (postgres, mysql), stripe-go v82.1+ (`stripe.NewClient`).

## When to Use

- Designing error types for a new package or service
- Reviewing error handling
- Implementing centralized error handling in a Gin HTTP service
- Wrapping third-party API errors into domain errors

## Rules

- Check every error; never discard with `_`. Best-effort work still logs its error - `_ =` is reserved for a value already handled
- Wrap with `fmt.Errorf("context: %w", err)` to preserve the chain
- Use `errors.Is` / `errors.As`; never string-match error messages
- Log OR return at each layer, never both - wrapping before returning is returning
- Panic only for programmer bugs at startup, never for business logic
- Map errors at layer boundaries: repo -> service -> HTTP status
- Classify external API errors as retryable, permanent, or indeterminate

## Patterns

### Sentinel Errors

For expected, checkable conditions. A sentinel is a package-level `var`; a function returning a fresh struct value each call (`func ErrNotFound() error { return notFoundError{} }`) is not a sentinel - `errors.Is` compares with `==`, so it matches only while the struct is comparable and every field is equal, an accident of representation rather than an identity.

```go
var (
    ErrNotFound     = errors.New("not found")
    ErrUnauthorized = errors.New("unauthorized")
    ErrForbidden    = errors.New("forbidden")
    ErrConflict     = errors.New("conflict")
)

if errors.Is(err, ErrNotFound) { /* handle */ }
```

### Custom Error Types

When callers read fields off the error (a response body that shows `Remaining`, a validator that names the field). Identity alone (`errors.Is`) means a sentinel - a field-less struct type is overspecification, and one sentinel per distinct handling decision beats one per distinct message.

```go
type ValidationError struct {
    Field, Message string
}
func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation failed on %s: %s", e.Field, e.Message)
}

var ve *ValidationError
if errors.As(err, &ve) { /* ve.Field available */ }
```

### Error Wrapping

```go
// Bad - loses call site
if err != nil { return nil, err }

// Good
if err != nil { return nil, fmt.Errorf("GetUser id=%d: %w", id, err) }
```

Error strings: no trailing punctuation, lowercase unless they begin with an exported identifier (`GetUser id=%d`). Wrap context names the operation, never "failed to ..." - the chain already implies failure and the prefix stutters when every layer adds it.

### Layer Mapping

Each layer wraps with its context; the handler hands the error to the middleware, which maps it to HTTP:

```go
// Repository: data access error
if notFound { return nil, fmt.Errorf("userRepo.Find id=%d: %w", id, ErrNotFound) }

// Service: adds its own context, sentinel preserved through the chain
if err != nil { return nil, fmt.Errorf("promote user %d: %w", id, err) }

// Handler: delegates to centralized middleware; only a binding error is written here (the handler owns that 400's shape)
if err != nil { c.Error(err); return }
```

### Wrapping External API Errors

Third-party SDK error types stop at the gateway; callers depend only on domain sentinels. The cause rides along as `%v`.

```go
var (
    ErrPaymentDeclined = errors.New("payment declined")
    ErrGatewayTimeout  = errors.New("payment gateway timeout")
    ErrGatewayFailure  = errors.New("payment gateway failure")
    ErrRetryable       = errors.New("retryable")
    ErrIndeterminate   = errors.New("outcome indeterminate")
)

// stripe-go v82.1+: client-based API, ctx-first. sc := stripe.NewClient(key)
func (g *stripeGateway) Charge(ctx context.Context, req ChargeRequest) error {
    params := &stripe.PaymentIntentCreateParams{ /* ... */ }
    params.SetIdempotencyKey(req.ID) // the same key on every attempt is what makes a retry safe
    _, err := g.sc.V1PaymentIntents.Create(ctx, params)
    if err == nil { return nil }

    var stripeErr *stripe.Error
    if errors.As(err, &stripeErr) {
        switch stripeErr.Code {
        case stripe.ErrorCodeCardDeclined:
            return fmt.Errorf("charge %s: %w: %v", req.ID, ErrPaymentDeclined, err)
        case stripe.ErrorCodeRateLimit:
            return fmt.Errorf("charge %s: %w: %v", req.ID, ErrRetryable, err)
        }
    }
    // Anything that is not a Stripe-decoded rejection may have reached Stripe: a deadline, a reset
    // connection, the SDK's own timeout, a 5xx after send, a Canceled that fired after the write.
    // All of it is indeterminate - resolve by read or same-key re-send, never a blind retry.
    if stripeErr == nil || stripeErr.HTTPStatusCode >= 500 {
        return fmt.Errorf("charge %s: %w: %w: %v", req.ID, ErrIndeterminate, ErrGatewayTimeout, err)
    }
    // A decoded 4xx Stripe did not match above: %v, not %w - wrapping keeps *stripe.Error matchable
    // by every caller, which is the leak this gateway exists to stop. The text survives for logs.
    return fmt.Errorf("charge %s: %w: %v", req.ID, ErrGatewayFailure, err)
}
```

**Indeterminate** = the call may have taken effect (timeout after send, connection reset, 5xx after a write). Resolve a call that got no response (timeout, reset) by re-sending with the same idempotency key - Stripe replays the stored result for at least 24h, a 5xx included, so a decoded 5xx is resolved by a read instead: a reference you set (`metadata`, `transfer_group`, a search by your order id - eventually consistent) or the webhook; Stripe has no lookup by idempotency key. Never a blind retry - that is how a capture gets charged twice. `context.Canceled` is `No` only when checked before the SDK call is made; after the call it is `Indeterminate` like the rest.

### Code-Based SDK Errors

Not every dependency exposes a matchable type. Extract the code first, then map it:

```go
var ErrUpstreamDown = errors.New("upstream unavailable")

// gRPC - status.Code returns codes.Unknown for non-status errors, so it is safe as the discriminator
switch status.Code(err) {
case codes.NotFound:    return fmt.Errorf("%s: %w: %v", op, ErrNotFound, err)
case codes.Unavailable: return fmt.Errorf("%s: %w: %w: %v", op, ErrRetryable, ErrUpstreamDown, err)
}

// Postgres - SQLSTATE off the driver error (pgx v5: github.com/jackc/pgx/v5/pgconn)
var pgErr *pgconn.PgError
if errors.As(err, &pgErr) && pgErr.Code == pgerrcode.UniqueViolation { // "23505"
    return fmt.Errorf("%s: %w: %v", op, ErrConflict, err)
}
```

With `gorm.Config{TranslateError: true}` GORM replaces the driver error with `gorm.ErrDuplicatedKey` / `gorm.ErrForeignKeyViolated`; match those with `errors.Is` instead - `errors.As(&pgErr)` never fires.

### Retryable Classification (multi-`%w`, Go 1.20+)

```go
// %w twice lets one error match two sentinels
return fmt.Errorf("%w: %w", ErrRetryable, cause)
// caller: if errors.Is(err, ErrRetryable) { retry }
```

Markers come first, the cause last. When the last `%w` is a domain sentinel rather than the original error, keep the cause with a trailing `%v` (`"%s: %w: %w: %v", op, ErrRetryable, ErrUpstreamDown, err`) - a chain of markers alone leaves the operator nothing to log.

### Aggregate Errors (`errors.Join`, Go 1.20+)

Collect-all semantics (batch items, multi-field validation, parallel results). Carry the item's identity in a typed wrapper so the aggregate can be decomposed without parsing text:

```go
type ItemError struct { ID string; Err error }
func (e *ItemError) Error() string { return fmt.Sprintf("record %s: %s", e.ID, e.Err) }
func (e *ItemError) Unwrap() error { return e.Err }

var errs []error
for _, rec := range records {
    if err := process(rec); err != nil {
        errs = append(errs, &ItemError{ID: rec.ID, Err: err})
    }
}
return errors.Join(errs...) // nil when errs is empty
```

`errors.Is`/`As` traverse the joined tree but stop at the **first** match - they answer "does this contain X", never "which items failed". Enumerating means walking both `Unwrap() []error` and `Unwrap() error` yourself.

**Collect-all or fail-fast:** keep going when the failure is scoped to the item (validation, not-found, conflict); abort when it is infrastructure-wide (connection lost, context cancelled, credentials revoked) - one of those means every remaining item fails identically. Mark the abort with its own sentinel so the caller can tell "500 bad rows" from "we stopped at row 12".

### Gin Centralized Error Middleware

```go
func ErrorMiddleware() gin.HandlerFunc {
    return func(c *gin.Context) {
        c.Next()
        if len(c.Errors) == 0 { return }

        err := c.Errors.Last().Err
        if c.Writer.Written() { // handler already responded - a second write corrupts the response
            slog.ErrorContext(c.Request.Context(), "error after response written", "err", err)
            return
        }

        status, msg := http.StatusInternalServerError, "internal server error"
        var ve *ValidationError
        switch {
        case errors.As(err, &ve):
            status, msg = http.StatusBadRequest, ve.Error()
        case errors.Is(err, ErrUnauthorized):
            status, msg = http.StatusUnauthorized, "unauthorized"
        case errors.Is(err, ErrNotFound):
            status, msg = http.StatusNotFound, "not found"
        case errors.Is(err, ErrConflict):
            status, msg = http.StatusConflict, "conflict"
        case errors.Is(err, ErrPaymentDeclined):
            status, msg = http.StatusPaymentRequired, "payment declined"
        case errors.Is(err, ErrForbidden):
            status, msg = http.StatusForbidden, "forbidden"
        case errors.Is(err, ErrIndeterminate):
            status, msg = http.StatusAccepted, "pending" // outcome unknown: hand back the pending resource, never a retryable 5xx
        case errors.Is(err, ErrRetryable), errors.Is(err, ErrGatewayTimeout), errors.Is(err, ErrUpstreamDown):
            status, msg = http.StatusServiceUnavailable, "service temporarily unavailable"
        case errors.Is(err, ErrGatewayFailure):
            status, msg = http.StatusBadGateway, "payment gateway error"
        }
        if status >= 500 { // expected conditions (4xx) are not error-level noise
            slog.ErrorContext(c.Request.Context(), "request failed", "err", err)
        } else {
            slog.WarnContext(c.Request.Context(), "request rejected", "err", err)
        }
        c.JSON(status, gin.H{"error": msg})
    }
}
```

Every sentinel the service can return has a case here; an unmapped expected condition falls to 500 and an error-level log. `gin.Recovery()` records a panic in `c.Errors` only for broken-pipe panics; every other panic becomes a bare `AbortWithStatus(500)` this middleware never sees. Return errors instead of panicking. A handler with partial-success semantics (batch import) writes its own multi-status response and does not call `c.Error` at all; one `c.Errors.Last()` cannot express "412 of 500 rows succeeded".

A webhook handler's status is a protocol: `2xx` acknowledges and the provider stops redelivering, `5xx` asks for redelivery, and a signature failure is `400`; Stripe retries every non-2xx for up to 3 days, so a wrong secret shows as sustained 400s, and the only response that stops redelivery is the 2xx a bad signature must never receive.

## Edge Cases

- `fmt.Errorf("ctx: %w", nil)` returns a non-nil error - guard before wrapping
- Custom error types must not create `Unwrap` cycles (`errors.Is` / `As` would hang)
- Some libraries return values that don't implement `error` - assert at the boundary

## Output Format

Emit these headings, in this order, for the engagement:

| Engagement | Headings |
|------------|----------|
| Design / implementation | `## Error Design` with `### Sentinels`, `### Custom Types`, `### Layer Mapping`, `### External Classification` |
| Review | `## Findings`, then `## Error Design` holding `### Layer Mapping` and, when the input includes an external call, `### External Classification`, both describing the code as it exists today (the target state lives in each finding's `Fix`) |

```
## Error Design

### Sentinels
| Error | Declared In | Matched By |
|-------|-------------|------------|

### Custom Types
| Type | Fields | Used When |
|------|--------|-----------|

### Layer Mapping
| Layer | Input | Output | Surface Result |
|-------|-------|--------|----------------|

### External Classification
| External Error | Domain Error | Retryable? |
|----------------|--------------|------------|
```

Cell values: `Declared In` is the package (one row per sentinel). `Matched By` is `errors.Is` or `errors.As` plus the layer that matches it (`errors.Is, middleware`). Layer Mapping has one row per layer per path through it - `Capture` via HTTP and `Capture` via the worker are two rows. `Input` is the error the layer receives (a driver type, a sentinel from the layer below, a `context` error); `Output` is what it returns (the sentinel or type it wraps to) or `handled (<what is returned instead>)` when it consumes the error. `Surface Result` is what the outermost caller sees on that path - an HTTP status, a worker decision, a CLI exit code, or for a webhook route the status plus `ack` / `redeliver`. Worker decisions are `Retry | Drop | DeadLetter | Resolve`: on Asynq `Retry` = return the error, `Drop` = return nil, `DeadLetter` = wrap `asynq.SkipRetry` (archived at once, no retries), `Resolve` = an indeterminate outcome the handler must look up before deciding; on a Kafka consumer `Drop` = commit, `DeadLetter` = produce to the DLQ topic then commit, `Retry` = re-process in the handler loop with backoff, then `DeadLetter` - an uncommitted record is not redelivered to the same running consumer. `Retryable?` is `Yes | No | Indeterminate`. `External Error` covers anything crossing into the package: third-party SDK, gRPC status, driver/SQLSTATE, `context` errors. A table with no rows emits `None.` rather than being dropped; a cell the input does not supply is `unknown` and a column that does not apply to the row is `n/a`, whichever enum the column carries - a layer the input names but does not show gets one row of `unknown` cells.

Every finding carries exactly one label:

```
## Findings

### [{Must | Recommend}] {file:line | file:start-end | file:<symbol>}

- Defect: {the rule broken}
- Consequence: {what the caller or the operator loses}
- Fix: {concrete edit}
```

`[Must]` when the defect loses information the caller needs (severed chain, swallowed error, string-matched status, a failure after a side effect that is only logged), corrupts state, panics on a reachable path, reaches the client with internal detail, or answers a processed webhook event with a status the sender redelivers; `[Recommend]` otherwise. Cite `file:line` when the input carries line numbers, `file:<symbol>` when it does not; a range is `file:start-end`. Order `[Must]` first, then by file in the order the input listed them, then line. With no findings, `## Findings` holds the single line `None.` One root cause at several sites is one heading citing the first site, with the rest named on the `Defect:` line. A defect this skill does not own (a detached goroutine, a signature computed over the wrong bytes, a transaction held open) is still reported, never dropped: one block per such defect after the owned findings, in the same file-then-line order, labelled by the criteria above, with its `Defect:` line reading `owned by <concern>` in plain words and any enum slot it cannot fill reading `n/a`.

## Avoid

- Discarding errors with `_`
- `panic` for flow control or expected conditions
- Logging and returning at the same layer
- Leaking DB / third-party error types past the gateway
- Generic `errors.New("failed")` with no context
- Blind-retrying an indeterminate outcome
