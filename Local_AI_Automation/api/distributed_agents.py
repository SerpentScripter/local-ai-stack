"""
Distributed Agent Support
Enables agents to run across multiple nodes with coordination

Features:
- Node registration and discovery
- Work distribution and load balancing
- Distributed task queue
- Agent migration
- Health monitoring
- Gossip protocol for state sync
"""
import json
import asyncio
import socket
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .database import get_db
from .logging_config import api_logger
from .message_bus import get_message_bus


class NodeStatus(Enum):
    """Status of a distributed node"""
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    DRAINING = "draining"  # Not accepting new work, finishing current


class LoadBalanceStrategy(Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    RANDOM = "random"
    CAPABILITY_MATCH = "capability_match"


@dataclass
class WorkerNode:
    """Represents a worker node in the distributed system"""
    node_id: str
    hostname: str
    address: str
    port: int
    status: NodeStatus = NodeStatus.ONLINE
    capabilities: Set[str] = field(default_factory=set)
    current_load: int = 0
    max_capacity: int = 5
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def available_capacity(self) -> int:
        return max(0, self.max_capacity - self.current_load)

    @property
    def is_available(self) -> bool:
        return (
            self.status == NodeStatus.ONLINE and
            self.available_capacity > 0 and
            (datetime.utcnow() - self.last_heartbeat).seconds < 60
        )


@dataclass
class DistributedTask:
    """A task distributed across nodes"""
    task_id: str
    task_type: str
    payload: Dict[str, Any]
    assigned_node: Optional[str] = None
    status: str = "pending"
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    retries: int = 0
    max_retries: int = 3


class DistributedAgentCoordinator:
    """
    Coordinator for distributed agent execution

    Manages:
    - Node registration and discovery
    - Task distribution
    - Load balancing
    - Failure recovery
    - State synchronization
    """

    def __init__(self):
        self._nodes: Dict[str, WorkerNode] = {}
        self._tasks: Dict[str, DistributedTask] = {}
        self._task_queue: List[str] = []
        self._strategy = LoadBalanceStrategy.LEAST_LOADED
        self._local_node_id = f"node_{uuid.uuid4().hex[:8]}"
        self._running = False
        self._init_database()

    def _init_database(self):
        """Initialize distributed coordination tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS distributed_nodes (
                        node_id TEXT PRIMARY KEY,
                        hostname TEXT NOT NULL,
                        address TEXT NOT NULL,
                        port INTEGER NOT NULL,
                        status TEXT DEFAULT 'online',
                        capabilities TEXT,
                        current_load INTEGER DEFAULT 0,
                        max_capacity INTEGER DEFAULT 5,
                        last_heartbeat TEXT,
                        metadata TEXT
                    );

                    CREATE TABLE IF NOT EXISTS distributed_tasks (
                        task_id TEXT PRIMARY KEY,
                        task_type TEXT NOT NULL,
                        payload TEXT NOT NULL,
                        assigned_node TEXT,
                        status TEXT DEFAULT 'pending',
                        created_at TEXT NOT NULL,
                        started_at TEXT,
                        completed_at TEXT,
                        result TEXT,
                        retries INTEGER DEFAULT 0
                    );

                    CREATE INDEX IF NOT EXISTS idx_dist_tasks_status
                    ON distributed_tasks(status);

                    CREATE INDEX IF NOT EXISTS idx_dist_tasks_node
                    ON distributed_tasks(assigned_node);
                """)
        except Exception as e:
            api_logger.error(f"Failed to init distributed tables: {e}")

    # ==================== Node Management ====================

    def register_node(
        self,
        hostname: str,
        address: str,
        port: int,
        capabilities: Set[str] = None,
        max_capacity: int = 5
    ) -> WorkerNode:
        """Register a new worker node"""
        node_id = f"node_{uuid.uuid4().hex[:8]}"

        node = WorkerNode(
            node_id=node_id,
            hostname=hostname,
            address=address,
            port=port,
            capabilities=capabilities or set(),
            max_capacity=max_capacity
        )

        self._nodes[node_id] = node
        self._persist_node(node)

        api_logger.info(f"Registered node {node_id} at {address}:{port}")
        return node

    def register_local_node(
        self,
        capabilities: Set[str] = None,
        max_capacity: int = 5
    ) -> WorkerNode:
        """Register the local node"""
        hostname = socket.gethostname()
        address = "127.0.0.1"
        port = 8765

        node = WorkerNode(
            node_id=self._local_node_id,
            hostname=hostname,
            address=address,
            port=port,
            capabilities=capabilities or {"research", "code", "chat"},
            max_capacity=max_capacity
        )

        self._nodes[self._local_node_id] = node
        self._persist_node(node)

        return node

    def deregister_node(self, node_id: str) -> bool:
        """Remove a node from the cluster"""
        if node_id not in self._nodes:
            return False

        node = self._nodes[node_id]
        node.status = NodeStatus.DRAINING

        # Reassign tasks from this node
        self._reassign_node_tasks(node_id)

        del self._nodes[node_id]

        try:
            with get_db() as conn:
                conn.execute(
                    "DELETE FROM distributed_nodes WHERE node_id = ?",
                    (node_id,)
                )
        except Exception:
            pass

        return True

    def update_heartbeat(self, node_id: str, load: int = None) -> bool:
        """Update node heartbeat"""
        if node_id not in self._nodes:
            return False

        node = self._nodes[node_id]
        node.last_heartbeat = datetime.utcnow()

        if load is not None:
            node.current_load = load

        self._persist_node(node)
        return True

    def get_nodes(self, status: NodeStatus = None) -> List[WorkerNode]:
        """Get all nodes, optionally filtered by status"""
        nodes = list(self._nodes.values())
        if status:
            nodes = [n for n in nodes if n.status == status]
        return nodes

    def get_available_nodes(self, capability: str = None) -> List[WorkerNode]:
        """Get nodes available for work"""
        nodes = [n for n in self._nodes.values() if n.is_available]

        if capability:
            nodes = [n for n in nodes if capability in n.capabilities]

        return nodes

    def _persist_node(self, node: WorkerNode):
        """Persist node to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO distributed_nodes
                    (node_id, hostname, address, port, status, capabilities,
                     current_load, max_capacity, last_heartbeat, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node.node_id,
                    node.hostname,
                    node.address,
                    node.port,
                    node.status.value,
                    json.dumps(list(node.capabilities)),
                    node.current_load,
                    node.max_capacity,
                    node.last_heartbeat.isoformat(),
                    json.dumps(node.metadata)
                ))
        except Exception as e:
            api_logger.error(f"Failed to persist node: {e}")

    # ==================== Task Distribution ====================

    async def submit_task(
        self,
        task_type: str,
        payload: Dict[str, Any],
        required_capability: str = None
    ) -> DistributedTask:
        """Submit a task for distributed execution"""
        task_id = f"dtask_{uuid.uuid4().hex[:12]}"

        task = DistributedTask(
            task_id=task_id,
            task_type=task_type,
            payload=payload
        )

        self._tasks[task_id] = task
        self._persist_task(task)

        # Try to assign immediately
        assigned = await self._assign_task(task, required_capability)

        if not assigned:
            # Add to queue for later assignment
            self._task_queue.append(task_id)

        return task

    async def _assign_task(
        self,
        task: DistributedTask,
        required_capability: str = None
    ) -> bool:
        """Assign a task to an available node"""
        available = self.get_available_nodes(required_capability)

        if not available:
            return False

        # Select node based on strategy
        node = self._select_node(available)

        if not node:
            return False

        task.assigned_node = node.node_id
        task.status = "assigned"
        node.current_load += 1

        self._persist_task(task)
        self._persist_node(node)

        # Send task to node
        await self._send_task_to_node(task, node)

        return True

    def _select_node(self, available: List[WorkerNode]) -> Optional[WorkerNode]:
        """Select a node based on load balancing strategy"""
        if not available:
            return None

        if self._strategy == LoadBalanceStrategy.ROUND_ROBIN:
            # Simple round robin using modulo
            idx = len(self._tasks) % len(available)
            return available[idx]

        elif self._strategy == LoadBalanceStrategy.LEAST_LOADED:
            # Select node with most available capacity
            return max(available, key=lambda n: n.available_capacity)

        elif self._strategy == LoadBalanceStrategy.RANDOM:
            import random
            return random.choice(available)

        elif self._strategy == LoadBalanceStrategy.CAPABILITY_MATCH:
            # Already filtered by capability, pick least loaded
            return max(available, key=lambda n: n.available_capacity)

        return available[0]

    async def _send_task_to_node(self, task: DistributedTask, node: WorkerNode):
        """Send task to a worker node for execution"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"http://{node.address}:{node.port}/distributed/execute",
                    json={
                        "task_id": task.task_id,
                        "task_type": task.task_type,
                        "payload": task.payload
                    }
                )

                if response.status_code == 200:
                    task.status = "running"
                    task.started_at = datetime.utcnow()
                    self._persist_task(task)
                else:
                    # Failed to send, mark for retry
                    await self._handle_task_failure(task, "Failed to send to node")

        except Exception as e:
            api_logger.error(f"Failed to send task to node: {e}")
            await self._handle_task_failure(task, str(e))

    async def _handle_task_failure(self, task: DistributedTask, error: str):
        """Handle task execution failure"""
        task.retries += 1

        if task.retries < task.max_retries:
            # Reset for retry
            task.status = "pending"
            task.assigned_node = None

            if task.assigned_node and task.assigned_node in self._nodes:
                self._nodes[task.assigned_node].current_load -= 1

            # Re-queue
            self._task_queue.append(task.task_id)

        else:
            # Max retries exceeded
            task.status = "failed"
            task.result = {"error": error}
            task.completed_at = datetime.utcnow()

        self._persist_task(task)

    def complete_task(
        self,
        task_id: str,
        result: Dict[str, Any],
        success: bool = True
    ):
        """Mark a task as completed"""
        if task_id not in self._tasks:
            return

        task = self._tasks[task_id]
        task.status = "completed" if success else "failed"
        task.result = result
        task.completed_at = datetime.utcnow()

        # Free up node capacity
        if task.assigned_node and task.assigned_node in self._nodes:
            self._nodes[task.assigned_node].current_load -= 1
            self._persist_node(self._nodes[task.assigned_node])

        self._persist_task(task)

    def _reassign_node_tasks(self, node_id: str):
        """Reassign all tasks from a node"""
        for task in self._tasks.values():
            if task.assigned_node == node_id and task.status in ("assigned", "running"):
                task.status = "pending"
                task.assigned_node = None
                self._task_queue.append(task.task_id)
                self._persist_task(task)

    def _persist_task(self, task: DistributedTask):
        """Persist task to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO distributed_tasks
                    (task_id, task_type, payload, assigned_node, status,
                     created_at, started_at, completed_at, result, retries)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    task.task_id,
                    task.task_type,
                    json.dumps(task.payload),
                    task.assigned_node,
                    task.status,
                    task.created_at.isoformat(),
                    task.started_at.isoformat() if task.started_at else None,
                    task.completed_at.isoformat() if task.completed_at else None,
                    json.dumps(task.result) if task.result else None,
                    task.retries
                ))
        except Exception as e:
            api_logger.error(f"Failed to persist task: {e}")

    # ==================== Background Processes ====================

    async def start(self):
        """Start the coordinator background processes"""
        self._running = True

        # Register local node
        self.register_local_node()

        # Start background tasks
        asyncio.create_task(self._heartbeat_loop())
        asyncio.create_task(self._queue_processor())
        asyncio.create_task(self._health_checker())

    async def stop(self):
        """Stop the coordinator"""
        self._running = False
        self.deregister_node(self._local_node_id)

    async def _heartbeat_loop(self):
        """Send periodic heartbeats"""
        while self._running:
            try:
                self.update_heartbeat(self._local_node_id)

                # Broadcast heartbeat via message bus
                bus = get_message_bus()
                await bus.publish("distributed.heartbeat", {
                    "node_id": self._local_node_id,
                    "timestamp": datetime.utcnow().isoformat()
                })

            except Exception as e:
                api_logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(15)

    async def _queue_processor(self):
        """Process queued tasks"""
        while self._running:
            try:
                if self._task_queue:
                    task_id = self._task_queue[0]
                    task = self._tasks.get(task_id)

                    if task and task.status == "pending":
                        assigned = await self._assign_task(task)
                        if assigned:
                            self._task_queue.pop(0)
                    else:
                        self._task_queue.pop(0)

            except Exception as e:
                api_logger.error(f"Queue processor error: {e}")

            await asyncio.sleep(1)

    async def _health_checker(self):
        """Check node health and handle failures"""
        while self._running:
            try:
                now = datetime.utcnow()
                timeout = timedelta(seconds=60)

                for node_id, node in list(self._nodes.items()):
                    if node_id == self._local_node_id:
                        continue

                    if (now - node.last_heartbeat) > timeout:
                        api_logger.warning(f"Node {node_id} is unresponsive")
                        node.status = NodeStatus.OFFLINE
                        self._reassign_node_tasks(node_id)

            except Exception as e:
                api_logger.error(f"Health checker error: {e}")

            await asyncio.sleep(30)

    # ==================== Queries ====================

    def get_task(self, task_id: str) -> Optional[DistributedTask]:
        """Get a task by ID"""
        return self._tasks.get(task_id)

    def get_tasks(
        self,
        status: str = None,
        node_id: str = None,
        limit: int = 100
    ) -> List[DistributedTask]:
        """Get tasks with optional filtering"""
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status == status]
        if node_id:
            tasks = [t for t in tasks if t.assigned_node == node_id]

        return tasks[:limit]

    def get_stats(self) -> Dict[str, Any]:
        """Get distributed system statistics"""
        nodes = list(self._nodes.values())
        tasks = list(self._tasks.values())

        online_nodes = len([n for n in nodes if n.status == NodeStatus.ONLINE])
        total_capacity = sum(n.max_capacity for n in nodes)
        used_capacity = sum(n.current_load for n in nodes)

        return {
            "nodes": {
                "total": len(nodes),
                "online": online_nodes,
                "total_capacity": total_capacity,
                "used_capacity": used_capacity
            },
            "tasks": {
                "total": len(tasks),
                "pending": len([t for t in tasks if t.status == "pending"]),
                "running": len([t for t in tasks if t.status == "running"]),
                "completed": len([t for t in tasks if t.status == "completed"]),
                "failed": len([t for t in tasks if t.status == "failed"]),
                "queued": len(self._task_queue)
            },
            "strategy": self._strategy.value,
            "local_node_id": self._local_node_id
        }


# Global coordinator instance
_coordinator: Optional[DistributedAgentCoordinator] = None


def get_distributed_coordinator() -> DistributedAgentCoordinator:
    """Get the global DistributedAgentCoordinator instance"""
    global _coordinator
    if _coordinator is None:
        _coordinator = DistributedAgentCoordinator()
    return _coordinator
