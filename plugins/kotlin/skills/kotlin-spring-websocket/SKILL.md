---
name: kotlin-spring-websocket
description: Kotlin / Spring WebSocket / STOMP: CONNECT-frame JWT, message-level AuthorizationManager, broker relay, Mutex over ReentrantLock for suspend handlers.
metadata:
  category: backend
  tags: [kotlin, websocket, stomp, messaging, real-time, spring, coroutines]
user-invocable: false
---

# Kotlin Spring WebSocket

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Real-time bidirectional channels (chat, notifications, live status) in Kotlin / Spring
- Server-pushed updates over STOMP / WebSocket

## Rules

- Authenticate once at the STOMP `CONNECT` frame via `ChannelInterceptor`. Prefer CONNECT-frame JWT over handshake query params (query strings leak to proxy logs and browser history).
- `/topic/**` for broadcasts; `/user/queue/**` via `convertAndSendToUser` for per-user delivery. Never broadcast sensitive payloads on `/topic`.
- `enableSimpleBroker` is in-process. For >1 instance, use `enableStompBrokerRelay` (RabbitMQ / Artemis / ActiveMQ).
- Set heartbeats, message size, send buffer, and send time limits. Without them stale or slow clients consume threads and memory indefinitely.
- Use `ReentrantLock` (blocking handlers) or `kotlinx.coroutines.sync.Mutex` (`suspend` handlers) - `synchronized` pins Virtual Threads on Boot 3.2+.
- Handle errors with `@MessageExceptionHandler`. Unhandled exceptions close the session with no client-visible reason.
- Configuration class needs `kotlin-spring` plugin (`@Configuration` / `@EnableWebSocketMessageBroker` proxying).

## Patterns

### Broker + transport config

```kotlin
@Configuration
@EnableWebSocketMessageBroker
class WebSocketConfig(
    @Value("\${app.cors.origins}") private val corsOrigins: String,
) : WebSocketMessageBrokerConfigurer {

    override fun configureMessageBroker(registry: MessageBrokerRegistry) {
        // Single instance: in-process broker
        registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(longArrayOf(10_000, 10_000))
        // Multi-instance: swap the line above for the relay below
        // registry.enableStompBrokerRelay("/topic", "/queue")
        //     .setRelayHost("rabbitmq").setRelayPort(61613)
        //     .setClientLogin("app").setClientPasscode("\${broker.password}")
        //     // REQUIRED for cross-instance convertAndSendToUser - without these a private
        //     // message from instance A to a user on instance B is silently dropped:
        //     .setUserRegistryBroadcast("/topic/user-registry")
        //     .setUserDestinationBroadcast("/queue/user-unresolved")
        registry.setApplicationDestinationPrefixes("/app")
        registry.setUserDestinationPrefix("/user")
    }

    override fun registerStompEndpoints(registry: StompEndpointRegistry) {
        registry.addEndpoint("/ws")
            .setAllowedOriginPatterns(corsOrigins)    // patterns, not origins, behind proxy
            .withSockJS()
    }

    override fun configureWebSocketTransport(r: WebSocketTransportRegistration) {
        r.setMessageSizeLimit(64 * 1024)
            .setSendBufferSizeLimit(512 * 1024)
            .setSendTimeLimit(20_000)
    }
}
```

`SimpleBrokerMessageHandler` heartbeats need a `TaskScheduler` - configure one if not already present.

### CONNECT-frame JWT auth

```kotlin
override fun configureClientInboundChannel(registration: ChannelRegistration) {
    registration.interceptors(object : ChannelInterceptor {
        override fun preSend(message: Message<*>, channel: MessageChannel): Message<*> {
            val acc = StompHeaderAccessor.wrap(message)
            if (StompCommand.CONNECT == acc.command) {
                val header = acc.getFirstNativeHeader("Authorization")
                    ?: throw MessageDeliveryException("Missing Bearer token")
                require(header.startsWith("Bearer ")) { "Bearer token required" }
                val jwt = jwtDecoder.decode(header.substring(7))
                acc.user = jwtAuthConverter.convert(jwt)     // reuse the HTTP JwtAuthenticationConverter bean
            }
            return message
        }
    })
}
```

Reusing the existing `JwtAuthenticationConverter` keeps role mapping consistent with the REST side. The `Principal` set here flows through `@MessageMapping` methods and powers `convertAndSendToUser`.

**`JwtDecoder.decode(...)` is blocking.** Inside a `suspend` interceptor or downstream consumer, wrap with `withContext(Dispatchers.IO)` only if Virtual Threads are not enabled - under `spring.threads.virtual.enabled=true` the carrier handles blocking without dispatcher switching.

### Message-level authorization

```kotlin
@Configuration
@EnableWebSocketSecurity
class WebSocketSecurityConfig {
    @Bean
    fun messageAuthz(
        messages: MessageMatcherDelegatingAuthorizationManager.Builder,
    ): AuthorizationManager<Message<*>> = messages
        .nullDestMatcher().authenticated()                               // CONNECT/DISCONNECT
        .simpSubscribeDestMatchers("/topic/admin/**").hasRole("ADMIN")
        .simpDestMatchers("/app/admin/**").hasRole("ADMIN")
        .simpSubscribeDestMatchers("/user/queue/**").authenticated()
        .anyMessage().authenticated()
        .build()
}
```

`simpSubscribeDestMatchers` guards SUBSCRIBE; `simpDestMatchers` guards SEND. Both are needed - a SEND-only rule lets attackers subscribe to other users' destinations.

### Controller + per-user send

