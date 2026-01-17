"""
AI Prioritization Engine
Intelligent task prioritization with context-aware recommendations

Features:
- Multi-factor task scoring
- "What to work on next" recommendations
- Predictive completion dates
- Scope creep detection
- Energy/context-aware scheduling
"""
import json
import math
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from .database import get_db
from .logging_config import api_logger


class EnergyLevel(Enum):
    """User energy/focus levels"""
    HIGH = "high"         # Complex, creative work
    MEDIUM = "medium"     # Standard tasks
    LOW = "low"           # Administrative, routine


class TaskComplexity(Enum):
    """Task complexity levels"""
    TRIVIAL = 1      # < 15 min
    SIMPLE = 2       # 15-60 min
    MEDIUM = 3       # 1-4 hours
    COMPLEX = 4      # 4-8 hours
    EPIC = 5         # > 1 day


@dataclass
class PrioritizationFactors:
    """Factors used in task prioritization"""
    priority_weight: float = 0.25      # P0-P3 priority
    deadline_weight: float = 0.20      # Due date urgency
    dependency_weight: float = 0.15    # Blocks other tasks
    age_weight: float = 0.10           # Time in backlog
    complexity_match: float = 0.15     # Matches current energy
    context_switch: float = 0.10       # Same category bonus
    momentum_weight: float = 0.05      # Recent progress bonus


@dataclass
class TaskScore:
    """Calculated score for a task"""
    task_id: str
    external_id: str
    title: str
    total_score: float
    factor_breakdown: Dict[str, float]
    recommendation_reason: str
    estimated_duration: Optional[timedelta] = None
    predicted_completion: Optional[datetime] = None


@dataclass
class VelocityMetrics:
    """Historical velocity data"""
    tasks_per_day: float
    avg_completion_time: timedelta
    completion_rate: float  # % of tasks completed vs created
    by_priority: Dict[str, float]
    by_category: Dict[str, float]


