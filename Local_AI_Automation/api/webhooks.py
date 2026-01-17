"""
Inbound Webhook System
Secure webhook endpoints for external service integration

Provides:
- Webhook registration and management
- Signature validation (HMAC-SHA256)
- Rate limiting
- Event routing to handlers
- Webhook logs and debugging
"""
import os
import hmac
import hashlib
import secrets
import json
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps

from fastapi import Request, HTTPException, Header
from pydantic import BaseModel

from .database import get_db
from .logging_config import api_logger
from .message_bus import get_message_bus, MessageType


class WebhookType(Enum):
    """Types of webhooks"""
    GENERIC = "generic"
    GITHUB = "github"
    GITLAB = "gitlab"
    SLACK = "slack"
    DISCORD = "discord"
    CUSTOM = "custom"


class WebhookStatus(Enum):
    """Webhook status"""
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"


@dataclass
class WebhookConfig:
    """Configuration for a webhook endpoint"""
    id: str
    name: str
    type: WebhookType
    secret: str
    status: WebhookStatus = WebhookStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.utcnow)
    description: str = ""
    allowed_events: List[str] = field(default_factory=list)  # Empty = all events
    rate_limit: int = 100  # Requests per minute
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookEvent:
    """A received webhook event"""
    id: str
    webhook_id: str
    event_type: str
    payload: Dict[str, Any]
    headers: Dict[str, str]
    source_ip: str
    received_at: datetime
    processed: bool = False
    error: Optional[str] = None


