"""
Self-Assessment Routes
API endpoints for the self-assessment dashboard
"""
from fastapi import APIRouter, Query, BackgroundTasks

from ..self_assessment import get_assessment_system

router = APIRouter(prefix="/assessment", tags=["assessment"])


@router.get("/run")
async def run_assessment():
    """
    Run a full self-assessment

    Evaluates:
    - Model Currency (installed vs latest)
    - Tool Versions (Docker containers)
    - Capability Coverage (modalities)
    - Benchmark Scores (quality)
    - Security Posture (configs, secrets)
    - System Health (resources)
    """
    system = get_assessment_system()
    report = await system.run_full_assessment()

    return {
        "timestamp": report.timestamp.isoformat(),
        "overall_score": round(report.overall_score, 1),
        "overall_grade": report.overall_grade.value,
        "dimensions": [
            {
                "name": d.name,
                "score": round(d.score, 1),
                "grade": d.grade.value,
                "weight": d.weight,
                "issues": d.issues,
                "recommendations": d.recommendations,
                "details": d.details
            }
            for d in report.dimensions
        ],
        "critical_issues": report.critical_issues,
        "improvement_plan": report.improvement_plan
    }


@router.post("/schedule")
async def schedule_assessment(background_tasks: BackgroundTasks):
    """Schedule an assessment to run in the background"""

    async def run_bg():
        system = get_assessment_system()
        await system.run_full_assessment()

    background_tasks.add_task(run_bg)
    return {"status": "scheduled", "message": "Assessment will run in background"}


@router.get("/history")
def get_assessment_history(
    days: int = Query(30, ge=1, le=365, description="Number of days of history")
):
    """Get historical assessment results"""
    system = get_assessment_system()
    return system.get_assessment_history(days)


@router.get("/trend")
def get_assessment_trend(
    days: int = Query(30, ge=7, le=365, description="Number of days for trend analysis")
):
    """Get assessment score trend over time"""
    system = get_assessment_system()
    return system.get_trend(days)


@router.get("/grade")
async def get_current_grade():
    """Get just the current overall grade (quick check)"""
    system = get_assessment_system()

    # Check for recent assessment
    history = system.get_assessment_history(days=1)
    if history:
        recent = history[0]
        return {
            "grade": recent["overall_grade"],
            "score": recent["overall_score"],
            "timestamp": recent["timestamp"],
            "cached": True
        }

    # Run new assessment
    report = await system.run_full_assessment()
    return {
        "grade": report.overall_grade.value,
        "score": round(report.overall_score, 1),
        "timestamp": report.timestamp.isoformat(),
        "cached": False
    }


@router.get("/dimension/{dimension_name}")
async def get_dimension_detail(dimension_name: str):
    """Get detailed assessment for a specific dimension"""
    system = get_assessment_system()
    report = await system.run_full_assessment()

    for dim in report.dimensions:
        if dim.name.lower().replace(" ", "_") == dimension_name.lower().replace(" ", "_"):
            return {
                "name": dim.name,
                "score": round(dim.score, 1),
                "grade": dim.grade.value,
                "weight": dim.weight,
                "issues": dim.issues,
                "recommendations": dim.recommendations,
                "details": dim.details
            }

    return {"error": f"Dimension '{dimension_name}' not found"}


@router.get("/scoreboard")
async def get_scoreboard():
    """
    Get the assessment scoreboard

    Returns all dimensions in a format suitable for dashboard display.
    """
    system = get_assessment_system()
    report = await system.run_full_assessment()
    trend = system.get_trend(30)

    return {
        "overall": {
            "score": round(report.overall_score, 1),
            "grade": report.overall_grade.value,
            "trend": trend["trend"],
            "change": trend["change"]
        },
        "dimensions": [
            {
                "name": d.name,
                "score": round(d.score, 1),
                "grade": d.grade.value,
                "status": "critical" if d.grade.value in ("D", "F") else "warning" if d.grade.value == "C" else "good"
            }
            for d in sorted(report.dimensions, key=lambda x: x.score)
        ],
        "top_issues": report.critical_issues[:5],
        "top_recommendations": report.improvement_plan[:5],
        "last_updated": report.timestamp.isoformat()
    }
