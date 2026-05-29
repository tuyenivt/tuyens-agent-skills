---
name: kotlin-spring-security-patterns
description: Kotlin / Spring Security DSL patterns: SecurityFilterChain, OAuth2/JWT, method security, CORS, CSRF, headers, coroutine security context propagation.
metadata:
  category: backend
  tags: [kotlin, security, spring-security, oauth2, jwt, cors, csrf, authorization, kotlin-dsl]
user-invocable: false
---

# Kotlin Spring Security Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Configuring authentication / authorization for Kotlin / Spring Boot 3.5+ APIs
- Setting up OAuth2 / JWT resource server with the Kotlin DSL
- Applying method security, CORS, CSRF, security headers
- Propagating `SecurityContext` across `suspend` functions

## Rules

- `SecurityFilterChain` as `@Bean`. `WebSecurityConfigurerAdapter` is removed in Spring Security 6.
- Kotlin DSL `http { ... }` over the chained Java builder. Requires `import org.springframework.security.config.annotation.web.invoke`.
- `@EnableMethodSecurity` (not deprecated `@EnableGlobalMethodSecurity`).
- Stateless APIs: disable CSRF, set `SessionCreationPolicy.STATELESS`.
- Externalize issuers / allowed origins / secrets via `@ConfigurationProperties`. Never wildcards (`"*"`) in production CORS.
- Escape `$` in SpEL (`@Value("\${...}")`, `@PreAuthorize`) - Kotlin string templates collide with `${...}`.
- `SecurityContextHolder` does not propagate across `suspend` boundaries. Use `ReactiveSecurityContextHolder`, `@AuthenticationPrincipal`, or pass the principal explicitly.

## Patterns

### `SecurityFilterChain` (Kotlin DSL)

Multiple chains for different path groups, ordered by `@Order`:

```kotlin
@Configuration
@EnableWebSecurity
@EnableMethodSecurity
class SecurityConfig {

    @Bean @Order(1)
    fun apiChain(http: HttpSecurity): SecurityFilterChain {
        http {
            securityMatcher("/api/**")
            authorizeHttpRequests {
                authorize("/api/public/**", permitAll)
                authorize("/api/admin/**", hasRole("ADMIN"))
                authorize(anyRequest, authenticated)
            }
            oauth2ResourceServer { jwt { } }
            sessionManagement { sessionCreationPolicy = SessionCreationPolicy.STATELESS }
            csrf { disable() }
            cors { }
        }
        return http.build()
    }

    @Bean @Order(2)
    fun actuatorChain(http: HttpSecurity): SecurityFilterChain {
        http {
            securityMatcher("/actuator/**")
            authorizeHttpRequests {
                authorize("/actuator/health", permitAll)
                authorize(anyRequest, hasRole("OPS"))
            }
            httpBasic { }
        }
        return http.build()
    }
}
```

### JWT / OAuth2 resource server

```kotlin
@Bean
fun jwtDecoder(@Value("\${spring.security.oauth2.resourceserver.jwt.issuer-uri}") issuer: String): JwtDecoder {
    val decoder = JwtDecoders.fromIssuerLocation(issuer) as NimbusJwtDecoder
    val audience = JwtClaimValidator<List<String>>("aud") { it != null && "my-api" in it }
    decoder.setJwtValidator(DelegatingOAuth2TokenValidator(JwtValidators.createDefaultWithIssuer(issuer), audience))
    return decoder
}

@Bean
fun jwtAuthConverter(): JwtAuthenticationConverter {
    val authorities = JwtGrantedAuthoritiesConverter().apply {
        setAuthoritiesClaimName("roles")
        setAuthorityPrefix("ROLE_")
    }
    return JwtAuthenticationConverter().apply { setJwtGrantedAuthoritiesConverter(authorities) }
}
```

Multi-tenant: keep a `Map<issuer, JwtDecoder>` and dispatch by the `iss` claim from `JWTParser`.

### Method security

```kotlin
@Service
class OrderService(private val repo: OrderRepository) {
    @PreAuthorize("hasRole('ADMIN') or #userId == authentication.name")
    fun findByUser(userId: String): List<OrderDto> = ...

    @PostAuthorize("returnObject.ownerId == authentication.name or hasRole('ADMIN')")
    fun findById(id: Long): OrderDto = ...
}
```

Custom permission for domain-object authorization:

```kotlin
@Component
class ProjectPermissionEvaluator : PermissionEvaluator {
    override fun hasPermission(auth: Authentication, target: Any?, permission: Any?): Boolean = when (target) {
        is Project -> target.ownerId == auth.name || auth.authorities.any { it.authority == "ROLE_ADMIN" }
        else -> false
    }
    override fun hasPermission(a: Authentication, id: Serializable?, t: String?, p: Any?) = false
}
```