```kotlin
@Controller
class ChatController(
    private val template: SimpMessagingTemplate,
    private val chatService: ChatService,
) {
    @MessageMapping("/chat.send")
    fun send(@Payload msg: ChatMessageDTO, principal: Principal) {
        val saved = chatService.save(msg, principal.name)
        template.convertAndSend("/topic/chat.${msg.roomId}", saved)
    }

    @MessageMapping("/chat.private")
    fun privateMessage(@Payload m: PrivateMessageDTO, principal: Principal) {
        // Derive the sender from the authenticated Principal, never from the payload (anti-spoofing).
        // Authorize the target: a destination-prefix rule can't stop A from messaging an arbitrary recipientId.
        require(chatService.canMessage(principal.name, m.recipientId)) { "not allowed" }
        val outbound = m.copy(senderId = principal.name)
        template.convertAndSendToUser(m.recipientId, "/queue/messages", outbound)
    }

    @MessageExceptionHandler
    @SendToUser("/queue/errors")
    fun handle(ex: Exception): ErrorDTO = ErrorDTO(ex.message ?: "error")
}
```

### `suspend` handlers + `Mutex`

`@MessageMapping` accepts `suspend` methods on Boot 3.2+ when `kotlinx-coroutines-reactor` is on the classpath. For shared state across handler invocations, use `Mutex`, not `synchronized` / `ReentrantLock` - `Mutex` is coroutine-aware and does not pin Virtual Threads:

```kotlin
@Controller
class RoomController(private val rooms: RoomService) {
    private val mutex = Mutex()
    private val active = mutableMapOf<String, Set<String>>()

    @MessageMapping("/room.join")
    suspend fun join(@Payload req: JoinRequest, principal: Principal) {
        val members = mutex.withLock {                       // snapshot inside the lock; never read `active` outside it
            (active[req.roomId].orEmpty() + principal.name).also { active[req.roomId] = it }
        }
        rooms.publishPresence(req.roomId, members)           // suspend broadcast OUTSIDE the lock
    }
}
```

For blocking handlers on Boot 3.2+ with VTs enabled, use `ReentrantLock.withLock { }` - `synchronized {}` pins the carrier.

### Coroutine broadcaster fan-out

When a single event must fan out to many subscribers, use an injected `CoroutineScope` bean instead of `GlobalScope`:

```kotlin
@Service
class PresenceBroadcaster(
    private val template: SimpMessagingTemplate,
    @Qualifier("applicationScope") private val scope: CoroutineScope,   // see kotlin-coroutines-spring
) {
    fun broadcast(event: PresenceEvent) {
        scope.launch(MDCContext()) {                                    // preserve traceId / userId
            event.targets.forEach { user ->
                template.convertAndSendToUser(user, "/queue/presence", event)
            }
        }
    }
}
```

### Connection lifecycle

```kotlin
@Component
class WebSocketEventListener(private val presence: UserPresenceService) {
    @EventListener
    fun onConnect(e: SessionConnectedEvent) {
        e.user?.name?.let(presence::markOnline)
    }

    @EventListener
    fun onDisconnect(e: SessionDisconnectEvent) {
        e.user?.name?.let(presence::markOffline)
    }
}
```

Keep broadcasting inside the service - listeners stay thin and the presence rule (debounce, last-write-wins) lives in one place.

### Reverse proxy

Behind nginx / ALB: forward `Upgrade` / `Connection` headers, set `proxy_read_timeout` above the heartbeat interval (default 60s drops idle WS). Use `setAllowedOriginPatterns(...)` (not `setAllowedOrigins`) when CORS varies by tenant or `X-Forwarded-Host` is rewritten.

## Testing notes

- `WebSocketStompClient` + `@SpringBootTest(RANDOM_PORT)` for integration tests; assert frame round-trips, not internal state.
- Authentication: stub `JwtDecoder` with `@MockkBean`; supply CONNECT headers via `StompHeaders`.
- For `suspend` handlers, test bodies wrap with `runTest { }` and `coVerify` outbound `SimpMessagingTemplate` calls.

## Output Format

```
Endpoint: {WebSocket path, e.g. /ws}
Protocol: {STOMP | raw WebSocket}
Auth: {CONNECT-frame JWT | handshake JWT | session}
Broker: {simple in-process | STOMP relay (RabbitMQ/Artemis/ActiveMQ)}
Destinations: {/topic/*, /queue/* patterns}
Heartbeat: {client ms, server ms}
Limits: {message size, send buffer, send time}
Suspend Handlers: {yes - Mutex | no - ReentrantLock | no - none}
Multi-instance: {yes via relay | single instance only}
```

## Avoid

- Authenticating per message instead of once at CONNECT
- `synchronized` / `@Synchronized` in `@MessageMapping` / interceptors (Virtual Thread pinning on Boot 3.2+)
- `ReentrantLock` inside `suspend` handlers - use `Mutex`
- Authorizing only SEND while leaving SUBSCRIBE open
- Shipping `enableSimpleBroker` to a multi-instance deployment
- Omitting heartbeat or transport size limits
- Swallowing exceptions instead of `@MessageExceptionHandler` (session dies silently)
- `GlobalScope.launch` for broadcaster fan-out - use a managed scope bean
- JWT in handshake query parameters (leaks to proxy logs)
- Targeting `convertAndSendToUser` at a `recipientId` taken from the payload without an authz check, or trusting a payload `senderId` over `Principal` (impersonation)
- A STOMP relay without `setUserRegistryBroadcast` / `setUserDestinationBroadcast` - cross-instance `convertAndSendToUser` silently fails
