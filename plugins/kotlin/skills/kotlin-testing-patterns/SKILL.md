---
name: kotlin-testing-patterns
description: "Kotlin testing patterns: MockK coEvery/coVerify for suspend, Kotest matchers, Turbine for Flow, @MockkBean test slices, runTest, Testcontainers."
user-invocable: false
---

# Kotlin Testing Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Writing or reviewing unit tests for Kotlin services, handlers, or domain logic
- Mocking `suspend` functions or `Flow` producers
- Setting up Testcontainers for integration tests
- Choosing between MockK, Mockito, Kotest, and JUnit 5

Not for production debugging (`task-kotlin-debug`) or coroutine design (`kotlin-coroutines-spring`).

## Rules

- MockK over Mockito - works on final classes by default.
- `coEvery` / `coVerify` for `suspend` functions. Regular `every` / `verify` silently fail (MockK reports "no answer found" at runtime).
- `@MockkBean` (springmockk) over `@MockBean` in Spring slices.
- `runTest { }` for all coroutine test bodies. Virtual time, no real waits, no flakes.
- Kotest matchers (`shouldBe`, `shouldThrow`) over JUnit assertions for readability.
- `clearAllMocks()` in `@AfterEach` (or `@BeforeEach` for `@MockkBean` - Spring caches contexts and mocks carry stub state between tests).
- Testcontainers for persistence tests - never H2 for Postgres-feature apps.

## Patterns

### MockK basics

```kotlin
class OrderServiceTest {
    private val repo = mockk<OrderRepository>()
    private val service = OrderService(repo)

    @AfterEach fun cleanup() = clearAllMocks()

    @Test fun `returns order when found`() {
        every { repo.findById(1L) } returns Order(id = 1L)
        service.getOrder(1L) shouldBe Order(id = 1L)
        verify(exactly = 1) { repo.findById(1L) }
    }

    @Test fun `throws when not found`() {
        every { repo.findById(any()) } returns null
        shouldThrow<OrderNotFoundException> { service.getOrder(999L) }
    }

    @Test fun `captures save argument`() {
        val slot = slot<Order>()
        every { repo.save(capture(slot)) } answers { slot.captured }
        service.placeOrder(PlaceOrderRequest(userId = 1L))
        slot.captured.userId shouldBe 1L
    }
}
```

### MockK for suspend functions

```kotlin
@Test fun `places order in sequence`() = runTest {
    coEvery { userRepo.findById(42L) } returns User(id = 42L)
    coEvery { inventoryRepo.reserve(any()) } returns Reservation("r1")
    coEvery { orderRepo.save(any()) } answers { firstArg() }

    service.placeOrder(PlaceOrderRequest(userId = 42L, items = listOf(item)))

    coVerifyOrder {     // stricter: coVerifySequence checks nothing else called
        userRepo.findById(42L)
        inventoryRepo.reserve(any())
        orderRepo.save(any())
    }
}

// Bad: every silently fails for suspend
every { repo.findById(1L) } returns order

// Good
coEvery { repo.findById(1L) } returns order
```

**`Flow`-returning functions are usually not suspend** (e.g. `fun findAllByUserId(): Flow<Order>` on `CoroutineCrudRepository`). Use plain `every` + `returns flow`. Only `coEvery` when the signature is `suspend fun ... : Flow<T>`.

### Flow testing with Turbine

```kotlin
@Test fun `streams active orders`() = runTest {
    every { repo.findAllByUserId(42L) } returns listOf(
        Order(id = 1, status = ACTIVE),
        Order(id = 2, status = CANCELLED),
    ).asFlow()

    service.streamActiveOrders(42L).test {
        awaitItem().id shouldBe 1L
        awaitComplete()
    }
}

@Test fun `propagates flow error`() = runTest {
    every { repo.findAllByUserId(any()) } returns flow { throw RuntimeException("db") }
    service.streamActiveOrders(42L).test { awaitError().message shouldBe "db" }
}
```

### `@MockkBean` in Spring slices

