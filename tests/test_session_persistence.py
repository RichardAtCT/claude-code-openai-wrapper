#!/usr/bin/env python3
"""
Unit tests for SQLite session persistence and native SDK session resume.
"""

import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from src.main import build_turn_prompt
from src.models import Message
from src.session_manager import SessionManager


def user(text):
    return Message(role="user", content=text)


def assistant(text):
    return Message(role="assistant", content=text)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "sessions.db")


class TestPersistence:
    @pytest.mark.asyncio
    async def test_sessions_survive_restart(self, db_path):
        manager = SessionManager(db_path=db_path)
        await manager.prepare_turn([user("Hi")], "s1")
        await manager.add_assistant_response("s1", assistant("Hello"), sdk_session_id="sdk-1")

        restarted = SessionManager(db_path=db_path)
        session = await restarted.get_session("s1")
        assert session is not None
        assert [m.content for m in session.messages] == ["Hi", "Hello"]
        assert session.sdk_session_id == "sdk-1"
        assert session.sdk_synced_count == 2

    @pytest.mark.asyncio
    async def test_deleted_session_stays_deleted(self, db_path):
        manager = SessionManager(db_path=db_path)
        await manager.get_or_create_session("s1")
        assert await manager.delete_session("s1") is True

        assert await SessionManager(db_path=db_path).get_session("s1") is None

    @pytest.mark.asyncio
    async def test_expired_sessions_not_restored(self, db_path):
        manager = SessionManager(db_path=db_path)
        session = await manager.get_or_create_session("old")
        session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        manager._persist(session)

        restarted = SessionManager(db_path=db_path)
        assert "old" not in restarted.sessions
        assert await restarted.get_session("old") is None

    @pytest.mark.asyncio
    async def test_reloads_from_db_after_shutdown(self, db_path):
        manager = SessionManager(db_path=db_path)
        await manager.get_or_create_session("s1")
        await manager.shutdown()

        assert await manager.get_session("s1") is not None


class TestTranscriptStore:
    @pytest.mark.asyncio
    async def test_roundtrip_ignores_project_key(self, db_path):
        store = SessionManager(db_path=db_path).transcript_store
        entries = [{"type": "user", "uuid": "u1", "n": 1}, {"type": "assistant", "uuid": "a1"}]
        await store.append({"project_key": "/tmp/a", "session_id": "sdk-1"}, entries)
        # Duplicate uuids are ignored
        await store.append({"project_key": "/tmp/a", "session_id": "sdk-1"}, entries[:1])

        loaded = await store.load({"project_key": "/tmp/other", "session_id": "sdk-1"})
        assert loaded == entries
        assert await store.load({"project_key": "/tmp/a", "session_id": "missing"}) is None

    @pytest.mark.asyncio
    async def test_subkeys_and_delete(self, db_path):
        store = SessionManager(db_path=db_path).transcript_store
        await store.append({"project_key": "p", "session_id": "s"}, [{"type": "user"}])
        await store.append(
            {"project_key": "p", "session_id": "s", "subpath": "subagents/agent-1"},
            [{"type": "user"}],
        )
        assert await store.list_subkeys({"project_key": "p", "session_id": "s"}) == [
            "subagents/agent-1"
        ]

        await store.delete({"project_key": "p", "session_id": "s"})
        assert await store.load({"project_key": "p", "session_id": "s"}) is None
        assert await store.list_subkeys({"project_key": "p", "session_id": "s"}) == []

    @pytest.mark.asyncio
    async def test_deleting_session_drops_its_transcript(self, db_path):
        manager = SessionManager(db_path=db_path)
        await manager.prepare_turn([user("Hi")], "s1")
        await manager.add_assistant_response("s1", assistant("Hello"), sdk_session_id="sdk-1")
        await manager.transcript_store.append(
            {"project_key": "p", "session_id": "sdk-1"}, [{"type": "user"}]
        )

        await manager.delete_session("s1")
        assert (
            await manager.transcript_store.load({"project_key": "p", "session_id": "sdk-1"}) is None
        )


