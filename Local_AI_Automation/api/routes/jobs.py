"""
Job Queue Routes
API endpoints for job queue management
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Any
from datetime import datetime

from ..job_queue import (
    get_job_queue, JobPriority, JobStatus,
    JobInfo, JobResult, REDIS_AVAILABLE
)
from ..auth import optional_auth

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobResponse(BaseModel):
    """Response for a single job"""
    job_id: str
    func_name: str
    priority: str
    status: str
    created_at: datetime
    error: Optional[str] = None
    meta: dict = {}


class JobResultResponse(BaseModel):
    """Response for job result"""
    job_id: str
    status: str
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class QueueStatsResponse(BaseModel):
    """Response for queue statistics"""
    connected: bool
    fallback_mode: bool
    redis_available: bool
    queues: dict = {}


@router.get("/", response_model=List[JobResponse])
def list_jobs(
    priority: Optional[str] = Query(None, description="Filter by priority"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(100, ge=1, le=500)
):
    """
    List jobs in the queue

    Optional filtering by priority and status.
    """
    queue = get_job_queue()

    # Convert string params to enums
    priority_enum = JobPriority(priority) if priority else None
    status_enum = JobStatus(status) if status else None

    jobs = queue.list_jobs(priority=priority_enum, status=status_enum, limit=limit)

    return [
        JobResponse(
            job_id=j.job_id,
            func_name=j.func_name,
            priority=j.priority.value,
            status=j.status.value,
            created_at=j.created_at,
            error=j.error,
            meta=j.meta
        )
        for j in jobs
    ]


@router.get("/stats", response_model=QueueStatsResponse)
def get_queue_stats():
    """
    Get queue statistics

    Shows queue sizes and connection status.
    """
    queue = get_job_queue()
    stats = queue.get_queue_stats()

    return QueueStatsResponse(
        connected=stats["connected"],
        fallback_mode=stats["fallback_mode"],
        redis_available=REDIS_AVAILABLE,
        queues=stats["queues"]
    )


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str):
    """
    Get job details by ID
    """
    queue = get_job_queue()
    job = queue.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobResponse(
        job_id=job.job_id,
        func_name=job.func_name,
        priority=job.priority.value,
        status=job.status.value,
        created_at=job.created_at,
        error=job.error,
        meta=job.meta
    )


@router.get("/{job_id}/result", response_model=JobResultResponse)
def get_job_result(job_id: str):
    """
    Get job result

    Returns the result if the job has finished.
    """
    queue = get_job_queue()
    result = queue.get_job_result(job_id)

    if not result:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return JobResultResponse(
        job_id=result.job_id,
        status=result.status.value,
        result=result.result,
        error=result.error,
        started_at=result.started_at,
        ended_at=result.ended_at
    )


@router.delete("/{job_id}")
def cancel_job(job_id: str):
    """
    Cancel a queued job

    Only works for jobs that haven't started yet.
    """
    queue = get_job_queue()

    success = queue.cancel_job(job_id)

    if success:
        return {"status": "cancelled", "job_id": job_id}
    else:
        raise HTTPException(
            status_code=400,
            detail="Failed to cancel job (may have already started or completed)"
        )


@router.post("/retry-failed")
def retry_failed_jobs(queue_name: Optional[str] = None):
    """
    Retry all failed jobs

    Optionally specify a queue name to retry only that queue.
    """
    queue = get_job_queue()
    count = queue.retry_failed_jobs(queue_name)

    return {
        "status": "success",
        "retried_count": count,
        "queue": queue_name or "all"
    }


@router.get("/priorities/list")
def list_priorities():
    """List available job priorities"""
    return {
        "priorities": [
            {"value": p.value, "name": p.name}
            for p in JobPriority
        ]
    }


@router.get("/statuses/list")
def list_statuses():
    """List available job statuses"""
    return {
        "statuses": [
            {"value": s.value, "name": s.name}
            for s in JobStatus
        ]
    }
