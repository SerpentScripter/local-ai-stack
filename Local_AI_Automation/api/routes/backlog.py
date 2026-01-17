"""
Backlog CRUD Routes
Handles all backlog item operations
"""
from fastapi import APIRouter, HTTPException, Query
from typing import List, Optional

from ..models import BacklogItemCreate, BacklogItemUpdate
from ..database import get_db, generate_external_id, log_event

router = APIRouter(prefix="/items", tags=["Backlog"])


@router.get("", response_model=List[dict])
def list_items(
    status: Optional[str] = Query(None, description="Filter by status"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0)
):
    """List backlog items with optional filters"""
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

        query += " ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END, created_at DESC"
        query += f" LIMIT {limit} OFFSET {offset}"

        rows = conn.execute(query, params).fetchall()
        return [dict(row) for row in rows]


@router.get("/{external_id}")
def get_item(external_id: str):
    """Get a single backlog item by external ID"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM backlog_items WHERE external_id = ?",
            (external_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")
        return dict(row)


@router.post("", status_code=201)
def create_item(item: BacklogItemCreate):
    """Create a new backlog item"""
    external_id = generate_external_id()
    with get_db() as conn:
        cursor = conn.execute(
            """INSERT INTO backlog_items
               (external_id, title, description, category, priority, item_type,
                next_action, estimated_effort, source_channel, source_message_ts,
                source_user, raw_input, status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'open')""",
            (external_id, item.title, item.description, item.category,
             item.priority, item.item_type, item.next_action, item.estimated_effort,
             item.source_channel, item.source_message_ts, item.source_user, item.raw_input)
        )
        item_id = cursor.lastrowid
        log_event(conn, item_id, external_id, "created", {"title": item.title})
        return {"external_id": external_id, "id": item_id, "status": "created"}


@router.patch("/{external_id}")
def update_item(external_id: str, updates: BacklogItemUpdate):
    """Update a backlog item"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM backlog_items WHERE external_id = ?",
            (external_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        item_id = row["id"]
        update_fields = []
        params = []

        for field, value in updates.model_dump(exclude_unset=True).items():
            if value is not None:
                update_fields.append(f"{field} = ?")
                params.append(value)

        if not update_fields:
            raise HTTPException(status_code=400, detail="No fields to update")

        params.append(external_id)
        conn.execute(
            f"UPDATE backlog_items SET {', '.join(update_fields)} WHERE external_id = ?",
            params
        )
        log_event(conn, item_id, external_id, "updated", updates.model_dump(exclude_unset=True))
        return {"external_id": external_id, "status": "updated"}


@router.post("/{external_id}/done")
def mark_done(external_id: str):
    """Mark a backlog item as done"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, status FROM backlog_items WHERE external_id = ?",
            (external_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        if row["status"] == "done":
            raise HTTPException(status_code=400, detail="Item is already done")

        conn.execute(
            "UPDATE backlog_items SET status = 'done', completed_at = CURRENT_TIMESTAMP WHERE external_id = ?",
            (external_id,)
        )
        log_event(conn, row["id"], external_id, "completed")
        return {"external_id": external_id, "status": "done"}


@router.post("/{external_id}/priority/{new_priority}")
def change_priority(external_id: str, new_priority: str):
    """Change the priority of a backlog item"""
    if new_priority not in ["P0", "P1", "P2", "P3"]:
        raise HTTPException(status_code=400, detail="Invalid priority. Use P0, P1, P2, or P3")

    with get_db() as conn:
        row = conn.execute(
            "SELECT id, priority FROM backlog_items WHERE external_id = ?",
            (external_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Item not found")

        old_priority = row["priority"]
        conn.execute(
            "UPDATE backlog_items SET priority = ? WHERE external_id = ?",
            (new_priority, external_id)
        )
        log_event(conn, row["id"], external_id, "priority_changed",
                  {"old": old_priority, "new": new_priority})
        return {"external_id": external_id, "priority": new_priority}


@router.get("/{external_id}/events")
def get_item_events(external_id: str):
    """Get the event history for a backlog item"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM backlog_events
               WHERE external_id = ?
               ORDER BY created_at DESC""",
            (external_id,)
        ).fetchall()
        return [dict(row) for row in rows]
