"""
Agent Message Bus
Pub/Sub communication system for agent coordination

Provides:
- Topic-based publish/subscribe
- Request/response patterns
- Message queuing
- Event broadcasting
"""
import asyncio
import uuid
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Awaitable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from collections import defaultdict

# Try to import Redis for distributed messaging
try:
    import redis.asyncio as aioredis
    ASYNC_REDIS_AVAILABLE = True
except ImportError:
    try:
        import aioredis
        ASYNC_REDIS_AVAILABLE = True
    except ImportError:
        ASYNC_REDIS_AVAILABLE = False

from .logging_config import api_logger


class MessageType(Enum):
    """Types of messages"""
    EVENT = "event"           # Fire-and-forget notification
    REQUEST = "request"       # Request expecting response
    RESPONSE = "response"     # Response to a request
    BROADCAST = "broadcast"   # System-wide announcement
    COMMAND = "command"       # Direct command to agent


class MessagePriority(Enum):
    """Message priority levels"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass
class Message:
    """A message on the bus"""
    id: str
    type: MessageType
    topic: str
    payload: Any
    sender: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: MessagePriority = MessagePriority.NORMAL
    correlation_id: Optional[str] = None  # For request/response pairing
    reply_to: Optional[str] = None  # Topic to send response
    ttl: int = 300  # Time-to-live in seconds
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "topic": self.topic,
            "payload": self.payload,
            "sender": self.sender,
            "timestamp": self.timestamp.isoformat(),
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "reply_to": self.reply_to,
            "ttl": self.ttl,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        return cls(
            id=data["id"],
            type=MessageType(data["type"]),
            topic=data["topic"],
            payload=data["payload"],
            sender=data.get("sender"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            priority=MessagePriority(data.get("priority", 1)),
            correlation_id=data.get("correlation_id"),
            reply_to=data.get("reply_to"),
            ttl=data.get("ttl", 300),
            metadata=data.get("metadata", {})
        )


# Type alias for message handlers
MessageHandler = Callable[[Message], Awaitable[Optional[Any]]]


@dataclass
class Subscription:
    """A subscription to a topic"""
    id: str
    topic: str
    handler: MessageHandler
    subscriber: Optional[str] = None
    filter_func: Optional[Callable[[Message], bool]] = None
    created_at: datetime = field(default_factory=datetime.utcnow)


class MessageBus:
    """
    Central message bus for agent communication

    Features:
    - Topic-based pub/sub
    - Wildcard subscriptions (e.g., "agents.*")
    - Request/response with correlation
    - Message persistence (optional)
    - Redis backend for distributed messaging
    """

    def __init__(self, use_redis: bool = True):
        self._subscriptions: Dict[str, List[Subscription]] = defaultdict(list)
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._message_history: List[Message] = []
        self._max_history = 1000
        self._redis: Optional[Any] = None
        self._pubsub: Optional[Any] = None
        self._listener_task: Optional[asyncio.Task] = None
        self._use_redis = use_redis and ASYNC_REDIS_AVAILABLE
        self._running = False

    async def start(self, redis_url: str = "redis://localhost:6379/2"):
        """Start the message bus"""
        if self._running:
            return

        self._running = True

        if self._use_redis:
            try:
                self._redis = await aioredis.from_url(redis_url)
                self._pubsub = self._redis.pubsub()
                self._listener_task = asyncio.create_task(self._redis_listener())
                api_logger.info("Message bus started with Redis backend")
            except Exception as e:
                api_logger.warning(f"Redis unavailable: {e}, using local bus only")
                self._use_redis = False

        api_logger.info("Message bus started")

    async def stop(self):
        """Stop the message bus"""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        if self._pubsub:
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        api_logger.info("Message bus stopped")

    # ==================== Publishing ====================

    async def publish(
        self,
        topic: str,
        payload: Any,
        sender: Optional[str] = None,
        msg_type: MessageType = MessageType.EVENT,
        priority: MessagePriority = MessagePriority.NORMAL,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Publish a message to a topic

        Args:
            topic: Topic to publish to
            payload: Message payload
            sender: Sender identifier
            msg_type: Type of message
            priority: Message priority
            metadata: Additional metadata

        Returns:
            Message ID
        """
        message = Message(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            type=msg_type,
            topic=topic,
            payload=payload,
            sender=sender,
            priority=priority,
            metadata=metadata or {}
        )

        await self._deliver(message)
        return message.id

    async def broadcast(
        self,
        payload: Any,
        sender: Optional[str] = None
    ) -> str:
        """Broadcast a message to all subscribers"""
        return await self.publish(
            "__broadcast__",
            payload,
            sender=sender,
            msg_type=MessageType.BROADCAST,
            priority=MessagePriority.HIGH
        )

    async def request(
        self,
        topic: str,
        payload: Any,
        sender: Optional[str] = None,
        timeout: float = 30.0
    ) -> Optional[Any]:
        """
        Send a request and wait for response

        Args:
            topic: Topic to send request to
            payload: Request payload
            sender: Sender identifier
            timeout: Response timeout in seconds

        Returns:
            Response payload or None if timeout
        """
        correlation_id = f"req-{uuid.uuid4().hex[:12]}"
        reply_topic = f"__reply__.{correlation_id}"

        # Create future for response
        response_future = asyncio.get_event_loop().create_future()
        self._pending_responses[correlation_id] = response_future

        # Subscribe to reply topic
        async def response_handler(msg: Message):
            if not response_future.done():
                response_future.set_result(msg.payload)

        sub_id = await self.subscribe(reply_topic, response_handler)

        try:
            # Send request
            message = Message(
                id=f"msg-{uuid.uuid4().hex[:12]}",
                type=MessageType.REQUEST,
                topic=topic,
                payload=payload,
                sender=sender,
                correlation_id=correlation_id,
                reply_to=reply_topic
            )
            await self._deliver(message)

            # Wait for response
            return await asyncio.wait_for(response_future, timeout=timeout)

        except asyncio.TimeoutError:
            api_logger.warning(f"Request timeout for {topic}")
            return None

        finally:
            # Cleanup
            await self.unsubscribe(sub_id)
            self._pending_responses.pop(correlation_id, None)

    async def respond(
        self,
        original_message: Message,
        payload: Any
    ):
        """
        Respond to a request message

        Args:
            original_message: The request message being responded to
            payload: Response payload
        """
        if not original_message.reply_to:
            return

        response = Message(
            id=f"msg-{uuid.uuid4().hex[:12]}",
            type=MessageType.RESPONSE,
            topic=original_message.reply_to,
            payload=payload,
            correlation_id=original_message.correlation_id
        )

        await self._deliver(response)

    # ==================== Subscribing ====================

    async def subscribe(
        self,
        topic: str,
        handler: MessageHandler,
        subscriber: Optional[str] = None,
        filter_func: Optional[Callable[[Message], bool]] = None
    ) -> str:
        """
        Subscribe to a topic

        Args:
            topic: Topic to subscribe to (supports wildcards: "agents.*")
            handler: Async function to handle messages
            subscriber: Subscriber identifier
            filter_func: Optional filter function

        Returns:
            Subscription ID
        """
        sub = Subscription(
            id=f"sub-{uuid.uuid4().hex[:8]}",
            topic=topic,
            handler=handler,
            subscriber=subscriber,
            filter_func=filter_func
        )

        self._subscriptions[topic].append(sub)

        # Subscribe in Redis if available
        if self._use_redis and self._pubsub:
            if "*" in topic:
                await self._pubsub.psubscribe(topic)
            else:
                await self._pubsub.subscribe(topic)

        api_logger.debug(f"Subscription {sub.id} created for topic '{topic}'")
        return sub.id

    async def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription"""
        for topic, subs in self._subscriptions.items():
            for sub in subs:
                if sub.id == subscription_id:
                    subs.remove(sub)
                    api_logger.debug(f"Subscription {subscription_id} removed")
                    return True
        return False

    async def unsubscribe_all(self, subscriber: str):
        """Remove all subscriptions for a subscriber"""
        for topic in list(self._subscriptions.keys()):
            self._subscriptions[topic] = [
                s for s in self._subscriptions[topic]
                if s.subscriber != subscriber
            ]

    # ==================== Message Delivery ====================

    async def _deliver(self, message: Message):
        """Deliver a message to all matching subscribers"""
        # Store in history
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history = self._message_history[-self._max_history:]

        # Find matching subscriptions
        matching_subs = self._find_matching_subscriptions(message.topic)

        # Also check for broadcast
        if message.type == MessageType.BROADCAST:
            for topic_subs in self._subscriptions.values():
                matching_subs.extend(topic_subs)

        # Deliver to each subscriber
        for sub in matching_subs:
            try:
                # Apply filter if present
                if sub.filter_func and not sub.filter_func(message):
                    continue

                # Call handler
                result = await sub.handler(message)

                # Auto-respond if handler returns value and message expects response
                if result is not None and message.reply_to:
                    await self.respond(message, result)

            except Exception as e:
                api_logger.error(f"Error in message handler for {sub.topic}: {e}")

        # Publish to Redis for distributed delivery
        if self._use_redis and self._redis:
            try:
                await self._redis.publish(
                    message.topic,
                    json.dumps(message.to_dict())
                )
            except Exception as e:
                api_logger.error(f"Redis publish failed: {e}")

    def _find_matching_subscriptions(self, topic: str) -> List[Subscription]:
        """Find subscriptions matching a topic (including wildcards)"""
        matching = []

        # Exact matches
        matching.extend(self._subscriptions.get(topic, []))

        # Wildcard matches
        for pattern, subs in self._subscriptions.items():
            if "*" in pattern:
                # Convert wildcard to regex
                import fnmatch
                if fnmatch.fnmatch(topic, pattern):
                    matching.extend(subs)

        return matching

    async def _redis_listener(self):
        """Listen for Redis pub/sub messages"""
        try:
            while self._running:
                try:
                    message = await self._pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )
                    if message and message["type"] == "message":
                        data = json.loads(message["data"])
                        msg = Message.from_dict(data)
                        # Deliver locally (don't re-publish to Redis)
                        await self._deliver_local(msg)
                except asyncio.TimeoutError:
                    continue
        except asyncio.CancelledError:
            pass
        except Exception as e:
            api_logger.error(f"Redis listener error: {e}")

    async def _deliver_local(self, message: Message):
        """Deliver message locally without Redis publish"""
        matching_subs = self._find_matching_subscriptions(message.topic)

        for sub in matching_subs:
            try:
                if sub.filter_func and not sub.filter_func(message):
                    continue
                await sub.handler(message)
            except Exception as e:
                api_logger.error(f"Error in message handler: {e}")

    # ==================== Queries ====================

    def get_message_history(
        self,
        topic: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Message]:
        """Get recent messages"""
        messages = self._message_history

        if topic:
            messages = [m for m in messages if m.topic == topic]

        if since:
            messages = [m for m in messages if m.timestamp > since]

        return messages[-limit:]

    def get_subscriptions(self, subscriber: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get subscription information"""
        subs = []
        for topic, topic_subs in self._subscriptions.items():
            for sub in topic_subs:
                if subscriber is None or sub.subscriber == subscriber:
                    subs.append({
                        "id": sub.id,
                        "topic": sub.topic,
                        "subscriber": sub.subscriber,
                        "created_at": sub.created_at.isoformat()
                    })
        return subs

    def get_stats(self) -> Dict[str, Any]:
        """Get message bus statistics"""
        return {
            "running": self._running,
            "redis_connected": self._use_redis and self._redis is not None,
            "subscriptions": sum(len(s) for s in self._subscriptions.values()),
            "topics": len(self._subscriptions),
            "message_history_size": len(self._message_history),
            "pending_responses": len(self._pending_responses)
        }


