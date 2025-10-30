#!/usr/bin/env python3
"""FastAPI MCP Server for Claude Code

Provides tools to interact with Zenzefi Backend API endpoints for testing and validation.
"""

from fastmcp import FastMCP
from app.main import app

# Generate MCP server from FastAPI application
mcp = FastMCP.from_fastapi(app=app)

if __name__ == "__main__":
    mcp.run()
