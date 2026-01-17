"""
Session State Machine
XState-inspired state machine for agent session management

States:
- idle: No active work
- working: Agent actively processing
- waiting_for_approval: Requires human approval
- waiting_for_input: Waiting for user input
- completed: Session finished successfully
- failed: Session ended with error

Transitions follow the pattern from claude-code-ui
"""
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .database import get_db
from .logging_config import api_logger
from .message_bus import get_message_bus


class SessionState(Enum):
    """Session states (XState-inspired)"""
    IDLE = "idle"
    WORKING = "working"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    WAITING_FOR_INPUT = "waiting_for_input"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class SessionEvent(Enum):
    """Events that trigger state transitions"""
    START = "start"
    USER_PROMPT = "user_prompt"
    TOOL_REQUEST = "tool_request"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUESTED = "approval_requested"
    APPROVAL_GRANTED = "approval_granted"
    APPROVAL_DENIED = "approval_denied"
    INPUT_REQUESTED = "input_requested"
    INPUT_PROVIDED = "input_provided"
    COMPLETE = "complete"
    ERROR = "error"
    PAUSE = "pause"
    RESUME = "resume"
    TIMEOUT = "timeout"


@dataclass
class StateTransition:
    """A state transition record"""
    from_state: SessionState
    to_state: SessionState
    event: SessionEvent
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Session:
    """An agent session with state tracking"""
    session_id: str
    project_id: str
    goal: str
    state: SessionState = SessionState.IDLE
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    transitions: List[StateTransition] = field(default_factory=list)
    context: Dict[str, Any] = field(default_factory=dict)
    agent_type: str = "general"
    pr_url: Optional[str] = None
    ci_status: Optional[str] = None
    summary: Optional[str] = None
    # Worktree integration
    worktree_id: Optional[str] = None
    worktree_path: Optional[str] = None
    branch_name: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

    @property
    def kanban_column(self) -> str:
        """Map state to Kanban column"""
        mapping = {
            SessionState.IDLE: "idle",
            SessionState.WORKING: "working",
            SessionState.WAITING_FOR_APPROVAL: "needs_approval",
            SessionState.WAITING_FOR_INPUT: "waiting",
            SessionState.PAUSED: "waiting",
            SessionState.COMPLETED: "completed",
            SessionState.FAILED: "failed"
        }
        return mapping.get(self.state, "idle")

    @property
    def duration(self) -> timedelta:
        """Calculate session duration"""
        return datetime.utcnow() - self.created_at


