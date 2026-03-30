---
name: go-testing-patterns
description: "Go testing: table-driven tests, httptest for Gin handlers and webhooks, testcontainers-go for integration, testify, interface mocking, t.Parallel, test fixtures, benchmarks, and testing/synctest."
metadata:
  category: backend
  tags: [go, testing, httptest, testcontainers, testify, benchmarks]
user-invocable: false
---

# Go Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing a test strategy for a new Go service
- Writing unit tests for handlers, services, or domain logic
- Writing integration tests against a real PostgreSQL database
- Testing webhook handlers with signature validation
- Reviewing test quality - coverage gaps, brittle tests, or slow suites

## Rules

- Table-driven tests for all functions with multiple input/output cases
- Use `require` (stops test on failure) for setup assertions; use `assert` (continues) for all other assertions
- Use `t.Parallel()` on all independent tests - it's opt-in and fast tests get faster
- Mock via interfaces defined in the consumer package - never mock concrete types or the database directly
- Use `testcontainers-go` for integration tests that need a real database - never `time.Sleep` for async assertions
- Test public behavior, not private implementation - if you're testing a private function, the package design may need rethinking

## Patterns

### Table-Driven Tests

```go
func TestValidateEmail(t *testing.T) {
    t.Parallel()

    tests := []struct {
        name    string
        email   string
        wantErr bool
    }{
        {name: "valid email", email: "user@example.com", wantErr: false},
        {name: "missing @", email: "userexample.com", wantErr: true},
        {name: "empty string", email: "", wantErr: true},
        {name: "subdomain", email: "user@mail.example.com", wantErr: false},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            err := ValidateEmail(tt.email)
            if tt.wantErr {
                require.Error(t, err)
            } else {
                require.NoError(t, err)
            }
        })
    }
}
```

### Table-Driven Tests for State Transitions

When testing state machines (e.g., payment status), cover all valid and invalid transitions:

```go
func TestPaymentTransition(t *testing.T) {
    t.Parallel()

    tests := []struct {
        name      string
        from      string
        to        string
        wantErr   bool
        errTarget error
    }{
        {name: "pending to processing", from: "pending", to: "processing", wantErr: false},
        {name: "processing to completed", from: "processing", to: "completed", wantErr: false},
        {name: "processing to failed", from: "processing", to: "failed", wantErr: false},
        {name: "pending to completed (skip)", from: "pending", to: "completed", wantErr: true, errTarget: ErrInvalidTransition},
        {name: "completed to pending (reverse)", from: "completed", to: "pending", wantErr: true, errTarget: ErrInvalidTransition},
    }

    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            svc := NewPaymentService(mockRepo(tt.from))
            err := svc.Transition(context.Background(), "pay_123", tt.to)
            if tt.wantErr {
                require.Error(t, err)
                assert.ErrorIs(t, err, tt.errTarget)
            } else {
                require.NoError(t, err)
            }
        })
    }
}
```

### Handler Tests with httptest

Test Gin handlers without starting a real server:

```go
func TestGetUser_Found(t *testing.T) {
    t.Parallel()

    mockSvc := &MockUserService{
        GetUserFn: func(ctx context.Context, id string) (*User, error) {
            return &User{ID: id, Name: "Alice"}, nil
        },
    }

    r := gin.New()
    r.GET("/users/:id", GetUser(mockSvc))

    w := httptest.NewRecorder()
    req := httptest.NewRequest(http.MethodGet, "/users/123", nil)
    r.ServeHTTP(w, req)

    require.Equal(t, http.StatusOK, w.Code)

    var resp SuccessResponse
    require.NoError(t, json.Unmarshal(w.Body.Bytes(), &resp))
    assert.Equal(t, "Alice", resp.Data.(map[string]any)["name"])
}

func TestGetUser_NotFound(t *testing.T) {
    t.Parallel()

    mockSvc := &MockUserService{
        GetUserFn: func(ctx context.Context, id string) (*User, error) {
            return nil, ErrNotFound
        },
    }

    r := gin.New()
    r.Use(ErrorHandler())
    r.GET("/users/:id", GetUser(mockSvc))

    w := httptest.NewRecorder()
    req := httptest.NewRequest(http.MethodGet, "/users/999", nil)
    r.ServeHTTP(w, req)

    assert.Equal(t, http.StatusNotFound, w.Code)
}
```

### Webhook Handler Tests (Signature Validation)

Webhook handlers require testing with raw bodies and valid/invalid signatures:

