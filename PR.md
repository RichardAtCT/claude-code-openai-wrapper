# Release v2.3.0: Concurrency improvements, SDK options wiring, and critical bug fixes

This PR introduces version 2.3.0, focusing on significant reliability improvements, full support for concurrent SDK calls, wiring of new Claude API options, and resolutions for several critical proxy bugs.

## Features & Enhancements
* **SDK Options Wiring:** Full support for `reasoning_effort`, `response_format`, `thinking`, `max_budget_usd`, and `user` fields passed directly to the Claude SDK.
* **Concurrency:** Removed `os.environ` mutex (`_env_lock`) by passing auth via `options.env`, allowing fully concurrent SDK calls. `SessionManager` has been refactored to use `asyncio.Lock` with all session methods converted to async.
* **Token & Reason Mapping:** Extracts real token counts directly from the SDK's `ResultMessage` and properly maps `stop_reason` to `finish_reason` (e.g., `max_tokens` → `length`).
* **Tool Handling:** Changed `AnthropicMessagesRequest.enable_tools` default to `False` so simple message requests do not trigger unintended 10-turn loops. 

## Bug Fixes
* **Session Continuity:** Fixed session continuation by correcting `continue_session` to `continue_conversation` and replaced list appending with replacement to prevent exponential duplication.
* **Timeouts & Hangs:** Wrapped async `query()` iterations with `asyncio.timeout` to prevent indefinite hangs when the SDK subprocess stalls.
* **Proxy Reliability:** 
  * Removed `filter_content()` from user input which was silently stripping XML-like tags.
  * Secured `/v1/auth/status` endpoint with the `verify_api_key()` auth guard.
  * Marked the Bash tool as `is_safe=False`.
  * Replaced bare `except:` clauses with `except Exception:`.

## Maintenance & Chores
* Updated `poetry.lock` and the test suite for compatibility with `pydantic 2.13` and `poetry 2.3`.
* Replaced deprecated `datetime.utcnow()` with `datetime.now(timezone.utc)`.
* Ignored `.worktrees` directories in `.gitignore`.
* Added diagnostic print statements for `/v1/messages` and improved the `test_message.py` script.
