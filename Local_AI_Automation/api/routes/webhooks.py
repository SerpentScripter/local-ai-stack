"""
Webhook Routes
API endpoints for webhook management and receiving
"""
from fastapi import APIRouter, HTTPException, Request, Header, BackgroundTasks
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from ..webhooks import (
    get_webhook_manager, WebhookType, WebhookStatus,
    WebhookConfig
)
from ..auth import require_auth, AUTH_ENABLED

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


# ==================== Pydantic Models ====================

class WebhookCreateRequest(BaseModel):
    """Request to create a webhook"""
    name: str = Field(..., min_length=1, max_length=100)
    type: str = "generic"
    description: str = ""
    allowed_events: List[str] = []
    rate_limit: int = Field(100, ge=1, le=10000)


class WebhookUpdateRequest(BaseModel):
    """Request to update a webhook"""
    name: Optional[str] = None
    status: Optional[str] = None
    description: Optional[str] = None
    allowed_events: Optional[List[str]] = None
    rate_limit: Optional[int] = None


class WebhookResponse(BaseModel):
    """Response for webhook operations"""
    id: str
    name: str
    type: str
    status: str
    created_at: str
    description: str
    endpoint: str
    rate_limit: int


class WebhookSecretResponse(BaseModel):
    """Response including webhook secret (only on create)"""
    id: str
    name: str
    type: str
    secret: str
    endpoint: str
    instructions: str


# ==================== Management Endpoints ====================

@router.post("/", response_model=WebhookSecretResponse)
def create_webhook(data: WebhookCreateRequest):
    """
    Create a new webhook endpoint

    Returns the webhook ID and secret. The secret is only shown once!
    """
    manager = get_webhook_manager()

    try:
        wh_type = WebhookType(data.type)
    except ValueError:
        wh_type = WebhookType.GENERIC

    webhook = manager.create_webhook(
        name=data.name,
        webhook_type=wh_type,
        description=data.description,
        allowed_events=data.allowed_events,
        rate_limit=data.rate_limit
    )

    return WebhookSecretResponse(
        id=webhook.id,
        name=webhook.name,
        type=webhook.type.value,
        secret=webhook.secret,
        endpoint=f"/webhooks/receive/{webhook.id}",
        instructions=f"Send POST requests to /webhooks/receive/{webhook.id} with X-Webhook-Signature header"
    )


@router.get("/", response_model=List[WebhookResponse])
def list_webhooks():
    """List all webhooks (secrets not included)"""
    manager = get_webhook_manager()
    webhooks = manager.list_webhooks()

    return [
        WebhookResponse(
            id=w.id,
            name=w.name,
            type=w.type.value,
            status=w.status.value,
            created_at=w.created_at.isoformat(),
            description=w.description,
            endpoint=f"/webhooks/receive/{w.id}",
            rate_limit=w.rate_limit
        )
        for w in webhooks
    ]


@router.get("/{webhook_id}", response_model=WebhookResponse)
def get_webhook(webhook_id: str):
    """Get webhook details (secret not included)"""
    manager = get_webhook_manager()
    webhook = manager.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return WebhookResponse(
        id=webhook.id,
        name=webhook.name,
        type=webhook.type.value,
        status=webhook.status.value,
        created_at=webhook.created_at.isoformat(),
        description=webhook.description,
        endpoint=f"/webhooks/receive/{webhook.id}",
        rate_limit=webhook.rate_limit
    )


