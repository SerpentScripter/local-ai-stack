"""
Pydantic models for the Local AI Hub API
"""
from typing import Optional, List
from pydantic import BaseModel
from datetime import datetime


class BacklogItemCreate(BaseModel):
    """Schema for creating a new backlog item"""
    title: str
    description: Optional[str] = None
    category: str = "Personal"
    priority: str = "P2"
    item_type: str = "personal"
    next_action: Optional[str] = None
    estimated_effort: Optional[str] = None
    source_channel: Optional[str] = None
    source_message_ts: Optional[str] = None
    source_user: Optional[str] = None
    raw_input: Optional[str] = None


class BacklogItemUpdate(BaseModel):
    """Schema for updating a backlog item"""
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    next_action: Optional[str] = None
    estimated_effort: Optional[str] = None


class BacklogItem(BaseModel):
    """Full backlog item response model"""
    id: int
    external_id: str
    title: str
    description: Optional[str]
    category: str
    priority: str
    item_type: str
    status: str
    next_action: Optional[str]
    estimated_effort: Optional[str]
    created_at: str
    updated_at: Optional[str]
    completed_at: Optional[str]


class ServiceInfo(BaseModel):
    """Service status information"""
    id: str
    name: str
    port: int
    type: str  # 'docker' or 'native'
    status: str  # 'running', 'stopped', 'unknown'
    health_url: Optional[str] = None
    container_name: Optional[str] = None


class ChatMessage(BaseModel):
    """Chat message model"""
    role: str  # 'user', 'assistant', 'system'
    content: str
    model: Optional[str] = None


class SystemMetrics(BaseModel):
    """System metrics snapshot"""
    cpu_percent: float
    memory_percent: float
    memory_used_gb: float
    disk_percent: float
    disk_used_gb: float
    gpu_percent: Optional[float] = None
    gpu_memory_percent: Optional[float] = None
    gpu_temp: Optional[int] = None
    timestamp: str


class WorkflowConfig(BaseModel):
    """Workflow configuration"""
    name: str
    description: Optional[str] = None
    config_json: str
    is_preset: bool = False


class AgentJob(BaseModel):
    """Agent job information"""
    id: str
    type: str  # 'research', 'project'
    goal: str
    status: str  # 'pending', 'running', 'completed', 'failed'
    created_at: str
    completed_at: Optional[str] = None
    result: Optional[str] = None


class RouterResponse(BaseModel):
    """Router agent response"""
    intent: str  # 'RESEARCH', 'PROJECT', 'BACKLOG', 'CHAT'
    confidence: float
    parameters: Optional[dict] = None