class SessionStateMachine:
    """
    XState-inspired state machine for session management

    Manages state transitions with validation and side effects.
    """

    # Valid state transitions
    TRANSITIONS: Dict[SessionState, Dict[SessionEvent, SessionState]] = {
        SessionState.IDLE: {
            SessionEvent.START: SessionState.WORKING,
            SessionEvent.USER_PROMPT: SessionState.WORKING,
        },
        SessionState.WORKING: {
            SessionEvent.TOOL_REQUEST: SessionState.WORKING,
            SessionEvent.TOOL_RESULT: SessionState.WORKING,
            SessionEvent.APPROVAL_REQUESTED: SessionState.WAITING_FOR_APPROVAL,
            SessionEvent.INPUT_REQUESTED: SessionState.WAITING_FOR_INPUT,
            SessionEvent.COMPLETE: SessionState.COMPLETED,
            SessionEvent.ERROR: SessionState.FAILED,
            SessionEvent.PAUSE: SessionState.PAUSED,
            SessionEvent.TIMEOUT: SessionState.FAILED,
        },
        SessionState.WAITING_FOR_APPROVAL: {
            SessionEvent.APPROVAL_GRANTED: SessionState.WORKING,
            SessionEvent.APPROVAL_DENIED: SessionState.IDLE,
            SessionEvent.TIMEOUT: SessionState.IDLE,
            SessionEvent.ERROR: SessionState.FAILED,
        },
        SessionState.WAITING_FOR_INPUT: {
            SessionEvent.INPUT_PROVIDED: SessionState.WORKING,
            SessionEvent.USER_PROMPT: SessionState.WORKING,
            SessionEvent.TIMEOUT: SessionState.IDLE,
            SessionEvent.ERROR: SessionState.FAILED,
        },
        SessionState.PAUSED: {
            SessionEvent.RESUME: SessionState.WORKING,
            SessionEvent.ERROR: SessionState.FAILED,
        },
        SessionState.COMPLETED: {
            SessionEvent.START: SessionState.WORKING,  # Allow restart
        },
        SessionState.FAILED: {
            SessionEvent.START: SessionState.WORKING,  # Allow retry
        },
    }

    def __init__(self):
        self._sessions: Dict[str, Session] = {}
        self._listeners: Dict[str, List[Callable]] = defaultdict(list)
        self._init_database()

    def _init_database(self):
        """Initialize session state tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS session_states (
                        session_id TEXT PRIMARY KEY,
                        project_id TEXT NOT NULL,
                        goal TEXT,
                        state TEXT NOT NULL,
                        agent_type TEXT DEFAULT 'general',
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL,
                        context TEXT,
                        pr_url TEXT,
                        ci_status TEXT,
                        summary TEXT,
                        worktree_id TEXT,
                        worktree_path TEXT,
                        branch_name TEXT,
                        result TEXT,
                        error TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_session_state
                    ON session_states(state);

                    CREATE INDEX IF NOT EXISTS idx_session_project
                    ON session_states(project_id);

                    CREATE TABLE IF NOT EXISTS session_transitions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        from_state TEXT NOT NULL,
                        to_state TEXT NOT NULL,
                        event TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        metadata TEXT,
                        FOREIGN KEY (session_id) REFERENCES session_states(session_id)
                    );

                    CREATE INDEX IF NOT EXISTS idx_transition_session
                    ON session_transitions(session_id);
                """)
        except Exception as e:
            api_logger.error(f"Failed to init session state tables: {e}")

    # ==================== Session Management ====================

    def create_session(
        self,
        session_id: str,
        project_id: str,
        goal: str,
        agent_type: str = "general",
        context: Dict[str, Any] = None
    ) -> Session:
        """Create a new session"""
        session = Session(
            session_id=session_id,
            project_id=project_id,
            goal=goal,
            agent_type=agent_type,
            context=context or {}
        )

        self._sessions[session_id] = session
        self._persist_session(session)

        # Emit event
        self._emit("session_created", session)

        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID"""
        if session_id in self._sessions:
            return self._sessions[session_id]

        # Try loading from database
        return self._load_session(session_id)

    def get_sessions_by_state(self, state: SessionState) -> List[Session]:
        """Get all sessions in a specific state"""
        return [s for s in self._sessions.values() if s.state == state]

    def get_sessions_by_project(self, project_id: str) -> List[Session]:
        """Get all sessions for a project"""
        return [s for s in self._sessions.values() if s.project_id == project_id]

    def get_kanban_board(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get sessions organized by Kanban columns"""
        columns = {
            "working": [],
            "needs_approval": [],
            "waiting": [],
            "idle": [],
            "completed": [],
            "failed": []
        }

        for session in self._sessions.values():
            column = session.kanban_column
            if column in columns:
                columns[column].append(self._session_to_dict(session))

        # Sort by updated_at (most recent first)
        for column in columns.values():
            column.sort(key=lambda x: x["updated_at"], reverse=True)

        return columns

    # ==================== State Transitions ====================

    def transition(
        self,
        session_id: str,
        event: SessionEvent,
        metadata: Dict[str, Any] = None
    ) -> bool:
        """
        Attempt a state transition

        Returns True if transition was valid and executed.
        """
        session = self.get_session(session_id)
        if not session:
            api_logger.warning(f"Session {session_id} not found")
            return False

        current_state = session.state
        valid_transitions = self.TRANSITIONS.get(current_state, {})

        if event not in valid_transitions:
            api_logger.warning(
                f"Invalid transition: {current_state.value} + {event.value}"
            )
            return False

        new_state = valid_transitions[event]

        # Record transition
        transition = StateTransition(
            from_state=current_state,
            to_state=new_state,
            event=event,
            metadata=metadata or {}
        )
        session.transitions.append(transition)

        # Update session
        session.state = new_state
        session.updated_at = datetime.utcnow()

        # Update context with metadata
        if metadata:
            session.context.update(metadata)

        # Persist
        self._persist_session(session)
        self._persist_transition(session_id, transition)

        # Emit events
        self._emit("state_changed", session, transition)
        self._emit(f"state_{new_state.value}", session)

        api_logger.info(
            f"Session {session_id}: {current_state.value} -> {new_state.value} ({event.value})"
        )

        return True

    def can_transition(self, session_id: str, event: SessionEvent) -> bool:
        """Check if a transition is valid without executing it"""
        session = self.get_session(session_id)
        if not session:
            return False

        valid_transitions = self.TRANSITIONS.get(session.state, {})
        return event in valid_transitions

    # ==================== Convenience Methods ====================

    def start_session(self, session_id: str, metadata: Dict = None) -> bool:
        """Start a session (transition to working)"""
        return self.transition(session_id, SessionEvent.START, metadata)

    def request_approval(self, session_id: str, reason: str = None) -> bool:
        """Request human approval"""
        return self.transition(
            session_id,
            SessionEvent.APPROVAL_REQUESTED,
            {"approval_reason": reason}
        )

    def grant_approval(self, session_id: str) -> bool:
        """Grant approval to continue"""
        return self.transition(session_id, SessionEvent.APPROVAL_GRANTED)

    def deny_approval(self, session_id: str, reason: str = None) -> bool:
        """Deny approval"""
        return self.transition(
            session_id,
            SessionEvent.APPROVAL_DENIED,
            {"denial_reason": reason}
        )

    def complete_session(self, session_id: str, result: Dict = None) -> bool:
        """Mark session as completed"""
        return self.transition(
            session_id,
            SessionEvent.COMPLETE,
            {"result": result}
        )

    def fail_session(self, session_id: str, error: str = None) -> bool:
        """Mark session as failed"""
        return self.transition(
            session_id,
            SessionEvent.ERROR,
            {"error": error}
        )

    def pause_session(self, session_id: str) -> bool:
        """Pause a session"""
        return self.transition(session_id, SessionEvent.PAUSE)

    def resume_session(self, session_id: str) -> bool:
        """Resume a paused session"""
        return self.transition(session_id, SessionEvent.RESUME)

    # ==================== PR/CI Integration ====================

    def update_pr_status(
        self,
        session_id: str,
        pr_url: str,
        ci_status: str = None
    ):
        """Update PR and CI status for a session"""
        session = self.get_session(session_id)
        if session:
            session.pr_url = pr_url
            session.ci_status = ci_status
            session.updated_at = datetime.utcnow()
            self._persist_session(session)
            self._emit("pr_updated", session)

    def update_summary(self, session_id: str, summary: str):
        """Update AI-generated summary"""
        session = self.get_session(session_id)
        if session:
            session.summary = summary
            session.updated_at = datetime.utcnow()
            self._persist_session(session)

    # ==================== Worktree Integration ====================

    def attach_worktree(
        self,
        session_id: str,
        worktree_id: str,
        worktree_path: str,
        branch_name: str
    ):
        """Attach a worktree to a session"""
        session = self.get_session(session_id)
        if session:
            session.worktree_id = worktree_id
            session.worktree_path = worktree_path
            session.branch_name = branch_name
            session.updated_at = datetime.utcnow()
            self._persist_session(session)
            self._emit("worktree_attached", session)

    def detach_worktree(self, session_id: str):
        """Detach worktree from a session"""
        session = self.get_session(session_id)
        if session:
            session.worktree_id = None
            session.worktree_path = None
            session.branch_name = None
            session.updated_at = datetime.utcnow()
            self._persist_session(session)
            self._emit("worktree_detached", session)

    def set_result(self, session_id: str, result: Dict[str, Any]):
        """Set the session result"""
        session = self.get_session(session_id)
        if session:
            session.result = result
            session.updated_at = datetime.utcnow()
            self._persist_session(session)

    def set_error(self, session_id: str, error: str):
        """Set the session error message"""
        session = self.get_session(session_id)
        if session:
            session.error = error
            session.updated_at = datetime.utcnow()
            self._persist_session(session)

    # ==================== Event Listeners ====================

    def on(self, event: str, callback: Callable):
        """Register an event listener"""
        self._listeners[event].append(callback)

    def off(self, event: str, callback: Callable):
        """Remove an event listener"""
        if callback in self._listeners[event]:
            self._listeners[event].remove(callback)

    def _emit(self, event: str, *args):
        """Emit an event to all listeners"""
        for callback in self._listeners[event]:
            try:
                callback(*args)
            except Exception as e:
                api_logger.error(f"Event listener error: {e}")

        # Also publish to message bus
        try:
            bus = get_message_bus()
            asyncio.create_task(bus.publish(
                f"session.{event}",
                {"args": [self._session_to_dict(a) if isinstance(a, Session) else a for a in args]}
            ))
        except Exception:
            pass

    # ==================== Persistence ====================

    def _persist_session(self, session: Session):
        """Save session to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO session_states
                    (session_id, project_id, goal, state, agent_type,
                     created_at, updated_at, context, pr_url, ci_status, summary,
                     worktree_id, worktree_path, branch_name, result, error)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.session_id,
                    session.project_id,
                    session.goal,
                    session.state.value,
                    session.agent_type,
                    session.created_at.isoformat(),
                    session.updated_at.isoformat(),
                    json.dumps(session.context),
                    session.pr_url,
                    session.ci_status,
                    session.summary,
                    session.worktree_id,
                    session.worktree_path,
                    session.branch_name,
                    json.dumps(session.result) if session.result else None,
                    session.error
                ))
        except Exception as e:
            api_logger.error(f"Failed to persist session: {e}")

    def _persist_transition(self, session_id: str, transition: StateTransition):
        """Save transition to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO session_transitions
                    (session_id, from_state, to_state, event, timestamp, metadata)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (
                    session_id,
                    transition.from_state.value,
                    transition.to_state.value,
                    transition.event.value,
                    transition.timestamp.isoformat(),
                    json.dumps(transition.metadata)
                ))
        except Exception as e:
            api_logger.error(f"Failed to persist transition: {e}")

    def _load_session(self, session_id: str) -> Optional[Session]:
        """Load session from database"""
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM session_states WHERE session_id = ?",
                    (session_id,)
                ).fetchone()

                if row:
                    session = Session(
                        session_id=row["session_id"],
                        project_id=row["project_id"],
                        goal=row["goal"],
                        state=SessionState(row["state"]),
                        agent_type=row["agent_type"],
                        created_at=datetime.fromisoformat(row["created_at"]),
                        updated_at=datetime.fromisoformat(row["updated_at"]),
                        context=json.loads(row["context"]) if row["context"] else {},
                        pr_url=row["pr_url"],
                        ci_status=row["ci_status"],
                        summary=row["summary"],
                        worktree_id=row["worktree_id"] if "worktree_id" in row.keys() else None,
                        worktree_path=row["worktree_path"] if "worktree_path" in row.keys() else None,
                        branch_name=row["branch_name"] if "branch_name" in row.keys() else None,
                        result=json.loads(row["result"]) if ("result" in row.keys() and row["result"]) else None,
                        error=row["error"] if "error" in row.keys() else None
                    )
                    self._sessions[session_id] = session
                    return session
        except Exception as e:
            api_logger.error(f"Failed to load session: {e}")

        return None

    def _session_to_dict(self, session: Session) -> Dict[str, Any]:
        """Convert session to dictionary"""
        return {
            "session_id": session.session_id,
            "project_id": session.project_id,
            "goal": session.goal,
            "state": session.state.value,
            "kanban_column": session.kanban_column,
            "agent_type": session.agent_type,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "duration_seconds": session.duration.total_seconds(),
            "pr_url": session.pr_url,
            "ci_status": session.ci_status,
            "summary": session.summary,
            "context": session.context,
            "worktree_id": session.worktree_id,
            "worktree_path": session.worktree_path,
            "branch_name": session.branch_name,
            "result": session.result,
            "error": session.error
        }

    def load_all_sessions(self):
        """Load all sessions from database"""
        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT session_id FROM session_states"
                ).fetchall()

                for row in rows:
                    self._load_session(row["session_id"])
        except Exception as e:
            api_logger.error(f"Failed to load sessions: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """Get session statistics"""
        states = defaultdict(int)
        for session in self._sessions.values():
            states[session.state.value] += 1

        return {
            "total_sessions": len(self._sessions),
            "by_state": dict(states),
            "active": states[SessionState.WORKING.value] +
                     states[SessionState.WAITING_FOR_APPROVAL.value] +
                     states[SessionState.WAITING_FOR_INPUT.value]
        }


# Global instance
_state_machine: Optional[SessionStateMachine] = None


def get_session_state_machine() -> SessionStateMachine:
    """Get the global SessionStateMachine instance"""
    global _state_machine
    if _state_machine is None:
        _state_machine = SessionStateMachine()
        _state_machine.load_all_sessions()
    return _state_machine
