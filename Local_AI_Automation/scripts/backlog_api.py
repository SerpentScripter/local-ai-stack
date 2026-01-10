#!/usr/bin/env python3
"""
Local Backlog API Server
Provides REST API for n8n to interact with the backlog database.

Run: python backlog_api.py
Access: http://localhost:8765
"""

import sqlite3
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional, List
from contextlib import contextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import uvicorn

import os
import socket
from dotenv import load_dotenv

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Configuration
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "backlog" / "backlog.db"
LOG_DIR = PROJECT_ROOT / "data" / "logs"
PORT = int(os.getenv("BACKLOG_API_PORT", 8765))
HOST = os.getenv("BACKLOG_API_HOST", "127.0.0.1")

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0

app = FastAPI(
    title="Backlog API",
    description="Local API for TR Automation Hub backlog management",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static Files
STATIC_DIR = PROJECT_ROOT / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# Models
class BacklogItemCreate(BaseModel):
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
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    next_action: Optional[str] = None
    estimated_effort: Optional[str] = None

class BacklogItem(BaseModel):
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
    updated_at: str
    completed_at: Optional[str]

@contextmanager
def get_db():
    """Database connection context manager."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def generate_external_id():
    """Generate unique external ID."""
    return f"BL-{datetime.now().strftime('%y%m%d')}-{uuid.uuid4().hex[:6].upper()}"

def log_event(conn, item_id: int, external_id: str, event_type: str, event_data: dict = None, actor: str = "api"):
    """Log an event to the backlog_events table."""
    conn.execute("""
        INSERT INTO backlog_events (item_id, external_id, event_type, event_data, actor_type, actor_id)
        VALUES (?, ?, ?, ?, 'system', ?)
    """, (item_id, external_id, event_type, json.dumps(event_data) if event_data else None, actor))

# API Endpoints

@app.get("/")
def serve_dashboard():
    """Serve the management dashboard."""
    if STATIC_DIR.exists():
        return FileResponse(STATIC_DIR / "index.html")
    return {
        "message": "Dashboard not found. Static files missing.",
        "api_info": "/api/info"
    }

@app.get("/api/info")
def api_info():
    """API info."""
    return {
        "name": "Backlog API",
        "version": "1.0.0",
        "endpoints": ["/items", "/items/{id}", "/categories", "/stats"]
    }

@app.get("/health")
def health():
    """Health check."""
    try:
        with get_db() as conn:
            conn.execute("SELECT 1")
        return {"status": "healthy", "database": str(DB_PATH)}
    except Exception as e:
        raise HTTPException(status_code=503, detail=str(e))

@app.get("/items", response_model=List[dict])
def list_items(
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, description="Max items to return"),
    offset: int = Query(0, description="Offset for pagination")
):
    """List backlog items with optional filters."""
    with get_db() as conn:
        query = "SELECT * FROM backlog_items WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if priority:
            query += " AND priority = ?"
            params.append(priority)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += """
            ORDER BY
                CASE priority WHEN 'P0' THEN 1 WHEN 'P1' THEN 2 WHEN 'P2' THEN 3 WHEN 'P3' THEN 4 END,
                created_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])

        cursor = conn.execute(query, params)
        items = [dict(row) for row in cursor.fetchall()]
        return items

@app.get("/items/{external_id}")
def get_item(external_id: str):
    """Get a single backlog item."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT * FROM backlog_items WHERE external_id = ?",
            (external_id,)
        )
        item = cursor.fetchone()
        if not item:
            raise HTTPException(status_code=404, detail="Item not found")
        return dict(item)

@app.post("/items", status_code=201)
def create_item(item: BacklogItemCreate):
    """Create a new backlog item."""
    external_id = generate_external_id()

    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO backlog_items
            (external_id, title, description, category, priority, item_type,
             next_action, estimated_effort, source_channel, source_message_ts,
             source_user, raw_input, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')
        """, (
            external_id, item.title, item.description, item.category,
            item.priority, item.item_type, item.next_action,
            item.estimated_effort, item.source_channel,
            item.source_message_ts, item.source_user, item.raw_input
        ))

        item_id = cursor.lastrowid
        log_event(conn, item_id, external_id, "created", item.dict())
        conn.commit()

        return {
            "external_id": external_id,
            "id": item_id,
            "message": "Item created successfully"
        }

