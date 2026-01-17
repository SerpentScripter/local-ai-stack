"""
Shared Memory System
Hybrid Redis + SQLite memory for agent context sharing

Provides:
- Fast in-memory storage (Redis) for active sessions
- Persistent storage (SQLite) for long-term memory
- Vector similarity search for semantic retrieval
- Blackboard pattern for agent coordination
"""
import os
import json
import hashlib
import sqlite3
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Union
from dataclasses import dataclass, asdict
from enum import Enum
from contextlib import contextmanager

# Try to import Redis
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Try to import numpy for vector operations
try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False

from .database import get_db, DB_PATH
from .logging_config import api_logger


# Configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_MEMORY_DB", 1))  # Separate DB from job queue
MEMORY_PREFIX = "mem:"
DEFAULT_TTL = 3600 * 24  # 24 hours


class MemoryScope(Enum):
    """Memory visibility scopes"""
    GLOBAL = "global"          # Visible to all agents
    SESSION = "session"        # Visible within a session
    AGENT = "agent"            # Private to specific agent
    GROUP = "group"            # Visible to agent group


@dataclass
class MemoryEntry:
    """A single memory entry"""
    key: str
    value: Any
    scope: MemoryScope
    owner: Optional[str] = None  # Agent ID or session ID
    created_at: datetime = None
    updated_at: datetime = None
    ttl: Optional[int] = None
    tags: List[str] = None
    embedding: List[float] = None  # For vector search

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()
        if self.updated_at is None:
            self.updated_at = self.created_at
        if self.tags is None:
            self.tags = []


