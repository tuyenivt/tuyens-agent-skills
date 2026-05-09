---
name: kotlin-spring-test-integration
description: Kotlin / Spring Boot test slices and Testcontainers: @DataJpaTest, @WebMvcTest, singleton containers, MockK, kotest, runTest, Awaitility.
metadata:
  category: backend
  tags: [kotlin, testing, spring-boot, testcontainers, integration-test, test-slices, mockk, kotest]
user-invocable: false
---

# Kotlin Spring Integration Testing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing the right Spring test slice for a Kotlin layer
- Setting up Testcontainers for integration tests
- Designing reusable test fixtures and assertions in Kotlin
- Configuring test profiles and test-specific beans
- Writing async / coroutine / Virtual-Thread-safe tests

## Rules

- Never use `@SpringBootTest` when a slice test suffices - it's 10x slower
- Use Testcontainers with the real database - never H2 for integration tests against Postgres-feature apps
- Use `@MockkBean` (springmockk) for mocking Kotlin classes in test slices, not `@MockBean` / `@MockitoBean`
- Use `coEvery` / `coVerify` for `suspend` function mocks; regular `every` / `verify` silently fails
- Use `runTest { }` for coroutine-based test bodies; never `runBlocking` (use real time, makes tests flaky)
- Use kotest matchers (`shouldBe`, `shouldThrow`) for readability over JUnit `assertEquals`
- `@ActiveProfiles("test")` - always explicit, never rely on default
- Test-specific `@Configuration` classes belong in `src/test/kotlin`, never in `src/main/kotlin`
- Never use `Thread.sleep()` in async tests - use Awaitility or `runTest` virtual time
- Never use `@DirtiesContext` - redesign the test instead
- Configure `kotlin("plugin.spring")` so test-relevant beans (`@Service`, `@Configuration`) are not `final`

## Patterns

### Test Slice Selection Guide

```
Repository layer       -> @DataJpaTest (JPA, Flyway, Testcontainers Postgres)
Controller layer       -> @WebMvcTest (MockMvc Kotlin DSL, no DB, mock services)
Service (logic only)   -> Plain JUnit 5 / Kotest + MockK (no Spring context)
Service (Spring wiring)-> @SpringBootTest + @MockkBean for externals
Full integration       -> @SpringBootTest + Testcontainers + WebTestClient (or MockMvc)
```

### @DataJpaTest with Testcontainers

`@ServiceConnection` (Spring Boot 3.1+) auto-configures datasource:

```kotlin
@Testcontainers
@DataJpaTest
class OrderRepositoryTest {

    companion object {
        @Container
        @ServiceConnection
        @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine")
    }

    @Autowired lateinit var orderRepository: OrderRepository

    @Test
    fun `should find orders by status`() {
        orderRepository.save(createOrder(status = OrderStatus.PAID))

        val results = orderRepository.findByStatus(OrderStatus.PAID)

        results shouldHaveSize 1
        results.first().status shouldBe OrderStatus.PAID
    }
}
```

### @WebMvcTest - Controller Slice with @MockkBean

```kotlin
@WebMvcTest(OrderController::class)
class OrderControllerTest {

    @Autowired lateinit var mockMvc: MockMvc

    @MockkBean lateinit var orderService: OrderService

    @Test
    fun `should return order`() {
        val order = createOrderDto()
        every { orderService.findById(1L) } returns order

        mockMvc.get("/api/orders/1").andExpect {
            status { isOk() }
            jsonPath("$.status") { value("PAID") }
        }
    }

    @Test
    fun `should return order via suspend service`() = runTest {
        val order = createOrderDto()
        coEvery { orderService.findByIdAsync(1L) } returns order

        mockMvc.get("/api/orders/1").andExpect { status { isOk() } }
        coVerify(exactly = 1) { orderService.findByIdAsync(1L) }
    }
}
```

### Service Layer - Plain JUnit 5 / Kotest (No Spring Context)

```kotlin
class OrderServiceTest {
    private val orderRepository = mockk<OrderRepository>()
    private val paymentGateway = mockk<PaymentGateway>()
    private val orderService = OrderService(orderRepository, paymentGateway)

    @AfterEach
    fun cleanup() = clearAllMocks()

    @Test
    fun `should complete order`() {
        val order = createOrder(status = OrderStatus.PENDING)
        every { orderRepository.findById(1L) } returns Optional.of(order)
        every { paymentGateway.charge(any()) } returns PaymentResult.success()

        val result = orderService.complete(1L)

        result.status shouldBe OrderStatus.PAID
        verify { orderRepository.save(any()) }
    }
}
```

