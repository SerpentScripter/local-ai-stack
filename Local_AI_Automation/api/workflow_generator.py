"""
Natural Language Workflow Generator
Converts natural language descriptions into n8n workflow JSON

Features:
- Parse user intent from natural language
- Generate valid n8n workflow JSON
- Support common triggers (webhook, schedule, email)
- Support common actions (Ollama, HTTP, Slack, database)
- Human-in-the-loop approval before activation
"""
import json
import re
import uuid
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .database import get_db
from .logging_config import api_logger


class TriggerType(Enum):
    """Supported workflow triggers"""
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    MANUAL = "manual"
    EMAIL = "email"
    FILE_WATCH = "file_watch"
    MESSAGE_BUS = "message_bus"


class ActionType(Enum):
    """Supported workflow actions"""
    OLLAMA = "ollama"
    HTTP_REQUEST = "http_request"
    SLACK_MESSAGE = "slack_message"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    SEND_EMAIL = "send_email"
    CONDITIONAL = "conditional"
    CODE = "code"
    DATABASE = "database"
    SET_VARIABLE = "set_variable"


@dataclass
class WorkflowNode:
    """A node in the workflow"""
    id: str
    name: str
    type: str
    parameters: Dict[str, Any]
    position: Tuple[int, int] = (0, 0)

    def to_n8n(self) -> Dict[str, Any]:
        """Convert to n8n node format"""
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "typeVersion": 1,
            "position": list(self.position),
            "parameters": self.parameters
        }


@dataclass
class WorkflowConnection:
    """Connection between nodes"""
    source_node: str
    source_output: int
    target_node: str
    target_input: int


@dataclass
class GeneratedWorkflow:
    """A generated workflow ready for review"""
    id: str
    name: str
    description: str
    original_prompt: str
    nodes: List[WorkflowNode]
    connections: List[WorkflowConnection]
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending_review"  # pending_review, approved, rejected, deployed

    def to_n8n_json(self) -> Dict[str, Any]:
        """Convert to full n8n workflow JSON"""
        # Build connections structure
        conn_dict = {}
        for conn in self.connections:
            if conn.source_node not in conn_dict:
                conn_dict[conn.source_node] = {"main": [[]]}

            while len(conn_dict[conn.source_node]["main"]) <= conn.source_output:
                conn_dict[conn.source_node]["main"].append([])

            conn_dict[conn.source_node]["main"][conn.source_output].append({
                "node": conn.target_node,
                "type": "main",
                "index": conn.target_input
            })

        return {
            "name": self.name,
            "nodes": [node.to_n8n() for node in self.nodes],
            "connections": conn_dict,
            "active": False,
            "settings": {
                "executionOrder": "v1"
            },
            "tags": ["auto-generated", "local-ai-hub"],
            "meta": {
                "generated_by": "local-ai-hub",
                "original_prompt": self.original_prompt,
                "generated_at": self.created_at.isoformat()
            }
        }


