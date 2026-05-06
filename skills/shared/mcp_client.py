"""Dual-mode MCP client — works both locally (direct mcpserver) and in sandbox (MCP proxy).

Local mode: POST JSON-RPC to mcpserver's /sse endpoint (sync execution path).
Sandbox mode: POST JSON-RPC to MCP_PROXY_URL with Bearer MCP_PROXY_TOKEN.
"""

import os
import uuid
from typing import Any, Optional

import httpx


class MCPToolError(Exception):
    """MCP tool returned an error."""
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(f"MCP tool error ({code}): {message}")


class MCPConnectionError(Exception):
    """Failed to connect to MCP server."""
    pass


class MCPClient:
    """Lightweight MCP client using sync HTTP POST (JSON-RPC 2.0)."""

    def __init__(self, url: str, token: Optional[str] = None, timeout: float = 300):
        self.url = url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.Client] = None

    def connect(self):
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        self._client = httpx.Client(headers=headers, timeout=httpx.Timeout(self.timeout, connect=10.0))

    def close(self):
        if self._client:
            self._client.close()
            self._client = None

    def call_tool(self, name: str, arguments: dict[str, Any], timeout: Optional[float] = None) -> dict:
        if not self._client:
            self.connect()

        body = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }

        effective_timeout = timeout or self.timeout
        try:
            resp = self._client.post(self.url, json=body, timeout=effective_timeout)
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise MCPToolError(-1, f"HTTP {e.response.status_code}: {e.response.text[:500]}")
        except httpx.ConnectError as e:
            raise MCPConnectionError(f"Cannot connect to MCP server at {self.url}: {e}")
        except httpx.TimeoutException as e:
            raise MCPToolError(-1, f"MCP call timed out after {effective_timeout}s: {e}")

        result = resp.json()

        if "error" in result:
            err = result["error"]
            raise MCPToolError(err.get("code", -1), err.get("message", "Unknown error"))

        return result.get("result", {})

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        self.close()


def extract_text_content(result: dict) -> str:
    """Extract all text content from an MCP tool result."""
    content = result.get("content", [])
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if c.get("type") == "text")
    if isinstance(content, str):
        return content
    return str(result)


def create_mcp_client(cfg: dict) -> MCPClient:
    """Auto-detect mode and create appropriate MCP client.

    Priority:
    1. Sandbox mode: MCP_PROXY_URL + MCP_PROXY_TOKEN env vars
    2. Local mode: MCP_SERVER_URL env var or config.json mcp_server.url
    """
    proxy_url = os.environ.get("MCP_PROXY_URL")
    proxy_token = os.environ.get("MCP_PROXY_TOKEN")

    if proxy_url and proxy_token:
        print(f"  [MCP] Sandbox mode → {proxy_url}")
        return MCPClient(url=proxy_url, token=proxy_token, timeout=600)

    url = os.environ.get("MCP_SERVER_URL") or cfg.get("mcp_server", {}).get("url", "")
    if not url:
        raise MCPConnectionError(
            "MCP server URL not configured. Set MCP_SERVER_URL env var "
            "or add mcp_server.url to config.json"
        )

    # Local mcpserver: POST to /message endpoint for sync JSON-RPC
    if url.endswith("/sse"):
        url = url[:-4] + "/message"
    elif not url.endswith("/message"):
        url = url.rstrip("/") + "/message"

    timeout = cfg.get("mcp_server", {}).get("timeout", 300)
    print(f"  [MCP] Local mode → {url}")
    return MCPClient(url=url, timeout=timeout)
