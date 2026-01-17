"""
System Metrics Routes
Handles CPU, memory, disk, and GPU monitoring
"""
import subprocess
import psutil
from datetime import datetime
from fastapi import APIRouter

from ..database import get_db

router = APIRouter(prefix="/system", tags=["System"])


def get_gpu_metrics() -> dict:
    """Get NVIDIA GPU metrics using nvidia-smi"""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
                "--format=csv,noheader,nounits"
            ],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            if len(parts) >= 4:
                gpu_util = float(parts[0])
                mem_used = float(parts[1])
                mem_total = float(parts[2])
                temp = int(parts[3])
                return {
                    "gpu_percent": gpu_util,
                    "gpu_memory_percent": (mem_used / mem_total) * 100 if mem_total > 0 else 0,
                    "gpu_temp": temp
                }
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        pass
    return {"gpu_percent": None, "gpu_memory_percent": None, "gpu_temp": None}


@router.get("/metrics")
def get_system_metrics() -> dict:
    """Get current system metrics"""
    # CPU and Memory
    cpu_percent = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()

    # Disk (D: drive for Windows, / for Linux)
    try:
        disk = psutil.disk_usage("D:")
    except Exception:
        try:
            disk = psutil.disk_usage("/")
        except Exception:
            disk = None

    # GPU
    gpu_metrics = get_gpu_metrics()

    metrics = {
        "cpu_percent": cpu_percent,
        "memory_percent": memory.percent,
        "memory_used_gb": memory.used / (1024**3),
        "disk_percent": disk.percent if disk else 0,
        "disk_used_gb": disk.used / (1024**3) if disk else 0,
        **gpu_metrics,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Store metrics in database for history
    with get_db() as conn:
        conn.execute(
            """INSERT INTO system_metrics
               (cpu_percent, memory_percent, disk_percent, gpu_percent, gpu_temp)
               VALUES (?, ?, ?, ?, ?)""",
            (cpu_percent, memory.percent,
             disk.percent if disk else 0,
             gpu_metrics.get("gpu_percent"),
             gpu_metrics.get("gpu_temp"))
        )

    return metrics


@router.get("/metrics/history")
def get_metrics_history(minutes: int = 60):
    """Get historical system metrics"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM system_metrics
               WHERE recorded_at >= datetime('now', ?)
               ORDER BY recorded_at ASC""",
            (f"-{minutes} minutes",)
        ).fetchall()
        return [dict(row) for row in rows]


@router.get("/info")
def get_system_info():
    """Get system information"""
    import platform
    return {
        "platform": platform.system(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": psutil.cpu_count(),
        "memory_total_gb": psutil.virtual_memory().total / (1024**3)
    }
