---
name: kotlin-testing-patterns
description: "Kotlin testing with MockK, kotest, and Spring test integration. Mocking Kotlin classes (no open requirement), coroutine testing, Kotlin-friendly assertions."
user-invocable: false
---

# Kotlin Testing Patterns

## When to Use

- Writing unit tests for Kotlin services, handlers, or domain logic with Spring Boot
- Mocking `suspend` functions or `Flow` producers in tests
- Choosing between MockK, Mockito, Kotest, and JUnit 5 for a Kotlin project
- Reviewing tests for Kotlin-specific anti-patterns (Mockito with final classes, missing `coEvery`)

## Rules

- Use MockK over Mockito for Kotlin - MockK works with final classes by default; Mockito requires `open` or the `mock-maker-inline` extension
- Use `coEvery` / `coVerify` for `suspend` function mocks - regular `every` / `verify` silently fails on coroutines
- Use `@MockkBean` instead of `@MockBean` in Spring test slices when mocking Kotlin classes
- Use `runTest { }` for all coroutine-based test bodies - it controls time and prevents test flakiness
- Prefer kotest matchers (`shouldBe`, `shouldThrow`) over JUnit assertions in Kotlin tests for readability

## Patterns

### MockK Basics

```kotlin
// Unit test with MockK
class OrderServiceTest {

    private val repo = mockk<OrderRepository>()
    private val service = OrderService(repo)

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

### Kotest Styles and Matchers

```kotlin
// FunSpec style (similar to JUnit 5)
class OrderServiceSpec : FunSpec({

    val repo = mockk<OrderRepository>()
    val service = OrderService(repo)

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

### Spring Test Slices with Kotlin

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

// WebTestClient with Kotlin DSL (for reactive or Spring WebFlux)
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

## Anti-Patterns

```kotlin
// Bad: Mockito with final Kotlin classes - fails at runtime without extra config
val service = Mockito.mock(OrderService::class.java) // Kotlin classes are final by default

// Bad: regular every {} for a suspend function - test passes vacuously, stub never applies
every { repo.findById(any()) } returns order // should be coEvery
service.findOrder(1L) // suspend call - the stub above doesn't apply

// Bad: JUnit-style assertions in Kotlin - harder to read
assertEquals(expected, actual)  // use shouldBe instead
assertTrue(result.isNotEmpty()) // use result.shouldNotBeEmpty()

// Bad: runBlocking in test body - use runTest for coroutine tests
@Test
fun `test suspend function`() = runBlocking {  // use runTest instead
    val result = service.findOrder(1L)
    result shouldBe expected
}

// Bad: @MockBean for Kotlin classes in Spring slices - use @MockkBean
@MockBean  // Mockito-based, misses final class issue
lateinit var service: OrderService
```

## Avoid

- Mockito for mocking Kotlin classes - use MockK
- `every` / `verify` for `suspend` functions - use `coEvery` / `coVerify`
- `@MockBean` in Spring test slices - use `@MockkBean`
- `runBlocking` in test bodies - use `runTest`
- JUnit 5 assertions in Kotlin code - use kotest matchers or assertk for readability
