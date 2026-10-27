"""Message content parts from agentic clients (tool_use, tool_result, images) must not 422."""

from src.models import ContentPart, Message


def test_text_part_still_normalizes():
    msg = Message(role="user", content=[{"type": "text", "text": "hello"}])
    assert msg.content == "hello"


def test_non_text_parts_are_accepted_and_skipped():
    msg = Message(
        role="assistant",
        content=[
            {"type": "text", "text": "calling"},
            {"type": "tool_use", "id": "t1", "name": "read", "input": {"path": "x"}},
            {"type": "image", "source": {"type": "base64", "data": "AAA"}},
        ],
    )
    assert msg.content == "calling"


def test_tool_result_text_is_kept():
    msg = Message(
        role="user",
        content=[
            {
                "type": "tool_result",
                "tool_use_id": "t1",
                "content": [{"type": "text", "text": "file body"}],
            },
            {"type": "tool_result", "tool_use_id": "t2", "content": "plain"},
        ],
    )
    assert msg.content == "file body\nplain"


def test_null_content_and_unknown_fields_are_tolerated():
    msg = Message(role="assistant", content=None, store=True)
    assert msg.content is None
    part = ContentPart(type="input_image", image_url="data:x")
    assert part.text is None
