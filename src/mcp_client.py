"""
MCP (Model Context Protocol) client for connecting to external MCP servers.

Provides functionality to discover, connect to, and interact with MCP servers
that expose tools, resources, and prompts.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from threading import Lock

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False
    ClientSession = None
    StdioServerParameters = None
    stdio_client = None

logger = logging.getLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    command: str
    args: List[str] = field(default_factory=list)
    env: Optional[Dict[str, str]] = None
    description: str = ""
    enabled: bool = True


@dataclass
class MCPServerConnection:
    """Represents an active connection to an MCP server."""

    config: MCPServerConfig
    session: Any  # ClientSession
    read_stream: Any
    write_stream: Any
    connected_at: datetime = field(default_factory=datetime.utcnow)
    available_tools: List[Dict[str, Any]] = field(default_factory=list)
    available_resources: List[Dict[str, Any]] = field(default_factory=list)
    available_prompts: List[Dict[str, Any]] = field(default_factory=list)


class MCPClient:
    """Client for managing connections to external MCP servers."""

    def __init__(self):
        if not MCP_AVAILABLE:
            logger.warning("MCP SDK not available. MCP functionality will be disabled.")

        self.servers: Dict[str, MCPServerConfig] = {}
        self.connections: Dict[str, MCPServerConnection] = {}
        self.lock = Lock()

    def is_available(self) -> bool:
        """Check if MCP SDK is available."""
        return MCP_AVAILABLE

    def register_server(self, config: MCPServerConfig) -> None:
        """Register an MCP server configuration."""
        with self.lock:
            if config.name in self.servers:
                logger.warning(f"Overwriting existing MCP server configuration: {config.name}")
            self.servers[config.name] = config
            logger.info(f"Registered MCP server: {config.name}")

    def unregister_server(self, name: str) -> bool:
        """Unregister an MCP server."""
        with self.lock:
            if name in self.servers:
                del self.servers[name]
                logger.info(f"Unregistered MCP server: {name}")
                return True
            return False

    def list_servers(self) -> List[MCPServerConfig]:
        """List all registered MCP servers."""
        with self.lock:
            return list(self.servers.values())

    def get_server(self, name: str) -> Optional[MCPServerConfig]:
        """Get a specific server configuration."""
        with self.lock:
            return self.servers.get(name)

    async def connect_server(self, name: str) -> bool:
        """
        Connect to an MCP server.

        Returns True if connection successful, False otherwise.
        """
        if not MCP_AVAILABLE:
            logger.error("Cannot connect to MCP server: MCP SDK not available")
            return False

        config = self.get_server(name)
        if not config:
            logger.error(f"MCP server not found: {name}")
            return False

        if not config.enabled:
            logger.warning(f"MCP server is disabled: {name}")
            return False

        # Check if already connected
        if name in self.connections:
            logger.info(f"Already connected to MCP server: {name}")
            return True

        try:
            # Create server parameters
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env,
            )

            # Connect to server
            read, write = await stdio_client(server_params)
            session = ClientSession(read, write)

            # Initialize session
            await session.initialize()

            # List available capabilities
            available_tools = []
            available_resources = []
            available_prompts = []

            try:
                # List tools
                tools_response = await session.list_tools()
                if tools_response and hasattr(tools_response, "tools"):
                    available_tools = [
                        {
                            "name": tool.name,
                            "description": getattr(tool, "description", ""),
                            "input_schema": getattr(tool, "inputSchema", {}),
                        }
                        for tool in tools_response.tools
                    ]
            except Exception as e:
                logger.warning(f"Could not list tools from {name}: {e}")

            try:
                # List resources
                resources_response = await session.list_resources()
                if resources_response and hasattr(resources_response, "resources"):
                    available_resources = [
                        {
                            "uri": resource.uri,
                            "name": getattr(resource, "name", ""),
                            "description": getattr(resource, "description", ""),
                            "mimeType": getattr(resource, "mimeType", None),
                        }
                        for resource in resources_response.resources
                    ]
            except Exception as e:
                logger.warning(f"Could not list resources from {name}: {e}")

            try:
                # List prompts
                prompts_response = await session.list_prompts()
                if prompts_response and hasattr(prompts_response, "prompts"):
                    available_prompts = [
                        {
                            "name": prompt.name,
                            "description": getattr(prompt, "description", ""),
                            "arguments": getattr(prompt, "arguments", []),
                        }
                        for prompt in prompts_response.prompts
                    ]
            except Exception as e:
                logger.warning(f"Could not list prompts from {name}: {e}")

            # Store connection
            connection = MCPServerConnection(
                config=config,
                session=session,
                read_stream=read,
                write_stream=write,
                available_tools=available_tools,
                available_resources=available_resources,
                available_prompts=available_prompts,
            )

            with self.lock:
                self.connections[name] = connection

            logger.info(
                f"Connected to MCP server '{name}': "
                f"{len(available_tools)} tools, "
                f"{len(available_resources)} resources, "
                f"{len(available_prompts)} prompts"
            )

            return True

        except ConnectionError as e:
            logger.error(f"Connection failed for MCP server '{name}': {e}")
            return False
        except ValueError as e:
            logger.error(f"Invalid configuration for MCP server '{name}': {e}")
            return False
        except TimeoutError as e:
            logger.error(f"Connection timeout for MCP server '{name}': {e}")
            return False
        except FileNotFoundError as e:
            logger.error(f"Command not found for MCP server '{name}': {e}")
            return False
        except PermissionError as e:
            logger.error(f"Permission denied for MCP server '{name}': {e}")
            return False
        except Exception as e:
            logger.exception(f"Unexpected error connecting to MCP server '{name}': {e}")
            return False

    async def disconnect_server(self, name: str) -> bool:
        """Disconnect from an MCP server."""
        with self.lock:
            if name not in self.connections:
                logger.warning(f"Not connected to MCP server: {name}")
                return False

            connection = self.connections[name]
            del self.connections[name]

        try:
            # Close the session gracefully
            # The MCP SDK handles cleanup when session is garbage collected
            logger.info(f"Disconnected from MCP server: {name}")
            return True
        except Exception as e:
            logger.exception(f"Unexpected error disconnecting from MCP server '{name}': {e}")
            return False

    def list_connected_servers(self) -> List[str]:
        """List names of currently connected servers."""
        with self.lock:
            return list(self.connections.keys())

    def get_connection(self, name: str) -> Optional[MCPServerConnection]:
        """Get an active server connection."""
        with self.lock:
            return self.connections.get(name)

    async def call_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """
        Call a tool on an MCP server.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool response
        """
        connection = self.get_connection(server_name)
        if not connection:
            raise ValueError(f"Not connected to MCP server: {server_name}")

        try:
            response = await connection.session.call_tool(tool_name, arguments)
            return response
        except Exception as e:
            logger.error(f"Error calling tool '{tool_name}' on server '{server_name}': {e}")
            raise

    async def read_resource(self, server_name: str, uri: str) -> Any:
        """
        Read a resource from an MCP server.

        Args:
            server_name: Name of the MCP server
            uri: Resource URI

        Returns:
            Resource content
        """
        connection = self.get_connection(server_name)
        if not connection:
            raise ValueError(f"Not connected to MCP server: {server_name}")

        try:
            response = await connection.session.read_resource(uri)
            return response
        except Exception as e:
            logger.error(f"Error reading resource '{uri}' from server '{server_name}': {e}")
            raise

    async def get_prompt(
        self, server_name: str, prompt_name: str, arguments: Dict[str, Any] = None
    ) -> Any:
        """
        Get a prompt from an MCP server.

        Args:
            server_name: Name of the MCP server
            prompt_name: Name of the prompt
            arguments: Prompt arguments

        Returns:
            Prompt content
        """
        connection = self.get_connection(server_name)
        if not connection:
            raise ValueError(f"Not connected to MCP server: {server_name}")

        try:
            response = await connection.session.get_prompt(prompt_name, arguments or {})
            return response
        except Exception as e:
            logger.error(f"Error getting prompt '{prompt_name}' from server '{server_name}': {e}")
            raise

    def get_all_tools(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get all available tools from all connected MCP servers.

        Returns dict mapping server name to list of tools.
        """
        with self.lock:
            return {
                name: connection.available_tools for name, connection in self.connections.items()
            }

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about MCP connections."""
        with self.lock:
            total_tools = sum(len(conn.available_tools) for conn in self.connections.values())
            total_resources = sum(
                len(conn.available_resources) for conn in self.connections.values()
            )
            total_prompts = sum(len(conn.available_prompts) for conn in self.connections.values())

            return {
                "mcp_available": MCP_AVAILABLE,
                "registered_servers": len(self.servers),
                "connected_servers": len(self.connections),
                "total_tools": total_tools,
                "total_resources": total_resources,
                "total_prompts": total_prompts,
                "servers": [
                    {
                        "name": name,
                        "enabled": config.enabled,
                        "connected": name in self.connections,
                        "description": config.description,
                    }
                    for name, config in self.servers.items()
                ],
            }


# Global MCP client instance
mcp_client = MCPClient()
