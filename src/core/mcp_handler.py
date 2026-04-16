"""
CRAVE MCP Handler — Model Context Protocol Client
Save to: D:\\CRAVE\\src\\core\\mcp_handler.py

Manages local MCP servers (Filesystem, Fetch, Memory) and exposes a simple
call_tool() interface for the Orchestrator.

Architecture:
  Orchestrator → MCPHandler → [Server Process] ← stdin/stdout (JSON-RPC 2.0)

Each MCP server runs as a child process communicating via stdio transport.
Servers are defined in config/mcp_servers.json.
"""

import os
import sys
import json
import subprocess
import threading
import logging
from typing import Optional, Any

logger = logging.getLogger("crave.core.mcp_handler")

CRAVE_ROOT = os.environ.get("CRAVE_ROOT", r"D:\CRAVE")
MCP_CONFIG_PATH = os.path.join(CRAVE_ROOT, "config", "mcp_servers.json")


class MCPServerProcess:
    """Manages a single MCP server child process."""

    def __init__(self, name: str, command: str, args: list, env: dict = None):
        self.name = name
        self.command = command
        self.args = args
        self.env = env or {}
        self.process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._request_id = 0
        self._available_tools: list[dict] = []

    def start(self) -> bool:
        """Start the MCP server process."""
        try:
            # Build environment
            full_env = os.environ.copy()
            for k, v in self.env.items():
                # Support ${VAR} expansion from os.environ
                if v.startswith("${") and v.endswith("}"):
                    var_name = v[2:-1]
                    full_env[k] = os.environ.get(var_name, "")
                else:
                    full_env[k] = v

            cmd = [self.command] + self.args
            logger.info(f"[MCP] Starting server '{self.name}': {' '.join(cmd)}")

            self.process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=full_env,
                shell=True if os.name == "nt" else False,
            )

            # Initialize the connection
            self._initialize()
            return True

        except FileNotFoundError:
            logger.error(f"[MCP] Command not found for '{self.name}': {self.command}")
            return False
        except Exception as e:
            logger.error(f"[MCP] Failed to start '{self.name}': {e}")
            return False

    def stop(self):
        """Stop the MCP server process."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except:
                try:
                    self.process.kill()
                except:
                    pass
            self.process = None
            logger.info(f"[MCP] Server '{self.name}' stopped.")

    def _send_request(self, method: str, params: dict = None) -> dict:
        """Send a JSON-RPC 2.0 request and return the response."""
        if not self.process or self.process.poll() is not None:
            return {"error": "Server not running"}

        with self._lock:
            self._request_id += 1
            request = {
                "jsonrpc": "2.0",
                "id": self._request_id,
                "method": method,
            }
            if params:
                request["params"] = params

            try:
                request_str = json.dumps(request) + "\n"
                self.process.stdin.write(request_str.encode("utf-8"))
                self.process.stdin.flush()

                # Read response line
                response_line = self.process.stdout.readline()
                if not response_line:
                    return {"error": "No response from server"}

                return json.loads(response_line.decode("utf-8"))

            except Exception as e:
                return {"error": str(e)}

    def _initialize(self):
        """Send the initialize handshake."""
        resp = self._send_request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "CRAVE", "version": "1.0.0"},
        })

        if "error" not in resp:
            # Send initialized notification
            self._send_request("notifications/initialized")

            # Discover available tools
            tools_resp = self._send_request("tools/list")
            if "result" in tools_resp:
                self._available_tools = tools_resp["result"].get("tools", [])
                logger.info(f"[MCP] '{self.name}' ready — {len(self._available_tools)} tools available")
            else:
                logger.warning(f"[MCP] '{self.name}' initialized but tool discovery failed")

    def call_tool(self, tool_name: str, arguments: dict = None) -> dict:
        """Call a specific tool on this MCP server."""
        resp = self._send_request("tools/call", {
            "name": tool_name,
            "arguments": arguments or {},
        })

        if "result" in resp:
            return resp["result"]
        elif "error" in resp:
            return {"error": resp["error"]}
        return {"error": "Unknown response format"}

    @property
    def tools(self) -> list[dict]:
        return self._available_tools

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None


class MCPHandler:
    """
    Main MCP client that manages multiple MCP server processes.
    
    Usage:
        handler = MCPHandler()
        handler.start_all()
        result = handler.call_tool("filesystem", "read_file", {"path": "/data/test.txt"})
        handler.stop_all()
    """

    def __init__(self):
        self._servers: dict[str, MCPServerProcess] = {}
        self._config = self._load_config()

    def _load_config(self) -> dict:
        """Load MCP server configurations from config/mcp_servers.json."""
        if not os.path.exists(MCP_CONFIG_PATH):
            logger.warning(f"[MCP] Config not found at {MCP_CONFIG_PATH}")
            return {}

        try:
            with open(MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[MCP] Failed to load config: {e}")
            return {}

    def start_all(self) -> dict[str, bool]:
        """Start all configured MCP servers. Returns {name: success}."""
        results = {}
        for name, cfg in self._config.items():
            server = MCPServerProcess(
                name=name,
                command=cfg.get("command", "npx"),
                args=cfg.get("args", []),
                env=cfg.get("env", {}),
            )
            success = server.start()
            if success:
                self._servers[name] = server
            results[name] = success
            logger.info(f"[MCP] {name}: {'✅ started' if success else '❌ failed'}")

        return results

    def start_server(self, name: str) -> bool:
        """Start a single MCP server by name."""
        if name not in self._config:
            logger.error(f"[MCP] Unknown server: {name}")
            return False

        cfg = self._config[name]
        server = MCPServerProcess(
            name=name,
            command=cfg.get("command", "npx"),
            args=cfg.get("args", []),
            env=cfg.get("env", {}),
        )
        success = server.start()
        if success:
            self._servers[name] = server
        return success

    def stop_all(self):
        """Stop all running MCP servers."""
        for name, server in self._servers.items():
            server.stop()
        self._servers.clear()
        logger.info("[MCP] All servers stopped.")

    def stop_server(self, name: str):
        """Stop a specific MCP server."""
        if name in self._servers:
            self._servers[name].stop()
            del self._servers[name]

    def call_tool(self, server_name: str, tool_name: str, arguments: dict = None) -> dict:
        """
        Call a tool on a specific MCP server.
        
        Args:
            server_name: e.g. "filesystem", "fetch", "memory"
            tool_name: e.g. "read_file", "fetch", "create_entities"
            arguments: tool-specific arguments dict
            
        Returns:
            Result dict from the MCP server
        """
        if server_name not in self._servers:
            return {"error": f"Server '{server_name}' not running. Available: {list(self._servers.keys())}"}

        server = self._servers[server_name]
        if not server.is_running:
            return {"error": f"Server '{server_name}' process has died."}

        return server.call_tool(tool_name, arguments)

    def list_tools(self, server_name: str = None) -> dict[str, list]:
        """
        List available tools. If server_name is specified, list tools for that server.
        Otherwise, list tools for all servers.
        """
        if server_name:
            if server_name in self._servers:
                return {server_name: self._servers[server_name].tools}
            return {}

        return {name: server.tools for name, server in self._servers.items()}

    def status(self) -> dict[str, dict]:
        """Get status of all servers."""
        return {
            name: {
                "running": server.is_running,
                "tools_count": len(server.tools),
            }
            for name, server in self._servers.items()
        }


# ── Global singleton ─────────────────────────────────────────────────────────

_global_mcp: Optional[MCPHandler] = None


def get_mcp_handler() -> MCPHandler:
    """Return the global MCPHandler singleton."""
    global _global_mcp
    if _global_mcp is None:
        _global_mcp = MCPHandler()
    return _global_mcp
