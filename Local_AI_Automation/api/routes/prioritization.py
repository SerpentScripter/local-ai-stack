"""
Prioritization Engine Routes
API endpoints for AI-driven task prioritization
"""
from fastapi import APIRouter, Query
from typing import Optional

from ..prioritization_engine import get_prioritization_engine, EnergyLevel

router = APIRouter(prefix="/prioritize", tags=["prioritization"])


@router.get("/recommend")
def get_recommendations(
    energy: str = Query("medium", description="Energy level: high, medium, low"),
    context: Optional[str] = Query(None, description="Current working context/category"),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get prioritized task recommendations

    Takes into account:
    - Task priority (P0-P3)
    - Deadline urgency
    - Dependencies (what blocks other tasks)
    - Task age
    - Energy level match
    - Context switch cost
    - Recent momentum
    """
    engine = get_prioritization_engine()

    energy_map = {
        "high": EnergyLevel.HIGH,
        "medium": EnergyLevel.MEDIUM,
        "low": EnergyLevel.LOW
    }
    energy_level = energy_map.get(energy.lower(), EnergyLevel.MEDIUM)

    return engine.get_recommendations(
        energy_level=energy_level,
        context=context,
        limit=limit
    )


@router.get("/next")
def what_should_i_do(
    energy: str = Query("medium", description="Energy level: high, medium, low"),
    context: Optional[str] = Query(None, description="Current working context")
):
    """
    Simple "what should I work on next" endpoint

    Returns the single best task recommendation with explanation.
    """
    engine = get_prioritization_engine()
    return engine.what_should_i_do(energy=energy, context=context)


@router.get("/predict/{task_id}")
def predict_completion(task_id: str):
    """
    Predict when a specific task will be completed

    Based on:
    - Current queue position
    - Historical velocity
    - Task priority/score
    """
    engine = get_prioritization_engine()
    prediction = engine.predict_completion_date(task_id)

    if not prediction:
        return {"error": "Task not found or already completed"}

    return prediction


@router.get("/scope-creep")
def detect_scope_creep():
    """
    Detect potential scope creep in tasks

    Looks for:
    - Tasks updated many times
    - Tasks stale in 'in_progress'
    - Frequent priority changes
    """
    engine = get_prioritization_engine()
    alerts = engine.detect_scope_creep()

    return {
        "alert_count": len(alerts),
        "alerts": alerts
    }


@router.get("/velocity")
def get_velocity():
    """Get velocity metrics (tasks per day, completion rate, etc.)"""
    engine = get_prioritization_engine()
    stats = engine.get_stats()
    return stats["velocity"]


@router.get("/stats")
def get_prioritization_stats():
    """Get full prioritization engine statistics"""
    engine = get_prioritization_engine()
    return engine.get_stats()
