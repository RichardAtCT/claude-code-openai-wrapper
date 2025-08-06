"""
Sandbox session tracker for time-based cleanup.

This module tracks sandbox sessions created in chat mode and manages
delayed cleanup based on configured time intervals. Only sessions from
sandboxed environments are tracked and cleaned up.
"""

import os
import json
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import logging
import fcntl
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class SandboxSessionTracker:
    """Track sandbox sessions for delayed cleanup."""
    
    def __init__(self, tracker_file: str = None):
        """Initialize the tracker with optional custom file path."""
        if tracker_file is None:
            # Default location in user's home directory
            config_dir = Path.home() / ".claude-wrapper"
            config_dir.mkdir(exist_ok=True)
            self.tracker_file = config_dir / "sandbox_session_tracker.json"
        else:
            self.tracker_file = Path(tracker_file)
        
        # Ensure the tracker file exists
        if not self.tracker_file.exists():
            self._write_sessions({})
            logger.info(f"Created new session tracker file: {self.tracker_file}")
    
    @contextmanager
    def _file_lock(self, file_handle):
        """Context manager for file locking to ensure thread safety."""
        try:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)
            yield
        finally:
            fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)
    
    def _read_sessions(self) -> Dict[str, Dict]:
        """Read sessions from tracker file with file locking."""
        try:
            with open(self.tracker_file, 'r') as f:
                with self._file_lock(f):
                    return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            logger.warning(f"Could not read tracker file, returning empty dict")
            return {}
        except Exception as e:
            logger.error(f"Error reading tracker file: {e}")
            return {}
    
    def _write_sessions(self, sessions: Dict[str, Dict]) -> bool:
        """Write sessions to tracker file with file locking."""
        try:
            # Write to temp file first for atomicity
            temp_file = self.tracker_file.with_suffix('.tmp')
            with open(temp_file, 'w') as f:
                with self._file_lock(f):
                    json.dump(sessions, f, indent=2)
            
            # Atomic move
            temp_file.replace(self.tracker_file)
            return True
        except Exception as e:
            logger.error(f"Error writing tracker file: {e}")
            return False
    
    def track_sandbox_session(self, session_id: str, sandbox_dir: str) -> bool:
        """Track a new sandbox session for delayed cleanup.
        
        Args:
            session_id: The Claude session ID
            sandbox_dir: The sandbox directory path
            
        Returns:
            True if tracking was successful
        """
        # Safety check: only track sessions with sandbox marker in path
        if "claude_chat_sandbox" not in sandbox_dir:
            logger.warning(f"Refusing to track non-sandbox session: {sandbox_dir}")
            return False
        
        sessions = self._read_sessions()
        
        # Add new session with current timestamp
        sessions[session_id] = {
            "sandbox_dir": sandbox_dir,
            "created_at": time.time(),
            "is_sandbox": True  # Explicit marker for safety
        }
        
        success = self._write_sessions(sessions)
        if success:
            logger.info(f"Tracked sandbox session {session_id} for delayed cleanup")
        
        return success
    
    def get_expired_sandbox_sessions(self, delay_minutes: int) -> Dict[str, Dict]:
        """Get sandbox sessions that have expired based on delay.
        
        Args:
            delay_minutes: Minutes to wait before considering a session expired
            
        Returns:
            Dictionary of expired sessions {session_id: session_info}
        """
        sessions = self._read_sessions()
        current_time = time.time()
        delay_seconds = delay_minutes * 60
        
        expired = {}
        for session_id, info in sessions.items():
            # Double safety check
            if not info.get("is_sandbox", False):
                logger.warning(f"Skipping non-sandbox session {session_id}")
                continue
            
            if "claude_chat_sandbox" not in info.get("sandbox_dir", ""):
                logger.warning(f"Skipping session without sandbox marker: {session_id}")
                continue
            
            # Check if session has expired
            created_at = info.get("created_at", 0)
            age_seconds = current_time - created_at
            
            if age_seconds >= delay_seconds:
                expired[session_id] = info
                logger.debug(f"Session {session_id} expired (age: {age_seconds/60:.1f} minutes)")
        
        return expired
    
    def cleanup_tracked_session(self, session_id: str) -> bool:
        """Remove a session from tracking after cleanup.
        
        Args:
            session_id: The session ID to remove
            
        Returns:
            True if removal was successful
        """
        sessions = self._read_sessions()
        
        if session_id in sessions:
            del sessions[session_id]
            success = self._write_sessions(sessions)
            if success:
                logger.debug(f"Removed session {session_id} from tracker")
            return success
        
        return True  # Not an error if session wasn't tracked
    
    def get_all_tracked_sessions(self) -> Dict[str, Dict]:
        """Get all currently tracked sessions."""
        return self._read_sessions()
    
    def cleanup_stale_entries(self, max_age_hours: int = 5) -> int:
        """Remove stale entries that are very old (failsafe cleanup).
        
        Args:
            max_age_hours: Maximum age in hours before forced cleanup (default: 5 to match Claude Code sessions)
            
        Returns:
            Number of stale entries removed
        """
        sessions = self._read_sessions()
        current_time = time.time()
        max_age_seconds = max_age_hours * 3600
        
        stale_sessions = []
        for session_id, info in sessions.items():
            created_at = info.get("created_at", 0)
            age_seconds = current_time - created_at
            
            if age_seconds >= max_age_seconds:
                stale_sessions.append(session_id)
        
        # Remove stale entries
        for session_id in stale_sessions:
            del sessions[session_id]
        
        if stale_sessions:
            self._write_sessions(sessions)
            logger.info(f"Removed {len(stale_sessions)} stale tracker entries")
        
        return len(stale_sessions)
    
    def get_tracker_stats(self) -> Dict[str, any]:
        """Get statistics about tracked sessions."""
        sessions = self._read_sessions()
        current_time = time.time()
        
        if not sessions:
            return {
                "total_tracked": 0,
                "oldest_session_age_minutes": 0,
                "newest_session_age_minutes": 0,
                "average_age_minutes": 0
            }
        
        ages = []
        for info in sessions.values():
            created_at = info.get("created_at", current_time)
            age_minutes = (current_time - created_at) / 60
            ages.append(age_minutes)
        
        return {
            "total_tracked": len(sessions),
            "oldest_session_age_minutes": max(ages) if ages else 0,
            "newest_session_age_minutes": min(ages) if ages else 0,
            "average_age_minutes": sum(ages) / len(ages) if ages else 0
        }


