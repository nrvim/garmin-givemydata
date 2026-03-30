#!/usr/bin/env python3
"""Entry point for Garmin MCP server — avoids module import issues."""

import sys
from pathlib import Path

# Ensure the project is on the path
sys.path.insert(0, str(Path(__file__).parent))

from garmin_mcp.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
