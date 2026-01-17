"""
Agent Routes
Handles research agent, project agent, and router functionality
"""
import subprocess
import shlex
import json
from pathlib import Path
from fastapi import APIRouter, HTTPException, BackgroundTasks

from ..database import get_db

router = APIRouter(prefix="/agent", tags=["Agents"])

PROJECT_ROOT = Path(__file__).parent.parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


@router.post("/research")
def start_research(goal: str, limit: int = 10, background_tasks: BackgroundTasks = None):
    """Start a research agent session"""
    cmd = f'python "{SCRIPTS_DIR}/research_agent.py" --goal "{goal}" --limit {limit}'
    subprocess.Popen(shlex.split(cmd), cwd=str(PROJECT_ROOT))
    return {"status": "started", "goal": goal, "time_limit_minutes": limit}


@router.get("/research")
def list_research_sessions():
    """List all research sessions"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM research_sessions ORDER BY start_time DESC LIMIT 20"
        ).fetchall()
        return [dict(row) for row in rows]


@router.get("/research/{session_id}")
def get_research_session(session_id: int):
    """Get details of a specific research session"""
    with get_db() as conn:
        session = conn.execute(
            "SELECT * FROM research_sessions WHERE id = ?",
            (session_id,)
        ).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        findings = conn.execute(
            "SELECT * FROM research_findings WHERE session_id = ? ORDER BY created_at",
            (session_id,)
        ).fetchall()

        return {
            "session": dict(session),
            "findings": [dict(f) for f in findings]
        }


@router.post("/project")
def start_project(goal: str):
    """Start a project agent to scaffold a new project"""
    cmd = f'python "{SCRIPTS_DIR}/project_agency.py" --goal "{goal}"'
    subprocess.Popen(shlex.split(cmd), cwd=str(PROJECT_ROOT))
    return {"status": "started", "goal": goal}


@router.get("/projects")
def list_projects():
    """List all agent-created projects"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM agent_projects ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        return [dict(row) for row in rows]


@router.get("/projects/{project_id}")
def get_project(project_id: int):
    """Get details of a specific project"""
    with get_db() as conn:
        project = conn.execute(
            "SELECT * FROM agent_projects WHERE id = ?",
            (project_id,)
        ).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return dict(project)


@router.post("/router")
def route_prompt(prompt: str):
    """Route a user prompt to the appropriate intent"""
    try:
        result = subprocess.run(
            ['python', str(SCRIPTS_DIR / 'router.py'), '--prompt', prompt],
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT)
        )
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
        return {"intent": "CHAT", "confidence": 0.5, "error": result.stderr}
    except subprocess.TimeoutExpired:
        return {"intent": "CHAT", "confidence": 0.5, "error": "Router timeout"}
    except json.JSONDecodeError:
        return {"intent": "CHAT", "confidence": 0.5, "error": "Invalid router response"}
    except Exception as e:
        return {"intent": "CHAT", "confidence": 0.5, "error": str(e)}
