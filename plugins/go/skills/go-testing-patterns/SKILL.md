---
name: go-testing-patterns
description: "Go testing: table-driven, httptest, testcontainers-go, testify, interface mocking, t.Parallel, fixtures, benchmarks, testing/synctest."
metadata:
  category: backend
  tags: [go, testing, httptest, testcontainers, testify, benchmarks]
user-invocable: false
---

# Go Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Designing a test strategy for a Go service
- Writing handler / service / repository / webhook / async tests
- Reviewing tests for coverage, brittleness, or speed

## Rules

- Table-driven for any function with multiple cases
- `require` halts on failure (setup); `assert` continues (post-conditions)
- `t.Parallel()` on every independent test
- Mock via consumer-defined interfaces; never mock concrete types or the DB
- Integration tests use `testcontainers-go` against the real DB; never SQLite-for-Postgres
- Test public behavior; testing a private function suggests bad package design
- No `time.Sleep` for synchronization - use channels, `testing/synctest`, or testcontainers wait strategies

## Patterns

### Table-Driven

```go
func TestPaymentTransition(t *testing.T) {
    t.Parallel()
    tests := []struct {
        name      string
        from, to  string
        wantErr   bool
        errTarget error
    }{
        {"pending->processing", "pending", "processing", false, nil},
        {"processing->completed", "processing", "completed", false, nil},
        {"pending->completed (skip)", "pending", "completed", true, ErrInvalidTransition},
        {"completed->pending (reverse)", "completed", "pending", true, ErrInvalidTransition},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            t.Parallel()
            err := NewPaymentService(mockRepo(tt.from)).Transition(context.Background(), "pay_123", tt.to)
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

### Handler Tests (httptest)

```go
func TestGetUser_NotFound(t *testing.T) {
    t.Parallel()
    mockSvc := &MockUserService{
        GetUserFn: func(ctx context.Context, id string) (*User, error) { return nil, ErrNotFound },
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

### Webhook Tests (Signature)

```go
tests := []struct {
    name, sigHeader string
    wantStatus      int
}{
    {"valid", computeStripeSignature(t, payload, secret), http.StatusOK},
    {"invalid", "invalid", http.StatusUnauthorized},
    {"missing", "", http.StatusUnauthorized},
}
```

Compute signatures dynamically with the provider's test helpers; never hardcode (timestamps must match).

### Interface Mocking

Function-field structs are simplest; for larger projects use `mockery` / `gomock`.

```go
type MockUserRepository struct {
    FindByIDFn func(ctx context.Context, id string) (*User, error)
    SaveFn     func(ctx context.Context, u *User) error
}
func (m *MockUserRepository) FindByID(ctx context.Context, id string) (*User, error) {
    return m.FindByIDFn(ctx, id)
}
func (m *MockUserRepository) Save(ctx context.Context, u *User) error { return m.SaveFn(ctx, u) }
```

### Fixtures (functional options)

```go
func newTestPayment(opts ...func(*Payment)) *Payment {
    p := &Payment{
        ID: "pay_test_123", Amount: 1000, Currency: "usd", Status: "pending",
        IdempotencyKey: "idk_" + uuid.New().String(), CreatedAt: time.Now(),
    }
    for _, opt := range opts { opt(p) }
    return p
}

func withStatus(s string) func(*Payment) { return func(p *Payment) { p.Status = s } }
func withAmount(a int64) func(*Payment)  { return func(p *Payment) { p.Amount = a } }

p := newTestPayment(withStatus("completed"), withAmount(5000))
```

### Integration (testcontainers-go)

```go
func TestUserRepo_Integration(t *testing.T) {
    if testing.Short() { t.Skip() }
    ctx := context.Background()

    pg, err := postgres.RunContainer(ctx,
        testcontainers.WithImage("postgres:16-alpine"),
        postgres.WithDatabase("testdb"),
        postgres.WithUsername("test"),
        postgres.WithPassword("test"),
        testcontainers.WithWaitStrategy(
            wait.ForLog("database system is ready to accept connections").WithOccurrence(2)),
    )
    require.NoError(t, err)
    t.Cleanup(func() { pg.Terminate(ctx) })

    connStr, err := pg.ConnectionString(ctx, "sslmode=disable")
    require.NoError(t, err)
    db := setupTestDB(t, connStr) // runs migrations
    repo := NewUserRepository(db)

    t.Run("creates and retrieves", func(t *testing.T) {
        u := &User{Name: "Alice", Email: "alice@example.com"}
        require.NoError(t, repo.Save(ctx, u))
        got, err := repo.FindByID(ctx, u.ID)
        require.NoError(t, err)
        assert.Equal(t, "Alice", got.Name)
    })
}
```

### Idempotent Upsert Integration

```go
t.Run("duplicate returns existing", func(t *testing.T) {
    p := newTestPayment()
    first, _ := repo.CreateIdempotent(ctx, p)
    dup := newTestPayment(withAmount(9999))
    dup.IdempotencyKey = p.IdempotencyKey
    second, err := repo.CreateIdempotent(ctx, dup)
    require.NoError(t, err)
    assert.Equal(t, first.ID, second.ID)
    assert.Equal(t, first.Amount, second.Amount) // original wins
})
```

### TestMain

```go
func TestMain(m *testing.M) {
    gin.SetMode(gin.TestMode)
    pool, resource := setupTestDatabase()
    code := m.Run()
    pool.Purge(resource)
    os.Exit(code)
}
```

### Benchmarks

```go
func BenchmarkHashPassword(b *testing.B) {
    for b.Loop() { // Go 1.24+
        _, _ = HashPassword("secret")
    }
}
// go test -bench=. -benchmem ./...
```

### Deterministic Concurrency (testing/synctest)

```go
synctest.Run(func() {
    calls := 0
    fn := Debounce(func() { calls++ }, 100*time.Millisecond)
    fn(); fn(); fn()
    synctest.Wait()
    time.Sleep(150 * time.Millisecond)
    synctest.Wait()
    assert.Equal(t, 1, calls)
})
```

## Edge Cases

- testcontainers: use `MappedPort()` / `ConnectionString()`, never hardcode ports
- `t.Cleanup` runs LIFO - register container teardown before DB close
- `gin.SetMode(gin.TestMode)` in `TestMain` to suppress debug noise

## Output Format

```
## Test Strategy

### Coverage
| Layer | Type | Count | Key Scenarios |

### Fixtures
| Fixture | Builder | Variants |

### Mocks
| Interface | Package | Strategy |
```

## Avoid

- `time.Sleep` for sync
- Testing private functions
- Mocking the database
- Missing `t.Parallel()`
- Shared global state across tests
- Hardcoded webhook signatures
