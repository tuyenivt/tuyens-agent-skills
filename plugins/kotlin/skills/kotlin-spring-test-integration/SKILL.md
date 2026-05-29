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
- Setting up Testcontainers
- Writing async / coroutine / Virtual-Thread-safe integration tests

Atomic patterns (MockK, `coEvery`, `runTest`, fixture factories) live in `kotlin-testing-patterns`. This skill is about **wiring** them into Spring.

## Rules

- Never `@SpringBootTest` when a slice works - it's 10x slower.
- Testcontainers with the production engine, never H2 for Postgres-feature apps (JSONB, partial indexes, `ON CONFLICT` diverge).
- `@MockkBean` over `@MockBean` / `@MockitoBean`.
- `@ActiveProfiles("test")` always explicit.
- Test config classes live in `src/test/kotlin`, never `src/main/kotlin`.
- Never `Thread.sleep()` in async tests - Awaitility or `runTest` virtual time.
- Never `@DirtiesContext` - redesign the test instead.
- `kotlin("plugin.spring")` configured - otherwise test-relevant `@Service` / `@Configuration` are final.

## Patterns

### Slice selection

| Layer                     | Slice                                                                |
| ------------------------- | -------------------------------------------------------------------- |
| Repository                | `@DataJpaTest` (Flyway, Testcontainers Postgres)                     |
| Controller                | `@WebMvcTest` (MockMvc Kotlin DSL, no DB, mock services)             |
| Service logic only        | Plain JUnit 5 / Kotest + MockK (no Spring context)                   |
| Service Spring wiring     | `@SpringBootTest` + `@MockkBean` for externals                       |
| Full integration          | `@SpringBootTest` + Testcontainers + WebTestClient / MockMvc         |

### `@DataJpaTest` + Testcontainers

`@ServiceConnection` (Boot 3.1+) auto-wires the datasource:

```kotlin
@DataJpaTest
@Testcontainers
class OrderRepositoryTest {
    companion object {
        @Container @ServiceConnection @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine")
    }

    @Autowired lateinit var repo: OrderRepository

    @Test fun `finds orders by status`() {
        repo.save(createOrder(status = PAID))
        repo.findByStatus(PAID) shouldHaveSize 1
    }
}
```

### `@WebMvcTest` with `@MockkBean`

```kotlin
@WebMvcTest(OrderController::class)
class OrderControllerTest {
    @Autowired lateinit var mockMvc: MockMvc
    @MockkBean lateinit var service: OrderService

    @Test fun `GET order`() {
        every { service.findById(1L) } returns createOrderDto()
        mockMvc.get("/api/orders/1").andExpect { status { isOk() } }
    }

    @Test fun `GET via suspend service`() = runTest {
        coEvery { service.findByIdAsync(1L) } returns createOrderDto()
        mockMvc.get("/api/orders/1").andExpect { status { isOk() } }
        coVerify(exactly = 1) { service.findByIdAsync(1L) }
    }
}
```

### Singleton container base class

`withReuse(true)` plus `testcontainers.reuse.enable=true` in `~/.testcontainers.properties` for fast local re-runs. CI typically leaves reuse off.

```kotlin
@Testcontainers
abstract class AbstractIntegrationTest {
    companion object {
        @Container @ServiceConnection @JvmStatic
        val postgres = PostgreSQLContainer("postgres:16-alpine").withReuse(true)

        @Container @ServiceConnection @JvmStatic
        val kafka = KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.0")).withReuse(true)
    }
}
```

Without `@ServiceConnection`:

```kotlin
@DynamicPropertySource @JvmStatic
fun props(registry: DynamicPropertyRegistry) {
    registry.add("spring.data.redis.host", redis::getHost)
    registry.add("spring.data.redis.port") { redis.getMappedPort(6379) }
}
```

### WireMock for HTTP

Use for `@SpringBootTest` paths exercising real `WebClient` / `RestClient` wiring. For unit tests, `mockk<RestClient>()` directly.

```kotlin
@SpringBootTest(webEnvironment = RANDOM_PORT)
@WireMockTest(httpPort = 8089)
class PaymentIntegrationTest : AbstractIntegrationTest() {
    @Autowired lateinit var gateway: PaymentGateway

    @Test fun `processes payment`() {
        stubFor(post(urlPathEqualTo("/api/charges"))
            .willReturn(okJson("""{"status":"success","chargeId":"ch_123"}""")))
        gateway.charge(ChargeRequest(orderId = 1L, amount = BigDecimal.TEN)).status shouldBe "success"
    }
}
```

### Kafka

Testcontainers `KafkaContainer` over `@EmbeddedKafka` - matches production version. Verify produced messages with a test consumer; verify consumed messages with Awaitility on downstream state.

```kotlin
@Test fun `placing order publishes event and updates async`() {
    val id = orderService.placeOrder(createOrderRequest()).id
    await().atMost(5.seconds.toJavaDuration()).untilAsserted {
        orderRepo.findById(id).get().status shouldBe ENRICHED
    }
}
```

### `@DataJpaTest` vs `@SpringBootTest` rollback

`@DataJpaTest` wraps each test in a transaction that rolls back. `@SpringBootTest` does **not** - state survives. Adding `@Transactional` to `@SpringBootTest` hides commit-dependent side effects (`@TransactionalEventListener(AFTER_COMMIT)`, async listeners) - the rollback makes them disappear. Prefer explicit cleanup or `@Sql(scripts = "/cleanup.sql", executionPhase = AFTER_TEST_METHOD)`.

### Coroutine tests

`runTest { }` + `coEvery` / `coVerify` + Turbine for `Flow`. Canonical examples in `kotlin-testing-patterns`. Same patterns apply inside `@SpringBootTest` and `@WebMvcTest`.

### Awaitility for non-coroutine async

```kotlin
@Test fun `processes async`() {
    orderService.processAsync(orderId)
    await().atMost(Duration.ofSeconds(5)).pollInterval(Duration.ofMillis(100)).untilAsserted {
        orderRepo.findById(orderId).get().status shouldBe COMPLETED
    }
}
```

### Test profile

`application-test.yml`: enable `spring.jpa.show-sql`, disable cache (`spring.cache.type: none`), raise `org.springframework.test` / `org.testcontainers` log levels to WARN. Always `@ActiveProfiles("test")`.

## Output Format

```
Layer: {Controller | Service | Repository | Integration}
Slice: {@WebMvcTest | @DataJpaTest | @SpringBootTest | Plain JUnit/Kotest}
Containers: {Postgres | Kafka | Redis | WireMock | none}
Mocking: {mockk() | @MockkBean | WireMock | none}
Coroutines: {runTest | n/a}
Cases: {scenarios}
```

## Avoid

- `@SpringBootTest` when a slice works
- H2 for Postgres-feature apps
- `Thread.sleep()` in async tests
- `@DirtiesContext` - redesign isolation
- Mockito for Kotlin classes
- `every` / `verify` for `suspend` (use `coEvery` / `coVerify`)
- `@MockBean` / `@MockitoBean` for Kotlin classes
- `runBlocking` in test bodies
- Testing implementation details (assert behavior, not method calls)
- `@DynamicPropertySource` when `@ServiceConnection` works
