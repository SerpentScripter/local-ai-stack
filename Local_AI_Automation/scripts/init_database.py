#!/usr/bin/env python3
"""
Initialize the backlog SQLite database.
Run: python init_database.py
"""

import sqlite3
import os
import json
from datetime import datetime
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "backlog"
DB_PATH = DATA_DIR / "backlog.db"
SCHEMA_PATH = DATA_DIR / "schema.sql"

def init_database():
    """Initialize the database with schema."""
    print("Initializing Backlog Database...")

    # Ensure directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Backup existing database
    if DB_PATH.exists():
        backup_path = DB_PATH.with_suffix(f".backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db")
        print(f"Backing up existing database to: {backup_path}")
        os.rename(DB_PATH, backup_path)

    # Connect and create schema
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Read and execute schema
    if SCHEMA_PATH.exists():
        with open(SCHEMA_PATH, 'r') as f:
            schema = f.read()
        cursor.executescript(schema)
        print("Schema loaded from file.")
    else:
        # Inline schema if file doesn't exist
        create_schema(cursor)
        print("Schema created inline.")

    conn.commit()

    # Verify tables
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = cursor.fetchall()
    print(f"\nTables created: {[t[0] for t in tables]}")

    # Show categories
    cursor.execute("SELECT name FROM categories")
    categories = cursor.fetchall()
    print(f"Categories: {[c[0] for c in categories]}")

    conn.close()
    print(f"\nDatabase initialized: {DB_PATH}")
    return DB_PATH

def create_schema(cursor):
    """Create schema inline."""
    cursor.executescript("""
    -- Backlog Items
    CREATE TABLE IF NOT EXISTS backlog_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        external_id TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        description TEXT,
        category TEXT NOT NULL DEFAULT 'Personal',
        secondary_tags TEXT,
        priority TEXT NOT NULL DEFAULT 'P2' CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
        item_type TEXT NOT NULL DEFAULT 'personal' CHECK (item_type IN ('personal', 'work', 'mixed')),
        status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'needs_clarification', 'in_progress', 'blocked', 'done', 'cancelled')),
        next_action TEXT,
        estimated_effort TEXT CHECK (estimated_effort IN ('S', 'M', 'L', NULL)),
        dependencies TEXT,
        source_channel TEXT,
        source_message_ts TEXT,
        source_user TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        completed_at DATETIME,
        llm_confidence REAL,
        raw_input TEXT
    );

    -- Event Log
    CREATE TABLE IF NOT EXISTS backlog_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        external_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        event_data TEXT,
        actor_type TEXT NOT NULL DEFAULT 'system',
        actor_id TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (item_id) REFERENCES backlog_items(id)
    );

    -- Clarifications
    CREATE TABLE IF NOT EXISTS clarifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_id INTEGER NOT NULL,
        question TEXT NOT NULL,
        answer TEXT,
        asked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        answered_at DATETIME,
        thread_ts TEXT,
        FOREIGN KEY (item_id) REFERENCES backlog_items(id)
    );

    -- Categories
    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT,
        parent_category TEXT,
        color TEXT,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );

    -- Default categories
    INSERT OR IGNORE INTO categories (name, description) VALUES
        ('Consulting Lead / Sales', 'New business opportunities'),
        ('Client Delivery', 'Active client work'),
        ('Security / GRC', 'Security and compliance'),
        ('AI / Automation', 'AI and automation projects'),
        ('Software / App Dev', 'Software development'),
        ('Ops / Admin / Finance', 'Operations and admin'),
        ('Learning / Research', 'Learning activities'),
        ('Personal', 'Personal tasks');

    -- Indexes
    CREATE INDEX IF NOT EXISTS idx_backlog_status ON backlog_items(status);
    CREATE INDEX IF NOT EXISTS idx_backlog_priority ON backlog_items(priority);
    CREATE INDEX IF NOT EXISTS idx_backlog_category ON backlog_items(category);
    """)

def add_sample_items():
    """Add sample backlog items for testing."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    samples = [
        {
            "external_id": "BL-TEST001",
            "title": "Review DORA compliance requirements",
            "description": "Analyze DORA requirements for client's financial services platform",
            "category": "Security / GRC",
            "priority": "P1",
            "item_type": "work",
            "status": "open",
            "next_action": "Download DORA regulation document",
            "estimated_effort": "L",
            "raw_input": "Need to review DORA compliance requirements for the banking client - this is important"
        },
        {
            "external_id": "BL-TEST002",
            "title": "Set up local RAG system",
            "description": "Configure RAG pipeline with Ollama and vector database",
            "category": "AI / Automation",
            "priority": "P2",
            "item_type": "personal",
            "status": "open",
            "next_action": "Research vector database options",
            "estimated_effort": "M",
            "raw_input": "I want to build a local RAG system for my notes"
        },
        {
            "external_id": "BL-TEST003",
            "title": "Prepare ISO 27001 audit checklist",
            "description": "Create checklist for upcoming ISO 27001 surveillance audit",
            "category": "Client Delivery",
            "priority": "P0",
            "item_type": "work",
            "status": "in_progress",
            "next_action": "Review previous audit findings",
            "estimated_effort": "M",
            "raw_input": "URGENT: Need ISO 27001 audit checklist ready by Friday"
        },
        {
            "external_id": "BL-TEST004",
            "title": "Learn Claude Code hooks",
            "description": "Explore Claude Code hook system for automation",
            "category": "Learning / Research",
            "priority": "P3",
            "item_type": "personal",
            "status": "open",
            "next_action": "Read documentation",
            "estimated_effort": "S",
            "raw_input": "nice to have: learn about claude code hooks when I have time"
        }
    ]

    for item in samples:
        try:
            cursor.execute("""
                INSERT INTO backlog_items
                (external_id, title, description, category, priority, item_type, status, next_action, estimated_effort, raw_input)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                item["external_id"], item["title"], item["description"],
                item["category"], item["priority"], item["item_type"],
                item["status"], item["next_action"], item["estimated_effort"],
                item["raw_input"]
            ))

            # Log creation event
            cursor.execute("""
                INSERT INTO backlog_events (item_id, external_id, event_type, event_data, actor_type)
                VALUES (?, ?, 'created', ?, 'system')
            """, (cursor.lastrowid, item["external_id"], json.dumps({"source": "test_data"})))

        except sqlite3.IntegrityError:
            print(f"Item {item['external_id']} already exists, skipping.")

    conn.commit()
    conn.close()
    print(f"\nAdded {len(samples)} sample items.")

def show_items():
    """Display current backlog items."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT external_id, priority, status, title, category
        FROM backlog_items
        ORDER BY
            CASE priority WHEN 'P0' THEN 1 WHEN 'P1' THEN 2 WHEN 'P2' THEN 3 WHEN 'P3' THEN 4 END,
            created_at
    """)

    items = cursor.fetchall()

    print("\n" + "="*80)
    print("BACKLOG ITEMS")
    print("="*80)
    print(f"{'ID':<12} {'Pri':<4} {'Status':<15} {'Title':<30} {'Category':<20}")
    print("-"*80)

    for item in items:
        print(f"{item[0]:<12} {item[1]:<4} {item[2]:<15} {item[3][:28]:<30} {item[4]:<20}")

    conn.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--with-samples":
        init_database()
        add_sample_items()
        show_items()
    elif len(sys.argv) > 1 and sys.argv[1] == "--show":
        show_items()
    else:
        init_database()
        print("\nRun with --with-samples to add test data")
        print("Run with --show to display items")
