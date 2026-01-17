"""
Job Queue System
Asynchronous task processing using Redis + RQ

Provides:
- Priority-based job queues
- Fault-tolerant execution
- Job status tracking
- Retry mechanisms
- Dead letter queue for failed jobs
"""
import os
import json
import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field, asdict
from functools import wraps

# Try to import Redis and RQ
try:
    import redis
    from rq import Queue, Worker, Connection
    from rq.job import Job
    from rq.registry import FailedJobRegistry, FinishedJobRegistry
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

from .logging_config import api_logger
from .database import get_db


class JobPriority(Enum):
    """Job priority levels"""
    CRITICAL = "critical"  # P0 - Immediate processing
    HIGH = "high"          # P1 - Process before normal
    NORMAL = "normal"      # P2 - Default priority
    LOW = "low"            # P3 - Background processing


class JobStatus(Enum):
    """Job execution status"""
    QUEUED = "queued"
    STARTED = "started"
    FINISHED = "finished"
    FAILED = "failed"
    DEFERRED = "deferred"
    CANCELED = "canceled"


@dataclass
class JobResult:
    """Result of a job execution"""
    job_id: str
    status: JobStatus
    result: Any = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    retries: int = 0


@dataclass
class JobInfo:
    """Information about a queued job"""
    job_id: str
    func_name: str
    priority: JobPriority
    status: JobStatus
    created_at: datetime
    args: tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    result: Any = None
    error: Optional[str] = None
    meta: Dict[str, Any] = field(default_factory=dict)


# Redis connection configuration
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

# Queue names by priority
QUEUE_NAMES = {
    JobPriority.CRITICAL: "critical",
    JobPriority.HIGH: "high",
    JobPriority.NORMAL: "default",
    JobPriority.LOW: "low",
}