# Global instance for convenience
_tracker_instance = None


def get_tracker() -> SandboxSessionTracker:
    """Get the global tracker instance."""
    global _tracker_instance
    if _tracker_instance is None:
        _tracker_instance = SandboxSessionTracker()
    return _tracker_instance


def scan_claude_projects_for_sandbox_sessions(older_than_minutes: int) -> List[Tuple[str, str, float]]:
    """Scan Claude projects directory for sandbox sessions older than specified time.
    
    This is used during startup to find sessions created before tracking was implemented.
    
    Args:
        older_than_minutes: Only return sessions older than this
        
    Returns:
        List of tuples: (session_id, project_dir, age_minutes)
    """
    claude_projects = Path.home() / ".claude" / "projects"
    if not claude_projects.exists():
        return []
    
    current_time = time.time()
    cutoff_seconds = older_than_minutes * 60
    sandbox_sessions = []
    
    try:
        # Look for directories with sandbox markers
        for project_dir in claude_projects.iterdir():
            if not project_dir.is_dir():
                continue
            
            # Check if this is a sandbox project directory
            dir_name = project_dir.name
            if "claude-chat-sandbox" not in dir_name:
                continue
            
            # Check session files in this directory
            for session_file in project_dir.glob("*.jsonl"):
                if not session_file.is_file():
                    continue
                
                # Get file modification time
                try:
                    mtime = session_file.stat().st_mtime
                    age_seconds = current_time - mtime
                    
                    if age_seconds >= cutoff_seconds:
                        session_id = session_file.stem  # Remove .jsonl extension
                        age_minutes = age_seconds / 60
                        sandbox_sessions.append((session_id, str(project_dir), age_minutes))
                        logger.info(f"Found old sandbox session: {session_id} in {project_dir} (age: {age_minutes:.1f} minutes)")
                except Exception as e:
                    logger.debug(f"Could not check session file {session_file}: {e}")
        
        logger.info(f"Found {len(sandbox_sessions)} old sandbox sessions for cleanup")
        return sandbox_sessions
        
    except Exception as e:
        logger.error(f"Error scanning Claude projects: {e}")
        return []