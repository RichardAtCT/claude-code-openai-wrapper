"""Unit tests for dynamic Anthropic model listing."""

import pytest

from src import main


@pytest.mark.asyncio
async def test_get_available_models_uses_anthropic_models_api(monkeypatch):
    main._model_list_cache = {"expires_at": 0.0, "models": None}

    async def fake_fetch():
        return [
            {
                "id": "claude-test-latest",
                "object": "model",
                "owned_by": "anthropic",
                "display_name": "Claude Test Latest",
            }
        ]

    monkeypatch.delenv("CLAUDE_MODELS_OVERRIDE", raising=False)
    monkeypatch.setattr(main, "_fetch_anthropic_models", fake_fetch)

    models = await main.get_available_models()

    assert models[0]["id"] == "claude-test-latest"
    assert models[0]["display_name"] == "Claude Test Latest"


@pytest.mark.asyncio
async def test_get_available_models_falls_back_to_constants(monkeypatch):
    main._model_list_cache = {"expires_at": 0.0, "models": None}

    async def fake_fetch():
        return None

    monkeypatch.delenv("CLAUDE_MODELS_OVERRIDE", raising=False)
    monkeypatch.setattr(main, "_fetch_anthropic_models", fake_fetch)

    models = await main.get_available_models()

    assert {model["id"] for model in models} >= {"claude-sonnet-4-6", "claude-opus-4-6"}


@pytest.mark.asyncio
async def test_model_override_skips_live_fetch(monkeypatch):
    main._model_list_cache = {"expires_at": 0.0, "models": None}

    async def fake_fetch():
        raise AssertionError("override should not call live Anthropic API")

    monkeypatch.setenv("CLAUDE_MODELS_OVERRIDE", "custom-a,custom-b")
    monkeypatch.setattr(main, "CLAUDE_MODELS", ["custom-a", "custom-b"])
    monkeypatch.setattr(main, "_fetch_anthropic_models", fake_fetch)

    models = await main.get_available_models()

    assert [model["id"] for model in models] == ["custom-a", "custom-b"]


def test_openai_model_from_anthropic_preserves_metadata():
    model = main._openai_model_from_anthropic(
        {
            "id": "claude-test",
            "type": "model",
            "display_name": "Claude Test",
            "created_at": "2026-01-01T00:00:00Z",
            "max_input_tokens": 200000,
            "max_tokens": 64000,
            "capabilities": {"batch": {"supported": True}},
        }
    )

    assert model["id"] == "claude-test"
    assert model["object"] == "model"
    assert model["owned_by"] == "anthropic"
    assert model["capabilities"] == {"batch": {"supported": True}}
