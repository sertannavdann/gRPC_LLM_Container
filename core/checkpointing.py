"""
SQLite-based checkpointing for conversation persistence.

Wraps LangGraph's SqliteSaver with convenience methods for managing
conversation threads, checkpoints, and state recovery.
"""

import logging
import sqlite3
from pathlib import Path
from typing import Optional
from contextlib import contextmanager

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
