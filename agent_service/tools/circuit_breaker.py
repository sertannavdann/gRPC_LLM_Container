"""
Production-grade circuit breaker implementation following Google ADK patterns.

This module provides time-based circuit breakers with exponential backoff,
half-open recovery, and configurable failure thresholds.
"""

import time
import logging
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field
from threading import Lock

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, requests blocked
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""
    failure_threshold: int = 3
    recovery_timeout: float = 60.0  # seconds
    expected_exception: tuple = (Exception,)
    success_threshold: int = 1  # successes needed in half-open
    backoff_multiplier: float = 2.0
    max_backoff: float = 300.0  # 5 minutes

    def __post_init__(self):
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if self.recovery_timeout <= 0:
            raise ValueError("recovery_timeout must be > 0")


@dataclass
class CircuitBreakerStats:
    """Runtime statistics for circuit breaker"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changes: int = 0


class CircuitBreaker:
    """
    Time-based circuit breaker with exponential backoff.

    Follows Google ADK patterns for reliability and observability.
    """

    def __init__(self, name: str, config: Optional[CircuitBreakerConfig] = None):
        """
        Initialize circuit breaker.

        Args:
            name: Unique identifier for this circuit breaker
            config: Configuration object (uses defaults if None)
        """
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.stats = CircuitBreakerStats()
        self._lock = Lock()
        self._backoff_time = self.config.recovery_timeout

        logger.info(f"CircuitBreaker '{name}' initialized: {self.config}")

    def call(self, func, *args, **kwargs) -> Any:
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result

        Raises:
            Exception: If circuit is open or function fails
        """
        with self._lock:
            if not self._should_allow_call():
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is {self.state.value}"
                )

            self.stats.total_calls += 1

        try:
            result = func(*args, **kwargs)

            with self._lock:
                self._record_success()
                logger.debug(f"CircuitBreaker '{self.name}': success")

            return result

        except self.config.expected_exception as e:
            with self._lock:
                self._record_failure()
                logger.warning(f"CircuitBreaker '{self.name}': failure - {e}")

            raise

    def _should_allow_call(self) -> bool:
        """Determine if call should be allowed based on current state"""
        now = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        elif self.state == CircuitState.OPEN:
            if self._is_recovery_timeout_expired(now):
                self._transition_to_half_open()
                return True
            return False

        elif self.state == CircuitState.HALF_OPEN:
            return True

        return False

    def _is_recovery_timeout_expired(self, now: float) -> bool:
        """Check if recovery timeout has expired"""
        if self.stats.last_failure_time is None:
            return True
        return (now - self.stats.last_failure_time) >= self._backoff_time

    def _record_success(self):
        """Record successful call and update state"""
        self.stats.successful_calls += 1
        self.stats.consecutive_successes += 1
        self.stats.consecutive_failures = 0
        self.stats.last_success_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            if self.stats.consecutive_successes >= self.config.success_threshold:
                self._transition_to_closed()

    def _record_failure(self):
        """Record failed call and update state"""
        self.stats.failed_calls += 1
        self.stats.consecutive_failures += 1
        self.stats.consecutive_successes = 0
        self.stats.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
        elif (self.state == CircuitState.CLOSED and
              self.stats.consecutive_failures >= self.config.failure_threshold):
            self._transition_to_open()

    def _transition_to_open(self):
        """Transition to OPEN state with exponential backoff"""
        old_state = self.state
        self.state = CircuitState.OPEN
        self.stats.state_changes += 1

        # Exponential backoff
        self._backoff_time = min(
            self._backoff_time * self.config.backoff_multiplier,
            self.config.max_backoff
        )

        logger.info(
            f"CircuitBreaker '{self.name}': {old_state.value} → {self.state.value} "
            f"(backoff: {self._backoff_time:.1f}s)"
        )

    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        old_state = self.state
        self.state = CircuitState.HALF_OPEN
        self.stats.state_changes += 1
        self.stats.consecutive_successes = 0

        logger.info(f"CircuitBreaker '{self.name}': {old_state.value} → {self.state.value}")

    def _transition_to_closed(self):
        """Transition to CLOSED state and reset backoff"""
        old_state = self.state
        self.state = CircuitState.CLOSED
        self.stats.state_changes += 1
        self.stats.consecutive_failures = 0
        self._backoff_time = self.config.recovery_timeout

        logger.info(f"CircuitBreaker '{self.name}': {old_state.value} → {self.state.value}")

    def reset(self):
        """Manually reset circuit breaker to CLOSED state"""
        with self._lock:
            old_state = self.state
            self.state = CircuitState.CLOSED
            self.stats = CircuitBreakerStats()
            self._backoff_time = self.config.recovery_timeout

            logger.info(f"CircuitBreaker '{self.name}': manually reset {old_state.value} → {self.state.value}")

    def get_stats(self) -> Dict[str, Any]:
        """Get current statistics"""
        return {
            "name": self.name,
            "state": self.state.value,
            "config": {
                "failure_threshold": self.config.failure_threshold,
                "recovery_timeout": self.config.recovery_timeout,
                "backoff_multiplier": self.config.backoff_multiplier,
                "max_backoff": self.config.max_backoff
            },
            "stats": {
                "total_calls": self.stats.total_calls,
                "successful_calls": self.stats.successful_calls,
                "failed_calls": self.stats.failed_calls,
                "consecutive_failures": self.stats.consecutive_failures,
                "consecutive_successes": self.stats.consecutive_successes,
                "last_failure_time": self.stats.last_failure_time,
                "last_success_time": self.stats.last_success_time,
                "state_changes": self.stats.state_changes,
                "current_backoff": self._backoff_time
            }
        }


class CircuitBreakerOpenException(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.

    Provides centralized management and monitoring of circuit breakers.
    """

    def __init__(self):
        self.breakers: Dict[str, CircuitBreaker] = {}
        self._lock = Lock()

    def get_or_create(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get existing circuit breaker or create new one"""
        with self._lock:
            if name not in self.breakers:
                self.breakers[name] = CircuitBreaker(name, config)
            return self.breakers[name]

    def get_all_stats(self) -> Dict[str, Dict[str, Any]]:
        """Get statistics for all circuit breakers"""
        with self._lock:
            return {name: cb.get_stats() for name, cb in self.breakers.items()}

    def reset_all(self):
        """Reset all circuit breakers"""
        with self._lock:
            for cb in self.breakers.values():
                cb.reset()

    def reset_breaker(self, name: str):
        """Reset specific circuit breaker"""
        with self._lock:
            if name in self.breakers:
                self.breakers[name].reset()
