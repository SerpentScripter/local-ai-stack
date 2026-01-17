#!/usr/bin/env python3
"""
Local AI Hub API Server - Entry Point

This is the main entry point for the API server.
The actual implementation is in the modular api/ package.

Run: python backlog_api.py
Access: http://localhost:8765
"""
import os
import sys
import socket
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

# Add parent directory to path for api package import
sys.path.insert(0, str(Path(__file__).parent.parent))

# Load environment variables
load_dotenv(Path(__file__).parent.parent.parent / ".env")

# Configuration
PORT = int(os.getenv("BACKLOG_API_PORT", 8765))
HOST = os.getenv("BACKLOG_API_HOST", "127.0.0.1")


def is_port_in_use(port: int) -> bool:
    """Check if a port is already in use"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def main():
    """Main entry point"""
    print("=" * 50)
    print("  LOCAL AI HUB API SERVER v2.0")
    print("=" * 50)
    print()

    # Check if port is already in use
    if is_port_in_use(PORT):
        print(f"[WARNING] Port {PORT} is already in use!")
        print("[INFO] Another instance may be running.")
        print("[INFO] Use BACKLOG_API_PORT env var to change port.")
        print()

    print(f"[INFO] Starting server on {HOST}:{PORT}")
    print(f"[INFO] Dashboard: http://localhost:{PORT}")
    print(f"[INFO] API Docs:  http://localhost:{PORT}/docs")
    print()

    # Import and run the FastAPI app from the api package
    from api.main import app

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        log_level="info"
    )


if __name__ == "__main__":
    main()