Kotest FunSpec alternative:

```kotlin
class OrderServiceSpec : FunSpec({
    val repo = mockk<OrderRepository>()
    val service = OrderService(repo)

    afterEach { clearAllMocks() }

    test("returns order when found") {
        val order = createOrder(id = 1L)
        coEvery { repo.findById(1L) } returns order
        service.findOrder(1L) shouldBe order
    }
})
```

### Singleton Container Pattern (Kotlin)

For shared containers across multiple test classes. Use `withReuse(true)` plus `~/.testcontainers.properties` (`testcontainers.reuse.enable=true`) for fast local re-runs; CI typically leaves reuse off so each pipeline starts clean.

```kotlin
@Testcontainers
abstract class AbstractIntegrationTest {
    companion object {
        @Container
        @ServiceConnection
        @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine").withReuse(true)

        @Container
        @ServiceConnection
        @JvmStatic
        val kafka = KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.0"))
            .withReuse(true)
    }
}
```

Without `@ServiceConnection`, use `@DynamicPropertySource` with `@JvmStatic`:

```kotlin
companion object {
    @Container @JvmStatic
    val redis = GenericContainer("redis:7-alpine").withExposedPorts(6379)

    @DynamicPropertySource @JvmStatic
    fun configure(registry: DynamicPropertyRegistry) {
        registry.add("spring.data.redis.host", redis::getHost)
        registry.add("spring.data.redis.port") { redis.getMappedPort(6379) }
    }
}
```

### Test Fixture Factories (Kotlin)

Kotlin's named parameters with defaults make test factories cleaner than Java builders:

```kotlin
fun createOrder(
    id: Long = 0L,
    userId: Long = 42L,
    status: OrderStatus = OrderStatus.PENDING,
    total: BigDecimal = BigDecimal("99.99"),
    createdAt: Instant = Instant.now(),
) = Order(id = id, userId = userId, status = status, total = total, createdAt = createdAt)

fun createOrderRequest(
    userId: Long = 1L,
    items: List<OrderItemRequest> = listOf(createOrderItemRequest()),
    shippingAddress: String = "123 Test St",
) = CreateOrderRequest(userId = userId, items = items, shippingAddress = shippingAddress)

// Usage - only specify what differs from defaults
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

### Mocking External HTTP Services with WireMock

For services that call external APIs, use WireMock instead of mocking the client class:

```kotlin
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@WireMockTest(httpPort = 8089)
class PaymentIntegrationTest : AbstractIntegrationTest() {

    @Autowired lateinit var paymentGateway: PaymentGateway

    @Test
    fun `should process payment successfully`() {
        stubFor(post(urlPathEqualTo("/api/charges"))
            .willReturn(okJson("""{"status":"success","chargeId":"ch_123"}""")))

        val result = paymentGateway.charge(ChargeRequest(orderId = 1L, amount = BigDecimal.TEN))

        result.status shouldBe "success"
        verify(postRequestedFor(urlPathEqualTo("/api/charges"))
            .withRequestBody(matchingJsonPath("$.amount")))
    }
}
```

### Kafka with Testcontainers

For tests that exercise a Kafka producer or `@KafkaListener` consumer, prefer Testcontainers `KafkaContainer` over `@EmbeddedKafka` - it matches the broker version you run in production and avoids JVM-classpath surprises. Verify produced messages with a test consumer; verify consumed messages with Awaitility waiting for downstream state.

```kotlin
@SpringBootTest
@ActiveProfiles("test")
class OrderEventIntegrationTest : AbstractIntegrationTest() {

    @Autowired lateinit var orderService: OrderService
    @Autowired lateinit var orderRepo: OrderRepository

    @Test
    fun `placing an order publishes OrderPlaced and updates status async`() {
        val orderId = orderService.placeOrder(createOrderRequest()).id

        // Verify the @KafkaListener-driven status update lands in the DB
        await().atMost(5.seconds.toJavaDuration()).untilAsserted {
            orderRepo.findById(orderId).get().status shouldBe OrderStatus.ENRICHED
        }
    }

