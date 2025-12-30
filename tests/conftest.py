"""
Pytest configuration and fixtures for claude-code-openai-wrapper tests.
"""

import pytest
import requests


# Check if server is running for integration tests
def is_server_running(base_url: str = "http://localhost:8000") -> bool:
    """Check if the test server is running."""
    try:
        response = requests.get(f"{base_url}/health", timeout=2)
        return response.status_code == 200
    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return False


# Marker for tests that require a running server
requires_server = pytest.mark.skipif(
    not is_server_running(),
    reason="Server not running at localhost:8000. Start with: poetry run python main.py",
)
