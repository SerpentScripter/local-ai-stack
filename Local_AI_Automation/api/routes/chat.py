"""
LLM Chat Routes
Handles chat with Ollama models including streaming
"""
import os
import json
import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..database import get_db

router = APIRouter(prefix="/chat", tags=["Chat"])

OLLAMA_BASE = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


@router.get("/models")
async def list_chat_models():
    """List available Ollama models"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{OLLAMA_BASE}/api/tags", timeout=10)
            return response.json()
    except httpx.RequestError:
        return {"models": [], "error": "Ollama not available"}


@router.get("/stream")
async def stream_chat(prompt: str, model: str = "qwen2.5:14b", system: str = None):
    """Stream chat response from Ollama"""

    async def generate():
        try:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": True
            }
            if system:
                payload["system"] = system

            async with httpx.AsyncClient() as client:
                async with client.stream(
                    "POST",
                    f"{OLLAMA_BASE}/api/generate",
                    json=payload,
                    timeout=120.0
                ) as response:
                    async for line in response.aiter_lines():
                        if line:
                            try:
                                data = json.loads(line)
                                token = data.get("response", "")
                                done = data.get("done", False)
                                yield f"data: {json.dumps({'token': token, 'done': done})}\n\n"
                                if done:
                                    break
                            except json.JSONDecodeError:
                                continue
        except httpx.RequestError as e:
            yield f"data: {json.dumps({'error': str(e), 'done': True})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )


@router.post("/message")
async def send_chat_message(prompt: str, model: str = "qwen2.5:14b", system: str = None):
    """Send a chat message and get the full response (non-streaming)"""
    try:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False
        }
        if system:
            payload["system"] = system

        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{OLLAMA_BASE}/api/generate",
                json=payload,
                timeout=120.0
            )
            data = response.json()
            return {
                "response": data.get("response", ""),
                "model": model,
                "done": True
            }
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Ollama unavailable: {str(e)}")


@router.get("/history")
def get_chat_history(limit: int = 50):
    """Get recent chat history"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT * FROM chat_history
               ORDER BY created_at DESC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


@router.delete("/history")
def clear_chat_history():
    """Clear all chat history"""
    with get_db() as conn:
        conn.execute("DELETE FROM chat_history")
        return {"status": "cleared"}


@router.post("/history")
def save_chat_message(session_id: str, role: str, content: str, model: str = None):
    """Save a chat message to history"""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO chat_history (session_id, role, content, model)
               VALUES (?, ?, ?, ?)""",
            (session_id, role, content, model)
        )
        return {"status": "saved"}
