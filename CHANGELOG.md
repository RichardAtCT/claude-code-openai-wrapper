# Changelog

All notable changes to this project will be documented in this file.

## [1.1.0] - 2025-07-06

### 🎉 Major Features

- **OpenAI Function Calling Support** - Full implementation of OpenAI's function calling format
  - Complete compatibility with OpenAI's `tools` and `tool_choice` parameters
  - Support for legacy `functions` and `function_call` format
  - All 9 Claude tools available through OpenAI-compatible interface
  - Tool response handling with proper `tool_calls` format
  - GET /v1/tools endpoint to list available tools

### 🔧 Technical Improvements

- Added comprehensive tool mapping system (OpenAI names → Claude tools)
- Implemented tool execution handler with proper error handling
- Enhanced Swagger/OpenAPI documentation with tool schemas
- Added production-ready test suite for tool functionality
- Improved message handling for tool responses

### 📚 Documentation

- Updated README with complete function calling examples
- Added tool usage documentation with all three supported formats
- Created comprehensive examples in `examples/tools_example.py`
- Enhanced API documentation with tool-related endpoints

### 🧪 Testing

- Created extensive test suite for tool functionality
- Added actual execution demonstrations
- Implemented production readiness checks
- Verified all tool mappings and structures

## [1.0.0] - Previous Release

- Initial release with core OpenAI compatibility
- Session management and continuity
- Multi-provider authentication support
- Streaming and non-streaming responses