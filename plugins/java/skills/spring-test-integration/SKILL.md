---
name: spring-test-integration
description: "Spring Boot 3.5 test slices and Testcontainers: @DataJpaTest, @WebMvcTest, @JsonTest, @ServiceConnection, Awaitility, security."
metadata:
  category: backend
  tags: [testing, spring-boot, testcontainers, integration-test, test-slices]
user-invocable: false
---

# Spring Integration Testing

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Choosing the right Spring test slice
- Setting up Testcontainers with `@ServiceConnection`
- Async / Virtual Thread-safe tests
- Reusable fixtures and security tests

## Rules

- Match slice to layer (see table); avoid `@SpringBootTest` when a slice fits
- Testcontainers with the production DB engine - H2 silently passes Postgres-only syntax (JSONB, partial indexes, `ON CONFLICT`, window functions)
- `@MockitoBean` (Boot 3.4+), not `@MockBean`
- Mockito strict stubbing (default in JUnit 5 extension); fix `UnnecessaryStubbingException` by deleting the stub, not by `lenient()`
- AssertJ over `assertEquals`; `@ActiveProfiles("test")` always explicit
- No `Thread.sleep()` in async tests - use Awaitility
- No `@DirtiesContext` - redesign or use `@Sql` cleanup

## Slice Selection

| Layer                   | Choice                                              |
| ----------------------- | --------------------------------------------------- |
| Repository              | `@DataJpaTest` + Testcontainers Postgres            |
| Controller              | `@WebMvcTest` + MockMvc, `@MockitoBean` services    |
| JSON (de)serialization  | `@JsonTest` + `JacksonTester`                       |
| Service (pure logic)    | Plain JUnit 5 + Mockito                             |
| Service (Spring wiring) | `@SpringBootTest` + `@MockitoBean` externals        |
| Full integration        | `@SpringBootTest` + Testcontainers + WebTestClient  |

## Patterns

### `@DataJpaTest` with `@ServiceConnection`

`@ServiceConnection` (Boot 3.1+) auto-wires the container to Spring's datasource - no `@DynamicPropertySource` glue.

```java
@Testcontainers @DataJpaTest
class OrderRepositoryTest {
    @Container @ServiceConnection
    static PostgreSQLContainer<?> postgres = new PostgreSQLContainer<>("postgres:16-alpine");

    @Autowired OrderRepository orderRepository;

    @Test
    void findsByStatus() {
        orderRepository.save(OrderFixtures.anOrder(PAID));
        assertThat(orderRepository.findByStatus(PAID)).hasSize(1);
    }
}
```

`@DataJpaTest` defaults to in-memory DB; the container override is what activates Postgres.

### `@WebMvcTest` controller slice

```java
@WebMvcTest(OrderController.class)
class OrderControllerTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean OrderService orderService;

    @Test
    void returnsOrder() throws Exception {
        when(orderService.findById(1L)).thenReturn(OrderFixtures.anOrderDto());
        mockMvc.perform(get("/api/orders/1"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("PAID"));
    }
}
```

### `@JsonTest` for serialization contracts

```java
@JsonTest
class OrderDtoJsonTest {
    @Autowired JacksonTester<OrderDto> json;

    @Test
    void serializesAmount() throws Exception {
        assertThat(json.write(new OrderDto(1L, 1L, PAID, new BigDecimal("99.99"))))
            .extractingJsonPathStringValue("$.totalAmount").isEqualTo("99.99");
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
        when(repo.findById(1L)).thenReturn(Optional.of(OrderFixtures.anOrder(PENDING)));
        when(gateway.charge(any())).thenReturn(PaymentResult.success());

        assertThat(service.complete(1L).status()).isEqualTo(PAID);
        verify(repo).save(any(Order.class));
    }
}
```

### Singleton containers across the suite

`@Container` restarts per class - the main cost in multi-class suites. Hoist to a JVM-level singleton in a base class:

```java
public abstract class AbstractIntegrationTest {
    @Container @ServiceConnection
    static final PostgreSQLContainer<?> POSTGRES =
        new PostgreSQLContainer<>("postgres:16-alpine").withReuse(true);
}
```