@app.patch("/items/{external_id}")
def update_item(external_id: str, updates: BacklogItemUpdate):
    """Update a backlog item."""
    with get_db() as conn:
        # Get current item
        cursor = conn.execute(
            "SELECT id FROM backlog_items WHERE external_id = ?",
            (external_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        item_id = row["id"]

        # Build update query
        update_fields = []
        params = []
        for field, value in updates.dict(exclude_unset=True).items():
            if value is not None:
                update_fields.append(f"{field} = ?")
                params.append(value)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No updates provided")

        params.append(external_id)
        query = f"UPDATE backlog_items SET {', '.join(update_fields)} WHERE external_id = ?"
        conn.execute(query, params)

        log_event(conn, item_id, external_id, "updated", updates.dict(exclude_unset=True))
        conn.commit()

        return {"message": "Item updated", "external_id": external_id}

@app.post("/items/{external_id}/done")
def mark_done(external_id: str):
    """Mark item as done."""
    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, status FROM backlog_items WHERE external_id = ?",
            (external_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        conn.execute("""
            UPDATE backlog_items
            SET status = 'done', completed_at = CURRENT_TIMESTAMP
            WHERE external_id = ?
        """, (external_id,))

        log_event(conn, row["id"], external_id, "completed",
                  {"previous_status": row["status"]})
        conn.commit()

        return {"message": "Item marked as done", "external_id": external_id}

@app.post("/items/{external_id}/priority/{new_priority}")
def change_priority(external_id: str, new_priority: str):
    """Change item priority."""
    if new_priority not in ["P0", "P1", "P2", "P3"]:
        raise HTTPException(status_code=400, detail="Invalid priority")

    with get_db() as conn:
        cursor = conn.execute(
            "SELECT id, priority FROM backlog_items WHERE external_id = ?",
            (external_id,)
        )
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        conn.execute(
            "UPDATE backlog_items SET priority = ? WHERE external_id = ?",
            (new_priority, external_id)
        )

        log_event(conn, row["id"], external_id, "priority_changed",
                  {"old": row["priority"], "new": new_priority})
        conn.commit()

        return {"message": f"Priority changed to {new_priority}", "external_id": external_id}

@app.get("/categories")
def list_categories():
    """List all categories."""
    with get_db() as conn:
        cursor = conn.execute("SELECT name, description FROM categories ORDER BY name")
        return [dict(row) for row in cursor.fetchall()]

@app.get("/stats")
def get_stats():
    """Get backlog statistics."""
    with get_db() as conn:
        stats = {}

        # Total counts
        cursor = conn.execute("SELECT COUNT(*) as total FROM backlog_items")
        stats["total_items"] = cursor.fetchone()["total"]

        # By status
        cursor = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM backlog_items
            GROUP BY status
        """)
        stats["by_status"] = {row["status"]: row["count"] for row in cursor.fetchall()}

        # By priority
        cursor = conn.execute("""
            SELECT priority, COUNT(*) as count
            FROM backlog_items
            WHERE status NOT IN ('done', 'cancelled')
            GROUP BY priority
        """)
        stats["by_priority"] = {row["priority"]: row["count"] for row in cursor.fetchall()}

        # By category
        cursor = conn.execute("""
            SELECT category, COUNT(*) as count
            FROM backlog_items
            WHERE status NOT IN ('done', 'cancelled')
            GROUP BY category
            ORDER BY count DESC
        """)
        stats["by_category"] = {row["category"]: row["count"] for row in cursor.fetchall()}

        # Recent activity
        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM backlog_items
            WHERE created_at >= datetime('now', '-7 days')
        """)
        stats["created_last_7_days"] = cursor.fetchone()["count"]

        cursor = conn.execute("""
            SELECT COUNT(*) as count FROM backlog_items
            WHERE completed_at >= datetime('now', '-7 days')
        """)
        stats["completed_last_7_days"] = cursor.fetchone()["count"]

        return stats

@app.get("/events/{external_id}")
def get_item_events(external_id: str):
    """Get event history for an item."""
    with get_db() as conn:
        cursor = conn.execute("""
            SELECT event_type, event_data, actor_type, actor_id, created_at
            FROM backlog_events
            WHERE external_id = ?
            ORDER BY created_at DESC
        """, (external_id,))
        return [dict(row) for row in cursor.fetchall()]

if __name__ == "__main__":
    try:
        # Ensure log directory exists
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        
        print(f"========================================")
        print(f" Starting Backlog API")
        print(f" URL: http://{HOST}:{PORT}")
        print(f" Database: {DB_PATH}")
        print(f"========================================")
        
        if is_port_in_use(PORT):
            print(f"CRITICAL ERROR: Port {PORT} is already in use!")
            print(f"Please change BACKLOG_API_PORT in your .env file.")
            sys.exit(1)
            
        if not DB_PATH.exists():
            print(f"WARNING: Database file not found at {DB_PATH}")
            print(f"Please run init_database.py first.")
            
        uvicorn.run(app, host=HOST, port=PORT, log_level="info")
    except Exception as e:
        print(f"FATAL ERROR during startup: {e}")
        import traceback
        traceback.print_exc()
