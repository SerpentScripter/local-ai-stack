"""
Agent Base Class
Abstract base class for all agents with lifecycle hooks and common functionality
"""
import os
import uuid
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field

from .database import get_db
from .logging_config import log_agent_event


class AgentStatus(Enum):
    """Agent execution status"""
    PENDING = "pending"
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentContext:
    """Context passed to agent during execution"""
    session_id: str
    goal: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    memory: Dict[str, Any] = field(default_factory=dict)
    start_time: datetime = field(default_factory=datetime.utcnow)
    max_iterations: int = 100
    timeout_seconds: int = 600  # 10 minutes default


@dataclass
class AgentResult:
    """Result returned by agent execution"""
    success: bool
    output: Any
    error: Optional[str] = None
    iterations: int = 0
    duration_seconds: float = 0
    artifacts: List[Dict[str, Any]] = field(default_factory=list)


class BaseAgent(ABC):
    """
    Abstract base class for all agents

    Provides:
    - Lifecycle hooks (on_start, on_complete, on_error, on_cancel)
    - State management
    - Logging integration
    - Memory persistence
    - Graceful cancellation
    """

    def __init__(self, agent_type: str):
        self.agent_type = agent_type
        self.session_id: Optional[str] = None
        self.status = AgentStatus.PENDING
        self.context: Optional[AgentContext] = None
        self._cancelled = False
        self._pause_event = asyncio.Event()
        self._pause_event.set()  # Not paused by default

    # ==================== Lifecycle Hooks ====================

    async def on_start(self, context: AgentContext) -> None:
        """
        Called when agent starts execution

        Override to perform initialization tasks like:
        - Loading resources
        - Connecting to services
        - Validating parameters
        """
        log_agent_event(self.agent_type, "started", self.session_id, {
            "goal": context.goal,
            "parameters": context.parameters
        })

    async def on_complete(self, result: AgentResult) -> None:
        """
        Called when agent completes successfully

        Override to perform cleanup or post-processing like:
        - Saving final results
        - Sending notifications
        - Releasing resources
        """
        log_agent_event(self.agent_type, "completed", self.session_id, {
            "success": result.success,
            "iterations": result.iterations,
            "duration_seconds": result.duration_seconds
        })

    async def on_error(self, error: Exception) -> None:
        """
        Called when agent encounters an error

        Override to handle errors like:
        - Logging detailed error info
        - Attempting recovery
        - Sending alerts
        """
        log_agent_event(self.agent_type, "error", self.session_id, {
            "error": str(error),
            "error_type": type(error).__name__
        })

    async def on_cancel(self) -> None:
        """
        Called when agent is cancelled

        Override to handle cancellation like:
        - Saving partial results
        - Cleaning up resources
        - Notifying dependents
        """
        log_agent_event(self.agent_type, "cancelled", self.session_id)

    async def on_iteration(self, iteration: int, state: Dict[str, Any]) -> None:
        """
        Called at the start of each iteration

        Override to:
        - Log progress
        - Update UI
        - Check for external signals
        """
        pass

    # ==================== Abstract Methods ====================

    @abstractmethod
    async def execute(self, context: AgentContext) -> AgentResult:
        """
        Main execution logic - must be implemented by subclasses

        Args:
            context: Execution context with goal, parameters, and memory

        Returns:
            AgentResult with output and metadata
        """
        pass

    # ==================== Public Methods ====================

    async def run(self, goal: str, parameters: Dict[str, Any] = None) -> AgentResult:
        """
        Run the agent with lifecycle management

        Args:
            goal: The goal/task for the agent to accomplish
            parameters: Optional parameters for the agent

        Returns:
            AgentResult with execution outcome
        """
        # Generate session ID
        self.session_id = f"{self.agent_type}-{uuid.uuid4().hex[:8]}"

        # Create context
        self.context = AgentContext(
            session_id=self.session_id,
            goal=goal,
            parameters=parameters or {}
        )

        # Record in database
        self._save_session_start()

        try:
            # Lifecycle: Start
            self.status = AgentStatus.INITIALIZING
            await self.on_start(self.context)

            # Execute
            self.status = AgentStatus.RUNNING
            result = await self._execute_with_timeout()

            # Lifecycle: Complete
            self.status = AgentStatus.COMPLETED
            await self.on_complete(result)

            # Save result
            self._save_session_end(result)

            return result

        except asyncio.CancelledError:
            self.status = AgentStatus.CANCELLED
            await self.on_cancel()
            result = AgentResult(success=False, output=None, error="Cancelled")
            self._save_session_end(result)
            return result

        except Exception as e:
            self.status = AgentStatus.FAILED
            await self.on_error(e)
            result = AgentResult(success=False, output=None, error=str(e))
            self._save_session_end(result)
            raise

    def cancel(self) -> None:
        """Request cancellation of the agent"""
        self._cancelled = True
        log_agent_event(self.agent_type, "cancel_requested", self.session_id)

    def pause(self) -> None:
        """Pause agent execution"""
        self._pause_event.clear()
        self.status = AgentStatus.PAUSED
        log_agent_event(self.agent_type, "paused", self.session_id)

    def resume(self) -> None:
        """Resume agent execution"""
        self._pause_event.set()
        self.status = AgentStatus.RUNNING
        log_agent_event(self.agent_type, "resumed", self.session_id)

    async def wait_if_paused(self) -> None:
        """Wait if agent is paused - call this in iteration loops"""
        await self._pause_event.wait()

    def is_cancelled(self) -> bool:
        """Check if cancellation was requested"""
        return self._cancelled

    # ==================== Memory Management ====================

    def remember(self, key: str, value: Any) -> None:
        """Store a value in agent memory"""
        if self.context:
            self.context.memory[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        """Retrieve a value from agent memory"""
        if self.context:
            return self.context.memory.get(key, default)
        return default

    # ==================== Private Methods ====================

    async def _execute_with_timeout(self) -> AgentResult:
        """Execute with timeout handling"""
        try:
            return await asyncio.wait_for(
                self.execute(self.context),
                timeout=self.context.timeout_seconds
            )
        except asyncio.TimeoutError:
            log_agent_event(self.agent_type, "timeout", self.session_id, {
                "timeout_seconds": self.context.timeout_seconds
            })
            return AgentResult(
                success=False,
                output=None,
                error=f"Execution timeout after {self.context.timeout_seconds} seconds"
            )

    def _save_session_start(self) -> None:
        """Save session start to database"""
        try:
            with get_db() as conn:
                # Check if research_sessions table exists and use appropriate table
                conn.execute(
                    """INSERT OR IGNORE INTO research_sessions
                       (id, goal, status, start_time)
                       VALUES (?, ?, ?, ?)""",
                    (self.session_id, self.context.goal, self.status.value,
                     self.context.start_time.isoformat())
                )
        except Exception:
            pass  # Table might not exist yet

    def _save_session_end(self, result: AgentResult) -> None:
        """Save session end to database"""
        try:
            with get_db() as conn:
                conn.execute(
                    """UPDATE research_sessions
                       SET status = ?, end_time = ?, knowledge_graph = ?
                       WHERE id = ?""",
                    (self.status.value, datetime.utcnow().isoformat(),
                     str(result.output) if result.output else None,
                     self.session_id)
                )
        except Exception:
            pass  # Table might not exist yet


class ToolMixin:
    """
    Mixin class providing tool capabilities for agents

    Tools are functions that agents can call to interact with
    external systems (web search, file operations, API calls, etc.)
    """

    def __init__(self):
        self._tools: Dict[str, callable] = {}

    def register_tool(self, name: str, func: callable, description: str = "") -> None:
        """Register a tool for the agent to use"""
        self._tools[name] = {
            "func": func,
            "description": description
        }

    async def use_tool(self, name: str, **kwargs) -> Any:
        """Use a registered tool"""
        if name not in self._tools:
            raise ValueError(f"Unknown tool: {name}")

        tool = self._tools[name]
        func = tool["func"]

        if asyncio.iscoroutinefunction(func):
            return await func(**kwargs)
        return func(**kwargs)

    def list_tools(self) -> List[Dict[str, str]]:
        """List available tools"""
        return [
            {"name": name, "description": tool["description"]}
            for name, tool in self._tools.items()
        ]


class ToolAgent(BaseAgent, ToolMixin):
    """
    Agent with tool capabilities

    Combines BaseAgent lifecycle management with ToolMixin
    for agents that need to call external tools.
    """

    def __init__(self, agent_type: str):
        BaseAgent.__init__(self, agent_type)
        ToolMixin.__init__(self)
