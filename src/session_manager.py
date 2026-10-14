import asyncio
import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field

from src.models import Message, SessionInfo
from src.constants import MAX_SESSIONS, MAX_SESSION_MESSAGES, SESSION_DB_PATH

logger = logging.getLogger(__name__)


class SessionLimitExceeded(ValueError):
    """Raised when the maximum number of concurrent sessions has been reached."""


@dataclass
class Session:
    """Represents a conversation session with message history."""

    session_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + timedelta(hours=1)
    )
    max_messages: Optional[int] = None
    # Native Claude SDK session backing this conversation, and how many of
    # `messages` it already contains. Lets the next turn resume the SDK session
    # and send only the new messages instead of replaying the whole history.
    sdk_session_id: Optional[str] = None
    sdk_synced_count: int = 0

    def touch(self):
        """Update last accessed time and extend expiration."""
        self.last_accessed = datetime.now(timezone.utc)
        self.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    def add_messages(self, messages: List[Message]):
        """Add new messages to the session."""
        self.messages.extend(messages)
        if self.max_messages is not None and len(self.messages) > self.max_messages:
            self.messages = self.messages[-self.max_messages :]
        self.touch()

    def get_all_messages(self) -> List[Message]:
        """Get all messages in the session."""
        return self.messages

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        return datetime.now(timezone.utc) > self.expires_at

    def clear_sdk_session(self):
        """Forget the native SDK session; the next turn replays full history."""
        self.sdk_session_id = None
        self.sdk_synced_count = 0

    def to_session_info(self) -> SessionInfo:
        """Convert to SessionInfo model."""
        return SessionInfo(
            session_id=self.session_id,
            created_at=self.created_at,
            last_accessed=self.last_accessed,
            message_count=len(self.messages),
            expires_at=self.expires_at,
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "messages": [m.model_dump(exclude_none=True) for m in self.messages],
                "created_at": self.created_at.isoformat(),
                "last_accessed": self.last_accessed.isoformat(),
                "expires_at": self.expires_at.isoformat(),
                "max_messages": self.max_messages,
                "sdk_session_id": self.sdk_session_id,
                "sdk_synced_count": self.sdk_synced_count,
            }
        )

    @classmethod
    def from_json(cls, session_id: str, raw: str) -> "Session":
        data = json.loads(raw)
        return cls(
            session_id=session_id,
            messages=[Message(**m) for m in data.get("messages", [])],
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
            max_messages=data.get("max_messages"),
            sdk_session_id=data.get("sdk_session_id"),
            sdk_synced_count=data.get("sdk_synced_count", 0),
        )


@dataclass
class Turn:
    """What a request should send to Claude, as decided by the session manager."""

    all_messages: List[Message]
    session_id: Optional[str]
    # When set, resume this SDK session and send only `new_messages`.
    resume_id: Optional[str] = None
    new_messages: Optional[List[Message]] = None


def _same_history(a: List[Message], b: List[Message]) -> bool:
    """Whether two message lists describe the same conversation.

    Assistant text is compared by role only: streamed replies are filtered
    chunk-by-chunk, so the client's copy can differ slightly from what we stored.
    """
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x.role != y.role:
            return False
        if x.role != "assistant" and x.content != y.content:
            return False
    return True


