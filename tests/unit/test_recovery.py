"""Unit tests for RecoveryManager."""

import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "core"))

from recovery import RecoveryManager


class TestRecoveryManager:
    """Test recovery manager logic."""
    
    @pytest.fixture
    def mock_checkpoint_manager(self):
        """Mock checkpoint manager."""
        manager = Mock()
        manager.get_incomplete_threads.return_value = ["thread-1", "thread-2"]
        manager.validate_checkpoint_integrity.return_value = (True, None)
        manager.get_thread_history.return_value = [{"checkpoint_id": "cp-1"}]
        return manager
    
    @pytest.fixture
    def recovery_manager(self, mock_checkpoint_manager):
        """Create recovery manager with mocked checkpoint manager."""
        return RecoveryManager(mock_checkpoint_manager)
    
    def test_scan_for_crashed_threads(self, recovery_manager, mock_checkpoint_manager):
        """Test scanning for crashed threads."""
        threads = recovery_manager.scan_for_crashed_threads(older_than_minutes=5)
        
        assert len(threads) == 2
        assert "thread-1" in threads
        assert "thread-2" in threads
        mock_checkpoint_manager.get_incomplete_threads.assert_called_once_with(
            older_than_minutes=5
        )
    
    def test_scan_filters_max_attempts(self, recovery_manager, mock_checkpoint_manager):
        """Test that threads exceeding max attempts are filtered out."""
        # Mark thread-1 as having max attempts
        recovery_manager.recovery_attempts["thread-1"] = 3
        
        threads = recovery_manager.scan_for_crashed_threads(older_than_minutes=5)
        
        # Only thread-2 should be returned
        assert len(threads) == 1
        assert "thread-2" in threads
        assert "thread-1" not in threads
    
    def test_can_recover_thread_success(self, recovery_manager, mock_checkpoint_manager):
        """Test successful recovery check."""
        can_recover, reason = recovery_manager.can_recover_thread("thread-1")
        
        assert can_recover is True
        assert reason is None
        mock_checkpoint_manager.validate_checkpoint_integrity.assert_called_once_with("thread-1")
    
    def test_can_recover_thread_max_attempts(self, recovery_manager):
        """Test recovery blocked after max attempts."""
        recovery_manager.recovery_attempts["thread-1"] = 3
        
        can_recover, reason = recovery_manager.can_recover_thread("thread-1")
        
        assert can_recover is False
        assert "Max recovery attempts" in reason
    
    def test_can_recover_thread_validation_failure(self, recovery_manager, mock_checkpoint_manager):
        """Test recovery blocked when checkpoint validation fails."""
        mock_checkpoint_manager.validate_checkpoint_integrity.return_value = (
            False, "Checkpoint is corrupted"
        )
        
        can_recover, reason = recovery_manager.can_recover_thread("thread-1")
        
        assert can_recover is False
        assert "Checkpoint validation failed" in reason
        assert "corrupted" in reason
    
    def test_load_checkpoint_state_success(self, recovery_manager, mock_checkpoint_manager):
        """Test successful checkpoint loading."""
        # Mock database connection
        mock_conn = Mock()
        mock_cursor = Mock()
        import pickle
        test_state = {"messages": ["hello"], "tool_results": []}
        mock_cursor.fetchone.return_value = (pickle.dumps(test_state),)
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        
        mock_checkpoint_manager._get_connection.return_value = mock_conn
        
        state = recovery_manager.load_checkpoint_state("thread-1")
        
        assert state is not None
        assert state["messages"] == ["hello"]
        assert state["tool_results"] == []
    
    def test_load_checkpoint_state_no_history(self, recovery_manager, mock_checkpoint_manager):
        """Test checkpoint loading fails when no history exists."""
        mock_checkpoint_manager.get_thread_history.return_value = []
        
        state = recovery_manager.load_checkpoint_state("thread-1")
        
        assert state is None
    
    def test_load_checkpoint_state_exception(self, recovery_manager, mock_checkpoint_manager):
        """Test checkpoint loading handles exceptions gracefully."""
        mock_checkpoint_manager.get_thread_history.side_effect = Exception("DB error")
        
        state = recovery_manager.load_checkpoint_state("thread-1")
        
        assert state is None
    
    def test_mark_recovery_attempt_success(self, recovery_manager):
        """Test marking successful recovery attempt."""
        # Set some failed attempts first
        recovery_manager.recovery_attempts["thread-1"] = 2
        
        # Mark as successful
        recovery_manager.mark_recovery_attempt("thread-1", success=True)
        
        # Should reset to 0
        assert recovery_manager.recovery_attempts["thread-1"] == 0
    
    def test_mark_recovery_attempt_failure(self, recovery_manager):
        """Test marking failed recovery attempt."""
        # First failure
        recovery_manager.mark_recovery_attempt("thread-1", success=False)
        assert recovery_manager.recovery_attempts["thread-1"] == 1
        
        # Second failure
        recovery_manager.mark_recovery_attempt("thread-1", success=False)
        assert recovery_manager.recovery_attempts["thread-1"] == 2
        
        # Third failure
        recovery_manager.mark_recovery_attempt("thread-1", success=False)
        assert recovery_manager.recovery_attempts["thread-1"] == 3
    
    def test_get_recovery_report(self, recovery_manager):
        """Test getting recovery report."""
        recovery_manager.recovery_attempts["thread-1"] = 2
        recovery_manager.recovery_attempts["thread-2"] = 1
        
        report = recovery_manager.get_recovery_report()
        
        assert report["threads_being_recovered"] == 2
        assert report["recovery_attempts"]["thread-1"] == 2
        assert report["recovery_attempts"]["thread-2"] == 1
        assert "timestamp" in report
    
    def test_max_recovery_attempts_default(self, recovery_manager):
        """Test that max recovery attempts defaults to 3."""
        assert recovery_manager.max_recovery_attempts == 3
    
    def test_recovery_manager_initialization(self, mock_checkpoint_manager):
        """Test recovery manager initializes correctly."""
        manager = RecoveryManager(mock_checkpoint_manager)
        
        assert manager.checkpoint_manager == mock_checkpoint_manager
        assert manager.recovery_attempts == {}
        assert manager.max_recovery_attempts == 3


