"""
Workflow Routes
Handles workflow presets and configurations
"""
from fastapi import APIRouter, HTTPException

from ..models import WorkflowConfig
from ..database import get_db

router = APIRouter(prefix="/workflows", tags=["Workflows"])

# Built-in workflow presets for visualization
WORKFLOW_PRESETS = [
    {
        "id": "chat-pipeline",
        "name": "Chat Pipeline",
        "description": "Simple user input to LLM response flow",
        "nodes": [
            {"id": "input", "type": "input", "label": "User Input", "x": 50, "y": 75},
            {"id": "ollama", "type": "service", "service": "ollama", "label": "Ollama LLM", "x": 250, "y": 75},
            {"id": "output", "type": "output", "label": "Response", "x": 450, "y": 75}
        ],
        "connections": [
            {"from": "input", "to": "ollama"},
            {"from": "ollama", "to": "output"}
        ]
    },
    {
        "id": "research-agent",
        "name": "Research Agent",
        "description": "Autonomous research with web search and knowledge synthesis",
        "nodes": [
            {"id": "input", "type": "input", "label": "Research Goal", "x": 50, "y": 75},
            {"id": "router", "type": "agent", "label": "Router", "x": 200, "y": 75},
            {"id": "search", "type": "tool", "label": "Web Search", "x": 350, "y": 25},
            {"id": "analyze", "type": "service", "service": "ollama", "label": "Analyze", "x": 350, "y": 125},
            {"id": "kb", "type": "output", "label": "Knowledge Base", "x": 500, "y": 75}
        ],
        "connections": [
            {"from": "input", "to": "router"},
            {"from": "router", "to": "search"},
            {"from": "router", "to": "analyze"},
            {"from": "search", "to": "analyze"},
            {"from": "analyze", "to": "kb"}
        ]
    },
    {
        "id": "document-processing",
        "name": "Document Processing",
        "description": "PDF extraction, OCR, and summarization pipeline",
        "nodes": [
            {"id": "input", "type": "input", "label": "PDF Upload", "x": 50, "y": 75},
            {"id": "ocr", "type": "tool", "label": "OCR Extract", "x": 200, "y": 75},
            {"id": "summarize", "type": "service", "service": "ollama", "label": "Summarize", "x": 350, "y": 75},
            {"id": "output", "type": "output", "label": "Summary", "x": 500, "y": 75}
        ],
        "connections": [
            {"from": "input", "to": "ocr"},
            {"from": "ocr", "to": "summarize"},
            {"from": "summarize", "to": "output"}
        ]
    },
    {
        "id": "email-lead-detection",
        "name": "Email Lead Detection",
        "description": "Automated consulting lead detection from emails",
        "nodes": [
            {"id": "email", "type": "input", "label": "Email Inbox", "x": 50, "y": 75},
            {"id": "classify", "type": "service", "service": "ollama", "label": "Classify", "x": 200, "y": 75},
            {"id": "extract", "type": "agent", "label": "Extract Info", "x": 350, "y": 75},
            {"id": "slack", "type": "output", "label": "Slack Alert", "x": 500, "y": 75}
        ],
        "connections": [
            {"from": "email", "to": "classify"},
            {"from": "classify", "to": "extract"},
            {"from": "extract", "to": "slack"}
        ]
    },
    {
        "id": "backlog-monitor",
        "name": "Backlog Monitor",
        "description": "Slack message to structured task creation",
        "nodes": [
            {"id": "slack", "type": "input", "label": "Slack Message", "x": 50, "y": 75},
            {"id": "parse", "type": "service", "service": "ollama", "label": "Parse Task", "x": 200, "y": 75},
            {"id": "clarify", "type": "agent", "label": "Clarify", "x": 350, "y": 25},
            {"id": "create", "type": "tool", "label": "Create Item", "x": 350, "y": 125},
            {"id": "confirm", "type": "output", "label": "Confirm", "x": 500, "y": 75}
        ],
        "connections": [
            {"from": "slack", "to": "parse"},
            {"from": "parse", "to": "clarify"},
            {"from": "parse", "to": "create"},
            {"from": "clarify", "to": "create"},
            {"from": "create", "to": "confirm"}
        ]
    }
]


@router.get("/presets")
def list_workflow_presets():
    """Get built-in workflow presets for visualization"""
    return WORKFLOW_PRESETS


@router.get("/presets/{preset_id}")
def get_workflow_preset(preset_id: str):
    """Get a specific workflow preset"""
    preset = next((p for p in WORKFLOW_PRESETS if p["id"] == preset_id), None)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    return preset


@router.get("/configs")
def list_workflow_configs():
    """List saved workflow configurations"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM workflow_configs ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


@router.post("/configs")
def save_workflow_config(config: WorkflowConfig):
    """Save a workflow configuration"""
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO workflow_configs (name, description, config_json, is_preset)
               VALUES (?, ?, ?, ?)""",
            (config.name, config.description, config.config_json, config.is_preset)
        )
        return {"id": cursor.lastrowid, "status": "created"}


@router.get("/configs/{config_id}")
def get_workflow_config(config_id: int):
    """Get a specific workflow configuration"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM workflow_configs WHERE id = ?",
            (config_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Config not found")
        return dict(row)


@router.delete("/configs/{config_id}")
def delete_workflow_config(config_id: int):
    """Delete a workflow configuration"""
    with get_db() as conn:
        result = conn.execute(
            "DELETE FROM workflow_configs WHERE id = ? AND is_preset = 0",
            (config_id,)
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Config not found or is a preset")
        return {"status": "deleted"}
