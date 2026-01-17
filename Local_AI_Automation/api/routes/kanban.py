"""
Kanban Board Routes
API endpoints for session Kanban board management
"""
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio

from ..session_state_machine import (
    get_session_state_machine,
    SessionState,
    SessionEvent
)

router = APIRouter(prefix="/kanban", tags=["kanban"])


class CreateSessionRequest(BaseModel):
    """Request to create a new session"""
    session_id: str
    project_id: str
    goal: str
    agent_type: str = "general"
    context: Optional[Dict[str, Any]] = None


class TransitionRequest(BaseModel):
    """Request to transition a session"""
    event: str
    metadata: Optional[Dict[str, Any]] = None


class ApprovalRequest(BaseModel):
    """Request to approve/deny a session"""
    approved: bool
    reason: Optional[str] = None


class PRUpdateRequest(BaseModel):
    """Request to update PR status"""
    pr_url: str
    ci_status: Optional[str] = None


class SummaryUpdateRequest(BaseModel):
    """Request to update session summary"""
    summary: str


class WorktreeAttachRequest(BaseModel):
    """Request to attach a worktree to a session"""
    worktree_id: str
    worktree_path: str
    branch_name: str


@router.get("/board")
def get_kanban_board():
    """
    Get the full Kanban board

    Returns sessions organized into columns:
    - working: Currently active
    - needs_approval: Waiting for human approval
    - waiting: Waiting for input or paused
    - idle: Not started or finished waiting
    - completed: Successfully finished
    - failed: Ended with error
    """
    machine = get_session_state_machine()
    return machine.get_kanban_board()


@router.get("/sessions")
def list_sessions(
    state: Optional[str] = None,
    project_id: Optional[str] = None
):
    """List all sessions with optional filtering"""
    machine = get_session_state_machine()

    if state:
        try:
            session_state = SessionState(state)
            sessions = machine.get_sessions_by_state(session_state)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid state: {state}")
    elif project_id:
        sessions = machine.get_sessions_by_project(project_id)
    else:
        sessions = list(machine._sessions.values())

    return [machine._session_to_dict(s) for s in sessions]


@router.post("/sessions")
def create_session(request: CreateSessionRequest):
    """Create a new session"""
    machine = get_session_state_machine()

    # Check if session already exists
    existing = machine.get_session(request.session_id)
    if existing:
        raise HTTPException(status_code=409, detail="Session already exists")

    session = machine.create_session(
        session_id=request.session_id,
        project_id=request.project_id,
        goal=request.goal,
        agent_type=request.agent_type,
        context=request.context
    )

    return machine._session_to_dict(session)


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    """Get a specific session"""
    machine = get_session_state_machine()
    session = machine.get_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return machine._session_to_dict(session)


@router.post("/sessions/{session_id}/transition")
def transition_session(session_id: str, request: TransitionRequest):
    """
    Transition a session to a new state

    Valid events:
    - start: Begin working
    - user_prompt: User provided input
    - tool_request: Tool execution requested
    - tool_result: Tool execution completed
    - approval_requested: Need human approval
    - approval_granted: Approval given
    - approval_denied: Approval denied
    - input_requested: Need user input
    - input_provided: User provided input
    - complete: Session finished
    - error: Session failed
    - pause: Pause session
    - resume: Resume session
    """
    machine = get_session_state_machine()

    try:
        event = SessionEvent(request.event)
    except ValueError:
        valid_events = [e.value for e in SessionEvent]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event. Valid events: {valid_events}"
        )

    # Check if transition is valid
    if not machine.can_transition(session_id, event):
        session = machine.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from {session.state.value} with event {event.value}"
        )

    success = machine.transition(session_id, event, request.metadata)

    if not success:
        raise HTTPException(status_code=400, detail="Transition failed")

    session = machine.get_session(session_id)
    return machine._session_to_dict(session)


@router.post("/sessions/{session_id}/start")
def start_session(session_id: str):
    """Start a session (convenience endpoint)"""
    machine = get_session_state_machine()

    if not machine.start_session(session_id):
        raise HTTPException(status_code=400, detail="Cannot start session")

    session = machine.get_session(session_id)
    return machine._session_to_dict(session)


@router.post("/sessions/{session_id}/approval")
def handle_approval(session_id: str, request: ApprovalRequest):
    """Approve or deny a session"""
    machine = get_session_state_machine()

    if request.approved:
        success = machine.grant_approval(session_id)
    else:
        success = machine.deny_approval(session_id, request.reason)

    if not success:
        raise HTTPException(status_code=400, detail="Cannot process approval")

    session = machine.get_session(session_id)
    return machine._session_to_dict(session)


