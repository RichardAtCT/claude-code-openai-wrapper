"""
Tool definitions and handling for OpenAI-compatible function calling.
Maps Claude Code tools to OpenAI function calling format.
"""

from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field
from enum import Enum
import json
import logging

logger = logging.getLogger(__name__)


class ToolType(str, Enum):
    """Available Claude Code tools."""
    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    BASH = "bash"
    SEARCH = "search"
    GREP = "grep"
    LS = "ls"
    CD = "cd"
    
    # Advanced tools
    WEB_SEARCH = "web_search"
    WEB_FETCH = "web_fetch"
    TODO_READ = "todo_read"
    TODO_WRITE = "todo_write"
    
    # Future tools
    GIT = "git"
    DOCKER = "docker"
    K8S = "kubectl"


class ToolParameter(BaseModel):
    """OpenAI-compatible tool parameter definition."""
    type: str
    description: str
    required: bool = True
    enum: Optional[List[str]] = None
    default: Optional[Any] = None


class ToolFunction(BaseModel):
    """OpenAI-compatible function definition."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON Schema format


class Tool(BaseModel):
    """OpenAI-compatible tool definition."""
    type: str = "function"
    function: ToolFunction


class ToolCall(BaseModel):
    """Tool call in a message."""
    id: str
    type: str = "function"
    function: Dict[str, Any]  # Contains 'name' and 'arguments'


class ToolChoice(BaseModel):
    """Tool choice configuration."""
    type: str  # "none", "auto", or "function"
    function: Optional[Dict[str, str]] = None  # {"name": "function_name"}


# Tool definitions mapping Claude Code tools to OpenAI format
CLAUDE_TOOLS = {
    ToolType.READ: Tool(
        type="function",
        function=ToolFunction(
            name="read_file",
            description="Read the contents of a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to read"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding",
                        "default": "utf-8"
                    }
                },
                "required": ["path"]
            }
        )
    ),
    ToolType.WRITE: Tool(
        type="function",
        function=ToolFunction(
            name="write_file",
            description="Write content to a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to write"
                    },
                    "content": {
                        "type": "string",
                        "description": "Content to write to the file"
                    },
                    "encoding": {
                        "type": "string",
                        "description": "File encoding",
                        "default": "utf-8"
                    }
                },
                "required": ["path", "content"]
            }
        )
    ),
    ToolType.EDIT: Tool(
        type="function",
        function=ToolFunction(
            name="edit_file",
            description="Edit a file by replacing text",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Path to the file to edit"
                    },
                    "old_text": {
                        "type": "string",
                        "description": "Text to replace"
                    },
                    "new_text": {
                        "type": "string",
                        "description": "New text to insert"
                    }
                },
                "required": ["path", "old_text", "new_text"]
            }
        )
    ),
    ToolType.BASH: Tool(
        type="function",
        function=ToolFunction(
            name="run_command",
            description="Execute a bash command",
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "Bash command to execute"
                    },
                    "cwd": {
                        "type": "string",
                        "description": "Working directory for the command",
                        "default": "."
                    },
                    "timeout": {
                        "type": "integer",
                        "description": "Command timeout in seconds",
                        "default": 30
                    }
                },
                "required": ["command"]
            }
        )
    ),
    ToolType.SEARCH: Tool(
        type="function",
        function=ToolFunction(
            name="search_files",
            description="Search for files by name pattern",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Search pattern (glob format)"
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in",
                        "default": "."
                    }
                },
                "required": ["pattern"]
            }
        )
    ),
    ToolType.GREP: Tool(
        type="function",
        function=ToolFunction(
            name="search_in_files",
            description="Search for text within files",
            parameters={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regular expression pattern to search for"
                    },
                    "path": {
                        "type": "string",
                        "description": "Path to search in",
                        "default": "."
                    },
                    "file_pattern": {
                        "type": "string",
                        "description": "File pattern to search within",
                        "default": "*"
                    }
                },
                "required": ["pattern"]
            }
        )
    ),
    ToolType.LS: Tool(
        type="function",
        function=ToolFunction(
            name="list_directory",
            description="List contents of a directory",
            parameters={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Directory path to list",
                        "default": "."
                    },
                    "show_hidden": {
                        "type": "boolean",
                        "description": "Show hidden files",
                        "default": False
                    }
                },
                "required": []
            }
        )
    ),
    ToolType.WEB_SEARCH: Tool(
        type="function",
        function=ToolFunction(
            name="web_search",
            description="Search the web for information",
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 5
                    }
                },
                "required": ["query"]
            }
        )
    ),
    ToolType.WEB_FETCH: Tool(
        type="function",
        function=ToolFunction(
            name="fetch_url",
            description="Fetch content from a URL",
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL to fetch"
                    },
                    "extract_text": {
                        "type": "boolean",
                        "description": "Extract text content only",
                        "default": True
                    }
                },
                "required": ["url"]
            }
        )
    ),
}


class ToolRegistry:
    """Registry for managing available tools."""
    
    def __init__(self):
        self.tools = CLAUDE_TOOLS.copy()
        self.enabled_tools = set(ToolType)  # All tools enabled by default
        
    def get_tool(self, name: str) -> Optional[Tool]:
        """Get a tool by name."""
        for tool_type, tool in self.tools.items():
            if tool.function.name == name:
                return tool
        return None
    
    def get_enabled_tools(self) -> List[Tool]:
        """Get list of currently enabled tools."""
        return [
            tool for tool_type, tool in self.tools.items()
            if tool_type in self.enabled_tools
        ]
    
    def enable_tools(self, tools: List[str]):
        """Enable specific tools."""
        for tool_name in tools:
            try:
                tool_type = ToolType(tool_name)
                self.enabled_tools.add(tool_type)
            except ValueError:
                logger.warning(f"Unknown tool type: {tool_name}")
    
    def disable_tools(self, tools: List[str]):
        """Disable specific tools."""
        for tool_name in tools:
            try:
                tool_type = ToolType(tool_name)
                self.enabled_tools.discard(tool_type)
            except ValueError:
                logger.warning(f"Unknown tool type: {tool_name}")
    
    def set_allowed_tools(self, tools: Optional[List[str]]):
        """Set the list of allowed tools (disables all others)."""
        if tools is None:
            self.enabled_tools = set(ToolType)
        else:
            self.enabled_tools = set()
            self.enable_tools(tools)
    
    def format_for_openai(self) -> List[Dict[str, Any]]:
        """Format enabled tools for OpenAI API response."""
        return [tool.model_dump() for tool in self.get_enabled_tools()]


# Global tool registry instance
tool_registry = ToolRegistry()


def parse_tool_response(claude_response: str) -> Optional[Dict[str, Any]]:
    """
    Parse Claude's tool usage from response text.
    Claude may use tools inline, so we need to extract tool calls.
    """
    # This is a simplified parser - in practice, you'd need to handle
    # Claude's actual tool usage format
    tool_calls = []
    
    # Look for patterns like:
    # <tool>read_file</tool>
    # <path>/etc/hosts</path>
    # or JSON-like tool invocations
    
    # For now, return None to indicate no tool parsing
    # This would need to be implemented based on Claude's actual format
    return None


def format_tool_result(tool_name: str, result: Any) -> str:
    """Format a tool result for inclusion in conversation."""
    return f"Tool '{tool_name}' returned:\n{json.dumps(result, indent=2)}"