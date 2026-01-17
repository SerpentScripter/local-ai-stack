"""
Model Benchmark Routes
API endpoints for model performance tracking and benchmarking
"""
from fastapi import APIRouter, Query, BackgroundTasks
from pydantic import BaseModel
from typing import Optional

from ..model_benchmarks import get_benchmark_system, BenchmarkType

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


class BenchmarkRequest(BaseModel):
    """Request to run benchmarks"""
    model: str
    benchmark_type: Optional[str] = None  # If None, run all


class CompareRequest(BaseModel):
    """Request to compare two models"""
    model_a: str
    model_b: str
    benchmark_type: str = "reasoning"


@router.get("/metrics/{model}")
def get_model_metrics(
    model: str,
    days: int = Query(7, ge=1, le=90, description="Days of history")
):
    """
    Get aggregated metrics for a model

    Includes:
    - Total requests
    - Average latency
    - P95 latency
    - Tokens per second
    - Error rate
    - Benchmark scores
    """
    system = get_benchmark_system()
    metrics = system.get_model_metrics(model, days)

    if not metrics:
        return {"error": f"No data for model: {model}"}

    return {
        "model": metrics.model_name,
        "period_days": days,
        "total_requests": metrics.total_requests,
        "avg_latency_ms": metrics.avg_latency_ms,
        "p95_latency_ms": metrics.p95_latency_ms,
        "tokens_generated": metrics.tokens_generated,
        "avg_tokens_per_second": metrics.avg_tokens_per_second,
        "error_rate_percent": metrics.error_rate,
        "benchmark_scores": metrics.benchmark_scores
    }


@router.post("/run")
async def run_benchmark(request: BenchmarkRequest, background_tasks: BackgroundTasks):
    """
    Run benchmarks on a model

    If benchmark_type is not specified, runs the full benchmark suite.
    """
    system = get_benchmark_system()

    if request.benchmark_type:
        # Run specific benchmark
        try:
            benchmark_type = BenchmarkType(request.benchmark_type)
        except ValueError:
            return {"error": f"Invalid benchmark type. Valid types: {[b.value for b in BenchmarkType]}"}

        result = await system.run_benchmark(request.model, benchmark_type)

        return {
            "model": result.model,
            "benchmark": result.benchmark_type.value,
            "score": round(result.score, 1),
            "latency_ms": round(result.latency_ms, 2),
            "tokens_per_second": round(result.tokens_per_second, 2),
            "details": result.details
        }

    else:
        # Run full suite
        results = await system.run_full_benchmark_suite(request.model)
        return results


@router.post("/run-background")
async def run_benchmark_background(request: BenchmarkRequest, background_tasks: BackgroundTasks):
    """Run benchmarks in the background"""

    async def run_bg():
        system = get_benchmark_system()
        if request.benchmark_type:
            benchmark_type = BenchmarkType(request.benchmark_type)
            await system.run_benchmark(request.model, benchmark_type)
        else:
            await system.run_full_benchmark_suite(request.model)

    background_tasks.add_task(run_bg)
    return {"status": "scheduled", "model": request.model}


@router.post("/compare")
async def compare_models(request: CompareRequest):
    """Compare two models on a specific benchmark"""
    system = get_benchmark_system()

    try:
        benchmark_type = BenchmarkType(request.benchmark_type)
    except ValueError:
        return {"error": f"Invalid benchmark type: {request.benchmark_type}"}

    result = await system.compare_models(
        request.model_a,
        request.model_b,
        benchmark_type
    )

    return result


@router.get("/leaderboard")
def get_leaderboard(
    benchmark_type: Optional[str] = Query(None, description="Filter by benchmark type"),
    days: int = Query(30, ge=1, le=365)
):
    """
    Get model leaderboard

    Ranks models by their benchmark scores.
    """
    system = get_benchmark_system()

    bt = None
    if benchmark_type:
        try:
            bt = BenchmarkType(benchmark_type)
        except ValueError:
            return {"error": f"Invalid benchmark type: {benchmark_type}"}

    return system.get_leaderboard(bt, days)


@router.get("/trends/{model}")
def get_performance_trends(
    model: str,
    days: int = Query(30, ge=1, le=365)
):
    """Get performance trends for a model over time"""
    system = get_benchmark_system()
    return system.get_performance_trends(model, days)


@router.get("/types")
def list_benchmark_types():
    """List available benchmark types"""
    return {
        "benchmark_types": [
            {
                "id": bt.value,
                "name": bt.name.replace("_", " ").title(),
                "description": {
                    "response_time": "Measures response latency",
                    "coherence": "Tests narrative consistency and clarity",
                    "instruction_following": "Tests ability to follow specific formats",
                    "code_generation": "Tests code writing ability",
                    "reasoning": "Tests logical reasoning",
                    "creativity": "Tests creative writing ability",
                    "factual_accuracy": "Tests factual knowledge"
                }.get(bt.value, "")
            }
            for bt in BenchmarkType
        ]
    }


@router.post("/track")
def track_request(
    model: str,
    latency_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    success: bool = True,
    error_message: Optional[str] = None
):
    """
    Manually track a model request

    This is typically called automatically by the chat endpoint,
    but can be used for external tracking.
    """
    system = get_benchmark_system()
    system.track_request(
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        success=success,
        error_message=error_message
    )
    return {"status": "tracked"}
