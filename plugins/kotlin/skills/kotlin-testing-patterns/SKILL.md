---
name: kotlin-testing-patterns
description: "Kotlin testing patterns with MockK (coEvery/coVerify for suspend functions), Kotest matchers, Turbine for Flow testing, Spring test slice integration with @MockkBean, runTest for coroutine test bodies, Testcontainers for integration tests, and test fixture factories."
user-invocable: false
---

# Kotlin Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing unit tests for Kotlin services, handlers, or domain logic with Spring Boot
- Mocking `suspend` functions or `Flow` producers in tests
- Setting up integration tests with Testcontainers for Kotlin Spring Boot projects
- Choosing between MockK, Mockito, Kotest, and JUnit 5 for a Kotlin project
- Reviewing tests for Kotlin-specific anti-patterns (Mockito with final classes, missing `coEvery`)

Not for production debugging (see `task-kotlin-debug`) or coroutine design patterns (see `kotlin-coroutines-spring`).

## Rules

- Use MockK over Mockito for Kotlin - MockK works with final classes by default; Mockito requires `open` or the `mock-maker-inline` extension
- Use `coEvery` / `coVerify` for `suspend` function mocks - regular `every` / `verify` silently fails on coroutines
- Use `@MockkBean` instead of `@MockBean` in Spring test slices when mocking Kotlin classes
- Use `runTest { }` for all coroutine-based test bodies - it controls virtual time and prevents test flakiness
- Prefer kotest matchers (`shouldBe`, `shouldThrow`) over JUnit assertions in Kotlin tests for readability
- Call `clearAllMocks()` in `@AfterEach` when tests share mock state - stale stubs cause intermittent failures
- Use Testcontainers for repository/integration tests - never mock the database for persistence tests

## Patterns

### MockK Basics

```kotlin
// Unit test with MockK
class OrderServiceTest {

    private val repo = mockk<OrderRepository>()
    private val service = OrderService(repo)

    @AfterEach
    fun cleanup() = clearAllMocks()

    @Test
    fun `returns order when found`() {
        val order = Order(id = 1L, userId = 42L, status = OrderStatus.PENDING)
        every { repo.findById(1L) } returns order

        val result = service.getOrder(1L)

        result shouldBe order
        verify(exactly = 1) { repo.findById(1L) }
    }

    @Test
    fun `throws when order not found`() {
        every { repo.findById(any()) } returns null

        shouldThrow<OrderNotFoundException> {
            service.getOrder(999L)
        }
    }

    @Test
    fun `captures argument passed to save`() {
        val slot = slot<Order>()
        every { repo.save(capture(slot)) } answers { slot.captured }

        service.placeOrder(PlaceOrderRequest(userId = 1L))

        slot.captured.userId shouldBe 1L
        slot.captured.status shouldBe OrderStatus.PENDING
    }
}
```

### MockK for Suspend Functions

The most common MockK mistake in Kotlin projects: using `every`/`verify` instead of `coEvery`/`coVerify` for `suspend` functions. Regular versions silently ignore the stub and MockK reports "no answer found."

```kotlin
class OrderServiceTest {

    private val repo = mockk<OrderRepository>()
    private val service = OrderService(repo)

    @Test
    fun `finds order asynchronously`() = runTest {
        val order = Order(id = 1L, userId = 42L)
        coEvery { repo.findById(1L) } returns order  // coEvery for suspend functions

        val result = service.findOrder(1L)

        result shouldBe order
        coVerify(exactly = 1) { repo.findById(1L) }  // coVerify for suspend functions
    }

    @Test
    fun `handles suspend function throwing`() = runTest {
        coEvery { repo.findById(any()) } throws OrderNotFoundException(999L)

        shouldThrow<OrderNotFoundException> {
            service.findOrder(999L)
        }
    }
}

// Bad: every silently fails for suspend functions
every { repo.findById(1L) } returns order  // stub is ignored -> "no answer found" at runtime

// Good: coEvery for suspend functions
coEvery { repo.findById(1L) } returns order
```

### Flow Testing with Turbine

```kotlin
// Turbine library: https://github.com/cashapp/turbine
class OrderStreamServiceTest {

    private val repo = mockk<OrderRepository>()
    private val service = OrderStreamService(repo)

    @Test
    fun `streams active orders`() = runTest {
        val orders = listOf(
            Order(id = 1L, status = OrderStatus.ACTIVE),
            Order(id = 2L, status = OrderStatus.CANCELLED),
            Order(id = 3L, status = OrderStatus.ACTIVE),
        )
        every { repo.findAllByUserId(42L) } returns orders.asFlow()

        service.streamActiveOrders(42L).test {
            awaitItem().id shouldBe 1L
            awaitItem().id shouldBe 3L  // CANCELLED filtered out
            awaitComplete()
        }
    }

    @Test
    fun `propagates error in flow`() = runTest {
        every { repo.findAllByUserId(any()) } returns flow { throw RuntimeException("db error") }

        service.streamActiveOrders(42L).test {
            awaitError().message shouldBe "db error"
        }
    }
}
```