class TestResumePlanning:
    @pytest.fixture
    def manager(self, db_path):
        return SessionManager(db_path=db_path)

    async def _first_turn(self, manager):
        turn = await manager.prepare_turn([user("Hi")], "s1")
        assert turn.resume_id is None
        await manager.add_assistant_response("s1", assistant("Hello"), sdk_session_id="sdk-1")

    @pytest.mark.asyncio
    async def test_stateless_never_resumes(self, manager):
        turn = await manager.prepare_turn([user("Hi")], None)
        assert turn.session_id is None and turn.resume_id is None

    @pytest.mark.asyncio
    async def test_continuation_resumes_with_new_messages_only(self, manager):
        await self._first_turn(manager)

        turn = await manager.prepare_turn([user("Hi"), assistant("Hello"), user("More")], "s1")
        assert turn.resume_id == "sdk-1"
        assert [m.content for m in turn.new_messages] == ["More"]
        assert len(turn.all_messages) == 3

    @pytest.mark.asyncio
    async def test_assistant_text_drift_still_resumes(self, manager):
        await self._first_turn(manager)

        turn = await manager.prepare_turn([user("Hi"), assistant("Hello!"), user("More")], "s1")
        assert turn.resume_id == "sdk-1"

    @pytest.mark.asyncio
    async def test_edited_history_replays(self, manager):
        await self._first_turn(manager)

        turn = await manager.prepare_turn([user("Hey"), assistant("Hello"), user("More")], "s1")
        assert turn.resume_id is None
        session = await manager.get_session("s1")
        assert session.sdk_session_id is None

    @pytest.mark.asyncio
    async def test_regenerate_replays(self, manager):
        await self._first_turn(manager)

        turn = await manager.prepare_turn([user("Hi")], "s1")
        assert turn.resume_id is None

    @pytest.mark.asyncio
    async def test_new_system_message_replays(self, manager):
        await self._first_turn(manager)

        turn = await manager.prepare_turn(
            [user("Hi"), assistant("Hello"), Message(role="system", content="Be terse"), user("x")],
            "s1",
        )
        assert turn.resume_id is None

    @pytest.mark.asyncio
    async def test_response_without_sdk_id_disables_resume(self, manager):
        await self._first_turn(manager)
        await manager.prepare_turn([user("Hi"), assistant("Hello"), user("More")], "s1")
        await manager.add_assistant_response("s1", assistant("Ok"))

        turn = await manager.prepare_turn(
            [user("Hi"), assistant("Hello"), user("More"), assistant("Ok"), user("Again")], "s1"
        )
        assert turn.resume_id is None

    @pytest.mark.asyncio
    async def test_resume_survives_restart(self, db_path, manager):
        await self._first_turn(manager)

        restarted = SessionManager(db_path=db_path)
        turn = await restarted.prepare_turn([user("Hi"), assistant("Hello"), user("More")], "s1")
        assert turn.resume_id == "sdk-1"

    @pytest.mark.asyncio
    async def test_build_turn_prompt(self, manager):
        await self._first_turn(manager)
        system = Message(role="system", content="Be nice")
        await manager.prepare_turn([system, user("Hi")], "s2")
        await manager.add_assistant_response("s2", assistant("Hello"), sdk_session_id="sdk-2")

        turn = await manager.prepare_turn(
            [system, user("Hi"), assistant("Hello"), user("More")], "s2"
        )
        prompt, system_prompt, fallback = build_turn_prompt(turn, None)
        assert prompt == "Human: More"
        assert system_prompt == "Be nice"
        assert fallback == "Human: Hi\n\nAssistant: Hello\n\nHuman: More"


class TestRunCompletionResumeFallback:
    @pytest.fixture
    def cli(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            from src.claude_cli import ClaudeCodeCLI

            yield ClaudeCodeCLI(cwd=temp_dir)

    @pytest.mark.asyncio
    async def test_resume_passes_session_and_store(self, cli):
        calls = []
        store = object()

        async def mock_query(prompt, options):
            calls.append((prompt, options.resume, options.session_store))
            yield {"subtype": "init", "data": {"session_id": "sdk-1"}}
            yield {"type": "assistant", "content": [{"type": "text", "text": "ok"}]}

        with patch("src.claude_cli.query", mock_query):
            chunks = [
                c
                async for c in cli.run_completion(
                    "new", session_id="sdk-1", fallback_prompt="full", session_store=store
                )
            ]

        assert calls == [("new", "sdk-1", store)]
        assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_failed_resume_replays_full_history(self, cli):
        calls = []

        async def mock_query(prompt, options):
            calls.append((prompt, options.resume))
            if options.resume:
                yield {"subtype": "init", "data": {"session_id": "sdk-1"}}
                raise RuntimeError("No conversation found with session ID: sdk-1")
            yield {"type": "assistant", "content": [{"type": "text", "text": "fresh"}]}

        with patch("src.claude_cli.query", mock_query):
            chunks = [
                c
                async for c in cli.run_completion("new", session_id="sdk-1", fallback_prompt="full")
            ]

        assert calls == [("new", "sdk-1"), ("full", None)]
        assert chunks == [{"type": "assistant", "content": [{"type": "text", "text": "fresh"}]}]