@router.post("/sessions/{session_id}/complete")
def complete_session(session_id: str, result: Optional[Dict[str, Any]] = None):
    """Mark session as completed"""
    machine = get_session_state_machine()

    if not machine.complete_session(session_id, result):
        raise HTTPException(status_code=400, detail="Cannot complete session")

    session = machine.get_session(session_id)
    return machine._session_to_dict(session)


@router.post("/sessions/{session_id}/fail")
def fail_session(session_id: str, error: Optional[str] = None):
    """Mark session as failed"""
    machine = get_session_state_machine()

    if not machine.fail_session(session_id, error):
        raise HTTPException(status_code=400, detail="Cannot fail session")

    session = machine.get_session(session_id)
    return machine._session_to_dict(session)


@router.post("/sessions/{session_id}/pause")
def pause_session(session_id: str):
    """Pause a session"""
    machine = get_session_state_machine()

    if not machine.pause_session(session_id):
        raise HTTPException(status_code=400, detail="Cannot pause session")

    session = machine.get_session(session_id)
    return machine._session_to_dict(session)


@router.post("/sessions/{session_id}/resume")
def resume_session(session_id: str):
    """Resume a paused session"""
    machine = get_session_state_machine()

    if not machine.resume_session(session_id):
        raise HTTPException(status_code=400, detail="Cannot resume session")

    session = machine.get_session(session_id)
    return machine._session_to_dict(session)


@router.put("/sessions/{session_id}/pr")
def update_pr_status(session_id: str, request: PRUpdateRequest):
    """Update PR and CI status for a session"""
    machine = get_session_state_machine()

    session = machine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    machine.update_pr_status(session_id, request.pr_url, request.ci_status)

    return machine._session_to_dict(machine.get_session(session_id))


@router.put("/sessions/{session_id}/summary")
def update_summary(session_id: str, request: SummaryUpdateRequest):
    """Update AI-generated summary for a session"""
    machine = get_session_state_machine()

    session = machine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    machine.update_summary(session_id, request.summary)

    return machine._session_to_dict(machine.get_session(session_id))


@router.get("/stats")
def get_session_stats():
    """Get session statistics"""
    machine = get_session_state_machine()
    return machine.get_stats()


@router.put("/sessions/{session_id}/worktree")
def attach_worktree(session_id: str, request: WorktreeAttachRequest):
    """Attach a worktree to a session for isolated development"""
    machine = get_session_state_machine()

    session = machine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    machine.attach_worktree(
        session_id=session_id,
        worktree_id=request.worktree_id,
        worktree_path=request.worktree_path,
        branch_name=request.branch_name
    )

    return machine._session_to_dict(machine.get_session(session_id))


@router.delete("/sessions/{session_id}/worktree")
def detach_worktree(session_id: str):
    """Detach worktree from a session"""
    machine = get_session_state_machine()

    session = machine.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    machine.detach_worktree(session_id)

    return machine._session_to_dict(machine.get_session(session_id))


@router.get("/states")
def list_valid_states():
    """List all valid session states"""
    return {
        "states": [s.value for s in SessionState],
        "events": [e.value for e in SessionEvent],
        "transitions": {
            state.value: {
                event.value: target.value
                for event, target in transitions.items()
            }
            for state, transitions in get_session_state_machine().TRANSITIONS.items()
        }
    }


# WebSocket for real-time updates
@router.websocket("/ws")
async def kanban_websocket(websocket: WebSocket):
    """WebSocket for real-time Kanban updates"""
    await websocket.accept()

    machine = get_session_state_machine()

    # Send initial board state
    await websocket.send_json({
        "type": "board",
        "data": machine.get_kanban_board()
    })

    # Set up listeners
    async def on_state_change(session, transition=None):
        try:
            await websocket.send_json({
                "type": "state_changed",
                "session": machine._session_to_dict(session),
                "transition": {
                    "from": transition.from_state.value,
                    "to": transition.to_state.value,
                    "event": transition.event.value
                } if transition else None
            })
        except Exception:
            pass

    machine.on("state_changed", on_state_change)

    try:
        while True:
            # Keep connection alive and handle incoming messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
            elif data == "board":
                await websocket.send_json({
                    "type": "board",
                    "data": machine.get_kanban_board()
                })
    except WebSocketDisconnect:
        machine.off("state_changed", on_state_change)
    except Exception:
        machine.off("state_changed", on_state_change)