```kotlin
@WebMvcTest(OrderController::class)
class OrderControllerTest {
    @Autowired lateinit var mockMvc: MockMvc
    @MockkBean lateinit var service: OrderService

    @BeforeEach fun reset() = clearAllMocks()       // Spring caches contexts; mocks carry stubs across tests

    @Test fun `GET order`() {
        coEvery { service.findOrder(1L) } returns Order(id = 1)
        mockMvc.get("/api/orders/1").andExpect { status { isOk() } }
    }
}
```

### Testcontainers for persistence

```kotlin
@DataJpaTest
@Testcontainers
@AutoConfigureTestDatabase(replace = Replace.NONE)
abstract class AbstractRepositoryTest {
    companion object {
        @Container @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine")

        @DynamicPropertySource @JvmStatic
        fun props(registry: DynamicPropertyRegistry) {
            registry.add("spring.datasource.url", postgres::getJdbcUrl)
            registry.add("spring.datasource.username", postgres::getUsername)
            registry.add("spring.datasource.password", postgres::getPassword)
        }
    }
}
```

`@Container` on a `companion object` `@JvmStatic` property - otherwise the container is recreated per test class instance.

### Fixture factories

Named parameters with defaults replace builders:

```kotlin
fun createOrder(
    id: Long = 0L,
    userId: Long = 42L,
    status: OrderStatus = PENDING,
    total: BigDecimal = BigDecimal("99.99"),
) = Order(id, userId, status, total)

@Test fun example() {
    val active = createOrder(status = ACTIVE, total = BigDecimal("10"))
    val cancelled = createOrder(status = CANCELLED)
    // only specify what differs
}
```

Share factories across slice and full-context tests in `TestFixtures.kt`; never duplicate per test class.

### Kotest styles

```kotlin
class OrderServiceSpec : FunSpec({
    val repo = mockk<OrderRepository>()
    afterEach { clearAllMocks() }
    test("returns order") {
        coEvery { repo.findById(1L) } returns Order(id = 1L)
        OrderService(repo).findOrder(1L).id shouldBe 1L
    }
})
```

`BehaviorSpec` (Given/When/Then) and property-based `Arb` / `checkAll` also available.

### Other patterns

- **`runTest` timeouts**: `delay()` advances instantly; wrap in `withTimeout(1_000)` to assert real timeout, expect `TimeoutCancellationException`.
- **Mocking extensions**: `mockkStatic(Order::isExpired)` (member); `mockkStatic("com.example.OrdersKt")` (top-level - file `Orders.kt`). JVM-wide - always `unmockkStatic` in `@AfterEach`.
- **Relaxed mocks** (`mockk(relaxed = true)`): hides missing stubs; use sparingly.

## Output Format

```
## Test Plan

### Layers
| Layer       | Framework                          | Count | Description |
| ----------- | ---------------------------------- | ----- | ----------- |
| Unit        | MockK + kotest                     |       | Service logic, domain rules |
| Integration | @DataJpaTest + Testcontainers      |       | Repository queries |
| API         | @WebMvcTest + @MockkBean           |       | Routing, validation, serialization |

### Coverage
| Scenario        | Test method | Layer |
| --------------- | ----------- | ----- |
| Happy path      |             |       |
| Not found       |             |       |
| Validation      |             |       |

### MockK configuration
- Suspend functions stubbed with coEvery/coVerify: {list}
- Relaxed mocks: {none | justified}
- clearAllMocks: {location}

### Testcontainers
- Container: {PostgreSQLContainer | none}
- Shared base class: {yes | no}
```

## Avoid

- Mockito for Kotlin classes - use MockK
- `every` / `verify` for `suspend` functions
- `@MockBean` in Spring slices for Kotlin classes
- `runBlocking` in test bodies - use `runTest`
- JUnit assertions in Kotlin tests - use kotest matchers
- Relaxed mocks as default
- Mocking the database in persistence tests
- Forgetting `clearAllMocks()` cleanup
- `@MockkBean` without `clearAllMocks()` in `@BeforeEach` - Spring caches contexts and stubs leak across tests
