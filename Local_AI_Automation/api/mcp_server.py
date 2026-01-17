"""
MCP (Model Context Protocol) Server
Enables Claude Code and other MCP clients to interact with the Local AI Hub

Implements:
- JSON-RPC 2.0 over stdio
- Tools for task management, agent control, and service operations
- Resources for accessing backlog, research, and system data
"""
import sys
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, List, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum

from .database import get_db
from .logging_config import api_logger


# MCP Protocol Constants
MCP_VERSION = "2024-11-05"
SERVER_NAME = "local-ai-hub"
SERVER_VERSION = "2.0.0"


class MCPError(Exception):
    """MCP protocol error"""
    def __init__(self, code: int, message: str, data: Any = None):
        self.code = code
        self.message = message
        self.data = data
        super().__init__(message)


# Standard JSON-RPC error codes
class ErrorCode:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


@dataclass
class Tool:
    """MCP Tool definition"""
    name: str
    description: str
    inputSchema: Dict[str, Any]
    handler: Callable = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.inputSchema
        }


@dataclass
class Resource:
    """MCP Resource definition"""
    uri: str
    name: str
    description: str
    mimeType: str = "application/json"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mimeType
        }


@dataclass
class ResourceTemplate:
    """MCP Resource Template definition"""
    uriTemplate: str
    name: str
    description: str
    mimeType: str = "application/json"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "uriTemplate": self.uriTemplate,
            "name": self.name,
            "description": self.description,
            "mimeType": self.mimeType
        }