`withReuse(true)` + `testcontainers.reuse.enable=true` in `~/.testcontainers.properties` keeps the container across JVM exits. Local-only; CI runs clean.

### Security tests

Controller slices auto-wire the filter chain but bind no user. Import your `SecurityConfig` and use Spring Security Test post-processors.

```java
@WebMvcTest(OrderController.class) @Import(SecurityConfig.class)
class OrderControllerSecurityTest {
    @Autowired MockMvc mockMvc;
    @MockitoBean OrderService orderService;

    @Test @WithMockUser(roles = "ADMIN")
    void admin_can_delete() throws Exception {
        mockMvc.perform(delete("/api/orders/1").with(csrf())).andExpect(status().isNoContent());
    }

    @Test
    void anonymous_unauthorized() throws Exception {
        mockMvc.perform(delete("/api/orders/1").with(csrf())).andExpect(status().isUnauthorized());
    }

    @Test
    void jwt_scope_allows_read() throws Exception {
        mockMvc.perform(get("/api/orders/1")
                .with(jwt().jwt(j -> j.claim("scope", "orders:read"))))
            .andExpect(status().isOk());
    }
}
```

### Transactional rollback gotcha

`@DataJpaTest` auto-rolls back. `@SpringBootTest` does not - add `@Transactional` on the test class. `@Transactional` does not cover spawned threads (`@Async`, `REQUIRES_NEW`, event listeners with their own tx). Clean those with `@Sql(executionPhase = AFTER_TEST_METHOD)` or an `@AfterEach` truncate.

### Async with Awaitility

```java
@Test
void processesAsync() {
    orderService.processAsync(orderId);

    await().atMost(Duration.ofSeconds(5)).pollInterval(Duration.ofMillis(100))
        .untilAsserted(() -> assertThat(orderRepository.findById(orderId).orElseThrow().getStatus())
            .isEqualTo(COMPLETED));
}
```

### WireMock for outbound HTTP

Exercises the real `RestClient` / `WebClient` config (timeouts, retries, deserialization) rather than bypassing it via a mocked client.

```java
@SpringBootTest(webEnvironment = RANDOM_PORT)
@WireMockTest(httpPort = 8089)
class PaymentIntegrationTest extends AbstractIntegrationTest {
    @Test
    void processesPayment() {
        stubFor(post(urlPathEqualTo("/api/charges"))
            .willReturn(okJson("""{"status":"success","chargeId":"ch_123"}""")));

        assertThat(paymentGateway.charge(new ChargeRequest(orderId, amount)).status()).isEqualTo("success");
        verify(postRequestedFor(urlPathEqualTo("/api/charges"))
            .withRequestBody(matchingJsonPath("$.amount")));
    }
}
```

### Fixtures

Static factories on a `*Fixtures` class per aggregate. Use `@TestConfiguration` only when fixtures need Spring-managed beans.

```java
public class OrderFixtures {
    public static Order anOrder(OrderStatus status) {
        return Order.builder().customerId(1L).status(status).totalAmount(new BigDecimal("99.99")).build();
    }
    public static OrderDto anOrderDto() { return new OrderDto(1L, 1L, PAID, new BigDecimal("99.99")); }
}
```

For entity comparison, ignore generated fields:

```java
assertThat(actual).usingRecursiveComparison()
    .ignoringFields("id", "createdAt", "updatedAt").isEqualTo(expected);
```

## Output Format

```
Layer: {Controller | Service | Repository | JSON | Integration}
Slice: {@WebMvcTest | @DataJpaTest | @JsonTest | @SpringBootTest | Plain JUnit}
Containers: {Postgres | Kafka | Redis | WireMock | none}
Mocking: {mock() | @MockitoBean | WireMock | none}
Cases: {list}
```

## Avoid

- `@SpringBootTest` when a slice suffices
- H2 for apps using Postgres features
- `Thread.sleep()` in async tests
- `@DirtiesContext` (kills suite speed)
- `lenient()` to silence strict stubbing - delete the unused stub
- Testing implementation details over behavior
