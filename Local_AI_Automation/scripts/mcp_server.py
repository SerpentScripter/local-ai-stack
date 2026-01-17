#!/usr/bin/env python
"""
MCP Server CLI
Run the Local AI Hub MCP server for integration with Claude Code

Usage:
    python mcp_server.py              # Run stdio server
    python mcp_server.py --http       # Run HTTP/SSE server (for testing)
    python mcp_server.py --test       # Test tool execution
"""
import sys
import json
import asyncio
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.mcp_server import MCPServer, run_stdio_server


async def test_tools():
    """Test MCP tools"""
    server = MCPServer()

    print("=" * 50)
    print("  MCP Server Tool Test")
    print("=" * 50)

    # Test search_backlog
    print("\n[Test] search_backlog...")
    result = await server._tool_search_backlog({"limit": 5})
    print(f"  Found {result['count']} items")

    # Test list_services
    print("\n[Test] list_services...")
    result = await server._tool_list_services({})
    print(f"  Found {len(result['services'])} services")
    for svc in result['services']:
        print(f"    - {svc['name']}: {svc['status']}")

    # Test get_metrics
    print("\n[Test] get_system_metrics...")
    result = await server._tool_get_metrics({})
    print(f"  CPU: {result['cpu_percent']}%")
    print(f"  Memory: {result['memory']['percent']}%")
    if result.get('gpu'):
        print(f"  GPU: {result['gpu']['utilization']}%")

    # Test resource reading
    print("\n[Test] Reading hub://status...")
    result = await server._read_resource("hub://status")
    print(f"  Status: {result['status']}")
    print(f"  Services: {result['services_running']}/{result['services_total']}")

    print("\n" + "=" * 50)
    print("  All tests passed!")
    print("=" * 50)


async def run_http_server(host: str = "localhost", port: int = 8766):
    """Run HTTP server for testing (not full MCP SSE, just REST)"""
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import JSONResponse
    import uvicorn

    app = FastAPI(title="MCP Test Server")
    server = MCPServer()

    @app.post("/mcp")
    async def mcp_endpoint(message: dict):
        response = await server.handle_message(message)
        return response or {"status": "ok"}

    @app.get("/tools")
    async def list_tools():
        return await server._handle_list_tools()

    @app.post("/tools/{name}")
    async def call_tool(name: str, arguments: dict = {}):
        return await server._handle_call_tool({"name": name, "arguments": arguments})

    @app.get("/resources")
    async def list_resources():
        return await server._handle_list_resources()

    @app.get("/resources/read")
    async def read_resource(uri: str):
        return await server._handle_read_resource({"uri": uri})

    print(f"Starting HTTP test server on http://{host}:{port}")
    print("Endpoints:")
    print("  POST /mcp           - Raw MCP messages")
    print("  GET  /tools         - List tools")
    print("  POST /tools/{name}  - Call tool")
    print("  GET  /resources     - List resources")
    print("  GET  /resources/read?uri=... - Read resource")

    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


def main():
    parser = argparse.ArgumentParser(description="MCP Server for Local AI Hub")
    parser.add_argument("--http", action="store_true", help="Run HTTP test server")
    parser.add_argument("--port", type=int, default=8766, help="HTTP server port")
    parser.add_argument("--test", action="store_true", help="Run tool tests")
    args = parser.parse_args()

    if args.test:
        asyncio.run(test_tools())
    elif args.http:
        asyncio.run(run_http_server(port=args.port))
    else:
        # Run stdio server (default for MCP)
        print("Starting MCP stdio server...", file=sys.stderr)
        asyncio.run(run_stdio_server())


if __name__ == "__main__":
    main()
