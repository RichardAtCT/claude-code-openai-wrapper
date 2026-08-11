"""Unit tests for the typed SDK message parser (_message_to_dict)."""

from claude_agent_sdk import AssistantMessage, ResultMessage, SystemMessage, TextBlock

from src.claude_cli import _message_to_dict


def test_assistant_message_keeps_textblock_content():
    msg = AssistantMessage(content=[TextBlock(text="hello world")], model="glm-5.2")
    d = _message_to_dict(msg)
    assert d["type"] == "assistant"
    assert isinstance(d["content"], list)
    assert d["content"][0].text == "hello world"


def test_result_message_fields_preserved():
    msg = ResultMessage(
        subtype="success",
        duration_ms=100,
        duration_api_ms=80,
        is_error=False,
        num_turns=2,
        session_id="sess-1",
        result="done",
        total_cost_usd=0.01,
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    d = _message_to_dict(msg)
    assert d["type"] == "result"
    assert d["subtype"] == "success"
    assert d["result"] == "done"
    assert d["session_id"] == "sess-1"
    assert d["total_cost_usd"] == 0.01
    assert d["num_turns"] == 2
    assert d["is_error"] is False
    assert d["stop_reason"] == "end_turn"


def test_system_message_init_data_preserved():
    msg = SystemMessage(
        subtype="init",
        data={"session_id": "sess-1", "model": "glm-5.2"},
    )
    d = _message_to_dict(msg)
    assert d["type"] == "system"
    assert d["subtype"] == "init"
    assert d["data"]["session_id"] == "sess-1"
    assert d["data"]["model"] == "glm-5.2"


def test_dict_passthrough_unchanged():
    original = {
        "type": "result",
        "subtype": "error_during_execution",
        "is_error": True,
        "error_message": "boom",
    }
    assert _message_to_dict(original) is original


def test_unknown_object_falls_back_to_attr_copy():
    class Unknown:
        type = "weird"
        foo = "bar"

    d = _message_to_dict(Unknown())
    assert d.get("foo") == "bar"
