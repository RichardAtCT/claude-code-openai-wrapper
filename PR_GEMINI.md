# Gemini CLI Proxy Support and Interactive Chat Client

This PR introduces support for the Gemini CLI as an alternative backend, allowing users to use Gemini models (like Gemini 3 and 2.5) through the OpenAI-compatible proxy. It also includes a new interactive chat client with Markdown rendering.

## New Features
* **Gemini CLI Proxy:**
  * New `GeminiCodeCLI` wrapper for the `@google/gemini-cli` tool.
  * Real-time NDJSON stream parsing for low-latency responses.
  * Full session continuity support using the CLI's `--resume` flag.
  * Integrated model routing: models starting with `gemini-` or using aliases like `pro`, `flash`, `auto` are automatically routed to Gemini.
* **Interactive Chat Client:**
  * Added `examples/interactive_chat.py` which manages the background server, provides a rich TUI with `rich` for Markdown rendering, and supports live streaming.
* **Unified Model Listing:**
  * Updated `/v1/models` to return both Claude and Gemini models with correct metadata.

## Enhancements
* **Authentication:** Added support for `GEMINI_API_KEY` and `GOOGLE_API_KEY` in the `ClaudeCodeAuthManager`.
* **Constants:** Defined the latest Gemini model IDs and aliases.
* **Configuration:** Updated `.env.example` with Gemini-specific settings.

## Bug Fixes & Refactoring
* **Unified Interface:** Refactored `main.py` endpoints to use a common `get_cli_for_model` helper, making it easier to add more backends in the future.
* **Metadata Extraction:** Improved metadata and usage parsing to handle both Anthropic and Gemini formats consistently.

## Testing
* Added `tests/test_gemini_cli_unit.py` with 100% coverage for the new wrapper.
* Verified both streaming and non-streaming responses for both backends.
