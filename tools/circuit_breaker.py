"""
Circuit breaker pattern for tool reliability.

Automatically disables tools after repeated failures, preventing
cascading failures and excessive retries. Follows production-grade
patterns from distributed systems.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CircuitBreaker:
    """
    Circuit breaker for tool execution following the three-state pattern.
    
    States:
    - CLOSED: Normal operation, all requests allowed
    - OPEN: Failing state, all requests rejected immediately
    - HALF_OPEN: Testing state, limited requests allowed
    
    The circuit opens after max_failures consecutive errors within the
    failure_window. After reset_timeout, it enters HALF_OPEN state for testing.
    
    Attributes:
        max_failures: Number of failures before circuit opens (default: 3)
        failure_window: Time window for counting failures (default: 5 minutes)
        reset_timeout: Time before attempting recovery (default: 1 minute)
    
    Example:
        >>> breaker = CircuitBreaker(max_failures=3)
        >>> if breaker.is_available():
        ...     try:
        ...         result = execute_tool()
        ...         breaker.record_success()
        ...     except Exception:
        ...         breaker.record_failure()
    """
    
    max_failures: int = 3
    failure_window: timedelta = field(default_factory=lambda: timedelta(minutes=5))
    reset_timeout: timedelta = field(default_factory=lambda: timedelta(minutes=1))
    
    # Internal state (not part of public API)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: Optional[datetime] = field(default=None, init=False)
    _opened_at: Optional[datetime] = field(default=None, init=False)
    _is_open: bool = field(default=False, init=False)
    
    def record_failure(self):
        """
        Record a tool execution failure.
        
        Increments failure counter and checks if circuit should open.
        Failures outside the failure_window are ignored.
        """
        now = datetime.now()
        
        # Reset counter if outside failure window
        if (
            self._last_failure_time
            and now - self._last_failure_time > self.failure_window
        ):
            logger.debug("Failure window expired, resetting counter")
            self._failure_count = 0
        
        self._failure_count += 1
        self._last_failure_time = now
        
        logger.warning(
            f"Circuit breaker recorded failure {self._failure_count}/{self.max_failures}"
        )
        
        # Open circuit if threshold reached
        if self._failure_count >= self.max_failures:
            self._open_circuit()
    
    def record_success(self):
        """
        Record a successful tool execution.
        
        Resets failure counter and closes circuit if in HALF_OPEN state.
        """
        if self._is_open:
            logger.info("Circuit breaker: Successful execution in HALF_OPEN state, closing circuit")
        
        self._failure_count = 0
        self._last_failure_time = None
        self._opened_at = None
        self._is_open = False
    
    def is_available(self) -> bool:
        """
        Check if tool is available for execution.
        
        Returns:
            bool: True if circuit is CLOSED or HALF_OPEN, False if OPEN
        """
        if not self._is_open:
            return True
        
        # Check if reset timeout has elapsed (transition to HALF_OPEN)
        now = datetime.now()
        if self._opened_at and now - self._opened_at > self.reset_timeout:
            logger.info("Circuit breaker: Entering HALF_OPEN state for testing")
            self._is_open = False  # Allow one request
            return True
        
        return False
    
    def _open_circuit(self):
        """Transition circuit to OPEN state."""
        if not self._is_open:
            self._is_open = True
            self._opened_at = datetime.now()
            logger.error(
                f"Circuit breaker OPENED after {self._failure_count} failures"
            )
    
    def reset(self):
        """
        Manually reset circuit breaker to CLOSED state.
        
        Use this for administrative recovery or after fixing underlying issues.
        """
        self._failure_count = 0
        self._last_failure_time = None
        self._opened_at = None
        self._is_open = False
        logger.info("Circuit breaker manually reset to CLOSED state")
    
    @property
    def state(self) -> str:
        """
        Get current circuit state.
        
        Returns:
            str: "CLOSED", "OPEN", or "HALF_OPEN"
        """
        if not self._is_open:
            return "CLOSED"
        
        if self._opened_at and datetime.now() - self._opened_at > self.reset_timeout:
            return "HALF_OPEN"
        
        return "OPEN"
    
    def get_metrics(self) -> dict:
        """
        Get circuit breaker metrics for monitoring.
        
        Returns:
            dict: Metrics including state, failure count, and timing info
        """
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "max_failures": self.max_failures,
            "last_failure": self._last_failure_time.isoformat() if self._last_failure_time else None,
            "opened_at": self._opened_at.isoformat() if self._opened_at else None,
            "is_available": self.is_available(),
        }