@router.patch("/{webhook_id}", response_model=WebhookResponse)
def update_webhook(webhook_id: str, data: WebhookUpdateRequest):
    """Update webhook configuration"""
    manager = get_webhook_manager()

    status = None
    if data.status:
        try:
            status = WebhookStatus(data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")

    webhook = manager.update_webhook(
        webhook_id,
        name=data.name,
        status=status,
        description=data.description,
        allowed_events=data.allowed_events,
        rate_limit=data.rate_limit
    )

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return WebhookResponse(
        id=webhook.id,
        name=webhook.name,
        type=webhook.type.value,
        status=webhook.status.value,
        created_at=webhook.created_at.isoformat(),
        description=webhook.description,
        endpoint=f"/webhooks/receive/{webhook.id}",
        rate_limit=webhook.rate_limit
    )


@router.delete("/{webhook_id}")
def delete_webhook(webhook_id: str):
    """Delete a webhook"""
    manager = get_webhook_manager()

    if not manager.delete_webhook(webhook_id):
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {"status": "deleted", "webhook_id": webhook_id}


@router.post("/{webhook_id}/regenerate-secret")
def regenerate_secret(webhook_id: str):
    """
    Regenerate webhook secret

    Returns the new secret. The old secret is immediately invalidated.
    """
    manager = get_webhook_manager()
    new_secret = manager.regenerate_secret(webhook_id)

    if not new_secret:
        raise HTTPException(status_code=404, detail="Webhook not found")

    return {
        "webhook_id": webhook_id,
        "secret": new_secret,
        "message": "Secret regenerated. Update your integration immediately."
    }


# ==================== Receiving Endpoints ====================

@router.post("/receive/{webhook_id}")
async def receive_webhook(
    webhook_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    x_webhook_signature: Optional[str] = Header(None, alias="X-Webhook-Signature"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_gitlab_token: Optional[str] = Header(None, alias="X-Gitlab-Token"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_gitlab_event: Optional[str] = Header(None, alias="X-Gitlab-Event")
):
    """
    Receive webhook events

    Validates signature and processes the webhook.
    Supports GitHub, GitLab, and generic webhook formats.
    """
    manager = get_webhook_manager()
    webhook = manager.get_webhook(webhook_id)

    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if webhook.status != WebhookStatus.ACTIVE:
        raise HTTPException(status_code=403, detail="Webhook is not active")

    # Check rate limit
    if not manager.check_rate_limit(webhook_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # Get payload
    body = await request.body()
    try:
        payload = await request.json()
    except Exception:
        payload = {"raw": body.decode(errors="replace")}

    # Get signature (check multiple header formats)
    signature = (
        x_webhook_signature or
        x_hub_signature_256 or
        x_gitlab_token or
        ""
    )

    # Validate signature
    if signature and webhook.secret:
        if not manager.validate_signature(webhook_id, body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")

    # Determine event type
    event_type = x_github_event or x_gitlab_event or payload.get("event", "unknown")

    # Get headers
    headers = dict(request.headers)

    # Get source IP
    source_ip = request.client.host if request.client else "unknown"

    # Process webhook (in background for fast response)
    async def process():
        await manager.process_webhook(
            webhook_id=webhook_id,
            payload=payload,
            headers=headers,
            source_ip=source_ip,
            event_type=event_type
        )

    background_tasks.add_task(process)

    return {
        "status": "accepted",
        "webhook_id": webhook_id,
        "event_type": event_type
    }


# ==================== Event History Endpoints ====================

@router.get("/{webhook_id}/events")
def get_webhook_events(
    webhook_id: str,
    event_type: Optional[str] = None,
    limit: int = 100
):
    """Get event history for a webhook"""
    manager = get_webhook_manager()

    webhook = manager.get_webhook(webhook_id)
    if not webhook:
        raise HTTPException(status_code=404, detail="Webhook not found")

    events = manager.get_events(
        webhook_id=webhook_id,
        event_type=event_type,
        limit=limit
    )

    return {"events": events, "count": len(events)}


@router.get("/events/all")
def get_all_events(
    event_type: Optional[str] = None,
    limit: int = 100
):
    """Get all webhook events across all webhooks"""
    manager = get_webhook_manager()
    events = manager.get_events(event_type=event_type, limit=limit)
    return {"events": events, "count": len(events)}


@router.get("/stats")
def get_webhook_stats():
    """Get webhook statistics"""
    manager = get_webhook_manager()
    return manager.get_stats()


# ==================== Type Information ====================

@router.get("/types/list")
def list_webhook_types():
    """List available webhook types"""
    return {
        "types": [
            {"value": t.value, "name": t.name}
            for t in WebhookType
        ]
    }


@router.get("/status/list")
def list_webhook_statuses():
    """List available webhook statuses"""
    return {
        "statuses": [
            {"value": s.value, "name": s.name}
            for s in WebhookStatus
        ]
    }
