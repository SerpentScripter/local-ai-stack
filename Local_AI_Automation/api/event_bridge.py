"""
Event Bridge
Unified event system connecting all components of the Local AI Hub

Provides:
- Cross-service event routing
- Event persistence and replay
- Webhook-to-internal event translation
- Event filtering and transformation
- Dead letter queue for failed events
"""
import asyncio
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Awaitable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .message_bus import get_message_bus, Message, MessageType
from .webhooks import get_webhook_manager, WebhookEvent
from .slack_bot import get_slack_bot, slack_notify
from .logging_config import api_logger
from .database import get_db


class EventPriority(Enum):
    """Event priority levels"""
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


class EventCategory(Enum):
    """Categories of events"""
    SYSTEM = "system"           # System status changes
    AGENT = "agent"             # Agent lifecycle events
    TASK = "task"               # Task/backlog events
    SERVICE = "service"         # Service status changes
    WEBHOOK = "webhook"         # External webhook events
    USER = "user"               # User actions
    INTEGRATION = "integration" # External integration events


@dataclass
class BridgeEvent:
    """An event in the bridge"""
    id: str
    category: EventCategory
    event_type: str
    source: str
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: EventPriority = EventPriority.NORMAL
    metadata: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None  # ID of event that caused this one


@dataclass
class EventRule:
    """Rule for event routing/transformation"""
    id: str
    name: str
    source_pattern: str  # Glob pattern for source events
    action: str  # "route", "transform", "notify", "store"
    target: Optional[str] = None  # Target topic/webhook/channel
    transform: Optional[Callable] = None  # Transform function
    filter_func: Optional[Callable] = None  # Filter function
    enabled: bool = True


