---
name: spring-test-integration
description: "Spring Boot 4 test slices and Testcontainers 2: @DataJpaTest, @WebMvcTest, @JsonTest, @ServiceConnection, Awaitility, security."
metadata:
  category: backend
  tags: [testing, spring-boot, testcontainers, integration-test, test-slices]
user-invocable: false
---

# Spring Integration Testing

> Load `Use skill: stack-detect` first to determine the project stack. Its `Database` picks the container image and the cleanup/catalog SQL (PostgreSQL and MySQL variants below); its `Build tool` picks Gradle or Maven dependency syntax. The engine's major version comes from the Tech Stack, compose/Helm files or the managed-DB version (Aurora MySQL 3 = MySQL 8.0); unknown -> state the assumed version. `Database: unknown` - give both variants.

Written for Boot 4: slice annotations live in per-technology modules (`org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest`, `org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest`) brought in by `spring-boot-starter-<tech>-test`, and Testcontainers is 2.x. A Boot 3.x project keeps the Boot 3 packages, `spring-boot-starter-test` and Testcontainers 1.x (`org.testcontainers:postgresql`, generic `PostgreSQLContainer<?>`) - write for the version the build declares.

## When to Use

- Choosing the right Spring test slice; writing missing tests
- Setting up Testcontainers with `@ServiceConnection`; migrating off H2
- Async, commit-gated and concurrency tests
- Reusable fixtures and security tests
- Reviewing a test suite (flakiness, speed, false passes)

## Rules

- Match slice to layer (table); avoid `@SpringBootTest` when a slice fits
- Testcontainers with the production DB engine and major version - H2 silently passes or fails differently on engine-specific SQL (JSONB, partial indexes, `ON CONFLICT`, window functions, locking)
- `@MockitoBean` / `@MockitoSpyBean` (Boot 3.4+; Boot 4 removed `@MockBean` / `@SpyBean`), declared on the test class or a shared base class - never inside a `@Configuration` / `@TestConfiguration` class
- Mockito strict stubbing (the `MockitoExtension` default); fix `UnnecessaryStubbingException` by deleting the stub, not by `lenient()`
- AssertJ over `assertEquals`; `@ActiveProfiles("test")` explicit
- No `Thread.sleep()` in async tests - use Awaitility
- No `@DirtiesContext` - redesign or clean up explicitly
- Context-cache fragmentation is the dominant cost in a slow suite, ahead of containers. Every distinct combination of `@MockitoBean`, `@TestPropertySource`, `@DynamicPropertySource`, `@EmbeddedKafka` and `@Import` is a separate cache key and a separate context build - declare them on shared base classes so classes collapse onto a handful of contexts, and count the target number before restructuring

## Slice Selection

| Layer                   | Choice                                              |
| ----------------------- | --------------------------------------------------- |
| Repository              | `@DataJpaTest` + Testcontainers                     |
| Controller              | `@WebMvcTest` + MockMvc, `@MockitoBean` services    |
| JSON (de)serialization  | `@JsonTest` + `JacksonTester`                       |
| Outbound HTTP client    | `@RestClientTest` (RestClient/RestTemplate) or `@SpringBootTest` + WireMock (real timeouts/retries) |
| Service (pure logic)    | Plain JUnit + Mockito                               |
| Service (Spring wiring) | `@SpringBootTest` + `@MockitoBean` externals        |
| Full integration        | `@SpringBootTest(RANDOM_PORT)` + Testcontainers + `@AutoConfigureRestTestClient` (MVC) / `@AutoConfigureWebTestClient` (WebFlux) |

"Spring wiring" means the proxy behavior itself is under test (tx rollback, `@PreAuthorize`, listener firing). Injectable collaborators alone don't make it Spring wiring - use plain JUnit. A commit-gated path (`AFTER_COMMIT` listener, outbox relay) is Spring wiring *and* needs the real database, because the commit has to happen: `@SpringBootTest` + Testcontainers, no `@Transactional`. A container-backed `@SpringBootTest` with no HTTP surface is "Service (Spring wiring)".

