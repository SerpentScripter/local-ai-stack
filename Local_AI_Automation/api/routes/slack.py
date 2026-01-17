"""
Slack Integration Routes
API endpoints for Slack bot interactions
"""
import json
from fastapi import APIRouter, Request, HTTPException, Form, Header
from fastapi.responses import JSONResponse
from typing import Optional
from urllib.parse import parse_qs

from ..slack_bot import get_slack_bot

router = APIRouter(prefix="/slack", tags=["slack"])


@router.post("/commands")
async def handle_slash_command(
    request: Request,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature")
):
    """
    Handle incoming Slack slash commands

    Slack sends slash commands as form-encoded POST requests.
    """
    bot = get_slack_bot()

    # Get raw body for signature verification
    body = await request.body()

    # Verify signature
    if not bot.verify_signature(body, x_slack_request_timestamp, x_slack_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse form data
    form_data = parse_qs(body.decode())

    command = form_data.get("command", [""])[0]
    text = form_data.get("text", [""])[0]
    user_id = form_data.get("user_id", [""])[0]
    channel_id = form_data.get("channel_id", [""])[0]
    response_url = form_data.get("response_url", [""])[0]

    # Handle command
    response = await bot.handle_slash_command(
        command=command,
        text=text,
        user_id=user_id,
        channel_id=channel_id,
        response_url=response_url
    )

    return JSONResponse(content=response)


@router.post("/interactions")
async def handle_interaction(
    request: Request,
    x_slack_request_timestamp: str = Header(..., alias="X-Slack-Request-Timestamp"),
    x_slack_signature: str = Header(..., alias="X-Slack-Signature")
):
    """
    Handle Slack interactive components (buttons, modals, etc.)

    Slack sends interactions as form-encoded with a 'payload' JSON field.
    """
    bot = get_slack_bot()

    # Get raw body for signature verification
    body = await request.body()

    # Verify signature
    if not bot.verify_signature(body, x_slack_request_timestamp, x_slack_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Parse payload
    form_data = parse_qs(body.decode())
    payload_str = form_data.get("payload", ["{}"])[0]
    payload = json.loads(payload_str)

    # Handle interaction
    response = await bot.handle_interaction(payload)

    if response:
        return JSONResponse(content=response)
    return JSONResponse(content={"ok": True})


@router.post("/events")
async def handle_events(
    request: Request,
    x_slack_request_timestamp: Optional[str] = Header(None, alias="X-Slack-Request-Timestamp"),
    x_slack_signature: Optional[str] = Header(None, alias="X-Slack-Signature")
):
    """
    Handle Slack Events API

    Used for:
    - URL verification challenge
    - Event subscriptions (messages, reactions, etc.)
    """
    bot = get_slack_bot()

    body = await request.body()
    data = await request.json()

    # Handle URL verification challenge
    if data.get("type") == "url_verification":
        return {"challenge": data.get("challenge")}

    # Verify signature for actual events
    if x_slack_request_timestamp and x_slack_signature:
        if not bot.verify_signature(body, x_slack_request_timestamp, x_slack_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Process event
    event = data.get("event", {})
    event_type = event.get("type")

    # Handle different event types
    if event_type == "message":
        # Could trigger agent or log message
        pass
    elif event_type == "app_mention":
        # Bot was mentioned
        pass

    return {"ok": True}


@router.get("/status")
async def get_slack_status():
    """Check Slack integration status"""
    from ..secrets_manager import get_secret, SecretKeys
    import os

    bot_token = get_secret(SecretKeys.SLACK_BOT_TOKEN) or os.getenv("SLACK_BOT_TOKEN")
    webhook_url = get_secret(SecretKeys.SLACK_WEBHOOK_URL) or os.getenv("SLACK_WEBHOOK_URL")
    signing_secret = get_secret("slack_signing_secret") or os.getenv("SLACK_SIGNING_SECRET")

    return {
        "configured": {
            "bot_token": bool(bot_token),
            "webhook_url": bool(webhook_url),
            "signing_secret": bool(signing_secret)
        },
        "features": {
            "outbound_messages": bool(bot_token),
            "webhook_notifications": bool(webhook_url),
            "slash_commands": bool(signing_secret),
            "interactive_components": bool(signing_secret)
        }
    }


@router.post("/test-notification")
async def test_notification(message: str = "Test notification from Local AI Hub"):
    """Send a test notification to Slack"""
    bot = get_slack_bot()

    success = await bot.send_webhook(
        text=message,
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"🔔 *Test Notification*\n{message}"
                }
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Sent from Local AI Hub"}
                ]
            }
        ]
    )

    if success:
        return {"status": "sent", "message": message}
    else:
        raise HTTPException(
            status_code=500,
            detail="Failed to send notification. Check Slack webhook configuration."
        )