    @Test
    fun `produces OrderPlaced event to the right topic`() {
        val consumer = newTestConsumer(kafka.bootstrapServers, topics = listOf("order.events"))

        orderService.placeOrder(createOrderRequest(idempotencyKey = "evt-1"))

        val record = KafkaTestUtils.getSingleRecord(consumer, "order.events", 5.seconds.toJavaDuration())
        record.value() shouldContain "\"idempotencyKey\":\"evt-1\""
    }
}
```

`KafkaTestUtils.getSingleRecord` (from `spring-kafka-test`) and the Awaitility loop together cover the two directions: outbound production and inbound consumption with side effects.

### Transactional Rollback in Tests (Slice Differences)

`@DataJpaTest` wraps each test method in a transaction that rolls back at the end - tests don't pollute each other. `@SpringBootTest` does **not**: persistence side-effects survive between tests unless you explicitly add `@Transactional` to the class or method, or clean state in `@AfterEach`. This trips up everyone porting a `@DataJpaTest` to `@SpringBootTest`.

Adding `@Transactional` to a `@SpringBootTest` is also a trap when the code under test relies on commit (e.g. `@TransactionalEventListener(AFTER_COMMIT)`, async listeners): the rollback hides the post-commit side effects from the test. In that case, prefer explicit cleanup or use `@Sql(scripts = "/cleanup.sql", executionPhase = AFTER_TEST_METHOD)` instead.

### Coroutine Tests with runTest

```kotlin
@Test
fun `parallel operations complete correctly`() = runTest {
    coEvery { userService.findUser(any()) } coAnswers {
        delay(100) // virtual time - advances instantly
        User(id = 1L)
    }

    val result = dashboardService.getDashboard(userId = 1L)

    result.user.id shouldBe 1L
}

@Test
fun `timeout enforced`() = runTest {
    coEvery { slowService.fetch() } coAnswers { delay(10_000); "result" }

    shouldThrow<TimeoutCancellationException> {
        withTimeout(1_000) { slowService.fetch() }
    }
}
```

### Awaitility for Non-Coroutine Async

Mockito-style and `@Async` paths still need real-time waits. Use Awaitility:

```kotlin
@Test
fun `should process order async`() {
    orderService.processAsync(orderId)

    await().atMost(Duration.ofSeconds(5)).pollInterval(Duration.ofMillis(100))
        .untilAsserted {
            val order = orderRepository.findById(orderId).orElseThrow()
            order.status shouldBe OrderStatus.COMPLETED
        }
}
```

Bad - `Thread.sleep` is flaky and slow:

```kotlin
orderService.processAsync(orderId)
Thread.sleep(2000) // flaky, slow
orderRepository.findById(orderId).get().status shouldBe OrderStatus.COMPLETED
```

### Testing Idempotency and State Transitions

```kotlin
@Test
fun `should return existing payment for duplicate idempotency key`() {
    val request = createPaymentRequest("idem-key-123")

    val first = paymentService.processPayment(request)
    first.status shouldBe PaymentStatus.COMPLETED

    val second = paymentService.processPayment(request)
    second.id shouldBe first.id
    paymentRepository.findAllByIdempotencyKey("idem-key-123") shouldHaveSize 1
}

@Test
fun `should reject invalid state transition`() {
    val order = orderRepository.save(createOrder(status = OrderStatus.DELIVERED))

    shouldThrow<InvalidStateTransitionException> {
        orderService.transition(order.id, OrderStatus.PENDING)
    }
}
```

### Test Configuration

`application-test.yml`:

```yaml
spring:
  jpa:
    show-sql: true
    properties:
      hibernate:
        format_sql: true
  cache:
    type: none

logging:
  level:
    org.springframework.test: WARN
    org.testcontainers: WARN
```

Always activate test profile explicitly:

```kotlin
@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTest : AbstractIntegrationTest() { /* ... */ }
```

## Output Format

When recommending test strategy, document the test plan:

```
Layer: {Controller | Service | Repository | Integration}
Slice: {@WebMvcTest | @DataJpaTest | @SpringBootTest | Plain JUnit 5 / Kotest}
Containers: {Postgres | Kafka | Redis | WireMock | none}
Mocking: {mockk() | @MockkBean | WireMock | none}
Coroutines: {runTest | n/a}
Cases: {list of test scenarios}
```

## Avoid

- `@SpringBootTest` for everything (slow, flaky)
- H2 for integration tests against Postgres-feature apps (JSONB, partial indexes, ON CONFLICT diverge)
- `Thread.sleep()` in async tests (use Awaitility or `runTest` virtual time)
- `@DirtiesContext` (kills test speed - redesign the test instead)
- Mockito for Kotlin classes (final by default - use MockK)
- `every` / `verify` for `suspend` functions (silently fails - use `coEvery` / `coVerify`)
- `@MockBean` / `@MockitoBean` for Kotlin classes (use `@MockkBean` from springmockk)
- `runBlocking` in test bodies (use `runTest` for virtual time)
- Testing implementation details (verify behavior, not method calls)
- `@DynamicPropertySource` when `@ServiceConnection` is available (Spring Boot 3.1+)
