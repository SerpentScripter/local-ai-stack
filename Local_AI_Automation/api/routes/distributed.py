"""
Distributed Agent Routes
API endpoints for distributed agent coordination
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Set

from ..distributed_agents import get_distributed_coordinator, NodeStatus, LoadBalanceStrategy

router = APIRouter(prefix="/distributed", tags=["distributed"])


class RegisterNodeRequest(BaseModel):
    """Request to register a worker node"""
    hostname: str
    address: str
    port: int
    capabilities: List[str] = []
    max_capacity: int = 5


class SubmitTaskRequest(BaseModel):
    """Request to submit a distributed task"""
    task_type: str
    payload: dict
    required_capability: Optional[str] = None


class TaskResultRequest(BaseModel):
    """Request to report task completion"""
    task_id: str
    result: dict
    success: bool = True


class HeartbeatRequest(BaseModel):
    """Heartbeat update"""
    node_id: str
    current_load: Optional[int] = None


@router.get("/stats")
def get_distributed_stats():
    """Get distributed system statistics"""
    coordinator = get_distributed_coordinator()
    return coordinator.get_stats()


@router.post("/nodes/register")
def register_node(request: RegisterNodeRequest):
    """Register a new worker node"""
    coordinator = get_distributed_coordinator()

    node = coordinator.register_node(
        hostname=request.hostname,
        address=request.address,
        port=request.port,
        capabilities=set(request.capabilities),
        max_capacity=request.max_capacity
    )

    return {
        "node_id": node.node_id,
        "status": node.status.value,
        "message": "Node registered successfully"
    }


@router.post("/nodes/register-local")
def register_local_node(
    capabilities: List[str] = ["research", "code", "chat"],
    max_capacity: int = 5
):
    """Register the local node"""
    coordinator = get_distributed_coordinator()

    node = coordinator.register_local_node(
        capabilities=set(capabilities),
        max_capacity=max_capacity
    )

    return {
        "node_id": node.node_id,
        "hostname": node.hostname,
        "status": node.status.value
    }


@router.delete("/nodes/{node_id}")
def deregister_node(node_id: str):
    """Remove a node from the cluster"""
    coordinator = get_distributed_coordinator()

    success = coordinator.deregister_node(node_id)

    if not success:
        raise HTTPException(status_code=404, detail="Node not found")

    return {"status": "deregistered", "node_id": node_id}


@router.post("/nodes/heartbeat")
def send_heartbeat(request: HeartbeatRequest):
    """Send a heartbeat update"""
    coordinator = get_distributed_coordinator()

    success = coordinator.update_heartbeat(
        node_id=request.node_id,
        load=request.current_load
    )

    if not success:
        raise HTTPException(status_code=404, detail="Node not found")

    return {"status": "ok"}


@router.get("/nodes")
def list_nodes(status: Optional[str] = None):
    """List all registered nodes"""
    coordinator = get_distributed_coordinator()

    node_status = None
    if status:
        try:
            node_status = NodeStatus(status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    nodes = coordinator.get_nodes(node_status)

    return [
        {
            "node_id": n.node_id,
            "hostname": n.hostname,
            "address": n.address,
            "port": n.port,
            "status": n.status.value,
            "capabilities": list(n.capabilities),
            "current_load": n.current_load,
            "max_capacity": n.max_capacity,
            "available_capacity": n.available_capacity,
            "last_heartbeat": n.last_heartbeat.isoformat()
        }
        for n in nodes
    ]


@router.get("/nodes/available")
def list_available_nodes(capability: Optional[str] = None):
    """List nodes available for work"""
    coordinator = get_distributed_coordinator()
    nodes = coordinator.get_available_nodes(capability)

    return [
        {
            "node_id": n.node_id,
            "hostname": n.hostname,
            "available_capacity": n.available_capacity,
            "capabilities": list(n.capabilities)
        }
        for n in nodes
    ]


@router.post("/tasks/submit")
async def submit_task(request: SubmitTaskRequest):
    """Submit a task for distributed execution"""
    coordinator = get_distributed_coordinator()

    task = await coordinator.submit_task(
        task_type=request.task_type,
        payload=request.payload,
        required_capability=request.required_capability
    )

    return {
        "task_id": task.task_id,
        "status": task.status,
        "assigned_node": task.assigned_node,
        "queued": task.assigned_node is None
    }


@router.post("/tasks/complete")
def complete_task(request: TaskResultRequest):
    """Report task completion"""
    coordinator = get_distributed_coordinator()

    task = coordinator.get_task(request.task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    coordinator.complete_task(
        task_id=request.task_id,
        result=request.result,
        success=request.success
    )

    return {"status": "completed", "task_id": request.task_id}


@router.get("/tasks")
def list_tasks(
    status: Optional[str] = None,
    node_id: Optional[str] = None,
    limit: int = 100
):
    """List distributed tasks"""
    coordinator = get_distributed_coordinator()
    tasks = coordinator.get_tasks(status, node_id, limit)

    return [
        {
            "task_id": t.task_id,
            "task_type": t.task_type,
            "status": t.status,
            "assigned_node": t.assigned_node,
            "created_at": t.created_at.isoformat(),
            "started_at": t.started_at.isoformat() if t.started_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
            "retries": t.retries
        }
        for t in tasks
    ]


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    """Get task details"""
    coordinator = get_distributed_coordinator()
    task = coordinator.get_task(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    return {
        "task_id": task.task_id,
        "task_type": task.task_type,
        "payload": task.payload,
        "status": task.status,
        "assigned_node": task.assigned_node,
        "created_at": task.created_at.isoformat(),
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "result": task.result,
        "retries": task.retries
    }


@router.post("/execute")
async def execute_task(task_id: str, task_type: str, payload: dict):
    """
    Execute a task on this node

    This endpoint is called by the coordinator to run a task locally.
    """
    # This would integrate with the local agent system
    # For now, acknowledge receipt

    coordinator = get_distributed_coordinator()

    # TODO: Actually execute the task via orchestrator
    # from ..orchestrator import get_orchestrator
    # orchestrator = get_orchestrator()
    # await orchestrator.execute(task_type, payload)

    return {"status": "accepted", "task_id": task_id}


@router.post("/start")
async def start_coordinator(background_tasks: BackgroundTasks):
    """Start the distributed coordinator"""
    coordinator = get_distributed_coordinator()

    async def start():
        await coordinator.start()

    background_tasks.add_task(start)

    return {"status": "starting"}


@router.post("/stop")
async def stop_coordinator():
    """Stop the distributed coordinator"""
    coordinator = get_distributed_coordinator()
    await coordinator.stop()

    return {"status": "stopped"}


@router.put("/strategy")
def set_load_balance_strategy(strategy: str):
    """Set the load balancing strategy"""
    coordinator = get_distributed_coordinator()

    try:
        new_strategy = LoadBalanceStrategy(strategy)
    except ValueError:
        valid = [s.value for s in LoadBalanceStrategy]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Valid options: {valid}"
        )

    coordinator._strategy = new_strategy

    return {"strategy": new_strategy.value}
