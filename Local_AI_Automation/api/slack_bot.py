"""
Slack Bot Integration
Bidirectional Slack integration for the Local AI Hub

Provides:
- Outbound notifications (webhooks)
- Slash commands (/task, /research, /status)
- Interactive components (buttons, modals)
- Event subscriptions
"""
import os
import hmac
import hashlib
import time
import json
import httpx
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable, Awaitable
from dataclasses import dataclass
from enum import Enum

from .secrets_manager import get_secret, SecretKeys
from .logging_config import api_logger
from .database import get_db


# Slack configuration
SLACK_BOT_TOKEN = get_secret(SecretKeys.SLACK_BOT_TOKEN) or os.getenv("SLACK_BOT_TOKEN")
SLACK_SIGNING_SECRET = get_secret("slack_signing_secret") or os.getenv("SLACK_SIGNING_SECRET")
SLACK_WEBHOOK_URL = get_secret(SecretKeys.SLACK_WEBHOOK_URL) or os.getenv("SLACK_WEBHOOK_URL")


class SlackMessageType(Enum):
    """Types of Slack messages"""
    TEXT = "text"
    BLOCKS = "blocks"
    ATTACHMENT = "attachment"


@dataclass
class SlackMessage:
    """A Slack message"""
    channel: Optional[str] = None
    text: str = ""
    blocks: Optional[List[Dict[str, Any]]] = None
    attachments: Optional[List[Dict[str, Any]]] = None
    thread_ts: Optional[str] = None
    reply_broadcast: bool = False


