"""
Orchestration Routes
API endpoints for agent orchestration, shared memory, and messaging
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime
import asyncio

from ..orchestrator import get_orchestrator, OrchestratorConfig, SupervisorStrategy
from ..shared_memory import get_shared_memory, MemoryScope
from ..capability_registry import (
    get_capability_registry, Capability, CapabilityType, TaskRequirement
)
from ..message_bus import get_message_bus, MessageType
from ..agent_base import AgentStatus

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


# ==================== Pydantic Models ====================

class AgentStartRequest(BaseModel):
    """Request to start an agent"""
    agent_id: str
    goal: str
    parameters: Optional[Dict[str, Any]] = None


class MemorySetRequest(BaseModel):
    """Request to set a memory value"""
    key: str
    value: Any
    scope: str = "global"
    owner: Optional[str] = None
    ttl: Optional[int] = None
    tags: Optional[List[str]] = None


class MemoryGetRequest(BaseModel):
    """Request to get a memory value"""
    key: str
    scope: str = "global"
    owner: Optional[str] = None


class CapabilitySearchRequest(BaseModel):
    """Request to search for capabilities"""
    capability_name: Optional[str] = None
    capability_type: Optional[str] = None
    tags: Optional[List[str]] = None
    min_reliability: float = 0.0
    max_cost: float = 999999


class MessagePublishRequest(BaseModel):
    """Request to publish a message"""
    topic: str
    payload: Any
    sender: Optional[str] = None
    priority: int = 1


# ==================== Orchestrator Endpoints ====================

@router.get("/status")
def get_orchestrator_status():
    """Get orchestrator status and statistics"""
    orch = get_orchestrator()
    return orch.get_stats()


@router.get("/agents")
def list_orchestrated_agents(group: Optional[str] = None):
    """List agents managed by the orchestrator"""
    orch = get_orchestrator()
    return orch.list_agents(group)


@router.get("/agents/{agent_id}")
def get_agent_status(agent_id: str):
    """Get status of a specific agent"""
    orch = get_orchestrator()
    status = orch.get_agent_status(agent_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    return status


@router.post("/agents/{agent_id}/start")
async def start_agent(agent_id: str, request: AgentStartRequest):
    """Start a registered agent"""
    orch = get_orchestrator()
    try:
        success = await orch.start_agent(agent_id, request.goal, request.parameters)
        return {"status": "started" if success else "already_running", "agent_id": agent_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/agents/{agent_id}/stop")
async def stop_agent(agent_id: str, graceful: bool = True):
    """Stop a running agent"""
    orch = get_orchestrator()
    success = await orch.stop_agent(agent_id, graceful)
    return {"status": "stopped" if success else "not_running", "agent_id": agent_id}


@router.post("/agents/{agent_id}/pause")
async def pause_agent(agent_id: str):
    """Pause a running agent"""
    orch = get_orchestrator()
    success = await orch.pause_agent(agent_id)
    return {"status": "paused" if success else "not_running", "agent_id": agent_id}


@router.post("/agents/{agent_id}/resume")
async def resume_agent(agent_id: str):
    """Resume a paused agent"""
    orch = get_orchestrator()
    success = await orch.resume_agent(agent_id)
    return {"status": "resumed" if success else "not_paused", "agent_id": agent_id}


# ==================== Shared Memory Endpoints ====================

@router.post("/memory/set")
def set_memory(request: MemorySetRequest):
    """Store a value in shared memory"""
    mem = get_shared_memory()
    try:
        scope = MemoryScope(request.scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {request.scope}")

    success = mem.set(
        request.key,
        request.value,
        scope=scope,
        owner=request.owner,
        ttl=request.ttl,
        tags=request.tags
    )
    return {"status": "stored" if success else "failed", "key": request.key}


@router.post("/memory/get")
def get_memory(request: MemoryGetRequest):
    """Retrieve a value from shared memory"""
    mem = get_shared_memory()
    try:
        scope = MemoryScope(request.scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {request.scope}")

    value = mem.get(request.key, scope=scope, owner=request.owner)
    if value is None:
        raise HTTPException(status_code=404, detail=f"Key not found: {request.key}")
    return {"key": request.key, "value": value}


@router.delete("/memory/{key}")
def delete_memory(key: str, scope: str = "global", owner: Optional[str] = None):
    """Delete a value from shared memory"""
    mem = get_shared_memory()
    try:
        scope_enum = MemoryScope(scope)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid scope: {scope}")

    mem.delete(key, scope=scope_enum, owner=owner)
    return {"status": "deleted", "key": key}


@router.get("/memory/stats")
def get_memory_stats():
    """Get shared memory statistics"""
    mem = get_shared_memory()
    return mem.get_stats()


@router.get("/memory/list")
def list_memory_keys(pattern: str = "*", scope: Optional[str] = None, limit: int = 100):
    """List memory keys matching a pattern"""
    mem = get_shared_memory()
    scope_enum = MemoryScope(scope) if scope else None
    keys = mem.list_keys(pattern=pattern, scope=scope_enum, limit=limit)
    return {"keys": keys, "count": len(keys)}


# ==================== Capability Registry Endpoints ====================

@router.get("/capabilities")
def list_capabilities():
    """List all registered capabilities"""
    registry = get_capability_registry()
    return {
        "capabilities": registry.list_capabilities(),
        "agents": registry.list_agents(),
        "stats": registry.get_stats()
    }


@router.get("/capabilities/agents")
def list_capable_agents():
    """List all agents with their capabilities"""
    registry = get_capability_registry()
    return registry.export()


@router.post("/capabilities/search")
def search_capabilities(request: CapabilitySearchRequest):
    """Search for agents matching requirements"""
    registry = get_capability_registry()

    cap_type = None
    if request.capability_type:
        try:
            cap_type = CapabilityType(request.capability_type)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid capability type: {request.capability_type}"
            )

    requirement = TaskRequirement(
        capability_name=request.capability_name,
        capability_type=cap_type,
        tags=request.tags or [],
        min_reliability=request.min_reliability,
        max_cost=request.max_cost
    )

    results = registry.find_agents(requirement)
    return {
        "matches": [
            {
                "agent_type": r.agent_type,
                "capability": r.capability.name,
                "score": r.score,
                "reasons": r.reasons
            }
            for r in results
        ]
    }


@router.get("/capabilities/types")
def list_capability_types():
    """List available capability types"""
    return {
        "types": [{"value": t.value, "name": t.name} for t in CapabilityType]
    }


# ==================== Message Bus Endpoints ====================

@router.post("/messages/publish")
async def publish_message(request: MessagePublishRequest):
    """Publish a message to the bus"""
    bus = get_message_bus()
    msg_id = await bus.publish(
        request.topic,
        request.payload,
        sender=request.sender
    )
    return {"status": "published", "message_id": msg_id}


@router.get("/messages/history")
def get_message_history(topic: Optional[str] = None, limit: int = 100):
    """Get recent message history"""
    bus = get_message_bus()
    messages = bus.get_message_history(topic=topic, limit=limit)
    return {
        "messages": [m.to_dict() for m in messages],
        "count": len(messages)
    }


@router.get("/messages/subscriptions")
def get_subscriptions(subscriber: Optional[str] = None):
    """Get active subscriptions"""
    bus = get_message_bus()
    return {"subscriptions": bus.get_subscriptions(subscriber)}


@router.get("/messages/stats")
def get_message_bus_stats():
    """Get message bus statistics"""
    bus = get_message_bus()
    return bus.get_stats()


# ==================== Timeline Endpoint ====================

@router.get("/timeline")
def get_agent_timeline(hours: int = 24, limit: int = 100):
    """
    Get agent execution timeline for visualization

    Returns events for the timeline UI component.
    """
    from ..database import get_db
    from datetime import timedelta

    events = []
    cutoff = datetime.utcnow() - timedelta(hours=hours)

    try:
        with get_db() as conn:
            # Get from research_sessions (agent executions)
            rows = conn.execute("""
                SELECT id, goal, status, start_time, end_time, knowledge_graph
                FROM research_sessions
                WHERE start_time >= ?
                ORDER BY start_time DESC
                LIMIT ?
            """, (cutoff.isoformat(), limit)).fetchall()

            for row in rows:
                events.append({
                    "id": row["id"],
                    "type": "agent_execution",
                    "title": row["goal"][:50] + "..." if len(row["goal"]) > 50 else row["goal"],
                    "status": row["status"],
                    "start_time": row["start_time"],
                    "end_time": row["end_time"],
                    "details": {
                        "goal": row["goal"],
                        "has_output": row["knowledge_graph"] is not None
                    }
                })

            # Get from job_queue
            rows = conn.execute("""
                SELECT job_id, func_name, status, created_at, ended_at, error
                FROM job_queue
                WHERE created_at >= ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (cutoff.isoformat(), limit)).fetchall()

            for row in rows:
                events.append({
                    "id": row["job_id"],
                    "type": "job",
                    "title": row["func_name"],
                    "status": row["status"],
                    "start_time": row["created_at"],
                    "end_time": row["ended_at"],
                    "details": {
                        "error": row["error"]
                    }
                })

    except Exception as e:
        pass  # Tables might not exist

    # Sort by start time
    events.sort(key=lambda e: e.get("start_time") or "", reverse=True)

    return {
        "events": events[:limit],
        "count": len(events),
        "hours": hours
    }


# ==================== WebSocket for Real-time Updates ====================

@router.websocket("/ws/events")
async def orchestration_websocket(websocket: WebSocket):
    """WebSocket for real-time orchestration events"""
    await websocket.accept()

    bus = get_message_bus()

    # Subscribe to all agent events
    async def forward_to_ws(message):
        try:
            await websocket.send_json(message.to_dict())
        except Exception:
            pass

    sub_id = await bus.subscribe("agents.*", forward_to_ws)

    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await bus.unsubscribe(sub_id)
    except Exception:
        await bus.unsubscribe(sub_id)
