"""Unit tests for GLM-5.2 passthrough: advertisement + routing."""

from src.constants import GLM_MODELS, PASSTHROUGH_MODELS
from src.main import _append_passthrough, get_cli_for_model, claude_cli, gemini_cli


def test_glm_model_listed():
    assert "glm-5.2" in GLM_MODELS
    assert "glm-5.2[1m]" in GLM_MODELS
    assert "glm-5.2" in PASSTHROUGH_MODELS
    assert "glm-5.2[1m]" in PASSTHROUGH_MODELS


def test_append_passthrough_adds_glm():
    result = _append_passthrough([{"id": "claude-sonnet-4-6", "object": "model"}])
    ids = [m["id"] for m in result]
    assert "glm-5.2" in ids
    assert "claude-sonnet-4-6" in ids


def test_append_passthrough_dedupes():
    models = [{"id": "glm-5.2", "object": "model"}]
    result = _append_passthrough(models)
    assert sum(1 for m in result if m["id"] == "glm-5.2") == 1


def test_glm_routes_to_claude_cli():
    assert get_cli_for_model("glm-5.2") is claude_cli
    assert get_cli_for_model("glm-5.2") is not gemini_cli
