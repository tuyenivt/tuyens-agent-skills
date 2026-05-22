---
name: spring-test-integration
description: "Spring test slices and Testcontainers: @DataJpaTest, @WebMvcTest, @SpringBootTest, singleton containers, fixtures, Awaitility, security tests."
metadata:
  category: backend
  tags: [testing, spring-boot, testcontainers, integration-test, test-slices]
user-invocable: false
---

# Spring Integration Testing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing the right Spring test slice
- Setting up Testcontainers
- Writing async / Virtual Thread-safe tests
- Designing reusable fixtures

## Rules

- Match slice to layer (table below); never `@SpringBootTest` when a slice suffices
- Testcontainers with the production DB engine when SQL is non-standard (JSONB, partial indexes, `ON CONFLICT`, window functions) - H2 silently passes prod-failing syntax
- `@MockitoBean` (Boot 3.4+), not `@MockBean`
- AssertJ over `assertEquals`
- `@ActiveProfiles("test")` always explicit
- No `Thread.sleep()` in async tests - use Awaitility
- No `@DirtiesContext` - redesign the test instead

## Test Slice Selection

| Layer                    | Choice                                              |
| ------------------------ | --------------------------------------------------- |
| Repository               | `@DataJpaTest` + Testcontainers Postgres            |
| Controller               | `@WebMvcTest` + MockMvc, mock services              |
| Service (pure logic)     | Plain JUnit 5 + Mockito                             |
| Service (Spring wiring)  | `@SpringBootTest` + `@MockitoBean` externals        |
| Full integration         | `@SpringBootTest` + Testcontainers + WebTestClient  |

## Patterns

### `@DataJpaTest` with `@ServiceConnection`

```java
@Testcontainers @DataJpaTest
class OrderRepositoryTest {
    @Container @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderRepository orderRepository;

    @Test
    void findsByStatus() {
        orderRepository.save(OrderTestFixtures.anOrder(PAID));
        assertThat(orderRepository.findByStatus(PAID)).hasSize(1);
    }
}
```

Prefer `@ServiceConnection` (Spring Boot 3.1+) over `@DynamicPropertySource`.

### `@WebMvcTest` controller slice

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean OrderService orderService;

    @Test
    void returnsOrder() throws Exception {
        when(orderService.findById(1L)).thenReturn(OrderTestFixtures.anOrderDto());
        mockMvc.perform(get("/api/orders/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PAID"));
    }
}
```

### Plain JUnit for service logic

```java
class OrderServiceTest {
    OrderRepository repo = mock(OrderRepository.class);
    PaymentGateway gateway = mock(PaymentGateway.class);
    OrderService service = new OrderService(repo, gateway);

    @Test
    void completesOrder() {
        when(repo.findById(1L)).thenReturn(Optional.of(OrderTestFixtures.anOrder(PENDING)));
        when(gateway.charge(any())).thenReturn(PaymentResult.success());

        var result = service.complete(1L);

        assertThat(result.status()).isEqualTo(PAID);
        verify(repo).save(any(Order.class));
    }
}
```

### Singleton container pattern

`@Container` + `@Testcontainers` restarts per class; for a multi-class suite this is the main test-time cost. Make the container a JVM-level singleton in a base class:

```java
public abstract class AbstractIntegrationTest {
    @Container @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine").withReuse(true);

    @Container @ServiceConnection
    static final KafkaContainer KAFKA =
        new KafkaContainer(DockerImageName.parse("confluentinc/cp-kafka:7.6.0"));
}
```

`withReuse(true)` + `testcontainers.reuse.enable=true` in `~/.testcontainers.properties` survives JVM exit. Local-only - keep off in CI for clean runs.

### Security tests

Controller slices auto-wire the filter chain but bind no user. Use Spring Security Test post-processors:

```java
@WebMvcTest(OrderController.class)
@Import(SecurityConfig.class)  // controller slices don't auto-load it
class OrderControllerTest {
    @Test @WithMockUser(roles = "ADMIN")
    void admin_can_delete() throws Exception {
        mockMvc.perform(delete("/api/orders/1").with(csrf())).andExpect(status().isNoContent());
    }

    @Test
    void anonymous_unauthorized() throws Exception {
        mockMvc.perform(delete("/api/orders/1").with(csrf())).andExpect(status().isUnauthorized());
    }

    @Test
    void with_jwt() throws Exception {
        mockMvc.perform(get("/api/orders/1")
                .with(jwt().jwt(j -> j.claim("scope", "orders:read"))))
            .andExpect(status().isOk());
    }
}
```

### Transactional rollback gotcha

`@DataJpaTest` auto-rolls back. `@SpringBootTest` does NOT by default - add `@Transactional` to the test class for rollback. But `@Transactional` does NOT cover spawned threads (`@Async`, `REQUIRES_NEW`, event listeners with their own transaction). Clean those up with `@Sql(executionPhase = AFTER_TEST_METHOD)` or `@AfterEach` truncate.

### Async tests with Awaitility

```java
@Test
void processesAsync() {
    orderService.processAsync(orderId);

    await().atMost(Duration.ofSeconds(5))
        .pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> assertThat(orderRepository.findById(orderId).orElseThrow().getStatus())
            .isEqualTo(COMPLETED));
}
```

### WireMock for outbound HTTP

For integration tests where the HTTP contract matters, use WireMock - it exercises the actual `RestClient` / `WebClient` config (timeouts, retries, deserialization) rather than bypassing it via a mocked client.

```java
@SpringBootTest(webEnvironment = RANDOM_PORT)
@WireMockTest(httpPort = 8089)
class PaymentIntegrationTest extends AbstractIntegrationTest {
    @Test
    void processesPayment() {
        stubFor(post(urlPathEqualTo("/api/charges"))
            .willReturn(okJson("""{"status":"success","chargeId":"ch_123"}""")));

        var result = paymentGateway.charge(new ChargeRequest(orderId, amount));

        assertThat(result.status()).isEqualTo("success");
        verify(postRequestedFor(urlPathEqualTo("/api/charges"))
            .withRequestBody(matchingJsonPath("$.amount")));
    }
}
```

### Fixtures

Static factory methods on a `*TestFixtures` class per aggregate; only reach for `@TestConfiguration` when fixtures need Spring-managed dependencies.

```java
public class OrderTestFixtures {
    public static Order anOrder(OrderStatus status) {
        return Order.builder().customerId(1L).status(status).totalAmount(BigDecimal.valueOf(99.99)).build();
    }
    public static OrderDto anOrderDto() {
        return new OrderDto(1L, 1L, PAID, BigDecimal.valueOf(99.99));
    }
}
```

Recursive comparison ignoring generated fields:

```java
assertThat(actual)
    .usingRecursiveComparison()
    .ignoringFields("id", "createdAt", "updatedAt")
    .isEqualTo(expected);
```

## Output Format

```
Layer: {Controller | Service | Repository | Integration}
Slice: {@WebMvcTest | @DataJpaTest | @SpringBootTest | Plain JUnit}
Containers: {Postgres | Kafka | Redis | WireMock | none}
Mocking: {mock() | @MockitoBean | WireMock | none}
Cases: {list}
```

## Avoid

- `@SpringBootTest` when a slice suffices
- H2 for apps using Postgres features
- `Thread.sleep()` in async tests
- `@DirtiesContext` (kills suite speed)
- `@MockBean` (deprecated since Boot 3.4)
- Testing implementation details over behavior
