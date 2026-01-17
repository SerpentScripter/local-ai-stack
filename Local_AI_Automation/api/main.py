"""
Local AI Hub API - Main Application
Modular FastAPI backend for the TR Automation Hub
"""
import os
import time
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .routes import (
    backlog, agents, services, chat, metrics, workflows, auth, secrets,
    jobs, orchestration, webhooks, slack,
    # Phase 4: Intelligence Layer
    workflow_gen, prioritization, assessment, benchmarks, updates,
    # Phase 5: Scale & Polish
    distributed,
    # Phase 6: Kanban & Worktree
    kanban,
    worktree
)
from .websocket import manager
from .database import get_db, init_job_queue_table
from .auth import AUTH_ENABLED
from .logging_config import api_logger, log_request

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
STATIC_DIR = PROJECT_ROOT / "static"

# Security: Restrict CORS to localhost origins only
ALLOWED_ORIGINS = [
    "http://localhost:8765",
    "http://127.0.0.1:8765",
    "http://localhost:3000",  # Open WebUI
    "http://127.0.0.1:3000",
    "http://localhost:7860",  # Langflow
    "http://127.0.0.1:7860",
    "http://localhost:5678",  # n8n
    "http://127.0.0.1:5678",
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup
    print("[API] Starting Local AI Hub API v2.0...")
    print(f"[API] Static files: {STATIC_DIR}")
    # Initialize database tables
    try:
        init_job_queue_table()
        print("[API] Job queue table initialized")
    except Exception as e:
        print(f"[API] Warning: Could not init job queue table: {e}")
    yield
    # Shutdown
    print("[API] Shutting down...")


# Create FastAPI application
app = FastAPI(
    title="Local AI Hub API",
    description="Modular API for TR Automation Hub - service control, LLM chat, agents, and monitoring",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# Request logging middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing"""
    start_time = time.time()

    # Skip logging for static files and health checks
    skip_paths = ["/static", "/health", "/favicon.ico"]
    should_log = not any(request.url.path.startswith(p) for p in skip_paths)

    response = await call_next(request)

    if should_log:
        duration_ms = (time.time() - start_time) * 1000
        log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms
        )

    return response


# Mount static files
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Include all route modules
app.include_router(auth.router)  # Auth first for token generation
app.include_router(backlog.router)
app.include_router(agents.router)
app.include_router(services.router)
app.include_router(chat.router)
app.include_router(metrics.router)
app.include_router(workflows.router)
app.include_router(secrets.router)
app.include_router(jobs.router)
app.include_router(orchestration.router)
app.include_router(webhooks.router)
app.include_router(slack.router)
# Phase 4: Intelligence Layer
app.include_router(workflow_gen.router)
app.include_router(prioritization.router)
app.include_router(assessment.router)
app.include_router(benchmarks.router)
app.include_router(updates.router)
# Phase 5: Scale & Polish
app.include_router(distributed.router)
# Phase 6: Kanban & Worktree
app.include_router(kanban.router)
app.include_router(worktree.router)


# Root routes
@app.get("/")
def serve_dashboard():
    """Serve the main dashboard"""
    index_path = STATIC_DIR / "index.html"
    if index_path.exists():
        return FileResponse(str(index_path))
    return {"message": "Local AI Hub API", "docs": "/docs"}


@app.get("/api/info")
def api_info():
    """API information and version"""
    return {
        "name": "Local AI Hub API",
        "version": "3.0.0",
        "modules": [
            "auth", "backlog", "agents", "services", "chat", "metrics",
            "workflows", "secrets", "jobs", "orchestration", "webhooks", "slack",
            "workflow-gen", "prioritization", "assessment", "benchmarks", "updates"
        ],
        "auth_enabled": AUTH_ENABLED,
        "docs": "/docs"
    }


@app.get("/health")
def health():
    """Health check endpoint"""
    from .database import DB_PATH
    return {
        "status": "healthy",
        "database": str(DB_PATH)
    }


@app.get("/categories")
def list_categories():
    """List available backlog categories"""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM categories").fetchall()
        return [dict(row) for row in rows]


@app.get("/stats")
def get_stats():
    """Get backlog statistics"""
    with get_db() as conn:
        stats = {}

        # Total counts by status
        rows = conn.execute(
            "SELECT status, COUNT(*) as count FROM backlog_items GROUP BY status"
        ).fetchall()
        stats["by_status"] = {row["status"]: row["count"] for row in rows}

        # Total counts by priority
        rows = conn.execute(
            "SELECT priority, COUNT(*) as count FROM backlog_items GROUP BY priority"
        ).fetchall()
        stats["by_priority"] = {row["priority"]: row["count"] for row in rows}

        # Total counts by category
        rows = conn.execute(
            "SELECT category, COUNT(*) as count FROM backlog_items GROUP BY category"
        ).fetchall()
        stats["by_category"] = {row["category"]: row["count"] for row in rows}

        # Recent activity
        stats["recent_created"] = conn.execute(
            "SELECT COUNT(*) FROM backlog_items WHERE created_at >= datetime('now', '-7 days')"
        ).fetchone()[0]
        stats["recent_completed"] = conn.execute(
            "SELECT COUNT(*) FROM backlog_items WHERE completed_at >= datetime('now', '-7 days')"
        ).fetchone()[0]

        return stats


@app.get("/events/{external_id}")
def get_item_events(external_id: str):
    """Get event history for a backlog item"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM backlog_events
               WHERE external_id = ?
               ORDER BY created_at DESC""",
            (external_id,)
        ).fetchall()
        return [dict(row) for row in rows]


# WebSocket endpoint
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=35)
                # Handle ping/pong
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send heartbeat ping
                await websocket.send_json({"type": "ping"})
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"[WS] Error: {e}")
        manager.disconnect(websocket)


def create_app() -> FastAPI:
    """Factory function for creating the app (useful for testing)"""
    return app