class SharedMemory:
    """
    Hybrid memory system with Redis caching and SQLite persistence

    Features:
    - Fast reads/writes via Redis
    - Automatic persistence to SQLite
    - TTL-based expiration
    - Scope-based access control
    - Optional vector similarity search
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._connected = False
        self._init_database()

    def _init_database(self):
        """Initialize SQLite tables for persistent memory"""
        with get_db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS shared_memory (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    scope TEXT DEFAULT 'global',
                    owner TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    ttl INTEGER,
                    tags TEXT,
                    embedding BLOB
                );

                CREATE INDEX IF NOT EXISTS idx_memory_scope ON shared_memory(scope);
                CREATE INDEX IF NOT EXISTS idx_memory_owner ON shared_memory(owner);
                CREATE INDEX IF NOT EXISTS idx_memory_updated ON shared_memory(updated_at);

                CREATE TABLE IF NOT EXISTS memory_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    changed_at TEXT NOT NULL,
                    changed_by TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_history_key ON memory_history(key);
            """)

    def connect_redis(self) -> bool:
        """Connect to Redis for fast access"""
        if not REDIS_AVAILABLE:
            api_logger.debug("Redis not available, using SQLite only")
            return False

        try:
            self._redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                decode_responses=True
            )
            self._redis.ping()
            self._connected = True
            api_logger.info("Shared memory connected to Redis")
            return True
        except Exception as e:
            api_logger.warning(f"Redis connection failed: {e}, using SQLite only")
            self._connected = False
            return False

    # ==================== Core Operations ====================

    def set(
        self,
        key: str,
        value: Any,
        scope: MemoryScope = MemoryScope.GLOBAL,
        owner: Optional[str] = None,
        ttl: Optional[int] = DEFAULT_TTL,
        tags: Optional[List[str]] = None,
        persist: bool = True
    ) -> bool:
        """
        Store a value in shared memory

        Args:
            key: Unique key for the value
            value: Value to store (will be JSON serialized)
            scope: Visibility scope
            owner: Agent ID or session ID for scoped access
            ttl: Time-to-live in seconds (None for permanent)
            tags: Optional tags for categorization
            persist: Whether to persist to SQLite

        Returns:
            True if stored successfully
        """
        full_key = self._make_key(key, scope, owner)
        json_value = json.dumps(value)
        now = datetime.utcnow()

        # Store in Redis if available
        if self._connected:
            try:
                if ttl:
                    self._redis.setex(full_key, ttl, json_value)
                else:
                    self._redis.set(full_key, json_value)

                # Store metadata
                meta_key = f"{full_key}:meta"
                self._redis.hset(meta_key, mapping={
                    "scope": scope.value,
                    "owner": owner or "",
                    "created_at": now.isoformat(),
                    "updated_at": now.isoformat(),
                    "tags": json.dumps(tags or [])
                })
                if ttl:
                    self._redis.expire(meta_key, ttl)

            except Exception as e:
                api_logger.error(f"Redis set failed: {e}")

        # Persist to SQLite
        if persist:
            try:
                with get_db() as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO shared_memory
                        (key, value, scope, owner, created_at, updated_at, ttl, tags)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        full_key, json_value, scope.value, owner,
                        now.isoformat(), now.isoformat(), ttl, json.dumps(tags or [])
                    ))
            except Exception as e:
                api_logger.error(f"SQLite persist failed: {e}")
                return False

        return True

    def get(
        self,
        key: str,
        scope: MemoryScope = MemoryScope.GLOBAL,
        owner: Optional[str] = None,
        default: Any = None
    ) -> Any:
        """
        Retrieve a value from shared memory

        Args:
            key: Key to retrieve
            scope: Visibility scope
            owner: Owner for scoped access
            default: Default value if not found

        Returns:
            Stored value or default
        """
        full_key = self._make_key(key, scope, owner)

        # Try Redis first
        if self._connected:
            try:
                value = self._redis.get(full_key)
                if value:
                    return json.loads(value)
            except Exception:
                pass

        # Fall back to SQLite
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT value, ttl, updated_at FROM shared_memory WHERE key = ?",
                    (full_key,)
                ).fetchone()

                if row:
                    # Check TTL
                    if row["ttl"]:
                        updated = datetime.fromisoformat(row["updated_at"])
                        if datetime.utcnow() > updated + timedelta(seconds=row["ttl"]):
                            # Expired
                            self.delete(key, scope, owner)
                            return default

                    return json.loads(row["value"])
        except Exception as e:
            api_logger.error(f"Memory get failed: {e}")

        return default

    def delete(
        self,
        key: str,
        scope: MemoryScope = MemoryScope.GLOBAL,
        owner: Optional[str] = None
    ) -> bool:
        """Delete a value from shared memory"""
        full_key = self._make_key(key, scope, owner)

        # Delete from Redis
        if self._connected:
            try:
                self._redis.delete(full_key, f"{full_key}:meta")
            except Exception:
                pass

        # Delete from SQLite
        try:
            with get_db() as conn:
                conn.execute("DELETE FROM shared_memory WHERE key = ?", (full_key,))
            return True
        except Exception:
            return False

    def exists(
        self,
        key: str,
        scope: MemoryScope = MemoryScope.GLOBAL,
        owner: Optional[str] = None
    ) -> bool:
        """Check if a key exists"""
        full_key = self._make_key(key, scope, owner)

        if self._connected:
            try:
                if self._redis.exists(full_key):
                    return True
            except Exception:
                pass

        with get_db() as conn:
            row = conn.execute(
                "SELECT 1 FROM shared_memory WHERE key = ?",
                (full_key,)
            ).fetchone()
            return row is not None

    # ==================== Blackboard Pattern ====================

    def publish(
        self,
        channel: str,
        message: Any,
        scope: MemoryScope = MemoryScope.GLOBAL
    ) -> bool:
        """
        Publish a message to the blackboard

        Messages are stored with timestamps for polling-based retrieval.
        Also uses Redis pub/sub if available.
        """
        msg_id = f"{channel}:{datetime.utcnow().timestamp()}"
        self.set(
            msg_id,
            {"channel": channel, "message": message, "timestamp": datetime.utcnow().isoformat()},
            scope=scope,
            ttl=3600  # Messages expire in 1 hour
        )

        # Redis pub/sub if available
        if self._connected:
            try:
                self._redis.publish(f"blackboard:{channel}", json.dumps(message))
            except Exception:
                pass

        return True

    def get_messages(
        self,
        channel: str,
        since: Optional[datetime] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get messages from a blackboard channel

        Args:
            channel: Channel name
            since: Only messages after this time
            limit: Maximum messages to return

        Returns:
            List of messages with timestamps
        """
        messages = []

        try:
            with get_db() as conn:
                query = """
                    SELECT key, value, updated_at FROM shared_memory
                    WHERE key LIKE ?
                """
                params = [f"mem:global::{channel}:%"]

                if since:
                    query += " AND updated_at > ?"
                    params.append(since.isoformat())

                query += " ORDER BY updated_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                for row in rows:
                    try:
                        data = json.loads(row["value"])
                        messages.append(data)
                    except Exception:
                        pass

        except Exception as e:
            api_logger.error(f"Get messages failed: {e}")

        return messages

    # ==================== Scoped Operations ====================

    def get_session_memory(self, session_id: str) -> Dict[str, Any]:
        """Get all memory for a session"""
        return self._get_by_scope(MemoryScope.SESSION, session_id)

    def get_agent_memory(self, agent_id: str) -> Dict[str, Any]:
        """Get all memory for an agent"""
        return self._get_by_scope(MemoryScope.AGENT, agent_id)

    def get_group_memory(self, group_id: str) -> Dict[str, Any]:
        """Get all memory for a group"""
        return self._get_by_scope(MemoryScope.GROUP, group_id)

    def _get_by_scope(self, scope: MemoryScope, owner: str) -> Dict[str, Any]:
        """Get all entries for a scope/owner combination"""
        prefix = f"mem:{scope.value}:{owner}:"
        results = {}

        try:
            with get_db() as conn:
                rows = conn.execute(
                    "SELECT key, value FROM shared_memory WHERE key LIKE ?",
                    (f"{prefix}%",)
                ).fetchall()

                for row in rows:
                    short_key = row["key"].replace(prefix, "")
                    try:
                        results[short_key] = json.loads(row["value"])
                    except Exception:
                        results[short_key] = row["value"]

        except Exception as e:
            api_logger.error(f"Get by scope failed: {e}")

        return results

    def clear_scope(self, scope: MemoryScope, owner: Optional[str] = None) -> int:
        """Clear all memory for a scope"""
        if owner:
            pattern = f"mem:{scope.value}:{owner}:%"
        else:
            pattern = f"mem:{scope.value}:%"

        count = 0

        # Clear Redis
        if self._connected:
            try:
                keys = self._redis.keys(pattern.replace("%", "*"))
                if keys:
                    count = self._redis.delete(*keys)
            except Exception:
                pass

        # Clear SQLite
        try:
            with get_db() as conn:
                cursor = conn.execute(
                    "DELETE FROM shared_memory WHERE key LIKE ?",
                    (pattern,)
                )
                count = max(count, cursor.rowcount)
        except Exception:
            pass

        return count

    # ==================== Search ====================

    def search_by_tags(self, tags: List[str], scope: Optional[MemoryScope] = None) -> List[MemoryEntry]:
        """Search memory entries by tags"""
        entries = []

        try:
            with get_db() as conn:
                query = "SELECT * FROM shared_memory WHERE 1=1"
                params = []

                if scope:
                    query += " AND scope = ?"
                    params.append(scope.value)

                rows = conn.execute(query, params).fetchall()

                for row in rows:
                    entry_tags = json.loads(row["tags"] or "[]")
                    if any(tag in entry_tags for tag in tags):
                        entries.append(MemoryEntry(
                            key=row["key"],
                            value=json.loads(row["value"]),
                            scope=MemoryScope(row["scope"]),
                            owner=row["owner"],
                            created_at=datetime.fromisoformat(row["created_at"]),
                            updated_at=datetime.fromisoformat(row["updated_at"]),
                            ttl=row["ttl"],
                            tags=entry_tags
                        ))

        except Exception as e:
            api_logger.error(f"Tag search failed: {e}")

        return entries

    def list_keys(
        self,
        pattern: str = "*",
        scope: Optional[MemoryScope] = None,
        limit: int = 100
    ) -> List[str]:
        """List memory keys matching a pattern"""
        keys = []

        try:
            with get_db() as conn:
                query = "SELECT key FROM shared_memory WHERE key LIKE ?"
                sql_pattern = pattern.replace("*", "%")
                params = [f"mem:%{sql_pattern}%"]

                if scope:
                    query += " AND scope = ?"
                    params.append(scope.value)

                query += " LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                keys = [row["key"] for row in rows]

        except Exception:
            pass

        return keys

    # ==================== Utilities ====================

    def _make_key(self, key: str, scope: MemoryScope, owner: Optional[str]) -> str:
        """Create a full key with scope and owner"""
        owner_part = owner or ""
        return f"{MEMORY_PREFIX}{scope.value}:{owner_part}:{key}"

    def get_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        stats = {
            "redis_connected": self._connected,
            "entries": {},
            "total_size": 0
        }

        try:
            with get_db() as conn:
                # Count by scope
                rows = conn.execute("""
                    SELECT scope, COUNT(*) as count
                    FROM shared_memory GROUP BY scope
                """).fetchall()
                stats["entries"] = {row["scope"]: row["count"] for row in rows}

                # Total entries
                stats["total_entries"] = sum(stats["entries"].values())

        except Exception:
            pass

        return stats


# Global shared memory instance
_shared_memory: Optional[SharedMemory] = None


def get_shared_memory() -> SharedMemory:
    """Get the global SharedMemory instance"""
    global _shared_memory
    if _shared_memory is None:
        _shared_memory = SharedMemory()
        _shared_memory.connect_redis()
    return _shared_memory


# Convenience functions
def remember(key: str, value: Any, **kwargs) -> bool:
    """Store a value in global shared memory"""
    return get_shared_memory().set(key, value, **kwargs)


def recall(key: str, default: Any = None, **kwargs) -> Any:
    """Retrieve a value from global shared memory"""
    return get_shared_memory().get(key, default=default, **kwargs)


def forget(key: str, **kwargs) -> bool:
    """Remove a value from shared memory"""
    return get_shared_memory().delete(key, **kwargs)