class SlackBot:
    """
    Slack bot for Local AI Hub integration

    Features:
    - Send notifications to channels
    - Handle slash commands
    - Process interactive components
    - Verify request signatures
    """

    def __init__(self):
        self._bot_token = SLACK_BOT_TOKEN
        self._signing_secret = SLACK_SIGNING_SECRET
        self._webhook_url = SLACK_WEBHOOK_URL
        self._command_handlers: Dict[str, Callable] = {}
        self._action_handlers: Dict[str, Callable] = {}
        self._register_default_commands()

    def _register_default_commands(self):
        """Register default slash command handlers"""
        self.register_command("task", self._cmd_task)
        self.register_command("research", self._cmd_research)
        self.register_command("status", self._cmd_status)
        self.register_command("help", self._cmd_help)

    # ==================== Outbound Messages ====================

    async def send_message(
        self,
        channel: str,
        text: str,
        blocks: Optional[List[Dict]] = None,
        thread_ts: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Send a message to a Slack channel

        Args:
            channel: Channel ID or name
            text: Message text (fallback for blocks)
            blocks: Block Kit blocks
            thread_ts: Thread timestamp for replies

        Returns:
            Slack API response or None on error
        """
        if not self._bot_token:
            api_logger.warning("Slack bot token not configured")
            return None

        payload = {
            "channel": channel,
            "text": text
        }

        if blocks:
            payload["blocks"] = blocks
        if thread_ts:
            payload["thread_ts"] = thread_ts

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self._bot_token}",
                        "Content-Type": "application/json"
                    },
                    json=payload
                )
                result = response.json()

                if not result.get("ok"):
                    api_logger.error(f"Slack API error: {result.get('error')}")
                    return None

                return result

        except Exception as e:
            api_logger.error(f"Failed to send Slack message: {e}")
            return None

    async def send_webhook(
        self,
        text: str,
        blocks: Optional[List[Dict]] = None,
        attachments: Optional[List[Dict]] = None
    ) -> bool:
        """
        Send a message via incoming webhook

        Args:
            text: Message text
            blocks: Block Kit blocks
            attachments: Legacy attachments

        Returns:
            True if sent successfully
        """
        if not self._webhook_url:
            api_logger.warning("Slack webhook URL not configured")
            return False

        payload = {"text": text}

        if blocks:
            payload["blocks"] = blocks
        if attachments:
            payload["attachments"] = attachments

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self._webhook_url,
                    json=payload
                )
                return response.status_code == 200

        except Exception as e:
            api_logger.error(f"Failed to send Slack webhook: {e}")
            return False

    # ==================== Notification Helpers ====================

    async def notify_task_created(self, task: Dict[str, Any], channel: Optional[str] = None):
        """Send notification for new task"""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "📋 New Task Created"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*ID:*\n{task.get('external_id', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Priority:*\n{task.get('priority', 'P2')}"}
                ]
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*{task.get('title', 'Untitled')}*"}
            }
        ]

        if task.get('description'):
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": task['description'][:500]}
            })

        blocks.append({
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "View in Hub"},
                    "url": f"http://localhost:8765/#task-{task.get('external_id', '')}",
                    "action_id": "view_task"
                }
            ]
        })

        if channel:
            await self.send_message(channel, f"New task: {task.get('title')}", blocks)
        else:
            await self.send_webhook(f"New task: {task.get('title')}", blocks)

    async def notify_research_complete(self, session: Dict[str, Any], channel: Optional[str] = None):
        """Send notification for completed research"""
        blocks = [
            {
                "type": "header",
                "text": {"type": "plain_text", "text": "🔬 Research Complete"}
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Goal:* {session.get('goal', 'Unknown')}"}
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": f"*Session:*\n{session.get('id', 'N/A')}"},
                    {"type": "mrkdwn", "text": f"*Status:*\n{session.get('status', 'unknown')}"}
                ]
            }
        ]

        if channel:
            await self.send_message(channel, f"Research complete: {session.get('goal')}", blocks)
        else:
            await self.send_webhook(f"Research complete: {session.get('goal')}", blocks)

    async def notify_service_status(self, service: Dict[str, Any], channel: Optional[str] = None):
        """Send notification for service status change"""
        status = service.get('status', 'unknown')
        emoji = "🟢" if status == "running" else "🔴"

        text = f"{emoji} *{service.get('name', 'Service')}* is now *{status}*"

        if channel:
            await self.send_message(channel, text)
        else:
            await self.send_webhook(text)

    # ==================== Slash Commands ====================

    def register_command(self, command: str, handler: Callable):
        """Register a slash command handler"""
        self._command_handlers[command] = handler

    async def handle_slash_command(
        self,
        command: str,
        text: str,
        user_id: str,
        channel_id: str,
        response_url: str
    ) -> Dict[str, Any]:
        """
        Handle an incoming slash command

        Args:
            command: Command name (without /)
            text: Command arguments
            user_id: Slack user ID
            channel_id: Slack channel ID
            response_url: URL for delayed responses

        Returns:
            Response dict for Slack
        """
        # Remove leading slash if present
        command = command.lstrip("/")

        handler = self._command_handlers.get(command)
        if not handler:
            return {
                "response_type": "ephemeral",
                "text": f"Unknown command: /{command}"
            }

        try:
            return await handler(text, user_id, channel_id, response_url)
        except Exception as e:
            api_logger.error(f"Slash command error: {e}")
            return {
                "response_type": "ephemeral",
                "text": f"Error processing command: {str(e)}"
            }

    # ==================== Default Command Handlers ====================

    async def _cmd_task(self, text: str, user_id: str, channel_id: str, response_url: str) -> Dict:
        """Handle /task command"""
        parts = text.split(maxsplit=1)
        action = parts[0].lower() if parts else "list"
        args = parts[1] if len(parts) > 1 else ""

        if action == "list":
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT external_id, title, priority, status FROM backlog_items ORDER BY created_at DESC LIMIT 5"
                ).fetchall()

            if not rows:
                return {"response_type": "ephemeral", "text": "No tasks found"}

            blocks = [{"type": "header", "text": {"type": "plain_text", "text": "📋 Recent Tasks"}}]
            for row in rows:
                blocks.append({
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": f"`{row['external_id']}` *{row['title']}*\n_{row['priority']} | {row['status']}_"}
                })

            return {"response_type": "ephemeral", "blocks": blocks}

        elif action == "create":
            if not args:
                return {"response_type": "ephemeral", "text": "Usage: /task create <title>"}

            from .database import generate_external_id
            external_id = generate_external_id()

            with get_db() as conn:
                conn.execute(
                    "INSERT INTO backlog_items (external_id, title, status, priority, created_at) VALUES (?, ?, 'backlog', 'P2', ?)",
                    (external_id, args, datetime.utcnow().isoformat())
                )

            return {
                "response_type": "in_channel",
                "text": f"✅ Created task `{external_id}`: {args}"
            }

        elif action == "status":
            if not args:
                return {"response_type": "ephemeral", "text": "Usage: /task status <task_id> <new_status>"}

            task_id, new_status = args.split(maxsplit=1) if " " in args else (args, None)

            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM backlog_items WHERE external_id = ?", (task_id,)
                ).fetchone()

                if not row:
                    return {"response_type": "ephemeral", "text": f"Task `{task_id}` not found"}

                if new_status:
                    conn.execute(
                        "UPDATE backlog_items SET status = ? WHERE external_id = ?",
                        (new_status, task_id)
                    )
                    return {"response_type": "in_channel", "text": f"✅ Updated `{task_id}` to *{new_status}*"}
                else:
                    return {"response_type": "ephemeral", "text": f"`{task_id}`: {row['title']} ({row['status']})"}

        return {"response_type": "ephemeral", "text": f"Unknown action: {action}. Try: list, create, status"}

    async def _cmd_research(self, text: str, user_id: str, channel_id: str, response_url: str) -> Dict:
        """Handle /research command"""
        if not text:
            return {"response_type": "ephemeral", "text": "Usage: /research <topic>"}

        import uuid
        session_id = f"research-{uuid.uuid4().hex[:8]}"

        with get_db() as conn:
            conn.execute(
                "INSERT INTO research_sessions (id, goal, status, start_time) VALUES (?, ?, 'queued', ?)",
                (session_id, text, datetime.utcnow().isoformat())
            )

        return {
            "response_type": "in_channel",
            "text": f"🔬 Research session `{session_id}` started!\n*Goal:* {text}\n\nI'll notify you when complete."
        }

    async def _cmd_status(self, text: str, user_id: str, channel_id: str, response_url: str) -> Dict:
        """Handle /status command"""
        from .routes.services import SERVICE_REGISTRY, get_service_status

        services = []
        for svc_id, svc in SERVICE_REGISTRY.items():
            status = get_service_status(svc)
            emoji = "🟢" if status == "running" else "🔴"
            services.append(f"{emoji} {svc['name']}: {status}")

        return {
            "response_type": "ephemeral",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🖥️ System Status"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": "\n".join(services)}}
            ]
        }

    async def _cmd_help(self, text: str, user_id: str, channel_id: str, response_url: str) -> Dict:
        """Handle /help command"""
        return {
            "response_type": "ephemeral",
            "blocks": [
                {"type": "header", "text": {"type": "plain_text", "text": "🤖 Local AI Hub Commands"}},
                {"type": "section", "text": {"type": "mrkdwn", "text": """
*Task Management:*
• `/task list` - Show recent tasks
• `/task create <title>` - Create new task
• `/task status <id> [status]` - View/update task status

*Research:*
• `/research <topic>` - Start research on a topic

*System:*
• `/status` - Show service status
• `/help` - Show this help
                """.strip()}}
            ]
        }

    # ==================== Interactive Components ====================

    def register_action(self, action_id: str, handler: Callable):
        """Register an action handler for interactive components"""
        self._action_handlers[action_id] = handler

    async def handle_interaction(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle interactive component payload"""
        interaction_type = payload.get("type")

        if interaction_type == "block_actions":
            for action in payload.get("actions", []):
                action_id = action.get("action_id")
                handler = self._action_handlers.get(action_id)
                if handler:
                    return await handler(payload, action)

        elif interaction_type == "view_submission":
            callback_id = payload.get("view", {}).get("callback_id")
            handler = self._action_handlers.get(callback_id)
            if handler:
                return await handler(payload)

        return None

    # ==================== Signature Verification ====================

    def verify_signature(self, body: bytes, timestamp: str, signature: str) -> bool:
        """
        Verify Slack request signature

        Args:
            body: Request body
            timestamp: X-Slack-Request-Timestamp header
            signature: X-Slack-Signature header

        Returns:
            True if signature is valid
        """
        if not self._signing_secret:
            api_logger.warning("Slack signing secret not configured")
            return True  # Skip verification if not configured

        # Check timestamp is recent (within 5 minutes)
        try:
            ts = int(timestamp)
            if abs(time.time() - ts) > 300:
                return False
        except ValueError:
            return False

        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{body.decode()}"
        expected = "v0=" + hmac.new(
            self._signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, signature)


# Global Slack bot instance
_slack_bot: Optional[SlackBot] = None


def get_slack_bot() -> SlackBot:
    """Get the global SlackBot instance"""
    global _slack_bot
    if _slack_bot is None:
        _slack_bot = SlackBot()
    return _slack_bot


# Convenience functions
async def slack_notify(text: str, blocks: Optional[List[Dict]] = None):
    """Send a notification to Slack"""
    bot = get_slack_bot()
    return await bot.send_webhook(text, blocks)
