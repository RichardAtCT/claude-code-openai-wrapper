#!/usr/bin/env python3
"""
Example of using OpenAI-compatible function calling with Claude Code tools.
"""

import json
import os
from openai import OpenAI

# Configure the client
client = OpenAI(
    base_url="http://localhost:8000/v1",
    api_key=os.getenv("TEST_API_KEY", "not-needed")
)

def list_available_tools():
    """List all available tools/functions."""
    print("Available Tools:")
    print("=" * 50)
    
    # This would work with the /v1/tools endpoint
    # For now, we'll show the tool definitions
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List contents of a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path to list",
                            "default": "."
                        }
                    },
                    "required": []
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Execute a bash command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "Bash command to execute"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    ]
    
    for tool in tools:
        func = tool["function"]
        print(f"\n- {func['name']}: {func['description']}")
        print(f"  Parameters: {json.dumps(func['parameters'], indent=4)}")
    
    return tools


def example_with_tools():
    """Example using function calling with Claude."""
    print("\n\nFunction Calling Example:")
    print("=" * 50)
    
    # Define available tools
    tools = [
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List contents of a directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Directory path to list",
                            "default": "."
                        }
                    },
                    "required": []
                }
            }
        }
    ]
    
    # Make a request that should trigger tool use
    messages = [
        {
            "role": "user",
            "content": "What files are in the current directory?"
        }
    ]
    
    print(f"\nUser: {messages[0]['content']}")
    
    # Call with tools
    response = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=messages,
        tools=tools,
        tool_choice="auto"  # Let Claude decide when to use tools
    )
    
    # Check if Claude wants to use a tool
    message = response.choices[0].message
    
    if message.tool_calls:
        print(f"\nAssistant wants to call tools:")
        for tool_call in message.tool_calls:
            print(f"  - {tool_call.function.name}({tool_call.function.arguments})")
            
        # In a real application, you would:
        # 1. Execute the tool calls
        # 2. Add the results as tool messages
        # 3. Call the API again with the results
        
        # Example of continuing the conversation with tool results
        messages.append(message)
        messages.append({
            "role": "tool",
            "tool_call_id": message.tool_calls[0].id,
            "content": json.dumps({
                "files": ["main.py", "README.md", "pyproject.toml", "examples/", "tests/"]
            })
        })
        
        # Get final response
        final_response = client.chat.completions.create(
            model="claude-3-5-sonnet-20241022",
            messages=messages
        )
        
        print(f"\nAssistant (after tool execution): {final_response.choices[0].message.content}")
    else:
        print(f"\nAssistant: {message.content}")


def example_with_enable_tools():
    """Example using the enable_tools flag (Claude-specific)."""
    print("\n\nEnable Tools Example (Claude-specific):")
    print("=" * 50)
    
    messages = [
        {
            "role": "user",
            "content": "List the files in the current directory and tell me what each one does."
        }
    ]
    
    print(f"\nUser: {messages[0]['content']}")
    
    # Use enable_tools to let Claude use its native tools
    response = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=messages,
        extra_body={"enable_tools": True}
    )
    
    print(f"\nAssistant: {response.choices[0].message.content}")


def example_with_specific_tool():
    """Example forcing use of a specific tool."""
    print("\n\nSpecific Tool Example:")
    print("=" * 50)
    
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the file to read"
                        }
                    },
                    "required": ["path"]
                }
            }
        }
    ]
    
    messages = [
        {
            "role": "user",
            "content": "Read the README.md file"
        }
    ]
    
    print(f"\nUser: {messages[0]['content']}")
    
    # Force Claude to use a specific tool
    response = client.chat.completions.create(
        model="claude-3-5-sonnet-20241022",
        messages=messages,
        tools=tools,
        tool_choice={
            "type": "function",
            "function": {"name": "read_file"}
        }
    )
    
    message = response.choices[0].message
    if message.tool_calls:
        print(f"\nAssistant called: {message.tool_calls[0].function.name}")
        print(f"With arguments: {message.tool_calls[0].function.arguments}")


if __name__ == "__main__":
    # List available tools
    list_available_tools()
    
    # Run examples
    try:
        example_with_tools()
    except Exception as e:
        print(f"\nError in tools example: {e}")
    
    try:
        example_with_enable_tools()
    except Exception as e:
        print(f"\nError in enable_tools example: {e}")
    
    try:
        example_with_specific_tool()
    except Exception as e:
        print(f"\nError in specific tool example: {e}")