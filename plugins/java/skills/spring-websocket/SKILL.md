---
name: spring-websocket
description: Spring WebSocket and STOMP messaging patterns
metadata:
  category: backend
  tags: [websocket, stomp, messaging, real-time, spring]
user-invocable: false
---

# Spring WebSocket

## When to Use

- Real-time bidirectional communication (chat, notifications, live updates)
- Server-sent events to connected clients
- Implementing STOMP messaging over WebSocket

## Rules

- Use STOMP over WebSocket for structured messaging
- Always configure message broker (simple or external like RabbitMQ)
- Authenticate WebSocket handshake, not individual messages
- Use `/topic` for broadcast, `/queue` for user-specific messages
- Handle connection/disconnection events for cleanup
- Set heartbeat intervals to detect stale connections
- Limit message size and rate to prevent abuse
- Use Virtual Thread-compatible patterns (no synchronized)

## Pattern

### Configuration

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[]{10000, 10000});
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("${app.cors.origins}")
                .withSockJS();
    }
}
```

### Controller

Bad - No authentication, blocking operations:

```java
@MessageMapping("/chat")
public void handleMessage(ChatMessage message) {
    synchronized (messages) { // Blocks Virtual Threads
        messages.add(message);
    }
    template.convertAndSend("/topic/chat", message);
}
```

Good - Authenticated, non-blocking:

```java
@Controller
public class ChatController {

    private final SimpMessagingTemplate messagingTemplate;
    private final ChatService chatService;

    @MessageMapping("/chat.send")
    public void sendMessage(@Payload ChatMessageDTO message,
                            Principal principal) {
        ChatMessageDTO saved = chatService.save(message, principal.getName());
        messagingTemplate.convertAndSend("/topic/chat." + message.roomId(), saved);
    }

    @MessageMapping("/chat.private")
    public void sendPrivateMessage(@Payload PrivateMessageDTO message,
                                   Principal principal) {
        messagingTemplate.convertAndSendToUser(
            message.recipientId(),
            "/queue/messages",
            message
        );
    }
}
```

### Connection Events

```java
@Component
public class WebSocketEventListener {

    private final SimpMessagingTemplate messagingTemplate;
    private final UserPresenceService presenceService;

    @EventListener
    public void handleConnect(SessionConnectedEvent event) {
        String userId = event.getUser().getName();
        presenceService.markOnline(userId);
    }

    @EventListener
    public void handleDisconnect(SessionDisconnectEvent event) {
        String userId = event.getUser().getName();
        presenceService.markOffline(userId);
        messagingTemplate.convertAndSend("/topic/presence",
            new PresenceEvent(userId, "OFFLINE"));
    }
}
```

### Security

```java
@Configuration
public class WebSocketSecurityConfig {

    @Bean
    public AuthorizationManager<Message<?>> messageAuthorizationManager() {
        return MessageMatcherDelegatingAuthorizationManager.builder()
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").authenticated()
            .simpSubscribeDestMatchers("/topic/**", "/queue/**").authenticated()
            .anyMessage().denyAll()
            .build();
    }
}
```

## Avoid

- Synchronized blocks (use ReentrantLock or concurrent collections)
- Missing heartbeat configuration
- Unauthenticated WebSocket endpoints
- Broadcasting sensitive data to all subscribers
- Unbounded message queues (configure limits)
- Missing error handling for message processing
