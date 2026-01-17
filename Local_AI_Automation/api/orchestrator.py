"""
Agent Orchestrator
Central coordinator for multi-agent systems with supervisor pattern

Provides:
- Agent lifecycle management (spawn, monitor, restart)
- Fault tolerance with automatic recovery
- Task distribution and load balancing
- Result aggregation
- Execution coordination
"""
import asyncio
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, List, Callable, Type
from dataclasses import dataclass, field
from collections import defaultdict

from .agent_base import BaseAgent, AgentContext, AgentResult, AgentStatus
from .logging_config import api_logger, log_agent_event
from .job_queue import get_job_queue, JobPriority


class SupervisorStrategy(Enum):
    """Strategies for handling agent failures"""
    ONE_FOR_ONE = "one_for_one"      # Restart only the failed agent
    ONE_FOR_ALL = "one_for_all"      # Restart all agents in group
    REST_FOR_ONE = "rest_for_one"    # Restart failed + agents started after it
    ESCALATE = "escalate"            # Escalate to parent supervisor


@dataclass
class AgentSpec:
    """Specification for an agent to be managed"""
    agent_id: str
    agent_class: Type[BaseAgent]
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    restart_policy: str = "always"  # always, on_failure, never
    max_restarts: int = 3
    restart_window: int = 60  # seconds


@dataclass
class AgentState:
    """Runtime state of a managed agent"""
    spec: AgentSpec
    instance: Optional[BaseAgent] = None
    task: Optional[asyncio.Task] = None
    status: AgentStatus = AgentStatus.PENDING
    started_at: Optional[datetime] = None
    restarts: int = 0
    last_restart: Optional[datetime] = None
    last_error: Optional[str] = None
    result: Optional[AgentResult] = None


@dataclass
class OrchestratorConfig:
    """Configuration for the orchestrator"""
    max_concurrent_agents: int = 10
    default_timeout: int = 600  # 10 minutes
    health_check_interval: int = 30  # seconds
    supervisor_strategy: SupervisorStrategy = SupervisorStrategy.ONE_FOR_ONE
    enable_auto_recovery: bool = True