Boot 4's `@SpringBootTest` wires no client by itself: `@AutoConfigureMockMvc` for MockMvc, `@AutoConfigureRestTestClient` for `RestTestClient` (the replacement for `TestRestTemplate`), `@AutoConfigureWebTestClient` for `WebTestClient`. An existing `TestRestTemplate` suite needs `@AutoConfigureTestRestTemplate`, the import moved to `org.springframework.boot.resttestclient.TestRestTemplate`, and the `spring-boot-resttestclient` + `spring-boot-restclient` dependencies. Boot 3.x: `RANDOM_PORT` supplies `TestRestTemplate` and `WebTestClient` itself; `RestTestClient` does not exist.

## Patterns

### `@DataJpaTest` with `@ServiceConnection`

`@ServiceConnection` wires the container into Spring's connection properties - no `@DynamicPropertySource` glue. It works on `PostgreSQLContainer`, `MySQLContainer`, `RabbitMQContainer`, Kafka containers and Redis (`new GenericContainer<>("redis:7").withExposedPorts(6379)`).

```java
@Testcontainers @DataJpaTest
class OrderRepositoryTest {
    @Container @ServiceConnection
    static PostgreSQLContainer postgres = new PostgreSQLContainer("postgres:16-alpine");   // MySQL: new MySQLContainer("mysql:8.0")

    @Autowired OrderRepository orderRepository;

    @Test
    void findsByStatus() {
        orderRepository.save(OrderFixtures.anOrder(PAID));
        assertThat(orderRepository.findByStatus(PAID)).hasSize(1);
    }
}
```