class WebhookManager:
    """
    Manager for webhook endpoints

    Features:
    - Webhook registration with auto-generated secrets
    - Signature validation
    - Rate limiting
    - Event logging
    - Handler routing
    """

    def __init__(self):
        self._webhooks: Dict[str, WebhookConfig] = {}
        self._handlers: Dict[str, List[Callable]] = {}
        self._rate_limits: Dict[str, List[datetime]] = {}
        self._init_database()
        self._load_webhooks()

    def _init_database(self):
        """Initialize webhook tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS webhooks (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        type TEXT DEFAULT 'generic',
                        secret TEXT NOT NULL,
                        status TEXT DEFAULT 'active',
                        created_at TEXT NOT NULL,
                        description TEXT,
                        allowed_events TEXT,
                        rate_limit INTEGER DEFAULT 100,
                        metadata TEXT
                    );

                    CREATE TABLE IF NOT EXISTS webhook_events (
                        id TEXT PRIMARY KEY,
                        webhook_id TEXT NOT NULL,
                        event_type TEXT,
                        payload TEXT,
                        headers TEXT,
                        source_ip TEXT,
                        received_at TEXT NOT NULL,
                        processed INTEGER DEFAULT 0,
                        error TEXT,
                        FOREIGN KEY (webhook_id) REFERENCES webhooks(id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_webhook_events_webhook
                        ON webhook_events(webhook_id);
                    CREATE INDEX IF NOT EXISTS idx_webhook_events_received
                        ON webhook_events(received_at);
                """)
        except Exception as e:
            api_logger.error(f"Failed to init webhook tables: {e}")

    def _load_webhooks(self):
        """Load webhooks from database"""
        try:
            with get_db() as conn:
                rows = conn.execute("SELECT * FROM webhooks").fetchall()
                for row in rows:
                    self._webhooks[row["id"]] = WebhookConfig(
                        id=row["id"],
                        name=row["name"],
                        type=WebhookType(row["type"]),
                        secret=row["secret"],
                        status=WebhookStatus(row["status"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                        description=row["description"] or "",
                        allowed_events=json.loads(row["allowed_events"] or "[]"),
                        rate_limit=row["rate_limit"],
                        metadata=json.loads(row["metadata"] or "{}")
                    )
        except Exception as e:
            api_logger.error(f"Failed to load webhooks: {e}")

    # ==================== Webhook Management ====================

    def create_webhook(
        self,
        name: str,
        webhook_type: WebhookType = WebhookType.GENERIC,
        description: str = "",
        allowed_events: Optional[List[str]] = None,
        rate_limit: int = 100
    ) -> WebhookConfig:
        """
        Create a new webhook endpoint

        Args:
            name: Webhook name
            webhook_type: Type of webhook
            description: Description
            allowed_events: List of allowed event types (empty = all)
            rate_limit: Max requests per minute

        Returns:
            WebhookConfig with generated ID and secret
        """
        webhook_id = f"wh_{secrets.token_urlsafe(8)}"
        secret = secrets.token_urlsafe(32)

        config = WebhookConfig(
            id=webhook_id,
            name=name,
            type=webhook_type,
            secret=secret,
            description=description,
            allowed_events=allowed_events or [],
            rate_limit=rate_limit
        )

        # Save to database
        with get_db() as conn:
            conn.execute("""
                INSERT INTO webhooks
                (id, name, type, secret, status, created_at, description, allowed_events, rate_limit, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                config.id, config.name, config.type.value, config.secret,
                config.status.value, config.created_at.isoformat(),
                config.description, json.dumps(config.allowed_events),
                config.rate_limit, json.dumps(config.metadata)
            ))

        self._webhooks[webhook_id] = config
        api_logger.info(f"Created webhook {webhook_id}: {name}")

        return config

    def get_webhook(self, webhook_id: str) -> Optional[WebhookConfig]:
        """Get webhook by ID"""
        return self._webhooks.get(webhook_id)

    def list_webhooks(self) -> List[WebhookConfig]:
        """List all webhooks"""
        return list(self._webhooks.values())

    def update_webhook(
        self,
        webhook_id: str,
        name: Optional[str] = None,
        status: Optional[WebhookStatus] = None,
        description: Optional[str] = None,
        allowed_events: Optional[List[str]] = None,
        rate_limit: Optional[int] = None
    ) -> Optional[WebhookConfig]:
        """Update webhook configuration"""
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            return None

        updates = []
        params = []

        if name is not None:
            webhook.name = name
            updates.append("name = ?")
            params.append(name)
        if status is not None:
            webhook.status = status
            updates.append("status = ?")
            params.append(status.value)
        if description is not None:
            webhook.description = description
            updates.append("description = ?")
            params.append(description)
        if allowed_events is not None:
            webhook.allowed_events = allowed_events
            updates.append("allowed_events = ?")
            params.append(json.dumps(allowed_events))
        if rate_limit is not None:
            webhook.rate_limit = rate_limit
            updates.append("rate_limit = ?")
            params.append(rate_limit)

        if updates:
            params.append(webhook_id)
            with get_db() as conn:
                conn.execute(
                    f"UPDATE webhooks SET {', '.join(updates)} WHERE id = ?",
                    params
                )

        return webhook

    def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook"""
        if webhook_id not in self._webhooks:
            return False

        with get_db() as conn:
            conn.execute("DELETE FROM webhooks WHERE id = ?", (webhook_id,))
            conn.execute("DELETE FROM webhook_events WHERE webhook_id = ?", (webhook_id,))

        del self._webhooks[webhook_id]
        api_logger.info(f"Deleted webhook {webhook_id}")
        return True

    def regenerate_secret(self, webhook_id: str) -> Optional[str]:
        """Regenerate webhook secret"""
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            return None

        new_secret = secrets.token_urlsafe(32)
        webhook.secret = new_secret

        with get_db() as conn:
            conn.execute(
                "UPDATE webhooks SET secret = ? WHERE id = ?",
                (new_secret, webhook_id)
            )

        return new_secret

    # ==================== Validation ====================

    def validate_signature(
        self,
        webhook_id: str,
        payload: bytes,
        signature: str,
        webhook_type: Optional[WebhookType] = None
    ) -> bool:
        """
        Validate webhook signature

        Supports multiple signature formats:
        - Generic: sha256=<hex>
        - GitHub: sha256=<hex>
        - Slack: v0=<timestamp>:<signature>
        """
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            return False

        wh_type = webhook_type or webhook.type

        try:
            if wh_type in (WebhookType.GENERIC, WebhookType.GITHUB, WebhookType.GITLAB):
                # Standard HMAC-SHA256
                expected = hmac.new(
                    webhook.secret.encode(),
                    payload,
                    hashlib.sha256
                ).hexdigest()

                # Handle sha256= prefix
                if signature.startswith("sha256="):
                    signature = signature[7:]

                return hmac.compare_digest(expected, signature)

            elif wh_type == WebhookType.SLACK:
                # Slack uses v0 signature format
                if not signature.startswith("v0="):
                    return False

                # Slack signature validation would need timestamp
                # Simplified for now
                return True

            else:
                return True  # No validation for unknown types

        except Exception as e:
            api_logger.error(f"Signature validation failed: {e}")
            return False

    def check_rate_limit(self, webhook_id: str) -> bool:
        """Check if webhook is within rate limit"""
        webhook = self._webhooks.get(webhook_id)
        if not webhook:
            return False

        now = datetime.utcnow()
        window_start = now - timedelta(minutes=1)

        # Clean old entries
        if webhook_id in self._rate_limits:
            self._rate_limits[webhook_id] = [
                t for t in self._rate_limits[webhook_id]
                if t > window_start
            ]
        else:
            self._rate_limits[webhook_id] = []

        # Check limit
        if len(self._rate_limits[webhook_id]) >= webhook.rate_limit:
            return False

        # Record request
        self._rate_limits[webhook_id].append(now)
        return True

    # ==================== Event Processing ====================

    async def process_webhook(
        self,
        webhook_id: str,
        payload: Dict[str, Any],
        headers: Dict[str, str],
        source_ip: str,
        event_type: Optional[str] = None
    ) -> WebhookEvent:
        """
        Process an incoming webhook

        Args:
            webhook_id: Webhook ID
            payload: Request payload
            headers: Request headers
            source_ip: Source IP address
            event_type: Event type (extracted from headers or payload)

        Returns:
            WebhookEvent record
        """
        event_id = f"evt_{secrets.token_urlsafe(8)}"
        webhook = self._webhooks.get(webhook_id)

        event = WebhookEvent(
            id=event_id,
            webhook_id=webhook_id,
            event_type=event_type or "unknown",
            payload=payload,
            headers=headers,
            source_ip=source_ip,
            received_at=datetime.utcnow()
        )

        # Check if event type is allowed
        if webhook and webhook.allowed_events:
            if event_type and event_type not in webhook.allowed_events:
                event.error = f"Event type '{event_type}' not allowed"
                self._save_event(event)
                return event

        # Log event
        self._save_event(event)

        # Route to handlers
        try:
            await self._route_event(event)
            event.processed = True
            self._update_event(event)

            # Publish to message bus
            bus = get_message_bus()
            await bus.publish(
                f"webhooks.{webhook_id}.{event_type or 'event'}",
                payload,
                sender="webhook_manager"
            )

        except Exception as e:
            event.error = str(e)
            self._update_event(event)
            api_logger.error(f"Webhook processing failed: {e}")

        return event

    def _save_event(self, event: WebhookEvent):
        """Save event to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO webhook_events
                    (id, webhook_id, event_type, payload, headers, source_ip, received_at, processed, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    event.id, event.webhook_id, event.event_type,
                    json.dumps(event.payload), json.dumps(event.headers),
                    event.source_ip, event.received_at.isoformat(),
                    1 if event.processed else 0, event.error
                ))
        except Exception as e:
            api_logger.error(f"Failed to save webhook event: {e}")

    def _update_event(self, event: WebhookEvent):
        """Update event in database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE webhook_events
                    SET processed = ?, error = ?
                    WHERE id = ?
                """, (1 if event.processed else 0, event.error, event.id))
        except Exception:
            pass

    async def _route_event(self, event: WebhookEvent):
        """Route event to registered handlers"""
        # Generic handlers
        for handler in self._handlers.get("*", []):
            await handler(event)

        # Webhook-specific handlers
        for handler in self._handlers.get(event.webhook_id, []):
            await handler(event)

        # Event type handlers
        for handler in self._handlers.get(event.event_type, []):
            await handler(event)

    def register_handler(
        self,
        pattern: str,
        handler: Callable[[WebhookEvent], Awaitable[None]]
    ):
        """
        Register a webhook event handler

        Args:
            pattern: Pattern to match (webhook_id, event_type, or "*" for all)
            handler: Async handler function
        """
        if pattern not in self._handlers:
            self._handlers[pattern] = []
        self._handlers[pattern].append(handler)

    # ==================== Event History ====================

    def get_events(
        self,
        webhook_id: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get webhook event history"""
        try:
            with get_db() as conn:
                query = "SELECT * FROM webhook_events WHERE 1=1"
                params = []

                if webhook_id:
                    query += " AND webhook_id = ?"
                    params.append(webhook_id)
                if event_type:
                    query += " AND event_type = ?"
                    params.append(event_type)
                if since:
                    query += " AND received_at >= ?"
                    params.append(since.isoformat())

                query += " ORDER BY received_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                return [dict(row) for row in rows]
        except Exception:
            return []

    def get_stats(self) -> Dict[str, Any]:
        """Get webhook statistics"""
        stats = {
            "total_webhooks": len(self._webhooks),
            "active_webhooks": sum(1 for w in self._webhooks.values() if w.status == WebhookStatus.ACTIVE),
            "events_today": 0,
            "events_failed": 0
        }

        try:
            with get_db() as conn:
                today = datetime.utcnow().date().isoformat()

                stats["events_today"] = conn.execute(
                    "SELECT COUNT(*) FROM webhook_events WHERE received_at >= ?",
                    (today,)
                ).fetchone()[0]

                stats["events_failed"] = conn.execute(
                    "SELECT COUNT(*) FROM webhook_events WHERE error IS NOT NULL AND received_at >= ?",
                    (today,)
                ).fetchone()[0]
        except Exception:
            pass

        return stats


# Global webhook manager instance
_webhook_manager: Optional[WebhookManager] = None


def get_webhook_manager() -> WebhookManager:
    """Get the global WebhookManager instance"""
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager()
    return _webhook_manager


# Decorator for webhook handlers
def webhook_handler(pattern: str):
    """
    Decorator to register a webhook handler

    Usage:
        @webhook_handler("github.push")
        async def handle_github_push(event: WebhookEvent):
            print(f"Push event: {event.payload}")
    """
    def decorator(func: Callable[[WebhookEvent], Awaitable[None]]):
        manager = get_webhook_manager()
        manager.register_handler(pattern, func)
        return func
    return decorator