# Global message bus instance
_message_bus: Optional[MessageBus] = None


def get_message_bus() -> MessageBus:
    """Get the global MessageBus instance"""
    global _message_bus
    if _message_bus is None:
        _message_bus = MessageBus()
    return _message_bus


# Convenience decorators and functions
def on_message(topic: str, bus: Optional[MessageBus] = None):
    """
    Decorator to register a message handler

    Usage:
        @on_message("agents.research.complete")
        async def handle_research_complete(message: Message):
            print(f"Research completed: {message.payload}")
    """
    def decorator(handler: MessageHandler):
        actual_bus = bus or get_message_bus()

        async def register():
            await actual_bus.subscribe(topic, handler)

        # Schedule registration
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(register())
            else:
                loop.run_until_complete(register())
        except RuntimeError:
            # No event loop, defer registration
            pass

        return handler
    return decorator


async def emit(topic: str, payload: Any, **kwargs) -> str:
    """Convenience function to emit a message"""
    bus = get_message_bus()
    return await bus.publish(topic, payload, **kwargs)


async def ask(topic: str, payload: Any, timeout: float = 30.0, **kwargs) -> Optional[Any]:
    """Convenience function for request/response"""
    bus = get_message_bus()
    return await bus.request(topic, payload, timeout=timeout, **kwargs)