class Orchestrator:
    """
    Central orchestrator for managing multiple agents

    Implements the supervisor pattern for fault tolerance:
    - Monitors agent health
    - Automatically restarts failed agents
    - Coordinates task execution
    - Aggregates results
    """

    def __init__(self, config: Optional[OrchestratorConfig] = None):
        self.config = config or OrchestratorConfig()
        self._agents: Dict[str, AgentState] = {}
        self._groups: Dict[str, List[str]] = defaultdict(list)
        self._running = False
        self._health_check_task: Optional[asyncio.Task] = None
        self._event_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_agents)

    # ==================== Agent Management ====================

    def register_agent(
        self,
        agent_class: Type[BaseAgent],
        agent_id: Optional[str] = None,
        group: Optional[str] = None,
        restart_policy: str = "always",
        max_restarts: int = 3,
        **kwargs
    ) -> str:
        """
        Register an agent with the orchestrator

        Args:
            agent_class: The agent class to instantiate
            agent_id: Optional custom ID (auto-generated if not provided)
            group: Optional group name for related agents
            restart_policy: When to restart (always, on_failure, never)
            max_restarts: Maximum restart attempts
            **kwargs: Arguments passed to agent constructor

        Returns:
            Agent ID string
        """
        agent_id = agent_id or f"agent-{uuid.uuid4().hex[:8]}"

        spec = AgentSpec(
            agent_id=agent_id,
            agent_class=agent_class,
            kwargs=kwargs,
            restart_policy=restart_policy,
            max_restarts=max_restarts
        )

        self._agents[agent_id] = AgentState(spec=spec)

        if group:
            self._groups[group].append(agent_id)

        log_agent_event("orchestrator", "agent_registered", agent_id, {
            "class": agent_class.__name__,
            "group": group,
            "restart_policy": restart_policy
        })

        return agent_id

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the orchestrator"""
        if agent_id not in self._agents:
            return False

        state = self._agents[agent_id]

        # Cancel if running
        if state.task and not state.task.done():
            state.task.cancel()

        # Remove from groups
        for group_agents in self._groups.values():
            if agent_id in group_agents:
                group_agents.remove(agent_id)

        del self._agents[agent_id]

        log_agent_event("orchestrator", "agent_unregistered", agent_id)
        return True

    async def start_agent(
        self,
        agent_id: str,
        goal: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Start a registered agent

        Args:
            agent_id: The agent ID to start
            goal: The goal/task for the agent
            parameters: Optional parameters

        Returns:
            True if started successfully
        """
        if agent_id not in self._agents:
            raise ValueError(f"Unknown agent: {agent_id}")

        state = self._agents[agent_id]

        # Check if already running
        if state.task and not state.task.done():
            api_logger.warning(f"Agent {agent_id} is already running")
            return False

        # Instantiate agent
        spec = state.spec
        state.instance = spec.agent_class(*spec.args, **spec.kwargs)

        # Create execution task
        async def run_with_supervision():
            async with self._semaphore:
                try:
                    state.status = AgentStatus.RUNNING
                    state.started_at = datetime.utcnow()
                    await self._emit_event("agent_started", agent_id, state)

                    result = await state.instance.run(goal, parameters)
                    state.result = result
                    state.status = AgentStatus.COMPLETED

                    await self._emit_event("agent_completed", agent_id, state, result)
                    return result

                except asyncio.CancelledError:
                    state.status = AgentStatus.CANCELLED
                    await self._emit_event("agent_cancelled", agent_id, state)
                    raise

                except Exception as e:
                    state.status = AgentStatus.FAILED
                    state.last_error = str(e)
                    await self._emit_event("agent_failed", agent_id, state, error=e)

                    # Handle restart based on policy
                    if self.config.enable_auto_recovery:
                        await self._handle_failure(agent_id, goal, parameters)

                    raise

        state.task = asyncio.create_task(run_with_supervision())
        return True

    async def stop_agent(self, agent_id: str, graceful: bool = True) -> bool:
        """
        Stop a running agent

        Args:
            agent_id: The agent to stop
            graceful: If True, request cancellation; if False, force kill

        Returns:
            True if stopped
        """
        if agent_id not in self._agents:
            return False

        state = self._agents[agent_id]

        if not state.task or state.task.done():
            return False

        if graceful and state.instance:
            state.instance.cancel()
            # Give it time to clean up
            try:
                await asyncio.wait_for(state.task, timeout=5.0)
            except asyncio.TimeoutError:
                state.task.cancel()
        else:
            state.task.cancel()

        try:
            await state.task
        except asyncio.CancelledError:
            pass

        state.status = AgentStatus.CANCELLED
        return True

    async def pause_agent(self, agent_id: str) -> bool:
        """Pause a running agent"""
        if agent_id not in self._agents:
            return False

        state = self._agents[agent_id]
        if state.instance and state.status == AgentStatus.RUNNING:
            state.instance.pause()
            state.status = AgentStatus.PAUSED
            return True
        return False

    async def resume_agent(self, agent_id: str) -> bool:
        """Resume a paused agent"""
        if agent_id not in self._agents:
            return False

        state = self._agents[agent_id]
        if state.instance and state.status == AgentStatus.PAUSED:
            state.instance.resume()
            state.status = AgentStatus.RUNNING
            return True
        return False

    # ==================== Supervisor Pattern ====================

    async def _handle_failure(
        self,
        agent_id: str,
        goal: str,
        parameters: Optional[Dict[str, Any]]
    ):
        """Handle agent failure based on supervisor strategy"""
        state = self._agents[agent_id]
        spec = state.spec

        # Check restart policy
        if spec.restart_policy == "never":
            return

        if spec.restart_policy == "on_failure" and state.status != AgentStatus.FAILED:
            return

        # Check restart limits
        now = datetime.utcnow()
        if state.last_restart:
            window_start = now - timedelta(seconds=spec.restart_window)
            if state.last_restart > window_start:
                if state.restarts >= spec.max_restarts:
                    log_agent_event("orchestrator", "max_restarts_exceeded", agent_id, {
                        "restarts": state.restarts,
                        "max": spec.max_restarts
                    })
                    await self._emit_event("agent_max_restarts", agent_id, state)
                    return
            else:
                # Reset counter if outside window
                state.restarts = 0

        # Apply supervisor strategy
        if self.config.supervisor_strategy == SupervisorStrategy.ONE_FOR_ONE:
            await self._restart_agent(agent_id, goal, parameters)

        elif self.config.supervisor_strategy == SupervisorStrategy.ONE_FOR_ALL:
            # Find agent's group and restart all
            for group_name, agent_ids in self._groups.items():
                if agent_id in agent_ids:
                    for aid in agent_ids:
                        await self._restart_agent(aid, goal, parameters)
                    break
            else:
                # Not in a group, just restart this one
                await self._restart_agent(agent_id, goal, parameters)

        elif self.config.supervisor_strategy == SupervisorStrategy.ESCALATE:
            # Log and don't restart
            log_agent_event("orchestrator", "failure_escalated", agent_id, {
                "error": state.last_error
            })

    async def _restart_agent(
        self,
        agent_id: str,
        goal: str,
        parameters: Optional[Dict[str, Any]]
    ):
        """Restart a single agent"""
        state = self._agents[agent_id]

        # Update restart tracking
        state.restarts += 1
        state.last_restart = datetime.utcnow()

        log_agent_event("orchestrator", "restarting_agent", agent_id, {
            "attempt": state.restarts,
            "max": state.spec.max_restarts
        })

        # Small delay before restart
        await asyncio.sleep(min(state.restarts * 2, 30))

        # Restart
        await self.start_agent(agent_id, goal, parameters)

    # ==================== Health Monitoring ====================

    async def start(self):
        """Start the orchestrator"""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        log_agent_event("orchestrator", "started", None)

    async def stop(self):
        """Stop the orchestrator and all agents"""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Stop all agents
        for agent_id in list(self._agents.keys()):
            await self.stop_agent(agent_id, graceful=True)

        log_agent_event("orchestrator", "stopped", None)

    async def _health_check_loop(self):
        """Periodic health check of all agents"""
        while self._running:
            try:
                await asyncio.sleep(self.config.health_check_interval)

                for agent_id, state in list(self._agents.items()):
                    if state.task and state.task.done():
                        # Check for unhandled exceptions
                        try:
                            state.task.result()
                        except Exception as e:
                            if state.status not in (AgentStatus.FAILED, AgentStatus.CANCELLED):
                                state.status = AgentStatus.FAILED
                                state.last_error = str(e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                api_logger.error(f"Health check error: {e}")

    # ==================== Event System ====================

    def on(self, event: str, handler: Callable):
        """Register an event handler"""
        self._event_handlers[event].append(handler)

    def off(self, event: str, handler: Callable):
        """Unregister an event handler"""
        if handler in self._event_handlers[event]:
            self._event_handlers[event].remove(handler)

    async def _emit_event(self, event: str, agent_id: str, state: AgentState, **kwargs):
        """Emit an event to all registered handlers"""
        for handler in self._event_handlers[event]:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(agent_id, state, **kwargs)
                else:
                    handler(agent_id, state, **kwargs)
            except Exception as e:
                api_logger.error(f"Event handler error for {event}: {e}")

    # ==================== Query Methods ====================

    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed status of an agent"""
        if agent_id not in self._agents:
            return None

        state = self._agents[agent_id]
        return {
            "agent_id": agent_id,
            "class": state.spec.agent_class.__name__,
            "status": state.status.value,
            "started_at": state.started_at.isoformat() if state.started_at else None,
            "restarts": state.restarts,
            "last_error": state.last_error,
            "has_result": state.result is not None
        }

    def list_agents(self, group: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all registered agents"""
        if group:
            agent_ids = self._groups.get(group, [])
        else:
            agent_ids = list(self._agents.keys())

        return [self.get_agent_status(aid) for aid in agent_ids if aid in self._agents]

    def get_stats(self) -> Dict[str, Any]:
        """Get orchestrator statistics"""
        status_counts = defaultdict(int)
        for state in self._agents.values():
            status_counts[state.status.value] += 1

        return {
            "running": self._running,
            "total_agents": len(self._agents),
            "groups": len(self._groups),
            "by_status": dict(status_counts),
            "config": {
                "max_concurrent": self.config.max_concurrent_agents,
                "strategy": self.config.supervisor_strategy.value,
                "auto_recovery": self.config.enable_auto_recovery
            }
        }


# ==================== Coordination Patterns ====================

class AgentCoordinator:
    """
    Higher-level coordination patterns for multi-agent workflows

    Provides:
    - Parallel execution with result aggregation
    - Sequential pipelines
    - Map-reduce patterns
    - Voting/consensus
    """

    def __init__(self, orchestrator: Orchestrator):
        self.orchestrator = orchestrator

    async def run_parallel(
        self,
        agents: List[tuple],  # [(agent_class, goal, params), ...]
        timeout: Optional[int] = None
    ) -> List[AgentResult]:
        """
        Run multiple agents in parallel and collect results

        Args:
            agents: List of (agent_class, goal, parameters) tuples
            timeout: Optional timeout for all agents

        Returns:
            List of AgentResult in same order as input
        """
        agent_ids = []

        # Register and start all agents
        for agent_class, goal, params in agents:
            aid = self.orchestrator.register_agent(agent_class, restart_policy="never")
            agent_ids.append(aid)
            await self.orchestrator.start_agent(aid, goal, params)

        # Wait for all to complete
        results = []
        for aid in agent_ids:
            state = self.orchestrator._agents[aid]
            if state.task:
                try:
                    if timeout:
                        await asyncio.wait_for(state.task, timeout=timeout)
                    else:
                        await state.task
                except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                    pass

            results.append(state.result)

            # Cleanup
            self.orchestrator.unregister_agent(aid)

        return results

    async def run_pipeline(
        self,
        stages: List[tuple],  # [(agent_class, goal_template), ...]
        initial_input: Any
    ) -> AgentResult:
        """
        Run agents sequentially, passing output to next stage

        Args:
            stages: List of (agent_class, goal_template) - template uses {input}
            initial_input: Input for first stage

        Returns:
            Final AgentResult
        """
        current_input = initial_input
        final_result = None

        for agent_class, goal_template in stages:
            goal = goal_template.format(input=current_input)

            aid = self.orchestrator.register_agent(agent_class, restart_policy="never")
            await self.orchestrator.start_agent(aid, goal, {"input": current_input})

            state = self.orchestrator._agents[aid]
            if state.task:
                try:
                    await state.task
                except Exception:
                    pass

            final_result = state.result
            if final_result and final_result.success:
                current_input = final_result.output
            else:
                # Pipeline failed
                break

            self.orchestrator.unregister_agent(aid)

        return final_result

    async def run_map_reduce(
        self,
        map_agent_class: Type[BaseAgent],
        reduce_agent_class: Type[BaseAgent],
        items: List[Any],
        map_goal_template: str,
        reduce_goal: str
    ) -> AgentResult:
        """
        Map-reduce pattern: process items in parallel, then reduce

        Args:
            map_agent_class: Agent class for map phase
            reduce_agent_class: Agent class for reduce phase
            items: Items to process
            map_goal_template: Goal template for map (uses {item})
            reduce_goal: Goal for reduce phase

        Returns:
            Final reduced AgentResult
        """
        # Map phase - parallel
        map_tasks = [
            (map_agent_class, map_goal_template.format(item=item), {"item": item})
            for item in items
        ]
        map_results = await self.run_parallel(map_tasks)

        # Collect successful outputs
        outputs = [r.output for r in map_results if r and r.success]

        # Reduce phase
        aid = self.orchestrator.register_agent(reduce_agent_class, restart_policy="never")
        await self.orchestrator.start_agent(aid, reduce_goal, {"inputs": outputs})

        state = self.orchestrator._agents[aid]
        if state.task:
            try:
                await state.task
            except Exception:
                pass

        result = state.result
        self.orchestrator.unregister_agent(aid)

        return result


# Global orchestrator instance
_orchestrator: Optional[Orchestrator] = None


def get_orchestrator() -> Orchestrator:
    """Get the global Orchestrator instance"""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