class WorkflowGenerator:
    """
    Natural Language to n8n Workflow Generator

    Uses LLM to understand intent and generates valid n8n workflows.
    Includes human-in-the-loop approval before deployment.
    """

    def __init__(self):
        self._templates = self._load_templates()
        self._pending_workflows: Dict[str, GeneratedWorkflow] = {}
        self._init_database()

    def _init_database(self):
        """Initialize workflow storage tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS generated_workflows (
                        id TEXT PRIMARY KEY,
                        name TEXT NOT NULL,
                        description TEXT,
                        original_prompt TEXT NOT NULL,
                        workflow_json TEXT NOT NULL,
                        status TEXT DEFAULT 'pending_review',
                        created_at TEXT NOT NULL,
                        reviewed_at TEXT,
                        deployed_at TEXT,
                        n8n_workflow_id TEXT
                    );

                    CREATE INDEX IF NOT EXISTS idx_workflow_status ON generated_workflows(status);
                """)
        except Exception as e:
            api_logger.error(f"Failed to init workflow tables: {e}")

    def _load_templates(self) -> Dict[str, Dict[str, Any]]:
        """Load workflow templates for common patterns"""
        return {
            "email_classification": {
                "description": "Classify incoming emails and route based on content",
                "triggers": [TriggerType.EMAIL],
                "actions": [ActionType.OLLAMA, ActionType.CONDITIONAL, ActionType.CREATE_TASK]
            },
            "webhook_to_slack": {
                "description": "Receive webhook and send Slack notification",
                "triggers": [TriggerType.WEBHOOK],
                "actions": [ActionType.SLACK_MESSAGE]
            },
            "scheduled_report": {
                "description": "Generate and send scheduled reports",
                "triggers": [TriggerType.SCHEDULE],
                "actions": [ActionType.DATABASE, ActionType.OLLAMA, ActionType.SEND_EMAIL]
            },
            "file_processing": {
                "description": "Watch for files and process with AI",
                "triggers": [TriggerType.FILE_WATCH],
                "actions": [ActionType.OLLAMA, ActionType.DATABASE]
            }
        }

    async def generate_from_prompt(
        self,
        prompt: str,
        ollama_url: str = "http://localhost:11434",
        model: str = "llama3.2"
    ) -> GeneratedWorkflow:
        """
        Generate a workflow from natural language description

        Args:
            prompt: Natural language description of desired workflow
            ollama_url: Ollama API URL
            model: Model to use for generation

        Returns:
            GeneratedWorkflow ready for review
        """
        import httpx

        workflow_id = f"wf_{uuid.uuid4().hex[:12]}"

        # Build the LLM prompt
        system_prompt = self._build_system_prompt()
        user_prompt = f"""Generate an n8n workflow for the following request:

"{prompt}"

Respond with a JSON object containing:
1. "name": A short name for the workflow
2. "description": Brief description
3. "trigger": The trigger type and configuration
4. "steps": Array of workflow steps with type and parameters

Be specific about node types and parameters. Use real n8n node types."""

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{ollama_url}/api/generate",
                    json={
                        "model": model,
                        "prompt": f"{system_prompt}\n\nUser: {user_prompt}",
                        "stream": False,
                        "format": "json"
                    }
                )

                if response.status_code != 200:
                    raise Exception(f"Ollama error: {response.status_code}")

                result = response.json()
                llm_response = result.get("response", "{}")

                # Parse the LLM response
                workflow_spec = self._parse_llm_response(llm_response)

        except Exception as e:
            api_logger.error(f"LLM generation failed: {e}")
            # Fall back to template matching
            workflow_spec = self._match_template(prompt)

        # Build the workflow
        nodes, connections = self._build_workflow_nodes(workflow_spec)

        workflow = GeneratedWorkflow(
            id=workflow_id,
            name=workflow_spec.get("name", "Generated Workflow"),
            description=workflow_spec.get("description", prompt[:200]),
            original_prompt=prompt,
            nodes=nodes,
            connections=connections
        )

        # Store for review
        self._pending_workflows[workflow_id] = workflow
        self._save_workflow(workflow)

        return workflow

    def _build_system_prompt(self) -> str:
        """Build system prompt for workflow generation"""
        return """You are an n8n workflow generator. You create valid n8n workflow configurations.

Available trigger types:
- n8n-nodes-base.webhook: HTTP webhook trigger
- n8n-nodes-base.scheduleTrigger: Cron/interval schedule
- n8n-nodes-base.manualTrigger: Manual execution
- n8n-nodes-base.emailReadImap: Email trigger

Available action nodes:
- n8n-nodes-base.httpRequest: Make HTTP requests
- n8n-nodes-base.slack: Send Slack messages
- n8n-nodes-base.if: Conditional branching
- n8n-nodes-base.code: Execute JavaScript
- n8n-nodes-base.set: Set variables
- @n8n/n8n-nodes-langchain.lmChatOllama: Ollama LLM

Always respond with valid JSON. Include realistic parameters for each node."""

    def _parse_llm_response(self, response: str) -> Dict[str, Any]:
        """Parse LLM response into workflow spec"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        # Return basic spec if parsing fails
        return {
            "name": "Generated Workflow",
            "description": "Auto-generated workflow",
            "trigger": {"type": "webhook"},
            "steps": []
        }

    def _match_template(self, prompt: str) -> Dict[str, Any]:
        """Match prompt to a template when LLM fails"""
        prompt_lower = prompt.lower()

        if "email" in prompt_lower and ("classify" in prompt_lower or "sort" in prompt_lower):
            return {
                "name": "Email Classifier",
                "description": "Classify and route emails",
                "trigger": {"type": "email"},
                "steps": [
                    {"type": "ollama", "action": "classify"},
                    {"type": "conditional", "field": "classification"},
                    {"type": "create_task"}
                ]
            }
        elif "webhook" in prompt_lower and "slack" in prompt_lower:
            return {
                "name": "Webhook to Slack",
                "description": "Forward webhooks to Slack",
                "trigger": {"type": "webhook"},
                "steps": [
                    {"type": "slack_message"}
                ]
            }
        elif "schedule" in prompt_lower or "daily" in prompt_lower or "weekly" in prompt_lower:
            return {
                "name": "Scheduled Task",
                "description": "Run task on schedule",
                "trigger": {"type": "schedule", "interval": "daily"},
                "steps": [
                    {"type": "ollama", "action": "generate"},
                    {"type": "slack_message"}
                ]
            }
        else:
            # Default: webhook trigger with Ollama processing
            return {
                "name": "AI Processor",
                "description": "Process input with AI",
                "trigger": {"type": "webhook"},
                "steps": [
                    {"type": "ollama", "action": "process"},
                    {"type": "set_variable"}
                ]
            }

    def _build_workflow_nodes(
        self,
        spec: Dict[str, Any]
    ) -> Tuple[List[WorkflowNode], List[WorkflowConnection]]:
        """Build n8n nodes from workflow spec"""
        nodes = []
        connections = []
        x_pos = 250
        y_pos = 300

        # Create trigger node
        trigger = spec.get("trigger", {"type": "webhook"})
        trigger_node = self._create_trigger_node(trigger, (x_pos, y_pos))
        nodes.append(trigger_node)

        prev_node_name = trigger_node.name
        x_pos += 200

        # Create action nodes
        for i, step in enumerate(spec.get("steps", [])):
            node = self._create_action_node(step, i, (x_pos, y_pos))
            nodes.append(node)

            # Connect to previous node
            connections.append(WorkflowConnection(
                source_node=prev_node_name,
                source_output=0,
                target_node=node.name,
                target_input=0
            ))

            prev_node_name = node.name
            x_pos += 200

        return nodes, connections

    def _create_trigger_node(
        self,
        trigger: Dict[str, Any],
        position: Tuple[int, int]
    ) -> WorkflowNode:
        """Create a trigger node"""
        trigger_type = trigger.get("type", "webhook")

        if trigger_type == "webhook":
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="Webhook Trigger",
                type="n8n-nodes-base.webhook",
                parameters={
                    "httpMethod": "POST",
                    "path": f"workflow-{uuid.uuid4().hex[:8]}",
                    "responseMode": "onReceived",
                    "responseData": "allEntries"
                },
                position=position
            )
        elif trigger_type == "schedule":
            interval = trigger.get("interval", "daily")
            cron = "0 9 * * *" if interval == "daily" else "0 9 * * 1"
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="Schedule Trigger",
                type="n8n-nodes-base.scheduleTrigger",
                parameters={
                    "rule": {
                        "interval": [{"field": "cronExpression", "expression": cron}]
                    }
                },
                position=position
            )
        elif trigger_type == "email":
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="Email Trigger",
                type="n8n-nodes-base.emailReadImap",
                parameters={
                    "mailbox": "INBOX",
                    "options": {}
                },
                position=position
            )
        else:
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="Manual Trigger",
                type="n8n-nodes-base.manualTrigger",
                parameters={},
                position=position
            )

    def _create_action_node(
        self,
        step: Dict[str, Any],
        index: int,
        position: Tuple[int, int]
    ) -> WorkflowNode:
        """Create an action node"""
        step_type = step.get("type", "set_variable")

        if step_type == "ollama":
            action = step.get("action", "process")
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name=f"Ollama {action.title()}",
                type="n8n-nodes-base.httpRequest",
                parameters={
                    "method": "POST",
                    "url": "http://host.docker.internal:11434/api/generate",
                    "sendBody": True,
                    "bodyParameters": {
                        "parameters": [
                            {"name": "model", "value": "llama3.2"},
                            {"name": "prompt", "value": "={{ $json.body }}"},
                            {"name": "stream", "value": False}
                        ]
                    },
                    "options": {}
                },
                position=position
            )
        elif step_type == "slack_message":
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="Send Slack Message",
                type="n8n-nodes-base.slack",
                parameters={
                    "resource": "message",
                    "operation": "post",
                    "channel": "#general",
                    "text": "={{ $json.message || $json.body || 'Notification' }}"
                },
                position=position
            )
        elif step_type == "conditional":
            field = step.get("field", "result")
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="Check Condition",
                type="n8n-nodes-base.if",
                parameters={
                    "conditions": {
                        "string": [{
                            "value1": f"={{{{ $json.{field} }}}}",
                            "operation": "isNotEmpty"
                        }]
                    }
                },
                position=position
            )
        elif step_type == "create_task":
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="Create Task",
                type="n8n-nodes-base.httpRequest",
                parameters={
                    "method": "POST",
                    "url": "http://host.docker.internal:8765/backlog",
                    "sendBody": True,
                    "bodyParameters": {
                        "parameters": [
                            {"name": "title", "value": "={{ $json.title || 'New Task' }}"},
                            {"name": "description", "value": "={{ $json.description || '' }}"},
                            {"name": "priority", "value": "P2"}
                        ]
                    },
                    "options": {}
                },
                position=position
            )
        elif step_type == "http_request":
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name="HTTP Request",
                type="n8n-nodes-base.httpRequest",
                parameters={
                    "method": step.get("method", "GET"),
                    "url": step.get("url", "https://api.example.com"),
                    "options": {}
                },
                position=position
            )
        else:
            return WorkflowNode(
                id=str(uuid.uuid4()),
                name=f"Set Variables {index + 1}",
                type="n8n-nodes-base.set",
                parameters={
                    "values": {
                        "string": [{"name": "processed", "value": "true"}]
                    }
                },
                position=position
            )

    def _save_workflow(self, workflow: GeneratedWorkflow):
        """Save workflow to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO generated_workflows
                    (id, name, description, original_prompt, workflow_json, status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    workflow.id,
                    workflow.name,
                    workflow.description,
                    workflow.original_prompt,
                    json.dumps(workflow.to_n8n_json()),
                    workflow.status,
                    workflow.created_at.isoformat()
                ))
        except Exception as e:
            api_logger.error(f"Failed to save workflow: {e}")

    # ==================== Review & Approval ====================

    def get_pending_workflows(self) -> List[Dict[str, Any]]:
        """Get all workflows pending review"""
        try:
            with get_db() as conn:
                rows = conn.execute("""
                    SELECT * FROM generated_workflows
                    WHERE status = 'pending_review'
                    ORDER BY created_at DESC
                """).fetchall()
                return [dict(row) for row in rows]
        except Exception:
            return []

    def get_workflow(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific workflow"""
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM generated_workflows WHERE id = ?",
                    (workflow_id,)
                ).fetchone()
                if row:
                    result = dict(row)
                    result["workflow_json"] = json.loads(result["workflow_json"])
                    return result
                return None
        except Exception:
            return None

    def approve_workflow(self, workflow_id: str) -> bool:
        """Approve a workflow for deployment"""
        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE generated_workflows
                    SET status = 'approved', reviewed_at = ?
                    WHERE id = ?
                """, (datetime.utcnow().isoformat(), workflow_id))
                return True
        except Exception:
            return False

    def reject_workflow(self, workflow_id: str, reason: str = "") -> bool:
        """Reject a workflow"""
        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE generated_workflows
                    SET status = 'rejected', reviewed_at = ?,
                        description = description || ' [Rejected: ' || ? || ']'
                    WHERE id = ?
                """, (datetime.utcnow().isoformat(), reason, workflow_id))
                return True
        except Exception:
            return False

    async def deploy_workflow(
        self,
        workflow_id: str,
        n8n_url: str = "http://localhost:5678",
        api_key: Optional[str] = None
    ) -> Optional[str]:
        """Deploy an approved workflow to n8n"""
        import httpx

        workflow = self.get_workflow(workflow_id)
        if not workflow or workflow["status"] != "approved":
            return None

        headers = {}
        if api_key:
            headers["X-N8N-API-KEY"] = api_key

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{n8n_url}/api/v1/workflows",
                    json=workflow["workflow_json"],
                    headers=headers
                )

                if response.status_code in (200, 201):
                    result = response.json()
                    n8n_id = result.get("id")

                    # Update status
                    with get_db() as conn:
                        conn.execute("""
                            UPDATE generated_workflows
                            SET status = 'deployed', deployed_at = ?, n8n_workflow_id = ?
                            WHERE id = ?
                        """, (datetime.utcnow().isoformat(), n8n_id, workflow_id))

                    return n8n_id

        except Exception as e:
            api_logger.error(f"Failed to deploy workflow: {e}")

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get workflow generation statistics"""
        try:
            with get_db() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM generated_workflows"
                ).fetchone()[0]

                by_status = {}
                rows = conn.execute("""
                    SELECT status, COUNT(*) as count
                    FROM generated_workflows
                    GROUP BY status
                """).fetchall()
                for row in rows:
                    by_status[row["status"]] = row["count"]

                return {
                    "total_generated": total,
                    "by_status": by_status,
                    "templates_available": len(self._templates)
                }
        except Exception:
            return {"total_generated": 0, "by_status": {}, "templates_available": 0}


# Global instance
_workflow_generator: Optional[WorkflowGenerator] = None


def get_workflow_generator() -> WorkflowGenerator:
    """Get the global WorkflowGenerator instance"""
    global _workflow_generator
    if _workflow_generator is None:
        _workflow_generator = WorkflowGenerator()
    return _workflow_generator
