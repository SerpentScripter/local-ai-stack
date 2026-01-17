"""
WebSocket connection management for real-time updates
"""
import asyncio
from typing import List
from fastapi import WebSocket


class ConnectionManager:
    """Manages WebSocket connections for real-time broadcasting"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[WS] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        """Remove a WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        print(f"[WS] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        """Broadcast a message to all connected clients"""
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.append(connection)

        # Clean up disconnected clients
        for conn in disconnected:
            self.disconnect(conn)

    async def send_personal(self, websocket: WebSocket, message: dict):
        """Send a message to a specific client"""
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)


# Global connection manager instance
manager = ConnectionManager()


async def broadcast_service_status(service_id: str, status: str):
    """Broadcast service status change to all clients"""
    await manager.broadcast({
        "type": "service_status",
        "payload": {
            "id": service_id,
            "status": status
        }
    })


async def broadcast_metrics(metrics: dict):
    """Broadcast system metrics to all clients"""
    await manager.broadcast({
        "type": "metrics",
        "payload": metrics
    })


async def broadcast_agent_update(agent_type: str, status: str, data: dict = None):
    """Broadcast agent status update to all clients"""
    await manager.broadcast({
        "type": "agent_update",
        "payload": {
            "agent_type": agent_type,
            "status": status,
            "data": data or {}
        }
    })
