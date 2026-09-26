"""
shared/mcp_client.py
--------------------
A one-line way for an agent to call a tool on its MCP server.

HOW IT WORKS
  FastMCP's Client can point straight at a .py file. It starts that file
  as a background process, talks to it over stdio, and shuts it down after.
  So you do NOT need to start the MCP servers yourself - the agents do it.

USAGE INSIDE AN AGENT
    tools = McpToolbox("applicant_db_server.py")
    record = await tools.call("get_applicant", {"applicant_id": "APP001"})
"""

import json
from pathlib import Path

from fastmcp import Client

MCP_DIR = Path(__file__).resolve().parent.parent / "mcp_servers"


class McpToolbox:
    """Wraps one MCP server and remembers which tools were called."""

    def __init__(self, server_filename: str):
        self.server_path = str(MCP_DIR / server_filename)
        self.tools_called: list[str] = []

    async def call(self, tool_name: str, arguments: dict) -> dict:
        """Call one tool and return its result as a plain Python dict."""
        self.tools_called.append(tool_name)

        async with Client(self.server_path) as client:
            response = await client.call_tool(tool_name, arguments)

        return _unwrap(response)

    async def call_many(self, calls: list[tuple[str, dict]]) -> list[dict]:
        """
        Call several tools over ONE connection. Much faster than calling
        .call() repeatedly, because the server only starts once.
        """
        results = []
        async with Client(self.server_path) as client:
            for tool_name, arguments in calls:
                self.tools_called.append(tool_name)
                response = await client.call_tool(tool_name, arguments)
                results.append(_unwrap(response))
        return results


def _unwrap(response) -> dict:
    """
    FastMCP versions differ slightly in what they return. This handles all
    the common shapes so your code does not break after a library update.
    """
    # Newer FastMCP exposes the parsed result directly
    for attribute in ("data", "structured_content"):
        value = getattr(response, attribute, None)
        if isinstance(value, dict):
            return value

    # Otherwise dig the text out of the content blocks and parse the JSON
    content = getattr(response, "content", response)
    if isinstance(content, list) and content:
        text = getattr(content[0], "text", None)
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"value": text}

    if isinstance(response, dict):
        return response

    return {"value": str(response)}
