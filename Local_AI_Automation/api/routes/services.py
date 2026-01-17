"""
Service Control Routes
Handles starting, stopping, and monitoring Docker and native services
"""
import subprocess
import asyncio
import httpx
from typing import List
from fastapi import APIRouter, HTTPException

from ..websocket import broadcast_service_status

router = APIRouter(prefix="/services", tags=["Services"])

# Service Registry - defines all manageable services
SERVICES = {
    "ollama": {
        "name": "Ollama",
        "port": 11434,
        "type": "native",
        "health_url": "http://localhost:11434/api/tags",
        "container_name": None,
        "start_cmd": "ollama serve",
        "stop_cmd": "taskkill /F /IM ollama.exe"
    },
    "open-webui": {
        "name": "Open WebUI",
        "port": 3000,
        "type": "docker",
        "health_url": "http://localhost:3000",
        "container_name": "open-webui",
        "start_cmd": "docker start open-webui",
        "stop_cmd": "docker stop open-webui"
    },
    "langflow": {
        "name": "Langflow",
        "port": 7860,
        "type": "docker",
        "health_url": "http://localhost:7860/health",
        "container_name": "langflow",
        "start_cmd": "docker start langflow",
        "stop_cmd": "docker stop langflow"
    },
    "n8n": {
        "name": "n8n",
        "port": 5678,
        "type": "docker",
        "health_url": "http://localhost:5678/healthz",
        "container_name": "n8n",
        "start_cmd": "docker start n8n",
        "stop_cmd": "docker stop n8n"
    },
    "hub-api": {
        "name": "Hub API",
        "port": 8765,
        "type": "native",
        "health_url": "http://localhost:8765/health",
        "container_name": None,
        "start_cmd": None,  # Self - can't restart
        "stop_cmd": None
    }
}


async def check_service_health(url: str, timeout: float = 2.0) -> bool:
    """Check if a service is healthy by pinging its health endpoint"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout)
            return response.status_code < 500
    except Exception:
        return False


@router.get("", response_model=List[dict])
async def list_services():
    """List all services with their current status"""
    # Parallelize health checks for better performance
    service_items = list(SERVICES.items())
    health_checks = [
        check_service_health(config["health_url"])
        for _, config in service_items
    ]
    health_results = await asyncio.gather(*health_checks)

    results = []
    for (service_id, config), is_healthy in zip(service_items, health_results):
        results.append({
            "id": service_id,
            "name": config["name"],
            "port": config["port"],
            "type": config["type"],
            "status": "running" if is_healthy else "stopped",
            "health_url": config["health_url"],
            "container_name": config["container_name"]
        })
    return results


@router.post("/{service_id}/start")
async def start_service(service_id: str):
    """Start a service"""
    if service_id not in SERVICES:
        raise HTTPException(status_code=404, detail="Service not found")

    config = SERVICES[service_id]
    if not config["start_cmd"]:
        raise HTTPException(status_code=400, detail="Service cannot be started via API")

    # Broadcast starting status
    await broadcast_service_status(service_id, "starting")

    try:
        if config["type"] == "docker":
            result = subprocess.run(
                config["start_cmd"].split(),
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                await broadcast_service_status(service_id, "error")
                raise HTTPException(status_code=500, detail=result.stderr)
        else:
            # Native service - start in background
            subprocess.Popen(
                config["start_cmd"],
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

        # Wait a bit for service to start
        await asyncio.sleep(2)

        # Check if it started successfully
        is_healthy = await check_service_health(config["health_url"])
        status = "running" if is_healthy else "starting"
        await broadcast_service_status(service_id, status)

        return {"service": service_id, "status": status}

    except subprocess.TimeoutExpired:
        await broadcast_service_status(service_id, "error")
        raise HTTPException(status_code=500, detail="Service start timeout")


@router.post("/{service_id}/stop")
async def stop_service(service_id: str):
    """Stop a service"""
    if service_id not in SERVICES:
        raise HTTPException(status_code=404, detail="Service not found")

    config = SERVICES[service_id]
    if not config["stop_cmd"]:
        raise HTTPException(status_code=400, detail="Service cannot be stopped via API")

    # Broadcast stopping status
    await broadcast_service_status(service_id, "stopping")

    try:
        result = subprocess.run(
            config["stop_cmd"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )

        # Check final status
        await asyncio.sleep(1)
        is_healthy = await check_service_health(config["health_url"])
        status = "running" if is_healthy else "stopped"
        await broadcast_service_status(service_id, status)

        return {"service": service_id, "status": status}

    except subprocess.TimeoutExpired:
        await broadcast_service_status(service_id, "error")
        raise HTTPException(status_code=500, detail="Service stop timeout")


@router.post("/{service_id}/restart")
async def restart_service(service_id: str):
    """Restart a service"""
    await stop_service(service_id)
    await asyncio.sleep(2)
    return await start_service(service_id)


@router.get("/{service_id}/logs")
def get_service_logs(service_id: str, lines: int = 50):
    """Get recent logs for a Docker service"""
    if service_id not in SERVICES:
        raise HTTPException(status_code=404, detail="Service not found")

    config = SERVICES[service_id]
    if config["type"] != "docker" or not config["container_name"]:
        raise HTTPException(status_code=400, detail="Logs only available for Docker services")

    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines), config["container_name"]],
            capture_output=True,
            text=True,
            timeout=10
        )
        return {
            "service": service_id,
            "logs": result.stdout + result.stderr,
            "lines": lines
        }
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="Log retrieval timeout")