class SessionDB:
    """SQLite persistence for wrapper sessions and mirrored SDK transcripts."""

    def __init__(self, path: str):
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        with self._lock:
            if path != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    sdk_session_id TEXT,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sdk_transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    subpath TEXT NOT NULL DEFAULT '',
                    uuid TEXT,
                    entry TEXT NOT NULL,
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_sdk_transcripts_key
                    ON sdk_transcripts(session_id, subpath, id);
                CREATE UNIQUE INDEX IF NOT EXISTS idx_sdk_transcripts_uuid
                    ON sdk_transcripts(session_id, subpath, uuid) WHERE uuid IS NOT NULL;
                """
            )

    def execute(self, sql: str, params: Tuple = ()) -> List[Tuple]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def executemany(self, sql: str, rows: List[Tuple]) -> None:
        with self._lock:
            self._conn.execute("BEGIN")
            try:
                self._conn.executemany(sql, rows)
                self._conn.execute("COMMIT")
            except Exception:
                self._conn.execute("ROLLBACK")
                raise

    def save_session(self, session: Session) -> None:
        self.execute(
            "INSERT OR REPLACE INTO sessions (session_id, data, sdk_session_id, expires_at) "
            "VALUES (?, ?, ?, ?)",
            (
                session.session_id,
                session.to_json(),
                session.sdk_session_id,
                session.expires_at.timestamp(),
            ),
        )

    def load_session(self, session_id: str) -> Optional[Session]:
        rows = self.execute("SELECT data FROM sessions WHERE session_id = ?", (session_id,))
        if not rows:
            return None
        try:
            return Session.from_json(session_id, rows[0][0])
        except Exception as e:
            logger.warning(f"Dropping unreadable persisted session {session_id}: {e}")
            self.delete_session(session_id)
            return None

    def load_active_sessions(self) -> List[Session]:
        self.delete_expired_sessions()
        sessions = []
        for (session_id,) in self.execute("SELECT session_id FROM sessions"):
            session = self.load_session(session_id)
            if session:
                sessions.append(session)
        return sessions

    def delete_session(self, session_id: str) -> None:
        self.execute(
            "DELETE FROM sdk_transcripts WHERE session_id IN "
            "(SELECT sdk_session_id FROM sessions WHERE session_id = ?)",
            (session_id,),
        )
        self.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))

    def delete_expired_sessions(self) -> None:
        now = time.time()
        self.execute(
            "DELETE FROM sdk_transcripts WHERE session_id IN "
            "(SELECT sdk_session_id FROM sessions WHERE expires_at < ?)",
            (now,),
        )
        self.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))

    def delete_orphan_transcripts(self, older_than_seconds: float) -> None:
        """Drop transcripts no live session points at (e.g. superseded by a replay)."""
        self.execute(
            "DELETE FROM sdk_transcripts WHERE created_at < ? AND session_id NOT IN "
            "(SELECT sdk_session_id FROM sessions WHERE sdk_session_id IS NOT NULL)",
            (time.time() - older_than_seconds,),
        )


class SQLiteTranscriptStore:
    """Claude Agent SDK `SessionStore` adapter backed by `SessionDB`.

    The SDK mirrors each session transcript here and materializes it again on
    `resume` when the local transcript is missing (e.g. after a restart with a
    fresh temp workspace). Keys ignore `project_key` — it is derived from the
    working directory, which can change between restarts, while SDK session
    IDs are UUIDs and unique on their own.
    """

    def __init__(self, db: SessionDB):
        self.db = db

    async def append(self, key: Dict[str, Any], entries: List[Dict[str, Any]]) -> None:
        now = time.time()
        rows = [
            (key["session_id"], key.get("subpath") or "", e.get("uuid"), json.dumps(e), now)
            for e in entries
        ]
        self.db.executemany(
            "INSERT OR IGNORE INTO sdk_transcripts (session_id, subpath, uuid, entry, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            rows,
        )

    async def load(self, key: Dict[str, Any]) -> Optional[List[Dict[str, Any]]]:
        rows = self.db.execute(
            "SELECT entry FROM sdk_transcripts WHERE session_id = ? AND subpath = ? ORDER BY id",
            (key["session_id"], key.get("subpath") or ""),
        )
        return [json.loads(r[0]) for r in rows] if rows else None

    async def list_subkeys(self, key: Dict[str, Any]) -> List[str]:
        rows = self.db.execute(
            "SELECT DISTINCT subpath FROM sdk_transcripts WHERE session_id = ? AND subpath != ''",
            (key["session_id"],),
        )
        return [r[0] for r in rows]

    async def delete(self, key: Dict[str, Any]) -> None:
        if key.get("subpath"):
            self.db.execute(
                "DELETE FROM sdk_transcripts WHERE session_id = ? AND subpath = ?",
                (key["session_id"], key["subpath"]),
            )
        else:
            self.db.execute(
                "DELETE FROM sdk_transcripts WHERE session_id = ?", (key["session_id"],)
            )


class SessionManager:
    """Manages conversation sessions with automatic cleanup and SQLite persistence."""

    def __init__(
        self,
        default_ttl_hours: int = 1,
        cleanup_interval_minutes: int = 5,
        max_sessions: int = MAX_SESSIONS,
        max_session_messages: int = MAX_SESSION_MESSAGES,
        db_path: str = SESSION_DB_PATH,
    ):
        self.sessions: Dict[str, Session] = {}
        self.lock = asyncio.Lock()
        self.default_ttl_hours = default_ttl_hours
        self.cleanup_interval_minutes = cleanup_interval_minutes
        self.max_sessions = max_sessions
        self.max_session_messages = max_session_messages
        self._cleanup_task = None

        self.db = SessionDB(db_path or ":memory:")
        self.transcript_store = SQLiteTranscriptStore(self.db)
        for session in self.db.load_active_sessions():
            self.sessions[session.session_id] = session
        if self.sessions:
            logger.info(f"Restored {len(self.sessions)} sessions from {self.db.path}")

    def _persist(self, session: Session) -> None:
        try:
            self.db.save_session(session)
        except Exception as e:
            logger.warning(f"Failed to persist session {session.session_id}: {e}")

    def _forget(self, session_id: str) -> None:
        self.sessions.pop(session_id, None)
        try:
            self.db.delete_session(session_id)
        except Exception as e:
            logger.warning(f"Failed to delete persisted session {session_id}: {e}")

    def _lookup(self, session_id: str) -> Optional[Session]:
        """Find a session in the cache, falling back to the database."""
        session = self.sessions.get(session_id)
        if session is None:
            session = self.db.load_session(session_id)
            if session is not None:
                self.sessions[session_id] = session
        return session

    def start_cleanup_task(self):
        """Start the automatic cleanup task - call this after the event loop is running."""
        if self._cleanup_task is not None:
            return  # Already started

        async def cleanup_loop():
            try:
                while True:
                    await asyncio.sleep(self.cleanup_interval_minutes * 60)
                    await self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                logger.info("Session cleanup task cancelled")
                raise

        try:
            loop = asyncio.get_running_loop()
            self._cleanup_task = loop.create_task(cleanup_loop())
            logger.info(
                f"Started session cleanup task (interval: {self.cleanup_interval_minutes} minutes)"
            )
        except RuntimeError:
            logger.warning("No running event loop, automatic session cleanup disabled")

    async def _cleanup_expired_sessions(self):
        """Remove expired sessions."""
        async with self.lock:
            expired_sessions = [
                session_id for session_id, session in self.sessions.items() if session.is_expired()
            ]

            for session_id in expired_sessions:
                self._forget(session_id)
                logger.info(f"Cleaned up expired session: {session_id}")

            try:
                self.db.delete_expired_sessions()
                self.db.delete_orphan_transcripts(self.default_ttl_hours * 3600)
            except Exception as e:
                logger.warning(f"Session database cleanup failed: {e}")

    async def check_session_limit(self, session_id: str) -> None:
        """Check if a new session can be created without actually creating it.

        Raises SessionLimitExceeded if the limit is reached and the session_id
        does not already exist (or is expired). Uses len(self.sessions) to match
        the counting logic in get_or_create_session.
        """
        async with self.lock:
            session = self._lookup(session_id)
            if session and not session.is_expired():
                return  # Existing active session — no slot needed
            # Would need a new slot — check limit (same counting as get_or_create_session)
            if len(self.sessions) >= self.max_sessions:
                raise SessionLimitExceeded(
                    f"Maximum number of sessions ({self.max_sessions}) reached"
                )

    async def get_or_create_session(self, session_id: str) -> Session:
        """Get existing session or create a new one."""
        async with self.lock:
            session = self._lookup(session_id)
            if session is not None:
                if session.is_expired():
                    # Session expired, create new one — check limit first
                    logger.info(f"Session {session_id} expired, creating new session")
                    self._forget(session_id)
                    if len(self.sessions) >= self.max_sessions:
                        raise SessionLimitExceeded(
                            f"Maximum number of sessions ({self.max_sessions}) reached"
                        )
                    session = Session(session_id=session_id, max_messages=self.max_session_messages)
                    self.sessions[session_id] = session
                else:
                    session.touch()
            else:
                if len(self.sessions) >= self.max_sessions:
                    raise SessionLimitExceeded(
                        f"Maximum number of sessions ({self.max_sessions}) reached"
                    )
                session = Session(session_id=session_id, max_messages=self.max_session_messages)
                self.sessions[session_id] = session
                logger.info(f"Created new session: {session_id}")

            self._persist(session)
            return session

    async def get_session(self, session_id: str) -> Optional[Session]:
        """Get existing session without creating new one."""
        async with self.lock:
            session = self._lookup(session_id)
            if session and not session.is_expired():
                session.touch()
                self._persist(session)
                return session
            elif session and session.is_expired():
                # Clean up expired session
                self._forget(session_id)
                logger.info(f"Removed expired session: {session_id}")
            return None

    async def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        async with self.lock:
            if self._lookup(session_id) is not None:
                self._forget(session_id)
                logger.info(f"Deleted session: {session_id}")
                return True
            return False

    async def list_sessions(self) -> List[SessionInfo]:
        """List all active sessions."""
        async with self.lock:
            # Clean up expired sessions first
            expired_sessions = [
                session_id for session_id, session in self.sessions.items() if session.is_expired()
            ]

            for session_id in expired_sessions:
                self._forget(session_id)

            # Return active sessions
            return [session.to_session_info() for session in self.sessions.values()]

    async def prepare_turn(self, messages: List[Message], session_id: Optional[str] = None) -> Turn:
        """
        Decide what to send to Claude for a request.

        Clients send the full history each request. When it extends the
        conversation the session's SDK session already holds, the turn resumes
        that SDK session with only the new messages; otherwise (stateless mode,
        first turn, edited or regenerated history, changed system prompt) the
        full history is replayed into a fresh SDK session.
        """
        if session_id is None:
            # Stateless mode - just return the messages as-is
            return Turn(all_messages=messages, session_id=None)

        session = await self.get_or_create_session(session_id)

        async with self.lock:
            resume_id = None
            new_messages = None
            synced = session.sdk_synced_count
            if (
                session.sdk_session_id
                and synced
                and len(messages) > synced
                and _same_history(messages[:synced], session.messages[:synced])
            ):
                tail = list(messages[synced:])
                if any(m.role == "user" for m in tail) and all(m.role != "system" for m in tail):
                    resume_id = session.sdk_session_id
                    new_messages = tail

            if resume_id is None:
                session.clear_sdk_session()

            # Replace session messages with client-provided history
            session.messages = list(messages)
            session.touch()
            self._persist(session)

        logger.info(
            f"Session {session_id}: {len(messages)} messages, "
            + (
                f"resuming SDK session {resume_id} with {len(new_messages)} new"
                if resume_id
                else "replaying full history"
            )
        )

        return Turn(
            all_messages=session.get_all_messages(),
            session_id=session_id,
            resume_id=resume_id,
            new_messages=new_messages,
        )

    async def process_messages(
        self, messages: List[Message], session_id: Optional[str] = None
    ) -> Tuple[List[Message], Optional[str]]:
        """
        Process messages for a request, handling both stateless and session modes.

        Returns:
            Tuple of (all_messages_for_claude, actual_session_id_used)
        """
        turn = await self.prepare_turn(messages, session_id)
        return turn.all_messages, turn.session_id

    async def add_assistant_response(
        self,
        session_id: Optional[str],
        assistant_message: Message,
        sdk_session_id: Optional[str] = None,
    ):
        """Add assistant response to session if session mode is active.

        `sdk_session_id` is the native SDK session that produced the response;
        recording it lets the next turn resume instead of replaying.
        """
        if session_id is None:
            return

        session = await self.get_session(session_id)
        if session:
            async with self.lock:
                session.add_messages([assistant_message])
                if sdk_session_id:
                    session.sdk_session_id = sdk_session_id
                    session.sdk_synced_count = len(session.messages)
                else:
                    session.clear_sdk_session()
                self._persist(session)
            logger.info(f"Added assistant response to session {session_id}")

    async def get_stats(self) -> Dict[str, int]:
        """Get session manager statistics."""
        async with self.lock:
            active_sessions = sum(1 for s in self.sessions.values() if not s.is_expired())
            expired_sessions = sum(1 for s in self.sessions.values() if s.is_expired())
            total_messages = sum(len(s.messages) for s in self.sessions.values())

            return {
                "active_sessions": active_sessions,
                "expired_sessions": expired_sessions,
                "total_messages": total_messages,
            }

    async def shutdown(self):
        """Shutdown the session manager and cleanup tasks.

        Persisted sessions stay in the database and are reloaded on demand.
        """
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None

        async with self.lock:
            self.sessions.clear()
            logger.info("Session manager shutdown complete")


# Global session manager instance
session_manager = SessionManager()