- `@DataJpaTest` (`Replace.NON_TEST` default) keeps a test database - one wired through `@ServiceConnection`, a `@DynamicPropertySource` URL, or a `jdbc:tc:` URL - and swaps anything else for an embedded one. Boot 3.0-3.3: both wirings need `@AutoConfigureTestDatabase(replace = Replace.NONE)`.
- Data slices (`@DataJpaTest`, `@JdbcTest`, `@JooqTest`) and `@SpringBootTest` run Flyway/Liquibase by default (on Boot 4 only with `spring-boot-starter-flyway` / `-liquibase` - a bare `flyway-core` migrates nothing), so tests exercise the real schema; `@WebMvcTest` / `@JsonTest` run none. Disable migrations only deliberately (`spring.flyway.enabled=false` + `ddl-auto: create-drop`).
- Pin image tags to the production major version (`postgres:16-alpine`, `mysql:8.0` for Aurora MySQL 3, `rabbitmq:4.1-management`).

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
        // BigDecimal serializes as a JSON number by default; assert a string only when the
        // field declares @JsonFormat(shape = STRING)
        assertThat(json.write(new OrderDto(1L, 1L, PAID, new BigDecimal("99.99"))))
            .extractingJsonPathNumberValue("$.totalAmount").isEqualTo(99.99);
    }
}
```

### Plain JUnit for service logic

```java
@ExtendWith(MockitoExtension.class)   // bare mock() gets no strict stubbing - only the extension does
class OrderServiceTest {
    @Mock OrderRepository repo;
    @Mock PaymentGateway gateway;
    @InjectMocks OrderService service;

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

`@Container` stops/starts per test class, and each class's `@ServiceConnection` field is its own context-cache key - per-class containers both restart and defeat context caching. For one container per JVM, start it in a base class and skip the `@Testcontainers`/`@Container` lifecycle; multi-class suites extend this base:

```java
public abstract class AbstractIntegrationTest {
    @ServiceConnection
    static final PostgreSQLContainer POSTGRES = new PostgreSQLContainer("postgres:16-alpine");   // org.testcontainers.postgresql
    @ServiceConnection
    static final RabbitMQContainer RABBIT = new RabbitMQContainer("rabbitmq:4.1-management");
    static { POSTGRES.start(); RABBIT.start(); }   // manual start = JVM singleton
}
```

Each Gradle/Maven fork is its own JVM with its own singleton containers, so parallel forks do not share data. `withReuse(true)` + `testcontainers.reuse.enable=true` in `~/.testcontainers.properties` keeps containers across runs and shares them between forks - local only, and then keep `maxParallelForks = 1` or give each fork its own schema.

### Test dependencies (H2 -> Testcontainers migration)

```groovy
// one -test starter per technology in use; each brings spring-boot-starter-test (JUnit 6, Mockito, AssertJ, Awaitility)
testImplementation 'org.springframework.boot:spring-boot-starter-data-jpa-test'
testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
testImplementation 'org.springframework.boot:spring-boot-starter-security-test'   // jwt(), csrf(), @WithMockUser
testImplementation 'org.springframework.boot:spring-boot-testcontainers'          // @ServiceConnection
testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
testImplementation 'org.testcontainers:testcontainers-postgresql'   // or -mysql; -rabbitmq / -kafka per broker
testImplementation 'org.springframework.boot:spring-boot-starter-kafka-test'   // spring-kafka-test: ContainerTestUtils, @EmbeddedKafka
testImplementation 'org.wiremock:wiremock-standalone:3.10.0'       // not in the Boot BOM - pin it
// remove: testRuntimeOnly 'com.h2database:h2'
```

Maven: the same coordinates with `<scope>test</scope>` (versions from the Boot parent except WireMock). Removing H2 is the enforcement step: any test still pointing at an H2 URL then fails loudly.

### Security tests

Controller slices wire the filter chain but no user (on Boot 4 the slice's security auto-configuration comes only from `spring-boot-starter-security-test`), and `@WebMvcTest` loads neither a custom `SecurityFilterChain` nor `@EnableMethodSecurity` configuration from a separate `@Configuration` class (on the `@SpringBootApplication` class it does apply) - `@Import` them, or `@PreAuthorize` silently no-ops and the test passes for the wrong reason. Method-security rules are asserted in a `@SpringBootTest` against the real bean (a `@MockitoBean` replaces the proxy).

Importing a resource-server config into a slice needs a `JwtDecoder` bean - stub it, or a config using `fromIssuerLocation` fetches the issuer at startup. Tests using the `jwt()` post-processor never call the decoder; a full `@SpringBootTest` with Boot's property-configured decoder resolves the issuer lazily and starts without it.

```java
@WebMvcTest(OrderController.class) @Import(SecurityConfig.class)
class OrderControllerSecurityTest {
    @Autowired MockMvc mockMvc;
    @Autowired JwtAuthenticationConverter jwtConverter;   // the production claim mapping
    @Autowired JsonMapper json;                           // Boot's Jackson 3 mapper (tools.jackson.databind.json)
    @MockitoBean OrderService orderService;
    @MockitoBean JwtDecoder jwtDecoder;

    @Test
    void realm_role_from_real_token_shape() throws Exception {
        Map<String, Object> claims = json.readValue(
            new ClassPathResource("tokens/finance-user.json").getInputStream(), new TypeReference<>() {});
        // decoded tokens carry epoch numbers; Jwt requires Instant timestamps
        Stream.of("iat", "exp", "nbf").forEach(k -> claims.computeIfPresent(k, (n, v) -> Instant.ofEpochSecond(((Number) v).longValue())));
        mockMvc.perform(post("/api/admin/refunds/1/approve")
                .with(csrf())   // jwt() sends no Authorization header, so the bearer CSRF exemption does not apply
                .with(jwt().jwt(j -> j.claims(c -> c.putAll(claims)))
                    .authorities(jwtConverter.convert(Jwt.withTokenValue("t").header("alg", "none").claims(c -> c.putAll(claims)).build()).getAuthorities())))
            .andExpect(status().isOk());
    }

    @Test
    void anonymous_unauthorized() throws Exception {
        mockMvc.perform(get("/api/orders/1")).andExpect(status().isUnauthorized());
    }

    // session-based apps use @WithMockUser(roles = ...); writes need .with(csrf()) unless the imported config disables CSRF
}
```

`jwt()` alone maps only `scope`/`scp` to `SCOPE_*`; role rules need the production converter's authorities, which is also the only form that catches a broken claim mapping (a nested claim like Keycloak `realm_access.roles` needs a custom converter - `JwtGrantedAuthoritiesConverter` cannot reach it). `hasRole` matching is case-sensitive: a fixture whose role values differ in case from the rule is a mapping bug, not a test to paper over. A route guarded by both a URL rule and `@PreAuthorize` needs a token satisfying both - test each layer's denial separately.

### Transactions in tests

- `@DataJpaTest` rolls back each test. `@SpringBootTest` with the default `MOCK` environment rolls back when the test class is `@Transactional`; under `RANDOM_PORT`/`DEFINED_PORT` the request runs on a server thread in its own transaction, so the test's rollback cleans up nothing it wrote.
- Inside a test transaction: `AFTER_COMMIT` listeners never fire (no commit); `@Async` work and `REQUIRES_NEW` methods run outside it - they cannot see its uncommitted rows (or block on its locks), and `REQUIRES_NEW` writes commit and survive the rollback.
- For those flows: no `@Transactional` on the test, explicit cleanup, and Awaitility for the post-commit effect.

Cleanup: `@Sql(executionPhase = AFTER_TEST_METHOD)` when a script exists; otherwise an `@AfterEach` that truncates the application tables - never `flyway_schema_history` / `databasechangelog`:

```sql
-- PostgreSQL
TRUNCATE orders, order_lines, shipments RESTART IDENTITY CASCADE;
-- MySQL: FOREIGN_KEY_CHECKS is per session, so run all four on one connection (an @Sql script, or
-- jdbc.execute((ConnectionCallback<Void>) c -> {...}))
SET FOREIGN_KEY_CHECKS = 0; TRUNCATE TABLE order_lines; TRUNCATE TABLE shipments; TRUNCATE TABLE orders; SET FOREIGN_KEY_CHECKS = 1;
```

A singleton context also keeps its caches between tests: clear the `CacheManager` in `@AfterEach`, or set `spring.cache.type=none` in the test profile.

### Concurrency and schema assertions

- Row-locking behavior (`FOR UPDATE`, `SKIP LOCKED`, a conditional `UPDATE`) needs two real transactions on two threads. In `@DataJpaTest` remove the test-managed transaction (`@Transactional(propagation = NOT_SUPPORTED)`); in a non-transactional `@SpringBootTest` there is nothing to remove. Start both callers behind a `CountDownLatch`, collect outcomes, and assert exactly one succeeded and the row's final value. The code under test needs a real guard (an atomic conditional `UPDATE`, `@Version`, or a pessimistic lock - `spring-jpa-performance`); adding it is a production change. Add the test as a method in an existing class that shares its context rather than a new class.
- Assert migration DDL from the catalog, not a query plan (the planner prefers a seq scan on a ten-row table): PostgreSQL `SELECT indexdef FROM pg_indexes WHERE indexname = ?`; MySQL `information_schema.STATISTICS`.

### Broker round trips

```java
@Autowired KafkaListenerEndpointRegistry registry;

@BeforeEach
void waitForAssignment() {   // publishing before the consumer owns its partitions is the classic flake
    registry.getListenerContainers().forEach(c -> ContainerTestUtils.waitForAssignment(c, 1));   // = the topic's partition count
}
```

Declare test topics as `@TestConfiguration` `NewTopic` beans with an explicit partition count (`TopicBuilder.name(...).partitions(1).build()`) and set `spring.kafka.consumer.auto-offset-reset: earliest`. Kafka containers: `org.testcontainers.kafka.KafkaContainer` (`apache/kafka-native`) or `ConfluentKafkaContainer` - the old `org.testcontainers.containers.KafkaContainer` is deprecated. `@EmbeddedKafka` is fine for listener contract tests, and each distinct configuration is another context key. RabbitMQ: wait until the listener containers report `isRunning()`, then assert the effect with Awaitility.

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

Asserting that work did *not* happen (a duplicate was skipped, a rollback fired nothing) needs a window: `await().during(Duration.ofMillis(500)).atMost(Duration.ofSeconds(1)).untilAsserted(...)` - `atMost` must exceed `during`.

### WireMock for outbound HTTP

Exercises the real `RestClient` / `WebClient` config (timeouts, retries, deserialization) rather than bypassing it with a mocked client. One server per JVM, like the singleton containers - a `@RegisterExtension` server stops after each class and restarts on a new port, while the cached context still points at the old one:

```java
public abstract class AbstractHttpIntegrationTest extends AbstractIntegrationTest {
    protected static final WireMockServer WIREMOCK = new WireMockServer(wireMockConfig().dynamicPort());
    static { WIREMOCK.start(); }

    @DynamicPropertySource
    static void gatewayUrl(DynamicPropertyRegistry registry) {
        registry.add("payment.base-url", WIREMOCK::baseUrl);
    }

    @AfterEach
    void resetWireMock() { WIREMOCK.resetAll(); }
}
```

```java
@SpringBootTest
class PaymentIntegrationTest extends AbstractHttpIntegrationTest {
    @Autowired PaymentGateway paymentGateway;

    @Test
    void processesPayment() {
        WIREMOCK.stubFor(post(urlPathEqualTo("/api/charges"))
            .willReturn(okJson("""
                {"status":"success","chargeId":"ch_123"}""")));

        assertThat(paymentGateway.charge(new ChargeRequest(1L, new BigDecimal("99.99"))).status()).isEqualTo("success");
        WIREMOCK.verify(postRequestedFor(urlPathEqualTo("/api/charges")).withRequestBody(matchingJsonPath("$.amount")));
    }

    @Test
    void givesUpAfterReadTimeout() {
        WIREMOCK.stubFor(post(urlPathEqualTo("/api/charges")).willReturn(ok().withFixedDelay(3_000)));   // > the 2 s read timeout
        assertThatThrownBy(() -> paymentGateway.charge(new ChargeRequest(1L, BigDecimal.TEN)))
            .isInstanceOf(ResourceAccessException.class);   // root cause varies by client: SocketTimeoutException,
                                                        // HttpTimeoutException (JDK client), ReadTimeoutException (Netty)
    }
}
```

The timeout test fails if the read timeout is ever widened or dropped - the regression a mocked client cannot catch. Setting the timeout is the production change: `var f = new SimpleClientHttpRequestFactory(); f.setReadTimeout(Duration.ofSeconds(2)); RestClient.builder().requestFactory(f)`. A `@WireMockTest` extension exposes its dynamic port only through an injected `WireMockRuntimeInfo`, which a static `@DynamicPropertySource` cannot reach - hence the manual server.

### Fixtures

Static factories on a `*Fixtures` class per aggregate; `@TestConfiguration` only when fixtures need Spring-managed beans. Realistic payloads (tokens, webhook bodies) live as JSON under `src/test/resources` and are loaded into the test.

```java
assertThat(actual).usingRecursiveComparison().ignoringFields("id", "createdAt", "updatedAt").isEqualTo(expected);
```

## Output Format

In every mode, emit the header block once (Engine, production changes, suite-level artifacts: build-file changes, test properties, shared base classes), then one block per test class of the target suite. Base classes and fixtures get no block. `Containers` lists every container the class uses, inherited ones included; `Mocking` lists every mechanism. When reviewing, the consuming workflow owns the finding envelope; invoked standalone, list findings first - `### [Must|Recommend] file:line` (pasted input: `Class.method`), then `Issue:` and `Fix:` as separate paragraphs, `[Must]` first, `[Must]` when a test passes for the wrong reason, is flaky, or cannot catch the regression it names, `[Recommend]` otherwise (deprecated-but-working APIs included) - then the blocks for the target suite.

```
**Engine:** {PostgreSQL <major> | MySQL <major> | <other engine> <major> | unknown - <assumed version> | none}

Production changes: {one line per change | none}

Suite artifacts: {one line per build-file change, test property, shared base class | none}
```

```
Class: {test class name}

Layer: {Controller | Service | Repository | JSON | HTTP Client | Integration}

Slice: {@WebMvcTest | @DataJpaTest | @JsonTest | @RestClientTest | @SpringBootTest | Plain JUnit}

Containers: {Postgres | MySQL | Kafka | RabbitMQ | Redis | none}

Mocking: {@Mock | @MockitoBean | @MockitoSpyBean | WireMock | none}

Cases: {list}
```

A suite restructuring (or a review of one) closes with `Contexts: {n}` - scoped to the classes reviewed when the review is partial: the distinct Spring context cache keys the new layout produces. Count one per distinct merged configuration: each slice annotation counts separately, `@WebMvcTest(A.class)` and `@WebMvcTest(B.class)` are two, and any class adding its own `@MockitoBean`, property override or `@EmbeddedKafka` forks another. Verify with `logging.level.org.springframework.test.context.cache=DEBUG`.

## Avoid

- `@SpringBootTest` when a slice suffices
- H2 for apps whose production engine is not H2
- `Thread.sleep()` in async tests
- `@DirtiesContext` (kills suite speed)
- `lenient()` to silence strict stubbing - delete the unused stub
- `@Transactional` on tests of commit-gated, async or `REQUIRES_NEW` paths
- Testing implementation details over behavior