class MCPServer:
    """
    MCP Server implementation for Local AI Hub

    Provides tools and resources for:
    - Backlog management (search, create, update tasks)
    - Agent control (start research, check status)
    - Service management (start/stop services)
    - System information (metrics, status)
    """

    def __init__(self):
        self._tools: Dict[str, Tool] = {}
        self._resources: List[Resource] = []
        self._resource_templates: List[ResourceTemplate] = []
        self._initialized = False
        self._register_tools()
        self._register_resources()

    # ==================== Tool Registration ====================

    def _register_tools(self):
        """Register all available tools"""

        # Backlog Tools
        self._add_tool(Tool(
            name="search_backlog",
            description="Search the backlog for tasks matching criteria. Returns matching items with their status, priority, and details.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to match against task titles and descriptions"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["backlog", "ready", "in_progress", "blocked", "done"],
                        "description": "Filter by task status"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["P0", "P1", "P2", "P3"],
                        "description": "Filter by priority level"
                    },
                    "category": {
                        "type": "string",
                        "description": "Filter by category"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 20,
                        "description": "Maximum number of results"
                    }
                }
            },
            handler=self._tool_search_backlog
        ))

        self._add_tool(Tool(
            name="create_task",
            description="Create a new task in the backlog. Returns the created task with its assigned ID.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Task title (required)"
                    },
                    "description": {
                        "type": "string",
                        "description": "Detailed task description"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["P0", "P1", "P2", "P3"],
                        "default": "P2",
                        "description": "Task priority"
                    },
                    "category": {
                        "type": "string",
                        "default": "general",
                        "description": "Task category"
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tags for categorization"
                    }
                },
                "required": ["title"]
            },
            handler=self._tool_create_task
        ))

        self._add_tool(Tool(
            name="update_task",
            description="Update an existing task's status, priority, or other fields.",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "Task external ID (e.g., BL-240115-ABC123)"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["backlog", "ready", "in_progress", "blocked", "done"]
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["P0", "P1", "P2", "P3"]
                    },
                    "title": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["task_id"]
            },
            handler=self._tool_update_task
        ))

        # Agent Tools
        self._add_tool(Tool(
            name="run_research",
            description="Start a research agent to investigate a topic. The agent will search the web and compile findings.",
            inputSchema={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Research goal or question to investigate"
                    },
                    "depth": {
                        "type": "integer",
                        "default": 5,
                        "description": "Number of search iterations (1-20)"
                    }
                },
                "required": ["goal"]
            },
            handler=self._tool_run_research
        ))

        self._add_tool(Tool(
            name="get_research_status",
            description="Check the status of a research session and get results if complete.",
            inputSchema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Research session ID"
                    }
                },
                "required": ["session_id"]
            },
            handler=self._tool_get_research_status
        ))

        # Service Tools
        self._add_tool(Tool(
            name="list_services",
            description="List all configured services and their current status.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            handler=self._tool_list_services
        ))

        self._add_tool(Tool(
            name="control_service",
            description="Start, stop, or restart a service.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_id": {
                        "type": "string",
                        "description": "Service identifier"
                    },
                    "action": {
                        "type": "string",
                        "enum": ["start", "stop", "restart"],
                        "description": "Action to perform"
                    }
                },
                "required": ["service_id", "action"]
            },
            handler=self._tool_control_service
        ))

        # System Tools
        self._add_tool(Tool(
            name="get_system_metrics",
            description="Get current system metrics including CPU, memory, GPU, and disk usage.",
            inputSchema={
                "type": "object",
                "properties": {}
            },
            handler=self._tool_get_metrics
        ))

        self._add_tool(Tool(
            name="query_knowledge",
            description="Search the knowledge base from past research sessions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "limit": {
                        "type": "integer",
                        "default": 10
                    }
                },
                "required": ["query"]
            },
            handler=self._tool_query_knowledge
        ))

        # Chat Tool
        self._add_tool(Tool(
            name="chat_with_llm",
            description="Send a message to the local LLM (Ollama) and get a response.",
            inputSchema={
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string",
                        "description": "Message to send to the LLM"
                    },
                    "model": {
                        "type": "string",
                        "default": "llama3.2",
                        "description": "Model to use"
                    },
                    "system_prompt": {
                        "type": "string",
                        "description": "Optional system prompt"
                    }
                },
                "required": ["message"]
            },
            handler=self._tool_chat_llm
        ))

    def _register_resources(self):
        """Register available resources"""

        # Static resources
        self._resources = [
            Resource(
                uri="hub://status",
                name="Hub Status",
                description="Current status of the Local AI Hub including service health"
            ),
            Resource(
                uri="hub://backlog/stats",
                name="Backlog Statistics",
                description="Statistics about backlog items by status, priority, and category"
            ),
            Resource(
                uri="hub://services",
                name="Services List",
                description="List of all configured services and their status"
            ),
            Resource(
                uri="hub://models",
                name="Available Models",
                description="List of available LLM models in Ollama"
            )
        ]

        # Resource templates
        self._resource_templates = [
            ResourceTemplate(
                uriTemplate="hub://backlog/{task_id}",
                name="Backlog Item",
                description="Get details of a specific backlog item by ID"
            ),
            ResourceTemplate(
                uriTemplate="hub://research/{session_id}",
                name="Research Session",
                description="Get details and results of a research session"
            )
        ]

    def _add_tool(self, tool: Tool):
        """Add a tool to the registry"""
        self._tools[tool.name] = tool

    # ==================== Tool Handlers ====================

    async def _tool_search_backlog(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Search backlog items"""
        query = arguments.get("query", "")
        status = arguments.get("status")
        priority = arguments.get("priority")
        category = arguments.get("category")
        limit = arguments.get("limit", 20)

        with get_db() as conn:
            sql = "SELECT * FROM backlog_items WHERE 1=1"
            params = []

            if query:
                sql += " AND (title LIKE ? OR description LIKE ?)"
                params.extend([f"%{query}%", f"%{query}%"])
            if status:
                sql += " AND status = ?"
                params.append(status)
            if priority:
                sql += " AND priority = ?"
                params.append(priority)
            if category:
                sql += " AND category = ?"
                params.append(category)

            sql += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)

            rows = conn.execute(sql, params).fetchall()
            items = [dict(row) for row in rows]

        return {
            "items": items,
            "count": len(items),
            "query": query
        }

    async def _tool_create_task(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new backlog task"""
        from .database import generate_external_id

        title = arguments.get("title")
        if not title:
            raise MCPError(ErrorCode.INVALID_PARAMS, "Title is required")

        external_id = generate_external_id()
        now = datetime.utcnow().isoformat()

        with get_db() as conn:
            cursor = conn.execute("""
                INSERT INTO backlog_items
                (external_id, title, description, priority, category, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'backlog', ?)
            """, (
                external_id,
                title,
                arguments.get("description", ""),
                arguments.get("priority", "P2"),
                arguments.get("category", "general"),
                now
            ))

            return {
                "success": True,
                "task_id": external_id,
                "message": f"Created task {external_id}: {title}"
            }

    async def _tool_update_task(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing task"""
        task_id = arguments.get("task_id")
        if not task_id:
            raise MCPError(ErrorCode.INVALID_PARAMS, "task_id is required")

        updates = []
        params = []

        for field in ["status", "priority", "title", "description"]:
            if field in arguments and arguments[field] is not None:
                updates.append(f"{field} = ?")
                params.append(arguments[field])

        if not updates:
            raise MCPError(ErrorCode.INVALID_PARAMS, "No fields to update")

        params.append(task_id)

        with get_db() as conn:
            cursor = conn.execute(
                f"UPDATE backlog_items SET {', '.join(updates)} WHERE external_id = ?",
                params
            )

            if cursor.rowcount == 0:
                raise MCPError(ErrorCode.INVALID_PARAMS, f"Task {task_id} not found")

            return {
                "success": True,
                "task_id": task_id,
                "updated_fields": list(arguments.keys())
            }

    async def _tool_run_research(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Start a research agent"""
        import subprocess
        import uuid

        goal = arguments.get("goal")
        if not goal:
            raise MCPError(ErrorCode.INVALID_PARAMS, "Goal is required")

        depth = min(max(arguments.get("depth", 5), 1), 20)
        session_id = f"research-{uuid.uuid4().hex[:8]}"

        # Record session start
        with get_db() as conn:
            conn.execute("""
                INSERT INTO research_sessions (id, goal, status, start_time)
                VALUES (?, ?, 'running', ?)
            """, (session_id, goal, datetime.utcnow().isoformat()))

        # Note: In production, this would use the job queue
        # For now, return the session ID for status checking
        return {
            "session_id": session_id,
            "goal": goal,
            "status": "started",
            "message": f"Research session {session_id} started. Use get_research_status to check progress."
        }

    async def _tool_get_research_status(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get research session status"""
        session_id = arguments.get("session_id")
        if not session_id:
            raise MCPError(ErrorCode.INVALID_PARAMS, "session_id is required")

        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM research_sessions WHERE id = ?",
                (session_id,)
            ).fetchone()

            if not row:
                raise MCPError(ErrorCode.INVALID_PARAMS, f"Session {session_id} not found")

            return dict(row)

    async def _tool_list_services(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """List all services"""
        from .routes.services import SERVICES, check_service_health

        services = []
        for svc_id, svc in SERVICES.items():
            # Check health asynchronously
            try:
                is_healthy = await check_service_health(svc["health_url"])
                status = "running" if is_healthy else "stopped"
            except Exception:
                status = "unknown"

            services.append({
                "id": svc_id,
                "name": svc["name"],
                "port": svc["port"],
                "type": svc["type"],
                "status": status
            })

        return {"services": services}

    async def _tool_control_service(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Control a service"""
        service_id = arguments.get("service_id")
        action = arguments.get("action")

        if not service_id or not action:
            raise MCPError(ErrorCode.INVALID_PARAMS, "service_id and action are required")

        # This would integrate with the actual service control
        return {
            "service_id": service_id,
            "action": action,
            "status": "requested",
            "message": f"Service {action} requested for {service_id}"
        }

    async def _tool_get_metrics(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Get system metrics"""
        import psutil

        metrics = {
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory": {
                "percent": psutil.virtual_memory().percent,
                "used_gb": round(psutil.virtual_memory().used / (1024**3), 2),
                "total_gb": round(psutil.virtual_memory().total / (1024**3), 2)
            },
            "disk": {
                "percent": psutil.disk_usage('/').percent,
                "used_gb": round(psutil.disk_usage('/').used / (1024**3), 2),
                "total_gb": round(psutil.disk_usage('/').total / (1024**3), 2)
            }
        }

        # Try to get GPU info
        try:
            import subprocess
            result = subprocess.run(
                ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total', '--format=csv,noheader,nounits'],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                parts = result.stdout.strip().split(', ')
                metrics["gpu"] = {
                    "utilization": int(parts[0]),
                    "memory_used_mb": int(parts[1]),
                    "memory_total_mb": int(parts[2])
                }
        except Exception:
            metrics["gpu"] = None

        return metrics

    async def _tool_query_knowledge(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Search knowledge base"""
        query = arguments.get("query", "")
        limit = arguments.get("limit", 10)

        with get_db() as conn:
            rows = conn.execute("""
                SELECT id, goal, knowledge_graph, start_time
                FROM research_sessions
                WHERE knowledge_graph LIKE ? AND status = 'completed'
                ORDER BY start_time DESC
                LIMIT ?
            """, (f"%{query}%", limit)).fetchall()

            results = [dict(row) for row in rows]

        return {
            "query": query,
            "results": results,
            "count": len(results)
        }

    async def _tool_chat_llm(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Chat with local LLM"""
        import httpx

        message = arguments.get("message")
        if not message:
            raise MCPError(ErrorCode.INVALID_PARAMS, "Message is required")

        model = arguments.get("model", "llama3.2")
        system_prompt = arguments.get("system_prompt")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": message})

        try:
            async with httpx.AsyncClient(timeout=120) as client:
                response = await client.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": model,
                        "messages": messages,
                        "stream": False
                    }
                )
                response.raise_for_status()
                data = response.json()

                return {
                    "response": data.get("message", {}).get("content", ""),
                    "model": model,
                    "done": True
                }
        except Exception as e:
            raise MCPError(ErrorCode.INTERNAL_ERROR, f"LLM request failed: {str(e)}")

    # ==================== Resource Handlers ====================

    async def _read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a resource by URI"""
        if uri == "hub://status":
            return await self._resource_hub_status()
        elif uri == "hub://backlog/stats":
            return await self._resource_backlog_stats()
        elif uri == "hub://services":
            return await self._tool_list_services({})
        elif uri == "hub://models":
            return await self._resource_models()
        elif uri.startswith("hub://backlog/"):
            task_id = uri.replace("hub://backlog/", "")
            return await self._resource_backlog_item(task_id)
        elif uri.startswith("hub://research/"):
            session_id = uri.replace("hub://research/", "")
            return await self._tool_get_research_status({"session_id": session_id})
        else:
            raise MCPError(ErrorCode.INVALID_PARAMS, f"Unknown resource: {uri}")

    async def _resource_hub_status(self) -> Dict[str, Any]:
        """Get hub status"""
        services = await self._tool_list_services({})
        running = sum(1 for s in services["services"] if s["status"] == "running")

        return {
            "status": "healthy",
            "version": SERVER_VERSION,
            "services_running": running,
            "services_total": len(services["services"]),
            "timestamp": datetime.utcnow().isoformat()
        }

    async def _resource_backlog_stats(self) -> Dict[str, Any]:
        """Get backlog statistics"""
        with get_db() as conn:
            stats = {}

            rows = conn.execute(
                "SELECT status, COUNT(*) as count FROM backlog_items GROUP BY status"
            ).fetchall()
            stats["by_status"] = {row["status"]: row["count"] for row in rows}

            rows = conn.execute(
                "SELECT priority, COUNT(*) as count FROM backlog_items GROUP BY priority"
            ).fetchall()
            stats["by_priority"] = {row["priority"]: row["count"] for row in rows}

            total = conn.execute("SELECT COUNT(*) FROM backlog_items").fetchone()[0]
            stats["total"] = total

        return stats

    async def _resource_models(self) -> Dict[str, Any]:
        """Get available models"""
        import httpx

        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get("http://localhost:11434/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "models": [m["name"] for m in data.get("models", [])],
                        "count": len(data.get("models", []))
                    }
        except Exception:
            pass

        return {"models": [], "count": 0, "error": "Ollama not available"}

    async def _resource_backlog_item(self, task_id: str) -> Dict[str, Any]:
        """Get a specific backlog item"""
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM backlog_items WHERE external_id = ?",
                (task_id,)
            ).fetchone()

            if not row:
                raise MCPError(ErrorCode.INVALID_PARAMS, f"Task {task_id} not found")

            return dict(row)

    # ==================== Protocol Handlers ====================

    async def handle_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Handle an incoming MCP message"""
        method = message.get("method")
        params = message.get("params", {})
        msg_id = message.get("id")

        try:
            if method == "initialize":
                result = await self._handle_initialize(params)
            elif method == "initialized":
                result = None  # Notification, no response
            elif method == "tools/list":
                result = await self._handle_list_tools()
            elif method == "tools/call":
                result = await self._handle_call_tool(params)
            elif method == "resources/list":
                result = await self._handle_list_resources()
            elif method == "resources/read":
                result = await self._handle_read_resource(params)
            elif method == "resources/templates/list":
                result = await self._handle_list_templates()
            elif method == "ping":
                result = {}
            else:
                raise MCPError(ErrorCode.METHOD_NOT_FOUND, f"Unknown method: {method}")

            if msg_id is not None and result is not None:
                return {"jsonrpc": "2.0", "id": msg_id, "result": result}
            return None

        except MCPError as e:
            if msg_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": e.code, "message": e.message, "data": e.data}
                }
        except Exception as e:
            api_logger.error(f"MCP error: {e}")
            if msg_id is not None:
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "error": {"code": ErrorCode.INTERNAL_ERROR, "message": str(e)}
                }
        return None

    async def _handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request"""
        self._initialized = True
        return {
            "protocolVersion": MCP_VERSION,
            "capabilities": {
                "tools": {},
                "resources": {"subscribe": False, "listChanged": False}
            },
            "serverInfo": {
                "name": SERVER_NAME,
                "version": SERVER_VERSION
            }
        }

    async def _handle_list_tools(self) -> Dict[str, Any]:
        """Handle tools/list request"""
        return {
            "tools": [tool.to_dict() for tool in self._tools.values()]
        }

    async def _handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle tools/call request"""
        name = params.get("name")
        arguments = params.get("arguments", {})

        if name not in self._tools:
            raise MCPError(ErrorCode.METHOD_NOT_FOUND, f"Unknown tool: {name}")

        tool = self._tools[name]
        result = await tool.handler(arguments)

        return {
            "content": [
                {"type": "text", "text": json.dumps(result, indent=2, default=str)}
            ]
        }

    async def _handle_list_resources(self) -> Dict[str, Any]:
        """Handle resources/list request"""
        return {
            "resources": [r.to_dict() for r in self._resources]
        }

    async def _handle_read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle resources/read request"""
        uri = params.get("uri")
        if not uri:
            raise MCPError(ErrorCode.INVALID_PARAMS, "URI is required")

        result = await self._read_resource(uri)
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": json.dumps(result, indent=2, default=str)
                }
            ]
        }

    async def _handle_list_templates(self) -> Dict[str, Any]:
        """Handle resources/templates/list request"""
        return {
            "resourceTemplates": [t.to_dict() for t in self._resource_templates]
        }


async def run_stdio_server():
    """Run MCP server over stdio"""
    server = MCPServer()

    # Read from stdin, write to stdout
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await asyncio.get_event_loop().connect_write_pipe(
        asyncio.streams.FlowControlMixin, sys.stdout
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, asyncio.get_event_loop())

    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            message = json.loads(line.decode())
            response = await server.handle_message(message)

            if response:
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

        except json.JSONDecodeError:
            error_response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": ErrorCode.PARSE_ERROR, "message": "Parse error"}
            }
            writer.write((json.dumps(error_response) + "\n").encode())
            await writer.drain()
        except Exception as e:
            api_logger.error(f"MCP server error: {e}")
            break


# Global server instance
_mcp_server: Optional[MCPServer] = None


def get_mcp_server() -> MCPServer:
    """Get the global MCP server instance"""
    global _mcp_server
    if _mcp_server is None:
        _mcp_server = MCPServer()
    return _mcp_server