```go
func TestStripeWebhook_ValidSignature(t *testing.T) {
    t.Parallel()

    secret := "whsec_test_secret"
    payload := []byte(`{"type": "payment_intent.succeeded", "data": {"object": {"id": "pi_123"}}}`)

    // Generate a valid signature (use Stripe's test helper or compute HMAC)
    sig := computeStripeSignature(t, payload, secret)

    mockSvc := &MockPaymentService{
        HandleWebhookEventFn: func(ctx context.Context, event stripe.Event) error {
            assert.Equal(t, "payment_intent.succeeded", event.Type)
            return nil
        },
    }

    r := gin.New()
    r.POST("/webhooks/stripe", WebhookSignature(secret), StripeWebhook(mockSvc))

    w := httptest.NewRecorder()
    req := httptest.NewRequest(http.MethodPost, "/webhooks/stripe", bytes.NewReader(payload))
    req.Header.Set("Stripe-Signature", sig)
    r.ServeHTTP(w, req)

    assert.Equal(t, http.StatusOK, w.Code)
}

func TestStripeWebhook_InvalidSignature(t *testing.T) {
    t.Parallel()

    r := gin.New()
    r.POST("/webhooks/stripe", WebhookSignature("whsec_test"), StripeWebhook(nil))

    w := httptest.NewRecorder()
    req := httptest.NewRequest(http.MethodPost, "/webhooks/stripe", strings.NewReader(`{}`))
    req.Header.Set("Stripe-Signature", "invalid")
    r.ServeHTTP(w, req)

    assert.Equal(t, http.StatusUnauthorized, w.Code)
}

func TestStripeWebhook_MissingSignature(t *testing.T) {
    t.Parallel()

    r := gin.New()
    r.POST("/webhooks/stripe", WebhookSignature("whsec_test"), StripeWebhook(nil))

    w := httptest.NewRecorder()
    req := httptest.NewRequest(http.MethodPost, "/webhooks/stripe", strings.NewReader(`{}`))
    // No Stripe-Signature header
    r.ServeHTTP(w, req)

    assert.Equal(t, http.StatusUnauthorized, w.Code)
}
```

### Interface Mocking (define in consumer, implement in test)

```go
// In service package (consumer defines the interface it needs)
type UserRepository interface {
    FindByID(ctx context.Context, id string) (*User, error)
    Save(ctx context.Context, user *User) error
}

// In test file (not a generated mock - simple struct with function fields)
type MockUserRepository struct {
    FindByIDFn func(ctx context.Context, id string) (*User, error)
    SaveFn     func(ctx context.Context, user *User) error
}

func (m *MockUserRepository) FindByID(ctx context.Context, id string) (*User, error) {
    return m.FindByIDFn(ctx, id)
}

func (m *MockUserRepository) Save(ctx context.Context, user *User) error {
    return m.SaveFn(ctx, user)
}
```

For larger projects, use `mockery` or `gomock` to generate mocks from interfaces automatically.

### Test Fixtures

For services with complex domain objects, use builder functions to create valid test data:

```go
func newTestPayment(opts ...func(*Payment)) *Payment {
    p := &Payment{
        ID:             "pay_test_123",
        Amount:         1000,
        Currency:       "usd",
        Status:         "pending",
        IdempotencyKey: "idk_" + uuid.New().String(),
        CreatedAt:      time.Now(),
    }
    for _, opt := range opts {
        opt(p)
    }
    return p
}

func withStatus(status string) func(*Payment) {
    return func(p *Payment) { p.Status = status }
}

func withAmount(amount int64) func(*Payment) {
    return func(p *Payment) { p.Amount = amount }
}

// Usage
payment := newTestPayment(withStatus("completed"), withAmount(5000))
```

### Integration Tests with testcontainers-go

```go
func TestUserRepo_Integration(t *testing.T) {
    if testing.Short() {
        t.Skip("skipping integration test in short mode")
    }

    ctx := context.Background()

    pgContainer, err := postgres.RunContainer(ctx,
        testcontainers.WithImage("postgres:16-alpine"),
        postgres.WithDatabase("testdb"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
        testcontainers.WithWaitStrategy(
            wait.ForLog("database system is ready to accept connections").WithOccurrence(2),
        ),
    )
    require.NoError(t, err)
    t.Cleanup(func() { pgContainer.Terminate(ctx) })

    connStr, err := pgContainer.ConnectionString(ctx, "sslmode=disable")
    require.NoError(t, err)

    db := setupTestDB(t, connStr) // run migrations
    repo := NewUserRepository(db)

    t.Run("creates and retrieves user", func(t *testing.T) {
        user := &User{Name: "Alice", Email: "alice@example.com"}
        require.NoError(t, repo.Save(ctx, user))
        require.NotEmpty(t, user.ID)

        found, err := repo.FindByID(ctx, user.ID)
        require.NoError(t, err)
        assert.Equal(t, "Alice", found.Name)
    })
}
```