### Spring Test Slices with @MockkBean

```kotlin
// @WebMvcTest with MockK
@WebMvcTest(OrderController::class)
class OrderControllerTest {

    @Autowired
    lateinit var mockMvc: MockMvc

    @MockkBean  // NOT @MockBean - use MockkBean for Kotlin classes
    lateinit var orderService: OrderService

    @Test
    fun `GET order returns 200`() {
        val order = Order(id = 1L, userId = 42L)
        coEvery { orderService.findOrder(1L) } returns order

        mockMvc.get("/api/orders/1")
            .andExpect {
                status { isOk() }
                jsonPath("$.id") { value(1) }
            }
    }

    @Test
    fun `GET non-existent order returns 404`() {
        coEvery { orderService.findOrder(999L) } throws OrderNotFoundException(999L)

        mockMvc.get("/api/orders/999")
            .andExpect { status { isNotFound() } }
    }
}
```

### Testcontainers for Integration Tests

```kotlin
// Abstract base class for repository tests with Testcontainers
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
abstract class AbstractRepositoryTest {

    companion object {
        @Container
        @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine")
            .withDatabaseName("test")
            .withUsername("test")
            .withPassword("test")

        @DynamicPropertySource
        @JvmStatic
        fun configureProperties(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url", postgres::getJdbcUrl)
            registry.add("spring.datasource.username", postgres::getUsername)
            registry.add("spring.datasource.password", postgres::getPassword)
        }
    }
}

// Concrete repository test
class OrderRepositoryTest : AbstractRepositoryTest() {

    @Autowired
    lateinit var repo: OrderRepository

    @Test
    fun `saves and retrieves order`() {
        val order = Order(userId = 42L, status = OrderStatus.PENDING)
        val saved = repo.save(order)

        val found = repo.findById(saved.id)

        found shouldNotBeNull()
        found.userId shouldBe 42L
        found.status shouldBe OrderStatus.PENDING
    }

    @Test
    fun `finds orders by user ID`() {
        repo.save(Order(userId = 1L, status = OrderStatus.ACTIVE))
        repo.save(Order(userId = 1L, status = OrderStatus.CANCELLED))
        repo.save(Order(userId = 2L, status = OrderStatus.ACTIVE))

        val orders = repo.findAllByUserId(1L)

        orders shouldHaveSize 2
        orders.map { it.userId }.toSet() shouldBe setOf(1L)
    }
}
```

### Test Fixture Factories

Use factory functions instead of complex builders to create test data. Kotlin named parameters with defaults make this clean:

```kotlin
// Test fixture factory - keep in a shared test-support file
fun createOrder(
    id: Long = 0L,
    userId: Long = 42L,
    status: OrderStatus = OrderStatus.PENDING,
    total: BigDecimal = BigDecimal("99.99"),
    createdAt: Instant = Instant.now(),
) = Order(
    id = id,
    userId = userId,
    status = status,
    total = total,
    createdAt = createdAt,
)

fun createOrderRequest(
    userId: Long = 1L,
    items: List<OrderItemRequest> = listOf(createOrderItemRequest()),
    shippingAddress: String = "123 Test St",
) = CreateOrderRequest(
    userId = userId,
    items = items,
    shippingAddress = shippingAddress,
)

// Usage in tests - only specify what differs from defaults
@Test
fun `calculates total for active orders`() {
    val orders = listOf(
        createOrder(total = BigDecimal("10.00"), status = OrderStatus.ACTIVE),
        createOrder(total = BigDecimal("20.00"), status = OrderStatus.ACTIVE),
        createOrder(total = BigDecimal("30.00"), status = OrderStatus.CANCELLED),
    )

    service.totalActiveRevenue(orders) shouldBe BigDecimal("30.00")
}
```

### Kotest Styles and Matchers

```kotlin
// FunSpec style (similar to JUnit 5)
class OrderServiceSpec : FunSpec({

    val repo = mockk<OrderRepository>()
    val service = OrderService(repo)

    afterEach { clearAllMocks() }

    test("returns order when found") {
        val order = Order(id = 1L)
        coEvery { repo.findById(1L) } returns order

        service.findOrder(1L) shouldBe order
    }
})

// BehaviorSpec style (Given/When/Then)
class OrderServiceBehaviorSpec : BehaviorSpec({

    val repo = mockk<OrderRepository>()
    val service = OrderService(repo)

    afterEach { clearAllMocks() }

    given("an existing order") {
        val order = Order(id = 1L, status = OrderStatus.ACTIVE)
        coEvery { repo.findById(1L) } returns order

        `when`("finding by ID") {
            val result = service.findOrder(1L)

            then("returns the order") {
                result.id shouldBe 1L
                result.status shouldBe OrderStatus.ACTIVE
            }
        }
    }
})

// Property-based testing with Arb generators
class OrderValidationSpec : FunSpec({

    test("total is always non-negative") {
        checkAll(Arb.long(min = 1), Arb.bigDecimal(min = BigDecimal.ZERO)) { userId, total ->
            val order = Order(userId = userId, total = total)
            order.total shouldBeGreaterThanOrEqualTo BigDecimal.ZERO
        }
    }
})
```

