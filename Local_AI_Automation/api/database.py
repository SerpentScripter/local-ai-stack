"""
Database utilities for the Local AI Hub API
"""
import sqlite3
import uuid
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
from typing import Optional

# Database path - configurable via environment
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "backlog" / "backlog.db"


@contextmanager
def get_db():
    """Context manager for database connections"""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def generate_external_id() -> str:
    """Generate a unique external ID in format BL-YYMMDD-XXXXXX"""
    date_part = datetime.now().strftime("%y%m%d")
    unique_part = uuid.uuid4().hex[:6].upper()
    return f"BL-{date_part}-{unique_part}"


def log_event(
    conn,
    item_id: int,
    external_id: str,
    event_type: str,
    event_data: dict = None,
    actor: str = "api"
):
    """Log an event to the backlog_events table"""
    import json
    conn.execute(
        """INSERT INTO backlog_events (item_id, external_id, event_type, event_data, actor_type, actor_id)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (item_id, external_id, event_type, json.dumps(event_data or {}), "system", actor)
    )


def get_item_by_external_id(conn, external_id: str) -> Optional[dict]:
    """Fetch a backlog item by its external ID"""
    row = conn.execute(
        "SELECT * FROM backlog_items WHERE external_id = ?",
        (external_id,)
    ).fetchone()
    return dict(row) if row else None


def init_database():
    """Initialize the database schema if needed"""
    schema_path = PROJECT_ROOT / "data" / "backlog" / "schema.sql"
    if schema_path.exists():
        with get_db() as conn:
            with open(schema_path) as f:
                conn.executescript(f.read())


def init_job_queue_table():
    """Initialize the job queue table"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS job_queue (
                job_id TEXT PRIMARY KEY,
                func_name TEXT NOT NULL,
                priority TEXT DEFAULT 'normal',
                status TEXT DEFAULT 'queued',
                created_at TEXT NOT NULL,
                started_at TEXT,
                ended_at TEXT,
                args TEXT,
                kwargs TEXT,
                result TEXT,
                error TEXT,
                meta TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_job_queue_status ON job_queue(status);
            CREATE INDEX IF NOT EXISTS idx_job_queue_priority ON job_queue(priority);
            CREATE INDEX IF NOT EXISTS idx_job_queue_created ON job_queue(created_at);
        """)