### Testing Idempotent Upserts

```go
func TestPaymentRepo_CreateIdempotent(t *testing.T) {
    // ... testcontainers setup ...

    t.Run("first create succeeds", func(t *testing.T) {
        payment := newTestPayment()
        result, err := repo.CreateIdempotent(ctx, payment)
        require.NoError(t, err)
        assert.Equal(t, payment.IdempotencyKey, result.IdempotencyKey)
    })

    t.Run("duplicate returns existing without error", func(t *testing.T) {
        payment := newTestPayment()
        first, err := repo.CreateIdempotent(ctx, payment)
        require.NoError(t, err)

        // Same idempotency key, different amount
        duplicate := newTestPayment(withAmount(9999))
        duplicate.IdempotencyKey = payment.IdempotencyKey

        second, err := repo.CreateIdempotent(ctx, duplicate)
        require.NoError(t, err)
        assert.Equal(t, first.ID, second.ID)
        assert.Equal(t, first.Amount, second.Amount) // original amount preserved
    })
}
```

### TestMain for Suite-Level Setup

```go
func TestMain(m *testing.M) {
    // One-time setup before any tests in the package run
    gin.SetMode(gin.TestMode) // suppress debug logging in tests
    pool, resource := setupTestDatabase()

    code := m.Run()

    // Teardown
    pool.Purge(resource)
    os.Exit(code)
}
```

### Benchmarks

```go
func BenchmarkHashPassword(b *testing.B) {
    password := "supersecretpassword"
    b.ResetTimer()
    for b.Loop() { // Go 1.24+ - replaces for i := 0; i < b.N; i++
        _, _ = HashPassword(password)
    }
}
```

Run with: `go test -bench=. -benchmem ./...`

### Deterministic Concurrency Tests (testing/synctest)

For testing goroutine behavior without `time.Sleep`:

```go
func TestDebounce(t *testing.T) {
    synctest.Run(func() {
        calls := 0
        fn := Debounce(func() { calls++ }, 100*time.Millisecond)

        fn()
        fn()
        fn()
        synctest.Wait() // wait for all goroutines to block

        time.Sleep(150 * time.Millisecond) // advance fake clock
        synctest.Wait()

        assert.Equal(t, 1, calls) // only one call despite three triggers
    })
}
```

## Edge Cases

- **t.Parallel with shared state**: subtests sharing a loop variable must capture it (Go < 1.22) or use `t.Parallel()` only when each subtest is truly independent - shared mocks or counters need synchronization
- **testcontainers port mapping**: container internal port differs from host-mapped port - always use `container.MappedPort()` or `ConnectionString()`, never hardcode ports
- **Gin test mode**: set `gin.SetMode(gin.TestMode)` in `TestMain` or init to suppress debug logging and avoid misleading output in CI
- **Cleanup ordering**: `t.Cleanup` functions run in LIFO order - register container termination before DB connection close to avoid connection errors during teardown
- **Webhook test signatures**: use the provider's test helpers or compute HMAC-SHA256 manually. Do not hardcode signatures - they include a timestamp that must match

## Output Format

```
## Test Strategy

### Test Coverage
| Layer | Type | Count | Key Scenarios |
|-------|------|-------|--------------|
| Service | Unit (table-driven) | {n} | {happy path, transitions, errors} |
| Handler | httptest | {n} | {CRUD, webhook sig validation} |
| Repository | Integration (testcontainers) | {n} | {CRUD, upsert idempotency} |
| Benchmark | Performance | {n} | {hot path functions} |

### Test Fixtures
| Fixture | Builder | Variants |
|---------|---------|----------|
| {Payment} | newTestPayment() | withStatus, withAmount |

### Mock Interfaces
| Interface | Package | Mock Strategy |
|-----------|---------|--------------|
| {PaymentRepository} | service | function-field struct |
```

## Avoid

- `time.Sleep` in tests - use channels, `synctest`, or `testcontainers` wait strategies
- Testing private functions - restructure or test through the public API
- Mocking the database - use `testcontainers-go` for real query validation
- Missing `t.Parallel()` on independent tests - suites become unnecessarily slow
- Shared global state between tests - each test must be independently runnable
- Hardcoding webhook signatures in tests - compute them dynamically
