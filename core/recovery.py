"""
Crash recovery for agent workflows.

Handles detection and resumption of interrupted workflows after service restarts.
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .checkpointing import CheckpointManager
from .state import AgentState

logger = logging.getLogger(__name__)


class RecoveryManager:
    """
    Manages workflow recovery after crashes.
    
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
        incomplete_threads = self.checkpoint_manager.get_incomplete_threads(
            older_than_minutes=older_than_minutes
        )
        
        # Filter out threads that have exceeded max recovery attempts
        recoverable = [
            tid for tid in incomplete_threads
            if self.recovery_attempts.get(tid, 0) < self.max_recovery_attempts
        ]
        
        if recoverable:
            logger.warning(
                f"Found {len(recoverable)} potentially crashed threads: {recoverable}"
            )
        
        return recoverable
    
    def can_recover_thread(self, thread_id: str) -> tuple[bool, Optional[str]]:
        """
        Check if a thread can be recovered.
        
        Args:
            thread_id: Thread to check
        
        Returns:
            tuple: (can_recover, reason_if_not)
        """
        # Check recovery attempt limit
        if self.recovery_attempts.get(thread_id, 0) >= self.max_recovery_attempts:
            return False, f"Max recovery attempts ({self.max_recovery_attempts}) exceeded"
        
        # Validate checkpoint integrity
        is_valid, error_msg = self.checkpoint_manager.validate_checkpoint_integrity(thread_id)
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
            history = self.checkpoint_manager.get_thread_history(thread_id, limit=1)
            if not history:
                logger.error(f"No checkpoint history for thread {thread_id}")
                return None
            
            checkpoint_id = history[0]["checkpoint_id"]
            logger.info(f"Loading checkpoint {checkpoint_id} for thread {thread_id}")
            
            # Load from SqliteSaver (via LangGraph)
            # This is a simplified version - actual implementation depends on LangGraph API
            with self.checkpoint_manager._get_connection() as conn:
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
    
    def mark_recovery_attempt(self, thread_id: str, success: bool) -> None:
        """
        Record a recovery attempt.
        
        Args:
            thread_id: Thread being recovered
            success: Whether recovery succeeded
        """
        if success:
            self.recovery_attempts[thread_id] = 0
            logger.info(f"Recovery successful for thread {thread_id}")
        else:
            self.recovery_attempts[thread_id] = self.recovery_attempts.get(thread_id, 0) + 1
            attempts = self.recovery_attempts[thread_id]
            logger.warning(
                f"Recovery attempt {attempts}/{self.max_recovery_attempts} "
                f"failed for thread {thread_id}"
            )
    
    def get_recovery_report(self) -> Dict[str, Any]:
        """
        Get recovery statistics for observability.
        
        Returns:
            dict: Recovery metrics
        """
        return {
            "threads_being_recovered": len(self.recovery_attempts),
            "recovery_attempts": dict(self.recovery_attempts),
            "timestamp": datetime.utcnow().isoformat(),
        }
