-- Backlog Database Schema
-- SQLite database for task tracking
-- Location: data/backlog/backlog.db

-- ============================================
-- BACKLOG ITEMS
-- ============================================

CREATE TABLE IF NOT EXISTS backlog_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE NOT NULL,  -- UUID for external reference

    -- Core fields
    title TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL DEFAULT 'Personal',
    secondary_tags TEXT,  -- JSON array of tags

    -- Priority and type
    priority TEXT NOT NULL DEFAULT 'P2' CHECK (priority IN ('P0', 'P1', 'P2', 'P3')),
    item_type TEXT NOT NULL DEFAULT 'personal' CHECK (item_type IN ('personal', 'work', 'mixed')),

    -- Action tracking
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'needs_clarification', 'in_progress', 'blocked', 'done', 'cancelled')),
    next_action TEXT,
    estimated_effort TEXT CHECK (estimated_effort IN ('S', 'M', 'L', NULL)),
    dependencies TEXT,  -- JSON array of external_ids

    -- Source tracking
    source_channel TEXT,  -- Slack channel
    source_message_ts TEXT,  -- Slack message timestamp
    source_user TEXT,

    -- Timestamps
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    completed_at DATETIME,

    -- Metadata
    llm_confidence REAL,  -- 0.0-1.0 confidence score
    raw_input TEXT  -- Original user message
);

-- Index for common queries
CREATE INDEX IF NOT EXISTS idx_backlog_status ON backlog_items(status);
CREATE INDEX IF NOT EXISTS idx_backlog_priority ON backlog_items(priority);
CREATE INDEX IF NOT EXISTS idx_backlog_category ON backlog_items(category);
CREATE INDEX IF NOT EXISTS idx_backlog_created ON backlog_items(created_at);

-- ============================================
-- EVENT LOG (Event Sourcing)
-- ============================================

CREATE TABLE IF NOT EXISTS backlog_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    external_id TEXT NOT NULL,  -- Item's external_id

    event_type TEXT NOT NULL,  -- created, updated, status_changed, priority_changed, clarified, completed
    event_data TEXT,  -- JSON with change details

    -- Actor
    actor_type TEXT NOT NULL DEFAULT 'system' CHECK (actor_type IN ('user', 'system', 'llm')),
    actor_id TEXT,

    -- Timestamp
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (item_id) REFERENCES backlog_items(id)
);

CREATE INDEX IF NOT EXISTS idx_events_item ON backlog_events(item_id);
CREATE INDEX IF NOT EXISTS idx_events_type ON backlog_events(event_type);

-- ============================================
-- CLARIFICATION QUESTIONS
-- ============================================

CREATE TABLE IF NOT EXISTS clarifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,

    question TEXT NOT NULL,
    answer TEXT,

    asked_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    answered_at DATETIME,

    -- Slack thread tracking
    thread_ts TEXT,

    FOREIGN KEY (item_id) REFERENCES backlog_items(id)
);

-- ============================================
-- CATEGORIES
-- ============================================

CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    parent_category TEXT,
    color TEXT,  -- Hex color for UI
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Insert default categories
INSERT OR IGNORE INTO categories (name, description) VALUES
    ('Consulting Lead / Sales', 'New business opportunities and sales activities'),
    ('Client Delivery', 'Active client work and deliverables'),
    ('Security / GRC', 'Security, governance, risk, and compliance tasks'),
    ('AI / Automation', 'AI tooling and automation projects'),
    ('Software / App Dev', 'Software development and applications'),
    ('Ops / Admin / Finance', 'Operations, administration, and financial tasks'),
    ('Learning / Research', 'Learning, reading, and research activities'),
    ('Personal', 'Personal tasks and items');

-- ============================================
-- VIEWS
-- ============================================

-- Active items by priority
CREATE VIEW IF NOT EXISTS v_active_by_priority AS
SELECT
    external_id,
    title,
    category,
    priority,
    status,
    next_action,
    created_at,
    JULIANDAY('now') - JULIANDAY(created_at) as days_old
FROM backlog_items
WHERE status NOT IN ('done', 'cancelled')
ORDER BY
    CASE priority
        WHEN 'P0' THEN 1
        WHEN 'P1' THEN 2
        WHEN 'P2' THEN 3
        WHEN 'P3' THEN 4
    END,
    created_at ASC;

-- Items needing clarification
CREATE VIEW IF NOT EXISTS v_needs_clarification AS
SELECT
    b.external_id,
    b.title,
    b.raw_input,
    c.question,
    c.asked_at
FROM backlog_items b
JOIN clarifications c ON b.id = c.item_id
WHERE b.status = 'needs_clarification'
AND c.answer IS NULL
ORDER BY c.asked_at ASC;

-- Daily summary stats
CREATE VIEW IF NOT EXISTS v_daily_stats AS
SELECT
    DATE(created_at) as date,
    COUNT(*) as items_created,
    SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) as items_completed,
    SUM(CASE WHEN priority = 'P0' THEN 1 ELSE 0 END) as p0_items,
    SUM(CASE WHEN priority = 'P1' THEN 1 ELSE 0 END) as p1_items
FROM backlog_items
GROUP BY DATE(created_at)
ORDER BY date DESC;

-- ============================================
-- TRIGGERS
-- ============================================

-- Auto-update updated_at timestamp
CREATE TRIGGER IF NOT EXISTS trg_backlog_updated
AFTER UPDATE ON backlog_items
BEGIN
    UPDATE backlog_items
    SET updated_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;

-- Log status changes
CREATE TRIGGER IF NOT EXISTS trg_log_status_change
AFTER UPDATE OF status ON backlog_items
WHEN OLD.status != NEW.status
BEGIN
    INSERT INTO backlog_events (item_id, external_id, event_type, event_data, actor_type)
    VALUES (
        NEW.id,
        NEW.external_id,
        'status_changed',
        json_object('old_status', OLD.status, 'new_status', NEW.status),
        'system'
    );
END;

-- Log priority changes
CREATE TRIGGER IF NOT EXISTS trg_log_priority_change
AFTER UPDATE OF priority ON backlog_items
WHEN OLD.priority != NEW.priority
BEGIN
    INSERT INTO backlog_events (item_id, external_id, event_type, event_data, actor_type)
    VALUES (
        NEW.id,
        NEW.external_id,
        'priority_changed',
        json_object('old_priority', OLD.priority, 'new_priority', NEW.priority),
        'system'
    );
END;

-- Set completed_at when status becomes done
CREATE TRIGGER IF NOT EXISTS trg_set_completed_at
AFTER UPDATE OF status ON backlog_items
WHEN NEW.status = 'done' AND OLD.status != 'done'
BEGIN
    UPDATE backlog_items
    SET completed_at = CURRENT_TIMESTAMP
    WHERE id = NEW.id;
END;
