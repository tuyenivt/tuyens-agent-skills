---
name: go-testing-patterns
description: "Go testing: table-driven tests, httptest for Gin handlers, testcontainers-go for integration, testify (assert/require), interface mocking, t.Parallel, benchmarks, and testing/synctest."
user-invocable: false
---

# Go Testing Patterns

## When to Use

- Designing a test strategy for a new Go service
- Writing unit tests for handlers, services, or domain logic
- Writing integration tests against a real PostgreSQL database
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

### TestMain for Suite-Level Setup

```go
func TestMain(m *testing.M) {
    // One-time setup before any tests in the package run
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

## Anti-Patterns

```go
// Bad: no t.Parallel - tests run serially, suite takes 10x longer
func TestSomething(t *testing.T) {
    // missing t.Parallel()
}

// Bad: testing private functions - tests the implementation, not the behavior
func TestparseToken(t *testing.T) { ... } // lowercase = private

// Bad: mocking the database directly (brittle, misses real query behavior)
mockDB.On("Query", ...).Return(...)

// Bad: time.Sleep for async assertions (flaky on slow CI)
go doAsyncWork()
time.Sleep(100 * time.Millisecond)
assert.Equal(t, expected, result)

// Good: use channels or synctest for async assertions
done := make(chan struct{})
go func() { doAsyncWork(); close(done) }()
<-done
assert.Equal(t, expected, result)
```

## Avoid

- `time.Sleep` in tests - use channels, `synctest`, or `testcontainers` wait strategies
- Testing private functions - restructure or test through the public API
- Mocking the database - use `testcontainers-go` for real query validation
- Missing `t.Parallel()` on independent tests - suites become unnecessarily slow
- Shared global state between tests - each test must be independently runnable
