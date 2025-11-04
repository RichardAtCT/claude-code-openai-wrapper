import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from threading import Lock

from src.models import Message, SessionInfo

logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Represents a conversation session with message history."""

    session_id: str
    messages: List[Message] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    expires_at: datetime = field(default_factory=lambda: datetime.utcnow() + timedelta(hours=1))

    def touch(self):
        """Update last accessed time and extend expiration."""
        self.last_accessed = datetime.utcnow()
        self.expires_at = datetime.utcnow() + timedelta(hours=1)

    def add_messages(self, messages: List[Message]):
        """Add new messages to the session."""
        self.messages.extend(messages)
        self.touch()

    def get_all_messages(self) -> List[Message]:
        """Get all messages in the session."""
        return self.messages

    def is_expired(self) -> bool:
        """Check if the session has expired."""
        return datetime.utcnow() > self.expires_at

    def to_session_info(self) -> SessionInfo:
        """Convert to SessionInfo model."""
        return SessionInfo(
            session_id=self.session_id,
            created_at=self.created_at,
            last_accessed=self.last_accessed,
            message_count=len(self.messages),
            expires_at=self.expires_at,
        )


class SessionManager:
    """Manages conversation sessions with automatic cleanup."""

    def __init__(self, default_ttl_hours: int = 1, cleanup_interval_minutes: int = 5):
        self.sessions: Dict[str, Session] = {}
        self.lock = Lock()
        self.default_ttl_hours = default_ttl_hours
        self.cleanup_interval_minutes = cleanup_interval_minutes
        self._cleanup_task = None

    def start_cleanup_task(self):
        """Start the automatic cleanup task - call this after the event loop is running."""
        if self._cleanup_task is not None:
            return  # Already started

        async def cleanup_loop():
            try:
                while True:
                    await asyncio.sleep(self.cleanup_interval_minutes * 60)
                    self._cleanup_expired_sessions()
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

    def _cleanup_expired_sessions(self):
        """Remove expired sessions."""
        with self.lock:
            expired_sessions = [
                session_id for session_id, session in self.sessions.items() if session.is_expired()
            ]

            for session_id in expired_sessions:
                del self.sessions[session_id]
                logger.info(f"Cleaned up expired session: {session_id}")

    def get_or_create_session(self, session_id: str) -> Session:
        """Get existing session or create a new one."""
        with self.lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                if session.is_expired():
                    # Session expired, create new one
                    logger.info(f"Session {session_id} expired, creating new session")
                    del self.sessions[session_id]
                    session = Session(session_id=session_id)
                    self.sessions[session_id] = session
                else:
                    session.touch()
            else:
                session = Session(session_id=session_id)
                self.sessions[session_id] = session
                logger.info(f"Created new session: {session_id}")

            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get existing session without creating new one."""
        with self.lock:
            session = self.sessions.get(session_id)
            if session and not session.is_expired():
                session.touch()
                return session
            elif session and session.is_expired():
                # Clean up expired session
                del self.sessions[session_id]
                logger.info(f"Removed expired session: {session_id}")
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Deleted session: {session_id}")
                return True
            return False

    def list_sessions(self) -> List[SessionInfo]:
        """List all active sessions."""
        with self.lock:
            # Clean up expired sessions first
            expired_sessions = [
                session_id for session_id, session in self.sessions.items() if session.is_expired()
            ]

            for session_id in expired_sessions:
                del self.sessions[session_id]

            # Return active sessions
            return [session.to_session_info() for session in self.sessions.values()]

    def process_messages(
        self, messages: List[Message], session_id: Optional[str] = None
    ) -> Tuple[List[Message], Optional[str]]:
        """
        Process messages for a request, handling both stateless and session modes.

        Returns:
            Tuple of (all_messages_for_claude, actual_session_id_used)
        """
        if session_id is None:
            # Stateless mode - just return the messages as-is
            return messages, None

        # Session mode - get or create session and merge messages
        session = self.get_or_create_session(session_id)

        # Add new messages to session
        session.add_messages(messages)

        # Return all messages in the session for Claude
        all_messages = session.get_all_messages()

        logger.info(
            f"Session {session_id}: processing {len(messages)} new messages, {len(all_messages)} total"
        )

        return all_messages, session_id

    def add_assistant_response(self, session_id: Optional[str], assistant_message: Message):
        """Add assistant response to session if session mode is active."""
        if session_id is None:
            return

        session = self.get_session(session_id)
        if session:
            session.add_messages([assistant_message])
            logger.info(f"Added assistant response to session {session_id}")

    def get_stats(self) -> Dict[str, int]:
        """Get session manager statistics."""
        with self.lock:
            active_sessions = sum(1 for s in self.sessions.values() if not s.is_expired())
            expired_sessions = sum(1 for s in self.sessions.values() if s.is_expired())
            total_messages = sum(len(s.messages) for s in self.sessions.values())

            return {
                "active_sessions": active_sessions,
                "expired_sessions": expired_sessions,
                "total_messages": total_messages,
            }

    def shutdown(self):
        """Shutdown the session manager and cleanup tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()

        with self.lock:
            self.sessions.clear()
            logger.info("Session manager shutdown complete")


# Global session manager instance
session_manager = SessionManager()