### CORS

```kotlin
@ConfigurationProperties(prefix = "app.cors")
data class CorsProperties(val allowedOrigins: List<String> = emptyList())

@Bean
fun corsSource(props: CorsProperties): CorsConfigurationSource {
    val config = CorsConfiguration().apply {
        allowedOrigins = props.allowedOrigins
        allowedMethods = listOf("GET", "POST", "PUT", "DELETE", "OPTIONS")
        allowedHeaders = listOf("Authorization", "Content-Type", "X-XSRF-TOKEN")
        exposedHeaders = listOf("X-Total-Count")
        allowCredentials = true
        maxAge = 3600
    }
    return UrlBasedCorsConfigurationSource().apply { registerCorsConfiguration("/api/**", config) }
}
```

Wire via `cors { }` inside the DSL.

### CSRF

```kotlin
// Stateless JWT API
csrf { disable() }
sessionManagement { sessionCreationPolicy = SessionCreationPolicy.STATELESS }

// Stateful SPA - XSRF-TOKEN cookie + X-XSRF-TOKEN header
// SpaCsrfTokenRequestHandler: project-defined extending CsrfTokenRequestAttributeHandler that resolves from the header
csrf {
    csrfTokenRepository = CookieCsrfTokenRepository.withHttpOnlyFalse()
    csrfTokenRequestHandler = SpaCsrfTokenRequestHandler()
}
```

### Security headers

```kotlin
headers {
    contentSecurityPolicy { policyDirectives = "default-src 'self'; script-src 'self'" }
    httpStrictTransportSecurity { includeSubDomains = true; maxAgeInSeconds = 31_536_000 }
    contentTypeOptions { }
    frameOptions { deny = true }
}
```

### Webhook endpoints

External webhooks (Stripe, GitHub) authenticate via signature, not JWT. Exclude from API chain:

```kotlin
@Bean @Order(0)
fun webhookChain(http: HttpSecurity): SecurityFilterChain {
    http {
        securityMatcher("/webhooks/**")
        authorizeHttpRequests { authorize(anyRequest, permitAll) }
        csrf { disable() }
        sessionManagement { sessionCreationPolicy = SessionCreationPolicy.STATELESS }
    }
    return http.build()
}
```

HMAC validation via `MessageDigest.isEqual` (timing-safe) in the controller.

### `@AuthenticationPrincipal` for suspend controllers

```kotlin
@GetMapping("/orders")
suspend fun list(@AuthenticationPrincipal jwt: Jwt): List<OrderResponse> =
    service.listForUser(jwt.subject).map { it.toResponse() }
```

Cleanest option for `suspend` - principal is a method argument, no ThreadLocal involved.

### `AuthorizationManager` for request-context rules

When the decision depends on request attributes (tenant header, body, IP), expose an `AuthorizationManager<RequestAuthorizationContext>` bean and wire via `authorize("/api/tenants/**", access(ownsTenant()))`.

### Coroutine `SecurityContext`

```kotlin
// Bad - empty after dispatcher switch
suspend fun currentUser(): String? = SecurityContextHolder.getContext().authentication?.name

// Good - reactive holder
suspend fun currentUser(): String? =
    ReactiveSecurityContextHolder.getContext().awaitFirstOrNull()?.authentication?.name

// Best - pass principal explicitly
suspend fun listUserOrders(principal: String): List<Order> = orderRepo.findByUserId(principal)
```

For `@Async` (non-coroutine), use `MODE_INHERITABLETHREADLOCAL` or `DelegatingSecurityContextExecutor`.

Testing patterns: `@WithMockUser`, `with(jwt().authorities(...).jwt { it.claim("sub", "u") })` - see `kotlin-spring-test-integration`.

## Output Format

```
Endpoint: {path pattern}
Auth: {permitAll | authenticated | hasRole(X) | @PreAuthorize(expr)}
CSRF: {enabled | disabled - reason}
Session: {STATELESS | IF_REQUIRED}
CORS Origins: {list | N/A}
JWT Issuer: {URI | N/A}
DSL: {Kotlin DSL | Java builder}
```

## Avoid

- `WebSecurityConfigurerAdapter` - removed in Spring Security 6
- `@EnableGlobalMethodSecurity` - replaced by `@EnableMethodSecurity`
- `@Secured` - use `@PreAuthorize` with SpEL
- Disabling CSRF on session-based applications
- JWT in `localStorage` - HttpOnly cookie or memory only
- Wildcard CORS origins (`"*"`) in production
- Hardcoded secrets or issuer URIs
- `SecurityContextHolder.getContext()` inside `suspend`
- Forgetting to escape `$` in SpEL strings
