"""
SQLite-based checkpointing and crash recovery for conversation persistence.

Wraps LangGraph's SqliteSaver with convenience methods for managing
conversation threads, checkpoints, state recovery, and crash detection.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
from contextlib import contextmanager
from datetime import datetime, timezone

from langgraph.checkpoint.sqlite import SqliteSaver

logger = logging.getLogger(__name__)


class CheckpointManager:
    """
    Manages SQLite checkpoints for conversation persistence.
    
    Provides high-level API for:
    - Creating checkpointers with connection pooling
    - Listing conversation threads
    - Retrieving checkpoint history
    - Cleaning up old conversations
    
    Example:
        >>> manager = CheckpointManager("agent_memory.db")
        >>> checkpointer = manager.create_checkpointer()
        >>> app = workflow.compile(checkpointer)
    """
    
    def __init__(self, db_path: str = "agent_memory.sqlite"):
        """
        Initialize checkpoint manager with SQLite database.
        
        Args:
            db_path: Path to SQLite database file (created if not exists)
        """
        self.db_path = Path(db_path)
        self._ensure_db_exists()
        self.setup_status_table()
        
        logger.info(f"CheckpointManager initialized: {self.db_path}")
    
    def _ensure_db_exists(self):
        """Create database file and parent directories if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.db_path.exists():
            # Create empty database
            conn = sqlite3.connect(str(self.db_path))
            conn.close()
            logger.info(f"Created new checkpoint database: {self.db_path}")
    
    def create_checkpointer(self):
        """
        Create SqliteSaver for use with compiled LangGraph.
        
        Returns:
            SqliteSaver: Checkpointer instance ready for graph compilation
        
        Example:
            >>> checkpointer = manager.create_checkpointer()
            >>> app = workflow.compile(checkpointer)
            >>> app.invoke(state, config={"thread_id": "conv-123"})
        """
        # Create a persistent connection with thread safety disabled
        # This is safe in gRPC since each request gets its own thread
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for concurrency
        
        # Create SqliteSaver with the persistent connection
        checkpointer = SqliteSaver(conn=conn)
        
        # Initialize database tables
        checkpointer.setup()
        logger.debug(f"Created checkpointer for {self.db_path}")
        return checkpointer
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            yield conn
        finally:
            conn.close()
    
    def list_threads(self, limit: int = 100) -> list[dict]:
        """
        List recent conversation threads.
        
        Args:
            limit: Maximum number of threads to return
        
        Returns:
            list[dict]: Thread metadata with IDs and timestamps
        
        Example:
            >>> threads = manager.list_threads(limit=10)
            >>> for thread in threads:
            ...     print(f"{thread['thread_id']}: {thread['last_updated']}")
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT DISTINCT thread_id, MAX(timestamp) as last_updated
                FROM checkpoints
                GROUP BY thread_id
                ORDER BY last_updated DESC
                LIMIT ?
                """,
                (limit,),
            )
            
            threads = [
                {"thread_id": row[0], "last_updated": row[1]}
                for row in cursor.fetchall()
            ]
            
            logger.debug(f"Listed {len(threads)} conversation threads")
            return threads
    
    def get_thread_history(self, thread_id: str, limit: int = 50) -> list[dict]:
        """
        Retrieve checkpoint history for a conversation thread.
        
        Args:
            thread_id: Conversation identifier
            limit: Maximum checkpoints to return
        
        Returns:
            list[dict]: Checkpoint metadata ordered by timestamp
        
        Example:
            >>> history = manager.get_thread_history("conv-123")
            >>> print(f"Found {len(history)} checkpoints")
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT checkpoint_id, thread_id, timestamp, parent_id
                FROM checkpoints
                WHERE thread_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (thread_id, limit),
            )
            
            history = [
                {
                    "checkpoint_id": row[0],
                    "thread_id": row[1],
                    "timestamp": row[2],
                    "parent_id": row[3],
                }
                for row in cursor.fetchall()
            ]
            
            logger.debug(f"Retrieved {len(history)} checkpoints for thread {thread_id}")
            return history
    
    def delete_thread(self, thread_id: str):
        """
        Delete all checkpoints for a conversation thread.
        
        Args:
            thread_id: Conversation identifier to delete
        
        Example:
            >>> manager.delete_thread("conv-123")
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                "DELETE FROM checkpoints WHERE thread_id = ?",
                (thread_id,),
            )
            conn.commit()
            
            deleted_count = cursor.rowcount
            logger.info(f"Deleted {deleted_count} checkpoints for thread {thread_id}")
    
    def cleanup_old_threads(self, days: int = 30) -> int:
        """
        Remove conversation threads older than specified days.
        
        Args:
            days: Age threshold in days (threads older than this are deleted)
        
        Returns:
            int: Number of checkpoints deleted
        
        Example:
            >>> deleted = manager.cleanup_old_threads(days=7)
            >>> print(f"Cleaned up {deleted} old checkpoints")
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM checkpoints
                WHERE timestamp < datetime('now', ? || ' days')
                """,
                (-days,),
            )
            conn.commit()
            
            deleted_count = cursor.rowcount
            logger.info(f"Cleaned up {deleted_count} checkpoints older than {days} days")
            return deleted_count
    
    def get_database_size(self) -> int:
        """
        Get size of checkpoint database in bytes.
        
        Returns:
            int: Database file size in bytes
        """
        size = self.db_path.stat().st_size
        logger.debug(f"Database size: {size / 1024:.2f} KB")
        return size
    
    def vacuum(self):
        """
        Compact database to reclaim space after deletions.
        
        Should be called after cleanup_old_threads() or delete_thread()
        to actually free disk space.
        
        Example:
            >>> manager.cleanup_old_threads(days=7)
            >>> manager.vacuum()
        """
        with self._get_connection() as conn:
            conn.execute("VACUUM")
            logger.info("Database vacuumed successfully")
    
    def setup_status_table(self) -> None:
        """Create thread_status table if it doesn't exist."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS thread_status (
                    thread_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    last_updated DATETIME NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_status_updated ON thread_status(status, last_updated)"
            )
            conn.commit()
            logger.debug("Thread status table setup complete")
    
    def validate_checkpoint_integrity(self, thread_id: str) -> tuple[bool, Optional[str]]:
        """
        Validate checkpoint data integrity for a thread.
        
        Args:
            thread_id: Thread to validate
        
        Returns:
            tuple: (is_valid, error_message)
        """
        try:
            with self._get_connection() as conn:
                # Check if checkpoints table exists
                cursor = conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='checkpoints'"
                )
                if not cursor.fetchone():
                    return False, "Checkpoints table does not exist"
                
                # Get latest checkpoint
                cursor = conn.execute(
                    """
                    SELECT checkpoint_id, checkpoint, metadata
                    FROM checkpoints
                    WHERE thread_id = ?
                    ORDER BY timestamp DESC
                    LIMIT 1
                    """,
                    (thread_id,),
                )
                
                row = cursor.fetchone()
                if not row:
                    return False, f"No checkpoints found for thread {thread_id}"
                
                checkpoint_id, checkpoint_data, metadata = row
                
                # Validate checkpoint data is not null
                if checkpoint_data is None:
                    return False, f"Checkpoint {checkpoint_id} has null data"
                
                # Try to deserialize checkpoint (basic validation)
                try:
                    import pickle
                    pickle.loads(checkpoint_data)
                except Exception as e:
                    return False, f"Checkpoint {checkpoint_id} is corrupted: {e}"
                
                return True, None
                
        except Exception as e:
            return False, f"Validation error: {e}"
    
    def mark_thread_incomplete(self, thread_id: str) -> None:
        """
        Mark a thread as incomplete (workflow in progress).
        
        Used to track threads that may need recovery after crash.
        """
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO thread_status (thread_id, status, last_updated)
                VALUES (?, 'incomplete', datetime('now'))
                """,
                (thread_id,),
            )
            conn.commit()
            logger.debug(f"Marked thread {thread_id} as incomplete")
    
    def mark_thread_complete(self, thread_id: str) -> None:
        """Mark a thread as complete (workflow finished)."""
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO thread_status (thread_id, status, last_updated)
                VALUES (?, 'complete', datetime('now'))
                """,
                (thread_id,),
            )
            conn.commit()
            logger.debug(f"Marked thread {thread_id} as complete")
    
    def get_incomplete_threads(self, older_than_minutes: int = 5) -> list[str]:
        """
        Get threads that were incomplete and potentially crashed.
        
        Args:
            older_than_minutes: Consider threads incomplete if last updated more than N minutes ago
        
        Returns:
            list: Thread IDs that may need recovery
        """
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT thread_id
                FROM thread_status
                WHERE status = 'incomplete'
                AND last_updated < datetime('now', ? || ' minutes')
                ORDER BY last_updated DESC
                """,
                (-older_than_minutes,),
            )
            return [row[0] for row in cursor.fetchall()]
    
    def flush_wal(self) -> None:
        """
        Force WAL checkpoint to disk.
        
        Should be called after critical operations to ensure durability.
        """
        with self._get_connection() as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            logger.debug("WAL checkpoint flushed to disk")
    
    def get_wal_info(self) -> dict:
        """Get WAL file information for diagnostics."""
        with self._get_connection() as conn:
            cursor = conn.execute("PRAGMA wal_checkpoint")
            busy, log, checkpointed = cursor.fetchone()
            return {
                "wal_mode": "enabled",
                "busy": busy,
                "log_size": log,
                "checkpointed_frames": checkpointed,
            }
    
    # ========================================================================
    # Crash Recovery Methods (merged from recovery.py)
    # ========================================================================
    
    def scan_for_crashed_threads(
        self, 
        older_than_minutes: int = 5,
        max_recovery_attempts: int = 3,
        recovery_attempts: Optional[Dict[str, int]] = None
    ) -> list[str]:
        """
        Scan for threads that may have crashed.
        
        Args:
            older_than_minutes: Consider threads crashed if inactive for N minutes
            max_recovery_attempts: Maximum recovery attempts per thread
            recovery_attempts: Dict tracking recovery attempts (thread_id -> count)
        
        Returns:
            list: Thread IDs that need recovery
        """
        if recovery_attempts is None:
            recovery_attempts = {}
            
        incomplete_threads = self.get_incomplete_threads(
            older_than_minutes=older_than_minutes
        )
        
        # Filter out threads that have exceeded max recovery attempts
        recoverable = [
            tid for tid in incomplete_threads
            if recovery_attempts.get(tid, 0) < max_recovery_attempts
        ]
        
        if recoverable:
            logger.warning(
                f"Found {len(recoverable)} potentially crashed threads: {recoverable}"
            )
        
        return recoverable
    
    def can_recover_thread(
        self, 
        thread_id: str,
        max_recovery_attempts: int = 3,
        recovery_attempts: Optional[Dict[str, int]] = None
    ) -> tuple[bool, Optional[str]]:
        """
        Check if a thread can be recovered.
        
        Args:
            thread_id: Thread to check
            max_recovery_attempts: Maximum recovery attempts allowed
            recovery_attempts: Dict tracking recovery attempts
        
        Returns:
            tuple: (can_recover, reason_if_not)
        """
        if recovery_attempts is None:
            recovery_attempts = {}
            
        # Check recovery attempt limit
        if recovery_attempts.get(thread_id, 0) >= max_recovery_attempts:
            return False, f"Max recovery attempts ({max_recovery_attempts}) exceeded"
        
        # Validate checkpoint integrity
        is_valid, error_msg = self.validate_checkpoint_integrity(thread_id)
        if not is_valid:
            return False, f"Checkpoint validation failed: {error_msg}"
        
        return True, None
    
    def load_checkpoint_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Load the last checkpoint state for a thread.
        
        Args:
            thread_id: Thread to recover
        
        Returns:
            dict: Checkpoint state, or None if loading fails
        """
        try:
            # Get checkpoint history
            history = self.get_thread_history(thread_id, limit=1)
            if not history:
                logger.error(f"No checkpoint history for thread {thread_id}")
                return None
            
            checkpoint_id = history[0]["checkpoint_id"]
            logger.info(f"Loading checkpoint {checkpoint_id} for thread {thread_id}")
            
            # Load from SqliteSaver (via LangGraph)
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT checkpoint FROM checkpoints WHERE checkpoint_id = ?",
                    (checkpoint_id,),
                )
                row = cursor.fetchone()
                if not row:
                    return None
                
                import pickle
                state = pickle.loads(row[0])
                return state
                
        except Exception as e:
            logger.error(f"Failed to load checkpoint for {thread_id}: {e}")
            return None
    
    @staticmethod
    def mark_recovery_attempt(
        thread_id: str, 
        success: bool,
        recovery_attempts: Dict[str, int]
    ) -> None:
        """
        Record a recovery attempt.
        
        Args:
            thread_id: Thread being recovered
            success: Whether recovery succeeded
            recovery_attempts: Dict to update with attempt count
        """
        if success:
            recovery_attempts[thread_id] = 0
            logger.info(f"Recovery successful for thread {thread_id}")
        else:
            recovery_attempts[thread_id] = recovery_attempts.get(thread_id, 0) + 1
            attempts = recovery_attempts[thread_id]
            logger.warning(
                f"Recovery attempt {attempts} failed for thread {thread_id}"
            )
    
    @staticmethod
    def get_recovery_report(recovery_attempts: Dict[str, int]) -> Dict[str, Any]:
        """
        Get recovery statistics for observability.
        
        Args:
            recovery_attempts: Dict tracking recovery attempts
        
        Returns:
            dict: Recovery metrics
        """
        return {
            "threads_being_recovered": len(recovery_attempts),
            "recovery_attempts": dict(recovery_attempts),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class RecoveryManager:
    """
    Manages workflow recovery after crashes.
    
    This is a convenience wrapper around CheckpointManager that maintains
    instance state for recovery attempt tracking.
    
    Responsibilities:
    - Detect crashed workflows on startup
    - Load last checkpoint
    - Resume workflow execution
    - Handle recovery failures
    """
    
    def __init__(self, checkpoint_manager: CheckpointManager):
        self.checkpoint_manager = checkpoint_manager
        self.recovery_attempts = {}  # thread_id -> attempt_count
        self.max_recovery_attempts = 3
    
    def scan_for_crashed_threads(self, older_than_minutes: int = 5) -> list[str]:
        """
        Scan for threads that may have crashed.
        
        Args:
            older_than_minutes: Consider threads crashed if inactive for N minutes
        
        Returns:
            list: Thread IDs that need recovery
        """
        return self.checkpoint_manager.scan_for_crashed_threads(
            older_than_minutes=older_than_minutes,
            max_recovery_attempts=self.max_recovery_attempts,
            recovery_attempts=self.recovery_attempts
        )
    
    def can_recover_thread(self, thread_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if a thread can be recovered.
        
        Args:
            thread_id: Thread to check
        
        Returns:
            tuple: (can_recover, reason_if_not)
        """
        return self.checkpoint_manager.can_recover_thread(
            thread_id=thread_id,
            max_recovery_attempts=self.max_recovery_attempts,
            recovery_attempts=self.recovery_attempts
        )
    
    def load_checkpoint_state(self, thread_id: str) -> Optional[Dict[str, Any]]:
        """
        Load the last checkpoint state for a thread.
        
        Args:
            thread_id: Thread to recover
        
        Returns:
            dict: Checkpoint state, or None if loading fails
        """
        return self.checkpoint_manager.load_checkpoint_state(thread_id)
    
    def mark_recovery_attempt(self, thread_id: str, success: bool) -> None:
        """
        Record a recovery attempt.
        
        Args:
            thread_id: Thread being recovered
            success: Whether recovery succeeded
        """
        CheckpointManager.mark_recovery_attempt(
            thread_id=thread_id,
            success=success,
            recovery_attempts=self.recovery_attempts
        )
    
    def get_recovery_report(self) -> Dict[str, Any]:
        """
        Get recovery statistics for observability.
        
        Returns:
            dict: Recovery metrics
        """
        return CheckpointManager.get_recovery_report(self.recovery_attempts)