### Coroutine Testing with runTest

```kotlin
@Test
fun `parallel operations complete correctly`() = runTest {
    // TestDispatcher controls virtual time - no real waiting
    coEvery { userService.findUser(any()) } coAnswers {
        delay(100) // simulated delay - advances instantly in runTest
        User(id = 1L)
    }

    val result = dashboardService.getDashboard(userId = 1L)

    result.user.id shouldBe 1L
}

@Test
fun `timeout is enforced`() = runTest {
    coEvery { slowService.fetch() } coAnswers {
        delay(10_000) // 10 seconds in virtual time
        "result"
    }

    shouldThrow<TimeoutCancellationException> {
        withTimeout(1_000) {
            slowService.fetch()
        }
    }
}
```

## Edge Cases

**Mocking extension functions**: MockK can mock extension functions, but only with `mockkStatic`:

```kotlin
// Extension function under test
fun Order.isExpired(): Boolean = this.createdAt.isBefore(Instant.now().minus(Duration.ofDays(30)))

// Test
mockkStatic(Order::isExpired) // required for extension functions
every { any<Order>().isExpired() } returns true
// Don't forget: unmockkStatic(Order::isExpired) in cleanup
```

**lateinit in tests**: When using `@MockkBean` with `lateinit var`, ensure the test context is properly initialized. If you see `UninitializedPropertyAccessException`, verify `@ExtendWith(MockKExtension::class)` or `@SpringBootTest` is present on the test class.

**Relaxed mocks for large interfaces**: When a mock has many methods but only a few are relevant to the test, use `relaxed = true` to avoid stubbing every call:

```kotlin
val repo = mockk<OrderRepository>(relaxed = true) // returns default values for unstubbed methods
coEvery { repo.findById(1L) } returns order // override only what matters
```

Use relaxed mocks sparingly - they hide missing stubs that might indicate incorrect test assumptions.

**Testing coroutine timeouts**: `runTest` uses virtual time, so `delay()` advances instantly. To test real timeout behavior, use `withTimeout` inside `runTest` - the virtual clock handles it correctly without real waiting.

**Testcontainers lifecycle**: Use `@Container` on a `companion object` property with `@JvmStatic` - otherwise the container is recreated per test class instance instead of being shared. For multi-container setups (Postgres + Redis), use `@DynamicPropertySource` to wire each container's connection details.

**WebTestClient with coroutines**: Use `WebTestClient` (not `MockMvc`) when testing reactive/coroutine controllers with `@SpringBootTest(webEnvironment = RANDOM_PORT)`:

```kotlin
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OrderIntegrationTest {

    @Autowired
    lateinit var client: WebTestClient

    @Test
    fun `creates and retrieves order`() {
        val request = CreateOrderRequest(userId = 1L, total = BigDecimal("99.99"))

        client.post().uri("/api/orders")
            .bodyValue(request)
            .exchange()
            .expectStatus().isCreated
            .expectBody<OrderResponse>()
            .consumeWith { response ->
                response.responseBody?.total shouldBe BigDecimal("99.99")
            }
    }
}
```

## Output Format

```
## Test Plan

### Test Layers
| Layer | Framework | Test Count | Description |
|-------|-----------|------------|-------------|
| Unit | MockK + kotest | {count} | Service logic, domain rules |
| Integration | @DataJpaTest + Testcontainers | {count} | Repository queries, persistence |
| API | @WebMvcTest + @MockkBean | {count} | Controller routing, validation, serialization |

### Coverage
| Scenario | Test Method | Layer |
|----------|-------------|-------|
| Happy path - {operation} | {test method name} | {unit/integration/API} |
| Not found | {test method name} | {unit/API} |
| Validation error | {test method name} | {API} |
| {edge case} | {test method name} | {layer} |

### MockK Configuration
- Suspend functions: coEvery/coVerify used for {list of suspend methods}
- Relaxed mocks: {none / justified usage}
- clearAllMocks: {in @AfterEach / per-spec afterEach}

### Testcontainers
- Container: {PostgreSQLContainer / MySQLContainer / none}
- Shared base class: {yes / no}
```

## Avoid

- Mockito for mocking Kotlin classes - use MockK (works with final classes by default)
- `every` / `verify` for `suspend` functions - use `coEvery` / `coVerify` (regular versions silently fail)
- `@MockBean` in Spring test slices - use `@MockkBean`
- `runBlocking` in test bodies - use `runTest` (controls virtual time, prevents flakiness)
- JUnit 5 assertions in Kotlin code - use kotest matchers or assertk for readability
- Relaxed mocks as default - use only when a mock has many irrelevant methods
- Mocking the database in persistence tests - use Testcontainers with `@DataJpaTest`
- Forgetting `clearAllMocks()` cleanup - causes intermittent failures from stale stubs