class PrioritizationEngine:
    """
    AI-driven task prioritization engine

    Uses multiple signals to score tasks and provide intelligent
    recommendations on what to work on next.
    """

    def __init__(self):
        self._factors = PrioritizationFactors()
        self._current_context: Optional[str] = None
        self._current_energy: EnergyLevel = EnergyLevel.MEDIUM
        self._init_database()

    def _init_database(self):
        """Initialize prioritization tables"""
        try:
            with get_db() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS task_estimates (
                        external_id TEXT PRIMARY KEY,
                        estimated_hours REAL,
                        actual_hours REAL,
                        complexity TEXT,
                        updated_at TEXT
                    );

                    CREATE TABLE IF NOT EXISTS prioritization_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        recommended_task TEXT,
                        was_selected INTEGER DEFAULT 0,
                        energy_level TEXT,
                        context TEXT
                    );

                    CREATE TABLE IF NOT EXISTS scope_changes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        external_id TEXT NOT NULL,
                        change_type TEXT NOT NULL,
                        old_value TEXT,
                        new_value TEXT,
                        detected_at TEXT NOT NULL
                    );
                """)
        except Exception as e:
            api_logger.error(f"Failed to init prioritization tables: {e}")

    # ==================== Task Scoring ====================

    def score_task(
        self,
        task: Dict[str, Any],
        all_tasks: List[Dict[str, Any]]
    ) -> TaskScore:
        """
        Calculate prioritization score for a single task

        Args:
            task: Task to score
            all_tasks: All tasks (for dependency analysis)

        Returns:
            TaskScore with breakdown
        """
        factors = {}
        reasons = []

        # 1. Priority score (P0=1.0, P1=0.75, P2=0.5, P3=0.25)
        priority_map = {"P0": 1.0, "P1": 0.75, "P2": 0.5, "P3": 0.25}
        priority = task.get("priority", "P2")
        factors["priority"] = priority_map.get(priority, 0.5) * self._factors.priority_weight
        if priority == "P0":
            reasons.append("Critical priority")

        # 2. Deadline urgency
        deadline_score = self._calculate_deadline_score(task)
        factors["deadline"] = deadline_score * self._factors.deadline_weight
        if deadline_score > 0.8:
            reasons.append("Approaching deadline")

        # 3. Dependency score (does this block others?)
        dependency_score = self._calculate_dependency_score(task, all_tasks)
        factors["dependency"] = dependency_score * self._factors.dependency_weight
        if dependency_score > 0.5:
            reasons.append("Blocks other tasks")

        # 4. Age score (older tasks get slight boost)
        age_score = self._calculate_age_score(task)
        factors["age"] = age_score * self._factors.age_weight
        if age_score > 0.8:
            reasons.append("Long time in backlog")

        # 5. Energy/complexity match
        complexity_score = self._calculate_complexity_match(task)
        factors["complexity_match"] = complexity_score * self._factors.complexity_match
        if complexity_score > 0.8:
            reasons.append(f"Matches {self._current_energy.value} energy level")

        # 6. Context switch penalty/bonus
        context_score = self._calculate_context_score(task)
        factors["context"] = context_score * self._factors.context_switch
        if context_score > 0.8:
            reasons.append("Same context - no switch cost")

        # 7. Momentum (recently worked on similar tasks)
        momentum_score = self._calculate_momentum_score(task)
        factors["momentum"] = momentum_score * self._factors.momentum_weight

        # Calculate total
        total_score = sum(factors.values())

        # Estimate duration
        estimated_duration = self._estimate_duration(task)

        # Predict completion
        predicted_completion = None
        if estimated_duration:
            velocity = self._get_velocity_metrics()
            if velocity.tasks_per_day > 0:
                # Simple prediction based on queue position and velocity
                queue_position = len([t for t in all_tasks if self._quick_score(t) > total_score])
                days_ahead = queue_position / velocity.tasks_per_day
                predicted_completion = datetime.utcnow() + timedelta(days=days_ahead)

        return TaskScore(
            task_id=str(task.get("id", "")),
            external_id=task.get("external_id", ""),
            title=task.get("title", ""),
            total_score=total_score,
            factor_breakdown=factors,
            recommendation_reason=" | ".join(reasons) if reasons else "Standard priority",
            estimated_duration=estimated_duration,
            predicted_completion=predicted_completion
        )

    def _quick_score(self, task: Dict[str, Any]) -> float:
        """Quick scoring for comparison"""
        priority_map = {"P0": 4, "P1": 3, "P2": 2, "P3": 1}
        return priority_map.get(task.get("priority", "P2"), 2)

    def _calculate_deadline_score(self, task: Dict[str, Any]) -> float:
        """Score based on deadline proximity"""
        due_date_str = task.get("due_date")
        if not due_date_str:
            return 0.3  # No deadline = moderate urgency

        try:
            due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00"))
            now = datetime.utcnow()

            if due_date.tzinfo:
                now = now.replace(tzinfo=due_date.tzinfo)

            days_until = (due_date - now).days

            if days_until < 0:
                return 1.0  # Overdue
            elif days_until == 0:
                return 0.95
            elif days_until <= 1:
                return 0.9
            elif days_until <= 3:
                return 0.7
            elif days_until <= 7:
                return 0.5
            elif days_until <= 14:
                return 0.3
            else:
                return 0.1

        except Exception:
            return 0.3

    def _calculate_dependency_score(
        self,
        task: Dict[str, Any],
        all_tasks: List[Dict[str, Any]]
    ) -> float:
        """Score based on how many tasks this blocks"""
        task_id = task.get("external_id", "")

        # Count tasks that mention this task as a blocker
        blocked_count = 0
        for other_task in all_tasks:
            blockers = other_task.get("blocked_by", [])
            if isinstance(blockers, str):
                blockers = [blockers]
            if task_id in blockers:
                blocked_count += 1

        # Normalize (0-1 scale, max at 5+ blocked tasks)
        return min(blocked_count / 5, 1.0)

    def _calculate_age_score(self, task: Dict[str, Any]) -> float:
        """Score based on time in backlog"""
        created_str = task.get("created_at")
        if not created_str:
            return 0.5

        try:
            created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
            age_days = (datetime.utcnow() - created.replace(tzinfo=None)).days

            if age_days > 30:
                return 1.0
            elif age_days > 14:
                return 0.7
            elif age_days > 7:
                return 0.5
            elif age_days > 3:
                return 0.3
            else:
                return 0.1

        except Exception:
            return 0.5

    def _calculate_complexity_match(self, task: Dict[str, Any]) -> float:
        """Score based on matching current energy level"""
        # Estimate task complexity from title/description length and priority
        title = task.get("title", "")
        description = task.get("description", "")
        priority = task.get("priority", "P2")

        # Simple heuristic
        content_length = len(title) + len(description)

        if content_length < 50 and priority in ("P2", "P3"):
            task_complexity = TaskComplexity.SIMPLE
        elif content_length < 200:
            task_complexity = TaskComplexity.MEDIUM
        elif priority == "P0":
            task_complexity = TaskComplexity.COMPLEX
        else:
            task_complexity = TaskComplexity.MEDIUM

        # Match with energy
        energy_complexity_map = {
            EnergyLevel.HIGH: [TaskComplexity.COMPLEX, TaskComplexity.EPIC],
            EnergyLevel.MEDIUM: [TaskComplexity.SIMPLE, TaskComplexity.MEDIUM],
            EnergyLevel.LOW: [TaskComplexity.TRIVIAL, TaskComplexity.SIMPLE]
        }

        preferred = energy_complexity_map.get(self._current_energy, [])
        if task_complexity in preferred:
            return 1.0
        elif task_complexity.value == self._current_energy.value:
            return 0.7
        else:
            return 0.3

    def _calculate_context_score(self, task: Dict[str, Any]) -> float:
        """Score based on context switch cost"""
        if not self._current_context:
            return 0.5

        task_category = task.get("category", "")
        if task_category == self._current_context:
            return 1.0  # Same context - no switch
        else:
            return 0.3  # Context switch penalty

    def _calculate_momentum_score(self, task: Dict[str, Any]) -> float:
        """Score based on recent work momentum"""
        category = task.get("category", "")

        try:
            with get_db() as conn:
                # Check recent completions in same category
                recent = conn.execute("""
                    SELECT COUNT(*) FROM backlog_items
                    WHERE category = ?
                    AND status = 'done'
                    AND completed_at >= datetime('now', '-1 day')
                """, (category,)).fetchone()[0]

                if recent >= 3:
                    return 1.0  # Strong momentum
                elif recent >= 1:
                    return 0.6
                else:
                    return 0.3
        except Exception:
            return 0.5

    def _estimate_duration(self, task: Dict[str, Any]) -> Optional[timedelta]:
        """Estimate task duration"""
        external_id = task.get("external_id", "")

        # Check for stored estimate
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT estimated_hours FROM task_estimates WHERE external_id = ?",
                    (external_id,)
                ).fetchone()
                if row and row["estimated_hours"]:
                    return timedelta(hours=row["estimated_hours"])
        except Exception:
            pass

        # Default estimates by priority
        default_hours = {"P0": 4, "P1": 2, "P2": 1, "P3": 0.5}
        hours = default_hours.get(task.get("priority", "P2"), 1)
        return timedelta(hours=hours)

    # ==================== Recommendations ====================

    def get_recommendations(
        self,
        energy_level: EnergyLevel = EnergyLevel.MEDIUM,
        context: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Get prioritized task recommendations

        Args:
            energy_level: Current energy/focus level
            context: Current working context (category)
            limit: Number of recommendations

        Returns:
            List of recommended tasks with scores
        """
        self._current_energy = energy_level
        self._current_context = context

        # Get all active tasks
        tasks = self._get_active_tasks()
        if not tasks:
            return []

        # Score all tasks
        scored = [self.score_task(task, tasks) for task in tasks]

        # Sort by score
        scored.sort(key=lambda x: x.total_score, reverse=True)

        # Build recommendations
        recommendations = []
        for score in scored[:limit]:
            task = next((t for t in tasks if t.get("external_id") == score.external_id), {})
            recommendations.append({
                "task": task,
                "score": round(score.total_score, 3),
                "factors": {k: round(v, 3) for k, v in score.factor_breakdown.items()},
                "reason": score.recommendation_reason,
                "estimated_duration": str(score.estimated_duration) if score.estimated_duration else None,
                "predicted_completion": score.predicted_completion.isoformat() if score.predicted_completion else None
            })

        # Log recommendation
        if recommendations:
            self._log_recommendation(recommendations[0]["task"].get("external_id", ""))

        return recommendations

    def what_should_i_do(
        self,
        energy: str = "medium",
        context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Simple "what should I work on next" interface

        Returns single best recommendation with explanation
        """
        energy_map = {
            "high": EnergyLevel.HIGH,
            "medium": EnergyLevel.MEDIUM,
            "low": EnergyLevel.LOW
        }
        energy_level = energy_map.get(energy.lower(), EnergyLevel.MEDIUM)

        recommendations = self.get_recommendations(
            energy_level=energy_level,
            context=context,
            limit=3
        )

        if not recommendations:
            return {
                "recommendation": None,
                "message": "No tasks available! Your backlog is empty.",
                "alternatives": []
            }

        top = recommendations[0]
        return {
            "recommendation": {
                "task_id": top["task"].get("external_id"),
                "title": top["task"].get("title"),
                "priority": top["task"].get("priority"),
                "category": top["task"].get("category"),
                "score": top["score"],
                "reason": top["reason"]
            },
            "message": f"Work on: {top['task'].get('title')} ({top['reason']})",
            "estimated_duration": top["estimated_duration"],
            "alternatives": [
                {"title": r["task"].get("title"), "score": r["score"]}
                for r in recommendations[1:]
            ]
        }

    def _get_active_tasks(self) -> List[Dict[str, Any]]:
        """Get all active (non-completed) tasks"""
        try:
            with get_db() as conn:
                rows = conn.execute("""
                    SELECT * FROM backlog_items
                    WHERE status NOT IN ('done', 'cancelled', 'archived')
                    ORDER BY created_at DESC
                """).fetchall()
                return [dict(row) for row in rows]
        except Exception:
            return []

    def _log_recommendation(self, task_id: str):
        """Log recommendation for analysis"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO prioritization_history
                    (timestamp, recommended_task, energy_level, context)
                    VALUES (?, ?, ?, ?)
                """, (
                    datetime.utcnow().isoformat(),
                    task_id,
                    self._current_energy.value,
                    self._current_context
                ))
        except Exception:
            pass

    # ==================== Velocity & Predictions ====================

    def _get_velocity_metrics(self) -> VelocityMetrics:
        """Calculate velocity metrics from history"""
        try:
            with get_db() as conn:
                # Tasks completed in last 30 days
                completed = conn.execute("""
                    SELECT COUNT(*) FROM backlog_items
                    WHERE status = 'done'
                    AND completed_at >= datetime('now', '-30 days')
                """).fetchone()[0]

                tasks_per_day = completed / 30 if completed else 0.5

                # Average completion time (created to completed)
                avg_time = conn.execute("""
                    SELECT AVG(
                        julianday(completed_at) - julianday(created_at)
                    ) as avg_days
                    FROM backlog_items
                    WHERE status = 'done'
                    AND completed_at >= datetime('now', '-30 days')
                """).fetchone()

                avg_days = avg_time["avg_days"] if avg_time["avg_days"] else 3
                avg_completion_time = timedelta(days=avg_days)

                # Completion rate
                created = conn.execute("""
                    SELECT COUNT(*) FROM backlog_items
                    WHERE created_at >= datetime('now', '-30 days')
                """).fetchone()[0]

                completion_rate = completed / created if created else 0.5

                # By priority
                by_priority = {}
                rows = conn.execute("""
                    SELECT priority, COUNT(*) as count
                    FROM backlog_items
                    WHERE status = 'done'
                    AND completed_at >= datetime('now', '-30 days')
                    GROUP BY priority
                """).fetchall()
                for row in rows:
                    by_priority[row["priority"]] = row["count"] / 30

                # By category
                by_category = {}
                rows = conn.execute("""
                    SELECT category, COUNT(*) as count
                    FROM backlog_items
                    WHERE status = 'done'
                    AND completed_at >= datetime('now', '-30 days')
                    GROUP BY category
                """).fetchall()
                for row in rows:
                    by_category[row["category"]] = row["count"] / 30

                return VelocityMetrics(
                    tasks_per_day=tasks_per_day,
                    avg_completion_time=avg_completion_time,
                    completion_rate=completion_rate,
                    by_priority=by_priority,
                    by_category=by_category
                )

        except Exception as e:
            api_logger.error(f"Failed to get velocity metrics: {e}")
            return VelocityMetrics(
                tasks_per_day=0.5,
                avg_completion_time=timedelta(days=3),
                completion_rate=0.5,
                by_priority={},
                by_category={}
            )

    def predict_completion_date(
        self,
        task_id: str
    ) -> Optional[Dict[str, Any]]:
        """Predict when a specific task will be completed"""
        tasks = self._get_active_tasks()
        task = next((t for t in tasks if t.get("external_id") == task_id), None)

        if not task:
            return None

        score = self.score_task(task, tasks)
        velocity = self._get_velocity_metrics()

        # Calculate queue position
        all_scores = [(self.score_task(t, tasks).total_score, t.get("external_id"))
                      for t in tasks]
        all_scores.sort(reverse=True)
        position = next(
            (i for i, (_, eid) in enumerate(all_scores) if eid == task_id),
            len(all_scores)
        )

        # Predict based on position and velocity
        if velocity.tasks_per_day > 0:
            days_ahead = position / velocity.tasks_per_day
            predicted = datetime.utcnow() + timedelta(days=days_ahead)
        else:
            predicted = datetime.utcnow() + timedelta(days=position * 3)

        return {
            "task_id": task_id,
            "title": task.get("title"),
            "queue_position": position + 1,
            "predicted_completion": predicted.isoformat(),
            "confidence": "high" if velocity.tasks_per_day > 1 else "medium",
            "factors": {
                "current_velocity": round(velocity.tasks_per_day, 2),
                "completion_rate": round(velocity.completion_rate, 2),
                "task_score": round(score.total_score, 3)
            }
        }

    # ==================== Scope Creep Detection ====================

    def detect_scope_creep(self) -> List[Dict[str, Any]]:
        """Detect potential scope creep in tasks"""
        alerts = []

        try:
            with get_db() as conn:
                # Tasks that have been updated multiple times
                frequently_updated = conn.execute("""
                    SELECT external_id, title, COUNT(*) as update_count
                    FROM backlog_events
                    WHERE event_type = 'updated'
                    GROUP BY external_id
                    HAVING update_count >= 5
                """).fetchall()

                for row in frequently_updated:
                    alerts.append({
                        "type": "frequent_updates",
                        "task_id": row["external_id"],
                        "title": row["title"],
                        "update_count": row["update_count"],
                        "message": f"Task updated {row['update_count']} times - possible scope creep"
                    })

                # Tasks in progress for too long
                stale_in_progress = conn.execute("""
                    SELECT external_id, title, status,
                           julianday('now') - julianday(updated_at) as days_stale
                    FROM backlog_items
                    WHERE status = 'in_progress'
                    AND updated_at < datetime('now', '-7 days')
                """).fetchall()

                for row in stale_in_progress:
                    alerts.append({
                        "type": "stale_in_progress",
                        "task_id": row["external_id"],
                        "title": row["title"],
                        "days_stale": round(row["days_stale"]),
                        "message": f"In progress for {round(row['days_stale'])} days without update"
                    })

                # Priority escalations
                priority_changes = conn.execute("""
                    SELECT external_id, old_value, new_value, created_at
                    FROM backlog_events
                    WHERE event_type = 'updated'
                    AND changes LIKE '%priority%'
                    AND created_at >= datetime('now', '-7 days')
                """).fetchall()

                escalation_count = defaultdict(int)
                for row in priority_changes:
                    escalation_count[row["external_id"]] += 1

                for task_id, count in escalation_count.items():
                    if count >= 2:
                        alerts.append({
                            "type": "priority_churn",
                            "task_id": task_id,
                            "change_count": count,
                            "message": f"Priority changed {count} times in past week"
                        })

        except Exception as e:
            api_logger.error(f"Scope creep detection failed: {e}")

        return alerts

    def get_stats(self) -> Dict[str, Any]:
        """Get prioritization engine statistics"""
        velocity = self._get_velocity_metrics()
        scope_alerts = self.detect_scope_creep()

        return {
            "velocity": {
                "tasks_per_day": round(velocity.tasks_per_day, 2),
                "avg_completion_days": velocity.avg_completion_time.days,
                "completion_rate": round(velocity.completion_rate * 100, 1)
            },
            "scope_alerts": len(scope_alerts),
            "factors": {
                "priority_weight": self._factors.priority_weight,
                "deadline_weight": self._factors.deadline_weight,
                "complexity_weight": self._factors.complexity_match
            }
        }


# Global instance
_prioritization_engine: Optional[PrioritizationEngine] = None


def get_prioritization_engine() -> PrioritizationEngine:
    """Get the global PrioritizationEngine instance"""
    global _prioritization_engine
    if _prioritization_engine is None:
        _prioritization_engine = PrioritizationEngine()
    return _prioritization_engine