class JobQueue:
    """
    Job queue manager for async task processing

    Uses Redis + RQ when available, falls back to
    synchronous execution otherwise.
    """

    def __init__(self):
        self._redis: Optional[redis.Redis] = None
        self._queues: Dict[JobPriority, Queue] = {}
        self._connected = False
        self._fallback_mode = not REDIS_AVAILABLE

    def connect(self) -> bool:
        """Connect to Redis"""
        if self._fallback_mode:
            api_logger.warning("Redis/RQ not available, using synchronous fallback")
            return False

        try:
            self._redis = redis.Redis(
                host=REDIS_HOST,
                port=REDIS_PORT,
                db=REDIS_DB,
                password=REDIS_PASSWORD,
                decode_responses=False
            )
            # Test connection
            self._redis.ping()

            # Create queues for each priority
            for priority, queue_name in QUEUE_NAMES.items():
                self._queues[priority] = Queue(
                    queue_name,
                    connection=self._redis,
                    default_timeout=600  # 10 min default timeout
                )

            self._connected = True
            api_logger.info("Connected to Redis job queue")
            return True

        except Exception as e:
            api_logger.warning(f"Failed to connect to Redis: {e}, using fallback")
            self._fallback_mode = True
            return False

    def enqueue(
        self,
        func: Callable,
        *args,
        priority: JobPriority = JobPriority.NORMAL,
        job_id: Optional[str] = None,
        timeout: Optional[int] = None,
        ttl: Optional[int] = None,
        retry: int = 0,
        meta: Optional[Dict[str, Any]] = None,
        **kwargs
    ) -> str:
        """
        Enqueue a job for processing

        Args:
            func: Function to execute
            *args: Positional arguments
            priority: Job priority level
            job_id: Optional custom job ID
            timeout: Execution timeout in seconds
            ttl: Time-to-live for result
            retry: Number of retries on failure
            meta: Additional metadata
            **kwargs: Keyword arguments

        Returns:
            Job ID string
        """
        job_id = job_id or f"job-{uuid.uuid4().hex[:12]}"

        if self._fallback_mode or not self._connected:
            # Synchronous fallback
            return self._execute_sync(func, job_id, args, kwargs, meta)

        try:
            queue = self._queues.get(priority, self._queues[JobPriority.NORMAL])

            job = queue.enqueue(
                func,
                *args,
                job_id=job_id,
                job_timeout=timeout or 600,
                result_ttl=ttl or 3600,
                failure_ttl=86400,  # Keep failed jobs for 24h
                retry=retry,
                meta=meta or {},
                **kwargs
            )

            # Store job info in database
            self._save_job_info(job_id, func.__name__, priority, args, kwargs, meta)

            api_logger.info(f"Job {job_id} enqueued with priority {priority.value}")
            return job_id

        except Exception as e:
            api_logger.error(f"Failed to enqueue job: {e}")
            # Fall back to sync execution
            return self._execute_sync(func, job_id, args, kwargs, meta)

    def _execute_sync(
        self,
        func: Callable,
        job_id: str,
        args: tuple,
        kwargs: dict,
        meta: Optional[Dict[str, Any]]
    ) -> str:
        """Execute job synchronously as fallback"""
        try:
            result = func(*args, **kwargs)
            self._save_job_result(job_id, JobStatus.FINISHED, result=result)
            return job_id
        except Exception as e:
            self._save_job_result(job_id, JobStatus.FAILED, error=str(e))
            raise

    def get_job(self, job_id: str) -> Optional[JobInfo]:
        """Get job information by ID"""
        if self._connected and not self._fallback_mode:
            try:
                job = Job.fetch(job_id, connection=self._redis)
                return self._job_to_info(job)
            except Exception:
                pass

        # Check database
        return self._get_job_from_db(job_id)

    def get_job_status(self, job_id: str) -> Optional[JobStatus]:
        """Get job status"""
        job = self.get_job(job_id)
        return job.status if job else None

    def get_job_result(self, job_id: str) -> Optional[JobResult]:
        """Get job result"""
        if self._connected and not self._fallback_mode:
            try:
                job = Job.fetch(job_id, connection=self._redis)
                return JobResult(
                    job_id=job_id,
                    status=JobStatus(job.get_status()),
                    result=job.result,
                    error=job.exc_info if job.is_failed else None,
                    started_at=job.started_at,
                    ended_at=job.ended_at,
                    retries=job.retries_left or 0
                )
            except Exception:
                pass

        return self._get_result_from_db(job_id)

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued job"""
        if self._connected and not self._fallback_mode:
            try:
                job = Job.fetch(job_id, connection=self._redis)
                job.cancel()
                self._update_job_status(job_id, JobStatus.CANCELED)
                return True
            except Exception as e:
                api_logger.error(f"Failed to cancel job {job_id}: {e}")
                return False
        return False

    def list_jobs(
        self,
        priority: Optional[JobPriority] = None,
        status: Optional[JobStatus] = None,
        limit: int = 100
    ) -> List[JobInfo]:
        """List jobs with optional filtering"""
        jobs = []

        if self._connected and not self._fallback_mode:
            queues = [self._queues[priority]] if priority else list(self._queues.values())

            for queue in queues:
                for job in queue.jobs[:limit]:
                    info = self._job_to_info(job)
                    if status is None or info.status == status:
                        jobs.append(info)

        # Also check database
        db_jobs = self._list_jobs_from_db(priority, status, limit)
        job_ids = {j.job_id for j in jobs}
        for job in db_jobs:
            if job.job_id not in job_ids:
                jobs.append(job)

        return jobs[:limit]

    def get_queue_stats(self) -> Dict[str, Any]:
        """Get queue statistics"""
        stats = {
            "connected": self._connected,
            "fallback_mode": self._fallback_mode,
            "queues": {}
        }

        if self._connected and not self._fallback_mode:
            for priority, queue in self._queues.items():
                failed_registry = FailedJobRegistry(queue=queue)
                finished_registry = FinishedJobRegistry(queue=queue)

                stats["queues"][priority.value] = {
                    "queued": len(queue),
                    "failed": len(failed_registry),
                    "finished": len(finished_registry),
                }

        return stats

    def retry_failed_jobs(self, queue_name: Optional[str] = None) -> int:
        """Retry all failed jobs in a queue"""
        if not self._connected or self._fallback_mode:
            return 0

        retried = 0
        queues = [self._queues[JobPriority(queue_name)]] if queue_name else list(self._queues.values())

        for queue in queues:
            registry = FailedJobRegistry(queue=queue)
            for job_id in registry.get_job_ids():
                try:
                    registry.requeue(job_id)
                    retried += 1
                except Exception:
                    pass

        return retried

    # Private helper methods

    def _job_to_info(self, job: 'Job') -> JobInfo:
        """Convert RQ Job to JobInfo"""
        return JobInfo(
            job_id=job.id,
            func_name=job.func_name or "unknown",
            priority=self._get_job_priority(job),
            status=JobStatus(job.get_status()),
            created_at=job.created_at or datetime.utcnow(),
            args=job.args or (),
            kwargs=job.kwargs or {},
            result=job.result,
            error=job.exc_info if job.is_failed else None,
            meta=job.meta or {}
        )

    def _get_job_priority(self, job: 'Job') -> JobPriority:
        """Determine job priority from queue name"""
        queue_name = job.origin
        for priority, name in QUEUE_NAMES.items():
            if name == queue_name:
                return priority
        return JobPriority.NORMAL

    def _save_job_info(
        self,
        job_id: str,
        func_name: str,
        priority: JobPriority,
        args: tuple,
        kwargs: dict,
        meta: Optional[Dict[str, Any]]
    ):
        """Save job info to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO job_queue
                    (job_id, func_name, priority, status, created_at, args, kwargs, meta)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    job_id,
                    func_name,
                    priority.value,
                    JobStatus.QUEUED.value,
                    datetime.utcnow().isoformat(),
                    json.dumps(args),
                    json.dumps(kwargs),
                    json.dumps(meta or {})
                ))
        except Exception:
            pass  # Table might not exist

    def _save_job_result(
        self,
        job_id: str,
        status: JobStatus,
        result: Any = None,
        error: Optional[str] = None
    ):
        """Save job result to database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE job_queue
                    SET status = ?, result = ?, error = ?, ended_at = ?
                    WHERE job_id = ?
                """, (
                    status.value,
                    json.dumps(result) if result else None,
                    error,
                    datetime.utcnow().isoformat(),
                    job_id
                ))
        except Exception:
            pass

    def _update_job_status(self, job_id: str, status: JobStatus):
        """Update job status in database"""
        try:
            with get_db() as conn:
                conn.execute("""
                    UPDATE job_queue SET status = ? WHERE job_id = ?
                """, (status.value, job_id))
        except Exception:
            pass

    def _get_job_from_db(self, job_id: str) -> Optional[JobInfo]:
        """Get job info from database"""
        try:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT * FROM job_queue WHERE job_id = ?",
                    (job_id,)
                ).fetchone()

                if row:
                    return JobInfo(
                        job_id=row["job_id"],
                        func_name=row["func_name"],
                        priority=JobPriority(row["priority"]),
                        status=JobStatus(row["status"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                        args=tuple(json.loads(row["args"] or "[]")),
                        kwargs=json.loads(row["kwargs"] or "{}"),
                        result=json.loads(row["result"]) if row["result"] else None,
                        error=row["error"],
                        meta=json.loads(row["meta"] or "{}")
                    )
        except Exception:
            pass
        return None

    def _get_result_from_db(self, job_id: str) -> Optional[JobResult]:
        """Get job result from database"""
        job = self._get_job_from_db(job_id)
        if job:
            return JobResult(
                job_id=job.job_id,
                status=job.status,
                result=job.result,
                error=job.error
            )
        return None

    def _list_jobs_from_db(
        self,
        priority: Optional[JobPriority],
        status: Optional[JobStatus],
        limit: int
    ) -> List[JobInfo]:
        """List jobs from database"""
        jobs = []
        try:
            with get_db() as conn:
                query = "SELECT * FROM job_queue WHERE 1=1"
                params = []

                if priority:
                    query += " AND priority = ?"
                    params.append(priority.value)
                if status:
                    query += " AND status = ?"
                    params.append(status.value)

                query += " ORDER BY created_at DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                for row in rows:
                    jobs.append(JobInfo(
                        job_id=row["job_id"],
                        func_name=row["func_name"],
                        priority=JobPriority(row["priority"]),
                        status=JobStatus(row["status"]),
                        created_at=datetime.fromisoformat(row["created_at"]),
                        args=tuple(json.loads(row["args"] or "[]")),
                        kwargs=json.loads(row["kwargs"] or "{}"),
                        result=json.loads(row["result"]) if row["result"] else None,
                        error=row["error"],
                        meta=json.loads(row["meta"] or "{}")
                    ))
        except Exception:
            pass
        return jobs


# Global job queue instance
_job_queue: Optional[JobQueue] = None


def get_job_queue() -> JobQueue:
    """Get the global JobQueue instance"""
    global _job_queue
    if _job_queue is None:
        _job_queue = JobQueue()
        _job_queue.connect()
    return _job_queue


def enqueue_job(
    func: Callable,
    *args,
    priority: JobPriority = JobPriority.NORMAL,
    **kwargs
) -> str:
    """Convenience function to enqueue a job"""
    return get_job_queue().enqueue(func, *args, priority=priority, **kwargs)


# Decorator for making functions queueable
def queueable(priority: JobPriority = JobPriority.NORMAL, timeout: int = 600):
    """
    Decorator to make a function queueable

    Usage:
        @queueable(priority=JobPriority.HIGH)
        def my_task(arg1, arg2):
            ...

        # Execute immediately
        my_task(1, 2)

        # Queue for async execution
        my_task.enqueue(1, 2)
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        def enqueue_wrapper(*args, **kwargs) -> str:
            return get_job_queue().enqueue(
                func, *args,
                priority=priority,
                timeout=timeout,
                **kwargs
            )

        wrapper.enqueue = enqueue_wrapper
        wrapper.__wrapped__ = func
        return wrapper

    return decorator
