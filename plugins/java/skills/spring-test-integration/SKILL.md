---
name: spring-test-integration
description: Spring Boot test slice strategy, Testcontainers patterns, and integration test architecture. Covers @DataJpaTest, @WebMvcTest, @SpringBootTest scoping, test fixtures, and Virtual Thread-safe test configuration.
metadata:
  category: backend
  tags: [testing, spring-boot, testcontainers, integration-test, test-slices]
user-invocable: false
---

# Spring Integration Testing

## When to Use

- Choosing the right Spring test slice for a layer
- Setting up Testcontainers for integration tests
- Designing reusable test fixtures and assertions
- Configuring test profiles and test-specific beans
- Writing async/Virtual Thread-safe tests

## Rules

- Never use `@SpringBootTest` when a slice test suffices — it's 10x slower
- Use Testcontainers with the real database — never H2 for integration tests
- Use `@MockitoBean` not `@MockBean` (deprecated since Spring Boot 3.4.0)
- Constructor injection with manual mocks over `@MockitoBean` when no Spring context needed
- AssertJ fluent assertions over JUnit `assertEquals`
- `@ActiveProfiles("test")` — always explicit, never rely on default
- Test-specific `@Configuration` classes belong in `src/test/java`, never in `src/main/java`
- Never use `Thread.sleep()` in async tests — use Awaitility
- Never use `@DirtiesContext` — redesign the test instead

## Pattern

### Test Slice Selection Guide

```
Repository layer       → @DataJpaTest (JPA, Flyway, Testcontainers Postgres)
Controller layer       → @WebMvcTest (MockMvc, no DB, mock services)
Service (logic only)   → Plain JUnit 5 + Mockito (no Spring context)
Service (Spring wiring)→ @SpringBootTest + @MockitoBean for externals
Full integration       → @SpringBootTest + Testcontainers + WebTestClient
```

### @DataJpaTest with Testcontainers

Good — `@ServiceConnection` (Spring Boot 3.1+) auto-configures datasource:

```java
@Testcontainers
@DataJpaTest
class OrderRepositoryTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired
    private OrderRepository orderRepository;

    @Test
    void shouldFindOrdersByStatus() {
        orderRepository.save(OrderTestFixtures.anOrder(OrderStatus.PAID));

        var results = orderRepository.findByStatus(OrderStatus.PAID);

        assertThat(results).hasSize(1)
            .first()
            .satisfies(order -> assertThat(order.getStatus()).isEqualTo(OrderStatus.PAID));
    }
}
```

### @WebMvcTest — Controller Slice

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired
    private MockMvc mockMvc;

    @MockitoBean
    private OrderService orderService;

    @Test
    void shouldReturnOrder() throws Exception {
        var order = OrderTestFixtures.anOrderDto();
        when(orderService.findById(1L)).thenReturn(order);

        mockMvc.perform(get("/api/orders/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PAID"));
    }
}
```

### Service Layer — Plain JUnit 5 (No Spring Context)

```java
class OrderServiceTest {
    private final OrderRepository orderRepository = mock(OrderRepository.class);
    private final PaymentGateway paymentGateway = mock(PaymentGateway.class);
    private final OrderService orderService = new OrderService(orderRepository, paymentGateway);

    @Test
    void shouldCompleteOrder() {
        var order = OrderTestFixtures.anOrder(OrderStatus.PENDING);
        when(orderRepository.findById(1L)).thenReturn(Optional.of(order));
        when(paymentGateway.charge(any())).thenReturn(PaymentResult.success());

        var result = orderService.complete(1L);

        assertThat(result.status()).isEqualTo(OrderStatus.PAID);
        verify(orderRepository).save(any(Order.class));
    }
}
```

### Singleton Container Pattern

For shared containers across multiple test classes:

```java
public abstract class AbstractIntegrationTest {
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine");
    static final GenericContainer<?> REDIS =
        new GenericContainer<>("redis:7-alpine").withExposedPorts(6379);

    static {
        POSTGRES.start();
        REDIS.start();
    }

    @DynamicPropertySource
    static void configureProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.data.redis.host", REDIS::getHost);
        registry.add("spring.data.redis.port", () -> REDIS.getMappedPort(6379));
    }
}
```

Prefer `@ServiceConnection` over `@DynamicPropertySource` when available:

```java
public abstract class AbstractIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Container
    @ServiceConnection
    static KafkaContainer kafka = new KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.0"));
}
```

### Test Fixture Patterns

Builder pattern for test entities:

```java
public class OrderTestFixtures {
    public static Order anOrder(OrderStatus status) {
        return Order.builder()
            .customerId(1L)
            .status(status)
            .totalAmount(BigDecimal.valueOf(99.99))
            .build();
    }

    public static OrderDto anOrderDto() {
        return new OrderDto(1L, 1L, OrderStatus.PAID, BigDecimal.valueOf(99.99));
    }
}
```

Bad — duplicated `@BeforeEach` setup:

```java
@BeforeEach
void setUp() {
    var order = new Order();
    order.setCustomerId(1L);
    order.setStatus(OrderStatus.PAID);
    order.setTotalAmount(BigDecimal.valueOf(99.99));
    // ... repeated in every test class
}
```

Good — shared fixture via `@TestConfiguration`:

```java
@TestConfiguration
class TestFixtureConfig {
    @Bean
    OrderTestFixtures orderTestFixtures() {
        return new OrderTestFixtures();
    }
}
```

### Mockito in Virtual Thread Context

Mockito is safe with Virtual Threads — no thread-local issues. For async/Virtual Thread tests, use Awaitility:

```java
@Test
void shouldProcessOrderAsync() {
    orderService.processAsync(orderId);

    await().atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> {
            var order = orderRepository.findById(orderId).orElseThrow();
            assertThat(order.getStatus()).isEqualTo(OrderStatus.COMPLETED);
        });
}
```

Bad — blocks test unreliably:

```java
orderService.processAsync(orderId);
Thread.sleep(2000); // Flaky, slow, unreliable
assertThat(orderRepository.findById(orderId).get().getStatus()).isEqualTo(OrderStatus.COMPLETED);
```

### Assertion Patterns

Recursive comparison for entities (ignoring generated fields):

```java
assertThat(actual)
    .usingRecursiveComparison()
    .ignoringFields("id", "createdAt", "updatedAt")
    .isEqualTo(expected);
```

Custom assertion class for domain objects:

```java
public class OrderAssert extends AbstractAssert<OrderAssert, Order> {
    public static OrderAssert assertThatOrder(Order actual) {
        return new OrderAssert(actual);
    }

    public OrderAssert isPaid() {
        assertThat(actual.getStatus()).isEqualTo(OrderStatus.PAID);
        return this;
    }

    private OrderAssert(Order actual) {
        super(actual, OrderAssert.class);
    }
}
```

JSON assertions for API responses:

```java
mockMvc.perform(get("/api/orders/1"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.id").value(1))
    .andExpect(jsonPath("$.items", hasSize(3)));
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

```java
@SpringBootTest
@ActiveProfiles("test")
class OrderIntegrationTest extends AbstractIntegrationTest {
    // ...
}
```

## Avoid

- `@SpringBootTest` for everything (slow, flaky)
- H2 for integration tests (use Testcontainers with real DB)
- `Thread.sleep()` in async tests (use Awaitility)
- `@DirtiesContext` (kills test speed — redesign the test instead)
- Testing implementation details (verify behavior, not method calls)
- `@MockBean` (deprecated since Spring Boot 3.4.0 — use `@MockitoBean`)
- `@DynamicPropertySource` when `@ServiceConnection` is available (Spring Boot 3.1+)