class EventBridge:
    """
    Central event bridge for the Local AI Hub

    Features:
    - Event routing between components
    - Event persistence for audit/replay
    - Automatic notifications
    - Event transformation
    - Dead letter queue
    """

    def __init__(self):
        self._rules: Dict[str, EventRule] = {}
        self._dead_letter: List[BridgeEvent] = []
        self._max_dead_letter = 1000
        self._subscribers: Dict[str, Set[str]] = defaultdict(set)  # category -> subscriber IDs
        self._running = False
        self._init_database()
        self._register_default_rules()

    def _init_database(self):
        """Initialize event storage tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS event_log (
                        id TEXT PRIMARY KEY,
                        category TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        source TEXT NOT NULL,
                        payload TEXT,
                        timestamp TEXT NOT NULL,
                        priority INTEGER DEFAULT 1,
                        metadata TEXT,
                        correlation_id TEXT,
                        causation_id TEXT,
                        processed INTEGER DEFAULT 1
                    );

                    CREATE INDEX IF NOT EXISTS idx_event_category ON event_log(category);
                    CREATE INDEX IF NOT EXISTS idx_event_type ON event_log(event_type);
                    CREATE INDEX IF NOT EXISTS idx_event_timestamp ON event_log(timestamp);
                    CREATE INDEX IF NOT EXISTS idx_event_correlation ON event_log(correlation_id);

                    CREATE TABLE IF NOT EXISTS event_rules (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        source_pattern TEXT NOT NULL,
                        action TEXT NOT NULL,
                        target TEXT,
                        enabled INTEGER DEFAULT 1,
                        created_at TEXT NOT NULL
                    );
                """)
        except Exception as e:
            api_logger.error(f"Failed to init event bridge tables: {e}")

    def _register_default_rules(self):
        """Register default event routing rules"""
        # Route task events to Slack
        self.add_rule(EventRule(
            id="task_notifications",
            name="Task Notifications",
            source_pattern="task.*",
            action="notify",
            target="slack"
        ))

        # Route agent completion events
        self.add_rule(EventRule(
            id="agent_complete",
            name="Agent Completion",
            source_pattern="agent.completed",
            action="notify",
            target="slack"
        ))

        # Store all events
        self.add_rule(EventRule(
            id="store_all",
            name="Store All Events",
            source_pattern="*",
            action="store"
        ))

    # ==================== Event Publishing ====================

    async def publish(
        self,
        category: EventCategory,
        event_type: str,
        source: str,
        payload: Dict[str, Any],
        priority: EventPriority = EventPriority.NORMAL,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None
    ) -> str:
        """
        Publish an event to the bridge

        Args:
            category: Event category
            event_type: Specific event type
            source: Source component
            payload: Event data
            priority: Event priority
            correlation_id: ID linking related events
            causation_id: ID of causing event

        Returns:
            Event ID
        """
        import uuid
        event_id = f"evt_{uuid.uuid4().hex[:12]}"

        event = BridgeEvent(
            id=event_id,
            category=category,
            event_type=event_type,
            source=source,
            payload=payload,
            priority=priority,
            correlation_id=correlation_id,
            causation_id=causation_id
        )

        # Process through rules
        await self._process_event(event)

        # Forward to message bus
        bus = get_message_bus()
        await bus.publish(
            f"{category.value}.{event_type}",
            payload,
            sender=source,
            priority=priority.value
        )

        return event_id

    async def _process_event(self, event: BridgeEvent):
        """Process an event through all matching rules"""
        event_pattern = f"{event.category.value}.{event.event_type}"

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            if self._matches_pattern(event_pattern, rule.source_pattern):
                try:
                    # Apply filter if present
                    if rule.filter_func and not rule.filter_func(event):
                        continue

                    # Apply transformation if present
                    if rule.transform:
                        event = rule.transform(event)

                    # Execute action
                    await self._execute_action(rule, event)

                except Exception as e:
                    api_logger.error(f"Rule {rule.id} failed: {e}")
                    self._add_to_dead_letter(event, str(e))

    async def _execute_action(self, rule: EventRule, event: BridgeEvent):
        """Execute a rule action"""
        if rule.action == "store":
            self._store_event(event)

        elif rule.action == "notify":
            await self._send_notification(rule.target, event)

        elif rule.action == "route":
            # Route to another topic
            bus = get_message_bus()
            await bus.publish(rule.target, event.payload, sender=event.source)

        elif rule.action == "webhook":
            # Send to external webhook
            await self._send_to_webhook(rule.target, event)

    def _matches_pattern(self, event_pattern: str, rule_pattern: str) -> bool:
        """Check if event pattern matches rule pattern"""
        import fnmatch
        return fnmatch.fnmatch(event_pattern, rule_pattern)

    # ==================== Notifications ====================

    async def _send_notification(self, target: str, event: BridgeEvent):
        """Send notification based on target"""
        if target == "slack":
            await self._notify_slack(event)
        # Add more notification targets as needed

    async def _notify_slack(self, event: BridgeEvent):
        """Send Slack notification for an event"""
        # Build message based on event type
        emoji_map = {
            EventCategory.TASK: "📋",
            EventCategory.AGENT: "🤖",
            EventCategory.SERVICE: "🖥️",
            EventCategory.WEBHOOK: "🔗",
            EventCategory.SYSTEM: "⚙️",
        }

        emoji = emoji_map.get(event.category, "📢")
        text = f"{emoji} *{event.event_type}* from {event.source}"

        # Add payload summary
        if event.payload:
            summary = self._summarize_payload(event.payload)
            if summary:
                text += f"\n{summary}"

        await slack_notify(text)

    def _summarize_payload(self, payload: Dict[str, Any]) -> str:
        """Create a summary of event payload"""
        summary_parts = []

        if "title" in payload:
            summary_parts.append(f"*{payload['title']}*")
        if "message" in payload:
            summary_parts.append(payload["message"][:200])
        if "status" in payload:
            summary_parts.append(f"Status: {payload['status']}")
        if "error" in payload:
            summary_parts.append(f"Error: {payload['error'][:100]}")

        return "\n".join(summary_parts)

    async def _send_to_webhook(self, webhook_id: str, event: BridgeEvent):
        """Send event to external webhook"""
        import httpx

        manager = get_webhook_manager()
        webhook = manager.get_webhook(webhook_id)

        if not webhook:
            api_logger.warning(f"Webhook {webhook_id} not found")
            return

        # Would need to store outbound webhook URLs
        # For now, log
        api_logger.info(f"Would send event {event.id} to webhook {webhook_id}")

    # ==================== Event Storage ====================

    def _store_event(self, event: BridgeEvent):
        """Store event in database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO event_log
                    (id, category, event_type, source, payload, timestamp, priority, metadata, correlation_id, causation_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.id,
                    event.category.value,
                    event.event_type,
                    event.source,
                    json.dumps(event.payload),
                    event.timestamp.isoformat(),
                    event.priority.value,
                    json.dumps(event.metadata),
                    event.correlation_id,
                    event.causation_id
                ))
        except Exception as e:
            api_logger.error(f"Failed to store event: {e}")

    def _add_to_dead_letter(self, event: BridgeEvent, error: str):
        """Add failed event to dead letter queue"""
        event.metadata["error"] = error
        event.metadata["failed_at"] = datetime.utcnow().isoformat()

        self._dead_letter.append(event)

        # Trim if too large
        if len(self._dead_letter) > self._max_dead_letter:
            self._dead_letter = self._dead_letter[-self._max_dead_letter:]

    # ==================== Rule Management ====================

    def add_rule(self, rule: EventRule):
        """Add a routing rule"""
        self._rules[rule.id] = rule

        # Persist to database
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO event_rules
                    (id, name, source_pattern, action, target, enabled, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    rule.id, rule.name, rule.source_pattern,
                    rule.action, rule.target, 1 if rule.enabled else 0,
                    datetime.utcnow().isoformat()
                ))
        except Exception:
            pass

    def remove_rule(self, rule_id: str) -> bool:
        """Remove a routing rule"""
        if rule_id not in self._rules:
            return False

        del self._rules[rule_id]

        try:
            with get_db() as conn:
                conn.execute("DELETE FROM event_rules WHERE id = ?", (rule_id,))
        except Exception:
            pass

        return True

    def list_rules(self) -> List[Dict[str, Any]]:
        """List all routing rules"""
        return [
            {
                "id": r.id,
                "name": r.name,
                "source_pattern": r.source_pattern,
                "action": r.action,
                "target": r.target,
                "enabled": r.enabled
            }
            for r in self._rules.values()
        ]

    # ==================== Queries ====================

    def get_events(
        self,
        category: Optional[EventCategory] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        correlation_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Query stored events"""
        try:
            with get_db() as conn:
                query = "SELECT * FROM event_log WHERE 1=1"
                params = []

                if category:
                    query += " AND category = ?"
                    params.append(category.value)
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type)
                if since:
                    query += " AND timestamp >= ?"
                    params.append(since.isoformat())
                if correlation_id:
                    query += " AND correlation_id = ?"
                    params.append(correlation_id)

                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                return [dict(row) for row in rows]
        except Exception:
            return []

    def get_dead_letter_queue(self) -> List[Dict[str, Any]]:
        """Get events from dead letter queue"""
        return [
            {
                "id": e.id,
                "category": e.category.value,
                "event_type": e.event_type,
                "source": e.source,
                "payload": e.payload,
                "error": e.metadata.get("error"),
                "failed_at": e.metadata.get("failed_at")
            }
            for e in self._dead_letter
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get event bridge statistics"""
        stats = {
            "rules_count": len(self._rules),
            "dead_letter_count": len(self._dead_letter),
            "events_today": 0,
            "events_by_category": {}
        }

        try:
            with get_db() as conn:
                today = datetime.utcnow().date().isoformat()

                stats["events_today"] = conn.execute(
                    "SELECT COUNT(*) FROM event_log WHERE timestamp >= ?",
                    (today,)
                ).fetchone()[0]

                rows = conn.execute("""
                    SELECT category, COUNT(*) as count
                    FROM event_log
                    WHERE timestamp >= ?
                    GROUP BY category
                """, (today,)).fetchall()
                stats["events_by_category"] = {row["category"]: row["count"] for row in rows}
        except Exception:
            pass

        return stats


# Global event bridge instance
_event_bridge: Optional[EventBridge] = None


def get_event_bridge() -> EventBridge:
    """Get the global EventBridge instance"""
    global _event_bridge
    if _event_bridge is None:
        _event_bridge = EventBridge()
    return _event_bridge


# Convenience functions
async def emit_event(
    category: EventCategory,
    event_type: str,
    payload: Dict[str, Any],
    source: str = "api"
) -> str:
    """Emit an event to the bridge"""
    bridge = get_event_bridge()
    return await bridge.publish(category, event_type, source, payload)


# Pre-built event emitters for common events
async def emit_task_created(task: Dict[str, Any]):
    return await emit_event(EventCategory.TASK, "created", task, "backlog")


async def emit_task_updated(task: Dict[str, Any]):
    return await emit_event(EventCategory.TASK, "updated", task, "backlog")


async def emit_agent_started(session_id: str, goal: str):
    return await emit_event(EventCategory.AGENT, "started", {"session_id": session_id, "goal": goal}, "agent")


async def emit_agent_completed(session_id: str, success: bool):
    return await emit_event(EventCategory.AGENT, "completed", {"session_id": session_id, "success": success}, "agent")


async def emit_service_status(service_id: str, status: str):
    return await emit_event(EventCategory.SERVICE, "status_changed", {"service_id": service_id, "status": status}, "services")