class TestRecoveryEdgeCases:
    """Test edge cases and error scenarios."""
    
    @pytest.fixture
    def mock_checkpoint_manager(self):
        """Mock checkpoint manager."""
        manager = Mock()
        return manager
    
    @pytest.fixture
    def recovery_manager(self, mock_checkpoint_manager):
        """Create recovery manager."""
        return RecoveryManager(mock_checkpoint_manager)
    
    def test_empty_crashed_threads_list(self, recovery_manager, mock_checkpoint_manager):
        """Test handling empty crashed threads list."""
        mock_checkpoint_manager.get_incomplete_threads.return_value = []
        
        threads = recovery_manager.scan_for_crashed_threads()
        
        assert threads == []
    
    def test_multiple_recovery_cycles(self, recovery_manager):
        """Test multiple recovery cycles for same thread."""
        # Cycle 1: Fail
        recovery_manager.mark_recovery_attempt("thread-1", success=False)
        assert recovery_manager.recovery_attempts["thread-1"] == 1
        
        # Cycle 2: Fail
        recovery_manager.mark_recovery_attempt("thread-1", success=False)
        assert recovery_manager.recovery_attempts["thread-1"] == 2
        
        # Cycle 3: Success
        recovery_manager.mark_recovery_attempt("thread-1", success=True)
        assert recovery_manager.recovery_attempts["thread-1"] == 0
        
        # Cycle 4: Can try again after success
        recovery_manager.mark_recovery_attempt("thread-1", success=False)
        assert recovery_manager.recovery_attempts["thread-1"] == 1
